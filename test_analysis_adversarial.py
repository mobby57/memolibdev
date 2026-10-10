"""
MemoLibDev — V0.1.2 : Tests ADVERSARIAUX du mode ANALYSER
=========================================================

Objectif : FAIRE ÉCHOUER l'analyse. Un bon système de contrôle doit
savoir dire « les preuves disponibles ne permettent pas de déterminer la
cause » plutôt que de fabriquer une cause à partir de simples mots-clés.

Distinction imposée (jamais confondue) :
    FAIT      : « j'ai observé X dans Y:Z »          -> faits_verifies
    HYPOTHÈSE : « X pourrait contribuer »            -> jamais présentée comme cause
    CAUSE     : « les éléments permettent d'attribuer raisonnablement »
                -> UNIQUEMENT si plusieurs éléments COHÉRENTS et observés

Règle gravée : la simple présence de AUTH/LOGIN/REDIRECT/SIGNIN/ROUTE/
ERROR/LOCALE ne suffit JAMAIS à établir une cause.

Doublures locales (aucun moteur, aucun git, aucun LLM, aucun disque).
Tous les tests sont DÉTERMINISTES.

Scénarios :
  AX1  Faux signal AUTH (import seul)        -> pas de cause HIGH
  AX2  Faux signal REDIRECT (valide)         -> pas de cause
  AX3  Causes multiples (2 fichiers)         -> pas de choix arbitraire
  AX4  Preview tronqué                       -> cause None/MEDIUM/LOW + incertitude
  AX5  Fichier causal absent du contexte     -> jamais de cause établie dessus
  AX6  Fait pertinent mais non causal        -> fait oui, cause non
  AX7  Coïncidence lexicale multi-fichiers   -> aucune cause automatique
  AX8  Preuves insuffisantes (1-2 indices)   -> LOW + incertitudes
  AX9  Source invalide (hors contexte)       -> rejet strict (0 fait étranger)
  AX10 Contradiction entre deux faits        -> contradiction explicite, pas masquée
"""

from __future__ import annotations

from dataclasses import dataclass

from analysis_builder import build_analysis, VerifiedFact


PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


@dataclass(frozen=True)
class FakeVersion:
    text_sha256: str
    byte_sha256: str = "b" * 64


@dataclass(frozen=True)
class FakeRelevantFile:
    path: str
    preview: str
    score: int = 50
    kind: str = "CODE"
    version: FakeVersion = None


@dataclass(frozen=True)
class FakeCtx:
    mission_text: str
    relevant_files: tuple
    budget_reduced: bool = False


@dataclass(frozen=True)
class FakeIntent:
    objectif: str = "ANALYSER"
    domaine: str = "AUTH"
    type_mission: str = "ANALYSE"
    cibles_probables: tuple = ()
    risque: str = "HIGH"
    confiance: str = "HIGH"


def _rf(path, preview, sha):
    return FakeRelevantFile(path=path, preview=preview,
                            version=FakeVersion(text_sha256=sha))


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TESTS ADVERSARIAUX ANALYSER (V0.1.2)")
    print("=" * 72)

    # ============================================================
    # AX1 — FAUX SIGNAL AUTH : un import signIn, aucun défaut de navigation.
    # ============================================================
    print("\n[AX1] faux signal AUTH (import seul)")
    ctx = FakeCtx(
        mission_text="Analyse le problème de navigation vers /fr/auth/login",
        relevant_files=(_rf(
            "src/components/Header.tsx",
            "import { signIn } from 'next-auth/react';\n"
            "export function Header() {\n"
            "  return <nav>Menu</nav>;\n"
            "}\n",
            "a1" + "0" * 62),),
    )
    r = build_analysis(ctx, FakeIntent(domaine="AUTH"))
    ok("AX1 un import signIn ne donne PAS une cause HIGH",
       not (r.confiance == "HIGH" and r.cause_probable is not None),
       f"confiance={r.confiance} cause={'oui' if r.cause_probable else 'non'}")
    ok("AX1 l'import reste un FAIT observable",
       any(f.fichier == "src/components/Header.tsx" for f in r.faits_verifies))

    # ============================================================
    # AX2 — FAUX SIGNAL REDIRECT : redirect parfaitement valide.
    # ============================================================
    print("\n[AX2] faux signal REDIRECT (valide)")
    ctx = FakeCtx(
        mission_text="Analyse la navigation login",
        relevant_files=(_rf(
            "src/app/page.tsx",
            "import { redirect } from 'next/navigation';\n"
            "export default function Home() {\n"
            "  // comportement normal et attendu\n"
            "  redirect('/dashboard');\n"
            "}\n",
            "a2" + "0" * 62),),
    )
    r = build_analysis(ctx, FakeIntent(domaine="ROUTES"))
    ok("AX2 présence de 'redirect' ne constitue PAS une cause",
       r.cause_probable is None or r.confiance != "HIGH",
       f"confiance={r.confiance} cause={'oui' if r.cause_probable else 'non'}")

    # ============================================================
    # AX3 — CAUSES MULTIPLES : deux fichiers également plausibles.
    # ============================================================
    print("\n[AX3] causes multiples -> pas de choix arbitraire")
    preview_a = (
        "import { signIn } from 'next-auth/react';\n"
        "export async function GET(req) {\n"
        "  if (!session) { return NextResponse.redirect('/login'); }\n"
        "}\n")
    preview_b = (
        "import { getServerSession } from 'next-auth';\n"
        "export async function POST(req) {\n"
        "  if (!token) { return NextResponse.redirect('/login'); }\n"
        "}\n")
    ctx = FakeCtx(
        mission_text="Analyse le problème de connexion login redirect",
        relevant_files=(
            _rf("src/app/api/auth/a/route.ts", preview_a, "a3" + "0" * 62),
            _rf("src/app/api/auth/b/route.ts", preview_b, "b3" + "0" * 62),
        ),
    )
    r = build_analysis(ctx, FakeIntent(domaine="AUTH"))
    # Si une cause est donnée, elle ne doit pas désigner arbitrairement UN
    # fichier alors que deux sont également plausibles : soit indéterminée,
    # soit elle signale explicitement la pluralité.
    cause = r.cause_probable or ""
    arbitraire = (r.confiance == "HIGH" and r.cause_probable is not None
                  and ("a/route.ts" in cause) != ("b/route.ts" in cause)
                  and "plusieurs" not in cause.lower()
                  and "départager" not in cause.lower()
                  and "ne permettent pas" not in cause.lower())
    ok("AX3 pas de désignation arbitraire d'un seul fichier parmi deux",
       not arbitraire, f"cause={cause[:80]!r}")
    ok("AX3 pluralité reflétée (incertitude ou confiance réduite)",
       (r.confiance != "HIGH")
       or any("plusieurs" in u.lower() or "départager" in u.lower()
              for u in r.incertitudes)
       or "plusieurs" in cause.lower(),
       f"confiance={r.confiance}")

    # ============================================================
    # AX4 — PREVIEW TRONQUÉ : la partie pertinente est absente.
    # ============================================================
    print("\n[AX4] preview tronqué -> cause None/MEDIUM/LOW + incertitude")
    ctx = FakeCtx(
        mission_text="Analyse la redirection après login",
        relevant_files=(_rf(
            "src/app/[locale]/auth/login/page.tsx",
            "import React from 'react';\n"
            "// ... (contenu tronqué par le budget) ...\n",
            "a4" + "0" * 62),),
        budget_reduced=True,
    )
    r = build_analysis(ctx, FakeIntent(domaine="AUTH"))
    ok("AX4 pas de cause HIGH sur preview tronqué",
       r.confiance in ("LOW", "MEDIUM") or r.cause_probable is None,
       f"confiance={r.confiance}")
    ok("AX4 incertitude explicite (budget/contenu)",
       any("budget" in u.lower() or "portions" in u.lower()
           or "contenu" in u.lower() for u in r.incertitudes),
       str(r.incertitudes))

    # ============================================================
    # AX5 — FICHIER CAUSAL ABSENT : la vraie cause est hors contexte.
    # ============================================================
    print("\n[AX5] fichier causal absent -> jamais de cause établie dessus")
    ctx = FakeCtx(
        mission_text="Analyse pourquoi la redirection locale échoue",
        relevant_files=(_rf(
            "src/components/Button.tsx",
            "export function Button() { return <button/>; }\n",
            "a5" + "0" * 62),),
    )
    r = build_analysis(ctx, FakeIntent(domaine="ROUTES"))
    # Le vrai coupable simulé serait 'middleware.ts' (absent du contexte).
    ok("AX5 aucun fait ne cite un fichier hors contexte",
       all(f.fichier == "src/components/Button.tsx" for f in r.faits_verifies))
    ok("AX5 aucune cause attribuée (fichier causal absent)",
       r.cause_probable is None, f"cause={'oui' if r.cause_probable else 'non'}")
    ok("AX5 'middleware' n'apparaît pas comme cause inventée",
       "middleware" not in (r.cause_probable or "").lower())

    # ============================================================
    # AX6 — FAIT PERTINENT MAIS NON CAUSAL.
    # ============================================================
    print("\n[AX6] fait pertinent mais non causal -> fait oui, cause non")
    ctx = FakeCtx(
        mission_text="Analyse la connexion",
        relevant_files=(_rf(
            "src/lib/auth.ts",
            "import { getToken } from 'next-auth/jwt';\n"
            "// utilitaire de lecture de token, sans logique de navigation\n",
            "a6" + "0" * 62),),
    )
    r = build_analysis(ctx, FakeIntent(domaine="AUTH"))
    ok("AX6 le fait AUTH est bien listé",
       any(f.categorie == "AUTH" for f in r.faits_verifies)
       or any("auth" in f.extrait.lower() for f in r.faits_verifies))
    ok("AX6 mais aucune cause HIGH n'en est tirée",
       not (r.confiance == "HIGH" and r.cause_probable is not None),
       f"confiance={r.confiance}")

    # ============================================================
    # AX7 — COÏNCIDENCE LEXICALE : même mot, fichiers sans relation.
    # ============================================================
    print("\n[AX7] coïncidence lexicale -> aucune conclusion causale")
    ctx = FakeCtx(
        mission_text="Analyse le login",
        relevant_files=(
            _rf("src/a.ts", "// login mentionné en commentaire\n"
                            "export const a = 1;\n", "a7" + "0" * 62),
            _rf("src/b.ts", "// login encore un commentaire\n"
                            "export const b = 2;\n", "b7" + "0" * 62),
        ),
    )
    r = build_analysis(ctx, FakeIntent(domaine="AUTH"))
    ok("AX7 aucune cause automatique sur simple coïncidence lexicale",
       r.cause_probable is None or r.confiance != "HIGH",
       f"confiance={r.confiance} cause={'oui' if r.cause_probable else 'non'}")

    # ============================================================
    # AX8 — PREUVES INSUFFISANTES : un ou deux indices faibles.
    # ============================================================
    print("\n[AX8] preuves insuffisantes -> LOW + incertitudes")
    ctx = FakeCtx(
        mission_text="Analyse",
        relevant_files=(_rf(
            "src/x.ts", "export const x = 1;\n", "a8" + "0" * 62),),
    )
    r = build_analysis(ctx, FakeIntent(domaine="UNKNOWN", risque="UNKNOWN",
                                       confiance="LOW"))
    ok("AX8 confiance LOW", r.confiance == "LOW", r.confiance)
    ok("AX8 aucune cause", r.cause_probable is None)
    ok("AX8 incertitudes présentes", len(r.incertitudes) > 0)

    # ============================================================
    # AX9 — SOURCE INVALIDE : impossible de fabriquer un fait hors contexte.
    # ============================================================
    print("\n[AX9] source invalide -> rejet strict")
    ctx = FakeCtx(
        mission_text="Analyse auth login redirect",
        relevant_files=(_rf(
            "src/only.ts",
            "import { signIn } from 'next-auth/react';\n"
            "export async function GET() { return NextResponse.redirect('/x'); }\n",
            "a9" + "0" * 62),),
    )
    r = build_analysis(ctx, FakeIntent(domaine="AUTH"))
    allowed = {"src/only.ts"}
    ok("AX9 tous les faits proviennent du seul fichier du contexte",
       all(f.fichier in allowed for f in r.faits_verifies),
       str(sorted({f.fichier for f in r.faits_verifies})))
    ok("AX9 elements_examines ⊆ contexte",
       set(r.elements_examines) <= allowed)

    # ============================================================
    # AX10 — CONTRADICTION : deux faits mènent à des conclusions opposées.
    # ============================================================
    print("\n[AX10] contradiction -> explicitée, jamais masquée")
    # Un fichier dit 'redirect vers /login si NON authentifié', un autre dit
    # 'redirect vers /login si authentifié' : signaux contradictoires.
    preview_x = (
        "export async function GET(req) {\n"
        "  if (!session) { return NextResponse.redirect('/login'); }\n"
        "}\n")
    preview_y = (
        "export async function GET(req) {\n"
        "  if (session) { return NextResponse.redirect('/login'); }\n"
        "}\n")
    ctx = FakeCtx(
        mission_text="Analyse la redirection de connexion login session",
        relevant_files=(
            _rf("src/app/api/x/route.ts", preview_x, "ax" + "0" * 62),
            _rf("src/app/api/y/route.ts", preview_y, "ay" + "0" * 62),
        ),
    )
    r = build_analysis(ctx, FakeIntent(domaine="AUTH"))
    # On n'exige pas une détection sémantique de contradiction, mais on
    # EXIGE que l'analyse ne tranche pas HIGH en masquant la divergence :
    # soit confiance < HIGH, soit la pluralité/divergence est signalée.
    signale = (r.confiance != "HIGH"
               or any(("plusieurs" in u.lower() or "diverg" in u.lower()
                       or "contradict" in u.lower() or "départager" in u.lower())
                      for u in r.incertitudes))
    ok("AX10 la divergence n'est pas masquée par une cause HIGH tranchée",
       signale, f"confiance={r.confiance} incert={r.incertitudes}")

    # ============================================================
    # Bilan
    # ============================================================
    print("\n" + "=" * 72)
    print(f"RÉSULTAT ADVERSARIAL : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
