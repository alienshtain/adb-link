"""Incoming-call popup, bar and monitor."""
from __future__ import annotations

import threading
import time
from . import compat
from gi.repository import Adw, GLib, Gio, Gtk, Pango
from .adbutil import adb
from .apps_helpers import avatar
from .phone_tools import CALL_SCRIPT, parse_call_state, pause_media, resume_media
from .ui import clear_children, close_on_escape, make_icon


# ---------------------------------------------------------------- calls

class CallPopup(Gtk.Window):
    """A small window that appears when the phone rings: answer, reject or end the call."""

    def __init__(self, win, monitor):
        super().__init__(title="Phone call", default_width=340, resizable=False,
                         application=win.get_application())
        self.monitor, self.mode, self.started = monitor, "ringing", 0
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=26,
                      margin_bottom=22, margin_start=26, margin_end=26)
        self.holder = Gtk.Box(halign=Gtk.Align.CENTER)
        self.name = Gtk.Label(css_classes=["title-2"], wrap=True, justify=Gtk.Justification.CENTER)
        self.number = Gtk.Label(css_classes=["dim-label"])
        self.status = Gtk.Label(css_classes=["heading"], margin_top=6)
        for w in (self.holder, self.name, self.number, self.status):
            box.append(w)
        self.buttons = Gtk.Box(spacing=14, halign=Gtk.Align.CENTER, margin_top=14)
        self.reject_btn = Gtk.Button(css_classes=["pill", "call-reject"])
        self.reject_btn.set_child(compat.content("call-stop-symbolic", "Reject"))
        self.answer_btn = Gtk.Button(css_classes=["pill", "call-answer"])
        self.answer_btn.set_child(compat.content("call-start-symbolic", "Answer"))
        self.end_btn = Gtk.Button(css_classes=["pill", "call-reject"])
        self.end_btn.set_child(compat.content("call-stop-symbolic", "End call"))
        self.reject_btn.connect("clicked", lambda _b: monitor.reject())
        self.answer_btn.connect("clicked", lambda _b: monitor.answer())
        self.end_btn.connect("clicked", lambda _b: monitor.hangup())
        for b in (self.reject_btn, self.answer_btn, self.end_btn):
            self.buttons.append(b)
        box.append(self.buttons)
        self.set_child(box)
        close_on_escape(self)
        self.set_mode("ringing")

    def set_caller(self, name, number):
        clear_children(self.holder)
        shown = name or number or "Unknown number"
        big = avatar(shown, 88)
        big.add_css_class("big-avatar")
        self.holder.append(big)
        self.name.set_text(shown)
        self.number.set_text(number if name and number else "")

    def set_mode(self, mode):
        self.mode = mode
        ringing = mode == "ringing"
        self.reject_btn.set_visible(ringing)
        self.answer_btn.set_visible(ringing)
        self.end_btn.set_visible(not ringing)
        if ringing:
            self.status.set_text("Incoming call...")
        else:
            self.started = time.monotonic()
            self.status.set_text("00:00")
            GLib.timeout_add_seconds(1, self._tick, self.started)

    def _tick(self, started):
        if self.mode != "talking" or self.started != started:
            return False
        secs = int(time.monotonic() - started)
        self.status.set_text(f"{secs // 60:02d}:{secs % 60:02d}")
        return True


class CallBar(Gtk.Revealer):
    """A coloured strip at the top of the window while a call is ringing or running."""

    def __init__(self, monitor):
        super().__init__(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        row = Gtk.Box(spacing=10, css_classes=["call-bar"])
        row.append(make_icon("call-start-symbolic", 20))
        self.label = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
        row.append(self.label)
        self.reject_btn = Gtk.Button(label="Reject", css_classes=["destructive-action"])
        self.answer_btn = Gtk.Button(label="Answer", css_classes=["suggested-action"])
        self.end_btn = Gtk.Button(label="End call", css_classes=["destructive-action"])
        self.reject_btn.connect("clicked", lambda _b: monitor.reject())
        self.answer_btn.connect("clicked", lambda _b: monitor.answer())
        self.end_btn.connect("clicked", lambda _b: monitor.hangup())
        for b in (self.reject_btn, self.answer_btn, self.end_btn):
            row.append(b)
        self.set_child(row)

    def show_call(self, mode, text):
        self.label.set_text(text)
        ringing = mode == "ringing"
        self.reject_btn.set_visible(ringing)
        self.answer_btn.set_visible(ringing)
        self.end_btn.set_visible(not ringing)
        self.set_reveal_child(True)


class CallMonitor:
    """Watches the phone's call state with adb (every 2 seconds) and reacts to calls."""

    def __init__(self, win):
        self.win, self.state, self.number = win, "idle", ""
        self.busy, self.sim, self.rejected = False, False, False
        self.paused, self.popup, self.ticks = [], None, 0
        GLib.timeout_add_seconds(2, self._tick)

    # ---- polling
    def _tick(self):
        win = self.win
        if self.sim or not win.pref("watch_calls"):
            return True
        if not win._serial:
            self.ticks += 1
            if self.ticks % 5 == 0:
                win.refresh_devices()
            return True
        if not self.busy:
            self.busy = True
            win.bg(lambda: adb("shell", CALL_SCRIPT, timeout=8), self._got)
        return True

    def _got(self, res):
        self.busy = False
        if isinstance(res, Exception) or self.sim:
            return
        rc, out, _err = res
        if rc == 0 and "mCallState" in out:
            self.update(*parse_call_state(out))

    # ---- state changes
    def update(self, state, number=""):
        prev = self.state
        if state == "ringing" and prev == "ringing":
            if number and number != self.number:  # the number often arrives a moment later
                self.number = number
                self._show("ringing")
            return
        if state == prev:
            return
        self.state = state
        if state == "ringing":
            self.number, self.rejected = number, False
            self._ring()
        elif state == "offhook":
            if prev == "idle":
                self.number = number or self.number
                self._pause_media()
            self._show("talking")
        else:
            self._ended(prev)

    def caller(self):
        return self.win.contact_name(self.number), self.number

    def _label(self, mode="ringing"):
        name, number = self.caller()
        return name or number or ("Unknown number" if mode == "ringing" else "Phone call")

    def _mode(self):
        return "ringing" if self.state == "ringing" else "talking"

    def _ring(self):
        win = self.win
        self._pause_media()
        if self.number and win.contacts is None:
            win.load_contacts(lambda: self._show(self._mode()) if self.state != "idle" else None)
        self._show("ringing")
        if win.pref("call_popup"):
            win.present()
            if self.popup:
                self.popup.present()

    def _show(self, mode):
        win = self.win
        name, number = self.caller()
        label = self._label(mode)
        if self.popup is None and mode == "ringing" and win.pref("call_popup"):
            self.popup = CallPopup(win, self)
            self.popup.connect("close-request", self._popup_closed)
        if self.popup:
            self.popup.set_caller(name, number)
            if self.popup.mode != ("ringing" if mode == "ringing" else "talking"):
                self.popup.set_mode("ringing" if mode == "ringing" else "talking")
            self.popup.present()
        win.call_bar.show_call(mode, f"{'Incoming call' if mode == 'ringing' else 'In call'}: {label}")
        if mode == "ringing" and win.pref("call_notify"):
            self._notify_ring(label, number)

    def _popup_closed(self, _popup):
        self.popup = None
        return False

    def _notify_ring(self, label, number):
        app = self.win.get_application()
        n = Gio.Notification.new("Incoming call")
        n.set_body(label + (f"\n{number}" if number and number != label else ""))
        n.set_priority(Gio.NotificationPriority.URGENT)
        n.set_icon(Gio.ThemedIcon.new("call-start-symbolic"))
        n.add_button("Answer", "app.call-answer")
        n.add_button("Reject", "app.call-reject")
        n.set_default_action("app.call-show")
        app.send_notification("phone-call", n)

    def _ended(self, prev):
        win, app = self.win, self.win.get_application()
        app.withdraw_notification("phone-call")
        win.call_bar.set_reveal_child(False)
        if self.popup:
            popup, self.popup = self.popup, None
            popup.close()
        if self.paused and win.pref("resume_media"):
            names, self.paused = self.paused, []
            threading.Thread(target=resume_media, args=(names,), daemon=True).start()
        self.paused = []
        if prev == "ringing" and not self.rejected and win.pref("call_notify"):
            n = Gio.Notification.new("Missed call")
            n.set_body(self._label())
            n.set_icon(Gio.ThemedIcon.new("call-missed-symbolic"))
            n.set_default_action("app.call-show")
            app.send_notification("phone-missed", n)
        self.number, self.sim = "", False

    def _pause_media(self):
        if self.win.pref("pause_media") and not self.paused:
            def work():
                self.paused = pause_media()
            threading.Thread(target=work, daemon=True).start()

    # ---- buttons
    def answer(self):
        if self.sim:
            self.update("offhook", self.number)
            return

        def work():
            adb("shell", "input keyevent 5", timeout=10)
            time.sleep(1.5)
            _rc, out, _err = adb("shell", CALL_SCRIPT, timeout=8)
            if "mCallState=1" in out:
                adb("shell", "input keyevent 79", timeout=10)
        self.win.bg(work)

    def reject(self):
        self.rejected = True
        self.hangup()

    def hangup(self):
        if self.sim:
            self.update("idle")
            return
        self.win.bg(lambda: adb("shell", "input keyevent 6", timeout=10))

    def simulate(self):
        """Shows what a call looks like without a real call (Settings > Test)."""
        self.sim = True
        self.state = "idle"
        self.update("ringing", "07701234567")
