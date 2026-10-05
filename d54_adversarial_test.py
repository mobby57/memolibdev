from pathlib import Path
from dataclasses import replace

from project_target import resolve_target
from evidence_resolver_v2_2 import (
    build_store,
    validate_record,
    resolve_exact_symbol,
    EvidenceStatus,
)
from import_provenance import (
    ImportReference,
    ProvenanceStatus,
    resolve_import_reference,
)


print("=" * 80)
print("5F.3.4.4-D5.4 — ADVERSARIAL EVIDENCE / PROVENANCE")
print("=" * 80)

target = resolve_target()
root = target.git_root.resolve()

print()
print("TARGET")
print("  root   :", root)
print("  HEAD   :", target.head_full)
print("  finger :", target.fingerprint)


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def require_blocked(label, condition):
    print(f"  {label:<38}: ", end="")
    assert condition, f"SECURITY FAILURE: {label}"
    print("BLOCKED / PASS")


# ------------------------------------------------------------------
# 1. REAL FILE
# ------------------------------------------------------------------

real_file = (
    root / "src/lib/auth/nextauth-token.ts"
).resolve()

assert real_file.is_file()

selected = [str(real_file)]

store = build_store(
    selected,
    root,
    target,
)

assert len(store) == 1

record = store[0]

print()
print("BASELINE")
print("  record :", record.normalized_path)

valid, reason = validate_record(
    record,
    target,
)

assert valid

print("  integrity : PASS")


# ------------------------------------------------------------------
# 2. SHA FALSIFICATION
# ------------------------------------------------------------------

fake_sha = replace(
    record,
    content_sha256="0" * 64,
)

valid, reason = validate_record(
    fake_sha,
    target,
)

require_blocked(
    "Falsified content SHA",
    not valid,
)


# ------------------------------------------------------------------
# 3. HEAD FALSIFICATION
# ------------------------------------------------------------------

fake_head = replace(
    record,
    head="0" * 40,
)

valid, reason = validate_record(
    fake_head,
    target,
)

require_blocked(
    "Falsified HEAD",
    not valid,
)


# ------------------------------------------------------------------
# 4. FINGERPRINT FALSIFICATION
# ------------------------------------------------------------------

fake_fingerprint = replace(
    record,
    repository_fingerprint="deadbeefdeadbeef",
)

valid, reason = validate_record(
    fake_fingerprint,
    target,
)

require_blocked(
    "Falsified repository fingerprint",
    not valid,
)


# ------------------------------------------------------------------
# 5. WRONG REPOSITORY
# ------------------------------------------------------------------

fake_root = replace(
    record,
    git_root=str(root.parent),
)

valid, reason = validate_record(
    fake_root,
    target,
)

require_blocked(
    "Wrong repository identity",
    not valid,
)


# ------------------------------------------------------------------
# 6. PATH TRAVERSAL IN EVIDENCE
# ------------------------------------------------------------------

fake_path = replace(
    record,
    path="../../outside.ts",
    normalized_path="../../outside.ts",
)

valid, reason = validate_record(
    fake_path,
    target,
)

require_blocked(
    "Evidence path traversal",
    not valid,
)


# ------------------------------------------------------------------
# 7. EXTERNAL MODULE
# ------------------------------------------------------------------

external = ImportReference(
    source_path=(
        "src/lib/auth/nextauth-token.ts"
    ),
    symbol="getToken",
    module_specifier="next-auth/jwt",
)

external_result = resolve_import_reference(
    external,
    target,
)

require_blocked(
    "External module treated as local",
    external_result.status
    == ProvenanceStatus.EXTERNAL_MODULE,
)


# ------------------------------------------------------------------
# 8. IMPORT PATH TRAVERSAL
# ------------------------------------------------------------------

malicious = ImportReference(
    source_path=(
        "src/middleware/tenant-isolation.ts"
    ),
    symbol="getAuthToken",
    module_specifier="../../../../outside",
)

malicious_result = resolve_import_reference(
    malicious,
    target,
)

require_blocked(
    "Import path traversal",
    malicious_result.status
    == ProvenanceStatus.OUTSIDE_REPOSITORY,
)


# ------------------------------------------------------------------
# 9. NON-EXISTING ALIAS TARGET
# ------------------------------------------------------------------

fake_alias = ImportReference(
    source_path=(
        "src/middleware/tenant-isolation.ts"
    ),
    symbol="getAuthToken",
    module_specifier="@/this/does/not/exist",
)

fake_alias_result = resolve_import_reference(
    fake_alias,
    target,
)

require_blocked(
    "Falsified alias target",
    fake_alias_result.status
    in (
        ProvenanceStatus.MODULE_NOT_FOUND,
        ProvenanceStatus.INVALID_IMPORT,
    ),
)


# ------------------------------------------------------------------
# 10. REAL SYMBOL MUST STILL WORK
# ------------------------------------------------------------------

results = resolve_exact_symbol(
    store,
    "getAuthToken",
    target,
)

accepted = [
    result
    for result in results
    if result.status == EvidenceStatus.ACCEPTED
]

print()
print("REAL DECLARATION")

assert accepted

print("  status :", accepted[0].status)
print("  score  :", accepted[0].score)
print("  path   :", accepted[0].path)

assert accepted[0].score == 100

print("  result : PASS")


# ------------------------------------------------------------------
# FINAL
# ------------------------------------------------------------------

print()
print("=" * 80)
print("5F.3.4.4-D5.4 — VERDICT")
print("=" * 80)

print("SHA FALSIFICATION        : BLOCKED")
print("HEAD FALSIFICATION       : BLOCKED")
print("FINGERPRINT FALSIFICATION: BLOCKED")
print("WRONG REPOSITORY         : BLOCKED")
print("PATH TRAVERSAL           : BLOCKED")
print("EXTERNAL MODULE          : BLOCKED")
print("ALIAS FALSIFICATION      : BLOCKED")
print("REAL DECLARATION         : ACCEPTED")
print()
print("[PASS] D5.4 adversarial baseline validated.")

print()
print("SAFETY")
print("MemoLib : NON MODIFIÉ")
print("Ollama  : NON")
print("Git     : NON")
