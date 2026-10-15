"""
MemoLibDev — Usage Metering (contrat 6A)
========================================

Enregistrement déterministe des opérations (lecture/analyse/code) pour
audit. Aucune I/O réseau, aucune écriture dans le dépôt cible. Les
enregistrements sont conservés en mémoire (liste) et retournés sous
forme de dict sérialisable.

Contrat public :
    build_and_record(...) -> dict  (avec clés id, operation_type, status)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


_records: list[dict] = []


def build_and_record(
    *,
    request: str,
    model: str,
    selection: dict,
    metadata: dict,
    validation: dict,
    plan: dict,
    operation_type: str = "CODE",
    agent: str = "unknown",
) -> dict:
    """
    Construit un enregistrement d'usage et le conserve en mémoire.
    Retourne un dict avec au moins : id, operation_type, status, timestamp.
    """
    op_id = uuid.uuid4().hex[:16]
    verdict = validation.get("verdict", "UNKNOWN")
    status = "REJECTED" if verdict in ("REJECT", "REJECTED") else verdict

    record = {
        "id": op_id,
        "operation_type": operation_type,
        "agent": agent,
        "model": model,
        "request": request,
        "selection": selection,
        "metadata": metadata,
        "validation": validation,
        "plan": plan,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _records.append(record)
    return record


def get_records() -> list[dict]:
    """Retourne une copie de tous les enregistrements (audit)."""
    return list(_records)


def clear_records() -> None:
    """Vide les enregistrements (tests)."""
    _records.clear()
