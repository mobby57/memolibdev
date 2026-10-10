"""
MemoLibDev — D6.0.1 : Context Versioning
=========================================

Versionnement du contexte. Chaque fichier intégré au contexte porte
son identité cryptographique au moment de l'inspection :

    - text_sha256   : SHA-256 du TEXTE (read_text utf-8)  -> contrats D5.6
    - byte_sha256   : SHA-256 des OCTETS (lecture binaire)  -> D5.9
    - git_head      : HEAD de la cible au moment de la capture

Ces DEUX conventions de SHA sont conservées distinctes, volontairement.
Les uniformiser casserait soit authorize()/validate_record (texte) soit
pre_apply D5.9 (octets). (Distinction découverte et prouvée en D6.0.)

Règle CONTEXT_STALE :
    Si, au moment d'autoriser une action, l'un des SHA capturés ne
    correspond plus au contenu actuel, OU si le HEAD de la cible a
    changé, le contexte est PÉRIMÉ. L'agent doit alors BLOCK et
    réinspecter — jamais appliquer une proposition fondée sur un
    contexte périmé.

100 % déterministe, offline, read-only. Aucune écriture, aucun git
mutant, aucun LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib


def text_sha256(content: str) -> str:
    """SHA-256 du texte (convention D5.6 : authorize/validate_record)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def byte_sha256_of_file(path: Path) -> str:
    """SHA-256 des octets bruts (convention D5.9 : ApplyCertificate)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class FileVersion:
    """
    Identité versionnée d'un fichier dans le contexte, au moment de la
    capture. Immuable (frozen). Porte les deux SHA sans les fusionner.
    """
    path: str              # chemin relatif posix dans la cible
    text_sha256: str       # SHA du texte     (D5.6)
    byte_sha256: str       # SHA des octets   (D5.9)
    size: int              # taille en octets
    git_head: str          # HEAD de la cible au moment de la capture

    def matches_current(self, git_root: Path, current_head: str) -> tuple[bool, str]:
        """
        Vérifie que cette version correspond toujours à l'état courant.
        Fail-closed : toute divergence => (False, raison).
        """
        if self.git_head != current_head:
            return False, (
                f"HEAD divergent: capture={self.git_head[:12]} "
                f"actuel={current_head[:12]}"
            )

        abs_path = (git_root / self.path).resolve()
        try:
            abs_path.relative_to(git_root.resolve())
        except ValueError:
            return False, f"chemin hors cible: {self.path}"

        if not abs_path.is_file():
            return False, f"fichier disparu: {self.path}"

        # Les deux SHA doivent rester identiques.
        current_text = abs_path.read_text(encoding="utf-8", errors="replace")
        if text_sha256(current_text) != self.text_sha256:
            return False, f"text SHA divergent: {self.path}"

        if byte_sha256_of_file(abs_path) != self.byte_sha256:
            return False, f"byte SHA divergent: {self.path}"

        return True, "version inchangée"


@dataclass(frozen=True)
class StalenessReport:
    """Résultat d'une vérification de péremption du contexte."""
    stale: bool
    reason: str
    diverged_files: tuple[str, ...]

    @property
    def status(self) -> str:
        return "CONTEXT_STALE" if self.stale else "CONTEXT_FRESH"


def capture_file_version(git_root: Path, relative_path: str,
                         git_head: str) -> FileVersion:
    """
    Capture la version d'un fichier (deux SHA + HEAD). Read-only.
    Lève FileNotFoundError si le fichier n'existe pas (fail-closed).
    """
    abs_path = (git_root / relative_path).resolve()
    abs_path.relative_to(git_root.resolve())  # confinement
    if not abs_path.is_file():
        raise FileNotFoundError(f"fichier absent pour capture: {relative_path}")

    content = abs_path.read_text(encoding="utf-8", errors="replace")
    rel_posix = abs_path.relative_to(git_root.resolve()).as_posix()
    return FileVersion(
        path=rel_posix,
        text_sha256=text_sha256(content),
        byte_sha256=byte_sha256_of_file(abs_path),
        size=abs_path.stat().st_size,
        git_head=git_head,
    )


def check_staleness(versions: list[FileVersion], git_root: Path,
                    current_head: str) -> StalenessReport:
    """
    Vérifie si un ensemble de versions capturées est toujours valide.
    Un seul fichier divergent (ou HEAD changé) => CONTEXT_STALE.
    """
    diverged: list[str] = []
    first_reason = ""
    for v in versions:
        ok, reason = v.matches_current(git_root, current_head)
        if not ok:
            diverged.append(v.path)
            if not first_reason:
                first_reason = reason

    if diverged:
        return StalenessReport(
            stale=True,
            reason=f"CONTEXT_STALE: {first_reason}",
            diverged_files=tuple(diverged),
        )
    return StalenessReport(
        stale=False,
        reason="Toutes les versions correspondent à l'état courant.",
        diverged_files=(),
    )
