"""
MemoLibDev — V0.2 : Contrat d'états HUMAINS (traduction, sans autorité)
=======================================================================

Couche de TRADUCTION, pure et déterministe. Elle convertit un état RÉEL
produit par le serveur/Core (MissionState d'api_facade, ou status moteur
d'un AgentReport/CliResult) en un ÉTAT HUMAIN compréhensible, et fournit
une PROGRESSION dérivée STRICTEMENT de cet état réel.

RÈGLES GRAVÉES (non négociables) :
    1. Le front ne décide de RIEN : il TRADUIT un état fourni par le
       serveur. Aucune invention d'état, aucune animation fictive.
    2. Un état terminal négatif (REFUSED / BLOCKED / FAILED / ROLLED_BACK)
       n'est JAMAIS présenté comme un succès.
    3. Cette couche ne possède AUCUNE autorité : elle n'exécute rien,
       n'autorise rien, ne lit NI git NI secret. Pure fonction texte.
    4. Supprimer cette couche ne retire aucune protection du Core.

Aucun import hors stdlib. Aucun I/O, aucun réseau, aucun LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ------------------------------------------------------------------
# 1. États humains (clés stables) + phrase affichée
# ------------------------------------------------------------------

HUMAN_STATES: dict[str, str] = {
    "UNDERSTANDING":      "Je comprends votre demande",
    "INSPECTING":         "J'examine votre projet",
    "VERIFYING":          "Je vérifie les éléments importants",
    "ANALYZING":          "J'analyse ce que j'ai trouvé",
    "ANALYZED":           "Analyse terminée",
    "PROPOSING":          "Je prépare une proposition",
    "AWAITING_APPROVAL":  "Votre décision est nécessaire",
    "EXECUTING":          "J'effectue l'action",
    "VERIFYING_RESULT":   "Je vérifie le résultat",
    "COMPLETED":          "Terminé",
    "REFUSED":            "L'action a été refusée",
    "BLOCKED":            "Je me suis arrêté pour votre sécurité",
    "ROLLED_BACK":        "La modification a été annulée et l'état a été vérifié",
    "FAILED":             "L'action n'a pas pu être terminée",
}

# États humains TERMINAUX (plus de progression attendue).
TERMINAL_HUMAN_STATES = frozenset({
    "ANALYZED", "COMPLETED", "REFUSED", "BLOCKED", "ROLLED_BACK", "FAILED",
})

# États terminaux NÉGATIFS : jamais présentés comme un succès.
NEGATIVE_TERMINAL_STATES = frozenset({
    "REFUSED", "BLOCKED", "ROLLED_BACK", "FAILED",
})

# États terminaux de SUCCÈS (les seuls autorisés à afficher une réussite).
SUCCESS_TERMINAL_STATES = frozenset({"ANALYZED", "COMPLETED"})


# ------------------------------------------------------------------
# 2. Mapping ÉTAT RÉEL (serveur/moteur) -> ÉTAT HUMAIN
# ------------------------------------------------------------------
#
# Les clés sont des états RÉELS :
#   - MissionState d'api_facade (ANALYZING, PROPOSAL_READY, ...)
#   - status moteur d'un AgentReport/CliResult (ANALYZED, AWAIT_HUMAN, ...)
# On ne mappe QUE des états réellement produits ailleurs. Tout état inconnu
# est traité de façon fail-safe (voir to_human_state).

_SERVER_STATE_TO_HUMAN: dict[str, str] = {
    # --- MissionState (api_facade) ---
    "ANALYZING":              "ANALYZING",
    "PROPOSAL_READY":         "ANALYZED",       # lecture seule : analyse prête
    "AWAITING_AUTHORIZATION": "AWAITING_APPROVAL",
    "AUTHORIZED":             "EXECUTING",
    "EXECUTING":              "EXECUTING",
    "VERIFYING":              "VERIFYING_RESULT",
    "COMPLETED":              "COMPLETED",
    "REFUSED":                "REFUSED",
    "BLOCKED":                "BLOCKED",
    "FAILED":                 "FAILED",
    "ROLLED_BACK":            "ROLLED_BACK",
    "QUESTION":               "UNDERSTANDING",  # besoin d'une précision

    # --- status moteur (AgentReport / CliResult) ---
    "ANALYZED":               "ANALYZED",
    "AWAIT_HUMAN":            "AWAITING_APPROVAL",
    "APPLIED":                "COMPLETED",
    "NO_PATCH_POSSIBLE":      "BLOCKED",
    "OK":                     "ANALYZED",
    "ERROR":                  "FAILED",
}


# ------------------------------------------------------------------
# 3. Progression HUMAINE (étapes), dérivée de l'état réel
# ------------------------------------------------------------------
#
# L'ordre des étapes affichées. Chaque étape porte un libellé humain.
# L'avancement est calculé À PARTIR de l'état réel : jamais animé.

PROGRESS_STEPS: tuple[tuple[str, str], ...] = (
    ("COMPRENDRE", "Comprendre"),
    ("EXAMINER",   "Examiner"),
    ("ANALYSER",   "Analyser"),
    ("PROPOSER",   "Proposer"),
    ("DECIDER",    "Décider"),
    ("EXECUTER",   "Exécuter"),
    ("VERIFIER",   "Vérifier le résultat"),
)

# Pour chaque état HUMAIN, l'étape de progression ATTEINTE (index dans
# PROGRESS_STEPS). L'étape courante est marquée "en cours" (●), les
# précédentes "faites" (✓), les suivantes "à venir" (○). Déterministe.
# Les états terminaux négatifs n'« avancent » pas la barre au-delà du
# point où le moteur s'est arrêté : on ne prétend jamais avoir exécuté.
_HUMAN_STATE_TO_STEP_INDEX: dict[str, int] = {
    "UNDERSTANDING":     0,   # Comprendre (en cours)
    "INSPECTING":        1,   # Examiner
    "VERIFYING":         1,   # Examiner (vérif des éléments)
    "ANALYZING":         2,   # Analyser (en cours)
    "ANALYZED":          2,   # Analyser (terminé) — lecture seule s'arrête ici
    "PROPOSING":         3,   # Proposer
    "AWAITING_APPROVAL": 4,   # Décider (en cours)
    "EXECUTING":         5,   # Exécuter (en cours)
    "VERIFYING_RESULT":  6,   # Vérifier le résultat (en cours)
    "COMPLETED":         6,   # Vérifier (terminé)
    # Terminaux négatifs : la barre reste au stade atteint, sans succès.
    "REFUSED":           4,   # arrêt à la décision
    "BLOCKED":           2,   # arrêt (sécurité) au plus tard à l'analyse
    "ROLLED_BACK":       6,   # tentative d'exécution annulée + vérifiée
    "FAILED":            5,   # échec pendant/avant exécution
}


@dataclass(frozen=True)
class ProgressStep:
    key: str
    label: str
    status: str   # "done" | "current" | "todo"

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "status": self.status}


@dataclass(frozen=True)
class HumanStateView:
    """Vue d'état humaine, dérivée d'un état réel. Immuable, pure."""
    human_state: str                    # clé ∈ HUMAN_STATES
    message: str                        # phrase affichée
    is_terminal: bool
    is_success: bool                    # True UNIQUEMENT pour succès réels
    is_negative: bool                   # True pour REFUSED/BLOCKED/FAILED/ROLLED_BACK
    server_state: str                   # état réel source (traçabilité)
    progression: tuple[ProgressStep, ...]

    def to_dict(self) -> dict:
        return {
            "human_state": self.human_state,
            "message": self.message,
            "is_terminal": self.is_terminal,
            "is_success": self.is_success,
            "is_negative": self.is_negative,
            "server_state": self.server_state,
            "progression": [p.to_dict() for p in self.progression],
        }


def to_human_state(server_state: Optional[str]) -> str:
    """
    Traduit un état RÉEL serveur/moteur en clé d'état humain.

    Fail-safe (jamais inventer un succès) : un état inconnu ou absent est
    rendu « FAILED » (l'action n'a pas pu être terminée) plutôt qu'un faux
    « terminé ». On ne fabrique JAMAIS un état positif par défaut.
    """
    if not server_state or not isinstance(server_state, str):
        return "FAILED"
    key = _SERVER_STATE_TO_HUMAN.get(server_state.strip())
    if key is None:
        return "FAILED"
    return key


def _progression_for(human_state: str) -> tuple[ProgressStep, ...]:
    """
    Construit la progression déterministe pour un état humain. L'étape
    atteinte vient de _HUMAN_STATE_TO_STEP_INDEX ; aucune animation.
    Pour un état terminal NÉGATIF, l'étape courante n'est PAS marquée
    "done" (on ne prétend pas l'avoir réussie) mais "current" (point
    d'arrêt), et les suivantes restent "todo".
    """
    idx = _HUMAN_STATE_TO_STEP_INDEX.get(human_state, 0)
    terminal = human_state in TERMINAL_HUMAN_STATES
    negative = human_state in NEGATIVE_TERMINAL_STATES
    success_terminal = human_state in SUCCESS_TERMINAL_STATES

    steps: list[ProgressStep] = []
    for i, (key, label) in enumerate(PROGRESS_STEPS):
        if i < idx:
            status = "done"
        elif i == idx:
            # Terminal de succès -> l'étape atteinte est "done".
            # Terminal négatif ou étape en cours -> "current" (jamais "done").
            if success_terminal:
                status = "done"
            else:
                status = "current"
        else:
            status = "todo"
        steps.append(ProgressStep(key=key, label=label, status=status))
    return tuple(steps)


def build_human_state_view(server_state: Optional[str]) -> HumanStateView:
    """
    Construit la vue d'état humaine complète à partir d'un état RÉEL.
    Pure, déterministe. Ne présente JAMAIS un terminal négatif comme un
    succès (invariant vérifié par les tests UX).
    """
    human = to_human_state(server_state)
    message = HUMAN_STATES.get(human, HUMAN_STATES["FAILED"])
    is_terminal = human in TERMINAL_HUMAN_STATES
    is_negative = human in NEGATIVE_TERMINAL_STATES
    is_success = human in SUCCESS_TERMINAL_STATES
    # Garde-fou dur : un état négatif ne peut jamais être un succès.
    if is_negative:
        is_success = False
    return HumanStateView(
        human_state=human,
        message=message,
        is_terminal=is_terminal,
        is_success=is_success,
        is_negative=is_negative,
        server_state=(server_state or "").strip(),
        progression=_progression_for(human),
    )
