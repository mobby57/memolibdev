"""API publique du moteur documentaire technique déterministe."""
from .generator import generate
from .schema import (
    ENGINE_VERSION,
    REPORT_SCHEMA_VERSION,
    EvidenceRef,
    GeneratedDocument,
    HumanDecision,
    ProjectRef,
    TechnicalReport,
    TemplateDefinition,
    TestResult,
)
from .template_registry import load_registered_template
from .validator import validate_report

__all__ = [
    "ENGINE_VERSION",
    "REPORT_SCHEMA_VERSION",
    "EvidenceRef",
    "GeneratedDocument",
    "HumanDecision",
    "ProjectRef",
    "TechnicalReport",
    "TemplateDefinition",
    "TestResult",
    "generate",
    "load_registered_template",
    "validate_report",
]
