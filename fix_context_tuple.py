# fix_context_tuple.py — Remplace .append par une reconstruction de tuple
import shutil, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
F = ROOT / "context" / "context_builder.py"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

src = F.read_text(encoding="utf-8")

# Bloc actuel (qui crash)
OLD = """    # Si un chemin explicite n'a pas ete inspecte (rate par la limite
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

NEW = """    # Si un chemin explicite n'a pas ete inspecte (rate par la limite
    # de inspect_target), l'inspecter directement et l'ajouter.
    # InspectedFile = dataclass frozen(path: str, size: int, preview: str)
    # ATTENTION : inspection.files est un TUPLE (immuable), on reconstruit.
    if explicit_direct and inspection.files:
        import dataclasses as _dc

        template = inspection.files[0]
        existing_paths = {f.path for f in inspection.files}
        extra_files = []

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
                extra_files.append(new_obj)

        if extra_files:
            # Reconstruire inspection avec les fichiers supplementaires
            try:
                inspection = _dc.replace(
                    inspection,
                    files=tuple(inspection.files) + tuple(extra_files),
                )
            except Exception:
                # Fallback : SimpleNamespace mimique l'objet inspection
                from types import SimpleNamespace
                inspection = SimpleNamespace(
                    files=tuple(inspection.files) + tuple(extra_files),
                    **{k: v for k, v in vars(inspection).items() if k != "files"},
                )"""

if NEW.strip() in src:
    print("[--] Deja patche")
    sys.exit(0)

if OLD not in src:
    print("[KO] Bloc actuel introuvable")
    sys.exit(1)

backup = F.with_suffix(F.suffix + f".before-tuple-{STAMP}")
shutil.copy2(F, backup)
print(f"[OK] Backup : {backup.name}")

src = src.replace(OLD, NEW, 1)
F.write_text(src, encoding="utf-8")
print(f"[OK] {F.name} patche (tuple-safe)")
