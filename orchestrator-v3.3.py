import os
from pathlib import Path
from datetime import datetime
import json
import subprocess
import sys

V3 = Path(r"C:\Users\moros\MemoLibDev\v3").resolve()
ROOT = Path(r"C:\Users\moros\Desktop\memolib").resolve()

REPORTS = V3 / "reports"
PATCHES = V3 / "patches"

REPORTS.mkdir(parents=True, exist_ok=True)


def run(cmd, cwd, timeout=300):
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        result = subprocess.run(
            cmd,
            cwd=cwd,
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
    return run(
        ["git", "status", "--porcelain"],
        ROOT,
        60
    )


def find_latest_patch():
    patches = sorted(
        PATCHES.glob("*.diff"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    return patches[0] if patches else None


def save_report(report):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = REPORTS / f"orchestrator-v3.3-{timestamp}.json"

    path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return path


def main():
    print("=" * 70)
    print(" MEMOLIBDEV V3.3 — ORCHESTRATEUR SÉCURISÉ")
    print("=" * 70)
    print()

    report = {
        "created_at": datetime.now().isoformat(),
        "version": "3.3",
        "repository": str(ROOT),
        "mode": "READ_ONLY_PREVIEW",
        "automatic_apply": False,
        "automatic_commit": False,
        "automatic_push": False,
        "automatic_production": False,
        "steps": []
    }

    if not ROOT.exists():
        print("STOP — dépôt MemoLib introuvable.")
        report["overall_status"] = "STOP"
        report["reason"] = "repository_not_found"
        output = save_report(report)
        print("Rapport :", output)
        sys.exit(2)

    print("[1] VÉRIFICATION GIT")
    status = git_status()

    if status["returncode"] != 0:
        print("STOP — Git inaccessible.")
        report["overall_status"] = "STOP"
        report["reason"] = "git_unavailable"
        report["steps"].append({
            "name": "git_status",
            "status": "FAIL",
            "details": status
        })

        output = save_report(report)
        print("Rapport :", output)
        sys.exit(2)

    modified = status["stdout"].splitlines() if status["stdout"] else []

    if modified:
        print("ATTENTION — MemoLib possède déjà des modifications :")
        for line in modified:
            print("  ", line)

        report["steps"].append({
            "name": "git_status",
            "status": "WARN",
            "modified_files": modified
        })

    else:
        print("PASS — dépôt propre")

        report["steps"].append({
            "name": "git_status",
            "status": "PASS",
            "modified_files": []
        })

    print()

    print("[2] RECHERCHE DU PATCH")
    patch = find_latest_patch()

    if not patch:
        print("STOP — aucun patch .diff trouvé.")

        report["overall_status"] = "STOP"
        report["reason"] = "no_patch_found"

        output = save_report(report)
        print("Rapport :", output)
        sys.exit(2)

    print("Patch :", patch)

    report["steps"].append({
        "name": "patch_detection",
        "status": "PASS",
        "patch": str(patch)
    })

    print()

    print("[3] VÉRIFICATION DU PATCH")
    check = run(
        ["git", "apply", "--check", str(patch)],
        ROOT,
        60
    )

    if check["returncode"] != 0:
        print("STOP — patch non applicable.")

        report["steps"].append({
            "name": "git_apply_check",
            "status": "FAIL",
            "details": check
        })

        report["overall_status"] = "STOP"
        report["reason"] = "patch_check_failed"

        output = save_report(report)
        print("Rapport :", output)
        sys.exit(2)

    print("PASS — patch applicable")

    report["steps"].append({
        "name": "git_apply_check",
        "status": "PASS"
    })

    print()

    print("[4] TESTS AVANT APPLICATION")
    print("Commande : python post_test.py")
    print("NOTE : cette étape vérifie l'état actuel de MemoLib.")
    print()

    before = run(
        [sys.executable, str(V3 / "post_test.py")],
        V3,
        1200
    )

    before_ok = before["returncode"] == 0

    report["steps"].append({
        "name": "tests_before",
        "status": "PASS" if before_ok else "FAIL",
        "returncode": before["returncode"],
        "stdout": before["stdout"],
        "stderr": before["stderr"]
    })

    if not before_ok:
        print("STOP — TESTS BEFORE en échec.")
        report["overall_status"] = "STOP"
        report["reason"] = "tests_before_failed"

        output = save_report(report)
        print("Rapport :", output)
        sys.exit(2)

    print("PASS — TESTS BEFORE")

    print()
    print("=" * 70)
    print(" HUMAN APPROVAL REQUIRED")
    print("=" * 70)
    print()
    print("Patch prêt à être soumis à l'étape d'application :")
    print(patch)
    print()
    print("AUCUNE APPLICATION N'A ÉTÉ EFFECTUÉE.")
    print("AUCUN COMMIT.")
    print("AUCUN PUSH.")
    print("AUCUNE MODIFICATION AUTOMATIQUE DE MEMOLIB.")
    print()

    report["overall_status"] = "READY_FOR_HUMAN_APPROVAL"
    report["next_step"] = "HUMAN_APPROVAL"
    report["human_approval_required"] = True

    output = save_report(report)

    print("Rapport :", output)
    print()
    print("V3.3 — ARRÊT NORMAL AVANT APPLICATION.")

    sys.exit(0)


if __name__ == "__main__":
    main()


