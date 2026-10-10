"""Evidence fail-closed de l'absence d'une cible CREATE."""

from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from create_target import CreateTarget


ABSENCE_SENTINEL = b"MemoLibDev CREATE absence evidence v1\n"
ABSENCE_SENTINEL_SHA256 = hashlib.sha256(ABSENCE_SENTINEL).hexdigest()
EVIDENCE_VERSION = "CREATE_ABSENCE_V1"


class CreateProofError(ValueError):
    """Evidence d'absence invalide ou devenue non vérifiable."""


@dataclass(frozen=True)
class AbsenceEvidence:
    version: str
    git_root: str
    target_path: str
    git_head: str
    captured_at: str
    expires_at: str
    sentinel_sha256: str
    evidence_sha256: str


@dataclass(frozen=True)
class RollbackAbsenceProof:
    version: str
    absence_evidence_sha256: str
    git_root: str
    target_path: str
    confirmed_at: str
    sentinel_sha256: str
    proof_sha256: str


def _canonical_json(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_payload(payload: dict) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _git_head(git_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(git_root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise CreateProofError("HEAD Git non verifiable")
    return result.stdout.strip()


def _evidence_payload(
    *,
    git_root: str,
    target_path: str,
    git_head: str,
    captured_at: str,
    expires_at: str,
    sentinel_sha256: str,
) -> dict:
    return {
        "version": EVIDENCE_VERSION,
        "git_root": git_root,
        "target_path": target_path,
        "git_head": git_head,
        "captured_at": captured_at,
        "expires_at": expires_at,
        "sentinel_sha256": sentinel_sha256,
    }


def capture_absence_evidence(
    target: CreateTarget,
    *,
    ttl_seconds: int = 300,
    now: datetime | None = None,
) -> AbsenceEvidence:
    """Observe une cible absente et produit une evidence bornée dans le temps."""
    if target.exists_before:
        raise CreateProofError("cible CREATE initialement presente")
    if ttl_seconds <= 0:
        raise CreateProofError("TTL d'evidence invalide")
    if target.abs_path.exists():
        raise CreateProofError("cible deja presente")
    if not target.abs_path.parent.is_dir():
        raise CreateProofError("dossier parent absent")

    captured = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    expires = captured + timedelta(seconds=ttl_seconds)
    git_root = str(target.git_root.resolve())
    payload = _evidence_payload(
        git_root=git_root,
        target_path=target.rel_path,
        git_head=_git_head(target.git_root),
        captured_at=captured.isoformat(timespec="microseconds"),
        expires_at=expires.isoformat(timespec="microseconds"),
        sentinel_sha256=ABSENCE_SENTINEL_SHA256,
    )
    return AbsenceEvidence(
        **payload,
        evidence_sha256=_sha256_payload(payload),
    )


def validate_absence_evidence(
    target: CreateTarget,
    evidence: AbsenceEvidence,
    *,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Revérifie l'evidence et l'absence avant toute écriture."""
    if target.exists_before:
        return False, "cible CREATE initialement presente"
    if not isinstance(evidence, AbsenceEvidence):
        return False, "evidence d'absence invalide"
    if evidence.version != EVIDENCE_VERSION:
        return False, "version d'evidence inconnue"
    if evidence.git_root != str(target.git_root.resolve()):
        return False, "git_root de l'evidence different"
    if evidence.target_path != target.rel_path:
        return False, "chemin de l'evidence different"
    if evidence.sentinel_sha256 != ABSENCE_SENTINEL_SHA256:
        return False, "sentinelle d'absence invalide"

    payload = _evidence_payload(
        git_root=evidence.git_root,
        target_path=evidence.target_path,
        git_head=evidence.git_head,
        captured_at=evidence.captured_at,
        expires_at=evidence.expires_at,
        sentinel_sha256=evidence.sentinel_sha256,
    )
    expected_sha = _sha256_payload(payload)
    if not hmac.compare_digest(evidence.evidence_sha256, expected_sha):
        return False, "SHA de l'evidence invalide"

    try:
        expires_at = datetime.fromisoformat(evidence.expires_at)
    except ValueError:
        return False, "expiration d'evidence invalide"
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if expires_at.tzinfo is None or current_time > expires_at:
        return False, "evidence d'absence expiree"
    if target.abs_path.exists():
        return False, "le fichier est apparu depuis la proposition"
    if not target.abs_path.parent.is_dir():
        return False, "dossier parent absent"
    try:
        if _git_head(target.git_root) != evidence.git_head:
            return False, "HEAD Git different depuis la proposition"
    except CreateProofError as exc:
        return False, str(exc)
    return True, "absence verifiee"


def build_rollback_absence_proof(
    target: CreateTarget,
    evidence: AbsenceEvidence,
    *,
    now: datetime | None = None,
) -> RollbackAbsenceProof:
    """Produit une confirmation hachée uniquement après suppression vérifiée."""
    if target.abs_path.exists():
        raise CreateProofError("rollback non confirme : fichier encore present")
    confirmed = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = _rollback_payload(
        absence_evidence_sha256=evidence.evidence_sha256,
        git_root=str(target.git_root.resolve()),
        target_path=target.rel_path,
        confirmed_at=confirmed.isoformat(timespec="microseconds"),
        sentinel_sha256=ABSENCE_SENTINEL_SHA256,
    )
    return RollbackAbsenceProof(
        **payload,
        proof_sha256=_sha256_payload(payload),
    )


def _rollback_payload(
    *,
    absence_evidence_sha256: str,
    git_root: str,
    target_path: str,
    confirmed_at: str,
    sentinel_sha256: str,
) -> dict:
    return {
        "version": "CREATE_ROLLBACK_ABSENCE_V1",
        "absence_evidence_sha256": absence_evidence_sha256,
        "git_root": git_root,
        "target_path": target_path,
        "confirmed_at": confirmed_at,
        "sentinel_sha256": sentinel_sha256,
    }


def validate_rollback_absence_proof(
    target: CreateTarget,
    evidence: AbsenceEvidence,
    proof: RollbackAbsenceProof,
) -> tuple[bool, str]:
    """Vérifie que la preuve de rollback lie bien l'absence observée."""
    if not isinstance(proof, RollbackAbsenceProof):
        return False, "preuve de rollback invalide"
    if target.abs_path.exists():
        return False, "rollback non confirme : fichier encore present"
    if proof.git_root != str(target.git_root.resolve()):
        return False, "git_root de preuve different"
    if proof.target_path != target.rel_path:
        return False, "chemin de preuve different"
    if proof.absence_evidence_sha256 != evidence.evidence_sha256:
        return False, "evidence liee differente"
    if proof.sentinel_sha256 != ABSENCE_SENTINEL_SHA256:
        return False, "sentinelle de preuve invalide"
    payload = _rollback_payload(
        absence_evidence_sha256=proof.absence_evidence_sha256,
        git_root=proof.git_root,
        target_path=proof.target_path,
        confirmed_at=proof.confirmed_at,
        sentinel_sha256=proof.sentinel_sha256,
    )
    if not hmac.compare_digest(proof.proof_sha256, _sha256_payload(payload)):
        return False, "SHA de preuve invalide"
    return True, "rollback confirme"
