"""
MemoLibDev — Test de la métrique de pertinence (étape 4)
========================================================

Vérifie que classify_relevance produit les bons verdicts par catégorie.
Déterministe, aucun LLM, aucun accès moteur en écriture.
"""

from __future__ import annotations

from relevance_metric import (
    classify_relevance, verdict_score,
    PERTINENT, PARTIEL, NON_PERTINENT,
)


PASS: list[str] = []
FAIL: list[str] = []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def check(cat, target, expected):
    v = classify_relevance(cat, target)
    ok(f"{cat}:{target or 'None'}", v.verdict == expected,
       f"{v.verdict} (attendu {expected}) [{v.reason}]")


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST métrique de pertinence (étape 4)")
    print("=" * 72)

    print("\n[Code -> src pertinent]")
    check("bug_code", "src/app/x.ts", PERTINENT)
    check("bug_code", "src/components/Btn.tsx", PERTINENT)
    check("bug_code", "src/__tests__/x.test.ts", PARTIEL)      # test = voisin
    check("bug_code", "docs/CAHIER.md", NON_PERTINENT)         # doc != code
    check("bug_code", ".amazonq/rules/x.md", NON_PERTINENT)

    print("\n[Doc/règles -> doc/rules pertinent (correctif principal)]")
    check("doc_regles", "README.md", PERTINENT)
    check("doc_regles", "docs/CAHIER_DES_CHARGES.md", PERTINENT)
    check("doc_regles", ".amazonq/rules/agent-security-engineer.md", PERTINENT)
    check("doc_regles", ".vscode/SETUP_GUIDE.md", PERTINENT)   # .vscode = RULES
    check("doc_regles", "src/app/x.ts", NON_PERTINENT)         # code != doc

    print("\n[Tests -> *.test pertinent]")
    check("tests", "src/__tests__/x.test.ts", PERTINENT)
    check("tests", "x.spec.ts", PERTINENT)
    check("tests", "src/app/x.ts", PARTIEL)                    # source = voisin

    print("\n[Config -> config pertinent]")
    check("config", "next.config.js", PERTINENT)
    check("config", "tsconfig.json", PERTINENT)
    check("config", "package.json", PERTINENT)
    check("config", "scripts/deploy.ts", PARTIEL)              # SCRIPT = voisin
    # (5A) SCRIPT est désormais distinct de SOURCE : un vrai composant
    # métier (src/) n'est plus un voisin de config -> NON_PERTINENT.
    check("config", "src/app/x.ts", NON_PERTINENT)
    check("config", "dist/bundle.js", NON_PERTINENT)           # GENERATED

    print("\n[Auth/Routes -> hubs proxy/middleware pertinents]")
    check("auth_secu", "proxy.ts", PERTINENT)
    check("routes_api", "middleware.ts", PERTINENT)
    check("auth_secu", "src/app/[locale]/auth/login/page.tsx", PERTINENT)
    check("routes_api", "src/app/api/x/route.ts", PERTINENT)
    check("auth_secu", "docs/x.md", NON_PERTINENT)

    print("\n[Ambigu -> src pertinent, voisins partiels]")
    check("ambigu", "src/app/[locale]/auth/login/page.tsx", PERTINENT)
    check("ambigu", "docs/x.md", NON_PERTINENT)

    print("\n[Cas sans cible -> NON_PERTINENT]")
    check("bug_code", None, NON_PERTINENT)

    print("\n[Score numérique]")
    ok("score_pertinent", verdict_score(PERTINENT) == 1.0, "")
    ok("score_partiel", verdict_score(PARTIEL) == 0.5, "")
    ok("score_non", verdict_score(NON_PERTINENT) == 0.0, "")

    print("\n[Déterminisme]")
    a = classify_relevance("doc_regles", "README.md").verdict
    b = classify_relevance("doc_regles", "README.md").verdict
    ok("deterministe", a == b, "")

    print("\n" + "=" * 72)
    print(f"RÉSULTAT MÉTRIQUE : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
