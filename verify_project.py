#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verification reelle post-apply. Retourne (ok, message)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _repo_file(repo_root: Path, relative_path: Path) -> Path | None:
    if relative_path.is_absolute():
        return None
    candidate = (repo_root / relative_path).resolve()
    try:
        candidate.relative_to(repo_root)
    except ValueError:
        return None
    return candidate


def _check_readable(repo_root: Path, files: list[Path]) -> list[str]:
    errors = []
    for f in files:
        p = _repo_file(repo_root, f)
        if p is None:
            errors.append(f"hors depot: {f}")
            continue
        if not p.is_file():
            errors.append(f"absent: {f}")
            continue
        try:
            content = p.read_text(encoding="utf-8")
            if not content.strip():
                errors.append(f"vide: {f}")
        except OSError as exc:
            errors.append(f"illisible: {f} ({exc})")
    return errors


def _check_python_syntax(repo_root: Path, files: list[Path]) -> list[str]:
    errors = []
    with tempfile.TemporaryDirectory(prefix="memolibdev-verify-pyc-") as pycache:
        env = os.environ.copy()
        env["PYTHONPYCACHEPREFIX"] = pycache
        for f in files:
            p = _repo_file(repo_root, f)
            if p is None:
                errors.append(f"hors depot: {f}")
                continue
            if p.suffix.lower() != ".py":
                continue
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(p)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()
                errors.append(f"syntaxe invalide: {f}\n{detail}")
    return errors


def _check_git_whitespace(repo_root: Path, files: list[Path]) -> list[str]:
    if not files:
        return ["aucun fichier modifie a verifier"]
    result = subprocess.run(
        ["git", "diff", "--check", "--", *[str(f) for f in files]],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0:
        return []
    detail = "\n".join(
        item for item in (result.stdout.strip(), result.stderr.strip()) if item
    )
    return [f"git diff --check: {detail or 'echec sans detail'}"]


def _check_pytest(repo_root: Path) -> list[str]:
    """Lance pytest si un dossier tests/ ou un fichier test_*.py existe."""
    has_tests = (repo_root / "tests").is_dir() or any(
        repo_root.glob("test_*.py")
    )
    if not has_tests:
        return []
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--no-header",
                "-x",
                "--tb=no",
                "--maxfail=1",
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"pytest impossible: {exc}"]
    if result.returncode != 0:
        detail = "\n".join(
            item for item in (result.stdout.strip(), result.stderr.strip()) if item
        )
        return [f"pytest: {detail[-500:] or 'echec sans detail'}"]
    return []


def verify_project(
    repo_root: Path | str,
    changed_files: list[str | Path],
    *,
    run_tests: bool = True,
) -> tuple[bool, str]:
    """Verifie un projet apres apply sans ecrire dans le depot cible."""
    root = Path(repo_root).resolve()
    if not root.is_dir() or not (root / ".git").exists():
        return False, "VERIFY FAIL\nracine Git invalide"

    files = [Path(f) for f in changed_files]
    if not files:
        return False, "VERIFY FAIL\naucun fichier modifie a verifier"

    errors = _check_readable(root, files)
    if errors:
        return False, "VERIFY FAIL\n" + "\n".join(errors)

    errors = _check_python_syntax(root, files)
    if errors:
        return False, "VERIFY FAIL\n" + "\n".join(errors)

    errors = _check_git_whitespace(root, files)
    if errors:
        return False, "VERIFY FAIL\n" + "\n".join(errors)

    if run_tests:
        errors = _check_pytest(root)
        if errors:
            return False, "VERIFY FAIL\n" + "\n".join(errors)

    return True, f"verify OK ({len(files)} fichier(s))"
