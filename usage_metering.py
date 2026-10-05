"""
MemoLibDev — 6A : Usage Metering
================================

Module AUTONOME de mesure d'usage.

Rôle unique : transformer ce qui s'est RÉELLEMENT passé pendant une
opération agent (sélection déterministe + métadonnées du modèle +
validation) en une OPÉRATION MESURÉE normalisée.

Principe directeur (règle d'or MemoLibDev) :

    On ne mélange PAS l'agent et le billing.

Conséquences concrètes de cette règle, appliquées ici :

  * AUCUN prix.
  * AUCUN crédit facturé.
  * AUCUN coefficient de conversion.
  * AUCUNE dépendance à Stripe ni à un ledger.

Ce module ne fait QUE MESURER des *unités de travail* brutes :
tokens, caractères, fichiers, étapes de plan, durée. Les coefficients
crédits (6B/6D) seront calibrés PLUS TARD, à partir des coûts réels
agrégés dans le journal produit ici.

Le contrat de données `agent_operations` est figé dans ce fichier
(voir OPERATION_SCHEMA_VERSION et build_operation).
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import uuid


# ============================================================
# CONTRAT DE DONNÉES — agent_operations (figé)
# ============================================================
#
# Toute évolution du schéma DOIT incrémenter cette version.
# Les consommateurs (6B ledger, 6C réservation, 6E dashboard)
# s'appuient sur ce numéro pour rester compatibles.

OPERATION_SCHEMA_VERSION = "6A.1"


# Types d'opération reconnus. Le Decision Agent produit "DECISION".
# Les autres sont réservés pour 5G/5H/5I et au-delà.
OPERATION_TYPES = {
    "DECISION",
    "QUESTION",
    "AUDIT",
    "PLAN",
    "CODE",
    "REVIEW",
    "TEST",
    "FULL_AGENT",
}


# États du cycle de vie d'une opération mesurée.
# NB : ce sont les états de l'OPÉRATION, pas du plan agent.
OPERATION_STATUSES = {
    "COMPLETED",      # opération allée jusqu'au bout
    "TRUNCATED",      # génération modèle tronquée
    "REJECTED",       # plan rejeté par la validation
    "FAILED",         # erreur technique
}


# Journal append-only des opérations mesurées.
OPERATIONS_LOG = Path(__file__).resolve().parent / "reports" / "operations.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _derive_status(
    validation: dict,
    metadata: dict,
) -> str:
    """
    Déduit le statut MESURÉ de l'opération à partir de la validation
    et des métadonnées du modèle. Déterministe, sans effet de bord.
    """

    if metadata.get("generation_truncated"):
        return "TRUNCATED"

    verdict = (validation or {}).get("verdict")

    if verdict == "REJECT":
        return "REJECTED"

    # ACCEPTABLE, REVIEW, ou tout verdict non bloquant : l'opération
    # a bien été menée à son terme (la décision humaine vient après).
    return "COMPLETED"


def _count_plan_steps(plan: dict) -> int:
    steps = (plan or {}).get("proposed_steps")

    if isinstance(steps, list):
        return len(steps)

    return 0


def build_operation(
    *,
    request: str,
    model: str,
    selection: dict,
    metadata: dict,
    validation: dict,
    operation_type: str = "DECISION",
    agent: str = "decision_agent",
    workspace_id: str = "local",
    user_id: str = "local",
) -> dict:
    """
    Construit UNE opération mesurée normalisée (contrat agent_operations).

    Entrées = ce qui s'est réellement passé :
      - selection : le bloc `selection` produit par le Decision Agent
      - metadata  : les métadonnées renvoyées par Ollama
      - validation: le verdict du garde-fou anti-hallucination

    Sortie = un dict JSON-sérialisable, SANS aucune notion de prix.
    """

    if operation_type not in OPERATION_TYPES:
        raise ValueError(
            f"operation_type inconnu : {operation_type!r}"
        )

    selection = selection or {}
    metadata = metadata or {}
    validation = validation or {}

    status = _derive_status(validation, metadata)

    # --- Unités de travail BRUTES (ce que l'on mesure) -----------
    prompt_tokens = _coerce_int(metadata.get("prompt_eval_count"))
    output_tokens = _coerce_int(metadata.get("eval_count"))
    total_tokens = prompt_tokens + output_tokens

    usage = {
        # modèle / génération
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "response_chars": _coerce_int(metadata.get("response_chars")),
        "duration_seconds": _coerce_float(metadata.get("elapsed_seconds")),
        "generation_truncated": bool(metadata.get("generation_truncated")),

        # sélection déterministe (travail d'inspection/contexte)
        "candidate_files": _coerce_int(selection.get("candidate_count")),
        "selected_files": _coerce_int(selection.get("selected_count")),
        "primary_files": _coerce_int(selection.get("primary_count")),
        "secondary_files": _coerce_int(selection.get("secondary_count")),
        "context_chars": _coerce_int(selection.get("context_chars")),
        "context_estimated_tokens": _coerce_int(
            selection.get("context_estimated_tokens")
        ),

        # raisonnement / plan
        "plan_steps": _count_plan_steps(validation.get("_plan_ref", {})),
    }

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "id": str(uuid.uuid4()),
        "workspace_id": workspace_id,
        "user_id": user_id,

        "operation_type": operation_type,
        "agent": agent,
        "model": model,

        "status": status,

        "request": request,

        "usage": usage,

        # Traçabilité de la décision de validation (sans contenu lourd).
        "validation_verdict": validation.get("verdict"),
        "validation_reason": validation.get("reason"),

        # Pas de billing ici : ces champs existent dans le contrat mais
        # restent explicitement NON RENSEIGNÉS en 6A. Ils seront remplis
        # par 6B (ledger) / 6D (billing) une fois les coefficients fixés.
        "estimated_credits": None,
        "reserved_credits": None,
        "consumed_credits": None,

        "created_at": _utc_now_iso(),
    }


def record_operation(
    operation: dict,
    log_path: Path | None = None,
) -> Path:
    """
    Émet l'opération mesurée dans le journal append-only (JSONL).

    Une opération = une ligne JSON. Jamais de réécriture, jamais de
    suppression : c'est un journal immuable, source de vérité pour la
    calibration future des crédits.
    """

    path = log_path or OPERATIONS_LOG
    path.parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(operation, ensure_ascii=False)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")

    return path


def build_and_record(
    *,
    request: str,
    model: str,
    selection: dict,
    metadata: dict,
    validation: dict,
    plan: dict | None = None,
    operation_type: str = "DECISION",
    agent: str = "decision_agent",
    workspace_id: str = "local",
    user_id: str = "local",
    log_path: Path | None = None,
) -> dict:
    """
    Raccourci : construit l'opération ET l'écrit au journal.

    `plan` est accepté pour compter les étapes proposées sans coupler
    le contrat au format exact du plan ailleurs dans le code.
    """

    # On fait transiter le plan via validation["_plan_ref"] pour que
    # build_operation puisse compter les étapes sans signature élargie.
    enriched_validation = dict(validation or {})
    enriched_validation["_plan_ref"] = plan or {}

    operation = build_operation(
        request=request,
        model=model,
        selection=selection,
        metadata=metadata,
        validation=enriched_validation,
        operation_type=operation_type,
        agent=agent,
        workspace_id=workspace_id,
        user_id=user_id,
    )

    record_operation(operation, log_path=log_path)

    return operation
