# conftest.py
import os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent

DEFAULT_TARGET = r"C:\Users\moros\Desktop\memolib"
if "MEMOLIBDEV_TARGET" not in os.environ and Path(DEFAULT_TARGET).is_dir():
    os.environ["MEMOLIBDEV_TARGET"] = DEFAULT_TARGET

collect_ignore_glob = [
    "*.pre-*.py",
    "*.before-*.py",
    "_legacy_document_engine/*",
]

SLOW_FILES = {"test_gui_process_supervision.py"}

INTEGRATION_FILES = {
    "test_5f3_2_context_manager.py",
    "test_5f3_3_evidence_resolver.py",
    "test_5f3_4_2_target_bound_evidence.py",
    "test_5f3_4_evidence_resolver_v2.py",
    "test_5f3_compaction.py",
    "test_5f_qwen7b.py",
    "test_5g1_integration_v4.py",
    "test_5g1_integration_v5.py",
    "test_5g_guardrail.py",
    "test_analyze_vs_correct.py",
    "test_api_facade.py",
    "test_api_state_machine.py",
    "test_cli_memolibdev.py",
    "test_d58_e2e_authorization.py",
    "test_d60_agent_loop.py",
    "test_d60_phase2_integration.py",
    "test_e2e_ollama.py",
    "test_llm_controlled.py",
    "test_ollama_integration.py",
    "test_r2_authority_hierarchy.py",
    "test_r4_timeout.py",
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
