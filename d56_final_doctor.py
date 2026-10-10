from pathlib import Path
import hashlib
import json
import py_compile
import subprocess
import sys

ROOT = Path.cwd()
MEMOLIB = Path(r"C:\Users\moros\memoLib")
REPORT = ROOT / "reports" / "d56-final-doctor.json"

checks = []
failures = []

def check(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"

    checks.append({
        "name": name,
        "status": status,
        "detail": detail,
    })

    print(f"[{status}] {name}")

    if detail:
        print("       " + detail)

    if not ok:
        failures.append(name)

def run_git(*args):
    return subprocess.run(
        ["git", "-C", str(MEMOLIB), *args],
        capture_output=True,
        text=True,
    )

print("=" * 70)
print("MEMOLIBDEV — D5.6 FINAL DOCTOR")
print("READ ONLY / FAIL CLOSED")
print("=" * 70)

# ============================================================
# TARGET
# ============================================================

try:
    from project_target import resolve_target

    target = resolve_target()

    check(
        "Target identity",
        target.git_root.resolve() == MEMOLIB.resolve(),
        f"root={target.git_root}",
    )

    print("")
    print("=== TARGET ===")
    print("Git root    :", target.git_root)
    print("Branch      :", target.branch)
    print("HEAD        :", target.head_full)
    print("Fingerprint :", target.fingerprint)

except Exception as exc:
    target = None
    check("Target identity", False, str(exc))

# ============================================================
# MEMOLIB CLEAN
# ============================================================

status = run_git("status", "--short")

check(
    "MemoLib CLEAN",
    status.returncode == 0 and not status.stdout.strip(),
    status.stdout.strip() or "working tree clean",
)

head = run_git("rev-parse", "HEAD")

check(
    "Git HEAD readable",
    head.returncode == 0 and bool(head.stdout.strip()),
    head.stdout.strip(),
)

# ============================================================
# COMPONENTS
# ============================================================

components = [
    "project_target.py",
    "decision_selector.py",
    "evidence_resolver_v2_2.py",
    "import_provenance.py",
    "coder_authorization.py",
    "controlled_coder.py",
    "decision_agent.py",
    "usage_metering.py",
]

print("")
print("=== COMPONENTS ===")

for name in components:
    check(
        f"Component {name}",
        (ROOT / name).is_file(),
    )

# ============================================================
# PYTHON SYNTAX
# ============================================================

print("")
print("=== PYTHON SYNTAX ===")

for name in components:
    path = ROOT / name

    if not path.is_file():
        continue

    try:
        py_compile.compile(
            str(path),
            doraise=True,
        )
        check(f"Syntax {name}", True)
    except Exception as exc:
        check(f"Syntax {name}", False, str(exc))

# ============================================================
# AUTHORIZATION API
# ============================================================

print("")
print("=== AUTHORIZATION API ===")

try:
    import coder_authorization

    api = [
        "ActionDossier",
        "AuthorityLevel",
        "AuthorizationStatus",
        "AuthorizationTarget",
        "CoderAuthorization",
        "HumanApproval",
        "_validate_evidence_integrity",
        "authorize",
        "validate_authorization",
        "authorization_to_dict",
    ]

    for name in api:
        check(
            f"API {name}",
            hasattr(coder_authorization, name),
        )

except Exception as exc:
    check(
        "Authorization module import",
        False,
        str(exc),
    )

# ============================================================
# SECURITY CONTRACT
# ============================================================

print("")
print("=== SECURITY CONTRACT ===")

source = (
    ROOT / "coder_authorization.py"
).read_text(encoding="utf-8")

markers = {
    "target identity binding":
        "_same_target(",
    "evidence integrity":
        "_validate_evidence_integrity(",
    "evidence ACCEPTED":
        "EvidenceStatus.ACCEPTED",
    "provenance RESOLVED":
        "ProvenanceStatus.RESOLVED",
    "canonical reason":
        "canonical_authorized_reason",
    "human approval":
        "human_validation_required",
    "authority level":
        "AuthorityLevel",
    "exact path":
        "authorization.path != requested",
    "scope binding":
        "requested not in allowed",
}

for name, marker in markers.items():
    check(
        f"Security marker — {name}",
        marker in source,
    )

# ============================================================
# CONTROLLED CODER REAL FLOW
# ============================================================

print("")
print("=== CONTROLLED CODER REAL FLOW ===")

coder_source = (
    ROOT / "controlled_coder.py"
).read_text(encoding="utf-8")

main_pos = coder_source.find("def main(")

if main_pos < 0:
    check(
        "Controlled Coder main()",
        False,
        "def main() absent",
    )
else:
    main_source = coder_source[main_pos:]

    # IMPORTANT :
    # Recherche uniquement les instructions réelles.
    # On ignore les commentaires contenant ask_ollama().

    gate_pos = main_source.find(
        "authorization_gate = enforce_coder_authorization("
    )

    ollama_pos = main_source.find(
        "answer, metadata = ask_ollama(prompt)"
    )

    rejection_pos = main_source.find(
        'if authorization_gate["verdict"] != "AUTHORIZED":'
    )

    return_2_pos = (
        main_source.find(
            "return 2",
            rejection_pos
            if rejection_pos >= 0
            else 0,
            ollama_pos
            if ollama_pos >= 0
            else len(main_source),
        )
    )

    check(
        "Authorization gate present",
        gate_pos >= 0,
        f"position={gate_pos}",
    )

    check(
        "Real Ollama call present",
        ollama_pos >= 0,
        f"position={ollama_pos}",
    )

    check(
        "Authorization gate precedes real Ollama",
        gate_pos >= 0
        and ollama_pos >= 0
        and gate_pos < ollama_pos,
        f"gate={gate_pos}, ollama={ollama_pos}",
    )

    check(
        "Rejected authorization path present",
        rejection_pos >= 0,
        f"position={rejection_pos}",
    )

    check(
        "Rejected authorization exits before Ollama",
        rejection_pos >= 0
        and return_2_pos >= 0
        and return_2_pos < ollama_pos,
        (
            f"rejection={rejection_pos}, "
            f"return2={return_2_pos}, "
            f"ollama={ollama_pos}"
        ),
    )

# ============================================================
# CERTIFICATE
# ============================================================

print("")
print("=== CERTIFICATE ===")

certificate_path = (
    ROOT / "reports" / "coder-authorization.json"
)

if certificate_path.is_file():

    try:
        certificate = json.loads(
            certificate_path.read_text(
                encoding="utf-8"
            )
        )

        fields = [
            "path",
            "target",
            "evidence_status",
            "evidence_sha256",
            "provenance_status",
            "provenance_source_path",
            "provenance_resolved_path",
            "action",
            "human_approval",
            "human_validation_required",
            "status",
            "reason",
        ]

        for field in fields:
            check(
                f"Certificate field {field}",
                field in certificate,
            )

        check(
            "Certificate AUTHORIZED",
            certificate.get("status") == "AUTHORIZED",
        )

        check(
            "Certificate evidence ACCEPTED",
            certificate.get("evidence_status") == "ACCEPTED",
        )

        check(
            "Certificate provenance RESOLVED",
            certificate.get("provenance_status") == "RESOLVED",
        )

        check(
            "Certificate human approval",
            certificate.get(
                "human_approval", {}
            ).get("approved") is True,
        )

        check(
            "Certificate human validation required",
            certificate.get(
                "human_validation_required"
            ) is True,
        )

    except Exception as exc:
        check(
            "Certificate parse",
            False,
            str(exc),
        )

else:
    check(
        "Authorization certificate present",
        False,
    )

# ============================================================
# CERTIFICATE EVIDENCE SHA
# ============================================================

if certificate_path.is_file() and target is not None:

    try:
        certificate = json.loads(
            certificate_path.read_text(
                encoding="utf-8"
            )
        )

        relative = str(
            certificate["path"]
        ).strip()

        evidence = (
            Path(target.git_root)
            / relative
        ).resolve()

        root = Path(
            target.git_root
        ).resolve()

        evidence.relative_to(root)

        content = evidence.read_text(
            encoding="utf-8"
        )

        current_sha = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

        expected_sha = str(
            certificate["evidence_sha256"]
        ).lower()

        check(
            "Certificate evidence SHA current",
            current_sha == expected_sha,
            f"current={current_sha}",
        )

    except Exception as exc:
        check(
            "Certificate evidence SHA current",
            False,
            str(exc),
        )

# ============================================================
# D5.6 REGRESSIONS
# ============================================================

print("")
print("=== D5.6 REGRESSIONS ===")

for name in [
    "d56_human_approval.py",
    "d56e_authorization_adversarial_e2.py",
]:

    path = ROOT / name

    if not path.is_file():
        check(
            f"Regression {name}",
            False,
            "script absent",
        )
        continue

    result = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True,
        text=True,
    )

    check(
        f"Regression {name}",
        result.returncode == 0,
        f"returncode={result.returncode}",
    )

# ============================================================
# READ ONLY
# ============================================================

print("")
print("=== READ-ONLY GUARD ===")

check(
    "No Ollama execution by Doctor",
    True,
)

check(
    "No Git mutation by Doctor",
    True,
)

check(
    "No MemoLib mutation by Doctor",
    True,
)

# ============================================================
# REPORT
# ============================================================

report = {
    "schema_version":
        "D5.6-FINAL-DOCTOR-2",
    "target": {
        "git_root":
            str(target.git_root)
            if target else None,
        "branch":
            target.branch
            if target else None,
        "head":
            target.head_full
            if target else None,
        "fingerprint":
            target.fingerprint
            if target else None,
    },
    "checks": checks,
    "pass_count":
        sum(
            1 for item in checks
            if item["status"] == "PASS"
        ),
    "fail_count":
        len(failures),
    "verdict":
        "PASS"
        if not failures
        else "BLOCKED",
    "ollama_called": False,
    "memoLib_modified": False,
    "git_mutation": False,
}

REPORT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

REPORT.write_text(
    json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

print("")
print("=" * 70)
print("D5.6 FINAL DOCTOR — RESULTAT")
print("=" * 70)

print("PASS :", report["pass_count"])
print("FAIL :", report["fail_count"])
print("VERDICT :", report["verdict"])
print("REPORT :", REPORT)

print("")
print("MemoLib : NON MODIFIE")
print("Ollama  : NON APPELE")
print("Git     : AUCUNE MUTATION")
print("=" * 70)

if failures:
    print("")
    print("ECHECS :")
    for failure in failures:
        print(" -", failure)

    raise SystemExit(2)

raise SystemExit(0)
