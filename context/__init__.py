"""
MemoLibDev — D6.0.1 : package `context`
========================================

Context Builder contrôlé : construit un MissionContext borné, versionné
et traçable à partir d'une mission texte et d'un ProjectTarget résolu.
100 % déterministe, offline, read-only. Aucun LLM, aucun apply.
"""

from context.mission_context import (
    MissionContext, ProjectContext, RelevantFile, EvidenceEntry, HistoryEntry,
)
from context.context_version import (
    FileVersion, StalenessReport, capture_file_version, check_staleness,
    text_sha256, byte_sha256_of_file,
)
from context.project_inspector import inspect_target, InspectionResult, InspectedFile
from context.context_budget import apply_budget, BudgetResult, BudgetedItem
from context.context_builder import build_mission_context, is_stale

__all__ = [
    "MissionContext", "ProjectContext", "RelevantFile", "EvidenceEntry",
    "HistoryEntry", "FileVersion", "StalenessReport", "capture_file_version",
    "check_staleness", "text_sha256", "byte_sha256_of_file", "inspect_target",
    "InspectionResult", "InspectedFile", "apply_budget", "BudgetResult",
    "BudgetedItem", "build_mission_context", "is_stale",
]
