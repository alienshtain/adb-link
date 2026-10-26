"""Phone page: power, screen mirroring."""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import threading
from . import compat
from gi.repository import Adw, GLib, Gtk
from .adbutil import adb, first_line
from .ui import confirm_dialog


# ---------------------------------------------------------------- phone page

STATS_SCRIPT = (
    "echo @@PROP; getprop ro.product.model; getprop ro.product.manufacturer; "
    "getprop ro.build.version.release; getprop ro.build.version.sdk; "
    "getprop ro.build.version.security_patch; getprop ro.product.cpu.abi; "
    "getprop ro.build.display.id; "
    "echo @@BAT; dumpsys battery; echo @@DF; df -k /data; echo @@MEM; cat /proc/meminfo; "
    "echo @@UP; cat /proc/uptime; echo @@IP; ip -o -4 addr show; "
    "echo @@WM; wm size; wm density")
BATTERY_STATUS = {"2": "Charging", "3": "Discharging", "4": "Not charging", "5": "Full"}


def fmt_uptime(seconds):
    d, rem = divmod(int(seconds), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return (f"{d}d " if d else "") + f"{h}h {m}m"


def parse_stats(text):
    """Turn the combined phone report into a flat dict (missing values are left out)."""
    sec, cur = {}, None
    for line in text.splitlines():
        if line.startswith("@@"):
            cur = line[2:].strip()
            sec[cur] = []
        elif cur:
            sec[cur].append(line.rstrip())
    info = {}
    props = [p.strip() for p in sec.get("PROP", [])]
    for key, value in zip(("model", "maker", "android", "sdk", "patch", "abi", "build"),
                          props + [""] * 7):
        info[key] = value
    bat = {}
    for line in sec.get("BAT", []):
        key, _, value = line.partition(":")
        bat[key.strip().lower()] = value.strip()
    if bat.get("level", "").isdigit():
        info["battery"] = int(bat["level"])
        info["battery_state"] = BATTERY_STATUS.get(bat.get("status", ""), "Unknown")
        info["plugged"] = ("USB" if bat.get("usb powered") == "true" else
                           "AC" if bat.get("ac powered") == "true" else
                           "Wireless" if bat.get("wireless powered") == "true" else "")
        if bat.get("temperature", "").lstrip("-").isdigit():
            info["temp"] = int(bat["temperature"]) / 10
        if bat.get("voltage", "").isdigit():
            info["volt"] = int(bat["voltage"]) / 1000
    tokens = " ".join(l for l in sec.get("DF", [])[1:] if l.strip()).split()
    idx = next((i for i, t in enumerate(tokens) if t.isdigit()), None)
    if idx is not None and len(tokens) >= idx + 3:
        info["disk_total"], info["disk_used"] = int(tokens[idx]) * 1024, int(tokens[idx + 1]) * 1024
    mem = {}
    for line in sec.get("MEM", []):
        m = re.match(r"(\w+):\s+(\d+)", line)
        if m:
            mem[m.group(1)] = int(m.group(2)) * 1024
    if "MemTotal" in mem and "MemAvailable" in mem:
        info["mem_total"], info["mem_used"] = mem["MemTotal"], mem["MemTotal"] - mem["MemAvailable"]
    up = " ".join(sec.get("UP", [])).split()
    if up:
        try:
            info["uptime"] = float(up[0])
        except ValueError:
            pass
    ips = []
    for line in sec.get("IP", []):
        m = re.search(r"\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)", line)
        if m and m.group(1) != "lo":
            ips.append(f"{m.group(1)}  {m.group(2)}")
    info["ips"] = ips
    wm = " ".join(sec.get("WM", []))
    size, dens = re.search(r"size:\s*(\d+x\d+)", wm), re.search(r"density:\s*(\d+)", wm)
    info["screen"] = (size.group(1) if size else "") + (f" @ {dens.group(1)} dpi" if dens else "")
    return info


class PhonePage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win, self.needs_reload, self.loading = win, False, False
        self.scrcpy = None

        power = Adw.PreferencesGroup(title="Power and screen")
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                           min_children_per_line=2, max_children_per_line=6,
                           row_spacing=8, column_spacing=8)
        actions = [
            ("Lock screen", "system-lock-screen-symbolic", ["shell", "input", "keyevent", "223"], None),
            ("Wake screen", "display-brightness-symbolic", ["shell", "input", "keyevent", "224"], None),
            ("Reboot", "system-reboot-symbolic", ["reboot"], "The phone will restart."),
            ("Shut down", "system-shutdown-symbolic",
             ["shell", "reboot -p || svc power shutdown"],
             "The phone will turn off. You must press its power button to start it again."),
            ("Recovery", "applications-system-symbolic", ["reboot", "recovery"],
             "The phone will restart into recovery mode."),
            ("Bootloader", "applications-system-symbolic", ["reboot", "bootloader"],
             "The phone will restart into the bootloader."),
        ]
        for label, icon, argv, warn in actions:
            btn = Gtk.Button()
            btn.set_child(compat.content(icon, label))
            btn.connect("clicked", lambda _b, l=label, a=argv, w=warn: self.power(l, a, w))
            flow.append(btn)
        power.add(flow)
        self.add(power)

        mirror = Adw.PreferencesGroup(title="Mirror and control (scrcpy)",
                                      description="Opens the phone screen in a window you can use "
                                                  "with the mouse and keyboard.")
        row = Gtk.Box(spacing=8)
        for label, extra in (("Open scrcpy", []), ("Phone screen off", ["-S"]), ("Stay awake", ["-w"])):
            btn = Gtk.Button(label=label, css_classes=["suggested-action"] if not extra else [])
            btn.connect("clicked", lambda _b, e=extra: self.start_scrcpy(e))
            row.append(btn)
        self.stop_btn = Gtk.Button(label="Stop", sensitive=False, css_classes=["destructive-action"])
        self.stop_btn.connect("clicked", self.stop_scrcpy)
        row.append(self.stop_btn)
        mirror.add(row)
        self.add(mirror)

    def reload(self):
        """The phone information moved to the panel on the right (the (i) button)."""
        self.needs_reload = False

    # ---- power
    def power(self, label, argv, warning):
        def go():
            self.win.log(f"$ adb {' '.join(argv)}\n")

            def done(res):
                rc, out, err = res if not isinstance(res, Exception) else (1, "", str(res))
                text = (out + err).strip()
                if text:
                    self.win.log(text + "\n")
                self.win.toast(f"{label}: done" if rc == 0 else f"{label}: {first_line(text)}")

            self.win.bg(lambda: adb(*argv, timeout=30), done)

        if warning:
            confirm_dialog(self.win, f"{label}?", warning, label, go)
        else:
            go()

    # ---- scrcpy
    def start_scrcpy(self, extra):
        exe = shutil.which("scrcpy")
        if not exe:
            self.win.toast("scrcpy is not installed. Run: sudo dnf install scrcpy")
            return
        if self.scrcpy and self.scrcpy.poll() is None:
            self.win.toast("scrcpy is already running")
            return
        try:
            proc = subprocess.Popen([exe, *extra], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, errors="replace",
                                    start_new_session=True)
        except OSError as err:
            self.win.toast(f"Could not start scrcpy: {err}")
            return
        self.scrcpy = proc
        self.stop_btn.set_sensitive(True)
        threading.Thread(target=self._watch_scrcpy, args=(proc,), daemon=True).start()

    def _watch_scrcpy(self, proc):
        tail = []
        for line in proc.stdout:
            tail.append(line)
            del tail[:-15]
        GLib.idle_add(self._scrcpy_done, proc, proc.wait(), "".join(tail))

    def _scrcpy_done(self, proc, code, tail):
        if self.scrcpy is proc:
            self.scrcpy = None
            self.stop_btn.set_sensitive(False)
        if code > 0:
            self.win.log("scrcpy stopped:\n" + tail)
            lines = tail.strip().splitlines()
            self.win.toast("scrcpy stopped: " + (lines[-1] if lines else "error"))
        return False

    def stop_scrcpy(self, _b):
        if self.scrcpy and self.scrcpy.poll() is None:
            try:
                os.killpg(self.scrcpy.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
