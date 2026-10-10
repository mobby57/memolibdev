"""
MemoLibDev — D6.1 : FileTarget
===============================

Dataclass FROZEN (read-only) qui DÉCRIT une ressource cible sans
jamais la modifier. C'est l'abstraction générique définie dans
SPEC-D6.0 §7bis.1 : MemoLibDev ne pense plus « modifier foo.py »
mais « transformer cette ressource dans ce périmètre précis ».

Garanties :
  - Ne modifie JAMAIS le fichier.
  - Ne fait JAMAIS d'écriture disque.
  - Pas d'Ollama, pas de patch, pas de git apply, pas de commit/push.
  - Fail-closed : chemin hors périmètre ou fichier absent → erreur.
  - content_sha256 = hash du contenu brut (format-agnostic).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib

from project_target import ProjectTarget


# ----------------------------------------------------------------
# Détection format / kind / textualité
# ----------------------------------------------------------------

TEXTUAL_EXTENSIONS = {
    # code
    ".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".java",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
    ".kt", ".scala", ".sh", ".bash", ".zsh", ".bat", ".ps1",
    # config / data texte
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env",
    ".xml", ".html", ".htm", ".css", ".scss", ".less", ".svg",
    ".sql", ".graphql", ".prisma",
    # documents texte
    ".md", ".txt", ".rst", ".csv", ".tsv", ".log",
    # divers
    ".gitignore", ".editorconfig", ".eslintrc",
}

BINARY_EXTENSIONS = {
    ".xlsx", ".xls", ".docx", ".doc", ".pptx", ".ppt",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".exe", ".dll", ".so", ".dylib",
    ".sqlite", ".db",
}

KIND_MAP: dict[str, str] = {
    # code
    ".py": "CODE", ".ts": "CODE", ".tsx": "CODE", ".js": "CODE",
    ".jsx": "CODE", ".rs": "CODE", ".go": "CODE", ".java": "CODE",
    ".c": "CODE", ".cpp": "CODE", ".h": "CODE", ".cs": "CODE",
    ".rb": "CODE", ".php": "CODE", ".swift": "CODE", ".kt": "CODE",
    ".sh": "CODE", ".bat": "CODE", ".ps1": "CODE",
    # données
    ".json": "DATA", ".yaml": "DATA", ".yml": "DATA", ".toml": "DATA",
    ".xml": "DATA", ".csv": "DATA", ".tsv": "DATA", ".sql": "DATA",
    ".ini": "DATA", ".cfg": "DATA", ".env": "DATA",
    # docs texte
    ".md": "DOC", ".txt": "DOC", ".rst": "DOC", ".log": "DOC",
    # feuilles
    ".xlsx": "SHEET", ".xls": "SHEET",
    # documents Office
    ".docx": "DOC", ".doc": "DOC",
    # présentations
    ".pptx": "SLIDES", ".ppt": "SLIDES",
    # PDF
    ".pdf": "PDF",
    # images
    ".png": "IMAGE", ".jpg": "IMAGE", ".jpeg": "IMAGE",
    ".gif": "IMAGE", ".bmp": "IMAGE", ".ico": "IMAGE",
    ".svg": "IMAGE", ".webp": "IMAGE",
}


def _detect_format(path: Path) -> str:
    """Extension normalisée en minuscules, ou '' si absente."""
    return path.suffix.lower()


def _detect_kind(fmt: str) -> str:
    return KIND_MAP.get(fmt, "BINARY")


def _is_textual(fmt: str) -> bool:
    if fmt in TEXTUAL_EXTENSIONS:
        return True
    if fmt in BINARY_EXTENSIONS:
        return False
    # Inconnu → False (fail-closed : on ne suppose pas textuel).
    return False


def _content_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------
# FileTarget
# ----------------------------------------------------------------

@dataclass(frozen=True)
class FileTarget:
    """
    Description read-only d'une ressource cible.
    Ne modifie jamais le fichier. Ne fait jamais d'écriture disque.
    """

    path: str               # chemin relatif (posix) dans la cible
    format: str             # extension (.ts, .xlsx, .pdf…)
    kind: str               # CODE | DATA | DOC | SHEET | SLIDES | PDF | IMAGE | BINARY
    size: int               # taille en octets
    adapter: str            # nom de l'adaptateur responsable
    content_sha256: str     # SHA-256 du contenu brut (format-agnostic)
    git_root: str           # racine git de la cible
    git_head: str           # HEAD complet de la cible
    permissions: str        # READ_ONLY (D6.1 ne fait que décrire)
    scope: str              # périmètre autorisé (= le fichier lui-même)
    risk_level: str         # LOW | MEDIUM | HIGH
    is_textual: bool        # un diff textuel est-il applicable ?


class FileTargetError(RuntimeError):
    """Erreur de résolution d'un FileTarget (fail-closed)."""


# ----------------------------------------------------------------
# Résolution
# ----------------------------------------------------------------

# Adaptateur par défaut selon le kind.
_DEFAULT_ADAPTER: dict[str, str] = {
    "CODE": "code_adapter",
    "DATA": "code_adapter",       # texte structuré → traité comme code en v1
    "DOC": "code_adapter",        # texte → code_adapter en v1 ; docx_adapter en v2+
    "SHEET": "xlsx_adapter",
    "SLIDES": "pptx_adapter",
    "PDF": "pdf_adapter",
    "IMAGE": "image_adapter",
    "BINARY": "binary_adapter",
}


def resolve_file_target(
    relative_path: str,
    target: ProjectTarget,
    *,
    risk_level: str = "MEDIUM",
) -> FileTarget:
    """
    Résout un chemin relatif en FileTarget SANS modifier le fichier.

    Fail-closed :
      - chemin hors périmètre → FileTargetError
      - fichier absent        → FileTargetError
      - chemin vers .git      → FileTargetError
    """

    root = target.git_root.resolve()

    # Normalise le chemin relatif (posix).
    rel = Path(relative_path.replace("\\", "/"))

    # Résolution contre la racine cible.
    if rel.is_absolute():
        absolute = rel.resolve()
    else:
        absolute = (root / rel).resolve()

    # Confinement.
    try:
        absolute.relative_to(root)
    except ValueError:
        raise FileTargetError(
            f"Chemin hors périmètre du dépôt : {relative_path}"
        )

    if ".git" in absolute.parts:
        raise FileTargetError(
            f"Accès .git interdit : {relative_path}"
        )

    if not absolute.is_file():
        raise FileTargetError(
            f"Fichier absent : {relative_path} "
            f"(résolu: {absolute})"
        )

    # Description (lecture seule).
    fmt = _detect_format(absolute)
    kind = _detect_kind(fmt)
    textual = _is_textual(fmt)
    size = absolute.stat().st_size
    sha = _content_sha256(absolute)
    adapter = _DEFAULT_ADAPTER.get(kind, "binary_adapter")

    posix_rel = absolute.relative_to(root).as_posix()

    return FileTarget(
        path=posix_rel,
        format=fmt,
        kind=kind,
        size=size,
        adapter=adapter,
        content_sha256=sha,
        git_root=str(root),
        git_head=target.head_full,
        permissions="READ_ONLY",
        scope=posix_rel,
        risk_level=risk_level,
        is_textual=textual,
    )
