"""
MemoLibDev — Benchmark comparatif modèles (1.5B vs 7B)
======================================================

Compare deux modèles sur les MÊMES 11 missions du Reality Benchmark,
avec EXACTEMENT le même contexte, le même planner, le même prompt, les
mêmes garde-fous (R1/D5.8/D5.9) et les mêmes paramètres. SEUL le nom du
modèle change.

Ne modifie NI le contexte, NI le prompt, NI R1, NI D5.8/D5.9, NI la
clarification, NI humanize. Réutilise tel quel :
  - les 11 missions (copie identique de reality_benchmark.MISSIONS) ;
  - build_mission_context (D6.0.1) ;
  - derive_intent (planner + R1) ;
  - OllamaProvider (seul `model` varie).

STRICTEMENT READ_ONLY : n'appelle jamais run_controlled_apply. Prouve
HEAD/working tree de la cible inchangés avant/après.

Mesure ajoutée (demandée) : PERTINENCE DE LA CIBLE.
  REPLACE valide ≠ bonne réponse. Une proposition sur .amazonq/ ou un
  fichier de doc/règles est signalée « cible non pertinente » pour une
  mission portant sur le code.
"""

from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import time

from project_target import resolve_target, ProjectTargetError, ProjectTarget
from context.context_builder import build_mission_context, is_stale
from llm.llm_planner import derive_intent
from llm.ollama_provider import OllamaProvider

# MÊMES missions que le Reality Benchmark (importées, non redéfinies).
from reality_benchmark import MISSIONS, TIMEOUT_S


MODELS = ["qwen2.5-coder:1.5b-base", "qwen2.5-coder:7b"]

# Heuristique déterministe de pertinence de cible pour une mission CODE.
_CODE_DIRS = ("src/",)
_TEST_MARKERS = ("__tests__", ".test.", ".spec.")
_NON_CODE_PREFIX = (".amazonq/", ".vscode/", ".github/", "docs/", "doc/")


def _safe(s: str) -> str:
    enc = (sys.stdout.encoding or "utf-8")
    try:
        return s.encode(enc, errors="replace").decode(enc, errors="replace")
    except Exception:
        return s.encode("ascii", errors="replace").decode("ascii")


def git(root: Path, *a) -> str:
    return subprocess.run(["git", "-C", str(root), *a], text=True,
                          capture_output=True, encoding="utf-8",
                          errors="replace").stdout.strip()


def snapshot(root: Path) -> dict:
    return {"head": git(root, "rev-parse", "HEAD"),
            "porcelain": git(root, "status", "--porcelain"),
            "commits": git(root, "rev-list", "--count", "HEAD")}


def target_relevance(path: str) -> str:
    """pertinente | non_pertinente | neutre (déterministe, transparent)."""
    if not path:
        return "neutre"
    p = path.replace("\\", "/")
    if any(m in p for m in _TEST_MARKERS) or p.startswith(_CODE_DIRS):
        return "pertinente"
    if p.startswith(_NON_CODE_PREFIX) or p.endswith(".md"):
        return "non_pertinente"
    return "neutre"


def run_one(model: str, mission_id: str, mission: str,
            target: ProjectTarget) -> dict:
    t0 = time.time()
    provider = OllamaProvider(model=model, http_timeout=TIMEOUT_S)
    rec: dict = {"model": model, "id": mission_id, "mission": mission}

    ctx = build_mission_context(mission_id, mission, target,
                                max_files=8, max_context_chars=6000)
    rec["relevant_count"] = len(ctx.relevant_files)
    rec["top_score"] = ctx.relevant_files[0].score if ctx.relevant_files else 0

    if not ctx.relevant_files:
        rec.update(status="BLOCK", reason="aucun fichier pertinent",
                   format_ok=False, old_present=False, target=None,
                   target_relevance="neutre", hallucination=False,
                   duration_s=round(time.time() - t0, 2))
        return rec

    planner = derive_intent(ctx, provider, timeout_s=TIMEOUT_S)
    rec["status"] = planner.status
    rec["reason"] = planner.reason
    rec["target"] = planner.target_path
    rec["intent"] = (planner.intent[:120] if planner.intent else None)

    # Format REPLACE correct = planner OK (R1 l'exige déjà : forme + old présent).
    rec["format_ok"] = planner.ok and bool(planner.intent and
                                            planner.intent.startswith("REPLACE:"))
    # old réellement présent : si OK, R1 l'a déjà garanti.
    rec["old_present"] = planner.ok
    rec["target_relevance"] = target_relevance(planner.target_path or "")

    halluc = False
    if planner.ok and planner.target_path:
        if planner.target_path not in ctx.authority_sources():
            halluc = True
        else:
            abs_t = (target.git_root / planner.target_path).resolve()
            try:
                abs_t.relative_to(target.git_root.resolve())
                halluc = not abs_t.is_file()
            except ValueError:
                halluc = True
    rec["hallucination"] = halluc
    rec["duration_s"] = round(time.time() - t0, 2)
    return rec


def summarize(records: list[dict]) -> dict:
    n = len(records)
    ok = sum(1 for r in records if r["status"] == "OK")
    fmt = sum(1 for r in records if r.get("format_ok"))
    pert = sum(1 for r in records if r.get("target_relevance") == "pertinente")
    nonpert = sum(1 for r in records if r.get("target_relevance") == "non_pertinente")
    halluc = sum(1 for r in records if r.get("hallucination"))
    dur = round(sum(r["duration_s"] for r in records) / n, 2) if n else 0
    # Proposition "exploitable ET pertinente" = OK + cible pertinente.
    exploitable_pertinente = sum(
        1 for r in records
        if r["status"] == "OK" and r.get("target_relevance") == "pertinente")
    return {"n": n, "ok": ok, "format_ok": fmt, "cible_pertinente": pert,
            "cible_non_pertinente": nonpert, "ok_et_pertinente": exploitable_pertinente,
            "hallucination": halluc, "avg_duration_s": dur}


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — BENCHMARK COMPARATIF 1.5B vs 7B (READ_ONLY)")
    print("=" * 72)

    try:
        target = resolve_target()
    except ProjectTargetError as e:
        print(_safe(f"[STOP] Cible non résolue : {e}"))
        return 2
    root = target.git_root
    print(f"Cible : {root} (HEAD {target.head})")

    # Vérifier dispo des deux modèles.
    for m in MODELS:
        if not OllamaProvider(model=m, http_timeout=10.0).available:
            print(_safe(f"[STOP] Modèle indisponible : {m}"))
            return 3

    before = snapshot(root)
    print(f"[AVANT] HEAD={before['head'][:12]} "
          f"wt={'propre' if not before['porcelain'] else 'MODIFIÉ'}")

    all_records: dict[str, list[dict]] = {}
    for model in MODELS:
        print(f"\n{'='*72}\nMODÈLE : {model}\n{'='*72}")
        recs = []
        for mid, mission in MISSIONS:
            r = run_one(model, mid, mission, target)
            recs.append(r)
            print(f"  {mid:16} status={r['status']:6} "
                  f"pert={r.get('target_relevance','-'):14} "
                  f"halluc={r['hallucination']} {r['duration_s']}s "
                  f"-> {_safe(str(r.get('target')))}")
        all_records[model] = recs

    after = snapshot(root)

    # ----- Tableau comparatif -----
    print("\n" + "=" * 72)
    print("TABLEAU COMPARATIF")
    print("=" * 72)
    s = {m: summarize(all_records[m]) for m in MODELS}
    rows = [
        ("Proposition exploitable (OK)", "ok"),
        ("Format REPLACE correct", "format_ok"),
        ("Cible pertinente", "cible_pertinente"),
        ("Cible NON pertinente", "cible_non_pertinente"),
        ("OK ET cible pertinente", "ok_et_pertinente"),
        ("Hallucination", "hallucination"),
        ("Durée moyenne (s)", "avg_duration_s"),
    ]
    print(f"{'Mesure':34} | {'1.5B':>10} | {'7B':>10}")
    print("-" * 60)
    for label, key in rows:
        v15 = s[MODELS[0]][key]
        v7 = s[MODELS[1]][key]
        print(f"{label:34} | {str(v15):>10} | {str(v7):>10}")

    # ----- Preuve READ-ONLY -----
    print("\n" + "=" * 72)
    print("PREUVES READ-ONLY")
    print("=" * 72)
    checks = [("HEAD inchangé", before["head"] == after["head"]),
              ("working tree inchangé", before["porcelain"] == after["porcelain"]),
              ("aucun nouveau commit", before["commits"] == after["commits"])]
    all_ok = all(c for _, c in checks)
    for name, cond in checks:
        print(f"  [{'OK' if cond else 'ÉCHEC'}] {name}")
    print("VERDICT :", "READ-ONLY CONFIRMÉ" if all_ok else "ANOMALIE")

    out = {"target": str(root), "head": before["head"], "models": MODELS,
           "records": all_records, "summary": s, "readonly_confirmed": all_ok}
    Path("benchmark_models_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nRapport JSON : benchmark_models_result.json")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
