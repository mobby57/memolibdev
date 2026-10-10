import hashlib
from dataclasses import dataclass
from pathlib import Path

from create_proof import (
    AbsenceEvidence,
    RollbackAbsenceProof,
    build_rollback_absence_proof,
    validate_absence_evidence,
)

@dataclass(frozen=True)
class ApplyResult:
    status: str
    path: str
    sha256: str | None
    rolled_back: bool
    reason: str | None
    absence_evidence_sha256: str | None = None
    rollback_proof_sha256: str | None = None
    rollback_proof: RollbackAbsenceProof | None = None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_create(target, content, verify_fn, absence_evidence: AbsenceEvidence):
    evidence_ok, evidence_reason = validate_absence_evidence(
        target, absence_evidence
    )
    if not evidence_ok:
        return ApplyResult(
            "BLOCKED",
            target.rel_path,
            None,
            False,
            evidence_reason,
            absence_evidence.evidence_sha256,
        )
    try:
        with target.abs_path.open("x", encoding="utf-8", newline="\n") as output:
            output.write(content)
    except FileExistsError:
        return ApplyResult(
            "BLOCKED",
            target.rel_path,
            None,
            False,
            "le fichier est apparu entre la preuve et l'ecriture",
            absence_evidence.evidence_sha256,
        )
    except OSError as exc:
        return ApplyResult(
            "FAILED",
            target.rel_path,
            None,
            False,
            f"ecriture : {exc}",
            absence_evidence.evidence_sha256,
        )

    sha = _sha256_file(target.abs_path)
    try:
        ok, msg = verify_fn(target.abs_path)
    except Exception as exc:
        ok, msg = False, f"verify exception : {exc}"
    if ok:
        return ApplyResult(
            "APPLIED",
            target.rel_path,
            sha,
            False,
            None,
            absence_evidence.evidence_sha256,
        )

    if not target.abs_path.is_file() or _sha256_file(target.abs_path) != sha:
        return ApplyResult(
            "ROLLBACK_FAILED",
            target.rel_path,
            None,
            False,
            "fichier modifie avant rollback ; suppression refusee",
            absence_evidence.evidence_sha256,
        )
    try:
        target.abs_path.unlink()
    except OSError as exc:
        return ApplyResult(
            "ROLLBACK_FAILED",
            target.rel_path,
            None,
            False,
            f"rollback echoue : {exc}",
            absence_evidence.evidence_sha256,
        )
    if target.abs_path.exists():
        return ApplyResult(
            "ROLLBACK_FAILED",
            target.rel_path,
            None,
            False,
            "rollback : le fichier existe encore",
            absence_evidence.evidence_sha256,
        )
    rollback_proof = build_rollback_absence_proof(target, absence_evidence)
    return ApplyResult(
        "ROLLED_BACK",
        target.rel_path,
        None,
        True,
        msg,
        absence_evidence.evidence_sha256,
        rollback_proof.proof_sha256,
        rollback_proof,
    )
