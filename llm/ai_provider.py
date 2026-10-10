"""
MemoLibDev — LLM CONTROLLED v1 : AI Provider
=============================================

Abstraction de fournisseur d'intelligence. Le provider reçoit un
contexte DÉJÀ scanné (sans secret) et produit un `LLMPlan` strict —
une INTENTION, jamais un effet. Il n'appelle aucun module D5/D6,
n'écrit rien, ne touche pas git.

Invariants :
  - LLM ≠ autorité : le plan est non fiable, re-validé en aval.
  - Fail-closed : provider indisponible / réponse vide / non parsable
    -> None (traité comme BLOCK par le planner).
  - Confidentialité : HIGH/CRITICAL -> provider local uniquement.

v1 : un FakeProvider déterministe (prouve la FRONTIÈRE de contrôle sans
dépendre d'Ollama). L'OllamaProvider réel viendra après, en implémentant
la même interface, sans changer le planner ni l'Agent Loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class LLMPlan:
    """
    Sortie CONTRAINTE du LLM. Porte une intention, jamais un effet.
    - target_path : DOIT appartenir à context.authority_sources().
    - intent      : chaîne consommable par code_adapter.plan
                    (ex. "REPLACE:old:new").
    - rationale   : explication humaine (affichage), NON autorité.
    """
    target_path: str
    intent: str
    rationale: str


class ProviderLocality:
    LOCAL = "LOCAL"
    CLOUD = "CLOUD"


class AIProvider(Protocol):
    """Contrat commun. analyze_plan renvoie LLMPlan | None (None=BLOCK)."""

    @property
    def locality(self) -> str: ...

    @property
    def available(self) -> bool: ...

    def analyze_plan(self, context) -> Optional[LLMPlan]: ...


# ------------------------------------------------------------------
# FakeProvider déterministe (v1) — prouve la chaîne de contrôle
# ------------------------------------------------------------------

@dataclass
class FakeProvider:
    """
    Provider déterministe pour prouver la frontière de contrôle et le
    fail-closed, SANS dépendre d'un service externe.

    Comportement piloté par `scenario` :
      - "happy"        : propose un intent valide sur le fichier le plus
                         pertinent du contexte.
      - "out_of_scope" : propose un target_path hors authority_sources.
      - "control_plane": propose un fichier du control-plane.
      - "corrupt"      : propose un intent qui videra le fichier.
      - "empty"        : renvoie None (réponse vide).
      - "unparsable"   : renvoie un LLMPlan au format intent invalide.
    """
    scenario: str = "happy"
    locality_value: str = ProviderLocality.LOCAL
    available_value: bool = True
    # Pour les scénarios qui injectent un chemin arbitraire.
    injected_path: str = "../../etc/passwd"
    injected_intent: str = "REPLACE:version = '1.0':version = '2.0'"

    @property
    def locality(self) -> str:
        return self.locality_value

    @property
    def available(self) -> bool:
        return self.available_value

    def analyze_plan(self, context) -> Optional[LLMPlan]:
        if not self.available_value:
            return None   # provider indisponible -> BLOCK en aval

        if self.scenario == "empty":
            return None

        sources = list(context.authority_sources())
        primary = sources[0] if sources else ""

        if self.scenario == "happy":
            return LLMPlan(
                target_path=primary,
                intent=self.injected_intent,
                rationale="Mise à jour déterministe (fake provider).",
            )

        if self.scenario == "out_of_scope":
            return LLMPlan(
                target_path=self.injected_path,
                intent=self.injected_intent,
                rationale="Tentative hors scope.",
            )

        if self.scenario == "control_plane":
            return LLMPlan(
                target_path="d59_controlled_apply.py",
                intent="REPLACE:x:y",
                rationale="Tentative control-plane.",
            )

        if self.scenario == "corrupt":
            # Intent qui remplacera tout le contenu par du vide.
            return LLMPlan(
                target_path=primary,
                intent="WIPE",      # format non reconnu -> fallback APPEND ?
                rationale="Intent douteux.",
            )

        if self.scenario == "unparsable":
            return LLMPlan(
                target_path=primary,
                intent="",          # intent vide -> invalide
                rationale="Format cassé.",
            )

        return None



# ------------------------------------------------------------------
# SlowFakeProvider (R4) — bloque RÉELLEMENT, pour tester le timeout
# ------------------------------------------------------------------

@dataclass
class SlowFakeProvider:
    """
    Provider qui BLOQUE réellement `sleep_s` secondes avant de répondre.
    Picklable (dataclass de module) => utilisable avec l'isolation par
    processus (spawn) du wrapper timeout.

    Preuve d'absence d'exécution fantôme : si `sentinel_path` est fourni,
    le provider écrit ce fichier APRÈS son sleep. Si le process est tué
    par le timeout avant la fin du sleep, la sentinelle n'apparaît JAMAIS,
    ce qui prouve que le calcul a réellement été interrompu.

    NB : la sentinelle est un fichier de TEST (chemin fourni par le test,
    hors dépôt cible). Le provider n'a et n'exerce aucune autorité
    d'écriture sur la cible ; ceci sert uniquement à prouver l'arrêt.
    """
    sleep_s: float = 5.0
    sentinel_path: str = ""
    locality_value: str = ProviderLocality.LOCAL
    available_value: bool = True
    intent: str = "REPLACE:version = '1.0':version = '2.0'"

    @property
    def locality(self) -> str:
        return self.locality_value

    @property
    def available(self) -> bool:
        return self.available_value

    def analyze_plan(self, context) -> Optional[LLMPlan]:
        import time
        time.sleep(self.sleep_s)
        # Point atteint UNIQUEMENT si le sleep s'est terminé (pas de kill).
        if self.sentinel_path:
            try:
                with open(self.sentinel_path, "w", encoding="utf-8") as f:
                    f.write("ghost-executed\n")
            except OSError:
                pass
        sources = list(context.authority_sources())
        primary = sources[0] if sources else ""
        return LLMPlan(target_path=primary, intent=self.intent,
                       rationale="slow provider")
