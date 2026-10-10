"""
MemoLibDev — E2E-REAL-SANDBOX : chaîne complète avec Ollama réel
================================================================

Valide la chaîne complète de bout en bout avec un VRAI modèle local
(qwen2.5-coder:1.5b-base), ENTIÈREMENT sur sandbox éphémère. Le dépôt
MemoLib réel n'est JAMAIS touché. L'humain reste l'autorité finale.

Modèle : 1.5b (volontairement, pour tester la SÉCURITÉ de la chaîne et
non la qualité du modèle). Non-déterministe : la chaîne doit soit
ABOUTIR proprement (APPLIED si le modèle coopère), soit BLOQUER
proprement (si la sortie n'est pas conforme). Jamais d'état incohérent.

  E1  Mission -> Context -> Ollama -> proposition -> HUMAN APPROVAL
      -> D5.8 -> sandbox/D5.8 gates -> D5.9 apply -> verify
      => APPLIED (coopère) OU BLOCKED (non conforme) ; jamais autre chose.
  E2  Human gate : SANS approbation -> AWAIT_HUMAN, aucune écriture.
  E3  Verify FAIL -> ROLLED_BACK (SHA restauré), même avec LLM réel.
  E4  Jamais de commit/push ; D5.9 seule voie d'écriture ; MemoLib intact.

Skippable si Ollama/modèle absent.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import urllib.request

from project_target import ProjectTarget
from coder_authorization import ActionDossier, HumanApproval, AuthorityLevel
from d59_controlled_apply import sha256_file
from agent_loop import run_from_mission
from context.context_builder import build_mission_context
from llm.ollama_provider import OllamaProvider


MODEL = "qwen2.5-coder:1.5b-base"
PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def ollama_up() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            data = json.load(r)
        return MODEL in {m.get("name") for m in data.get("models", [])}
    except Exception:
        return False


def git(root: Path, *a):
    return subprocess.run(["git", "-C", str(root), *a], text=True,
                          capture_output=True, encoding="utf-8", errors="replace")


def make_lab():
    root = Path(tempfile.mkdtemp(prefix="memolibdev-e2e-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "e2e@memolibdev.local")
    git(root, "config", "user.name", "e2e")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.eol", "lf")
    (root / "src").mkdir()
    (root / "src" / "version.ts").write_text(
        "export const version = '1.0';\n", encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "baseline")
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    fp = hashlib.sha256(f"{root}|main|{head}".encode()).hexdigest()[:16]
    target = ProjectTarget(
        path=root, git_root=root,
        head=git(root, "rev-parse", "--short", "HEAD").stdout.strip(),
        head_full=head, branch="main", fingerprint=fp, env_var="MEMOLIBDEV_TARGET")
    return root, target


MISSION = "remplace la version 1.0 par 2.0 dans version.ts"


def approval():
    return HumanApproval(approved=True, approver="moro",
                         approved_at="2026-10-06T23:00:00+02:00",
                         authority_level=AuthorityLevel.L3_PROPOSE.value)


def action_for(rel):
    return ActionDossier("ACT-E2E", "PROPOSE_CODE_PATCH", rel, "MEDIUM", "REVERSIBLE_SANDBOX")


def predicted_target(target):
    ctx = build_mission_context("probe", MISSION, target)
    return ctx.relevant_files[0].path if ctx.relevant_files else ""


def no_commit_no_push(root, name):
    count = git(root, "rev-list", "--count", "HEAD").stdout.strip()
    ok(f"{name}_aucun_commit", count == "1", f"commits={count}")
    ok(f"{name}_aucun_remote", git(root, "remote").stdout.strip() == "", "")


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — E2E-REAL-SANDBOX (Ollama 1.5b, chaîne complète)")
    print("=" * 72)

    if not ollama_up():
        print(f"\n[SKIP] Ollama/modèle {MODEL} absent. Test ignoré.")
        return 0

    # ========================================================
    # E1 — Chaîne complète avec human approval
    #      APPLIED si le modèle coopère, sinon BLOCKED propre.
    # ========================================================
    print("\n[E1] Mission -> LLM réel -> approval -> D5.9 -> verify")
    root, target = make_lab()
    try:
        tf = predicted_target(target)
        sha_before = sha256_file(root / tf)

        def verify_pass(r: Path) -> tuple[bool, str]:
            return ("version = '2.0'" in (r / tf).read_text(encoding="utf-8"),
                    "marqueur 2.0")

        provider = OllamaProvider(model=MODEL, http_timeout=120.0)
        res = run_from_mission(
            "E2E-1", MISSION, target, None, verify_pass,
            action=action_for(tf), human_approval=approval(),
            provider=provider, provider_timeout_s=150.0)

        final = res.report.final_state
        print(f"    -> final_state={final} | {res.report.reason[:70]}")
        # Terminal propre uniquement :
        ok("E1_terminal_propre",
           final in {"APPLIED", "BLOCKED", "ROLLED_BACK", "NO_PATCH_POSSIBLE"},
           final)
        if final == "APPLIED":
            ok("E1_coopere_APPLIED",
               sha256_file(root / tf) != sha_before, "modèle a coopéré -> modifié")
            ok("E1_not_committed",
               res.report.committed is False and res.report.pushed is False, "")
        else:
            # BLOCK propre : la cible NE DOIT PAS avoir changé.
            ok("E1_block_propre_fichier_intact",
               sha256_file(root / tf) == sha_before,
               "non conforme -> aucune écriture")
        no_commit_no_push(root, "E1")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    # E2 — Human gate : SANS approbation -> AWAIT_HUMAN, aucune écriture
    # ========================================================
    print("\n[E2] Sans approbation -> AWAIT_HUMAN (human gate)")
    root, target = make_lab()
    try:
        tf = predicted_target(target)
        sha_before = sha256_file(root / tf)
        provider = OllamaProvider(model=MODEL, http_timeout=120.0)
        res = run_from_mission(
            "E2E-2", MISSION, target, None, lambda r: (True, "x"),
            action=None, human_approval=None,     # pas d'approbation
            provider=provider, provider_timeout_s=150.0)
        ok("E2_AWAIT_HUMAN", res.report.final_state == "AWAIT_HUMAN",
           res.report.reason[:50])
        ok("E2_fichier_intact", sha256_file(root / tf) == sha_before, "")
        no_commit_no_push(root, "E2")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    # E3 — Verify FAIL -> ROLLED_BACK (si le modèle coopère et qu'on
    #      applique, un verify qui échoue doit déclencher le rollback).
    #      Si le modèle ne coopère pas (BLOCK), le test reste cohérent.
    # ========================================================
    print("\n[E3] Verify FAIL -> ROLLED_BACK (SHA restauré)")
    root, target = make_lab()
    try:
        tf = predicted_target(target)
        sha_before = sha256_file(root / tf)

        def verify_fail(r: Path) -> tuple[bool, str]:
            return (False, "verify volontairement échoué")

        provider = OllamaProvider(model=MODEL, http_timeout=120.0)
        res = run_from_mission(
            "E2E-3", MISSION, target, None, verify_fail,
            action=action_for(tf), human_approval=approval(),
            provider=provider, provider_timeout_s=150.0)
        final = res.report.final_state
        print(f"    -> final_state={final}")
        if final == "ROLLED_BACK":
            ok("E3_rolled_back", res.report.rolled_back is True, "")
            ok("E3_SHA_restaure", sha256_file(root / tf) == sha_before,
               "SHA initial restauré")
            porcelain = git(root, "status", "--porcelain").stdout.strip()
            ok("E3_working_tree_propre", porcelain == "", f"status={porcelain!r}")
        else:
            # Modèle non coopératif -> BLOCK avant apply : acceptable,
            # la cible doit rester intacte.
            ok("E3_block_ou_rollback_coherent",
               final in {"BLOCKED", "NO_PATCH_POSSIBLE"}
               and sha256_file(root / tf) == sha_before,
               f"{final} + fichier intact")
        no_commit_no_push(root, "E3")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    print("\n" + "=" * 72)
    print(f"RÉSULTAT E2E : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print("Chaîne complète E2E avec Ollama réel, sur sandbox éphémère.")
    print("Human gate obligatoire. Verify FAIL -> rollback. D5.9 seule voie "
          "d'écriture.")
    print("MemoLib réel JAMAIS touché. Aucun commit/push.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
