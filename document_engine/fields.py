"""Chargement et validation des champs declares par un template."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path


class FieldsError(ValueError):
    pass


def load_fields(template_dir):
    template_dir = Path(template_dir)
    p = template_dir / "fields.json"
    if not p.is_file():
        raise FieldsError(f"fields.json introuvable : {p}")
    return json.loads(p.read_text(encoding="utf-8-sig"))


def _get_nested(data, dotted):
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def champs_manquants(fields, data):
    """Champs OBLIGATOIRES absents ou vides."""
    manquants = []
    for chemin, spec in fields.get("champs", {}).items():
        if not spec.get("obligatoire"):
            continue
        val = _get_nested(data, chemin)
        if val is None or (isinstance(val, str) and not val.strip()) or \
           (isinstance(val, list) and not val):
            manquants.append({
                "chemin": chemin,
                "question": spec.get("question", chemin),
                "type": spec.get("type", "texte"),
                "exemple": spec.get("exemple"),
                "sous_champs": spec.get("sous_champs"),
            })
    return manquants


def appliquer_defauts(fields, data):
    """Remplit les OPTIONNELS avec leur vrai defaut (pas l'exemple)."""
    for chemin, spec in fields.get("champs", {}).items():
        if spec.get("obligatoire"):
            continue
        val = _get_nested(data, chemin)
        if val:
            continue
        defaut = spec.get("defaut", "")
        if defaut == "aujourd'hui":
            defaut = datetime.now().strftime("%d/%m/%Y")
        elif defaut == "+30 jours":
            defaut = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")
        elif defaut == "auto":
            continue
        if defaut:
            parts = chemin.split(".")
            cur = data
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
            cur[parts[-1]] = defaut
    return data
