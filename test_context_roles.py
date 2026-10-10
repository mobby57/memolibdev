"""
MemoLibDev — Test classement par rôle (étape 2 context selection)
=================================================================

Vérifie la pondération par rôle, SANS exclusion :
  R1  _detect_role classe correctement par chemin
  R2  _mission_intent : CODE / DOC / NEUTRE déterministe
  R3  mission CODE -> SOURCE/TEST priorisés sur DOC/RULES à score lexical égal
  R4  mission DOC -> DOC/RULES restent sélectionnables (jamais exclus)
  R5  mission NEUTRE -> aucun rôle pénalisé (×1.0)
  R6  aucun fichier n'est exclu par le rôle (score jamais 0)
  R7  déterminisme

Aucun LLM. Aucun réseau. Sandbox éphémère pour les tests de bout en bout.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile

from project_target import ProjectTarget
from context import build_mission_context
from context.context_builder import (
    _detect_role, _mission_intent, _role_multiplier, _extract_terms,
    ROLE_SOURCE, ROLE_TEST, ROLE_CONFIG, ROLE_DOC, ROLE_RULES,
    ROLE_SCRIPT, ROLE_GENERATED, ROLE_OTHER,
)


PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def git(root: Path, *a) -> str:
    return subprocess.run(["git", "-C", str(root), *a], text=True,
                          capture_output=True, encoding="utf-8",
                          errors="replace").stdout.strip()


def make_lab() -> tuple[Path, ProjectTarget]:
    root = Path(tempfile.mkdtemp(prefix="memolibdev-roles-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "roles@memolibdev.local")
    git(root, "config", "user.name", "roles")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.eol", "lf")
    (root / "src").mkdir()
    (root / "docs").mkdir()
    (root / ".amazonq").mkdir()
    # Même densité de mots-clés "auth login" dans un SOURCE et un RULES.
    kw = "auth login auth login auth login\n"
    (root / "src" / "login.ts").write_text(
        "export function login(){} // " + kw, encoding="utf-8", newline="\n")
    (root / ".amazonq" / "rules.md").write_text(
        "# règles\n" + kw * 3, encoding="utf-8", newline="\n")
    (root / "docs" / "guide.md").write_text(
        "# guide\n" + kw * 3, encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "baseline")
    head = git(root, "rev-parse", "HEAD")
    fp = hashlib.sha256(f"{root}|main|{head}".encode()).hexdigest()[:16]
    target = ProjectTarget(
        path=root, git_root=root, head=git(root, "rev-parse", "--short", "HEAD"),
        head_full=head, branch="main", fingerprint=fp,
        env_var="MEMOLIBDEV_TARGET")
    return root, target


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST classement par rôle (étape 2)")
    print("=" * 72)

    # ========================================================
    # R1 — _detect_role
    # ========================================================
    print("\n[R1] Détection de rôle")
    cases = {
        "src/app/login.ts": ROLE_SOURCE,
        "src/components/Btn.tsx": ROLE_SOURCE,
        "lib/util.py": ROLE_SOURCE,
        "src/__tests__/x.test.ts": ROLE_TEST,
        "x.spec.ts": ROLE_TEST,
        "next.config.js": ROLE_CONFIG,
        "tsconfig.json": ROLE_CONFIG,
        "package.json": ROLE_CONFIG,
        "docs/CAHIER.md": ROLE_DOC,
        "README.md": ROLE_DOC,
        ".amazonq/rules/x.md": ROLE_RULES,
        ".vscode/settings.json": ROLE_RULES,
        ".github/workflows/ci.yml": ROLE_RULES,
        "scripts/deploy.ts": ROLE_SCRIPT,
        "scripts/smoke-tests.js": ROLE_SCRIPT,
        "tools/build-release.sh": ROLE_SCRIPT,
        "setup.sh": ROLE_SCRIPT,
        "dist/bundle.js": ROLE_GENERATED,
        "build/out.js": ROLE_GENERATED,
        "x.min.js": ROLE_GENERATED,
        "unknown.xyz": ROLE_OTHER,
    }
    for path, expected in cases.items():
        got = _detect_role(path)
        ok(f"R1_{path}", got == expected, f"{got} (attendu {expected})")

    # ========================================================
    # R2 — _mission_intent
    # ========================================================
    print("\n[R2] Intention de mission")
    ok("R2_code", _mission_intent(_extract_terms("corrige le bug de login auth")) == "CODE", "")
    ok("R2_doc", _mission_intent(_extract_terms("analyse la documentation et le cahier des charges")) == "DOC", "")
    ok("R2_doc_prime", _mission_intent(_extract_terms("mets à jour la documentation du code auth")) == "DOC",
       "doc explicite prime")
    ok("R2_neutre", _mission_intent(_extract_terms("bonjour ceci est vague xyz")) == "NEUTRE", "")

    # ========================================================
    # R3+R4 — multiplicateurs
    # ========================================================
    print("\n[R3+R4] Multiplicateurs")
    ok("R3_code_source_boost", _role_multiplier("CODE", ROLE_SOURCE) == 1.5, "")
    ok("R3_code_rules_reduit", _role_multiplier("CODE", ROLE_RULES) == 0.3, "")
    ok("R3_code_doc_reduit", _role_multiplier("CODE", ROLE_DOC) == 0.5, "")
    ok("R4_doc_doc_boost", _role_multiplier("DOC", ROLE_DOC) == 1.5, "")
    ok("R4_doc_rules_boost", _role_multiplier("DOC", ROLE_RULES) == 1.3, "")
    ok("R5_neutre_source", _role_multiplier("NEUTRE", ROLE_SOURCE) == 1.0, "")
    # Aucun multiplicateur n'est 0 (pas d'exclusion).
    all_mults = [
        _role_multiplier(i, r)
        for i in ("CODE", "DOC", "NEUTRE")
        for r in (ROLE_SOURCE, ROLE_TEST, ROLE_CONFIG, ROLE_DOC, ROLE_RULES, ROLE_OTHER)
    ]
    ok("R6_jamais_zero", all(m > 0 for m in all_mults), f"min={min(all_mults)}")

    # ========================================================
    # Bout-en-bout sur sandbox
    # ========================================================
    print("\n[E2E] Priorisation réelle via build_mission_context")
    root, target = make_lab()
    try:
        # Mission CODE : src/login.ts doit passer DEVANT .amazonq/rules.md
        # et docs/guide.md malgré leur densité de mots-clés supérieure.
        ctx_code = build_mission_context("c", "corrige le bug de login auth", target)
        paths_code = [rf.path for rf in ctx_code.relevant_files]
        ok("E2E_code_source_present", "src/login.ts" in paths_code, str(paths_code))
        if "src/login.ts" in paths_code:
            idx_src = paths_code.index("src/login.ts")
            idx_rules = paths_code.index(".amazonq/rules.md") if ".amazonq/rules.md" in paths_code else 999
            idx_doc = paths_code.index("docs/guide.md") if "docs/guide.md" in paths_code else 999
            ok("E2E_code_source_prioritaire",
               idx_src < idx_rules and idx_src < idx_doc,
               f"src@{idx_src} rules@{idx_rules} doc@{idx_doc}")
        # Les DOC/RULES ne sont PAS exclus (toujours présents dans la liste).
        ok("E2E_code_rules_non_exclu", ".amazonq/rules.md" in paths_code, "")
        ok("E2E_code_doc_non_exclu", "docs/guide.md" in paths_code, "")

        # Mission DOC : docs/guide.md et .amazonq/rules.md remontent.
        ctx_doc = build_mission_context("d", "analyse la documentation et les règles auth login", target)
        paths_doc = [rf.path for rf in ctx_doc.relevant_files]
        ok("E2E_doc_doc_present", "docs/guide.md" in paths_doc, str(paths_doc))
        if "docs/guide.md" in paths_doc and "src/login.ts" in paths_doc:
            ok("E2E_doc_doc_prioritaire",
               paths_doc.index("docs/guide.md") < paths_doc.index("src/login.ts"),
               "doc devant source en intention DOC")
        # Source jamais exclu non plus.
        ok("E2E_doc_source_non_exclu", "src/login.ts" in paths_doc, "")

        # Déterminisme.
        ctx_code2 = build_mission_context("c", "corrige le bug de login auth", target)
        ok("E2E_deterministe",
           [rf.path for rf in ctx_code2.relevant_files] == paths_code, "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n" + "=" * 72)
    print(f"RÉSULTAT RÔLES : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print("Pondération par rôle : SOURCE/TEST priorisés en CODE ; DOC/RULES")
    print("priorisés en DOC ; aucun rôle exclu ; déterministe.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
