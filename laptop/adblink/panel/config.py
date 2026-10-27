"""Paths, preferences and saved settings."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..paths import APP_ID, cache_dir, config_dir

CONFIG_DIR = config_dir()
SETTINGS_FILE = CONFIG_DIR / "panel.json"
ICON_CACHE = cache_dir() / "icons"
_OLD_SETTINGS = Path.home() / ".config" / "adb-panel" / "settings.json"   # the old "ADB Panel" app

__all__ = ["APP_ID", "CONFIG_DIR", "SETTINGS_FILE", "ICON_CACHE", "PREF_DEFAULTS", "load_settings", "save_settings"]


def load_settings():
    if not SETTINGS_FILE.exists() and _OLD_SETTINGS.exists():  # keep the commands / favourites of the old app
        try:
            shutil.copy2(_OLD_SETTINGS, SETTINGS_FILE)
        except OSError:
            pass
    try:
        data = json.loads(SETTINGS_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        tmp.replace(SETTINGS_FILE)
    except OSError:
        pass


PREF_DEFAULTS = {
    "background": True,       # closing the window keeps ADB Link running (watching calls, serving the phone app)
    "tray": True,             # icon in the system tray (click: Open / Quit)
    "save_dir": "",           # empty = Documents/ADB Link
    "language": "auto",       # auto | en | ar
    "autostart": False,       # start hidden when you log in
    "auto_reconnect": True,   # reconnect remembered phones (Wi-Fi) by itself
    "watch_calls": True,
    "call_popup": True,
    "call_notify": True,
    "pause_media": True,
    "resume_media": True,
    "contacts_page": True,
    "phone_panel": True,
    "sim": -1,                # slot used for calls and messages: 0 = SIM 1, 1 = SIM 2, -1 = phone default
    "link_enabled": True,     # serve the ADB Link phone app
    "link_port": 8765,
    "link_shell": True,       # the phone may run commands in a terminal on this computer
    "link_clipboard": True,
    "link_notifications": True,
}
