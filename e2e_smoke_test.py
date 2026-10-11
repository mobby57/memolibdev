# e2e_smoke_test.py — Verifie que la chaine ne touche pas au fichier cible
import subprocess, hashlib, sys
from pathlib import Path

TARGET = Path(r"C:\Users\moros\Desktop\memolib")

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

print("=" * 60)
print(" E2E SMOKE TEST")
print("=" * 60)

# 1. Trouver un fichier .ts quelconque dans src/lib
candidates = list((TARGET / "src" / "lib").rglob("*.ts"))
if not candidates:
    print("  [KO] Aucun fichier .ts dans src/lib/")
    sys.exit(1)

# Prend le premier fichier non-test, taille > 0
TEST_FILE = None
for c in candidates:
    if "__tests__" in str(c) or ".test." in c.name or ".spec." in c.name:
        continue
    if c.stat().st_size > 100:
        TEST_FILE = c
        break

if TEST_FILE is None:
    print("  [KO] Aucun fichier .ts utilisable")
    sys.exit(1)

print(f"  Cible choisie : {TEST_FILE.relative_to(TARGET)}")
print(f"  Taille        : {TEST_FILE.stat().st_size} octets")

before = sha(TEST_FILE)
print(f"  Hash AVANT    : {before[:16]}...")

# 2. Lancer une mission d'analyse (ne doit PAS ecrire)
print()
print("  Lancement : mission ANALYSER (read-only)")
print("  ---")

r = subprocess.run(
    [sys.executable, "memolibdev_cli.py",
     f"Analyse le fichier {TEST_FILE.relative_to(TARGET)}"],
    capture_output=True, text=True, timeout=120,
)

print(f"  Exit code : {r.returncode}")
if r.stdout:
    tail = r.stdout.strip().splitlines()[-5:]
    for line in tail:
        print(f"    {line}")

# 3. Verifier que rien n'a change
after = sha(TEST_FILE)
print()
print(f"  Hash APRES    : {after[:16]}...")

if before == after:
    print()
    print("  [OK] AUCUNE ECRITURE NON AUTORISEE")
    print("  [OK] La chaine respecte le contrat read-only")
    sys.exit(0)
else:
    print()
    print("  [KO] FICHIER MODIFIE SANS AUTORISATION")
    print(f"       Avant : {before}")
    print(f"       Apres : {after}")
    sys.exit(1)
