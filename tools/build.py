#!/usr/bin/env python3
"""Build a complete GRUB theme at native resolution: background, selectors, icons, logo, and theme.txt."""

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

from errors import BuildError
from layout import FONTS, SCREENS, SIDES, TYPES, compute, theme_txt
from palette import rgb
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps
from validate import validate

# ----- CONSTANTS & GLOBALS -------------------------------------------------- #

ROOT = Path(__file__).resolve().parent.parent
SS = 3  # supersampling for rounded corners
NAME = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]*"
)  # allowed names for photos and logos in backgrounds/ and assets/logos/
MARKER = ".tokyonight-theme"  # marks directories created by this script: only these are replaced or removed


# ----- IMAGE PROCESSING HELPERS --------------------------------------------- #


def rounded_mask(size, radius, corners=(True,) * 4):
    m = Image.new("L", (size[0] * SS, size[1] * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        (0, 0, m.width - 1, m.height - 1), radius * SS, fill=255, corners=corners
    )
    return m.resize(size, Image.LANCZOS)


def grade(img, mode):
    """Color-grade the photo towards the palette: monochrome is mapped to bg_dark, blue0, and fg."""
    if mode == "none":
        return img
    duo = ImageOps.colorize(ImageOps.grayscale(img), rgb("bg_dark"), rgb("fg"), mid=rgb("blue0"))
    return Image.blend(img, duo, 0.35 if mode == "soft" else 1.0)


def photo_panel(photo, rect, radius, side):
    """Crop the photo to the panel and add a dark gradient at the bottom for readability of key hints."""
    w, h = rect[2:]
    panel = ImageOps.fit(photo, (w, h), Image.LANCZOS, centering=(0.5, 0.5)).convert("RGBA")
    ramp = Image.linear_gradient("L").resize((w, h)).point(lambda v: 50 + max(0, v - 130) * 0.8)
    panel.alpha_composite(
        Image.merge("RGBA", (*[Image.new("L", (w, h), c) for c in rgb("bg_dark")], ramp))
    )
    return panel, rounded_mask((w, h), radius) if radius else None


def blurred(photo, size, radius, dim):
    bg = ImageOps.fit(photo, size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(radius))
    return Image.blend(bg, Image.new("RGB", size, rgb("bg_dark")), dim)


def background(lay, style, side, photo):
    size, u = lay["size"], lay["u"]
    img = Image.new("RGB", size, rgb("bg_dark"))
    cx, cy, cw, ch = lay["card"]
    if style in ("window", "blur"):
        img = blurred(photo, size, 40 * u, 0.55 if style == "window" else 0.3)
    if style == "window":
        mask = rounded_mask((cw, ch), lay["card_radius"])
        shadow = Image.new("L", size, 0)
        shadow.paste(mask, (cx, cy + round(14 * u)))
        shadow = shadow.filter(ImageFilter.GaussianBlur(28 * u)).point(lambda v: v * 0.65)
        img.paste(Image.new("RGB", size, (0, 0, 0)), mask=shadow)
        img.paste(Image.new("RGB", (cw, ch), rgb("bg_hl")), (cx, cy), mask)  # border
        inner = rounded_mask((cw - 2, ch - 2), lay["card_radius"] - 1)
        img.paste(Image.new("RGB", (cw - 2, ch - 2), rgb("bg")), (cx + 1, cy + 1), inner)
    if style == "blur":  # the menu side is a dark veil over the blurred background
        mx = size[0] - lay["photo"][2] if side == "left" else 0
        veil = Image.new("RGB", (size[0] - lay["photo"][2], size[1]), rgb("bg_dark"))
        img.paste(Image.blend(img.crop((mx, 0, mx + veil.width, size[1])), veil, 0.55), (mx, 0))
    panel, mask = photo_panel(photo, lay["photo"], lay["photo_radius"], side)
    img.paste(panel.convert("RGB"), lay["photo"][:2], mask)
    return img


def selectors(dest, font):
    """Three-piece pill selector (w, c, e), height equal to the item height."""
    h, r = FONTS[font][0], round(FONTS[font][0] * 0.22)
    pill = rounded_mask((2 * r + 4, h), r).convert("L")
    fill = Image.new("RGBA", pill.size, rgb("blue0") + (255,))
    fill.putalpha(pill)
    fill.crop((0, 0, r, h)).save(dest / "select_w.png")
    fill.crop((r, 0, r + 4, h)).save(dest / "select_c.png")
    fill.crop((pill.width - r, 0, pill.width, h)).save(dest / "select_e.png")


def tinted(src, size, tint=None):
    img = Image.open(src).convert("RGBA").resize((size, size), Image.LANCZOS)
    if tint:
        a = img.getchannel("A")
        img = ImageChops.multiply(img.convert("RGB"), Image.new("RGB", img.size, tint)).convert(
            "RGBA"
        )
        img.putalpha(a)
    return img


# ----- ASSET RESOLUTION & LOADING ------------------------------------------- #


def find_asset(directory, name, suffixes, kind, required=True):
    """Find name strictly inside directory: names with path separators are rejected."""
    if not NAME.fullmatch(name):
        raise BuildError(f"invalid {kind}: {name!r}")
    directory = Path(directory).resolve()
    candidates = [directory / name] if Path(name).suffix.lower() in suffixes else []
    candidates += [directory / f"{name}{suffix}" for suffix in suffixes]
    for path in candidates:
        if path.is_file():
            if not path.resolve().is_relative_to(directory):
                raise BuildError(f"{kind} {name!r} resolves outside {directory}")
            return path
    if required:
        raise BuildError(f"{kind} {name!r} not found in {directory}")
    return None


def load_photo(spec, min_size):
    """Open a photo from backgrounds/ (by name) or from a path; normalize orientation and color mode."""
    path = Path(spec)
    if not path.is_file():
        suffixes = (".jpg", ".jpeg", ".png", ".webp")
        for directory in (ROOT / "backgrounds", ROOT / "backgrounds" / "default"):
            path = find_asset(directory, spec, suffixes, "photo", required=False)
            if path:
                break
        else:
            raise BuildError(f"photo {spec!r} not found in backgrounds/ or backgrounds/default/")
    try:
        img = ImageOps.exif_transpose(Image.open(path))
        img.load()
    except (OSError, ValueError) as e:
        raise BuildError(f"unreadable image ({path}): {e}")
    if img.mode in ("RGBA", "LA", "P"):  # transparency is composited onto the background color
        img = img.convert("RGBA")
        flat = Image.new("RGBA", img.size, rgb("bg_dark") + (255,))
        img = Image.alpha_composite(flat, img)
    img = img.convert("RGB")
    if img.width < min_size[0] or img.height < min_size[1]:
        print(
            f"Warning: {path.name} is {img.width}x{img.height}, below panel size {min_size[0]}x{min_size[1]}: it will be scaled up.",
            file=sys.stderr,
        )
    return img


# ----- THEME BUILD PIPELINE ------------------------------------------------- #


def build(dest, screen, style, side, photo_spec, logo, mode):
    """Build the theme in a staging directory, validate it, and only then replace dest."""
    dest = Path(dest)
    if dest.is_symlink():
        raise BuildError(f"{dest} is a symlink: refusing to replace it")
    if dest.exists() and not (dest / MARKER).is_file():
        raise BuildError(
            f"{dest} exists and was not created by this script: refusing to replace it"
        )
    lay = compute(screen, style, side)
    font = lay["font"]
    photo = grade(load_photo(photo_spec, lay["photo"][2:]), mode)
    logo_path = (
        None if logo == "none" else find_asset(ROOT / "assets" / "logos", logo, (".png",), "logo")
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{dest.name}.tmp-", dir=dest.parent))
    old = dest.parent / f".{dest.name}.old-{stage.name.rsplit('-', 1)[-1]}"
    try:
        background(lay, style, side, photo).save(
            stage / "background.jpg", quality=93, subsampling=0
        )
        selectors(stage, font)
        (stage / "theme.txt").write_text(theme_txt(lay))
        shutil.copytree(ROOT / "assets" / "icons" / str(FONTS[font][1]), stage / "icons")
        if logo_path:
            tinted(logo_path, lay["logo"], rgb("fg")).save(stage / "logo.png")
        else:
            Image.new("RGBA", (1, 1)).save(stage / "logo.png")
        for f in ("terminus-14.pf2", "terminus-18.pf2", f"unifont-{font}.pf2"):
            shutil.copy(ROOT / "common" / f, stage)
        (stage / MARKER).write_text(f"{screen} {style} {side}\n")
        validate(stage, lay)
        if dest.exists():
            if not (dest / MARKER).exists():
                raise BuildError(
                    f"{dest} exists and was not created by this script: refusing to replace it"
                )
            dest.rename(old)
        stage.rename(dest)
        shutil.rmtree(old, ignore_errors=True)
    except BaseException:
        if old.exists() and not dest.exists():
            old.rename(dest)
        shutil.rmtree(stage, ignore_errors=True)
        raise


# ----- CLI ENTRY POINT ------------------------------------------------------ #

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dest", type=Path)
    ap.add_argument("-s", "--screen", choices=SCREENS, default="1080p")
    ap.add_argument("-p", "--type", choices=TYPES, default="window")
    ap.add_argument("-i", "--side", choices=SIDES, default="left")
    ap.add_argument(
        "-f", "--photo", default="mountain", help="name in backgrounds/ or path to an image"
    )
    ap.add_argument("-l", "--logo", default="cachyos", help="name in assets/logos/ or none")
    ap.add_argument("-g", "--grade", choices=("none", "soft", "full"), default="soft")
    a = ap.parse_args()
    try:
        build(a.dest, a.screen, a.type, a.side, a.photo, a.logo, a.grade)
    except BuildError as e:
        sys.exit(f"Error: {e}")
