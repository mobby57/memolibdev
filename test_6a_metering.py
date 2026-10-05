"""
Test 6A — rejoue le metering sur un rapport Decision Agent réel,
SANS solliciter Ollama. Journal isolé pour ne pas polluer la prod.
"""

from pathlib import Path
import json

from usage_metering import (
    build_and_record,
    OPERATION_SCHEMA_VERSION,
    OPERATION_TYPES,
    OPERATION_STATUSES,
)

HERE = Path(__file__).resolve().parent
REPORT = HERE / "reports" / "decision-5f-20261005-112023.json"
TEST_LOG = HERE / "reports" / "operations.test.jsonl"


def main() -> int:
    if TEST_LOG.exists():
        TEST_LOG.unlink()

    report = json.loads(REPORT.read_text(encoding="utf-8"))

    op = build_and_record(
        request=report["request"],
        model=report["model"],
        selection=report["selection"],
        metadata=report["metadata"],
        validation=report["validation"],
        plan=report["plan"],
        operation_type="DECISION",
        agent="decision_agent",
        log_path=TEST_LOG,
    )

    print("SCHEMA_VERSION :", OPERATION_SCHEMA_VERSION)
    print("OPÉRATION MESURÉE :")
    print(json.dumps(op, indent=2, ensure_ascii=False))

    # --- Assertions de contrat ----------------------------------
    assert op["schema_version"] == OPERATION_SCHEMA_VERSION
    assert op["operation_type"] in OPERATION_TYPES
    assert op["status"] in OPERATION_STATUSES
    assert isinstance(op["id"], str) and len(op["id"]) == 36

    # Metering pur : aucun crédit renseigné en 6A.
    assert op["estimated_credits"] is None
    assert op["reserved_credits"] is None
    assert op["consumed_credits"] is None

    u = op["usage"]
    # Les unités mesurées correspondent au rapport réel.
    assert u["prompt_tokens"] == report["metadata"]["prompt_eval_count"]
    assert u["output_tokens"] == report["metadata"]["eval_count"]
    assert u["total_tokens"] == u["prompt_tokens"] + u["output_tokens"]
    assert u["selected_files"] == report["selection"]["selected_count"]
    assert u["candidate_files"] == report["selection"]["candidate_count"]
    assert u["context_chars"] == report["selection"]["context_chars"]

    # Le rapport réel avait un verdict ACCEPTABLE non tronqué -> COMPLETED.
    assert op["status"] == "COMPLETED"

    # --- Append-only : une ligne par écriture -------------------
    build_and_record(
        request=report["request"],
        model=report["model"],
        selection=report["selection"],
        metadata=report["metadata"],
        validation=report["validation"],
        plan=report["plan"],
        log_path=TEST_LOG,
    )

    lines = [
        l for l in TEST_LOG.read_text(encoding="utf-8").splitlines() if l.strip()
    ]
    assert len(lines) == 2, f"attendu 2 lignes, obtenu {len(lines)}"
    for l in lines:
        json.loads(l)  # chaque ligne est un JSON valide

    print()
    print("JOURNAL :", TEST_LOG.name, "->", len(lines), "lignes (append-only OK)")
    print("TOUTES LES ASSERTIONS PASSENT.")

    # Vérifier aussi la dérivation TRUNCATED et REJECTED.
    trunc_meta = dict(report["metadata"])
    trunc_meta["generation_truncated"] = True
    op_trunc = build_and_record(
        request="x", model="m",
        selection=report["selection"], metadata=trunc_meta,
        validation={"verdict": "REVIEW"}, plan={}, log_path=TEST_LOG,
    )
    assert op_trunc["status"] == "TRUNCATED"

    op_rej = build_and_record(
        request="x", model="m",
        selection=report["selection"], metadata=report["metadata"],
        validation={"verdict": "REJECT", "reason": "test"}, plan={},
        log_path=TEST_LOG,
    )
    assert op_rej["status"] == "REJECTED"

    print("DÉRIVATION STATUT : COMPLETED / TRUNCATED / REJECTED OK.")

    TEST_LOG.unlink()  # nettoyage
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
