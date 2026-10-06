"""Checks on the compiled theme: if they fail, installation modifies nothing."""

import re
from pathlib import Path

from errors import BuildError
from layout import FONTS, Layout
from PIL import Image

# ----- CONSTANTS & REQUIREMENTS --------------------------------------------- #

REQUIRED = (
    "theme.txt",
    "background.jpg",
    "logo.png",
    "select_w.png",
    "select_c.png",
    "select_e.png",
)
CLASSES = (
    "cachyos",
    "windows",
    "nixos",
    "arch",
    "efi",
    "unknown",
    "gnu-linux",
    "debian",
    "fedora",
    "ubuntu",
)
PROPORTIONAL = re.compile(r"(?:0|[1-9][0-9]*)%?(?:[+-](?:0|[1-9][0-9]*)%?)*")


# ----- VALIDATION ROUTINES -------------------------------------------------- #


def overlaps(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def validate(theme, lay: Layout):
    theme = Path(theme)
    errors = [f"missing {f}" for f in REQUIRED if not (theme / f).is_file()]
    if not errors:
        with Image.open(theme / "background.jpg") as bg:
            if bg.size != lay["size"]:
                errors.append(f"background.jpg is {bg.size}, expected {lay['size']}")
        text = (theme / "theme.txt").read_text()
        for prop, value in re.findall(
            r"^[ \t]*((?:terminal-)?(?:left|top|width|height))[ \t]*[=:][ \t]*(.+)$",
            text,
            re.M,
        ):
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            if not PROPORTIONAL.fullmatch(value):
                errors.append(f"invalid proportional value for {prop}: {value!r}")
        for ref in re.findall(r'(?:file|desktop-image)\s*[=:]\s*"([^"]+)"', text):
            if not (theme / ref).is_file():
                errors.append(f"theme.txt references {ref}, which does not exist")
        for font in re.findall(r'Regular (\d+)"', text):
            if not any(theme.glob(f"*-{font}.pf2")):
                errors.append(f"missing pf2 font for {font}")
        for cls in CLASSES:
            if not (theme / "icons" / f"{cls}.png").is_file():
                errors.append(f"missing icon {cls}")
        h = FONTS[lay["font"]][0]
        for k in "wce":
            with Image.open(theme / f"select_{k}.png") as sel:
                if sel.height != h:
                    errors.append(f"select_{k}.png height {sel.height}, expected {h}")
    w, hh = lay["size"]
    for name in ("photo", "menu"):
        x, y, rw, rh = lay[name]
        if x < 0 or y < 0 or x + rw > w or y + rh > hh or rw <= 0 or rh <= 0:
            errors.append(f"{name} outside screen: {lay[name]}")
    if overlaps(lay["photo"], lay["menu"]):
        errors.append("photo and menu overlap")
    if errors:
        raise BuildError("invalid theme: " + "; ".join(errors))
