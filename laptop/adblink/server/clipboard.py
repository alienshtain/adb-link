"""Clipboard access and watcher."""
from __future__ import annotations

import subprocess
import time
from .common import IS_MAC, IS_WIN, is_wayland, run_env, run_quiet, which
from .events import EVENTS


# ----------------------------------------------------------------------------- clipboard

def clip_tools():
    """(read argv list, write argv list) of every clipboard tool found, best first."""
    readers, writers = [], []
    if IS_MAC:
        return [["pbpaste"]], [["pbcopy"]]
    if IS_WIN:
        return ([["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"]],
                [["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"]])
    if which("wl-paste") and which("wl-copy") and is_wayland():
        readers.append(["wl-paste", "--no-newline"])
        writers.append(["wl-copy"])
    if which("xclip"):
        readers.append(["xclip", "-selection", "clipboard", "-o"])
        writers.append(["xclip", "-selection", "clipboard"])
    if which("xsel"):
        readers.append(["xsel", "-b", "-o"])
        writers.append(["xsel", "-b", "-i"])
    return readers, writers


def get_clipboard():
    for argv in clip_tools()[0]:
        rc, out, _ = run_quiet(argv, timeout=3)
        if rc == 0:
            if b"\x00" in out[:4096] or len(out) > 200000:
                return None
            return out.decode("utf-8", "replace")
    return None


def set_clipboard(text: str) -> bool:
    for argv in clip_tools()[1]:
        try:
            p = subprocess.run(argv, input=text.encode("utf-8"), stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=4, env=run_env())
            if p.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


_clip_state = {"last": None}


def clipboard_watcher():
    _clip_state["last"] = get_clipboard()
    while True:
        time.sleep(1.0)
        try:
            cur = get_clipboard()
        except Exception:
            continue
        if cur is not None and cur != _clip_state["last"]:
            _clip_state["last"] = cur
            if cur.strip():
                EVENTS.add({"type": "clipboard", "text": cur})
