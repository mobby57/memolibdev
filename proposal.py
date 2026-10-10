"""
MemoLibDev — V0.3 : Proposal (modèle de TRANSPORT, descriptif, sans autorité)
=============================================================================

Objet DÉDIÉ qui transporte, jusqu'à la façade puis l'UI, la proposition
DÉJÀ produite par le pipeline CODER (agent_loop §4.7) :

        plan (CodePlan) + new_content (mémoire) + diff (git réel)

Pourquoi un objet dédié ?
    AgentReport reste INCHANGÉ dans sa forme actuelle (compatibilité des 27
    tests D6.0 + humanize/facade). On AJOUTE seulement un champ optionnel
    `proposal` (par défaut None) rempli UNIQUEMENT quand le pipeline a
    réellement produit un diff. Rien d'autre ne change.

RÈGLE GRAVÉE (identique à humanize/façade) :
    « Une proposition est STRICTEMENT DESCRIPTIVE. »
    Construire une Proposal NE DOIT PAS :
        - écrire sur le disque ;        - appeler D5.9 ;
        - modifier le workspace ;       - créer un commit ;
        - pousser ;                     - modifier MemoLib ;
        - fabriquer une autorisation.

    Le `diff` est une REPRÉSENTATION de ce qui POURRAIT être appliqué.
    Il n'est jamais appliqué pendant la phase PROPOSER.

ANTI-FABRICATION (exigence §3) :
    Chaque champ provient d'un artefact RÉELLEMENT produit par le pipeline.
    Aucune donnée n'est inventée. Quand une donnée n'existe pas réellement
    dans la pile déterministe actuelle (ex. un score de confiance calculé,
    une preuve au-delà de l'auto-provenance), le champ vaut `None` /
    `"non disponible"` — JAMAIS une valeur fabriquée.

Imports volontairement limités à la stdlib (dataclasses, hashlib, typing).
Aucun import de git/subprocess/D5.8/D5.9 : ce module ne fait que PROJETER
des objets déjà calculés en amont.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import hashlib


# Marqueur explicite pour « donnée non réellement disponible » (jamais
# confondu avec une valeur fabriquée).
NON_DISPONIBLE = "non disponible"


@dataclass(frozen=True)
class ProposalFile:
    """
    Un fichier concerné par la proposition. Tous les champs proviennent
    d'artefacts réels (FileTarget, contenu lu, CodePlan, diff). Les champs
    sans source réelle valent None.
    """
    path: str                              # FileTarget.path (réel)
    sha_before: Optional[str]              # SHA du contenu courant (réel) ou None
    lines: Optional[list]                  # lignes impactées (du CodePlan) ou None
    current_excerpt: Optional[str]         # extrait du contenu courant (réel)
    proposed_change: Optional[str]         # description issue du CodePlan (réelle)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "sha_before": self.sha_before,
            "lines": list(self.lines) if self.lines is not None else None,
            "current_excerpt": self.current_excerpt,
            "proposed_change": self.proposed_change,
        }


@dataclass(frozen=True)
class Proposal:
    """
    Proposition descriptive, immuable (frozen). Transporte le diff RÉEL du
    Core. N'EST PAS une autorisation et NE DÉCLENCHE AUCUNE application.

    `requires_human_approval` est TOUJOURS True pour une proposition : une
    application ne peut survenir qu'après HumanApproval via D5.8/D5.9. Ce
    booléen est DESCRIPTIF (il ne confère aucun pouvoir), conforme à
    « CAPACITÉ ≠ AUTORISATION ≠ APPLICATION ».
    """
    mission_id: Optional[str] = None
    summary: Optional[str] = None
    reason: Optional[str] = None
    confidence: Optional[str] = None       # HIGH|MEDIUM|LOW (engine) ou None
    risk: Optional[str] = None             # du contexte mission (réel) ou None
    scope: Optional[str] = None            # FileTarget.scope (réel) ou None
    files: tuple = ()                      # tuple[ProposalFile, ...]
    diff_preview: Optional[str] = None     # = diff RÉEL du Core (jamais recalculé)
    evidence: Optional[str] = None         # auto-provenance réelle ou NON_DISPONIBLE
    reversible: Optional[bool] = None      # de l'ActionDossier (réel) ou None
    requires_human_approval: bool = True   # invariant descriptif
    # V0.3.1 : explications déterministes de la confiance (jamais fabriquées,
    # jamais issues d'un LLM). Vides si aucune confiance calculée.
    confidence_reasons: tuple = ()         # tuple[str, ...]
    confidence_evidence: tuple = ()        # tuple[str, ...]
    confidence_gates: tuple = ()           # tuple[str, ...] (gates déclenchés)
    # V0.4.1 : identité immuable de la proposition + SHA-256 des OCTETS EXACTS
    # du diff (diff.encode("utf-8")). Permettent de lier la décision humaine
    # au patch exact. None si aucun diff réel n'a été produit.
    proposal_id: Optional[str] = None
    diff_sha256: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "summary": self.summary,
            "reason": self.reason,
            "confidence": self.confidence,
            "risk": self.risk,
            "scope": self.scope,
            "files": [f.to_dict() for f in self.files],
            "diff_preview": self.diff_preview,
            "evidence": self.evidence,
            "reversible": self.reversible,
            "requires_human_approval": self.requires_human_approval,
            "confidence_reasons": list(self.confidence_reasons),
            "confidence_evidence": list(self.confidence_evidence),
            "confidence_gates": list(self.confidence_gates),
            "proposal_id": self.proposal_id,
            "diff_sha256": self.diff_sha256,
        }


# ------------------------------------------------------------------
# Extraction d'extrait sûr (lecture seule, aucune écriture).
# ------------------------------------------------------------------

def _excerpt_for_change(current_content: str, change, max_lines: int = 6) -> Optional[str]:
    """
    Extrait, depuis le CONTENU COURANT RÉEL, les lignes autour du
    changement, pour un affichage « ce qu'il y a aujourd'hui ». Ne
    fabrique rien : si on ne peut pas localiser, retourne None.
    """
    if not current_content:
        return None
    lines = current_content.splitlines()
    # REPLACE/DELETE : on tente de retrouver le fragment courant réel.
    frag = getattr(change, "old_fragment", "") or ""
    if frag.strip() and frag in current_content:
        start_char = current_content.index(frag)
        start_line = current_content[:start_char].count("\n")
        end_line = start_line + frag.count("\n")
        lo = max(0, start_line)
        hi = min(len(lines), end_line + 1)
        snippet = "\n".join(lines[lo:hi])
        return snippet if snippet.strip() else None
    # APPEND : il n'y a pas d'extrait courant pertinent (ajout en fin).
    return None


def _lines_for_change(current_content: str, change) -> Optional[list]:
    """
    Détermine les lignes impactées À PARTIR du CodeChange réel. Pour un
    APPEND global (line == 0), il n'y a pas de ligne existante précise :
    retourne None (jamais une ligne inventée).
    """
    line = getattr(change, "line", 0) or 0
    if line and line > 0:
        frag = getattr(change, "old_fragment", "") or ""
        span = frag.count("\n") if frag else 0
        return [line, line + span] if span else [line]
    return None


# ------------------------------------------------------------------
# BUILDER : projette les artefacts RÉELS du pipeline en Proposal.
# ------------------------------------------------------------------

def build_proposal(
    *,
    mission_id: Optional[str],
    request_text: Optional[str],
    reason: Optional[str],
    code_plan,                         # CodePlan réel (code_adapter) ou None
    diff: Optional[str],               # diff RÉEL (git) du Core
    current_content: Optional[str],    # contenu courant RÉELLEMENT lu
    file_target,                       # FileTarget réel ou None
    sha_before: Optional[str],         # SHA RÉEL (texte) du contenu courant
    risk: Optional[str] = None,        # risk_level réel de la mission
    reversible: Optional[bool] = None, # réversibilité RÉELLE (ActionDossier)
    confidence: Optional[str] = None,  # HIGH|MEDIUM|LOW du moteur, ou None
    evidence: Optional[str] = None,    # auto-provenance réelle ou None
    confidence_reasons: tuple = (),    # explications déterministes (engine)
    confidence_evidence: tuple = (),   # preuves utilisées (engine)
    confidence_gates: tuple = (),      # gates déclenchés (engine)
    proposal_id: Optional[str] = None, # identité immuable de la proposition
) -> Proposal:
    """
    Construit une Proposal UNIQUEMENT à partir d'artefacts réels. Aucune
    valeur n'est inventée : tout champ sans source réelle reste None ou
    NON_DISPONIBLE. Ne lit/écrit AUCUN fichier (le contenu est fourni),
    n'appelle NI git NI D5.8 NI D5.9.

    `diff` : le diff RÉEL produit par le Core (code_adapter.generate_diff_git).
             Il est transporté TEL QUEL. Jamais recalculé ici.
    """
    # scope : vient du FileTarget réel (jamais fabriqué).
    scope = getattr(file_target, "scope", None) if file_target is not None else None
    path = getattr(file_target, "path", None) if file_target is not None else None

    # Fichiers concernés : dérivés du CodePlan réel.
    files: list[ProposalFile] = []
    changes = getattr(code_plan, "changes", None) if code_plan is not None else None
    if path and changes:
        for change in changes:
            proposed = getattr(change, "description", None)
            files.append(ProposalFile(
                path=path,
                sha_before=sha_before,                      # SHA réel ou None
                lines=_lines_for_change(current_content or "", change),
                current_excerpt=_excerpt_for_change(current_content or "", change),
                proposed_change=proposed,
            ))
    elif path:
        # Un fichier cible existe mais aucun change détaillé : on expose le
        # fichier et son SHA réel, sans inventer de changement.
        files.append(ProposalFile(
            path=path, sha_before=sha_before, lines=None,
            current_excerpt=None, proposed_change=None,
        ))

    # summary : dérivé de l'intent réel du plan si présent, sinon de la
    # requête réelle. Jamais inventé.
    summary = None
    intent = getattr(code_plan, "intent", None) if code_plan is not None else None
    if intent and str(intent).strip():
        summary = str(intent).strip()
    elif request_text and str(request_text).strip():
        summary = str(request_text).strip()

    # evidence : en v1 la pile fournit une AUTO-PROVENANCE (le scope est sa
    # propre source). On la mentionne factuellement si un chemin existe ;
    # sinon NON_DISPONIBLE. Aucune preuve n'est fabriquée.
    if evidence is None:
        evidence = (f"auto-provenance: {path}" if path else NON_DISPONIBLE)

    # diff_preview : le diff RÉEL, transporté tel quel (None si vide).
    diff_preview = diff if (diff and diff.strip()) else None

    # V0.4.1 : diff_sha256 sur les OCTETS EXACTS (diff.encode("utf-8")),
    # via l'helper AUTORITÉ de coder_authorization pour garantir des octets
    # canoniques identiques à ceux consommés par D5.9. None si pas de diff.
    computed_diff_sha = None
    if diff_preview is not None:
        from coder_authorization import diff_sha256 as _diff_sha256
        computed_diff_sha = _diff_sha256(diff)

    return Proposal(
        mission_id=mission_id,
        summary=summary,
        reason=(reason if reason and str(reason).strip() else None),
        confidence=confidence,          # None : pas de score fabriqué
        risk=(risk if risk and str(risk).strip() else None),
        scope=scope,
        files=tuple(files),
        diff_preview=diff_preview,
        evidence=evidence,
        reversible=reversible,
        requires_human_approval=True,
        confidence_reasons=tuple(confidence_reasons or ()),
        confidence_evidence=tuple(confidence_evidence or ()),
        confidence_gates=tuple(confidence_gates or ()),
        proposal_id=proposal_id,
        diff_sha256=computed_diff_sha,
    )


def sha256_text(content: str) -> str:
    """
    SHA256 d'un texte (utilitaire local, lecture seule). Fourni pour les
    tests/afficheurs qui veulent recalculer un SHA sur un contenu DÉJÀ en
    mémoire — jamais pour lire un fichier.
    """
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()
