"""
MemoLibDev — LLM CONTROLLED v1 : package `llm`
===============================================

Intelligence contrôlée. Le LLM produit UNIQUEMENT une intention
(LLMPlan), jamais une autorité ni un effet. Toute sortie est re-validée
par la chaîne D5/D6 en aval. Fail-closed. Aucun secret transmis.
"""

from llm.secret_scanner import scan_context, scan_text, redact_text, ScanResult, SecretHit
from llm.ai_provider import AIProvider, LLMPlan, FakeProvider, SlowFakeProvider, ProviderLocality
from llm.llm_planner import derive_intent, PlannerResult
from llm.provider_timeout import call_provider_with_timeout, TimeoutOutcome
from llm.ollama_provider import OllamaProvider

__all__ = [
    "scan_context", "scan_text", "redact_text", "ScanResult", "SecretHit",
    "AIProvider", "LLMPlan", "FakeProvider", "SlowFakeProvider", "ProviderLocality",
    "derive_intent", "PlannerResult",
    "call_provider_with_timeout", "TimeoutOutcome",
    "OllamaProvider",
]
