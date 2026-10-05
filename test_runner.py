from pathlib import Path
from datetime import datetime
import json
import subprocess
import sys
import re


ROOT = Path(r"C:\Users\moros\Desktop\memolib").resolve()
V3 = Path(r"C:\Users\moros\MemoLibDev\v3").resolve()
REPORTS = V3 / "reports"

REPORTS.mkdir(parents=True, exist_ok=True)


def run_command(args):
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            capture_output=True,
            text=True,
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


def extract_files_from_patch(patch):
    files = []

    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()

            if path != "/dev/null" and path not in files:
                files.append(path)

    return files


def safe_repo_path(relative_path):
    path = (ROOT / relative_path).resolve()

    try:
        path.relative_to(ROOT)
    except ValueError:
        return None

    if ".git" in path.parts:
        return None

    return path


def save_report(report):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = REPORTS / f"test-run-{timestamp}.json"

    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return output


def main():
    if len(sys.argv) != 2:
        print("Usage : python test_runner.py chemin-vers-patch.diff")
        sys.exit(1)

    patch_path = Path(sys.argv[1]).resolve()

    if not patch_path.exists():
        print("ERREUR : patch introuvable")
        sys.exit(1)

    if patch_path.suffix not in {".diff", ".patch"}:
        print("ERREUR : extension de patch invalide")
        sys.exit(1)

    patch = patch_path.read_text(encoding="utf-8")

    print("=" * 60)
    print(" MEMOLIBDEV V3 — TEST RUNNER")
    print("=" * 60)
    print()
    print("Dépôt :", ROOT)
    print("Patch :", patch_path)
    print()

    # ---------------------------------------------------------
    # CAS SPÉCIAL : aucun patch produit
    # ---------------------------------------------------------

    if "NO_PATCH_POSSIBLE" in patch:
        print("NO_PATCH_POSSIBLE détecté.")
        print("Aucun patch à tester.")
        print("Application interdite.")
        print("MemoLib n'a PAS été modifié.")

        report = {
            "created_at": datetime.now().isoformat(),
            "patch": str(patch_path),
            "repository": str(ROOT),
            "repository_modified": False,
            "human_validation_required": True,
            "overall_status": "NO_PATCH_POSSIBLE",
            "next_step": "DO_NOT_APPLY",
            "checks": {
                "patch": {
                    "status": "SKIPPED",
                    "reason": "Le Coder n'a produit aucun patch."
                }
            }
        }

        output = save_report(report)

        print()
        print("Rapport :", output)
        sys.exit(0)

    report = {
        "created_at": datetime.now().isoformat(),
        "patch": str(patch_path),
        "repository": str(ROOT),
        "repository_modified": False,
        "human_validation_required": True,
        "checks": {}
    }

    # ---------------------------------------------------------
    # 1. État Git
    # ---------------------------------------------------------

    print("[1] État Git")

    git_status = run_command(
        ["git", "status", "--porcelain"]
    )

    if git_status["returncode"] != 0:

        report["checks"]["git_status"] = {
            "status": "FAIL",
            "details": git_status
        }

        print("FAIL — impossible de lire l'état Git")

    elif git_status["stdout"]:

        report["checks"]["git_status"] = {
            "status": "BLOCKED",
            "details": git_status["stdout"]
        }

        print("BLOQUÉ — dépôt non propre")
        print(git_status["stdout"])

    else:

        report["checks"]["git_status"] = {
            "status": "PASS"
        }

        print("PASS — dépôt propre")

    # ---------------------------------------------------------
    # 2. Vérification du patch
    # ---------------------------------------------------------

    print()
    print("[2] Vérification du patch")

    check = run_command(
        ["git", "apply", "--check", str(patch_path)]
    )

    if check["returncode"] == 0:

        report["checks"]["patch_check"] = {
            "status": "PASS",
            "stdout": check["stdout"]
        }

        print("PASS — patch applicable")

    else:

        report["checks"]["patch_check"] = {
            "status": "FAIL",
            "stdout": check["stdout"],
            "stderr": check["stderr"]
        }

        print("FAIL — patch non applicable")

        if check["stderr"]:
            print(check["stderr"])

    # ---------------------------------------------------------
    # 3. Fichiers ciblés
    # ---------------------------------------------------------

    print()
    print("[3] Fichiers ciblés")

    files = extract_files_from_patch(patch)
    file_results = []

    if not files:
        print("ATTENTION — aucun fichier détecté")

    for relative_path in files:

        target = safe_repo_path(relative_path)

        if target is None:

            result = {
                "file": relative_path,
                "status": "BLOCKED",
                "reason": "Chemin hors dépôt ou accès interdit"
            }

            print("BLOQUÉ :", relative_path)

        elif target.exists():

            result = {
                "file": relative_path,
                "status": "PASS",
                "size": target.stat().st_size
            }

            print("PASS :", relative_path)

        else:

            result = {
                "file": relative_path,
                "status": "FAIL",
                "reason": "Fichier inexistant"
            }

            print("FAIL :", relative_path)

        file_results.append(result)

    report["checks"]["target_files"] = file_results

    # ---------------------------------------------------------
    # 4. Analyse sécurité
    # ---------------------------------------------------------

    print()
    print("[4] Analyse de sécurité du patch")

    security_flags = []

    dangerous_patterns = {
        "git": r"(^|/)\.git(/|$)",
        "secrets": r"(^|/)(\.env|\.env\.local|.*secret.*|.*private.*)",
        "package_lock": r"(^|/)package-lock\.json$",
        "delete": r"^deleted file mode|^--- /dev/null$",
        "binary": r"^GIT binary patch$"
    }

    for name, pattern in dangerous_patterns.items():

        if re.search(
            pattern,
            patch,
            re.IGNORECASE | re.MULTILINE
        ):
            security_flags.append(name)

    if security_flags:

        security_status = "REVIEW_REQUIRED"

        print(
            "ATTENTION :",
            ", ".join(security_flags)
        )

    else:

        security_status = "PASS"

        print(
            "PASS — aucun indicateur dangereux détecté"
        )

    report["checks"]["security_scan"] = {
        "status": security_status,
        "flags": security_flags
    }

    # ---------------------------------------------------------
    # Résultat global
    # ---------------------------------------------------------

    statuses = []

    statuses.append(
        report["checks"]["git_status"]["status"]
    )

    statuses.append(
        report["checks"]["patch_check"]["status"]
    )

    for item in file_results:
        statuses.append(item["status"])

    statuses.append(security_status)

    if "FAIL" in statuses:

        overall = "FAIL"

    elif (
        "BLOCKED" in statuses
        or "REVIEW_REQUIRED" in statuses
    ):

        overall = "NEEDS_REVIEW"

    elif statuses and all(
        status == "PASS"
        for status in statuses
    ):

        overall = "PASS"

    else:

        overall = "NEEDS_REVIEW"

    report["overall_status"] = overall

    if overall == "PASS":
        report["next_step"] = "HUMAN_VALIDATION_REQUIRED"
    else:
        report["next_step"] = "DO_NOT_APPLY"

    output = save_report(report)

    print()
    print("=" * 60)
    print("RÉSULTAT :", overall)
    print("Rapport  :", output)
    print("=" * 60)
    print()
    print("MemoLib n'a PAS été modifié.")
    print("Aucun commit.")
    print("Aucun push.")


if __name__ == "__main__":
    main()
