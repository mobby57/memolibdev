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
print("5G.1 — DIAGNOSTIC GIT APPLY")
print("=" * 62)

before = sha256(SOURCE)

work = Path(tempfile.mkdtemp(prefix="memolibdev-5g1-debug-"))
repo = work / "repo"
patch = work / "test.diff"

try:
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            text=True,
            capture_output=True,
        )

    print("[1] INIT")
    r = git("init", "-q")
    print("returncode:", r.returncode)
    print("stderr:", r.stderr.strip())

    git("config", "user.email", "test@memolibdev.local")
    git("config", "user.name", "memolibdev-test")

    test_file = repo / REL
    test_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, test_file)

    git("add", "-A")
    r = git("commit", "-q", "-m", "baseline")

    print("[2] BASELINE COMMIT")
    print("returncode:", r.returncode)
    print("stderr:", r.stderr.strip())

    original = test_file.read_text(encoding="utf-8")
    needle = "const nextAuthSecret = process.env.NEXTAUTH_SECRET;"

    assert needle in original

    modified = original.replace(
        needle,
        needle + " // 5G1-SANDBOX-TEST",
        1,
    )

    test_file.write_text(modified, encoding="utf-8")

    r = git("diff", "--", str(REL))

    print("[3] GENERATED DIFF")
    print(r.stdout)

    patch.write_text(r.stdout, encoding="utf-8")

    print("[4] PATCH FILE")
    print(patch)
    print("exists:", patch.exists())
    print("size:", patch.stat().st_size)

    print("[5] DIRECT GIT APPLY CHECK")

    direct = subprocess.run(
        [
            "git",
            "apply",
            "--check",
            "--verbose",
            str(patch),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )

    print("returncode:", direct.returncode)
    print("stdout:")
    print(direct.stdout)
    print("stderr:")
    print(direct.stderr)

    print("[6] CONTROLLED SANDBOX")

    result = verify_patch_in_sandbox(
        r.stdout,
        {str(REL).replace("\\", "/")},
        patch,
    )

    print("applicable :", result["applicable"])
    print("returncode :", result["returncode"])
    print("stderr    :", result["stderr"])
    print("stat      :", result["stat"])
    print("sandbox   :", result["sandbox"])

    sandbox = Path(result["sandbox"])

    print("")
    print("=== CLEANUP ===")
    print("sandbox exists:", sandbox.exists())

    after = sha256(SOURCE)

    print("")
    print("=== MEMOLIB ===")
    print("SHA avant:", before)
    print("SHA après:", after)
    print("SHA identique:", before == after)

finally:
    shutil.rmtree(work, ignore_errors=True)

print("")
print("=" * 62)
print("FIN DIAGNOSTIC")
print("=" * 62)
