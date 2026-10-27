"""Finds out which helper programs are missing and installs them with the system's package manager.

Run ``adblink doctor`` to see the list and ``adblink install-deps`` to install what is missing.
Works with apt (Ubuntu, Debian, Mint, Pop!_OS), dnf (Fedora, RHEL), pacman (Arch, Manjaro) and zypper (openSUSE).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field


@dataclass
class Dep:
    key: str
    title: str
    why: str
    level: str                       # core | recommended | optional
    binaries: tuple = ()             # any one of these on PATH counts
    pypi: str = ""                   # importable python module that counts
    pkgs: dict = field(default_factory=dict)   # manager -> list of package names
    when: str = ""                   # "gnome" | "kde" | "wlroots" | "x11" | "wayland" | "gui" ... only needed there


def _p(apt, dnf=None, pacman=None, zypper=None):
    dnf = apt if dnf is None else dnf
    return {"apt": apt.split(), "dnf": dnf.split(), "pacman": (pacman or apt).split(), "zypper": (zypper or dnf).split()}


DEPS = [
    Dep("adb", "adb (Android platform tools)", "Talks to the phone over USB or network", "core", ("adb",), "",
        _p("adb", "android-tools", "android-tools", "android-tools")),
    Dep("gtk", "GTK 4 + libadwaita + PyGObject", "The ADB Link window", "core", (), "gi",
        {"apt": ["python3-gi", "gir1.2-gtk-4.0", "gir1.2-adw-1"],
         "dnf": ["python3-gobject", "gtk4", "libadwaita"],
         "pacman": ["python-gobject", "gtk4", "libadwaita"],
         "zypper": ["python3-gobject", "python3-gobject-Gdk", "typelib-1_0-Gtk-4_0", "typelib-1_0-Adw-1"]}),
    Dep("scrcpy", "scrcpy", "Shows and controls the phone screen on the computer", "recommended", ("scrcpy",), "",
        _p("scrcpy")),
    Dep("brightnessctl", "brightnessctl", "Brightness buttons for the computer", "recommended", ("brightnessctl",), "",
        _p("brightnessctl")),
    Dep("playerctl", "playerctl", "Pause / resume music when a call comes, media keys", "recommended", ("playerctl",), "",
        _p("playerctl")),
    Dep("pactl", "pactl (PulseAudio / PipeWire tools)", "Volume buttons for the computer", "recommended", ("pactl",), "",
        {"apt": ["pulseaudio-utils"], "dnf": ["pulseaudio-utils"], "pacman": ["libpulse"], "zypper": ["pulseaudio-utils"]}),
    Dep("notify", "notify-send", "Desktop notifications", "recommended", ("notify-send",), "",
        {"apt": ["libnotify-bin"], "dnf": ["libnotify"], "pacman": ["libnotify"], "zypper": ["libnotify-tools"]}),
    Dep("wlclip", "wl-clipboard", "Clipboard sharing and typing other languages (Wayland)", "recommended",
        ("wl-copy",), "", _p("wl-clipboard"), when="wayland"),
    Dep("xclip", "xclip", "Clipboard sharing without flicker (X11, and GNOME on Wayland)", "recommended", ("xclip", "xsel"), "", _p("xclip")),
    Dep("pillow", "Pillow (Python imaging)", "Picture previews for the phone app", "recommended", (), "PIL",
        {"apt": ["python3-pil"], "dnf": ["python3-pillow"], "pacman": ["python-pillow"], "zypper": ["python3-Pillow"]}),
    Dep("bluez", "bluez (bluetoothctl)", "Connect over Bluetooth tethering", "optional", ("bluetoothctl",), "",
        {"apt": ["bluez"], "dnf": ["bluez"], "pacman": ["bluez-utils"], "zypper": ["bluez"]}),
    Dep("acl", "acl (setfacl)", "Lets remote input start working without logging out", "optional", ("setfacl",), "",
        _p("acl")),
    Dep("xdotool", "xdotool", "Backup for remote mouse/keyboard on X11", "optional", ("xdotool",), "", _p("xdotool"), when="x11"),
    Dep("iproute", "iproute2 (ip)", "Finding the phone on the network", "recommended", ("ip",), "",
        {"apt": ["iproute2"], "dnf": ["iproute"], "pacman": ["iproute2"], "zypper": ["iproute2"]}),
]


# ----------------------------------------------------------------------------- environment

def manager():
    for name, exe in (("apt", "apt-get"), ("dnf", "dnf"), ("pacman", "pacman"), ("zypper", "zypper")):
        if shutil.which(exe):
            return name
    return ""


def session():
    """('gnome'|'kde'|'wlroots'|'other', 'wayland'|'x11')"""
    desk = (os.environ.get("XDG_CURRENT_DESKTOP", "") + ":" + os.environ.get("DESKTOP_SESSION", "")).lower()
    kind = "wayland" if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or os.environ.get("WAYLAND_DISPLAY") else "x11"
    if "gnome" in desk or "ubuntu" in desk or "unity" in desk or "cinnamon" in desk or "budgie" in desk or "pantheon" in desk:
        d = "gnome"
    elif "kde" in desk or "plasma" in desk:
        d = "kde"
    elif any(x in desk for x in ("sway", "hypr", "wlroots", "river", "niri")):
        d = "wlroots"
    else:
        d = "other"
    return d, kind


def applies(dep, desk=None, kind=None):
    if not dep.when:
        return True
    if desk is None:
        desk, kind = session()
    if dep.when in ("gnome", "kde", "wlroots"):
        return desk == dep.when or (dep.when == "gnome" and desk == "other" and kind == "wayland")
    if dep.when == "wayland":
        return kind == "wayland"
    if dep.when == "x11":
        return True  # the X11 tools are also used by XWayland apps and are tiny
    return True


def present(dep):
    if any(shutil.which(b) for b in dep.binaries):
        return True
    if dep.pypi:
        try:
            __import__(dep.pypi)
            return True
        except Exception:
            return False
    return False


def report(levels=("core", "recommended")):
    """[(dep, ok)] for the tools that make sense on this computer."""
    desk, kind = session()
    out = []
    for d in DEPS:
        if d.level in levels and applies(d, desk, kind):
            out.append((d, present(d)))
    # one screenshot tool is enough
    shots = [(d, ok) for d, ok in out if d.key.startswith("shot-")]
    if any(ok for _d, ok in shots):
        out = [(d, ok) for d, ok in out if not d.key.startswith("shot-") or ok]
    return out


def missing(levels=("core", "recommended")):
    return [d for d, ok in report(levels) if not ok]


# ----------------------------------------------------------------------------- installing

def install_command(mgr, packages):
    if mgr == "apt":
        return ["apt-get", "install", "-y", *packages]
    if mgr == "dnf":
        return ["dnf", "install", "-y", *packages]
    if mgr == "pacman":
        return ["pacman", "-S", "--needed", "--noconfirm", *packages]
    if mgr == "zypper":
        return ["zypper", "--non-interactive", "install", *packages]
    return []


def _elevate(argv):
    if os.geteuid() == 0:
        return argv
    if shutil.which("sudo") and sys.stdin.isatty():
        return ["sudo", *argv]
    if shutil.which("pkexec"):
        return ["pkexec", *argv]
    if shutil.which("sudo"):
        return ["sudo", *argv]
    return argv


def install(deps, say=print):
    """Install the packages for ``deps``. One by one if the bulk install fails (so one bad name never blocks the rest).
    Returns (installed_titles, failed_titles)."""
    mgr = manager()
    if not mgr:
        say("No supported package manager found (apt, dnf, pacman, zypper). Install these by hand: "
            + ", ".join(d.title for d in deps))
        return [], [d.title for d in deps]
    if mgr == "apt":
        subprocess.call(_elevate(["apt-get", "update", "-qq"]))
    elif mgr == "zypper":
        subprocess.call(_elevate(["zypper", "--non-interactive", "refresh"]))
    done, failed = [], []
    allpk = []
    for d in deps:
        allpk += [p for p in d.pkgs.get(mgr, []) if p not in allpk]
    if allpk:
        say(f"Installing with {mgr}: {' '.join(allpk)}")
        subprocess.call(_elevate(install_command(mgr, allpk)))
    for d in deps:
        if present(d):
            done.append(d.title)
            continue
        # bulk install failed or skipped this one: try its packages one by one
        for pk in d.pkgs.get(mgr, []):
            subprocess.call(_elevate(install_command(mgr, [pk])), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (done if present(d) else failed).append(d.title)
    return done, failed


def doctor_text(levels=("core", "recommended", "optional")):
    lines = []
    desk, kind = session()
    lines.append(f"Desktop: {desk}   Session: {kind}   Package manager: {manager() or 'unknown'}")
    lines.append("")
    for d, ok in report(levels):
        lines.append(f"  {'ok     ' if ok else 'MISSING'}  {d.title:42s} {d.why}")
    try:
        from .server.inputdev import uinput_status
        ok, msg = uinput_status()
        lines.append(f"  {'ok     ' if ok else 'MISSING'}  {'Remote mouse/keyboard (uinput)':42s} "
                     + ("ready" if ok else msg))
    except Exception:
        pass
    return "\n".join(lines)
