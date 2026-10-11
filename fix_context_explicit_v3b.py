# fix_context_explicit_v3b.py — Gere v1 et v2
import re, shutil, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
F = ROOT / "context" / "context_builder.py"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

src = F.read_text(encoding="utf-8")

# Bloc v2 (fix_context_explicit_v2)
BLOCK_V2 = '''            # Methode 1 : dataclasses.replace sur le template
            if _dc.is_dataclass(template):
                try:
                    new_obj = _dc.replace(
                        template,
                        path=p,
                        content=content,
                        size=full.stat().st_size,
                    )
                except Exception:
                    new_obj = None

            # Methode 2 : type(template) avec **vars()
            if new_obj is None:
                try:
                    fields = vars(template).copy()
                    fields.update({
                        "path": p,
                        "content": content,
                        "size": full.stat().st_size,
                    })
                    new_obj = type(template)(**fields)
                except Exception:
                    new_obj = None

            # Methode 3 : SimpleNamespace en dernier recours
            if new_obj is None:
                from types import SimpleNamespace
                new_obj = SimpleNamespace(
                    path=p, content=content,
                    size=full.stat().st_size,
                )'''

# Bloc v1 (fix_context_explicit)
BLOCK_V1 = '''            # Reutiliser la classe du premier fichier inspecte
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
                    pass'''

# Nouveau bloc v3 (champ "preview")
BLOCK_V3 = '''            # InspectedFile = dataclass frozen :
            #   path: str, size: int, preview: str
            # Le contenu complet va dans "preview" (utilise par le scoring).
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
                    path=p,
                    size=full.stat().st_size,
                    preview=content,
                )'''

if BLOCK_V3.strip() in src:
    print("[--] Deja en v3")
    sys.exit(0)

if BLOCK_V2 in src:
    print("[..] Bloc v2 detecte -> remplacement par v3")
    backup = F.with_suffix(F.suffix + f".before-v3-{STAMP}")
    shutil.copy2(F, backup)
    print(f"[OK] Backup : {backup.name}")
    src = src.replace(BLOCK_V2, BLOCK_V3, 1)
    F.write_text(src, encoding="utf-8")
    print("[OK] Patch v3 applique")
    sys.exit(0)

if BLOCK_V1 in src:
    print("[..] Bloc v1 detecte -> remplacement par v3")
    # Il faut aussi le header "template" qui n'existe pas dans v1
    # Remplacer tout le bloc v1 par un bloc v3 complet incluant le header
    V1_FULL = '''    if explicit_direct:
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
                ''' + BLOCK_V1

    V3_FULL = '''    if explicit_direct and inspection.files:
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

''' + BLOCK_V3 + '''

            if new_obj is not None:
                inspection.files.append(new_obj)'''

    if V1_FULL not in src:
        print("[KO] Bloc v1 non trouve tel quel")
        print("     Colle-moi les 50 lignes autour de 'explicit_direct'")
        sys.exit(1)

    backup = F.with_suffix(F.suffix + f".before-v3-{STAMP}")
    shutil.copy2(F, backup)
    print(f"[OK] Backup : {backup.name}")

    src = src.replace(V1_FULL, V3_FULL, 1)
    F.write_text(src, encoding="utf-8")
    print("[OK] Patch v3 applique (depuis v1)")
    sys.exit(0)

print("[KO] Ni v1 ni v2 detecte")
print("     Colle-moi les 50 lignes autour de 'explicit_direct'")
sys.exit(1)
