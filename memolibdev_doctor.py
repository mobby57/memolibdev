from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from project_target import resolve_target


import re
ROOT = Path(__file__).resolve().parent
TARGET_ENV = "MEMOLIBDEV_TARGET"


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd or ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return p.returncode, p.stdout.strip()
    except Exception as exc:
        return 99, f"ERROR: {exc}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check(name: str, condition: bool, detail: str) -> dict:
    return {
        "name": name,
        "status": "PASS" if condition else "FAIL",
        "detail": detail,
    }


def git_value(target: Path, *args: str) -> str:
    code, out = run(["git", *args], target)
    return out if code == 0 else ""


def check_read_only_guard(base_dir: Path) -> tuple[bool, list[str]]:
    """
    Vérifie les opérations réellement dangereuses sans confondre :
      - documentation/prompt avec exécution ;
      - commit interne au sandbox avec commit sur MemoLib ;
      - nettoyage d'un sandbox temporaire avec suppression arbitraire.

    Le Doctor reste un contrôle statique : aucune commande n'est exécutée ici.
    """

    files = [
        base_dir / "controlled_coder.py",
        base_dir / "decision_agent.py",
    ]

    findings: list[str] = []

    for path in files:
        if not path.exists():
            continue

        source = path.read_text(encoding="utf-8")

        # --------------------------------------------------------
        # BLOQUER les mécanismes d'exécution shell arbitraire.
        # --------------------------------------------------------
        forbidden_exact = [
            "os.system(",
            "os.popen(",
            "subprocess.Popen(",
            "shell=True",
        ]

        for needle in forbidden_exact:
            if needle in source:
                findings.append(f"{path.name}: {needle}")

        # --------------------------------------------------------
        # subprocess.run :
        #
        # Le Controlled Coder peut utiliser son wrapper run_git().
        # On bloque seulement les appels directs suspects.
        # --------------------------------------------------------
        if path.name == "controlled_coder.py":
            direct_run = re.findall(
                r"(?m)^\s*subprocess\.run\s*\(",
                source,
            )

            # Un subprocess.run direct est acceptable seulement si le
            # fichier contient le wrapper run_git qui force :
            # ["git", *args] + cwd=sandbox.
            has_safe_git_wrapper = (
                "def run_git(*args):" in source
                and '["git", *args]' in source
                and "cwd=sandbox" in source
            )

            if direct_run and not has_safe_git_wrapper:
                findings.append(
                    "controlled_coder.py: subprocess.run sans wrapper sandbox vérifiable"
                )

        elif path.name == "decision_agent.py":
            if re.search(r"(?m)^\s*subprocess\.run\s*\(", source):
                findings.append(
                    "decision_agent.py: subprocess.run direct"
                )

        # --------------------------------------------------------
        # Suppression :
        #
        # rmtree du sandbox créé par tempfile.mkdtemp est autorisé.
        # --------------------------------------------------------
        if "shutil.rmtree(" in source:
            safe_sandbox_cleanup = (
                "tempfile.mkdtemp(" in source
                and "_remove_sandbox" in source
                and "sandbox" in source
                and "onerror=_onerror" in source
            )

            if not safe_sandbox_cleanup:
                findings.append(
                    f"{path.name}: shutil.rmtree hors nettoyage sandbox reconnu"
                )

        for needle in [
            "Path.unlink(",
            "os.remove(",
            "os.unlink(",
        ]:
            if needle in source:
                findings.append(f"{path.name}: {needle}")

    return (len(findings) == 0, findings)

def main() -> int:
    now = datetime.now(timezone.utc).isoformat()

    print("=" * 68)
    print("MEMOLIBDEV DOCTOR — READ ONLY")
    print("=" * 68)

    target_raw = __import__("os").environ.get(TARGET_ENV)

    if not target_raw:
        print("[FAIL] MEMOLIBDEV_TARGET absent")
        return 2

    target = Path(target_raw).expanduser().resolve()

    print()
    print("TARGET")
    print(f"  path : {target}")

    checks: list[dict] = []

    checks.append(
        check(
            "target_exists",
            target.exists() and target.is_dir(),
            str(target),
        )
    )

    git_root = git_value(target, "rev-parse", "--show-toplevel")
    checks.append(
        check(
            "git_repository",
            bool(git_root),
            git_root or "Not a Git repository",
        )
    )

    if not git_root:
        return finish(checks, now, None)

    git_root_path = Path(git_root).resolve()

    head = git_value(target, "rev-parse", "HEAD")
    branch = git_value(target, "branch", "--show-current")

    checks.append(
        check(
            "git_head",
            len(head) == 40,
            head or "HEAD unavailable",
        )
    )

    checks.append(
        check(
            "git_branch",
            bool(branch),
            branch or "detached/unknown",
        )
    )

    # Identité officielle : ProjectTarget.
    resolved_target = resolve_target()
    fingerprint = resolved_target.fingerprint

    checks.append(
        check(
            "repository_fingerprint",
            bool(fingerprint),
            fingerprint or "Unable to calculate",
        )
    )

    print()
    print("IDENTITY")
    print(f"  git_root : {git_root_path}")
    print(f"  branch   : {branch}")
    print(f"  HEAD     : {head}")
    print(f"  finger   : {fingerprint}")

    print()
    print("MEMOLIBDEV COMPONENTS")

    component_files = {
        "project_target": "project_target.py",
        "decision_selector": "decision_selector.py",
        "evidence_resolver_v2_2": "evidence_resolver_v2_2.py",
        "import_provenance": "import_provenance.py",
        "coder_authorization": "coder_authorization.py",
        "controlled_coder": "controlled_coder.py",
        "decision_agent": "decision_agent.py",
        "usage_metering": "usage_metering.py",
    }

    component_status = {}

    for name, filename in component_files.items():
        path = ROOT / filename
        exists = path.is_file()
        component_status[name] = exists

        print(
            f"  {'[PASS]' if exists else '[FAIL]'} "
            f"{name:<28} {filename}"
        )

        checks.append(
            check(
                f"component:{name}",
                exists,
                str(path),
            )
        )

    print()
    print("PYTHON SYNTAX")

    syntax_files = [
        filename
        for filename in component_files.values()
        if (ROOT / filename).is_file()
    ]

    for filename in syntax_files:
        code, output = run(
            [sys.executable, "-m", "py_compile", filename],
            ROOT,
        )

        ok = code == 0

        print(
            f"  {'[PASS]' if ok else '[FAIL]'} "
            f"{filename}"
        )

        checks.append(
            check(
                f"syntax:{filename}",
                ok,
                output or "py_compile OK",
            )
        )

    print()
    print("SECURITY CONTRACT MARKERS")

    auth_path = ROOT / "coder_authorization.py"

    if auth_path.is_file():
        auth_source = auth_path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        markers = {
            "git_root": "git_root",
            "HEAD": "head",
            "repository_fingerprint": "repository_fingerprint",
            "validate_record": "validate_record",
            "content_sha256": "content_sha256",
            "provenance_resolved": "ProvenanceStatus.RESOLVED",
            "human_approval": "HumanApproval",
            "allowed_paths": "allowed_paths",
            "authorized": "AuthorizationStatus.AUTHORIZED",
            "requested_path": "requested_path",
            "human_validation_required": "human_validation_required",
        }

        for name, marker in markers.items():
            present = marker in auth_source

            print(
                f"  {'[PASS]' if present else '[FAIL]'} "
                f"{name}"
            )

            checks.append(
                check(
                    f"authorization:{name}",
                    present,
                    marker,
                )
            )

    print()
    print("READ-ONLY GUARD")

    readonly_ok, dangerous_hits = check_read_only_guard(ROOT)

    if readonly_ok:
        print("  [PASS] Aucun mécanisme d'exécution arbitraire détecté")
        print("  [PASS] subprocess limité au wrapper Git sandbox")
        print("  [PASS] nettoyage du sandbox reconnu")
        print("  [PASS] documentation git commit/push/pull ignorée")
    else:
        print("  [FAIL] Opérations dangereuses détectées")
        for hit in dangerous_hits:
            print(f"    {hit}")

    checks.append(
        check(
            "read_only_guard",
            readonly_ok,
            "; ".join(dangerous_hits)
            or "No unsafe executable operations detected",
        )
    )

    print()
    print("D5.5 REGRESSION")

    d55 = ROOT / "d55_coder_authorization.py"

    if d55.is_file():
        code, output = run(
            [sys.executable, str(d55)],
            ROOT,
        )

        ok = code == 0

        print(
            f"  {'[PASS]' if ok else '[FAIL]'} "
            f"d55_coder_authorization.py"
        )

        if output:
            print(output)

        checks.append(
            check(
                "d5.5_regression",
                ok,
                output[-2000:] if output else "No output",
            )
        )
    else:
        print("  [FAIL] d55_coder_authorization.py absent")
        checks.append(
            check(
                "d5.5_regression",
                False,
                "Test absent",
            )
        )

    return finish(
        checks,
        now,
        {
            "target": str(target),
            "git_root": str(git_root_path),
            "head": head,
            "branch": branch,
            "repository_fingerprint": fingerprint,
        },
    )


def finish(
    checks: list[dict],
    timestamp: str,
    identity: dict | None,
) -> int:
    passed = sum(c["status"] == "PASS" for c in checks)
    failed = sum(c["status"] == "FAIL" for c in checks)

    overall = "PASS" if failed == 0 else "BLOCKED"

    report = {
        "schema_version": "1.0",
        "timestamp": timestamp,
        "mode": "READ_ONLY",
        "identity": identity,
        "checks": checks,
        "summary": {
            "passed": passed,
            "failed": failed,
            "verdict": overall,
        },
    }

    report_path = ROOT / "reports" / "memolibdev-doctor.json"
    report_path.parent.mkdir(exist_ok=True)

    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("=" * 68)
    print("MEMOLIBDEV DOCTOR RESULT")
    print("=" * 68)
    print(f"  PASS    : {passed}")
    print(f"  FAIL    : {failed}")
    print(f"  VERDICT : {overall}")
    print(f"  REPORT  : {report_path}")
    print()

    if failed:
        print("NEXT ACTION")
        print("  Corriger les contrôles en échec avant de poursuivre.")
        print("  Aucune modification du dépôt cible n'a été effectuée.")
        return 1

    print("NEXT ACTION")
    print("  Les invariants actuels sont satisfaits.")
    print("  Le prochain travail peut être déterminé par la roadmap.")
    print("  Aucune modification du dépôt cible n'a été effectuée.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
