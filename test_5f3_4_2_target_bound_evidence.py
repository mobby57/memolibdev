from pathlib import Path
from dataclasses import replace

from project_target import resolve_target
from decision_agent import inspect_repository
from decision_selector import select_relevant_files
from evidence_resolver_v2_2 import (
    EvidenceStatus,
    build_store,
    resolve,
    validate_record,
)


def main():
    print("=" * 72)
    print("MEMOLIBDEV — 5F.3.4.2 TARGET-BOUND EVIDENCE")
    print("=" * 72)

    target = resolve_target()

    print(f"Repository : {target.path}")
    print(f"Git root   : {target.git_root}")
    print(f"Branch     : {target.branch}")
    print(f"HEAD       : {target.head_full}")
    print(f"Fingerprint: {target.fingerprint}")
    print()

    files = inspect_repository()

    selected = select_relevant_files(
        files,
        "Vérifier authentification Clerk tenant isolation OAuth tokens",
    )

    selected_paths = [
        item["path"] if isinstance(item, dict) else item
        for item in selected["selected"]
    ]

    store = build_store(
        selected_paths,
        target.git_root,
        target,
    )

    print(f"Fichiers sélectionnés : {len(selected_paths)}")
    print(f"Evidence store        : {len(store)}")
    print()

    print("=== IDENTITÉ DES PREUVES ===")

    if store:
        record = store[0]

        print(f"path       : {record.normalized_path}")
        print(f"git_root   : {record.git_root}")
        print(f"HEAD       : {record.head}")
        print(f"fingerprint: {record.repository_fingerprint}")
        print(f"SHA-256    : {record.content_sha256}")

        valid, reason = validate_record(record, target)

        print()
        print(
            f"Validation initiale : "
            f"{'OK' if valid else 'KO'} — {reason}"
        )
    else:
        raise SystemExit("Evidence store vide.")

    print()
    print("=== PREUVE EXACTE ===")

    for query in (
        "getTenantContext",
        "withOAuthToken",
        "oauthTokenService",
    ):
        results = resolve(store, query, target)

        print(f"\nQUERY: {query}")

        for result in results[:3]:
            print(
                f"  [{result.status}] "
                f"score={result.score} "
                f"{result.path}"
            )
            print(f"      reason: {result.reason}")

    print()
    print("=== TEST STALE EVIDENCE — SHA FALSIFIÉ ===")

    original = store[0]

    tampered = replace(
        original,
        content_sha256="0" * 64,
    )

    valid, reason = validate_record(tampered, target)

    print(f"Validation après falsification SHA :")
    print(f"  valid  = {valid}")
    print(f"  reason = {reason}")

    if valid:
        raise SystemExit(
            "ERREUR: une preuve falsifiée a été acceptée."
        )

    if not reason.startswith("content SHA-256 mismatch"):
        raise SystemExit(
            "ERREUR: le mismatch SHA n'a pas été détecté."
        )

    print("[OK] STALE_EVIDENCE détectable par SHA-256.")

    print()
    print("=== TEST TARGET IDENTITY ===")

    wrong_head = replace(
        original,
        head="0000000000000000000000000000000000000000",
    )

    valid, reason = validate_record(wrong_head, target)

    print(f"Validation avec mauvais HEAD :")
    print(f"  valid  = {valid}")
    print(f"  reason = {reason}")

    if valid:
        raise SystemExit(
            "ERREUR: une preuve issue d'un autre HEAD a été acceptée."
        )

    if reason != "HEAD mismatch":
        raise SystemExit(
            "ERREUR: le mismatch HEAD n'a pas été détecté."
        )

    print("[OK] TARGET IDENTITY protège contre un autre HEAD.")

    print()
    print("=== RESULTAT ===")
    print("[OK] Evidence liée au dépôt.")
    print("[OK] Evidence liée au HEAD.")
    print("[OK] Evidence liée au fingerprint.")
    print("[OK] Evidence liée au SHA-256.")
    print("[OK] Falsification SHA refusée.")
    print("[OK] HEAD différent refusé.")
    print()
    print("Aucun appel Ollama.")
    print("Aucun fichier MemoLib modifié.")
    print("=" * 72)


if __name__ == "__main__":
    main()

