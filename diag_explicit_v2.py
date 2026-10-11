# diag_explicit_v2.py — Teste la NOUVELLE fonction
import os, sys
from pathlib import Path

os.environ["MEMOLIBDEV_TARGET"] = r"C:\Users\moros\Desktop\memolib"
sys.path.insert(0, ".")

from project_target import resolve_target
from context.context_builder import _resolve_explicit_paths

target = resolve_target()
mission = "Analyse le fichier src/lib/ai-isolation.ts"

print("=" * 70)
print(" DIAGNOSTIC NOUVELLE FONCTION _resolve_explicit_paths")
print("=" * 70)
print(f" Mission : {mission}")
print()

explicit = _resolve_explicit_paths(mission, target)
print(f" Resultat : {explicit}")
print()

if explicit:
    for p in explicit:
        full = Path(target.git_root) / p
        print(f"  [OK] {p}")
        print(f"       taille : {full.stat().st_size} octets")
else:
    print("  [KO] Aucun chemin resolu")
    print()
    print("  Verifions manuellement :")
    full = Path(target.git_root) / "src/lib/ai-isolation.ts"
    print(f"    Fichier existe : {full.is_file()}")
    print(f"    Chemin absolu  : {full}")
