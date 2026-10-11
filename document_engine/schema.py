"""Contrat immuable du moteur documentaire technique V1."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


ENGINE_VERSION = "TECHNICAL_REPORT_ENGINE_V1"
REPORT_SCHEMA_VERSION = "TECHNICAL_REPORT_V1"

TEST_STATUSES = frozenset({
    "EXECUTED_PASS",
    "EXECUTED_FAIL",
    "EXECUTED_SKIPPED",
    "NOT_EXECUTED",
    "EVIDENCE_UNAVAILABLE",
})
VALIDATION_STATUSES = frozenset({
    "DRAFT",
    "VALID",
    "INVALID",
    "REVIEW_REQUIRED",
})
HUMAN_APPROVAL_STATUSES = frozenset({
    "NOT_REQUESTED",
    "PENDING",
    "APPROVED",
    "REJECTED",
})
DECISION_STATUSES = frozenset({"APPROVED", "REJECTED"})
OUTPUT_FORMATS = frozenset({"md", "html", "txt"})


def _freeze(value):
    """Fige listes et tuples ; toute autre valeur est laissée au validateur."""
    return tuple(value) if isinstance(value, (list, tuple)) else value


@dataclass(frozen=True)
class EvidenceRef:
    ref_id: str
    kind: str
    source_ref: str
    sha256: str
    captured_at: Optional[str] = None


@dataclass(frozen=True)
class TestResult:
    name: str
    command: tuple[str, ...]
    status: str
    returncode: Optional[int]
    evidence_refs: tuple[str, ...]
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _freeze(self.command))
        object.__setattr__(self, "evidence_refs", _freeze(self.evidence_refs))


@dataclass(frozen=True)
class HumanDecision:
    decision_id: str
    status: str
    approver: str
    decided_at: str
    evidence_ref: Optional[str] = None
    purpose: str = "REPORT_DELIVERY"


@dataclass(frozen=True)
class ProjectRef:
    project_id: str
    commit_sha: Optional[str]
    target_fingerprint: Optional[str]


@dataclass(frozen=True)
class TemplateDefinition:
    template_id: str
    version: str
    schema_version: str
    required_sections: tuple[str, ...]
    supported_formats: tuple[str, ...]
    template_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_sections", _freeze(self.required_sections))
        object.__setattr__(self, "supported_formats", _freeze(self.supported_formats))


@dataclass(frozen=True)
class TechnicalReport:
    report_id: str
    mission_id: str
    generated_at: str
    project: ProjectRef
    template_id: str
    template_version: str
    template_sha256: str
    engine_version: str
    evidence_refs: tuple[EvidenceRef, ...]
    tests: tuple[TestResult, ...]
    decisions: tuple[HumanDecision, ...]
    validation_status: str
    human_approval: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", _freeze(self.evidence_refs))
        object.__setattr__(self, "tests", _freeze(self.tests))
        object.__setattr__(self, "decisions", _freeze(self.decisions))


@dataclass(frozen=True)
class DocumentValidationResult:
    ok: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedDocument:
    format: str
    content: str
    content_sha256: str
    report: TechnicalReport
