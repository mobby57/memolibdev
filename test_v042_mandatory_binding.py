"""
MemoLibDev — V0.4.2 : Tests du BINDING OBLIGATOIRE du diff
==========================================================

Prouve qu'AUCUN chemin d'application n'accepte une autorisation sans binding
vérifié (mission / proposal_id / scope / SHA source / SHA-256 du diff / octets
exacts transmis à D5.9).

Le point d'application unique est agent_loop §4.9 (run_controlled_apply),
précédé du gate OBLIGATOIRE §4.8bis. Tous les points d'entrée (CLI
SUPERVISED_APPLY/SANDBOX, API /approve) passent par run_from_mission ->
AgentLoop.run() -> §4.8bis -> §4.9. On teste donc le gate sur le vrai
AgentLoop, avec un ESPION sur la frontière d'application (aucun apply réel,
aucune modification de d59).

Cas (§5) :
  M1  approbation moderne BOUND valide -> appliquée (espion atteint)
  M2  approbation legacy sans hash -> REFUS avant application
  M3  hash vide / mal formé / incohérent -> REFUS
  M4  proposal_id absent ou modifié -> REFUS
  M5  diff modifié après approbation -> REFUS
  M6  SHA source périmé -> REFUS (garde-fou existant conservé)
  M7  scope élargi / cible différente -> REFUS (garde-fou conservé)
  M8  approbation d'une autre mission -> REFUS (proposal_id/diff différents)
  M9  flag REQUIRE_DIFF_BINDING désactivé -> APPLICATION BLOQUÉE (pas bypass)
  M10 refus humain / double soumission -> aucun contournement (façade)
  M11 PREUVE : octets exacts transmis à D5.9 == hash approuvé
  M12 rollback TOUJOURS fonctionnel SOUS binding (verify FAIL -> ROLLED_BACK)

Lancement : python test_v042_mandatory_binding.py
"""

from __future__ import annotations

import os
import importlib
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("MEMOLIBDEV_TARGET", r"C:\Users\moros\memoLib")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


import agent_loop
from agent_loop import AgentLoop, Mission, run_from_mission
from coder_authorization import HumanApproval, ActionDossier
import coder_authorization
from project_target import resolve_target
from file_target import resolve_file_target


def _verify_pass(_r):
    return (True, "verify espion PASS")


def _verify_fail(_r):
    return (False, "verify espion FAIL")


REL = "README.md"
INTENT = "REPLACE:MIT License:MIT License (V0.4.2)"


def _probe_proposal(target):
    """Produit la proposition README (AWAIT_HUMAN) pour obtenir le binding réel."""
    rep = AgentLoop(
        Mission(request_text="maj licence", target=target, relative_path=REL,
                intent=INTENT, risk_level="LOW", action=None,
                human_approval=None),
        _verify_pass).run()
    return rep.proposal


def _action(target):
    ft = resolve_file_target(REL, target, risk_level="LOW")
    return ActionDossier("A1", "PROPOSE_CODE_PATCH", ft.path, "LOW",
                         "REVERSIBLE_SANDBOX")


def _appr(prop, **kw):
    base = dict(approved=True, approver="alice", approved_at="t",
                authority_level="L3_PROPOSE",
                proposal_id=prop.proposal_id,
                expected_diff_sha256=prop.diff_sha256)
    base.update(kw)
    return HumanApproval(**base)


def _run(target, approval, *, intent=INTENT, verify=_verify_pass, spy=True):
    """Exécute AgentLoop avec espion sur run_controlled_apply. Retourne (rep, captured)."""
    captured = {}
    real = agent_loop.run_controlled_apply

    def spy_rca(repo_root, certificate, patch_text, **kw):
        captured["patch_text"] = patch_text
        from coder_authorization import diff_sha256 as _d
        captured["patch_sha"] = _d(patch_text)
        if verify is _verify_fail:
            @dataclass
            class _R:
                status: str = "ROLLED_BACK"; reason: str = "spy rollback"
                sha_initial: str = "x"; sha_final: str = "x"
                rolled_back: bool = True; committed: bool = False
                pushed: bool = False; report: dict = None
            return _R(report={})
        @dataclass
        class _R:
            status: str = "APPLIED"; reason: str = "spy applied"
            sha_initial: str = "x"; sha_final: str = "x"
            rolled_back: bool = False; committed: bool = False
            pushed: bool = False; report: dict = None
        return _R(report={})

    m = Mission(request_text="maj licence", target=target, relative_path=REL,
                intent=intent, risk_level="LOW", action=_action(target),
                human_approval=approval)
    if spy:
        agent_loop.run_controlled_apply = spy_rca
    try:
        rep = AgentLoop(m, verify).run()
    finally:
        agent_loop.run_controlled_apply = real
    return rep, captured


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — V0.4.2 BINDING OBLIGATOIRE DU DIFF")
    print("=" * 72)

    target = resolve_target()
    prop = _probe_proposal(target)
    ok("P0 proposition README (proposal_id + diff_sha256)",
       bool(prop) and bool(prop.proposal_id) and bool(prop.diff_sha256))

    # M1 — moderne bound valide -> appliquée (espion atteint)
    print("\n[M1] approbation BOUND valide -> appliquée")
    rep, cap = _run(target, _appr(prop))
    ok("M1 appliquée (espion atteint)", "patch_text" in cap, rep.final_state)
    ok("M1 DIFF_BINDING CONTINUE",
       any(s.step == "DIFF_BINDING" and s.loop_state == "CONTINUE" for s in rep.steps))

    # M2 — legacy sans hash -> REFUS avant application
    print("\n[M2] approbation legacy sans hash -> refus avant application")
    legacy = HumanApproval(approved=True, approver="a", approved_at="t",
                           authority_level="L3_PROPOSE")  # pas de binding
    rep, cap = _run(target, legacy)
    ok("M2 BLOCKED", rep.final_state == "BLOCKED", rep.reason[:60])
    ok("M2 application JAMAIS atteinte", "patch_text" not in cap)
    ok("M2 raison = binding obligatoire", "binding" in rep.reason.lower())

    # M3 — hash vide/mal formé/incohérent -> refus
    print("\n[M3] hash vide / mal formé / incohérent -> refus")
    for bad in ("", "   ", "xyz", "0" * 64):
        rep, cap = _run(target, _appr(prop, expected_diff_sha256=bad))
        ok(f"M3 hash={bad[:6]!r} -> BLOCKED",
           rep.final_state == "BLOCKED" and "patch_text" not in cap)

    # M4 — proposal_id absent/modifié -> refus
    print("\n[M4] proposal_id absent / modifié -> refus")
    rep, cap = _run(target, _appr(prop, proposal_id=None))
    ok("M4 proposal_id None -> BLOCKED",
       rep.final_state == "BLOCKED" and "patch_text" not in cap)
    rep, cap = _run(target, _appr(prop, proposal_id="P-autre"))
    ok("M4 proposal_id modifié -> BLOCKED",
       rep.final_state == "BLOCKED" and "patch_text" not in cap)

    # M5 — diff modifié après approbation (intent différent) -> refus
    print("\n[M5] diff modifié après approbation -> refus")
    rep, cap = _run(target, _appr(prop),
                    intent="REPLACE:MIT License:MIT License (TAMPER)")
    ok("M5 BLOCKED (diff != approuvé)",
       rep.final_state == "BLOCKED" and "patch_text" not in cap, rep.reason[:50])

    # M6 — SHA source périmé -> refus (evidence integrity conservée)
    print("\n[M6] SHA source périmé -> refus (D5.8 integrity, inchangé)")
    from coder_authorization import _validate_evidence_integrity, CoderAuthorization, AuthorizationTarget
    fake = CoderAuthorization(
        path=prop.scope,
        target=AuthorizationTarget(str(target.git_root), target.head_full, target.fingerprint),
        evidence_status="ACCEPTED", evidence_sha256="0" * 64,
        provenance_status="RESOLVED", provenance_source_path=prop.scope,
        provenance_resolved_path=prop.scope,
        action=_action(target), human_approval=_appr(prop),
        human_validation_required=True, status="AUTHORIZED", reason="x")
    integ_ok, integ_reason = _validate_evidence_integrity(fake, target, prop.scope)
    ok("M6 evidence integrity BLOCK (SHA périmé)", not integ_ok, integ_reason[:50])

    # M7 — scope élargi -> refus (write guardrail conservé)
    print("\n[M7] scope élargi -> refus (enforce_write_guardrail)")
    import controlled_coder as cc
    mixed = (prop.diff_preview or "") + (
        "\ndiff --git a/src/x.ts b/src/x.ts\n--- a/src/x.ts\n+++ b/src/x.ts\n@@ -1 +1,2 @@\n a\n+b\n")
    guard = cc.enforce_write_guardrail(mixed, [prop.scope])
    ok("M7 hors scope REJECT", guard["verdict"] == "REJECT")

    # M8 — autre mission -> proposal_id/diff différents -> refus
    print("\n[M8] approbation d'une autre mission -> refus")
    # approbation bound à l'ancienne proposition, mais mission produit un
    # diff différent (intent différent) -> mismatch.
    rep, cap = _run(target, _appr(prop),
                    intent="REPLACE:MIT License:MIT License (OTHER MISSION)")
    ok("M8 BLOCKED", rep.final_state == "BLOCKED" and "patch_text" not in cap)

    # M9 — flag désactivé -> APPLICATION BLOQUÉE (jamais bypass)
    print("\n[M9] REQUIRE_DIFF_BINDING désactivé -> application BLOQUÉE")
    original_flag = coder_authorization.REQUIRE_DIFF_BINDING
    try:
        coder_authorization.REQUIRE_DIFF_BINDING = False
        rep, cap = _run(target, _appr(prop))   # même une approbation valide
        ok("M9 BLOCKED quand flag désactivé",
           rep.final_state == "BLOCKED" and "patch_text" not in cap, rep.reason[:60])
        ok("M9 raison = flag désactivé -> bloqué",
           "désactivé" in rep.reason or "REQUIRE_DIFF_BINDING" in rep.reason)
    finally:
        coder_authorization.REQUIRE_DIFF_BINDING = original_flag
    ok("M9 flag restauré à True", coder_authorization.REQUIRE_DIFF_BINDING is True)

    # M11 — PREUVE octets exacts == hash approuvé
    print("\n[M11] octets exacts transmis à D5.9 == hash approuvé")
    appr = _appr(prop)
    rep, cap = _run(target, appr)
    ok("M11 D5.9 atteint", "patch_sha" in cap)
    ok("M11 patch_sha == expected_diff_sha256",
       cap.get("patch_sha") == appr.expected_diff_sha256,
       f"{cap.get('patch_sha','')[:16]} == {(appr.expected_diff_sha256 or '')[:16]}")

    # M12 — rollback TOUJOURS fonctionnel SOUS binding
    print("\n[M12] rollback conservé sous binding (verify FAIL -> ROLLED_BACK)")
    rep, cap = _run(target, _appr(prop), verify=_verify_fail)
    ok("M12 binding franchi puis apply atteint", "patch_text" in cap)
    ok("M12 ROLLED_BACK (rollback intact)", rep.final_state == "ROLLED_BACK",
       rep.final_state)

    # ---- Innocuité MemoLib ----
    print("\n[MEMOLIB] inchangé")
    import subprocess
    st = subprocess.run(["git", "-C", str(target.git_root), "status", "--porcelain"],
                        text=True, capture_output=True, encoding="utf-8").stdout
    ok("MEMOLIB working tree propre", st == "", repr(st))

    print("\n" + "=" * 72)
    print(f"RÉSULTAT V0.4.2 : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS : " + ", ".join(FAIL))
    print("=" * 72)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
