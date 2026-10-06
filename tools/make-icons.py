#!/usr/bin/env python3
"""Regenerate assets/icons/<px>/ from assets/icons.svg (rendered via Chromium), tinted with the palette and with aliases added."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from palette import rgb
from PIL import Image, ImageChops

# ----- CONSTANTS & ALIASES -------------------------------------------------- #

ROOT = Path(__file__).resolve().parent.parent
SIZES = {32: 96, 48: 144, 64: 192}  # icon px: render dpi (SVG is based on 32 units)
ALIASES = {
    "arch": "archlinux",
    "linux": "gnu-linux",
    "unknown": "gnu-linux",
    "lfs": "gnu-linux",
    "Manjaro.i686": "manjaro",
    "Manjaro.x86_64": "manjaro",
    "manjarolinux": "manjaro",
    "pop": "pop-os",
    "openSUSE": "opensuse",
    "memtest": "driver",
}
ids = [i for i in (ROOT / "assets" / "icons.txt").read_text().split() if i]


# ----- ICON RENDERING & SCALING --------------------------------------------- #

for px, dpi in SIZES.items():
    out = ROOT / "assets" / "icons" / str(px)
    shutil.rmtree(out, ignore_errors=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                "node",
                ROOT / "tools" / "render.mjs",
                ROOT / "assets" / "icons.svg",
                str(dpi),
                tmp,
                *ids,
            ],
            check=True,
        )
        out.mkdir(parents=True)
        for f in Path(tmp).glob("*.png"):
            img = Image.open(f).convert("RGBA")
            img = img.resize((px, px), Image.Resampling.LANCZOS) if img.size != (px, px) else img
            alpha = img.getchannel("A")
            tint = ImageChops.multiply(img.convert("RGB"), Image.new("RGB", img.size, rgb("fg")))
            tint.putalpha(alpha)
            tint.save(out / f.name, optimize=True)
    for alias, src in ALIASES.items():
        shutil.copy(out / f"{src}.png", out / f"{alias}.png")
    logo = Image.open(ROOT / "assets" / "logos" / "cachyos.png").resize((px, px), Image.Resampling.LANCZOS)
    tinted = ImageChops.multiply(logo.convert("RGB"), Image.new("RGB", logo.size, rgb("fg")))
    tinted.putalpha(logo.getchannel("A"))
    tinted.save(out / "cachyos.png", optimize=True)


# ----- LOGO RENDERING & COMPOSITION ----------------------------------------- #

# Large logos for the photo panel: same SVG at 512 px, cropped and centered on a square.
LOGOS = {"nixos": "nixos", "linux": "gnu-linux", "arch": "archlinux", "windows": "windows"}
with tempfile.TemporaryDirectory() as tmp:
    subprocess.run(
        [
            "node",
            ROOT / "tools" / "render.mjs",
            ROOT / "assets" / "icons.svg",
            "1536",
            tmp,
            *set(LOGOS.values()),
        ],
        check=True,
    )
    for name, src in LOGOS.items():
        img = Image.open(Path(tmp) / f"{src}.png").convert("RGBA")
        img = img.crop(img.getchannel("A").getbbox())
        side = max(img.size)
        square = Image.new("RGBA", (side, side), (255, 255, 255, 0))
        square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
        square.resize((512, 512), Image.Resampling.LANCZOS).save(
            ROOT / "assets" / "logos" / f"{name}.png", optimize=True
        )
