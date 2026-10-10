"""
MemoLibDev — LLM CONTROLLED v1 : Secret Scanner
================================================

Prérequis DUR du LLM (Phase B1). Avant tout appel à un AIProvider, le
contexte est scanné. Un secret détecté => BLOCK (ou rédaction contrôlée).
Aucun secret ne doit jamais être transmis à un provider.

100 % déterministe, offline, read-only. Aucune écriture, aucun LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


# Motifs déterministes de secrets. Volontairement conservateurs
# (fail-closed : en cas de doute sur un format sensible, on signale).
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("generic_assignment", re.compile(
        r"(?i)(?:api[_-]?key|secret|token|password|passwd|credential)"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{12,}['\"]?")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}")),
]


@dataclass(frozen=True)
class SecretHit:
    source_path: str
    kind: str
    span_preview: str          # extrait masqué (jamais le secret en clair)


@dataclass(frozen=True)
class ScanResult:
    safe: bool
    hits: tuple[SecretHit, ...]

    @property
    def status(self) -> str:
        return "SAFE" if self.safe else "SECRET"


def _mask(text: str, start: int, end: int) -> str:
    """Masque la zone détectée : on ne renvoie jamais le secret en clair."""
    frag = text[start:end]
    if len(frag) <= 6:
        return "***"
    return frag[:3] + "***" + frag[-2:]


def scan_text(source_path: str, text: str) -> list[SecretHit]:
    hits: list[SecretHit] = []
    for kind, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            hits.append(SecretHit(
                source_path=source_path,
                kind=kind,
                span_preview=_mask(text, m.start(), m.end()),
            ))
    return hits


def scan_context(context) -> ScanResult:
    """
    Scanne les aperçus (preview) des fichiers pertinents d'un
    MissionContext ET la mission texte. Déterministe.
    """
    hits: list[SecretHit] = []

    # Mission texte (entrée client) : scannée aussi.
    for h in scan_text("<mission_text>", context.mission_text):
        hits.append(h)

    for rf in context.relevant_files:
        hits.extend(scan_text(rf.path, rf.preview))

    return ScanResult(safe=(len(hits) == 0), hits=tuple(hits))


def redact_text(text: str) -> str:
    """
    Rédaction déterministe : remplace chaque secret détecté par un
    marqueur. Utilisée si la politique = rédaction plutôt que BLOCK.
    """
    redacted = text
    for _kind, pattern in _PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted
