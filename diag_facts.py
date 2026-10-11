# diag_facts.py — Comprendre pourquoi peu de faits
import os, sys, inspect
from pathlib import Path

os.environ["MEMOLIBDEV_TARGET"] = r"C:\Users\moros\Desktop\memolib"
sys.path.insert(0, ".")

from project_target import resolve_target
import analysis_builder as ab

target = resolve_target()
f = Path(target.git_root) / "src/lib/ai-isolation.ts"
content = f.read_text(encoding="utf-8")

print("=" * 70)
print(" DIAGNOSTIC EXTRACTEUR DE FAITS")
print("=" * 70)
print(f" Fichier : {f.name}")
print(f" Taille  : {len(content)} chars, {content.count(chr(10))} lignes")
print()

# Fonctions d'extraction disponibles
print(" Fonctions d'extraction dans analysis_builder :")
for name, obj in inspect.getmembers(ab, inspect.isfunction):
    if any(k in name.lower() for k in ["fact", "extract", "parse", "scan", "build"]):
        try:
            sig = inspect.signature(obj)
            print(f"   • {name}{sig}")
        except Exception:
            print(f"   • {name}")
print()

# Test direct sur le contenu
if hasattr(ab, "_extract_facts"):
    sig = inspect.signature(ab._extract_facts)
    print(f" _extract_facts{sig}")
    try:
        facts = ab._extract_facts(content)
        print(f" Faits extraits : {len(facts)}")
        for fact in facts[:30]:
            cat = getattr(fact, "categorie", "?")
            txt = getattr(fact, "extrait", str(fact))[:70]
            print(f"   • [{cat}] {txt}")
    except Exception as e:
        import traceback
        print(f" [KO] {e}")
        traceback.print_exc()

# Cherche d'autres extracteurs
for name in ["_extract_facts_from_content", "_scan_facts", "_build_facts"]:
    if hasattr(ab, name):
        print(f"\n [{name}] existe aussi")
