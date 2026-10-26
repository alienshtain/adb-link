"""Application object and entry point of the window."""
from __future__ import annotations

import sys

from gi.repository import Adw, Gdk, Gio, Gtk

from ..paths import APP_ID, data_dir
from .ui import install_css
from .window import MainWindow


class App(Adw.Application):
    def __init__(self, background=False):
        flags = getattr(Gio.ApplicationFlags, "DEFAULT_FLAGS", Gio.ApplicationFlags.FLAGS_NONE)
        super().__init__(application_id=APP_ID, flags=flags)
        self.css_done, self.background, self.window = False, background, None
        for name, handler in (("quit", lambda *_: self.quit()),
                              ("call-answer", lambda *_: self.window and self.window.monitor.answer()),
                              ("call-reject", lambda *_: self.window and self.window.monitor.reject()),
                              ("call-show", lambda *_: self._show_call())):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)
        self.set_accels_for_action("app.quit", ["<Primary>q"])

    def _show_call(self):
        if self.window:
            self.window.present()
            if self.window.monitor.popup:
                self.window.monitor.popup.present()

    def do_startup(self):
        Adw.Application.do_startup(self)
        display = Gdk.Display.get_default()
        if display is not None:   # the icon also works before "adblink install" has been run
            Gtk.IconTheme.get_for_display(display).add_search_path(str(data_dir() / "icons"))
            Gtk.Window.set_default_icon_name(APP_ID)

    def do_activate(self):
        if not self.css_done:
            install_css()
            self.css_done = True
        first = self.window is None
        if first:
            self.window = MainWindow(self)
        if first and self.background:
            return  # started at login: stay hidden until the phone rings or the user opens it
        self.window.present()

    def do_shutdown(self):
        if self.window is not None:
            self.window.link.stop()
        Adw.Application.do_shutdown(self)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    return App("--background" in argv).run(["adblink"])
