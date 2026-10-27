"""Shared constants, logging and small process helpers."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import types
from pathlib import Path


from ..paths import VERSION  # noqa: E402
APP_TAG = "ADB Link (phone)"  # app name used for notifications we show; the D-Bus watcher skips it
IS_LINUX = sys.platform.startswith("linux")
IS_MAC = sys.platform == "darwin"
IS_WIN = os.name == "nt"

FLAGS = argparse.Namespace(verbose=False, shell=True, clipboard=True, notifications=True)


def log(*a):
    if FLAGS.verbose:
        print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


class ApiError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status = status
        self.msg = msg


# ----------------------------------------------------------------------------- state

def state_dir() -> Path:
    if IS_WIN:
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "adblink"
    elif IS_MAC:
        base = Path.home() / "Library" / "Application Support" / "adblink"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "adblink"
    base.mkdir(parents=True, exist_ok=True)
    return base


# ----------------------------------------------------------------------------- system helpers

def which(name):
    return shutil.which(name)


def run_env():
    env = os.environ.copy()
    if IS_LINUX:
        run = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        env.setdefault("XDG_RUNTIME_DIR", run)
        if os.path.exists(f"{run}/bus"):
            env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={run}/bus")
        if not env.get("WAYLAND_DISPLAY") and os.path.exists(f"{run}/wayland-0"):
            env["WAYLAND_DISPLAY"] = "wayland-0"
        if not env.get("DISPLAY") and os.path.exists("/tmp/.X11-unix/X0"):
            env["DISPLAY"] = ":0"
    return env


def is_wayland():
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(
        run_env().get("WAYLAND_DISPLAY"))


def run_quiet(argv, timeout=5, input_bytes=None):
    """Run a program, return (returncode, stdout bytes, stderr text). Never raises."""
    try:
        p = subprocess.run(argv, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, env=run_env())
        return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace").strip()
    except FileNotFoundError:
        return 127, b"", f"{argv[0]} is not installed"
    except subprocess.TimeoutExpired:
        return 124, b"", f"{argv[0]} timed out"
    except OSError as e:
        return 126, b"", str(e)


ctx = types.SimpleNamespace(state=None, pairing=None, last_seen=0.0, last_phone='', last_ip='')  # filled in by startup.start()
