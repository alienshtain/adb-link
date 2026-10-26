"""File browsing, previews, thumbnails, uploads."""
from __future__ import annotations

import hashlib
import io
import os
import re
import secrets
import time
from pathlib import Path
from .common import ApiError, ctx, run_quiet, which
from .system import home_posix


# ----------------------------------------------------------------------------- files

TEXT_LIMIT = 1_000_000
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def resolve_path(p: str) -> Path:
    if not p:
        return Path.home()
    return Path(os.path.abspath(os.path.expanduser(p)))


def need_exists(p: Path):
    if not p.exists():
        raise ApiError(404, "Not found")


def op_list(path: str, hidden: bool):
    d = resolve_path(path)
    need_exists(d)
    if not d.is_dir():
        raise ApiError(400, "Not a folder")
    items = []
    try:
        with os.scandir(d) as it:
            for e in it:
                if not hidden and e.name.startswith("."):
                    continue
                try:
                    st = e.stat()
                    isdir = e.is_dir()
                except OSError:
                    continue
                items.append({"name": e.name, "dir": isdir, "size": 0 if isdir else st.st_size,
                              "mtime": int(st.st_mtime)})
    except PermissionError:
        raise ApiError(403, "Permission denied")
    items.sort(key=lambda i: (not i["dir"], i["name"].lower()))
    return {"path": d.as_posix(), "home": home_posix(), "items": items}


def dir_stats(d: Path, limit_s=3.0, limit_n=60000):
    files = dirs = size = 0
    t0 = time.time()
    trunc = False
    for root, dnames, fnames in os.walk(d, onerror=lambda e: None, followlinks=False):
        dirs += len(dnames)
        for fn in fnames:
            files += 1
            try:
                size += os.lstat(os.path.join(root, fn)).st_size
            except OSError:
                pass
            if files % 300 == 0 and time.time() - t0 > limit_s:
                trunc = True
                break
        if trunc or files + dirs > limit_n or time.time() - t0 > limit_s:
            trunc = True
            break
    return files, dirs, size, trunc


def op_info(path: str):
    p = resolve_path(path)
    need_exists(p)
    st = p.stat()
    res = {"name": p.name or p.as_posix(), "path": p.as_posix(), "dir": p.is_dir(),
           "mtime": int(st.st_mtime)}
    if p.is_dir():
        try:
            res["items"] = sum(1 for _ in os.scandir(p))
        except PermissionError:
            raise ApiError(403, "Permission denied")
        res["files"], res["dirs"], res["size"], res["truncated"] = dir_stats(p)
    else:
        res["size"] = st.st_size
    return res


def op_tree(path: str, limit=20000):
    d = resolve_path(path)
    need_exists(d)
    if not d.is_dir():
        raise ApiError(400, "Not a folder")
    files, total, trunc = [], 0, False
    for root, _dn, fnames in os.walk(d, onerror=lambda e: None, followlinks=False):
        for fn in fnames:
            fp = Path(root) / fn
            try:
                sz = fp.stat().st_size
            except OSError:
                continue
            files.append({"rel": fp.relative_to(d).as_posix(), "size": sz})
            total += sz
            if len(files) >= limit:
                trunc = True
                break
        if trunc:
            break
    return {"name": d.name or "root", "files": files, "total": total, "truncated": trunc}


def op_text(path: str, maxb: int):
    p = resolve_path(path)
    need_exists(p)
    if p.is_dir():
        raise ApiError(400, "This is a folder")
    maxb = max(1, min(maxb, TEXT_LIMIT))
    try:
        with open(p, "rb") as f:
            data = f.read(maxb + 1)
    except PermissionError:
        raise ApiError(403, "Permission denied")
    truncated = len(data) > maxb
    data = data[:maxb]
    if b"\x00" in data[:8192]:
        raise ApiError(415, "Not a text file")
    text = data.decode("utf-8", "replace")
    if truncated:
        text = text.rstrip("�")
    return {"text": text, "truncated": truncated, "size": p.stat().st_size}


def cache_dir() -> Path:
    d = ctx.state.dir / "cache"
    d.mkdir(exist_ok=True)
    return d


def make_thumb(p: Path, w: int):
    """JPEG bytes of the picture, at most w pixels wide/high. None when it cannot be made."""
    st = p.stat()
    key = hashlib.sha1(f"{p}|{st.st_mtime_ns}|{st.st_size}|{w}".encode()).hexdigest()
    cached = cache_dir() / (key + ".jpg")
    if cached.exists():
        return cached.read_bytes()
    data = None
    try:
        from PIL import Image, ImageOps
        with Image.open(p) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((w, w))
            if im.mode not in ("RGB", "L"):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                rgba = im.convert("RGBA")
                bg.paste(rgba, mask=rgba.split()[-1])
                im = bg
            elif im.mode == "L":
                im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=75)
            data = buf.getvalue()
    except ImportError:
        pass
    except Exception:
        data = None
    if data is None:
        tool = which("magick") or which("convert")
        if tool:
            argv = [tool, f"{p}[0]", "-auto-orient", "-thumbnail", f"{w}x{w}", "-quality", "75", "jpg:-"]
            rc, out, _ = run_quiet(argv, timeout=20)
            if rc == 0 and out:
                data = out
    if data is None:
        return None
    try:
        files = sorted(cache_dir().glob("*.jpg"), key=lambda f: f.stat().st_mtime)
        if len(files) > 1500:
            for f in files[:300]:
                f.unlink(missing_ok=True)
        cached.write_bytes(data)
    except OSError:
        pass
    return data


def downloads_dir() -> Path:
    cfg = Path.home() / ".config" / "user-dirs.dirs"
    try:
        for line in cfg.read_text().splitlines():
            if line.startswith("XDG_DOWNLOAD_DIR="):
                v = line.split("=", 1)[1].strip().strip('"').replace("$HOME", str(Path.home()))
                if v:
                    return Path(v)
    except OSError:
        pass
    return Path.home() / "Downloads"


def safe_part(s: str) -> str:
    s = re.sub(r"[\x00-\x1f]", "", s).strip()
    return "" if s in ("", ".", "..") else s[:200]


def safe_rel(s: str):
    parts = []
    for part in re.split(r"[\\/]+", s or ""):
        if part in ("", ".", ".."):
            continue
        part = safe_part(part)
        if part:
            parts.append(part)
    return parts


def unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    stem, suf = p.stem, p.suffix
    for i in range(1, 10000):
        cand = p.with_name(f"{stem} ({i}){suf}")
        if not cand.exists():
            return cand
    return p.with_name(f"{stem}-{secrets.token_hex(3)}{suf}")
