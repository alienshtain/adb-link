"""Settings page."""
from __future__ import annotations

from gi.repository import Adw, Gtk


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
