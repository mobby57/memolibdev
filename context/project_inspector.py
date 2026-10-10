"""
MemoLibDev — D6.0.1 : Project Inspector (read-only, cible-agnostique)
=====================================================================

Inspection READ-ONLY d'une cible quelconque, bornée au `git_root` du
`ProjectTarget` résolu. Remplace la dépendance de `inspect_repository()`
à la constante MEMOLIB codée en dur (invariant 1 : pas de chemin cible
par défaut, pas de fallback).

Garanties :
  - read-only : aucune écriture, aucun git mutant, aucun commit/push.
  - cible-agnostique : fonctionne sur n'importe quel ProjectTarget.
  - confinement : ne sort jamais du git_root ; .git exclu ; symlinks /
    reparse points ignorés (pas de traversée hors cible).
  - déterministe : résultats triés par chemin.
  - borné : extensions texte connues + plafond de fichiers.

Ne modifie AUCUN fichier existant. N'importe PAS decision_agent.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from project_target import ProjectTarget


# Extensions texte connues (reprises comme référence, non importées de
# decision_agent). Cible-agnostique.
TEXT_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".py", ".json", ".md", ".txt",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".tsv",
    ".html", ".css", ".scss", ".sql", ".sh", ".rs", ".go", ".java",
}

IGNORED_DIR_NAMES = {
    ".git", "node_modules", ".next", "dist", "build", "__pycache__",
    ".pytest_cache", ".venv", "venv", ".cache", "target",
}

# Plafond déterministe du nombre de fichiers inspectés (fail-safe).
MAX_INSPECTED_FILES = 2000


@dataclass(frozen=True)
class InspectedFile:
    """Un fichier texte inspecté (métadonnées + aperçu borné)."""
    path: str          # relatif posix
    size: int          # octets
    preview: str       # contenu borné (lecture seule)


@dataclass(frozen=True)
class InspectionResult:
    """Résultat d'inspection, déterministe et borné."""
    git_root: str
    git_head: str
    files: tuple[InspectedFile, ...]
    files_count: int
    issues: tuple[str, ...]          # chemins ignorés / erreurs d'accès
    truncated: bool                  # True si MAX_INSPECTED_FILES atteint


# Taille max d'aperçu par fichier (le budget réel est géré ailleurs).
_PREVIEW_CHARS = 12000


def inspect_target(target: ProjectTarget,
                   max_files: int = MAX_INSPECTED_FILES) -> InspectionResult:
    """
    Inspecte la cible en lecture seule, bornée à son git_root.

    Ne traverse jamais .git, node_modules, les symlinks ou reparse
    points. Les erreurs d'accès sont enregistrées, jamais fatales.
    """
    root = target.git_root.resolve()
    files: list[InspectedFile] = []
    issues: list[str] = []
    truncated = False

    def rel(p: Path) -> str:
        try:
            return p.resolve().relative_to(root).as_posix()
        except ValueError:
            return str(p)

    def walk(directory: Path) -> None:
        nonlocal truncated
        if truncated:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda x: x.name)
        except OSError as exc:
            issues.append(f"dir_access_error:{rel(directory)}:{exc}")
            return

        for path in entries:
            if truncated:
                return
            try:
                if path.name in IGNORED_DIR_NAMES:
                    continue

                if path.is_symlink():
                    issues.append(f"symlink_skipped:{rel(path)}")
                    continue

                if path.is_dir():
                    # Reparse point (junction) detection (Windows).
                    try:
                        attrs = path.stat().st_file_attributes  # type: ignore[attr-defined]
                        if attrs & 0x400:
                            issues.append(f"reparse_skipped:{rel(path)}")
                            continue
                    except (OSError, AttributeError):
                        pass
                    walk(path)
                    continue

                if not path.is_file():
                    continue
                if path.suffix.lower() not in TEXT_EXTENSIONS:
                    continue

                content = path.read_text(encoding="utf-8", errors="replace")
                files.append(InspectedFile(
                    path=rel(path),
                    size=path.stat().st_size,
                    preview=content[:_PREVIEW_CHARS],
                ))
                if len(files) >= max_files:
                    truncated = True
                    issues.append("max_files_reached")
                    return

            except OSError as exc:
                issues.append(f"entry_access_error:{rel(path)}:{exc}")

    walk(root)

    files.sort(key=lambda f: f.path)   # déterminisme
    return InspectionResult(
        git_root=str(root),
        git_head=target.head_full,
        files=tuple(files),
        files_count=len(files),
        issues=tuple(issues),
        truncated=truncated,
    )
