# conftest.py
import os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent

DEFAULT_TARGET = str(ROOT / "target_repo")
if "MEMOLIBDEV_TARGET" not in os.environ and Path(DEFAULT_TARGET).is_dir():
    os.environ["MEMOLIBDEV_TARGET"] = DEFAULT_TARGET

collect_ignore_glob = [
    "*.pre-*.py",
    "*.before-*.py",
    "_legacy_document_engine/*",
]

SLOW_FILES: set[str] = set()

INTEGRATION_FILES = {
    "test_d601_context_builder.py",
}


def _name(item):
    p = getattr(item, "path", None)
    if p is not None:
        return Path(p).name
    p = getattr(item, "fspath", None)
    if p is not None:
        return str(p).replace("\\", "/").rsplit("/", 1)[-1]
    return None


def pytest_collection_modifyitems(config, items):
    for item in items:
        n = _name(item)
        if not n:
            continue
        if n in SLOW_FILES:
            item.add_marker(pytest.mark.slow)
        if n in INTEGRATION_FILES:
            item.add_marker(pytest.mark.integration)
