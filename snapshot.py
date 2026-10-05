from pathlib import Path
import hashlib
import json
import re
import subprocess
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
    return result.returncode, result.stdout.strip(), result.stderr.strip()


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


def safe_repo_path(relative_path):
    candidate = (ROOT / relative_path).resolve()

    try:
        candidate.relative_to(ROOT)
    except ValueError:
        return None

    if ".git" in candidate.parts:
        return None

    return candidate


def main():
    import sys

    if len(sys.argv) != 2:
        print("Usage: python snapshot.py <patch.diff>")
        raise SystemExit(2)

    patch = Path(sys.argv[1]).resolve()

    print("=" * 60)
    print(" MEMOLIBDEV V3.1 — SNAPSHOT")
    print("=" * 60)
    print()
    print(f"Dépôt : {ROOT}")
    print(f"Patch : {patch}")
    print()

    if not patch.exists():
        print("ERREUR — patch introuvable")
        raise SystemExit(1)

    code, head, err = run_git("rev-parse", "HEAD")
    if code != 0:
        print("ERREUR — impossible de lire HEAD")
        print(err)
        raise SystemExit(1)

    code, status, err = run_git("status", "--short")
    if code != 0:
        print("ERREUR — impossible de lire Git status")
        raise SystemExit(1)

    if status:
        print("ERREUR — dépôt non propre")
        print(status)
        raise SystemExit(1)

    patch_sha256 = sha256_file(patch)
    patch_text = patch.read_text(encoding="utf-8", errors="replace")
    targets = extract_targets(patch_text)

    if not targets:
        print("ERREUR — aucun fichier cible trouvé dans le patch")
        raise SystemExit(1)

    files = []

    for relative in targets:
        target = safe_repo_path(relative)

        if target is None:
            print(f"ERREUR — chemin interdit : {relative}")
            raise SystemExit(1)

        if not target.exists():
            print(f"ERREUR — fichier cible absent : {relative}")
            raise SystemExit(1)

        digest = sha256_file(target)

        print(f"SHA256 : {relative}")
        print(f"        {digest}")

        files.append({
            "path": relative,
            "sha256": digest,
        })

    created = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = REPORTS / f"snapshot-{created}.json"
    REPORTS.mkdir(parents=True, exist_ok=True)

    report = {
        "created_at": datetime.now().isoformat(),
        "repository": str(ROOT),
        "patch": str(patch),
        "patch_sha256": patch_sha256,
        "git_head": head,
        "git_status": "clean",
        "files": files,
        "human_validation_required": True,
        "repository_modified": False,
    }

    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("PATCH SHA256 :")
    print(f"  {patch_sha256}")
    print()
    print("SNAPSHOT CRÉÉ")
    print(f"Rapport : {report_path}")
    print()
    print("MemoLib n'a PAS été modifié.")
    print("Aucun commit.")
    print("Aucun push.")


if __name__ == "__main__":
    main()
