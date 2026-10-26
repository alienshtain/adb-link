"""Files page (browse the phone's storage)."""
from __future__ import annotations

import posixpath
import re
import shlex
from . import compat
from gi.repository import GLib, Gdk, Gtk, Pango
from .adbutil import adb, first_line, fmt_size
from .preview import icon_for, kind_of, open_preview
from .ui import (
    PromptWindow,
    button_content,
    choose_path,
    clear_children,
    confirm_dialog,
    make_icon,
)


# ---------------------------------------------------------------- files page

LS_NEW = re.compile(r"^([-dlbcps])\S{9}[+.@]?\s+\d+\s+\S+\s+\S+\s+(\d+)\s+(\d{4}-\d\d-\d\d)\s+(\d\d:\d\d)\s+(.+)$")
LS_OLD = re.compile(r"^([-dlbcps])\S{9}[+.@]?\s+\S+\s+\S+\s+(\d{4}-\d\d-\d\d)\s+(\d\d:\d\d)\s+(.+)$")


def parse_ls(text):
    """Parse `ls -lA` output from Android (both the new and the older layout)."""
    entries = []
    for line in text.splitlines():
        m = LS_NEW.match(line)
        if m:
            kind, size, date, clock, name = m.groups()
            size = int(size)
        else:
            m = LS_OLD.match(line)
            if not m:
                continue
            (kind, date, clock, name), size = m.groups(), None
        name = name.split(" -> ")[0]
        if name not in (".", ".."):
            entries.append({"name": name, "dir": kind in "dl", "size": size, "date": f"{date} {clock}"})
    return entries


class FileRow(Gtk.ListBoxRow):
    def __init__(self, entry):
        super().__init__()
        self.entry = entry
        box = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=10, margin_end=10)
        box.append(make_icon(icon_for(entry), 20))
        box.append(Gtk.Label(label=entry["name"], xalign=0, hexpand=True,
                             ellipsize=Pango.EllipsizeMode.MIDDLE))
        size = "" if entry["dir"] or entry["size"] is None else fmt_size(entry["size"])
        box.append(Gtk.Label(label=size, xalign=1, width_chars=9, css_classes=["dim-label"]))
        box.append(Gtk.Label(label=entry["date"], xalign=1, width_chars=16, css_classes=["dim-label"]))
        self.set_child(box)


class FilesPage(Gtk.Box):
    HOME = "/sdcard"

    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win, self.path, self.needs_reload, self.busy = win, self.HOME, True, False

        nav = Gtk.Box(spacing=6, margin_top=8, margin_start=12, margin_end=12)
        home = Gtk.Button(icon_name="go-home-symbolic", tooltip_text="Phone storage")
        home.connect("clicked", lambda _b: self.reload(self.HOME))
        up = Gtk.Button(icon_name="go-up-symbolic", tooltip_text="Parent folder")
        up.connect("clicked", lambda _b: self.reload(posixpath.dirname(self.path.rstrip("/")) or "/"))
        self.entry = Gtk.Entry(hexpand=True, text=self.path)
        self.entry.connect("activate", lambda e: self.reload(posixpath.normpath(e.get_text().strip() or "/")))
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Reload")
        refresh.connect("clicked", lambda _b: self.reload())
        self.hidden = Gtk.ToggleButton(icon_name="view-reveal-symbolic", tooltip_text="Show hidden files")
        self.hidden.connect("toggled", lambda _b: self.listbox.invalidate_filter())
        for w in (home, up, self.entry, refresh, self.hidden):
            nav.append(w)
        self.append(nav)

        acts = Gtk.Box(spacing=6, margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
        for icon, label, handler, css in (
                ("folder-download-symbolic", "Download", self.download, ["suggested-action"]),
                ("document-send-symbolic", "Upload files", self.upload_files, []),
                ("folder-new-symbolic", "Upload folder", self.upload_folder, []),
                ("list-add-symbolic", "New folder", self.new_folder, []),
                ("user-trash-symbolic", "Delete", self.delete, ["destructive-action"])):
            btn = button_content(icon, label, css)
            btn.connect("clicked", handler)
            acts.append(btn)
        self.append(acts)

        self.placeholder = Gtk.Label(margin_top=30, margin_bottom=30, css_classes=["dim-label"])
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE,
                                   activate_on_single_click=False, css_classes=["rich-list"])
        self.listbox.set_placeholder(self.placeholder)
        self.listbox.set_filter_func(
            lambda row: self.hidden.get_active() or not row.entry["name"].startswith("."))
        self.listbox.connect("row-activated", self._on_activate)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(self.listbox)
        self.append(scroller)

        foot = Gtk.Box(spacing=8, margin_top=4, margin_bottom=6, margin_start=12, margin_end=12)
        self.spinner = Gtk.Spinner()
        self.status = Gtk.Label(xalign=0, css_classes=["dim-label", "caption"],
                                label="Double-click a folder to open it, or a picture / text file to preview it. Drag files here to upload.")
        foot.append(self.spinner)
        foot.append(self.status)
        self.append(foot)

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.add_controller(drop)

    # ---- browsing
    def reload(self, path=None):
        if path is not None:
            self.path = path
        self.needs_reload = False
        self.entry.set_text(self.path)
        self.placeholder.set_text("Loading...")
        clear_children(self.listbox)
        target = self.path
        self.win.bg(lambda: adb("shell", "ls -lA " + shlex.quote(target.rstrip("/") + "/"), timeout=60),
                    lambda res: self._listed(target, res))

    def _listed(self, target, result):
        if target != self.path:
            return
        if isinstance(result, Exception):
            result = (1, "", str(result))
        rc, out, err = result
        entries = parse_ls(out)
        entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
        self.entries = entries
        clear_children(self.listbox)
        for entry in entries:
            self.listbox.append(FileRow(entry))
        message = first_line(err or out, "") if not entries else ""
        self.placeholder.set_text(message if rc != 0 or message else "This folder is empty.")

    def _on_activate(self, _listbox, row):
        if row.entry["dir"]:
            self.reload(posixpath.join(self.path, row.entry["name"]))
        elif kind_of(row.entry["name"]):
            open_preview(self.win, self.path, getattr(self, "entries", []), row.entry["name"])
        else:
            self.win.toast("No preview for this type. Select it and press Download.")

    def _selected(self):
        return [posixpath.join(self.path, r.entry["name"]) for r in self.listbox.get_selected_rows()]

    # ---- transfers
    def transfer(self, jobs, success, reload):
        if self.busy:
            self.win.toast("Wait for the current transfer to finish")
            return
        self.busy = True
        self.spinner.start()

        def work():
            failures = []
            for i, (argv, label) in enumerate(jobs, 1):
                GLib.idle_add(self.status.set_text, f"{i}/{len(jobs)}  {posixpath.basename(label.rstrip('/'))}")
                self.win.log("$ adb " + " ".join(shlex.quote(a) for a in argv) + "\n")
                rc, out, err = adb(*argv, timeout=3600)
                text = (out + err).strip()
                self.win.log(text + "\n")
                if rc != 0:
                    failures.append(first_line(text))
            return failures

        def done(res):
            self.busy = False
            self.spinner.stop()
            self.status.set_text("")
            if isinstance(res, Exception):
                self.win.toast(str(res))
                return
            self.win.toast(success if not res else f"{len(res)} failed: {res[0]}")
            if reload:
                self.reload()

        self.win.bg(work, done)

    def download(self, _b):
        paths = self._selected()
        if not paths:
            self.win.toast("Select files or folders first (Ctrl or Shift to pick several)")
            return
        choose_path(self.win, "folder", lambda dest: self.transfer(
            [(["pull", p, dest + "/"], p) for p in paths],
            f"Downloaded {len(paths)} item(s) to {dest}", False))

    def upload(self, paths):
        if paths:
            dest = self.path.rstrip("/") + "/"
            self.transfer([(["push", p, dest], p) for p in paths],
                          f"Sent {len(paths)} item(s) to {self.path}", True)

    def upload_files(self, _b):
        compat.pick(self.win, "file", self.upload, "Choose files to send to the phone", True)

    def upload_folder(self, _b):
        choose_path(self.win, "folder", lambda p: self.upload([p]))

    def _on_drop(self, _target, value, _x, _y):
        self.upload([f.get_path() for f in value.get_files() if f.get_path()])
        return True

    # ---- changes on the phone
    def new_folder(self, _b):
        def make(values):
            full = posixpath.join(self.path, values["folder_name"])
            self.transfer([(["shell", "mkdir -p " + shlex.quote(full)], full)],
                          f"Created {values['folder_name']}", True)
        PromptWindow(self.win, "New folder", f"Creates a folder inside {self.path}",
                     ["folder_name"], {}, make).present()

    def delete(self, _b):
        paths = self._selected()
        if not paths:
            self.win.toast("Select the items to delete first")
            return
        shown = "\n".join(posixpath.basename(p) for p in paths[:8])
        if len(paths) > 8:
            shown += f"\n... and {len(paths) - 8} more"
        confirm_dialog(self.win, f"Delete {len(paths)} item(s) from the phone?",
                       shown + "\n\nThis cannot be undone.", "Delete",
                       lambda: self.transfer([(["shell", "rm -rf " + shlex.quote(p)], p) for p in paths],
                                             f"Deleted {len(paths)} item(s)", True))
