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
    "api_facade.py", "cli_entry.py",
]
DIRS = ["llm", "context"]
HIDDEN = [
    "customtkinter",
    "llm.ollama_provider", "llm.llm_planner", "llm.ai_provider",
    "context.context_builder",
]

print("=" * 60)
print(" BUILD DEBUG : MemoLibDev-debug.exe (mode console)")
print("=" * 60)

args = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm", "--clean", "--onefile",
    "--console",  # CONSOLE, pas windowed, pour voir les erreurs
    "--name", "MemoLibDev-debug",
    "--distpath", str(DIST),
    "--workpath", str(BUILD / "debug"),
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

args.append(str(ROOT / "memolibdev_gui_v4.py"))

r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout[-2000:] if r.stdout else "")
if r.returncode != 0:
    print("BUILD ECHEC")
    print(r.stderr[-2000:] if r.stderr else "")
    sys.exit(1)

exe = DIST / "MemoLibDev-debug.exe"
if exe.is_file():
    print(f"BUILD OK : {exe} ({exe.stat().st_size / (1024*1024):.1f} Mo)")
else:
    print("BUILD OK mais exe introuvable")
    sys.exit(1)
