# fix_context_explicit.py — Ajoute resolution directe des chemins cites
import re, shutil, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
F = ROOT / "context" / "context_builder.py"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

src = F.read_text(encoding="utf-8")

# 1) Verifier que le patch n'est pas deja applique
if "_resolve_explicit_paths" in src:
    print("[--] Patch deja applique")
    sys.exit(0)

# 2) Ajouter la fonction helper AVANT build_mission_context
helper = '''

def _resolve_explicit_paths(mission_text: str, target) -> list[str]:
    """
    Extrait les chemins de fichiers CITIES EXPLICITEMENT dans la mission
    et verifie leur existence reelle dans la cible, SANS dependre de
    l'inspection limitee (qui peut rater des dossiers).

    Exemple :
        'Analyse le fichier src/lib/ai-isolation.ts'
        -> ['src/lib/ai-isolation.ts']

    Retourne une liste de chemins relatifs valides (fichiers existants).
    Fail-closed : si rien, retourne [].
    """
    import re
    from pathlib import Path

    if not mission_text or not mission_text.strip():
        return []

    # Motifs : src/lib/foo.ts, ./src/foo.py, chemin/avec/slash.ext
    # Extension : 1 a 5 lettres/chiffres
    pattern = r'(?:^|[\\s"\\'\\(\\[])([\\w./-]+\\.[A-Za-z0-9]{1,5})(?=[\\s"\\'\\)\\],.;:]|$)'

    candidates = re.findall(pattern, mission_text)

    git_root = Path(target.git_root).resolve()
    valid = []

    for raw in candidates:
        # Normaliser
        p = raw.strip().lstrip("./").replace("\\\\", "/")
        if not p or ".." in p.split("/"):
            continue
        if p.startswith("http"):
            continue
        if "/" not in p:  # on exige au moins un slash pour eviter les faux positifs
            continue

        full = (git_root / p).resolve()

        # Confinement : doit etre DANS la cible
        try:
            full.relative_to(git_root)
        except ValueError:
            continue

        if full.is_file():
            valid.append(p)

    # Deduplication en preservant l'ordre
    seen = set()
    out = []
    for p in valid:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out

'''

anchor = "def build_mission_context("
idx = src.find(anchor)
if idx == -1:
    print("[KO] build_mission_context introuvable")
    sys.exit(1)

# Backup
backup = F.with_suffix(F.suffix + f".before-explicitfix-{STAMP}")
shutil.copy2(F, backup)
print(f"[OK] Backup : {backup.name}")

# Inserer le helper avant build_mission_context
src = src[:idx] + helper.lstrip("\n") + "\n\n" + src[idx:]

# 3) Modifier build_mission_context pour utiliser la resolution directe
# Apres "if not mission_text.strip():" et avant "inspection = inspect_target",
# inserer un bloc qui resout directement et injecte

old_block = """    if not mission_text.strip():
        raise ValueError("mission vide")

    inspection = inspect_target(target, max_files=max_files * 100)
    terms = _extract_terms(mission_text)"""

new_block = """    if not mission_text.strip():
        raise ValueError("mission vide")

    # PRIORITE 0 : resolution directe des chemins cites dans la mission.
    # Ne depend PAS de inspect_target (qui peut etre plafonne et rater
    # des dossiers profonds comme src/lib/).
    explicit_direct = _resolve_explicit_paths(mission_text, target)

    inspection = inspect_target(target, max_files=max_files * 100)
    terms = _extract_terms(mission_text)"""

if old_block not in src:
    print("[KO] Bloc 'inspection = inspect_target' non trouve tel quel")
    print("     Structure differente, patch manuel requis")
    sys.exit(1)

src = src.replace(old_block, new_block, 1)

# 4) Modifier la logique de filtre explicite pour inclure explicit_direct
old_filter = """    all_paths = [f.path for f in inspection.files]
    explicit = _extract_explicit_filenames(mission_text, all_paths)
    if explicit:
        files_to_score = [f for f in inspection.files if f.path in explicit]
    else:
        files_to_score = inspection.files"""

new_filter = """    all_paths = [f.path for f in inspection.files]

    # Filtrer sur les chemins explicites (union : directs + detectes par l'inspecteur)
    explicit_inspect = _extract_explicit_filenames(mission_text, all_paths)
    explicit = set(explicit_inspect) | set(explicit_direct)

    # Si un chemin explicite n'a pas ete inspecte (rate par la limite),
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
                        pass

    if explicit:
        files_to_score = [f for f in inspection.files if f.path in explicit]
    else:
        files_to_score = inspection.files"""

if old_filter not in src:
    print("[KO] Bloc de filtre explicite non trouve tel quel")
    print("     Structure differente, patch manuel requis")
    sys.exit(1)

src = src.replace(old_filter, new_filter, 1)

F.write_text(src, encoding="utf-8")
print(f"[OK] {F.name} patche")
print()
print("Verifie ensuite avec : python diag_explicit.py")
