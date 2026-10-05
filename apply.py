from pathlib import Path
import hashlib
import json
import subprocess
import sys
from datetime import datetime

ROOT = Path(r"C:\Users\moros\Desktop\memolib").resolve()
V3 = Path(r"C:\Users\moros\MemoLibDev\v3").resolve()
REPORTS = V3 / "reports"


def sha256_file(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def run_git(*args):
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    return (
        result.returncode,
        result.stdout.strip(),
        result.stderr.strip(),
    )


def safe_repo_path(relative_path):
    candidate = (ROOT / relative_path).resolve()

    try:
        candidate.relative_to(ROOT)
    except ValueError:
        return None

    if ".git" in candidate.parts:
        return None

    return candidate


def extract_targets(patch_text):
    targets = []

    for line in patch_text.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()

            if path == "/dev/null":
                continue

            if path not in targets:
                targets.append(path)

    return targets


def find_latest_snapshot():
    snapshots = sorted(
        REPORTS.glob("snapshot-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    return snapshots[0] if snapshots else None


def write_report(data):
    REPORTS.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = REPORTS / f"apply-{timestamp}.json"

    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return path


def stop(message, report):
    print()
    print("============================================================")
    print(" APPLICATION REFUSÉE")
    print("============================================================")
    print(message)
    print()
    print("MemoLib : NON MODIFIÉ")
    print("Aucun commit.")
    print("Aucun push.")

    report_path = write_report(report)

    print(f"Rapport : {report_path}")

    raise SystemExit(1)


def main():
    if len(sys.argv) != 2:
        print("Usage: python apply.py <patch.diff>")
        raise SystemExit(2)

    patch = Path(sys.argv[1]).resolve()

    print("=" * 60)
    print(" MEMOLIBDEV V3.1 — APPLY")
    print("=" * 60)
    print()
    print(f"Dépôt : {ROOT}")
    print(f"Patch : {patch}")
    print()

    if not patch.exists():
        stop(
            "ERREUR — patch introuvable.",
            {
                "status": "REFUSED",
                "reason": "PATCH_NOT_FOUND",
                "patch": str(patch),
                "repository_modified": False,
            },
        )

    snapshot = find_latest_snapshot()

    print("[1] Snapshot")

    if snapshot is None:
        stop(
            "ERREUR — aucun snapshot disponible.",
            {
                "status": "REFUSED",
                "reason": "SNAPSHOT_NOT_FOUND",
                "patch": str(patch),
                "repository_modified": False,
            },
        )

    print(f"       {snapshot}")

    try:
        snapshot_data = json.loads(
            snapshot.read_text(
                encoding="utf-8",
            )
        )
    except Exception as exc:
        stop(
            f"ERREUR — snapshot invalide : {exc}",
            {
                "status": "REFUSED",
                "reason": "INVALID_SNAPSHOT",
                "snapshot": str(snapshot),
                "patch": str(patch),
                "repository_modified": False,
            },
        )

    expected_patch_sha = snapshot_data.get("patch_sha256")

    if not expected_patch_sha:
        stop(
            "ERREUR — snapshot sans SHA256 du patch.",
            {
                "status": "REFUSED",
                "reason": "SNAPSHOT_MISSING_PATCH_SHA256",
                "snapshot": str(snapshot),
                "patch": str(patch),
                "repository_modified": False,
            },
        )

    actual_patch_sha = sha256_file(patch)

    print()
    print("[2] Vérification SHA-256 du patch")
    print(f"     Snapshot : {expected_patch_sha}")
    print(f"     Actuel   : {actual_patch_sha}")

    if actual_patch_sha != expected_patch_sha:
        stop(
            "REFUS — le patch a changé depuis la création du snapshot.",
            {
                "status": "REFUSED",
                "reason": "PATCH_SHA256_MISMATCH",
                "snapshot": str(snapshot),
                "patch": str(patch),
                "expected_patch_sha256": expected_patch_sha,
                "actual_patch_sha256": actual_patch_sha,
                "repository_modified": False,
            },
        )

    print("PASS — SHA-256 identique")

    print()
    print("[3] Vérification HEAD")

    code, head, err = run_git("rev-parse", "HEAD")

    if code != 0:
        stop(
            f"ERREUR Git : {err}",
            {
                "status": "REFUSED",
                "reason": "GIT_HEAD_ERROR",
                "repository_modified": False,
            },
        )

    expected_head = snapshot_data.get("git_head")

    if head != expected_head:
        stop(
            "REFUS — HEAD différent du snapshot.",
            {
                "status": "REFUSED",
                "reason": "HEAD_MISMATCH",
                "expected_head": expected_head,
                "actual_head": head,
                "repository_modified": False,
            },
        )

    print("PASS — HEAD identique")

    print()
    print("[4] État Git")

    code, status, err = run_git("status", "--short")

    if code != 0:
        stop(
            f"ERREUR Git status : {err}",
            {
                "status": "REFUSED",
                "reason": "GIT_STATUS_ERROR",
                "repository_modified": False,
            },
        )

    if status:
        stop(
            "REFUS — le dépôt n'est pas propre.",
            {
                "status": "REFUSED",
                "reason": "GIT_NOT_CLEAN",
                "git_status": status,
                "repository_modified": False,
            },
        )

    print("PASS — dépôt propre")

    print()
    print("[5] Vérification SHA-256 des fichiers")

    snapshot_files = snapshot_data.get("files", [])

    for item in snapshot_files:
        relative = item["path"]
        expected_sha = item["sha256"]

        target = safe_repo_path(relative)

        if target is None or not target.exists():
            stop(
                f"REFUS — fichier cible invalide ou absent : {relative}",
                {
                    "status": "REFUSED",
                    "reason": "TARGET_INVALID",
                    "target": relative,
                    "repository_modified": False,
                },
            )

        actual_sha = sha256_file(target)

        if actual_sha != expected_sha:
            stop(
                f"REFUS — SHA256 différent : {relative}",
                {
                    "status": "REFUSED",
                    "reason": "TARGET_SHA256_MISMATCH",
                    "target": relative,
                    "expected_sha256": expected_sha,
                    "actual_sha256": actual_sha,
                    "repository_modified": False,
                },
            )

        print(f"PASS : {relative}")

    print()
    print("[6] Vérification du patch")

    check = subprocess.run(
        ["git", "apply", "--check", str(patch)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if check.returncode != 0:
        stop(
            "REFUS — git apply --check a échoué.",
            {
                "status": "REFUSED",
                "reason": "PATCH_CHECK_FAILED",
                "stderr": check.stderr,
                "repository_modified": False,
            },
        )

    print("PASS — patch applicable")

    patch_text = patch.read_text(
        encoding="utf-8",
        errors="replace",
    )

    print()
    print("=" * 60)
    print(" PATCH PROPOSÉ")
    print("=" * 60)
    print()
    print(patch_text)
    print("=" * 60)
    print()
    print("ATTENTION :")
    print("Cette opération va modifier le dépôt MemoLib.")
    print("Aucun commit ne sera effectué.")
    print("Aucun push ne sera effectué.")
    print()
    print("Tapez exactement OUI pour appliquer le patch : ", end="", flush=True)

    answer = sys.stdin.readline().strip()

    if answer != "OUI":
        stop(
            "Validation humaine refusée ou non exacte.",
            {
                "status": "REFUSED",
                "reason": "HUMAN_VALIDATION_REFUSED",
                "snapshot": str(snapshot),
                "patch": str(patch),
                "patch_sha256": actual_patch_sha,
                "repository_modified": False,
            },
        )

    print()
    print("[7] Application du patch...")

    apply_result = subprocess.run(
        ["git", "apply", str(patch)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if apply_result.returncode != 0:
        stop(
            "ERREUR — git apply a échoué.",
            {
                "status": "APPLY_FAILED",
                "reason": "GIT_APPLY_FAILED",
                "stderr": apply_result.stderr,
                "repository_modified": False,
            },
        )

    print("PATCH APPLIQUÉ")

    print()
    print("[8] Vérification après application")

    code, new_status, err = run_git("status", "--short")

    if code != 0:
        print("ERREUR — impossible de lire Git status après application.")
    else:
        print("État Git :")
        print(new_status or "(aucune modification détectée)")

    report = {
        "status": "APPLIED",
        "snapshot": str(snapshot),
        "patch": str(patch),
        "patch_sha256": actual_patch_sha,
        "git_head": head,
        "git_status_after": new_status,
        "human_validation": "OUI",
        "commit": False,
        "push": False,
        "repository_modified": True,
    }

    report_path = write_report(report)

    print()
    print("=" * 60)
    print(" APPLICATION TERMINÉE")
    print("=" * 60)
    print()
    print(f"Rapport : {report_path}")
    print()
    print("Aucun commit.")
    print("Aucun push.")
    print()
    print("IMPORTANT : le commit reste sous contrôle humain.")


if __name__ == "__main__":
    main()
