"""Settings page."""
from __future__ import annotations

from gi.repository import Adw, Gio, GLib, Gtk

from .. import storage
from ..i18n import LANGUAGES
from .ui import choose_path


# ---------------------------------------------------------------- settings page

class SettingsPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win, self.rows = win, {}

        run = Adw.PreferencesGroup(title="Running in the background",
                                   description="ADB Link can stay open without a window so it can "
                                               "watch for calls and serve the phone app.")
        self._switch(run, "background", "Keep running when the window is closed",
                     "Use the menu > Quit to really close it.")
        self._switch(run, "autostart", "Start when I log in", "Starts hidden, without a window.")
        self.add(run)

        self._switch(run, "tray", "Icon in the system tray",
                     "A small icon (like Discord): click it to open ADB Link or quit.")

        files = Adw.PreferencesGroup(title="Saved files",
                                     description="Everything ADB Link saves on this computer goes here: files from "
                                                 "the phone, screenshots, recordings and saved apps.")
        self.folder_row = Adw.ActionRow(title="Folder", activatable=False)
        pick = Gtk.Button(label="Change", valign=Gtk.Align.CENTER)
        pick.connect("clicked", self._pick_folder)
        opn = Gtk.Button(label="Open", valign=Gtk.Align.CENTER)
        opn.connect("clicked", lambda _b: Gio.AppInfo.launch_default_for_uri(
            Gio.File.new_for_path(str(storage.folder("files").parent)).get_uri(), None))
        reset = Gtk.Button(icon_name="edit-undo-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER,
                           tooltip_text="Back to Documents/ADB Link")
        reset.connect("clicked", lambda _b: self._set_folder(""))
        for w in (opn, pick, reset):
            self.folder_row.add_suffix(w)
        files.add(self.folder_row)
        self.add(files)
        self._show_folder()

        lang = Adw.PreferencesGroup(title="Language")
        self.lang_row = Adw.ActionRow(title="Language of ADB Link", subtitle="Restart to apply the change.")
        self.lang_codes = list(LANGUAGES)
        self.lang_drop = Gtk.DropDown.new_from_strings([LANGUAGES[c] for c in self.lang_codes])
        self.lang_drop.set_valign(Gtk.Align.CENTER)
        current = win.pref("language")
        self.lang_drop.set_selected(self.lang_codes.index(current) if current in self.lang_codes else 0)
        self.lang_drop.connect("notify::selected", self._language_changed)
        self.lang_row.add_suffix(self.lang_drop)
        self.restart_btn = Gtk.Button(label="Restart now", css_classes=["suggested-action"],
                                      valign=Gtk.Align.CENTER, visible=False)
        self.restart_btn.connect("clicked", lambda _b: win.restart_app())
        self.lang_row.add_suffix(self.restart_btn)
        lang.add(self.lang_row)
        self.add(lang)

        net = Adw.PreferencesGroup(title="Connection")
        self._switch(net, "auto_reconnect", "Reconnect my phone by itself",
                     "Phones you connected over Wi-Fi come back after sleep, restarts or a changed network.")
        row = Adw.ActionRow(title="Connect your phone", subtitle="USB, Wi-Fi, Wireless debugging, Bluetooth")
        btn = Gtk.Button(label="Open", valign=Gtk.Align.CENTER)
        btn.connect("clicked", lambda _b: win.open_connect())
        row.add_suffix(btn)
        net.add(row)
        self.add(net)

        calls = Adw.PreferencesGroup(title="Phone calls")
        self._switch(calls, "watch_calls", "Watch for calls", "Checks the phone every 2 seconds.")
        self._switch(calls, "call_popup", "Show a pop-up window when the phone rings")
        self._switch(calls, "call_notify", "Show a desktop notification with Answer and Reject")
        self._switch(calls, "pause_media", "Pause the music and videos on this computer during a call")
        self._switch(calls, "resume_media", "Play them again when the call ends")
        test = Gtk.Button(label="Test the call pop-up", valign=Gtk.Align.CENTER)
        test.connect("clicked", lambda _b: win.monitor.simulate())
        row = Adw.ActionRow(title="Preview", subtitle="Shows a pretend call. Nothing is sent to the phone.")
        row.add_suffix(test)
        calls.add(row)
        self.add(calls)

        look = Adw.PreferencesGroup(title="Pages and panels")
        self._switch(look, "contacts_page", "Contacts page", "Call or message from the phone's SIM cards.")
        self._switch(look, "phone_panel", "Phone panel on the right")
        self.add(look)

    def _show_folder(self):
        self.folder_row.set_subtitle(GLib.markup_escape_text(str(storage.save_root())))

    def _set_folder(self, path):
        self.win.set_pref("save_dir", path)
        self._show_folder()

    def _pick_folder(self, _b):
        choose_path(self.win, "folder", self._set_folder)

    def _language_changed(self, drop, _pspec):
        code = self.lang_codes[drop.get_selected()]
        if code != self.win.pref("language"):
            self.win.set_pref("language", code)
            self.restart_btn.set_visible(True)

    def _switch(self, group, key, title, subtitle=""):
        row = Adw.ActionRow(title=title, subtitle=subtitle, activatable=False)
        sw = Gtk.Switch(valign=Gtk.Align.CENTER, active=bool(self.win.pref(key)))
        sw.connect("notify::active", lambda s, _p, k=key: self.win.set_pref(k, s.get_active()))
        row.add_suffix(sw)
        row.set_activatable_widget(sw)
        group.add(row)
        self.rows[key] = sw

    def sync(self):
        for key, sw in self.rows.items():
            sw.set_active(bool(self.win.pref(key)))
