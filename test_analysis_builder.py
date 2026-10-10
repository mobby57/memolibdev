"""
MemoLibDev — V0.1.1 : Test de l'Analysis Builder (analyse explicative)
======================================================================

Prouve que `analysis_builder.build_analysis(...)` produit une analyse
EXPLICATIVE déterministe, SOURCÉE et HONNÊTE, sans jamais inventer de
fait, sans LLM et sans écriture.

Doublures locales (pas de moteur, pas de git, pas d'Ollama, pas de disque) :
on imite MissionContext/RelevantFile/FileVersion/StructuredIntent avec le
STRICT nécessaire consommé par le builder (attributs lus uniquement).

Exigences couvertes (12) :
  T1  Même contexte -> résultat déterministe (sérialisation identique).
  T2  Chaque fait possède une source EXISTANTE (fichier ∈ contexte).
  T3  Impossible de créer un fait provenant d'un fichier absent du contexte.
  T4  Preview insuffisant -> confiance LOW + incertitude explicite.
  T5  ANALYSER reste ANALYZED (via agent_loop._build_analysis -> texte).
  T6  ANALYSER ne produit AUCUN diff (ni dans AnalysisResult ni dans le texte).
  T7  ANALYSER ne passe jamais par CORRIGER (pas de REPLACE/apply/D5.x).
  T8  Pas d'écriture : build_analysis est pur (aucun I/O, aucun git).
  T9  Cause non étayée -> cause_probable=None + incertitude dédiée.
  T10 Confiance HIGH exige des faits pertinents observables (>=2).
  T11 Chaque fait porte (fichier, lignes, extrait réel, sha) ; extrait ⊂ preview.
  T12 aucune_modification == True (invariant) ; sérialisation complète du contrat.

Aucun moteur gelé touché. Aucun apply/commit/push.
"""

from __future__ import annotations

from dataclasses import dataclass
import ast
import inspect
import os

from analysis_builder import (
    build_analysis, render_analysis_text, AnalysisResult, VerifiedFact,
)


PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


# ------------------------------------------------------------------
# Doublures minimales (uniquement les attributs lus par le builder)
# ------------------------------------------------------------------

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


# Preview réaliste contenant des éléments AUTH/REDIRECT/LOCALE/ROUTE.
_LOGIN_PREVIEW = (
    "import { NextResponse } from 'next/server';\n"
    "import { getLocale } from '@/i18n';\n"
    "export async function GET(req) {\n"
    "  const session = await getAuth(req);\n"
    "  if (!session) {\n"
    "    return NextResponse.redirect('/login');\n"
    "  }\n"
    "  return NextResponse.next();\n"
    "}\n"
)

_SHA_LOGIN = "36a7dd5c3afa" + "0" * 52  # 64 hex déterministe


def _ctx_auth() -> FakeCtx:
    return FakeCtx(
        mission_text="Analyse le problème de navigation vers /fr/auth/login.",
        relevant_files=(
            FakeRelevantFile(
                path="src/app/[locale]/auth/login/page.tsx",
                preview=_LOGIN_PREVIEW,
                version=FakeVersion(text_sha256=_SHA_LOGIN)),
        ),
    )


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST analysis_builder (analyse explicative)")
    print("=" * 72)

    # ---------------- T1 — déterminisme ----------------
    print("\n[T1] même contexte -> résultat déterministe")
    r1 = build_analysis(_ctx_auth(), FakeIntent())
    r2 = build_analysis(_ctx_auth(), FakeIntent())
    ok("T1 sérialisation identique", r1.to_dict() == r2.to_dict())
    ok("T1 rendu texte identique",
       render_analysis_text(r1, FakeIntent()) == render_analysis_text(r2, FakeIntent()))

    # ---------------- T2 — chaque fait a une source existante ----------------
    print("\n[T2] chaque fait provient d'un fichier du contexte")
    ctx = _ctx_auth()
    res = build_analysis(ctx, FakeIntent())
    sources = {rf.path for rf in ctx.relevant_files}
    ok("T2 au moins un fait extrait", len(res.faits_verifies) > 0,
       str(len(res.faits_verifies)))
    ok("T2 tous les faits ont une source du contexte",
       all(f.fichier in sources for f in res.faits_verifies),
       str([f.fichier for f in res.faits_verifies]))
    ok("T2 elements_examines == fichiers du contexte",
       set(res.elements_examines) == sources)

    # ---------------- T3 — impossible : fait hors contexte ----------------
    print("\n[T3] aucun fait ne peut provenir d'un fichier absent du contexte")
    # On fabrique un contexte à UN fichier ; aucun fait ne doit porter un
    # autre chemin que celui-là (le builder ne lit QUE relevant_files).
    only = "src/app/[locale]/auth/login/page.tsx"
    ok("T3 aucun chemin étranger dans les faits",
       all(f.fichier == only for f in res.faits_verifies),
       str([f.fichier for f in res.faits_verifies]))
    # Preuve structurelle : build_analysis n'itère que sur ctx.relevant_files.
    src = inspect.getsource(build_analysis)
    ok("T3 build_analysis n'itère que sur relevant_files",
       "for rf in relevant_files" in src and "relevant_files = tuple(getattr(ctx"
       in src)

    # ---------------- T4 — preview insuffisant -> LOW + incertitude ----------------
    print("\n[T4] preview insuffisant -> LOW + incertitude")
    ctx_empty = FakeCtx(
        mission_text="Analyse la connexion",
        relevant_files=(
            FakeRelevantFile(path="src/auth/x.ts", preview="   \n  ",
                             version=FakeVersion(text_sha256="a" * 64)),
        ),
    )
    r_empty = build_analysis(ctx_empty, FakeIntent())
    ok("T4 confiance LOW", r_empty.confiance == "LOW", r_empty.confiance)
    ok("T4 aucune cause", r_empty.cause_probable is None)
    ok("T4 incertitude présente", len(r_empty.incertitudes) > 0)
    ok("T4 incertitude mentionne contenu indisponible/insuffisant",
       any(("contenu" in u.lower() or "disponible" in u.lower()
            or "insuffisant" in u.lower() or "permet pas" in u.lower())
           for u in r_empty.incertitudes),
       str(r_empty.incertitudes))

    # Aucun fichier pertinent du tout -> LOW + incertitude d'analyse impossible.
    ctx_none = FakeCtx(mission_text="Analyse X", relevant_files=())
    r_none = build_analysis(ctx_none, FakeIntent())
    ok("T4b aucun fichier -> LOW", r_none.confiance == "LOW")
    ok("T4b aucun fichier -> incertitude",
       any("aucun fichier" in u.lower() for u in r_none.incertitudes),
       str(r_none.incertitudes))
    ok("T4b aucun fichier -> aucun fait", len(r_none.faits_verifies) == 0)

    # ---------------- T5 — ANALYSER reste ANALYZED ----------------
    print("\n[T5] agent_loop._build_analysis -> texte (branche ANALYZED)")
    # NB : importer agent_loop déclenche la résolution de cible au niveau
    # module de certains composants (controlled_coder/decision_agent) — un
    # comportement EXISTANT et HORS PÉRIMÈTRE de cette étape (bug --project
    # à ne pas corriger ici). On fournit donc MEMOLIBDEV_TARGET en lecture
    # seule, pointé sur le dépôt MemoLibDev lui-même, uniquement pour
    # permettre l'import. Aucune écriture, aucune analyse réelle de cible.
    os.environ.setdefault("MEMOLIBDEV_TARGET", os.path.dirname(__file__))
    import agent_loop
    txt = agent_loop._build_analysis(_ctx_auth(), FakeIntent())
    ok("T5 texte non vide", isinstance(txt, str) and len(txt) > 0)
    ok("T5 en-tête lecture seule",
       "ANALYSE (lecture seule" in txt and "Aucune modification effectuée" in txt)
    # La branche ANALYSE pose final_state=ANALYZED dans agent_loop (preuve
    # statique : la chaîne 'ANALYZED' est bien reliée à _build_analysis).
    loop_src = inspect.getsource(agent_loop)
    ok("T5 _build_analysis alimente final_state=ANALYZED",
       'final_state="ANALYZED"' in loop_src and "_build_analysis(ctx" in loop_src)

    # ---------------- T6 — aucun diff ----------------
    print("\n[T6] aucun diff produit")
    blob = (render_analysis_text(res, FakeIntent()) + " "
            + str(res.to_dict())).lower()
    for marker in ("--- a/", "+++ b/", "@@ ", "diff --git", "<<<<<<<", ">>>>>>>"):
        ok(f"T6 pas de marqueur diff {marker!r}", marker not in blob)

    # ---------------- T7 — jamais CORRIGER / REPLACE / D5.x ----------------
    print("\n[T7] jamais CORRIGER/REPLACE/apply/D5.x")
    # (a) sortie : la correction est DESCRIPTIVE, jamais un REPLACE exécutable.
    corr = (res.correction_minimale or "")
    ok("T7 pas de REPLACE: dans la correction", "REPLACE:" not in corr)
    # (b) structurel : le module n'importe NI apply NI D5.8/D5.9 NI subprocess.
    with open(os.path.join(os.path.dirname(__file__), "analysis_builder.py"),
              "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    for forbidden in ("subprocess", "d59_controlled_apply", "coder_authorization",
                      "controlled_coder", "decision_agent", "os", "git",
                      "urllib", "socket"):
        ok(f"T7 pas d'import {forbidden}", forbidden not in imported,
           str(sorted(imported)))

    # ---------------- T8 — pureté (aucune écriture) ----------------
    print("\n[T8] pureté : aucune écriture / aucun open en écriture")
    ab_src = inspect.getsource(__import__("analysis_builder"))
    ok("T8 pas d'open(", "open(" not in ab_src)
    ok("T8 pas de .write(", ".write(" not in ab_src)
    ok("T8 pas de Path(", "Path(" not in ab_src)

    # ---------------- T9 — cause non étayée -> None + incertitude ----------------
    print("\n[T9] cause non étayée -> None + incertitude dédiée")
    # Domaine UNKNOWN : les faits ne sont pas rattachés au domaine -> pas HIGH.
    r_unknown = build_analysis(_ctx_auth(),
                               FakeIntent(domaine="UNKNOWN", confiance="LOW"))
    ok("T9 cause=None quand domaine inconnu", r_unknown.cause_probable is None)
    ok("T9 incertitude 'ne permet pas de confirmer la cause'",
       any("confirmer la cause" in u.lower() for u in r_unknown.incertitudes),
       str(r_unknown.incertitudes))

    # ---------------- T10 — HIGH exige >=2 faits pertinents ----------------
    print("\n[T10] confiance HIGH exige des faits pertinents observables")
    r_high = build_analysis(_ctx_auth(), FakeIntent(domaine="AUTH"))
    # Le preview AUTH contient AUTH + REDIRECT + ROUTE + LOCALE (>=2 pertinents).
    ok("T10 HIGH atteint sur preview riche + domaine AUTH",
       r_high.confiance == "HIGH", r_high.confiance)
    ok("T10 cause probable fournie en HIGH", r_high.cause_probable is not None)
    ok("T10 correction descriptive fournie en HIGH",
       r_high.correction_minimale is not None)

    # Un seul fait pertinent -> MEDIUM, pas HIGH, pas de cause affirmée.
    ctx_one = FakeCtx(
        mission_text="Analyse la configuration",
        relevant_files=(
            FakeRelevantFile(
                path="next.config.js",
                preview="const x = 1;\nmodule.exports = { key: 'value' };\n",
                version=FakeVersion(text_sha256="c" * 64)),
        ),
    )
    r_one = build_analysis(ctx_one, FakeIntent(domaine="CONFIG", risque="LOW"))
    ok("T10 MEDIUM ou LOW si <2 faits pertinents",
       r_one.confiance in ("MEDIUM", "LOW"), r_one.confiance)
    ok("T10 pas de cause si pas HIGH",
       (r_one.cause_probable is None) == (r_one.confiance != "HIGH"))

    # ---------------- T11 — chaque fait sourcé + extrait ⊂ preview ----------------
    print("\n[T11] chaque fait : fichier+lignes+extrait réel+sha ; extrait ⊂ preview")
    ctx = _ctx_auth()
    res = build_analysis(ctx, FakeIntent())
    preview_by_path = {rf.path: rf.preview for rf in ctx.relevant_files}
    sha_by_path = {rf.path: rf.version.text_sha256 for rf in ctx.relevant_files}
    all_ok_fields = True
    all_ok_excerpt = True
    all_ok_sha = True
    for f in res.faits_verifies:
        if not (isinstance(f, VerifiedFact) and f.fichier and f.ligne_debut >= 1
                and f.ligne_fin >= f.ligne_debut and f.extrait and f.sha):
            all_ok_fields = False
        # L'extrait doit être une sous-chaîne réelle du preview (modulo clip/strip).
        core = f.extrait.replace(" …", "").strip()
        if core and core not in preview_by_path.get(f.fichier, ""):
            all_ok_excerpt = False
        if f.sha != sha_by_path.get(f.fichier):
            all_ok_sha = False
    ok("T11 champs complets (fichier/lignes/extrait/sha)", all_ok_fields)
    ok("T11 extrait réellement présent dans le preview", all_ok_excerpt)
    ok("T11 sha du fait == sha de la source", all_ok_sha)
    # La ligne annoncée correspond vraiment au contenu annoncé.
    line_match = True
    for f in res.faits_verifies:
        lines = preview_by_path.get(f.fichier, "").splitlines()
        if not (1 <= f.ligne_debut <= len(lines)):
            line_match = False
            break
        core = f.extrait.replace(" …", "").strip()
        if core and core not in lines[f.ligne_debut - 1]:
            line_match = False
            break
    ok("T11 n° de ligne cohérent avec l'extrait", line_match)

    # ---------------- T12 — invariant + contrat complet ----------------
    print("\n[T12] invariant aucune_modification + contrat sérialisable complet")
    d = res.to_dict()
    for key in ("demande_comprise", "faits_verifies", "elements_examines",
                "analyse", "cause_probable", "correction_minimale",
                "confiance", "incertitudes", "aucune_modification"):
        ok(f"T12 clé contrat '{key}' présente", key in d)
    ok("T12 aucune_modification == True", d["aucune_modification"] is True)
    ok("T12 confiance ∈ {HIGH,MEDIUM,LOW}", d["confiance"] in ("HIGH", "MEDIUM", "LOW"))
    ok("T12 faits sérialisés en dicts sourcés",
       all(set(("fichier", "lignes", "extrait", "sha", "categorie")) <= set(x)
           for x in d["faits_verifies"]))

    print("\n" + "=" * 72)
    print(f"RÉSULTAT analysis_builder : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
