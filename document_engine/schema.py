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
        object.__setattr__(self, "command", tuple(self.command))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))


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
        object.__setattr__(self, "required_sections", tuple(self.required_sections))
        object.__setattr__(self, "supported_formats", tuple(self.supported_formats))


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
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "tests", tuple(self.tests))
        object.__setattr__(self, "decisions", tuple(self.decisions))


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
