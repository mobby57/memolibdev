from pathlib import Path
import argparse
from datetime import datetime
import json
import os
import subprocess
import sys

ROOT = Path(r"C:\Users\moros\Desktop\memolib").resolve()
V3 = Path(r"C:\Users\moros\MemoLibDev\v3").resolve()
REPORTS = V3 / "reports"

REPORTS.mkdir(parents=True, exist_ok=True)

TESTS = [
    {
        "name": "type-check",
        "command": ["npm.cmd", "run", "type-check"],
        "timeout": 300
    },
    {
        "name": "lint",
        "command": ["npm.cmd", "run", "lint"],
        "timeout": 300
    },
    {
        "name": "test",
        "command": ["npm.cmd", "run", "test:ci"],
        "timeout": 600
    }
]


def run_command(command, timeout):
    try:
        env = os.environ.copy()

        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-12000:]
        }

    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": -2,
            "stdout": str(exc.stdout or "")[-12000:],
            "stderr": str(exc.stderr or "")[-12000:] + "\nTIMEOUT"
        }

    except Exception as exc:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc)
        }


def git_status():
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }

    except Exception as exc:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc)
        }


def save_report(report):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = REPORTS / f"post-test-{timestamp}.json"

    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return output


def parse_args():
    parser = argparse.ArgumentParser(
        description="MemoLibDev V3 — tests contrôlés avant ou après application."
    )

    parser.add_argument(
        "--mode",
        choices=["PRE_APPLY", "POST_APPLY"],
        default="POST_APPLY",
        help="Mode d'exécution des tests."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    print("=" * 60)
    print(
        f" MEMOLIBDEV V3.2.2 — TEST {args.mode}"
    )
    print("=" * 60)
    print()
    print("Dépôt :", ROOT)
    print()

    if not ROOT.exists():
        print("REGRESSION — dépôt introuvable")
        sys.exit(2)

    report = {
        "created_at": datetime.now().isoformat(),
        "repository": str(ROOT),
        "repository_modified": False,
        "mode": args.mode,
        "human_validation_required": True,
        "tests": [],
        "checks": {}
    }

    if args.mode == "PRE_APPLY":
        print("[1] État Git avant application")
    else:
        print("[1] État Git après application")

    status = git_status()

    if status["returncode"] != 0:
        report["checks"]["git_status"] = {
            "status": "FAIL",
            "details": status
        }

        print("FAIL — impossible de lire Git")

        report["overall_status"] = "REGRESSION"
        report["next_step"] = "STOP_HUMAN_REVIEW"

        output = save_report(report)
        print("Rapport :", output)
        sys.exit(2)

    modified_files = (
        status["stdout"].splitlines()
        if status["stdout"] else []
    )

    report["checks"]["git_status"] = {
        "status": "PASS",
        "modified_files": modified_files
    }

    report["repository_modified"] = bool(modified_files)

    if modified_files:
        if args.mode == "PRE_APPLY":
            print("INFO — modifications déjà présentes dans le dépôt")
        else:
            print("PASS — modifications détectées après application")
        for line in status["stdout"].splitlines():
            print("  ", line)
    else:
        print("ATTENTION — aucune modification détectée")

    print()

    failed = False

    for index, test in enumerate(TESTS, start=2):

        print(f"[{index}] {test['name']}")
        print("Commande :", " ".join(test["command"]))

        result = run_command(
            test["command"],
            test["timeout"]
        )

        if result["returncode"] == 0:
            status_name = "PASS"
            print("PASS")

        elif result["returncode"] == -2:
            status_name = "TIMEOUT"
            failed = True
            print("TIMEOUT")

        else:
            status_name = "FAIL"
            failed = True
            print("FAIL")

        report["tests"].append({
            "name": test["name"],
            "command": test["command"],
            "timeout_seconds": test["timeout"],
            "status": status_name,
            "returncode": result["returncode"],
            "stdout": result["stdout"],
            "stderr": result["stderr"]
        })

        if result["stderr"]:
            print(result["stderr"][-3000:])

        print()

    if failed:
        overall = "REGRESSION"
        next_step = "STOP_HUMAN_REVIEW"
    elif args.mode == "PRE_APPLY":
        overall = "PASS"
        next_step = "HUMAN_APPROVAL"
    else:
        overall = "PASS"
        next_step = "HUMAN_COMMIT_REVIEW"

    report["overall_status"] = overall
    report["next_step"] = next_step

    output = save_report(report)

    print("=" * 60)
    print("RÉSULTAT POST-TEST :", overall)
    print("Rapport            :", output)
    print("=" * 60)
    print()

    if overall == "REGRESSION":
        print("STOP — aucune correction automatique.")
        print("MemoLib reste dans son état après application.")
        print("Aucun rollback.")
        print("Aucun commit.")
        print("Aucun push.")
        sys.exit(2)

    if args.mode == "PRE_APPLY":
        print("PRE-APPLY PASS.")
        print("Aucune application.")
        print("Aucun commit.")
        print("Aucun push.")
    else:
        print("POST-TEST PASS.")
        print("Aucun commit.")
        print("Aucun push.")

    sys.exit(0)


if __name__ == "__main__":
    main()


