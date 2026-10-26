"""Menu entry, icons and autostart for the desktop app (Linux)."""
from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

from .paths import APP_ID, APP_NAME, data_dir


def exec_command(extra=""):
    """The command a launcher should run."""
    exe = shutil.which("adblink")
    local = Path.home() / ".local" / "bin" / "adblink"
    if exe or local.exists():
        base = shlex.quote(exe or str(local))
    else:  # running straight from a checkout
        root = Path(__file__).resolve().parent.parent
        base = f"env PYTHONPATH={shlex.quote(str(root))} {shlex.quote(sys.executable)} -m adblink"
    return f"{base} {extra}".strip()


def _apps_dir():
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "applications"


def _icons_dir():
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "icons" / "hicolor"


def autostart_file():
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "autostart" / f"{APP_ID}.desktop"


DESKTOP = """[Desktop Entry]
Type=Application
Name={name}
GenericName=Phone and computer link
Comment=Control your Android phone from the computer and the computer from your phone
Exec={exec}
Icon={icon}
Terminal=false
Categories=Utility;Development;
Keywords=adb;android;phone;scrcpy;remote;
StartupNotify=true
StartupWMClass={app_id}
"""

AUTOSTART = """[Desktop Entry]
Type=Application
Name={name}
Comment=Watches your phone (calls, notifications) and serves the phone app
Exec={exec}
Icon={icon}
Terminal=false
X-GNOME-Autostart-enabled=true
NoDisplay=true
"""


def install_icons():
    src = data_dir() / "icons" / "hicolor"
    if not src.is_dir():
        return 0
    n = 0
    for f in src.rglob(f"{APP_ID}.*"):
        dest = _icons_dir() / f.relative_to(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        n += 1
    return n


def install_desktop():
    apps = _apps_dir()
    apps.mkdir(parents=True, exist_ok=True)
    install_icons()
    for old in ("adb-panel.desktop", "org.local.AdbPanel.desktop", "adblink-panel.desktop"):
        (apps / old).unlink(missing_ok=True)
    f = apps / f"{APP_ID}.desktop"
    f.write_text(DESKTOP.format(name=APP_NAME, exec=exec_command(), icon=APP_ID, app_id=APP_ID))
    for tool, args in (("update-desktop-database", [str(apps)]),
                       ("gtk-update-icon-cache", ["-f", "-t", str(_icons_dir())])):
        if shutil.which(tool):
            os.system(" ".join([tool, *map(shlex.quote, args)]) + " >/dev/null 2>&1")
    return f


def uninstall_desktop():
    for f in (_apps_dir() / f"{APP_ID}.desktop", autostart_file()):
        f.unlink(missing_ok=True)
    src = data_dir() / "icons" / "hicolor"
    for f in src.rglob(f"{APP_ID}.*") if src.is_dir() else []:
        (_icons_dir() / f.relative_to(src)).unlink(missing_ok=True)


def autostart_enabled():
    return autostart_file().exists()


def set_autostart(on):
    f = autostart_file()
    if on:
        f.parent.mkdir(parents=True, exist_ok=True)
        install_icons()
        f.write_text(AUTOSTART.format(name=APP_NAME, exec=exec_command("--background"), icon=APP_ID))
    else:
        f.unlink(missing_ok=True)
        (f.parent / "org.local.AdbPanel.desktop").unlink(missing_ok=True)
