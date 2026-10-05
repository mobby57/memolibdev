from pathlib import Path
import sys

from project_target import resolve_target, ProjectTargetError
from decision_agent import inspect_repository
from decision_selector import select_relevant_files
from evidence_resolver_v2 import (
    build_store,
    resolve,
    EvidenceStatus,
)


REQUEST = (
    "Auditer l'authentification Clerk OAuth middleware "
    "et isolation tenant de MemoLib"
)


def get_selected_paths(selection):
    paths = []

    for item in selection.get("selected", []):
        if isinstance(item, dict):
            value = item.get("path")
        else:
            value = item

        if value:
            paths.append(value)

    return paths


def main():
    print("=" * 72)
    print("MEMOLIBDEV — 5F.3.4 EVIDENCE RESOLVER V2 LAB")
    print("=" * 72)

    try:
        target = resolve_target()
    except ProjectTargetError as exc:
        print(f"[TARGET][ERROR] {exc}")
        return 2

    repo_root = target.git_root

    print(f"Repository : {repo_root}")
    print(f"Branch     : {target.branch}")
    print(f"HEAD       : {target.head}")
    print(f"Fingerprint: {target.fingerprint}")

    files = inspect_repository()
    selection = select_relevant_files(files, REQUEST)

    selected_paths = get_selected_paths(selection)
    store = build_store(selected_paths, repo_root)

    print()
    print(f"Fichiers sélectionnés : {len(selected_paths)}")
    print(f"Evidence store        : {len(store)}")

    print()
    print("=== REQUÊTES EXACTES ===")

    exact_queries = [
        "verifyToken",
        "getTenantContext",
        "withOAuthToken",
        "oauthTokenService",
    ]

    failures = 0

    for query in exact_queries:
        print()
        print(f"QUERY: {query}")

        results = resolve(
            store,
            query,
            repo_root,
            max_results=3,
        )

        for result in results:
            print(
                f"  [{result.status}] "
                f"score={result.score} "
                f"{result.path or '-'}"
            )
            print(f"      reason: {result.reason}")

        if not results:
            print("  [ERROR] aucun résultat")
            failures += 1

    print()
    print("=== REQUÊTES CONCEPTUELLES ===")

    concept_queries = [
        "Clerk authentication",
        "tenant workspace",
        "OAuth authorization",
    ]

    for query in concept_queries:
        print()
        print(f"QUERY: {query}")

        results = resolve(
            store,
            query,
            repo_root,
            max_results=3,
        )

        for result in results:
            print(
                f"  [{result.status}] "
                f"score={result.score} "
                f"{result.path or '-'}"
            )
            print(f"      reason: {result.reason}")

    print()
    print("=== TEST DE NON-PREUVE ===")

    results = resolve(
        store,
        "verifyToken",
        repo_root,
        max_results=5,
    )

    if any(r.status == EvidenceStatus.ACCEPTED for r in results):
        print(
            "[ATTENTION] verifyToken est réellement présent "
            "dans le store actuel."
        )
    else:
        print(
            "[OK] verifyToken n'est pas accepté comme preuve "
            "si aucun symbole exact n'existe."
        )

    print()
    print("=== FIN 5F.3.4 ===")
    print("Aucun appel Ollama.")
    print("Aucun fichier MemoLib modifié.")

    return failures


if __name__ == "__main__":
    sys.exit(main())
