"""
MemoLibDev — LLM : OllamaProvider (réel, local, lecture seule)
==============================================================

Implémente le contrat `AIProvider` avec un vrai modèle local via l'API
Ollama (`/api/generate`, non-stream). Le provider :

  - reçoit un `MissionContext` DÉJÀ scanné (sans secret) et borné ;
  - construit un prompt STRICT demandant une seule ligne `REPLACE:old:new`
    et un fichier cible choisi PARMI `context.authority_sources()` ;
  - renvoie un `LLMPlan` si et seulement si la sortie est conforme,
    sinon `None` -> BLOCK par le planner (fail-closed).

Garanties :
  - LLM ≠ autorité : la sortie est re-validée par R1 (fragment présent),
    R2 (D6.1/D5.8), control-plane, scope. Le provider ne décide rien.
  - Picklable (dataclass à champs simples) => compatible avec l'isolation
    par processus du timeout R4 (spawn). L'appel HTTP se fait DANS le
    process enfant (urllib, stdlib — aucune dépendance externe).
  - Lecture seule : aucun écriture disque, aucun git, aucun apply.
  - available : ping /api/tags (le modèle demandé doit être présent).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import json
import urllib.request
import urllib.error

from llm.ai_provider import LLMPlan, ProviderLocality


DEFAULT_BASE_URL = "http://localhost:11434"


def _http_json(url: str, payload: dict, timeout: float) -> Optional[dict]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception:                      # réseau/HTTP/JSON -> fail-closed
        return None


def _http_get_json(url: str, timeout: float) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


@dataclass
class OllamaProvider:
    """
    Provider Ollama local. Picklable (champs simples uniquement).
    L'appel réseau est effectué dans analyze_plan (donc dans le process
    enfant quand on l'exécute via le wrapper timeout R4).
    """
    model: str = "qwen2.5-coder:1.5b-base"
    base_url: str = DEFAULT_BASE_URL
    http_timeout: float = 60.0
    num_predict: int = 64
    temperature: float = 0.0
    locality_value: str = ProviderLocality.LOCAL

    @property
    def locality(self) -> str:
        return self.locality_value

    @property
    def available(self) -> bool:
        """UP si l'API répond ET le modèle demandé est présent."""
        tags = _http_get_json(f"{self.base_url}/api/tags", timeout=5.0)
        if not tags:
            return False
        names = {m.get("name") for m in tags.get("models", [])}
        return self.model in names

    # ----------------------------------------------------------
    # Prompt strict
    # ----------------------------------------------------------

    def _build_prompt(self, context) -> str:
        sources = list(context.authority_sources())
        files_block = "\n".join(f"- {p}" for p in sources) or "- (aucun)"
        # On fournit un extrait borné du fichier le mieux scoré pour que
        # le modèle puisse choisir un `old` RÉELLEMENT présent (sinon R1
        # bloquera en aval). Lecture seule : extrait déjà dans le contexte.
        primary_preview = ""
        if context.relevant_files:
            rf = context.relevant_files[0]
            primary_preview = rf.preview[:800]
        return (
            "Tu es un assistant qui propose UNE seule transformation de code.\n"
            "Réponds EXCLUSIVEMENT par une seule ligne au format strict :\n"
            "REPLACE:<texte_existant>:<nouveau_texte>\n"
            "Le <texte_existant> DOIT exister tel quel dans le fichier.\n"
            "N'ajoute aucune explication, aucun autre texte.\n\n"
            f"Mission: {context.mission_text}\n\n"
            f"Fichiers autorisés (choisis-en un) :\n{files_block}\n\n"
            f"Extrait du fichier principal :\n{primary_preview}\n\n"
            "Réponse (une seule ligne REPLACE:...:...):"
        )

    # ----------------------------------------------------------
    # Parsing fail-closed
    # ----------------------------------------------------------

    @staticmethod
    def _extract_plan(text: str, context) -> Optional[LLMPlan]:
        """
        Extrait la PREMIÈRE ligne REPLACE:old:new valide de la sortie
        modèle. target_path = fichier principal du contexte (le modèle ne
        choisit pas librement un chemin ; on l'ancre sur la cible
        pertinente, et R1/R2 revalident). Fail-closed : rien de conforme
        -> None.
        """
        if not text:
            return None
        sources = list(context.authority_sources())
        if not sources:
            return None
        target = sources[0]
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("REPLACE:"):
                parts = line.split(":", 2)
                if len(parts) == 3 and parts[1]:
                    return LLMPlan(
                        target_path=target,
                        intent=line,
                        rationale="OllamaProvider (sortie modèle, non-autorité)",
                    )
        return None

    def analyze_plan(self, context) -> Optional[LLMPlan]:
        prompt = self._build_prompt(context)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": self.num_predict,
                        "temperature": self.temperature},
        }
        data = _http_json(f"{self.base_url}/api/generate", payload,
                          timeout=self.http_timeout)
        if not data:
            return None                    # erreur réseau/HTTP -> BLOCK
        response = data.get("response")
        if not isinstance(response, str):
            return None
        return self._extract_plan(response, context)
