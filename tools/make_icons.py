#!/usr/bin/env python3
"""Draws every icon size from assets/icon.svg (needs: pip install cairosvg).  Run from the repository root."""
import pathlib
import shutil

import cairosvg

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP_ID = "org.adblink.AdbLink"
ART = ROOT / "assets" / "icon.svg"
FG = ROOT / "assets" / "icon-foreground.svg"


def png(src, dest, px):
    dest.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(url=str(src), write_to=str(dest), output_width=px, output_height=px)


# desktop (Linux): scalable svg + pngs
hicolor = ROOT / "laptop" / "adblink" / "data" / "icons" / "hicolor"
(hicolor / "scalable" / "apps").mkdir(parents=True, exist_ok=True)
shutil.copy(ART, hicolor / "scalable" / "apps" / f"{APP_ID}.svg")
for px in (48, 64, 128, 256, 512):
    png(ART, hicolor / f"{px}x{px}" / "apps" / f"{APP_ID}.png", px)
png(ART, ROOT / "assets" / "icon-512.png", 512)
png(ART, ROOT / "assets" / "icon-128.png", 128)

# Android launcher icons (copied over the Flutter project by phone/setup.sh)
res = ROOT / "phone" / "android_src" / "res"
for name, px in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
    png(ART, res / f"mipmap-{name}" / "ic_launcher.png", px)
    png(ART, res / f"mipmap-{name}" / "ic_launcher_round.png", px)
for name, px in (("mdpi", 108), ("hdpi", 162), ("xhdpi", 216), ("xxhdpi", 324), ("xxxhdpi", 432)):
    png(FG, res / f"mipmap-{name}" / "ic_launcher_foreground.png", px)
(res / "mipmap-anydpi-v26").mkdir(parents=True, exist_ok=True)
for fname in ("ic_launcher.xml", "ic_launcher_round.xml"):
    (res / "mipmap-anydpi-v26" / fname).write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@color/ic_launcher_background"/>\n'
        '    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>\n'
        '</adaptive-icon>\n')
(res / "values").mkdir(parents=True, exist_ok=True)
(res / "values" / "ic_launcher_colors.xml").write_text(
    '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
    '    <color name="ic_launcher_background">#2F6FE4</color>\n</resources>\n')
print("icons written")
