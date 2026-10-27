"""Getting the ADB Link phone app onto a phone (download the latest release APK, install with adb)."""
from __future__ import annotations

import json
import urllib.request

from . import connect as conn
from .paths import GITHUB_REPO, cache_dir


def _get(url, accept=None, timeout=30):
    headers = {"User-Agent": "adblink"}
    if accept:
        headers["Accept"] = accept
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)


def latest_apk(say=print):
    """Downloads the newest .apk of the GitHub release and returns its path."""
    say(f"Looking for the latest phone app in {GITHUB_REPO} ...")
    with _get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", "application/vnd.github+json", 20) as r:
        rel = json.load(r)
    asset = next(a for a in rel.get("assets", []) if a["name"].endswith(".apk"))
    dest = cache_dir() / asset["name"]
    say(f"Downloading {asset['name']} ...")
    with _get(asset["browser_download_url"], timeout=60) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            f.write(chunk)
    return str(dest)


def install_to_phone(apk="", say=print):
    """Returns (ok, message)."""
    if not apk:
        try:
            apk = latest_apk(say)
        except Exception as e:  # noqa: BLE001 - network, no release yet, no asset...
            return False, (f"Could not download the phone app ({e}). Get the APK from "
                           f"https://github.com/{GITHUB_REPO}/releases and open it on the phone, "
                           f"or run:  adblink install-phone path/to/adblink.apk")
    ready = [d for d in conn.devices() if d.ready]
    if not ready:
        return False, "No phone connected with adb. Plug it in (USB debugging on) or use Connect."
    say("Installing on the phone ...")
    rc, out = conn.adb("-s", ready[0].serial, "install", "-r", apk, timeout=180)
    ok = rc == 0 and "Success" in out
    return ok, ("Installed. Open ADB Link on the phone." if ok else out or "install failed")
