from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from coder_authorization import (
    ActionDossier,
    AuthorityLevel,
    HumanApproval,
    AuthorizationStatus,
    authorize,
    validate_authorization,
)
from evidence_resolver_v2_2 import (
    EvidenceRecord,
    EvidenceResult,
    EvidenceStatus,
    content_sha256,
)
from import_provenance import (
    ImportReference,
    ProvenanceResult,
    ProvenanceStatus,
)
from project_target import resolve_target


def fail(name: str, message: str) -> None:
    print(f"[FAIL] {name} :: {message}")
    raise SystemExit(1)


def expect_rejected(name: str, authorization) -> None:
    if authorization.status != AuthorizationStatus.REJECTED.value:
        fail(
            name,
            f"expected REJECTED, got {authorization.status}",
        )
    print(f"[PASS] {name}")


def expect_authorized(name: str, authorization) -> None:
    if authorization.status != AuthorizationStatus.AUTHORIZED.value:
        fail(
            name,
            f"expected AUTHORIZED, got {authorization.status}",
        )
    print(f"[PASS] {name}")


target = resolve_target()

relative_path = "src/lib/auth/nextauth-token.ts"
absolute_path = target.git_root / relative_path

if not absolute_path.is_file():
    fail(
        "fixture",
        f"target file missing: {absolute_path}",
    )

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

accepted_result = EvidenceResult(
    status=EvidenceStatus.ACCEPTED,
    query="getAuthToken",
    path=relative_path,
    line_start=6,
    line_end=8,
    evidence=content,
    score=100,
    reason="Exact symbol declaration",
)

weak_result = replace(
    accepted_result,
    status=EvidenceStatus.WEAK_EVIDENCE,
    score=40,
    reason="Exact identifier reference only",
)

stale_result = replace(
    accepted_result,
    status=EvidenceStatus.STALE_EVIDENCE,
    score=0,
    reason="Evidence is stale",
)

provenance = ProvenanceResult(
    status=ProvenanceStatus.RESOLVED,
    source_path="src/middleware/tenant-isolation.ts",
    symbol="getAuthToken",
    module_specifier="@/lib/auth/nextauth-token",
    resolved_path=relative_path,
    reason="Resolved through path alias @/*",
)

external_provenance = replace(
    provenance,
    status=ProvenanceStatus.EXTERNAL_MODULE,
    resolved_path=None,
    reason="External module",
)

mismatched_provenance = replace(
    provenance,
    resolved_path="src/lib/auth/auth.ts",
)

action = ActionDossier(
    action_id="ACT-5F36-TEST-001",
    action_type="PROPOSE_CODE_PATCH",
    target_path=relative_path,
    risk="MEDIUM",
    reversibility="REVERSIBLE_SANDBOX",
)

approval = HumanApproval(
    approved=True,
    approver="test-human",
    approved_at="2026-10-05T12:00:00+02:00",
    authority_level=AuthorityLevel.L3_PROPOSE.value,
)

scope = [relative_path]


# ------------------------------------------------------------
# 1. VALID CASE
# ------------------------------------------------------------

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=provenance,
    allowed_paths=scope,
    action=action,
    human_approval=approval,
)

expect_authorized("valid complete authorization", authorization)


# ------------------------------------------------------------
# 2. EVIDENCE RESULT ABSENT
# ------------------------------------------------------------

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=None,
    provenance=provenance,
    allowed_paths=scope,
    action=action,
    human_approval=approval,
)

expect_rejected("EvidenceResult absent", authorization)


# ------------------------------------------------------------
# 3. WEAK EVIDENCE
# ------------------------------------------------------------

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=weak_result,
    provenance=provenance,
    allowed_paths=scope,
    action=action,
    human_approval=approval,
)

expect_rejected("WEAK_EVIDENCE rejected", authorization)


# ------------------------------------------------------------
# 4. STALE EVIDENCE
# ------------------------------------------------------------

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=stale_result,
    provenance=provenance,
    allowed_paths=scope,
    action=action,
    human_approval=approval,
)

expect_rejected("STALE_EVIDENCE rejected", authorization)


# ------------------------------------------------------------
# 5. EVIDENCE RESULT WRONG FILE
# ------------------------------------------------------------

wrong_result = replace(
    accepted_result,
    path="src/lib/auth/auth.ts",
)

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=wrong_result,
    provenance=provenance,
    allowed_paths=scope,
    action=action,
    human_approval=approval,
)

expect_rejected("EvidenceResult path mismatch", authorization)


# ------------------------------------------------------------
# 6. PROVENANCE EXTERNAL
# ------------------------------------------------------------

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=external_provenance,
    allowed_paths=scope,
    action=action,
    human_approval=approval,
)

expect_rejected("external provenance rejected", authorization)


# ------------------------------------------------------------
# 7. PROVENANCE PATH MISMATCH
# ------------------------------------------------------------

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=mismatched_provenance,
    allowed_paths=scope,
    action=action,
    human_approval=approval,
)

expect_rejected("provenance path mismatch", authorization)


# ------------------------------------------------------------
# 8. HUMAN APPROVAL ABSENT
# ------------------------------------------------------------

no_approval = replace(
    approval,
    approved=False,
)

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=provenance,
    allowed_paths=scope,
    action=action,
    human_approval=no_approval,
)

expect_rejected("human approval absent", authorization)


# ------------------------------------------------------------
# 9. APPROVER ABSENT
# ------------------------------------------------------------

missing_approver = replace(
    approval,
    approver="",
)

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=provenance,
    allowed_paths=scope,
    action=action,
    human_approval=missing_approver,
)

expect_rejected("approver absent", authorization)


# ------------------------------------------------------------
# 10. TIMESTAMP ABSENT
# ------------------------------------------------------------

missing_timestamp = replace(
    approval,
    approved_at="",
)

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=provenance,
    allowed_paths=scope,
    action=action,
    human_approval=missing_timestamp,
)

expect_rejected("approval timestamp absent", authorization)


# ------------------------------------------------------------
# 11. INVALID AUTHORITY
# ------------------------------------------------------------

invalid_authority = replace(
    approval,
    authority_level="L99_ROOT",
)

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=provenance,
    allowed_paths=scope,
    action=action,
    human_approval=invalid_authority,
)

expect_rejected("invalid authority level", authorization)


# ------------------------------------------------------------
# 12. L5 EXECUTION AUTHORITY
# ------------------------------------------------------------

l5_approval = replace(
    approval,
    authority_level=AuthorityLevel.L5_EXECUTE_ACTION.value,
)

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=provenance,
    allowed_paths=scope,
    action=action,
    human_approval=l5_approval,
)

expect_rejected("L5 execution authority blocked", authorization)


# ------------------------------------------------------------
# 13. L6 CRITICAL AUTHORITY
# ------------------------------------------------------------

l6_approval = replace(
    approval,
    authority_level=AuthorityLevel.L6_CRITICAL_ACTION.value,
)

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=provenance,
    allowed_paths=scope,
    action=action,
    human_approval=l6_approval,
)

expect_rejected("L6 critical authority blocked", authorization)


# ------------------------------------------------------------
# 14. ACTION PATH MISMATCH
# ------------------------------------------------------------

wrong_action = replace(
    action,
    target_path="src/lib/auth/auth.ts",
)

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=provenance,
    allowed_paths=scope,
    action=wrong_action,
    human_approval=approval,
)

expect_rejected("action path mismatch", authorization)


# ------------------------------------------------------------
# 15. EMPTY ACTION ID
# ------------------------------------------------------------

empty_action_id = replace(
    action,
    action_id="",
)

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=provenance,
    allowed_paths=scope,
    action=empty_action_id,
    human_approval=approval,
)

expect_rejected("empty action id", authorization)


# ------------------------------------------------------------
# 16. OUT OF SCOPE
# ------------------------------------------------------------

authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=provenance,
    allowed_paths=["src/lib/auth/auth.ts"],
    action=action,
    human_approval=approval,
)

expect_rejected("scope expansion blocked", authorization)


# ------------------------------------------------------------
# 17. FORGED HEAD
# ------------------------------------------------------------

forged_target = replace(
    target,
    head_full="0000000000000000000000000000000000000000",
)

authorization = authorize(
    target=forged_target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=provenance,
    allowed_paths=scope,
    action=action,
    human_approval=approval,
)

expect_rejected("forged target HEAD blocked", authorization)


# ------------------------------------------------------------
# 18. AUTHORIZATION REUSE ON OTHER PATH
# ------------------------------------------------------------

valid_authorization = authorize(
    target=target,
    evidence=evidence,
    evidence_result=accepted_result,
    provenance=provenance,
    allowed_paths=scope,
    action=action,
    human_approval=approval,
)

valid, reason = validate_authorization(
    valid_authorization,
    target,
    "src/lib/auth/auth.ts",
    scope,
)

if valid:
    fail(
        "authorization reuse on other path",
        "authorization incorrectly accepted",
    )

print("[PASS] authorization reuse on other path blocked")


# ------------------------------------------------------------
# 19. AUTHORIZATION REUSE WITH EXPANDED SCOPE
# ------------------------------------------------------------

valid, reason = validate_authorization(
    valid_authorization,
    target,
    relative_path,
    scope + ["src/lib/auth/auth.ts"],
)

if not valid:
    fail(
        "valid authorization with larger surrounding scope",
        reason,
    )

print("[PASS] authorization remains bound to exact authorized path")


# ------------------------------------------------------------
# 20. FORGED AUTHORIZATION STATUS
# ------------------------------------------------------------

forged_authorization = replace(
    valid_authorization,
    status=AuthorizationStatus.REJECTED.value,
)

valid, reason = validate_authorization(
    forged_authorization,
    target,
    relative_path,
    scope,
)

if valid:
    fail(
        "forged authorization status",
        "REJECTED authorization was accepted",
    )

print("[PASS] forged authorization status blocked")


print("")
print("============================================================")
print("D5.6 — HUMAN APPROVAL / ACTION DOSSIER ADVERSARIAL")
print("============================================================")
print("PASS : all authorization attacks blocked")
print("MemoLib : NON MODIFIÉ")
print("Git     : NON")
print("Ollama  : NON")
print("============================================================")
