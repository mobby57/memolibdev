# diag_context_v2.py — Verifie que build_mission_context inclut le fichier explicite
import os, sys
from pathlib import Path

os.environ["MEMOLIBDEV_TARGET"] = r"C:\Users\moros\Desktop\memolib"
sys.path.insert(0, ".")

from project_target import resolve_target
from context.context_builder import build_mission_context

target = resolve_target()
mission = "Analyse le fichier src/lib/ai-isolation.ts"

print("=" * 70)
print(" BUILD_MISSION_CONTEXT APRES PATCH")
print("=" * 70)

ctx = build_mission_context("diag-v2", mission, target, max_files=8, max_context_chars=8000)

print(f" Fichiers pertinents : {len(ctx.relevant_files or [])}")
for f in (ctx.relevant_files or []):
    p = getattr(f, "path", str(f))
    marker = ""
    if p == "src/lib/ai-isolation.ts":
        marker = "  <-- EXPLICIT (target)"
    elif "ai-isolation" in p:
        marker = "  <-- test"
    print(f"   • {p}{marker}")

print()
if any(getattr(f, "path", "") == "src/lib/ai-isolation.ts" for f in (ctx.relevant_files or [])):
    print(" [OK] Le fichier explicite est dans la selection")
else:
    print(" [KO] Le fichier explicite N'EST PAS dans la selection")
    print()
    print(" Verification du code source :")
    import inspect
    src = inspect.getsource(build_mission_context)
    if "_resolve_explicit_paths" in src:
        print("   -> _resolve_explicit_paths est APPELE dans build_mission_context")
    else:
        print("   -> _resolve_explicit_paths N'EST PAS appele")
    if "explicit_direct" in src:
        print("   -> variable explicit_direct PRESENTE")
    else:
        print("   -> variable explicit_direct ABSENTE")
