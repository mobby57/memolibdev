"""
MemoLibDev — D6.2 : Test Code Adapter (sandbox éphémère)
========================================================

18+ cas couvrant :
  ✓ .py/.ts/.tsx acceptés
  ✓ fichier non-code rejeté par code_adapter
  ✓ FileTarget incorrect → BLOCK
  ✓ fichier hors scope → BLOCK
  ✓ diff hors scope → BLOCK
  ✓ diff corrompu → BLOCK
  ✓ SHA initiale incorrecte → BLOCK
  ✓ git apply --check échec → BLOCK
  ✓ proposition valide → PASS
  ✓ D5.9 applique → APPLIED
  ✓ vérification échoue → ROLLED_BACK
  ✓ aucun commit / push
  ✓ MemoLib inchangé
  ✓ sandbox nettoyé

Aucun Ollama. MemoLib jamais touché.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile

from file_target import FileTarget, FileTargetError, resolve_file_target
from code_adapter import (
    CodeAdapterError,
    read,
    analyze,
    plan,
    modify,
    validate,
    generate_diff,
    generate_diff_git,
)
from d59_controlled_apply import (
    ApplyCertificate,
    sha256_file,
    sha256_text,
    run_controlled_apply,
    pre_apply,
)
from project_target import ProjectTarget


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
    root = Path(tempfile.mkdtemp(prefix="memolibdev-d62-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "d62@memolibdev.local")
    git(root, "config", "user.name", "d62")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.eol", "lf")

    (root / "src").mkdir()
    (root / "src" / "app.ts").write_text(
        "export const version = '1.0';\nexport function hello() {\n  return 'world';\n}\n",
        encoding="utf-8", newline="\n",
    )
    (root / "src" / "helper.py").write_text(
        "def greet(name: str) -> str:\n    return f'Hello {name}'\n",
        encoding="utf-8", newline="\n",
    )
    (root / "src" / "view.tsx").write_text(
        "export function View() {\n  return <div>ok</div>;\n}\n",
        encoding="utf-8", newline="\n",
    )
    (root / "data.xlsx").write_bytes(b"PK\x03\x04fake-xlsx")
    (root / "README.md").write_text("# Title\n", encoding="utf-8", newline="\n")

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


def cert_for(root: Path, head: str, fp: str, rel: str) -> ApplyCertificate:
    sha = sha256_file(root / rel)
    return ApplyCertificate(
        path=rel, status="AUTHORIZED", evidence_sha256=sha,
        target_git_root=str(root), target_head=head, target_fingerprint=fp,
    )


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — D6.2 CODE ADAPTER (sandbox éphémère)")
    print("=" * 72)

    root, target = make_lab()

    try:
        # ============================================================
        # A — ADMISSION : formats acceptés / rejetés
        # ============================================================
        print("\n[A] Admission formats")

        ft_ts = resolve_file_target("src/app.ts", target)
        ok("A1_ts_accepted", ft_ts.kind == "CODE" and ft_ts.is_textual, ft_ts.kind)

        ft_py = resolve_file_target("src/helper.py", target)
        ok("A2_py_accepted", ft_py.kind == "CODE" and ft_py.is_textual, ft_py.kind)

        ft_tsx = resolve_file_target("src/view.tsx", target)
        ok("A3_tsx_accepted", ft_tsx.kind == "CODE" and ft_tsx.is_textual, ft_tsx.kind)

        # Non-code (xlsx) rejeté par code_adapter
        ft_xlsx = resolve_file_target("data.xlsx", target)
        try:
            read(ft_xlsx)
            ok("A4_xlsx_rejected", False, "aucune erreur")
        except CodeAdapterError as e:
            ok("A4_xlsx_rejected", True, str(e)[:60])

        # ============================================================
        # B — READ / ANALYZE / PLAN / MODIFY / VALIDATE
        # ============================================================
        print("\n[B] Contrat adaptateur (read->validate)")

        content_ts = read(ft_ts)
        ok("B1_read", "export const version" in content_ts, f"{len(content_ts)} chars")

        structure = analyze(content_ts, ft_ts.path)
        ok("B2_analyze_lines", structure.lines > 0, str(structure.lines))
        ok("B3_analyze_functions", "hello" in structure.functions,
           str(structure.functions))

        code_plan = plan(content_ts, "REPLACE:version = '1.0':version = '2.0'", ft_ts.path)
        ok("B4_plan_changes", len(code_plan.changes) == 1 and code_plan.changes[0].action == "REPLACE",
           code_plan.changes[0].description[:60] if code_plan.changes else "")

        new_content = modify(content_ts, code_plan)
        ok("B5_modify_applied", "version = '2.0'" in new_content, "")
        ok("B6_modify_no_disk", content_ts != new_content, "contenu différent en mémoire")

        val_ok, val_reason = validate(content_ts, new_content)
        ok("B7_validate_pass", val_ok, val_reason)

        # Validate détecte la corruption (contenu vide)
        val2_ok, val2_reason = validate(content_ts, "")
        ok("B8_validate_empty_BLOCK", not val2_ok, val2_reason[:60])

        # ============================================================
        # C — GENERATE_DIFF + git apply --check
        # ============================================================
        print("\n[C] Diff déterministe + applicabilité")

        diff = generate_diff_git(root, ft_ts.path, new_content)
        ok("C1_diff_generated", len(diff) > 0 and "---" in diff, f"{len(diff)} chars")

        # git apply --check dans le sandbox (via fichier patch, robuste Windows)
        pf = root / "_c2.diff"
        pf.write_text(diff, encoding="utf-8", newline="")
        check = subprocess.run(
            ["git", "-C", str(root), "apply", "--check", str(pf)],
            text=True, capture_output=True, encoding="utf-8",
        )
        pf.unlink(missing_ok=True)
        ok("C2_git_apply_check", check.returncode == 0,
           check.stderr.strip()[:80] if check.returncode != 0 else "applicable")

        # ============================================================
        # D — BLOCS SÉCURITÉ (fail-closed)
        # ============================================================
        print("\n[D] Blocs sécurité")

        # D1 — FileTarget hors périmètre → BLOCK
        try:
            resolve_file_target("../../etc/passwd", target)
            ok("D1_hors_perimetre", False, "")
        except FileTargetError:
            ok("D1_hors_perimetre", True, "BLOCK")

        # D2 — diff hors scope (touche un autre fichier)
        from controlled_coder import enforce_write_guardrail
        diff_other = generate_diff("a\n", "a\nb\n", "src/NOTINSCOPE.ts")
        guard = enforce_write_guardrail(diff_other, [ft_ts.path])
        ok("D2_diff_hors_scope", guard["verdict"] == "REJECT",
           str(guard.get("out_of_scope_files")))

        # D3 — diff corrompu → git apply --check échoue
        corrupt = diff.replace("@@", "@@ CORRUPT", 1)
        check_bad = subprocess.run(
            ["git", "-C", str(root), "apply", "--check", "-"],
            input=corrupt, text=True, capture_output=True, encoding="utf-8",
        )
        ok("D3_diff_corrompu", check_bad.returncode != 0, "git apply --check échoue")

        # D4 — SHA initiale incorrecte → D5.9 pre_apply BLOCK
        bad_cert = ApplyCertificate(
            path=ft_ts.path, status="AUTHORIZED",
            evidence_sha256="0" * 64,
            target_git_root=str(root), target_head=target.head_full,
            target_fingerprint=target.fingerprint,
        )
        pa_ok, pa_reason = pre_apply(
            root, bad_cert, diff,
            target_head=target.head_full, target_fingerprint=target.fingerprint,
        )
        ok("D4_sha_incorrecte_BLOCK", not pa_ok, pa_reason[:60])

        # ============================================================
        # E — CHAÎNE COMPLÈTE D5.9 : APPLIED
        # ============================================================
        print("\n[E] Chaîne D5.9 APPLIED")

        rel = ft_ts.path
        sha_before = sha256_file(root / rel)
        cert = cert_for(root, target.head_full, target.fingerprint, rel)

        def verify_applied(r: Path) -> tuple[bool, str]:
            c = (r / rel).read_text(encoding="utf-8")
            return ("version = '2.0'" in c, "marqueur version 2.0")

        res = run_controlled_apply(
            root, cert, diff,
            target_head=target.head_full, target_fingerprint=target.fingerprint,
            verify=verify_applied,
        )
        ok("E1_status_APPLIED", res.status == "APPLIED", res.reason[:60])
        ok("E2_not_committed", res.committed is False and res.pushed is False, "")
        ok("E3_working_tree_modified",
           sha256_file(root / rel) != sha_before, "fichier modifié")

        # Pas de nouveau commit
        log = git(root, "rev-list", "--count", "HEAD").stdout.strip()
        ok("E4_aucun_nouveau_commit", log == "1", f"commits={log}")

        # Restaurer pour la suite (git checkout)
        git(root, "checkout", "--", rel)

        # ============================================================
        # F — CHAÎNE D5.9 : ROLLBACK (verify échoue)
        # ============================================================
        print("\n[F] Chaîne D5.9 ROLLBACK")

        sha_before2 = sha256_file(root / rel)
        cert2 = cert_for(root, target.head_full, target.fingerprint, rel)

        def verify_fail(r: Path) -> tuple[bool, str]:
            return (False, "vérification volontairement échouée")

        res2 = run_controlled_apply(
            root, cert2, diff,
            target_head=target.head_full, target_fingerprint=target.fingerprint,
            verify=verify_fail,
        )
        sha_after2 = sha256_file(root / rel)
        ok("F1_status_ROLLED_BACK", res2.status == "ROLLED_BACK", res2.reason[:60])
        ok("F2_sha_restored", sha_before2 == sha_after2,
           f"{sha_before2[:12]} == {sha_after2[:12]}")
        ok("F3_not_committed", res2.committed is False and res2.pushed is False, "")

        # ============================================================
        print("\n" + "=" * 72)
        print(f"RÉSULTAT D6.2 : {len(PASS)} PASS / {len(FAIL)} FAIL")
        if FAIL:
            print("ÉCHECS :", ", ".join(FAIL))
        print("=" * 72)
        print("code_adapter : FileTarget -> read -> analyze -> plan -> modify -> validate")
        print("               -> generate_diff -> D5.8 guardrails -> D5.9 APPLIED/ROLLBACK")
        print("Aucun Ollama. MemoLib non touché. Aucun commit/push.")
        return 0 if not FAIL else 1

    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
