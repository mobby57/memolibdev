"""
MemoLibDev — D6.0.1 : Context Builder (pipeline déterministe)
=============================================================

Construit un `MissionContext` CONTRÔLÉ à partir d'une mission texte et
d'un `ProjectTarget` résolu. Le client ne fournit QUE la mission ; le
builder détermine lui-même les fichiers pertinents, capture leurs
versions (SHA texte + octets), trace la provenance et borne le tout.

Pipeline :
    Mission (texte)
      -> inspect_target()                 (read-only, bornée au git_root)
      -> sélection de fichiers pertinents (déterministe, scorée)
      -> capture des versions (SHA x2 + HEAD)
      -> evidence tracée
      -> budget (réduction bornée)
      -> MissionContext

Invalidation :
    is_stale(context, target) -> StalenessReport
    Si un SHA ou le HEAD diverge -> CONTEXT_STALE. L'agent doit BLOCK et
    réinspecter ; jamais appliquer sur un contexte périmé.

Aucun LLM, aucun apply, aucun git mutant, aucune écriture. Déterministe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from project_target import ProjectTarget
from file_target import resolve_file_target, FileTargetError
import code_adapter

from context.project_inspector import inspect_target, InspectionResult
from context.context_version import (
    capture_file_version, check_staleness, StalenessReport,
)
from context.context_budget import apply_budget
from context.mission_context import (
    MissionContext, ProjectContext, RelevantFile, EvidenceEntry, HistoryEntry,
)


# Contraintes immuables injectées dans tout contexte (rappel des invariants).
DEFAULT_CONSTRAINTS = (
    "aucun commit",
    "aucun push",
    "aucune modification du control-plane",
    "validation humaine obligatoire (L6)",
    "application uniquement via D5.9",
)

# Détection déterministe de technologies (par présence de marqueurs).
_TECH_MARKERS = {
    "package.json": "node",
    "tsconfig.json": "typescript",
    "requirements.txt": "python",
    "pyproject.toml": "python",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "next.config.js": "nextjs",
    "next.config.mjs": "nextjs",
}

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _extract_terms(mission_text: str) -> set[str]:
    """Termes significatifs de la mission (déterministe, minuscules)."""
    return {w.lower() for w in _WORD_RE.findall(mission_text)}


def _score_file(path: str, preview: str, terms: set[str]) -> int:
    """
    Score déterministe d'un fichier vis-à-vis des termes de la mission.
    Pondération : chemin > contenu. Aucune magie, reproductible.
    """
    score = 0
    pl = path.lower()
    for t in terms:
        if t in pl:
            score += 8
    low_preview = preview.lower()
    for t in terms:
        score += min(low_preview.count(t), 5)  # bornage par terme
    return score


# ------------------------------------------------------------------
# Classement par RÔLE du fichier (étape 2 : pertinence du contexte)
# ------------------------------------------------------------------
#
# Le score lexical reste la base. On applique ENSUITE un multiplicateur
# selon le RÔLE du fichier ET l'INTENTION de la mission. Aucun rôle n'est
# jamais exclu (multiplicateurs toujours > 0) : DOC/RULES restent
# sélectionnables si la mission les concerne. Constantes explicites pour
# calibrage futur facile.

ROLE_SOURCE = "SOURCE"
ROLE_TEST = "TEST"
ROLE_CONFIG = "CONFIG"
ROLE_DOC = "DOC"
ROLE_RULES = "RULES"
ROLE_SCRIPT = "SCRIPT"        # (5A) scripts outillage/déploiement, distincts du code métier
ROLE_GENERATED = "GENERATED"  # (5A) fichiers générés/build, rarement la vraie cible
ROLE_OTHER = "OTHER"

# Multiplicateurs validés (ne pas modifier sans refaire le benchmark).
# (5A) SCRIPT = voisin faible du code (0.7 en CODE) ; GENERATED fortement
# dé-priorisé (0.2) car rarement la cible réelle, jamais exclu (>0).
_MULT_CODE_INTENT = {
    ROLE_SOURCE: 1.5, ROLE_TEST: 1.3, ROLE_CONFIG: 1.0,
    ROLE_DOC: 0.5, ROLE_RULES: 0.3, ROLE_SCRIPT: 0.7,
    ROLE_GENERATED: 0.2, ROLE_OTHER: 1.0,
}
_MULT_DOC_INTENT = {
    ROLE_DOC: 1.5, ROLE_RULES: 1.3, ROLE_SOURCE: 0.8,
    ROLE_TEST: 1.0, ROLE_CONFIG: 1.0, ROLE_SCRIPT: 0.8,
    ROLE_GENERATED: 0.2, ROLE_OTHER: 1.0,
}
_MULT_NEUTRE = {
    ROLE_SOURCE: 1.0, ROLE_TEST: 1.0, ROLE_CONFIG: 1.0,
    ROLE_DOC: 1.0, ROLE_RULES: 1.0, ROLE_SCRIPT: 1.0,
    ROLE_GENERATED: 1.0, ROLE_OTHER: 1.0,
}

# Préfixes/marqueurs de rôle (déterministes, par chemin).
_SOURCE_DIRS = ("src/", "app/", "lib/", "components/", "pages/", "server/")
_TEST_MARKERS = ("__tests__", ".test.", ".spec.", "tests/", "__mocks__")
_RULES_PREFIX = (".amazonq/", ".vscode/", ".github/", ".kiro/")
_SCRIPT_DIRS = ("scripts/", "script/", "tools/", "bin/")
_SCRIPT_EXT = {".sh", ".bash", ".ps1", ".bat", ".cmd"}
_SCRIPT_NAME_MARKERS = ("deploy", "setup", "install", "migrate", "seed",
                        "smoke", "diagnostic", "build-", "release")
_GENERATED_DIRS = ("dist/", "build/", "out/", ".next/", "coverage/",
                   "generated/", ".turbo/")
_GENERATED_MARKERS = (".generated.", ".min.", ".bundle.", ".map")
_CONFIG_EXT = {".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".env"}
_CONFIG_MARKERS = (".config.", "next.config", "tsconfig", "package.json")
_DOC_EXT = {".md", ".rst", ".txt"}
_DOC_DIRS = ("docs/", "doc/")
_SOURCE_EXT = {".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go", ".java",
               ".c", ".cpp", ".cs", ".rb", ".php", ".swift", ".kt"}

# Termes signalant une intention DOCUMENTAIRE explicite.
_DOC_INTENT_TERMS = {
    "documentation", "doc", "docs", "readme", "règle", "regle", "rules",
    "cahier", "charges", "guide", "manuel", "spécification", "specification",
    "spec", "procédure", "procedure",
}
# Termes signalant une intention CODE (large : cas par défaut dev).
_CODE_INTENT_TERMS = {
    "code", "bug", "corrige", "corriger", "fix", "auth", "login",
    "route", "routes", "composant", "component", "test", "tests",
    "type", "types", "typescript", "api", "fonction", "function",
    "classe", "class", "erreur", "error", "navigation", "proxy",
    "prisma", "schema", "config", "configuration", "session", "token",
    "sécurité", "securite", "security",
}


def _detect_role(path: str) -> str:
    """Rôle déterministe d'un fichier d'après son chemin/extension."""
    p = path.replace("\\", "/").lower()
    name = p.rsplit("/", 1)[-1]
    ext = ("." + name.rsplit(".", 1)[-1]) if "." in name else ""

    # Ordre : RULES, GENERATED, TEST, DOC, CONFIG, SCRIPT, SOURCE, OTHER.
    # (5A) GENERATED et SCRIPT sont distingués AVANT SOURCE : un script
    # d'outillage ou un fichier généré n'est pas du code métier.
    if p.startswith(_RULES_PREFIX):
        return ROLE_RULES
    if p.startswith(_GENERATED_DIRS) or any(m in name for m in _GENERATED_MARKERS):
        return ROLE_GENERATED
    if any(m in p for m in _TEST_MARKERS):
        return ROLE_TEST
    if p.startswith(_DOC_DIRS) or ext in _DOC_EXT:
        return ROLE_DOC
    if ext in _CONFIG_EXT or any(m in name for m in _CONFIG_MARKERS):
        return ROLE_CONFIG
    if p.startswith(_SCRIPT_DIRS) or ext in _SCRIPT_EXT \
            or any(m in name for m in _SCRIPT_NAME_MARKERS):
        return ROLE_SCRIPT
    if p.startswith(_SOURCE_DIRS) or ext in _SOURCE_EXT:
        return ROLE_SOURCE
    return ROLE_OTHER


def _mission_intent(terms: set[str]) -> str:
    """
    Intention déterministe : DOC_INTENT si la mission parle explicitement
    de documentation/règles ; CODE_INTENT si elle contient des termes de
    code ; sinon neutre. (DOC prime sur CODE si les deux apparaissent, car
    une demande doc explicite est plus spécifique.)
    """
    has_doc = bool(terms & _DOC_INTENT_TERMS)
    has_code = bool(terms & _CODE_INTENT_TERMS)
    if has_doc and not has_code:
        return "DOC"
    if has_doc and has_code:
        return "DOC"   # demande documentaire explicite = plus spécifique
    if has_code:
        return "CODE"
    return "NEUTRE"


def _role_multiplier(intent: str, role: str) -> float:
    table = {"CODE": _MULT_CODE_INTENT, "DOC": _MULT_DOC_INTENT}.get(
        intent, _MULT_NEUTRE)
    return table.get(role, 1.0)


# ==================================================================
# 5.3 — Consommation de StructuredIntent + budget de contexte
# ==================================================================
#
# Le score lexical pondéré par rôle (5A) reste la BASE. 5.3 applique
# ENSUITE un boost déterministe fondé sur StructuredIntent (5.2), modulé
# par la confiance. Aucune invention : si un champ vaut UNKNOWN, il
# n'apporte aucun boost. 5.3 COMPLÈTE 5A, ne le remplace pas.

# --- Budget de contexte 5.3 (explicite, déterministe, fail-closed) ---
MAX_CONTEXT_FILES = 8
MAX_CONTEXT_CHARS = 24000

# --- Boosts d'intention (constantes explicites, calibrage facile) ---
# Cible probable présente dans le CHEMIN du fichier : boost fort.
_BOOST_TARGET_IN_PATH = 1.6
# Affinité domaine (5.2) <-> rôle (5A) : favorise le bon type de fichier.
# Pour chaque domaine, rôles favorisés (>1) et éventuellement défavorisés.
_DOMAIN_ROLE_AFFINITY = {
    "AUTH":     {ROLE_SOURCE: 1.4, ROLE_TEST: 1.2, ROLE_DOC: 0.6, ROLE_RULES: 0.5, ROLE_GENERATED: 0.3},
    "ROUTES":   {ROLE_SOURCE: 1.4, ROLE_TEST: 1.1, ROLE_DOC: 0.6, ROLE_RULES: 0.5, ROLE_GENERATED: 0.3},
    "UI":       {ROLE_SOURCE: 1.4, ROLE_TEST: 1.1, ROLE_DOC: 0.6, ROLE_GENERATED: 0.3},
    "DATA":     {ROLE_SOURCE: 1.2, ROLE_CONFIG: 1.3, ROLE_GENERATED: 0.3},
    "CONFIG":   {ROLE_CONFIG: 1.5, ROLE_SCRIPT: 1.1, ROLE_SOURCE: 0.8, ROLE_GENERATED: 0.3},
    "TESTS":    {ROLE_TEST: 1.6, ROLE_SOURCE: 1.0, ROLE_SCRIPT: 0.7, ROLE_DOC: 0.6},
    "DOC":      {ROLE_DOC: 1.5, ROLE_RULES: 1.3, ROLE_SOURCE: 0.8},
    "SECURITE": {ROLE_SOURCE: 1.3, ROLE_TEST: 1.2, ROLE_CONFIG: 1.1, ROLE_GENERATED: 0.3},
}

# Modulation du boost selon la confiance de 5.2 (jamais une certitude).
_CONFIDENCE_WEIGHT = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}


def _intent_boost(intent_struct, path: str, role: str, *,
                  base_intent: str | None = None) -> float:
    """
    Facteur multiplicatif déterministe (>= un plancher > 0) issu de
    StructuredIntent. Neutre (1.0) si incertitude totale. N'invente rien :
    - boost cible SEULEMENT si la cible probable apparaît littéralement
      dans le chemin ;
    - boost domaine<->rôle SEULEMENT si domaine != UNKNOWN.
    Le tout est atténué par la confiance (HIGH/MEDIUM/LOW).
    """
    if intent_struct is None:
        return 1.0
    # Une demande documentaire explicite est déjà l'autorité la plus
    # spécifique de 5A. Un domaine 5.2 (p. ex. AUTH) ne doit pas faire
    # remonter du code devant la documentation demandée.
    if base_intent == "DOC":
        return 1.0
    conf = _CONFIDENCE_WEIGHT.get(getattr(intent_struct, "confiance", "LOW"), 0.3)
    pl = path.replace("\\", "/").lower()

    factor = 1.0

    # 1. Cibles probables présentes dans le chemin (preuve littérale).
    cibles = getattr(intent_struct, "cibles_probables", ()) or ()
    if any(c and c.lower() in pl for c in cibles):
        # Boost atténué par la confiance : (boost-1)*conf + 1.
        factor *= 1.0 + (_BOOST_TARGET_IN_PATH - 1.0) * conf

    # 2. Affinité domaine<->rôle (jamais si domaine inconnu).
    domaine = getattr(intent_struct, "domaine", "UNKNOWN")
    if domaine and domaine != "UNKNOWN":
        aff = _DOMAIN_ROLE_AFFINITY.get(domaine, {}).get(role)
        if aff is not None:
            factor *= 1.0 + (aff - 1.0) * conf

    # Plancher strict : jamais 0 (pas d'exclusion par 5.3).
    return max(factor, 0.05)


@dataclass(frozen=True)
class BudgetMetrics:
    """Métriques déterministes du budget de contexte 5.3."""
    candidats_total: int
    candidats_classes: int
    fichiers_selectionnes: int
    fichiers_exclus_budget: int
    fichiers_exclus_trop_grands: int
    chars_selectionnes: int
    budget_files: int
    budget_chars: int


def _apply_context_budget(ranked: list[dict], *,
                          max_files: int = MAX_CONTEXT_FILES,
                          max_chars: int = MAX_CONTEXT_CHARS):
    """
    Applique le budget 5.3 APRÈS classement. Déterministe, fail-closed :
      - au plus `max_files` fichiers ;
      - somme des tailles d'aperçu <= `max_chars` ;
      - un fichier dont l'aperçu seul dépasse `max_chars` est EXCLU
        (jamais tronqué silencieusement, jamais de dépassement) ;
      - un fichier qui ferait dépasser le total est sauté, on continue
        avec les candidats suivants pouvant entrer dans le budget.
    `ranked` doit déjà être trié (score desc, puis chemin — tie-break stable).
    Retourne (selected: list[dict], metrics: BudgetMetrics).
    """
    selected: list[dict] = []
    total = 0
    excl_budget = 0
    excl_too_large = 0

    for item in ranked:
        size = len(item.get("preview", "") or "")
        if size > max_chars:
            excl_too_large += 1          # fichier individuel trop grand -> exclu
            continue
        if len(selected) >= max_files:
            excl_budget += 1
            continue
        if total + size > max_chars:
            excl_budget += 1
            continue                     # saute, tente le candidat suivant
        selected.append(item)
        total += size

    metrics = BudgetMetrics(
        candidats_total=len(ranked),
        candidats_classes=len(ranked),
        fichiers_selectionnes=len(selected),
        fichiers_exclus_budget=excl_budget,
        fichiers_exclus_trop_grands=excl_too_large,
        chars_selectionnes=total,
        budget_files=max_files,
        budget_chars=max_chars,
    )
    return selected, metrics


def _detect_technologies(inspection: InspectionResult) -> tuple[str, ...]:
    names = {Path(f.path).name for f in inspection.files}
    techs = sorted({tech for marker, tech in _TECH_MARKERS.items()
                    if marker in names})
    # Déduction par extensions présentes.
    exts = {Path(f.path).suffix.lower() for f in inspection.files}
    if ".py" in exts:
        techs.append("python")
    if ".ts" in exts or ".tsx" in exts:
        techs.append("typescript")
    return tuple(sorted(set(techs)))


def _capabilities() -> tuple[str, ...]:
    """Capacités réellement disponibles (v1 : code_adapter)."""
    kinds = ",".join(sorted(code_adapter.ACCEPTED_KINDS))
    return (f"adapter=code_adapter", f"kinds={kinds}")


def build_mission_context(
    mission_id: str,
    mission_text: str,
    target: ProjectTarget,
    *,
    risk_level: str = "MEDIUM",
    history: tuple[HistoryEntry, ...] = (),
    max_files: int = MAX_CONTEXT_FILES,
    max_context_chars: int = MAX_CONTEXT_CHARS,
) -> MissionContext:
    """
    Construit le MissionContext. `mission_text` est la SEULE donnée
    client ; elle n'est jamais une autorité. Les fichiers pertinents et
    leurs versions sont déterminés et capturés par le builder.
    """
    if not mission_text.strip():
        raise ValueError("mission vide")

    inspection = inspect_target(target, max_files=max_files * 100)
    terms = _extract_terms(mission_text)
    intent = _mission_intent(terms)   # CODE | DOC | NEUTRE (déterministe)

    # Sélection déterministe des candidats (score > 0), exclut .git etc.
    # (déjà exclus par l'inspecteur). On ne retient que les fichiers de
    # la cible — jamais rien fourni par le client.
    #
    # Étape 2 : le score lexical est pondéré par le RÔLE du fichier selon
    # l'intention de la mission. Aucun rôle n'est exclu (multiplicateurs
    # > 0) : DOC/RULES restent sélectionnables si la mission les concerne.
    #
    # Étape 5.3 : le score (base × rôle 5A) est ENSUITE pondéré par un
    # boost déterministe issu de StructuredIntent (5.2), modulé par la
    # confiance. Puis classement déterministe, puis BUDGET explicite.
    from mission_intent import analyze_mission
    struct_intent = analyze_mission(mission_text)   # 5.2 (déterministe)

    candidates: list[dict] = []
    for f in inspection.files:
        base = _score_file(f.path, f.preview, terms)
        if base <= 0:
            continue
        role = _detect_role(f.path)
        mult = _role_multiplier(intent, role)             # 5A
        boost = _intent_boost(struct_intent, f.path, role, base_intent=intent)  # 5.3
        score = int(round(base * mult * boost))
        if score <= 0:
            score = 1  # garde-fou : jamais 0 (pas d'exclusion par le scoring)
        candidates.append({"path": f.path, "score": score,
                           "preview": f.preview, "role": role,
                           "base_score": base})

    # Classement déterministe : score desc, puis chemin asc (tie-break stable).
    ranked = sorted(candidates, key=lambda c: (-c["score"], c["path"]))

    # BUDGET 5.3 explicite et fail-closed (appliqué APRÈS le classement).
    selected, budget_metrics = _apply_context_budget(
        ranked, max_files=max_files, max_chars=max_context_chars)

    # Capture des versions (SHA texte + octets + HEAD) et evidence.
    relevant: list[RelevantFile] = []
    evidence: list[EvidenceEntry] = []
    provenance: list[str] = []

    for item in selected:
        version = capture_file_version(target.git_root, item["path"],
                                       target.head_full)
        # Résolution FileTarget pour obtenir le kind (sans modifier le fichier).
        try:
            ft = resolve_file_target(item["path"], target, risk_level=risk_level)
            kind = ft.kind
        except FileTargetError:
            kind = "UNKNOWN"

        relevant.append(RelevantFile(
            path=item["path"], score=item["score"], kind=kind,
            version=version, preview=item["preview"],
        ))
        evidence.append(EvidenceEntry(
            source_path=item["path"],
            text_sha256=version.text_sha256,
            byte_sha256=version.byte_sha256,
            line_start=1,
            line_end=max(1, item["preview"].count("\n") + 1),
            reason=f"Sélectionné pour la mission (score={item['score']})",
        ))
        provenance.append(
            f"{item['path']} @ HEAD {target.head_full[:12]} "
            f"text={version.text_sha256[:12]} byte={version.byte_sha256[:12]}"
        )

    project = ProjectContext(
        name=Path(target.git_root).name,
        git_root=str(target.git_root),
        git_head=target.head_full,
        branch=target.branch,
        fingerprint=target.fingerprint,
        technologies=_detect_technologies(inspection),
        files_count=inspection.files_count,
    )

    return MissionContext(
        mission_id=mission_id,
        mission_text=mission_text,
        constraints=DEFAULT_CONSTRAINTS,
        project=project,
        relevant_files=tuple(relevant),
        evidence=tuple(evidence),
        provenance=tuple(provenance),
        history=tuple(history),
        risk_level=risk_level,
        capabilities=_capabilities(),
        budget_reduced=(budget_metrics.fichiers_exclus_budget > 0
                        or budget_metrics.fichiers_exclus_trop_grands > 0),
        budget_metrics={
            "candidats_total": budget_metrics.candidats_total,
            "candidats_classes": budget_metrics.candidats_classes,
            "fichiers_selectionnes": budget_metrics.fichiers_selectionnes,
            "fichiers_exclus_budget": budget_metrics.fichiers_exclus_budget,
            "fichiers_exclus_trop_grands": budget_metrics.fichiers_exclus_trop_grands,
            "chars_selectionnes": budget_metrics.chars_selectionnes,
            "budget_files": budget_metrics.budget_files,
            "budget_chars": budget_metrics.budget_chars,
        },
    )


def is_stale(context: MissionContext, target: ProjectTarget) -> StalenessReport:
    """
    Vérifie si le contexte est périmé par rapport à l'état courant de la
    cible. CONTEXT_STALE si un SHA (texte ou octets) ou le HEAD diverge.
    """
    return check_staleness(
        context.file_versions(),
        target.git_root,
        target.head_full,
    )
