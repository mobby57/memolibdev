from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"

USER_AGENT = "MemoLibDev/3.6-web-research"

MAX_RESULTS = 8
MAX_PAGE_BYTES = 180_000
TIMEOUT = 15

OFFICIAL_DOMAINS = {
    "clerk.com",
    "nextjs.org",
    "react.dev",
    "nodejs.org",
    "github.com",
    "docs.github.com",
}


def _request(
    url: str,
    *,
    timeout: int = TIMEOUT,
    max_bytes: int = MAX_PAGE_BYTES,
) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json,text/plain,*/*",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = response.status
        data = response.read(max_bytes + 1)

    return status, data[:max_bytes]


def _github_repositories(query: str) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote_plus(query)
    url = f"https://api.github.com/search/repositories?q={encoded}&per_page={MAX_RESULTS}"

    try:
        status, data = _request(url)
        payload = json.loads(data.decode("utf-8", "replace"))

        results = []

        for item in payload.get("items", [])[:MAX_RESULTS]:
            results.append(
                {
                    "title": item.get("full_name", ""),
                    "url": item.get("html_url", ""),
                    "description": item.get("description", ""),
                    "stars": item.get("stargazers_count", 0),
                    "source_type": "github_repository",
                    "domain": "github.com",
                    "verified_source": True,
                }
            )

        return results

    except Exception as exc:
        return [
            {
                "source_type": "github_repository",
                "error": str(exc),
                "verified_source": False,
            }
        ]


def _jina_read(url: str) -> dict[str, Any]:
    jina_url = "https://r.jina.ai/" + url

    try:
        status, data = _request(
            jina_url,
            timeout=TIMEOUT,
            max_bytes=MAX_PAGE_BYTES,
        )

        text = data.decode("utf-8", "replace").strip()

        return {
            "url": url,
            "reader_url": jina_url,
            "status": status,
            "content": text,
            "bytes": len(data),
            "success": status == 200 and bool(text),
        }

    except urllib.error.HTTPError as exc:
        return {
            "url": url,
            "reader_url": jina_url,
            "status": exc.code,
            "success": False,
            "error": f"HTTP {exc.code}",
        }

    except Exception as exc:
        return {
            "url": url,
            "reader_url": jina_url,
            "success": False,
            "error": str(exc),
        }


def _domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _official_score(url: str) -> int:
    domain = _domain(url)

    if domain in OFFICIAL_DOMAINS:
        return 100

    if domain.endswith(".github.com"):
        return 90

    if domain.endswith(".org"):
        return 50

    return 20


def _build_queries(question: str) -> list[str]:
    question = question.strip()

    queries = [
        question,
    ]

    # Recherche technique GitHub ciblée.
    technical_terms = [
        "clerk",
        "nextjs",
        "next.js",
        "middleware",
        "proxy",
        "authentication",
        "migration",
    ]

    lowered = question.lower()

    if any(term in lowered for term in technical_terms):
        queries.append(f"{question} Clerk Next.js")

    # Déduplication.
    output = []

    for query in queries:
        if query and query not in output:
            output.append(query)

    return output[:3]


def research(question: str) -> dict[str, Any]:
    question = question.strip()

    if not question:
        raise ValueError("Question vide.")

    github_results: list[dict[str, Any]] = []

    for query in _build_queries(question):
        github_results.extend(_github_repositories(query))

    # Déduplication GitHub.
    seen = set()
    unique_github = []

    for item in github_results:
        url = item.get("url")

        if not url or url in seen:
            continue

        seen.add(url)
        unique_github.append(item)

    # Sources officielles connues pour les recherches Clerk/Next.js.
    lowered = question.lower()

    known_sources = []

    if any(x in lowered for x in ["clerk", "auth", "authentication", "middleware", "proxy"]):
        known_sources.extend(
            [
                "https://clerk.com/docs/reference/nextjs/clerk-middleware",
                "https://clerk.com/docs/getting-started/quickstart",
                "https://clerk.com/docs/guides/development/upgrading/upgrade-guides/nextjs-v6",
                "https://clerk.com/docs/guides/development/upgrading/upgrade-guides/migrate-from-create-route-matcher",
            ]
        )

    if any(x in lowered for x in ["next", "next.js", "middleware", "proxy"]):
        known_sources.append("https://nextjs.org/docs")

    pages = []

    for url in known_sources:
        result = _jina_read(url)

        if result.get("success"):
            result["domain"] = _domain(url)
            result["official"] = True
            result["source_score"] = _official_score(url)
            pages.append(result)

    all_sources = []

    for item in unique_github[:MAX_RESULTS]:
        all_sources.append(item)

    for page in pages[:MAX_RESULTS]:
        all_sources.append(
            {
                "title": page["url"],
                "url": page["url"],
                "domain": page.get("domain", ""),
                "source_type": "official_documentation",
                "content": page.get("content", ""),
                "verified_source": True,
                "official": True,
                "source_score": page.get("source_score", 100),
            }
        )

    all_sources.sort(
        key=lambda item: item.get("source_score", 0),
        reverse=True,
    )

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "read_only": True,
        "engine": "github-api+jina-reader",
        "google_scraping": False,
        "duckduckgo_scraping": False,
        "sources": all_sources[:MAX_RESULTS],
    }


def save_report(report: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    path = REPORTS_DIR / f"web-research-{stamp}.json"

    path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="MemoLibDev V3.6 — lecture Web sécurisée"
    )

    parser.add_argument(
        "question",
        nargs="+",
        help="Question à rechercher",
    )

    args = parser.parse_args()

    question = " ".join(args.question)

    print("=" * 70)
    print("MEMOLIBDEV V3.6 — WEB RESEARCH")
    print("=" * 70)
    print()
    print(f"[WEB] Question : {question}")
    print("[WEB] Moteur    : GitHub API + Jina Reader")
    print("[WEB] Lecture seule : OUI")
    print("[WEB] Google scraping : NON")
    print("[WEB] DuckDuckGo scraping : NON")
    print()

    try:
        report = research(question)
        path = save_report(report)

        sources = report.get("sources", [])

        print(f"[WEB] Sources trouvées : {len(sources)}")
        print()

        for index, source in enumerate(sources, 1):
            print(
                f"{index}. "
                f"{source.get('source_type', 'unknown')} — "
                f"{source.get('title', source.get('url', ''))}"
            )

            if source.get("url"):
                print(f"   {source['url']}")

        print()
        print(f"[WEB] Rapport : {path}")
        print("[WEB] STATUS : OK")

    except Exception as exc:
        print()
        print(f"[WEB] STATUS : ERROR")
        print(f"[WEB] {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
