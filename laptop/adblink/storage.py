"""Where ADB Link keeps the files it receives: Documents/ADB Link (changeable in Settings)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .paths import config_dir

SUBDIRS = {
    "phone": "From the phone",      # files the phone app sends to this computer
    "files": "Phone files",         # files downloaded from the phone with the Files page
    "shots": "Screenshots",
    "apps": "Apps",                 # APK files saved from the phone
}


def documents_dir() -> Path:
    cfg = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "user-dirs.dirs"
    try:
        for line in cfg.read_text().splitlines():
            if line.startswith("XDG_DOCUMENTS_DIR="):
                v = line.split("=", 1)[1].strip().strip('"').replace("$HOME", str(Path.home()))
                if v and Path(v) != Path.home():
                    return Path(v)
    except OSError:
        pass
    return Path.home() / "Documents"


def default_root() -> Path:
    return documents_dir() / "ADB Link"


def save_root() -> Path:
    """The folder chosen in Settings, or Documents/ADB Link."""
    try:
        data = json.loads((config_dir() / "panel.json").read_text())
        chosen = str((data.get("prefs") or {}).get("save_dir") or "").strip()
    except (OSError, ValueError, AttributeError):
        chosen = ""
    return Path(os.path.expanduser(chosen)) if chosen else default_root()


def folder(kind: str) -> Path:
    """The (created) sub folder for one kind of file: 'phone', 'files', 'shots' or 'apps'."""
    path = save_root() / SUBDIRS.get(kind, kind)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path.home()
    return path
