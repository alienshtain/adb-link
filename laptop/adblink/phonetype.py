"""Type text on the phone, including Arabic and every other language.

``adb shell input text`` only knows ASCII. For anything else the text is put on the phone's clipboard
(by the ADB Link phone app, or by ADB Keyboard when that is installed) and then pasted.
"""
from __future__ import annotations

import base64
import re
import shlex

from . import connect as conn

PHONE_APP = "com.alienshtain.adblink"
ADB_KEYBOARD = "com.android.adbkeyboard"
KEY_PASTE = "279"


def _shell(cmd, timeout=20):
    return conn.adb("shell", cmd, timeout=timeout)


def _installed(package):
    rc, out = _shell(f"pm list packages {package}")
    return rc == 0 and f"package:{package}" in out


def ascii_command(text):
    """`input text` wants spaces as %s and shell characters escaped."""
    encoded = text.replace("%", "%25").replace(" ", "%s")
    return "input text " + shlex.quote(encoded)


def type_text(text):
    """Returns (ok, message)."""
    if not text:
        return False, "Nothing to type."
    lines = text.split("\n")
    for index, line in enumerate(lines):
        ok, msg = _type_line(line)
        if not ok:
            return ok, msg
        if index < len(lines) - 1:
            _shell("input keyevent 66")          # Enter
    return True, "Typed on the phone."


def _type_line(line):
    if not line:
        return True, ""
    if re.fullmatch(r"[\x20-\x7e]+", line):
        rc, out = _shell(ascii_command(line))
        return (rc == 0, out.strip() or "")
    b64 = base64.b64encode(line.encode("utf-8")).decode()
    if _installed(PHONE_APP):
        rc, out = _shell(f"am broadcast -f 32 -n {PHONE_APP}/.TypeReceiver -a org.adblink.TYPE --es b64 {b64}")
        if rc == 0 and "result=1" in out.replace(" ", ""):
            rc, out = _shell(f"input keyevent {KEY_PASTE}")
            return (rc == 0, out.strip() or "")
    if _installed(ADB_KEYBOARD):
        rc, out = _shell(f"ime enable {ADB_KEYBOARD}/.AdbIME; ime set {ADB_KEYBOARD}/.AdbIME; "
                         f"am broadcast -a ADB_INPUT_B64 --es msg {b64}")
        return (rc == 0, out.strip() or "")
    return False, ("Typing Arabic needs the ADB Link app on the phone (run:  adblink install-phone) "
                   "or the ADB Keyboard app.")
