"""Validation fail-closed du contrat TechnicalReport."""
from __future__ import annotations

from datetime import datetime
import re

from .schema import (
    DECISION_STATUSES,
    ENGINE_VERSION,
    HUMAN_APPROVAL_STATUSES,
    OUTPUT_FORMATS,
    REPORT_SCHEMA_VERSION,
    TEST_STATUSES,
    VALIDATION_STATUSES,
    DocumentValidationResult,
    EvidenceRef,
    HumanDecision,
    ProjectRef,
    TechnicalReport,
    TemplateDefinition,
    TestResult,
)


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
_V1_SECTIONS = ("metadata", "evidence", "tests", "decisions")


def _is_str(value: object) -> bool:
    return isinstance(value, str)


def _is_opt_str(value: object) -> bool:
    return value is None or isinstance(value, str)


def _is_str_tuple(value: object) -> bool:
    return isinstance(value, tuple) and all(isinstance(item, str) for item in value)


def _is_opt_int(value: object) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool))


def _type_errors(report: object, template: object) -> list[str]:
    """Contrôle structurel : aucune comparaison ni regex avant ce passage."""
    errors: list[str] = []
    if not isinstance(template, TemplateDefinition):
        return ["modele de type invalide"]
    if not isinstance(report, TechnicalReport):
        return ["rapport de type invalide"]

    for name in (
        "report_id", "mission_id", "generated_at", "template_id",
        "template_version", "template_sha256", "engine_version",
        "validation_status", "human_approval",
    ):
        if not _is_str(getattr(report, name)):
            errors.append(f"type invalide: {name}")
    for name in ("template_id", "version", "schema_version", "template_sha256"):
        if not _is_str(getattr(template, name)):
            errors.append(f"type invalide: modele.{name}")
    for name in ("required_sections", "supported_formats"):
        if not _is_str_tuple(getattr(template, name)):
            errors.append(f"type invalide: modele.{name}")

    project = report.project
    if not isinstance(project, ProjectRef):
        errors.append("type invalide: project")
    else:
        if not _is_str(project.project_id):
            errors.append("type invalide: project_id")
        if not _is_opt_str(project.commit_sha):
            errors.append("type invalide: commit_sha")
        if not _is_opt_str(project.target_fingerprint):
            errors.append("type invalide: target_fingerprint")

    collections = (
        ("evidence_refs", report.evidence_refs, EvidenceRef),
        ("tests", report.tests, TestResult),
        ("decisions", report.decisions, HumanDecision),
    )
    for label, items, expected in collections:
        if not isinstance(items, tuple):
            errors.append(f"type invalide: {label}")
            continue
        for item in items:
            if not isinstance(item, expected):
                errors.append(f"element invalide dans {label}")
                continue
            if expected is EvidenceRef and not (
                _is_str(item.ref_id) and _is_str(item.kind)
                and _is_str(item.source_ref) and _is_str(item.sha256)
                and _is_opt_str(item.captured_at)
            ):
                errors.append("type invalide: evidence")
            if expected is TestResult and not (
                _is_str(item.name) and _is_str(item.status)
                and _is_str_tuple(item.command)
                and _is_str_tuple(item.evidence_refs)
                and _is_opt_int(item.returncode) and _is_str(item.detail)
            ):
                errors.append("type invalide: test")
            if expected is HumanDecision and not (
                _is_str(item.decision_id) and _is_str(item.status)
                and _is_str(item.approver) and _is_str(item.decided_at)
                and _is_opt_str(item.evidence_ref) and _is_str(item.purpose)
            ):
                errors.append("type invalide: decision")
    return errors


def _template_errors(template: TemplateDefinition) -> list[str]:
    """Vérifie la définition effective du modèle, pas seulement son empreinte."""
    errors: list[str] = []
    if template.schema_version != REPORT_SCHEMA_VERSION:
        errors.append("schema de modele incompatible")
    if template.required_sections != _V1_SECTIONS:
        errors.append("sections requises du modele incompatibles")
    formats = template.supported_formats
    if (
        not formats
        or not set(formats) <= OUTPUT_FORMATS
        or len(formats) != len(set(formats))
    ):
        errors.append("formats du modele invalides")
    return errors


def _canonical_timestamp(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return (
        parsed.tzinfo is not None
        and parsed.utcoffset() is not None
        and parsed.isoformat(timespec="seconds") == value
    )


def validate_report(
    report: TechnicalReport,
    template: TemplateDefinition,
) -> DocumentValidationResult:
    """Vérifie le contrat sans créer, interpréter ou chercher de preuve."""
    errors: list[str] = _type_errors(report, template)
    if errors:
        return DocumentValidationResult(ok=False, errors=tuple(errors))
    errors.extend(_template_errors(template))

    if not _IDENTIFIER_RE.fullmatch(report.report_id):
        errors.append("report_id invalide")
    if not _IDENTIFIER_RE.fullmatch(report.mission_id):
        errors.append("mission_id invalide")
    if not _canonical_timestamp(report.generated_at):
        errors.append("generated_at doit etre ISO-8601 avec timezone et secondes")
    if not isinstance(report.project.project_id, str) or not report.project.project_id:
        errors.append("project_id obligatoire")
    if report.project.commit_sha is not None and not _GIT_SHA_RE.fullmatch(
        report.project.commit_sha
    ):
        errors.append("commit_sha invalide")
    if report.project.target_fingerprint is not None and not _SHA256_RE.fullmatch(
        report.project.target_fingerprint
    ):
        errors.append("target_fingerprint invalide")
    if report.engine_version != ENGINE_VERSION:
        errors.append("version du moteur incompatible")
    if report.validation_status not in VALIDATION_STATUSES:
        errors.append("validation_status invalide")
    if report.human_approval not in HUMAN_APPROVAL_STATUSES:
        errors.append("human_approval invalide")

    if (
        report.template_id != template.template_id
        or report.template_version != template.version
        or report.template_sha256 != template.template_sha256
    ):
        errors.append("reference de modele contradictoire")

    evidence_by_id = {}
    source_hashes: dict[str, str] = {}
    for evidence in report.evidence_refs:
        if not _IDENTIFIER_RE.fullmatch(evidence.ref_id):
            errors.append("evidence ref_id invalide")
        if evidence.ref_id in evidence_by_id:
            errors.append(f"evidence ref_id duplique: {evidence.ref_id}")
        evidence_by_id[evidence.ref_id] = evidence
        if not evidence.kind or not evidence.source_ref:
            errors.append(f"evidence incomplete: {evidence.ref_id}")
        if not _SHA256_RE.fullmatch(evidence.sha256):
            errors.append(f"SHA-256 evidence invalide: {evidence.ref_id}")
        existing_sha = source_hashes.get(evidence.source_ref)
        if existing_sha is not None and existing_sha != evidence.sha256:
            errors.append(f"preuve contradictoire: {evidence.source_ref}")
        source_hashes[evidence.source_ref] = evidence.sha256
        if evidence.captured_at is not None and not _canonical_timestamp(
            evidence.captured_at
        ):
            errors.append(f"captured_at invalide: {evidence.ref_id}")

    test_names: set[str] = set()
    for test in report.tests:
        if not isinstance(test.name, str) or not test.name:
            errors.append("test sans nom")
        elif test.name in test_names:
            errors.append(f"nom de test duplique: {test.name}")
        test_names.add(test.name)
        if test.status not in TEST_STATUSES:
            errors.append(f"statut de test invalide: {test.name}")
            continue
        if tuple(sorted(test.evidence_refs)) != test.evidence_refs:
            errors.append(f"references de preuve non normalisees: {test.name}")
        if len(set(test.evidence_refs)) != len(test.evidence_refs):
            errors.append(f"references de preuve dupliquees: {test.name}")
        if any(reference not in evidence_by_id for reference in test.evidence_refs):
            errors.append(f"preuve de test inconnue: {test.name}")

        executed = test.status.startswith("EXECUTED_")
        if executed and not test.evidence_refs:
            errors.append(f"test execute sans preuve: {test.name}")
        if executed and not test.command:
            errors.append(f"test execute sans commande: {test.name}")
        if test.status == "EXECUTED_PASS" and test.returncode != 0:
            errors.append(f"PASS sans code retour 0: {test.name}")
        if test.status == "EXECUTED_FAIL" and (
            test.returncode is None or test.returncode == 0
        ):
            errors.append(f"FAIL sans code retour non nul: {test.name}")
        if not executed and test.returncode is not None:
            errors.append(f"test non execute avec code retour: {test.name}")
        if not executed and test.evidence_refs:
            errors.append(f"test non execute avec preuve d execution: {test.name}")

    delivery_decisions = []
    decision_ids: set[str] = set()
    for decision in report.decisions:
        if not _IDENTIFIER_RE.fullmatch(decision.decision_id):
            errors.append("decision_id invalide")
        elif decision.decision_id in decision_ids:
            errors.append(f"decision_id duplique: {decision.decision_id}")
        decision_ids.add(decision.decision_id)
        if decision.status not in DECISION_STATUSES:
            errors.append(f"statut de decision invalide: {decision.decision_id}")
        if not decision.approver or not _canonical_timestamp(decision.decided_at):
            errors.append(f"decision incomplete: {decision.decision_id}")
        if decision.purpose != "REPORT_DELIVERY":
            errors.append(f"decision hors livraison: {decision.decision_id}")
        else:
            delivery_decisions.append(decision)
        if decision.evidence_ref is not None and decision.evidence_ref not in evidence_by_id:
            errors.append(f"preuve de decision inconnue: {decision.decision_id}")

    delivery_statuses = {decision.status for decision in delivery_decisions}
    if {"APPROVED", "REJECTED"} <= delivery_statuses:
        errors.append("decisions de livraison contradictoires: APPROVED et REJECTED")
    if report.human_approval == "APPROVED" and not any(
        decision.status == "APPROVED" for decision in delivery_decisions
    ):
        errors.append("approbation humaine sans decision APPROVED")
    if report.human_approval == "REJECTED" and not any(
        decision.status == "REJECTED" for decision in delivery_decisions
    ):
        errors.append("rejet humain sans decision REJECTED")
    if report.human_approval in {"NOT_REQUESTED", "PENDING"} and delivery_decisions:
        errors.append("decision de livraison incompatible avec l etat humain")

    return DocumentValidationResult(ok=not errors, errors=tuple(errors))
