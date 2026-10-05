from pathlib import Path

from decision_agent import inspect_repository
from decision_selector import select_relevant_files


REQUEST = (
    "Auditer l authentification Clerk OAuth middleware "
    "et isolation tenant de MemoLib"
)

# ------------------------------------------------------------
# 5F.3.2 — CONTEXT MANAGER
# ------------------------------------------------------------

INITIAL_FULL = {
    "src/lib/oauth/middleware.ts",
    "src/lib/clerk-auth.ts",
    "src/lib/auth/clerk-token.ts",
    "src/app/api/oauth/tokens/route.ts",
    "src/middleware/tenant-isolation.ts",
    "src/app/api/webhooks/clerk/route.ts",
    "src/app/api/oauth/callback/route.ts",
    "src/middleware/auth.ts",
    "src/middleware/zero-trust.ts",
}

SECONDARY = {
    "src/lib/oauth/oauth-service.ts",
    "src/lib/oauth/integrations.ts",
    "src/lib/oauth/token-service.ts",
}

TESTS = {
    "src/__tests__/middleware/middleware.test.ts",
    "src/__tests__/middleware/tenant-isolation.test.ts",
    "src/__tests__/lib/clerk-auth.test.ts",
    "src/__tests__/api/lawyer/workspaces/[id]/emails/route-tenant.test.ts",
}

INITIAL_BUDGET = 26000


def normalize(path):
    return path.replace("\\", "/")


def score_line(line):
    text = line.strip().lower()

    if not text:
        return 0

    score = 0

    keywords = (
        "clerk",
        "oauth",
        "token",
        "authorization",
        "authenticate",
        "authentication",
        "verify",
        "tenant",
        "workspace",
        "middleware",
        "session",
        "cookie",
        "headers",
        "currentuser",
        "return",
        "throw",
        "export",
        "function",
        "async",
        "class",
    )

    for keyword in keywords:
        if keyword in text:
            score += 2

    if text.startswith(("export ", "function ", "async ", "class ")):
        score += 4

    if "verify" in text or "authorize" in text:
        score += 4

    if "tenant" in text or "workspace" in text:
        score += 3

    return score


def extract_evidence(content, max_chars):
    """
    Extrait déterministe :
    - imports/configuration
    - fonctions/classes importantes
    - lignes critiques
    - voisinage des lignes critiques
    """

    if len(content) <= max_chars:
        return content

    lines = content.splitlines()

    selected = set()

    # Toujours conserver le début du fichier.
    for i in range(min(25, len(lines))):
        selected.add(i)

    scored = []

    for i, line in enumerate(lines):
        score = score_line(line)

        if score > 0:
            scored.append((score, i))

    scored.sort(key=lambda x: (-x[0], x[1]))

    for score, index in scored:
        for offset in range(-2, 3):
            candidate = index + offset

            if 0 <= candidate < len(lines):
                selected.add(candidate)

        current = "\n".join(lines[i] for i in sorted(selected))

        if len(current) >= max_chars:
            break

    result = "\n".join(lines[i] for i in sorted(selected))

    if len(result) > max_chars:
        result = result[:max_chars]

    return result


def compact_test(content, max_chars):
    """
    Les tests sont traités comme des preuves :
    describe / test / expect / assertions / sécurité.
    """

    lines = content.splitlines()
    selected = set()

    for i, line in enumerate(lines):
        text = line.strip().lower()

        important = (
            "describe(" in text
            or "it(" in text
            or "test(" in text
            or "expect(" in text
            or "assert" in text
            or "clerk" in text
            or "tenant" in text
            or "oauth" in text
            or "token" in text
            or "middleware" in text
            or "authorization" in text
            or "auth" in text
        )

        if important:
            for offset in range(-1, 2):
                candidate = i + offset

                if 0 <= candidate < len(lines):
                    selected.add(candidate)

    result = "\n".join(
        lines[i].strip()
        for i in sorted(selected)
        if lines[i].strip()
    )

    if len(result) > max_chars:
        result = result[:max_chars]

    return result


def build_initial_context(selected):
    """
    Construit le petit contexte initial.
    Les fichiers secondaires ne sont PAS envoyés intégralement.
    Ils restent disponibles dans l'evidence store.
    """

    sections = []
    used = 0

    # 1. Fichiers critiques FULL
    for item in selected:
        path = normalize(item["path"])

        if path not in INITIAL_FULL:
            continue

        content = item.get("content", "")

        block = (
            f"\n===== INITIAL / CRITICAL / FULL: {path} =====\n"
            + content
            + f"\n===== END: {path} =====\n"
        )

        if used + len(block) <= INITIAL_BUDGET:
            sections.append(block)
            used += len(block)

    # 2. Tests : uniquement les preuves importantes
    for item in selected:
        path = normalize(item["path"])

        if path not in TESTS:
            continue

        content = item.get("content", "")
        evidence = compact_test(content, 900)

        block = (
            f"\n===== INITIAL / TEST EVIDENCE: {path} =====\n"
            + evidence
            + f"\n===== END: {path} =====\n"
        )

        if used + len(block) <= INITIAL_BUDGET:
            sections.append(block)
            used += len(block)

    return "".join(sections), used


def build_evidence_store(selected):
    """
    Evidence store local :
    les fichiers sélectionnés restent disponibles pour
    récupération ultérieure.
    """

    store = {}

    for item in selected:
        path = normalize(item["path"])

        store[path] = {
            "path": path,
            "content": item.get("content", ""),
            "chars": len(item.get("content", "")),
        }

    return store


def search_evidence(store, query):
    """
    Recherche déterministe très simple pour le laboratoire.
    Elle ne contacte aucun LLM.
    """

    terms = [
        term.lower()
        for term in query.split()
        if len(term) >= 3
    ]

    results = []

    for path, item in store.items():
        content = item["content"].lower()

        score = 0

        for term in terms:
            if term in path.lower():
                score += 5

            score += content.count(term)

        if score > 0:
            results.append(
                {
                    "path": path,
                    "score": score,
                    "chars": item["chars"],
                }
            )

    results.sort(
        key=lambda x: (-x["score"], x["path"])
    )

    return results


# ------------------------------------------------------------
# EXECUTION
# ------------------------------------------------------------

files = inspect_repository()

selection = select_relevant_files(
    files,
    REQUEST
)

selected = selection["selected"]

initial_context, initial_chars = build_initial_context(
    selected
)

evidence_store = build_evidence_store(selected)

print("=" * 72)
print("MEMOLIBDEV — 5F.3.2 CONTEXT MANAGER LAB")
print("=" * 72)

print(f"Repository       : {len(files)}")
print(f"Candidats        : {selection['candidate_count']}")
print(f"Fichiers retenus : {len(selected)}")
print()

raw_chars = sum(
    len(item.get("content", ""))
    for item in selected
)

print(f"Contexte brut 5F.2 : {raw_chars} caractères")
print(f"Contexte initial   : {initial_chars} caractères")
print(f"Budget initial     : {INITIAL_BUDGET} caractères")

if raw_chars:
    reduction = 100 * (1 - initial_chars / raw_chars)
    print(f"Réduction initiale : {reduction:.1f}%")

print()
print("=== FICHIERS DU CONTEXTE INITIAL ===")

for line in initial_context.splitlines():
    if line.startswith("====="):
        print(line)

print()
print("=== EVIDENCE STORE ===")

for path, item in evidence_store.items():
    print(
        f"{item['chars']:7d} chars | {path}"
    )

print()
print("=== TEST DE RECHERCHE ON-DEMAND ===")

queries = [
    "verifyToken",
    "tenant workspace",
    "oauth token",
    "clerk authorization",
]

for query in queries:
    results = search_evidence(
        evidence_store,
        query
    )

    print()
    print(f"QUERY: {query}")

    for result in results[:5]:
        print(
            f"  score={result['score']:4d} "
            f"{result['chars']:7d} chars "
            f"{result['path']}"
        )

print()
print("=== ESTIMATION TOKENS ===")
print(f"Brut 5F.2       ~ {raw_chars // 4} tokens")
print(f"Initial 5F.3.2  ~ {initial_chars // 4} tokens")

print()
print("Aucun appel Ollama.")
print("Aucun fichier MemoLib modifié.")
