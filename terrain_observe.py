"""
MemoLibDev — PREUVE TERRAIN Observer/Préparer (ZERO modification)
=================================================================

Première preuve terrain sur le VRAI dépôt MemoLib, en mode OBSERVER/
PRÉPARER uniquement. Produit une ANALYSE + un PLAN STRUCTURÉ. Ne modifie
RIEN, n'applique RIEN, ne branche NI D5.8 NI D5.9.

Innocuité maximale : l'inspection se fait sur un CLONE FIGÉ (frozen_clone)
au HEAD courant ; le working tree réel de MemoLib n'est même pas lu de
façon mutante. Le plan reste une proposition (CAPACITÉ ≠ AUTORISATION
≠ APPLICATION).

Réutilise le VRAI pipeline (aucune réimplémentation) :
  build_mission_context (5.2/5A/5.3) -> secret scan -> derive_intent (R1/R2)
  -> proposition.  AUCUN run_controlled_apply.
"""

from __future__ import annotations

from pathlib import Path
import json
import subprocess
import time

from project_target import resolve_target, ProjectTargetError
from context.context_builder import build_mission_context, is_stale
from mission_intent import analyze_mission
from llm.secret_scanner import scan_context
from llm.llm_planner import derive_intent
from llm.ollama_provider import OllamaProvider
from benchmark_snapshot import frozen_clone

MODEL = "qwen2.5-coder:7b"
TIMEOUT_S = 200.0

# Mission réelle, concrète, à FAIBLE RISQUE (lecture/analyse d'un point
# d'auth bien délimité). La cible exacte reste déterminée par le pipeline.
MISSION = ("analyse la page de connexion /fr/auth/login et le flux "
           "d'authentification, identifie le fichier principal concerné "
           "et propose une amélioration mineure et réversible")


def git(root: Path, *a) -> str:
    return subprocess.run(["git", "-C", str(root), *a], text=True,
                          capture_output=True, encoding="utf-8",
                          errors="replace").stdout.strip()


def safe(s) -> str:
    return str(s).encode("ascii", "replace").decode("ascii")


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — PREUVE TERRAIN Observer/Préparer (ZERO modification)")
    print("=" * 72)

    try:
        source = resolve_target()
    except ProjectTargetError as e:
        print(f"[STOP] Cible non résolue : {e}")
        return 2

    src_root = source.git_root
    tree_before = git(src_root, "rev-parse", "HEAD^{tree}")
    wt_before = git(src_root, "status", "--porcelain")
    head_before = source.head_full

    print(f"[B] Dépôt observé : {src_root}")
    print(f"    HEAD : {head_before}")
    print(f"    tree : {tree_before}")
    print(f"[A] Mission : {MISSION}")

    if not OllamaProvider(model=MODEL, http_timeout=10.0).available:
        print(f"[STOP] Modèle indisponible : {MODEL}")
        return 3

    t0 = time.time()
    report = {"mission": MISSION, "head": head_before, "tree_before": tree_before}

    with frozen_clone(source) as snap:
        # [C/D/E/F] Contexte via le VRAI pipeline (5.2/5A/5.3) sur clone figé.
        ctx = build_mission_context("TERRAIN-001", MISSION, snap,
                                    risk_level="MEDIUM")
        inspected = ctx.project.files_count
        retained = [rf.path for rf in ctx.relevant_files]
        print(f"\n[C] Fichiers inspectés (clone figé) : {inspected}")
        print(f"[D] Fichiers retenus pertinents : {len(retained)}")
        for rf in ctx.relevant_files:
            print(f"    - {safe(rf.path)} (score={rf.score}, kind={rf.kind})")
        # [E] Exclusion : tout ce qui n'est pas retenu (budget/role/intent).
        print(f"[E] Fichiers hors périmètre : non retenus par le budget "
              f"5.3 (<= {ctx.budget_metrics['budget_files']} fichiers), "
              f"exclus_budget={ctx.budget_metrics['fichiers_exclus_budget']}, "
              f"exclus_trop_grands={ctx.budget_metrics['fichiers_exclus_trop_grands']}")

        # [G] SHA / evidence / provenance.
        fresh = is_stale(ctx, snap)
        print(f"[G] Fraîcheur contexte : {fresh.status}")
        for e in ctx.evidence[:5]:
            print(f"    evidence {safe(e.source_path)} "
                  f"text_sha={e.text_sha256[:12]} byte_sha={e.byte_sha256[:12]}")

        # [H] Secret scanner AVANT tout appel provider.
        scan = scan_context(ctx)
        print(f"[H] Secret scanner : {scan.status} (hits={len(scan.hits)})")

        # [I] Provider + intention structurée (déterministe).
        si = analyze_mission(MISSION)
        print(f"[I] Provider : OllamaProvider({MODEL})")
        print(f"    intent 5.2 : objectif={si.objectif} domaine={si.domaine} "
              f"type={si.type_mission} risque={si.risque} conf={si.confiance}")

        # [J/K/L/M/N] PIPELINE COMPLET via run_from_mission (traverse la
        # bifurcation GAP ANALYSER/CORRIGER). ANALYSER -> ANALYZED (aucun
        # REPLACE, aucun D5.8/D5.9, aucune écriture). Aucun apply.
        from agent_loop import run_from_mission
        res = run_from_mission(
            "TERRAIN-GAP", MISSION, snap, None,
            lambda r: (True, "verify léger (terrain)"),
            action=None, human_approval=None,
            provider=OllamaProvider(model=MODEL, http_timeout=TIMEOUT_S),
            provider_timeout_s=TIMEOUT_S)
        rep = res.report
        print(f"\n[J] État final : {rep.final_state}")
        print(f"[K] Scope/cible d'écriture : {safe(rep.scope)}")
        has_replace = "REPLACE:" in (rep.reason or "")
        print(f"[L] REPLACE exigé ? {has_replace}")
        print(f"[M] Risque (5.2) : {si.risque}")
        print(f"[N] Diagnostic / raison :")
        for line in (rep.reason or "").splitlines():
            print(f"    {safe(line)}")
        print(f"    committed={rep.committed} pushed={rep.pushed}")

        report.update(
            inspected=inspected, retained=retained,
            budget_metrics=ctx.budget_metrics,
            context_status=fresh.status,
            secret_status=scan.status, secret_hits=len(scan.hits),
            intent_52={"objectif": si.objectif, "domaine": si.domaine,
                       "type": si.type_mission, "risque": si.risque,
                       "confiance": si.confiance},
            plan_status=rep.final_state, plan_target=rep.scope,
            plan_intent=None, plan_reason=rep.reason,
            committed=rep.committed, pushed=rep.pushed,
            has_replace=has_replace)

    # [O] temps.
    dur = round(time.time() - t0, 2)
    report["duration_s"] = dur

    # [P/Q/R] Innocuité : MemoLib byte-for-byte inchangé.
    tree_after = git(src_root, "rev-parse", "HEAD^{tree}")
    wt_after = git(src_root, "status", "--porcelain")
    head_after = git(src_root, "rev-parse", "HEAD")
    unchanged = (tree_before == tree_after and wt_before == wt_after
                 and head_before == head_after)

    print("\n" + "=" * 72)
    print("INNOCUITÉ (MemoLib)")
    print("=" * 72)
    print(f"[P] git status avant/après : {'propre/propre' if not wt_before and not wt_after else 'CHANGÉ'}")
    print(f"[Q] tree avant == après : {tree_before == tree_after} "
          f"({tree_before[:12]} == {tree_after[:12]})")
    print(f"[Q] HEAD avant == après : {head_before == head_after}")
    print(f"[R] aucun apply/commit/push : run_controlled_apply NON importé, "
          f"aucun git mutant exécuté")
    print(f"[O] durée : {dur}s")
    print(f"VERDICT MemoLib byte-for-byte inchangé : {unchanged}")

    report["memolib_unchanged"] = unchanged
    Path("terrain_observe_result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nRapport JSON : terrain_observe_result.json")
    return 0 if unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
