"""
MemoLibDev — LLM CONTROLLED v1 : LLM Planner (sous-étape ANALYZE/PLAN)
=====================================================================

Orchestration fail-closed de la dérivation d'un `intent` à partir d'un
`MissionContext`, via un AIProvider. Le planner NE DÉCIDE RIEN et
N'APPLIQUE RIEN : il transforme (contexte -> intent) et VALIDE que la
sortie du LLM n'outrepasse pas la frontière de contrôle.

HIÉRARCHIE D'AUTORITÉ (R2 — verrouillage explicite) :
    La vérification `target_path ∈ context.authority_sources()` effectuée
    ici n'est qu'un **PRÉ-FILTRE** non-autoritaire, destiné à rejeter au
    plus tôt une proposition LLM manifestement hors sujet. Elle ne CONFÈRE
    aucune autorité et ne REMPLACE aucun contrôle.

    L'autorité RÉELLE de cible / scope / version reste, dans l'ordre :
      1. D6.1  `resolve_file_target()`  -> cible/scope/kind/version réels,
         fail-closed (hors périmètre / .git / absent -> FileTargetError) ;
      2. D5.8  `authorize()`            -> scope déterministe, concordance
         de chemin (evidence/provenance/action), intégrité SHA, approbation ;
      3. D5.8  `enforce_write_guardrail()` -> diff borné à authorization.path ;
      4. D5.9  pre_apply                -> target binding + evidence SHA +
         scope + git apply --check.

    Défense en profondeur : MÊME si ce pré-filtre était contourné ou
    neutralisé, un `target_path` incohérent serait bloqué par D6.1 puis
    D5.8 en aval. Le LLM n'est JAMAIS l'autorité finale de cible/scope.
    (Prouvé par test_r2_authority_hierarchy.py.)

Pipeline :
    MissionContext
       -> SecretScanner (SAFE requis, sinon BLOCK)
       -> provider.analyze_plan() -> LLMPlan | None (None => BLOCK)
       -> validation stricte :
            * provider disponible
            * confidentialité : HIGH/CRITICAL => provider LOCAL only
            * target_path ∈ context.authority_sources()
            * target_path hors control-plane
            * intent REPLACE strict : forme valide ET `old` réellement
              présent dans le contenu de la cible (R1 : jamais d'APPEND
              silencieux masquant un intent incohérent)
       -> PlannerResult(status=OK|BLOCK, intent, target_path, reason)

Le résultat alimente ENSUITE la chaîne D6.0 inchangée (code_adapter.plan
-> validate -> D5.8 -> CONTEXT_STALE -> D5.9). Le LLM ne devient jamais
une autorité : tout est re-vérifié en aval.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from llm.secret_scanner import scan_context
from llm.ai_provider import AIProvider, LLMPlan, ProviderLocality


# Fichiers control-plane (miroir de agent_loop.CONTROL_PLANE_FILES, pour
# bloquer AU PLUS TÔT côté planner ; l'Agent Loop re-bloque de toute façon).
_CONTROL_PLANE = frozenset({
    "coder_authorization.py", "controlled_coder.py", "d59_controlled_apply.py",
    "project_target.py", "evidence_resolver_v2_2.py", "evidence_resolver_v2.py",
    "import_provenance.py", "file_target.py", "code_adapter.py",
    "agent_loop.py", "SPEC-D6.0.md",
})

_HIGH_RISK = {"HIGH", "CRITICAL"}


@dataclass(frozen=True)
class PlannerResult:
    status: str                 # OK | BLOCK
    intent: Optional[str]
    target_path: Optional[str]
    rationale: Optional[str]
    reason: str

    @property
    def ok(self) -> bool:
        return self.status == "OK"


def _normalize(path: str) -> str:
    """
    Normalise un chemin pour comparaison/lecture, SANS casser les dotfiles.

    Correctif : `str.lstrip("./")` retirait TOUT caractère '.' ou '/' en
    tête, transformant ".vscode/x" en "vscode/x" (fichier introuvable ->
    faux BLOCK). On ne retire désormais QUE le préfixe "./" (ou ".\\")
    littéral, en préservant un '.' de dotfile.
    """
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _parse_replace_intent(intent: str) -> Optional[tuple[str, str]]:
    """
    Parse strict d'un intent REPLACE:old:new.
    Retourne (old, new) si la FORME est valide, sinon None.
    Forme valide = préfixe REPLACE: + exactement 3 segments + old non vide.
    (Le `new` peut être vide ; c'est `old` qui pilote la localisation.)
    """
    if not intent or not intent.strip():
        return None
    if not intent.startswith("REPLACE:"):
        return None
    parts = intent.split(":", 2)
    if len(parts) != 3:
        return None
    _, old_frag, new_frag = parts
    if not old_frag:
        return None
    return old_frag, new_frag


def _read_target_content(git_root: str, target_path: str) -> Optional[str]:
    """
    Lit le contenu RÉEL du fichier cible, confiné au git_root du contexte.

    IMPORTANT (R1) : ceci N'INTRODUIT PAS une nouvelle source d'autorité.
    On relit exactement le fichier que le Context Builder/FileTarget a déjà
    autorisé (même git_root, même chemin relatif), uniquement pour vérifier
    de façon déterministe que `old` existe réellement. Aucune écriture.
    Retourne None si le fichier est hors périmètre ou absent (fail-closed).
    """
    if not git_root:
        return None
    root = Path(git_root).resolve()
    candidate = (root / target_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if ".git" in candidate.parts:
        return None
    if not candidate.is_file():
        return None
    try:
        return candidate.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def derive_intent(context, provider: AIProvider,
                  *, timeout_s: Optional[float] = None) -> PlannerResult:
    """
    Dérive un intent depuis le contexte via le provider, fail-closed.

    timeout_s :
      - None  : appel provider in-process (comportement historique).
      - > 0   : appel ISOLÉ dans un process, borné par timeout_s, réellement
                interruptible (R4). TIMEOUT/ERROR -> BLOCK, sans exécution
                fantôme (le process enfant est terminé).
    """
    # 1. Provider disponible ?
    if not provider.available:
        return PlannerResult("BLOCK", None, None, None,
                             "LLM: provider indisponible")

    # 2. Secret scan AVANT tout appel provider.
    scan = scan_context(context)
    if not scan.safe:
        kinds = sorted({h.kind for h in scan.hits})
        return PlannerResult("BLOCK", None, None, None,
                             f"LLM: secret détecté dans le contexte ({kinds}) "
                             f"-> non transmis au provider")

    # 3. Confidentialité : HIGH/CRITICAL => provider LOCAL uniquement.
    if context.risk_level in _HIGH_RISK and provider.locality != ProviderLocality.LOCAL:
        return PlannerResult("BLOCK", None, None, None,
                             f"LLM: risk={context.risk_level} exige un provider "
                             f"LOCAL (provider={provider.locality})")

    # 4. Appel provider — borné par timeout si demandé (R4).
    #    timeout_s is None  -> appel in-process (comportement historique).
    #    timeout_s > 0       -> appel ISOLÉ dans un process, réellement
    #                           interruptible (pas d'exécution fantôme).
    #    Fail-closed : TIMEOUT ou ERROR -> plan None -> BLOCK.
    if timeout_s is None:
        plan: Optional[LLMPlan] = provider.analyze_plan(context)
    else:
        from llm.provider_timeout import call_provider_with_timeout
        outcome = call_provider_with_timeout(provider, context, timeout_s)
        if outcome.status == "TIMEOUT":
            return PlannerResult("BLOCK", None, None, None,
                                 f"LLM: {outcome.reason}")
        if outcome.status == "ERROR":
            return PlannerResult("BLOCK", None, None, None,
                                 f"LLM: appel provider échoué: {outcome.reason}")
        plan = outcome.plan

    if plan is None:
        return PlannerResult("BLOCK", None, None, None,
                             "LLM: réponse vide / provider sans plan")

    # 5. PRÉ-FILTRE non-autoritaire (R2) : target_path dans les sources
    #    d'autorité du contexte. Ceci rejette au plus tôt une proposition
    #    hors sujet, mais ne CONFÈRE aucune autorité : D6.1 (resolve_file_
    #    target) puis D5.8 (authorize/guardrail) restent l'autorité réelle
    #    de cible/scope/version en aval, même si ce pré-filtre était contourné.
    allowed = {_normalize(p) for p in context.authority_sources()}
    tp = _normalize(plan.target_path)
    if tp not in allowed:
        return PlannerResult("BLOCK", None, None, None,
                             f"LLM: target_path hors authority_sources: "
                             f"{plan.target_path}")

    # 6. Control-plane interdit.
    basename = tp.rsplit("/", 1)[-1]
    if basename in _CONTROL_PLANE or tp in _CONTROL_PLANE:
        return PlannerResult("BLOCK", None, None, None,
                             f"LLM: target_path control-plane interdit: {tp}")

    # 7. Format d'intent STRICT + présence réelle de `old` dans la cible.
    #    (R1) Un REPLACE:old:new dont `old` est absent du contenu RÉEL de
    #    la cible serait transformé silencieusement en APPEND par
    #    code_adapter.plan() -> comportement sémantiquement faux. On le
    #    BLOQUE au niveau planner, de façon déterministe, SANS modifier
    #    code_adapter et SANS introduire de nouvelle source d'autorité.
    parsed = _parse_replace_intent(plan.intent)
    if parsed is None:
        return PlannerResult("BLOCK", None, None, None,
                             f"LLM: intent invalide / non parsable: "
                             f"{plan.intent!r}")
    old_frag, _new_frag = parsed

    git_root = getattr(getattr(context, "project", None), "git_root", "")
    content = _read_target_content(git_root, tp)
    if content is None:
        return PlannerResult("BLOCK", None, None, None,
                             f"LLM: contenu cible illisible/hors périmètre: {tp}")

    if old_frag not in content:
        return PlannerResult("BLOCK", None, None, None,
                             f"LLM: fragment 'old' absent du contenu réel de "
                             f"la cible (évite un APPEND silencieux): "
                             f"{old_frag[:50]!r}")

    return PlannerResult("OK", plan.intent, tp, plan.rationale,
                         "LLM plan validé (intent dérivé, 'old' présent, "
                         "non-autorité)")
