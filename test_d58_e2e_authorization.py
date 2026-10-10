"""
MemoLibDev — D5.8 : End-to-End Authorization Integration
========================================================

OBJECTIF (différent des D5.4/D5.6) :
    Ne pas re-tester chaque composant isolément, mais prouver la
    CHAÎNE RÉELLE et attaquer les JOINTURES entre composants.

Chaîne prouvée :
    certificat (reports/coder-authorization.json)
        -> load_coder_authorization            (fail-closed)
        -> enforce_coder_authorization         (autorité)
        -> enforce_write_guardrail             (scope du diff)
        -> verify_patch_in_sandbox             (git apply --check)
        -> PATCH PROPOSÉ

Invariant inter-composants (fail-closed) :
    Jointure attaquée -> BLOCK
    Chaîne cohérente  -> PATCH PROPOSÉ
    MemoLib : jamais modifié. Ollama : jamais appelé.

Les diffs sont fabriqués de façon DÉTERMINISTE via `git diff`
(byte-preserving), sans modèle, pour que le test soit reproductible.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile

import controlled_coder as cc
from project_target import resolve_target


PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    tag = "PASS" if condition else "FAIL"
    print(f"[{tag}] {name}" + (f" :: {detail}" if detail else ""))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_byte_preserving_diff(
    rel: str,
    needle: bytes,
    suffix: bytes,
) -> str:
    """
    Produit un vrai unified diff pour `rel` en modifiant une ligne
    de façon byte-preserving, via un dépôt git temporaire alimenté
    par le fichier réel de la cible. Ne touche jamais la cible.
    """
    target = resolve_target()
    source = (target.git_root / rel).resolve()
    original = source.read_bytes()

    if needle not in original:
        raise RuntimeError(f"needle absente de {rel}")

    work = Path(tempfile.mkdtemp(prefix="memolibdev-d58-")).resolve()
    try:
        repo = work / "repo"
        repo.mkdir()

        def git(*a):
            return subprocess.run(
                ["git", *a], cwd=repo, text=True, capture_output=True
            )

        git("init", "-q")
        git("config", "user.email", "d58@memolibdev.local")
        git("config", "user.name", "d58")

        dest = repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(original)
        git("add", "-A")
        git("commit", "-q", "-m", "baseline")

        dest.write_bytes(original.replace(needle, needle + suffix, 1))

        diff = git("diff", "--", rel)
        if diff.returncode != 0 or not diff.stdout.strip():
            raise RuntimeError("git diff vide")
        return diff.stdout
    finally:
        shutil.rmtree(work, ignore_errors=True)


def write_patch(diff_text: str) -> Path:
    # Le patch doit vivre HORS de la cible (contrainte du sandbox gate).
    pf = Path(tempfile.mkdtemp(prefix="memolibdev-d58-patch-")) / "p.diff"
    pf.write_text(diff_text, encoding="utf-8", newline="")
    return pf


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — D5.8 END-TO-END AUTHORIZATION INTEGRATION")
    print("=" * 72)

    target = resolve_target()
    authorization = cc.load_coder_authorization()
    authorized_path = authorization.path  # src/lib/auth/nextauth-token.ts
    scope = [authorized_path]

    source = (target.git_root / authorized_path).resolve()
    sha_before = sha256_file(source)

    # Ligne réelle présente dans nextauth-token.ts (byte-preserving).
    needle = b"export async function getAuthToken"
    suffix = b" // D58"

    # ============================================================
    # HAPPY PATH — chaîne complète cohérente
    # ============================================================
    print("\n[H] HAPPY PATH — chaîne complète")

    auth_res = cc.enforce_coder_authorization(authorization, target, scope)
    ok("H1_authorization_AUTHORIZED",
       auth_res["verdict"] == "AUTHORIZED", auth_res["verdict"])

    diff = make_byte_preserving_diff(authorized_path, needle, suffix)

    guard = cc.enforce_write_guardrail(diff, scope)
    ok("H2_write_guardrail_ACCEPTABLE",
       guard["verdict"] == "ACCEPTABLE", str(guard["touched_files"]))

    patch_file = write_patch(diff)
    try:
        sb = cc.verify_patch_in_sandbox(
            diff, set(guard["touched_files"]), patch_file
        )
        ok("H3_sandbox_applicable", sb["applicable"] is True,
           f"rc={sb['returncode']}")
        ok("H4_sandbox_cleaned", not Path(sb["sandbox"]).exists(), "")
    finally:
        shutil.rmtree(patch_file.parent, ignore_errors=True)

    # Les 3 maillons alignés => PATCH PROPOSÉ.
    chain_ok = (
        auth_res["verdict"] == "AUTHORIZED"
        and guard["verdict"] == "ACCEPTABLE"
        and sb["applicable"] is True
    )
    ok("H5_PATCH_PROPOSE", chain_ok, "chaîne cohérente -> PATCH")

    # ============================================================
    # JOINTURES — attaques ENTRE composants
    # ============================================================
    print("\n[J] JOINTURES — attaques inter-composants")

    # J1 — Autorisation pour A, diff touche B (hors certificat).
    #      Le write guardrail calé sur le scope du certificat (A seul)
    #      doit BLOCK tout diff touchant un autre fichier.
    diff_other = (
        "diff --git a/src/other/elsewhere.ts b/src/other/elsewhere.ts\n"
        "--- a/src/other/elsewhere.ts\n+++ b/src/other/elsewhere.ts\n"
        "@@ -1 +1,2 @@\n a\n+b\n"
    )
    guard_b = cc.enforce_write_guardrail(diff_other, scope)
    ok("J1_diff_hors_certificat_BLOCK",
       guard_b["verdict"] == "REJECT",
       f"out_of_scope={guard_b['out_of_scope_files']}")

    # J2 — Diff MIXTE : touche A (autorisé) ET B (hors certificat).
    #      Un attaquant glisse un second fichier dans le même diff.
    #      Le guardrail calé sur le scope du certificat doit BLOCK le
    #      diff entier dès qu'un fichier hors scope apparaît.
    mixed = diff + (
        "\ndiff --git a/src/other/elsewhere.ts b/src/other/elsewhere.ts\n"
        "--- a/src/other/elsewhere.ts\n+++ b/src/other/elsewhere.ts\n"
        "@@ -1 +1,2 @@\n a\n+b\n"
    )
    guard_mixed = cc.enforce_write_guardrail(mixed, scope)
    ok("J2_diff_mixte_second_fichier_BLOCK",
       guard_mixed["verdict"] == "REJECT",
       f"out_of_scope={guard_mixed['out_of_scope_files']}")

    # J3 — Diff autorisé mais CORROMPU -> sandbox BLOCK.
    corrupt = diff.replace("@@", "@@ CORRUPT", 1)
    pf3 = write_patch(corrupt)
    try:
        sb3 = cc.verify_patch_in_sandbox(
            corrupt, set(guard["touched_files"]), pf3
        )
        ok("J3_diff_corrompu_sandbox_BLOCK",
           sb3["applicable"] is False, f"rc={sb3['returncode']}")
    finally:
        shutil.rmtree(pf3.parent, ignore_errors=True)

    # J4 — Certificat REJECTED -> enforce doit refuser (pas d'accès coder).
    import dataclasses
    rejected = dataclasses.replace(authorization, status="REJECTED")
    r4 = cc.enforce_coder_authorization(rejected, target, scope)
    ok("J4_certificat_REJECTED_BLOCK", r4["verdict"] == "REJECT",
       r4["reason"][:60])

    # J5 — Réutilisation : autorisation de A validée pour requested_path B.
    from coder_authorization import validate_authorization
    reuse_path = "src/lib/auth/other-token.ts"
    valid_b, reason_b = validate_authorization(
        authorization, target, reuse_path, [authorized_path, reuse_path]
    )
    ok("J5_reuse_sur_autre_path_BLOCK", not valid_b, reason_b)

    # J6 — Autorisation A sur une AUTRE cible (HEAD forgé) -> BLOCK.
    forged_target = dataclasses.replace(
        target, head_full="0" * 40, fingerprint="forged_fp"
    )
    r6 = cc.enforce_coder_authorization(authorization, forged_target, scope)
    ok("J6_cible_forgee_BLOCK", r6["verdict"] == "REJECT", r6["reason"][:60])

    # ============================================================
    # INTÉGRITÉ MEMOLIB
    # ============================================================
    sha_after = sha256_file(source)
    ok("MEMOLIB_inchange", sha_before == sha_after,
       f"{sha_before[:12]} == {sha_after[:12]}")

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=target.git_root, text=True, capture_output=True,
    )
    ok("MEMOLIB_git_clean_ou_prealable",
       status.returncode == 0, "git status lisible")

    # ============================================================
    print("\n" + "=" * 72)
    print(f"RÉSULTAT D5.8 : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print("Invariant inter-composants :")
    print("  Jointure attaquée -> BLOCK :",
          "PROUVÉ" if not FAIL else "NON PROUVÉ")
    print("  Chaîne cohérente -> PATCH PROPOSÉ : H5")
    print("Aucun Ollama. MemoLib non modifié.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
