"""
MemoLibDev — D5.9 : Test Controlled Apply (sandbox éphémère)
============================================================

Règle absolue : le premier D5.9 NE TOUCHE PAS MemoLib.
On crée un dépôt Git temporaire (d59-lab/target.txt), on y génère un
certificat D5.8-style lié à CE sandbox, puis on prouve :

  S1  PASS  -> APPLIED
  S2  FAIL  -> ROLLBACK  (SHA initial == SHA final)
  S3  hors scope -> BLOCK (aucune écriture)

Aucun commit, aucun push, aucune production.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile

from d59_controlled_apply import (
    ApplyCertificate,
    sha256_file,
    sha256_text,
    run_controlled_apply,
)


PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True, capture_output=True, encoding="utf-8", errors="replace",
    )


def make_lab() -> tuple[Path, str, str]:
    """Crée d59-lab/ avec target.txt committé. Retourne (root, head, fp)."""
    root = Path(tempfile.mkdtemp(prefix="memolibdev-d59-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "d59@memolibdev.local")
    git(root, "config", "user.name", "d59")
    (root / "target.txt").write_text(
        "line1\nline2\nline3\n", encoding="utf-8", newline="\n"
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "baseline")
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    # fingerprint factice mais stable pour le sandbox (comme project_target).
    import hashlib
    fp = hashlib.sha256(f"{root}|main|{head}".encode()).hexdigest()[:16]
    return root, head, fp


def make_diff(root: Path, rel: str, needle: bytes, suffix: bytes) -> str:
    """Produit un vrai unified diff byte-preserving pour `rel`."""
    f = root / rel
    original = f.read_bytes()
    assert needle in original
    f.write_bytes(original.replace(needle, needle + suffix, 1))
    diff = git(root, "diff", "--", rel).stdout
    # restaure le working tree (le test applique via d59, pas via ce diff)
    git(root, "checkout", "--", rel)
    return diff


def cert_for(root: Path, head: str, fp: str, rel: str) -> ApplyCertificate:
    sha = sha256_file(root / rel)
    return ApplyCertificate(
        path=rel,
        status="AUTHORIZED",
        evidence_sha256=sha,
        target_git_root=str(root),
        target_head=head,
        target_fingerprint=fp,
    )


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — D5.9 CONTROLLED APPLY (sandbox éphémère)")
    print("=" * 72)

    # ============================================================
    # S1 — PASS -> APPLIED
    # ============================================================
    print("\n[S1] POST_VERIFY PASS -> APPLIED")
    root, head, fp = make_lab()
    try:
        rel = "target.txt"
        sha_before = sha256_file(root / rel)
        diff = make_diff(root, rel, b"line2", b"-PATCHED")
        cert = cert_for(root, head, fp, rel)

        def verify_pass(r: Path) -> tuple[bool, str]:
            # vérif légère déterministe : le marqueur est présent
            content = (r / rel).read_text(encoding="utf-8")
            return ("line2-PATCHED" in content, "marqueur présent")

        res = run_controlled_apply(
            root, cert, diff,
            target_head=head, target_fingerprint=fp, verify=verify_pass,
        )
        ok("S1_status_APPLIED", res.status == "APPLIED", res.reason)
        ok("S1_not_committed", res.committed is False and res.pushed is False, "")
        ok("S1_working_tree_modifie",
           sha256_file(root / rel) != sha_before, "fichier bien modifié")
        # APPLIED != COMMITTED : la modif est dans le working tree, non commitée
        porcelain = git(root, "status", "--porcelain").stdout.strip()
        ok("S1_modif_non_committee", porcelain != "", f"status={porcelain!r}")
        log_count = git(root, "rev-list", "--count", "HEAD").stdout.strip()
        ok("S1_aucun_nouveau_commit", log_count == "1", f"commits={log_count}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    # S2 — FAIL -> ROLLBACK (SHA initial == SHA final)
    # ============================================================
    print("\n[S2] POST_VERIFY FAIL -> ROLLBACK")
    root, head, fp = make_lab()
    try:
        rel = "target.txt"
        diff = make_diff(root, rel, b"line2", b"-BADPATCH")
        # SHA de référence APRÈS make_diff (état réel du working tree
        # sur lequel D5.9 va opérer), pas avant.
        sha_before = sha256_file(root / rel)
        cert = cert_for(root, head, fp, rel)

        def verify_fail(r: Path) -> tuple[bool, str]:
            return (False, "verification volontairement échouée")

        res = run_controlled_apply(
            root, cert, diff,
            target_head=head, target_fingerprint=fp, verify=verify_fail,
        )
        ok("S2_status_ROLLED_BACK", res.status == "ROLLED_BACK", res.reason)
        ok("S2_rolled_back_flag", res.rolled_back is True, "")
        sha_after = sha256_file(root / rel)
        ok("S2_SHA_initial_==_final",
           res.sha_initial == res.sha_final == sha_before == sha_after,
           f"init={res.sha_initial[:12]} final={res.sha_final[:12]} "
           f"before={sha_before[:12]} after={sha_after[:12]}")
        porcelain = git(root, "status", "--porcelain").stdout.strip()
        ok("S2_working_tree_propre_apres_rollback",
           porcelain == "", f"status={porcelain!r}")
        ok("S2_not_committed", res.committed is False and res.pushed is False, "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    # S3 — patch HORS SCOPE -> BLOCK (aucune écriture)
    # ============================================================
    print("\n[S3] PATCH HORS SCOPE -> BLOCK")
    root, head, fp = make_lab()
    try:
        rel = "target.txt"
        # certificat autorise target.txt...
        cert = cert_for(root, head, fp, rel)
        # ...mais on fabrique un patch qui touche un AUTRE fichier.
        (root / "other.txt").write_text("a\nb\n", encoding="utf-8", newline="\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "add other")
        head2 = git(root, "rev-parse", "HEAD").stdout.strip()
        import hashlib
        fp2 = hashlib.sha256(f"{root}|main|{head2}".encode()).hexdigest()[:16]
        # certificat re-lié au nouvel état pour isoler le test de SCOPE
        cert = cert_for(root, head2, fp2, rel)

        of = root / "other.txt"
        of.write_bytes(of.read_bytes().replace(b"a", b"a-HORS", 1))
        diff_other = git(root, "diff", "--", "other.txt").stdout
        git(root, "checkout", "--", "other.txt")

        # SHA de référence APRÈS restauration (état réel avant apply).
        sha_target_before = sha256_file(root / rel)
        sha_other_before = sha256_file(root / "other.txt")

        def verify_unused(r: Path) -> tuple[bool, str]:
            return (True, "ne devrait jamais être appelé")

        res = run_controlled_apply(
            root, cert, diff_other,
            target_head=head2, target_fingerprint=fp2, verify=verify_unused,
        )
        ok("S3_status_BLOCKED", res.status == "BLOCKED", res.reason)
        ok("S3_reason_hors_scope", "hors scope" in res.reason, res.reason)
        ok("S3_target_inchange",
           sha256_file(root / rel) == sha_target_before, "")
        ok("S3_other_inchange",
           sha256_file(root / "other.txt") == sha_other_before,
           "aucune écriture")
        porcelain = git(root, "status", "--porcelain").stdout.strip()
        ok("S3_working_tree_propre", porcelain == "", f"status={porcelain!r}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ============================================================
    print("\n" + "=" * 72)
    print(f"RÉSULTAT D5.9 : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print("Démontré : APPLY (S1) + VERIFY + ROLLBACK (S2) + BLOCK hors scope (S3)")
    print("APPLIED != COMMITTED. Aucun commit, aucun push, aucune production.")
    print("MemoLib : NON TOUCHÉ (sandbox éphémère uniquement).")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
