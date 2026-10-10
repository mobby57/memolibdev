"""
MemoLibDev — D6.0 : Test Agent Loop (sandbox éphémère, adversarial)
===================================================================

Prouve que l'orchestrateur :
  G1  happy path                 -> APPLIED (non commité)
  G2  verify FAIL                 -> ROLLED_BACK (SHA initial == final)
  G3  cible control-plane         -> BLOCKED dès DECISION (SPEC §6)
  G4  sans approbation humaine    -> AWAIT_HUMAN (aucune écriture)
  G5  approbation forgée (False)  -> BLOCKED (agent ne fabrique pas L6)
  G6  cible hors périmètre        -> BLOCKED (FileTarget fail-closed)
  G7  jamais commit / push        -> sur TOUS les scénarios

Aucun commit, aucun push, aucune production. MemoLib jamais touché
(sandbox éphémère uniquement, comme D5.9).
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile

from project_target import ProjectTarget
from coder_authorization import ActionDossier, HumanApproval, AuthorityLevel
from d59_controlled_apply import sha256_file
from agent_loop import AgentLoop, Mission


PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f" :: {detail}" if detail else ""))


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True, capture_output=True, encoding="utf-8", errors="replace",
    )


def make_lab() -> tuple[Path, ProjectTarget]:
    root = Path(tempfile.mkdtemp(prefix="memolibdev-d60-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "d60@memolibdev.local")
    git(root, "config", "user.name", "d60")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.eol", "lf")

    (root / "src").mkdir()
    (root / "src" / "app.ts").write_text(
        "export const version = '1.0';\n"
        "export function hello() {\n"
        "  return 'world';\n"
        "}\n",
        encoding="utf-8", newline="\n",
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "baseline")
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    fp = hashlib.sha256(f"{root}|main|{head}".encode()).hexdigest()[:16]

    target = ProjectTarget(
        path=root, git_root=root,
        head=git(root, "rev-parse", "--short", "HEAD").stdout.strip(),
        head_full=head, branch="main", fingerprint=fp,
        env_var="MEMOLIBDEV_TARGET",
    )
    return root, target


def approval() -> HumanApproval:
    import datetime
    return HumanApproval(
        approved=True,
        approver="moro",
        approved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        authority_level=AuthorityLevel.L3_PROPOSE.value,
    )


def bound_approval(target, rel: str, intent: str,
                   verify=lambda r: (True, "probe"),
                   request_text: str = "probe") -> HumanApproval:
    """
    V0.4.3 — parcours en deux temps (sous binding obligatoire) :
      1. PROPOSER : AgentLoop avec human_approval=None -> AWAIT_HUMAN,
         produit la proposition (proposal_id + diff_sha256 sur octets exacts) ;
      2. APPROUVER : on lie une approbation humaine RÉELLE à CETTE proposition
         via coder_authorization.bind_approval (jamais fabriquée).
    Le gate §4.8bis revérifie ensuite le hash du diff réellement produit.
    `request_text` DOIT être identique à celui de la mission d'application
    (le proposal_id en dépend) : même proposition => même identité.
    """
    from coder_authorization import bind_approval
    probe = AgentLoop(
        Mission(request_text=request_text, target=target, relative_path=rel,
                intent=intent, risk_level="MEDIUM",
                action=None, human_approval=None),
        verify).run()
    assert probe.final_state == "AWAIT_HUMAN" and probe.proposal is not None, (
        f"probe inattendu: {probe.final_state}")
    return bind_approval(approval(), probe.proposal)


def action_for(rel: str) -> ActionDossier:
    return ActionDossier(
        action_id="ACT-D60-001",
        action_type="PROPOSE_CODE_PATCH",
        target_path=rel,
        risk="MEDIUM",
        reversibility="REVERSIBLE_SANDBOX",
    )


def no_commit_no_push(root: Path, name: str) -> None:
    """Invariant 6 : aucun nouveau commit, aucun remote poussé."""
    count = git(root, "rev-list", "--count", "HEAD").stdout.strip()
    ok(f"{name}_aucun_nouveau_commit", count == "1", f"commits={count}")


INTENT = "REPLACE:version = '1.0':version = '2.0'"


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — D6.0 AGENT LOOP (sandbox éphémère, adversarial)")
    print("=" * 72)

    # ============================================================
    # G1 — HAPPY PATH -> APPLIED (non commité)
    # ============================================================
    print("\n[G1] Happy path -> APPLIED")
    root, target = make_lab()
    try:
        rel = "src/app.ts"
        sha_before = sha256_file(root / rel)

        def verify_pass(r: Path) -> tuple[bool, str]:
            c = (r / rel).read_text(encoding="utf-8")
            return ("version = '2.0'" in c, "marqueur v2.0 présent")

        mission = Mission(
            request_text="Passe la version à 2.0",
            target=target, relative_path=rel, intent=INTENT,
            risk_level="MEDIUM",
            action=action_for(rel),
            human_approval=bound_approval(target, rel, INTENT, request_text="Passe la version à 2.0"),
        )
        report = AgentLoop(mission, verify_pass).run()

        ok("G1_final_APPLIED", report.final_state == "APPLIED", report.reason[:60])
        ok("G1_not_committed",
           report.committed is False and report.pushed is False, "")
        ok("G1_scope_locked", report.scope == rel, f"scope={report.scope}")
        ok("G1_working_tree_modifie",
           sha256_file(root / rel) != sha_before, "fichier modifié")
        porcelain = git(root, "status", "--porcelain").stdout.strip()
        ok("G1_modif_non_committee", porcelain != "", f"status={porcelain!r}")
        no_commit_no_push(root, "G1")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    # G2 — VERIFY FAIL -> ROLLED_BACK (SHA initial == final)
    # ============================================================
    print("\n[G2] Verify FAIL -> ROLLED_BACK")
    root, target = make_lab()
    try:
        rel = "src/app.ts"
        sha_before = sha256_file(root / rel)

        def verify_fail(r: Path) -> tuple[bool, str]:
            return (False, "verification volontairement échouée")

        mission = Mission(
            request_text="Passe la version à 2.0",
            target=target, relative_path=rel, intent=INTENT,
            risk_level="MEDIUM",
            action=action_for(rel),
            human_approval=bound_approval(target, rel, INTENT, request_text="Passe la version à 2.0"),
        )
        report = AgentLoop(mission, verify_fail).run()

        sha_after = sha256_file(root / rel)
        ok("G2_final_ROLLED_BACK", report.final_state == "ROLLED_BACK",
           report.reason[:60])
        ok("G2_rolled_back_flag", report.rolled_back is True, "")
        ok("G2_SHA_restaure", sha_before == sha_after,
           f"{sha_before[:12]} == {sha_after[:12]}")
        porcelain = git(root, "status", "--porcelain").stdout.strip()
        ok("G2_working_tree_propre", porcelain == "", f"status={porcelain!r}")
        ok("G2_not_committed",
           report.committed is False and report.pushed is False, "")
        no_commit_no_push(root, "G2")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    # G3 — CIBLE CONTROL-PLANE -> BLOCKED dès DECISION (SPEC §6)
    # ============================================================
    print("\n[G3] Control-plane -> BLOCKED (DECISION)")
    root, target = make_lab()
    try:
        # On crée un faux fichier control-plane dans le sandbox pour
        # prouver que le BLOCK vient de la RÈGLE §6, pas de l'absence.
        (root / "d59_controlled_apply.py").write_text(
            "# sentinel\n", encoding="utf-8", newline="\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "add sentinel")

        mission = Mission(
            request_text="Désactive le rollback",
            target=target, relative_path="d59_controlled_apply.py",
            intent="REPLACE:sentinel:HACKED",
            action=action_for("d59_controlled_apply.py"),
            human_approval=approval(),
        )

        def verify_unused(r: Path) -> tuple[bool, str]:
            return (True, "ne devrait jamais être appelé")

        report = AgentLoop(mission, verify_unused).run()
        ok("G3_final_BLOCKED", report.final_state == "BLOCKED", report.reason[:70])
        ok("G3_block_at_decision",
           any(s.step == "DECISION" and s.loop_state == "BLOCK"
               for s in report.steps),
           "BLOCK à DECISION")
        ok("G3_control_plane_mentionne", "control-plane" in report.reason, "")
        # Le sentinel ne doit pas avoir changé.
        c = (root / "d59_controlled_apply.py").read_text(encoding="utf-8")
        ok("G3_sentinel_inchange", c == "# sentinel\n", "aucune écriture")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    # G4 — SANS APPROBATION -> AWAIT_HUMAN (aucune écriture)
    # ============================================================
    print("\n[G4] Sans approbation -> AWAIT_HUMAN")
    root, target = make_lab()
    try:
        rel = "src/app.ts"
        sha_before = sha256_file(root / rel)

        def verify_unused(r: Path) -> tuple[bool, str]:
            return (True, "ne devrait jamais être appelé")

        mission = Mission(
            request_text="Passe la version à 2.0",
            target=target, relative_path=rel, intent=INTENT,
            action=None, human_approval=None,     # <-- pas d'approbation
        )
        report = AgentLoop(mission, verify_unused).run()
        ok("G4_final_AWAIT_HUMAN", report.final_state == "AWAIT_HUMAN",
           report.reason[:60])
        ok("G4_fichier_inchange", sha256_file(root / rel) == sha_before, "")
        porcelain = git(root, "status", "--porcelain").stdout.strip()
        ok("G4_working_tree_propre", porcelain == "", f"status={porcelain!r}")
        no_commit_no_push(root, "G4")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    # G5 — APPROBATION FORGÉE (approved=False) -> BLOCKED
    # ============================================================
    print("\n[G5] Approbation forgée (approved=False) -> BLOCKED")
    root, target = make_lab()
    try:
        rel = "src/app.ts"
        sha_before = sha256_file(root / rel)

        forged = HumanApproval(
            approved=False,                 # <-- l'agent ne peut pas forcer True
            approver="moro",
            approved_at="2026-10-06T19:00:00+02:00",
            authority_level=AuthorityLevel.L3_PROPOSE.value,
        )

        def verify_unused(r: Path) -> tuple[bool, str]:
            return (True, "ne devrait jamais être appelé")

        mission = Mission(
            request_text="Passe la version à 2.0",
            target=target, relative_path=rel, intent=INTENT,
            action=action_for(rel), human_approval=forged,
        )
        report = AgentLoop(mission, verify_unused).run()
        ok("G5_final_BLOCKED", report.final_state == "BLOCKED", report.reason[:60])
        ok("G5_fichier_inchange", sha256_file(root / rel) == sha_before, "")
        porcelain = git(root, "status", "--porcelain").stdout.strip()
        ok("G5_working_tree_propre", porcelain == "", f"status={porcelain!r}")
        no_commit_no_push(root, "G5")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    # G6 — CIBLE HORS PÉRIMÈTRE -> BLOCKED (FileTarget fail-closed)
    # ============================================================
    print("\n[G6] Cible hors périmètre -> BLOCKED")
    root, target = make_lab()
    try:
        def verify_unused(r: Path) -> tuple[bool, str]:
            return (True, "ne devrait jamais être appelé")

        mission = Mission(
            request_text="Modifie un fichier hors dépôt",
            target=target, relative_path="../../etc/passwd",
            intent=INTENT,
            action=action_for("../../etc/passwd"), human_approval=approval(),
        )
        report = AgentLoop(mission, verify_unused).run()
        ok("G6_final_BLOCKED", report.final_state == "BLOCKED", report.reason[:60])
        porcelain = git(root, "status", "--porcelain").stdout.strip()
        ok("G6_working_tree_propre", porcelain == "", f"status={porcelain!r}")
        no_commit_no_push(root, "G6")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    print("\n" + "=" * 72)
    print(f"RÉSULTAT D6.0 : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print("Agent Loop = orchestration pure. BLOCK/ABORT non rattrapables.")
    print("Point humain unique = APPROVAL (L6). Aucune sécurité parallèle.")
    print("APPLIED != COMMITTED. Aucun commit/push. MemoLib non touché.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
