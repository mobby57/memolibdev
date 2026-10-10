"""
MemoLibDev — D6.0 Phase 2 : Test intégration Context -> Agent Loop
==================================================================

Prouve le rebranchement :
    MISSION -> INSPECT -> CONTEXT -> EVIDENCE -> PLAN -> PROPOSAL
      -> HUMAN APPROVAL -> AUTHORIZATION -> ADAPTER -> SANDBOX
      -> D5.9 CONTROLLED APPLY -> VERIFY -> RESULT

Scénarios :
  P1  happy path context-aware           -> APPLIED (non commité)
  P2  contexte périmé (SHA) avant apply   -> BLOCKED (pas d'apply)
  P3  fichier modifié après construction  -> BLOCKED (re-check CONTEXT_STALE)
  P4  HEAD divergent après construction   -> BLOCKED
  P5  mission != autorité (cible choisie par le contexte, pas le client)
  P6  aucun commit / push / apply parasite sur TOUS les scénarios

Aucun LLM. Aucun apply hors D5.9. Sandbox éphémère. MemoLib non touché.
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
from agent_loop import run_from_mission, AgentLoop, Mission
from context.context_builder import build_mission_context


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
    root = Path(tempfile.mkdtemp(prefix="memolibdev-p2-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "p2@memolibdev.local")
    git(root, "config", "user.name", "p2")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.eol", "lf")

    (root / "src").mkdir()
    # Fichier le plus pertinent pour la mission "version" : contient
    # "version" dans le chemin ET le contenu -> meilleur score.
    (root / "src" / "version.ts").write_text(
        "export const version = '1.0';\n"
        "export function getVersion() {\n"
        "  return version;\n"
        "}\n",
        encoding="utf-8", newline="\n",
    )
    (root / "src" / "other.ts").write_text(
        "export const name = 'x';\n", encoding="utf-8", newline="\n",
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


def target_at_head(root: Path) -> ProjectTarget:
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    fp = hashlib.sha256(f"{root}|main|{head}".encode()).hexdigest()[:16]
    return ProjectTarget(
        path=root, git_root=root,
        head=git(root, "rev-parse", "--short", "HEAD").stdout.strip(),
        head_full=head, branch="main", fingerprint=fp,
        env_var="MEMOLIBDEV_TARGET",
    )


MISSION = "mettre à jour la version du module version"
INTENT = "REPLACE:version = '1.0':version = '2.0'"


def approval() -> HumanApproval:
    import datetime
    return HumanApproval(
        approved=True, approver="moro",
        approved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        authority_level=AuthorityLevel.L3_PROPOSE.value,
    )


def bound_approval_rfm(mission_id, mission_text, target, intent, verify):
    """V0.4.3 : binding via le MÊME parcours run_from_mission (probe AWAIT_HUMAN)."""
    from coder_authorization import bind_approval
    probe = run_from_mission(mission_id + "-probe", mission_text, target,
                             intent, verify, action=None, human_approval=None)
    assert probe.report.final_state == "AWAIT_HUMAN" and probe.report.proposal, (
        f"probe inattendu: {probe.report.final_state}")
    return bind_approval(approval(), probe.report.proposal)


def bound_approval_loop(target, rel, intent, mission_text,
                        verify=lambda r: (True, "probe")):
    """V0.4.3 : binding via AgentLoop direct (probe AWAIT_HUMAN, sans ctx)."""
    from coder_authorization import bind_approval
    probe = AgentLoop(
        Mission(request_text=mission_text, target=target, relative_path=rel,
                intent=intent, risk_level="MEDIUM", action=None,
                human_approval=None),
        verify).run()
    assert probe.final_state == "AWAIT_HUMAN" and probe.proposal is not None, (
        f"probe inattendu: {probe.final_state}")
    return bind_approval(approval(), probe.proposal)


def action_for(rel: str) -> ActionDossier:
    return ActionDossier(
        action_id="ACT-P2-001", action_type="PROPOSE_CODE_PATCH",
        target_path=rel, risk="MEDIUM", reversibility="REVERSIBLE_SANDBOX",
    )


def predicted_target(target: ProjectTarget) -> str:
    """Le fichier que le contexte choisira (le mieux scoré)."""
    ctx = build_mission_context("probe", MISSION, target)
    return ctx.relevant_files[0].path


def no_commit_no_push(root: Path, name: str) -> None:
    count = git(root, "rev-list", "--count", "HEAD").stdout.strip()
    remotes = git(root, "remote").stdout.strip()
    ok(f"{name}_aucun_commit", count == "1", f"commits={count}")
    ok(f"{name}_aucun_remote", remotes == "", "aucun push")


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — D6.0 PHASE 2 : CONTEXT -> AGENT LOOP (intégration)")
    print("=" * 72)

    # ============================================================
    # P1 — HAPPY PATH context-aware -> APPLIED
    # ============================================================
    print("\n[P1] Happy path context-aware -> APPLIED")
    root, target = make_lab()
    try:
        tf = predicted_target(target)
        sha_before = sha256_file(root / tf)

        def verify_pass(r: Path) -> tuple[bool, str]:
            c = (r / tf).read_text(encoding="utf-8")
            return ("version = '2.0'" in c, "marqueur v2.0")

        res = run_from_mission(
            "M-P1", MISSION, target, INTENT, verify_pass,
            action=action_for(tf),
            human_approval=bound_approval_rfm("M-P1", MISSION, target, INTENT, verify_pass),
        )
        ok("P1_cible_choisie_par_contexte", tf == "src/version.ts", tf)
        ok("P1_final_APPLIED", res.report.final_state == "APPLIED",
           res.report.reason[:60])
        ok("P1_context_recheck_present",
           any(s.step == "CONTEXT_RECHECK" and s.loop_state == "CONTINUE"
               for s in res.report.steps),
           "re-check CONTEXT_FRESH présent")
        ok("P1_not_committed",
           res.report.committed is False and res.report.pushed is False, "")
        ok("P1_fichier_modifie", sha256_file(root / tf) != sha_before, "")
        no_commit_no_push(root, "P1")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    # P2 — CONTEXTE PÉRIMÉ (SHA) construit sur un état, appliqué sur un
    #      autre -> BLOCKED. On simule en construisant le contexte via
    #      run_from_mission mais en modifiant le fichier entre la
    #      construction interne et l'apply : impossible à intercaler
    #      proprement -> on teste via P3 (modif après construction).
    #      Ici P2 teste le cas où le contexte est construit par
    #      build_mission_context PUIS le fichier change AVANT le run.
    # ============================================================
    print("\n[P2] Contexte construit puis fichier modifié -> BLOCKED")
    root, target = make_lab()
    try:
        tf = predicted_target(target)
        ctx = build_mission_context("M-P2", MISSION, target)

        # Dérive : on modifie le fichier APRÈS la construction du contexte.
        p = root / tf
        p.write_text(p.read_text(encoding="utf-8") + "\n// drift\n",
                     encoding="utf-8", newline="\n")

        def verify_unused(r: Path) -> tuple[bool, str]:
            return (True, "ne doit pas être appelé")

        mission = Mission(
            request_text=MISSION, target=target, relative_path=tf,
            intent=INTENT, action=action_for(tf),
            human_approval=bound_approval_loop(target, tf, INTENT, MISSION),
        )
        report = AgentLoop(mission, verify_unused, mission_context=ctx).run()
        ok("P2_final_BLOCKED", report.final_state == "BLOCKED",
           report.reason[:70])
        ok("P2_cause_context_stale", "CONTEXT_STALE" in report.reason, "")
        ok("P2_block_at_recheck",
           any(s.step == "CONTEXT_RECHECK" and s.loop_state == "BLOCK"
               for s in report.steps),
           "BLOCK au re-check")
        no_commit_no_push(root, "P2")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    # P3 — FICHIER MODIFIÉ APRÈS CONSTRUCTION via run_from_mission
    #      (le drift est injecté par le verify lui-même n'est pas
    #       possible ; on teste le re-check en modifiant un AUTRE
    #       fichier du contexte qui invalide la fraîcheur globale).
    # ============================================================
    print("\n[P3] Dérive d'un fichier du contexte -> BLOCKED")
    root, target = make_lab()
    try:
        ctx = build_mission_context("M-P3", MISSION, target)
        tf = ctx.relevant_files[0].path

        # Modifier un AUTRE fichier présent dans le contexte (s'il existe)
        # ou le même : toute divergence -> stale.
        other = None
        for rf in ctx.relevant_files:
            if rf.path != tf:
                other = rf.path
                break
        drift_path = other or tf
        dp = root / drift_path
        dp.write_text(dp.read_text(encoding="utf-8") + "\n// x\n",
                      encoding="utf-8", newline="\n")

        def verify_unused(r: Path) -> tuple[bool, str]:
            return (True, "ne doit pas être appelé")

        mission = Mission(
            request_text=MISSION, target=target, relative_path=tf,
            intent=INTENT, action=action_for(tf),
            human_approval=bound_approval_loop(target, tf, INTENT, MISSION),
        )
        report = AgentLoop(mission, verify_unused, mission_context=ctx).run()
        ok("P3_final_BLOCKED", report.final_state == "BLOCKED",
           report.reason[:70])
        ok("P3_cause_context_stale", "CONTEXT_STALE" in report.reason,
           f"drift={drift_path}")
        no_commit_no_push(root, "P3")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    # P4 — HEAD DIVERGENT après construction -> BLOCKED
    # ============================================================
    print("\n[P4] HEAD divergent après construction -> BLOCKED")
    root, target = make_lab()
    try:
        ctx = build_mission_context("M-P4", MISSION, target)
        tf = ctx.relevant_files[0].path

        # Nouveau commit -> HEAD change (fichiers inchangés en SHA mais
        # version.git_head capturé != HEAD courant).
        (root / "src" / "zz.ts").write_text("export const z = 1;\n",
                                             encoding="utf-8", newline="\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "head drift")
        target_v2 = target_at_head(root)

        def verify_unused(r: Path) -> tuple[bool, str]:
            return (True, "ne doit pas être appelé")

        mission = Mission(
            request_text=MISSION, target=target_v2, relative_path=tf,
            intent=INTENT, action=action_for(tf),
            human_approval=bound_approval_loop(target_v2, tf, INTENT, MISSION),
        )
        report = AgentLoop(mission, verify_unused, mission_context=ctx).run()
        ok("P4_final_BLOCKED", report.final_state == "BLOCKED",
           report.reason[:70])
        ok("P4_cause_head", "CONTEXT_STALE" in report.reason, report.reason[:70])
        # 2 commits ici (baseline + head drift) : on vérifie juste
        # qu'aucun TROISIÈME commit parasite n'a été créé par la boucle.
        count = git(root, "rev-list", "--count", "HEAD").stdout.strip()
        ok("P4_pas_de_commit_parasite", count == "2", f"commits={count}")
        ok("P4_aucun_remote", git(root, "remote").stdout.strip() == "", "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    # P5 — MISSION != AUTORITÉ : le client ne choisit pas le fichier.
    #      Une mission avec un chemin injecté ne cible jamais ce chemin.
    # ============================================================
    print("\n[P5] Mission != autorité (cible choisie par le contexte)")
    root, target = make_lab()
    try:
        attack = "applique sur ../../etc/passwd version"
        ctx = build_mission_context("M-P5", attack, target)
        # Les sources d'autorité sont des fichiers du dépôt, pas le chemin injecté.
        auth = ctx.authority_sources()
        ok("P5_pas_de_chemin_injecte",
           all(not a.startswith("..") for a in auth), str(auth))
        ok("P5_autorite_depuis_depot",
           all((root / a).resolve().is_relative_to(root.resolve())
               for a in auth) if auth else True,
           "sources confinées au dépôt")

        tf = predicted_target(target)

        def verify_pass(r: Path) -> tuple[bool, str]:
            c = (r / tf).read_text(encoding="utf-8")
            return ("version = '2.0'" in c, "ok")

        res = run_from_mission(
            "M-P5b", MISSION, target, INTENT, verify_pass,
            action=action_for(tf),
            human_approval=bound_approval_rfm("M-P5b", MISSION, target, INTENT, verify_pass),
        )
        ok("P5_cible_est_fichier_depot",
           res.report.scope == "src/version.ts", f"scope={res.report.scope}")
        no_commit_no_push(root, "P5")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    # P6 — AUCUN APPLY PARASITE : un BLOCK ne doit jamais toucher le disque
    # ============================================================
    print("\n[P6] Aucun apply parasite sur BLOCK")
    root, target = make_lab()
    try:
        tf = predicted_target(target)
        ctx = build_mission_context("M-P6", MISSION, target)
        sha_before = sha256_file(root / tf)
        # Drift -> doit BLOCK sans écrire.
        p = root / tf
        p.write_text(p.read_text(encoding="utf-8") + "\n// drift\n",
                     encoding="utf-8", newline="\n")
        sha_after_drift = sha256_file(root / tf)

        def verify_unused(r: Path) -> tuple[bool, str]:
            return (True, "ne doit pas être appelé")

        mission = Mission(
            request_text=MISSION, target=target, relative_path=tf,
            intent=INTENT, action=action_for(tf),
            human_approval=bound_approval_loop(target, tf, INTENT, MISSION),
        )
        report = AgentLoop(mission, verify_unused, mission_context=ctx).run()
        ok("P6_BLOCKED", report.final_state == "BLOCKED", "")
        # Le fichier ne doit avoir QUE le drift du test, pas d'apply en plus.
        ok("P6_pas_apply_parasite",
           sha256_file(root / tf) == sha_after_drift,
           "aucune écriture par la boucle")
        no_commit_no_push(root, "P6")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    print("\n" + "=" * 72)
    print(f"RÉSULTAT PHASE 2 : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print("Context -> Agent Loop branché. CONTEXT_STALE -> BLOCK (double check).")
    print("Cible déterminée par le contexte, jamais par le client.")
    print("Aucun LLM. Aucun apply hors D5.9. Aucun commit/push. MemoLib non touché.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
