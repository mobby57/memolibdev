from dataclasses import replace

from project_target import resolve_target
from evidence_resolver_v2_2 import (
    build_store,
    validate_record,
    content_sha256,
    resolve_exact_symbol,
)

target = resolve_target()
root = target.git_root

path = root / "src/lib/auth/nextauth-token.ts"

store = build_store(
    [str(path.resolve())],
    root,
    target,
)

record = store[0]

print("=" * 80)
print("D5.4-C — EVIDENCE RECORD CONTENT INTEGRITY")
print("=" * 80)

print()
print("BASELINE")

print("  path        :", record.normalized_path)
print("  stored SHA  :", record.content_sha256)
print("  actual SHA  :", content_sha256(record.content))
print("  SHA MATCH   :", content_sha256(record.content) == record.content_sha256)

valid, reason = validate_record(record, target)

print("  validation  :", valid)
print("  reason      :", reason)

print()
print("TAMPER CONTENT")

tampered_content = record.content.replace(
    "getAuthToken",
    "getAuthTokeX",
    1,
)

print("  original size:", len(record.content))
print("  tampered size:", len(tampered_content))
print("  same size    :", len(record.content) == len(tampered_content))

tampered = replace(
    record,
    content=tampered_content,
)

print()
print("  stored SHA   :", tampered.content_sha256)
print("  content SHA  :", content_sha256(tampered.content))
print(
    "  SHA MATCH    :",
    content_sha256(tampered.content) == tampered.content_sha256,
)

valid, reason = validate_record(tampered, target)

print()
print("  validate_record :", valid)
print("  reason          :", reason)

print()
print("RESOLUTION AGAINST TAMPERED RECORD")

results = resolve_exact_symbol(
    [tampered],
    "getAuthToken",
    target,
)

for result in results:
    print("  status :", result.status)
    print("  score  :", result.score)
    print("  path   :", result.path)
    print("  reason :", result.reason)

print()
print("=" * 80)
print("SAFETY")
print("MemoLib : NON MODIFIÉ")
print("Ollama  : NON")
print("Git     : NON")
print("=" * 80)
