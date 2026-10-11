#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test rollback EN REEL, en respectant le flux SUPERVISED_APPLY en 2 temps.
1. PROPOSER (sans approbation) -> proposal + diff_sha256
2. bind_approval -> HumanApproval lie
3. APPLIQUER avec verify_fail -> ROLLED_BACK attendu
"""
import datetime
import hashlib
import os
import subprocess
import sys
from pathlib import Path

MEMOLIBDEV_V3 = Path(r"C:\Users\moros\MemoLibDev\v3")
TARGET = Path(r"C:\Users\moros\Desktop\test_target")

sys.path.insert(0, str(MEMOLIBDEV_V3))
os.environ["MEMOLIBDEV_TARGET"] = str(TARGET)


def sha_of(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    print("=" * 60)
    print(" TEST ROLLBACK EN REEL (flux SUPERVISED_APPLY 2 temps)")
    print("=" * 60)

    # 1. Restaurer
    print("\n[1] Restauration sample.py")
    subprocess.run(["git", "checkout", "sample.py"],
                   cwd=str(TARGET), check=True, capture_output=True)
    sha_before = sha_of(TARGET / "sample.py")
    print(f"    SHA avant : {sha_before[:32]}...")

    # 2. Imports
    print("\n[2] Chargement du moteur")
    from project_target import resolve_target
    from agent_loop import run_from_mission
    from coder_authorization import (
        HumanApproval, AuthorityLevel, ActionDossier, bind_approval,
    )
    from memolibdev_cli import _make_provider

    target = resolve_target()
    provider = _make_provider("memolibdev-qwen7b-16k:latest")
    if not provider.available:
        print("    [ERREUR] Ollama indisponible")
        return 2
    print(f"    Cible : {target.git_root}")
    print(f"    Provider : OK")

    # 3. verify qui ECHOUE (sera utilise en phase APPLIQUER)
    def verify_fail(repo):
        print(f"    [VERIFY] Appele -> (False, 'echec force')")
        return (False, "echec force pour test rollback en reel")

    # 4. verify neutre (pour la phase PROPOSER, on ne verifie rien)
    def verify_ok(repo):
        return (True, "proposer - pas de verify reel")

    mission = "Renomme la fonction hello en greet dans sample.py"

    # ============================================================
    # PHASE 1 : PROPOSER (aucune approbation, aucune ecriture)
    # ============================================================
    print("\n[3] PHASE PROPOSER (sans approbation, aucune ecriture)")
    print("-" * 60)

    probe = run_from_mission(
        "TEST-ROLLBACK-propose",
        mission, target, None, verify_ok,
        action=None, human_approval=None,
        provider=provider, provider_timeout_s=300.0,
    )

    prep = probe.report
    print(f"    STATUT     : {prep.final_state}")
    print(f"    PROPOSAL   : {prep.proposal is not None}")

    if prep.final_state != "AWAIT_HUMAN" or prep.proposal is None:
        print(f"    [ECHEC] Pas de proposition disponible : {prep.reason}")
        return 2

    proposal = prep.proposal
    print(f"    proposal_id : {proposal.proposal_id}")
    print(f"    diff_sha256 : {proposal.diff_sha256[:32]}...")
    print(f"    scope       : {proposal.scope}")

    # Verifier que rien n'a ete ecrit
    sha_apres_propose = sha_of(TARGET / "sample.py")
    assert sha_apres_propose == sha_before, "PROPOSER a modifie le fichier !"
    print(f"    [OK] Fichier inchange apres PROPOSER")

    # ============================================================
    # PHASE 2 : LIAISON (bind_approval)
    # ============================================================
    print("\n[4] PHASE LIAISON (bind_approval)")
    print("-" * 60)

    approval_raw = HumanApproval(
        approved=True,
        approver="test_rollback_reel",
        approved_at=datetime.datetime.now().astimezone().isoformat(),
        authority_level=AuthorityLevel.L3_PROPOSE.value,
    )
    bound = bind_approval(approval_raw, proposal)
    print(f"    [OK] Approbation liee au diff")
    print(f"    expected_diff_sha256 : {bound.expected_diff_sha256[:32]}...")

    # ============================================================
    # PHASE 3 : APPLIQUER (avec verify qui echoue)
    # ============================================================
    print("\n[5] PHASE APPLIQUER (avec verify_fail)")
    print("-" * 60)

    action = ActionDossier(
        action_id="TEST-ROLLBACK-001",
        action_type="PROPOSE_CODE_PATCH",
        target_path=proposal.scope,
        risk="MEDIUM",
        reversibility="REVERSIBLE_SANDBOX",
    )

    res = run_from_mission(
        "TEST-ROLLBACK-apply",
        mission, target, None, verify_fail,
        action=action, human_approval=bound,
        provider=provider, provider_timeout_s=300.0,
    )

    rep = res.report
    print(f"    STATUT      : {rep.final_state}")
    print(f"    ROLLED_BACK : {rep.rolled_back}")
    print(f"    APPLY_STATUS: {rep.apply_status}")
    print(f"    RAISON      : {rep.reason}")

    # ============================================================
    # VERIFICATION FINALE
    # ============================================================
    print("\n[6] Verification finale")
    sha_after = sha_of(TARGET / "sample.py")
    print(f"    SHA apres : {sha_after[:32]}...")

    print("\n" + "=" * 60)
    if sha_after == sha_before:
        if rep.rolled_back:
            print(" ROLLBACK REUSSI EN REEL")
            print(" Le fichier est IDENTIQUE a l'etat initial.")
            print(" Le rollback automatique a bien restaure l'etat.")
        else:
            print(" AUCUNE ECRITURE EFFECTUEE")
            print(" Le fichier est identique mais le rollback n'a pas ete declenche.")
            print(f" Statut : {rep.final_state}")
        print(f"   SHA avant : {sha_before}")
        print(f"   SHA apres : {sha_after}")
        print("=" * 60)
        return 0
    else:
        print(" ROLLBACK ECHOUE")
        print(f"   SHA avant : {sha_before}")
        print(f"   SHA apres : {sha_after}")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
