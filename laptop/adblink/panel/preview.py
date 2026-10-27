"""Preview a file that lives on the phone (pictures and text) without downloading it by hand."""
from __future__ import annotations

import os
import posixpath
import shlex
import shutil
import tempfile

from gi.repository import Gdk, Gio, GLib, Gtk

from .. import storage
from .adbutil import adb, first_line, fmt_size
from .ui import close_on_escape

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic"}
TEXT_EXT = {".txt", ".md", ".log", ".json", ".xml", ".csv", ".ini", ".conf", ".cfg", ".yaml", ".yml",
            ".py", ".sh", ".js", ".ts", ".html", ".css", ".java", ".kt", ".dart", ".c", ".h", ".cpp",
            ".srt", ".vcf", ".properties", ".gradle", ".toml", ".sql", ".tsv"}
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".3gp", ".m4v", ".flv", ".wmv", ".mpg", ".mpeg", ".ts"}
MAX_VIDEO = 2 * 1024 * 1024 * 1024
MAX_IMAGE = 40 * 1024 * 1024
MAX_TEXT = 512 * 1024


def kind_of(name):
    ext = posixpath.splitext(name.lower())[1]
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in TEXT_EXT:
        return "text"
    return ""


def icon_for(entry):
    if entry["dir"]:
        return "folder-symbolic"
    return {"image": "image-x-generic-symbolic", "video": "video-x-generic-symbolic",
            "text": "text-x-generic-symbolic"}.get(
        kind_of(entry["name"]), "text-x-generic-symbolic")


class PreviewWindow(Gtk.Window):
    """Shows one file; Previous/Next walk through the other previewable files of the same folder."""

    def __init__(self, parent, folder, names, index):
        super().__init__(transient_for=parent, modal=False, default_width=900, default_height=640)
        close_on_escape(self)
        self.win, self.folder, self.names, self.index = parent, folder, names, index
        self.tmp = tempfile.mkdtemp(prefix="adblink-preview-")
        self.cache = {}
        self.local = None
        self.token = 0

        bar = Gtk.HeaderBar()
        self.set_titlebar(bar)
        self.prev_b = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Previous")
        self.next_b = Gtk.Button(icon_name="go-next-symbolic", tooltip_text="Next")
        self.prev_b.connect("clicked", lambda _b: self.step(-1))
        self.next_b.connect("clicked", lambda _b: self.step(1))
        bar.pack_start(self.prev_b)
        bar.pack_start(self.next_b)
        save = Gtk.Button(icon_name="document-save-symbolic", tooltip_text="Save a copy on this computer")
        save.connect("clicked", self.save_copy)
        opn = Gtk.Button(icon_name="document-open-symbolic", tooltip_text="Open with the default app")
        opn.connect("clicked", self.open_external)
        bar.pack_end(opn)
        bar.pack_end(save)

        self.stack = Gtk.Stack()
        self.spinner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER,
                               valign=Gtk.Align.CENTER)
        self.spinner.append(Gtk.Spinner(spinning=True, width_request=40, height_request=40))
        self.load_label = Gtk.Label(css_classes=["dim-label"])
        self.spinner.append(self.load_label)
        self.video = Gtk.Video(autoplay=True)
        self.message = Gtk.Label(wrap=True, css_classes=["dim-label"], margin_start=24, margin_end=24)
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True)
        self.text = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 left_margin=12, right_margin=12, top_margin=8, bottom_margin=8)
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.text)
        self.stack.add_named(self.spinner, "load")
        self.stack.add_named(self.message, "msg")
        self.stack.add_named(self.picture, "image")
        self.stack.add_named(self.video, "video")
        self.stack.add_named(scroll, "text")
        self.set_child(self.stack)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self.add_controller(keys)
        self.connect("close-request", self._closing)
        self.show_current()

    # ---- helpers
    def _key(self, _c, keyval, _code, _state):
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Page_Up):
            self.step(-1)
            return True
        if keyval in (Gdk.KEY_Right, Gdk.KEY_Page_Down):
            self.step(1)
            return True
        return False

    def _closing(self, *_a):
        self.video.set_file(None)
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def step(self, delta):
        self.index = (self.index + delta) % len(self.names)
        self.show_current()

    @property
    def name(self):
        return self.names[self.index]

    @property
    def remote(self):
        return posixpath.join(self.folder, self.name)

    def show_current(self):
        self.token += 1
        token, name = self.token, self.name
        self.set_title(f"{name}   ({self.index + 1}/{len(self.names)})")
        multi = len(self.names) > 1
        self.prev_b.set_sensitive(multi)
        self.next_b.set_sensitive(multi)
        self.video.set_file(None)       # stop the previous video
        self.local = self.cache.get(name)
        if self.local:
            self._display(name)
            return
        self.load_label.set_text("")
        self.stack.set_visible_child_name("load")
        remote = self.remote
        kind = kind_of(name)

        def work():
            size_rc, size_out, _e = adb("shell", "stat -c %s " + shlex.quote(remote), timeout=20)
            size = int(size_out.strip()) if size_rc == 0 and size_out.strip().isdigit() else 0
            limit = MAX_TEXT if kind == "text" else MAX_IMAGE
            if kind == "video":
                if size > MAX_VIDEO:
                    return "big", size
                GLib.idle_add(self.load_label.set_text, f"{fmt_size(size)}")
            elif size > limit and kind == "image":
                return "big", size
            dest = os.path.join(self.tmp, f"{self.index}-{name}")
            if kind == "text" and size > limit:
                rc, out, err = adb("shell", f"head -c {limit} " + shlex.quote(remote), timeout=60, binary=True)
                if rc != 0:
                    return "err", first_line(err)
                with open(dest, "wb") as fh:
                    fh.write(out)
                return "ok", dest
            rc, out, err = adb("pull", remote, dest, timeout=300)
            if rc != 0:
                return "err", first_line(err or out)
            return "ok", dest

        def done(res):
            if token != self.token:
                return
            if isinstance(res, Exception):
                res = ("err", str(res))
            state, value = res
            if state == "big":
                self._say(f"This file is {fmt_size(value)}. Download it instead (button above).")
            elif state == "err":
                self._say(value or "Could not read the file")
            else:
                self.cache[name] = value
                self.local = value
                self._display(name)
        self.win.bg(work, done)

    def _say(self, text):
        self.message.set_text(text)
        self.stack.set_visible_child_name("msg")

    def _display(self, name):
        kind = kind_of(name)
        if kind == "video":
            self.video.set_filename(self.local)
            self.stack.set_visible_child_name("video")
        elif kind == "image":
            try:
                texture = Gdk.Texture.new_from_filename(self.local)
            except GLib.Error:
                self._say("This picture format cannot be shown here. Use \"Open with the default app\".")
                return
            self.picture.set_paintable(texture)
            self.stack.set_visible_child_name("image")
        else:
            with open(self.local, "rb") as fh:
                data = fh.read()
            self.text.get_buffer().set_text(data.decode("utf-8", "replace"))
            self.stack.set_visible_child_name("text")

    # ---- toolbar
    def save_copy(self, _b):
        if not self.local:
            return
        dest = os.path.join(storage.folder("files"), self.name)
        try:
            shutil.copyfile(self.local, dest)
            self.win.toast(f"Saved to {dest}")
        except OSError as e:
            self.win.toast(str(e))

    def open_external(self, _b):
        if not self.local:
            return
        try:
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(self.local).get_uri(), None)
        except GLib.Error as e:
            self.win.toast(e.message)


def open_preview(win, folder, entries, name):
    """entries: all rows of the folder; opens `name` and lets the user walk through its siblings."""
    names = [e["name"] for e in entries if not e["dir"] and kind_of(e["name"]) == kind_of(name)]
    if name not in names:
        return False
    PreviewWindow(win, folder, names, names.index(name)).present()
    return True
