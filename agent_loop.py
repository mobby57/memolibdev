"""
MemoLibDev — D6.0 : Agent Loop (orchestration pure)
===================================================

Système nerveux de MemoLibDev. Orchestre les composants D5/D6 déjà
construits et prouvés, en une boucle fail-closed, SANS jamais recréer
ni contourner un garde-fou.

Principe fondateur (SPEC-D6.0) :
    L'intelligence appartient à l'IA. L'autorité appartient à l'humain.
    CAPACITÉ ≠ AUTORISATION ≠ APPLICATION.

Règle architecturale absolue (exigée) :
    Agent Loop DEMANDE les contrôles ; il n'en POSSÈDE aucun.
      - pas de scope propre        -> celui du certificat D5.8
      - pas de SHA propre          -> evidence_sha256 du certificat / D5.9
      - pas de snapshot/rollback   -> D5.9 (run_controlled_apply)
      - pas d'autorisation propre  -> coder_authorization.authorize()
      - pas d'apply propre         -> D5.9 écrit, jamais l'agent
    Cette classe ne contient AUCUN git apply, AUCUNE écriture disque.

Portée v1 (SPEC §7, ne pas dépasser) :
  1. Orchestrer les 11 étapes §4 dans l'ordre.
  2. Appeler UNIQUEMENT les composants réels du §0.
  3. Machine à états §3 : BLOCK / ABORT non rattrapables.
  4. Point d'injection humain UNIQUE en 4.6 (APPROVAL).
  5. Rapport immuable §4.11.
  6. Cible = sandbox éphémère ; VERIFY léger uniquement.

Hors v1 : VERIFY complet npm, multi-fichiers, risk engine calculé,
agents spécialisés, API. (Niveaux ultérieurs.)
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Optional
import hashlib

# --- Composants réels orchestrés (SPEC §0). Aucune réimplémentation. ---
from project_target import ProjectTarget

from file_target import resolve_file_target, FileTarget, FileTargetError
import code_adapter

from coder_authorization import (
    authorize,
    AuthorizationStatus,
    ActionDossier,
    HumanApproval,
)
from controlled_coder import (
    enforce_coder_authorization,
    enforce_write_guardrail,
)
from d59_controlled_apply import (
    ApplyCertificate,
    run_controlled_apply,
    sha256_file,
)


# ------------------------------------------------------------------
# États de la boucle (SPEC §3)
# ------------------------------------------------------------------

class LoopState:
    CONTINUE = "CONTINUE"
    BLOCK = "BLOCK"
    ABORT = "ABORT"
    AWAIT_HUMAN = "AWAIT_HUMAN"


# Verdicts terminaux de mission (SPEC §4.11).
TERMINAL_STATES = {
    "APPLIED",            # appliqué au working tree, NON commité
    "ROLLED_BACK",
    "BLOCKED",
    "ABORTED",
    "NO_PATCH_POSSIBLE",
    "AWAIT_HUMAN",
    "ROLLBACK_FAILED",    # incident majeur
}


# Fichiers du Control Plane — NEVER_ALLOW_AGENT (SPEC §6).
# L'agent ne peut JAMAIS proposer/appliquer un changement les touchant.
CONTROL_PLANE_FILES = frozenset({
    "coder_authorization.py",
    "controlled_coder.py",
    "d59_controlled_apply.py",
    "project_target.py",
    "evidence_resolver_v2_2.py",
    "evidence_resolver_v2.py",
    "import_provenance.py",
    "file_target.py",
    "code_adapter.py",
    "agent_loop.py",
    "SPEC-D6.0.md",
})


class AgentLoopError(RuntimeError):
    """Erreur d'orchestration (fail-closed)."""


# ------------------------------------------------------------------
# Rapport immuable (SPEC §4.11)
# ------------------------------------------------------------------

@dataclass(frozen=True)
class StepRecord:
    """Trace d'une étape : nom, verdict de boucle, détail."""
    step: str
    loop_state: str
    detail: str


@dataclass(frozen=True)
class AgentReport:
    """
    Rapport final immuable (frozen). Jamais `COMMITTED`, jamais `PUSHED`,
    jamais `PRODUCTION`.
    """
    final_state: str
    request_text: str
    target_fingerprint: str
    scope: Optional[str]
    steps: tuple[StepRecord, ...]
    apply_status: Optional[str]
    rolled_back: bool
    committed: bool
    pushed: bool
    reason: str
    # V0.3 : TRANSPORT de la proposition descriptive déjà produite en §4.7
    # (plan + new_content + diff). ADDITIF, défaut None : aucun rapport
    # existant ne change de forme, aucune des 27 épreuves D6.0 n'est touchée.
    # None quand aucun diff n'a été réellement produit (analyse, blocage
    # amont, no-patch). JAMAIS fabriqué.
    proposal: Optional[object] = None      # proposal.Proposal | None

    def to_dict(self) -> dict:
        return {
            "final_state": self.final_state,
            "request": self.request_text,
            "target_fingerprint": self.target_fingerprint,
            "scope": self.scope,
            "steps": [
                {"step": s.step, "state": s.loop_state, "detail": s.detail}
                for s in self.steps
            ],
            "apply_status": self.apply_status,
            "rolled_back": self.rolled_back,
            "committed": self.committed,
            "pushed": self.pushed,
            "reason": self.reason,
            # Sérialisation descriptive de la proposition (ou None).
            "proposal": (self.proposal.to_dict()
                         if self.proposal is not None
                         and hasattr(self.proposal, "to_dict")
                         else None),
        }


# ------------------------------------------------------------------
# Entrées de mission
# ------------------------------------------------------------------

@dataclass(frozen=True)
class Mission:
    """
    Entrée de la boucle. `human_approval` et `action` ne sont PAS
    fabriqués par l'agent : ils proviennent d'une décision humaine
    (APPROVAL, §4.6). Si `human_approval` est None, la boucle s'arrête
    en AWAIT_HUMAN avant toute écriture.
    """
    request_text: str
    target: ProjectTarget
    relative_path: str                 # fichier visé par la mission
    intent: str                        # intention (format code_adapter)
    risk_level: str = "MEDIUM"
    action: Optional[ActionDossier] = None
    human_approval: Optional[HumanApproval] = None


# ------------------------------------------------------------------
# L'orchestrateur
# ------------------------------------------------------------------

class AgentLoop:
    """
    Orchestration pure des 11 étapes §4. Ne possède aucun garde-fou :
    il appelle ceux de D5/D6. La seule logique propre est la machine à
    états (ordre, BLOCK/ABORT non rattrapables) et le passage de données.
    """

    def __init__(self, mission: Mission, verify: Callable[[Path], tuple[bool, str]],
                 *, mission_context=None):
        self.mission = mission
        self.verify = verify
        # Contexte optionnel (D6.0.1). Si fourni, un re-check CONTEXT_STALE
        # est effectué JUSTE AVANT l'apply D5.9. Absent (None) => comportement
        # D6.0 v1 inchangé (non-régression des 27 tests).
        self.mission_context = mission_context
        self._steps: list[StepRecord] = []
        self._scope: Optional[str] = None
        # V0.3 : proposition descriptive produite en §4.7 (ou None). Elle
        # n'est QU'un transport : la poser ici n'écrit rien et n'autorise
        # rien. Remplie uniquement quand un diff RÉEL existe.
        self._proposal: Optional[object] = None

    # -- helpers de machine à états ---------------------------------

    def _record(self, step: str, state: str, detail: str = "") -> None:
        self._steps.append(StepRecord(step=step, loop_state=state, detail=detail))

    def _terminate(self, final_state: str, reason: str,
                   apply_status: Optional[str] = None,
                   rolled_back: bool = False,
                   committed: bool = False,
                   pushed: bool = False) -> AgentReport:
        return AgentReport(
            final_state=final_state,
            request_text=self.mission.request_text,
            target_fingerprint=self.mission.target.fingerprint,
            scope=self._scope,
            steps=tuple(self._steps),
            apply_status=apply_status,
            rolled_back=rolled_back,
            committed=committed,
            pushed=pushed,
            reason=reason,
            proposal=self._proposal,
        )

    # -- la boucle ---------------------------------------------------

    def run(self) -> AgentReport:
        """
        Exécute la machine à états. Un BLOCK/ABORT n'est jamais rattrapé :
        dès qu'un verdict négatif tombe, on termine.
        """
        m = self.mission

        # ----- 4.1 REQUEST (L1) -----
        # La cible est déjà résolue (invariant 1 : une seule fois, en amont).
        if m.target is None:
            self._record("REQUEST", LoopState.ABORT, "cible non résolue")
            return self._terminate("ABORTED", "REQUEST: cible non résolue (invariant 1)")
        if not m.request_text.strip():
            self._record("REQUEST", LoopState.BLOCK, "requête vide")
            return self._terminate("BLOCKED", "REQUEST: requête vide")
        self._record("REQUEST", LoopState.CONTINUE,
                     f"target={m.target.fingerprint}")

        # ----- 4.2 DECISION (L1->L2) -----
        # Invariant global §6 prime : refuser toute cible control-plane
        # AVANT toute autre étape. (NEVER_ALLOW_AGENT.)
        normalized = m.relative_path.replace("\\", "/").lstrip("./")
        basename = normalized.rsplit("/", 1)[-1]
        if basename in CONTROL_PLANE_FILES or normalized in CONTROL_PLANE_FILES:
            self._record("DECISION", LoopState.BLOCK,
                         f"control-plane interdit: {normalized}")
            return self._terminate(
                "BLOCKED",
                f"DECISION: cible control-plane interdite (SPEC §6): {normalized}",
            )
        self._record("DECISION", LoopState.CONTINUE, "intention recevable")

        # ----- 4.3 PLAN (L3) + résolution FileTarget (D6.1) -----
        # Le scope naît ICI du FileTarget, mais il sera VERROUILLÉ par le
        # certificat D5.8 en 4.6. L'agent ne l'élargit jamais ensuite.
        try:
            file_target: FileTarget = resolve_file_target(
                m.relative_path, m.target, risk_level=m.risk_level,
            )
        except FileTargetError as exc:
            self._record("PLAN", LoopState.BLOCK, f"FileTarget: {exc}")
            return self._terminate("BLOCKED", f"PLAN: {exc}")

        if not file_target.is_textual or file_target.kind not in code_adapter.ACCEPTED_KINDS:
            self._record("PLAN", LoopState.BLOCK,
                         f"non adaptable v1: kind={file_target.kind}")
            return self._terminate(
                "BLOCKED",
                f"PLAN: fichier non adaptable par code_adapter v1 (kind={file_target.kind})",
            )
        self._scope = file_target.scope
        self._record("PLAN", LoopState.CONTINUE, f"scope={file_target.scope}")

        # ----- 4.4 EVIDENCE (L3) -----
        # L'intégrité de preuve est portée par le SHA du contenu courant.
        # D5.9 revérifiera evidence_sha256 == SHA actuel (continuité §4).
        try:
            current_content = code_adapter.read(file_target)
        except code_adapter.CodeAdapterError as exc:
            self._record("EVIDENCE", LoopState.BLOCK, f"read: {exc}")
            return self._terminate("BLOCKED", f"EVIDENCE: {exc}")
        # Deux conventions de SHA coexistent dans la pile et ne sont PAS
        # fusionnables :
        #   - D5.6 authorize()/validate_record : SHA du TEXTE
        #     (content_sha256 = sha256 de read_text("utf-8")).
        #   - D5.9 ApplyCertificate/pre_apply : SHA des OCTETS (sha256_file).
        # On calcule les deux séparément et on alimente chaque contrat
        # avec le sien. Les mélanger ferait échouer soit authorize soit
        # pre_apply dès qu'octets != texte (CRLF, BOM, non-UTF8).
        from evidence_resolver_v2_2 import content_sha256 as _text_sha
        evidence_text_sha = _text_sha(current_content)       # pour D5.6
        evidence_byte_sha = sha256_file(                     # pour D5.9
            m.target.git_root / file_target.path
        )
        self._record("EVIDENCE", LoopState.CONTINUE,
                     f"text_sha={evidence_text_sha[:12]} byte_sha={evidence_byte_sha[:12]}")

        # ----- 4.5 PROVENANCE (L3) -----
        # v1 : la cible EST le fichier du scope (auto-provenance triviale).
        # On ne fabrique pas de fausse provenance ; on constate que le
        # fichier existe dans la cible et est le scope autorisé.
        self._record("PROVENANCE", LoopState.CONTINUE,
                     f"resolved_path={file_target.path}")

        # ----- 4.7 CODER (L4) : adapter produit la proposition -----
        # Produite AVANT 4.6 pour que l'humain approuve une proposition
        # concrète (diff). Mais AUCUN apply tant que l'autorité L6 manque.
        code_plan = code_adapter.plan(current_content, m.intent, file_target.path)
        new_content = code_adapter.modify(current_content, code_plan)  # mémoire
        valid, vreason = code_adapter.validate(current_content, new_content)
        if not valid:
            self._record("CODER", LoopState.BLOCK, f"validate: {vreason}")
            return self._terminate("BLOCKED", f"CODER: {vreason}")
        diff = code_adapter.generate_diff_git(
            m.target.git_root, file_target.path, new_content,
        )
        if not diff.strip():
            self._record("CODER", LoopState.CONTINUE, "NO_PATCH_POSSIBLE")
            return self._terminate("NO_PATCH_POSSIBLE", "CODER: aucun diff produit")
        self._record("CODER", LoopState.CONTINUE, f"diff={len(diff)} chars")

        # ----- V0.3 : TRANSPORT de la proposition (descriptif, additif) -----
        # On projette les artefacts RÉELS déjà calculés (code_plan, diff,
        # contenu courant, SHA texte, scope du FileTarget, risk de la
        # mission) en une Proposal. AUCUNE écriture, AUCUN appel D5.8/D5.9,
        # AUCUN recalcul de diff : on transporte le diff du Core tel quel.
        # `reversible` n'est renseigné QUE si une ActionDossier réelle le
        # porte ; sinon None (jamais fabriqué). Cela ne modifie EN RIEN la
        # machine à états : c'est une capture passive avant 4.6.
        from proposal import build_proposal as _build_proposal

        # ----- V0.3.1 : CONFIANCE PROPOSITION (déterministe, via engine) -----
        # Signaux RÉELS, aucun LLM, aucune taille/volume :
        #   - has_diff/diff_valid : du Core (diff + code_adapter.validate) ;
        #   - diff_deterministic  : generate_diff_git est déterministe (git) ;
        #   - scope_verifiable    : le FileTarget porte un scope résolu ;
        #   - causal_evidence     : le plan contient un changement LOCALISÉ
        #     (REPLACE avec old_fragment réellement trouvé) et non un simple
        #     APPEND de repli ; preuve d'un point d'ancrage réel ;
        #   - has_fresh_sha/is_stale : fraîcheur du contexte si fourni.
        from confidence_engine import score_proposal as _score_proposal
        _changes = getattr(code_plan, "changes", ()) or ()
        _causal = any(getattr(c, "action", "") == "REPLACE"
                      and getattr(c, "old_fragment", "")
                      for c in _changes)
        _stale = False
        _fresh_sha = True
        if self.mission_context is not None:
            try:
                from context.context_builder import is_stale as _is_stale2
                _stale = bool(_is_stale2(self.mission_context, m.target).stale)
            except Exception:
                _stale = False
            _fresh_sha = not _stale
        _conf = _score_proposal(
            has_diff=bool(diff and diff.strip()),
            diff_valid=bool(valid),
            diff_deterministic=True,
            scope_verifiable=bool(file_target.scope),
            has_fresh_sha=_fresh_sha,
            is_stale=_stale,
            causal_evidence=_causal,
            contradiction=False,
        )

        # V0.4.1 : identité immuable de la proposition. Dérivée des octets
        # EXACTS du diff + cible + path + mission, pour qu'une proposition au
        # contenu/périmètre différent produise un proposal_id différent (une
        # nouvelle proposition => une nouvelle décision humaine).
        from coder_authorization import diff_sha256 as _diff_sha256
        _diff_sha = _diff_sha256(diff)
        import hashlib as _hl
        _pid_src = (f"{m.target.fingerprint}|{m.target.head_full}|"
                    f"{file_target.path}|{m.request_text}|{_diff_sha}")
        _proposal_id = "P-" + _hl.sha256(_pid_src.encode("utf-8")).hexdigest()[:24]

        self._proposal = _build_proposal(
            mission_id=None,
            request_text=m.request_text,
            reason=None,                         # non fabriqué ici
            code_plan=code_plan,
            diff=diff,                           # diff RÉEL du Core, tel quel
            current_content=current_content,
            file_target=file_target,
            sha_before=evidence_text_sha,        # SHA RÉEL (texte)
            risk=m.risk_level,                   # risk réel de la mission
            reversible=(getattr(m.action, "reversibility", None) is not None
                        and str(getattr(m.action, "reversibility", "")).upper()
                        .startswith("REVERSIBLE")) if m.action is not None else None,
            confidence=_conf.level,              # HIGH|MEDIUM|LOW du moteur
            confidence_reasons=_conf.reasons,
            confidence_evidence=_conf.evidence_used,
            confidence_gates=_conf.gates,
            proposal_id=_proposal_id,
        )

        # ----- 4.6 APPROVAL (L6, HUMAIN OBLIGATOIRE) -----
        # L'agent NE PEUT PAS fabriquer human_approval.approved=True.
        # Il reçoit l'approbation ; sinon AWAIT_HUMAN (arrêt propre).
        if m.human_approval is None or m.action is None:
            self._record("APPROVAL", LoopState.AWAIT_HUMAN, "approbation requise")
            return self._terminate("AWAIT_HUMAN", "APPROVAL: décision humaine requise (L6)")

        # Le certificat D5.8 est la SEULE source d'autorité. L'agent ne
        # calcule pas lui-même l'autorisation : il la DEMANDE.
        authorization = authorize(
            target=m.target,
            evidence=_evidence_record_for(file_target, current_content,
                                          m.target, evidence_text_sha),
            evidence_result=_accepted_result(file_target, current_content),
            provenance=_resolved_provenance(file_target),
            allowed_paths=[file_target.scope],   # scope du FileTarget
            action=m.action,
            human_approval=m.human_approval,
        )
        if authorization.status != AuthorizationStatus.AUTHORIZED.value:
            self._record("APPROVAL", LoopState.BLOCK,
                         f"authorize REJECTED: {authorization.reason}")
            return self._terminate("BLOCKED", f"APPROVAL: {authorization.reason}")
        self._record("APPROVAL", LoopState.CONTINUE, "AUTHORIZED (L6)")

        # ----- 4.8 D5.8 GATES (L4->L5) -----
        # Scope IMMUABLE : on réutilise EXACTEMENT authorization.path, le
        # scope du certificat — jamais une valeur de l'agent.
        allowed_paths = [authorization.path]

        gate_auth = enforce_coder_authorization(authorization, m.target, allowed_paths)
        if gate_auth["verdict"] != "AUTHORIZED":
            self._record("D5.8_GATES", LoopState.BLOCK,
                         f"enforce_coder_authorization: {gate_auth['reason']}")
            return self._terminate("BLOCKED", f"D5.8: {gate_auth['reason']}")

        gate_scope = enforce_write_guardrail(diff, allowed_paths)
        if gate_scope["verdict"] != "ACCEPTABLE":
            self._record("D5.8_GATES", LoopState.BLOCK,
                         f"write_guardrail hors scope: {gate_scope.get('out_of_scope_files')}")
            return self._terminate(
                "BLOCKED",
                f"D5.8: diff hors scope {gate_scope.get('out_of_scope_files')}",
            )
        self._record("D5.8_GATES", LoopState.CONTINUE, "gates AUTHORIZED+ACCEPTABLE")

        # ----- 4.8bis V0.4.2 : BINDING DU DIFF APPROUVÉ — OBLIGATOIRE -----
        # Lie la décision humaine aux OCTETS EXACTS du `diff` qui sera
        # consommé par D5.9 en §4.9 (MÊME variable `diff`, non recopiée, non
        # recalculée). Ce point n'est atteint que sur le CHEMIN D'APPLICATION
        # (human_approval ET action présents : §4.6 a laissé passer).
        #
        # V0.4.2 — FAIL-CLOSED SANS RÉTROCOMPATIBILITÉ :
        #   - le binding est EXIGÉ sur tout chemin pouvant aboutir à une
        #     application. Une approbation « legacy » sans expected_diff_sha256
        #     ou sans proposal_id est REFUSÉE AVANT la frontière D5.9 ;
        #   - le drapeau REQUIRE_DIFF_BINDING (coder_authorization) est à True
        #     par défaut ; s'il est désactivé, l'application est BLOQUÉE (jamais
        #     un contournement : une config qui désactive le binding bloque) ;
        #   - le hash des octets exacts du diff ET le proposal_id DOIVENT
        #     correspondre à la proposition réellement produite ici. Tout écart
        #     (un seul octet, proposal_id différent, mission/scope/cible/source
        #     différents via diff/SHA) -> BLOCK, aucune écriture.
        # D5.9 n'est pas modifié : la garantie tient parce que le binding est
        # vérifié sur le MÊME `diff` ensuite passé à run_controlled_apply(...).
        from coder_authorization import (
            verify_diff_binding, REQUIRE_DIFF_BINDING,
        )
        if not REQUIRE_DIFF_BINDING:
            # Fail-closed : désactiver le binding ne doit JAMAIS laisser
            # appliquer un patch non lié. On BLOQUE l'application.
            self._record("DIFF_BINDING", LoopState.BLOCK,
                         "REQUIRE_DIFF_BINDING désactivé -> application bloquée")
            return self._terminate(
                "BLOCKED",
                "V0.4.2 binding: REQUIRE_DIFF_BINDING désactivé — application "
                "interdite (binding obligatoire, aucun contournement).",
            )
        if not getattr(m.human_approval, "expected_diff_sha256", None) \
                or not getattr(m.human_approval, "proposal_id", None):
            # Approbation legacy / incomplète : REFUS avant application.
            self._record("DIFF_BINDING", LoopState.BLOCK,
                         "approbation sans binding (expected_diff_sha256/"
                         "proposal_id) -> refus avant application")
            return self._terminate(
                "BLOCKED",
                "V0.4.2 binding obligatoire: approbation non liée au diff "
                "(expected_diff_sha256/proposal_id manquant) — nouvelle "
                "décision humaine liée requise.",
            )
        bind_ok, bind_reason = verify_diff_binding(
            m.human_approval, diff,
            expected_proposal_id=getattr(self._proposal, "proposal_id", None),
        )
        if not bind_ok:
            self._record("DIFF_BINDING", LoopState.BLOCK, bind_reason)
            return self._terminate(
                "BLOCKED",
                f"V0.4.2 binding: {bind_reason} "
                f"(nouvelle décision humaine requise)",
            )
        self._record("DIFF_BINDING", LoopState.CONTINUE,
                     "diff lié à la décision humaine (octets exacts, obligatoire)")

        # ----- 4.8ter V0.4.4-A : EXPIRATION (TTL) — DERNIER POINT DE CONTRÔLE -
        # Vérifie, JUSTE AVANT l'application D5.9, que l'approbation liée n'a
        # pas expiré. Fail-closed : date absente/invalide, futur incohérent,
        # expiration indéterminable (TTL config invalide), ou expirée -> BLOCK.
        # Ce contrôle est effectué ICI (frontière d'application) et NON à la
        # présentation de la proposition : le temps écoulé entre approbation et
        # application est donc pris en compte. Source de temps = horloge
        # système UTC (limites documentées dans coder_authorization).
        from coder_authorization import verify_approval_freshness
        ttl_ok, ttl_reason = verify_approval_freshness(m.human_approval)
        if not ttl_ok:
            self._record("APPROVAL_TTL", LoopState.BLOCK, ttl_reason)
            return self._terminate(
                "BLOCKED",
                f"V0.4.4-A TTL: {ttl_reason}",
            )
        self._record("APPROVAL_TTL", LoopState.CONTINUE, ttl_reason)

        # ----- CONTEXT re-check (D6.0.1) : CONTEXT_STALE -> BLOCK -----
        # Si un contexte a été fourni, on vérifie JUSTE AVANT l'apply que
        # rien n'a dérivé depuis sa construction (SHA texte/octets + HEAD).
        # Toute dérive -> BLOCK, aucune écriture, réinspection requise.
        # Ce re-check NE DUPLIQUE PAS D5.9 : il interroge is_stale() de
        # D6.0.1 (versionnement), pas une logique de sécurité propre.
        if self.mission_context is not None:
            from context.context_builder import is_stale as _is_stale
            staleness = _is_stale(self.mission_context, m.target)
            if staleness.stale:
                self._record("CONTEXT_RECHECK", LoopState.BLOCK, staleness.reason)
                return self._terminate(
                    "BLOCKED",
                    f"CONTEXT_STALE avant apply: {staleness.reason} "
                    f"(réinspection requise)",
                )
            self._record("CONTEXT_RECHECK", LoopState.CONTINUE, "CONTEXT_FRESH")

        # ----- 4.9 D5.9 APPLY (L6) + 4.10 VERIFY léger -----
        # D5.9 est le SEUL à écrire. Il refait pre_apply (target binding +
        # evidence SHA + scope + git apply --check) -> snapshot -> apply ->
        # verify -> APPLIED | ROLLBACK. L'agent ne duplique rien.
        certificate = ApplyCertificate(
            path=authorization.path,
            status="AUTHORIZED",
            evidence_sha256=evidence_byte_sha,
            target_git_root=str(m.target.git_root),
            target_head=m.target.head_full,
            target_fingerprint=m.target.fingerprint,
        )
        result = run_controlled_apply(
            m.target.git_root,
            certificate,
            diff,
            target_head=m.target.head_full,
            target_fingerprint=m.target.fingerprint,
            verify=self.verify,          # VERIFY léger fourni par l'appelant
        )

        # Invariant 6 : jamais commit/push/production. D5.9 le garantit ;
        # on le re-vérifie fail-closed côté orchestrateur.
        if result.committed or result.pushed:
            self._record("D5.9_APPLY", LoopState.ABORT, "commit/push détecté")
            return self._terminate("ABORTED",
                                   "INVARIANT 6 violé: commit/push détecté",
                                   apply_status=result.status)

        self._record("D5.9_APPLY", LoopState.CONTINUE, f"apply={result.status}")
        self._record("VERIFY", LoopState.CONTINUE, result.reason)

        # ----- 4.11 RESULT -----
        return self._terminate(
            final_state=result.status,       # APPLIED | ROLLED_BACK | BLOCKED | ...
            reason=result.reason,
            apply_status=result.status,
            rolled_back=result.rolled_back,
            committed=result.committed,      # False (D5.9)
            pushed=result.pushed,            # False (D5.9)
        )


# ------------------------------------------------------------------
# Adaptateurs vers les contrats D5.6 (pas de logique de sécurité ici :
# on construit les objets d'ENTRÉE que authorize() va VÉRIFIER).
# ------------------------------------------------------------------

def _evidence_record_for(ft: FileTarget, content: str, target: ProjectTarget,
                         sha: str):
    """Projette un FileTarget en EvidenceRecord (contrat D5.4/D5.6)."""
    from evidence_resolver_v2_2 import EvidenceRecord
    return EvidenceRecord(
        path=ft.path,
        normalized_path=ft.path,
        git_root=str(target.git_root),
        head=target.head_full,
        repository_fingerprint=target.fingerprint,
        content_sha256=sha,
        size=len(content.encode("utf-8")),
        content=content,
    )


def _accepted_result(ft: FileTarget, content: str):
    """
    EvidenceResult ACCEPTED pour le fichier du scope. En v1 le scope EST
    le fichier : la preuve de déclaration est l'existence du fichier
    autorisé. authorize() revérifiera la concordance de chemin et le SHA.
    """
    from evidence_resolver_v2_2 import EvidenceResult, EvidenceStatus
    return EvidenceResult(
        status=EvidenceStatus.ACCEPTED,
        query=ft.path,
        path=ft.path,
        line_start=1,
        line_end=max(1, content.count("\n") + 1),
        evidence=content,
        score=100,
        reason="Scope file present and bound to target",
    )


def _resolved_provenance(ft: FileTarget):
    """
    ProvenanceResult RESOLVED vers le fichier lui-même. v1 : auto-
    provenance (le scope est sa propre source). authorize() exige
    resolved_path == fichier cible, ce qui est satisfait trivialement.
    """
    from import_provenance import ProvenanceResult, ProvenanceStatus
    return ProvenanceResult(
        status=ProvenanceStatus.RESOLVED,
        source_path=ft.path,
        symbol=ft.path,
        module_specifier=ft.path,
        resolved_path=ft.path,
        reason="v1 self-provenance within scope",
    )



# ------------------------------------------------------------------
# Point d'entrée CONTEXT-AWARE (Phase 2) : INSPECT -> CONTEXT -> boucle
# ------------------------------------------------------------------

@dataclass(frozen=True)
class ContextMissionResult:
    """Résultat enrichi : rapport de boucle + contexte construit."""
    report: AgentReport
    mission_context: object            # MissionContext (D6.0.1)
    context_status: str                # CONTEXT_FRESH | CONTEXT_STALE


def run_from_mission(
    mission_id: str,
    mission_text: str,
    target: ProjectTarget,
    intent: Optional[str],
    verify: Callable[[Path], tuple[bool, str]],
    *,
    risk_level: str = "MEDIUM",
    action: Optional[ActionDossier] = None,
    human_approval: Optional[HumanApproval] = None,
    provider=None,
    provider_timeout_s: Optional[float] = None,
) -> ContextMissionResult:
    """
    Cycle complet CONTEXT-AWARE :

        MISSION -> INSPECT -> CONTEXT -> [ANALYZE/PLAN LLM] -> (cible)
          -> EVIDENCE -> PLAN -> PROPOSAL -> HUMAN APPROVAL
          -> AUTHORIZATION -> ADAPTER -> SANDBOX -> D5.9 APPLY
          -> VERIFY -> RESULT

    Deux modes pour l'intent :
      - `provider is None` : `intent` est fourni (D6.0 Phase 2 inchangé).
      - `provider` fourni  : l'intent est DÉRIVÉ par le LLM planner à
        partir du contexte (sous-étape ANALYZE/PLAN). Le LLM ne produit
        qu'une INTENTION ; target_path et intent sont re-validés
        (authority_sources, control-plane, format) avant la chaîne D5/D6.
        Fail-closed : tout verdict BLOCK du planner termine en BLOCKED
        sans aucune écriture.

    Le fichier cible n'est jamais fourni par le client : il vient du
    contexte (mode direct) ou du LLMPlan validé (mode provider).
    """
    from context.context_builder import build_mission_context, is_stale

    # ----- INSPECT + CONTEXT (D6.0.1) -----
    ctx = build_mission_context(
        mission_id, mission_text, target, risk_level=risk_level,
    )

    # Le client ne choisit pas le fichier : on prend le plus pertinent
    # déterminé par le contexte (authorité = fichiers inspectés, pas la
    # mission texte).
    if not ctx.relevant_files:
        report = AgentReport(
            final_state="BLOCKED",
            request_text=mission_text,
            target_fingerprint=target.fingerprint,
            scope=None,
            steps=(StepRecord("CONTEXT", LoopState.BLOCK,
                              "aucun fichier pertinent"),),
            apply_status=None, rolled_back=False,
            committed=False, pushed=False,
            reason="CONTEXT: aucun fichier pertinent déterminé pour la mission",
        )
        return ContextMissionResult(report, ctx, "CONTEXT_FRESH")

    # Vérification de fraîcheur initiale (fail-closed).
    initial = is_stale(ctx, target)
    if initial.stale:
        report = AgentReport(
            final_state="BLOCKED",
            request_text=mission_text,
            target_fingerprint=target.fingerprint,
            scope=None,
            steps=(StepRecord("CONTEXT", LoopState.BLOCK, initial.reason),),
            apply_status=None, rolled_back=False,
            committed=False, pushed=False,
            reason=f"CONTEXT_STALE à la construction: {initial.reason}",
        )
        return ContextMissionResult(report, ctx, "CONTEXT_STALE")

    target_file = ctx.relevant_files[0].path

    # ----- GAP : ANALYSER vs CORRIGER (bifurcation de contrat) -----
    # Une mission d'ANALYSE ne doit PAS être forcée vers un REPLACE:old:new.
    # On classe l'objectif de façon déterministe (5.2) ; seules les
    # missions CORRECTIVES passent par la dérivation d'intent + D5.8/D5.9.
    # La branche ANALYSE produit un diagnostic (constats + evidence +
    # risques + recommandation), SANS écriture, SANS apply, SANS D5.9.
    from mission_intent import analyze_mission as _analyze_mission
    _si = _analyze_mission(mission_text)
    # Branche ANALYSE UNIQUEMENT si l'objectif est EXPLICITEMENT ANALYSER.
    # Tout autre cas (CORRIGER/MODIFIER/… ou UNKNOWN/ambigu) conserve le
    # comportement correctif historique (dérivation + D5.8/D5.9), afin de
    # ne jamais désactiver par erreur la voie corrective existante.
    is_analysis = (_si.objectif == "ANALYSER")
    # Un intent REPLACE explicite force toujours le mode correctif.
    if intent and str(intent).startswith("REPLACE:"):
        is_analysis = False

    if is_analysis:
        # ----- Branche ANALYSE (lecture seule, aucun REPLACE, aucun D5.9) -----
        analysis = _build_analysis(ctx, _si)
        report = AgentReport(
            final_state="ANALYZED",
            request_text=mission_text,
            target_fingerprint=target.fingerprint,
            scope=None,                      # analyse : pas de scope d'écriture
            steps=(StepRecord("ANALYZE", LoopState.CONTINUE,
                              f"objectif={_si.objectif} domaine={_si.domaine}"),),
            apply_status=None, rolled_back=False,
            committed=False, pushed=False,   # jamais : analyse ne modifie rien
            reason=analysis,
        )
        return ContextMissionResult(report, ctx, "CONTEXT_FRESH")

    # ----- 4.6bis ANALYZE/PLAN (L3) : dérivation LLM optionnelle (CORRIGER) -----
    # Si un provider est fourni, l'intent est DÉRIVÉ du contexte par le
    # LLM planner (fail-closed). Le LLM ne produit qu'une INTENTION ;
    # son target_path est re-validé (authority_sources, control-plane,
    # format) AVANT d'entrer dans la chaîne D5/D6. BLOCK du planner =>
    # BLOCKED sans aucune écriture.
    effective_intent = intent
    if provider is not None:
        from llm.llm_planner import derive_intent
        planner = derive_intent(ctx, provider, timeout_s=provider_timeout_s)
        if not planner.ok:
            report = AgentReport(
                final_state="BLOCKED",
                request_text=mission_text,
                target_fingerprint=target.fingerprint,
                scope=None,
                steps=(StepRecord("ANALYZE_PLAN", LoopState.BLOCK,
                                  planner.reason),),
                apply_status=None, rolled_back=False,
                committed=False, pushed=False,
                reason=f"LLM ANALYZE/PLAN BLOCK: {planner.reason}",
            )
            return ContextMissionResult(report, ctx, "CONTEXT_FRESH")
        # L'intent ET la cible viennent du LLMPlan validé (jamais du client).
        effective_intent = planner.intent
        target_file = planner.target_path

    if effective_intent is None or not str(effective_intent).strip():
        report = AgentReport(
            final_state="BLOCKED",
            request_text=mission_text,
            target_fingerprint=target.fingerprint,
            scope=None,
            steps=(StepRecord("ANALYZE_PLAN", LoopState.BLOCK,
                              "aucun intent (ni fourni ni dérivé)"),),
            apply_status=None, rolled_back=False,
            committed=False, pushed=False,
            reason="ANALYZE/PLAN: aucun intent disponible",
        )
        return ContextMissionResult(report, ctx, "CONTEXT_FRESH")

    mission = Mission(
        request_text=mission_text,
        target=target,
        relative_path=target_file,       # déterminé par le CONTEXTE ou le LLMPlan
        intent=effective_intent,
        risk_level=risk_level,
        action=action,
        human_approval=human_approval,
    )

    loop = AgentLoop(mission, verify, mission_context=ctx)
    report = loop.run()
    final_status = is_stale(ctx, target)
    return ContextMissionResult(
        report, ctx,
        "CONTEXT_STALE" if final_status.stale else "CONTEXT_FRESH",
    )


# ------------------------------------------------------------------
# Branche ANALYSE : diagnostic déterministe, lecture seule
# ------------------------------------------------------------------

def _build_analysis(ctx, structured_intent) -> str:
    """
    Produit un diagnostic EXPLICATIF déterministe à partir du MissionContext
    (5.3) et de l'intention (5.2). DÉTERMINISTE, SANS LLM, SANS écriture.

    V0.1.1 : la logique est désormais portée par `analysis_builder`
    (séparation des responsabilités). Ce module reste l'ORCHESTRATEUR :
      - il appelle `build_analysis(...)` -> AnalysisResult sourcé (chaque
        fait est rattaché à un fichier réel : chemin + lignes + extrait +
        SHA) ;
      - il rend ensuite un texte lisible via `render_analysis_text(...)`,
        strictement dérivé de l'AnalysisResult (aucune info ajoutée).

    Invariants conservés : aucune affirmation non étayée par un fichier
    inspecté ; NI REPLACE, NI diff, NI autorisation ; aucune écriture.
    """
    from analysis_builder import build_analysis, render_analysis_text
    result = build_analysis(ctx, structured_intent)
    return render_analysis_text(result, structured_intent)
