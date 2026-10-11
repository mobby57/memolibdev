"""Orchestration en mémoire du rendu documentaire."""
from __future__ import annotations

import hashlib
from dataclasses import replace

from .renderers import render
from .schema import GeneratedDocument, TechnicalReport, TemplateDefinition
from .validator import validate_report


def generate(
    report: TechnicalReport,
    template: TemplateDefinition,
    format_name: str,
) -> GeneratedDocument:
    """Valide puis rend un rapport en mémoire, sans écriture et sans réseau."""
    if report.validation_status != "DRAFT":
        raise ValueError(
            "seul un rapport DRAFT peut etre valide et rendu"
        )
    validation = validate_report(report, template)
    if not validation.ok:
        raise ValueError("rapport invalide: " + "; ".join(validation.errors))
    if format_name not in template.supported_formats:
        raise ValueError(f"format absent du modele: {format_name!r}")

    validated_report = replace(report, validation_status="VALID")
    content = render(validated_report, template, format_name)
    return GeneratedDocument(
        format=format_name,
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        report=validated_report,
    )
