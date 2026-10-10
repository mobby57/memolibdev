"""
MemoLibDev — Benchmark 30 REPRODUCTIBLE (clone figé)
====================================================

Exécute UN SEUL benchmark 30 contre un CLONE FIGÉ du commit cible
(Option B). Réutilise EXACTEMENT :
  - les 30 MISSIONS de benchmark30 ;
  - run_one (vrai pipeline build_mission_context -> inspect_target
    -> 5A -> 5.2 -> 5.3) — AUCUNE réimplémentation du scoring ;
  - le modèle de référence MODEL de benchmark30 (7B).

Différence unique vs benchmark30.py : la cible n'est plus le working
tree vivant, mais un clone figé au HEAD demandé (frozen_clone). Le
working tree réel de MemoLib ne participe donc jamais à l'inspection.

Aucune modification du moteur / project_inspector / 5.3. Lecture seule
sur la source. Aucun apply/commit/push.
"""

from __future__ import annotations

from pathlib import Path
import json
import subprocess

from project_target import resolve_target, ProjectTargetError
from llm.ollama_provider import OllamaProvider
from benchmark30 import MISSIONS, run_one, MODEL
from benchmark_snapshot import frozen_clone


def git(root: Path, *a) -> str:
    return subprocess.run(["git", "-C", str(root), *a], text=True,
                          capture_output=True, encoding="utf-8",
                          errors="replace").stdout.strip()


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — BENCHMARK 30 REPRODUCTIBLE (clone figé)")
    print("=" * 72)

    # Cible réelle (source) : résolue via MEMOLIBDEV_TARGET.
    try:
        source = resolve_target()
    except ProjectTargetError as e:
        print(f"[STOP] Cible non résolue : {e}")
        return 2

    src_root = source.git_root
    head_demande = source.head_full
    wt_before = (git(src_root, "status", "--porcelain"))
    print(f"Source      : {src_root}")
    print(f"HEAD demandé: {head_demande}")
    print(f"Modèle      : {MODEL}")
    print(f"WT source avant: {'propre' if not wt_before else 'MODIFIÉ'}")

    if not OllamaProvider(model=MODEL, http_timeout=10.0).available:
        print(f"[STOP] Modèle indisponible : {MODEL}")
        return 3

    records = []
    clone_root = None
    # Exécution contre le CLONE FIGÉ au HEAD demandé.
    with frozen_clone(source, head=head_demande) as snap:
        clone_root = str(snap.git_root)
        print(f"Clone figé  : {clone_root} (HEAD {snap.head_full[:12]})")
        assert snap.head_full == head_demande, "HEAD du clone != HEAD demandé"
        assert str(snap.git_root) != str(src_root), "clone == source !"
        print("-" * 72)
        for cat, mid, mission in MISSIONS:
            r = run_one(MODEL, mid, mission, snap)   # VRAI pipeline, clone figé
            r["category"] = cat
            records.append(r)
            valid_rel = (r["status"] == "OK"
                         and r.get("target_relevance") == "pertinente")
            try:
                tgt = str(r.get("target")).encode("ascii", "replace").decode()
            except Exception:
                tgt = "?"
            print(f"  [{cat:10}] {mid} {r['status']:6} "
                  f"pert={r.get('target_relevance','-'):14} "
                  f"V+R={'Y' if valid_rel else '.'} halluc={r['hallucination']} "
                  f"-> {tgt}")

    # Le clone est détruit en sortie du with (prouvé par test_benchmark_snapshot).
    wt_after = git(src_root, "status", "--porcelain")

    # ----- Agrégats -----
    n = len(records)
    def count(pred): return sum(1 for r in records if pred(r))
    ok = count(lambda r: r["status"] == "OK")
    vr = count(lambda r: r["status"] == "OK" and r.get("target_relevance") == "pertinente")
    nonpert = count(lambda r: r.get("target_relevance") == "non_pertinente")
    halluc = count(lambda r: r.get("hallucination"))
    block = count(lambda r: r["status"] == "BLOCK")
    dur = round(sum(r["duration_s"] for r in records) / n, 2) if n else 0

    print("\n" + "=" * 72)
    print("AGRÉGATS GLOBAUX (clone figé)")
    print("=" * 72)
    print(f"Valid (OK)             : {ok}/{n} ({round(100*ok/n)}%)")
    print(f"Valid + Relevant       : {vr}/{n} ({round(100*vr/n)}%)")
    print(f"Cible non pertinente   : {nonpert}/{n}")
    print(f"BLOCK                  : {block}/{n}")
    print(f"Hallucination          : {halluc}/{n}")
    print(f"Durée moyenne          : {dur}s")

    cats: dict[str, list] = {}
    for r in records:
        cats.setdefault(r["category"], []).append(r)
    per_cat = {}
    print("\nPAR CATÉGORIE (valid+relevant / total)")
    for cat, rs in cats.items():
        c_vr = sum(1 for r in rs if r["status"] == "OK"
                   and r.get("target_relevance") == "pertinente")
        c_ok = sum(1 for r in rs if r["status"] == "OK")
        per_cat[cat] = {"n": len(rs), "ok": c_ok, "valid_relevant": c_vr}
        print(f"  {cat:12} : V+R {c_vr}/{len(rs)}  (valid {c_ok}/{len(rs)})")

    # ----- Innocuité -----
    wt_ok = (wt_before == wt_after)
    clone_removed = not Path(clone_root).exists() if clone_root else True
    print("\n" + "=" * 72)
    print("PREUVES REPRODUCTIBILITÉ / READ-ONLY")
    print(f"  working tree source inchangé : {wt_ok}")
    print(f"  clone figé supprimé          : {clone_removed}")
    print(f"  halluc                       : {halluc}")
    print("=" * 72)

    out = {"mode": "frozen_clone", "model": MODEL, "n": n,
           "head_demande": head_demande,
           "global": {"valid": ok, "valid_relevant": vr,
                      "non_pertinente": nonpert, "block": block,
                      "hallucination": halluc, "avg_duration_s": dur},
           "per_category": per_cat, "records": records,
           "working_tree_source_unchanged": wt_ok,
           "clone_removed": clone_removed}
    Path("benchmark30_frozen_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Rapport JSON : benchmark30_frozen_result.json")
    return 0 if (wt_ok and halluc == 0 and clone_removed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
