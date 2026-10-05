from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from project_target import ProjectTarget


class ProvenanceStatus(str, Enum):
    RESOLVED = "RESOLVED"
    EXTERNAL_MODULE = "EXTERNAL_MODULE"
    MODULE_NOT_FOUND = "MODULE_NOT_FOUND"
    INVALID_ALIAS = "INVALID_ALIAS"
    OUTSIDE_REPOSITORY = "OUTSIDE_REPOSITORY"
    INVALID_IMPORT = "INVALID_IMPORT"


@dataclass(frozen=True)
class ImportReference:
    source_path: str
    symbol: str
    module_specifier: str


@dataclass(frozen=True)
class ProvenanceResult:
    status: ProvenanceStatus
    source_path: str
    symbol: str
    module_specifier: str
    resolved_path: Optional[str]
    reason: str


_IMPORT_PATTERNS = (
    re.compile(
        r"import\s*\{(?P<names>[^}]*)\}\s*"
        r"from\s*['\"](?P<module>[^'\"]+)['\"]"
    ),
    re.compile(
        r"import\s+(?P<default>[A-Za-z_$][\w$]*)\s*,?\s*"
        r"(?:\{(?P<named>[^}]*)\}\s*)?"
        r"from\s*['\"](?P<module>[^'\"]+)['\"]"
    ),
)


def _normalize_repo_relative(
    path: Path,
    repo_root: Path,
) -> str:
    return path.resolve().relative_to(
        repo_root.resolve()
    ).as_posix()


def _inside_repository(
    path: Path,
    repo_root: Path,
) -> bool:
    try:
        path.resolve().relative_to(
            repo_root.resolve()
        )
        return True
    except ValueError:
        return False


def _read_json(path: Path) -> dict:
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def _load_path_config(
    repo_root: Path,
) -> tuple[Optional[str], dict]:
    """
    Read tsconfig.json first, then jsconfig.json.

    No hard-coded alias such as @/ -> src/ is used.
    """
    for filename in ("tsconfig.json", "jsconfig.json"):
        config_path = repo_root / filename

        if not config_path.is_file():
            continue

        data = _read_json(config_path)
        compiler_options = data.get(
            "compilerOptions",
            {},
        )

        return (
            compiler_options.get("baseUrl"),
            compiler_options.get("paths", {}),
        )

    return None, {}


def _resolve_candidate_file(
    candidate: Path,
    repo_root: Path,
) -> Optional[Path]:
    """
    Resolve a TypeScript/JavaScript file or directory.

    Resolution order deliberately stays deterministic.
    """

    candidate = candidate.resolve()

    if not _inside_repository(
        candidate,
        repo_root,
    ):
        return None

    # Direct file.
    if candidate.is_file():
        return candidate

    # TypeScript / JavaScript extensions.
    for extension in (
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mts",
        ".cts",
        ".mjs",
        ".cjs",
    ):
        file_candidate = Path(
            str(candidate) + extension
        ).resolve()

        if (
            file_candidate.is_file()
            and _inside_repository(
                file_candidate,
                repo_root,
            )
        ):
            return file_candidate

    # Directory index resolution.
    if candidate.is_dir():
        for filename in (
            "index.ts",
            "index.tsx",
            "index.js",
            "index.jsx",
            "index.mts",
            "index.cts",
            "index.mjs",
            "index.cjs",
        ):
            index_file = (
                candidate / filename
            ).resolve()

            if index_file.is_file():
                return index_file

    return None


def _match_path_pattern(
    specifier: str,
    pattern: str,
) -> Optional[str]:
    """
    Return wildcard content when `specifier` matches `pattern`.

    Supports TypeScript-style `*` mappings.
    """
    if "*" not in pattern:
        return "" if specifier == pattern else None

    prefix, suffix = pattern.split(
        "*",
        1,
    )

    if not specifier.startswith(prefix):
        return None

    if suffix and not specifier.endswith(suffix):
        return None

    end = (
        len(specifier) - len(suffix)
        if suffix
        else None
    )

    return specifier[
        len(prefix):end
    ]


def resolve_module_specifier(
    module_specifier: str,
    target: ProjectTarget,
) -> ProvenanceResult:
    """
    Resolve one module specifier against the target repository.

    External packages are deliberately NOT resolved here.
    """
    root = target.git_root.resolve()

    if not module_specifier:
        return ProvenanceResult(
            status=ProvenanceStatus.INVALID_IMPORT,
            source_path="",
            symbol="",
            module_specifier=module_specifier,
            resolved_path=None,
            reason="Empty module specifier",
        )

    # Relative imports are local by definition.
    if module_specifier.startswith("."):
        return _resolve_relative_module(
            module_specifier,
            root,
        )

    # Absolute filesystem paths are never accepted as imports.
    if (
        module_specifier.startswith("/")
        or re.match(
            r"^[A-Za-z]:[\\/]",
            module_specifier,
        )
    ):
        return ProvenanceResult(
            status=ProvenanceStatus.OUTSIDE_REPOSITORY,
            source_path="",
            symbol="",
            module_specifier=module_specifier,
            resolved_path=None,
            reason="Filesystem absolute import rejected",
        )

    base_url, paths = _load_path_config(root)

    # First: configured TypeScript/JavaScript aliases.
    if paths:
        matched_alias = False

        for pattern, targets in paths.items():
            wildcard = _match_path_pattern(
                module_specifier,
                pattern,
            )

            if wildcard is None:
                continue

            matched_alias = True

            if not isinstance(
                targets,
                list,
            ):
                targets = [targets]

            base = root

            if base_url:
                base = (
                    root / base_url
                ).resolve()

                if not _inside_repository(
                    base,
                    root,
                ):
                    return ProvenanceResult(
                        status=ProvenanceStatus.OUTSIDE_REPOSITORY,
                        source_path="",
                        symbol="",
                        module_specifier=module_specifier,
                        resolved_path=None,
                        reason="Configured baseUrl escapes repository",
                    )

            for target_pattern in targets:
                mapped = str(
                    target_pattern
                ).replace(
                    "*",
                    wildcard,
                    1,
                )

                candidate = (
                    base / mapped
                ).resolve()

                resolved = _resolve_candidate_file(
                    candidate,
                    root,
                )

                if resolved is not None:
                    return ProvenanceResult(
                        status=ProvenanceStatus.RESOLVED,
                        source_path="",
                        symbol="",
                        module_specifier=module_specifier,
                        resolved_path=_normalize_repo_relative(
                            resolved,
                            root,
                        ),
                        reason=(
                            f"Resolved through path alias "
                            f"{pattern}"
                        ),
                    )

        if matched_alias:
            return ProvenanceResult(
                status=ProvenanceStatus.MODULE_NOT_FOUND,
                source_path="",
                symbol="",
                module_specifier=module_specifier,
                resolved_path=None,
                reason=(
                    "Alias matched configuration "
                    "but no local target file exists"
                ),
            )

    # No configured alias matched.
    return ProvenanceResult(
        status=ProvenanceStatus.EXTERNAL_MODULE,
        source_path="",
        symbol="",
        module_specifier=module_specifier,
        resolved_path=None,
        reason=(
            "No local path alias matched; "
            "treated as external module"
        ),
    )


def _resolve_relative_module(
    module_specifier: str,
    repo_root: Path,
) -> ProvenanceResult:
    """
    Resolve ./ and ../ imports from repository root.

    The caller that knows the source file should use
    resolve_import_reference(), which resolves these relative
    to the actual source file.
    """
    candidate = (
        repo_root
        / module_specifier
    ).resolve()

    if not _inside_repository(
        candidate,
        repo_root,
    ):
        return ProvenanceResult(
            status=ProvenanceStatus.OUTSIDE_REPOSITORY,
            source_path="",
            symbol="",
            module_specifier=module_specifier,
            resolved_path=None,
            reason="Relative module escapes repository",
        )

    resolved = _resolve_candidate_file(
        candidate,
        repo_root,
    )

    if resolved is None:
        return ProvenanceResult(
            status=ProvenanceStatus.MODULE_NOT_FOUND,
            source_path="",
            symbol="",
            module_specifier=module_specifier,
            resolved_path=None,
            reason="Relative module not found",
        )

    return ProvenanceResult(
        status=ProvenanceStatus.RESOLVED,
        source_path="",
        symbol="",
        module_specifier=module_specifier,
        resolved_path=_normalize_repo_relative(
            resolved,
            repo_root,
        ),
        reason="Resolved relative module",
    )


def extract_import_reference(
    source_path: Path,
    symbol: str,
    repo_root: Path,
) -> Optional[ImportReference]:
    """
    Extract the import providing `symbol` from one source file.
    """
    source_path = source_path.resolve()
    repo_root = repo_root.resolve()

    if not _inside_repository(
        source_path,
        repo_root,
    ):
        return None

    if not source_path.is_file():
        return None

    content = source_path.read_text(
        encoding="utf-8"
    )

    for pattern in _IMPORT_PATTERNS:
        for match in pattern.finditer(content):

            module = match.group(
                "module"
            )

            names = []

            for group_name in (
                "names",
                "named",
            ):
                value = match.groupdict().get(
                    group_name
                )

                if value:
                    names.extend(
                        part.strip().split(
                            " as "
                        )[0].strip()
                        for part in value.split(",")
                        if part.strip()
                    )

            default_name = match.groupdict().get(
                "default"
            )

            if default_name:
                names.append(
                    default_name
                )

            if symbol in names:
                return ImportReference(
                    source_path=_normalize_repo_relative(
                        source_path,
                        repo_root,
                    ),
                    symbol=symbol,
                    module_specifier=module,
                )

    return None


def resolve_import_reference(
    reference: ImportReference,
    target: ProjectTarget,
) -> ProvenanceResult:
    """
    Resolve an extracted import against the target repository.
    """
    root = target.git_root.resolve()

    source_path = (
        root / reference.source_path
    ).resolve()

    if not _inside_repository(
        source_path,
        root,
    ):
        return ProvenanceResult(
            status=ProvenanceStatus.OUTSIDE_REPOSITORY,
            source_path=reference.source_path,
            symbol=reference.symbol,
            module_specifier=reference.module_specifier,
            resolved_path=None,
            reason="Source path outside repository",
        )

    module = reference.module_specifier

    # Relative imports must resolve relative to source file.
    if module.startswith("."):
        candidate = (
            source_path.parent / module
        ).resolve()

        if not _inside_repository(
            candidate,
            root,
        ):
            return ProvenanceResult(
                status=ProvenanceStatus.OUTSIDE_REPOSITORY,
                source_path=reference.source_path,
                symbol=reference.symbol,
                module_specifier=module,
                resolved_path=None,
                reason=(
                    "Relative import escapes repository"
                ),
            )

        resolved = _resolve_candidate_file(
            candidate,
            root,
        )

        if resolved is None:
            return ProvenanceResult(
                status=ProvenanceStatus.MODULE_NOT_FOUND,
                source_path=reference.source_path,
                symbol=reference.symbol,
                module_specifier=module,
                resolved_path=None,
                reason="Relative import target not found",
            )

        return ProvenanceResult(
            status=ProvenanceStatus.RESOLVED,
            source_path=reference.source_path,
            symbol=reference.symbol,
            module_specifier=module,
            resolved_path=_normalize_repo_relative(
                resolved,
                root,
            ),
            reason="Resolved relative import",
        )

    result = resolve_module_specifier(
        module,
        target,
    )

    return ProvenanceResult(
        status=result.status,
        source_path=reference.source_path,
        symbol=reference.symbol,
        module_specifier=module,
        resolved_path=result.resolved_path,
        reason=result.reason,
    )


def resolve_symbol_import(
    source_path: Path,
    symbol: str,
    target: ProjectTarget,
) -> ProvenanceResult:
    """
    High-level API:

        source file + symbol
              ↓
        import extraction
              ↓
        module resolution
    """
    reference = extract_import_reference(
        source_path,
        symbol,
        target.git_root,
    )

    if reference is None:
        return ProvenanceResult(
            status=ProvenanceStatus.INVALID_IMPORT,
            source_path=_normalize_repo_relative(
                source_path.resolve(),
                target.git_root.resolve(),
            ),
            symbol=symbol,
            module_specifier="",
            resolved_path=None,
            reason=(
                "No import for symbol found in source file"
            ),
        )

    return resolve_import_reference(
        reference,
        target,
    )
