"""
MemoLibDev — D5.4 : Suite ADVERSARIALE de l'Evidence Engine
===========================================================

Invariant fondamental à prouver (fail-closed) :

    Attaque        -> BLOCK   (tout statut != ACCEPTED)
    Preuve valide  -> ACCEPT  (status == ACCEPTED)
    Ambiguïté      -> BLOCK

On construit un dépôt Git SYNTHÉTIQUE et temporaire pour contrôler
exactement le contenu et les attaques (faux symbole, import-only,
re-export, path traversal, fichier supprimé, SHA/HEAD/fingerprint
falsifiés). Aucune écriture dans un dépôt réel. Aucun appel Ollama.

Chaque cas est explicite : nom, action, verdict attendu.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
import tempfile

from project_target import ProjectTarget
from evidence_resolver_v2_2 import (
    EvidenceStatus,
    EvidenceRecord,
    build_store,
    resolve,
    validate_record,
    content_sha256,
)


# ------------------------------------------------------------------
# Infra : dépôt git synthétique temporaire + ProjectTarget réel
# ------------------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True, capture_output=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def make_sandbox_repo() -> tuple[Path, ProjectTarget]:
    root = Path(tempfile.mkdtemp(prefix="memolibdev-d54-")).resolve()

    _git(root, "init", "-q")
    _git(root, "config", "user.email", "d54@memolibdev.local")
    _git(root, "config", "user.name", "d54")

    # Fichier avec une VRAIE déclaration de symbole.
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "auth.ts").write_text(
        "import { helper } from './helper';\n"
        "\n"
        "export function verifyToken(t: string): boolean {\n"
        "  return helper(t);\n"
        "}\n",
        encoding="utf-8",
    )

    # Fichier qui ne fait qu'IMPORTER et RÉ-EXPORTER un symbole
    # (ne doit JAMAIS être une déclaration acceptée).
    (root / "src" / "reexport.ts").write_text(
        "import { verifyToken } from './auth';\n"
        "export { verifyToken };\n"
        "\n"
        "export const x = verifyToken('abc'); // call reference\n",
        encoding="utf-8",
    )

    # Fichier de test qui mentionne un symbole SANS le déclarer.
    (root / "src" / "auth.test.ts").write_text(
        "import { verifyToken } from './auth';\n"
        "it('verifyToken works', () => {\n"
        "  expect(verifyToken('x')).toBe(true);\n"
        "});\n",
        encoding="utf-8",
    )

    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "baseline")

    head_full = _git(root, "rev-parse", "HEAD")
    head = _git(root, "rev-parse", "--short", "HEAD")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")

    import hashlib
    fp = hashlib.sha256(
        f"{root}|{branch}|{head_full}".encode("utf-8")
    ).hexdigest()[:16]

    target = ProjectTarget(
        path=root,
        git_root=root,
        head=head,
        head_full=head_full,
        branch=branch,
        fingerprint=fp,
        env_var="MEMOLIBDEV_TARGET",
    )

    return root, target


# ------------------------------------------------------------------
# Helpers d'assertion
# ------------------------------------------------------------------

PASS = []
FAIL = []


def expect_block(name: str, condition_blocked: bool, detail: str):
    if condition_blocked:
        PASS.append(name)
        print(f"  [BLOCK-OK] {name} :: {detail}")
    else:
        FAIL.append(name)
        print(f"  [FAIL]     {name} :: ATTENDU BLOCK, OBTENU PASS :: {detail}")


def expect_accept(name: str, condition_accepted: bool, detail: str):
    if condition_accepted:
        PASS.append(name)
        print(f"  [ACCEPT-OK] {name} :: {detail}")
    else:
        FAIL.append(name)
        print(f"  [FAIL]      {name} :: ATTENDU ACCEPT, OBTENU BLOCK :: {detail}")


def top_status(results):
    return results[0].status if results else "NO_RESULT"


# ------------------------------------------------------------------
# Suite
# ------------------------------------------------------------------

def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — D5.4 ADVERSARIAL EVIDENCE SUITE")
    print("=" * 72)

    root, target = make_sandbox_repo()

    try:
        all_files = [
            "src/auth.ts",
            "src/reexport.ts",
            "src/auth.test.ts",
        ]
        store = build_store(all_files, target.git_root, target)

        assert len(store) == 3, f"store attendu=3, obtenu={len(store)}"
        print(f"\nEvidence store synthétique : {len(store)} enregistrements\n")

        # ---- TÉMOIN POSITIF : vraie déclaration -> ACCEPT ----------
        print("[T0] Témoin positif (preuve valide)")
        res = resolve(store, "verifyToken", target)
        # La déclaration réelle est dans src/auth.ts
        accepted = [r for r in res if r.status == EvidenceStatus.ACCEPTED]
        decl_in_auth = any(r.path == "src/auth.ts" for r in accepted)
        expect_accept(
            "T0_declaration_reelle",
            top_status(res) == EvidenceStatus.ACCEPTED and decl_in_auth,
            f"top={top_status(res)} decl_in_auth={decl_in_auth}",
        )

        # ================= ATTAQUES IDENTITÉ / INTÉGRITÉ ============
        print("\n[A] Attaques d'identité / intégrité de preuve")
        rec = store[0]

        # A1 — mauvais git_root
        wrong_root = replace(target, git_root=Path(tempfile.gettempdir()).resolve())
        ok, reason = validate_record(rec, wrong_root)
        expect_block("A1_mauvais_git_root", not ok, reason)

        # A2 — mauvais HEAD
        bad_head = replace(rec, head="0" * 40)
        ok, reason = validate_record(bad_head, target)
        expect_block("A2_mauvais_HEAD", not ok, reason)

        # A3 — mauvais fingerprint
        bad_fp = replace(rec, repository_fingerprint="deadbeefdeadbeef")
        ok, reason = validate_record(bad_fp, target)
        expect_block("A3_mauvais_fingerprint", not ok, reason)

        # A4 — SHA différent (fichier modifié simulé)
        bad_sha = replace(rec, content_sha256="0" * 64)
        ok, reason = validate_record(bad_sha, target)
        expect_block("A4_SHA_different", not ok, reason)

        # A5 — fichier RÉELLEMENT modifié sur disque -> SHA mismatch
        auth_path = root / "src" / "auth.ts"
        original_text = auth_path.read_text(encoding="utf-8")
        auth_path.write_text(original_text + "\n// tampered\n", encoding="utf-8")
        ok, reason = validate_record(rec_for(store, "src/auth.ts"), target)
        expect_block("A5_fichier_modifie_disque", not ok, reason)
        auth_path.write_text(original_text, encoding="utf-8")  # restore

        # A6 — path traversal dans normalized_path
        traversal = replace(rec, normalized_path="../../etc/passwd")
        ok, reason = validate_record(traversal, target)
        expect_block("A6_path_traversal", not ok, reason)

        # A7 — fichier supprimé
        reexport_rec = rec_for(store, "src/reexport.ts")
        (root / "src" / "reexport.ts").unlink()
        ok, reason = validate_record(reexport_rec, target)
        expect_block("A7_fichier_supprime", not ok, reason)
        # restore pour la suite
        (root / "src" / "reexport.ts").write_text(
            "import { verifyToken } from './auth';\n"
            "export { verifyToken };\n"
            "export const x = verifyToken('abc');\n",
            encoding="utf-8",
        )
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "restore reexport")
        # NB: le commit change HEAD -> on reconstruit la cible+store
        head_full = _git(root, "rev-parse", "HEAD")
        head = _git(root, "rev-parse", "--short", "HEAD")
        import hashlib
        fp = hashlib.sha256(
            f"{root}|{target.branch}|{head_full}".encode("utf-8")
        ).hexdigest()[:16]
        target = replace(target, head=head, head_full=head_full, fingerprint=fp)
        store = build_store(all_files, target.git_root, target)

        # ================= ATTAQUES PROVENANCE SYMBOLIQUE ==========
        print("\n[B] Attaques de provenance symbolique (déclaration vs référence)")

        # B1 — faux symbole inexistant -> SYMBOL_NOT_FOUND (BLOCK)
        res = resolve(store, "totallyFakeSymbolXYZ", target)
        expect_block(
            "B1_faux_symbole",
            top_status(res) != EvidenceStatus.ACCEPTED,
            f"top={top_status(res)}",
        )

        # B2 — import-only ne doit JAMAIS être ACCEPTED pour reexport.ts
        res = resolve(store, "verifyToken", target)
        reexport_accepted = any(
            r.status == EvidenceStatus.ACCEPTED and r.path == "src/reexport.ts"
            for r in res
        )
        expect_block(
            "B2_import_reexport_pas_accepted",
            not reexport_accepted,
            "reexport.ts ne doit pas fournir une déclaration ACCEPTED",
        )

        # B3 — le symbole uniquement cité dans un test ne doit pas
        #      être traité comme déclaration. On vérifie que auth.test.ts
        #      n'apparaît pas comme ACCEPTED.
        test_accepted = any(
            r.status == EvidenceStatus.ACCEPTED and r.path == "src/auth.test.ts"
            for r in res
        )
        expect_block(
            "B3_symbole_dans_test_pas_accepted",
            not test_accepted,
            "auth.test.ts ne contient qu'une référence, pas une déclaration",
        )

        # B4 — la SEULE déclaration ACCEPTED doit être src/auth.ts
        accepted_paths = {
            r.path for r in res if r.status == EvidenceStatus.ACCEPTED
        }
        expect_accept(
            "B4_declaration_unique_correcte",
            accepted_paths == {"src/auth.ts"},
            f"accepted_paths={sorted(accepted_paths)}",
        )

        # B5 — module externe / symbole non présent -> BLOCK
        res = resolve(store, "PrismaClientFromNodeModules", target)
        expect_block(
            "B5_module_externe_absent",
            top_status(res) != EvidenceStatus.ACCEPTED,
            f"top={top_status(res)}",
        )

        # ================= SYNTHÈSE ================================
        print("\n" + "=" * 72)
        print(f"RÉSULTAT D5.4 : {len(PASS)} PASS / {len(FAIL)} FAIL")
        if FAIL:
            print("ÉCHECS :")
            for f in FAIL:
                print("  -", f)
        print("=" * 72)
        print("Invariant fail-closed :")
        print("  Attaque -> BLOCK :", "PROUVÉ" if not FAIL else "NON PROUVÉ")
        print("  Preuve valide -> ACCEPT : vérifié par T0 et B4")
        print("Aucun appel Ollama. Aucune écriture dans un dépôt réel.")

        return 0 if not FAIL else 1

    finally:
        shutil.rmtree(root, ignore_errors=True)


def rec_for(store, normalized_path: str) -> EvidenceRecord:
    for r in store:
        if r.normalized_path == normalized_path:
            return r
    raise KeyError(normalized_path)


if __name__ == "__main__":
    raise SystemExit(main())
