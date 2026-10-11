# e2e_smoke_test_v3.py — Syntaxe correcte
import subprocess, hashlib, sys
from pathlib import Path

TARGET = Path(r"C:\Users\moros\Desktop\memolib")
TEST_FILE = TARGET / "src" / "lib" / "ai-isolation.ts"

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

print("=" * 70)
print(" E2E SMOKE TEST v3")
print("=" * 70)
print(f" Cible : {TEST_FILE.relative_to(TARGET)}")

before = sha(TEST_FILE)
print(f" Hash AVANT : {before[:16]}...")

for mode in ["READ_ONLY", "PROPOSE"]:
    print()
    print(f"--- Mode {mode} ---")
    r = subprocess.run(
        [sys.executable, "memolibdev_cli.py",
         "--mission", "Analyse le fichier src/lib/ai-isolation.ts",
         "--mode", mode,
         "--model", "qwen2.5-coder:7b",
         "--timeout", "120"],
        capture_output=True, text=True, timeout=240,
    )
    print(f"  Exit : {r.returncode}")
    if r.stdout:
        tail = r.stdout.strip().splitlines()[-8:]
        for line in tail:
            print(f"  > {line[:100]}")

after = sha(TEST_FILE)
print()
print("=" * 70)
print(f" Hash APRES : {after[:16]}...")
if before == after:
    print(" [OK] Aucune ecriture non autorisee")
    sys.exit(0)
else:
    print(" [KO] Fichier modifie !")
    sys.exit(1)
