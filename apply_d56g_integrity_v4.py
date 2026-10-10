from pathlib import Path
import shutil
import subprocess
import sys
import importlib

TARGET = Path("coder_authorization.py")
BACKUP = Path("coder_authorization.py.pre-d56g-integrity-v4")
TEMP = Path("coder_authorization.py.d56g.tmp")


def block(message):
    print("[BLOCK]", message)
    print("AUCUNE MODIFICATION EFFECTUEE")
    raise SystemExit(1)


print("============================================================")
print("D5.6-G4 — INTEGRITY BINDING")
print("============================================================")


# ============================================================
# 1. PRECHECK
# ============================================================

if not TARGET.exists():
    block("coder_authorization.py absent")

if BACKUP.exists():
    block(
        f"Backup déjà présent : {BACKUP}. "
        "Refus de remplacer automatiquement."
    )

source = TARGET.read_text(encoding="utf-8")

print("[INFO] Source :", len(source), "octets")


# ============================================================
# 2. IMPORT
# ============================================================

import_old = """from evidence_resolver_v2_2 import (
    EvidenceRecord,
    EvidenceResult,
    EvidenceStatus,
    validate_record,
)"""

import_new = """from evidence_resolver_v2_2 import (
    EvidenceRecord,
    EvidenceResult,
    EvidenceStatus,
    content_sha256,
    validate_record,
)"""

if "content_sha256" not in source:

    if import_old not in source:
        block(
            "Bloc import evidence_resolver_v2_2 inattendu."
        )

    source = source.replace(
        import_old,
        import_new,
        1,
    )

    print("[PASS] Import content_sha256 ajouté")

else:
    print("[PASS] Import content_sha256 déjà présent")


# ============================================================
# 3. HELPER
# ============================================================

if "_validate_evidence_integrity" in source:
    block(
        "Helper integrity déjà présent. "
        "Refus d'un double patch."
    )


helper = '''

def _validate_evidence_integrity(
    authorization: CoderAuthorization,
    target: ProjectTarget,
    requested_path: str,
) -> tuple[bool, str]:
    """
    D5.6-G — Lie cryptographiquement l'autorisation
    au contenu actuel du fichier evidence dans la cible.

    Fail closed :
    - chemin vide => BLOCK
    - chemin hors repository => BLOCK
    - fichier absent => BLOCK
    - lecture impossible => BLOCK
    - SHA absent => BLOCK
    - SHA différent => BLOCK
    """

    try:
        root = Path(target.git_root).resolve()

        requested = _normalize_path(requested_path)

        if not requested:
            return False, "Evidence path vide"

        candidate = (root / requested).resolve()

        try:
            candidate.relative_to(root)
        except ValueError:
            return False, "Evidence hors du repository cible"

        if not candidate.is_file():
            return False, "Fichier evidence introuvable"

        content = candidate.read_text(
            encoding="utf-8"
        )

        current_sha256 = content_sha256(content)

        authorized_sha256 = str(
            authorization.evidence_sha256
        ).strip().lower()

        if not authorized_sha256:
            return False, "Evidence SHA-256 absent"

        if current_sha256.lower() != authorized_sha256:
            return (
                False,
                (
                    "Evidence SHA-256 mismatch: "
                    f"authorized={authorized_sha256} "
                    f"current={current_sha256}"
                ),
            )

        return (
            True,
            "Evidence SHA-256 conforme",
        )

    except (OSError, UnicodeError) as exc:
        return (
            False,
            f"Impossible de vérifier l'intégrité: {exc}",
        )

'''


# ============================================================
# 4. INSERTION HELPER
# ============================================================

validate_marker = "def validate_authorization("

if source.count(validate_marker) != 1:
    block(
        "Nombre inattendu de validate_authorization()"
    )

source = source.replace(
    validate_marker,
    helper + "\n\n" + validate_marker,
    1,
)

print("[PASS] Helper integrity inséré")


# ============================================================
# 5. INSERTION DU GATE
# ============================================================

status_block = '''    if authorization.status != AuthorizationStatus.AUTHORIZED.value:
        return False, "authorization is not AUTHORIZED"
'''

if source.count(status_block) != 1:
    block(
        "Bloc AUTHORIZED réel introuvable ou ambigu."
    )

integrity_gate = '''    # D5.6-G — Integrity binding obligatoire.
    evidence_ok, evidence_reason = _validate_evidence_integrity(
        authorization,
        target,
        requested_path,
    )

    if not evidence_ok:
        return False, evidence_reason

'''

source = source.replace(
    status_block,
    status_block + "\n" + integrity_gate,
    1,
)

print("[PASS] Integrity gate inséré")


# ============================================================
# 6. POSTCONDITIONS
# ============================================================

required = [
    "from evidence_resolver_v2_2 import (",
    "content_sha256,",
    "def _validate_evidence_integrity(",
    "candidate.relative_to(root)",
    "Evidence SHA-256 mismatch:",
    "evidence_ok, evidence_reason",
]

for marker in required:
    if marker not in source:
        block(
            f"Post-condition absente : {marker}"
        )

print("[PASS] Post-conditions complètes")


# ============================================================
# 7. SYNTAX CHECK SUR TEMPORAIRE
# ============================================================

try:
    TEMP.write_text(
        source,
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
        block("Compilation du patch temporaire échouée")

    print("[PASS] Compilation temporaire")

finally:
    if TEMP.exists():
        TEMP.unlink()


# ============================================================
# 8. BACKUP
# ============================================================

shutil.copy2(
    TARGET,
    BACKUP,
)

print("[PASS] Backup :", BACKUP)


# ============================================================
# 9. REMPLACEMENT ATOMIQUE
# ============================================================

try:
    TEMP.write_text(
        source,
        encoding="utf-8",
    )

    TEMP.replace(TARGET)

except Exception as exc:

    TEMP.unlink(missing_ok=True)

    if BACKUP.exists():
        shutil.copy2(
            BACKUP,
            TARGET,
        )

    block(
        f"Écriture échouée, restauration effectuée : {exc}"
    )

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

    block(
        "Compilation finale échouée — version précédente restaurée"
    )

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
        hasattr(coder_authorization, "authorize"),
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

        shutil.copy2(
            BACKUP,
            TARGET,
        )

        block(
            f"API absente après patch : {name}"
        )

    print("[PASS] API", name)


# ============================================================
# 12. MEMOLIB READ-ONLY STATUS
# ============================================================

memo = Path(r"C:\Users\moros\memoLib")

if memo.exists():

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
print("D5.6-G4 — PATCH REUSSI")
print("============================================================")
print("Helper integrity       : OK")
print("SHA evidence binding   : OK")
print("Compilation             : OK")
print("API                     : OK")
print("MemoLib                 : NON MODIFIE")
print("Ollama                  : NON APPELE")
print("Git commit/push         : NON")
print("============================================================")
