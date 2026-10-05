"""
MemoLibDev — Option 1 / Phase A : Project Target (lecture seule)
================================================================

Module AUTONOME responsable d'UNE seule chose : établir, de façon
sûre et vérifiable, QUEL dépôt MemoLibDev est en train d'analyser.

Règles non négociables (demandées explicitement) :

  1. AUCUN fallback silencieux. Le chemin cible vient UNIQUEMENT de
     la variable d'environnement MEMOLIBDEV_TARGET.
       - absente           -> erreur explicite (ProjectTargetError)
       - chemin inexistant -> STOP
       - pas un dépôt Git   -> STOP
       - OK -> analyse autorisée

  2. Identité Git OBLIGATOIRE : on résout git root + HEAD + branche.
     Si git ne répond pas, c'est une erreur, pas un avertissement.

  3. Ce module NE DONNE AUCUNE permission d'écriture. Il ne fait que
     RÉSOUDRE et DÉCRIRE la cible. L'écriture reste interdite partout
     ailleurs comme avant (5G intact).

API :
    resolve_target() -> ProjectTarget   (dataclass, attributs .path, .git_root, ...)
    resolve_target_root() -> Path        (racine Git uniquement)
    ProjectTargetError                   (exception explicite)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import os
import subprocess


ENV_VAR = "MEMOLIBDEV_TARGET"


class ProjectTargetError(RuntimeError):
    """Erreur explicite de résolution de la cible projet."""


# Alias de compatibilité (certains modules importent TargetError).
TargetError = ProjectTargetError


@dataclass(frozen=True)
class ProjectTarget:
    """Identité résolue et vérifiée d'un dépôt cible (lecture seule)."""

    path: Path          # racine Git canonique de la cible
    git_root: Path      # identique à path (racine Git résolue par git)
    head: str           # SHA court de HEAD
    head_full: str      # SHA complet de HEAD
    branch: str         # branche courante
    fingerprint: str    # empreinte stable projet@commit
    env_var: str        # nom de la variable source

    def describe(self) -> str:
        return (
            f"Cible    : {self.git_root}\n"
            f"Branche  : {self.branch}\n"
            f"HEAD     : {self.head}\n"
            f"Empreinte: {self.fingerprint}\n"
            f"(source  : ${self.env_var})"
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path)
        d["git_root"] = str(self.git_root)
        return d


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        raise ProjectTargetError(
            f"git {' '.join(args)} a échoué dans {repo} : "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )

    return result.stdout.strip()


def _compute_fingerprint(git_root: str, head: str, branch: str) -> str:
    raw = f"{git_root}|{branch}|{head}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def resolve_target() -> ProjectTarget:
    """
    Résout la cible projet depuis MEMOLIBDEV_TARGET.

    Lève ProjectTargetError (jamais de fallback) si :
      - la variable est absente/vide
      - le chemin n'existe pas / n'est pas un dossier
      - le dossier n'est pas un dépôt Git
    """

    raw = os.environ.get(ENV_VAR)

    if not raw or not raw.strip():
        raise ProjectTargetError(
            f"La variable d'environnement {ENV_VAR} est absente. "
            "Aucun dépôt cible par défaut n'est autorisé "
            "(pas de fallback silencieux). "
            f"Définis {ENV_VAR} vers la racine du dépôt à analyser."
        )

    path = Path(raw.strip()).expanduser()

    try:
        path = path.resolve()
    except OSError as exc:
        raise ProjectTargetError(
            f"Chemin cible invalide ({raw!r}) : {exc}"
        )

    if not path.exists():
        raise ProjectTargetError(
            f"Le chemin cible n'existe pas : {path}"
        )

    if not path.is_dir():
        raise ProjectTargetError(
            f"Le chemin cible n'est pas un répertoire : {path}"
        )

    # Dépôt Git obligatoire. On demande à git la racine : cela valide
    # à la fois que c'est un dépôt ET que git fonctionne.
    try:
        git_root = _run_git(path, "rev-parse", "--show-toplevel")
    except ProjectTargetError as exc:
        raise ProjectTargetError(
            f"Le chemin cible n'est pas un dépôt Git : {path}. "
            f"Détail : {exc}"
        )

    git_root_path = Path(git_root).resolve()

    head_full = _run_git(git_root_path, "rev-parse", "HEAD")
    head = _run_git(git_root_path, "rev-parse", "--short", "HEAD")
    branch = _run_git(git_root_path, "rev-parse", "--abbrev-ref", "HEAD")

    fingerprint = _compute_fingerprint(str(git_root_path), head_full, branch)

    return ProjectTarget(
        path=git_root_path,
        git_root=git_root_path,
        head=head,
        head_full=head_full,
        branch=branch,
        fingerprint=fingerprint,
        env_var=ENV_VAR,
    )


def resolve_target_root() -> Path:
    """Raccourci : racine Git (Path) de la cible. Lève ProjectTargetError."""

    return resolve_target().git_root


if __name__ == "__main__":
    try:
        info = resolve_target()
    except ProjectTargetError as exc:
        print("ERREUR DE CIBLE :")
        print(" ", exc)
        raise SystemExit(2)

    print(info.describe())
    raise SystemExit(0)
