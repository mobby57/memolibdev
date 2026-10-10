from __future__ import annotations

import re
import shutil
from pathlib import Path


TARGET = Path("coder_authorization.py")
BACKUP = Path("coder_authorization.py.pre-d56g-integrity")


def fail(message: str) -> None:
    raise SystemExit(f"[FAIL] {message}")


if not TARGET.is_file():
    fail(f"{TARGET} introuvable")

source = TARGET.read_text(encoding="utf-8")


# ============================================================
# 1. Vérification structurelle AVANT modification
# ============================================================

required_symbols = [
    "class CoderAuthorization",
    "def authorize(",
    "def validate_authorization(",
    "def authorization_to_dict(",
    "evidence_sha256",
]

for symbol in required_symbols:
    if symbol not in source:
        fail(f"Structure inattendue : {symbol} absent")


# Le patch ne doit être appliqué qu'une seule fois.
if "_validate_evidence_integrity(" in source:
    fail(
        "Integrity binding déjà présent. "
        "Aucun double patch autorisé."
    )


# ============================================================
# 2. Vérification de l'import
# ============================================================

if "from evidence_resolver_v2_2 import (" not in source:
    fail("Bloc evidence_resolver_v2_2 introuvable")


# Ajouter content_sha256 exactement dans l'import existant.
import_pattern = re.compile(
    r"(from evidence_resolver_v2_2 import \(\n"
    r"(?:.*\n)*?"
    r"\s*EvidenceStatus,\n)"
)

match = import_pattern.search(source)

if not match:
    fail("Import EvidenceStatus introuvable")

import_block = match.group(1)

if "content_sha256" not in import_block:
    replacement = import_block + "    content_sha256,\n"
    source = source[:match.start(1)] + replacement + source[match.end(1):]


# ============================================================
# 3. Insertion d'un helper dédié
# ============================================================

helper = r'''

def _validate_evidence_integrity(
    authorization: CoderAuthorization,
    target: ProjectTarget,
    requested_path: str,
) -> tuple[bool, str]:
    """
    D5.6-G — Integrity binding de l'evidence.

    Ne fait confiance ni au chemin ni au SHA stockés dans le certificat.

    Vérifie :
      1. chemin normalisé ;
      2. containment dans le repository cible ;
      3. existence du fichier ;
      4. lecture UTF-8 ;
      5. SHA-256 recalculé ;
      6. égalité avec le SHA autorisé.

    Fail closed sur toute anomalie.
    """
    try:
        root = Path(target.git_root).resolve()

        requested = _normalize_path(requested_path)
        candidate = (root / requested).resolve()

        # Protection contre path traversal et symlink escape.
        try:
            candidate.relative_to(root)
        except ValueError:
            return (
                False,
                "Evidence hors du repository cible.",
            )

        if not candidate.is_file():
            return (
                False,
                "Fichier evidence introuvable dans la cible.",
            )

        current_content = candidate.read_text(
            encoding="utf-8"
        )

        current_sha256 = content_sha256(current_content)

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

# Insérer juste avant validate_authorization.
marker = "\ndef validate_authorization(\n"

if marker not in source:
    fail("Point d'insertion validate_authorization introuvable")

source = source.replace(
    marker,
    helper + marker,
    1,
)


# ============================================================
# 4. Insérer le contrôle dans validate_authorization
# ============================================================

validation_marker = """    if authorization.status != AuthorizationStatus.AUTHORIZED.value:
        return False, "Autorisation non AUTHORIZED."

"""

if validation_marker not in source:
    fail(
        "Début de validate_authorization introuvable "
        "ou structure modifiée."
    )


integrity_call = """    # D5.6-G — Integrity binding obligatoire.
    evidence_ok, evidence_reason = _validate_evidence_integrity(
        authorization,
        target,
        requested_path,
    )

    if not evidence_ok:
        return False, evidence_reason

"""

source = source.replace(
    validation_marker,
    validation_marker + integrity_call,
    1,
)


# ============================================================
# 5. Vérifications post-patch en mémoire
# ============================================================

for symbol in [
    "def _validate_evidence_integrity(",
    "content_sha256(",
    "Evidence SHA-256 mismatch:",
    "Evidence SHA-256 absent de l'autorisation.",
    "candidate.relative_to(root)",
    "evidence_ok, evidence_reason",
]:
    if symbol not in source:
        fail(f"Post-condition absente : {symbol}")


# ============================================================
# 6. Backup uniquement maintenant
# ============================================================

if BACKUP.exists():
    fail(
        f"Backup déjà présent : {BACKUP}. "
        "Refus de l'écraser automatiquement."
    )

shutil.copy2(TARGET, BACKUP)

print(f"[BACKUP] {BACKUP}")


# ============================================================
# 7. Écriture
# ============================================================

TARGET.write_text(source, encoding="utf-8")

print("[PATCH] coder_authorization.py")
print("[PASS] Integrity binding installé")
print("[PASS] Patch unique vérifié")
