"""
MemoLibDev — R2 : Test hiérarchie d'autorité (défense en profondeur)
====================================================================

Prouve que `authority_sources()` du planner LLM n'est qu'un PRÉ-FILTRE
non-autoritaire, et que l'autorité RÉELLE de cible/scope/version reste
D6.1 (FileTarget) + D5.8 (authorize/guardrail) + D5.9 (pre_apply).

Approche : on CONTOURNE le planner (on n'appelle pas derive_intent) et
on injecte directement des cibles incohérentes/forgées dans la chaîne
D5/D6. Elles doivent être bloquées malgré l'absence de pré-filtre.

Scénarios :
  R2.1  D6.1 bloque une cible hors périmètre          (resolve_file_target)
  R2.2  D6.1 bloque une cible .git                     (resolve_file_target)
  R2.3  D5.8 authorize REJETTE action.target_path != scope résolu
  R2.4  D5.8 authorize REJETTE un scope (allowed_paths) incohérent
  R2.5  Agent Loop direct : relative_path hors périmètre -> BLOCKED
  R2.6  Agent Loop direct : action forgée (target_path != fichier) -> BLOCKED
  R2.7  authority_sources() = projection lecture seule, ne crée pas d'autorité

Aucun Ollama. Aucun commit/push/apply hors D5.9. Sandbox éphémère.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile

from project_target import ProjectTarget
from file_target import resolve_file_target, FileTargetError
from coder_authorization import (
    authorize, AuthorizationStatus, ActionDossier, HumanApproval, AuthorityLevel,
)
from agent_loop import AgentLoop, Mission
from context.context_builder import build_mission_context

# Imports pour construire des entrées D5.6 directes (contourner le planner).
from evidence_resolver_v2_2 import EvidenceRecord, EvidenceResult, EvidenceStatus, content_sha256
from import_provenance import ProvenanceResult, ProvenanceStatus


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
    root = Path(tempfile.mkdtemp(prefix="memolibdev-r2-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "r2@memolibdev.local")
    git(root, "config", "user.name", "r2")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.eol", "lf")
    (root / "src").mkdir()
    (root / "src" / "version.ts").write_text(
        "export const version = '1.0';\n", encoding="utf-8", newline="\n")
    (root / "src" / "other.ts").write_text(
        "export const other = 1;\n", encoding="utf-8", newline="\n")
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
    return HumanApproval(
        approved=True, approver="moro",
        approved_at="2026-10-06T20:00:00+02:00",
        authority_level=AuthorityLevel.L3_PROPOSE.value,
    )


def no_commit_no_push(root: Path, name: str) -> None:
    count = git(root, "rev-list", "--count", "HEAD").stdout.strip()
    ok(f"{name}_aucun_commit", count == "1", f"commits={count}")
    ok(f"{name}_aucun_remote", git(root, "remote").stdout.strip() == "", "")


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — R2 : HIÉRARCHIE D'AUTORITÉ (défense en profondeur)")
    print("=" * 72)

    root, target = make_lab()
    try:
        # ========================================================
        # R2.1 — D6.1 bloque une cible hors périmètre
        # ========================================================
        print("\n[R2.1] D6.1 bloque hors périmètre")
        try:
            resolve_file_target("../../etc/passwd", target)
            ok("R2_1_hors_perimetre_BLOCK", False, "aucune erreur !")
        except FileTargetError as e:
            ok("R2_1_hors_perimetre_BLOCK", True, str(e)[:50])

        # ========================================================
        # R2.2 — D6.1 bloque une cible .git
        # ========================================================
        print("\n[R2.2] D6.1 bloque .git")
        try:
            resolve_file_target(".git/config", target)
            ok("R2_2_git_BLOCK", False, "aucune erreur !")
        except FileTargetError as e:
            ok("R2_2_git_BLOCK", True, str(e)[:50])

        # ========================================================
        # R2.3 — D5.8 authorize REJETTE action.target_path != scope résolu
        #        (on contourne le planner : evidence/provenance pointent
        #         vers version.ts, mais l'action prétend viser other.ts)
        # ========================================================
        print("\n[R2.3] D5.8 rejette action incohérente")
        rel = "src/version.ts"
        content = (root / rel).read_text(encoding="utf-8")
        sha = content_sha256(content)
        evidence = EvidenceRecord(
            path=rel, normalized_path=rel, git_root=str(root),
            head=target.head_full, repository_fingerprint=target.fingerprint,
            content_sha256=sha, size=len(content.encode("utf-8")), content=content,
        )
        ev_result = EvidenceResult(
            status=EvidenceStatus.ACCEPTED, query=rel, path=rel,
            line_start=1, line_end=1, evidence=content, score=100, reason="ok")
        prov = ProvenanceResult(
            status=ProvenanceStatus.RESOLVED, source_path=rel, symbol=rel,
            module_specifier=rel, resolved_path=rel, reason="ok")
        forged_action = ActionDossier(
            action_id="ACT-R2", action_type="PROPOSE_CODE_PATCH",
            target_path="src/other.ts",   # <-- INCOHÉRENT avec le scope
            risk="MEDIUM", reversibility="REVERSIBLE_SANDBOX")
        auth = authorize(
            target=target, evidence=evidence, evidence_result=ev_result,
            provenance=prov, allowed_paths=[rel],
            action=forged_action, human_approval=approval())
        ok("R2_3_action_incoherente_REJECT",
           auth.status == AuthorizationStatus.REJECTED.value, auth.reason[:50])

        # ========================================================
        # R2.4 — D5.8 authorize REJETTE un scope (allowed_paths) incohérent
        #        (evidence version.ts mais allowed_paths = other.ts)
        # ========================================================
        print("\n[R2.4] D5.8 rejette scope incohérent")
        good_action = ActionDossier(
            action_id="ACT-R2b", action_type="PROPOSE_CODE_PATCH",
            target_path=rel, risk="MEDIUM", reversibility="REVERSIBLE_SANDBOX")
        auth2 = authorize(
            target=target, evidence=evidence, evidence_result=ev_result,
            provenance=prov, allowed_paths=["src/other.ts"],  # <-- hors scope
            action=good_action, human_approval=approval())
        ok("R2_4_scope_incoherent_REJECT",
           auth2.status == AuthorizationStatus.REJECTED.value, auth2.reason[:50])

        # ========================================================
        # R2.5 — Agent Loop direct (sans planner) : relative_path hors
        #        périmètre -> BLOCKED par D6.1 au PLAN
        # ========================================================
        print("\n[R2.5] Agent Loop direct : cible hors périmètre -> BLOCKED")
        mission_oob = Mission(
            request_text="forçage hors périmètre", target=target,
            relative_path="../../etc/passwd", intent="REPLACE:a:b",
            action=ActionDossier("A", "PROPOSE_CODE_PATCH", "../../etc/passwd",
                                 "MEDIUM", "REVERSIBLE_SANDBOX"),
            human_approval=approval())
        rep5 = AgentLoop(mission_oob, lambda r: (True, "x")).run()
        ok("R2_5_BLOCKED", rep5.final_state == "BLOCKED", rep5.reason[:50])
        no_commit_no_push(root, "R2_5")

        # ========================================================
        # R2.6 — Agent Loop direct : action forgée (target_path != fichier
        #        réellement résolu) -> BLOCKED par D5.8 à APPROVAL
        # ========================================================
        print("\n[R2.6] Agent Loop direct : action forgée -> BLOCKED")
        sha_before = content_sha256((root / "src" / "version.ts").read_text(encoding="utf-8"))
        mission_forged = Mission(
            request_text="action forgée", target=target,
            relative_path="src/version.ts",          # cible réelle
            intent="REPLACE:version = '1.0':version = '2.0'",
            action=ActionDossier("A2", "PROPOSE_CODE_PATCH",
                                 "src/other.ts",      # <-- MENT sur la cible
                                 "MEDIUM", "REVERSIBLE_SANDBOX"),
            human_approval=approval())
        rep6 = AgentLoop(mission_forged, lambda r: (True, "x")).run()
        ok("R2_6_BLOCKED", rep6.final_state == "BLOCKED", rep6.reason[:50])
        ok("R2_6_fichier_intact",
           content_sha256((root / "src" / "version.ts").read_text(encoding="utf-8")) == sha_before,
           "aucune écriture")
        no_commit_no_push(root, "R2_6")

        # ========================================================
        # R2.7 — authority_sources() = projection lecture seule
        # ========================================================
        print("\n[R2.7] authority_sources ne crée pas d'autorité")
        ctx = build_mission_context("M-R2", "modifier version", target)
        srcs = ctx.authority_sources()
        # (a) ce sont exactement des chemins de fichiers inspectés
        ok("R2_7_projection_fichiers",
           all(s in [rf.path for rf in ctx.relevant_files] for s in srcs), str(srcs))
        # (b) appeler authority_sources n'écrit rien / ne change pas HEAD
        head_a = git(root, "rev-parse", "HEAD").stdout.strip()
        _ = ctx.authority_sources()
        head_b = git(root, "rev-parse", "HEAD").stdout.strip()
        ok("R2_7_pas_d_effet", head_a == head_b, "HEAD inchangé")
        # (c) un chemin présent dans authority_sources ne « pré-autorise »
        #     pas une action incohérente : D5.8 bloque quand même (déjà
        #     prouvé en R2.3/R2.4) — on relie explicitement.
        ok("R2_7_prefiltre_non_autoritaire",
           auth.status == AuthorizationStatus.REJECTED.value
           and auth2.status == AuthorizationStatus.REJECTED.value,
           "pré-filtre != autorité (D5.8 décide)")

        # ========================================================
        print("\n" + "=" * 72)
        print(f"RÉSULTAT R2 : {len(PASS)} PASS / {len(FAIL)} FAIL")
        if FAIL:
            print("ÉCHECS :", ", ".join(FAIL))
        print("=" * 72)
        print("authority_sources = PRÉ-FILTRE non-autoritaire.")
        print("D6.1 FileTarget + D5.8 = autorité réelle de cible/scope/version.")
        print("Défense en profondeur : cible incohérente bloquée même sans pré-filtre.")
        return 0 if not FAIL else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
