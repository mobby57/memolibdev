# rename_scripts.py — Renomme les test_*.py qui sont des scripts
from pathlib import Path
import re, subprocess, sys

ROOT = Path(__file__).resolve().parent

SKIP = {
    "test_verify_project.py",
    "test_interface_diagnostics.py",
    "test_interface_diagnostic_flow.py",
    "test_cli_memolibdev.py",
    "test_gui_process_supervision.py",
}

for p in sorted(ROOT.glob("test_*.py")):
    if p.name in SKIP:
        continue
    src = p.read_text(encoding="utf-8", errors="replace")
    # Cherche des fonctions test_
    if re.search(r"^\s*def test_", src, re.MULTILINE):
        print(f"  [TEST ] {p.name}")
        continue
    if re.search(r"^class Test", src, re.MULTILINE):
        print(f"  [TEST ] {p.name}")
        continue
    # Sinon c'est un script
    new = p.with_name(p.stem + "_check.py")
    if new.exists():
        print(f"  [SKIP ] {p.name} (cible existe deja)")
        continue
    print(f"  [SCRIPT] {p.name} -> {new.name}")
    # En attente de confirmation
