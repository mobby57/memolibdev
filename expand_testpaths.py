# expand_testpaths.py — Teste chaque suite, met a jour pytest.ini
import re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTEST_INI = ROOT / "pytest.ini"

CANDIDATES = [
    "test_verify_project.py",
    "test_interface_diagnostics.py",
    "test_interface_diagnostic_flow.py",
    "test_analysis_builder.py",
    "test_confidence_engine.py",
    "test_d61_file_target.py",
    "test_d62_code_adapter.py",
    "test_api_facade.py",
    "test_api_state_machine.py",
    "test_cli_memolibdev.py",
    "test_gui_process_supervision.py",
]

def run_one(fname):
    r = subprocess.run(
        [sys.executable, "-m", "pytest", fname, "-q", "--timeout=30",
         "-o", "testpaths="],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    return r.returncode, (r.stdout or "")[-300:]

def main():
    print("=" * 60)
    print(" EXPAND TESTPATHS")
    print("=" * 60)

    good = []
    for f in CANDIDATES:
        p = ROOT / f
        if not p.exists():
            print(f"  [--] {f} absent")
            continue
        code, tail = run_one(f)
        if code == 0:
            print(f"  [OK] {f}")
            good.append(f)
        else:
            print(f"  [KO] {f}  (code={code})")
            print("      ", tail.splitlines()[-1] if tail else "")

    print()
    print(f"  {len(good)} suite(s) valide(s) :")
    for f in good:
        print(f"    - {f}")

    if not good:
        print("  Aucune suite validable, pytest.ini inchange.")
        return

    # Reecrire pytest.ini
    lines = ["[pytest]", "addopts = -q", "testpaths ="]
    for f in good:
        lines.append(f"    {f}")
    lines += [
        "norecursedirs =",
        "    .venv",
        "    venv",
        "    __pycache__",
        "    .git",
        "    .pytest_cache",
        "    _legacy_document_engine",
        "    _backups",
        "    node_modules",
        "markers =",
        "    slow: tests longs",
        "    integration: tests necessitant Ollama/API",
    ]
    PYTEST_INI.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print()
    print("  pytest.ini mis a jour.")

if __name__ == "__main__":
    main()
