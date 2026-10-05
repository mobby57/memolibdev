from decision_agent import inspect_repository
from decision_selector import select_relevant_files

REQUEST = "Auditer l authentification Clerk OAuth middleware et isolation tenant de MemoLib"

FULL_FILES = {
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

COMPACT_BUDGETS = {
    "src/lib/oauth/oauth-service.ts": 3200,
    "src/lib/oauth/integrations.ts": 2600,
    "src/lib/oauth/token-service.ts": 2600,
}

TEST_BUDGETS = {
    "src/__tests__/middleware/middleware.test.ts": 1800,
    "src/__tests__/middleware/tenant-isolation.test.ts": 1400,
    "src/__tests__/lib/clerk-auth.test.ts": 1400,
    "src/__tests__/api/lawyer/workspaces/[id]/emails/route-tenant.test.ts": 1000,
}

KEYWORDS = (
    "export ",
    "function ",
    "async ",
    "class ",
    "const ",
    "let ",
    "middleware",
    "auth",
    "token",
    "oauth",
    "clerk",
    "tenant",
    "workspace",
    "authorization",
    "verify",
    "session",
    "return ",
    "throw ",
    "redirect",
    "cookie",
    "headers",
)


def score_line(line):
    text = line.strip().lower()

    if not text:
        return 0

    score = 0

    for keyword in KEYWORDS:
        if keyword.lower() in text:
            score += 2

    if text.startswith(("export ", "function ", "async ", "class ")):
        score += 5

    if "return" in text:
        score += 2

    if "throw" in text:
        score += 2

    return score


def compact_source(content, budget):
    if len(content) <= budget:
        return content

    lines = content.splitlines()

    scored = []

    for index, line in enumerate(lines):
        score = score_line(line)

        if score > 0:
            scored.append((score, index, line))

    # Toujours garder les premières lignes : imports / configuration.
    selected_indexes = set(range(min(18, len(lines))))

    # Garder les lignes critiques et leur voisinage.
    ranked = sorted(
        scored,
        key=lambda item: (-item[0], item[1])
    )

    for _, index, _ in ranked:
        for offset in (-2, -1, 0, 1, 2):
            candidate = index + offset

            if 0 <= candidate < len(lines):
                selected_indexes.add(candidate)

        candidate_text = "\n".join(
            lines[i] for i in sorted(selected_indexes)
        )

        if len(candidate_text) >= budget:
            break

    output = "\n".join(
        lines[i] for i in sorted(selected_indexes)
    )

    if len(output) > budget:
        output = output[:budget]

    return (
        "[EXTRAIT STRUCTURÉ — fichier original "
        f"{len(content)} caractères]\n"
        + output
        + "\n[FIN EXTRAIT]"
    )


def compact_test(content, budget):
    lines = content.splitlines()

    selected = []

    for index, line in enumerate(lines):
        text = line.strip()

        if not text:
            continue

        lower = text.lower()

        important = (
            "describe(" in lower
            or "it(" in lower
            or "test(" in lower
            or "expect(" in lower
            or "assert" in lower
            or "clerk" in lower
            or "tenant" in lower
            or "middleware" in lower
            or "authorization" in lower
            or "token" in lower
            or "auth" in lower
        )

        if important:
            start = max(0, index - 1)
            end = min(len(lines), index + 2)

            for i in range(start, end):
                if lines[i].strip():
                    selected.append(lines[i].strip())

    # Déduplication tout en conservant l'ordre.
    seen = set()
    unique = []

    for line in selected:
        if line not in seen:
            seen.add(line)
            unique.append(line)

    output = "\n".join(unique)

    if len(output) > budget:
        output = output[:budget]

    return (
        "[PREUVES DE TEST — fichier original "
        f"{len(content)} caractères]\n"
        + output
        + "\n[FIN PREUVES]"
    )


def build_context(selected):
    sections = []
    details = []

    for item in selected:
        path = item["path"]
        content = item.get("content", "")

        if path in FULL_FILES:
            mode = "FULL"
            output = content

        elif path in COMPACT_BUDGETS:
            mode = "COMPACT"
            output = compact_source(
                content,
                COMPACT_BUDGETS[path]
            )

        elif path in TEST_BUDGETS:
            mode = "TEST"
            output = compact_test(
                content,
                TEST_BUDGETS[path]
            )

        else:
            mode = "COMPACT"
            output = compact_source(content, 1800)

        sections.append(
            f"\n===== {mode}: {path} =====\n"
            + output
            + f"\n===== FIN: {path} =====\n"
        )

        details.append(
            (
                mode,
                path,
                len(content),
                len(output),
            )
        )

    return "".join(sections), details


files = inspect_repository()
selection = select_relevant_files(files, REQUEST)
selected = selection["selected"]

raw_chars = sum(
    len(item.get("content", ""))
    for item in selected
)

compacted, details = build_context(selected)

compact_chars = len(compacted)

print("=" * 70)
print("MEMOLIBDEV — 5F.3.1 SEMANTIC CONTEXT COMPACTION")
print("=" * 70)

print(f"Repository       : {len(files)}")
print(f"Candidats        : {selection['candidate_count']}")
print(f"Fichiers retenus : {len(selected)}")
print()

print(f"5F.2 brut        : {raw_chars} caractères")
print(f"5F.3.1 compacté  : {compact_chars} caractères")

if raw_chars:
    reduction = 100 * (1 - compact_chars / raw_chars)
    print(f"Réduction        : {reduction:.1f}%")

print()
print("=== DETAIL ===")

for mode, path, original, compacted_size in details:
    print(
        f"{mode:7s} | "
        f"{original:7d} -> {compacted_size:7d} chars | "
        f"{path}"
    )

print()
print("=== ESTIMATION TOKENS ===")
print(f"5F.2 ~ {raw_chars // 4} tokens")
print(f"5F.3.1 ~ {compact_chars // 4} tokens")

print()
print("Aucun appel Ollama.")
print("Aucun fichier MemoLib modifié.")
