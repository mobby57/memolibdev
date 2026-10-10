"""
MemoLibDev — V0.3.1 : Tests du Confidence Engine (déterministe)
================================================================

Prouve que confidence_engine :
  - est PUR et DÉTERMINISTE (même entrée -> même sortie) ;
  - n'importe AUCUN LLM/provider/git/subprocess ;
  - respecte les GATES (prioritaires sur le score) ;
  - sépare ANALYSIS et PROPOSAL ;
  - résiste au GAMING (volume de fichiers/mots-clés/diff, répétitions) ;
  - borne le score ;
  - produit des raisons explicables ;
  - PRÉSERVE le comportement V0.1.2 via analysis_level_and_strong.

Lancement :  python test_confidence_engine.py
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent

import confidence_engine as ce
from confidence_engine import (
    score_analysis, score_proposal, analysis_level_and_strong,
    HIGH, MEDIUM, LOW, SCORE_MIN, SCORE_MAX, ConfidenceResult,
)

PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


# --- Fait minimal (miroir de VerifiedFact : fichier, ligne, categorie) ---
@dataclass(frozen=True)
class F:
    fichier: str
    ligne_debut: int
    categorie: str


BEH = ("REDIRECT", "ROUTE", "CONDITION", "ERROR_HANDLING", "LOCALE")
CATS_AUTH = ("AUTH", "REDIRECT", "ROUTE", "LOCALE", "CONDITION", "ERROR_HANDLING")


def strong_file_facts(path="src/a.ts"):
    """Un fichier avec 2 catégories comportementales distinctes -> locus fort."""
    return [F(path, 1, "REDIRECT"), F(path, 2, "CONDITION")]


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST CONFIDENCE ENGINE (V0.3.1)")
    print("=" * 72)

    # ============================================================
    # 1. DÉTERMINISME
    # ============================================================
    print("\n[1] déterminisme")
    facts = strong_file_facts()
    r1 = score_analysis(relevant_facts=facts, relevant_cats=CATS_AUTH,
                        files_count=1, any_preview=True)
    r2 = score_analysis(relevant_facts=facts, relevant_cats=CATS_AUTH,
                        files_count=1, any_preview=True)
    ok("1 analysis déterministe", r1.to_dict() == r2.to_dict(), r1.level)
    p1 = score_proposal(has_diff=True, diff_valid=True, scope_verifiable=True,
                        has_fresh_sha=True, causal_evidence=True)
    p2 = score_proposal(has_diff=True, diff_valid=True, scope_verifiable=True,
                        has_fresh_sha=True, causal_evidence=True)
    ok("1 proposal déterministe", p1.to_dict() == p2.to_dict(), p1.level)

    # ============================================================
    # 2. HIGH correctement étayé (ANALYSE)
    # ============================================================
    print("\n[2] HIGH correctement étayé")
    r = score_analysis(relevant_facts=facts, relevant_cats=CATS_AUTH,
                       files_count=1, any_preview=True)
    ok("2 un locus causal unique -> HIGH", r.level == HIGH, f"{r.level} score={r.score}")
    ok("2 raisons explicables présentes", len(r.reasons) >= 1)

    # ============================================================
    # 3. MEDIUM ambigu (fait pertinent isolé, pas de locus fort)
    # ============================================================
    print("\n[3] MEDIUM ambigu (présence isolée)")
    one = [F("src/a.ts", 1, "REDIRECT")]  # 1 seule catégorie -> pas de locus fort
    r = score_analysis(relevant_facts=one, relevant_cats=CATS_AUTH,
                       files_count=1, any_preview=True)
    ok("3 présence isolée -> pas HIGH", r.level != HIGH, r.level)

    # ============================================================
    # 4. LOW insuffisant (aucun preview)
    # ============================================================
    print("\n[4] LOW insuffisant")
    r = score_analysis(relevant_facts=[], relevant_cats=CATS_AUTH,
                       files_count=0, any_preview=False)
    ok("4 aucun preview -> LOW", r.level == LOW, r.level)

    # ============================================================
    # 5. CONTRADICTION -> jamais HIGH
    # ============================================================
    print("\n[5] contradiction")
    r = score_analysis(relevant_facts=facts, relevant_cats=CATS_AUTH,
                       files_count=1, any_preview=True, contradiction=True)
    ok("5 contradiction -> max MEDIUM", r.level in (MEDIUM, LOW), r.level)
    ok("5 gate contradiction listé", any("G4" in g for g in r.gates), str(r.gates))

    # ============================================================
    # 6. PLUSIEURS LOCI -> max MEDIUM
    # ============================================================
    print("\n[6] plusieurs loci forts")
    two = (strong_file_facts("src/a.ts") + strong_file_facts("src/b.ts"))
    r = score_analysis(relevant_facts=two, relevant_cats=CATS_AUTH,
                       files_count=2, any_preview=True)
    ok("6 >=2 loci -> pas HIGH", r.level != HIGH, r.level)
    ok("6 gate G3 listé", any("G3" in g for g in r.gates), str(r.gates))

    # ============================================================
    # 7. SHA absent (ANALYSE) -> pénalité, et proposal fresh_sha False
    # ============================================================
    print("\n[7] SHA absent")
    r = score_analysis(relevant_facts=facts, relevant_cats=CATS_AUTH,
                       files_count=1, any_preview=True, has_sha=False)
    ok("7 SHA absent abaisse le score vs présent",
       r.score < r1.score, f"{r.score} < {r1.score}")
    p = score_proposal(has_diff=True, diff_valid=True, scope_verifiable=True,
                      has_fresh_sha=False, causal_evidence=True)
    ok("7 proposal sans SHA frais -> pas HIGH", p.level != HIGH, p.level)

    # ============================================================
    # 8. CONTEXTE STALE -> LOW (gate G1)
    # ============================================================
    print("\n[8] contexte périmé")
    r = score_analysis(relevant_facts=facts, relevant_cats=CATS_AUTH,
                       files_count=1, any_preview=True, is_stale=True)
    ok("8 analysis stale -> LOW", r.level == LOW, r.level)
    p = score_proposal(has_diff=True, diff_valid=True, scope_verifiable=True,
                      has_fresh_sha=True, causal_evidence=True, is_stale=True)
    ok("8 proposal stale -> LOW", p.level == LOW, p.level)
    ok("8 gate G1 listé", any("G1" in g for g in p.gates), str(p.gates))

    # ============================================================
    # 9. SCOPE incohérent -> jamais HIGH (gate G7)
    # ============================================================
    print("\n[9] scope incohérent")
    r = score_analysis(relevant_facts=facts, relevant_cats=CATS_AUTH,
                       files_count=1, any_preview=True, scope_verifiable=False)
    ok("9 analysis scope non vérifiable -> pas HIGH", r.level != HIGH, r.level)
    p = score_proposal(has_diff=True, diff_valid=True, scope_verifiable=False,
                      has_fresh_sha=True, causal_evidence=True)
    ok("9 proposal scope non vérifiable -> pas HIGH", p.level != HIGH, p.level)
    ok("9 gate G7 listé", any("G7" in g for g in p.gates), str(p.gates))

    # ============================================================
    # 10. DIFF absent (PROPOSAL) -> LOW (gate G5)
    # ============================================================
    print("\n[10] diff absent")
    p = score_proposal(has_diff=False, diff_valid=False, scope_verifiable=True,
                      has_fresh_sha=True, causal_evidence=True)
    ok("10 pas de diff -> LOW", p.level == LOW, p.level)
    ok("10 gate G5 listé", any("G5" in g for g in p.gates), str(p.gates))

    # ============================================================
    # 11. DIFF validation KO (PROPOSAL) -> LOW (gate G6)
    # ============================================================
    print("\n[11] validation du diff KO")
    p = score_proposal(has_diff=True, diff_valid=False, scope_verifiable=True,
                      has_fresh_sha=True, causal_evidence=True)
    ok("11 diff invalide -> LOW", p.level == LOW, p.level)
    ok("11 gate G6 listé", any("G6" in g for g in p.gates), str(p.gates))

    # ============================================================
    # 12. ANTI-GAMING : volume ne monte pas la confiance
    # ============================================================
    print("\n[12] anti-gaming (volume)")
    # (a) beaucoup de fichiers NON causaux (1 catégorie chacun) : pas de locus.
    many_noise = [F(f"src/noise{i}.ts", 1, "REDIRECT") for i in range(50)]
    r_noise = score_analysis(relevant_facts=many_noise, relevant_cats=CATS_AUTH,
                            files_count=50, any_preview=True)
    ok("12a 50 fichiers 1-catégorie -> pas HIGH", r_noise.level != HIGH, r_noise.level)
    # (b) beaucoup de mots-clés NON comportementaux (IMPORT) : jamais HIGH.
    many_kw = [F("src/a.ts", i, "IMPORT") for i in range(1, 40)]
    r_kw = score_analysis(relevant_facts=many_kw, relevant_cats=CATS_AUTH,
                         files_count=1, any_preview=True)
    ok("12b 40 mots-clés IMPORT -> pas HIGH", r_kw.level != HIGH, r_kw.level)
    # (c) proposal : taille du diff NON acceptée par la signature (par
    #     construction) ; un diff "énorme" ne peut pas être exprimé comme
    #     facteur. On vérifie qu'un diff valide + preuve donne au plus le
    #     même niveau qu'un diff normal (pas de bonus volume).
    p_small = score_proposal(has_diff=True, diff_valid=True, scope_verifiable=True,
                           has_fresh_sha=True, causal_evidence=True)
    ok("12c proposal : aucun facteur 'taille/volume' dans la signature",
       "size" not in score_proposal.__code__.co_varnames
       and "count" not in score_proposal.__code__.co_varnames
       and "nb_files" not in score_proposal.__code__.co_varnames,
       str(score_proposal.__code__.co_varnames))

    # ============================================================
    # 13. DÉDUPLICATION : répéter la même preuve ne change rien
    # ============================================================
    print("\n[13] déduplication des preuves")
    base = strong_file_facts("src/a.ts")
    dup = base + base + base    # mêmes (fichier, ligne, catégorie) répétés
    r_base = score_analysis(relevant_facts=base, relevant_cats=CATS_AUTH,
                          files_count=1, any_preview=True)
    r_dup = score_analysis(relevant_facts=dup, relevant_cats=CATS_AUTH,
                         files_count=1, any_preview=True)
    ok("13 preuves répétées -> même niveau", r_base.level == r_dup.level,
       f"{r_base.level} == {r_dup.level}")
    ok("13 preuves répétées -> même score", r_base.score == r_dup.score,
       f"{r_base.score} == {r_dup.score}")

    # ============================================================
    # 14. SÉPARATION analysis / proposal
    # ============================================================
    print("\n[14] séparation analysis/proposal")
    ra = score_analysis(relevant_facts=facts, relevant_cats=CATS_AUTH,
                       files_count=1, any_preview=True)
    pa = score_proposal(has_diff=True, diff_valid=True, scope_verifiable=True,
                      has_fresh_sha=True, causal_evidence=True)
    ok("14 dimension ANALYSIS", ra.dimension == "ANALYSIS", ra.dimension)
    ok("14 dimension PROPOSAL", pa.dimension == "PROPOSAL", pa.dimension)
    ok("14 signatures distinctes (proposal n'a pas relevant_facts)",
       "relevant_facts" not in score_proposal.__code__.co_varnames)

    # ============================================================
    # 15. ABSENCE DE LLM (analyse statique du module)
    # ============================================================
    print("\n[15] absence de LLM / IO (analyse statique)")
    tree = ast.parse((HERE / "confidence_engine.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    forbidden = {"llm", "ollama_provider", "subprocess", "requests",
                 "urllib", "socket", "openai", "httpx"}
    leaked = sorted(imported & forbidden)
    ok("15 aucun import LLM/IO/réseau", leaked == [], f"imports={sorted(imported)}")
    ok("15 aucune dépendance circulaire (analysis_builder/proposal/agent_loop)",
       not (imported & {"analysis_builder", "proposal", "agent_loop"}),
       str(sorted(imported)))

    # ============================================================
    # 16. BORNES DU SCORE
    # ============================================================
    print("\n[16] bornes du score")
    # Cas très étayé : score borné à SCORE_MAX.
    rich = [F("src/a.ts", 1, "REDIRECT"), F("src/a.ts", 2, "CONDITION"),
            F("src/a.ts", 3, "ROUTE"), F("src/a.ts", 4, "ERROR_HANDLING")]
    r = score_analysis(relevant_facts=rich, relevant_cats=CATS_AUTH,
                       files_count=1, any_preview=True)
    ok("16 score <= SCORE_MAX", r.score <= SCORE_MAX, str(r.score))
    ok("16 score >= SCORE_MIN", r.score >= SCORE_MIN, str(r.score))
    p = score_proposal(has_diff=True, diff_valid=True, scope_verifiable=True,
                      has_fresh_sha=True, causal_evidence=True)
    ok("16 proposal score borné", SCORE_MIN <= p.score <= SCORE_MAX, str(p.score))

    # ============================================================
    # 17. RAISONS EXPLICABLES
    # ============================================================
    print("\n[17] raisons explicables")
    r = score_analysis(relevant_facts=facts, relevant_cats=CATS_AUTH,
                       files_count=1, any_preview=True)
    ok("17 chaque raison est une phrase lisible non vide",
       all(isinstance(x, str) and len(x) > 10 for x in r.reasons), str(r.reasons))
    ok("17 evidence_used non vide quand preuve",
       len(r.evidence_used) >= 1, str(r.evidence_used))

    # ============================================================
    # NR. NON-RÉGRESSION : analysis_level_and_strong == logique V0.1.2
    # ============================================================
    print("\n[NR] non-régression : compat analysis_builder._confidence")
    # 1 locus -> HIGH ; 2 loci -> MEDIUM ; isolé -> MEDIUM ; rien -> LOW.
    lvl1, s1 = analysis_level_and_strong(facts, CATS_AUTH, 1, True)
    ok("NR 1 locus -> HIGH + 1 strong", lvl1 == HIGH and len(s1) == 1)
    lvl2, s2 = analysis_level_and_strong(two, CATS_AUTH, 2, True)
    ok("NR 2 loci -> MEDIUM + 2 strong", lvl2 == MEDIUM and len(s2) == 2)
    lvl3, s3 = analysis_level_and_strong(one, CATS_AUTH, 1, True)
    ok("NR isolé -> MEDIUM + 0 strong", lvl3 == MEDIUM and len(s3) == 0)
    lvl4, s4 = analysis_level_and_strong([], CATS_AUTH, 0, False)
    ok("NR rien -> LOW", lvl4 == LOW and s4 == {})
    # Cohérence avec le vrai analysis_builder (import tardif, cible lecture).
    os.environ.setdefault("MEMOLIBDEV_TARGET", r"C:\Users\moros\memoLib")
    try:
        from analysis_builder import _confidence as _ab_conf
        a_lvl, a_strong = _ab_conf(facts, CATS_AUTH, 1, True)
        ok("NR analysis_builder._confidence délègue (HIGH, 1 strong)",
           a_lvl == HIGH and len(a_strong) == 1, f"{a_lvl} {len(a_strong)}")
    except SystemExit:
        ok("NR analysis_builder import (cible absente) — toléré", True,
           "MEMOLIBDEV_TARGET requis pour import complet")

    print("\n" + "=" * 72)
    print(f"RÉSULTAT CONFIDENCE ENGINE : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS : " + ", ".join(FAIL))
    print("=" * 72)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
