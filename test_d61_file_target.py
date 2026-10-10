"""
MemoLibDev — D6.1 : Test FileTarget (sandbox éphémère)
======================================================

Vérifie que FileTarget DÉCRIT correctement une ressource sans jamais
la modifier. Aucun Ollama, aucun patch, aucun git apply, aucun commit.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile

from file_target import (
    FileTarget,
    FileTargetError,
    resolve_file_target,
)
from project_target import ProjectTarget


PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True, capture_output=True, encoding="utf-8", errors="replace",
    )


def make_lab() -> tuple[Path, ProjectTarget]:
    root = Path(tempfile.mkdtemp(prefix="memolibdev-d61-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "d61@memolibdev.local")
    git(root, "config", "user.name", "d61")

    # Fichier TEXTUEL
    (root / "src").mkdir()
    (root / "src" / "app.ts").write_text(
        "export const x = 1;\n", encoding="utf-8", newline="\n",
    )

    # Fichier BINAIRE (simulé xlsx : quelques octets arbitraires)
    (root / "data.xlsx").write_bytes(b"PK\x03\x04fake-xlsx-content-for-test")

    # Fichier CSV (textuel données)
    (root / "report.csv").write_text(
        "nom,age\nAlice,30\nBob,25\n", encoding="utf-8", newline="\n",
    )

    # Fichier Markdown (doc texte)
    (root / "README.md").write_text(
        "# Title\nHello\n", encoding="utf-8", newline="\n",
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


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — D6.1 FILE TARGET (sandbox éphémère)")
    print("=" * 72)

    root, target = make_lab()

    try:
        # ============================================================
        # T1 — fichier textuel existant (TypeScript)
        # ============================================================
        print("\n[T1] Fichier textuel existant")
        ft = resolve_file_target("src/app.ts", target)
        ok("T1_path", ft.path == "src/app.ts", ft.path)
        ok("T1_format", ft.format == ".ts", ft.format)
        ok("T1_kind", ft.kind == "CODE", ft.kind)
        ok("T1_size", ft.size == len(b"export const x = 1;\n"), str(ft.size))
        expected_sha = sha256_bytes(b"export const x = 1;\n")
        ok("T1_sha256", ft.content_sha256 == expected_sha,
           f"{ft.content_sha256[:16]} == {expected_sha[:16]}")
        ok("T1_git_root", ft.git_root == str(root), ft.git_root)
        ok("T1_git_head", ft.git_head == target.head_full, ft.git_head[:12])
        ok("T1_permissions", ft.permissions == "READ_ONLY", ft.permissions)
        ok("T1_scope", ft.scope == "src/app.ts", ft.scope)
        ok("T1_risk", ft.risk_level == "MEDIUM", ft.risk_level)
        ok("T1_textual", ft.is_textual is True, str(ft.is_textual))
        ok("T1_adapter", ft.adapter == "code_adapter", ft.adapter)

        # ============================================================
        # T2 — fichier binaire (xlsx)
        # ============================================================
        print("\n[T2] Fichier binaire (xlsx)")
        ft2 = resolve_file_target("data.xlsx", target)
        ok("T2_format", ft2.format == ".xlsx", ft2.format)
        ok("T2_kind", ft2.kind == "SHEET", ft2.kind)
        ok("T2_textual", ft2.is_textual is False, str(ft2.is_textual))
        ok("T2_adapter", ft2.adapter == "xlsx_adapter", ft2.adapter)
        xlsx_sha = sha256_bytes(b"PK\x03\x04fake-xlsx-content-for-test")
        ok("T2_sha256", ft2.content_sha256 == xlsx_sha,
           f"{ft2.content_sha256[:16]} == {xlsx_sha[:16]}")

        # ============================================================
        # T3 — fichier CSV (textuel données)
        # ============================================================
        print("\n[T3] Fichier CSV")
        ft3 = resolve_file_target("report.csv", target)
        ok("T3_kind", ft3.kind == "DATA", ft3.kind)
        ok("T3_textual", ft3.is_textual is True, str(ft3.is_textual))

        # ============================================================
        # T4 — fichier Markdown (doc texte)
        # ============================================================
        print("\n[T4] Fichier Markdown")
        ft4 = resolve_file_target("README.md", target)
        ok("T4_kind", ft4.kind == "DOC", ft4.kind)
        ok("T4_textual", ft4.is_textual is True, str(ft4.is_textual))

        # ============================================================
        # T5 — chemin hors périmètre → rejeté
        # ============================================================
        print("\n[T5] Chemin hors périmètre")
        try:
            resolve_file_target("../../etc/passwd", target)
            ok("T5_hors_perimetre_BLOCK", False, "aucune erreur levée")
        except FileTargetError as e:
            ok("T5_hors_perimetre_BLOCK", True, str(e)[:60])

        # ============================================================
        # T6 — accès .git → rejeté
        # ============================================================
        print("\n[T6] Accès .git")
        try:
            resolve_file_target(".git/config", target)
            ok("T6_git_BLOCK", False, "aucune erreur levée")
        except FileTargetError as e:
            ok("T6_git_BLOCK", True, str(e)[:60])

        # ============================================================
        # T7 — fichier absent → rejeté
        # ============================================================
        print("\n[T7] Fichier absent")
        try:
            resolve_file_target("inexistant.py", target)
            ok("T7_absent_BLOCK", False, "aucune erreur levée")
        except FileTargetError as e:
            ok("T7_absent_BLOCK", True, str(e)[:60])

        # ============================================================
        # T8 — SHA change si fichier modifié (post-création)
        # ============================================================
        print("\n[T8] SHA change si fichier modifié")
        sha_before = ft.content_sha256
        (root / "src" / "app.ts").write_text(
            "export const x = 2;\n", encoding="utf-8", newline="\n",
        )
        ft_after = resolve_file_target("src/app.ts", target)
        ok("T8_SHA_different", ft_after.content_sha256 != sha_before,
           f"before={sha_before[:12]} after={ft_after.content_sha256[:12]}")
        # Restaurer pour propreté
        (root / "src" / "app.ts").write_text(
            "export const x = 1;\n", encoding="utf-8", newline="\n",
        )

        # ============================================================
        # T9 — risk_level paramétrable
        # ============================================================
        print("\n[T9] Risk level paramétrable")
        ft_high = resolve_file_target("src/app.ts", target, risk_level="HIGH")
        ok("T9_risk_HIGH", ft_high.risk_level == "HIGH", ft_high.risk_level)

        # ============================================================
        # T10 — FileTarget est frozen (immutable)
        # ============================================================
        print("\n[T10] Immutabilité")
        try:
            ft.path = "hacked"  # type: ignore
            ok("T10_frozen", False, "mutation autorisée")
        except (AttributeError, TypeError):
            ok("T10_frozen", True, "frozen dataclass")

        # ============================================================
        # INTÉGRITÉ CIBLE
        # ============================================================
        print("\n[INTÉGRITÉ]")
        ft_final = resolve_file_target("src/app.ts", target)
        ok("cible_inchangee", ft_final.content_sha256 == sha_before,
           "contenu restauré")

        # ============================================================
        print("\n" + "=" * 72)
        print(f"RÉSULTAT D6.1 : {len(PASS)} PASS / {len(FAIL)} FAIL")
        if FAIL:
            print("ÉCHECS :", ", ".join(FAIL))
        print("=" * 72)
        print("FileTarget DÉCRIT sans MODIFIER. Aucune écriture cible.")
        print("Aucun Ollama. Aucun patch. Aucun commit/push.")
        return 0 if not FAIL else 1

    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
