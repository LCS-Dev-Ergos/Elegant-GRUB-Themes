#!/usr/bin/env python3
"""Simulate the GRUB screen (entries, selector, logo, labels) on the theme compiled in a directory."""

import argparse
from pathlib import Path

from layout import FONTS, SCREENS, SIDES, TYPES, compute
from palette import PALETTE
from PIL import Image, ImageDraw, ImageFont

# ----- CONSTANTS & MOCK DATA ------------------------------------------------ #

ROOT = Path(__file__).resolve().parent.parent
ENTRIES = [
    ("CachyOS", "cachyos"),
    ("Windows Boot Manager", "windows"),
    ("NixOS", "nixos"),
    ("UEFI Firmware Settings", "efi"),
]


# ----- SCREEN SIMULATION ---------------------------------------------------- #


def preview(theme, out, screen, style, side):
    lay = compute(screen, style, side)
    img = Image.open(theme / "background.jpg").convert("RGBA")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(ROOT / "common" / "unifont.otf"), lay["font"])
    item_h, icon, space, pad, spacing = FONTS[lay["font"]]
    mx, my, mw, mh = lay["menu"]
    sel = [Image.open(theme / f"select_{k}.png") for k in "wce"]
    for n, (name, cls) in enumerate(ENTRIES):
        y = my + n * (item_h + spacing)
        if n == 0:
            img.alpha_composite(sel[0], (mx, y))
            img.alpha_composite(
                sel[1].resize((mw - sel[0].width - sel[2].width, item_h)), (mx + sel[0].width, y)
            )
            img.alpha_composite(sel[2], (mx + mw - sel[2].width, y))
        ico = Image.open(theme / "icons" / f"{cls}.png")
        img.alpha_composite(ico, (mx + pad + 8, y + (item_h - icon) // 2))
        d.text(
            (mx + pad + 8 + icon + space, y + item_h // 2),
            name,
            font=font,
            anchor="lm",
            fill=PALETTE["fg" if n == 0 else "fg_dark"],
        )
    logo = Image.open(theme / "logo.png")
    px, py, pw, ph = lay["photo"]
    img.alpha_composite(
        logo, (px + (pw - logo.width) // 2, py + round(0.40 * ph) - logo.height // 2)
    )
    d.text(
        (px + pw // 2, py + ph - round(64 * lay["u"]) + 12),
        "e  edit      c  console",
        font=font,
        anchor="mt",
        fill=PALETTE["fg_dark"],
    )
    d.text(
        (mx + mw // 2, my + mh + round(16 * lay["u"]) + 12),
        "Booting in 5 seconds",
        font=font,
        anchor="mt",
        fill=PALETTE["comment"],
    )
    img.convert("RGB").save(out)


# ----- CLI ENTRY POINT ------------------------------------------------------ #

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("theme", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("-s", "--screen", choices=SCREENS, default="1080p")
    ap.add_argument("-p", "--type", choices=TYPES, default="window")
    ap.add_argument("-i", "--side", choices=SIDES, default="left")
    a = ap.parse_args()
    preview(a.theme, a.out, a.screen, a.type, a.side)
