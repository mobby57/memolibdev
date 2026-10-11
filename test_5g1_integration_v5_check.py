from pathlib import Path
import hashlib
import subprocess
import tempfile
import shutil

from controlled_coder import verify_patch_in_sandbox

TARGET = Path(r"C:\Users\moros\memoLib")
REL = Path("src/lib/auth/nextauth-token.ts")
SOURCE = TARGET / REL

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

print("=" * 62)
print("5G.1 — INTEGRATION V5 / BYTE-PRESERVING")
print("=" * 62)

before = sha256(SOURCE)

work = Path(tempfile.mkdtemp(prefix="memolibdev-5g1-v5-"))
repo = work / "repo"
patch = work / "sandbox-test.diff"

try:
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

    # IMPORTANT :
    # copie byte-for-byte du fichier réel
    original_bytes = SOURCE.read_bytes()
    test_file.write_bytes(original_bytes)

    assert git("add", "-A").returncode == 0
    assert git("commit", "-q", "-m", "baseline").returncode == 0

    # --------------------------------------------------
    # Modification BYTE-PRESERVING
    # --------------------------------------------------

    needle = b"const nextAuthSecret = process.env.NEXTAUTH_SECRET;"

    assert needle in original_bytes, \
        "Ligne cible absente du fichier source"

    replacement = (
        needle +
        b" // 5G1-SANDBOX-TEST"
    )

    modified_bytes = original_bytes.replace(
        needle,
        replacement,
        1,
    )

    test_file.write_bytes(modified_bytes)

    # --------------------------------------------------
    # Vrai diff Git
    # --------------------------------------------------

    result = git("diff", "--", str(REL))

    assert result.returncode == 0
    assert result.stdout.strip()

    patch.write_text(
        result.stdout,
        encoding="utf-8",
        newline="",
    )

    print("")
    print("=== PATCH ===")
    print(result.stdout)

    # --------------------------------------------------
    # Sandbox Gate réel
    # --------------------------------------------------

    result_sandbox = verify_patch_in_sandbox(
        result.stdout,
        {str(REL).replace("\\", "/")},
        patch,
    )

    print("")
    print("=== RESULTAT SANDBOX ===")
    print("applicable :", result_sandbox["applicable"])
    print("returncode :", result_sandbox["returncode"])
    print("stderr     :", result_sandbox["stderr"])
    print("stat       :", result_sandbox["stat"])
    print("sandbox    :", result_sandbox["sandbox"])
    print("files      :", result_sandbox["sandbox_files"])

    # --------------------------------------------------
    # Assertions
    # --------------------------------------------------

    assert result_sandbox["applicable"] is True
    print("[PASS] Patch applicable")

    assert result_sandbox["returncode"] == 0
    print("[PASS] git apply --check = 0")

    sandbox = Path(result_sandbox["sandbox"])

    assert not sandbox.exists()
    print("[PASS] Sandbox supprimé")

    # --------------------------------------------------
    # MemoLib intégrité
    # --------------------------------------------------

    after = sha256(SOURCE)

    print("")
    print("=== MEMOLIB ===")
    print("SHA AVANT :", before)
    print("SHA APRES :", after)

    assert before == after
    print("[PASS] SHA MemoLib inchangé")

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=TARGET,
        text=True,
        capture_output=True,
    )

    assert status.returncode == 0

    if status.stdout.strip():
        print("[WARN] MemoLib possède déjà des modifications")
        print(status.stdout)
    else:
        print("[PASS] MemoLib CLEAN")

    print("")
    print("=" * 62)
    print("5G.1 — INTEGRATION V5 RESULTAT")
    print("=" * 62)
    print("PASS : Patch applicable")
    print("PASS : Cleanup")
    print("PASS : MemoLib inchangé")
    print("VERDICT : PASS")

finally:
    shutil.rmtree(work, ignore_errors=True)
