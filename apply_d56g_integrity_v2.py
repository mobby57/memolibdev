from __future__ import annotations

import shutil
from pathlib import Path


TARGET = Path("coder_authorization.py")
BACKUP = Path("coder_authorization.py.pre-d56g-integrity")


def stop(message: str) -> None:
    raise SystemExit(f"[BLOCK] {message}")


# ============================================================
# 1. Lecture et préconditions
# ============================================================

if not TARGET.is_file():
    stop("coder_authorization.py introuvable")

source = TARGET.read_text(encoding="utf-8")

required = [
    "class CoderAuthorization",
    "def authorize(",
    "def validate_authorization(",
    "def authorization_to_dict(",
    "evidence_sha256",
    "from evidence_resolver_v2_2 import (",
]

for marker in required:
    if marker not in source:
        stop(f"Structure inattendue : {marker}")

if "_validate_evidence_integrity" in source:
    stop("Integrity binding déjà présent — aucun double patch")

if BACKUP.exists():
    stop(
        f"Backup déjà présent : {BACKUP}. "
        "Aucune écriture automatique."
    )


# ============================================================
# 2. Vérifier précisément l'import
# ============================================================

import_start = source.find(
    "from evidence_resolver_v2_2 import ("
)

if import_start < 0:
    stop("Import evidence_resolver_v2_2 introuvable")

import_end = source.find(
    "\n)",
    import_start,
)

if import_end < 0:
    stop("Fin du bloc evidence_resolver_v2_2 introuvable")

import_end += 2

import_block = source[import_start:import_end]

if "content_sha256" not in import_block:
    new_import_block = import_block.replace(
        "    EvidenceStatus,\n",
        "    EvidenceStatus,\n    content_sha256,\n",
        1,
    )

    if new_import_block == import_block:
        stop(
            "EvidenceStatus absent du bloc d'import : "
            "structure inattendue"
        )

    source = (
        source[:import_start]
        + new_import_block
        + source[import_end:]
    )


# ============================================================
# 3. Helper d'intégrité
# ============================================================

helper = '''

def _validate_evidence_integrity(
    authorization: CoderAuthorization,
    target: ProjectTarget,
    requested_path: str,
) -> tuple[bool, str]:
    """
    D5.6-G — Vérifie que le SHA du certificat correspond
    exactement au contenu actuel du fichier dans la cible.

    Fail closed :
      - chemin hors repository -> BLOCK
      - fichier absent -> BLOCK
      - lecture impossible -> BLOCK
      - SHA absent -> BLOCK
      - SHA différent -> BLOCK
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

        content = candidate.read_text(
            encoding="utf-8"
        )

        current_sha256 = content_sha256(content)
        authorized_sha256 = str(
            authorization.evidence_sha256
        ).strip().lower()

        if not authorized_sha256:
            return (
                False,
                "Evidence SHA-256 absent de l'autorisation.",
            )

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

validation_marker = "\ndef validate_authorization(\n"

if validation_marker not in source:
    stop(
        "Signature validate_authorization introuvable. "
        "Aucune modification effectuée."
    )

source = source.replace(
    validation_marker,
    helper + validation_marker,
    1,
)


# ============================================================
# 4. Insertion du contrôle
# ============================================================

authorization_marker = (
    '    if authorization.status != '
    'AuthorizationStatus.AUTHORIZED.value:\n'
    '        return False, "Autorisation non AUTHORIZED."\n'
)

if authorization_marker not in source:
    stop(
        "Contrôle AuthorizationStatus attendu introuvable. "
        "Aucune modification effectuée."
    )

integrity_call = '''    # D5.6-G — Integrity binding obligatoire.
    evidence_ok, evidence_reason = _validate_evidence_integrity(
        authorization,
        target,
        requested_path,
    )

    if not evidence_ok:
        return False, evidence_reason

'''

source = source.replace(
    authorization_marker,
    authorization_marker + "\n" + integrity_call,
    1,
)


# ============================================================
# 5. Vérification du résultat AVANT écriture
# ============================================================

checks = [
    "def _validate_evidence_integrity(",
    "content_sha256(content)",
    "candidate.relative_to(root)",
    "Evidence SHA-256 mismatch:",
    "Evidence SHA-256 absent de l'autorisation.",
    "evidence_ok, evidence_reason",
]

for marker in checks:
    if marker not in source:
        stop(
            f"Post-condition absente : {marker}. "
            "Aucune modification effectuée."
        )


# ============================================================
# 6. Backup
# ============================================================

shutil.copy2(TARGET, BACKUP)

print("[PASS] Backup créé :", BACKUP)


# ============================================================
# 7. Écriture atomique
# ============================================================

TEMP = TARGET.with_suffix(".py.tmp")

try:
    TEMP.write_text(source, encoding="utf-8")
    TEMP.replace(TARGET)
except Exception:
    TEMP.unlink(missing_ok=True)
    raise


print("[PASS] coder_authorization.py modifié")
print("[PASS] Integrity binding installé")
