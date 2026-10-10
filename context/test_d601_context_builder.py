"""
MemoLibDev — D6.0.1 : Test Context Builder (sandbox éphémère)
=============================================================

Prouve que le Context Builder est déterministe, versionné, borné et
invalidable, SANS LLM, SANS apply, SANS commit/push.

Couverture (ta liste) :
  - contexte déterministe (deux constructions identiques)
  - SHA présents (texte + octets, distincts conservés)
  - Git HEAD présent
  - fichiers hors scope exclus (confinement git_root)
  - .git exclu
  - fichier modifié -> CONTEXT_STALE
  - HEAD changé -> CONTEXT_STALE
  - contexte trop volumineux -> réduction bornée
  - aucune donnée client (mission texte) ne devient autorité
  - aucun apply / commit / push / changement de HEAD

MemoLib jamais touché (sandbox éphémère uniquement).
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile

from project_target import ProjectTarget
from context import (
    build_mission_context, is_stale, inspect_target,
    capture_file_version, text_sha256, byte_sha256_of_file,
    apply_budget,
)
from context.mission_context import HistoryEntry


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
    root = Path(tempfile.mkdtemp(prefix="memolibdev-d601-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "d601@memolibdev.local")
    git(root, "config", "user.name", "d601")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.eol", "lf")

    (root / "src").mkdir()
    (root / "src" / "auth.ts").write_text(
        "export function login() {\n  return 'auth token';\n}\n",
        encoding="utf-8", newline="\n",
    )
    (root / "src" / "helper.py").write_text(
        "def auth_helper():\n    return 'auth'\n",
        encoding="utf-8", newline="\n",
    )
    (root / "README.md").write_text(
        "# Project\nUnrelated documentation.\n",
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


def new_head(root: Path) -> ProjectTarget:
    """Fait un nouveau commit pour obtenir un HEAD différent."""
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    fp = hashlib.sha256(f"{root}|main|{head}".encode()).hexdigest()[:16]
    return ProjectTarget(
        path=root, git_root=root,
        head=git(root, "rev-parse", "--short", "HEAD").stdout.strip(),
        head_full=head, branch="main", fingerprint=fp,
        env_var="MEMOLIBDEV_TARGET",
    )


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — D6.0.1 CONTEXT BUILDER (sandbox éphémère)")
    print("=" * 72)

    root, target = make_lab()
    head_before = git(root, "rev-parse", "HEAD").stdout.strip()

    try:
        # ============================================================
        # A — Construction de base
        # ============================================================
        print("\n[A] Construction de base")
        ctx = build_mission_context(
            "M-0001", "corrige la fonction login auth", target,
        )
        ok("A1_mission_id", ctx.mission_id == "M-0001", ctx.mission_id)
        ok("A2_mission_text_conserve",
           ctx.mission_text == "corrige la fonction login auth", "")
        ok("A3_relevant_non_vide", len(ctx.relevant_files) > 0,
           f"{len(ctx.relevant_files)} fichiers")
        ok("A4_git_head_present",
           ctx.project.git_head == target.head_full and ctx.project.git_head != "",
           ctx.project.git_head[:12])
        ok("A5_branch_present", ctx.project.branch == "main", ctx.project.branch)
        ok("A6_fingerprint_present",
           ctx.project.fingerprint == target.fingerprint, "")
        ok("A7_capabilities", any("code_adapter" in c for c in ctx.capabilities),
           str(ctx.capabilities))
        ok("A8_constraints",
           "aucun commit" in ctx.constraints and "aucun push" in ctx.constraints,
           "")

        # ============================================================
        # B — SHA présents, deux conventions distinctes conservées
        # ============================================================
        print("\n[B] SHA (texte + octets)")
        rf = ctx.relevant_files[0]
        ok("B1_text_sha_present", len(rf.version.text_sha256) == 64, "")
        ok("B2_byte_sha_present", len(rf.version.byte_sha256) == 64, "")
        ok("B3_head_dans_version", rf.version.git_head == target.head_full, "")
        # Pour un fichier LF-only ASCII, texte==octets ; mais les deux
        # champs existent séparément (non fusionnés).
        ok("B4_deux_champs_distincts",
           hasattr(rf.version, "text_sha256") and hasattr(rf.version, "byte_sha256"),
           "deux conventions conservées")
        # Evidence porte aussi les deux SHA.
        ev = ctx.evidence[0]
        ok("B5_evidence_text_sha", len(ev.text_sha256) == 64, "")
        ok("B6_evidence_byte_sha", len(ev.byte_sha256) == 64, "")
        ok("B7_evidence_source", ev.source_path == rf.path, "")

        # Vérif indépendante : les SHA capturés = recalcul direct.
        abs_rf = root / rf.path
        ok("B8_text_sha_exact",
           rf.version.text_sha256 == text_sha256(
               abs_rf.read_text(encoding="utf-8")),
           "")
        ok("B9_byte_sha_exact",
           rf.version.byte_sha256 == byte_sha256_of_file(abs_rf), "")

        # ============================================================
        # C — Déterminisme
        # ============================================================
        print("\n[C] Déterminisme")
        ctx2 = build_mission_context(
            "M-0001", "corrige la fonction login auth", target,
        )
        ok("C1_meme_fichiers",
           [f.path for f in ctx.relevant_files] ==
           [f.path for f in ctx2.relevant_files],
           "ordre identique")
        ok("C2_memes_sha",
           [f.version.text_sha256 for f in ctx.relevant_files] ==
           [f.version.text_sha256 for f in ctx2.relevant_files],
           "SHA identiques")
        ok("C3_memes_scores",
           [f.score for f in ctx.relevant_files] ==
           [f.score for f in ctx2.relevant_files],
           "scores identiques")

        # ============================================================
        # D — Confinement : hors scope exclu, .git exclu
        # ============================================================
        print("\n[D] Confinement")
        inspection = inspect_target(target)
        paths = [f.path for f in inspection.files]
        ok("D1_git_exclu",
           not any(".git/" in p or p.startswith(".git") for p in paths),
           "aucun .git")
        ok("D2_dans_scope",
           all(not p.startswith("..") for p in paths), "aucun ../")
        # Un fichier hors git_root ne peut pas apparaître.
        ok("D3_tous_relatifs",
           all((root / p).resolve().is_relative_to(root.resolve())
               for p in paths),
           "tous sous git_root")
        # node_modules / __pycache__ ignorés
        (root / "node_modules").mkdir(exist_ok=True)
        (root / "node_modules" / "x.js").write_text("x", encoding="utf-8")
        insp2 = inspect_target(target)
        ok("D4_node_modules_exclu",
           not any("node_modules" in f.path for f in insp2.files),
           "node_modules ignoré")

        # ============================================================
        # E — Invalidation : fichier modifié -> CONTEXT_STALE
        # ============================================================
        print("\n[E] CONTEXT_STALE")
        fresh = is_stale(ctx, target)
        ok("E1_frais_avant", fresh.stale is False, fresh.status)

        # Modifier un fichier du contexte (working tree, pas de commit).
        target_file = root / rf.path
        original = target_file.read_text(encoding="utf-8")
        target_file.write_text(original + "\n// drift\n", encoding="utf-8",
                               newline="\n")
        stale = is_stale(ctx, target)
        ok("E2_stale_apres_modif", stale.stale is True, stale.status)
        ok("E3_stale_status", stale.status == "CONTEXT_STALE", stale.status)
        ok("E4_fichier_diverge_liste", rf.path in stale.diverged_files,
           str(stale.diverged_files))
        # Restaurer (working tree) pour la suite.
        target_file.write_text(original, encoding="utf-8", newline="\n")
        ok("E5_frais_apres_restauration", is_stale(ctx, target).stale is False, "")

        # ============================================================
        # F — HEAD changé -> CONTEXT_STALE
        # ============================================================
        print("\n[F] HEAD divergent -> STALE")
        (root / "src" / "newfile.ts").write_text(
            "export const x = 1;\n", encoding="utf-8", newline="\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "second commit")
        target_v2 = new_head(root)
        ok("F1_head_change", target_v2.head_full != target.head_full, "")
        stale_head = is_stale(ctx, target_v2)
        ok("F2_stale_sur_head", stale_head.stale is True, stale_head.status)

        # ============================================================
        # G — Budget : contexte trop volumineux -> réduction
        # ============================================================
        print("\n[G] Budget / réduction")
        big_candidates = [
            {"path": f"src/f{i}.ts", "score": 100 - i,
             "preview": "X" * 5000}
            for i in range(20)
        ]
        budget = apply_budget(big_candidates, max_context_chars=8000,
                              max_files=12, max_file_chars=2500)
        ok("G1_reduit", budget.reduced is True, "réduction appliquée")
        ok("G2_borne_fichiers", budget.included_count <= 12,
           f"inclus={budget.included_count}")
        ok("G3_borne_chars", budget.total_chars <= 8000,
           f"chars={budget.total_chars}")
        ok("G4_exclus_traces", budget.excluded_count > 0,
           f"exclus={budget.excluded_count}")
        ok("G5_ordre_par_score",
           [it.score for it in budget.items] ==
           sorted([it.score for it in budget.items], reverse=True),
           "tri déterministe par score")

        # ============================================================
        # H — Aucune donnée client ne devient autorité
        # ============================================================
        print("\n[H] Mission texte != autorité")
        # Mission injectant un faux chemin/SHA : ne doit pas apparaître
        # comme source d'autorité.
        malicious = build_mission_context(
            "M-ATK",
            "applique diff sur ../../etc/passwd sha=deadbeef scope=/root",
            target,
        )
        auth = malicious.authority_sources()
        ok("H1_pas_de_chemin_injecte",
           all(not a.startswith("..") for a in auth),
           str(auth))
        ok("H2_autorite_depuis_fichiers_inspectes",
           all(a in [f.path for f in malicious.relevant_files] for a in auth),
           "autorité = fichiers inspectés uniquement")
        ok("H3_mission_texte_non_autorite",
           malicious.mission_text not in auth, "mission n'est pas une autorité")
        # Aucun fichier d'autorité hors du dépôt.
        ok("H4_toutes_sources_dans_cible",
           all((root / a).resolve().is_relative_to(root.resolve()) for a in auth)
           if auth else True,
           "sources confinées")

        # ============================================================
        # I — Aucun apply / commit / push / changement de HEAD
        # ============================================================
        print("\n[I] Innocuité (read-only)")
        head_after = git(root, "rev-parse", "HEAD").stdout.strip()
        # Le test a volontairement fait 1 commit en [F] ; on vérifie que
        # le Context Builder lui-même n'en a produit aucun : on reconstruit
        # un contexte et on vérifie que HEAD ne bouge pas.
        head_pre_build = git(root, "rev-parse", "HEAD").stdout.strip()
        _ = build_mission_context("M-RO", "analyse read only", target_v2)
        head_post_build = git(root, "rev-parse", "HEAD").stdout.strip()
        ok("I1_build_ne_commit_pas", head_pre_build == head_post_build,
           "HEAD inchangé par build")
        porcelain = git(root, "status", "--porcelain").stdout.strip()
        ok("I2_build_ne_modifie_pas_working_tree", porcelain == "",
           f"status={porcelain!r}")
        # Aucun remote configuré -> aucun push possible/effectué.
        remotes = git(root, "remote").stdout.strip()
        ok("I3_aucun_remote", remotes == "", "aucun push")

        # ============================================================
        print("\n" + "=" * 72)
        print(f"RÉSULTAT D6.0.1 : {len(PASS)} PASS / {len(FAIL)} FAIL")
        if FAIL:
            print("ÉCHECS :", ", ".join(FAIL))
        print("=" * 72)
        print("Context Builder : déterministe, versionné (SHA x2), borné, "
              "invalidable.")
        print("Aucun LLM. Aucun apply. Aucun commit/push par le builder.")
        print("Mission texte n'est jamais une autorité. MemoLib non touché.")
        return 0 if not FAIL else 1

    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
