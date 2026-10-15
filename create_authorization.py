import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone

class CreateAuthorizationError(ValueError):
    pass

@dataclass(frozen=True)
class CreateApproval:
    approved: bool
    approver: str
    approved_at: str
    authority_level: str
    target_path: str
    expected_content_sha256: str
    expected_absence_evidence_sha256: str

def compute_content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def build_create_approval(approver: str, target_path: str, content: str,
                          absence_evidence_sha256: str,
                          authority_level: str = "L3_PROPOSE"):
    if not approver or not approver.strip():
        raise CreateAuthorizationError("approbateur vide")
    if not target_path or not target_path.strip():
        raise CreateAuthorizationError("target_path vide")
    if content is None:
        raise CreateAuthorizationError("contenu manquant")
    if not absence_evidence_sha256 or not absence_evidence_sha256.strip():
        raise CreateAuthorizationError("evidence d'absence manquante")
    return CreateApproval(
        approved=True,
        approver=approver.strip(),
        approved_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        authority_level=authority_level,
        target_path=target_path.strip(),
        expected_content_sha256=compute_content_sha256(content),
        expected_absence_evidence_sha256=absence_evidence_sha256.strip(),
    )

def verify_create_approval(approval: CreateApproval, target_path: str, content: str,
                           absence_evidence_sha256: str):
    if approval is None:
        raise CreateAuthorizationError("approbation absente")
    if approval.approved is not True:
        raise CreateAuthorizationError("approbation refusee")
    if not approval.approver.strip():
        raise CreateAuthorizationError("approbateur vide")
    if approval.target_path != target_path:
        raise CreateAuthorizationError(f"chemin different : {approval.target_path} != {target_path}")
    actual_sha = compute_content_sha256(content)
    if actual_sha != approval.expected_content_sha256:
        raise CreateAuthorizationError(f"SHA different")
    if not hmac.compare_digest(
        approval.expected_absence_evidence_sha256,
        absence_evidence_sha256,
    ):
        raise CreateAuthorizationError("evidence d'absence differente")
