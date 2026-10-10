from pathlib import Path
import shutil
import subprocess
import sys
import importlib

target = Path("coder_authorization.py")
backup = Path("coder_authorization.py.pre-d56g-import")

print("============================================================")
print("D5.6-G5 — IMPORT content_sha256")
print("============================================================")

if not target.exists():
    print("[BLOCK] coder_authorization.py absent")
    sys.exit(1)

if backup.exists():
    print("[BLOCK] Backup déjà présent :", backup)
    sys.exit(1)

source = target.read_text(encoding="utf-8")

old = """from evidence_resolver_v2_2 import (
    EvidenceRecord,
    EvidenceResult,
    EvidenceStatus,
    validate_record,
)"""

new = """from evidence_resolver_v2_2 import (
    EvidenceRecord,
    EvidenceResult,
    EvidenceStatus,
    content_sha256,
    validate_record,
)"""

if old not in source:
    print("[BLOCK] Bloc import attendu introuvable")
    sys.exit(1)

patched = source.replace(old, new, 1)

if patched == source:
    print("[BLOCK] Aucun changement produit")
    sys.exit(1)

if "    content_sha256," not in patched:
    print("[BLOCK] Import content_sha256 absent après patch")
    sys.exit(1)

# Backup
shutil.copy2(target, backup)
print("[PASS] Backup créé :", backup)

# Écriture temporaire
temp = target.with_suffix(".py.tmp")

try:
    temp.write_text(patched, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(temp)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(result.stderr)
        temp.unlink(missing_ok=True)
        shutil.copy2(backup, target)
        print("[RESTORE] Version précédente restaurée")
        sys.exit(1)

    temp.replace(target)

except Exception as exc:
    temp.unlink(missing_ok=True)
    shutil.copy2(backup, target)
    print("[RESTORE]", exc)
    sys.exit(1)

print("[PASS] Import écrit")
print("[PASS] Compilation")


# Test d'import réel
import coder_authorization
importlib.reload(coder_authorization)

if not hasattr(coder_authorization, "content_sha256"):
    shutil.copy2(backup, target)
    print("[RESTORE] Import Python absent")
    sys.exit(1)

if not hasattr(
    coder_authorization,
    "_validate_evidence_integrity",
):
    shutil.copy2(backup, target)
    print("[RESTORE] Helper integrity absent")
    sys.exit(1)

print("[PASS] content_sha256 disponible dans coder_authorization")
print("[PASS] _validate_evidence_integrity disponible")


# MemoLib read-only
memo = Path(r"C:\Users\moros\memoLib")

status = subprocess.run(
    ["git", "-C", str(memo), "status", "--short"],
    capture_output=True,
    text=True,
)

print("")
print("=== MEMOLIB ===")

if status.stdout.strip():
    print("[ALERTE]")
    print(status.stdout)
else:
    print("[PASS] MemoLib CLEAN")

print("")
print("============================================================")
print("D5.6-G5 — REUSSI")
print("============================================================")
print("Import content_sha256 : OK")
print("Helper integrity      : OK")
print("Compilation           : OK")
print("MemoLib               : NON MODIFIE")
print("Ollama                : NON")
print("Git                   : NON")
print("============================================================")
