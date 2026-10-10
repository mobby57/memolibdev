"""
MemoLibDev — Brique B : humanize (traduction déterministe vers l'humain)
========================================================================

Couche de PRÉSENTATION, pure et déterministe. Elle traduit un résultat
technique de MemoLibDev (CliResult / AgentReport) en une vue orientée
utilisateur non technique (HumanView), sans jamais rien exécuter.

RÈGLE D'ARCHITECTURE (gravée) :
    « L'UI future est une façade. Elle ne possède aucune autorité
      d'exécution. Toute opération passe par le chemin validé
      CLI → run_from_mission → D5.8 → D5.9 → vérification. »

Ce module en est la première brique. Garanties PAR CONSTRUCTION :
    - fonction PURE : `humanize(result, *, mode, mission) -> HumanView` ;
    - n'importe NI git, NI run_controlled_apply (D5.9), NI authorize (D5.8) ;
    - ne lit/écrit AUCUN fichier ; aucun subprocess ; aucun réseau ;
    - aucun LLM : les phrases sont déterministes (un état -> un message) ;
    - ne peut pas fabriquer d'approbation : elle ne retourne que du texte ;
    - conserve INTÉGRALEMENT les informations techniques
      (`technique = report.to_dict()`), ne les masque jamais ;
    - ne transforme jamais une proposition en action réalisée, ni ne
      masque une erreur.

Imports volontairement limités à la stdlib (dataclasses, typing).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ------------------------------------------------------------------
# Mapping des 4 modes techniques -> niveaux de contrôle humains
# ------------------------------------------------------------------

_MODE_TO_CONTROL = {
    "READ_ONLY": "Observer",
    "PROPOSE": "Préparer",
    "SANDBOX": "Tester",
    "SUPERVISED_APPLY": "Modifier",
}

_CONTROL_WILL_DO = {
    "Observer": "examiner votre projet et expliquer ce que je trouve",
    "Préparer": "préparer une proposition de modification, sans l'appliquer",
    "Tester": "tester une solution dans un environnement isolé (une copie)",
    "Modifier": "appliquer une modification, uniquement après votre autorisation",
}

# Ce que l'agent ne fait JAMAIS (invariants), + nuance selon le mode.
_ALWAYS_WONT_DO = (
    "publier ou déployer quoi que ce soit",
    "enregistrer définitivement les changements sans votre accord",
)
_MODE_EXTRA_WONT_DO = {
    "Observer": ("modifier votre projet", "supprimer des fichiers"),
    "Préparer": ("modifier votre projet", "supprimer des fichiers"),
    "Tester": ("modifier votre projet réel (le travail se fait sur une copie)",),
    "Modifier": ("agir sans votre autorisation explicite",),
}


# ------------------------------------------------------------------
# Phrases déterministes par état (langage humain, factuel)
# ------------------------------------------------------------------

_STATE_RESULT = {
    "QUESTION": "J'ai besoin d'une précision avant de continuer.",
    "AWAIT_HUMAN": ("J'ai préparé une proposition. Rien n'a été modifié. "
                    "Votre autorisation est nécessaire pour continuer."),
    "BLOCKED": "Je ne peux pas continuer dans ces conditions.",
    "APPLIED": "La modification a été effectuée puis vérifiée.",
    "ROLLED_BACK": ("La modification n'a pas été conservée. "
                    "Le projet a été restauré dans son état initial."),
    "ROLLBACK_FAILED": ("La vérification a échoué et la restauration "
                        "automatique n'a pas abouti : une intervention "
                        "humaine est nécessaire."),
    "NO_PATCH_POSSIBLE": "Je n'ai pas trouvé de modification pertinente à proposer.",
    "OK": "Analyse terminée.",
    "ERROR": "Une erreur est survenue. Aucune modification n'a été effectuée.",
}

# Action requise de l'utilisateur, selon l'état.
_STATE_ACTION = {
    "QUESTION": "Merci de préciser votre demande pour que je puisse continuer.",
    "AWAIT_HUMAN": "Vous pouvez autoriser ou refuser cette proposition.",
    # Tous les autres états : aucune action d'autorisation.
}


@dataclass(frozen=True)
class HumanView:
    """
    Vue orientée utilisateur non technique. Immuable (frozen).
    Le niveau technique est conservé dans `technique` (jamais supprimé).
    """
    etat: str                              # état moteur d'origine (brut)
    niveau_de_controle: str                # Observer | Préparer | Tester | Modifier
    ce_que_j_ai_compris: str
    ce_que_je_vais_faire: str
    ce_que_je_ne_vais_pas_faire: tuple[str, ...]
    pourquoi: str
    ce_qui_a_ete_verifie: tuple[str, ...]
    action_requise: Optional[str]
    resultat: str
    technique: Optional[dict] = None       # = report.to_dict() si disponible

    def to_dict(self) -> dict:
        return {
            "etat": self.etat,
            "niveau_de_controle": self.niveau_de_controle,
            "ce_que_j_ai_compris": self.ce_que_j_ai_compris,
            "ce_que_je_vais_faire": self.ce_que_je_vais_faire,
            "ce_que_je_ne_vais_pas_faire": list(self.ce_que_je_ne_vais_pas_faire),
            "pourquoi": self.pourquoi,
            "ce_qui_a_ete_verifie": list(self.ce_qui_a_ete_verifie),
            "action_requise": self.action_requise,
            "resultat": self.resultat,
            "technique": self.technique,
        }


def _control_level(mode: str) -> str:
    return _MODE_TO_CONTROL.get(mode, "Observer")


def _wont_do(control: str) -> tuple[str, ...]:
    return tuple(_MODE_EXTRA_WONT_DO.get(control, ())) + _ALWAYS_WONT_DO


def _verified_steps(report) -> tuple[str, ...]:
    """
    Résume, en langage neutre, les étapes franchies avec succès. Lecture
    seule de report.steps ; aucune interprétation technique exposée ici
    (le détail reste dans `technique`).
    """
    if report is None:
        return ()
    labels = {
        "REQUEST": "demande reçue",
        "DECISION": "demande jugée recevable",
        "PLAN": "périmètre déterminé",
        "EVIDENCE": "éléments concernés identifiés",
        "PROVENANCE": "origine des éléments vérifiée",
        "CODER": "proposition préparée",
        "ANALYZE_PLAN": "analyse effectuée",
        "APPROVAL": "autorisation vérifiée",
        "D5.8_GATES": "contrôles de sécurité passés",
        "CONTEXT_RECHECK": "cohérence du projet revérifiée",
        "D5.9_APPLY": "application contrôlée effectuée",
        "VERIFY": "résultat vérifié",
    }
    out: list[str] = []
    for s in getattr(report, "steps", ()):  # StepRecord{step, loop_state, detail}
        if getattr(s, "loop_state", "") == "CONTINUE":
            label = labels.get(getattr(s, "step", ""), None)
            if label and label not in out:
                out.append(label)
    return tuple(out)


def _reason_human(report, fallback: str) -> str:
    """
    `pourquoi` : on expose la raison du moteur telle quelle (factuelle),
    sans la masquer. Si absente, on retombe sur le message fourni.
    """
    if report is not None and getattr(report, "reason", "").strip():
        return report.reason
    return fallback or ""


def humanize(result, *, mode: str, mission: str) -> HumanView:
    """
    Traduit un `CliResult` (ou tout objet exposant .status/.message et un
    éventuel .report avec .to_dict()) en `HumanView`. PURE et déterministe.

    `mode`    : READ_ONLY | PROPOSE | SANDBOX | SUPERVISED_APPLY.
    `mission` : texte de la mission (ce que l'utilisateur a demandé).
    """
    status = getattr(result, "status", "ERROR")
    message = getattr(result, "message", "") or ""
    report = getattr(result, "report", None)

    control = _control_level(mode)

    # `technique` : conservation INTÉGRALE si un report est disponible.
    technique = None
    if report is not None and hasattr(report, "to_dict"):
        technique = report.to_dict()

    compris = (mission.strip()
               if mission and mission.strip()
               else "votre demande")

    resultat = _STATE_RESULT.get(status, _STATE_RESULT["ERROR"])
    action = _STATE_ACTION.get(status)  # None pour les états sans action

    # Pour une QUESTION, la précision à demander figure dans result.question.
    if status == "QUESTION":
        question = getattr(result, "question", None)
        if question:
            action = question

    return HumanView(
        etat=status,
        niveau_de_controle=control,
        ce_que_j_ai_compris=f"Vous souhaitez que je {('traite votre demande : ' + compris) if compris != 'votre demande' else 'traite votre demande'}.",
        ce_que_je_vais_faire=f"Je vais {_CONTROL_WILL_DO.get(control, _CONTROL_WILL_DO['Observer'])}.",
        ce_que_je_ne_vais_pas_faire=_wont_do(control),
        pourquoi=_reason_human(report, message),
        ce_qui_a_ete_verifie=_verified_steps(report),
        action_requise=action,
        resultat=resultat,
        technique=technique,
    )
