#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build MemoLibDev.exe avec PyInstaller.
Embarque le GUI + le CLI + tous les modules necessaires.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\moros\MemoLibDev\v3")
DIST = ROOT / "dist"
BUILD = ROOT / "build"

# Modules .py a embarquer comme data (le CLI et ses dependances)
MODULES_PY = [
    "memolibdev_cli.py",
    "verify_project.py",
    "create_parser.py",
    "create_target.py",
    "create_apply.py",
    "create_authorization.py",
    "create_proof.py",
    "create_cli.py",
    "project_target.py",
    "coder_authorization.py",
    "d59_controlled_apply.py",
    "code_adapter.py",
    "file_target.py",
    "humanize.py",
    "human_states.py",
    "agent_loop.py",
    "analysis_builder.py",
    "confidence_engine.py",
    "proposal.py",
    "controlled_coder.py",
    "evidence_gate.py",
    "mission_intent.py",
    "api_facade.py",
]

# Dossiers a embarquer entierement
DIRS = ["llm", "context"]

# Hidden imports (modules charges dynamiquement)
HIDDEN = [
    "customtkinter",
    "llm.ollama_provider",
    "llm.llm_planner",
    "llm.ai_provider",
    "context.context_builder",
]


def build():
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "MemoLibDev",
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(ROOT),
    ]

    for h in HIDDEN:
        args += ["--hidden-import", h]

    for py in MODULES_PY:
        p = ROOT / py
        if p.is_file():
            args += ["--add-data", f"{p};."]
            print(f"[ADD] {py}")
        else:
            print(f"[SKIP] {py} (absent)")

    for d in DIRS:
        p = ROOT / d
        if p.is_dir():
            args += ["--add-data", f"{p};{d}"]
            print(f"[ADD] {d}/")
        else:
            print(f"[SKIP] {d}/ (absent)")

    args.append(str(ROOT / "memolibdev_gui_v4.py"))

    print()
    print("=" * 60)
    print(" LANCEMENT PyInstaller")
    print("=" * 60)
    print(" ".join(args[:10]) + " ...")
    print()

    r = subprocess.run(args)
    return r.returncode


def main():
    print("=" * 60)
    print(" Build MemoLibDev.exe")
    print("=" * 60)
    print()

    code = build()

    print()
    print("=" * 60)
    if code == 0:
        exe = DIST / "MemoLibDev.exe"
        if exe.is_file():
            size = exe.stat().st_size / (1024 * 1024)
            print(f" BUILD OK")
            print(f" Exe : {exe}")
            print(f" Taille : {size:.1f} Mo")
        else:
            print(" BUILD OK mais .exe introuvable")
    else:
        print(f" BUILD ECHEC (code {code})")
    print("=" * 60)


if __name__ == "__main__":
    main()
