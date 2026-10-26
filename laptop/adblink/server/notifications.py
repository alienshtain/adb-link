"""Desktop notifications to and from the phone."""
from __future__ import annotations

import re
import subprocess
import time
from .common import APP_TAG, FLAGS, IS_LINUX, IS_MAC, run_env, run_quiet, which
from .events import EVENTS


# ----------------------------------------------------------------------------- notifications

def show_notification(app, title, body):
    summary = title or app or "Phone"
    text = body if not title else (f"{app}: {body}" if app else body)
    if IS_LINUX and which("notify-send"):
        run_quiet(["notify-send", "-a", APP_TAG, "-i", "phone", summary, text], timeout=5)
    elif IS_MAC and which("osascript"):
        esc = lambda s: str(s).replace("\\", "\\\\").replace('"', '\\"')
        run_quiet(["osascript", "-e", f'display notification "{esc(text)}" with title "{esc(summary)}"'], timeout=5)


def dbus_notification_watcher():
    """Sends desktop notifications of this computer to the phone (Linux, needs dbus-monitor)."""
    if not (IS_LINUX and which("dbus-monitor")):
        return
    while True:
        try:
            proc = subprocess.Popen(
                ["dbus-monitor", "--session", "interface='org.freedesktop.Notifications',member='Notify'"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="replace", env=run_env())
            block, collecting = [], False
            for line in proc.stdout:
                if "member=Notify" in line and line.lstrip().startswith(("method call", "signal")):
                    block, collecting = [], True
                    continue
                if not collecting:
                    continue
                if line.lstrip().startswith("array ["):
                    collecting = False
                    parse_notify_block(block)
                    continue
                block.append(line.rstrip("\n"))
            proc.wait()
        except Exception:
            pass
        time.sleep(30)


def parse_notify_block(lines):
    segs = []
    for line in lines:
        if re.match(r'\s*(string "|uint32 )', line):
            segs.append(line.strip())
        elif segs:
            segs[-1] += "\n" + line
    strings = []
    for s in segs:
        if s.startswith("string "):
            i, j = s.find('"'), s.rfind('"')
            strings.append(s[i + 1:j] if j > i else "")
    if len(strings) < 4:
        return
    app, summary, body = strings[0], strings[2], strings[3]
    if app == APP_TAG or not (summary or body):
        return
    if FLAGS.notifications:
        EVENTS.add({"type": "notification", "app": app, "title": summary, "body": body})
