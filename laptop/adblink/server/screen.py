"""Screen capture for the phone's screen view."""
from __future__ import annotations

import io
import os
import tempfile
from .common import ApiError, IS_LINUX, IS_MAC, IS_WIN, is_wayland, run_quiet, which


# ----------------------------------------------------------------------------- screen

def screen_tools():
    tools = []
    if IS_MAC:
        tools = [("screencapture", lambda f: ["screencapture", "-x", "-t", "png", f])]
    elif IS_WIN:
        ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
              "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
              "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
              "$g=[System.Drawing.Graphics]::FromImage($bmp);"
              "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
              "$bmp.Save('%s')")
        tools = [("powershell", lambda f: ["powershell", "-NoProfile", "-Command", ps % f])]
    else:
        gs = ("gnome-screenshot", lambda f: ["gnome-screenshot", "-f", f])
        sp = ("spectacle", lambda f: ["spectacle", "-b", "-n", "-o", f])
        if is_wayland():
            cands = [("grim", lambda f: ["grim", f]), gs, sp]
        else:
            cands = [("scrot", lambda f: ["scrot", "-o", f]), ("maim", lambda f: ["maim", f]),
                     ("import", lambda f: ["import", "-window", "root", f]), gs, sp]
        tools = [(n, b) for n, b in cands if which(n) or (n == "powershell")]
    return tools


_screen_pref = {"name": None}


def to_jpeg(png: bytes, w: int, q: int):
    try:
        from PIL import Image
        with Image.open(io.BytesIO(png)) as im:
            im = im.convert("RGB")
            if im.width > w:
                resample = getattr(Image, "Resampling", Image).LANCZOS
                im = im.resize((w, max(1, round(im.height * w / im.width))), resample)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=q)
            return buf.getvalue(), "image/jpeg"
    except ImportError:
        pass
    except Exception:
        return png, "image/png"
    tool = which("magick") or which("convert")
    if tool:
        rc, out, _ = run_quiet([tool, "png:-", "-resize", f"{w}x>", "-quality", str(q), "jpg:-"],
                               timeout=15, input_bytes=png)
        if rc == 0 and out:
            return out, "image/jpeg"
    return png, "image/png"


def capture_screen(w: int, q: int):
    tools = screen_tools()
    if not tools:
        if IS_LINUX:
            hint = ("gnome-screenshot (GNOME / Ubuntu), grim (Sway), spectacle (KDE)" if is_wayland()
                    else "scrot, maim or gnome-screenshot")
            raise ApiError(501, f"No screenshot tool found. Install {hint} on the computer.")
        raise ApiError(501, "Screen view is not supported on this system")
    pref = _screen_pref["name"]
    tools.sort(key=lambda t: t[0] != pref)
    errors = []
    with tempfile.TemporaryDirectory(prefix="adblink-shot-") as tmp:
        for name, build in tools:
            target = os.path.join(tmp, "shot.png")
            if os.path.exists(target):
                os.unlink(target)
            rc, _out, err = run_quiet(build(target), timeout=10)
            if rc == 0 and os.path.exists(target) and os.path.getsize(target) > 0:
                _screen_pref["name"] = name
                with open(target, "rb") as f:
                    return to_jpeg(f.read(), w, q)
            errors.append(f"{name}: {(err.splitlines() or ['failed'])[0][:120]}")
    raise ApiError(500, "Screenshot failed. " + "; ".join(errors))
