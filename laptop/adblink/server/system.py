"""System info and running shell commands."""
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from . import clipboard
from .clipboard import clip_tools
from .common import FLAGS, IS_LINUX, IS_MAC, IS_WIN, VERSION, run_env, which
from .inputdev import input_backend, input_problem


def run_shell(cmd, cwd=None, timeout=30, keep=True, track_cwd=False):
    """Run a shell command. keep=True: a command still running after `timeout` is left running
    (good for opening programs); keep=False: it is stopped (good for a terminal)."""
    marker = "__ADBLINK_CWD__"
    script = cmd
    if track_cwd and not IS_WIN:
        script = cmd + f"\n__rc=$?\nprintf '\\n{marker}%s' \"$PWD\"\nexit $__rc"
    if cwd and not os.path.isdir(cwd):
        cwd = None
    out = tempfile.NamedTemporaryFile(prefix="adblink-out-", delete=False)
    try:
        if IS_WIN:
            proc = subprocess.Popen(script, shell=True, stdout=out, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, cwd=cwd, env=run_env())
        else:
            exe = which("bash") or "/bin/sh"
            proc = subprocess.Popen([exe, "-c", script], stdout=out, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, cwd=cwd, env=run_env(),
                                    start_new_session=True)
    except OSError as e:
        out.close()
        os.unlink(out.name)
        return {"ok": False, "error": str(e)}
    out.close()
    timed_out = False
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        code = None
        if not keep:
            try:
                if IS_WIN:
                    proc.kill()
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                code = proc.wait(5)
            except subprocess.TimeoutExpired:
                pass

    def read_out():
        try:
            with open(out.name, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 30000))
                return f.read().decode("utf-8", "replace")
        except OSError:
            return ""

    text = read_out()
    if timed_out and keep:
        def reaper():
            proc.wait()
            try:
                os.unlink(out.name)
            except OSError:
                pass
        threading.Thread(target=reaper, daemon=True).start()
    else:
        try:
            os.unlink(out.name)
        except OSError:
            pass
    new_cwd = None
    if marker in text:
        text, _, new_cwd = text.rpartition(marker)
        new_cwd = new_cwd.strip() or None
        if text.endswith("\n"):
            text = text[:-1]
    res = {"output": text, "cwd": new_cwd}
    if timed_out and keep:
        res.update(ok=True, code=None, running=True)
    elif timed_out:
        res.update(ok=False, code=code, timed_out=True)
    else:
        res.update(ok=code == 0, code=code)
    return res


def os_pretty():
    if IS_LINUX:
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
        return "Linux"
    if IS_MAC:
        import platform
        return "macOS " + platform.mac_ver()[0]
    import platform
    return platform.platform()


def battery_info():
    if IS_LINUX:
        for p in sorted(Path("/sys/class/power_supply").glob("BAT*")):
            try:
                return {"percent": int((p / "capacity").read_text()), "state": (p / "status").read_text().strip()}
            except (OSError, ValueError):
                continue
    return None


def memory_info():
    if IS_LINUX:
        try:
            m = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                k, _, v = line.partition(":")
                m[k] = int(v.split()[0]) * 1024
            return m["MemTotal"], m["MemTotal"] - m.get("MemAvailable", m.get("MemFree", 0))
        except (OSError, ValueError, KeyError):
            pass
    return 0, 0


def uptime_seconds():
    try:
        return int(float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        return 0


_cap_cache = {"t": 0.0, "v": None}


def capabilities():
    now = time.time()
    if _cap_cache["v"] is None or now - _cap_cache["t"] > 5:
        _cap_cache["v"] = {"input": input_backend(), "inputHint": input_problem(), "shell": FLAGS.shell,
                           "clipboard": bool(clip_tools()[0]) or clipboard.PROVIDER is not None}
        _cap_cache["t"] = now
    return _cap_cache["v"]


def home_posix():
    return Path.home().as_posix()


def info_json():
    mt, mu = memory_info()
    try:
        du = shutil.disk_usage(Path.home())
        dt, dused = du.total, du.used
    except OSError:
        dt = dused = 0
    return {"name": socket.gethostname(), "os": os_pretty(), "uptime": uptime_seconds(),
            "battery": battery_info(), "mem_total": mt, "mem_used": mu, "disk_total": dt,
            "disk_used": dused, "capabilities": capabilities(), "home": home_posix(),
            "version": VERSION}
