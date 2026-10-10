"""
MemoLibDev — D6.0.1 : Mission Context (objet central)
======================================================

`MissionContext` est le contexte CONTRÔLÉ qu'un futur agent (ou LLM)
recevra à la place du dépôt entier. Il est :

  - construit par le Context Builder (jamais fourni par le client) ;
  - versionné (chaque fichier porte ses deux SHA + HEAD) ;
  - borné (budget) ;
  - traçable (provenance de chaque information) ;
  - invalidable (CONTEXT_STALE si un SHA ou le HEAD diverge).

Règle d'autorité (fondamentale) :
    Le client fournit UNIQUEMENT `mission` (texte). Il ne fournit
    jamais les fichiers d'autorité, le scope, les SHA ni un diff. Le
    Context Builder DÉTERMINE lui-même ce qui entre dans le contexte.
    Les champs issus d'une entrée client (la mission) ne deviennent
    JAMAIS une source d'autorité : seuls les éléments inspectés et
    versionnés (relevant_files/evidence) le sont.

Aucun LLM, aucune écriture, 100 % déterministe/offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from context.context_version import FileVersion


# ------------------------------------------------------------------
# A. Contexte projet
# ------------------------------------------------------------------

@dataclass(frozen=True)
class ProjectContext:
    name: str
    git_root: str
    git_head: str
    branch: str
    fingerprint: str
    technologies: tuple[str, ...]      # détectées (déterministe)
    files_count: int


# ------------------------------------------------------------------
# C. Contexte fichiers (pertinents, bornés, versionnés)
# ------------------------------------------------------------------

@dataclass(frozen=True)
class RelevantFile:
    """Un fichier pertinent retenu, versionné et tracé."""
    path: str
    score: int
    kind: str                 # CODE | DATA | DOC | ... (via FileTarget)
    version: FileVersion      # deux SHA + HEAD
    preview: str              # aperçu borné (budget)


# ------------------------------------------------------------------
# D. Contexte preuves (chaque info répond : d'où, quel SHA, quelle ligne)
# ------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceEntry:
    source_path: str
    text_sha256: str
    byte_sha256: str
    line_start: Optional[int]
    line_end: Optional[int]
    reason: str


# ------------------------------------------------------------------
# E. Contexte historique (missions passées)
# ------------------------------------------------------------------

@dataclass(frozen=True)
class HistoryEntry:
    mission_id: str
    outcome: str              # ex: PROPOSED / REJECTED / APPLIED / ...
    summary: str


# ------------------------------------------------------------------
# B. Contexte mission + objet central
# ------------------------------------------------------------------

@dataclass(frozen=True)
class MissionContext:
    """
    Contexte complet et borné d'une mission. Immuable (frozen).
    `mission_text` est la SEULE donnée d'origine client ; elle n'est
    jamais une autorité (voir `authority_sources`).
    """
    mission_id: str
    mission_text: str                     # entrée client (NON autorité)
    constraints: tuple[str, ...]
    project: ProjectContext
    relevant_files: tuple[RelevantFile, ...]
    evidence: tuple[EvidenceEntry, ...]
    provenance: tuple[str, ...]           # notes de provenance tracées
    history: tuple[HistoryEntry, ...]
    risk_level: str                       # LOW | MEDIUM | HIGH (donnée contrôlée)
    capabilities: tuple[str, ...]         # kinds/adapters disponibles
    budget_reduced: bool
    budget_metrics: Optional[dict] = None  # (5.3) métriques déterministes du budget

    def authority_sources(self) -> tuple[str, ...]:
        """
        Les SEULES sources d'autorité sont les fichiers inspectés et
        versionnés — jamais la mission texte. Expose explicitement
        cette frontière pour l'audit.
        """
        return tuple(rf.path for rf in self.relevant_files)

    def file_versions(self) -> list[FileVersion]:
        return [rf.version for rf in self.relevant_files]

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "mission_text": self.mission_text,
            "constraints": list(self.constraints),
            "project": {
                "name": self.project.name,
                "git_root": self.project.git_root,
                "git_head": self.project.git_head,
                "branch": self.project.branch,
                "fingerprint": self.project.fingerprint,
                "technologies": list(self.project.technologies),
                "files_count": self.project.files_count,
            },
            "relevant_files": [
                {
                    "path": rf.path, "score": rf.score, "kind": rf.kind,
                    "text_sha256": rf.version.text_sha256,
                    "byte_sha256": rf.version.byte_sha256,
                    "git_head": rf.version.git_head,
                }
                for rf in self.relevant_files
            ],
            "evidence": [
                {
                    "source_path": e.source_path,
                    "text_sha256": e.text_sha256,
                    "byte_sha256": e.byte_sha256,
                    "line_start": e.line_start, "line_end": e.line_end,
                    "reason": e.reason,
                }
                for e in self.evidence
            ],
            "provenance": list(self.provenance),
            "history": [
                {"mission_id": h.mission_id, "outcome": h.outcome,
                 "summary": h.summary}
                for h in self.history
            ],
            "risk_level": self.risk_level,
            "capabilities": list(self.capabilities),
            "budget_reduced": self.budget_reduced,
            "budget_metrics": self.budget_metrics,
            "authority_sources": list(self.authority_sources()),
        }
