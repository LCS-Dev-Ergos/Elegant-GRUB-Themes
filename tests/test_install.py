"""Installer tests in DESTDIR mode: no system files are modified."""

# ----- IMPORTS & CONSTANTS -------------------------------------------------- #

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRUB_DEFAULT = 'GRUB_TIMEOUT=5\nGRUB_TERMINAL_OUTPUT="console"\n#GRUB_GFXMODE=auto\n'


# ----- TEST SUITE ----------------------------------------------------------- #


class InstallTest(unittest.TestCase):
    def setUp(self):
        """Set up a sandbox directory tree with fake /etc/default/grub and /boot/grub."""
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        (self.root / "etc/default").mkdir(parents=True)
        (self.root / "boot/grub").mkdir(parents=True)
        self.cfg = self.root / "etc/default/grub"
        self.cfg.write_text(GRUB_DEFAULT)
        self.theme = self.root / "boot/grub/themes/tokyonight"

    def run_install(self, *args, extra_env=None):
        """Execute install.sh within the sandboxed DESTDIR and TMPDIR environment."""
        env = dict(os.environ, DESTDIR=str(self.root), TMPDIR=str(self.root))
        env.update(extra_env or {})
        return subprocess.run(
            [str(ROOT / "install.sh"), *args], env=env, capture_output=True, text=True
        )

    def test_install_updates_grub_defaults(self):
        """Verify that installation updates /etc/default/grub and creates the theme files."""
        r = self.run_install("-s", "1600p", "-f", "forest")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self.cfg.read_text()
        self.assertIn('GRUB_THEME="/boot/grub/themes/tokyonight/theme.txt"', text)
        self.assertIn("GRUB_GFXMODE=2560x1600,auto", text)
        self.assertIn('#GRUB_TERMINAL_OUTPUT="console"', text)
        self.assertEqual((self.root / "etc/default/grub.bak").read_text(), GRUB_DEFAULT)
        self.assertTrue((self.theme / "theme.txt").is_file())

    def test_reinstall_is_idempotent(self):
        """Verify that running install twice produces identical configuration without duplication."""
        self.assertEqual(self.run_install("-s", "1080p").returncode, 0)
        first = self.cfg.read_text()
        self.assertEqual(self.run_install("-s", "1080p").returncode, 0)
        self.assertEqual(self.cfg.read_text(), first)

    def test_remove(self):
        """Verify that --remove deletes the theme directory and disables GRUB_THEME in configuration."""
        self.run_install("-s", "1080p")
        r = self.run_install("-r")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.theme.exists())
        self.assertIn('#GRUB_THEME="/boot/grub/themes/tokyonight/theme.txt"', self.cfg.read_text())

    def test_dry_run_changes_nothing(self):
        """Verify that --dry-run compiles and validates the theme without modifying system files."""
        r = self.run_install("-n", "-s", "4k")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.cfg.read_text(), GRUB_DEFAULT)
        self.assertFalse(self.theme.exists())

    def test_foreign_theme_directory_is_protected(self):
        """Verify that foreign directories lacking the marker file are protected from removal or replacement."""
        self.theme.mkdir(parents=True)
        (self.theme / "mine").write_text("x")
        self.assertNotEqual(self.run_install("-s", "1080p").returncode, 0)
        self.assertNotEqual(self.run_install("-r").returncode, 0)
        self.assertTrue((self.theme / "mine").exists())
        self.assertEqual(self.cfg.read_text(), GRUB_DEFAULT)

    def test_invalid_arguments_are_rejected_before_any_change(self):
        """Verify that invalid arguments cause an early exit without modifying configuration or creating files."""
        for args in (
            ["-s", "720p"],
            ["-p", "weird"],
            ["-i", "up"],
            ["-g", "x"],
            ["-l", "../evil"],
            ["-f", "../evil"],
            ["--nope"],
        ):
            with self.subTest(args=args):
                self.assertNotEqual(self.run_install(*args).returncode, 0)
                self.assertEqual(self.cfg.read_text(), GRUB_DEFAULT)
                self.assertFalse(self.theme.exists())

    def failing_sed(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        script = bin_dir / "sed"
        script.write_text("#!/bin/sh\nexit 1\n")
        script.chmod(0o755)
        return {"PATH": f"{bin_dir}:{os.environ['PATH']}"}

    def test_configuration_failure_restores_previous_theme(self):
        self.assertEqual(self.run_install("-s", "1080p", "-f", "forest").returncode, 0)
        before_cfg = self.cfg.read_bytes()
        before_theme = (self.theme / "background.jpg").read_bytes()
        result = self.run_install("-s", "1600p", "-f", "wave", extra_env=self.failing_sed())
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.cfg.read_bytes(), before_cfg)
        self.assertEqual((self.theme / "background.jpg").read_bytes(), before_theme)

    def test_failed_fresh_install_leaves_no_theme(self):
        result = self.run_install("-s", "1080p", "-f", "forest", extra_env=self.failing_sed())
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.cfg.read_text(), GRUB_DEFAULT)
        self.assertFalse(self.theme.exists())

    def test_remove_and_dry_run_are_rejected_together(self):
        self.assertEqual(self.run_install("-s", "1080p", "-f", "forest").returncode, 0)
        before = self.cfg.read_bytes()
        result = self.run_install("--dry-run", "--remove")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.theme.exists())
        self.assertEqual(self.cfg.read_bytes(), before)

    def test_failed_remove_restores_theme_and_defaults(self):
        self.assertEqual(self.run_install("-s", "1080p", "-f", "forest").returncode, 0)
        before_cfg = self.cfg.read_bytes()
        before_theme = (self.theme / "background.jpg").read_bytes()
        result = self.run_install("--remove", extra_env=self.failing_sed())
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.cfg.read_bytes(), before_cfg)
        self.assertEqual((self.theme / "background.jpg").read_bytes(), before_theme)

    def test_remove_handles_single_quotes_without_disabling_other_theme(self):
        self.assertEqual(self.run_install("-s", "1080p", "-f", "forest").returncode, 0)
        self.cfg.write_text(
            "GRUB_THEME='/boot/grub/themes/tokyonight/theme.txt' # installed\n"
            "GRUB_THEME='/boot/grub/themes/tokyonight/theme.txt.other'\n"
        )
        result = self.run_install("--remove")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.cfg.read_text(),
            "#GRUB_THEME='/boot/grub/themes/tokyonight/theme.txt' # installed\n"
            "GRUB_THEME='/boot/grub/themes/tokyonight/theme.txt.other'\n",
        )


# ----- TEST RUNNER ---------------------------------------------------------- #

if __name__ == "__main__":
    unittest.main()
