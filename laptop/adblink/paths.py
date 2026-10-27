"""Where ADB Link keeps its files."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ADB Link"
APP_ID = "org.adblink.AdbLink"  # also the name of the .desktop file (needed for notification buttons)
VERSION = "3.1"
GITHUB_REPO = os.environ.get("ADBLINK_REPO", "alienshtain/adb-link")  # <- change to your GitHub user/repo


def config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "adblink"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "adblink"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "adblink"
    base.mkdir(parents=True, exist_ok=True)
    return base


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "adblink"
    base.mkdir(parents=True, exist_ok=True)
    return base


def data_dir() -> Path:
    """Icons and other files that ship inside the package."""
    return Path(__file__).resolve().parent / "data"


def icon_path(name: str = "adblink.svg") -> Path:
    return data_dir() / name
