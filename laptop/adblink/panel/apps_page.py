"""Apps page."""
from __future__ import annotations

import shutil
import tempfile
from . import compat
from gi.repository import Adw, GLib, Gdk, Gio, Gtk
from .adbutil import adb, first_line
from .apps_helpers import (
    AppRow,
    IconLoader,
    build_units,
    download_app,
    install_units,
    parse_packages,
)
from .ui import choose_path, clear_children, confirm_dialog


APP_FILTERS = ["All apps", "User apps", "System apps", "Disabled", "Removed"]
APP_SORTS = ["Name A-Z", "Status"]


class AppsPage(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win, self.rows, self.needs_reload = win, [], True
        self.search_text, self.filter_mode, self.sort_mode = "", 0, 0
        self.loader, self.pending, self.total_icons = IconLoader(), 0, 0

        bar = Gtk.Box(spacing=8, margin_top=8, margin_bottom=4, margin_start=12, margin_end=12)
        search = Gtk.SearchEntry(hexpand=True, placeholder_text="Search apps")
        search.connect("search-changed", self._on_search)
        flt = Gtk.DropDown.new_from_strings(APP_FILTERS)
        flt.connect("notify::selected", self._on_filter)
        srt = Gtk.DropDown.new_from_strings(APP_SORTS)
        srt.connect("notify::selected", self._on_sort)
        reload_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Reload the app list")
        reload_btn.connect("clicked", lambda _b: self.reload())
        install_btn = Gtk.Button(css_classes=["suggested-action"],
                                 tooltip_text="Install .apk, .apks, .xapk or .apkm files "
                                              "(you can also drag them onto this page)")
        install_btn.set_child(compat.content("document-save-symbolic", "Install"))
        install_btn.connect("clicked", self.install_files)
        folder_btn = Gtk.Button(icon_name="folder-symbolic",
                                tooltip_text="Install an app from a folder "
                                             "(base.apk + split apks + obb folder)")
        folder_btn.connect("clicked", self.install_folder)
        for w in (search, flt, srt, reload_btn, install_btn, folder_btn):
            bar.append(w)
        self.append(bar)
        self.busy = False
        self.spinner = Gtk.Spinner()
        self.status = Gtk.Label(xalign=0, css_classes=["dim-label", "caption"])
        status_box = Gtk.Box(spacing=8, margin_start=14, margin_bottom=4)
        status_box.append(self.spinner)
        status_box.append(self.status)
        self.append(status_box)
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.add_controller(drop)

        self.placeholder = Gtk.Label(label="", margin_top=30, margin_bottom=30,
                                     css_classes=["dim-label"])
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["rich-list"])
        self.listbox.set_sort_func(self._sort_func)
        self.listbox.set_filter_func(self._match)
        self.listbox.set_placeholder(self.placeholder)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(self.listbox)
        self.append(scroller)

    # ---- loading
    def reload(self):
        self.needs_reload = False
        self.loader.clear()
        self.rows, self.pending, self.total_icons = [], 0, 0
        clear_children(self.listbox)
        self.placeholder.set_text("Loading apps from the phone...")
        self.status.set_text("Loading...")
        script = ("echo @@ALL; pm list packages -f -u; echo @@INST; pm list packages; "
                  "echo @@DIS; pm list packages -d; echo @@USER; pm list packages -3")
        self.win.bg(lambda: adb("shell", script, timeout=90), self._loaded)

    def _loaded(self, result):
        if isinstance(result, Exception):
            result = (1, "", str(result))
        rc, out, err = result
        if rc != 0 or "@@ALL" not in out:
            self.placeholder.set_text(first_line(err or out, "No phone connected."))
            self.status.set_text("")
            return
        for pkg, (apk, status, is_user) in parse_packages(out).items():
            row = AppRow(self, pkg, apk, status, is_user)
            self.rows.append(row)
            self.listbox.append(row)
        self.placeholder.set_text("No apps match.")
        queued = sorted(self.rows, key=lambda r: (not r.is_user, r.name.lower()))
        for row in queued:
            if row.apk:
                self.pending += 1
                self.loader.submit(row.pkg, row.apk, lambda g, path, r=row: self._icon_done(r, g, path))
        self.total_icons = self.pending
        self._update_status()

    def _icon_done(self, row, gen, path):
        if gen != self.loader.generation:
            return False
        self.pending -= 1
        if path:
            row.set_icon(path)
        self._update_status()
        return False

    def _update_status(self):
        if self.busy:
            return
        shown = sum(1 for r in self.rows if self._match(r))
        text = f"{shown} of {len(self.rows)} apps"
        if self.pending > 0:
            text += f"  -  loading icons {self.total_icons - self.pending}/{self.total_icons}"
        self.status.set_text(text)

    # ---- filtering / sorting
    def _match(self, row):
        mode = self.filter_mode
        if mode == 1 and not row.is_user:
            return False
        if mode == 2 and row.is_user:
            return False
        if mode == 3 and row.status != "disabled":
            return False
        if mode == 4 and row.status != "removed":
            return False
        return not self.search_text or self.search_text in (row.name + " " + row.pkg).lower()

    def _sort_func(self, a, b):
        order = {"enabled": 0, "disabled": 1, "removed": 2}
        ka = (order[a.status] if self.sort_mode == 1 else 0, a.name.lower(), a.pkg)
        kb = (order[b.status] if self.sort_mode == 1 else 0, b.name.lower(), b.pkg)
        return (ka > kb) - (ka < kb)

    def _refilter(self):
        self.listbox.invalidate_filter()
        self.listbox.invalidate_sort()
        self._update_status()

    def _on_search(self, entry):
        self.search_text = entry.get_text().strip().lower()
        self._refilter()

    def _on_filter(self, dropdown, _p):
        self.filter_mode = dropdown.get_selected()
        self._refilter()

    def _on_sort(self, dropdown, _p):
        self.sort_mode = dropdown.get_selected()
        self._refilter()

    # ---- install / download
    def _run_job(self, work, done):
        """Run a long job in the background with a spinner; one at a time."""
        if self.busy:
            self.win.toast("Wait for the current job to finish")
            return
        self.busy = True
        self.spinner.start()

        def progress(text):
            GLib.idle_add(self.status.set_text, text)

        def finished(res):
            self.busy = False
            self.spinner.stop()
            if isinstance(res, Exception):
                self.win.toast(f"Failed: {res}")
                self.win.log(f"Error: {res}\n")
            else:
                done(res)
            self._update_status()

        self.win.bg(lambda: work(progress), finished)

    def install_paths(self, paths):
        if not paths:
            return

        def work(progress):
            tmp = tempfile.mkdtemp(prefix="adb-panel-")
            try:
                progress("Reading the selected files...")
                units = build_units(paths, tmp)
                if not units:
                    return None
                return install_units(units, progress, self.win.log)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        def done(results):
            if results is None:
                self.win.toast("No .apk files found in what you selected")
                return
            bad = [r for r in results if not r[1]]
            if bad:
                self.win.toast(f"{len(bad)} of {len(results)} failed: {bad[0][0]}: {bad[0][2]}")
            else:
                self.win.toast(f"Installed {len(results)} app(s)")
            self.reload()

        self._run_job(work, done)

    def install_files(self, _b):
        compat.pick(self.win, "file", self.install_paths, "Choose app files to install", True,
                    [("Android apps (.apk .apks .xapk .apkm)", ["apk", "apks", "xapk", "apkm"]),
                     ("All files", ["*"])])

    def install_folder(self, _b):
        choose_path(self.win, "folder", lambda p: self.install_paths([p]))

    def _on_drop(self, _target, value, _x, _y):
        self.install_paths([f.get_path() for f in value.get_files() if f.get_path()])
        return True

    def download_app(self, row):
        def start(dest):
            def work(progress):
                return download_app(row.pkg, dest, progress, self.win.log)

            def done(res):
                ok, msg = res
                self.win.log(msg + "\n")
                self.win.toast(msg if ok else f"{row.name}: {msg}")

            self._run_job(work, done)

        choose_path(self.win, "folder", start)

    # ---- actions
    def act(self, row, action):
        if action == "download":
            self.download_app(row)
        elif action == "uninstall":
            detail = ("The app and its data will be deleted." if row.is_user else
                      "This removes the built-in app for your user only. "
                      "You can bring it back later with Restore.")
            confirm_dialog(self.win, f"Uninstall {row.name}?", f"{row.pkg}\n\n{detail}",
                           "Uninstall", lambda: self._do(row, action))
        else:
            self._do(row, action)

    def _do(self, row, action):
        pkg = row.pkg
        if action == "disable":
            argv, ok, new = ["shell", "pm", "disable-user", "--user", "0", pkg], "new state: disabled", "disabled"
        elif action == "enable":
            argv, ok, new = ["shell", "pm", "enable", pkg], "new state: enabled", "enabled"
        elif action == "restore":
            argv, ok, new = ["shell", "cmd", "package", "install-existing", pkg], "installed for user", "enabled"
        else:
            argv = ["uninstall", pkg] if row.is_user else ["shell", "pm", "uninstall", "--user", "0", pkg]
            ok, new = "success", "removed"
        self.win.log(f"$ adb {' '.join(argv)}\n")

        def done(res):
            if isinstance(res, Exception):
                res = (1, "", str(res))
            text = (res[1] + res[2]).strip()
            self.win.log(text + "\n")
            if ok in text.lower():
                if action == "uninstall" and row.is_user:
                    self.rows.remove(row)
                    self.listbox.remove(row)
                else:
                    row.status = new
                    row.refresh()
                self._refilter()
                self.win.toast(f"{row.name}: {new}")
            else:
                self.win.toast(f"{row.name}: {first_line(text)}")

        self.win.bg(lambda: adb(*argv, timeout=120), done)
