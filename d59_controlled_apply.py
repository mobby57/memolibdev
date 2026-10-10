"""
MemoLibDev — D5.9 : Controlled Apply
====================================

Frontière d'APPLICATION contrôlée, en CONTINUITÉ du certificat D5.8.

Principe directeur (exigé) :
    D5.8 Authorization -> D5.9 Apply est une continuité cryptographique
    et logique. On NE crée PAS une seconde logique d'autorisation.
    Le certificat D5.8 est la source de vérité :
        target binding + evidence_sha256 + scope + authorization.

Garanties non négociables :
    - APPLIED != COMMITTED : aucun git commit, aucun git push.
    - automatic_commit / automatic_push / production = toujours False.
    - POST_VERIFY FAIL  -> ROLLBACK automatique (SHA initial == final).
    - patch hors scope  -> BLOCK, aucune écriture.
    - Opère sur une racine git fournie en paramètre (jamais de chemin
      codé en dur). Le premier test utilise un sandbox éphémère.

Les 4 fonctions conceptuelles :
    pre_apply()                 -> gates D5.8 + git apply --check
    snapshot()                  -> SHA avant + HEAD + patch SHA
    controlled_apply()          -> git apply (jamais commit/push)
    post_apply_or_rollback()    -> verify -> APPLIED | ROLLBACK
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import hashlib
import subprocess


# ------------------------------------------------------------------
# Helpers purs (même logique que apply.py/snapshot.py, SANS ROOT codé)
# ------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _git_apply(
    repo_root: Path,
    patch_text: str,
    *extra_args: str,
) -> subprocess.CompletedProcess:
    """
    Exécute `git apply [extra_args] <patchfile>` via un FICHIER patch
    temporaire plutôt que stdin.

    Raison : sur Windows, passer un diff par stdin (`git apply -`) peut
    échouer (« patch does not apply ») à cause de la conversion de flux,
    alors que le même diff passé en fichier s'applique correctement.
    Le fichier temporaire est créé HORS du dépôt cible et supprimé.
    """
    import tempfile
    import os

    fd, tmp = tempfile.mkstemp(prefix="memolibdev-patch-", suffix=".diff")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(patch_text)
        return subprocess.run(
            ["git", "-C", str(repo_root), "apply", *extra_args, tmp],
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def extract_targets(patch_text: str) -> list[str]:
    """Chemins modifiés par le patch (lignes +++ b/...), hors /dev/null."""
    targets: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            if path == "/dev/null":
                continue
            if path not in targets:
                targets.append(path)
    return targets


def safe_repo_path(repo_root: Path, relative_path: str) -> Path | None:
    candidate = (repo_root / relative_path).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        return None
    if ".git" in candidate.parts:
        return None
    return candidate


# ------------------------------------------------------------------
# Vue minimale du certificat D5.8 (continuité, pas de duplication)
# ------------------------------------------------------------------

@dataclass(frozen=True)
class ApplyCertificate:
    """
    Projection des champs du certificat D5.8 nécessaires à l'apply.
    Correspond au JSON produit par coder_authorization.
    """
    path: str                    # scope autorisé (unique fichier)
    status: str                  # doit être "AUTHORIZED"
    evidence_sha256: str         # SHA du contenu autorisé
    target_git_root: str
    target_head: str
    target_fingerprint: str


@dataclass(frozen=True)
class ApplyResult:
    status: str                  # APPLIED | ROLLED_BACK | BLOCKED
    reason: str
    sha_initial: str | None
    sha_final: str | None
    rolled_back: bool
    committed: bool
    pushed: bool
    report: dict


# Constantes d'invariant : jamais vrai en D5.9.
AUTOMATIC_COMMIT = False
AUTOMATIC_PUSH = False
PRODUCTION = False


# ------------------------------------------------------------------
# 1. PRE-APPLY GATES (continuité D5.8)
# ------------------------------------------------------------------

def pre_apply(
    repo_root: Path,
    certificate: ApplyCertificate,
    patch_text: str,
    *,
    target_head: str,
    target_fingerprint: str,
) -> tuple[bool, str]:
    """
    Vérifie, AVANT toute écriture :
      G1. certificat AUTHORIZED
      G2. target binding (git_root + HEAD + fingerprint du certificat
          == cible courante)
      G3. scope : le patch ne touche QUE certificate.path
      G4. evidence_sha256 : SHA actuel du fichier == celui du certificat
      G5. git apply --check : le patch est applicable

    Fail-closed : toute condition non prouvée => BLOCK (False).
    """

    # G1 — Autorisation.
    if certificate.status != "AUTHORIZED":
        return False, "certificat non AUTHORIZED"

    # G2 — Target binding : la cible courante doit être celle du cert.
    if Path(certificate.target_git_root).resolve() != repo_root.resolve():
        return False, "target git_root mismatch"
    if certificate.target_head != target_head:
        return False, "target HEAD mismatch"
    if certificate.target_fingerprint != target_fingerprint:
        return False, "target fingerprint mismatch"

    # G3 — Scope : aucun fichier hors du scope autorisé.
    touched = extract_targets(patch_text)
    if not touched:
        return False, "aucun fichier identifiable dans le patch"
    allowed = {Path(certificate.path).as_posix()}
    touched_norm = {Path(t).as_posix() for t in touched}
    out_of_scope = sorted(touched_norm - allowed)
    if out_of_scope:
        return False, f"patch hors scope: {out_of_scope}"

    # G4 — Evidence integrity binding : le fichier n'a pas changé
    #      depuis l'émission du certificat.
    target_file = safe_repo_path(repo_root, certificate.path)
    if target_file is None:
        return False, "chemin cible interdit/hors dépôt"
    if not target_file.is_file():
        return False, "fichier cible absent"
    current_sha = sha256_file(target_file)
    if current_sha != certificate.evidence_sha256:
        return False, (
            "evidence SHA-256 mismatch: "
            f"cert={certificate.evidence_sha256[:16]} "
            f"actuel={current_sha[:16]}"
        )

    # G5 — Applicabilité réelle (patch via fichier, robuste sur Windows).
    check = _git_apply(repo_root, patch_text, "--check", "--verbose")
    if check.returncode != 0:
        return False, f"git apply --check a échoué: {check.stderr.strip()}"

    return True, "pre-apply gates OK"


# ------------------------------------------------------------------
# 2. SNAPSHOT (état réversible AVANT apply)
# ------------------------------------------------------------------

def snapshot(
    repo_root: Path,
    certificate: ApplyCertificate,
    patch_text: str,
) -> dict:
    """
    Capture l'état réversible : SHA du/des fichier(s) cible(s), HEAD,
    SHA du patch. Exige un dépôt propre (fail-closed).
    """
    status = run_git(repo_root, "status", "--porcelain")
    if status.returncode != 0:
        raise RuntimeError("git status impossible")
    if status.stdout.strip():
        raise RuntimeError("dépôt non propre — snapshot refusé")

    head = run_git(repo_root, "rev-parse", "HEAD")
    if head.returncode != 0:
        raise RuntimeError("git HEAD impossible")

    target_file = safe_repo_path(repo_root, certificate.path)
    if target_file is None or not target_file.is_file():
        raise RuntimeError("fichier cible invalide pour snapshot")

    return {
        "git_head": head.stdout.strip(),
        "patch_sha256": sha256_text(patch_text),
        "files": [
            {
                "path": certificate.path,
                "sha256": sha256_file(target_file),
            }
        ],
    }


# ------------------------------------------------------------------
# 3. CONTROLLED APPLY (jamais commit/push)
# ------------------------------------------------------------------

def controlled_apply(
    repo_root: Path,
    patch_text: str,
) -> tuple[bool, str]:
    """
    Applique le patch au working tree UNIQUEMENT.
    Aucun add, aucun commit, aucun push.
    """
    result = _git_apply(repo_root, patch_text)
    if result.returncode != 0:
        return False, f"git apply a échoué: {result.stderr.strip()}"
    return True, "patch appliqué au working tree"


def _rollback(repo_root: Path, snap: dict, patch_text: str) -> bool:
    """
    Restaure l'état d'avant apply. Deux voies, dans l'ordre :
      1. git apply -R (inverse du patch)
      2. git checkout -- <fichiers du snapshot> (filet de sécurité)
    Retourne True si l'état final correspond au snapshot.
    """
    # Voie 1 : patch inverse (via fichier, robuste sur Windows).
    _git_apply(repo_root, patch_text, "-R")

    # Voie 2 : checkout des fichiers (idempotent, nettoie tout résidu).
    for item in snap["files"]:
        run_git(repo_root, "checkout", "--", item["path"])

    # Vérifie que chaque fichier a retrouvé son SHA initial.
    for item in snap["files"]:
        target = safe_repo_path(repo_root, item["path"])
        if target is None or not target.is_file():
            return False
        if sha256_file(target) != item["sha256"]:
            return False
    return True


# ------------------------------------------------------------------
# 4. POST-APPLY VERIFY -> APPLIED | ROLLBACK
# ------------------------------------------------------------------

def post_apply_or_rollback(
    repo_root: Path,
    certificate: ApplyCertificate,
    patch_text: str,
    snap: dict,
    verify: Callable[[Path], tuple[bool, str]],
) -> ApplyResult:
    """
    Lance la vérification post-apply.
      PASS -> APPLIED (working tree modifié, NON commité).
      FAIL -> ROLLBACK automatique, SHA initial == SHA final garanti.
    """
    target_file = safe_repo_path(repo_root, certificate.path)
    sha_initial = snap["files"][0]["sha256"]

    verify_ok, verify_reason = verify(repo_root)

    if verify_ok:
        sha_final = sha256_file(target_file)
        return ApplyResult(
            status="APPLIED",
            reason=f"POST_VERIFY PASS: {verify_reason}",
            sha_initial=sha_initial,
            sha_final=sha_final,
            rolled_back=False,
            committed=AUTOMATIC_COMMIT,   # False
            pushed=AUTOMATIC_PUSH,        # False
            report={
                "status": "APPLIED",
                "applied_not_committed": True,
                "automatic_commit": AUTOMATIC_COMMIT,
                "automatic_push": AUTOMATIC_PUSH,
                "production": PRODUCTION,
                "verify_reason": verify_reason,
            },
        )

    # FAIL -> rollback automatique.
    restored = _rollback(repo_root, snap, patch_text)
    sha_final = sha256_file(target_file) if target_file.is_file() else None

    return ApplyResult(
        status="ROLLED_BACK" if restored else "ROLLBACK_FAILED",
        reason=f"POST_VERIFY FAIL: {verify_reason}",
        sha_initial=sha_initial,
        sha_final=sha_final,
        rolled_back=restored,
        committed=False,
        pushed=False,
        report={
            "status": "ROLLED_BACK" if restored else "ROLLBACK_FAILED",
            "sha_restored": restored and sha_final == sha_initial,
            "automatic_commit": False,
            "automatic_push": False,
            "production": PRODUCTION,
            "verify_reason": verify_reason,
        },
    )


# ------------------------------------------------------------------
# Orchestration complète
# ------------------------------------------------------------------

def run_controlled_apply(
    repo_root: Path,
    certificate: ApplyCertificate,
    patch_text: str,
    *,
    target_head: str,
    target_fingerprint: str,
    verify: Callable[[Path], tuple[bool, str]],
) -> ApplyResult:
    """
    Chaîne complète : pre_apply -> snapshot -> controlled_apply
    -> post_apply_or_rollback. Fail-closed à chaque étape.
    """
    ok, reason = pre_apply(
        repo_root,
        certificate,
        patch_text,
        target_head=target_head,
        target_fingerprint=target_fingerprint,
    )
    if not ok:
        return ApplyResult(
            status="BLOCKED",
            reason=f"PRE_APPLY BLOCK: {reason}",
            sha_initial=None,
            sha_final=None,
            rolled_back=False,
            committed=False,
            pushed=False,
            report={"status": "BLOCKED", "reason": reason},
        )

    snap = snapshot(repo_root, certificate, patch_text)

    applied, apply_reason = controlled_apply(repo_root, patch_text)
    if not applied:
        # L'apply lui-même a échoué : rien n'est écrit, pas de rollback.
        return ApplyResult(
            status="BLOCKED",
            reason=f"APPLY FAILED: {apply_reason}",
            sha_initial=snap["files"][0]["sha256"],
            sha_final=snap["files"][0]["sha256"],
            rolled_back=False,
            committed=False,
            pushed=False,
            report={"status": "BLOCKED", "reason": apply_reason},
        )

    return post_apply_or_rollback(
        repo_root, certificate, patch_text, snap, verify
    )
