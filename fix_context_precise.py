# fix_context_precise.py — Remplace exactement le bloc defaillant
import shutil, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
F = ROOT / "context" / "context_builder.py"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

src = F.read_text(encoding="utf-8")

# Bloc v1 exact (lignes 546-570)
OLD = """    # Si un chemin explicite n'a pas ete inspecte (rate par la limite),
    # l'inspecter directement et l'ajouter a inspection.files.
    if explicit_direct:
        existing_paths = {f.path for f in inspection.files}
        for p in explicit_direct:
            if p in existing_paths:
                continue
            full = (Path(target.git_root) / p).resolve()
            if full.is_file():
                try:
                    content = full.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                # Reutiliser la classe du premier fichier inspecte
                try:
                    from context.context_builder import InspectedFile
                except ImportError:
                    InspectedFile = None
                if InspectedFile is not None:
                    try:
                        inspection.files.append(InspectedFile(
                            path=p, size=full.stat().st_size, content=content,
                        ))
                    except Exception:
                        pass"""

NEW = """    # Si un chemin explicite n'a pas ete inspecte (rate par la limite
    # de inspect_target), l'inspecter directement et l'ajouter.
    # InspectedFile = dataclass frozen(path: str, size: int, preview: str)
    if explicit_direct and inspection.files:
        import dataclasses as _dc

        template = inspection.files[0]
        existing_paths = {f.path for f in inspection.files}

        for p in explicit_direct:
            if p in existing_paths:
                continue
            full = (Path(target.git_root) / p).resolve()
            if not full.is_file():
                continue
            try:
                content = full.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            new_obj = None
            try:
                new_obj = _dc.replace(
                    template,
                    path=p,
                    size=full.stat().st_size,
                    preview=content,
                )
            except Exception:
                from types import SimpleNamespace
                new_obj = SimpleNamespace(
                    path=p, size=full.stat().st_size, preview=content,
                )

            if new_obj is not None:
                inspection.files.append(new_obj)"""

if NEW.strip() in src:
    print("[--] Deja patche")
    sys.exit(0)

if OLD not in src:
    print("[KO] Bloc v1 exact introuvable")
    print("     Le fichier a peut-etre ete modifie manuellement")
    sys.exit(1)

backup = F.with_suffix(F.suffix + f".before-precise-{STAMP}")
shutil.copy2(F, backup)
print(f"[OK] Backup : {backup.name}")

src = src.replace(OLD, NEW, 1)
F.write_text(src, encoding="utf-8")
print(f"[OK] {F.name} patche")
print()
print("Verifie avec : python diag_context_v2.py")
