from pathlib import Path
import re


# ============================================================
# 5F.2 — SÉLECTION DÉTERMINISTE DU CONTEXTE
# ============================================================

EXCLUDED_PREFIXES = (
    ".git/",
    "node_modules/",
    ".next/",
    "dist/",
    "build/",
    "bin/",
    "obj/",
    "reports/",
    "_archive/",
)

PRIMARY_EXTENSIONS = {
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".py",
}

SECONDARY_EXTENSIONS = {
    ".json",
    ".md",
}

TECHNICAL_KEYWORDS = {
    "clerkmiddleware": 30,
    "verifytoken": 22,
    "currentuser": 20,
    "authorization": 16,
    "bearer": 16,
    "clerk": 18,
    "oauth": 14,
    "middleware": 12,
    "session": 10,
    "tenant": 9,
    "workspace": 8,
    "token": 8,
    "auth": 6,
    "login": 4,
    "user": 2,
}

ARCHITECTURAL_FILENAMES = {
    "middleware.ts",
    "proxy.ts",
    "clerk-auth.ts",
    "clerk-token.ts",
    "auth.ts",
}

PRIMARY_PATH_BONUS = {
    "/middleware/": 25,
    "/oauth/": 25,
    "/auth/": 22,
    "/security/": 10,
    "/api/": 5,
}

MAX_PRIMARY_FILES = 12
MAX_SECONDARY_FILES = 4
MAX_CONTEXT_CHARS = 80000


def normalize_repo_path(path: str) -> str:
    return path.replace("\\", "/").lower()


def extract_request_terms(request: str) -> set[str]:
    text = (request or "").lower()

    return set(
        re.findall(
            r"[a-zA-ZÀ-ÿ0-9_-]{3,}",
            text,
        )
    )


def classify_file(path: str) -> str:
    normalized = normalize_repo_path(path)
    suffix = Path(normalized).suffix

    if (
        "/__tests__/" in normalized
        or normalized.startswith("tests/")
        or normalized.endswith(".test.ts")
        or normalized.endswith(".test.tsx")
        or normalized.endswith(".spec.ts")
        or normalized.endswith(".spec.tsx")
    ):
        return "SECONDARY"

    if suffix in SECONDARY_EXTENSIONS:
        return "SECONDARY"

    if suffix in PRIMARY_EXTENSIONS:
        return "PRIMARY"

    return "SECONDARY"


def score_file(item: dict, request_terms: set[str]) -> dict:
    path = item.get("path", "")
    normalized = normalize_repo_path(path)
    content = item.get("content", "").lower()

    category = classify_file(path)

    score = 0
    reasons = []

    suffix = Path(normalized).suffix

    if category == "PRIMARY":
        score += 10
        reasons.append("primary")

    if suffix in {".ts", ".tsx"}:
        score += 6
        reasons.append("typescript")

    if normalized.startswith("src/"):
        score += 10
        reasons.append("src")

    for marker, bonus in PRIMARY_PATH_BONUS.items():
        if marker in normalized:
            score += bonus
            reasons.append(f"path:{marker}")

    basename = Path(normalized).name

    if basename in ARCHITECTURAL_FILENAMES:
        score += 35
        reasons.append("architectural-file")

    if "/webhooks/clerk/" in normalized:
        score += 30
        reasons.append("clerk-webhook")

    if "/api/" in normalized:
        score += 5
        reasons.append("api")

    if category == "SECONDARY" and (
        "/__tests__/" in normalized
        or normalized.startswith("tests/")
        or normalized.endswith(".test.ts")
        or normalized.endswith(".test.tsx")
        or normalized.endswith(".spec.ts")
        or normalized.endswith(".spec.tsx")
    ):
        score -= 20
        reasons.append("test-secondary")

    for keyword, weight in TECHNICAL_KEYWORDS.items():
        if keyword in normalized:
            score += weight * 3
            reasons.append(f"path:{keyword}")

        if keyword in content:
            score += weight
            reasons.append(f"content:{keyword}")

    for term in request_terms:
        if len(term) < 4:
            continue

        if term in normalized:
            score += 8
            reasons.append(f"request-path:{term}")

        elif term in content:
            score += 2
            reasons.append(f"request-content:{term}")

    return {
        "score": score,
        "path": path,
        "size": item.get("size", 0),
        "content": item.get("content", ""),
        "category": category,
        "reasons": reasons,
    }


def select_relevant_files(
    files: list[dict],
    request: str,
    max_primary: int = MAX_PRIMARY_FILES,
    max_secondary: int = MAX_SECONDARY_FILES,
    max_context_chars: int = MAX_CONTEXT_CHARS,
) -> dict:

    request_terms = extract_request_terms(request)

    candidates = []

    for item in files:
        if item.get("_inspection_metadata"):
            continue

        path = item.get("path", "")
        normalized = normalize_repo_path(path)

        if normalized.startswith(EXCLUDED_PREFIXES):
            continue

        scored = score_file(item, request_terms)

        if scored["score"] <= 0:
            continue

        candidates.append(scored)

    primary = sorted(
        (
            item
            for item in candidates
            if item["category"] == "PRIMARY"
        ),
        key=lambda item: (-item["score"], item["path"]),
    )

    secondary = sorted(
        (
            item
            for item in candidates
            if item["category"] == "SECONDARY"
        ),
        key=lambda item: (-item["score"], item["path"]),
    )

    selected = []

    primary_selected = 0

    for item in primary:
        if primary_selected >= max_primary:
            break

        selected.append(item)
        primary_selected += 1

    secondary_selected = 0

    for item in secondary:
        if secondary_selected >= max_secondary:
            break

        selected.append(item)
        secondary_selected += 1

    selected.sort(
        key=lambda item: (-item["score"], item["path"])
    )

    bounded = []
    total_chars = 0

    for item in selected:
        content_length = len(item["content"])

        if total_chars + content_length > max_context_chars:
            continue

        bounded.append(item)
        total_chars += content_length

    return {
        "request_terms": sorted(request_terms),
        "candidate_count": len(candidates),
        "selected": bounded,
        "primary_count": sum(
            1
            for item in bounded
            if item["category"] == "PRIMARY"
        ),
        "secondary_count": sum(
            1
            for item in bounded
            if item["category"] == "SECONDARY"
        ),
        "context_chars": total_chars,
        "context_estimated_tokens": total_chars // 4,
        "max_context_chars": max_context_chars,
    }
