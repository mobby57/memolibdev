"""
MemoLibDev — Confidence Engine (déterministe, sans LLM)
=======================================================

Moteur partagé de scoring déterministe pour les propositions (V0.3.1)
et les analyses (V0.1.1). Aucun LLM, aucune I/O, aucune écriture.

Deux contrats publics :
  - score_proposal(...)     -> ConfidenceResult  (utilisé par agent_loop §4.7)
  - analysis_level_and_strong(...) -> (level, strong_candidates)  (analysis_builder)

Aucun import circulaire : ce module n'importe rien d'analysis_builder ni
d'agent_loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ------------------------------------------------------------------
# Contrat 1 : score_proposal (utilisé par agent_loop §4.7)
# ------------------------------------------------------------------

@dataclass(frozen=True)
class ConfidenceResult:
    """Résultat immuable du scoring d'une proposition."""
    level: str                           # "HIGH" | "MEDIUM" | "LOW"
    reasons: tuple[str, ...]
    evidence_used: tuple[str, ...]
    gates: tuple[str, ...]


def score_proposal(
    *,
    has_diff: bool,
    diff_valid: bool,
    diff_deterministic: bool,
    scope_verifiable: bool,
    has_fresh_sha: bool,
    is_stale: bool,
    causal_evidence: bool,
    contradiction: bool,
) -> ConfidenceResult:
    """
    Score déterministe d'une proposition. Aucun LLM, aucun comptage de
    volume. Les signaux sont binaires et proviennent du Core.

    Gates (tous additifs, fail-closed) :
      G1 : has_diff + diff_valid => un diff réel et valide existe ;
      G2 : diff_deterministic     => le diff est produit par git (reproductible) ;
      G3 : scope_verifiable       => le FileTarget porte un scope résolu ;
      G4 : has_fresh_sha          => le contexte est frais (non dérivé) ;
      G5 : causal_evidence        => le plan contient un REPLACE ancré (non repli) ;
      G6 : !contradiction         => aucune contradiction détectée.

    Niveaux :
      HIGH   : G1 + G2 + G3 + G4 + G5 + G6  (tous les signaux présents) ;
      MEDIUM : G1 + G2 + G3 + G6, mais G4 ou G5 manquant ;
      LOW    : sinon (diff absent/invalide, scope non vérifiable, contradiction).
    """
    reasons: list[str] = []
    evidence: list[str] = []
    gates: list[str] = []

    if has_diff:
        evidence.append("diff réel produit par le Core")
    else:
        reasons.append("aucun diff réel produit")
        gates.append("G1_FAIL: no diff")

    if diff_valid:
        evidence.append("diff validé par code_adapter.validate")
    else:
        reasons.append("diff invalide (code_adapter.validate)")
        gates.append("G1_FAIL: invalid diff")

    if diff_deterministic:
        evidence.append("diff déterministe (git)")
        gates.append("G2_PASS: deterministic diff")
    else:
        reasons.append("diff non déterministe")
        gates.append("G2_FAIL: non-deterministic")

    if scope_verifiable:
        evidence.append("scope résolu via FileTarget")
        gates.append("G3_PASS: verifiable scope")
    else:
        reasons.append("scope non résolu")
        gates.append("G3_FAIL: no scope")

    if has_fresh_sha:
        evidence.append("contexte frais (SHA cohérent)")
        gates.append("G4_PASS: fresh sha")
    else:
        reasons.append("contexte potentiellement dérivé")
        gates.append("G4_WARN: stale context")

    if causal_evidence:
        evidence.append("changement localisé (REPLACE ancré)")
        gates.append("G5_PASS: causal evidence")
    else:
        reasons.append("changement non ancré (APPEND de repli possible)")
        gates.append("G5_WARN: no causal anchor")

    if contradiction:
        reasons.append("contradiction détectée")
        gates.append("G6_FAIL: contradiction")
    else:
        gates.append("G6_PASS: no contradiction")

    all_core = has_diff and diff_valid and diff_deterministic and scope_verifiable and not contradiction
    all_strong = all_core and has_fresh_sha and causal_evidence

    if all_strong:
        level = "HIGH"
    elif all_core:
        level = "MEDIUM"
    else:
        level = "LOW"

    return ConfidenceResult(
        level=level,
        reasons=tuple(reasons),
        evidence_used=tuple(evidence),
        gates=tuple(gates),
    )


# ------------------------------------------------------------------
# Contrat 2 : analysis_level_and_strong (utilisé par analysis_builder)
# ------------------------------------------------------------------

_BEHAVIORAL_CATEGORIES = (
    "REDIRECT", "ROUTE", "CONDITION", "ERROR_HANDLING",
    "LOCALE", "DEFINITION", "DOC_HEADING",
)


def _behavioral_relevant(facts: list, relevant_cats: tuple) -> list:
    """Faits à la fois pertinents au domaine ET comportementaux (causaux)."""
    return [
        f for f in facts
        if f.categorie in relevant_cats
        and f.categorie in _BEHAVIORAL_CATEGORIES
    ]


def _strong_candidate_files(relevant_facts: list, relevant_cats: tuple) -> dict:
    """
    Regroupe les faits causaux par fichier. Un fichier est un « candidat
    fort » s'il concentre >= 2 catégories comportementales distinctes.
    """
    by_file: dict[str, set] = {}
    for f in _behavioral_relevant(relevant_facts, relevant_cats):
        by_file.setdefault(f.fichier, set()).add(f.categorie)
    return {path: cats for path, cats in by_file.items() if len(cats) >= 2}


def analysis_level_and_strong(
    relevant_facts: list,
    relevant_cats: tuple,
    files_count: int,
    any_preview: bool,
) -> tuple[str, dict]:
    """
    Calcule le niveau de confiance (HIGH/MEDIUM/LOW) et les candidats forts.

      - HIGH   : exactement un fichier candidat fort (>= 2 catégories
                 comportementales distinctes) et aucun autre fichier fort ;
      - MEDIUM : plusieurs candidats forts, ou au moins un fait pertinent
                 mais preuve causale incomplète ;
      - LOW    : aucun preview exploitable ou aucun fait pertinent.
    """
    if not any_preview or not relevant_facts:
        return "LOW", {}

    strong = _strong_candidate_files(relevant_facts, relevant_cats)

    if len(strong) == 1:
        return "HIGH", strong

    if len(strong) >= 2:
        return "MEDIUM", strong

    # Pas de candidat fort mais des faits pertinents existent
    if relevant_facts:
        return "MEDIUM", strong

    return "LOW", strong
