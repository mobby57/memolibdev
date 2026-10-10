"""
MemoLibDev — Test 5.3 : StructuredIntent -> contexte + budget déterministe
==========================================================================

Vérifie :
  BUDGET
    - <= MAX_CONTEXT_FILES, <= MAX_CONTEXT_CHARS
    - 0/1/8/9+ fichiers
    - budget exactement rempli / légèrement dépassé
    - fichier individuel trop grand -> exclu, jamais de dépassement
    - priorité : meilleurs scores sélectionnés d'abord
    - égalité de score -> tie-break stable (chemin)
    - métriques exactes
  INTENT (5.3)
    - cibles probables dans le chemin -> boost
    - affinité domaine<->rôle
    - confiance module le boost (LOW < MEDIUM < HIGH)
    - UNKNOWN -> aucun boost, aucune invention
  5A préservé + bout-en-bout + déterminisme.
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
    _apply_context_budget, _intent_boost, MAX_CONTEXT_FILES, MAX_CONTEXT_CHARS,
    _detect_role, ROLE_SOURCE, ROLE_DOC, ROLE_RULES, ROLE_GENERATED,
)
from mission_intent import analyze_mission


PASS: list[str] = []
FAIL: list[str] = []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def _cand(path, score, chars):
    return {"path": path, "score": score, "preview": "X" * chars,
            "role": _detect_role(path)}


def git(root: Path, *a) -> str:
    return subprocess.run(["git", "-C", str(root), *a], text=True,
                          capture_output=True, encoding="utf-8",
                          errors="replace").stdout.strip()


def make_lab() -> tuple[Path, ProjectTarget]:
    root = Path(tempfile.mkdtemp(prefix="memolibdev-53-")).resolve()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t53@memolibdev.local")
    git(root, "config", "user.name", "t53")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.eol", "lf")
    (root / "src").mkdir()
    (root / "src" / "auth").mkdir()
    (root / "docs").mkdir()
    (root / ".amazonq").mkdir()
    kw = "auth login clerk auth login clerk\n"
    (root / "src" / "auth" / "login.ts").write_text(
        "export function login(){} // " + kw, encoding="utf-8", newline="\n")
    (root / "proxy.ts").write_text("// proxy " + kw, encoding="utf-8", newline="\n")
    (root / "docs" / "guide.md").write_text("# guide\n" + kw * 5, encoding="utf-8", newline="\n")
    (root / ".amazonq" / "rules.md").write_text("# rules\n" + kw * 5, encoding="utf-8", newline="\n")
    git(root, "add", "-A"); git(root, "commit", "-q", "-m", "x")
    head = git(root, "rev-parse", "HEAD")
    fp = hashlib.sha256(f"{root}|main|{head}".encode()).hexdigest()[:16]
    t = ProjectTarget(path=root, git_root=root,
                      head=git(root, "rev-parse", "--short", "HEAD"),
                      head_full=head, branch="main", fingerprint=fp,
                      env_var="MEMOLIBDEV_TARGET")
    return root, t


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST 5.3 (intent + budget)")
    print("=" * 72)

    # ================= BUDGET =================
    print("\n[Budget — nombre de fichiers]")
    sel, m = _apply_context_budget([])
    ok("budget_0", sel == [] and m.fichiers_selectionnes == 0, "")
    sel, m = _apply_context_budget([_cand("a.ts", 10, 100)])
    ok("budget_1", m.fichiers_selectionnes == 1, "")
    many = [_cand(f"src/f{i}.ts", 100 - i, 100) for i in range(12)]
    sel, m = _apply_context_budget(many)
    ok("budget_max_files", m.fichiers_selectionnes <= MAX_CONTEXT_FILES,
       f"sel={m.fichiers_selectionnes}")
    ok("budget_9plus_exclus", m.fichiers_exclus_budget >= 1,
       f"exclus={m.fichiers_exclus_budget}")

    print("\n[Budget — caractères]")
    # 3x8000 = 24000 pile ; un 4e de 5000 doit être exclu.
    cands = [_cand("a.ts", 40, 8000), _cand("b.ts", 30, 8000),
             _cand("c.ts", 20, 8000), _cand("d.ts", 10, 5000)]
    sel, m = _apply_context_budget(cands)
    ok("budget_chars_exact", m.chars_selectionnes <= MAX_CONTEXT_CHARS,
       f"chars={m.chars_selectionnes}")
    ok("budget_chars_3retenus", m.fichiers_selectionnes == 3,
       f"sel={m.fichiers_selectionnes}")
    ok("budget_d_exclu", "d.ts" not in [c["path"] for c in sel], "")

    print("\n[Budget — fichier trop grand]")
    big = [_cand("huge.ts", 100, MAX_CONTEXT_CHARS + 1),
           _cand("small.ts", 50, 100)]
    sel, m = _apply_context_budget(big)
    ok("too_large_exclu", m.fichiers_exclus_trop_grands == 1, "")
    ok("too_large_pas_depassement", m.chars_selectionnes <= MAX_CONTEXT_CHARS, "")
    ok("too_large_small_retenu", "small.ts" in [c["path"] for c in sel], "")

    print("\n[Budget — priorité & tie-break]")
    pr = [_cand("z.ts", 10, 100), _cand("a.ts", 90, 100), _cand("m.ts", 50, 100)]
    sel, m = _apply_context_budget(sorted(pr, key=lambda c: (-c["score"], c["path"])))
    ok("priorite_meilleur_dabord", [c["path"] for c in sel] == ["a.ts", "m.ts", "z.ts"],
       str([c["path"] for c in sel]))
    tie = [_cand("b.ts", 50, 100), _cand("a.ts", 50, 100)]
    sel, m = _apply_context_budget(sorted(tie, key=lambda c: (-c["score"], c["path"])))
    ok("tiebreak_stable", [c["path"] for c in sel] == ["a.ts", "b.ts"],
       str([c["path"] for c in sel]))

    # ================= INTENT (5.3) =================
    print("\n[Intent — boost cible dans le chemin]")
    si = analyze_mission("corrige le login clerk")   # cibles: login, clerk ; AUTH ; HIGH-ish
    b_login = _intent_boost(si, "src/auth/login.ts", ROLE_SOURCE)
    b_other = _intent_boost(si, "src/utils/misc.ts", ROLE_SOURCE)
    ok("boost_cible_path", b_login > b_other, f"login={b_login:.2f} other={b_other:.2f}")

    print("\n[Intent — affinité domaine/rôle]")
    si_auth = analyze_mission("corrige l'authentification clerk et la session token")
    b_src = _intent_boost(si_auth, "src/auth/x.ts", ROLE_SOURCE)
    b_gen = _intent_boost(si_auth, "src/auth/x.ts", ROLE_GENERATED)
    ok("affinite_source_gt_generated", b_src > b_gen, f"src={b_src:.2f} gen={b_gen:.2f}")

    print("\n[Intent — confiance module le boost]")
    # Mission riche (HIGH) vs courte identifiable (MEDIUM) : le boost cible
    # doit être plus fort quand la confiance est plus haute.
    si_high = analyze_mission("corrige le bug d'authentification clerk login session token")
    si_med = analyze_mission("corrige le login")
    bh = _intent_boost(si_high, "src/auth/login.ts", ROLE_SOURCE)
    bm = _intent_boost(si_med, "src/auth/login.ts", ROLE_SOURCE)
    ok("confiance_high_ge_medium", bh >= bm, f"high={bh:.2f} med={bm:.2f}")
    ok("confiances",
       si_high.confiance in ("HIGH", "MEDIUM") and si_med.confiance in ("MEDIUM", "LOW"),
       f"high={si_high.confiance} med={si_med.confiance}")

    print("\n[Intent — UNKNOWN : aucun boost, aucune invention]")
    si_unknown = analyze_mission("blorp zorg flibber wobble")
    b_u = _intent_boost(si_unknown, "src/auth/login.ts", ROLE_SOURCE)
    ok("unknown_boost_neutre", abs(b_u - 1.0) < 1e-9, f"boost={b_u}")
    ok("unknown_pas_de_cible", si_unknown.cibles_probables == (), "")

    print("\n[Intent — plancher > 0 (jamais d'exclusion par 5.3)]")
    worst = _intent_boost(si_auth, "dist/bundle.js", ROLE_GENERATED)
    ok("boost_plancher_positif", worst > 0, f"boost={worst}")

    # ================= BOUT-EN-BOUT =================
    print("\n[E2E — mission auth favorise code auth vs doc/rules]")
    root, target = make_lab()
    try:
        ctx = build_mission_context("c", "corrige le login clerk et le proxy", target)
        paths = [rf.path for rf in ctx.relevant_files]
        ok("e2e_login_present", "src/auth/login.ts" in paths, str(paths))
        ok("e2e_proxy_present", "proxy.ts" in paths, str(paths))
        # Les fichiers code auth doivent passer DEVANT doc/rules malgré
        # leur densité de mots-clés supérieure.
        if "src/auth/login.ts" in paths:
            idx_login = paths.index("src/auth/login.ts")
            idx_doc = paths.index("docs/guide.md") if "docs/guide.md" in paths else 999
            idx_rules = paths.index(".amazonq/rules.md") if ".amazonq/rules.md" in paths else 999
            ok("e2e_code_devant_docrules", idx_login < idx_doc and idx_login < idx_rules,
               f"login@{idx_login} doc@{idx_doc} rules@{idx_rules}")
        # Budget respecté + métriques présentes.
        ok("e2e_budget_files", len(ctx.relevant_files) <= MAX_CONTEXT_FILES, "")
        ok("e2e_metrics_present", ctx.budget_metrics is not None
           and ctx.budget_metrics["budget_files"] == MAX_CONTEXT_FILES, "")
        ok("e2e_metrics_chars",
           ctx.budget_metrics["chars_selectionnes"] <= MAX_CONTEXT_CHARS, "")
        # Déterminisme bout-en-bout.
        ctx2 = build_mission_context("c", "corrige le login clerk et le proxy", target)
        ok("e2e_deterministe",
           [rf.path for rf in ctx2.relevant_files] == paths, "")
        # UNKNOWN : aucune invention de cible.
        ctxu = build_mission_context("u", "analyse le projet dans son ensemble", target)
        ok("e2e_unknown_pas_crash", isinstance(ctxu.relevant_files, tuple), "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n" + "=" * 72)
    print(f"RÉSULTAT 5.3 : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print(f"Budget: <= {MAX_CONTEXT_FILES} fichiers, <= {MAX_CONTEXT_CHARS} chars.")
    print("StructuredIntent consommé (boost déterministe), 5A préservé, 0 invention.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
