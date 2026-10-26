"""Remote mouse and keyboard for the phone's touchpad.

Three backends, tried in this order:

* ``uinput``  - writes straight to /dev/uinput. Works on Wayland *and* X11, needs no helper
                program and no daemon. It only needs permission to open /dev/uinput once:
                run ``adblink setup-input`` (the installer does it for you).
* ``ydotool`` - needs the ydotoold daemon (Wayland).
* ``xdotool`` - X11 only.
"""
from __future__ import annotations

import fcntl
import os
import struct
import threading
import time

from .clipboard import _clip_state, set_clipboard
from .common import ApiError, IS_LINUX, is_wayland, run_env, run_quiet, which

# ----------------------------------------------------------------------------- key tables

EV_SYN, EV_KEY, EV_REL = 0, 1, 2
REL_X, REL_Y, REL_HWHEEL, REL_WHEEL = 0, 1, 6, 8
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE = 0x110, 0x111, 0x112

_ROW = {c: i for i, c in enumerate("qwertyuiop", 16)}
_ROW.update({c: i for i, c in enumerate("asdfghjkl", 30)})
_ROW.update({c: i for i, c in enumerate("zxcvbnm", 44)})
KEYS = dict(_ROW)
KEYS.update({str(d): c for d, c in zip("1234567890", range(2, 12))})
KEYS.update({"esc": 1, "minus": 12, "equal": 13, "backspace": 14, "tab": 15, "lbracket": 26,
             "rbracket": 27, "enter": 28, "semicolon": 39, "apostrophe": 40, "grave": 41,
             "backslash": 43, "comma": 51, "dot": 52, "slash": 53, "space": 57, "capslock": 58,
             "home": 102, "up": 103, "pageup": 104, "left": 105, "right": 106, "end": 107, "down": 108,
             "pagedown": 109, "insert": 110, "delete": 111, "mute": 113, "volumedown": 114,
             "volumeup": 115, "playpause": 164, "next": 163, "prev": 165, "print": 99, "menu": 127})
KEYS.update({f"f{i}": c for i, c in zip(range(1, 11), range(59, 69))})
KEYS.update({"f11": 87, "f12": 88})
MODS = {"ctrl": 29, "shift": 42, "alt": 56, "super": 125, "win": 125, "meta": 125}

# printable ASCII on a US layout: char -> (key name, needs shift)
CHARS = {}
for ch in "abcdefghijklmnopqrstuvwxyz":
    CHARS[ch] = (ch, False)
    CHARS[ch.upper()] = (ch, True)
for d, s in zip("1234567890", "!@#$%^&*()"):
    CHARS[d] = (d, False)
    CHARS[s] = (d, True)
for plain, shifted, name in (("-", "_", "minus"), ("=", "+", "equal"), ("[", "{", "lbracket"),
                             ("]", "}", "rbracket"), (";", ":", "semicolon"), ("'", '"', "apostrophe"),
                             ("`", "~", "grave"), ("\\", "|", "backslash"), (",", "<", "comma"),
                             (".", ">", "dot"), ("/", "?", "slash")):
    CHARS[plain] = (name, False)
    CHARS[shifted] = (name, True)
CHARS[" "] = ("space", False)
CHARS["\n"] = ("enter", False)
CHARS["\t"] = ("tab", False)

XDO_NAMES = {"esc": "Escape", "tab": "Tab", "backspace": "BackSpace", "enter": "Return", "up": "Up",
             "down": "Down", "left": "Left", "right": "Right", "home": "Home", "end": "End",
             "pageup": "Prior", "pagedown": "Next", "delete": "Delete", "space": "space",
             "insert": "Insert", "mute": "XF86AudioMute", "volumedown": "XF86AudioLowerVolume",
             "volumeup": "XF86AudioRaiseVolume", "playpause": "XF86AudioPlay",
             "next": "XF86AudioNext", "prev": "XF86AudioPrev", "super": "super", "win": "super",
             "print": "Print", "menu": "Menu"}


def parse_combo(text: str):
    """'ctrl+shift+t' -> (['ctrl', 'shift'], 't'). Raises ApiError for unknown keys."""
    parts = [p.strip().lower() for p in str(text).split("+") if p.strip()]
    if not parts:
        raise ApiError(400, "Empty key")
    mods, key = parts[:-1], parts[-1]
    if key == "plus":
        key = "equal"
        mods.append("shift")
    if any(m not in MODS for m in mods) or key not in KEYS and key not in MODS:
        raise ApiError(400, f"Unknown key: {text}")
    return mods, key


# ----------------------------------------------------------------------------- uinput

UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_RELBIT = 0x40045566
UI_DEV_SETUP = 0x405C5503
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
_EVENT = struct.Struct("llHHi")  # timeval (sec, usec), type, code, value  (64-bit Linux)
_EVENT_32 = struct.Struct("iiHHi")


class UInput:
    """One virtual mouse + keyboard. Created lazily and kept for the life of the server."""
    name = "uinput"

    def __init__(self):
        self.fd = -1
        self.lock = threading.Lock()
        self.struct = _EVENT if struct.calcsize("l") == 8 else _EVENT_32

    def open(self):
        if self.fd >= 0:
            return
        fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_REL)
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_SYN)
            for code in range(1, 249):
                fcntl.ioctl(fd, UI_SET_KEYBIT, code)
            for code in (BTN_LEFT, BTN_RIGHT, BTN_MIDDLE):
                fcntl.ioctl(fd, UI_SET_KEYBIT, code)
            for code in (REL_X, REL_Y, REL_HWHEEL, REL_WHEEL):
                fcntl.ioctl(fd, UI_SET_RELBIT, code)
            name = b"ADB Link virtual input".ljust(80, b"\0")
            setup = struct.pack("HHHH80sI", 0x06, 0x1209, 0xAD8B, 1, name, 0)  # BUS_VIRTUAL
            fcntl.ioctl(fd, UI_DEV_SETUP, setup)
            fcntl.ioctl(fd, UI_DEV_CREATE)
        except OSError:
            os.close(fd)
            raise
        self.fd = fd
        time.sleep(0.25)  # the desktop needs a moment to notice the new device

    def close(self):
        if self.fd >= 0:
            try:
                fcntl.ioctl(self.fd, UI_DEV_DESTROY)
            except OSError:
                pass
            os.close(self.fd)
            self.fd = -1

    def _emit(self, etype, code, value):
        now = time.time()
        os.write(self.fd, self.struct.pack(int(now), int((now % 1) * 1e6), etype, code, value))

    def _sync(self):
        self._emit(EV_SYN, 0, 0)

    def _do(self, fn):
        with self.lock:
            self.open()
            try:
                fn()
            except OSError:
                self.close()  # the next call reopens the device
                raise

    # ---- actions
    def move(self, dx, dy):
        def f():
            if dx:
                self._emit(EV_REL, REL_X, dx)
            if dy:
                self._emit(EV_REL, REL_Y, dy)
            self._sync()
        self._do(f)

    def button(self, name, down):
        code = {"left": BTN_LEFT, "right": BTN_RIGHT, "middle": BTN_MIDDLE}.get(name, BTN_LEFT)

        def f():
            self._emit(EV_KEY, code, 1 if down else 0)
            self._sync()
        self._do(f)

    def click(self, name="left", count=1):
        for i in range(max(1, min(count, 3))):
            self.button(name, True)
            time.sleep(0.02)
            self.button(name, False)
            if i:
                time.sleep(0.03)

    def scroll(self, dy=0, dx=0):
        def f():
            if dy:
                self._emit(EV_REL, REL_WHEEL, dy)
            if dx:
                self._emit(EV_REL, REL_HWHEEL, dx)
            self._sync()
        self._do(f)

    def _press(self, codes):
        def f():
            for c in codes:
                self._emit(EV_KEY, c, 1)
                self._sync()
            for c in reversed(codes):
                self._emit(EV_KEY, c, 0)
                self._sync()
        self._do(f)

    def key(self, combo):
        mods, key = parse_combo(combo)
        codes = [MODS[m] for m in mods] + [KEYS.get(key) or MODS[key]]
        self._press(codes)

    def text(self, text):
        for ch in text:
            name, shift = CHARS[ch]
            self._press(([MODS["shift"]] if shift else []) + [KEYS[name]])
            time.sleep(0.004)

    def can_type(self, text):
        return all(ch in CHARS for ch in text)

    def paste(self):
        self._press([MODS["ctrl"], KEYS["v"]])


_uinput = UInput()


def uinput_status():
    """(ok, message). ok means /dev/uinput can be opened by this user."""
    if not IS_LINUX:
        return False, "uinput is Linux only"
    if not os.path.exists("/dev/uinput"):
        return False, "The uinput kernel module is not loaded. Run:  adblink setup-input"
    if os.access("/dev/uinput", os.W_OK):
        return True, "ok"
    return False, "No permission for /dev/uinput. Run once:  adblink setup-input"


# ----------------------------------------------------------------------------- xdotool / ydotool

class XdoTool:
    name = "xdotool"

    def _run(self, *argv):
        rc, _o, err = run_quiet(list(argv), timeout=5)
        if rc != 0:
            raise ApiError(500, err.splitlines()[0] if err else "input failed")

    def move(self, dx, dy):
        self._run("xdotool", "mousemove_relative", "--", str(dx), str(dy))

    def click(self, name="left", count=1):
        self._run("xdotool", "click", "--repeat", str(count), {"left": "1", "middle": "2", "right": "3"}[name])

    def button(self, name, down):
        self._run("xdotool", "mousedown" if down else "mouseup", {"left": "1", "middle": "2", "right": "3"}[name])

    def scroll(self, dy=0, dx=0):
        if dy:
            self._run("xdotool", "click", "--repeat", str(abs(dy)), "4" if dy > 0 else "5")
        if dx:
            self._run("xdotool", "click", "--repeat", str(abs(dx)), "7" if dx > 0 else "6")

    def key(self, combo):
        mods, key = parse_combo(combo)
        names = [XDO_NAMES.get(m, m) for m in mods] + [XDO_NAMES.get(key, key)]
        self._run("xdotool", "key", "+".join(names))

    def text(self, text):
        self._run("xdotool", "type", "--delay", "5", "--", text)

    def can_type(self, text):
        return text.isascii()

    def paste(self):
        self._run("xdotool", "key", "ctrl+v")


class YdoTool:
    name = "ydotool"

    def _run(self, *argv):
        rc, _o, err = run_quiet(list(argv), timeout=5)
        if rc != 0:
            raise ApiError(500, err.splitlines()[0] if err else "input failed")

    def move(self, dx, dy):
        self._run("ydotool", "mousemove", "-x", str(dx), "-y", str(dy))

    def click(self, name="left", count=1):
        code = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}[name]
        for _ in range(count):
            self._run("ydotool", "click", code)

    def button(self, name, down):
        base = {"left": 0, "right": 1, "middle": 2}[name]
        self._run("ydotool", "click", hex(base | (0x40 if down else 0x80)))

    def scroll(self, dy=0, dx=0):
        self._run("ydotool", "mousemove", "-w", "-x", str(dx), "-y", str(dy))

    def key(self, combo):
        mods, key = parse_combo(combo)
        codes = [MODS[m] for m in mods] + [KEYS.get(key) or MODS[key]]
        args = [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
        self._run("ydotool", "key", *args)

    def text(self, text):
        self._run("ydotool", "type", "--", text)

    def can_type(self, text):
        return text.isascii()

    def paste(self):
        self._run("ydotool", "key", "29:1", "47:1", "47:0", "29:0")


def _ydotool_ready():
    run = run_env().get("XDG_RUNTIME_DIR", "")
    socks = [os.environ.get("YDOTOOL_SOCKET", ""), f"{run}/.ydotool_socket", "/tmp/.ydotool_socket"]
    return any(s and os.path.exists(s) for s in socks)


def input_backend():
    """Name of the backend that will be used, or None."""
    if not IS_LINUX:
        return None
    if uinput_status()[0]:
        return "uinput"
    if which("ydotool") and _ydotool_ready():
        return "ydotool"
    if which("xdotool") and run_env().get("DISPLAY") and not is_wayland():
        return "xdotool"
    if which("xdotool") and run_env().get("DISPLAY"):
        return "xdotool"  # Wayland with XWayland: only X11 windows follow it, better than nothing
    return None


def input_problem():
    """A sentence telling the user how to fix remote input, or '' when it works."""
    if input_backend():
        return ""
    ok, msg = uinput_status()
    return msg if not ok else ""


def _backend():
    name = input_backend()
    if name is None:
        raise ApiError(501, input_problem() or "Remote input is not available on this computer")
    return {"uinput": _uinput, "ydotool": YdoTool(), "xdotool": XdoTool()}[name]


def _int(v, lo=-4000, hi=4000):
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError):
        raise ApiError(400, "Bad number")


def do_input(body: dict):
    be = _backend()
    kind = body.get("kind")
    try:
        if kind == "move":
            be.move(_int(body.get("dx", 0)), _int(body.get("dy", 0)))
        elif kind == "click":
            be.click(str(body.get("button", "left")) if body.get("button") in ("left", "right", "middle") else "left",
                     _int(body.get("count", 1), 1, 3))
        elif kind in ("down", "up"):
            be.button(str(body.get("button", "left")) if body.get("button") in ("left", "right", "middle") else "left",
                      kind == "down")
        elif kind == "scroll":
            be.scroll(_int(body.get("dy", 0), -50, 50), _int(body.get("dx", 0), -50, 50))
        elif kind == "key":
            be.key(str(body.get("key", "")))
        elif kind == "text":
            text = str(body.get("text", ""))[:2000]
            if be.can_type(text):
                be.text(text)
            else:
                # other languages: put the text on the clipboard and paste it (works in any layout)
                if not set_clipboard(text):
                    raise ApiError(500, "Could not use the clipboard to type this text "
                                        "(install wl-clipboard or xclip)")
                _clip_state["last"] = text
                time.sleep(0.05)
                be.paste()
        else:
            raise ApiError(400, "Unknown input kind")
    except PermissionError:
        raise ApiError(500, "No permission for /dev/uinput. Run once:  adblink setup-input")
    except OSError as e:
        raise ApiError(500, f"Input failed: {e}")
    return {"ok": True, "backend": be.name}


# ----------------------------------------------------------------------------- one-time setup

UDEV_RULE = 'KERNEL=="uinput", SUBSYSTEM=="misc", OPTIONS+="static_node=uinput", TAG+="uaccess", GROUP="input", MODE="0660"\n'

SETUP_SCRIPT = r"""#!/bin/sh
# Lets your user create a virtual mouse/keyboard (used by the phone touchpad).
set -e
modprobe uinput 2>/dev/null || true
echo uinput > /etc/modules-load.d/adblink-uinput.conf
cat > /etc/udev/rules.d/70-adblink-uinput.rules <<'RULE'
%s
RULE
udevadm control --reload-rules 2>/dev/null || true
udevadm trigger --name-match=uinput 2>/dev/null || udevadm trigger 2>/dev/null || true
# apply right now, without logging out
if [ -n "$ADBLINK_USER" ] && command -v setfacl >/dev/null 2>&1; then
  setfacl -m "u:$ADBLINK_USER:rw" /dev/uinput 2>/dev/null || true
fi
""" % UDEV_RULE.strip()


def setup_input_permissions():
    """Run the one-time uinput permission setup (asks for the password). Returns (ok, message)."""
    import tempfile
    import getpass
    ok, _ = uinput_status()
    if ok:
        return True, "Remote input is already ready."
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(SETUP_SCRIPT)
        path = f.name
    try:
        env = dict(os.environ, ADBLINK_USER=getpass.getuser())
        if os.geteuid() == 0:
            argv = ["sh", path]
        elif which("pkexec"):
            argv = ["pkexec", "env", f"ADBLINK_USER={getpass.getuser()}", "sh", path]
        elif which("sudo"):
            argv = ["sudo", "env", f"ADBLINK_USER={getpass.getuser()}", "sh", path]
        else:
            return False, "Run this as root:  sh " + path
        import subprocess
        rc = subprocess.call(argv, env=env)
        for _ in range(10):
            if uinput_status()[0]:
                return True, "Remote input is ready."
            time.sleep(0.3)
        if rc == 0:
            return False, "Done, but this session still has no access. Log out and in once, then try again."
        return False, "The setup was cancelled or failed."
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
