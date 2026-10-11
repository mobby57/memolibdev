# diag_explicit.py — Verifie la chaine de selection
import os, sys
from pathlib import Path

os.environ["MEMOLIBDEV_TARGET"] = r"C:\Users\moros\Desktop\memolib"
sys.path.insert(0, ".")

from project_target import resolve_target
from context.context_builder import (
    inspect_target, _extract_explicit_filenames,
    _extract_terms, MAX_CONTEXT_FILES,
)

target = resolve_target()
mission = "Analyse le fichier src/lib/ai-isolation.ts"

print("=" * 70)
print(" DIAGNOSTIC EXPLICIT FILENAMES")
print("=" * 70)
print(f" Mission : {mission}")
print()

# 1. Inspection
inspection = inspect_target(target, max_files=MAX_CONTEXT_FILES * 100)
all_paths = [f.path for f in inspection.files]
print(f" [1] Inspection : {len(all_paths)} fichier(s)")

# Le fichier cible est-il inspecte ?
cible = "src/lib/ai-isolation.ts"
present = cible in all_paths
print(f"     '{cible}' present : {present}")

if not present:
    # Cherche des candidats proches
    print(f"     Fichiers contenant 'ai-isolation' :")
    for p in all_paths:
        if "ai-isolation" in p:
            print(f"       • {p}")
    print(f"     Fichiers dans src/lib/ :")
    count = 0
    for p in all_paths:
        if p.startswith("src/lib/"):
            print(f"       • {p}")
            count += 1
            if count >= 10:
                break
    print(f"     (total src/lib/ : {sum(1 for p in all_paths if p.startswith('src/lib/'))})")

# 2. Extraction explicite
explicit = _extract_explicit_filenames(mission, all_paths)
print()
print(f" [2] Explicit extrait : {explicit}")
print(f"     Match dans all_paths : {[p for p in all_paths if p in explicit]}")

# 3. Termes extraits
terms = _extract_terms(mission)
print()
print(f" [3] Termes : {terms}")
