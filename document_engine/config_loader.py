"""Charge et valide la config d'un template."""
from __future__ import annotations
import json
from pathlib import Path


class ConfigError(ValueError):
    pass


REQUIRED_KEYS = ("societe", "couleurs", "mentions")


def load_config(template_dir: Path) -> dict:
    """Charge config.json et verifie les cles obligatoires."""
    cfg_path = template_dir / "config.json"
    if not cfg_path.is_file():
        raise ConfigError(f"config.json introuvable : {cfg_path}")
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"config.json invalide : {e}")
    for key in REQUIRED_KEYS:
        if key not in cfg:
            raise ConfigError(f"config.json : cle manquante '{key}'")
    return cfg
