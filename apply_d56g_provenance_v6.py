from pathlib import Path
import shutil
import subprocess
import sys
import importlib

TARGET = Path("coder_authorization.py")
BACKUP = Path("coder_authorization.py.pre-d56g-provenance-v6")
TEMP = Path("coder_authorization.py.d56g-provenance.tmp")

print("============================================================")
print("D5.6-G6 — PROVENANCE INTEGRITY")
print("============================================================")


# ============================================================
# 1. PRECHECK
# ============================================================

if not TARGET.exists():
    print("[BLOCK] coder_authorization.py absent")
    sys.exit(1)

if BACKUP.exists():
    print("[BLOCK] Backup déjà présent :", BACKUP)
    sys.exit(1)

source = TARGET.read_text(encoding="utf-8")

print("[INFO] Source :", len(source), "octets")


# ============================================================
# 2. REFUS DOUBLE PATCH
# ============================================================

if "authorization provenance is not RESOLVED" in source:
    print("[BLOCK] Gate provenance déjà présent")
    sys.exit(1)


# ============================================================
# 3. LOCALISATION DU GATE EVIDENCE
# ============================================================

evidence_gate = '''    if authorization.evidence_status != EvidenceStatus.ACCEPTED:
        return False, "authorization evidence is not ACCEPTED"
'''

if source.count(evidence_gate) != 1:
    print("[BLOCK] Gate EvidenceStatus attendu introuvable ou ambigu")
    sys.exit(1)

print("[PASS] Gate evidence identifié")


# ============================================================
# 4. CONSTRUCTION DU GATE PROVENANCE
# ============================================================

provenance_gate = '''    # D5.6-G — Provenance binding obligatoire.
    if authorization.provenance_status != ProvenanceStatus.RESOLVED.value:
        return False, "authorization provenance is not RESOLVED"

    provenance_source = _normalize_path(
        authorization.provenance_source_path or ""
    )

    provenance_resolved = _normalize_path(
        authorization.provenance_resolved_path or ""
    )

    if not provenance_source:
        return False, "authorization provenance source is missing"

    if not provenance_resolved:
        return False, "authorization provenance resolved path is missing"

    if provenance_resolved != requested:
        return False, "authorization provenance resolved path differs from authorized path"

'''


# ============================================================
# 5. INSERTION
# ============================================================

patched = source.replace(
    evidence_gate,
    evidence_gate + "\n" + provenance_gate,
    1,
)

if patched == source:
    print("[BLOCK] Aucun changement produit")
    sys.exit(1)

print("[PASS] Gate provenance inséré")


# ============================================================
# 6. POST-CONDITIONS
# ============================================================

required = [
    "authorization provenance is not RESOLVED",
    "authorization provenance source is missing",
    "authorization provenance resolved path is missing",
    "authorization provenance resolved path differs from authorized path",
]

for marker in required:
    if marker not in patched:
        print("[BLOCK] Post-condition absente :", marker)
        sys.exit(1)

print("[PASS] Post-conditions complètes")


# ============================================================
# 7. COMPILATION TEMPORAIRE
# ============================================================

try:
    TEMP.write_text(
        patched,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(TEMP),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        TEMP.unlink(missing_ok=True)
        print("[BLOCK] Compilation temporaire échouée")
        sys.exit(1)

    print("[PASS] Compilation temporaire")

finally:
    TEMP.unlink(missing_ok=True)


# ============================================================
# 8. BACKUP
# ============================================================

shutil.copy2(
    TARGET,
    BACKUP,
)

print("[PASS] Backup :", BACKUP)


# ============================================================
# 9. REMPLACEMENT
# ============================================================

try:
    TEMP.write_text(
        patched,
        encoding="utf-8",
    )

    TEMP.replace(TARGET)

except Exception as exc:

    TEMP.unlink(missing_ok=True)

    shutil.copy2(
        BACKUP,
        TARGET,
    )

    print("[RESTORE] Écriture échouée :", exc)
    sys.exit(1)

print("[PASS] coder_authorization.py remplacé")


# ============================================================
# 10. COMPILE FINAL
# ============================================================

result = subprocess.run(
    [
        sys.executable,
        "-m",
        "py_compile",
        str(TARGET),
    ],
    capture_output=True,
    text=True,
)

if result.returncode != 0:

    print(result.stdout)
    print(result.stderr)

    shutil.copy2(
        BACKUP,
        TARGET,
    )

    print("[RESTORE] Compilation finale échouée")
    sys.exit(1)

print("[PASS] Compilation finale")


# ============================================================
# 11. API
# ============================================================

import coder_authorization
importlib.reload(coder_authorization)

checks = {
    "_validate_evidence_integrity":
        hasattr(
            coder_authorization,
            "_validate_evidence_integrity",
        ),
    "authorize":
        hasattr(
            coder_authorization,
            "authorize",
        ),
    "validate_authorization":
        hasattr(
            coder_authorization,
            "validate_authorization",
        ),
    "authorization_to_dict":
        hasattr(
            coder_authorization,
            "authorization_to_dict",
        ),
}

for name, ok in checks.items():

    if not ok:
        shutil.copy2(BACKUP, TARGET)
        print("[RESTORE] API absente :", name)
        sys.exit(1)

    print("[PASS] API", name)


# ============================================================
# 12. MEMOLIB
# ============================================================

memo = Path(r"C:\Users\moros\memoLib")

status = subprocess.run(
    [
        "git",
        "-C",
        str(memo),
        "status",
        "--short",
    ],
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
print("D5.6-G6 — PATCH REUSSI")
print("============================================================")
print("Provenance status       : OK")
print("Provenance source       : OK")
print("Provenance resolved     : OK")
print("Compilation             : OK")
print("API                     : OK")
print("MemoLib                 : NON MODIFIE")
print("Ollama                  : NON APPELE")
print("Git commit/push         : NON")
print("============================================================")
