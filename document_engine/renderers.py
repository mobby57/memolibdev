"""Rendus purs, déterministes et sans écriture du rapport technique.

Les valeurs rendues sont une représentation normalisée (NFC, fins de ligne
unifiées) et échappée (antislash doublé, retours à la ligne en ``\\n``, caractères
Markdown ou séparateur échappés) : ce ne sont pas les octets d'origine des preuves.
"""
from __future__ import annotations

import html
import unicodedata

from .schema import TechnicalReport, TemplateDefinition


def _ordered(report: TechnicalReport):
    return (
        tuple(sorted(report.evidence_refs, key=lambda item: item.ref_id)),
        tuple(sorted(report.tests, key=lambda item: item.name)),
        tuple(sorted(report.decisions, key=lambda item: item.decision_id)),
    )


def _normalized_text(value: object) -> str:
    return unicodedata.normalize(
        "NFC",
        str(value).replace("\r\n", "\n").replace("\r", "\n"),
    )


_ALWAYS_ESCAPED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Zl", "Zp"})
# Liste explicite, indépendante de la version d'unicodedata.
_ALWAYS_ESCAPED_RANGES = (
    (0x0000, 0x001F), (0x007F, 0x009F), (0x00AD, 0x00AD),
    (0x061C, 0x061C), (0x180E, 0x180E), (0x200B, 0x200F),
    (0x2028, 0x202E), (0x2060, 0x206F), (0xD800, 0xDFFF),
    (0xE000, 0xF8FF), (0xFEFF, 0xFEFF), (0xFFF9, 0xFFFB),
)


def _must_escape(character: str) -> bool:
    code = ord(character)
    if any(low <= code <= high for low, high in _ALWAYS_ESCAPED_RANGES):
        return True
    return unicodedata.category(character) in _ALWAYS_ESCAPED_CATEGORIES


def _escape_unsafe(text: str) -> str:
    """Remplace les caractères de contrôle/format par \\uXXXX ou \\UXXXXXXXX.

    Le saut de ligne est traité avant (devenu ``\\n``) ; l'antislash est déjà
    doublé, donc un ``\\u2028`` saisi littéralement reste distinct d'un vrai U+2028.
    """
    return "".join(
        (f"\\u{ord(c):04x}" if ord(c) <= 0xFFFF else f"\\U{ord(c):08x}")
        if c != "\n" and _must_escape(c) else c
        for c in text
    )


def _flat_text(value: object, *, markdown: bool = False) -> str:
    text = _normalized_text(value).replace("\\", "\\\\")
    if markdown:
        for character in "`*_{}[]()#+-.!|<>":
            text = text.replace(character, f"\\{character}")
    else:
        text = text.replace("|", "\\|")
    return _escape_unsafe(text.replace("\n", "\\n"))


def render_markdown(report: TechnicalReport, template: TemplateDefinition) -> str:
    evidence, tests, decisions = _ordered(report)
    lines = [
        "# Rapport technique",
        "",
        f"- Rapport : {_flat_text(report.report_id, markdown=True)}",
        f"- Mission : {_flat_text(report.mission_id, markdown=True)}",
        f"- Genere le : {_flat_text(report.generated_at, markdown=True)}",
        f"- Projet : {_flat_text(report.project.project_id, markdown=True)}",
        f"- Commit : {_flat_text(report.project.commit_sha or 'preuve indisponible', markdown=True)}",
        f"- Modele : {_flat_text(template.template_id, markdown=True)} v{_flat_text(template.version, markdown=True)}",
        f"- Validation documentaire : {_flat_text(report.validation_status, markdown=True)}",
        f"- Approbation humaine : {_flat_text(report.human_approval, markdown=True)}",
        "",
        "## Preuves",
    ]
    lines.extend(
        f"- {_flat_text(item.ref_id, markdown=True)} ({_flat_text(item.kind, markdown=True)}) : "
        f"{_flat_text(item.source_ref, markdown=True)} SHA-256 {_flat_text(item.sha256, markdown=True)}"
        for item in evidence
    )
    lines.extend(["", "## Tests"])
    lines.extend(
        f"- {_flat_text(item.name, markdown=True)} : "
        f"{_flat_text(item.status, markdown=True)}"
        f" — commande: {_flat_text(' '.join(item.command) if item.command else 'non executee', markdown=True)}"
        for item in tests
    )
    lines.extend(["", "## Decisions humaines"])
    lines.extend(
        f"- {_flat_text(item.decision_id, markdown=True)} : "
        f"{_flat_text(item.status, markdown=True)} par {_flat_text(item.approver, markdown=True)}"
        f" le {_flat_text(item.decided_at, markdown=True)} "
        f"(objet : {_flat_text(item.purpose, markdown=True)})"
        for item in decisions
    )
    return "\n".join(lines) + "\n"


def render_txt(report: TechnicalReport, template: TemplateDefinition) -> str:
    evidence, tests, decisions = _ordered(report)
    lines = [
        "RAPPORT TECHNIQUE",
        f"Rapport: {_flat_text(report.report_id)}",
        f"Mission: {_flat_text(report.mission_id)}",
        f"Genere le: {_flat_text(report.generated_at)}",
        f"Projet: {_flat_text(report.project.project_id)}",
        f"Commit: {_flat_text(report.project.commit_sha or 'preuve indisponible')}",
        f"Modele: {_flat_text(template.template_id)} v{_flat_text(template.version)}",
        f"Validation documentaire: {_flat_text(report.validation_status)}",
        f"Approbation humaine: {_flat_text(report.human_approval)}",
        "",
        "PREUVES",
    ]
    lines.extend(
        f"{_flat_text(item.ref_id)} | {_flat_text(item.kind)} | "
        f"{_flat_text(item.source_ref)} | {_flat_text(item.sha256)}"
        for item in evidence
    )
    lines.extend(["", "TESTS"])
    lines.extend(
        f"{_flat_text(item.name)} | {_flat_text(item.status)} | "
        f"{_flat_text(' '.join(item.command) if item.command else 'non executee')}"
        for item in tests
    )
    lines.extend(["", "DECISIONS HUMAINES"])
    lines.extend(
        f"{_flat_text(item.decision_id)} | {_flat_text(item.status)} | "
        f"{_flat_text(item.approver)} | {_flat_text(item.decided_at)} | "
        f"{_flat_text(item.purpose)}"
        for item in decisions
    )
    return "\n".join(lines) + "\n"


def render_html(report: TechnicalReport, template: TemplateDefinition) -> str:
    evidence, tests, decisions = _ordered(report)
    escape = lambda value: html.escape(_flat_text(value), quote=True)
    rows = lambda values: "".join(
        f"<tr>{''.join(f'<td>{escape(cell)}</td>' for cell in row)}</tr>"
        for row in values
    )
    return (
        "<!doctype html>\n<html lang=\"fr\">\n<head><meta charset=\"utf-8\">"
        "<title>Rapport technique</title></head>\n<body>\n"
        "<h1>Rapport technique</h1>\n"
        "<dl>"
        f"<dt>Rapport</dt><dd>{escape(report.report_id)}</dd>"
        f"<dt>Mission</dt><dd>{escape(report.mission_id)}</dd>"
        f"<dt>Genere le</dt><dd>{escape(report.generated_at)}</dd>"
        f"<dt>Projet</dt><dd>{escape(report.project.project_id)}</dd>"
        f"<dt>Commit</dt><dd>{escape(report.project.commit_sha or 'preuve indisponible')}</dd>"
        f"<dt>Modele</dt><dd>{escape(template.template_id)} v{escape(template.version)}</dd>"
        f"<dt>Validation documentaire</dt><dd>{escape(report.validation_status)}</dd>"
        f"<dt>Approbation humaine</dt><dd>{escape(report.human_approval)}</dd>"
        "</dl>\n<h2>Preuves</h2>\n<table><tbody>"
        + rows((item.ref_id, item.kind, item.source_ref, item.sha256) for item in evidence)
        + "</tbody></table>\n<h2>Tests</h2>\n<table><tbody>"
        + rows((item.name, item.status, " ".join(item.command) or "non executee") for item in tests)
        + "</tbody></table>\n<h2>Decisions humaines</h2>\n<table><tbody>"
        + rows((item.decision_id, item.status, item.approver, item.decided_at, item.purpose) for item in decisions)
        + "</tbody></table>\n</body>\n</html>\n"
    )


def render(report: TechnicalReport, template: TemplateDefinition, format_name: str) -> str:
    if format_name == "md":
        return render_markdown(report, template)
    if format_name == "txt":
        return render_txt(report, template)
    if format_name == "html":
        return render_html(report, template)
    raise ValueError(f"format de rendu non supporte: {format_name!r}")
