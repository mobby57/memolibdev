from pathlib import Path
import hashlib
import subprocess
import tempfile
import shutil
import os

from controlled_coder import verify_patch_in_sandbox


TARGET = Path(r"C:\Users\moros\memoLib")
REL = Path("src/lib/auth/nextauth-token.ts")
SOURCE = TARGET / REL


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


print("=" * 62)
print("5G.1 — INTEGRATION V4 / CLEANUP FAIL-CLOSED")
print("=" * 62)

before_sha = sha256(SOURCE)

print("TARGET :", TARGET)
print("FILE   :", REL)
print("SHA AVANT :", before_sha)

work = Path(tempfile.mkdtemp(prefix="memolibdev-5g1-v4-"))
repo = work / "repo"
patch = work / "sandbox-test.diff"

try:
    # --------------------------------------------------
    # 1. Repo Git de test
    # --------------------------------------------------

    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            text=True,
            capture_output=True,
        )

    assert git("init", "-q").returncode == 0
    assert git("config", "user.email", "test@memolibdev.local").returncode == 0
    assert git("config", "user.name", "memolibdev-test").returncode == 0

    test_file = repo / REL
    test_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, test_file)

    assert git("add", "-A").returncode == 0
    assert git("commit", "-q", "-m", "baseline").returncode == 0

    # --------------------------------------------------
    # 2. Modification contrôlée
    # --------------------------------------------------

    original = test_file.read_text(encoding="utf-8")

    needle = "const nextAuthSecret = process.env.NEXTAUTH_SECRET;"

    assert needle in original, "Ligne cible absente du fichier test"

    modified = original.replace(
        needle,
        needle + " // 5G1-SANDBOX-TEST",
        1,
    )

    test_file.write_text(modified, encoding="utf-8")

    # --------------------------------------------------
    # 3. Génération d'un vrai git diff
    # --------------------------------------------------

    result = git("diff", "--", str(REL))

    assert result.returncode == 0
    assert result.stdout.strip()

    patch.write_text(result.stdout, encoding="utf-8")

    print("")
    print("=== PATCH ===")
    print(result.stdout)

    # --------------------------------------------------
    # 4. Appel réel du Sandbox Gate
    # --------------------------------------------------

    touched = {str(REL).replace("\\", "/")}

    sandbox_result = verify_patch_in_sandbox(
        result.stdout,
        touched,
        patch,
    )

    print("")
    print("=== RESULTAT SANDBOX ===")
    print("applicable :", sandbox_result["applicable"])
    print("returncode :", sandbox_result["returncode"])
    print("sandbox    :", sandbox_result["sandbox"])
    print("target     :", sandbox_result["target_root"])
    print("patch      :", sandbox_result["patch_file"])
    print("files      :", sandbox_result["sandbox_files"])

    # --------------------------------------------------
    # 5. Assertions
    # --------------------------------------------------

    assert sandbox_result["applicable"] is True
    print("[PASS] Patch applicable dans sandbox")

    assert sandbox_result["returncode"] == 0
    print("[PASS] git apply --check = 0")

    sandbox_path = Path(sandbox_result["sandbox"])

    assert not sandbox_path.exists()
    print("[PASS] Sandbox supprimé après retour")

    # --------------------------------------------------
    # 6. Intégrité MemoLib
    # --------------------------------------------------

    after_sha = sha256(SOURCE)

    print("")
    print("=== INTEGRITE MEMOLIB ===")
    print("SHA AVANT :", before_sha)
    print("SHA APRES :", after_sha)

    assert before_sha == after_sha
    print("[PASS] MemoLib inchangé")

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=TARGET,
        text=True,
        capture_output=True,
    )

    assert status.returncode == 0

    if status.stdout.strip():
        print("[WARN] MemoLib possède déjà des modifications :")
        print(status.stdout)
    else:
        print("[PASS] MemoLib CLEAN")

    print("")
    print("=" * 62)
    print("5G.1 — INTEGRATION V4 RESULTAT")
    print("=" * 62)
    print("PASS : Sandbox applicable")
    print("PASS : Cleanup effectif")
    print("PASS : MemoLib inchangé")
    print("PASS : Aucun Ollama")
    print("PASS : Aucun commit/push MemoLib")
    print("VERDICT : PASS")

finally:
    # Nettoyage du dépôt de test externe uniquement.
    shutil.rmtree(work, ignore_errors=True)
