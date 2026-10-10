"""
MemoLibDev — Étape 4 : Re-scoring du benchmark 30 (nouvelle métrique)
=====================================================================

Relit benchmark30_result.json (cibles DÉJÀ produites par le 7B) et
applique la NOUVELLE métrique de pertinence par catégorie. AUCUNE
ré-exécution LLM, AUCUN accès au moteur en écriture : on ne change que
l'INSTRUMENT DE MESURE. Produit la comparaison ancienne vs nouvelle
métrique, globale et par catégorie.
"""

from __future__ import annotations

from pathlib import Path
import json

from relevance_metric import classify_relevance, verdict_score, PERTINENT, PARTIEL


SRC = "benchmark30_result.json"


def main() -> int:
    data = json.loads(Path(SRC).read_text(encoding="utf-8"))
    records = data["records"]

    print("=" * 72)
    print("RE-SCORING BENCHMARK 30 — nouvelle métrique de pertinence")
    print("(mêmes cibles 7B, aucune ré-exécution LLM)")
    print("=" * 72)

    # Ancienne métrique : "cible_pertinente" == target_relevance == 'pertinente'.
    old_valid_relevant = sum(
        1 for r in records
        if r["status"] == "OK" and r.get("target_relevance") == "pertinente")

    # Nouvelle métrique par catégorie.
    new_pert = new_part = new_non = 0
    weighted = 0.0
    per_cat: dict[str, dict] = {}
    print(f"\n{'cat':12} {'id':5} {'statut':6} {'cible':52} {'ancien':10} {'NOUVEAU'}")
    print("-" * 110)
    for r in records:
        cat = r["category"]
        target = r.get("target")
        v = classify_relevance(cat, target)
        if r["status"] != "OK":
            # Pas de proposition : on ne compte pas comme pertinence,
            # mais on trace (NON_PERTINENT par absence de cible).
            verdict = v.verdict
        else:
            verdict = v.verdict
        if verdict == PERTINENT:
            new_pert += 1
        elif verdict == PARTIEL:
            new_part += 1
        else:
            new_non += 1
        weighted += verdict_score(verdict) if r["status"] == "OK" else 0.0

        pc = per_cat.setdefault(cat, {"n": 0, "pert": 0, "part": 0,
                                      "old_pert": 0})
        pc["n"] += 1
        if verdict == PERTINENT:
            pc["pert"] += 1
        elif verdict == PARTIEL:
            pc["part"] += 1
        if r["status"] == "OK" and r.get("target_relevance") == "pertinente":
            pc["old_pert"] += 1

        old = r.get("target_relevance", "-")
        try:
            tshow = (str(target) or "-").encode("ascii", "replace").decode()
        except Exception:
            tshow = "-"
        print(f"{cat:12} {r['id']:5} {r['status']:6} {tshow[:52]:52} "
              f"{str(old):10} {verdict}")

    n = len(records)
    print("\n" + "=" * 72)
    print("COMPARAISON GLOBALE")
    print("=" * 72)
    print(f"Missions                         : {n}")
    print(f"ANCIENNE métrique (pertinente)   : {old_valid_relevant}/{n} "
          f"({round(100*old_valid_relevant/n)}%)")
    print(f"NOUVELLE : PERTINENT             : {new_pert}/{n} "
          f"({round(100*new_pert/n)}%)")
    print(f"NOUVELLE : PARTIELLEMENT         : {new_part}/{n}")
    print(f"NOUVELLE : NON_PERTINENT         : {new_non}/{n}")
    print(f"NOUVELLE : score pondéré (OK)    : {round(weighted,1)}/{n} "
          f"({round(100*weighted/n)}%)")

    print("\n" + "=" * 72)
    print("PAR CATÉGORIE (ancien pert -> NOUVEAU pert [+partiel])")
    print("=" * 72)
    for cat, pc in per_cat.items():
        print(f"  {cat:12} : {pc['old_pert']}/{pc['n']} "
              f"-> {pc['pert']}/{pc['n']} [+{pc['part']} partiel]")

    out = {"source": SRC, "n": n,
           "old_valid_relevant": old_valid_relevant,
           "new": {"pertinent": new_pert, "partiel": new_part,
                   "non_pertinent": new_non,
                   "weighted_ok": round(weighted, 2)},
           "per_category": per_cat}
    Path("rescore_benchmark30_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nRapport JSON : rescore_benchmark30_result.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
