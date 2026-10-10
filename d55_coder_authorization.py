from __future__ import annotations

import hashlib
from pathlib import Path
from dataclasses import replace

from coder_authorization import (
    ActionDossier,
    AuthorityLevel,
    AuthorizationStatus,
    HumanApproval,
    authorize,
    validate_authorization,
)
from evidence_resolver_v2_2 import (
    EvidenceRecord,
    EvidenceResult,
    EvidenceStatus,
)
from import_provenance import (
    ProvenanceResult,
    ProvenanceStatus,
)
from project_target import resolve_target


ROOT = Path(__file__).resolve().parent
TARGET = resolve_target()


def sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def evidence(path: str, content: str) -> EvidenceRecord:
    return EvidenceRecord(
        path=path,
        normalized_path=path.replace("\\", "/"),
        git_root=str(TARGET.git_root),
        head=TARGET.head_full,
        repository_fingerprint=TARGET.fingerprint,
        content_sha256=sha(content),
        size=len(content.encode("utf-8")),
        content=content,
    )


def provenance(path: str) -> ProvenanceResult:
    return ProvenanceResult(
        status=ProvenanceStatus.RESOLVED,
        source_path=path,
        symbol="getAuthToken",
        module_specifier="@/lib/auth/nextauth-token",
        resolved_path=path,
        reason="test provenance",
    )


def assert_rejected(name: str, result) -> None:
    assert result.status == AuthorizationStatus.REJECTED.value, (
        f"{name}: expected REJECTED, got {result.status}"
    )
    print(f"[PASS] {name}")


def main() -> int:
    test_path = "src/lib/auth/nextauth-token.ts"
    real_file = TARGET.git_root / Path(test_path)

    assert real_file.exists(), (
        f"Test file missing: {real_file}"
    )

    test_content = real_file.read_text(
        encoding="utf-8",
        errors="replace",
    )

    allowed = [test_path]

    ev = evidence(test_path, test_content)
    prov = provenance(test_path)

    accepted_result = EvidenceResult(
        status=EvidenceStatus.ACCEPTED,
        query="getAuthToken",
        path=test_path,
        line_start=1,
        line_end=max(1, len(test_content.splitlines())),
        evidence=test_content,
        score=100,
        reason="Exact symbol declaration",
    )

    action = ActionDossier(
        action_id="ACT-D55-TEST-001",
        action_type="PROPOSE_CODE_PATCH",
        target_path=test_path,
        risk="MEDIUM",
        reversibility="REVERSIBLE_SANDBOX",
    )

    approval = HumanApproval(
        approved=True,
        approver="test-human",
        approved_at="2026-10-05T12:00:00+02:00",
        authority_level=AuthorityLevel.L3_PROPOSE.value,
    )

    no_approval = replace(
        approval,
        approved=False,
    )

    # Baseline : sans validation humaine -> reject.
    result = authorize(
        target=TARGET,
        evidence=ev,
        evidence_result=accepted_result,
        provenance=prov,
        allowed_paths=allowed,
        action=action,
        human_approval=no_approval,
    )
    assert_rejected("approval absent", result)

    # Baseline autorisé.
    result = authorize(
        target=TARGET,
        evidence=ev,
        evidence_result=accepted_result,
        provenance=prov,
        allowed_paths=allowed,
        action=action,
        human_approval=approval,
    )
    assert result.status == AuthorizationStatus.AUTHORIZED.value
    print("[PASS] valid authorization")

    # Scope élargi.
    result = authorize(
        target=TARGET,
        evidence=ev,
        evidence_result=accepted_result,
        provenance=prov,
        allowed_paths=[],
        action=action,
        human_approval=approval,
    )
    assert_rejected("path outside deterministic scope", result)

    # Provenance externe.
    external = replace(
        prov,
        status=ProvenanceStatus.EXTERNAL_MODULE,
        resolved_path=None,
    )
    result = authorize(
        target=TARGET,
        evidence=ev,
        evidence_result=accepted_result,
        provenance=external,
        allowed_paths=allowed,
        action=action,
        human_approval=approval,
    )
    assert_rejected("external provenance", result)

    # Provenance vers un autre fichier.
    wrong_prov = replace(
        prov,
        resolved_path="src/app/api/auth/[...nextauth]/route.ts",
    )
    result = authorize(
        target=TARGET,
        evidence=ev,
        evidence_result=accepted_result,
        provenance=wrong_prov,
        allowed_paths=allowed,
        action=action,
        human_approval=approval,
    )
    assert_rejected("provenance/path mismatch", result)

    # HEAD falsifié.
    bad_head = replace(
        ev,
        head="0" * 40,
    )
    result = authorize(
        target=TARGET,
        evidence=bad_head,
        evidence_result=accepted_result,
        provenance=prov,
        allowed_paths=allowed,
        action=action,
        human_approval=approval,
    )
    assert_rejected("falsified HEAD", result)

    # Fingerprint falsifié.
    bad_fingerprint = replace(
        ev,
        repository_fingerprint="deadbeefdeadbeef",
    )
    result = authorize(
        target=TARGET,
        evidence=bad_fingerprint,
        evidence_result=accepted_result,
        provenance=prov,
        allowed_paths=allowed,
        action=action,
        human_approval=approval,
    )
    assert_rejected("falsified repository fingerprint", result)

    # Git root falsifié.
    bad_root = replace(
        ev,
        git_root=str(TARGET.git_root.parent),
    )
    result = authorize(
        target=TARGET,
        evidence=bad_root,
        evidence_result=accepted_result,
        provenance=prov,
        allowed_paths=allowed,
        action=action,
        human_approval=approval,
    )
    assert_rejected("falsified git root", result)

    # SHA falsifié.
    bad_sha = replace(
        ev,
        content_sha256=sha("different content"),
    )
    result = authorize(
        target=TARGET,
        evidence=bad_sha,
        evidence_result=accepted_result,
        provenance=prov,
        allowed_paths=allowed,
        action=action,
        human_approval=approval,
    )
    assert_rejected("falsified evidence SHA", result)

    # Même taille, contenu différent.
    same_size_content = (
        test_content[:-1]
        + ("X" if test_content[-1] != "X" else "Y")
    )

    assert len(same_size_content.encode("utf-8")) == len(
        test_content.encode("utf-8")
    )

    assert same_size_content != test_content

    same_size = replace(
        ev,
        content=same_size_content,
    )

    result = authorize(
        target=TARGET,
        evidence=same_size,
        evidence_result=accepted_result,
        provenance=prov,
        allowed_paths=allowed,
        action=action,
        human_approval=approval,
    )
    assert_rejected("same-size content tampering", result)

    # Autorisation existante réutilisée sur un autre chemin.
    authorization = authorize(
        target=TARGET,
        evidence=ev,
        evidence_result=accepted_result,
        provenance=prov,
        allowed_paths=allowed,
        action=action,
        human_approval=approval,
    )

    valid, _ = validate_authorization(
        authorization,
        TARGET,
        "src/other.ts",
        allowed,
    )
    assert not valid
    print("[PASS] authorization path reuse blocked")

    # Autorisation existante réutilisée hors scope.
    valid, _ = validate_authorization(
        authorization,
        TARGET,
        test_path,
        [],
    )
    assert not valid
    print("[PASS] authorization scope expansion blocked")

    # Approval falsifiée dans l'objet.
    fake = replace(
        authorization,
        human_validation_required=False,
    )

    valid, _ = validate_authorization(
        fake,
        TARGET,
        test_path,
        allowed,
    )
    assert not valid
    print("[PASS] forged approval invariant blocked")

    print()
    print("============================================================")
    print("D5.5 — CODER AUTHORIZATION ADVERSARIAL")
    print("============================================================")
    print("PASS : all authorization attacks blocked")
    print("MemoLib : NON MODIFIÉ")
    print("Git     : NON")
    print("Ollama  : NON")
    print("============================================================")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())