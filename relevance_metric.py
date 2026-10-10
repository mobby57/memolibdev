"""
MemoLibDev — Étape 4 : Métrique de pertinence par catégorie
===========================================================

INSTRUMENT DE MESURE uniquement. Ne touche à AUCUN module moteur
(context_builder, planner, D5.x, agent_loop…). Déterministe, sans LLM.

Problème corrigé : la métrique précédente jugeait « pertinent » = cible
sous src/ (orientée code). Elle classait donc à tort « non pertinente »
une cible .md/doc pour une mission DOCUMENTAIRE, ou une règle .amazonq
pour une mission RÈGLES. On introduit un verdict à 3 niveaux tenant
compte du TYPE de mission :

    PERTINENT            — la cible correspond au rôle attendu par la catégorie
    PARTIELLEMENT        — rôle plausible/voisin (ex. proxy/middleware pour auth)
    NON_PERTINENT        — rôle incohérent avec la catégorie

On réutilise `_detect_role` du context_builder EN LECTURE (import), sans
le modifier : c'est la même notion de rôle, mais ici elle sert à MESURER,
pas à sélectionner.
"""

from __future__ import annotations

from dataclasses import dataclass

# Import en lecture seule du détecteur de rôle (non modifié).
from context.context_builder import (
    _detect_role, ROLE_SOURCE, ROLE_TEST, ROLE_CONFIG, ROLE_DOC,
    ROLE_RULES, ROLE_SCRIPT, ROLE_GENERATED, ROLE_OTHER,
)


PERTINENT = "PERTINENT"
PARTIEL = "PARTIELLEMENT"
NON_PERTINENT = "NON_PERTINENT"


# Rôles attendus par catégorie de mission.
#   pertinent : rôles pleinement attendus
#   partiel   : rôles plausibles/voisins (demi-crédit)
_CATEGORY_EXPECT: dict[str, dict[str, set[str]]] = {
    "bug_code":   {"pertinent": {ROLE_SOURCE},
                   "partiel": {ROLE_TEST, ROLE_CONFIG, ROLE_SCRIPT}},
    "auth_secu":  {"pertinent": {ROLE_SOURCE},
                   "partiel": {ROLE_TEST, ROLE_CONFIG, ROLE_OTHER}},  # proxy.ts/middleware.ts = OTHER (racine)
    "routes_api": {"pertinent": {ROLE_SOURCE},
                   "partiel": {ROLE_TEST, ROLE_OTHER}},               # middleware.ts
    "tests":      {"pertinent": {ROLE_TEST},
                   "partiel": {ROLE_SOURCE}},
    "config":     {"pertinent": {ROLE_CONFIG},
                   "partiel": {ROLE_SCRIPT, ROLE_OTHER}},             # (5A) scripts = voisins ; plus SOURCE
    "doc_regles": {"pertinent": {ROLE_DOC, ROLE_RULES},
                   "partiel": set()},
    "ambigu":     {"pertinent": {ROLE_SOURCE},
                   "partiel": {ROLE_TEST, ROLE_CONFIG, ROLE_SCRIPT, ROLE_OTHER}},
}

# Fichiers « charnière » d'auth/routes souvent à la racine (OTHER) mais
# réellement pertinents : proxy.ts, middleware.ts. On les reconnaît pour
# accorder PERTINENT (et pas seulement PARTIEL) sur les bonnes catégories.
_AUTH_ROUTE_HUBS = {"proxy.ts", "middleware.ts"}


@dataclass(frozen=True)
class RelevanceVerdict:
    category: str
    target: str | None
    role: str | None
    verdict: str          # PERTINENT | PARTIELLEMENT | NON_PERTINENT
    reason: str


def classify_relevance(category: str, target_path: str | None) -> RelevanceVerdict:
    """
    Verdict déterministe de pertinence d'une cible pour une catégorie de
    mission. `target_path` None (ex. BLOCK) -> NON_PERTINENT (pas de cible).
    """
    if not target_path:
        return RelevanceVerdict(category, None, None, NON_PERTINENT,
                                "aucune cible (BLOCK ou sans proposition)")

    role = _detect_role(target_path)
    basename = target_path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    expect = _CATEGORY_EXPECT.get(category, {"pertinent": {ROLE_SOURCE},
                                             "partiel": set()})

    # Cas charnière auth/routes : proxy.ts / middleware.ts = PERTINENT.
    if category in ("auth_secu", "routes_api") and basename in _AUTH_ROUTE_HUBS:
        return RelevanceVerdict(category, target_path, role, PERTINENT,
                                f"hub auth/routes reconnu: {basename}")

    if role in expect["pertinent"]:
        return RelevanceVerdict(category, target_path, role, PERTINENT,
                                f"rôle {role} attendu pour {category}")
    if role in expect["partiel"]:
        return RelevanceVerdict(category, target_path, role, PARTIEL,
                                f"rôle {role} plausible pour {category}")
    return RelevanceVerdict(category, target_path, role, NON_PERTINENT,
                            f"rôle {role} incohérent avec {category}")


def verdict_score(verdict: str) -> float:
    """Score numérique pour agrégation : PERTINENT=1, PARTIEL=0.5, NON=0."""
    return {PERTINENT: 1.0, PARTIEL: 0.5, NON_PERTINENT: 0.0}.get(verdict, 0.0)
