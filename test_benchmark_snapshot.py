"""
MemoLibDev — Test harnais snapshot (Option B : clone figé)
==========================================================

Prouve :
  S1  clone créé au HEAD demandé
  S2  fichiers non suivis du working tree réel (_archive/, bin/, obj/)
      ABSENTS du clone (ne polluent plus le contexte)
  S3  build_mission_context utilise bien le clone (chemins du snapshot)
  S4  même snapshot exécuté 2x -> contexte identique (déterminisme)
  S5  working tree RÉEL de la source inchangé par le benchmark
  S6  le clone est supprimé en sortie (pas de fuite tmp)
  S7  snapshot d'un HEAD antérieur -> inventaire différent (figé par commit)

Aucun LLM. Aucune modification du moteur / project_inspector / 5.3.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import shutil

from project_target import ProjectTarget
from context import build_mission_context
from benchmark_snapshot import frozen_clone, snapshot_inventory


PASS: list[str] = []
FAIL: list[str] = []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), *a], text=True,
                          capture_output=True, encoding="utf-8", errors="replace")


def make_source() -> tuple[Path, ProjectTarget, str]:
    """Dépôt source avec un commit baseline, PUIS des fichiers non suivis parasites."""
    root = Path(tempfile.mkdtemp(prefix="memolibdev-src-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "s@memolibdev.local")
    git(root, "config", "user.name", "s")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.eol", "lf")
    (root / "src").mkdir()
    (root / "src" / "login.ts").write_text(
        "export function login(){ return clerk(); } // auth login clerk\n",
        encoding="utf-8", newline="\n")
    (root / "src" / "api.ts").write_text(
        "export const route = () => {}; // api route\n",
        encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "baseline")
    head1 = git(root, "rev-parse", "HEAD").stdout.strip()

    # Second commit (pour tester S7 : snapshot d'un HEAD antérieur).
    (root / "src" / "extra.ts").write_text("export const x=1;\n",
                                            encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "second")
    head2 = git(root, "rev-parse", "HEAD").stdout.strip()

    # Fichiers NON SUIVIS parasites (comme _archive/bin/obj dans le vrai MemoLib).
    (root / "_archive").mkdir()
    (root / "_archive" / "old-login.ts").write_text(
        "// auth login clerk auth login clerk PARASITE\n" * 10,
        encoding="utf-8", newline="\n")
    (root / "bin").mkdir()
    (root / "bin" / "diag.ts").write_text("// auth login PARASITE build\n" * 10,
                                          encoding="utf-8", newline="\n")

    import hashlib
    fp = hashlib.sha256(f"{root}|main|{head2}".encode()).hexdigest()[:16]
    target = ProjectTarget(
        path=root, git_root=root,
        head=git(root, "rev-parse", "--short", "HEAD").stdout.strip(),
        head_full=head2, branch="main", fingerprint=fp,
        env_var="MEMOLIBDEV_TARGET")
    return root, target, head1


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST harnais snapshot (clone figé)")
    print("=" * 72)

    src_root, source, head1 = make_source()
    captured_clone_path = {"p": None}
    try:
        # Working tree réel contient bien les parasites (pré-condition).
        ok("precond_parasites_presents",
           (src_root / "_archive").exists() and (src_root / "bin").exists(), "")

        # ----- S1/S2/S3 : via le clone figé -----
        with frozen_clone(source) as snap:
            captured_clone_path["p"] = snap.git_root
            ok("S1_clone_head", snap.head_full == source.head_full,
               f"{snap.head_full[:12]} == {source.head_full[:12]}")
            ok("S1_clone_ailleurs", snap.git_root != source.git_root,
               "clone dans un répertoire distinct")

            inv = snapshot_inventory(snap)
            ok("S2_pas_archive", not any("_archive" in p for p in inv),
               f"inventaire={inv}")
            ok("S2_pas_bin", not any(p.startswith("bin/") for p in inv), "")
            ok("S2_src_present", any(p.startswith("src/") for p in inv), str(inv))

            ctx = build_mission_context("c", "corrige le login clerk", snap)
            paths = [rf.path for rf in ctx.relevant_files]
            ok("S3_contexte_depuis_clone",
               paths and not any("_archive" in p or p.startswith("bin/") for p in paths),
               f"paths={paths}")
            ok("S3_login_present", "src/login.ts" in paths, str(paths))

            # ----- S4 : déterminisme (même snapshot, 2 contextes) -----
            ctx2 = build_mission_context("c", "corrige le login clerk", snap)
            ok("S4_deterministe",
               [rf.path for rf in ctx2.relevant_files] == paths, "")

        # ----- S6 : clone supprimé en sortie -----
        ok("S6_clone_supprime",
           captured_clone_path["p"] is not None
           and not captured_clone_path["p"].exists(),
           "répertoire du clone nettoyé")

        # ----- S5 : working tree réel inchangé -----
        ok("S5_source_parasites_intacts",
           (src_root / "_archive").exists() and (src_root / "bin").exists(),
           "la source réelle n'a pas été touchée")
        ok("S5_source_wt_identique",
           git(src_root, "rev-parse", "HEAD").stdout.strip() == source.head_full,
           "HEAD source inchangé")

        # ----- S7 : snapshot d'un HEAD antérieur = inventaire différent -----
        with frozen_clone(source, head=head1) as snap_old:
            inv_old = snapshot_inventory(snap_old)
            ok("S7_head_anterieur_fige",
               "src/extra.ts" not in inv_old and "src/login.ts" in inv_old,
               f"inv_old={inv_old}")
        with frozen_clone(source) as snap_new:
            inv_new = snapshot_inventory(snap_new)
            ok("S7_head_courant_contient_extra",
               "src/extra.ts" in inv_new, f"inv_new={inv_new}")

    finally:
        shutil.rmtree(src_root, ignore_errors=True)

    print("\n" + "=" * 72)
    print(f"RÉSULTAT snapshot : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print("Clone figé à HEAD : contexte reproductible, parasites exclus,")
    print("moteur/project_inspector/5.3 inchangés, source réelle intacte.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
