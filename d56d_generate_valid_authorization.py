from __future__ import annotations

import json
from pathlib import Path

from coder_authorization import (
    ActionDossier,
    AuthorityLevel,
    HumanApproval,
    authorize,
    authorization_to_dict,
)
from evidence_resolver_v2_2 import (
    EvidenceRecord,
    EvidenceResult,
    EvidenceStatus,
    content_sha256,
)
from import_provenance import (
    ProvenanceResult,
    ProvenanceStatus,
)
from project_target import resolve_target


target = resolve_target()

relative_path = "src/lib/auth/nextauth-token.ts"
absolute_path = target.git_root / relative_path

content = absolute_path.read_text(encoding="utf-8")
sha = content_sha256(content)

evidence = EvidenceRecord(
    path=relative_path,
    normalized_path=relative_path,
    git_root=str(target.git_root),
    head=target.head_full,
    repository_fingerprint=target.fingerprint,
    content_sha256=sha,
    size=len(content.encode("utf-8")),
    content=content,
)

evidence_result = EvidenceResult(
    status=EvidenceStatus.ACCEPTED,
    query="getAuthToken",
    path=relative_path,
    line_start=6,
    line_end=8,
    evidence=content,
    score=100,
    reason="Exact symbol declaration",
)

provenance = ProvenanceResult(
    status=ProvenanceStatus.RESOLVED,
    source_path="src/middleware/tenant-isolation.ts",
    symbol="getAuthToken",
    module_specifier="@/lib/auth/nextauth-token",
    resolved_path=relative_path,
    reason="Resolved through path alias @/*",
)

action = ActionDossier(
    action_id="ACT-5F36-D-001",
    action_type="PROPOSE_CODE_PATCH",
    target_path=relative_path,
    risk="MEDIUM",
    reversibility="REVERSIBLE_SANDBOX",
)

approval = HumanApproval(
    approved=True,
    approver="human-test",
    approved_at="2026-10-05T14:00:00+02:00",
    authority_level=AuthorityLevel.L3_PROPOSE.value,
)

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=evidence_result,
    provenance=provenance,
    allowed_paths=[relative_path],
    action=action,
    human_approval=approval,
)

if authorization.status != "AUTHORIZED":
    raise SystemExit(
        "[FAIL] Authorization should be AUTHORIZED: "
        + authorization.reason
    )

print("[PASS] CoderAuthorization = AUTHORIZED")

data = authorization_to_dict(authorization)

output = Path("reports/coder-authorization.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    json.dumps(data, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("[PASS] Certificat écrit :", output)
print("[PASS] Target :", data["target"]["git_root"])
print("[PASS] HEAD :", data["target"]["head"])
print("[PASS] Fingerprint :", data["target"]["repository_fingerprint"])
print("[PASS] Evidence :", data["evidence_status"])
print("[PASS] Provenance :", data["provenance_status"])
print("[PASS] Action :", data["action"]["action_type"])
print("[PASS] Approver :", data["human_approval"]["approver"])
print("[PASS] Authority :", data["human_approval"]["authority_level"])
print("[PASS] Status :", data["status"])

print("")
print("CERTIFICATE_READY")
