"""
MemoLibDev — V0.3.1 : Confidence Engine (déterministe, explicable, anti-gaming)
================================================================================

Moteur de CONFIANCE pur et déterministe. Il mesure UNIQUEMENT la FORCE DES
PREUVES OBSERVABLES dans le périmètre inspecté. Il ne mesure JAMAIS :
    - une certitude absolue ;
    - la probabilité qu'un correctif soit parfait ;
    - une validité juridique ;
    - la qualité générale d'un LLM.

HIGH signifie « preuves fortement étayées dans le périmètre inspecté »,
jamais « certain ».

GARANTIES PAR CONSTRUCTION (gravées) :
    - PUR / DÉTERMINISTE : mêmes entrées -> même sortie, aucun aléa ;
    - AUCUN LLM : ce module n'importe ni n'appelle aucun provider/LLM ;
    - AUCUN I/O : ni disque, ni réseau, ni git, ni subprocess ;
    - INDÉPENDANT du provider : n'importe aucun module provider ;
    - AUCUNE AUTORITÉ : ne touche ni D5.8 ni D5.9 ; ne décide d'aucun apply ;
    - PAS DE DÉPENDANCE CIRCULAIRE : n'importe NI analysis_builder NI
      proposal NI agent_loop. Il opère sur des PRIMITIVES (listes de faits,
      drapeaux booléens, chaînes). Ce sont les autres modules qui importent
      CE module, jamais l'inverse.

PRINCIPE : « gates + score borné ». Les GATES sont PRIORITAIRES sur le
score (ils peuvent plafonner ou forcer un niveau). Le score additionne des
facteurs de QUALITÉ de preuve (jamais de VOLUME).

Deux dimensions SÉPARÉES :
    score_analysis(...)  -> confiance de l'ANALYSE (cohérence causale)
    score_proposal(...)  -> confiance de la PROPOSITION (diff/scope/SHA)

Compatibilité V0.1/V0.1.2 : `analysis_level_and_strong(...)` reproduit
EXACTEMENT la logique historique de `analysis_builder._confidence`
(1 locus fort -> HIGH ; >=2 -> MEDIUM ; faits pertinents -> MEDIUM ;
sinon LOW). `analysis_builder` délègue à cette fonction : résultats
identiques, aucun changement de comportement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ------------------------------------------------------------------
# Niveaux + bornes de score (déterministes, explicites).
# ------------------------------------------------------------------

HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

# Bornes de score (après gates). Calibrées pour que « 1 locus causal fort »
# atteigne le seuil HIGH et que la seule présence lexicale ne l'atteigne
# jamais. Voir docstring §7 (calibration) et les tests dédiés.
SCORE_MIN = 0
SCORE_MAX = 10
THRESHOLD_HIGH = 6      # score >= 6 ET aucun gate bloquant -> HIGH
THRESHOLD_MEDIUM = 3    # 3 <= score < 6 -> MEDIUM ; < 3 -> LOW


# Catégories comportementales (causales). DOIT rester un MIROIR de
# analysis_builder._BEHAVIORAL_CATEGORIES. Dupliqué ICI en lecture seule
# pour éviter toute dépendance circulaire (le moteur ne doit RIEN importer
# d'analysis_builder). Un test de cohérence vérifie l'égalité des deux.
BEHAVIORAL_CATEGORIES = ("REDIRECT", "ROUTE", "CONDITION", "ERROR_HANDLING",
                         "LOCALE")


@dataclass(frozen=True)
class ConfidenceResult:
    """
    Résultat de confiance structuré, immuable et sérialisable.

    level         : HIGH | MEDIUM | LOW
    score         : entier borné [SCORE_MIN, SCORE_MAX] (après gates)
    reasons       : explications lisibles (facteurs POSITIFS retenus)
    gates         : gates DÉCLENCHÉS (plafonnements/forçages appliqués)
    evidence_used : description des preuves réellement utilisées
    dimension     : "ANALYSIS" | "PROPOSAL"
    """
    level: str
    score: int
    reasons: tuple[str, ...]
    gates: tuple[str, ...]
    evidence_used: tuple[str, ...]
    dimension: str = "ANALYSIS"

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "score": self.score,
            "reasons": list(self.reasons),
            "gates": list(self.gates),
            "evidence_used": list(self.evidence_used),
            "dimension": self.dimension,
        }


def _clamp(score: int) -> int:
    return max(SCORE_MIN, min(SCORE_MAX, score))


# ------------------------------------------------------------------
# Déduplication des preuves (ANTI-GAMING).
# Une preuve = (fichier, ligne_debut, categorie). Répéter la même preuve
# (même ligne, même catégorie) ne compte qu'UNE fois. Ajouter des fichiers
# non causaux ou des mots-clés ne crée pas de nouvelle preuve causale.
# ------------------------------------------------------------------

def _dedupe_behavioral(facts) -> list:
    """
    Retourne les faits COMPORTEMENTAUX dédupliqués par (fichier, ligne,
    catégorie). N'invente rien ; ne garde que des faits réellement fournis.
    """
    seen: set = set()
    out: list = []
    for f in facts or ():
        cat = getattr(f, "categorie", None)
        if cat not in BEHAVIORAL_CATEGORIES:
            continue
        key = (getattr(f, "fichier", None),
               getattr(f, "ligne_debut", None),
               cat)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _strong_candidates(behavioral_facts) -> dict:
    """
    Fichiers concentrant >= 2 catégories comportementales DISTINCTES
    (cohérence d'un même lieu causal). DÉTERMINISTE. Les faits sont déjà
    dédupliqués en amont, donc répéter une preuve ne gonfle rien.
    """
    by_file: dict = {}
    for f in behavioral_facts:
        by_file.setdefault(getattr(f, "fichier", None), set()).add(
            getattr(f, "categorie", None))
    return {path: cats for path, cats in by_file.items()
            if path is not None and len(cats) >= 2}


# ==================================================================
# CŒUR ANALYSE — compat V0.1.2 (résultat identique à _confidence)
# ==================================================================

def analysis_level_and_strong(relevant_facts, relevant_cats,
                              files_count: int, any_preview: bool):
    """
    REPRODUIT EXACTEMENT la logique historique de
    analysis_builder._confidence et retourne le MÊME tuple
    (level, strong_candidates) afin que analysis_builder puisse déléguer
    SANS changer son comportement (non-régression V0.1/V0.1.2).

      - LOW    : aucun preview exploitable OU 0 fichier.
      - HIGH   : EXACTEMENT un fichier candidat fort (>=2 catégories
                 comportementales distinctes, dédupliquées).
      - MEDIUM : >=2 candidats forts (pluralité, on ne tranche pas) OU
                 au moins un fait pertinent observé sans lieu causal fort.
      - LOW    : aucun fait pertinent.
    """
    if not any_preview or files_count == 0:
        return LOW, {}
    behavioral = [f for f in _dedupe_behavioral(relevant_facts)
                  if getattr(f, "categorie", None) in relevant_cats]
    strong = _strong_candidates(behavioral)
    if len(strong) == 1:
        return HIGH, strong
    if len(strong) >= 2:
        return MEDIUM, strong
    if relevant_facts:
        return MEDIUM, {}
    return LOW, {}


# ==================================================================
# DIMENSION 1 — SCORE ANALYSE (structuré + gates + explications)
# ==================================================================

def score_analysis(
    *,
    relevant_facts,
    relevant_cats,
    files_count: int,
    any_preview: bool,
    is_stale: bool = False,
    budget_reduced: bool = False,
    scope_verifiable: bool = True,
    has_sha: bool = True,
    contradiction: bool = False,
) -> ConfidenceResult:
    """
    Confiance de l'ANALYSE. Le NIVEAU reste strictement cohérent avec la
    logique historique (via analysis_level_and_strong) ; le score et les
    explications l'enrichissent SANS jamais rendre HIGH un cas qui ne peut
    pas l'être.

    GATES (prioritaires) :
      G1 is_stale            -> LOW
      G2 0 preuve causale    -> jamais HIGH
      G3 >=2 loci forts      -> max MEDIUM
      G4 contradiction forte -> max MEDIUM
      G7 scope non vérifiable-> jamais HIGH

    Entrées : primitives uniquement (aucun objet LLM, aucun texte libre).
    """
    reasons: list[str] = []
    gates: list[str] = []
    evidence: list[str] = []

    base_level, strong = analysis_level_and_strong(
        relevant_facts, relevant_cats, files_count, any_preview)

    behavioral = [f for f in _dedupe_behavioral(relevant_facts)
                  if getattr(f, "categorie", None) in relevant_cats]
    n_relevant = len(relevant_facts or ())
    n_behavioral = len(behavioral)

    # ----- Score (facteurs de QUALITÉ, jamais de VOLUME) -----
    score = 0
    if len(strong) == 1:
        locus = next(iter(strong))
        cats = sorted(strong[locus])
        score += 3
        reasons.append(f"Un lieu causal unique et cohérent ('{locus}', "
                       f"catégories {', '.join(cats)}).")
        evidence.append(f"locus={locus} categories={','.join(cats)}")
        if len(cats) >= 3:
            score += 1
            reasons.append("Trois catégories comportementales distinctes ou "
                           "plus convergent dans ce lieu.")
    elif len(strong) >= 2:
        reasons.append(f"Plusieurs lieux causaux plausibles ({len(strong)}) : "
                       "aucune cause unique n'est retenue.")
        evidence.append(f"strong_loci={sorted(strong.keys())}")
    elif n_relevant:
        reasons.append("Des éléments liés au domaine ont été observés, mais "
                       "aucun lieu causal cohérent (présence isolée).")

    if n_behavioral >= 2 and len(strong) >= 1:
        score += 2
        reasons.append("Au moins deux indices comportementaux dédupliqués "
                       "étayent l'observation.")
    if has_sha and n_relevant:
        score += 1
        reasons.append("Les faits sont ancrés sur une version vérifiable (SHA).")
        evidence.append("sha=present")
    if scope_verifiable and len(strong) == 1:
        score += 1
        reasons.append("Le périmètre (scope) est cohérent et vérifiable.")

    # Pénalités (abaissent sans jamais inventer).
    if budget_reduced:
        score -= 2
        reasons.append("Pénalité : contenu partiellement borné par le budget "
                       "(preuve incomplète).")
    if not has_sha and n_relevant:
        score -= 2
        reasons.append("Pénalité : des faits ne sont pas ancrés sur un SHA.")

    score = _clamp(score)

    # ----- Niveau par seuil (candidat), AVANT gates -----
    if score >= THRESHOLD_HIGH:
        level = HIGH
    elif score >= THRESHOLD_MEDIUM:
        level = MEDIUM
    else:
        level = LOW

    # Le niveau ne peut JAMAIS dépasser le niveau historique (sécurité :
    # on n'invente pas une confiance plus forte que la logique validée).
    level = _min_level(level, base_level)

    # ----- GATES (prioritaires) -----
    if is_stale:
        gates.append("G1 contexte périmé (is_stale) -> LOW")
        level = LOW
    if n_behavioral == 0:
        gates.append("G2 aucune preuve causale comportementale -> jamais HIGH")
        level = _min_level(level, MEDIUM)
    if len(strong) >= 2:
        gates.append("G3 plusieurs loci causaux forts -> max MEDIUM")
        level = _min_level(level, MEDIUM)
    if contradiction:
        gates.append("G4 contradiction critique -> max MEDIUM")
        level = _min_level(level, MEDIUM)
    if not scope_verifiable:
        gates.append("G7 scope non vérifiable -> jamais HIGH")
        level = _min_level(level, MEDIUM)

    if not evidence:
        evidence.append("aucune preuve causale exploitable")

    return ConfidenceResult(
        level=level, score=score, reasons=tuple(reasons),
        gates=tuple(gates), evidence_used=tuple(evidence),
        dimension="ANALYSIS",
    )


# ==================================================================
# DIMENSION 2 — SCORE PROPOSITION (séparée)
# ==================================================================

def score_proposal(
    *,
    has_diff: bool,
    diff_valid: bool,
    diff_deterministic: bool = True,
    scope_verifiable: bool,
    has_fresh_sha: bool,
    is_stale: bool = False,
    causal_evidence: bool,
    contradiction: bool = False,
) -> ConfidenceResult:
    """
    Confiance de la PROPOSITION. Dimension SÉPARÉE de l'analyse.

    NE DOIT PAS utiliser (interdits §5) : taille du diff, nombre de
    fichiers, nombre de mots-clés, StructuredIntent.confiance, score de
    pertinence, texte libre du LLM. Aucune de ces entrées n'est acceptée
    par la signature : impossible par construction.

    GATES (prioritaires) :
      G1 is_stale            -> LOW
      G5 pas de diff         -> LOW
      G6 validation diff KO  -> LOW
      G7 scope non vérifiable-> jamais HIGH
      (G2) aucune preuve causale -> jamais HIGH
      (G4) contradiction      -> max MEDIUM
    """
    reasons: list[str] = []
    gates: list[str] = []
    evidence: list[str] = []

    score = 0
    if causal_evidence:
        score += 3
        reasons.append("Une preuve causale est disponible pour la cible.")
        evidence.append("causal_evidence=present")
    if has_diff:
        score += 1
        reasons.append("Un diff concret est présent.")
        evidence.append("diff=present")
    if has_diff and diff_valid:
        score += 1
        reasons.append("Le diff passe la validation structurelle "
                       "(non vide, modification réelle, pas de perte massive).")
        evidence.append("diff_valid=true")
    if has_diff and diff_deterministic:
        score += 1
        reasons.append("Le diff est produit de façon déterministe (git).")
        evidence.append("diff_deterministic=true")
    if has_fresh_sha:
        score += 1
        reasons.append("La cible est ancrée sur un SHA frais (contexte à jour).")
        evidence.append("fresh_sha=true")
    if scope_verifiable:
        score += 1
        reasons.append("Le périmètre (scope) est cohérent et vérifiable.")
        evidence.append("scope_verifiable=true")

    # Pénalités.
    if not has_fresh_sha:
        score -= 1
        reasons.append("Pénalité : SHA non frais / cible potentiellement dérivée.")

    score = _clamp(score)

    if score >= THRESHOLD_HIGH:
        level = HIGH
    elif score >= THRESHOLD_MEDIUM:
        level = MEDIUM
    else:
        level = LOW

    # ----- GATES (prioritaires) -----
    if is_stale:
        gates.append("G1 contexte périmé (is_stale) -> LOW")
        level = LOW
    if not has_diff:
        gates.append("G5 proposition sans diff -> LOW")
        level = LOW
    if has_diff and not diff_valid:
        gates.append("G6 validation du diff KO -> LOW")
        level = LOW
    if not scope_verifiable:
        gates.append("G7 scope non vérifiable -> jamais HIGH")
        level = _min_level(level, MEDIUM)
    if not has_fresh_sha:
        # Pas un gate LOW (le contexte n'est pas forcément périmé), mais une
        # proposition dont l'ancrage SHA n'est pas frais ne peut pas prétendre
        # à une confiance ÉLEVÉE : l'ancre a pu dériver. Plafond MEDIUM.
        gates.append("SHA non frais -> max MEDIUM")
        level = _min_level(level, MEDIUM)
    if not causal_evidence:
        gates.append("G2 aucune preuve causale -> jamais HIGH")
        level = _min_level(level, MEDIUM)
    if contradiction:
        gates.append("G4 contradiction critique -> max MEDIUM")
        level = _min_level(level, MEDIUM)

    if not evidence:
        evidence.append("aucune preuve de proposition exploitable")

    return ConfidenceResult(
        level=level, score=score, reasons=tuple(reasons),
        gates=tuple(gates), evidence_used=tuple(evidence),
        dimension="PROPOSAL",
    )


# ------------------------------------------------------------------
# Ordre des niveaux (LOW < MEDIUM < HIGH) pour les plafonnements.
# ------------------------------------------------------------------

_LEVEL_ORDER = {LOW: 0, MEDIUM: 1, HIGH: 2}


def _min_level(a: str, b: str) -> str:
    """Retourne le niveau le PLUS BAS des deux (plafonnement de sécurité)."""
    return a if _LEVEL_ORDER.get(a, 0) <= _LEVEL_ORDER.get(b, 0) else b


# ------------------------------------------------------------------
# Traductions UI (texte serveur). Le FRONT ne calcule jamais la confiance.
# ------------------------------------------------------------------

UI_LABEL = {
    HIGH: "Confiance élevée",
    MEDIUM: "Confiance moyenne",
    LOW: "Confiance faible",
}

UI_SENTENCE = {
    HIGH: ("Confiance élevée — les éléments observés sont cohérents et "
           "suffisamment étayés dans le périmètre analysé."),
    MEDIUM: ("Confiance moyenne — plusieurs éléments concordent, mais "
             "certaines informations restent à confirmer."),
    LOW: ("Confiance faible — les éléments disponibles ne permettent pas "
          "encore de soutenir suffisamment cette conclusion."),
}


def ui_label(level: str) -> str:
    return UI_LABEL.get(level, UI_LABEL[LOW])


def ui_sentence(level: str) -> str:
    return UI_SENTENCE.get(level, UI_SENTENCE[LOW])
