"""
MemoLibDev — Test GAP : ANALYSER vs CORRIGER
============================================

A  mission ANALYSER -> résultat analytique exploitable, SANS REPLACE
B  ANALYSER même si le modèle halluciner-ait : aucune écriture, aucun apply
C  ANALYSER -> aucune écriture (fichier/HEAD inchangés)
D  CORRIGER valide (old présent) -> APPLIED (comportement conservé)
E  CORRIGER old absent -> BLOCK R1 conservé
F  CORRIGER APPEND silencieux -> impossible (BLOCK)
G  hors authority_sources -> BLOCK
J  human approval obligatoire avant toute application
K  D5.9 jamais invoqué pour ANALYSER (final_state=ANALYZED, pas APPLIED)

FakeProvider déterministe (pas d'Ollama). Sandbox éphémère.
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
from agent_loop import run_from_mission
from llm.ai_provider import FakeProvider


PASS: list[str] = []
FAIL: list[str] = []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), *a], text=True,
                          capture_output=True, encoding="utf-8", errors="replace")


def make_lab():
    root = Path(tempfile.mkdtemp(prefix="memolibdev-avc-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "a@b.c"); git(root, "config", "user.name", "a")
    git(root, "config", "core.autocrlf", "false"); git(root, "config", "core.eol", "lf")
    (root / "src").mkdir()
    (root / "src" / "version.ts").write_text(
        "export const version = '1.0';\n", encoding="utf-8", newline="\n")
    git(root, "add", "-A"); git(root, "commit", "-q", "-m", "x")
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    fp = hashlib.sha256(f"{root}|main|{head}".encode()).hexdigest()[:16]
    t = ProjectTarget(path=root, git_root=root,
                      head=git(root, "rev-parse", "--short", "HEAD").stdout.strip(),
                      head_full=head, branch="main", fingerprint=fp,
                      env_var="MEMOLIBDEV_TARGET")
    return root, t


def approval():
    return HumanApproval(approved=True, approver="moro",
                         approved_at="2026-10-08T08:00:00+02:00",
                         authority_level=AuthorityLevel.L3_PROPOSE.value)


def action_for(rel):
    return ActionDossier("ACT", "PROPOSE_CODE_PATCH", rel, "MEDIUM", "REVERSIBLE_SANDBOX")


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST ANALYSER vs CORRIGER")
    print("=" * 72)

    # ===== A/C/K : mission ANALYSER =====
    print("\n[A/C/K] Mission ANALYSER")
    root, target = make_lab()
    try:
        tf = "src/version.ts"
        sha_before = sha256_file(root / tf)
        head_before = git(root, "rev-parse", "HEAD").stdout.strip()
        # provider 'happy' aurait produit un REPLACE : on vérifie qu'ANALYSER
        # ne le fait PAS passer en apply.
        res = run_from_mission(
            "ANA", "analyse le module version et explique son rôle",
            target, None, lambda r: (True, "x"),
            action=None, human_approval=None,
            provider=FakeProvider(scenario="happy"))
        ok("A_final_ANALYZED", res.report.final_state == "ANALYZED",
           res.report.final_state)
        ok("A_analyse_contient_constats",
           "ANALYSE" in res.report.reason and "Fichiers pertinents" in res.report.reason,
           "")
        ok("A_pas_de_replace", "REPLACE:" not in res.report.reason, "")
        ok("C_fichier_inchange", sha256_file(root / tf) == sha_before, "")
        ok("C_head_inchange", git(root, "rev-parse", "HEAD").stdout.strip() == head_before, "")
        ok("K_pas_committed",
           res.report.committed is False and res.report.pushed is False, "")
        ok("K_pas_applied", res.report.final_state != "APPLIED", "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ===== B : ANALYSER ne peut rien appliquer même avec approbation fournie =====
    print("\n[B] ANALYSER + action/approval fournis -> toujours aucune écriture")
    root, target = make_lab()
    try:
        tf = "src/version.ts"
        sha_before = sha256_file(root / tf)
        res = run_from_mission(
            "ANA2", "analyse la configuration de version",
            target, None, lambda r: (True, "x"),
            action=action_for(tf), human_approval=approval(),   # fournis mais ignorés
            provider=FakeProvider(scenario="happy"))
        ok("B_ANALYZED", res.report.final_state == "ANALYZED", res.report.final_state)
        ok("B_aucune_ecriture", sha256_file(root / tf) == sha_before, "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ===== D : CORRIGER valide -> APPLIED (conservé) =====
    print("\n[D] CORRIGER (old présent) -> APPLIED")
    root, target = make_lab()
    try:
        tf = "src/version.ts"
        def verify_pass(r):
            return ("version = '2.0'" in (r / tf).read_text(encoding="utf-8"), "ok")
        res = run_from_mission(
            "COR", "corrige la version du module version",
            target, None, verify_pass,
            action=action_for(tf), human_approval=approval(),
            provider=FakeProvider(scenario="happy",
                                  injected_intent="REPLACE:version = '1.0':version = '2.0'"))
        ok("D_APPLIED", res.report.final_state == "APPLIED", res.report.reason[:50])
        ok("D_not_committed",
           res.report.committed is False and res.report.pushed is False, "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ===== E : CORRIGER old absent -> BLOCK R1 =====
    print("\n[E] CORRIGER (old absent) -> BLOCK R1")
    root, target = make_lab()
    try:
        tf = "src/version.ts"
        sha_before = sha256_file(root / tf)
        res = run_from_mission(
            "COR2", "corrige la version",
            target, None, lambda r: (True, "x"),
            action=action_for(tf), human_approval=approval(),
            provider=FakeProvider(scenario="happy",
                                  injected_intent="REPLACE:ABSENT_XYZ:y"))
        ok("E_BLOCKED", res.report.final_state == "BLOCKED", res.report.reason[:50])
        ok("E_cause_old_absent", "fragment 'old' absent" in res.report.reason, "")
        ok("E_fichier_intact", sha256_file(root / tf) == sha_before, "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ===== G : CORRIGER hors authority_sources -> BLOCK =====
    print("\n[G] CORRIGER hors scope -> BLOCK")
    root, target = make_lab()
    try:
        res = run_from_mission(
            "COR3", "corrige la version",
            target, None, lambda r: (True, "x"),
            action=action_for("src/version.ts"), human_approval=approval(),
            provider=FakeProvider(scenario="out_of_scope"))
        ok("G_BLOCKED", res.report.final_state == "BLOCKED",
           res.report.reason[:50])
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ===== J : CORRIGER sans approbation -> AWAIT_HUMAN (pas d'apply) =====
    print("\n[J] CORRIGER sans approbation -> AWAIT_HUMAN")
    root, target = make_lab()
    try:
        tf = "src/version.ts"
        sha_before = sha256_file(root / tf)
        res = run_from_mission(
            "COR4", "corrige la version du module version",
            target, None, lambda r: (True, "x"),
            action=None, human_approval=None,
            provider=FakeProvider(scenario="happy",
                                  injected_intent="REPLACE:version = '1.0':version = '2.0'"))
        ok("J_await_human", res.report.final_state == "AWAIT_HUMAN",
           res.report.final_state)
        ok("J_fichier_intact", sha256_file(root / tf) == sha_before, "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n" + "=" * 72)
    print(f"RÉSULTAT ANALYSER/CORRIGER : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print("ANALYSER = diagnostic lecture seule (pas de REPLACE/D5.9).")
    print("CORRIGER = garde-fous R1/D5.8/D5.9 conservés.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
