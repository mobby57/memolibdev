from pathlib import Path
import re

from decision_agent import inspect_repository
from decision_selector import select_relevant_files


REQUEST = (
    "Auditer l authentification Clerk OAuth middleware "
    "et isolation tenant de MemoLib"
)


def normalize(path):
    return path.replace("\\", "/")


def tokenize(value):
    """
    Transforme camelCase, snake_case, kebab-case et texte libre
    en tokens comparables.
    """
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = value.replace("_", " ")
    value = value.replace("-", " ")
    value = value.replace("/", " ")
    value = value.replace(".", " ")

    return [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+", value)
        if len(token) >= 3
    ]


def normalize_symbol(value):
    return "".join(tokenize(value))


def line_score(line, query_tokens):
    text = line.lower()
    line_tokens = tokenize(line)

    score = 0

    for token in query_tokens:
        if token in line_tokens:
            score += 10
        elif token in text:
            score += 4

    # Bonus pour déclarations / exports / fonctions.
    stripped = line.strip()

    if stripped.startswith(
        (
            "export ",
            "function ",
            "async function ",
            "const ",
            "class ",
        )
    ):
        score += 3

    return score


def find_evidence(path, content, query, max_chars=2200):
    """
    Recherche une preuve ciblée dans un fichier.

    Retourne :
    - score
    - lignes
    - extrait
    """

    query_tokens = tokenize(query)

    if not query_tokens:
        return None

    lines = content.splitlines()

    candidates = []

    for index, line in enumerate(lines):
        score = line_score(line, query_tokens)

        if score > 0:
            candidates.append((score, index))

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (-item[0], item[1])
    )

    best_score, best_index = candidates[0]

    # Conserve le voisinage de la meilleure preuve.
    start = max(0, best_index - 6)
    end = min(len(lines), best_index + 7)

    excerpt_lines = lines[start:end]

    excerpt = "\n".join(excerpt_lines)

    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars]

    return {
        "path": path,
        "score": best_score,
        "line_start": start + 1,
        "line_end": end,
        "excerpt": excerpt,
        "total_chars": len(content),
    }


def resolve(store, query, max_results=5):
    """
    Résolution déterministe de preuve.

    Cherche dans :
    1. chemin du fichier
    2. symboles / contenu
    3. variantes lexicales
    """

    query_tokens = tokenize(query)

    results = []

    for path, item in store.items():
        content = item["content"]

        path_tokens = tokenize(path)

        path_score = 0

        for token in query_tokens:
            if token in path_tokens:
                path_score += 8

        evidence = find_evidence(
            path,
            content,
            query,
        )

        content_score = (
            evidence["score"]
            if evidence
            else 0
        )

        total_score = path_score + content_score

        if total_score > 0:
            if evidence is None:
                evidence = {
                    "path": path,
                    "score": total_score,
                    "line_start": None,
                    "line_end": None,
                    "excerpt": "",
                    "total_chars": len(content),
                }
            else:
                evidence["score"] += path_score

            results.append(evidence)

    results.sort(
        key=lambda item: (
            -item["score"],
            item["path"],
        )
    )

    return results[:max_results]


def print_results(query, results):
    print()
    print("=" * 72)
    print(f"QUERY: {query}")
    print("=" * 72)

    if not results:
        print("AUCUNE PREUVE TROUVÉE")
        return

    for index, result in enumerate(results, 1):
        print()
        print(
            f"[{index}] "
            f"score={result['score']} "
            f"{result['path']}"
        )

        if result["line_start"] is not None:
            print(
                f"    lignes {result['line_start']}"
                f"-{result['line_end']}"
            )

        print(
            f"    fichier total : "
            f"{result['total_chars']} chars"
        )

        if result["excerpt"]:
            print()
            print("    --- EVIDENCE ---")

            for line in result["excerpt"].splitlines():
                print("    " + line)

            print("    --- FIN EVIDENCE ---")


# ============================================================
# EXECUTION
# ============================================================

files = inspect_repository()

selection = select_relevant_files(
    files,
    REQUEST,
)

selected = selection["selected"]

store = {}

for item in selected:
    path = normalize(item["path"])

    store[path] = {
        "path": path,
        "content": item.get("content", ""),
        "chars": len(item.get("content", "")),
    }


print("=" * 72)
print("MEMOLIBDEV — 5F.3.3 EVIDENCE RESOLVER LAB")
print("=" * 72)

print(f"Repository       : {len(files)}")
print(f"Candidats        : {selection['candidate_count']}")
print(f"Evidence store   : {len(store)} fichiers")

print()
print("=== TOKENIZATION TEST ===")

for value in (
    "verifyToken",
    "verify_token",
    "verify-token",
    "tenant-isolation",
    "Clerk OAuth Authorization",
):
    print(
        f"{value:30s} -> "
        f"{tokenize(value)}"
    )


queries = (
    "verifyToken",
    "tenant workspace",
    "oauth token",
    "clerk authorization",
)

print()
print("=== EVIDENCE RESOLUTION ===")

for query in queries:
    results = resolve(
        store,
        query,
        max_results=5,
    )

    print_results(
        query,
        results,
    )


print()
print("=" * 72)
print("FIN 5F.3.3")
print("Aucun appel Ollama.")
print("Aucun fichier MemoLib modifié.")
print("=" * 72)
