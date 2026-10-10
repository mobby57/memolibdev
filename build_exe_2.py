#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build deux .exe : MemoLibDev.exe (GUI) + MemoLibDev-cli.exe (CLI)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\moros\MemoLibDev\v3")
DIST = ROOT / "dist"
BUILD = ROOT / "build"

MODULES_PY = [
    "memolibdev_cli.py", "verify_project.py", "create_parser.py",
    "create_target.py", "create_apply.py", "create_authorization.py",
    "create_proof.py", "create_cli.py", "project_target.py",
    "coder_authorization.py", "d59_controlled_apply.py", "code_adapter.py",
    "file_target.py", "humanize.py", "human_states.py", "agent_loop.py",
    "analysis_builder.py", "confidence_engine.py", "proposal.py",
    "controlled_coder.py", "evidence_gate.py", "mission_intent.py",
    "api_facade.py",
]
DIRS = ["llm", "context"]
HIDDEN = [
    "customtkinter",
    "llm.ollama_provider", "llm.llm_planner", "llm.ai_provider",
    "context.context_builder",
]


def common_args(name, work_subdir):
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile",
        "--name", name,
        "--distpath", str(DIST),
        "--workpath", str(BUILD / work_subdir),
        "--specpath", str(BUILD),
    ]
    for h in HIDDEN:
        args += ["--hidden-import", h]
    for py in MODULES_PY:
        p = ROOT / py
        if p.is_file():
            args += ["--add-data", f"{p};."]
    for d in DIRS:
        p = ROOT / d
        if p.is_dir():
            args += ["--add-data", f"{p};{d}"]
    return args


def build_cli():
    print("=" * 60)
    print(" BUILD 1/2 : MemoLibDev-cli.exe")
    print("=" * 60)
    args = common_args("MemoLibDev-cli", "cli")
    args.append(str(ROOT / "cli_entry.py"))
    r = subprocess.run(args)
    return r.returncode


def build_gui():
    print()
    print("=" * 60)
    print(" BUILD 2/2 : MemoLibDev.exe")
    print("=" * 60)
    args = common_args("MemoLibDev", "gui")
    args.append("--windowed")
    args.append(str(ROOT / "memolibdev_gui_v4.py"))
    r = subprocess.run(args)
    return r.returncode


def main():
    print("=" * 60)
    print(" Build MemoLibDev (2 exe)")
    print("=" * 60)
    print()

    c1 = build_cli()
    if c1 != 0:
        print(f"\n[ECHEC] CLI build : {c1}")
        return 1

    c2 = build_gui()
    if c2 != 0:
        print(f"\n[ECHEC] GUI build : {c2}")
        return 1

    print()
    print("=" * 60)
    print(" BUILD OK")
    for exe in ("MemoLibDev-cli.exe", "MemoLibDev.exe"):
        p = DIST / exe
        if p.is_file():
            print(f"  {exe} : {p.stat().st_size / (1024*1024):.1f} Mo")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
