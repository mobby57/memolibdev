from pathlib import Path
from dataclasses import replace

from project_target import resolve_target
from decision_agent import inspect_repository
from decision_selector import select_relevant_files

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
print("5F.3.4.4-D5.4-B — ADVERSARIAL PROVENANCE")
print("=" * 80)


# ============================================================================
# TARGET
# ============================================================================

target = resolve_target()
root = target.git_root

print()
print("TARGET")
print(f"  root   : {root}")
print(f"  HEAD   : {target.head}")
print(f"  finger : {target.fingerprint}")


# ============================================================================
# INVENTORY / SELECTOR
# ============================================================================

inventory = inspect_repository()

selected_result = select_relevant_files(
    inventory,
    "getAuthToken authOptions NextAuth getToken middleware tenant oauth",
)

selected = selected_result["selected"]

selected_paths = [
    str((root / item["path"]).resolve())
    for item in selected
]

store = build_store(
    selected_paths,
    root,
    target,
)

print()
print("INITIAL STORE")
print(f"  selected : {len(selected_paths)}")
print(f"  records  : {len(store)}")


# ============================================================================
# HELPERS
# ============================================================================

passed = 0
failed = 0


def check(label, condition):
    global passed, failed

    if condition:
        print(f"  {label:<54}: PASS")
        passed += 1
    else:
        print(f"  {label:<54}: FAIL")
        failed += 1


def find_record(path, records):
    normalized = path.replace("\\", "/")

    for record in records:
        if record.normalized_path.replace("\\", "/") == normalized:
            return record

    return None


# ============================================================================
# 1 — TEST / REFERENCE PROVENANCE
# ============================================================================

print()
print("1 — TEST / REFERENCE PROVENANCE")

tenant = find_record(
    "src/middleware/tenant-isolation.ts",
    store,
)

check(
    "tenant-isolation record exists",
    tenant is not None,
)

if tenant:
    results = resolve_exact_symbol(
        [tenant],
        "getAuthToken",
        target,
    )

    check(
        "reference-only symbol is not ACCEPTED",
        not any(
            r.status == EvidenceStatus.ACCEPTED
            for r in results
        ),
    )

    check(
        "reference-only symbol is WEAK or NOT_FOUND",
        all(
            r.status in (
                EvidenceStatus.WEAK_EVIDENCE,
                EvidenceStatus.SYMBOL_NOT_FOUND,
            )
            for r in results
        ),
    )


# ============================================================================
# 2 — CONTROLLED EXPANSION FOR RE-EXPORT
# ============================================================================

print()
print("2 — RE-EXPORT PROVENANCE")

reexport_path = root / "src/lib/auth/authOptions.ts"

check(
    "re-export target exists on disk",
    reexport_path.is_file(),
)

if reexport_path.is_file():

    expanded_reexport = build_store(
        [str(reexport_path.resolve())],
        root,
        target,
    )

    print(
        f"  controlled expansion records : "
        f"{len(expanded_reexport)}"
    )

    check(
        "controlled expansion produced record",
        len(expanded_reexport) == 1,
    )

    if expanded_reexport:

        auth_options_reexport = expanded_reexport[0]

        check(
            "expanded record has expected path",
            auth_options_reexport.normalized_path
            == "src/lib/auth/authOptions.ts",
        )

        results = resolve_exact_symbol(
            [auth_options_reexport],
            "authOptions",
            target,
        )

        check(
            "re-export is not ACCEPTED",
            not any(
                r.status == EvidenceStatus.ACCEPTED
                for r in results
            ),
        )


# ============================================================================
# 3 — REAL DECLARATION
# ============================================================================

print()
print("3 — REAL DECLARATION")

auth_route = find_record(
    "src/app/api/auth/[...nextauth]/route.ts",
    store,
)

check(
    "auth route exists",
    auth_route is not None,
)

if auth_route:

    results = resolve_exact_symbol(
        [auth_route],
        "authOptions",
        target,
    )

    accepted = [
        r
        for r in results
        if r.status == EvidenceStatus.ACCEPTED
    ]

    check(
        "real authOptions declaration is ACCEPTED",
        bool(accepted),
    )

    if accepted:
        check(
            "accepted score is 100",
            accepted[0].score == 100,
        )


# ============================================================================
# 4 — HOMONYM CONTROL
# ============================================================================

print()
print("4 — HOMONYM CONTROL")

auth_options_records = [
    record
    for record in store
    if "authOptions" in record.content
]

if reexport_path.is_file():

    expanded_reexport = build_store(
        [str(reexport_path.resolve())],
        root,
        target,
    )

    auth_options_records.extend(
        expanded_reexport
    )

print(
    f"  records containing authOptions : "
    f"{len(auth_options_records)}"
)

results = resolve_exact_symbol(
    auth_options_records,
    "authOptions",
    target,
    max_results=20,
)

accepted = [
    r
    for r in results
    if r.status == EvidenceStatus.ACCEPTED
]

print("  ACCEPTED paths:")

for result in accepted:
    print(f"    - {result.path}")

check(
    "only actual declaration can be ACCEPTED",
    all(
        result.path
        == "src/app/api/auth/[...nextauth]/route.ts"
        for result in accepted
    ),
)


# ============================================================================
# 5 — REAL IMPORT PROVENANCE
# ============================================================================

print()
print("5 — REAL IMPORT PROVENANCE")

reference = ImportReference(
    source_path="src/middleware/tenant-isolation.ts",
    symbol="getAuthToken",
    module_specifier="@/lib/auth/nextauth-token",
)

provenance = resolve_import_reference(
    reference,
    target,
)

print(f"  status   : {provenance.status}")
print(f"  resolved : {provenance.resolved_path}")
print(f"  reason   : {provenance.reason}")

check(
    "real alias resolves",
    provenance.status == ProvenanceStatus.RESOLVED,
)

check(
    "real alias resolves expected file",
    provenance.resolved_path
    == "src/lib/auth/nextauth-token.ts",
)


# ============================================================================
# 6 — EXTERNAL MODULE
# ============================================================================

print()
print("6 — EXTERNAL MODULE")

external = ImportReference(
    source_path="src/lib/auth/nextauth-token.ts",
    symbol="getToken",
    module_specifier="next-auth/jwt",
)

external_result = resolve_import_reference(
    external,
    target,
)

print(f"  status : {external_result.status}")

check(
    "external module remains EXTERNAL_MODULE",
    external_result.status
    == ProvenanceStatus.EXTERNAL_MODULE,
)


# ============================================================================
# 7 — PATH TRAVERSAL
# ============================================================================

print()
print("7 — PATH TRAVERSAL")

traversal = ImportReference(
    source_path="src/middleware/tenant-isolation.ts",
    symbol="evil",
    module_specifier="../../../../outside",
)

traversal_result = resolve_import_reference(
    traversal,
    target,
)

print(f"  status : {traversal_result.status}")

check(
    "import traversal is blocked",
    traversal_result.status
    == ProvenanceStatus.OUTSIDE_REPOSITORY,
)


# ============================================================================
# 8 — NON-EXISTING ALIAS
# ============================================================================

print()
print("8 — NON-EXISTING ALIAS")

fake_alias = ImportReference(
    source_path="src/middleware/tenant-isolation.ts",
    symbol="anything",
    module_specifier="@/this/does/not/exist",
)

fake_result = resolve_import_reference(
    fake_alias,
    target,
)

print(f"  status : {fake_result.status}")

check(
    "fake alias is rejected",
    fake_result.status in (
        ProvenanceStatus.MODULE_NOT_FOUND,
        ProvenanceStatus.INVALID_ALIAS,
    ),
)


# ============================================================================
# 9 — SAME-SIZE CONTENT FALSIFICATION
# ============================================================================

print()
print("9 — SAME-SIZE CONTENT FALSIFICATION")

token_path = root / "src/lib/auth/nextauth-token.ts"

check(
    "real evidence target exists on disk",
    token_path.is_file(),
)

if token_path.is_file():

    expanded_token = build_store(
        [str(token_path.resolve())],
        root,
        target,
    )

    check(
        "controlled expansion produced token record",
        len(expanded_token) == 1,
    )

    if expanded_token:

        real_record = expanded_token[0]

        check(
            "token record has expected path",
            real_record.normalized_path
            == "src/lib/auth/nextauth-token.ts",
        )

        original = real_record.content

        replacement = original.replace(
            "getAuthToken",
            "getAuthTokeX",
            1,
        )

        if len(replacement) != len(original):
            replacement = (
                original[:-1]
                + (
                    "X"
                    if original[-1] != "X"
                    else "Y"
                )
            )

        check(
            "content size remains identical",
            len(replacement) == len(original),
        )

        falsified = replace(
            real_record,
            content=replacement,
        )

        valid, reason = validate_record(
            falsified,
            target,
        )

        print(f"  validation : {valid}")
        print(f"  reason     : {reason}")

        check(
            "same-size content falsification blocked",
            not valid,
        )


# ============================================================================
# 10 — TARGET IDENTITY BINDING
# ============================================================================

print()
print("10 — TARGET IDENTITY BINDING")

if token_path.is_file():

    expanded_token = build_store(
        [str(token_path.resolve())],
        root,
        target,
    )

    if expanded_token:

        real_record = expanded_token[0]

        wrong_identity = replace(
            real_record,
            git_root=str(root.parent),
        )

        valid, reason = validate_record(
            wrong_identity,
            target,
        )

        print(f"  validation : {valid}")
        print(f"  reason     : {reason}")

        check(
            "wrong git root blocked",
            not valid,
        )


# ============================================================================
# VERDICT
# ============================================================================

print()
print("=" * 80)
print("5F.3.4.4-D5.4-B — VERDICT")
print("=" * 80)

print(f"PASS : {passed}")
print(f"FAIL : {failed}")

if failed == 0:
    print()
    print("[PASS] D5.4-B adversarial provenance validated.")
else:
    print()
    print("[FAIL] D5.4-B requires investigation.")

print()
print("SAFETY")
print("MemoLib : NON MODIFIÉ")
print("Ollama  : NON")
print("Git     : NON")

raise SystemExit(0 if failed == 0 else 1)
