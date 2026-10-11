# setup_ollama.py — Configure le skip Ollama pour les tests 5F
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

HELPER = '''
# ollama_helpers.py — Skip conditionnel Ollama
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/tags"


def ollama_available(timeout=2):
    """Retourne True si Ollama repond en <timeout secondes."""
    try:
        urllib.request.urlopen(OLLAMA_URL, timeout=timeout)
        return True
    except Exception:
        return False


def ollama_has_model(model_name):
    """Verifie qu'un modele est present (ex: 'qwen:7b')."""
    import json
    try:
        r = urllib.request.urlopen(OLLAMA_URL, timeout=3)
        data = json.loads(r.read())
        names = [m.get("name", "") for m in data.get("models", [])]
        return any(model_name in n for n in names)
    except Exception:
        return False
'''

# 1) Creer ollama_helpers.py
helper_file = ROOT / "ollama_helpers.py"
helper_file.write_text(HELPER, encoding="utf-8")
print(f"  [OK] {helper_file.name} cree")

# 2) Patcher les tests 5F pour skip automatique
TESTS = [
    "test_5f_qwen7b_check.py",
    "test_5e_real.py",
]

SKIP_BLOCK = '''import pytest
from ollama_helpers import ollama_available, ollama_has_model

pytestmark = pytest.mark.skipif(
    not ollama_available(),
    reason="Ollama non disponible (lancer 'ollama serve')"
)
'''

for name in TESTS:
    p = ROOT / name
    if not p.exists():
        print(f"  [--] {name} absent")
        continue
    src = p.read_text(encoding="utf-8")
    if "ollama_available" in src:
        print(f"  [--] {name} deja patche")
        continue

    # Inserer apres les imports
    lines = src.splitlines()
    insert_at = 0
    for i, l in enumerate(lines):
        if l.startswith(("import ", "from ")) or l.startswith('"""') or l.startswith("'''"):
            insert_at = i + 1
    # Trouver la fin des imports
    for i in range(insert_at, len(lines)):
        if lines[i].startswith(("import ", "from ")):
            insert_at = i + 1
        elif lines[i].strip() == "":
            continue
        else:
            break

    new_lines = lines[:insert_at] + ["", SKIP_BLOCK, ""] + lines[insert_at:]
    p.write_text("\n".join(new_lines), encoding="utf-8")
    print(f"  [OK] {name} patche (skip conditionnel)")

print()
print("  Verification :")
import subprocess, sys
r = subprocess.run(
    [sys.executable, "-c", "from ollama_helpers import ollama_available; print('Ollama:', ollama_available())"],
    cwd=ROOT, text=True, capture_output=True,
)
print("   ", (r.stdout or r.stderr).strip())
