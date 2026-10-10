"""
MemoLibDev — Evidence Gate v1 (déterministe, fail-closed, isolé)
================================================================

Évalue une AFFIRMATION (`claim`) par rapport à des PREUVES présentes dans
un contexte inspecté. Composant NOUVEAU et ISOLÉ : branché sur rien
(ni agent_loop, ni D5.8/D5.9, ni LLM, ni CLI/API). Il PRODUIT UNIQUEMENT
UNE ÉVALUATION STRUCTURÉE. Il ne donne AUCUNE autorité d'exécution :
aucun apply, aucun commit, aucun git, aucune écriture.

Question à laquelle v1 répond :
    « Ce que l'on affirme est-il effectivement démontré par les fichiers
      inspectés ? » — de façon déterministe et fail-closed.

Principes NON négociables :
  - L'absence de preuve ne transforme JAMAIS une affirmation en FACT.
  - Une phrase produite par un LLM n'est JAMAIS une preuve en soi.
  - Fail-closed : jamais ACCEPT par défaut ; en cas de doute -> REVIEW.
  - Déterministe : même (claim, inspected_files) -> même résultat.
  - v1 volontairement limitée : correspondance lexicale littérale entre
    les affirmations vérifiables du claim et le CONTENU réel des fichiers.
    Pas de compréhension sémantique du dépôt.

Classification :
    FACT        — affirmation vérifiable littéralement présente dans le
                  contenu du fichier référencé (preuve directe).
    INFERENCE   — éléments présents, mais la conclusion dépasse la preuve
                  directe (déduction plausible non littérale).
    HYPOTHESIS  — formulée comme hypothèse / éléments trop faibles.
    UNKNOWN     — aucune preuve exploitable.

Verdict (fail-closed) :
    ACCEPT  — FACT avec preuve directe suffisante.
    REVIEW  — INFERENCE / HYPOTHESIS / UNKNOWN (doute -> humain).
    REJECT  — preuve CONTRADICTOIRE explicite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re


# Classifications
FACT = "FACT"
INFERENCE = "INFERENCE"
HYPOTHESIS = "HYPOTHESIS"
UNKNOWN = "UNKNOWN"

# Verdicts
ACCEPT = "ACCEPT"
REVIEW = "REVIEW"
REJECT = "REJECT"


# ------------------------------------------------------------------
# Structures minimales et explicites (pas de couplage à MissionContext)
# ------------------------------------------------------------------

@dataclass(frozen=True)
class InspectedFile:
    """Preuve disponible : un fichier inspecté (chemin + contenu réel)."""
    path: str
    content: str
    sha256: str = ""        # optionnel, si déjà disponible
    role: str = ""          # optionnel (SOURCE/TEST/...), indicatif


@dataclass(frozen=True)
class EvidenceResult:
    claim: str
    classification: str          # FACT | INFERENCE | HYPOTHESIS | UNKNOWN
    verdict: str                 # ACCEPT | REVIEW | REJECT
    evidence_used: tuple[str, ...]   # chemins ayant fourni une preuve
    reason: str
    contradictions: tuple[str, ...] = ()
    deterministic: bool = True
    fail_closed: bool = True

    def to_dict(self) -> dict:
        return {
            "claim": self.claim,
            "classification": self.classification,
            "verdict": self.verdict,
            "evidence_used": list(self.evidence_used),
            "reason": self.reason,
            "contradictions": list(self.contradictions),
            "deterministic": self.deterministic,
            "fail_closed": self.fail_closed,
        }


# ------------------------------------------------------------------
# Analyse déterministe du claim
# ------------------------------------------------------------------

# Marqueurs d'incertitude -> HYPOTHESIS (le claim lui-même se dit incertain).
_HYPOTHESIS_MARKERS = (
    "peut-être", "peut etre", "probablement", "sans doute", "je pense",
    "il semble", "semble", "possiblement", "pourrait", "may ", "might ",
    "maybe", "probably", "i think", "seems", "could be", "hypothèse",
    "hypothese", "suppose", "suppos",
)

# Référence de fichier dans le claim : chemins type a/b.ext ou mots .ext.
_PATH_RE = re.compile(r"[\w./\-\[\]]+\.[A-Za-z0-9]+")
# Fragments entre guillemets = affirmations vérifiables littérales.
_QUOTED_RE = re.compile(r"[\"'`]([^\"'`]{2,})[\"'`]")
# Négations simples (pour détecter une contradiction grossière).
_NEG_RE = re.compile(r"\b(ne|n'|not|no|jamais|aucun|absent|pas)\b", re.I)


def _normalize(s: str) -> str:
    return (s or "").strip()


def _referenced_paths(claim: str) -> list[str]:
    """Chemins de fichiers littéralement cités dans le claim (déterministe)."""
    out: list[str] = []
    for m in _PATH_RE.findall(claim):
        if m not in out:
            out.append(m)
    return out


def _verifiable_fragments(claim: str) -> list[str]:
    """
    Fragments 'vérifiables' du claim : d'abord ce qui est entre guillemets
    (affirmation littérale forte), sinon les identifiants significatifs.
    """
    quoted = [m.strip() for m in _QUOTED_RE.findall(claim) if m.strip()]
    if quoted:
        return quoted
    # Identifiants significatifs (symboles de code), hors mots trop courts.
    idents = re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", claim)
    # On enlève les chemins (gérés à part) et quelques mots vides.
    stop = {"dans", "le", "la", "les", "fichier", "contient", "existe",
            "the", "file", "contains", "exists", "function", "fonction",
            "classe", "class", "cette", "ligne", "line", "code", "with",
            "that", "this", "pour", "avec", "dans"}
    return [w for w in idents if w.lower() not in stop and "." not in w]


def _file_by_path(inspected, path: str):
    """Retrouve un fichier inspecté par correspondance de chemin (suffixe)."""
    p = path.replace("\\", "/").lower()
    for f in inspected:
        fp = f.path.replace("\\", "/").lower()
        if fp == p or fp.endswith("/" + p) or p.endswith("/" + fp) or fp.endswith(p):
            return f
    return None


# ------------------------------------------------------------------
# API v1
# ------------------------------------------------------------------

def classify(claim, inspected_files) -> EvidenceResult:
    """
    Classe `claim` par rapport aux `inspected_files` (liste d'InspectedFile).
    Déterministe, fail-closed. N'exécute rien, ne modifie rien.
    """
    claim = _normalize(claim if isinstance(claim, str) else "")

    # G — claim vide/invalide -> fail-closed.
    if not claim:
        return EvidenceResult(
            claim="", classification=UNKNOWN, verdict=REVIEW,
            evidence_used=(), reason="claim vide/invalide (fail-closed)")

    inspected = list(inspected_files or [])

    # F — contexte vide -> aucune preuve possible.
    if not inspected:
        return EvidenceResult(
            claim=claim, classification=UNKNOWN, verdict=REVIEW,
            evidence_used=(),
            reason="aucun fichier inspecté : preuve impossible (fail-closed)")

    low_claim = claim.lower()
    is_hypothesis = any(m in low_claim for m in _HYPOTHESIS_MARKERS)

    ref_paths = _referenced_paths(claim)
    fragments = _verifiable_fragments(claim)

    # Détermine le périmètre de preuve : si le claim cite un fichier, la
    # preuve DOIT venir de CE fichier (sinon pas d'ACCEPT -> cas I).
    scoped_files = None
    scoped_missing = False
    if ref_paths:
        scoped_files = []
        for rp in ref_paths:
            f = _file_by_path(inspected, rp)
            if f is not None:
                scoped_files.append(f)
        if not scoped_files:
            scoped_missing = True

    search_files = scoped_files if scoped_files else inspected

    # Recherche des fragments vérifiables dans le CONTENU réel.
    found_in: dict[str, list[str]] = {}
    contradictions: list[str] = []
    for frag in fragments:
        fl = frag.lower()
        for f in search_files:
            if fl and fl in (f.content or "").lower():
                found_in.setdefault(frag, [])
                if f.path not in found_in[frag]:
                    found_in[frag].append(f.path)

    evidence_used = tuple(sorted({p for ps in found_in.values() for p in ps}))

    # C — contradiction : le claim affirme la présence d'un fragment MAIS
    # il est explicitement absent du fichier cité, alors que le claim est
    # formulé positivement (pas de négation). On ne "prouve" pas l'absence
    # en général (fail-closed) ; on ne déclare REJECT que si le claim cite
    # un fichier précis, que le fichier EXISTE, et qu'une affirmation
    # littérale forte (entre guillemets) y est absente -> contradiction nette.
    has_negation = bool(_NEG_RE.search(claim))
    quoted_fragments = [m.strip() for m in _QUOTED_RE.findall(claim) if m.strip()]

    if ref_paths and scoped_files and quoted_fragments and not has_negation:
        for frag in quoted_fragments:
            present = any(frag.lower() in (f.content or "").lower()
                          for f in scoped_files)
            if not present:
                contradictions.append(
                    f"fragment cité absent du fichier référencé : {frag[:40]!r}")
        if contradictions:
            return EvidenceResult(
                claim=claim, classification=UNKNOWN, verdict=REJECT,
                evidence_used=(), reason="affirmation contredite par le contenu "
                "réel du fichier référencé",
                contradictions=tuple(contradictions))

    # I — fichier cité introuvable -> pas d'ACCEPT, preuve insuffisante.
    if scoped_missing:
        return EvidenceResult(
            claim=claim, classification=UNKNOWN, verdict=REVIEW,
            evidence_used=(),
            reason="fichier référencé par le claim introuvable dans le "
            "contexte inspecté (fail-closed, pas d'ACCEPT)")

    # Le claim se présente comme une hypothèse -> HYPOTHESIS/REVIEW,
    # même si des éléments sont trouvés (le claim lui-même ne tranche pas).
    if is_hypothesis:
        return EvidenceResult(
            claim=claim, classification=HYPOTHESIS, verdict=REVIEW,
            evidence_used=evidence_used,
            reason="affirmation formulée comme hypothèse : non démontrée, "
            "revue humaine requise")

    # B/A — selon la force de la preuve trouvée.
    if not fragments:
        # Rien de vérifiable dans le claim (trop vague).
        return EvidenceResult(
            claim=claim, classification=UNKNOWN, verdict=REVIEW,
            evidence_used=(),
            reason="aucune affirmation vérifiable extraite du claim "
            "(trop vague, fail-closed)")

    all_found = all(f in found_in for f in fragments)
    some_found = len(found_in) > 0

    if all_found and ref_paths and scoped_files:
        # Preuve directe : fragments présents DANS le fichier cité.
        return EvidenceResult(
            claim=claim, classification=FACT, verdict=ACCEPT,
            evidence_used=evidence_used,
            reason="toutes les affirmations vérifiables du claim sont "
            "présentes dans le contenu réel du fichier référencé")

    if all_found and not ref_paths:
        # Fragments trouvés mais sans fichier cité : preuve présente mais
        # la localisation exacte n'est pas affirmée -> INFERENCE/REVIEW.
        return EvidenceResult(
            claim=claim, classification=INFERENCE, verdict=REVIEW,
            evidence_used=evidence_used,
            reason="éléments présents dans le contexte mais aucun fichier "
            "précis n'est affirmé : déduction, revue humaine requise")

    if some_found:
        return EvidenceResult(
            claim=claim, classification=INFERENCE, verdict=REVIEW,
            evidence_used=evidence_used,
            reason="preuve partielle : certaines affirmations non démontrées, "
            "revue humaine requise")

    # Aucun fragment trouvé.
    return EvidenceResult(
        claim=claim, classification=UNKNOWN, verdict=REVIEW,
        evidence_used=(),
        reason="aucune des affirmations vérifiables n'a été trouvée dans le "
        "contenu inspecté (fail-closed, pas d'ACCEPT)")
