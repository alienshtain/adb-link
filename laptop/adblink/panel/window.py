"""Main window."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path
from gi.repository import Adw, GLib, Gio, Gtk
from .adbutil import adb, first_line
from .apps_page import AppsPage
from .calls import CallBar, CallMonitor
from .commanddata import DEFAULT_COMMANDS, REMOVED_DEFAULTS, REWRITTEN_DEFAULTS
from .commands_page import CommandsPage
from .config import ICON_CACHE, PREF_DEFAULTS, load_settings, save_settings
from .contacts_page import ContactsPage
from .files_page import FilesPage
from .phone_page import PhonePage
from .phone_panel import PhonePanel
from .phone_tools import CONTACTS_CMD, SIMS_CMD, parse_contacts, parse_sims, same_number
from .settings_page import SettingsPage
from .link_page import LinkPage, LinkServer
from .phone_link_page import PhoneLinkPage
from .connect_window import ConnectWindow
from ..i18n import tr
from .ui import InfoBar
from . import compat
from .. import connect as conn, deps, desktop, storage


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="ADB Link", default_width=1400, default_height=920)
        self.settings = load_settings()
        self.favorites = set(self.settings.get("favorites", []))
        if not isinstance(self.settings.get("commands"), list) or not self.settings["commands"]:
            self.settings["commands"] = json.loads(json.dumps(DEFAULT_COMMANDS))
        self._update_default_commands()
        for c in self.settings["commands"]:
            c.setdefault("icon", "")
            c.setdefault("description", "")
            c.setdefault("confirm", False)
        self.proc, self.devices, self._updating, self._serial = None, [], False, None
        self._missing, self._tools_dismissed, self._reconnecting, self._last_rc = [], False, False, 0
        self.contacts, self.sims = None, None  # None = not read from the phone yet
        self._contacts_loading, self._contact_waiters, self._hint_shown = False, [], False
        self.link = LinkServer(self)
        self.monitor = CallMonitor(self)
        self.call_bar = CallBar(self.monitor)
        self.connect("close-request", self._on_close)

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toasts.set_child(root)

        header = Adw.HeaderBar()
        self.device_model = Gtk.StringList()
        self.device_dd = Gtk.DropDown(model=self.device_model, tooltip_text="Phone to control")
        self.device_dd.connect("notify::selected", self._on_device)
        header.pack_start(self.device_dd)
        find = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Look for phones")
        find.connect("clicked", lambda _b: self.refresh_devices())
        header.pack_start(find)
        connect_btn = Gtk.Button(css_classes=["suggested-action"], tooltip_text="Connect a phone: USB, Wi-Fi, Bluetooth")
        connect_btn.set_child(compat.content("network-wireless-symbolic", "Connect"))
        connect_btn.connect("clicked", lambda _b: self.open_connect())
        header.pack_start(connect_btn)
        self.stack = Adw.ViewStack(vexpand=True)
        header.set_title_widget(Adw.ViewSwitcher(policy=Adw.ViewSwitcherPolicy.WIDE, stack=self.stack))
        menu = Gio.Menu()
        menu.append("Reset commands to defaults", "win.reset-commands")
        menu.append("Clear app icon cache", "win.clear-icons")
        menu.append("Check helper tools", "win.check-tools")
        menu.append("Quit ADB Link", "app.quit")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu))
        self.panel_btn = Gtk.ToggleButton(icon_name="phone-symbolic", tooltip_text="Show or hide the phone panel")
        self.panel_btn.connect("toggled", lambda b: self.set_pref("phone_panel", b.get_active()))
        header.pack_end(self.panel_btn)
        root.append(header)
        for name, handler in (("reset-commands", lambda *_: self.commands_page.reset_defaults()),
                              ("check-tools", lambda *_: self.check_tools(True)),
                              ("clear-icons", lambda *_: self._clear_icons())):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

        self.commands_page = CommandsPage(self)
        self.apps, self.phone, self.files = AppsPage(self), PhonePage(self), FilesPage(self)
        self.contacts_page, self.settings_page = ContactsPage(self), SettingsPage(self)
        self.link_page = LinkPage(self)
        self.phone_link = PhoneLinkPage(self, self.phone, self.link_page)
        self.panel = PhonePanel(self)
        for page, name, title, icon in (
                (self.commands_page, "commands", "Commands", "utilities-terminal-symbolic"),
                (self.apps, "apps", "Apps", "view-app-grid-symbolic"),
                (self.files, "files", "Files", "folder-symbolic"),
                (self.contacts_page, "contacts", "Contacts", "avatar-default-symbolic"),
                (self.phone_link, "phone", "Phone", "phone-symbolic"),
                (self.settings_page, "settings", "Settings", "emblem-system-symbolic")):
            self.stack.add_titled_with_icon(page, name, title, icon)
        self.stack.connect("notify::visible-child", lambda *_: self._on_page())

        out_head = Gtk.Box(spacing=8, margin_top=6, margin_bottom=6, margin_start=12, margin_end=12)
        out_head.append(Gtk.Label(label="Output", xalign=0, hexpand=True, css_classes=["heading"]))
        self.stop_btn = Gtk.Button(label="Stop", sensitive=False, css_classes=["destructive-action"])
        self.stop_btn.connect("clicked", self.on_stop)
        clear = Gtk.Button(label="Clear")
        clear.connect("clicked", lambda _b: self.buf.set_text(""))
        out_head.append(self.stop_btn)
        out_head.append(clear)
        self.view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                 wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, bottom_margin=8,
                                 left_margin=12, right_margin=12)
        self.buf = self.view.get_buffer()
        self.end_mark = self.buf.create_mark("end", self.buf.get_end_iter(), False)
        out_scroller = Gtk.ScrolledWindow(vexpand=True, min_content_height=100)
        out_scroller.set_child(self.view)
        out_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        out_box.append(out_head)
        out_box.append(out_scroller)

        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL, vexpand=True,
                          resize_start_child=True, resize_end_child=True,
                          shrink_start_child=False, shrink_end_child=False, position=680)
        paned.set_start_child(self.stack)
        paned.set_end_child(out_box)
        paned.set_hexpand(True)
        body = Gtk.Box(vexpand=True)
        body.append(paned)
        body.append(self.panel)
        self.info_bar = InfoBar()
        root.append(self.info_bar)
        root.append(self.call_bar)
        root.append(body)
        self.apply_prefs()

        self._append("Ready. Press Connect to link a phone, then use the pages above.\n")
        self.link.apply()
        self.refresh_devices()
        GLib.timeout_add_seconds(1, lambda: (self.auto_reconnect(), False)[1])
        GLib.timeout_add_seconds(25, self.auto_reconnect)
        GLib.timeout_add_seconds(2, lambda: (self.check_tools(False), False)[1])

    # ---- shared helpers used by every page
    @property
    def commands(self):
        return self.settings["commands"]

    def save(self):
        save_settings(self.settings)

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=tr(text), timeout=4))

    def log(self, text):
        GLib.idle_add(self._append, text)

    def _append(self, text):
        line = text.strip()
        if line and not line.startswith("$"):      # our own messages are translated, adb output stays as it is
            text = text.replace(line, tr(line), 1)
        self.buf.insert(self.buf.get_end_iter(), text)
        self.view.scroll_to_mark(self.end_mark, 0.0, False, 0.0, 0.0)
        return False

    def bg(self, work, done=None):
        """Run work() in a thread; call done(result_or_exception) on the GTK thread."""
        def runner():
            try:
                result = work()
            except Exception as err:  # noqa: BLE001
                result = err
            if done:
                GLib.idle_add(done, result)
        threading.Thread(target=runner, daemon=True).start()

    def _clear_icons(self):
        shutil.rmtree(ICON_CACHE, ignore_errors=True)
        self.toast("Icon cache cleared")
        self.apps.needs_reload = True
        self._on_page()

    # ---- preferences (Settings page)
    def pref(self, key):
        return self.settings.get("prefs", {}).get(key, PREF_DEFAULTS[key])

    def set_pref(self, key, value):
        self.settings.setdefault("prefs", {})[key] = value
        self.save()
        if key == "autostart":
            self.set_autostart(bool(value))
        if key.startswith("link_"):
            self.link.apply()
            self.link_page.reload()
        self.apply_prefs()
        self.settings_page.sync()

    def apply_prefs(self):
        show = bool(self.pref("phone_panel"))
        self.panel.set_visible(show)
        if self.panel_btn.get_active() != show:
            self.panel_btn.set_active(show)
        page = self.stack.get_page(self.contacts_page)
        page.set_visible(bool(self.pref("contacts_page")))
        if not page.get_visible() and self.stack.get_visible_child() is self.contacts_page:
            self.stack.set_visible_child_name("commands")

    def restart_app(self):
        """Start a fresh copy (after a language change) and close this one."""
        try:
            subprocess.Popen(["/bin/sh", "-c", "sleep 1; " + desktop.exec_command()],
                             start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as err:
            self.toast(str(err))
            return
        self.get_application().quit()

    def set_autostart(self, on):
        try:
            desktop.set_autostart(on)
        except OSError as err:
            self.toast(f"Autostart: {err}")

    def _on_close(self, _window):
        """With 'keep running' on, closing the window only hides it so calls are still noticed."""
        if not self.pref("background"):
            return False
        self.set_visible(False)
        if not self._hint_shown:
            self._hint_shown = True
            note = Gio.Notification.new("ADB Link is still running")
            note.set_body("It keeps watching for phone calls and serving the phone app. Open it again "
                          "from the app menu, or choose Quit in its menu to close it completely.")
            self.get_application().send_notification("background", note)
        return True

    # ---- phone book, SIM cards and quick phone commands shared by the pages
    def contact_name(self, number):
        for name, num in self.contacts or []:
            if same_number(num, number):
                return name
        return ""

    def load_contacts(self, then=None, force=False):
        if self.contacts is not None and not force:
            if then:
                then()
            return
        if then:
            self._contact_waiters.append(then)
        if self._contacts_loading:
            return
        self._contacts_loading = True

        def done(res):
            self._contacts_loading = False
            if not isinstance(res, Exception) and res[0] == 0:
                self.contacts = parse_contacts(res[1])
            waiters, self._contact_waiters = self._contact_waiters, []
            for cb in waiters:
                cb()
        self.bg(lambda: adb("shell", CONTACTS_CMD, timeout=90), done)

    def load_sims(self, then):
        def done(res):
            self.sims = parse_sims(res[1]) if not isinstance(res, Exception) and res[0] == 0 else []
            then()
        self.bg(lambda: adb("shell", SIMS_CMD, timeout=20), done)

    def run_phone(self, cmd, label=None):
        """Run one shell command on the phone and only speak up when it fails."""
        def done(res):
            rc, out, err = res if not isinstance(res, Exception) else (1, "", str(res))
            if rc != 0:
                self.toast(f"{label or 'Phone'}: {first_line(out + err)}")
        self.bg(lambda: adb("shell", cmd, timeout=30), done)

    # ---- phones
    def refresh_devices(self):
        self.bg(lambda: adb("devices", "-l", timeout=15), self._devices_loaded)

    def _devices_loaded(self, result):
        if isinstance(result, Exception):
            result = (1, "", str(result))
        rc, out, err = result
        devs = conn.parse_devices(out) if rc == 0 else []
        self.devices = [(d.serial, d.state) for d in devs]
        labels = []
        for d in devs:
            name = (d.model or d.product or d.serial).replace("_", " ")
            where = "Wi-Fi" if d.over_network else "USB"
            labels.append(f"{name}  ({where})" if d.ready else f"{name}  ({d.state})")
        if rc == 127:
            labels = ["adb is not installed"]
        self._updating = True
        self.device_model.splice(0, self.device_model.get_n_items(), labels or ["No phone connected"])
        usable = [s for s, st in self.devices if st == "device"]
        current = os.environ.get("ANDROID_SERIAL")
        if current not in usable:
            current = usable[0] if usable else None
            if current:
                os.environ["ANDROID_SERIAL"] = current
            else:
                os.environ.pop("ANDROID_SERIAL", None)
        self.device_dd.set_selected(next((i for i, (s, _) in enumerate(self.devices) if s == current), 0))
        self._updating = False
        self._last_rc = rc
        self.update_bar()
        if current != self._serial:
            self._serial = current
            self._mark_stale()

    # ---- connection helpers
    def open_connect(self):
        ConnectWindow(self).present()

    def auto_reconnect(self):
        """Every so often: if no phone is usable, try the remembered Wi-Fi ones (quietly)."""
        if not self.pref("auto_reconnect") or self._reconnecting or shutil.which("adb") is None:
            return True
        if any(st == "device" for _s, st in self.devices) or not conn.saved_hosts():
            return True
        self._reconnecting = True

        def done(res):
            self._reconnecting = False
            if not isinstance(res, Exception) and res:
                self.toast("Reconnected: " + ", ".join(res))
                self.refresh_devices()
        self.bg(conn.reconnect_saved, done)
        return True

    def check_tools(self, verbose):
        self._missing = deps.missing()
        if verbose and not self._missing:
            self.toast("All helper tools are installed")
        self.update_bar()

    def update_bar(self):
        if shutil.which("adb") is None:
            self.info_bar.show_msg("adb is not installed, so no phone can be controlled.", "Install",
                                   lambda: self.link_page._install_tools(None))
        elif self._missing and not self._tools_dismissed:
            names = ", ".join(d.title.split(" (")[0] for d in self._missing[:4])
            more = f" and {len(self._missing) - 4} more" if len(self._missing) > 4 else ""
            self.info_bar.show_msg(f"Missing helper tools: {names}{more}.", "Install",
                                   lambda: (setattr(self, "_tools_dismissed", True),
                                            self.link_page._install_tools(None)))
        elif not any(st == "device" for _s, st in self.devices):
            unauth = any(st == "unauthorized" for _s, st in self.devices)
            self.info_bar.show_msg("The phone is waiting for you to tap Allow on its screen." if unauth
                                   else "No phone connected yet.", "Connect", self.open_connect)
        else:
            self.info_bar.hide_bar()

    def _on_device(self, dropdown, _p):
        index = dropdown.get_selected()
        if self._updating or index >= len(self.devices):
            return
        serial, state = self.devices[index]
        if state == "device" and serial != self._serial:
            os.environ["ANDROID_SERIAL"] = self._serial = serial
            self._mark_stale()

    def _mark_stale(self):
        self.contacts = self.sims = None
        for page in (self.apps, self.phone, self.files, self.contacts_page):
            page.needs_reload = True
        self.panel.refresh()
        self._on_page()

    def show_page(self, name):
        """Switch to a page; 'link' is the second part of the Phone page."""
        if name == "link":
            self.stack.set_visible_child_name("phone")
            self.phone_link.show("link")
        else:
            self.stack.set_visible_child_name(name)
            if name == "phone":
                self.phone_link.show("phone")

    def _on_page(self):
        page = self.stack.get_visible_child()
        if getattr(page, "needs_reload", False):
            page.reload()

    def _update_default_commands(self):
        """Older saved lists: drop commands the Apps page took over, refresh the ones that changed."""
        fresh = {c["id"]: c for c in DEFAULT_COMMANDS}
        kept = []
        for c in self.settings["commands"]:
            if c.get("id") in REMOVED_DEFAULTS:
                continue
            if c.get("id") in REWRITTEN_DEFAULTS and c.get("id") in fresh and \
                    ("~/adb-" in c.get("cmd", "") or c.get("cmd", "").startswith("adb shell input text")):
                c = json.loads(json.dumps(fresh[c["id"]]))
            kept.append(c)
        self.settings["commands"] = kept

    # ---- run a command line from the Commands page
    def run_shell(self, command, on_done=None):
        if self.proc is not None:
            self.toast("A command is still running. Wait for it or press Stop.")
            return
        self._append(f"\n$ {command}\n")
        try:
            proc = subprocess.Popen(["/bin/bash", "-c", command], stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                                    errors="replace", bufsize=1, cwd=str(Path.home()),
                                    start_new_session=True, env=self._command_env())
        except OSError as err:
            self._append(f"Could not start: {err}\n")
            return
        self.proc = proc
        self.stop_btn.set_sensitive(True)

        def reader():
            for line in proc.stdout:
                self.log(line)
            GLib.idle_add(self._finished, proc, proc.wait(), on_done)

        threading.Thread(target=reader, daemon=True).start()

    def _command_env(self):
        env = os.environ.copy()
        env["ADBLINK_DIR"] = str(storage.save_root())
        local = str(Path.home() / ".local" / "bin")
        if local not in env.get("PATH", "").split(":"):
            env["PATH"] = local + ":" + env.get("PATH", "")
        return env

    def _finished(self, proc, code, on_done):
        if self.proc is proc:
            self.proc = None
        self.stop_btn.set_sensitive(False)
        if code in (-signal.SIGTERM, -signal.SIGKILL):
            self._append("[stopped]\n")
        else:
            self._append("[done]\n" if code == 0 else f"[failed - exit code {code}]\n")
        if on_done:
            on_done()
        return False

    def on_stop(self, _button):
        if self.proc is not None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
