from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from project_target import ProjectTarget


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
    git_root: str
    head: str
    repository_fingerprint: str
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


def normalize_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    root = repo_root.resolve()

    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"Evidence hors dépôt: {resolved}"
        ) from exc

    return relative.as_posix()


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def tokenize(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = re.sub(r"[^A-Za-z0-9]+", " ", value)
    return [
        token.lower()
        for token in value.split()
        if token.strip()
    ]


def is_declaration_of(line: str, identifier: str) -> bool:
    """
    Determine whether a source line actually declares `identifier`.

    Important provenance rule:
    - imports are NOT declarations;
    - re-exports are NOT declarations;
    - function calls are NOT declarations;
    - return expressions are NOT declarations.

    A local symbol is accepted only when the source line contains an
    explicit declaration form.
    """
    escaped = re.escape(identifier)

    patterns = [
        # JavaScript / TypeScript function declarations
        rf"^\s*(?:export\s+)?(?:default\s+)?"
        rf"(?:async\s+)?function\s+{escaped}\b",

        # JavaScript / TypeScript variable declarations
        rf"^\s*(?:export\s+)?"
        rf"(?:const|let|var)\s+{escaped}\b",

        # JavaScript / TypeScript class declarations
        rf"^\s*(?:export\s+)?(?:default\s+)?"
        rf"class\s+{escaped}\b",

        # TypeScript interface/type/enum declarations
        rf"^\s*(?:export\s+)?"
        rf"(?:interface|type|enum)\s+{escaped}\b",

        # Python function declarations
        rf"^\s*(?:async\s+)?def\s+{escaped}\s*\(",
    ]

    return any(re.search(pattern, line) for pattern in patterns)


def extract_window(
    content: str,
    line_number: int,
    radius: int = 6,
) -> tuple[int, int, str]:
    lines = content.splitlines()

    start_index = max(0, line_number - 1 - radius)
    end_index = min(len(lines), line_number + radius)

    start = start_index + 1
    end = end_index

    evidence = "\n".join(
        f"{index + 1:04d}: {lines[index]}"
        for index in range(start_index, end_index)
    )

    return start, end, evidence


def build_store(
    selected_files: list,
    repo_root: Path,
    target: ProjectTarget,
) -> list[EvidenceRecord]:
    root = repo_root.resolve()

    if root != target.git_root.resolve():
        raise ValueError(
            "Le repo_root fourni ne correspond pas au git_root de la cible."
        )

    records: list[EvidenceRecord] = []

    for candidate in selected_files:
        raw = Path(candidate)

        # Un chemin relatif (ex: "src/lib/x.ts" produit par le selector)
        # DOIT être résolu contre la racine du dépôt cible, jamais
        # contre le cwd. Un chemin absolu est pris tel quel puis
        # reconfirmé dans le dépôt via relative_to(root) ci-dessous.
        if raw.is_absolute():
            path = raw.resolve()
        else:
            path = (root / raw).resolve()

        try:
            path.relative_to(root)
        except ValueError:
            continue

        if not path.is_file():
            continue

        content = path.read_text(encoding="utf-8")

        records.append(
            EvidenceRecord(
                path=str(path),
                normalized_path=normalize_path(path, root),
                git_root=str(target.git_root),
                head=target.head_full,
                repository_fingerprint=target.fingerprint,
                content_sha256=content_sha256(content),
                size=len(content.encode("utf-8")),
                content=content,
            )
        )

    return records


def validate_record(
    record: EvidenceRecord,
    target: ProjectTarget,
) -> tuple[bool, str]:
    current_root = target.git_root.resolve()

    if Path(record.git_root).resolve() != current_root:
        return False, "git_root mismatch"

    if record.head != target.head_full:
        return False, "HEAD mismatch"

    if record.repository_fingerprint != target.fingerprint:
        return False, "repository fingerprint mismatch"

    path = (current_root / Path(record.normalized_path)).resolve()

    try:
        path.relative_to(current_root)
    except ValueError:
        return False, "evidence path escapes repository"

    if not path.is_file():
        return False, "evidence file no longer exists"

    current_content = path.read_text(encoding="utf-8")
    current_sha = content_sha256(current_content)

    if current_sha != record.content_sha256:
        return False, (
            "content SHA-256 mismatch: "
            f"stored={record.content_sha256[:16]} "
            f"current={current_sha[:16]}"
        )

    record_content_sha = content_sha256(record.content)

    if record_content_sha != record.content_sha256:
        return False, (
            "evidence record content SHA-256 mismatch: "
            f"stored={record.content_sha256[:16]} "
            f"record={record_content_sha[:16]}"
        )

    return True, "evidence identity and content validated"


def resolve_exact_symbol(
    records: list[EvidenceRecord],
    query: str,
    target: ProjectTarget,
    max_results: int = 5,
) -> list[EvidenceResult]:
    identifier = query.strip()

    if not identifier:
        return []

    results: list[EvidenceResult] = []

    for record in records:
        valid, reason = validate_record(record, target)

        if not valid:
            results.append(
                EvidenceResult(
                    status=EvidenceStatus.STALE_EVIDENCE,
                    query=query,
                    path=record.normalized_path,
                    line_start=None,
                    line_end=None,
                    evidence=None,
                    score=0,
                    reason=reason,
                )
            )
            continue

        for number, line in enumerate(
            record.content.splitlines(),
            start=1,
        ):
            if not re.search(
                rf"\b{re.escape(identifier)}\b",
                line,
            ):
                continue

            start, end, evidence = extract_window(
                record.content,
                number,
            )

            if is_declaration_of(line, identifier):
                results.append(
                    EvidenceResult(
                        status=EvidenceStatus.ACCEPTED,
                        query=query,
                        path=record.normalized_path,
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
                        path=record.normalized_path,
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
        key=lambda result: (
            result.status != EvidenceStatus.ACCEPTED,
            -result.score,
            result.path or "",
        )
    )

    accepted = [
        result for result in results
        if result.status == EvidenceStatus.ACCEPTED
    ]

    if accepted:
        return accepted[:max_results]

    weak = [
        result for result in results
        if result.status == EvidenceStatus.WEAK_EVIDENCE
    ]

    if weak:
        return weak[:max_results]

    stale = [
        result for result in results
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
            reason="No exact symbol found in validated evidence store",
        )
    ]


def resolve_concept(
    records: list[EvidenceRecord],
    query: str,
    target: ProjectTarget,
    max_results: int = 5,
) -> list[EvidenceResult]:
    tokens = tokenize(query)

    if not tokens:
        return [
            EvidenceResult(
                status=EvidenceStatus.INSUFFICIENT_EVIDENCE,
                query=query,
                path=None,
                line_start=None,
                line_end=None,
                evidence=None,
                score=0,
                reason="Empty conceptual query",
            )
        ]

    results: list[EvidenceResult] = []

    for record in records:
        valid, reason = validate_record(record, target)

        if not valid:
            continue

        searchable = (
            record.normalized_path.lower()
            + "\n"
            + record.content.lower()
        )

        score = sum(
            4 for token in tokens
            if token in searchable
        )

        if score <= 0:
            continue

        results.append(
            EvidenceResult(
                status=EvidenceStatus.WEAK_EVIDENCE,
                query=query,
                path=record.normalized_path,
                line_start=None,
                line_end=None,
                evidence=None,
                score=score,
                reason=(
                    "Conceptual/lexical match; not an exact proof"
                ),
            )
        )

    results.sort(
        key=lambda result: (
            -result.score,
            result.path or "",
        )
    )

    return results[:max_results]


def resolve(
    records: list[EvidenceRecord],
    query: str,
    target: ProjectTarget,
    max_results: int = 5,
) -> list[EvidenceResult]:
    exact = resolve_exact_symbol(
        records,
        query,
        target,
        max_results,
    )

    if exact and exact[0].status != EvidenceStatus.SYMBOL_NOT_FOUND:
        return exact

    if len(tokenize(query)) > 1:
        return resolve_concept(
            records,
            query,
            target,
            max_results,
        )

    return exact


def result_to_dict(result: EvidenceResult) -> dict:
    return {
        "status": result.status,
        "query": result.query,
        "path": result.path,
        "line_start": result.line_start,
        "line_end": result.line_end,
        "evidence": result.evidence,
        "score": result.score,
        "reason": result.reason,
    }
