"""Tests sans dépendance externe pour la vérification post-apply."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from verify_project import verify_project


class VerifyProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="memolibdev-verify-")
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "test@local"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "test"],
            check=True,
        )
        (self.root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "module.py"], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-qm", "baseline"],
            check=True,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_python_passes_from_another_working_directory(self) -> None:
        (self.root / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
        previous = Path.cwd()
        try:
            os.chdir(Path(__file__).resolve().parent)
            ok, message = verify_project(self.root, ["module.py"], run_tests=False)
        finally:
            os.chdir(previous)

        self.assertTrue(ok, message)
        self.assertIn("verify OK", message)

    def test_invalid_python_fails(self) -> None:
        (self.root / "module.py").write_text("def broken(:\n", encoding="utf-8")

        ok, message = verify_project(self.root, ["module.py"], run_tests=False)

        self.assertFalse(ok)
        self.assertIn("syntaxe invalide", message)

    def test_trailing_whitespace_fails(self) -> None:
        (self.root / "module.py").write_text("VALUE = 2  \n", encoding="utf-8")

        ok, message = verify_project(self.root, ["module.py"], run_tests=False)

        self.assertFalse(ok)
        self.assertIn("git diff --check", message)

    def test_missing_file_fails(self) -> None:
        (self.root / "module.py").unlink()

        ok, message = verify_project(self.root, ["module.py"], run_tests=False)

        self.assertFalse(ok)
        self.assertIn("absent: module.py", message)

    def test_empty_changed_set_fails_closed(self) -> None:
        ok, message = verify_project(self.root, [], run_tests=False)

        self.assertFalse(ok)
        self.assertIn("aucun fichier modifie", message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
