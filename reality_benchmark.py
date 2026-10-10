"""
MemoLibDev — Reality Benchmark (READ_ONLY, mesure de fiabilité)
===============================================================

Exécute N missions RÉELLES en lecture seule sur la cible MEMOLIBDEV_TARGET
et journalise des métriques OBJECTIVES par mission, pour découvrir le
levier dominant de fiabilité (modèle / contexte / raisonnement / preuves).

STRICTEMENT READ_ONLY :
  - n'importe NI n'appelle run_controlled_apply (D5.9) ;
  - s'arrête après la PROPOSITION (contexte + derive_intent) ;
  - aucune écriture, aucun git mutant, aucun commit/push ;
  - prouve HEAD + working tree inchangés avant/après.

Métriques automatiques (objectives) par mission :
  - statut planner (OK / BLOCK + raison)
  - clarification nécessaire ? (heuristique déterministe)
  - nb fichiers pertinents + top score
  - fichiers retenus (authority_sources)
  - cible proposée + intent (si OK)
  - diagnostic candidat (fichier + fragment visé)
  - hallucination = cible hors authority_sources (doit être False : le
    planner bloque sinon) OU cible hors dépôt
  - durée (s)

Les jugements qualitatifs (compréhension/diagnostic correct) restent
HUMAINS : le rapport fournit les faits bruts pour les renseigner.
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


MODEL = "qwen2.5-coder:1.5b-base"
TIMEOUT_S = 200.0

# Seuils de clarification (mêmes que la CLI, pour cohérence).
MIN_MISSION_WORDS = 3
MIN_TOP_SCORE = 4


# 10 missions réalistes + 1 volontairement ambiguë (M11).
MISSIONS = [
    ("M01-auth-login", "analyse la navigation vers la page de connexion /fr/auth/login"),
    ("M02-routes", "analyse l'organisation des routes publiques et protégées"),
    ("M03-clerk", "analyse le flux d'authentification Clerk et le rôle du proxy"),
    ("M04-ui", "identifie pourquoi des parties de l'interface se mélangent"),
    ("M05-tests", "analyse la couverture de tests autour de l'authentification"),
    ("M06-prisma", "analyse le schéma prisma et les modèles de données"),
    ("M07-config", "analyse la configuration next.config et les variables d'environnement"),
    ("M08-doc", "analyse la documentation du projet et sa complétude"),
    ("M09-typescript", "analyse les types TypeScript partagés et leurs incohérences"),
    ("M10-securite", "analyse les points de sécurité liés aux tokens et sessions"),
    ("M11-ambigu", "corrige le login"),   # volontairement ambiguë
]


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


def clarification_needed(mission: str, target: ProjectTarget) -> tuple[bool, str]:
    words = [w for w in mission.split() if len(w) > 2]
    if len(words) < MIN_MISSION_WORDS:
        return True, "mission trop courte"
    ctx = build_mission_context("probe", mission, target,
                                max_files=8, max_context_chars=4000)
    if not ctx.relevant_files:
        return True, "aucun fichier pertinent"
    if ctx.relevant_files[0].score < MIN_TOP_SCORE:
        return True, f"score top faible ({ctx.relevant_files[0].score})"
    return False, "mission suffisamment précise"


def run_mission(mission_id: str, mission: str, target: ProjectTarget,
                provider: OllamaProvider) -> dict:
    t0 = time.time()
    rec: dict = {"id": mission_id, "mission": mission}

    clar, clar_reason = clarification_needed(mission, target)
    rec["clarification_needed"] = clar
    rec["clarification_reason"] = clar_reason

    ctx = build_mission_context(mission_id, mission, target,
                                max_files=8, max_context_chars=6000)
    rec["relevant_count"] = len(ctx.relevant_files)
    rec["top_score"] = ctx.relevant_files[0].score if ctx.relevant_files else 0
    rec["authority_sources"] = list(ctx.authority_sources())
    rec["context_fresh"] = not is_stale(ctx, target).stale

    if not ctx.relevant_files:
        rec["planner_status"] = "BLOCK"
        rec["planner_reason"] = "aucun fichier pertinent"
        rec["target"] = None
        rec["intent"] = None
        rec["hallucination"] = False
        rec["duration_s"] = round(time.time() - t0, 2)
        return rec

    planner = derive_intent(ctx, provider, timeout_s=TIMEOUT_S)
    rec["planner_status"] = planner.status
    rec["planner_reason"] = planner.reason
    rec["target"] = planner.target_path
    rec["intent"] = (planner.intent[:120] if planner.intent else None)

    # Hallucination objective : une cible proposée hors authority_sources
    # OU hors dépôt. (Le planner BLOQUE normalement ces cas -> on vérifie.)
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


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — REALITY BENCHMARK (READ_ONLY, 10+1 missions)")
    print("=" * 72)

    try:
        target = resolve_target()
    except ProjectTargetError as e:
        print(_safe(f"[STOP] Cible non résolue : {e}"))
        return 2
    root = target.git_root
    print(f"Cible : {root}  (HEAD {target.head}, {git(root, 'rev-list', '--count', 'HEAD')} commits)")

    provider = OllamaProvider(model=MODEL, http_timeout=TIMEOUT_S)
    if not provider.available:
        print(_safe(f"[STOP] Ollama/modèle {MODEL} indisponible."))
        return 3

    before = snapshot(root)
    print(f"[AVANT] HEAD={before['head'][:12]} "
          f"working_tree={'propre' if not before['porcelain'] else 'MODIFIÉ'}")

    results = []
    for mid, mission in MISSIONS:
        print(f"\n--- {mid} : {_safe(mission)}")
        rec = run_mission(mid, mission, target, provider)
        results.append(rec)
        print(f"    clar={rec['clarification_needed']} "
              f"files={rec['relevant_count']} top={rec['top_score']} "
              f"status={rec['planner_status']} "
              f"halluc={rec['hallucination']} {rec['duration_s']}s")
        if rec.get("target"):
            print(f"    cible={_safe(str(rec['target']))} "
                  f"intent={_safe(str(rec['intent']))[:70]}")

    after = snapshot(root)

    # ----- Rapport agrégé -----
    print("\n" + "=" * 72)
    print("SYNTHÈSE")
    print("=" * 72)
    n = len(results)
    ok_count = sum(1 for r in results if r["planner_status"] == "OK")
    clar_count = sum(1 for r in results if r["clarification_needed"])
    halluc_count = sum(1 for r in results if r["hallucination"])
    zero_ctx = sum(1 for r in results if r["relevant_count"] == 0)
    avg_dur = round(sum(r["duration_s"] for r in results) / n, 2) if n else 0
    print(f"Missions                     : {n}")
    print(f"Proposition produite (OK)    : {ok_count}/{n}")
    print(f"Clarification recommandée    : {clar_count}/{n}")
    print(f"Contexte vide (0 fichier)    : {zero_ctx}/{n}")
    print(f"Hallucination (cible invalide): {halluc_count}/{n}")
    print(f"Durée moyenne                : {avg_dur}s")

    # ----- Preuve d'innocuité -----
    print("\n" + "=" * 72)
    print("PREUVES READ-ONLY")
    print("=" * 72)
    checks = [
        ("HEAD inchangé", before["head"] == after["head"]),
        ("working tree inchangé", before["porcelain"] == after["porcelain"]),
        ("aucun nouveau commit", before["commits"] == after["commits"]),
    ]
    all_ok = all(c for _, c in checks)
    for name, cond in checks:
        print(f"  [{'OK' if cond else 'ÉCHEC'}] {name}")
    print("VERDICT :", "READ-ONLY CONFIRMÉ" if all_ok else "ANOMALIE")

    # Sortie JSON exploitable.
    out = {"target": str(root), "head": before["head"], "model": MODEL,
           "missions": results,
           "summary": {"n": n, "ok": ok_count, "clarification": clar_count,
                       "zero_context": zero_ctx, "hallucination": halluc_count,
                       "avg_duration_s": avg_dur},
           "readonly_confirmed": all_ok}
    Path("reality_benchmark_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nRapport JSON : reality_benchmark_result.json")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
