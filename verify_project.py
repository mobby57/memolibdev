#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verification reelle post-apply. Retourne (ok, message)."""
import subprocess
from pathlib import Path


def _check_readable(files):
    errors = []
    for f in files:
        p = Path(f)
        if not p.is_file():
            errors.append(f"absent: {f}")
            continue
        try:
            content = p.read_text(encoding="utf-8")
            if not content.strip():
                errors.append(f"vide: {f}")
        except Exception as e:
            errors.append(f"illisible: {f} ({e})")
    return errors


def _check_python_syntax(files):
    errors = []
    for f in files:
        p = Path(f)
        if p.suffix.lower() != ".py":
            continue
        r = subprocess.run(
            ["python", "-m", "py_compile", str(p)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            errors.append(f"syntaxe invalide: {f}\n{r.stderr.strip()}")
    return errors


def _check_git_whitespace(repo_root, files):
    errors = []
    try:
        r = subprocess.run(
            ["git", "diff", "--check", "--"] + [str(f) for f in files],
            cwd=str(repo_root),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0 and r.stdout.strip():
            errors.append(f"whitespace: {r.stdout.strip()}")
    except Exception:
        pass
    return errors


def _check_pytest(repo_root):
    """Lance pytest si un dossier tests/ ou un fichier test_*.py existe."""
    root = Path(repo_root)
    has_tests = (root / "tests").is_dir() or any(root.glob("test_*.py"))
    if not has_tests:
        return []
    r = subprocess.run(
        ["python", "-m", "pytest", "-q", "--no-header", "-x",
         "--tb=no", "--maxfail=1"],
        cwd=str(root),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120,
    )
    if r.returncode != 0:
        return [f"pytest: {r.stdout.strip()[-500:]}"]
    return []


def verify_project(repo_root, changed_files, *, run_tests=False):
    """Verifie un projet apres apply.
    Retourne (ok: bool, message: str).
    """
    repo_root = Path(repo_root).resolve()
    files = [Path(f) for f in changed_files]

    errors = []
    errors += _check_readable(files)
    if errors:
        return (False, "VERIFY FAIL\n" + "\n".join(errors))

    errors += _check_python_syntax(files)
    if errors:
        return (False, "VERIFY FAIL\n" + "\n".join(errors))

    errors += _check_git_whitespace(repo_root, files)
    if errors:
        return (False, "VERIFY FAIL\n" + "\n".join(errors))

    if run_tests:
        errors += _check_pytest(repo_root)
        if errors:
            return (False, "VERIFY FAIL\n" + "\n".join(errors))

    return (True, f"verify OK ({len(files)} fichier(s))")
