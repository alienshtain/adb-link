"""The "Connect your phone" window: USB, Wi-Fi, Wireless debugging, Tailscale and Bluetooth in one place."""
from __future__ import annotations

from gi.repository import Adw, GLib, Gtk

from .. import connect as conn
from .ui import clear_children, close_on_escape


class ConnectWindow(Gtk.Window):
    def __init__(self, win):
        super().__init__(title="Connect your phone", transient_for=win, default_width=560, default_height=780)
        self.win = win
        close_on_escape(self)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(outer)

        # the result of the last action stays visible at the top
        self.result = Gtk.Label(wrap=True, xalign=0, selectable=True, margin_top=10, margin_bottom=10,
                                margin_start=14, margin_end=14)
        self.result_box = Gtk.Revealer(child=self.result)
        outer.append(self.result_box)

        page = Adw.PreferencesPage()
        outer.append(Gtk.ScrolledWindow(vexpand=True, child=page, hscrollbar_policy=Gtk.PolicyType.NEVER))

        # --- phones right now
        self.now = Adw.PreferencesGroup(title="Phones adb can see right now")
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER,
                             tooltip_text="Refresh")
        refresh.connect("clicked", lambda _b: self.reload())
        self.now.set_header_suffix(refresh)
        self.now_rows = []
        page.add(self.now)

        # --- USB -> Wi-Fi
        g = Adw.PreferencesGroup(title="1. The easy way: cable once, then Wi-Fi",
                                 description="Plug the phone with USB (USB debugging on), then press the button. "
                                             "It finds the phone's address, turns network mode on and connects. "
                                             "You can then unplug. After a phone restart, press it again.")
        row = Adw.ActionRow(title="Switch the USB phone to Wi-Fi", subtitle="Works with home Wi-Fi and Tailscale")
        self.wifi_btn = self._button("Switch to Wi-Fi", self._on_wifi, suggested=True)
        row.add_suffix(self.wifi_btn)
        g.add(row)
        page.add(g)

        # --- by address
        g = Adw.PreferencesGroup(title="2. Connect by address",
                                 description="The phone's Wi-Fi or Tailscale address. Network mode must be on "
                                             "(step 1, or Wireless debugging below).")
        self.addr = Gtk.Entry(placeholder_text="192.168.1.20  or  100.64.0.5:5555", valign=Gtk.Align.CENTER,
                              width_chars=24)
        self.addr.connect("activate", lambda _e: self._on_connect())
        row = Adw.ActionRow(title="Address")
        row.add_suffix(self.addr)
        row.add_suffix(self._button("Connect", lambda _b: self._on_connect(), suggested=True))
        g.add(row)
        page.add(g)
        self.saved = Adw.PreferencesGroup(title="Phones you connected before",
                                          description="They are reconnected automatically when they are reachable.")
        self.saved_rows = []
        page.add(self.saved)

        # --- wireless debugging
        g = Adw.PreferencesGroup(
            title="3. Android 11+ Wireless debugging (no cable at all)",
            description="On the phone: Settings -> Developer options -> Wireless debugging -> ON -> "
                        "\"Pair device with pairing code\". Type the address:port and the 6 digits shown there. "
                        "The pairing port is not the connection port.")
        self.pair_addr = Gtk.Entry(placeholder_text="192.168.1.20:37123", valign=Gtk.Align.CENTER, width_chars=22)
        self.pair_code = Gtk.Entry(placeholder_text="123456", valign=Gtk.Align.CENTER, width_chars=8, max_length=6)
        row = Adw.ActionRow(title="Pairing address and code")
        row.add_suffix(self.pair_addr)
        row.add_suffix(self.pair_code)
        row.add_suffix(self._button("Pair", lambda _b: self._on_pair(), suggested=True))
        g.add(row)
        row = Adw.ActionRow(title="Find phones with Wireless debugging on",
                            subtitle="Shows the connection port so you do not need to type it")
        row.add_suffix(self._button("Look", lambda _b: self._on_mdns()))
        g.add(row)
        page.add(g)
        self.found = Adw.PreferencesGroup(title="Found on the network")
        self.found_rows = []
        self.found.set_visible(False)
        page.add(self.found)

        # --- find
        g = Adw.PreferencesGroup(title="4. Look around for the phone",
                                 description="Checks remembered phones, Tailscale, your hotspot / tethering "
                                             "gateway and the neighbours on the network.")
        row = Adw.ActionRow(title="Find my phone")
        row.add_suffix(self._button("Look around", lambda _b: self._on_find()))
        g.add(row)
        page.add(g)

        # --- bluetooth
        g = Adw.PreferencesGroup(
            title="5. Bluetooth",
            description="adb cannot use Bluetooth directly. What works is Bluetooth tethering: the phone shares a small "
                        "network with the laptop and adb / the phone app use it. On the phone turn on "
                        "Settings -> Hotspot and tethering -> Bluetooth tethering. Network mode must have been "
                        "turned on once over USB (step 1) since the last phone restart.")
        self.bt_model = Gtk.StringList()
        self.bt_dd = Gtk.DropDown(model=self.bt_model, valign=Gtk.Align.CENTER)
        self.bt_devices = []
        row = Adw.ActionRow(title="Paired Bluetooth device")
        row.add_suffix(self.bt_dd)
        row.add_suffix(self._button("Join its network", lambda _b: self._on_bt(), suggested=True))
        g.add(row)
        page.add(g)

        # --- diagnose
        g = Adw.PreferencesGroup(title="Why can't I connect?",
                                 description="Tests step by step: adb installed, phone answers, port open, adb accepts.")
        self.diag_addr = Gtk.Entry(placeholder_text="192.168.1.20", valign=Gtk.Align.CENTER, width_chars=20)
        row = Adw.ActionRow(title="Address to test")
        row.add_suffix(self.diag_addr)
        row.add_suffix(self._button("Test", lambda _b: self._on_diag()))
        g.add(row)
        self.diag_out = Gtk.Label(wrap=True, xalign=0, selectable=True, margin_top=6, use_markup=True)
        g.add(self.diag_out)
        page.add(g)

        self.reload()
        self._load_bluetooth()

    # ---- helpers
    def _button(self, label, handler, suggested=False):
        b = Gtk.Button(label=label, valign=Gtk.Align.CENTER, css_classes=["suggested-action"] if suggested else [])
        b.connect("clicked", handler)
        return b

    def say(self, ok, text, hint=""):
        text = GLib.markup_escape_text(text)
        hint = GLib.markup_escape_text(hint)
        colour = "#26a269" if ok else "#c01c28"
        self.result.set_markup(f'<span foreground="{colour}" weight="bold">{"✓" if ok else "✗"}  {text}</span>'
                               + (f"\n{hint}" if hint else ""))
        self.result_box.set_reveal_child(True)

    def busy(self, text):
        self.result.set_markup(f"<i>{GLib.markup_escape_text(text)}</i>")
        self.result_box.set_reveal_child(True)

    def _after(self, res, refresh=True):
        if isinstance(res, Exception):
            self.say(False, str(res))
            return
        self.say(res.ok, res.message, res.hint)
        if refresh:
            self.win.refresh_devices()
            self.reload()

    # ---- phones now / remembered
    def reload(self):
        def work():
            return conn.devices()

        def done(devs):
            for r in self.now_rows:
                self.now.remove(r)
            self.now_rows = []
            if isinstance(devs, Exception) or not devs:
                row = Adw.ActionRow(title="No phone yet", subtitle="Plug it with USB or use one of the steps below")
                self.now.add(row)
                self.now_rows.append(row)
            else:
                for d in devs:
                    ok = d.ready
                    row = Adw.ActionRow(title=GLib.markup_escape_text(d.label),
                                        subtitle="Ready" if ok else (
                                            "Waiting for you to tap Allow on the phone" if d.state == "unauthorized"
                                            else d.state))
                    row.add_prefix(Gtk.Image(icon_name="emblem-ok-symbolic" if ok else "dialog-warning-symbolic"))
                    kind = "Wi-Fi / network" if d.over_network else "USB"
                    row.add_suffix(Gtk.Label(label=kind, css_classes=["badge"], valign=Gtk.Align.CENTER))
                    if d.over_network:
                        row.add_suffix(self._button("Disconnect", lambda _b, s=d.serial: self._disconnect(s)))
                    self.now.add(row)
                    self.now_rows.append(row)
            self._reload_saved()
        self.win.bg(work, done)

    def _reload_saved(self):
        for r in self.saved_rows:
            self.saved.remove(r)
        self.saved_rows = []
        hosts = conn.saved_hosts()
        self.saved.set_visible(bool(hosts))
        for h in hosts:
            addr = f"{h['host']}:{int(h.get('port', 5555))}"
            row = Adw.ActionRow(title=addr, subtitle=h.get("name") or "")
            row.add_suffix(self._button("Connect", lambda _b, a=addr: self._connect_to(a)))
            forget = Gtk.Button(icon_name="user-trash-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER,
                                tooltip_text="Forget this phone")
            forget.connect("clicked", lambda _b, hh=h: (conn.forget_host(hh["host"], hh.get("port")), self._reload_saved()))
            row.add_suffix(forget)
            self.saved.add(row)
            self.saved_rows.append(row)

    def _disconnect(self, serial):
        self.win.bg(lambda: conn.disconnect(serial), lambda _r: (self.win.refresh_devices(), self.reload()))

    # ---- actions
    def _on_wifi(self, _b=None):
        self.busy("Switching to Wi-Fi...")
        self.win.bg(conn.usb_to_wifi, self._after)

    def _connect_to(self, address):
        self.busy(f"Connecting to {address}...")
        self.win.bg(lambda: conn.connect(address), self._after)

    def _on_connect(self):
        text = self.addr.get_text().strip()
        if not text:
            self.say(False, "Type the phone's address first")
            return
        self._connect_to(text)

    def _on_pair(self):
        addr, code = self.pair_addr.get_text().strip(), self.pair_code.get_text().strip()
        self.busy("Pairing...")

        def work():
            res = conn.pair(addr, code)
            if res.ok:  # right after pairing the phone announces its connection port
                for s in conn.mdns_services():
                    if s["kind"] == "connect" and s["host"] == conn.split_host_port(addr)[0]:
                        nxt = conn.connect(s["host"], s["port"])
                        nxt.message = res.message + "  ->  " + nxt.message
                        return nxt
                res.message += "  Now press \"Look\" below to connect, or type the connection address."
            return res
        self.win.bg(work, self._after)

    def _show_found(self, items):
        for r in self.found_rows:
            self.found.remove(r)
        self.found_rows = []
        self.found.set_visible(bool(items))
        for it in items:
            addr = f"{it['host']}:{it['port']}"
            row = Adw.ActionRow(title=addr, subtitle=it.get("via") or it.get("kind", ""))
            row.add_suffix(self._button("Connect", lambda _b, a=addr: self._connect_to(a), suggested=True))
            self.found.add(row)
            self.found_rows.append(row)

    def _on_mdns(self):
        self.busy("Looking for Wireless debugging...")

        def done(res):
            if isinstance(res, Exception):
                self.say(False, str(res))
                return
            items = [dict(s, via="Wireless debugging") for s in res if s["kind"] == "connect"]
            pairing = [s for s in res if s["kind"] == "pairing"]
            if pairing:
                self.pair_addr.set_text(f"{pairing[0]['host']}:{pairing[0]['port']}")
            self._show_found(items)
            if items:
                self.say(True, f"Found {len(items)} phone(s)")
            else:
                self.say(False, "No phone announced itself",
                         "Turn Wireless debugging on, keep the phone awake and on the same Wi-Fi. "
                         "If your adb has no mDNS support, type the address:port shown on the Wireless debugging screen.")
        self.win.bg(conn.mdns_services, done)

    def _on_find(self):
        self.busy("Looking around... (up to 20 seconds)")

        def done(res):
            if isinstance(res, Exception):
                self.say(False, str(res))
                return
            self._show_found(res)
            if res:
                self.say(True, f"Found {len(res)} possible phone(s) - press Connect")
            else:
                self.say(False, "Nothing found",
                         "Use step 1 with the cable, or step 3 (Wireless debugging). On a hotspot / tethering "
                         "network the phone is the gateway - make sure network mode is on.")
        self.win.bg(conn.find_phone, done)

    def _load_bluetooth(self):
        def done(devs):
            self.bt_devices = [] if isinstance(devs, Exception) else devs
            self.bt_model.splice(0, self.bt_model.get_n_items(),
                                 [d["name"] + ("  (connected)" if d["connected"] else "") for d in self.bt_devices]
                                 or ["No paired Bluetooth devices"])
        self.win.bg(conn.bluetooth_devices, done)

    def _on_bt(self):
        i = self.bt_dd.get_selected()
        if not self.bt_devices or i >= len(self.bt_devices):
            self.say(False, "Pair the phone in your system Bluetooth settings first")
            return
        mac = self.bt_devices[i]["mac"]
        self.busy("Joining the phone's Bluetooth network...")

        def work():
            res = conn.bluetooth_tether(mac)
            if res.ok:
                gw = res.message
                nxt = conn.connect(gw, 5555, timeout=6)
                if nxt.ok:
                    return nxt
                res.message = f"Bluetooth network is up. The phone is at {gw}."
                res.hint = (f"adb did not answer on {gw}:5555 ({nxt.message}). Network mode is needed: plug USB once "
                            f"and press \"Switch to Wi-Fi\" (it works for the tethering address as well). "
                            f"The ADB Link phone app can already use {gw}.")
            return res
        self.win.bg(work, self._after)

    def _on_diag(self):
        host = self.diag_addr.get_text().strip() or self.addr.get_text().strip()
        if not host:
            self.say(False, "Type the phone's address to test")
            return
        self.diag_out.set_text("Testing...")

        def done(steps):
            if isinstance(steps, Exception):
                self.diag_out.set_text(str(steps))
                return
            self.diag_out.set_markup("\n".join(
                f'<span foreground="{"#26a269" if ok else "#c01c28"}">{"✓" if ok else "✗"}</span> {GLib.markup_escape_text(t)}'
                for ok, t in steps))
        self.win.bg(lambda: conn.diagnose(host), done)
