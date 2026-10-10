"""
MemoLibDev — V0.1.1 : Analysis Builder (analyse explicative déterministe)
=========================================================================

Produit une ANALYSE EXPLICATIVE à partir du seul contenu RÉELLEMENT
inspecté (les `preview` des `RelevantFile` d'un `MissionContext`) et de
l'intention structurée (5.2). 100 % DÉTERMINISTE, SANS LLM, SANS écriture.

Contrat (exigé) — AnalysisResult sérialisable :
    demande_comprise      : str
    faits_verifies        : list[VerifiedFact]
    elements_examines     : list[str]       (chemins réellement inspectés)
    analyse               : str
    cause_probable        : str | None      (None si non étayée)
    correction_minimale   : str | None      (DESCRIPTIVE, jamais un diff)
    confiance             : "HIGH"|"MEDIUM"|"LOW"
    incertitudes          : list[str]
    aucune_modification   : True            (invariant)

Chaque VerifiedFact est OBLIGATOIREMENT rattaché à une source réelle :
    fichier   : chemin ∈ ctx.relevant_files (jamais inventé)
    lignes    : (début, fin) relatifs au preview (portée connue)
    extrait   : texte RÉEL prélevé dans le preview (représentation déterministe)
    sha       : text_sha256 de la source (version capturée)

INTERDITS GRAVÉS (par construction) :
    - inventer un fait ;
    - produire un fait dont le fichier n'est pas dans le contexte ;
    - produire un fait sans source ;
    - prétendre avoir inspecté une portion absente du preview ;
    - produire un diff / une modification ;
    - appeler CORRIGER / D5.8 / D5.9 ;
    - écrire quoi que ce soit (aucun I/O, aucun réseau, aucun git).

Ce module n'importe que la stdlib. Il NE connaît NI git, NI apply, NI LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import re


# ------------------------------------------------------------------
# Structures sérialisables
# ------------------------------------------------------------------

@dataclass(frozen=True)
class VerifiedFact:
    """
    Un fait OBSERVÉ dans un preview réel, rattaché à sa source. Immuable.
    `extrait` est une copie LITTÉRALE d'une (ou plusieurs) ligne(s) du
    preview : jamais une paraphrase, jamais une invention.
    """
    fichier: str
    ligne_debut: int            # 1-based, relatif au preview inspecté
    ligne_fin: int              # 1-based, inclusif
    extrait: str                # texte réel prélevé dans le preview
    sha: str                    # text_sha256 de la source (version capturée)
    categorie: str              # ex: IMPORT | REDIRECT | ROUTE | EXPORT | ...

    def to_dict(self) -> dict:
        return {
            "fichier": self.fichier,
            "lignes": [self.ligne_debut, self.ligne_fin],
            "extrait": self.extrait,
            "sha": self.sha,
            "categorie": self.categorie,
        }


@dataclass(frozen=True)
class AnalysisResult:
    """Résultat d'analyse explicative, sérialisable. Immuable."""
    demande_comprise: str
    faits_verifies: tuple[VerifiedFact, ...]
    elements_examines: tuple[str, ...]
    analyse: str
    cause_probable: Optional[str]
    correction_minimale: Optional[str]
    confiance: str                      # HIGH | MEDIUM | LOW
    incertitudes: tuple[str, ...]
    aucune_modification: bool = True    # invariant : toujours True

    def to_dict(self) -> dict:
        return {
            "demande_comprise": self.demande_comprise,
            "faits_verifies": [f.to_dict() for f in self.faits_verifies],
            "elements_examines": list(self.elements_examines),
            "analyse": self.analyse,
            "cause_probable": self.cause_probable,
            "correction_minimale": self.correction_minimale,
            "confiance": self.confiance,
            "incertitudes": list(self.incertitudes),
            "aucune_modification": self.aucune_modification,
        }


# ------------------------------------------------------------------
# Détecteurs déterministes de faits (lecture seule du preview)
# ------------------------------------------------------------------
#
# Chaque détecteur est une (catégorie, regex). Il ne RETIENT que des
# lignes LITTÉRALEMENT présentes dans le preview. Aucune interprétation
# n'est encodée dans le fait : seul le texte réel est conservé. L'analyse
# qui en découle reste prudente et sourcée.

_DETECTORS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("REDIRECT", re.compile(
        r"\b(redirect|NextResponse\.redirect|router\.(push|replace)|"
        r"window\.location|res\.redirect|redirectTo)\b", re.IGNORECASE)),
    ("ROUTE", re.compile(
        r"\b(export\s+(async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)"
        r"|app\.(get|post|put|patch|delete)\s*\(|createRoute|"
        r"def\s+(get|post|put|patch|delete))\b")),
    ("LOCALE", re.compile(
        r"(locale|i18n|\[locale\]|getLocale|useLocale|defaultLocale|"
        r"localePrefix|/fr/|/en/)", re.IGNORECASE)),
    ("AUTH", re.compile(
        r"\b(auth|signIn|signOut|getToken|session|clerk|middleware|"
        r"useAuth|currentUser|getAuth|requireAuth)\b", re.IGNORECASE)),
    ("IMPORT", re.compile(r"^\s*(import\s|from\s+['\"]|const\s+\w+\s*=\s*require\()")),
    ("EXPORT", re.compile(r"^\s*export\s+(default\s+|const\s+|function\s+|class\s+)")),
    ("CONDITION", re.compile(r"\b(if|else if|switch|ternary|\?\s*.+\s*:)\b")),
    ("ERROR_HANDLING", re.compile(
        r"\b(try|catch|throw|error|Error|reject|fail)\b")),
    ("CONFIG_KEY", re.compile(
        r"^\s*[\"']?[A-Za-z0-9_.-]+[\"']?\s*[:=]\s*", )),
    ("DEFINITION", re.compile(
        r"^\s*(async\s+)?def\s+\w+\s*\(|^\s*class\s+\w+"
        r"|^\s*(export\s+)?(async\s+)?function\s+\w+\s*\(")),
    ("DOC_HEADING", re.compile(r"^\s*#{1,6}\s+\S")),
    ("DOC_LIST", re.compile(r"^\s*[-*+]\s+\S")),
    ("DOC_TABLE", re.compile(r"^\s*\|.+\|")),
)

# Catégories jugées "porteuses de cause" pour un domaine donné : ce sont
# les faits qui PEUVENT étayer une cause probable (jamais à eux seuls une
# certitude). Mapping déterministe domaine -> catégories pertinentes.
_DOMAIN_RELEVANT_CATEGORIES = {
    "AUTH": ("AUTH", "REDIRECT", "ROUTE", "LOCALE", "CONDITION", "ERROR_HANDLING"),
    "ROUTES": ("ROUTE", "REDIRECT", "LOCALE", "IMPORT", "CONDITION"),
    "UI": ("EXPORT", "IMPORT", "CONDITION", "REDIRECT"),
    "DATA": ("IMPORT", "CONFIG_KEY", "ERROR_HANDLING"),
    "CONFIG": ("CONFIG_KEY", "IMPORT"),
    "TESTS": ("IMPORT", "EXPORT", "ERROR_HANDLING"),
    "DOC": ("CONFIG_KEY", "DOC_HEADING", "DOC_LIST", "DOC_TABLE", "DEFINITION"),
    "SECURITE": ("AUTH", "ERROR_HANDLING", "CONFIG_KEY", "CONDITION"),
}

# Longueur maximale d'un extrait conservé (bornage déterministe, lisible).
_MAX_EXCERPT_CHARS = 240
# Nombre maximal de faits retenus par fichier (évite le bruit, déterministe).
_MAX_FACTS_PER_FILE = 6
# Nombre maximal de faits au total (bornage global déterministe).
_MAX_FACTS_TOTAL = 24


def _preview_lines(preview: str) -> list[str]:
    """Découpe le preview en lignes (représentation déterministe)."""
    if not preview:
        return []
    # splitlines() est déterministe et gère \n / \r\n uniformément.
    return preview.splitlines()


def _clip(text: str) -> str:
    """Borne un extrait sans jamais inventer de contenu (troncature marquée)."""
    t = text.strip()
    if len(t) <= _MAX_EXCERPT_CHARS:
        return t
    return t[:_MAX_EXCERPT_CHARS].rstrip() + " …"


def _extract_facts_from_file(path: str, preview: str, sha: str) -> list[VerifiedFact]:
    """
    Extrait des faits DÉTERMINISTES d'un preview réel. Chaque fait est une
    ligne littérale du preview, rattachée à (path, ligne, sha). N'invente
    rien : si le détecteur ne matche aucune ligne, aucun fait n'est produit.
    """
    facts: list[VerifiedFact] = []
    lines = _preview_lines(preview)
    seen: set[tuple[int, str]] = set()

    for idx, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        for categorie, pattern in _DETECTORS:
            if pattern.search(line):
                key = (idx, categorie)
                if key in seen:
                    continue
                seen.add(key)
                facts.append(VerifiedFact(
                    fichier=path,
                    ligne_debut=idx,
                    ligne_fin=idx,
                    extrait=_clip(line),
                    sha=sha,
                    categorie=categorie,
                ))
                break  # une catégorie par ligne (déterministe, 1er match)
        if len(facts) >= _MAX_FACTS_PER_FILE:
            break
    return facts


# Catégories "comportementales" : elles décrivent une LOGIQUE observable
# (flux, décision, redirection) et peuvent — à plusieurs et cohérentes —
# étayer une cause. Les autres catégories (IMPORT/EXPORT/AUTH-mot-clé/
# CONFIG_KEY) ne sont QUE des présences lexicales : elles restent des FAITS
# mais ne constituent JAMAIS une cause à elles seules.
_BEHAVIORAL_CATEGORIES = ("REDIRECT", "ROUTE", "CONDITION", "ERROR_HANDLING",
                          "LOCALE", "DEFINITION", "DOC_HEADING")


def _behavioral_relevant(facts: list, relevant_cats: tuple) -> list:
    """Faits à la fois pertinents au domaine ET comportementaux (causaux)."""
    return [f for f in facts
            if f.categorie in relevant_cats
            and f.categorie in _BEHAVIORAL_CATEGORIES]


def _strong_candidate_files(relevant_facts: list, relevant_cats: tuple) -> dict:
    """
    Regroupe les faits causaux par fichier et retourne, pour chaque fichier,
    l'ENSEMBLE de catégories comportementales DISTINCTES qu'il porte. Un
    fichier est un « candidat fort » s'il concentre >= 2 catégories
    comportementales distinctes (cohérence d'un même lieu). DÉTERMINISTE.
    """
    by_file: dict[str, set] = {}
    for f in _behavioral_relevant(relevant_facts, relevant_cats):
        by_file.setdefault(f.fichier, set()).add(f.categorie)
    return {path: cats for path, cats in by_file.items() if len(cats) >= 2}


def _confidence(relevant_facts: list, relevant_cats: tuple,
                files_count: int, any_preview: bool) -> tuple[str, dict]:
    """
    Confiance fondée sur la COHÉRENCE CAUSALE réellement observée, jamais
    sur un simple comptage de mots-clés.

    V0.3.1 : la LOGIQUE est désormais portée par le moteur partagé
    `confidence_engine.analysis_level_and_strong`, afin que ANALYSE et
    PROPOSITION reposent sur une seule source déterministe. Le CONTRAT de
    retour (level, strong_candidates) et les RÉSULTATS sont STRICTEMENT
    identiques à la logique historique V0.1.2 (non-régression prouvée par
    test_analysis_builder.py et test_analysis_adversarial.py). Aucun import
    circulaire : confidence_engine n'importe RIEN d'analysis_builder.

      - HIGH   : EXACTEMENT un fichier candidat fort (>= 2 catégories
                 comportementales distinctes, cohérentes et observées) ET
                 aucun autre fichier également fort -> lieu causal unique ;
      - MEDIUM : soit plusieurs candidats forts (pluralité -> on ne tranche
                 pas), soit au moins un fait pertinent observé mais preuve
                 causale incomplète ;
      - LOW    : aucun preview exploitable OU aucun fait pertinent.

    Aucun raisonnement probabiliste non sourcé. La simple présence de
    AUTH/LOGIN/REDIRECT/… (catégorie non comportementale, ou isolée) ne
    suffit JAMAIS à HIGH.
    """
    from confidence_engine import analysis_level_and_strong
    return analysis_level_and_strong(
        relevant_facts, relevant_cats, files_count, any_preview)


def build_analysis(ctx, structured_intent) -> AnalysisResult:
    """
    Construit un AnalysisResult déterministe à partir du MissionContext et
    de l'intention structurée (5.2). Lecture seule, sans LLM, sans écriture.

    `ctx`              : MissionContext (relevant_files versionnés + previews).
    `structured_intent`: StructuredIntent (objectif/domaine/risque/confiance).

    Garanties :
      - tout fait provient d'un fichier ∈ ctx.relevant_files ;
      - tout fait porte (fichier, lignes, extrait réel, sha) ;
      - cause_probable = None si non directement étayée (+ incertitude) ;
      - confiance = reflet des preuves observables, jamais une supposition ;
      - aucune_modification = True ; aucun diff ; aucun REPLACE.
    """
    si = structured_intent
    relevant_files = tuple(getattr(ctx, "relevant_files", ()) or ())
    domaine = getattr(si, "domaine", "UNKNOWN")

    demande = (ctx.mission_text.strip()
               if getattr(ctx, "mission_text", "").strip()
               else "votre demande")

    # 1. Extraction des faits — EXCLUSIVEMENT depuis les previews réels.
    all_facts: list[VerifiedFact] = []
    elements: list[str] = []
    any_preview = False
    files_without_preview: list[str] = []

    for rf in relevant_files:
        elements.append(rf.path)
        preview = getattr(rf, "preview", "") or ""
        sha = getattr(getattr(rf, "version", None), "text_sha256", "") or ""
        if preview.strip():
            any_preview = True
            all_facts.extend(_extract_facts_from_file(rf.path, preview, sha))
        else:
            files_without_preview.append(rf.path)
        if len(all_facts) >= _MAX_FACTS_TOTAL:
            all_facts = all_facts[:_MAX_FACTS_TOTAL]
            break

    # 2. Faits PERTINENTS au domaine (sous-ensemble, jamais une invention).
    relevant_cats = _DOMAIN_RELEVANT_CATEGORIES.get(domaine, ())
    relevant_facts = [f for f in all_facts if f.categorie in relevant_cats]

    # 3. Confiance = cohérence CAUSALE observée (jamais un comptage de
    #    mots-clés). strong_candidates = fichiers concentrant >= 2
    #    catégories comportementales distinctes.
    confiance, strong_candidates = _confidence(
        relevant_facts, relevant_cats, len(relevant_files), any_preview)

    # 4. Incertitudes explicites (déterministes, honnêtes).
    incertitudes: list[str] = []
    if not relevant_files:
        incertitudes.append(
            "Aucun fichier pertinent n'a été identifié : analyse impossible.")
    if not any_preview and relevant_files:
        incertitudes.append(
            "Aucun contenu de fichier n'était disponible dans le contexte : "
            "l'analyse ne peut s'appuyer sur aucune preuve de contenu.")
    if files_without_preview:
        incertitudes.append(
            "Contenu indisponible pour : "
            + ", ".join(files_without_preview[:5])
            + (" …" if len(files_without_preview) > 5 else "")
            + ".")
    if getattr(ctx, "budget_reduced", False):
        incertitudes.append(
            "Le contenu inspecté est borné par un budget : des portions de "
            "fichiers n'ont pas été examinées.")
    if domaine == "UNKNOWN":
        incertitudes.append(
            "Le domaine de la demande n'a pas pu être déterminé de façon "
            "fiable : la pertinence des faits ne peut être garantie.")
    if all_facts and not relevant_facts:
        incertitudes.append(
            "Des éléments ont été observés, mais aucun ne se rattache "
            "directement au domaine de la demande.")
    # Pluralité de lieux causaux : on refuse de trancher arbitrairement.
    if len(strong_candidates) >= 2:
        noms = ", ".join(sorted(strong_candidates.keys()))
        incertitudes.append(
            "Plusieurs fichiers présentent des éléments comparables pouvant "
            f"expliquer le problème ({noms}) : les preuves disponibles ne "
            "permettent pas de les départager. Aucune cause unique n'est "
            "attribuée.")
    # Faits pertinents présents mais aucun lieu causal cohérent (>=2
    # catégories comportementales dans un même fichier) : présence lexicale
    # insuffisante pour une cause.
    if relevant_facts and not strong_candidates:
        incertitudes.append(
            "Des éléments liés au domaine ont été observés, mais ils relèvent "
            "d'une présence isolée (p. ex. un import ou un mot-clé) et ne "
            "démontrent, à eux seuls, aucune relation causale.")

    # 5. Analyse (texte factuel, strictement adossé aux faits observés).
    if relevant_facts:
        cats = sorted({f.categorie for f in relevant_facts})
        fichiers_concernes = sorted({f.fichier for f in relevant_facts})
        analyse = (
            f"J'ai examiné {len(relevant_files)} fichier(s) et observé "
            f"{len(relevant_facts)} élément(s) directement liés à la demande "
            f"({', '.join(cats)}), répartis dans : "
            f"{', '.join(fichiers_concernes)}.")
    elif all_facts:
        analyse = (
            f"J'ai examiné {len(relevant_files)} fichier(s) et relevé "
            f"{len(all_facts)} élément(s), mais aucun ne se rattache "
            f"directement au domaine de la demande.")
    else:
        analyse = (
            f"J'ai examiné {len(relevant_files)} fichier(s), mais le contenu "
            f"disponible ne contient aucun élément exploitable pour conclure.")

    # 6. Cause probable — UNIQUEMENT si des faits pertinents l'étayent.
    #    Fail-closed : jamais une cause inventée. On NOMME les éléments
    #    observés et le lieu causal UNIQUE, sans affirmer une certitude.
    #    HIGH => il existe exactement UN fichier candidat fort (>= 2
    #    catégories comportementales cohérentes). On NE choisit jamais
    #    arbitrairement parmi plusieurs : la pluralité a déjà rétrogradé
    #    la confiance en MEDIUM et émis une incertitude dédiée.
    cause_probable: Optional[str] = None
    correction_minimale: Optional[str] = None

    if confiance == "HIGH" and len(strong_candidates) == 1:
        locus = next(iter(strong_candidates))               # fichier unique
        cats_locus = sorted(strong_candidates[locus])
        # Faits comportementaux de CE fichier (preuve directe, sourcée).
        locus_facts = sorted(
            (f for f in _behavioral_relevant(relevant_facts, relevant_cats)
             if f.fichier == locus),
            key=lambda f: f.ligne_debut)
        lignes = ", ".join(f"L{f.ligne_debut}" for f in locus_facts)
        cause_probable = (
            f"Les éléments observés dans '{locus}' présentent plusieurs "
            f"indices comportementaux cohérents ({', '.join(cats_locus)} "
            f"aux lignes {lignes}) convergeant vers le domaine « {domaine} » "
            f"de la demande. Cette attribution repose sur le contenu "
            f"réellement inspecté et sur la concordance d'au moins deux "
            f"indices dans un même fichier, non sur une simple présence de "
            f"mots-clés ni sur une supposition.")
        correction_minimale = (
            f"Examiner puis ajuster, dans '{locus}', la logique "
            f"comportementale identifiée ({', '.join(cats_locus)}, "
            f"lignes {lignes}), en conservant le comportement attendu du "
            f"domaine « {domaine} ». Correction à préparer en mode CORRIGER "
            f"(soumise à R1/D5.8/D5.9 + approbation humaine). Aucune "
            f"modification n'est effectuée ici.")
    else:
        # Pas de lieu causal unique et cohérent : on refuse de conclure.
        incertitudes.append(
            "Le contenu disponible ne permet pas de confirmer la cause.")

    return AnalysisResult(
        demande_comprise=demande,
        faits_verifies=tuple(all_facts),
        elements_examines=tuple(elements),
        analyse=analyse,
        cause_probable=cause_probable,
        correction_minimale=correction_minimale,
        confiance=confiance,
        incertitudes=tuple(incertitudes),
        aucune_modification=True,
    )


def render_analysis_text(result: AnalysisResult, structured_intent) -> str:
    """
    Rendu TEXTE lisible (compatible avec l'affichage CLI existant), dérivé
    STRICTEMENT de l'AnalysisResult. Aucune information nouvelle n'est
    ajoutée ici : pure présentation. Déterministe.
    """
    si = structured_intent
    lines: list[str] = []
    lines.append("ANALYSE (lecture seule — aucune modification)")
    lines.append(
        f"- Objectif compris : {getattr(si, 'objectif', 'UNKNOWN')} "
        f"| domaine : {getattr(si, 'domaine', 'UNKNOWN')} "
        f"| risque : {getattr(si, 'risque', 'UNKNOWN')} "
        f"| confiance (analyse) : {result.confiance}")
    lines.append(f"- Demande comprise : {result.demande_comprise}")

    # Section de compatibilité (contrat historique) : nommer explicitement
    # les fichiers pertinents réellement inspectés. Les « éléments examinés »
    # SONT ces fichiers ; on conserve le libellé « Fichiers pertinents »
    # attendu par les consommateurs/tests existants.
    lines.append(f"- Fichiers pertinents identifiés "
                 f"({len(result.elements_examines)}) :")
    for p in result.elements_examines:
        lines.append(f"    • {p}")

    lines.append(f"- Faits vérifiés ({len(result.faits_verifies)}) "
                 f"— chacun sourcé (fichier, ligne, extrait, SHA) :")
    for f in result.faits_verifies:
        lines.append(
            f"    • [{f.categorie}] {f.fichier}:L{f.ligne_debut} "
            f"(sha {f.sha[:12]}) :: {f.extrait}")

    lines.append(f"- Analyse : {result.analyse}")

    if result.cause_probable is not None:
        lines.append(f"- Cause probable : {result.cause_probable}")
    else:
        lines.append("- Cause probable : non déterminée (preuves insuffisantes).")

    if result.correction_minimale is not None:
        lines.append(f"- Correction minimale (descriptive) : "
                     f"{result.correction_minimale}")
    else:
        lines.append("- Correction minimale : non proposée "
                     "(cause non confirmée).")

    if result.incertitudes:
        lines.append("- Incertitudes :")
        for u in result.incertitudes:
            lines.append(f"    • {u}")

    lines.append("- Aucune affirmation non étayée par un fichier inspecté. "
                 "Aucune modification effectuée.")
    return "\n".join(lines)
