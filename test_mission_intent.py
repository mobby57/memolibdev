"""
MemoLibDev — Test 5.2 : compréhension structurée de mission
===========================================================

Vérifie l'extraction déterministe + la REPRÉSENTATION DE L'INCERTITUDE
(UNKNOWN quand aucune preuve lexicale ; aucune invention).
"""

from __future__ import annotations

from mission_intent import analyze_mission, StructuredIntent, UNKNOWN


PASS: list[str] = []
FAIL: list[str] = []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST 5.2 compréhension de mission")
    print("=" * 72)

    # ---- Bug code ----
    print("\n[Bug code]")
    i = analyze_mission("corrige le bug d'affichage du composant de navigation")
    ok("bug_objectif", i.objectif == "CORRIGER", i.objectif)
    ok("bug_type", i.type_mission == "BUG", i.type_mission)
    ok("bug_domaine", i.domaine in ("UI", "ROUTES"), i.domaine)

    # ---- Auth / sécurité ----
    print("\n[Auth/sécurité]")
    i = analyze_mission("corrige le problème de connexion Clerk et le token de session")
    ok("auth_domaine", i.domaine == "AUTH", i.domaine)
    ok("auth_objectif", i.objectif == "CORRIGER", i.objectif)
    ok("auth_risque_high", i.risque == "HIGH", i.risque)   # auth/token/session
    ok("auth_cibles", "clerk" in i.cibles_probables and "token" in i.cibles_probables,
       str(i.cibles_probables))

    # ---- Routes / API ----
    print("\n[Routes/API]")
    i = analyze_mission("analyse le middleware appliqué aux routes API")
    ok("routes_domaine", i.domaine == "ROUTES", i.domaine)
    ok("routes_objectif", i.objectif == "ANALYSER", i.objectif)
    ok("routes_type", i.type_mission == "ANALYSE", i.type_mission)
    ok("routes_cibles", "middleware" in i.cibles_probables, str(i.cibles_probables))

    # ---- Tests ----
    print("\n[Tests]")
    i = analyze_mission("analyse la couverture de tests autour de l'authentification")
    ok("tests_domaine", i.domaine in ("TESTS", "AUTH"), i.domaine)
    ok("tests_cible", "tests" in i.cibles_probables or "auth" in i.cibles_probables,
       str(i.cibles_probables))

    # ---- Config ----
    print("\n[Config]")
    i = analyze_mission("analyse la configuration next.config et les variables d'environnement")
    ok("config_domaine", i.domaine == "CONFIG", i.domaine)

    # ---- Doc / règles ----
    print("\n[Doc/règles]")
    i = analyze_mission("analyse la documentation du projet et le cahier des charges")
    ok("doc_domaine", i.domaine == "DOC", i.domaine)
    ok("doc_objectif", i.objectif == "ANALYSER", i.objectif)

    # ---- Ajout de feature ----
    print("\n[Feature]")
    i = analyze_mission("ajoute une nouvelle page de profil utilisateur")
    ok("feature_objectif", i.objectif == "AJOUTER", i.objectif)
    ok("feature_type", i.type_mission == "FEATURE", i.type_mission)
    ok("feature_domaine", i.domaine == "UI", i.domaine)

    # ---- Mission ambiguë ----
    print("\n[Ambiguë]")
    i = analyze_mission("corrige le login")
    ok("ambigu_objectif", i.objectif == "CORRIGER", i.objectif)
    ok("ambigu_domaine", i.domaine == "AUTH", i.domaine)
    # Confiance pas maximale (mission courte mais identifiable).
    ok("ambigu_confiance", i.confiance in ("MEDIUM", "HIGH"), i.confiance)

    # ---- Mission très courte -> incertitude ----
    print("\n[Très courte -> UNKNOWN]")
    i = analyze_mission("aide")
    ok("courte_objectif_unknown", i.objectif == UNKNOWN, i.objectif)
    ok("courte_domaine_unknown", i.domaine == UNKNOWN, i.domaine)
    ok("courte_type_unknown", i.type_mission == UNKNOWN, i.type_mission)
    ok("courte_risque_unknown", i.risque == UNKNOWN, i.risque)
    ok("courte_confiance_low", i.confiance == "LOW", i.confiance)

    # ---- Mission inconnue (hors vocabulaire) -> aucune invention ----
    print("\n[Inconnue -> aucune invention]")
    i = analyze_mission("blorp zorg flibber wobble")
    ok("inconnue_domaine_unknown", i.domaine == UNKNOWN, i.domaine)
    ok("inconnue_objectif_unknown", i.objectif == UNKNOWN, i.objectif)
    ok("inconnue_pas_de_cible", i.cibles_probables == (), str(i.cibles_probables))
    ok("inconnue_pas_invente",
       i.domaine == UNKNOWN and i.cibles_probables == (),
       "aucun domaine/cible inventé")

    # ---- Vide ----
    print("\n[Vide]")
    i = analyze_mission("")
    ok("vide_tout_unknown",
       i.objectif == UNKNOWN and i.domaine == UNKNOWN
       and i.type_mission == UNKNOWN and i.risque == UNKNOWN, "")

    # ---- Risque : suppression / production ----
    print("\n[Risque élevé : suppression/prod]")
    i = analyze_mission("supprime la table en production")
    ok("risque_suppr_prod_high", i.risque == "HIGH", i.risque)
    ok("objectif_supprimer", i.objectif == "SUPPRIMER", i.objectif)

    # ---- Déterminisme ----
    print("\n[Déterminisme]")
    a = analyze_mission("corrige le problème de connexion Clerk").to_dict()
    b = analyze_mission("corrige le problème de connexion Clerk").to_dict()
    ok("deterministe", a == b, "deux appels identiques")

    # ---- Frozen / immuable ----
    print("\n[Immuable]")
    i = analyze_mission("analyse les routes")
    try:
        i.domaine = "X"  # type: ignore
        ok("frozen", False, "mutation possible !")
    except Exception:
        ok("frozen", True, "StructuredIntent frozen")

    print("\n" + "=" * 72)
    print(f"RÉSULTAT 5.2 : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print("Compréhension déterministe. Incertitude représentée (UNKNOWN).")
    print("Aucune invention sans preuve lexicale. Aucun LLM.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
