# fix_clarif_budget.py — Augmente le budget de clarification
import shutil, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
F = ROOT / "memolibdev_cli.py"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

src = F.read_text(encoding="utf-8")

# Cherche la ligne exacte
import re
m = re.search(r'ctx = build_mission_context\([^)]+\)', src)
if not m:
    print("[KO] Appel build_mission_context introuvable")
    sys.exit(1)

old_call = m.group(0)
print(f"[..] Appel actuel :")
print(f"     {old_call}")
print()

# Remplace 4000 par 20000 (ou la valeur max_context_chars actuelle)
new_call = re.sub(r'max_context_chars=\d+', 'max_context_chars=20000', old_call)

if old_call == new_call:
    print("[--] Deja a 20000 ou pas de max_context_chars")
    # Affiche la ligne
    for i, line in enumerate(src.splitlines(), 1):
        if "clarify-probe" in line or ("build_mission_context" in line and "clarify" in src[max(0, src.find(line)-200):src.find(line)+200]):
            print(f"  {i}: {line}")
    sys.exit(0)

backup = F.with_suffix(F.suffix + f".before-clarif-{STAMP}")
shutil.copy2(F, backup)
print(f"[OK] Backup : {backup.name}")

src = src.replace(old_call, new_call, 1)
F.write_text(src, encoding="utf-8")
print(f"[OK] Budget clarification augmente")
print(f"     {old_call}")
print(f"     -> {new_call}")
