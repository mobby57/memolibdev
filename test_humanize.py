"""
MemoLibDev — Test de la brique B : humanize (déterministe, pur, fidèle)
======================================================================

Vérifie :
  H1  chaque état -> message déterministe attendu
  H2  mapping modes -> Observer/Préparer/Tester/Modifier
  H3  action_requise : QUESTION -> préciser ; AWAIT_HUMAN -> autoriser/refuser ;
      autres états -> aucune action d'autorisation
  H4  report=None géré (technique=None, pas de crash)
  H5  ERROR géré
  H6  technique = report.to_dict() conservé INTÉGRALEMENT
  H7  déterminisme (deux appels identiques)
  H8  PURETÉ : humanize n'importe NI git NI apply NI authorize (analyse du
      module), ne lit/écrit aucun fichier, ne fabrique pas d'approbation
  H9  FIDÉLITÉ (anti-invention) : un état AWAIT_HUMAN ne doit JAMAIS
      produire un message affirmant qu'une modification a été faite ;
      un état sans apply ne doit jamais contenir "effectuée"/"corrigé".

Aucun moteur gelé touché. Aucun apply/commit/push.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import ast

from humanize import humanize, HumanView, _MODE_TO_CONTROL


PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


# --- doublures minimales (on ne dépend pas du moteur pour tester humanize) ---

@dataclass
class FakeStep:
    step: str
    loop_state: str
    detail: str = ""


@dataclass
class FakeReport:
    final_state: str = "AWAIT_HUMAN"
    reason: str = "raison technique du moteur"
    steps: tuple = ()
    committed: bool = False
    pushed: bool = False

    def to_dict(self) -> dict:
        return {
            "final_state": self.final_state,
            "reason": self.reason,
            "committed": self.committed,
            "pushed": self.pushed,
            "steps": [{"step": s.step, "state": s.loop_state, "detail": s.detail}
                      for s in self.steps],
        }


@dataclass
class FakeResult:
    status: str
    message: str = ""
    report: Optional[object] = None
    question: Optional[str] = None


MISSION = "analyser la page de connexion"


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST humanize (brique B)")
    print("=" * 72)

    # ========================================================
    # H1 — chaque état -> message attendu
    # ========================================================
    print("\n[H1] États -> messages déterministes")
    cases = {
        "QUESTION": "besoin d'une précision",
        "AWAIT_HUMAN": "préparé une proposition",
        "BLOCKED": "ne peux pas continuer",
        "APPLIED": "effectuée puis vérifiée",
        "ROLLED_BACK": "restauré",
        "NO_PATCH_POSSIBLE": "pas trouvé de modification",
        "ERROR": "erreur est survenue",
    }
    for state, needle in cases.items():
        hv = humanize(FakeResult(status=state), mode="READ_ONLY", mission=MISSION)
        ok(f"H1_{state}", needle in hv.resultat, hv.resultat[:50])

    # ========================================================
    # H2 — mapping modes -> niveaux de contrôle
    # ========================================================
    print("\n[H2] Mapping modes -> contrôle")
    for mode, control in _MODE_TO_CONTROL.items():
        hv = humanize(FakeResult(status="OK"), mode=mode, mission=MISSION)
        ok(f"H2_{mode}", hv.niveau_de_controle == control,
           f"{mode} -> {hv.niveau_de_controle}")
    # mode inconnu -> Observer (fail-safe)
    hv = humanize(FakeResult(status="OK"), mode="???", mission=MISSION)
    ok("H2_inconnu_observer", hv.niveau_de_controle == "Observer", "")

    # ========================================================
    # H3 — action_requise selon état
    # ========================================================
    print("\n[H3] action_requise")
    hv_q = humanize(FakeResult(status="QUESTION",
                               question="Préciser : navigation ou affichage ?"),
                    mode="READ_ONLY", mission=MISSION)
    ok("H3_question_precise", hv_q.action_requise == "Préciser : navigation ou affichage ?",
       str(hv_q.action_requise))
    hv_q2 = humanize(FakeResult(status="QUESTION"), mode="READ_ONLY", mission=MISSION)
    ok("H3_question_defaut", "préciser" in (hv_q2.action_requise or "").lower(), "")

    hv_aw = humanize(FakeResult(status="AWAIT_HUMAN"), mode="SUPERVISED_APPLY",
                     mission=MISSION)
    ok("H3_await_autoriser",
       "autoriser" in (hv_aw.action_requise or "").lower()
       and "refuser" in (hv_aw.action_requise or "").lower(),
       str(hv_aw.action_requise))

    for state in ("APPLIED", "ROLLED_BACK", "BLOCKED", "NO_PATCH_POSSIBLE", "ERROR", "OK"):
        hv = humanize(FakeResult(status=state), mode="READ_ONLY", mission=MISSION)
        ok(f"H3_{state}_aucune_action", hv.action_requise is None,
           f"action={hv.action_requise}")

    # ========================================================
    # H4 — report=None
    # ========================================================
    print("\n[H4] report=None")
    hv = humanize(FakeResult(status="BLOCKED", report=None), mode="READ_ONLY",
                  mission=MISSION)
    ok("H4_technique_none", hv.technique is None, "")
    ok("H4_verifie_vide", hv.ce_qui_a_ete_verifie == (), "")

    # ========================================================
    # H5 — ERROR
    # ========================================================
    print("\n[H5] ERROR")
    hv = humanize(FakeResult(status="ERROR", message="boom"), mode="READ_ONLY",
                  mission=MISSION)
    ok("H5_error_resultat", "erreur" in hv.resultat.lower(), hv.resultat)
    ok("H5_error_pourquoi_fallback", hv.pourquoi == "boom",
       "reason absent -> message en fallback")

    # ========================================================
    # H6 — technique = report.to_dict() conservé intégralement
    # ========================================================
    print("\n[H6] technique conservé")
    rep = FakeReport(final_state="APPLIED", reason="appliqué et vérifié",
                     steps=(FakeStep("D5.9_APPLY", "CONTINUE"),
                            FakeStep("VERIFY", "CONTINUE")),
                     committed=False, pushed=False)
    hv = humanize(FakeResult(status="APPLIED", report=rep),
                  mode="SUPERVISED_APPLY", mission=MISSION)
    ok("H6_technique_present", hv.technique == rep.to_dict(), "")
    ok("H6_technique_committed", hv.technique["committed"] is False, "")
    ok("H6_verifie_depuis_steps",
       "application contrôlée effectuée" in hv.ce_qui_a_ete_verifie
       and "résultat vérifié" in hv.ce_qui_a_ete_verifie,
       str(hv.ce_qui_a_ete_verifie))

    # ========================================================
    # H7 — déterminisme
    # ========================================================
    print("\n[H7] Déterminisme")
    a = humanize(FakeResult(status="AWAIT_HUMAN", report=FakeReport()),
                 mode="PROPOSE", mission=MISSION)
    b = humanize(FakeResult(status="AWAIT_HUMAN", report=FakeReport()),
                 mode="PROPOSE", mission=MISSION)
    ok("H7_deterministe", a.to_dict() == b.to_dict(), "deux appels identiques")

    # ========================================================
    # H8 — PURETÉ (analyse statique du module humanize)
    # ========================================================
    print("\n[H8] Pureté / imports interdits")
    with open("humanize.py", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imported.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    forbidden = {"subprocess", "os", "git", "d59_controlled_apply",
                 "coder_authorization", "controlled_coder", "agent_loop",
                 "urllib", "socket", "shutil", "pathlib"}
    intrus = imported & forbidden
    ok("H8_aucun_import_dangereux", not intrus, f"imports={sorted(imported)}")
    # Aucune ÉCRITURE/exécution : on inspecte les APPELS réels via l'AST
    # (et non des sous-chaînes, qui matcheraient à tort la docstring).
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                called.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                called.add(fn.attr)
    forbidden_calls = {"open", "run_controlled_apply", "authorize", "system",
                       "run", "Popen", "write", "write_text", "write_bytes",
                       "unlink", "remove", "rmtree", "mkdir"}
    intrus_calls = called & forbidden_calls
    ok("H8_pas_appel_dangereux", not intrus_calls,
       f"appels interdits={sorted(intrus_calls)}")
    # Les mentions en docstring (run_controlled_apply/authorize) sont de la
    # documentation, pas des appels : l'AST ne les compte pas.
    ok("H8_docstring_documente_invariant",
       "run_controlled_apply" in (ast.get_docstring(tree) or ""),
       "la règle d'architecture est documentée")

    # ========================================================
    # H9 — FIDÉLITÉ : anti-invention de faits
    # ========================================================
    print("\n[H9] Fidélité (anti-invention)")
    # AWAIT_HUMAN ne doit jamais prétendre qu'une modif a été faite.
    hv_aw = humanize(FakeResult(status="AWAIT_HUMAN"), mode="SUPERVISED_APPLY",
                     mission=MISSION)
    blob_aw = (hv_aw.resultat + " " + (hv_aw.action_requise or "")).lower()
    ok("H9_await_pas_de_fait_corrige",
       "corrigé" not in blob_aw and "effectuée" not in blob_aw
       and "modification a été" not in blob_aw,
       "AWAIT_HUMAN ne prétend aucune modification")
    ok("H9_await_dit_rien_modifie", "rien n'a été modifié" in hv_aw.resultat.lower(), "")

    # QUESTION ne doit pas affirmer un diagnostic.
    hv_q = humanize(FakeResult(status="QUESTION"), mode="READ_ONLY", mission=MISSION)
    ok("H9_question_pas_diagnostic",
       "corrigé" not in hv_q.resultat.lower()
       and "le problème est" not in hv_q.resultat.lower(), "")

    # BLOCKED ne doit pas dire que c'est réussi.
    hv_b = humanize(FakeResult(status="BLOCKED"), mode="READ_ONLY", mission=MISSION)
    ok("H9_blocked_pas_succes",
       "vérifiée" not in hv_b.resultat.lower()
       and "effectuée" not in hv_b.resultat.lower(), "")

    # APPLIED (seul état qui peut dire "effectuée") le dit, et seulement lui.
    hv_ap = humanize(FakeResult(status="APPLIED"), mode="SUPERVISED_APPLY",
                     mission=MISSION)
    ok("H9_applied_peut_dire_effectuee", "effectuée" in hv_ap.resultat.lower(), "")

    # pourquoi = reason du moteur, jamais inventé.
    rep = FakeReport(reason="raison exacte du moteur XYZ")
    hv = humanize(FakeResult(status="AWAIT_HUMAN", report=rep),
                  mode="PROPOSE", mission=MISSION)
    ok("H9_pourquoi_fidele", hv.pourquoi == "raison exacte du moteur XYZ",
       "pourquoi reprend reason sans invention")

    print("\n" + "=" * 72)
    print(f"RÉSULTAT humanize : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    print("humanize : pur, déterministe, fidèle (n'invente aucun fait).")
    print("Aucun LLM. Aucun git/apply/authorize. technique conservé.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
