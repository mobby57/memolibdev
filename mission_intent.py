"""
MemoLibDev — 5.2 : Compréhension structurée de mission (déterministe)
=====================================================================

Transforme une mission en langage naturel en une structure explicite :

    StructuredIntent {
        objectif          : str   (CORRIGER / ANALYSER / AJOUTER / ... / UNKNOWN)
        domaine           : str   (AUTH / ROUTES / UI / DATA / CONFIG / DOC /
                                    TESTS / SECURITE / ... / UNKNOWN)
        type_mission      : str   (BUG / ANALYSE / FEATURE / REFACTOR / ... / UNKNOWN)
        cibles_probables  : tuple[str]  (indices lexicaux, JAMAIS inventés)
        risque            : str   (LOW / MEDIUM / HIGH / UNKNOWN)
        confiance         : str   (HIGH / MEDIUM / LOW)  — honnêteté de l'extraction
    }

Principes (exigés) :
  - 100 % DÉTERMINISTE, SANS LLM : table de mots-clés -> catégories.
  - REPRÉSENTE L'INCERTITUDE : si aucune preuve lexicale suffisante,
    le champ vaut "UNKNOWN". On N'INVENTE JAMAIS un domaine/une cible.
  - ISOLÉ : ce module ne modifie rien, n'est branché sur rien (la
    consommation par la sélection = 5.3, séparé). Aucune autorité.
  - Les `cibles_probables` sont des INDICES (hints), pas des chemins de
    fichiers réels ni une autorité de scope. Elles proviennent uniquement
    des mots présents dans la mission.

Aucun import de guardrail (D5.8/D5.9/R1), aucun accès disque, aucun git.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


UNKNOWN = "UNKNOWN"

# ------------------------------------------------------------------
# Vocabulaire déterministe (fr/en). Chaque entrée = preuve lexicale.
# ------------------------------------------------------------------

# OBJECTIF : ce que l'utilisateur veut faire.
_OBJECTIFS = {
    "CORRIGER": ("corrige", "corriger", "répare", "repare", "réparer", "fix",
                 "résous", "resous", "résoudre", "debug", "déboguer"),
    "ANALYSER": ("analyse", "analyser", "genere", "génère", "fais", "evalue", "évalue", "evaluer", "évaluer", "audite", "comprends", "comprendre", "explique",
                 "expliquer", "identifie", "identifier", "diagnostique",
                 "diagnostic", "inspecte", "inspecter", "examine", "vérifie",
                 "verifier", "audit", "decris", "décris", "decrire", "décrire",
                 "decrit", "décrit", "description", "documente", "documenter",
                 "liste", "lister", "resume", "résume", "resumer", "présente",
                 "presente", "explore", "explorer", "etat des lieux", "état des lieux", "topo", "tampon"),
    "AJOUTER":  ("ajoute", "ajouter", "crée", "creer", "créer", "implémente",
                 "implemente", "implémenter", "nouveau", "nouvelle", "add"),
    "MODIFIER": ("modifie", "modifier", "change", "changer", "mets à jour",
                 "met à jour", "update", "améliore", "ameliore", "améliorer"),
    "SUPPRIMER": ("supprime", "supprimer", "retire", "retirer", "enlève",
                  "enlever", "delete", "remove"),
    "REFACTORER": ("refactor", "refactore", "refactorer", "réorganise",
                   "reorganise", "nettoie", "nettoyer", "simplifie"),
}

# DOMAINE : zone fonctionnelle concernée.
_DOMAINES = {
    "AUTH":     ("auth", "authentification", "authentication", "login",
                 "connexion", "connecter", "session", "clerk", "oauth",
                 "token", "jwt", "mot de passe", "password", "signin"),
    "ROUTES":   ("route", "routes", "api", "endpoint", "endpoints",
                 "middleware", "proxy", "navigation", "redirection", "url"),
    "UI":       ("ui", "interface", "composant", "component", "page", "écran",
                 "ecran", "affichage", "css", "style", "bouton", "formulaire",
                 "layout", "render", "rendu"),
    "DATA":     ("données", "donnees", "data", "prisma", "schema", "schéma",
                 "base de données", "database", "db", "modèle", "modele",
                 "migration", "requête", "requete", "query"),
    "CONFIG":   ("config", "configuration", "variable", "variables",
                 "environnement", "env", "tsconfig", "package.json",
                 "next.config", "paramètre", "parametre", "réglage"),
    "TESTS":    ("test", "tests", "couverture", "coverage", "scénario",
                 "scenario", "spec", "mock", "jest", "vitest"),
    "DOC":      ("documentation", "doc", "docs", "readme", "cahier",
                 "charges", "guide", "manuel", "règle", "regle", "rules"),
    "SECURITE": ("sécurité", "securite", "security", "vulnérabilité",
                 "vulnerabilite", "faille", "secret", "secrets",
                 "credential", "credentials", "rgpd", "chiffrement"),
}

# TYPE de mission.
_TYPES = {
    "BUG":      ("bug", "erreur", "error", "problème", "probleme", "panne",
                 "cassé", "casse", "ne marche pas", "ne fonctionne pas",
                 "plante", "crash", "échoue", "echoue"),
    "FEATURE":  ("ajoute", "ajouter", "nouveau", "nouvelle", "feature",
                 "fonctionnalité", "fonctionnalite", "implémente", "implemente"),
    "ANALYSE":  ("analyse", "analyser", "comprends", "comprendre", "explique",
                 "identifie", "diagnostic", "inspecte", "examine", "audit",
                 "decris", "décris", "decrire", "décrire", "documente",
                 "liste", "resume", "résume", "présente", "presente",
                 "explore", "explorer"),
    "REFACTOR": ("refactor", "refactore", "réorganise", "reorganise",
                 "nettoie", "simplifie", "restructure"),
}

# Mots -> indices de cibles probables (hints lexicaux, PAS des fichiers réels).
_CIBLE_HINTS = {
    "proxy": "proxy", "middleware": "middleware", "login": "login",
    "auth": "auth", "route": "route", "routes": "routes", "api": "api",
    "composant": "composant", "component": "component", "page": "page",
    "prisma": "prisma", "schema": "schema", "config": "config",
    "test": "test", "tests": "tests", "session": "session", "token": "token",
    "clerk": "clerk", "navigation": "navigation", "ui": "ui",
}

# Facteurs de risque lexicaux (élèvent le niveau).
_RISK_HIGH_TERMS = ("auth", "authentification", "sécurité", "securite",
                    "security", "token", "session", "production", "prod",
                    "paiement", "payment", "secret", "credential", "migration",
                    "supprime", "supprimer", "delete", "drop")
_RISK_MEDIUM_TERMS = ("api", "route", "routes", "data", "prisma", "schema",
                      "config", "middleware", "proxy")

_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_]*", re.UNICODE)
# Seuil minimal de mots significatifs pour tenter une extraction fiable.
_MIN_SIGNIFICANT_WORDS = 3


@dataclass(frozen=True)
class StructuredIntent:
    objectif: str
    domaine: str
    type_mission: str
    cibles_probables: tuple[str, ...]
    risque: str
    confiance: str          # HIGH | MEDIUM | LOW

    def to_dict(self) -> dict:
        return {
            "objectif": self.objectif,
            "domaine": self.domaine,
            "type_mission": self.type_mission,
            "cibles_probables": list(self.cibles_probables),
            "risque": self.risque,
            "confiance": self.confiance,
        }


def _normalize(text: str) -> str:
    return (text or "").lower().strip()


def _match_category(text: str, table: dict[str, tuple]) -> str:
    """
    Retourne la 1re catégorie (ordre du dict) dont un terme est présent
    dans le texte. UNKNOWN si aucune preuve lexicale. Déterministe.
    """
    for category, terms in table.items():
        for term in terms:
            if term in text:
                return category
    return UNKNOWN


def _extract_targets(text: str) -> tuple[str, ...]:
    """Indices de cibles présents LITTÉRALEMENT dans la mission (jamais inventés)."""
    found: list[str] = []
    for word, hint in _CIBLE_HINTS.items():
        if word in text and hint not in found:
            found.append(hint)
    return tuple(found)


def _assess_risk(text: str, domaine: str) -> str:
    if any(t in text for t in _RISK_HIGH_TERMS):
        return "HIGH"
    if any(t in text for t in _RISK_MEDIUM_TERMS):
        return "MEDIUM"
    # Domaine connu mais sans terme à risque -> LOW ; domaine inconnu -> UNKNOWN.
    if domaine != UNKNOWN:
        return "LOW"
    return UNKNOWN


def analyze_mission(text: str) -> StructuredIntent:
    """
    Analyse déterministe d'une mission. Représente l'incertitude : tout
    champ sans preuve lexicale suffisante vaut UNKNOWN. N'invente rien.
    """
    norm = _normalize(text)
    words = _WORD_RE.findall(norm)
    significant = [w for w in words if len(w) > 2]

    # Extraction par preuve lexicale (déterministe, sans invention).
    objectif = _match_category(norm, _OBJECTIFS)
    domaine = _match_category(norm, _DOMAINES)
    type_mission = _match_category(norm, _TYPES)
    cibles = _extract_targets(norm)
    risque = _assess_risk(norm, domaine)

    known = sum(1 for v in (objectif, domaine, type_mission) if v != UNKNOWN)

    # Mission trop courte ET sans AUCUNE preuve lexicale : incertitude
    # maximale, on n'invente rien. (Si des preuves existent, on les garde,
    # même sur une mission courte comme « corrige le login ».)
    if len(significant) < _MIN_SIGNIFICANT_WORDS and known == 0 and not cibles:
        return StructuredIntent(
            objectif=UNKNOWN, domaine=UNKNOWN, type_mission=UNKNOWN,
            cibles_probables=cibles, risque=UNKNOWN, confiance="LOW",
        )

    # Confiance : fonction du nombre de champs identifiés ET de la longueur.
    if known >= 2 and (cibles or domaine != UNKNOWN):
        confiance = "HIGH" if len(significant) >= _MIN_SIGNIFICANT_WORDS else "MEDIUM"
    elif known >= 1:
        confiance = "MEDIUM"
    else:
        confiance = "LOW"

    return StructuredIntent(
        objectif=objectif, domaine=domaine, type_mission=type_mission,
        cibles_probables=cibles, risque=risque, confiance=confiance,
    )
