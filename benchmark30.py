"""
MemoLibDev — Étape 3 : Benchmark élargi (30 missions, 7B)
=========================================================

Variable UNIQUE modifiée vs étape 2 : la TAILLE de l'échantillon
(11 -> 30 missions catégorisées). AUCUN changement de code moteur :
on réutilise EXACTEMENT benchmark_models.run_one (même contexte, même
planner, même R1, même prompt, même pondération par rôle de l'étape 2).

Modèle : qwen2.5-coder:7b (modèle de laboratoire, inchangé).

Mesure centrale : valid + relevant (OK ET cible pertinente), par
catégorie et global. STRICTEMENT READ_ONLY (run_one n'appelle jamais
run_controlled_apply). Prouve HEAD/working tree cible inchangés.
"""

from __future__ import annotations

from pathlib import Path
import json
import subprocess

from project_target import resolve_target, ProjectTargetError
from llm.ollama_provider import OllamaProvider
from benchmark_models import run_one, snapshot


MODEL = "qwen2.5-coder:7b"

# 30 missions catégorisées (répartition demandée).
MISSIONS = [
    # 6 × bug/code
    ("bug_code", "B01", "corrige le bug d'affichage dans le composant de navigation"),
    ("bug_code", "B02", "analyse pourquoi le composant de login ne se rend pas correctement"),
    ("bug_code", "B03", "identifie la fonction responsable du formatage des dates"),
    ("bug_code", "B04", "analyse la gestion des erreurs dans le client API"),
    ("bug_code", "B05", "trouve le composant qui gère l'upload de fichiers"),
    ("bug_code", "B06", "analyse la logique de pagination des listes"),
    # 5 × authentification / sécurité
    ("auth_secu", "A01", "analyse la navigation vers la page de connexion /fr/auth/login"),
    ("auth_secu", "A02", "analyse le flux d'authentification Clerk et le rôle du proxy"),
    ("auth_secu", "A03", "analyse la gestion des sessions et des tokens"),
    ("auth_secu", "A04", "identifie les points de contrôle d'accès des routes protégées"),
    ("auth_secu", "A05", "analyse la validation des entrées utilisateur côté serveur"),
    # 5 × routes / API
    ("routes_api", "R01", "analyse l'organisation des routes publiques et protégées"),
    ("routes_api", "R02", "identifie les endpoints API liés aux dossiers"),
    ("routes_api", "R03", "analyse le middleware appliqué aux routes"),
    ("routes_api", "R04", "analyse la route API d'envoi d'emails"),
    ("routes_api", "R05", "analyse la structure des routes de l'espace workspace"),
    # 4 × tests
    ("tests", "T01", "analyse la couverture de tests autour de l'authentification"),
    ("tests", "T02", "identifie les tests du client email et leurs scénarios"),
    ("tests", "T03", "analyse les mocks utilisés dans les tests"),
    ("tests", "T04", "identifie les scénarios de test manquants pour les dossiers"),
    # 4 × configuration
    ("config", "C01", "analyse la configuration next.config et les variables d'environnement"),
    ("config", "C02", "analyse la configuration TypeScript tsconfig"),
    ("config", "C03", "analyse les dépendances déclarées dans package.json"),
    ("config", "C04", "analyse la configuration de la base de données prisma"),
    # 3 × documentation / règles
    ("doc_regles", "D01", "analyse la documentation du projet et le cahier des charges"),
    ("doc_regles", "D02", "analyse les règles de l'agent de sécurité dans la documentation"),
    ("doc_regles", "D03", "analyse le guide d'installation et de configuration"),
    # 3 × ambiguës
    ("ambigu", "X01", "corrige le login"),
    ("ambigu", "X02", "améliore l'authentification"),
    ("ambigu", "X03", "répare le problème"),
]


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — BENCHMARK 30 MISSIONS (7B, READ_ONLY)")
    print("=" * 72)

    try:
        target = resolve_target()
    except ProjectTargetError as e:
        print(f"[STOP] Cible non résolue : {e}")
        return 2
    root = target.git_root
    print(f"Cible : {root} (HEAD {target.head})")

    if not OllamaProvider(model=MODEL, http_timeout=10.0).available:
        print(f"[STOP] Modèle indisponible : {MODEL}")
        return 3

    before = snapshot(root)
    records = []
    for cat, mid, mission in MISSIONS:
        r = run_one(MODEL, mid, mission, target)
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
    after = snapshot(root)

    # ----- Agrégats globaux -----
    n = len(records)
    def count(pred):
        return sum(1 for r in records if pred(r))
    ok = count(lambda r: r["status"] == "OK")
    vr = count(lambda r: r["status"] == "OK" and r.get("target_relevance") == "pertinente")
    nonpert = count(lambda r: r.get("target_relevance") == "non_pertinente")
    halluc = count(lambda r: r.get("hallucination"))
    block = count(lambda r: r["status"] == "BLOCK")
    dur = round(sum(r["duration_s"] for r in records) / n, 2)

    print("\n" + "=" * 72)
    print("AGRÉGATS GLOBAUX (30 missions)")
    print("=" * 72)
    print(f"Valid (OK)             : {ok}/{n} ({round(100*ok/n)}%)")
    print(f"Valid + Relevant       : {vr}/{n} ({round(100*vr/n)}%)")
    print(f"Cible non pertinente   : {nonpert}/{n}")
    print(f"BLOCK                  : {block}/{n}")
    print(f"Hallucination          : {halluc}/{n}")
    print(f"Durée moyenne          : {dur}s")

    # ----- Par catégorie -----
    print("\n" + "=" * 72)
    print("PAR CATÉGORIE (valid+relevant / total)")
    print("=" * 72)
    cats: dict[str, list] = {}
    for r in records:
        cats.setdefault(r["category"], []).append(r)
    per_cat = {}
    for cat, rs in cats.items():
        c_vr = sum(1 for r in rs if r["status"] == "OK"
                   and r.get("target_relevance") == "pertinente")
        c_ok = sum(1 for r in rs if r["status"] == "OK")
        per_cat[cat] = {"n": len(rs), "ok": c_ok, "valid_relevant": c_vr}
        print(f"  {cat:12} : V+R {c_vr}/{len(rs)}   (valid {c_ok}/{len(rs)})")

    # ----- Innocuité -----
    ro = (before["head"] == after["head"]
          and before["porcelain"] == after["porcelain"]
          and before["commits"] == after["commits"])
    print("\n" + "=" * 72)
    print("PREUVES READ-ONLY :", "CONFIRMÉ" if ro else "ANOMALIE")
    print(f"  HEAD {before['head'][:12]} == {after['head'][:12]} ; "
          f"working_tree {'propre' if not after['porcelain'] else 'MODIFIÉ'}")
    print("=" * 72)

    out = {"model": MODEL, "n": n,
           "global": {"valid": ok, "valid_relevant": vr,
                      "non_pertinente": nonpert, "block": block,
                      "hallucination": halluc, "avg_duration_s": dur},
           "per_category": per_cat, "records": records,
           "readonly_confirmed": ro,
           "reference_etape2": "7B 11 missions : valid 7/11, valid+relevant 4/11"}
    Path("benchmark30_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Rapport JSON : benchmark30_result.json")
    return 0 if ro and halluc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
