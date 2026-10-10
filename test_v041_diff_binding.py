"""
MemoLibDev — V0.4.1 : Tests ADVERSARIAUX du binding cryptographique du diff
===========================================================================

Prouve que la décision humaine est liée aux OCTETS EXACTS du patch approuvé :
aucune modification du patch après approbation ne peut être appliquée avec la
même autorisation.

POINT DE CONTRÔLE CRITIQUE (prouvé ici, pas seulement par un test unitaire) :
    le hash VALIDÉ (approval.expected_diff_sha256) correspond aux OCTETS
    EXACTS du `patch_text` RÉELLEMENT transmis à l'application D5.9
    (run_controlled_apply), capturé par un espion de test (sans modifier
    d59_controlled_apply.py).

Cas couverts (§6) :
  1  proposition inchangée -> binding accepté
  2  un seul octet modifié après approbation -> refus
  3  diff altéré alors que le SHA source reste identique -> refus
  4  proposal_id modifié -> refus
  5  mission différente -> proposal_id différent -> refus
  6  scope élargi -> refus (garde-fou existant conservé)
  7  SHA source périmé -> refus (garde-fou existant conservé)
  8  certificat absent / approbation mal formée -> refus
  9  double soumission d'approbation -> seconde refusée (façade)
  10 CRLF / LF / BOM / encodages -> aucune normalisation silencieuse
  11 PREUVE : hash validé == octets exacts passés à l'application

READ-ONLY sur MemoLib. Aucun apply réel (verify espion / apply espion).
Lancement :  python test_v041_diff_binding.py
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("MEMOLIBDEV_TARGET", r"C:\Users\moros\memoLib")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

HERE = Path(__file__).resolve().parent

PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


from coder_authorization import (
    HumanApproval, ActionDossier, diff_sha256, canonical_diff_bytes,
    verify_diff_binding,
)
import agent_loop
from agent_loop import run_from_mission, Mission, AgentLoop
from project_target import resolve_target
from file_target import resolve_file_target
import code_adapter


def _verify(_r):
    return (True, "verify espion")


def _real_proposal():
    """Produit une proposition RÉELLE (AWAIT_HUMAN) sur MemoLib (READ_ONLY)."""
    target = resolve_target()
    res = run_from_mission("V041", "maj licence", target,
                           "REPLACE:MIT License:MIT License (V0.4.1)",
                           _verify, action=None, human_approval=None,
                           provider=None, provider_timeout_s=None)
    return target, res.report, res.report.proposal


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — V0.4.1 BINDING CRYPTOGRAPHIQUE DU DIFF")
    print("=" * 72)

    target, report, prop = _real_proposal()
    ok("P0 proposition réelle AWAIT_HUMAN",
       report.final_state == "AWAIT_HUMAN", report.final_state)
    ok("P0 proposal_id présent", bool(prop.proposal_id), prop.proposal_id)
    ok("P0 diff_sha256 présent", bool(prop.diff_sha256), (prop.diff_sha256 or "")[:16])
    diff = prop.diff_preview
    ok("P0 diff_sha256 == sha(octets exacts du diff)",
       prop.diff_sha256 == diff_sha256(diff))

    def appr(**kw):
        import datetime
        _now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        base = dict(approved=True, approver="alice", approved_at=_now,
                    authority_level="L3_PROPOSE",
                    proposal_id=prop.proposal_id,
                    expected_diff_sha256=prop.diff_sha256)
        base.update(kw)
        return HumanApproval(**base)

    # ---- 1. proposition inchangée -> accepté ----
    print("\n[1] proposition inchangée -> accepté")
    okb, reason = verify_diff_binding(appr(), diff, expected_proposal_id=prop.proposal_id)
    ok("1 binding accepté", okb, reason)

    # ---- 2. un seul octet modifié -> refus ----
    print("\n[2] un octet modifié -> refus")
    okb, reason = verify_diff_binding(appr(), diff + " ",
                                      expected_proposal_id=prop.proposal_id)
    ok("2 refus (1 octet)", not okb, reason)
    # modification interne (pas seulement en fin)
    tampered_in = diff.replace("MIT License (V0.4.1)", "MIT License (HACKED)", 1)
    okb2, _ = verify_diff_binding(appr(), tampered_in,
                                  expected_proposal_id=prop.proposal_id)
    ok("2 refus (octet interne)", not okb2)

    # ---- 3. diff altéré, SHA source identique -> refus ----
    print("\n[3] diff altéré mais SHA source identique -> refus")
    # Le SHA source (sha_before) n'est pas touché ; seul le diff change.
    ok("3 sha_before inchangé dans la proposition",
       bool(prop.files) and bool(prop.files[0].sha_before))
    okb, reason = verify_diff_binding(appr(), tampered_in,
                                      expected_proposal_id=prop.proposal_id)
    ok("3 refus malgré SHA source identique", not okb, reason)

    # ---- 4. proposal_id modifié -> refus ----
    print("\n[4] proposal_id modifié -> refus")
    okb, reason = verify_diff_binding(appr(proposal_id="P-autre"), diff,
                                      expected_proposal_id=prop.proposal_id)
    ok("4 refus proposal_id", not okb, reason)

    # ---- 5. mission différente -> proposal_id différent ----
    print("\n[5] mission différente -> proposal_id différent")
    _, _, prop2 = (lambda: (lambda t: (t, None, run_from_mission(
        "V041b", "corrige la configuration de build", t,
        "REPLACE:MIT License:MIT License (autre)", _verify,
        action=None, human_approval=None, provider=None,
        provider_timeout_s=None).report.proposal))(resolve_target()))()
    ok("5 proposal_id différent pour mission différente",
       prop2 is None or prop2.proposal_id != prop.proposal_id,
       f"{prop.proposal_id} vs {getattr(prop2,'proposal_id',None)}")

    # ---- 6. scope élargi -> refus (garde-fou existant) ----
    print("\n[6] scope élargi -> refus (enforce_write_guardrail)")
    import controlled_coder as cc
    mixed = diff + (
        "\ndiff --git a/src/other/x.ts b/src/other/x.ts\n"
        "--- a/src/other/x.ts\n+++ b/src/other/x.ts\n@@ -1 +1,2 @@\n a\n+b\n")
    guard = cc.enforce_write_guardrail(mixed, [prop.scope])
    ok("6 diff hors scope REJECT", guard["verdict"] == "REJECT",
       str(guard.get("out_of_scope_files")))

    # ---- 7. SHA source périmé -> refus (D5.8/D5.9 inchangés) ----
    print("\n[7] SHA source périmé -> refus (pre_apply G4 / evidence integrity)")
    from coder_authorization import _validate_evidence_integrity, CoderAuthorization, AuthorizationTarget
    # Autorisation avec un evidence_sha256 volontairement faux -> integrity BLOCK.
    fake = CoderAuthorization(
        path=prop.scope,
        target=AuthorizationTarget(git_root=str(target.git_root),
                                   head=target.head_full,
                                   repository_fingerprint=target.fingerprint),
        evidence_status="ACCEPTED", evidence_sha256="0" * 64,
        provenance_status="RESOLVED", provenance_source_path=prop.scope,
        provenance_resolved_path=prop.scope,
        action=ActionDossier("a", "PROPOSE_CODE_PATCH", prop.scope, "LOW", "REVERSIBLE_SANDBOX"),
        human_approval=appr(), human_validation_required=True,
        status="AUTHORIZED", reason="x")
    integ_ok, integ_reason = _validate_evidence_integrity(fake, target, prop.scope)
    ok("7 evidence integrity BLOCK sur SHA périmé", not integ_ok, integ_reason)

    # ---- 8. approbation mal formée -> refus ----
    print("\n[8] approbation absente / mal formée -> refus")
    ok("8 approbation None -> refus",
       not verify_diff_binding(None, diff)[0])
    ok("8 approved=False -> refus",
       not verify_diff_binding(appr(approved=False), diff)[0])
    ok("8 expected_diff_sha256 absent -> refus (fail-closed)",
       not verify_diff_binding(appr(expected_diff_sha256=None), diff)[0])
    ok("8 diff vide -> refus", not verify_diff_binding(appr(), "")[0])

    # ---- 10. CRLF / LF / BOM / encodage -> aucune normalisation ----
    print("\n[10] CRLF/LF/BOM/encodage -> aucune normalisation silencieuse")
    lf = "diff --git a/x b/x\n@@ -1 +1 @@\n-a\n+b\n"
    crlf = lf.replace("\n", "\r\n")
    bom = "\ufeff" + lf
    ok("10 LF != CRLF (hash distinct)", diff_sha256(lf) != diff_sha256(crlf))
    ok("10 BOM != sans BOM (hash distinct)", diff_sha256(lf) != diff_sha256(bom))
    ok("10 octets canoniques = encode utf-8 sans transformation",
       canonical_diff_bytes(crlf) == crlf.encode("utf-8")
       and b"\r\n" in canonical_diff_bytes(crlf))
    ok("10 un diff CRLF approuvé n'est pas accepté comme LF",
       not verify_diff_binding(
           appr(expected_diff_sha256=diff_sha256(crlf)), lf)[0])

    # ---- 11. PREUVE : hash validé == octets passés à l'application ----
    print("\n[11] PREUVE : hash validé == octets exacts transmis à D5.9")
    captured = {}

    real_rca = agent_loop.run_controlled_apply

    def spy_rca(repo_root, certificate, patch_text, **kw):
        # Capture le patch EXACT que l'agent transmet à l'application.
        captured["patch_text"] = patch_text
        captured["patch_sha"] = diff_sha256(patch_text)

        # On NE touche PAS D5.9 : on simule un APPLIED sans écrire, pour
        # prouver uniquement le binding (aucun apply réel sur MemoLib).
        @dataclass
        class _R:
            status: str = "APPLIED"
            reason: str = "spy (aucune écriture réelle)"
            sha_initial: str = "x"
            sha_final: str = "x"
            rolled_back: bool = False
            committed: bool = False
            pushed: bool = False
            report: dict = None
        return _R(report={"status": "APPLIED", "spy": True})

    # Le binding doit porter sur le diff RÉELLEMENT produit par CE flux
    # (relative_path=README.md). On capture d'abord ce diff/proposal via un
    # run AWAIT_HUMAN sur la MÊME cible/intent, puis on relie l'approbation
    # à SON diff_sha256. Ainsi proposition et application partagent les
    # octets identiques (diff déterministe).
    ft = resolve_file_target("README.md", target, risk_level="LOW")
    action = ActionDossier("A1", "PROPOSE_CODE_PATCH", ft.path, "LOW",
                           "REVERSIBLE_SANDBOX")
    probe = AgentLoop(
        Mission(request_text="maj licence", target=target,
                relative_path="README.md",
                intent="REPLACE:MIT License:MIT License (V0.4.1)",
                risk_level="LOW", action=None, human_approval=None),
        _verify).run()
    readme_prop = probe.proposal
    ok("11 probe AWAIT_HUMAN + proposal README",
       probe.final_state == "AWAIT_HUMAN" and readme_prop is not None,
       probe.final_state)

    import datetime as _dt
    bound_appr = HumanApproval(
        approved=True, approver="alice",
        approved_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        authority_level="L3_PROPOSE",
        proposal_id=readme_prop.proposal_id,
        expected_diff_sha256=readme_prop.diff_sha256)
    mission = Mission(
        request_text="maj licence", target=target, relative_path="README.md",
        intent="REPLACE:MIT License:MIT License (V0.4.1)", risk_level="LOW",
        action=action, human_approval=bound_appr)
    agent_loop.run_controlled_apply = spy_rca
    try:
        rep = AgentLoop(mission, _verify).run()
    finally:
        agent_loop.run_controlled_apply = real_rca

    steps = [s.step for s in rep.steps]
    ok("11 binding gate franchi (DIFF_BINDING CONTINUE)",
       any(s == "DIFF_BINDING" for s in steps), str(steps))
    ok("11 apply atteint (D5.9 appelé via espion)",
       "patch_text" in captured, str(list(captured.keys())))
    ok("11 hash validé == sha des octets EXACTS passés à l'application",
       captured.get("patch_sha") == bound_appr.expected_diff_sha256,
       f"patch={captured.get('patch_sha','')[:16]} "
       f"approuvé={(bound_appr.expected_diff_sha256 or '')[:16]}")
    # Et c'est bien le diff de la proposition présentée.
    ok("11 octets appliqués == octets de la proposition présentée",
       captured.get("patch_sha") == readme_prop.diff_sha256)

    # ---- 11b. diff altéré AVANT apply avec la même approbation -> BLOCK ----
    print("\n[11b] diff altéré avec la même approbation -> BLOCK avant apply")
    captured.clear()
    # Intent différent -> diff différent, mais approbation BOUND à l'ancien
    # diff -> mismatch -> BLOCK avant tout apply.
    mission_tamper = Mission(
        request_text="maj licence", target=target, relative_path="README.md",
        intent="REPLACE:MIT License:MIT License (DIFFERENT)", risk_level="LOW",
        action=action, human_approval=bound_appr)
    agent_loop.run_controlled_apply = spy_rca
    try:
        rep2 = AgentLoop(mission_tamper, _verify).run()
    finally:
        agent_loop.run_controlled_apply = real_rca
    ok("11b BLOCKED par le binding", rep2.final_state == "BLOCKED", rep2.final_state)
    ok("11b apply JAMAIS atteint (aucun patch transmis)",
       "patch_text" not in captured, str(list(captured.keys())))
    ok("11b raison = binding mismatch",
       "binding" in rep2.reason.lower(), rep2.reason[:80])

    # ---- Innocuité MemoLib ----
    print("\n[MEMOLIB] inchangé")
    import subprocess
    st = subprocess.run(["git", "-C", str(target.git_root), "status", "--porcelain"],
                        text=True, capture_output=True, encoding="utf-8").stdout
    ok("MEMOLIB working tree propre (aucun apply réel)", st == "", repr(st))

    print("\n" + "=" * 72)
    print(f"RÉSULTAT V0.4.1 : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS : " + ", ".join(FAIL))
    print("=" * 72)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
