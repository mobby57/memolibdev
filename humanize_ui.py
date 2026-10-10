"""
MemoLibDev — humanize_ui : vocabulaire humain additif (Comprendre/Proposer/Agir)
================================================================================

Couche de PRÉSENTATION additive, posée AU-DESSUS de `humanize.py` sans jamais
le modifier. Elle ne touche PAS `_MODE_TO_CONTROL` (le mapping technique
Observer/Préparer/Tester/Modifier reste intact, H2 de test_humanize.py reste
vert).

Rôle unique : exposer, pour une interface utilisateur (API/web/desktop), un
vocabulaire plus simple à trois intentions :

    Technique interne                    | Interface utilisateur
    -------------------------------------|----------------------
    READ_ONLY / ANALYSER  (Observer)     | Comprendre
    PROPOSE               (Préparer)     | Proposer
    SUPERVISED_APPLY      (Modifier)     | Agir
    SANDBOX               (Tester)       | (étape interne, invisible)

RÈGLE D'ARCHITECTURE (gravée, identique à humanize.py) :
    « L'UI est une façade. Elle ne possède AUCUNE autorité d'exécution. »

Garanties PAR CONSTRUCTION :
    - fonction PURE : `humanize_ui(result, *, mode, mission) -> dict` ;
    - délègue le fond à `humanize(...)` (brique B) : AUCUNE logique dupliquée ;
    - n'importe NI git, NI D5.9 (apply), NI D5.8 (authorize), NI subprocess ;
    - ne lit/écrit AUCUN fichier ; aucun réseau ; aucun LLM ;
    - ne fabrique AUCUNE approbation : ne retourne que du texte/dict ;
    - conserve INTÉGRALEMENT le niveau technique (`technique`) via humanize ;
    - purement ADDITIVE : ne redéfinit ni ne remplace aucun symbole existant.

Imports volontairement limités à la stdlib + humanize (brique B).
"""

from __future__ import annotations

from typing import Optional

from humanize import humanize, HumanView


# ------------------------------------------------------------------
# Mapping ADDITIF modes techniques -> intentions UI (3 verbes).
# NE REMPLACE PAS _MODE_TO_CONTROL : table parallèle, lecture seule.
# ------------------------------------------------------------------

_MODE_TO_UI = {
    "READ_ONLY": "Comprendre",
    "PROPOSE": "Proposer",
    "SUPERVISED_APPLY": "Agir",
    # SANDBOX est une étape interne : pas de verbe UI dédié (invisible).
    "SANDBOX": None,
}

# Phrase d'intention lisible par un utilisateur non technique.
_UI_INTENT_SENTENCE = {
    "Comprendre": "comprendre votre projet et vous expliquer ce que je trouve",
    "Proposer": "préparer une proposition de modification, sans rien appliquer",
    "Agir": "appliquer une modification, uniquement après votre autorisation",
}


def ui_label(mode: str) -> Optional[str]:
    """
    Traduit un mode technique en verbe UI (Comprendre/Proposer/Agir), ou
    None pour SANDBOX (étape interne, invisible). Lecture seule, pure.
    """
    return _MODE_TO_UI.get(mode, "Comprendre")


def humanize_ui(result, *, mode: str, mission: str) -> dict:
    """
    Produit une vue UI simplifiée (dict) à partir du résultat moteur.

    PURE et déterministe. Délègue tout le fond à `humanize(...)` (brique B)
    puis ajoute le vocabulaire UI additif (3 verbes). Ne masque jamais le
    niveau technique : `technique` est conservé tel quel.

    `mode`    : READ_ONLY | PROPOSE | SANDBOX | SUPERVISED_APPLY.
    `mission` : texte de la mission (ce que l'utilisateur a demandé).

    Retour (dict), additif par rapport à HumanView :
        {
          "intention_ui": "Comprendre"|"Proposer"|"Agir"|None,
          "niveau_de_controle": "Observer|Préparer|Tester|Modifier",  # inchangé
          "ce_que_j_ai_compris": ...,
          "ce_que_je_vais_faire": ...,
          "ce_que_je_ne_vais_pas_faire": [...],
          "pourquoi": ...,
          "ce_qui_a_ete_verifie": [...],
          "action_requise": ...|None,
          "resultat": ...,
          "etat": ...,                 # état moteur brut
          "technique": {...}|None,     # report.to_dict() intégral
        }
    """
    # Fond : la brique B (inchangée). Elle porte toute la fidélité/pureté.
    view: HumanView = humanize(result, mode=mode, mission=mission)

    intention = ui_label(mode)

    # On repart de la vue humaine complète (dict), puis on AJOUTE le verbe UI.
    # On ne supprime ni ne réécrit aucun champ existant.
    out = view.to_dict()

    # Phrase "ce que je vais faire" en vocabulaire UI quand une intention
    # UI existe (SANDBOX reste sur la phrase de la brique B, étape interne).
    if intention is not None:
        out["ce_que_je_vais_faire"] = (
            f"Je vais {_UI_INTENT_SENTENCE.get(intention, _UI_INTENT_SENTENCE['Comprendre'])}."
        )

    out["intention_ui"] = intention
    return out
