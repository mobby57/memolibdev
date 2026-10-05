from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import re
from typing import Iterable


class EvidenceStatus:
    ACCEPTED = "ACCEPTED"
    WEAK_EVIDENCE = "WEAK_EVIDENCE"
    SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class EvidenceRecord:
    path: str
    normalized_path: str
    content_sha256: str
    size: int
    content: str


@dataclass(frozen=True)
class EvidenceResult:
    status: str
    query: str
    path: str | None
    line_start: int | None
    line_end: int | None
    evidence: str | None
    score: int
    reason: str


_IDENTIFIER_RE = re.compile(
    r"(?<![A-Za-z0-9_$])"
    r"[A-Za-z_$][A-Za-z0-9_$]*"
    r"(?![A-Za-z0-9_$])"
)

_DECLARATION_RE = re.compile(
    r"\b(?:export\s+)?(?:async\s+)?"
    r"(?:function|class|interface|type|const|let|var)\s+"
    r"([A-Za-z_$][A-Za-z0-9_$]*)"
)


def normalize_path(path: str | Path) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def tokenize(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = re.sub(r"[_\-/.:]+", " ", value)

    return [
        token.lower()
        for token in value.split()
        if len(token) >= 3
    ]


def is_exact_identifier(line: str, identifier: str) -> bool:
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9_$]){re.escape(identifier)}"
            rf"(?![A-Za-z0-9_$])",
            line,
        )
    )


def is_declaration_of(line: str, identifier: str) -> bool:
    for match in _DECLARATION_RE.finditer(line):
        if match.group(1) == identifier:
            return True
    return False


def build_store(
    selected_files: Iterable[str | Path],
    repo_root: Path,
) -> dict[str, EvidenceRecord]:
    repo_root = repo_root.resolve()
    store: dict[str, EvidenceRecord] = {}

    for raw_path in selected_files:
        candidate = Path(raw_path)

        if not candidate.is_absolute():
            candidate = repo_root / candidate

        candidate = candidate.resolve()

        try:
            candidate.relative_to(repo_root)
        except ValueError:
            continue

        if not candidate.is_file():
            continue

        try:
            content = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        rel = normalize_path(candidate.relative_to(repo_root))

        store[rel] = EvidenceRecord(
            path=rel,
            normalized_path=rel,
            content_sha256=content_sha256(content),
            size=len(content),
            content=content,
        )

    return store


def validate_record(
    record: EvidenceRecord,
    repo_root: Path,
) -> str:
    root = repo_root.resolve()
    candidate = (root / record.normalized_path).resolve()

    try:
        candidate.relative_to(root)
    except ValueError:
        return EvidenceStatus.STALE_EVIDENCE

    if not candidate.is_file():
        return EvidenceStatus.STALE_EVIDENCE

    try:
        current = candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return EvidenceStatus.STALE_EVIDENCE

    if content_sha256(current) != record.content_sha256:
        return EvidenceStatus.STALE_EVIDENCE

    return EvidenceStatus.ACCEPTED


def extract_window(
    content: str,
    line_number: int,
    radius: int = 6,
) -> tuple[int, int, str]:
    lines = content.splitlines()

    index = max(0, line_number - 1)
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)

    return (
        start + 1,
        end,
        "\n".join(lines[start:end]),
    )


def resolve_exact_symbol(
    store: dict[str, EvidenceRecord],
    query: str,
    repo_root: Path,
) -> list[EvidenceResult]:
    identifier = query.strip()

    if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", identifier):
        return []

    results: list[EvidenceResult] = []

    for record in store.values():
        validation = validate_record(record, repo_root)

        if validation != EvidenceStatus.ACCEPTED:
            results.append(
                EvidenceResult(
                    status=EvidenceStatus.STALE_EVIDENCE,
                    query=query,
                    path=record.path,
                    line_start=None,
                    line_end=None,
                    evidence=None,
                    score=0,
                    reason="Evidence snapshot no longer matches repository content",
                )
            )
            continue

        for number, line in enumerate(record.content.splitlines(), start=1):
            if not is_exact_identifier(line, identifier):
                continue

            declaration = is_declaration_of(line, identifier)

            start, end, evidence = extract_window(
                record.content,
                number,
            )

            if declaration:
                results.append(
                    EvidenceResult(
                        status=EvidenceStatus.ACCEPTED,
                        query=query,
                        path=record.path,
                        line_start=start,
                        line_end=end,
                        evidence=evidence,
                        score=100,
                        reason="Exact symbol declaration",
                    )
                )
            else:
                results.append(
                    EvidenceResult(
                        status=EvidenceStatus.WEAK_EVIDENCE,
                        query=query,
                        path=record.path,
                        line_start=start,
                        line_end=end,
                        evidence=evidence,
                        score=40,
                        reason=(
                            "Exact identifier reference only; "
                            "not proof of symbol implementation"
                        ),
                    )
                )

    results.sort(
        key=lambda item: (
            item.status != EvidenceStatus.ACCEPTED,
            -item.score,
            item.path or "",
        )
    )

    return results


def resolve_path(
    store: dict[str, EvidenceRecord],
    query: str,
    repo_root: Path,
) -> list[EvidenceResult]:
    wanted = normalize_path(query)

    results: list[EvidenceResult] = []

    for record in store.values():
        if record.normalized_path != wanted:
            continue

        validation = validate_record(record, repo_root)

        if validation != EvidenceStatus.ACCEPTED:
            results.append(
                EvidenceResult(
                    status=EvidenceStatus.STALE_EVIDENCE,
                    query=query,
                    path=record.path,
                    line_start=None,
                    line_end=None,
                    evidence=None,
                    score=0,
                    reason="Exact path found but content is stale",
                )
            )
            continue

        results.append(
            EvidenceResult(
                status=EvidenceStatus.ACCEPTED,
                query=query,
                path=record.path,
                line_start=1,
                line_end=len(record.content.splitlines()),
                evidence=record.content,
                score=100,
                reason="Exact repository path",
            )
        )

    return results


def resolve_concept(
    store: dict[str, EvidenceRecord],
    query: str,
    repo_root: Path,
    max_results: int = 5,
) -> list[EvidenceResult]:
    tokens = tokenize(query)

    if not tokens:
        return []

    results: list[EvidenceResult] = []

    for record in store.values():
        validation = validate_record(record, repo_root)

        if validation != EvidenceStatus.ACCEPTED:
            continue

        best_score = 0
        best_line = None

        for number, line in enumerate(record.content.splitlines(), start=1):
            lower = line.lower()
            score = sum(4 for token in tokens if token in lower)

            if score > best_score:
                best_score = score
                best_line = number

        if best_line is None or best_score <= 0:
            continue

        start, end, evidence = extract_window(
            record.content,
            best_line,
        )

        results.append(
            EvidenceResult(
                status=EvidenceStatus.WEAK_EVIDENCE,
                query=query,
                path=record.path,
                line_start=start,
                line_end=end,
                evidence=evidence,
                score=best_score,
                reason="Conceptual/lexical match; not an exact proof",
            )
        )

    results.sort(key=lambda item: (-item.score, item.path or ""))

    return results[:max_results]


def resolve(
    store: dict[str, EvidenceRecord],
    query: str,
    repo_root: Path,
    max_results: int = 5,
) -> list[EvidenceResult]:
    query = query.strip()

    if not query:
        return [
            EvidenceResult(
                status=EvidenceStatus.INSUFFICIENT_EVIDENCE,
                query=query,
                path=None,
                line_start=None,
                line_end=None,
                evidence=None,
                score=0,
                reason="Empty query",
            )
        ]

    # Exact repository path has priority.
    path_results = resolve_path(store, query, repo_root)
    if path_results:
        return path_results[:max_results]

    # Exact symbol search.
    if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", query):
        exact = resolve_exact_symbol(store, query, repo_root)

        accepted = [
            result
            for result in exact
            if result.status == EvidenceStatus.ACCEPTED
        ]

        if accepted:
            return accepted[:max_results]

        weak = [
            result
            for result in exact
            if result.status == EvidenceStatus.WEAK_EVIDENCE
        ]

        if weak:
            return weak[:max_results]

        stale = [
            result
            for result in exact
            if result.status == EvidenceStatus.STALE_EVIDENCE
        ]

        if stale:
            return stale[:max_results]

        return [
            EvidenceResult(
                status=EvidenceStatus.SYMBOL_NOT_FOUND,
                query=query,
                path=None,
                line_start=None,
                line_end=None,
                evidence=None,
                score=0,
                reason="Exact symbol not found in the selected evidence store",
            )
        ]

    # Multi-word requests are concepts, not exact proof.
    concept = resolve_concept(
        store,
        query,
        repo_root,
        max_results=max_results,
    )

    if concept:
        return concept

    return [
        EvidenceResult(
            status=EvidenceStatus.INSUFFICIENT_EVIDENCE,
            query=query,
            path=None,
            line_start=None,
            line_end=None,
            evidence=None,
            score=0,
            reason="No grounded evidence found",
        )
    ]


def result_to_dict(result: EvidenceResult) -> dict:
    return asdict(result)
