# diag_preview.py — Version robuste
import os, sys, traceback
os.environ["MEMOLIBDEV_TARGET"] = r"C:\Users\moros\Desktop\memolib"
sys.path.insert(0, ".")

try:
    from project_target import resolve_target
    from context.context_builder import inspect_target, MAX_CONTEXT_FILES
    import analysis_builder as ab

    target = resolve_target()
    print(f"Cible : {target.git_root}")

    insp = inspect_target(target, max_files=MAX_CONTEXT_FILES * 100)
    print(f"Fichiers inspectes : {len(insp.files)}")

    # Chercher ai-isolation.ts
    cible = None
    for f in insp.files:
        if "ai-isolation" in f.path:
            print(f"  trouve : {f.path}  preview={len(f.preview)} chars")
            if f.path == "src/lib/ai-isolation.ts":
                cible = f

    if cible is None:
        print()
        print("=== ai-isolation.ts NON INSPECTE ===")
        print("On va le charger directement :")
        from pathlib import Path
        full = Path(target.git_root) / "src/lib/ai-isolation.ts"
        content = full.read_text(encoding="utf-8")
        print(f"  Taille reelle : {len(content)} chars, {content.count(chr(10))} lignes")
        print()
        print("=== Test _extract_facts_from_file sur contenu complet ===")
        facts = ab._extract_facts_from_file("src/lib/ai-isolation.ts", content, "test")
        print(f"  Faits extraits : {len(facts)}")
        for fact in facts[:30]:
            cat = getattr(fact, "categorie", "?")
            line = getattr(fact, "ligne", "?")
            txt = getattr(fact, "extrait", "")[:70]
            print(f"  [{cat}] L{line}: {txt}")
    else:
        print()
        print("=== preview tronque ===")
        print(f"  preview : {len(cible.preview)} chars")
        print(f"  reel    : {cible.size} octets")
        print()
        print("=== Derniers 200 chars du preview ===")
        print(cible.preview[-200:])
        print()
        facts = ab._extract_facts_from_file(cible.path, cible.preview, "sha")
        print(f"Faits extraits : {len(facts)}")
        for fact in facts[:20]:
            print(f"  [{fact.categorie}] {fact.extrait[:60]}")

except Exception as e:
    print(f"ERREUR : {e}")
    traceback.print_exc()
