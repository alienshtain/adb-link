"""Run adb and format its output."""
from __future__ import annotations

import subprocess


def adb(*args, timeout=60, binary=False):
    """Run adb. Returns (returncode, stdout, stderr)."""
    empty = b"" if binary else ""
    try:
        r = subprocess.run(["adb", *args], capture_output=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        return 127, empty, "adb not found - install it with: sudo dnf install android-tools"
    except subprocess.TimeoutExpired:
        return 124, empty, "adb timed out"
    out = r.stdout if binary else r.stdout.decode("utf-8", "replace")
    return r.returncode, out, r.stderr.decode("utf-8", "replace")


def fmt_size(num):
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024


def first_line(text, fallback="failed"):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return fallback
