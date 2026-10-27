"""App icons, package parsing, APK install / download."""
from __future__ import annotations

import io
import json
import os
import posixpath
import queue
import re
import shlex
import threading
import zipfile
from pathlib import Path
from gi.repository import GLib, Gdk, Gtk, Pango
from .adbutil import adb, first_line
from .config import ICON_CACHE
from .ui import clear_children


# ---------------------------------------------------------------- apps page

class RemoteFile(io.RawIOBase):
    """Read-only random access to a file on the phone (fetches only the bytes needed)."""

    BLOCK = 4096
    WINDOW = 64  # blocks per round trip (256 KB)

    def __init__(self, path, size):
        super().__init__()
        self.path, self.size, self.pos = path, size, 0
        self.win_start, self.win_data = 0, b""

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = max(0, (0, self.pos, self.size)[whence] + offset)
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = max(0, min(n, self.size - self.pos))
        if n == 0:
            return b""
        end = self.pos + n
        if not (self.win_start <= self.pos and end <= self.win_start + len(self.win_data)):
            self._fetch(self.pos, n)
        chunk = self.win_data[self.pos - self.win_start:end - self.win_start]
        self.pos += len(chunk)
        return chunk

    def _fetch(self, offset, n):
        first = offset // self.BLOCK
        count = max(self.WINDOW, -(-(offset + n) // self.BLOCK) - first + 1)
        cmd = f"dd if={shlex.quote(self.path)} bs={self.BLOCK} skip={first} count={count} 2>/dev/null"
        rc, data, err = adb("exec-out", cmd, binary=True, timeout=60)
        if rc != 0:
            raise OSError(err or "adb read failed")
        self.win_start, self.win_data = first * self.BLOCK, data


DENSITY = {"xxxhdpi": 6, "xxhdpi": 5, "xhdpi": 4, "hdpi": 3, "nodpi": 3, "mdpi": 2, "ldpi": 1}
NOT_ICON = ("foreground", "background", "monochrome", "adaptive")


def pick_icon(names):
    """Best launcher-icon image inside an APK (png/webp), or None."""
    best, best_score = None, -1
    for name in names:
        low = name.lower()
        if not low.startswith("res/") or not low.endswith((".png", ".webp")):
            continue
        folder, _, file = low[4:].rpartition("/")
        base = file.rsplit(".", 1)[0]
        if any(bad in base for bad in NOT_ICON):
            continue
        if not (base.startswith("ic_launcher")
                or base in ("icon", "app_icon", "logo", "launcher_icon", "ic_app")):
            continue
        score = max((v for k, v in DENSITY.items() if k in folder), default=2) * 10
        score += (5 if base == "ic_launcher" else 0) - (3 if "round" in base else 0)
        score += 1 if "mipmap" in folder else 0
        if score > best_score:
            best, best_score = name, score
    return best


def fetch_icon(pkg, apk_path):
    """Extract an app's icon from its APK on the phone. Returns a file path or None."""
    ICON_CACHE.mkdir(parents=True, exist_ok=True)
    png, none = ICON_CACHE / f"{pkg}.png", ICON_CACHE / f"{pkg}.none"
    if png.exists():
        return str(png)
    if none.exists():
        return None
    rc, out, _err = adb("shell", f"stat -c %s {shlex.quote(apk_path)}", timeout=20)
    if rc != 0 or not out.strip().isdigit():
        return None
    try:
        with zipfile.ZipFile(RemoteFile(apk_path, int(out.strip()))) as zf:
            name = pick_icon(zf.namelist())
            data = zf.read(name) if name and zf.getinfo(name).file_size < 300_000 else None
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError, KeyError):
        return None  # network trouble or odd APK: do not cache, try again next time
    if data:
        png.write_bytes(data)
        return str(png)
    none.touch()
    return None


class IconLoader:
    """Background workers that fetch app icons; results arrive on the GTK thread."""

    def __init__(self, workers=4):
        self.q, self.generation = queue.Queue(), 0
        for _ in range(workers):
            threading.Thread(target=self._work, daemon=True).start()

    def clear(self):
        self.generation += 1
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass

    def submit(self, pkg, apk, callback):
        self.q.put((self.generation, pkg, apk, callback))

    def _work(self):
        while True:
            gen, pkg, apk, callback = self.q.get()
            if gen != self.generation:
                continue
            try:
                path = fetch_icon(pkg, apk)
            except Exception:  # noqa: BLE001 - never kill a worker
                path = None
            GLib.idle_add(callback, gen, path)


GENERIC_LAST = {"android", "app", "apps", "mobile", "client", "service", "services", "main"}


def pretty_name(pkg):
    parts = pkg.split(".")
    name = parts[-2] if parts[-1].lower() in GENERIC_LAST and len(parts) > 1 else parts[-1]
    return name.replace("_", " ").replace("-", " ").capitalize()


def parse_packages(text):
    """-> {package: (apk_path, status, is_user)} from the combined listing."""
    sections, cur = {}, None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("@@"):
            cur = line[2:]
            sections[cur] = []
        elif cur and line.startswith("package:"):
            sections[cur].append(line[8:])
    installed, disabled = set(sections.get("INST", [])), set(sections.get("DIS", []))
    user = set(sections.get("USER", []))
    result = {}
    for item in sections.get("ALL", []):
        path, _, pkg = item.rpartition("=")
        if not pkg:
            continue
        status = "removed" if pkg not in installed else "disabled" if pkg in disabled else "enabled"
        result[pkg] = (path, status, pkg in user)
    return result


def avatar(name, px=40):
    lbl = Gtk.Label(label=(name[:1] or "?").upper(), width_request=px, height_request=px,
                    css_classes=["avatar", f"av{sum(map(ord, name)) % 8}"])
    return lbl


BUNDLE_SUFFIXES = (".apks", ".xapk", ".apkm", ".zip")
OBB_ROOT = "/sdcard/Android/obb"


def is_split_name(name):
    low = name.lower()
    return low == "base.apk" or low.startswith(("split_", "config."))


def find_obb_root(folder):
    for sub in ("Android/obb", "obb"):
        cand = Path(folder) / sub
        if cand.is_dir():
            return cand
    return None


def units_from_dir(folder, as_one):
    """Install units found in a folder. A unit is (list of apk paths, obb root or None).

    A folder holding one app (single apk, or base.apk + split_*.apk, or a bundle
    extracted from a zip) is one unit; a folder of unrelated apks gives one unit each.
    """
    folder = Path(folder)
    obb = find_obb_root(folder)
    apks = [p for p in folder.rglob("*")
            if p.is_file() and p.suffix.lower() == ".apk"
            and not (obb and obb in p.parents)]
    splits = [p for p in apks if "splits" in p.parent.parts]
    if splits:  # bundletool .apks: use the splits, skip universal/standalone variants
        apks = splits
    else:
        apks = [p for p in apks if not {"standalones", "instant"} & set(p.parent.parts)]
    apks.sort()
    if not apks:
        return []
    if as_one or len(apks) == 1 or any(is_split_name(p.name) for p in apks):
        return [([str(p) for p in apks], obb)]
    return [([str(p)], None) for p in apks]


def build_units(paths, tmp):
    """Turn what the user picked (apk files, folders, bundles) into install units."""
    units, loose = [], {}
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            units += units_from_dir(p, False)
        elif p.suffix.lower() in BUNDLE_SUFFIXES:
            dest = Path(tmp) / f"bundle{len(units)}_{p.stem}"
            with zipfile.ZipFile(p) as zf:
                zf.extractall(dest)
            units += units_from_dir(dest, True)
        elif p.suffix.lower() == ".apk":
            loose.setdefault(str(p.parent), []).append(str(p))
    for files in loose.values():
        if any(is_split_name(os.path.basename(f)) for f in files):
            units.append((sorted(files), None))
        else:
            units += [([f], None) for f in sorted(files)]
    return units


def install_units(units, progress, log):
    """Install every unit on the phone. Returns a list of (name, ok, message)."""
    results = []
    for i, (apks, obb) in enumerate(units, 1):
        name = os.path.basename(apks[0]) if len(apks) == 1 else \
            f"{os.path.basename(os.path.dirname(apks[0])) or 'app'} ({len(apks)} files)"
        progress(f"Installing {i}/{len(units)}: {name}")
        argv = ["install", "-r", apks[0]] if len(apks) == 1 else ["install-multiple", "-r", *apks]
        log("$ adb " + " ".join(shlex.quote(a) for a in argv) + "\n")
        rc, out, err = adb(*argv, timeout=3600)
        text = (out + err).strip()
        log(text + "\n")
        ok = rc == 0 and "success" in text.lower()
        if ok and obb:
            adb("shell", "mkdir -p " + OBB_ROOT)
            for sub in sorted(p for p in obb.iterdir() if p.is_dir()):
                progress(f"Copying game data for {name}")
                log(f"$ adb push {sub} {OBB_ROOT}/\n")
                rc2, out2, err2 = adb("push", str(sub), OBB_ROOT + "/", timeout=3600)
                log((out2 + err2).strip() + "\n")
                if rc2 != 0:
                    ok, text = False, "App installed, but copying its OBB data failed: " + first_line(out2 + err2)
        results.append((name, ok, "" if ok else first_line(text)))
    return results


def download_app(pkg, dest, progress, log):
    """Pull an installed app (base apk, split apks and OBB data) into dest/<pkg>/.

    Also writes dest/<pkg>.xapk when the app has more than one file, so the whole
    thing can be installed again later in one go. Returns (ok, message).
    """
    rc, out, err = adb("shell", "pm path " + shlex.quote(pkg), timeout=30)
    paths = [l.strip()[8:] for l in out.splitlines() if l.strip().startswith("package:")]
    if rc != 0 or not paths:
        return False, first_line(err or out, "Could not find the app's files on the phone")
    folder = Path(dest) / pkg
    n = 1
    while folder.exists():
        n += 1
        folder = Path(dest) / f"{pkg}-{n}"
    folder.mkdir(parents=True)

    files = []
    for i, remote in enumerate(paths, 1):
        progress(f"Downloading {i}/{len(paths)}: {posixpath.basename(remote)}")
        local = folder / (f"{pkg}.apk" if len(paths) == 1 else posixpath.basename(remote))
        log(f"$ adb pull {remote} {local}\n")
        rc, out, err = adb("pull", remote, str(local), timeout=3600)
        log((out + err).strip() + "\n")
        if rc != 0:
            return False, first_line(err or out)
        files.append(local)

    obb_dir = None
    rc, out, _err = adb("shell", f"ls {OBB_ROOT}/{shlex.quote(pkg)}", timeout=20)
    if rc == 0 and out.strip():
        progress("Downloading game data (OBB)")
        (folder / "obb").mkdir()
        log(f"$ adb pull {OBB_ROOT}/{pkg} {folder / 'obb'}/\n")
        rc, out, err = adb("pull", f"{OBB_ROOT}/{pkg}", str(folder / "obb") + "/", timeout=3600)
        log((out + err).strip() + "\n")
        if rc == 0:
            obb_dir = folder / "obb" / pkg

    version = ""
    rc, out, _err = adb("shell", f"dumpsys package {shlex.quote(pkg)} | grep -m1 versionName", timeout=30)
    m = re.search(r"versionName=(\S+)", out)
    if m:
        version = m.group(1)

    bundle = None
    if len(files) > 1 or obb_dir:
        progress("Packing everything into one .xapk file")
        bundle = Path(dest) / f"{pkg}{'-' + version if version else ''}.xapk"
        manifest = {"xapk_version": 2, "package_name": pkg, "version_name": version,
                    "split_apks": [{"file": f.name, "id": "base" if f.name == "base.apk"
                                    else f.stem} for f in files]}
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            for f in files:
                zf.write(f, f.name)
            if obb_dir:
                for f in obb_dir.rglob("*"):
                    if f.is_file():
                        zf.write(f, f"Android/obb/{pkg}/{f.relative_to(obb_dir)}")
    parts = [f"{len(files)} apk file(s)"] + (["OBB data"] if obb_dir else [])
    msg = f"Saved {' + '.join(parts)} to {folder}"
    if bundle:
        msg += f" and {bundle.name}"
    return True, msg


class AppRow(Gtk.ListBoxRow):
    def __init__(self, page, pkg, apk, status, is_user):
        super().__init__(activatable=False, selectable=False)
        self.page, self.pkg, self.apk, self.status, self.is_user = page, pkg, apk, status, is_user
        self.name = pretty_name(pkg)
        self.add_css_class("app-row")
        self.set_tooltip_text(f"{self.name}\n{pkg}" + (f"\n{apk}" if apk else ""))
        box = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=10, margin_end=10)
        self.icon_box = Gtk.Box(width_request=40, height_request=40, valign=Gtk.Align.CENTER)
        self.icon_box.append(avatar(self.name))
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        text.append(Gtk.Label(label=self.name, xalign=0, css_classes=["heading"]))
        text.append(Gtk.Label(label=pkg, xalign=0, ellipsize=Pango.EllipsizeMode.END,
                              css_classes=["monospace", "caption", "dim-label"]))
        self.badges = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        self.actions = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        for w in (self.icon_box, text, self.badges, self.actions):
            box.append(w)
        self.set_child(box)
        self.refresh()

    def set_icon(self, path):
        try:
            picture = Gtk.Picture.new_for_paintable(Gdk.Texture.new_from_filename(path))
        except GLib.Error:
            return
        picture.set_size_request(40, 40)
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        clear_children(self.icon_box)
        self.icon_box.append(picture)

    def refresh(self):
        clear_children(self.badges)
        clear_children(self.actions)
        self.badges.append(Gtk.Label(label="User" if self.is_user else "System", css_classes=["badge"]))
        if self.status == "disabled":
            self.badges.append(Gtk.Label(label="Disabled", css_classes=["badge", "badge-warn"]))
        elif self.status == "removed":
            self.badges.append(Gtk.Label(label="Removed", css_classes=["badge", "badge-bad"]))

        def button(text, action, css):
            b = Gtk.Button(label=text, css_classes=css)
            b.connect("clicked", lambda _b: self.page.act(self, action))
            self.actions.append(b)

        if self.status == "removed":
            button("Restore", "restore", ["suggested-action"])
        else:
            dl = Gtk.Button(icon_name="folder-download-symbolic", css_classes=["flat", "circular"],
                            tooltip_text="Download as APK (with split files and game data)")
            dl.connect("clicked", lambda _b: self.page.act(self, "download"))
            self.actions.append(dl)
            if self.status == "disabled":
                button("Enable", "enable", ["suggested-action"])
            else:
                button("Disable", "disable", [])
            button("Uninstall", "uninstall", ["destructive-action"])
