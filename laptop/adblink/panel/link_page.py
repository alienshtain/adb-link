"""Phone app page: the server the ADB Link phone app talks to, how to pair, and what works."""
from __future__ import annotations

import time

from gi.repository import Adw, Gdk, GLib, Gtk

from .. import deps, phoneapp
from ..server import startup
from ..server.inputdev import setup_input_permissions, uinput_status


class LinkServer:
    """Owns the embedded server so the window can start, stop and restart it."""

    def __init__(self, win):
        self.win, self.handle, self.error = win, None, ""

    @property
    def running(self):
        return self.handle is not None

    def apply(self):
        want = bool(self.win.pref("link_enabled"))
        port = int(self.win.pref("link_port"))
        if self.handle and (not want or self.handle.port != port):
            self.handle.stop()
            self.handle = None
        if want and not self.handle:
            try:
                self.handle = startup.start(
                    "0.0.0.0", port, shell=bool(self.win.pref("link_shell")),
                    clipboard=bool(self.win.pref("link_clipboard")),
                    notifications=bool(self.win.pref("link_notifications")))
                self.error = ""
            except OSError as e:
                self.error = f"Port {port} is busy ({e.strerror or e}). Is another ADB Link already running?"
        elif self.handle:  # same port: only the feature switches may have changed
            from ..server.common import FLAGS
            FLAGS.shell = bool(self.win.pref("link_shell"))
            FLAGS.clipboard = bool(self.win.pref("link_clipboard"))
            FLAGS.notifications = bool(self.win.pref("link_notifications"))

    def stop(self):
        if self.handle:
            self.handle.stop()
            self.handle = None


def ago(ts):
    if not ts:
        return "never"
    s = int(time.time() - ts)
    if s < 8:
        return "just now"
    if s < 90:
        return f"{s} seconds ago"
    if s < 5400:
        return f"{s // 60} minutes ago"
    return f"{s // 3600} hours ago"


class LinkPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win, self.needs_reload = win, False
        self.rows = {"addr": [], "phones": [], "caps": [], "tools": []}

        # --- server on/off
        g = Adw.PreferencesGroup(title="ADB Link server",
                                 description="This is what the ADB Link phone app talks to. It lives inside this "
                                             "window and keeps running when the window is hidden.")
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER, active=bool(win.pref("link_enabled")))
        self.switch.connect("notify::active", lambda s, _p: win.set_pref("link_enabled", s.get_active()))
        self.status_row = Adw.ActionRow(title="Phone app server", activatable=False)
        self.status_row.add_suffix(self.switch)
        g.add(self.status_row)
        self.port = Gtk.SpinButton.new_with_range(1024, 65535, 1)
        self.port.set_value(int(win.pref("link_port")))
        self.port.set_valign(Gtk.Align.CENTER)
        self.port.connect("value-changed", lambda s: win.set_pref("link_port", int(s.get_value())))
        row = Adw.ActionRow(title="Port", subtitle="Change it only if another program uses 8765")
        row.add_suffix(self.port)
        g.add(row)
        self.add(g)

        # --- pairing
        self.pair = Adw.PreferencesGroup(
            title="Pair a phone",
            description="Open ADB Link on the phone. Press \"Find my computer\", or type one address below and the code.")
        self.add(self.pair)
        self.code_row = Adw.ActionRow(title="Pairing code", subtitle="Changes after every pairing")
        self.code = Gtk.Label(css_classes=["title-1"], valign=Gtk.Align.CENTER, selectable=True)
        self.code_row.add_suffix(self.code)
        copy = Gtk.Button(icon_name="edit-copy-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER,
                          tooltip_text="Copy the code")
        copy.connect("clicked", lambda _b: self._copy(startup.pairing_code()))
        new = Gtk.Button(icon_name="view-refresh-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER,
                         tooltip_text="Make a new code")
        new.connect("clicked", lambda _b: (startup.new_code(), self.reload()))
        self.code_row.add_suffix(copy)
        self.code_row.add_suffix(new)

        # --- the phone app itself
        g = Adw.PreferencesGroup(title="Get the phone app")
        row = Adw.ActionRow(title="Install on the phone that is connected with adb",
                            subtitle="Downloads the latest ADB Link APK and installs it")
        self.install_btn = Gtk.Button(label="Install", css_classes=["suggested-action"], valign=Gtk.Align.CENTER)
        self.install_btn.connect("clicked", self._install_phone)
        row.add_suffix(self.install_btn)
        g.add(row)
        self.add(g)

        # --- connected phones
        self.phones = Adw.PreferencesGroup(title="Phones paired with this computer")
        reset = Gtk.Button(label="Unpair all", css_classes=["flat", "destructive-action"], valign=Gtk.Align.CENTER)
        reset.connect("clicked", self._unpair)
        self.phones.set_header_suffix(reset)
        self.add(self.phones)

        # --- what works
        self.caps = Adw.PreferencesGroup(title="What the phone can do here")
        self.add(self.caps)

        # --- what the phone may do
        g = Adw.PreferencesGroup(title="What the phone may do")
        for key, title, sub in (("link_shell", "Run commands in a terminal",
                                 "The phone gets a terminal on this computer. Turn it off if you do not need it."),
                                ("link_clipboard", "Share the clipboard", "Copy on one device, paste on the other."),
                                ("link_notifications", "Share notifications",
                                 "Computer notifications appear on the phone and the other way round.")):
            row = Adw.ActionRow(title=title, subtitle=sub, activatable=False)
            sw = Gtk.Switch(valign=Gtk.Align.CENTER, active=bool(win.pref(key)))
            sw.connect("notify::active", lambda s, _p, k=key: win.set_pref(k, s.get_active()))
            row.add_suffix(sw)
            g.add(row)
        self.add(g)

        # --- missing tools
        self.tools = Adw.PreferencesGroup(title="Helper tools")
        self.add(self.tools)

        self.reload()
        GLib.timeout_add_seconds(3, self._tick)

    # ---- refresh
    def _tick(self):
        if self.get_mapped():
            self._fill_dynamic()
        return True

    def reload(self):
        self.needs_reload = False
        self.switch.set_active(bool(self.win.pref("link_enabled")))
        self._fill_dynamic()
        self._fill_tools()

    def _clear(self, group, key):
        for r in self.rows[key]:
            group.remove(r)
        self.rows[key] = []

    def _add(self, group, key, row):
        group.add(row)
        self.rows[key].append(row)

    def _fill_dynamic(self):
        srv = self.win.link
        st = startup.status()
        port = int(self.win.pref("link_port"))
        if srv.error:
            self.status_row.set_subtitle(srv.error)
        elif srv.running:
            self.status_row.set_subtitle(f"Running on port {srv.handle.port}")
        else:
            self.status_row.set_subtitle("Stopped - the phone app cannot connect")
        self.code.set_text(st["code"])

        # addresses
        self._clear(self.pair, "addr")
        if self.code_row.get_parent() is None:
            self.pair.add(self.code_row)
        for ip in st["addresses"]:
            tail = startup.is_tailscale(ip)
            row = Adw.ActionRow(title=f"{ip}:{port}",
                                subtitle="Tailscale - works from anywhere" if tail else "Same Wi-Fi / network")
            btn = Gtk.Button(icon_name="edit-copy-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER,
                             tooltip_text="Copy the address")
            btn.connect("clicked", lambda _b, a=f"{ip}:{port}": self._copy(a))
            row.add_suffix(btn)
            self._add(self.pair, "addr", row)
        if not st["addresses"]:
            self._add(self.pair, "addr", Adw.ActionRow(title="No network address found",
                                                      subtitle="Connect this computer to Wi-Fi or Tailscale"))

        # phones
        self._clear(self.phones, "phones")
        if not st["paired"]:
            self._add(self.phones, "phones", Adw.ActionRow(title="No phone paired yet"))
        for p in st["paired"]:
            active = st["last_phone"] == p.get("name") and time.time() - st["last_seen"] < 20
            row = Adw.ActionRow(title=GLib.markup_escape_text(p.get("name", "Phone")),
                                subtitle=("Connected now" if active else
                                          (f"Last seen {ago(st['last_seen'])}" if st["last_phone"] == p.get("name")
                                           else "Paired")))
            row.add_prefix(Gtk.Image(icon_name="phone-symbolic"))
            self._add(self.phones, "phones", row)

        # capabilities
        self._clear(self.caps, "caps")
        caps = st["caps"]
        ok, msg = uinput_status()
        rows = [
            ("Mouse and keyboard from the phone", bool(caps["input"]),
             f"Using {caps['input']}" if caps["input"] else (caps.get("inputHint") or msg),
             None if caps["input"] else ("Allow", self._fix_input)),
            ("Show this screen on the phone", bool(caps["screen"]),
             "Ready" if caps["screen"] else "No screenshot tool found", None if caps["screen"] else ("Install", self._install_tools)),
            ("Clipboard sharing", bool(caps["clipboard"]),
             "Ready" if caps["clipboard"] else "Needs wl-clipboard or xclip", None if caps["clipboard"] else ("Install", self._install_tools)),
            ("Terminal for the phone", bool(caps["shell"]), "On" if caps["shell"] else "Off (see the switch above)", None),
        ]
        for title, good, sub, action in rows:
            row = Adw.ActionRow(title=title, subtitle=GLib.markup_escape_text(sub))
            row.add_prefix(Gtk.Image(icon_name="emblem-ok-symbolic" if good else "dialog-warning-symbolic"))
            if action:
                b = Gtk.Button(label=action[0], css_classes=["suggested-action"], valign=Gtk.Align.CENTER)
                b.connect("clicked", action[1])
                row.add_suffix(b)
            self._add(self.caps, "caps", row)

    def _fill_tools(self):
        self._clear(self.tools, "tools")
        miss = deps.missing()
        if not miss:
            self._add(self.tools, "tools", Adw.ActionRow(title="Everything is installed",
                                                        subtitle="adb, scrcpy, brightnessctl, playerctl ..."))
            return
        for d in miss:
            row = Adw.ActionRow(title=d.title, subtitle=d.why)
            row.add_prefix(Gtk.Image(icon_name="dialog-warning-symbolic"))
            self._add(self.tools, "tools", row)
        b = Gtk.Button(label="Install the missing tools", css_classes=["suggested-action"], halign=Gtk.Align.CENTER,
                       margin_top=6)
        b.connect("clicked", self._install_tools)
        row = Adw.ActionRow(title="Asks for your password once")
        row.add_suffix(b)
        self._add(self.tools, "tools", row)

    # ---- actions
    def _copy(self, text):
        Gdk.Display.get_default().get_clipboard().set(text)
        self.win.toast("Copied")

    def _unpair(self, _b):
        from .ui import confirm_dialog
        confirm_dialog(self.win, "Unpair every phone?", "The phones will have to pair again with the code.",
                       "Unpair", lambda: (startup.ensure_state().reset_tokens(), self.reload()))

    def _fix_input(self, _b):
        self.win.toast("Asking for permission...")
        self.win.bg(setup_input_permissions, self._fix_done)

    def _fix_done(self, res):
        self.win.toast(str(res) if isinstance(res, Exception) else res[1])
        self.reload()

    def _install_tools(self, _b):
        self.win.toast("Installing... a password window may open")

        def work():
            miss = deps.missing()
            return deps.install(miss, say=self.win.log) if miss else ([], [])

        def done(res):
            if isinstance(res, Exception):
                self.win.toast(str(res))
            else:
                done_, failed = res
                self.win.toast("Installed: " + (", ".join(done_) or "nothing") +
                               (f". Could not install: {', '.join(failed)}" if failed else ""))
            self.reload()
        self.win.bg(work, done)

    def _install_phone(self, _b):
        self.install_btn.set_sensitive(False)
        self.win.toast("Getting the phone app...")

        def done(res):
            self.install_btn.set_sensitive(True)
            self.win.toast(str(res) if isinstance(res, Exception) else res[1])
        self.win.bg(lambda: phoneapp.install_to_phone(say=self.win.log), done)
