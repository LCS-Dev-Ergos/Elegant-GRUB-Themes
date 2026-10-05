"""Tokyo Night palette (Night variant). Single source of truth for theme colors."""

# ----- TOKYO NIGHT COLOR DEFINITIONS ---------------------------------------- #

PALETTE = {
    "bg": "#1a1b26",  # Card and menu background
    "bg_dark": "#16161e",  # Screen background and shadows
    "bg_hl": "#292e42",  # Borders and raised surfaces
    "comment": "#565f89",  # Secondary text
    "fg_dark": "#a9b1d6",  # Menu items
    "fg": "#c0caf5",  # Selected item, icons
    "blue": "#7aa2f7",  # Accent
    "blue0": "#3d59a1",  # Selection fill
}


# ----- COLOR CONVERSION HELPERS --------------------------------------------- #


def rgb(name):
    h = PALETTE[name].lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
