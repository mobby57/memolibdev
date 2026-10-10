from pathlib import Path
import shutil
import subprocess
import sys
import importlib

TARGET = Path("coder_authorization.py")
BACKUP = Path("coder_authorization.py.pre-d56g-reason-v7")
TEMP = Path("coder_authorization.py.d56g-reason.tmp")

print("============================================================")
print("D5.6-G7 — AUTHORIZATION REASON INTEGRITY")
print("============================================================")

if not TARGET.exists():
    print("[BLOCK] coder_authorization.py absent")
    sys.exit(1)

if BACKUP.exists():
    print("[BLOCK] Backup déjà présent :", BACKUP)
    sys.exit(1)

source = TARGET.read_text(encoding="utf-8")

print("[INFO] Source :", len(source), "octets")

# Refus double patch
if "authorization reason does not match canonical authorized reason" in source:
    print("[BLOCK] Gate reason déjà présent")
    sys.exit(1)

# Motif exact actuellement produit par authorize()
canonical_reason = (
    "Cible, evidence ACCEPTED, provenance, scope, action "
    "et validation humaine concordent."
)

# Bloc exact de retour AUTHORIZED
authorized_return = '''        reason=(
            "Cible, evidence ACCEPTED, provenance, scope, action "
            "et validation humaine concordent."
        ),
'''

if source.count(authorized_return) != 1:
    print("[BLOCK] Motif AUTHORIZED attendu introuvable ou ambigu")
    print("[INFO] occurrences :", source.count(authorized_return))
    sys.exit(1)

print("[PASS] Motif AUTHORIZED identifié")

# Contrôle à insérer juste après le contrôle du statut.
status_gate = '''    if authorization.status != AuthorizationStatus.AUTHORIZED.value:
        return False, "authorization is not AUTHORIZED"
'''

if source.count(status_gate) != 1:
    print("[BLOCK] Gate status AUTHORIZED introuvable ou ambigu")
    sys.exit(1)

reason_gate = f'''    # D5.6-G7 — Reason binding obligatoire.
    # Pour une autorisation AUTHORIZED, le motif doit être
    # exactement celui produit par authorize().
    canonical_authorized_reason = (
        "{canonical_reason}"
    )

    if authorization.reason != canonical_authorized_reason:
        return False, "authorization reason does not match canonical authorized reason"

'''

patched = source.replace(
    status_gate,
    status_gate + "\n" + reason_gate,
    1,
)

if patched == source:
    print("[BLOCK] Aucun changement produit")
    sys.exit(1)

print("[PASS] Gate reason inséré")

# Post-conditions
required = [
    "D5.6-G7 — Reason binding obligatoire.",
    "canonical_authorized_reason",
    "authorization reason does not match canonical authorized reason",
]

for marker in required:
    if marker not in patched:
        print("[BLOCK] Post-condition absente :", marker)
        sys.exit(1)

print("[PASS] Post-conditions complètes")

# Compilation temporaire
try:
    TEMP.write_text(patched, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(TEMP)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        print("[BLOCK] Compilation temporaire échouée")
        sys.exit(1)

    print("[PASS] Compilation temporaire")

finally:
    TEMP.unlink(missing_ok=True)

# Backup
shutil.copy2(TARGET, BACKUP)
print("[PASS] Backup :", BACKUP)

# Remplacement avec restauration automatique
try:
    TEMP.write_text(patched, encoding="utf-8")
    TEMP.replace(TARGET)

except Exception as exc:
    TEMP.unlink(missing_ok=True)
    shutil.copy2(BACKUP, TARGET)
    print("[RESTORE] Écriture échouée :", exc)
    sys.exit(1)

print("[PASS] coder_authorization.py remplacé")

# Compilation finale
result = subprocess.run(
    [sys.executable, "-m", "py_compile", str(TARGET)],
    capture_output=True,
    text=True,
)

if result.returncode != 0:
    print(result.stdout)
    print(result.stderr)
    shutil.copy2(BACKUP, TARGET)
    print("[RESTORE] Compilation finale échouée")
    sys.exit(1)

print("[PASS] Compilation finale")

# API
import coder_authorization
importlib.reload(coder_authorization)

checks = {
    "_validate_evidence_integrity":
        hasattr(coder_authorization, "_validate_evidence_integrity"),
    "authorize":
        hasattr(coder_authorization, "authorize"),
    "validate_authorization":
        hasattr(coder_authorization, "validate_authorization"),
    "authorization_to_dict":
        hasattr(coder_authorization, "authorization_to_dict"),
}

for name, ok in checks.items():
    if not ok:
        shutil.copy2(BACKUP, TARGET)
        print("[RESTORE] API absente :", name)
        sys.exit(1)

    print("[PASS] API", name)

# MemoLib
memo = Path(r"C:\Users\moros\memoLib")

status = subprocess.run(
    ["git", "-C", str(memo), "status", "--short"],
    capture_output=True,
    text=True,
)

print("")
print("=== MEMOLIB ===")

if status.stdout.strip():
    print("[ALERTE] MemoLib possède des modifications :")
    print(status.stdout)
else:
    print("[PASS] MemoLib CLEAN")

print("")
print("============================================================")
print("D5.6-G7 — PATCH REUSSI")
print("============================================================")
print("Reason AUTHORIZED canonique : OK")
print("Gate falsification reason     : OK")
print("Compilation                   : OK")
print("API                           : OK")
print("MemoLib                       : NON MODIFIE")
print("Ollama                        : NON APPELE")
print("Git commit/push               : NON")
print("============================================================")
