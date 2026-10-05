from pathlib import Path
import subprocess
import sys

ROOT = (
    Path(r"C:\Users\moros\MemoLibDev\v3\workspace\patch-lab")
    .resolve()
)

PATCH = (
    Path(r"C:\Users\moros\MemoLibDev\v3\patches\lab-test.diff")
    .resolve()
)


def run_git(*args):
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True
    )


def main():
    print("=" * 60)
    print(" MEMOLIBDEV V3 — APPLY PATCH LAB")
    print("=" * 60)
    print()
    print("Dépôt laboratoire :", ROOT)
    print("Patch              :", PATCH)
    print()

    if not ROOT.exists():
        print("ERREUR : laboratoire introuvable")
        sys.exit(1)

    if not PATCH.exists():
        print("ERREUR : patch introuvable")
        sys.exit(1)

    if ".git" not in [p.name for p in ROOT.parents] and not (ROOT / ".git").exists():
        print("ERREUR : dépôt Git laboratoire introuvable")
        sys.exit(1)

    print("[1] Vérification du patch...")

    check = run_git("apply", "--check", str(PATCH))

    if check.returncode != 0:
        print("REFUS : le patch ne passe pas git apply --check")
        print(check.stderr)
        sys.exit(1)

    print("OK — patch applicable")
    print()

    print("[2] État AVANT application")
    status_before = run_git("status", "--short")

    if status_before.stdout.strip():
        print(status_before.stdout)
        print("REFUS : le laboratoire doit être propre")
        sys.exit(1)

    print("OK — dépôt propre")
    print()

    print("[3] Patch proposé")
    print("-" * 60)

    diff = run_git("diff", "--no-index", str(ROOT / "hello.txt"), str(ROOT / "hello.txt"))

    subprocess.run(
        ["git", "apply", "--stat", str(PATCH)],
        cwd=ROOT
    )

    print("-" * 60)
    print()

    print("ATTENTION : cette action va modifier UNIQUEMENT le laboratoire.")
    print("Aucun commit ou push ne sera effectué.")
    print()

    confirmation = input('Tape exactement "OUI" pour appliquer : ')

    if confirmation != "OUI":
        print()
        print("REFUS — aucune modification effectuée.")
        sys.exit(0)

    print()
    print("[4] Application du patch...")

    apply_result = run_git("apply", str(PATCH))

    if apply_result.returncode != 0:
        print("ERREUR pendant l'application")
        print(apply_result.stderr)
        sys.exit(1)

    print("PATCH APPLIQUÉ")
    print()

    print("[5] État APRÈS application")

    status_after = run_git("status", "--short")

    print(status_after.stdout)

    print("Contenu de hello.txt :")
    print((ROOT / "hello.txt").read_text(encoding="utf-8"))

    print()
    print("Aucun commit effectué.")
    print("Aucun push effectué.")
    print("MemoLib réel n'a pas été ciblé.")


if __name__ == "__main__":
    main()
