# diag_injection.py — Trace l'execution dans build_mission_context
import os, sys
from pathlib import Path

os.environ["MEMOLIBDEV_TARGET"] = r"C:\Users\moros\Desktop\memolib"
sys.path.insert(0, ".")

# Monkey-patch : logger ce qui se passe
import context.context_builder as cb

# 1. Tester _resolve_explicit_paths
from project_target import resolve_target
target = resolve_target()
mission = "Analyse le fichier src/lib/ai-isolation.ts"

explicit_direct = cb._resolve_explicit_paths(mission, target)
print(f"[A] _resolve_explicit_paths -> {explicit_direct}")
print()

# 2. Verifier la classe InspectedFile
print(f"[B] InspectedFile existe : {hasattr(cb, 'InspectedFile')}")
if hasattr(cb, 'InspectedFile'):
    import inspect
    sig = inspect.signature(cb.InspectedFile)
    print(f"    Signature : {sig}")
print()

# 3. Inspecter la cible
inspection = cb.inspect_target(target, max_files=cb.MAX_CONTEXT_FILES * 100)
print(f"[C] inspection.files : {len(inspection.files)} fichiers")
print(f"    Type du premier : {type(inspection.files[0]).__name__ if inspection.files else 'N/A'}")
print()

# 4. Verifier si on peut creer un InspectedFile
try:
    full = (Path(target.git_root) / "src/lib/ai-isolation.ts").resolve()
    content = full.read_text(encoding="utf-8", errors="replace")
    print(f"[D] Contenu lu : {len(content)} chars")
    if hasattr(cb, 'InspectedFile'):
        # Test avec les params probables
        import inspect
        sig = inspect.signature(cb.InspectedFile)
        params = list(sig.parameters.keys())
        print(f"    Parametres : {params}")
        # Essayer avec path + size + content
        try:
            obj = cb.InspectedFile(path="src/lib/ai-isolation.ts", size=len(content), content=content)
            print(f"    [OK] Creation reussie : {obj}")
        except Exception as e:
            print(f"    [KO] Creation echouee : {e}")
except Exception as e:
    print(f"[D] ERREUR lecture : {e}")
print()

# 5. Executer build_mission_context et voir
print(f"[E] Appel build_mission_context...")
ctx = cb.build_mission_context("diag", mission, target, max_files=8, max_context_chars=8000)
print(f"    relevant_files : {len(ctx.relevant_files or [])}")
for f in (ctx.relevant_files or []):
    print(f"      • {getattr(f, 'path', '?')}")
