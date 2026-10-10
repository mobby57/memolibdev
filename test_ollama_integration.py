"""
MemoLibDev — Test d'intégration Ollama RÉEL (lecture seule)
===========================================================

Premier essai avec un modèle local réel (qwen2.5-coder:1.5b-base), SANS
écriture MemoLib et SANS apply réel. Skippable si Ollama est absent.

Les 9 critères (brief) :
  O1  Ollama réellement appelé.
  O2  Résultat converti en PlannerResult.
  O3  Timeout R4 fonctionne AVEC Ollama (timeout court -> BLOCK).
  O4  Erreur Ollama (modèle inexistant) -> BLOCK.
  O5  Timeout Ollama -> BLOCK.
  O6  Aucune D5.9 déclenchée en cas d'échec.
  O7  Aucun fichier MemoLib modifié (sandbox éphémère uniquement).
  O8  Secret dans contexte -> non transmis au provider (BLOCK avant).
  O9  Les tests FakeProvider restent verts (non-régression — suite séparée).

Note : qwen2.5-coder:1.5b-base est un modèle BASE (non-instruct) : sa
sortie peut être non conforme. C'est acceptable — on teste la PLOMBERIE
fail-closed, pas la qualité du modèle. Le happy path (OK ou BLOCK) est
traité sans exiger une transformation parfaite ; les BLOCKS déterministes
(O3..O8) sont, eux, strictement exigés.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile
import time
import urllib.request

from project_target import ProjectTarget
from coder_authorization import ActionDossier, HumanApproval, AuthorityLevel
from d59_controlled_apply import sha256_file
from agent_loop import run_from_mission
from context.context_builder import build_mission_context
from llm.ollama_provider import OllamaProvider
from llm.llm_planner import derive_intent, PlannerResult


MODEL = "qwen2.5-coder:1.5b-base"
PASS: list[str] = []
FAIL: list[str] = []
SKIP = False


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f" :: {detail}" if detail else ""))


def ollama_up() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            import json
            data = json.load(r)
        names = {m.get("name") for m in data.get("models", [])}
        return MODEL in names
    except Exception:
        return False


def git(root: Path, *args):
    return subprocess.run(["git", "-C", str(root), *args],
                          text=True, capture_output=True, encoding="utf-8", errors="replace")


def make_lab(with_secret: bool = False):
    root = Path(tempfile.mkdtemp(prefix="memolibdev-ollama-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "o@memolibdev.local")
    git(root, "config", "user.name", "o")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.eol", "lf")
    (root / "src").mkdir()
    body = "export const version = '1.0';\n"
    if with_secret:
        body += "const KEY = 'sk-abcdefghijklmnopqrstuvwxyz0123';\n"
    (root / "src" / "version.ts").write_text(body, encoding="utf-8", newline="\n")
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
                         approved_at="2026-10-06T22:30:00+02:00",
                         authority_level=AuthorityLevel.L3_PROPOSE.value)


def action_for(rel):
    return ActionDossier("ACT-O", "PROPOSE_CODE_PATCH", rel, "MEDIUM", "REVERSIBLE_SANDBOX")


def predicted_target(target):
    ctx = build_mission_context("probe", MISSION, target)
    return ctx.relevant_files[0].path if ctx.relevant_files else ""


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — INTÉGRATION OLLAMA RÉEL (lecture seule)")
    print("=" * 72)

    if not ollama_up():
        print(f"\n[SKIP] Ollama absent ou modèle {MODEL} indisponible.")
        print("Test ignoré (skippable). Aucune régression.")
        return 0

    # ========================================================
    # O1 + O2 — Ollama réellement appelé + conversion PlannerResult
    # ========================================================
    print("\n[O1+O2] Appel réel + conversion PlannerResult")
    root, target = make_lab()
    try:
        ctx = build_mission_context("M-O1", MISSION, target)
        provider = OllamaProvider(model=MODEL, http_timeout=90.0)
        ok("O1_available", provider.available is True, "Ollama/modèle présents")
        pr = derive_intent(ctx, provider, timeout_s=120.0)
        ok("O2_is_planner_result", isinstance(pr, PlannerResult),
           f"status={pr.status}")
        # OK (si sortie conforme) ou BLOCK (si modèle base bruité) : les
        # deux prouvent l'appel + la conversion. Jamais autre chose.
        ok("O2_statut_valide", pr.status in {"OK", "BLOCK"}, pr.reason[:50])
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    # O3 + O5 — Timeout R4 avec Ollama (timeout très court -> BLOCK)
    # ========================================================
    print("\n[O3+O5] Timeout R4 avec Ollama -> BLOCK")
    root, target = make_lab()
    try:
        ctx = build_mission_context("M-O3", MISSION, target)
        provider = OllamaProvider(model=MODEL, http_timeout=90.0)
        t0 = time.time()
        pr = derive_intent(ctx, provider, timeout_s=0.5)   # 0.5s << génération
        elapsed = time.time() - t0
        ok("O3_timeout_BLOCK", not pr.ok, pr.reason[:60])
        ok("O3_cause_timeout", "timeout" in pr.reason.lower(), pr.reason[:60])
        ok("O5_borne_reelle", elapsed < 5.0, f"elapsed={elapsed:.2f}s")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    # O4 — Erreur Ollama (modèle inexistant) -> BLOCK
    # ========================================================
    print("\n[O4] Modèle inexistant -> BLOCK")
    root, target = make_lab()
    try:
        ctx = build_mission_context("M-O4", MISSION, target)
        bad = OllamaProvider(model="modele-inexistant-xyz:999", http_timeout=20.0)
        ok("O4_not_available", bad.available is False, "modèle absent détecté")
        pr = derive_intent(ctx, bad, timeout_s=30.0)
        ok("O4_BLOCK", not pr.ok, pr.reason[:50])
        ok("O4_cause_indispo", "indisponible" in pr.reason, "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    # O6 + O7 — Timeout dans la chaîne complète : aucune D5.9, fichier intact
    # ========================================================
    print("\n[O6+O7] Timeout chaîne -> aucune D5.9, fichier MemoLib(sandbox) intact")
    root, target = make_lab()
    try:
        tf = predicted_target(target)
        sha_before = sha256_file(root / tf)
        provider = OllamaProvider(model=MODEL, http_timeout=90.0)
        res = run_from_mission(
            "M-O6", MISSION, target, None, lambda r: (True, "x"),
            action=action_for(tf), human_approval=approval(),
            provider=provider, provider_timeout_s=0.5)   # timeout -> BLOCK
        ok("O6_BLOCKED", res.report.final_state == "BLOCKED", res.report.reason[:50])
        ok("O6_pas_de_D59",
           not any(s.step == "D5.9_APPLY" for s in res.report.steps),
           "D5.9 jamais atteint")
        ok("O7_fichier_intact", sha256_file(root / tf) == sha_before,
           "aucune écriture")
        count = git(root, "rev-list", "--count", "HEAD").stdout.strip()
        ok("O6_aucun_commit", count == "1", f"commits={count}")
        ok("O6_aucun_remote", git(root, "remote").stdout.strip() == "", "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    # O8 — Secret dans contexte -> non transmis (BLOCK avant provider)
    # ========================================================
    print("\n[O8] Secret -> non transmis au provider")
    root, target = make_lab(with_secret=True)
    try:
        ctx = build_mission_context("M-O8", MISSION, target)
        provider = OllamaProvider(model=MODEL, http_timeout=90.0)
        t0 = time.time()
        pr = derive_intent(ctx, provider, timeout_s=120.0)
        elapsed = time.time() - t0
        ok("O8_BLOCK", not pr.ok, pr.reason[:50])
        ok("O8_cause_secret", "secret détecté" in pr.reason, "")
        # Preuve indirecte de non-transmission : le BLOCK est quasi-instantané
        # (scan AVANT appel réseau), pas après une génération lente.
        ok("O8_block_avant_appel", elapsed < 5.0,
           f"BLOCK en {elapsed:.2f}s (avant tout appel Ollama)")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ========================================================
    print("\n" + "=" * 72)
    print(f"RÉSULTAT OLLAMA : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print("Ollama réel appelé en lecture seule. Fail-closed vérifié.")
    print("Timeout R4 opère sur Ollama. Aucune D5.9 en échec. Secret non transmis.")
    print("Aucune écriture MemoLib. Aucun commit/push/apply.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
