"""What can be put on the phone-shaped panel, and how the user's arrangement is stored.

A layout is a list of keys. A key is one of:

* a name from ACTIONS            ("shade", "camera", ...)
* "toggle:<key>"                 flips one of the quick settings (Wi-Fi, Bluetooth, ...)
* "page:<name>"                  jumps to a page of this window
* "cmd:<id>"                     one of the user's own commands from the Commands page
"""
from __future__ import annotations

from .phone_tools import TOGGLES

# key -> (icon, title, short label, kind, argument)
ACTIONS = {
    "shade": ("pan-down-symbolic", "Pull down the notification shade", "Shade", "shell",
              "cmd statusbar expand-notifications"),
    "qs": ("preferences-system-symbolic", "Open quick settings on the phone", "Quick", "shell",
           "cmd statusbar expand-settings"),
    "screenshot": ("applets-screenshooter-symbolic", "Screenshot (saved on this computer)", "Shot", "shot", ""),
    "camera": ("camera-photo-symbolic", "Camera", "Camera", "shell",
               "am start -a android.media.action.STILL_IMAGE_CAMERA"),
    "bright-": ("🔅", "Brightness down", "Dimmer", "bright", "-"),
    "bright+": ("🔆", "Brightness up", "Brighter", "bright", "+"),
    "mute": ("audio-volume-muted-symbolic", "Mute / unmute", "Mute", "shell", "input keyevent 164"),
    "play": ("media-playback-start-symbolic", "Play / pause", "Play", "shell", "input keyevent 85"),
    "prev": ("media-skip-backward-symbolic", "Previous track", "Prev", "shell", "input keyevent 88"),
    "next": ("media-skip-forward-symbolic", "Next track", "Next", "shell", "input keyevent 87"),
    "lock": ("system-lock-screen-symbolic", "Lock the screen", "Lock", "shell", "input keyevent 223"),
    "wake": ("view-reveal-symbolic", "Wake the screen", "Wake", "shell", "input keyevent 224"),
    "dialer": ("call-start-symbolic", "Open the dialer", "Dialer", "shell", "am start -a android.intent.action.DIAL"),
    "settings": ("emblem-system-symbolic", "Phone settings", "Settings", "shell",
                 "am start -a android.settings.SETTINGS"),
    "scrcpy": ("video-display-symbolic", "Mirror the phone screen (scrcpy)", "Mirror", "scrcpy", ""),
    "browser": ("web-browser-symbolic", "Open the browser on the phone", "Browser", "shell",
                "am start -a android.intent.action.VIEW -d https://www.google.com"),
    "home": ("go-home-symbolic", "Home", "Home", "shell", "input keyevent 3"),
    "back": ("go-previous-symbolic", "Back", "Back", "shell", "input keyevent 4"),
    "recents": ("view-app-grid-symbolic", "Recent apps", "Recents", "shell", "input keyevent 187"),
    "volup": ("audio-volume-high-symbolic", "Volume up", "Vol +", "shell", "input keyevent 24"),
    "voldown": ("audio-volume-low-symbolic", "Volume down", "Vol -", "shell", "input keyevent 25"),
    "power": ("system-shutdown-symbolic", "Power button", "Power", "shell", "input keyevent 26"),
    "reboot": ("system-reboot-symbolic", "Restart the phone", "Restart", "confirm-shell", "reboot"),
}

PAGES = [("page:apps", "view-app-grid-symbolic", "Apps"), ("page:files", "folder-symbolic", "Files"),
         ("page:contacts", "avatar-default-symbolic", "Contacts"), ("page:phone", "phone-symbolic", "Phone"),
         ("page:commands", "utilities-terminal-symbolic", "Commands"),
         ("page:link", "network-transmit-receive-symbolic", "Link")]

DEFAULT_LAYOUT = ["shade", "qs", "screenshot", "camera",
                  "bright-", "bright+", "mute", "play",
                  "prev", "next", "lock", "wake",
                  "dialer", "page:contacts", "settings", "scrcpy"]

GROUPS = [
    ("Phone buttons", ["shade", "qs", "screenshot", "camera", "lock", "wake", "home", "back", "recents",
                       "volup", "voldown", "power", "reboot"]),
    ("Media and screen", ["bright-", "bright+", "mute", "play", "prev", "next", "scrcpy"]),
    ("Apps and tools", ["dialer", "settings", "browser"]),
]


def describe(key, win=None):
    """(icon, title, short label) for any key; unknown keys come back with a plain icon."""
    if key in ACTIONS:
        icon, title, short, _k, _a = ACTIONS[key]
        return icon, title, short
    if key.startswith("toggle:"):
        for t in TOGGLES:
            if t["key"] == key[7:]:
                return t["icon"], f"Toggle {t['title']}", t["title"].split()[0]
    if key.startswith("page:"):
        for k, icon, label in PAGES:
            if k == key:
                return icon, f"Open the {label} page", label
    if key.startswith("cmd:") and win is not None:
        for c in win.commands:
            if c["id"] == key[4:]:
                return c.get("icon") or "utilities-terminal-symbolic", c["name"], c["name"]
    return "dialog-question-symbolic", key, key


def exists(key, win=None):
    if key in ACTIONS:
        return True
    if key.startswith("toggle:"):
        return any(t["key"] == key[7:] for t in TOGGLES)
    if key.startswith("page:"):
        return any(k == key for k, _i, _l in PAGES)
    if key.startswith("cmd:") and win is not None:
        return any(c["id"] == key[4:] for c in win.commands)
    return False


def catalog(win):
    """[(group title, [keys])] of everything that can still be added."""
    groups = [(title, list(keys)) for title, keys in GROUPS]
    groups.append(("Quick settings (tap flips them)", [f"toggle:{t['key']}" for t in TOGGLES]))
    groups.append(("Pages of this app", [k for k, _i, _l in PAGES]))
    groups.append(("Your commands", [f"cmd:{c['id']}" for c in win.commands]))
    return groups


def get_layout(settings, win=None):
    layout = settings.get("panel_layout")
    if not isinstance(layout, list):
        return list(DEFAULT_LAYOUT)
    return [k for k in layout if isinstance(k, str) and exists(k, win)]
