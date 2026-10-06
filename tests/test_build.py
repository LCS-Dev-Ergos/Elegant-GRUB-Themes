"""Builder tests: all combinations, edge-case inputs, and protections."""

# ----- IMPORTS & CONFIGURATION ---------------------------------------------- #

import itertools
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build
from errors import BuildError
from layout import SCREENS, SIDES, TYPES, compute, theme_txt
from validate import validate

# ----- TEST SUITE ----------------------------------------------------------- #


class BuildTest(unittest.TestCase):
    def setUp(self):
        """Create a temporary workspace directory and register cleanup."""
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def photo(self, name, size=(1600, 1200), mode="RGB", color=(120, 80, 60)):
        """Generate a dummy test image file with specified dimensions, mode, and color."""
        path = self.tmp / name
        Image.new(mode, size, color if mode == "RGB" else color + (128,)).save(path)
        return str(path)

    def test_every_combination_builds_and_is_native(self):
        """Verify that all 32 resolution, style, and side combinations build native-resolution backgrounds."""
        photo = self.photo("p.jpg")
        for screen, style, side in itertools.product(SCREENS, TYPES, SIDES):
            with self.subTest(screen=screen, style=style, side=side):
                out = self.tmp / f"{screen}-{style}-{side}"
                build.build(out, screen, style, side, photo, "cachyos", "soft")
                with Image.open(out / "background.jpg") as bg:
                    self.assertEqual(bg.size, SCREENS[screen][:2])

    def test_layout_stays_inside_screen_and_apart(self):
        """Verify that layout rectangles (photo and menu) fit within screen bounds without colliding."""
        for screen, style, side in itertools.product(SCREENS, TYPES, SIDES):
            lay = compute(screen, style, side)
            w, h = lay["size"]
            for rect in (lay["photo"], lay["menu"]):
                x, y, rw, rh = rect
                self.assertTrue(
                    0 <= x and 0 <= y and x + rw <= w and y + rh <= h, (screen, style, side, rect)
                )

    def test_theme_txt_percentages_in_range(self):
        """Reject decimal geometry that GRUB cannot load in any supported layout."""
        for screen, style, side in itertools.product(SCREENS, TYPES, SIDES):
            with self.subTest(screen=screen, style=style, side=side):
                text = theme_txt(compute(screen, style, side))
                values = re.findall(r"^  (?:left|top|width|height) = (.+)$", text, re.M)
                self.assertTrue(values)
                for value in values:
                    self.assertRegex(value, r"^\d+%(?:[+-]\d+)?$")
                    self.assertTrue(0 <= int(value.split("%")[0]) <= 100, value)

    def test_decimal_geometry_is_rejected_before_installation(self):
        """Prevent a valid asset bundle with invalid theme geometry from being installed."""
        out = self.tmp / "t"
        build.build(out, "1600p", "window", "left", self.photo("p.jpg"), "cachyos", "none")
        text = (out / "theme.txt").read_text()
        for prop in ("left", "top", "width", "height", "terminal-width"):
            with self.subTest(property=prop):
                invalid = re.sub(
                    rf"^([ \t]*{prop}[ \t]*[=:])[ \t]*.*$",
                    r"\1 46.60%",
                    text,
                    count=1,
                    flags=re.M,
                )
                (out / "theme.txt").write_text(invalid)
                with self.assertRaisesRegex(BuildError, "proportional"):
                    validate(out, compute("1600p", "window", "left"))

    def test_menu_geometry_preserves_native_pixel_alignment(self):
        """Keep the menu aligned when replacing decimal percentages with integer expressions."""
        text = theme_txt(compute("1600p", "window", "left"))
        values = re.findall(r"^  (?:left|top|width|height) = (.+)$", text, re.M)[:4]
        self.assertEqual(len(values), 4)
        for value, extent, expected in zip(values, (2560, 1600, 2560, 1600), (1193, 478, 895, 588)):
            percent, offset = value.split("%", 1)
            self.assertEqual(int(percent) * extent // 100 + int(offset or "0"), expected)

    def test_odd_inputs_are_accepted(self):
        """Verify that odd image formats (alpha channel, tiny sizes, portrait orientation) are handled safely."""
        cases = {
            "alpha.png": dict(mode="RGBA"),
            "tiny.jpg": dict(size=(64, 48)),
            "portrait.jpg": dict(size=(600, 1800)),
        }
        for name, kw in cases.items():
            with self.subTest(name=name):
                build.build(
                    self.tmp / name.split(".")[0],
                    "1080p",
                    "window",
                    "left",
                    self.photo(name, **kw),
                    "none",
                    "soft",
                )

    def test_corrupt_photo_is_a_clean_error(self):
        """Verify that corrupt or unreadable image files raise a clean BuildError without side effects."""
        bad = self.tmp / "bad.jpg"
        bad.write_bytes(b"not an image")
        with self.assertRaises(BuildError):
            build.build(self.tmp / "t", "1080p", "window", "left", str(bad), "none", "soft")
        self.assertFalse((self.tmp / "t").exists())

    def test_names_cannot_escape_asset_directories(self):
        """Verify that path traversal attempts in photo or logo names are rejected."""
        for bad in ("../x", "a/b", ".hidden", ""):
            with self.assertRaises(BuildError):
                build.find_asset(ROOT / "backgrounds", bad, (".jpg",), "photo")
        with self.assertRaises(BuildError):
            build.build(
                self.tmp / "t",
                "1080p",
                "window",
                "left",
                self.photo("p.jpg"),
                "../../etc/passwd",
                "soft",
            )

    def test_foreign_directory_is_never_replaced(self):
        """Verify that directories not generated by this theme builder are never overwritten or deleted."""
        foreign = self.tmp / "foreign"
        foreign.mkdir()
        (foreign / "keep").write_text("x")
        with self.assertRaises(BuildError):
            build.build(foreign, "1080p", "window", "left", self.photo("p.jpg"), "none", "soft")
        self.assertTrue((foreign / "keep").exists())
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name.startswith(".foreign")], [])

    def test_rebuild_replaces_own_directory(self):
        """Verify that subsequent builds over an existing theme directory replace it cleanly."""
        out = self.tmp / "t"
        build.build(out, "1080p", "window", "left", self.photo("p.jpg"), "none", "soft")
        build.build(out, "1600p", "sharp", "left", self.photo("p.jpg"), "none", "soft")
        with Image.open(out / "background.jpg") as bg:
            self.assertEqual(bg.size, (2560, 1600))

    def test_bundled_photos_resolve_after_directory_reorganization(self):
        for name in ("forest", "mojave", "mountain", "wave", "forest.jpeg"):
            with self.subTest(name=name):
                self.assertGreater(build.load_photo(name, (1, 1)).width, 1)

    def test_named_asset_symlinks_cannot_escape_directory(self):
        assets = self.tmp / "assets"
        assets.mkdir()
        (assets / "escape.jpg").symlink_to(self.photo("outside.jpg"))
        with self.assertRaises(BuildError):
            build.find_asset(assets, "escape", (".jpg",), "photo")

    def test_failed_promotion_restores_previous_theme(self):
        out = self.tmp / "t"
        photo = self.photo("p.jpg")
        build.build(out, "1080p", "window", "left", photo, "none", "soft")
        before = (out / "background.jpg").read_bytes()
        rename = Path.rename

        def fail_stage_promotion(path, target):
            if Path(target) == out and not path.name.startswith(".t.old"):
                raise OSError("injected promotion failure")
            return rename(path, target)

        with patch.object(Path, "rename", fail_stage_promotion), self.assertRaises(OSError):
            build.build(out, "1600p", "sharp", "left", photo, "none", "soft")
        self.assertEqual((out / "background.jpg").read_bytes(), before)

    def test_destination_symlink_does_not_move_or_modify_target(self):
        target = self.tmp / "target"
        photo = self.photo("p.jpg")
        build.build(target, "1080p", "window", "left", photo, "none", "soft")
        out = self.tmp / "link"
        out.symlink_to(target, target_is_directory=True)
        before = (target / "background.jpg").read_bytes()
        with self.assertRaises(BuildError):
            build.build(out, "1600p", "sharp", "left", photo, "none", "soft")
        self.assertTrue(out.is_symlink())
        self.assertEqual((target / "background.jpg").read_bytes(), before)


# ----- TEST RUNNER ---------------------------------------------------------- #

if __name__ == "__main__":
    unittest.main()
