"""Catalogue explicite et versionné des modèles documentaires."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .schema import OUTPUT_FORMATS, REPORT_SCHEMA_VERSION, TemplateDefinition


_REGISTERED_TEMPLATES = {
    "technical-report-v1": "technical-report-v1.json",
}
_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_REQUIRED_KEYS = frozenset({
    "template_id",
    "version",
    "schema_version",
    "required_sections",
    "supported_formats",
})
_REQUIRED_SECTIONS = ("metadata", "evidence", "tests", "decisions")


def canonical_template_bytes(payload: dict) -> bytes:
    """Octets UTF-8 canoniques servant à l'empreinte du modèle."""
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def load_registered_template(template_id: str, template_root: Path) -> TemplateDefinition:
    """Charge uniquement un modèle enregistré sous la racine explicitement fournie."""
    if template_id not in _REGISTERED_TEMPLATES:
        raise ValueError(f"modele non enregistre: {template_id!r}")
    if not _IDENTIFIER_RE.fullmatch(template_id):
        raise ValueError("identifiant de modele invalide")

    root = template_root.resolve()
    path = (root / _REGISTERED_TEMPLATES[template_id]).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("chemin de modele hors catalogue") from exc
    if not path.is_file():
        raise ValueError(f"modele enregistre introuvable: {template_id!r}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"modele illisible: {template_id!r}") from exc

    if not isinstance(payload, dict) or frozenset(payload) != _REQUIRED_KEYS:
        raise ValueError("schema de modele invalide")
    if payload["template_id"] != template_id:
        raise ValueError("identifiant du contenu different du catalogue")
    if payload["schema_version"] != REPORT_SCHEMA_VERSION:
        raise ValueError("schema de modele incompatible")
    if not isinstance(payload["version"], str) or not payload["version"]:
        raise ValueError("version de modele invalide")

    sections = payload["required_sections"]
    formats = payload["supported_formats"]
    if (
        not isinstance(sections, list)
        or tuple(sections) != _REQUIRED_SECTIONS
    ):
        raise ValueError("sections requises incompatibles avec le rendu V1")
    if (
        not isinstance(formats, list)
        or not formats
        or not all(isinstance(format_name, str) for format_name in formats)
        or not set(formats) <= OUTPUT_FORMATS
        or len(formats) != len(set(formats))
    ):
        raise ValueError("formats de modele invalides")

    return TemplateDefinition(
        template_id=template_id,
        version=payload["version"],
        schema_version=payload["schema_version"],
        required_sections=tuple(sections),
        supported_formats=tuple(formats),
        template_sha256=hashlib.sha256(canonical_template_bytes(payload)).hexdigest(),
    )
