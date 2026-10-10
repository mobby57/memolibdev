from pathlib import Path
import shutil
import sys

target = Path("coder_authorization.py")
backup = Path("coder_authorization.py.pre-d56g-integrity")

print("=== D5.6-G3 PATCH ===")

if not target.exists():
    raise SystemExit("[BLOCK] coder_authorization.py absent")

source = target.read_text(encoding="utf-8")

print("[INFO] Taille source :", len(source))


# ------------------------------------------------------------
# 1. IMPORT
# ------------------------------------------------------------

if "content_sha256" not in source:

    old = (
        "from evidence_resolver_v2_2 import (\n"
        "    EvidenceRecord,\n"
        "    EvidenceResult,\n"
        "    EvidenceStatus,\n"
        "    validate_record,\n"
        ")\n"
    )

    new = (
        "from evidence_resolver_v2_2 import (\n"
        "    EvidenceRecord,\n"
        "    EvidenceResult,\n"
        "    EvidenceStatus,\n"
        "    content_sha256,\n"
        "    validate_record,\n"
        ")\n"
    )

    if old not in source:
        print("[BLOCK] Bloc import exact introuvable")
        print("        Aucun fichier modifié")
        sys.exit(1)

    source = source.replace(old, new, 1)
    print("[PASS] Import content_sha256 préparé")

else:
    print("[INFO] content_sha256 déjà présent")


# ------------------------------------------------------------
# 2. HELPER
# ------------------------------------------------------------

helper_marker = "def _validate_evidence_integrity("

if helper_marker not in source:

    helper = '''

def _validate_evidence_integrity(
    authorization: CoderAuthorization,
    target: ProjectTarget,
    requested_path: str,
) -> tuple[bool, str]:
    """
    D5.6-G — Integrity binding de l'evidence.

    Le SHA présent dans le certificat est comparé au
    contenu actuel du fichier dans le ProjectTarget.
    """

    try:
        root = Path(target.git_root).resolve()

        requested = _normalize_path(requested_path)

        if not requested:
            return False, "Evidence path vide."

        candidate = (root / requested).resolve()

        try:
            candidate.relative_to(root)
        except ValueError:
            return False, "Evidence hors du repository cible."

        if not candidate.is_file():
            return False, "Fichier evidence introuvable dans la cible."

        content = candidate.read_text(encoding="utf-8")

        current_sha256 = content_sha256(content)

        authorized_sha256 = str(
            authorization.evidence_sha256
        ).strip().lower()

        if not authorized_sha256:
            return False, "Evidence SHA-256 absent de l'autorisation."

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
            "Evidence SHA-256 conforme au contenu actuel.",
        )

    except (OSError, UnicodeError) as exc:
        return (
            False,
            f"Impossible de vérifier l'intégrité de l'evidence: {exc}",
        )

'''

    marker = "def validate_authorization("

    if marker not in source:
        print("[BLOCK] validate_authorization introuvable")
        print("        Aucun fichier modifié")
        sys.exit(1)

    source = source.replace(
        marker,
        helper + "\n\n" + marker,
        1,
    )

    print("[PASS] Helper integrity préparé")

else:
    print("[INFO] Helper déjà présent")


# ------------------------------------------------------------
# 3. APPEL DU HELPER
# ------------------------------------------------------------

call_marker = "evidence_ok, evidence_reason = _validate_evidence_integrity("

if call_marker not in source:

    status_marker = (
        '    if authorization.status != '
        'AuthorizationStatus.AUTHORIZED.value:\n'
        '        return False, "Autorisation non AUTHORIZED."\n'
    )

    if status_marker not in source:
        print("[BLOCK] Contrôle AuthorizationStatus introuvable")
        print("        Aucun fichier modifié")
        sys.exit(1)

    call = '''
    # D5.6-G — Integrity binding obligatoire.
    evidence_ok, evidence_reason = _validate_evidence_integrity(
        authorization,
        target,
        requested_path,
    )

    if not evidence_ok:
        return False, evidence_reason

'''

    source = source.replace(
        status_marker,
        status_marker + "\n" + call,
        1,
    )

    print("[PASS] Appel integrity préparé")

else:
    print("[INFO] Appel integrity déjà présent")


# ------------------------------------------------------------
# 4. VALIDATION AVANT ÉCRITURE
# ------------------------------------------------------------

required_after_patch = [
    "content_sha256",
    "def _validate_evidence_integrity(",
    "candidate.relative_to(root)",
    "Evidence SHA-256 mismatch:",
    "evidence_ok, evidence_reason",
]

for marker in required_after_patch:
    if marker not in source:
        print("[BLOCK] Post-condition absente :", marker)
        print("        Aucun fichier modifié")
        sys.exit(1)

print("[PASS] Toutes les post-conditions sont présentes")


# ------------------------------------------------------------
# 5. BACKUP
# ------------------------------------------------------------

if backup.exists():
    print("[BLOCK] Backup déjà présent :", backup)
    print("        Aucun fichier modifié")
    sys.exit(1)

shutil.copy2(target, backup)

print("[PASS] Backup créé :", backup)


# ------------------------------------------------------------
# 6. ÉCRITURE
# ------------------------------------------------------------

temp = target.with_name(target.name + ".tmp")

try:
    temp.write_text(source, encoding="utf-8")
    temp.replace(target)
except Exception:
    temp.unlink(missing_ok=True)
    raise

print("[PASS] coder_authorization.py écrit")


# ------------------------------------------------------------
# 7. COMPILATION
# ------------------------------------------------------------

import py_compile

try:
    py_compile.compile(
        str(target),
        doraise=True,
    )
except Exception as exc:
    print("[FAIL] Compilation :", exc)

    # Restauration automatique depuis le backup.
    shutil.copy2(backup, target)

    print("[RESTORE] Version précédente restaurée")
    sys.exit(1)

print("[PASS] Python compile")


# ------------------------------------------------------------
# 8. API
# ------------------------------------------------------------

import importlib
import coder_authorization

importlib.reload(coder_authorization)

if not hasattr(
    coder_authorization,
    "_validate_evidence_integrity",
):
    print("[FAIL] Helper absent après import")

    shutil.copy2(backup, target)

    print("[RESTORE] Version précédente restaurée")
    sys.exit(1)

print("[PASS] Helper disponible")


print("")
print("============================================================")
print("D5.6-G3 — PATCH REUSSI")
print("============================================================")
print("MemoLib : NON MODIFIE")
print("Ollama  : NON")
print("Git     : NON")
print("============================================================")
