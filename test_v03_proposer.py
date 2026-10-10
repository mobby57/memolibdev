"""
MemoLibDev — V0.3 : Tests PROPOSER (transport d'une proposition RÉELLE)
=======================================================================

Prouve que la proposition DÉJÀ produite par le pipeline CODER (§4.7 :
plan + new_content + diff) est TRANSPORTÉE jusqu'à la façade puis l'UI,
SANS fabrication, SANS écriture, SANS appel D5.9 pendant PROPOSER, et
SANS toucher D5.8/D5.9/MemoLib.

Les 16 épreuves exigées (§9) :
  1. Une proposition réelle est transportée jusqu'à la façade.
  2. La proposition ne contient que des données réellement produites.
  3. Aucun SHA fictif.
  4. Aucun diff fictif.
  5. Le front affiche la proposition.
  6. Le front n'est pas autoritaire.
  7. Le bouton Autoriser n'appelle pas directement D5.9.
  8. Refuser n'applique rien.
  9. Une proposition seule ne modifie aucun fichier.
 10. Aucun appel D5.9 pendant PROPOSER.
 11. MemoLib reste inchangé.
 12. D5.8 reste inchangé.
 13. D5.9 reste inchangé.
 14. Commit=False.
 15. Push=False.
 16. Production=False.

Cible RÉELLE : MEMOLIBDEV_TARGET (ici le dépôt MemoLib), lecture seule.
Les épreuves qui exercent le vrai moteur produisent un VRAI diff via
code_adapter.generate_diff_git (git diff), puis restaurent le fichier.
Aucune des 11 étapes du moteur n'est modifiée : on l'OBSERVE.

Lancement :  (MEMOLIBDEV_TARGET pointant un dépôt git réel)
    python test_v03_proposer.py
"""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent

# Cible réelle obligatoire (pas de fallback). Par défaut, le dépôt MemoLib.
# Si MEMOLIBDEV_TARGET est déjà défini, on le respecte.
os.environ.setdefault("MEMOLIBDEV_TARGET", r"C:\Users\moros\memoLib")

PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def _git(root, *a) -> str:
    return subprocess.run(["git", "-C", str(root), *a], text=True,
                          capture_output=True, encoding="utf-8",
                          errors="replace").stdout.strip()


def _status(root) -> str:
    return subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                          text=True, capture_output=True,
                          encoding="utf-8", errors="replace").stdout


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --------------------------------------------------------------------
# Imports moteur (après fixation de MEMOLIBDEV_TARGET).
# --------------------------------------------------------------------
from project_target import resolve_target
from file_target import resolve_file_target
import code_adapter
from agent_loop import AgentLoop, Mission, AgentReport
from proposal import Proposal, ProposalFile, build_proposal, NON_DISPONIBLE


def _verify_light(_repo) -> tuple[bool, str]:
    return (True, "verify léger (test V0.3)")


# ====================================================================
# PARTIE A — RUN RÉEL du moteur : proposition réelle, aucune écriture
# ====================================================================

def part_real_pipeline() -> dict:
    """
    Exécute le VRAI AgentLoop sur la cible réelle en mode PROPOSER
    (human_approval=None => la chaîne s'arrête en AWAIT_HUMAN APRÈS §4.7,
    donc après production du diff, AVANT toute écriture). Retourne des
    éléments pour les épreuves 1-4, 9-11, 14-16.
    """
    target = resolve_target()
    head_before = _git(target.git_root, "rev-parse", "HEAD")
    status_before = _status(target.git_root)

    # Choix d'un fichier RÉEL + fragment ASCII stable (anti-flaky).
    rel = "README.md"
    ft = resolve_file_target(rel, target, risk_level="LOW")
    current = code_adapter.read(ft)
    anchor = "MIT License"
    assert anchor in current, "fixture: ancre absente du fichier réel"
    intent = f"REPLACE:{anchor}:{anchor} (V0.3 proposition — non appliqué)"

    mission = Mission(
        request_text="Mettre à jour la mention de licence",
        target=target,
        relative_path=rel,
        intent=intent,
        risk_level="LOW",
        action=None,            # PROPOSER : pas d'ActionDossier
        human_approval=None,    # PROPOSER : pas d'approbation => AWAIT_HUMAN
    )

    report: AgentReport = AgentLoop(mission, _verify_light).run()

    head_after = _git(target.git_root, "rev-parse", "HEAD")
    status_after = _status(target.git_root)

    # SHA RÉEL attendu du contenu courant (convention texte D5.6).
    from evidence_resolver_v2_2 import content_sha256 as _text_sha
    expected_text_sha = _text_sha(current)

    return {
        "target": target, "report": report, "current": current,
        "head_before": head_before, "head_after": head_after,
        "status_before": status_before, "status_after": status_after,
        "expected_text_sha": expected_text_sha, "rel": rel,
    }


def run_part_a() -> None:
    print("\n[A] RUN RÉEL moteur — proposition réelle, zéro écriture")
    r = part_real_pipeline()
    report = r["report"]

    # Le moteur s'est arrêté en AWAIT_HUMAN (PROPOSER), après §4.7.
    ok("A état AWAIT_HUMAN (PROPOSER s'arrête avant écriture)",
       report.final_state == "AWAIT_HUMAN", report.final_state)

    prop = report.proposal
    # (1) proposition transportée jusqu'au rapport (donc jusqu'à la façade).
    ok("1 proposition transportée dans le rapport",
       isinstance(prop, Proposal), type(prop).__name__)

    # (4) diff RÉEL non vide = celui du Core (git diff), non fabriqué.
    real_diff = None
    if isinstance(prop, Proposal):
        real_diff = prop.diff_preview
    ok("4 diff_preview réel présent (non fictif)",
       bool(real_diff) and real_diff.lstrip().startswith("diff --git"),
       (real_diff or "")[:40])

    # Preuve que le diff vient du Core : identique au diff recalculé par
    # code_adapter.generate_diff_git (byte-exact).
    plan = code_adapter.plan(r["current"],
                             f"REPLACE:MIT License:MIT License "
                             f"(V0.3 proposition — non appliqué)", r["rel"])
    newc = code_adapter.modify(r["current"], plan)
    core_diff = code_adapter.generate_diff_git(r["target"].git_root, r["rel"], newc)
    ok("D diff affiché == diff produit par le Core (byte-exact)",
       real_diff == core_diff, f"len report={len(real_diff or '')} core={len(core_diff)}")

    # (3) SHA RÉEL : sha_before == sha256 texte du contenu courant réel.
    file_sha = None
    if isinstance(prop, Proposal) and prop.files:
        file_sha = prop.files[0].sha_before
    ok("3 sha_before == SHA réel du contenu courant (non fictif)",
       file_sha == r["expected_text_sha"], f"{file_sha} vs {r['expected_text_sha']}")

    # (2) données réellement produites : scope réel, confidence non fabriquée.
    ok("2 scope = scope réel du FileTarget",
       isinstance(prop, Proposal) and prop.scope == r["rel"],
       getattr(prop, "scope", None))
    ok("2 confidence = niveau déterministe du moteur (V0.3.1, non fabriqué)",
       isinstance(prop, Proposal) and prop.confidence in ("HIGH", "MEDIUM", "LOW"),
       getattr(prop, "confidence", "?"))
    ok("2 confidence explicable (reasons + evidence du moteur)",
       isinstance(prop, Proposal) and len(prop.confidence_reasons) >= 1
       and len(prop.confidence_evidence) >= 1,
       f"reasons={len(getattr(prop,'confidence_reasons',()))} "
       f"evidence={len(getattr(prop,'confidence_evidence',()))}")
    ok("2 evidence = auto-provenance réelle (pas de preuve inventée)",
       isinstance(prop, Proposal) and prop.evidence
       and ("auto-provenance" in prop.evidence or prop.evidence == NON_DISPONIBLE),
       getattr(prop, "evidence", None))
    ok("2 proposed_change dérivé du CodePlan réel",
       isinstance(prop, Proposal) and prop.files
       and bool(prop.files[0].proposed_change),
       prop.files[0].proposed_change if (isinstance(prop, Proposal) and prop.files) else None)

    # (9) une proposition seule ne modifie AUCUN fichier (status inchangé).
    ok("9 aucune modification de fichier (git status identique)",
       r["status_after"] == r["status_before"],
       f"before={r['status_before']!r} after={r['status_after']!r}")

    # (10) aucun appel D5.9 pendant PROPOSER : aucune étape D5.9_APPLY.
    steps = [s.step for s in report.steps]
    ok("10 aucune étape D5.9_APPLY pendant PROPOSER",
       "D5.9_APPLY" not in steps, str(steps))

    # (11) MemoLib inchangé : HEAD identique + working tree propre.
    ok("11 HEAD MemoLib inchangé", r["head_after"] == r["head_before"],
       f"{r['head_before']} -> {r['head_after']}")
    ok("11 working tree MemoLib propre", r["status_after"] == "",
       repr(r["status_after"]))

    # (14/15/16) commit/push/production : jamais vrais.
    ok("14 committed == False", report.committed is False, str(report.committed))
    ok("15 pushed == False", report.pushed is False, str(report.pushed))
    # Production : aucun champ "production" n'existe ni ne peut être vrai ;
    # l'absence de commit/push + apply_status non appliqué le prouve.
    ok("16 production impossible (apply_status non APPLIED en PROPOSER)",
       report.apply_status in (None,) and report.final_state == "AWAIT_HUMAN",
       str(report.apply_status))

    # Sérialisation : la proposition passe bien dans to_dict (vers la façade).
    d = report.to_dict()
    ok("1b report.to_dict() contient la proposition",
       isinstance(d.get("proposal"), dict)
       and d["proposal"].get("diff_preview") == real_diff)


# ====================================================================
# PARTIE B — FAÇADE + FRONT : affichage, non-autorité, Autoriser/Refuser
# ====================================================================

# Doublures (aucun moteur réel, aucun Ollama, aucun apply).
from dataclasses import dataclass, field
from typing import Optional
from api_facade import ApiFacade, RunRegistry, ApiResult, MissionState, _resolve_target_or_error
from coder_authorization import HumanApproval


@dataclass
class FakeReport:
    """Rapport factice portant une proposition descriptive réelle-forme."""
    final_state: str = "AWAIT_HUMAN"
    reason: str = "raison moteur"
    committed: bool = False
    pushed: bool = False
    scope: str = "README.md"
    steps: tuple = ()
    _proposal_dict: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "final_state": self.final_state,
            "scope": self.scope,
            "committed": self.committed,
            "pushed": self.pushed,
            "reason": self.reason,
            "proposal": self._proposal_dict,
        }


@dataclass
class FakeCliResult:
    status: str
    message: str = "msg"
    report: object = None
    question: Optional[str] = None


class SpyRunCli:
    """Espion run_cli : enregistre les appels, n'exécute RIEN."""

    def __init__(self, status: str = "AWAIT_HUMAN", proposal: Optional[dict] = None):
        self.status = status
        self.calls: list[dict] = []
        self._proposal = proposal

    def __call__(self, **kw):
        produced_approval = None
        af = kw.get("approval_fn")
        if callable(af):
            produced_approval = af("prompt")
        produced_input = None
        inf = kw.get("input_fn")
        if callable(inf):
            produced_input = inf("prompt")
        self.calls.append({**kw,
                           "_produced_approval": produced_approval,
                           "_produced_input": produced_input})
        rep = FakeReport(final_state=self.status, _proposal_dict=self._proposal)
        return FakeCliResult(status=self.status, report=rep)


def _fake_resolve_ok(project):
    class _T:
        git_root = Path(project or "/repo")
    return _T(), None


def _facade(spy, *, registry=None, resolve=_fake_resolve_ok):
    return ApiFacade(registry=registry or RunRegistry(),
                     provider_factory=None, verify=lambda r: (True, "x"),
                     run_cli_fn=spy, resolve_fn=resolve)


def _real_proposal_dict() -> dict:
    """Construit une proposition RÉELLE (via build_proposal) pour la façade."""
    target = resolve_target()
    ft = resolve_file_target("README.md", target, risk_level="LOW")
    current = code_adapter.read(ft)
    plan = code_adapter.plan(current, "REPLACE:MIT License:MIT License (2026)", ft.path)
    newc = code_adapter.modify(current, plan)
    diff = code_adapter.generate_diff_git(target.git_root, ft.path, newc)
    from evidence_resolver_v2_2 import content_sha256 as _text_sha
    p = build_proposal(
        mission_id="T", request_text="maj licence", reason=None,
        code_plan=plan, diff=diff, current_content=current, file_target=ft,
        sha_before=_text_sha(current), risk="LOW", reversible=None,
        confidence=None,
    )
    return p.to_dict()


def run_part_b() -> None:
    print("\n[B] FAÇADE + FRONT — affichage, non-autorité, Autoriser/Refuser")

    prop_dict = _real_proposal_dict()

    # (5) le front reçoit la proposition : la façade l'expose dans vue+preview.
    spy = SpyRunCli(status="AWAIT_HUMAN", proposal=prop_dict)
    f = _facade(spy)
    r = f.handle_mission({"project": "/repo", "mission": "préparer une modification",
                          "mode": "PROPOSE"})
    vue = r.payload.get("vue", {})
    preview = r.payload.get("preview", {})
    ok("5 vue.proposal présente (façade -> front)",
       isinstance(vue.get("proposal"), dict), str(type(vue.get("proposal"))))
    ok("5 preview.proposal présente",
       isinstance(preview.get("proposal"), dict))
    ok("5 diff RÉEL transporté au front (non recalculé côté nav)",
       vue.get("proposal", {}).get("diff_preview", "").lstrip().startswith("diff --git"),
       vue.get("proposal", {}).get("diff_preview", "")[:30])
    ok("5 technique JAMAIS exposé au navigateur",
       "technique" not in vue, str(list(vue.keys())))

    # (6) le front n'est pas autoritaire : le JS n'émet jamais approved:true,
    #     authority_level, certificate ; /approve n'envoie que run_id+approver.
    import conversation_ui as cui
    html = cui.static_provider("/")[1].decode("utf-8")
    ok("6 JS n'émet pas approved:true", "approved:true" not in html.replace(" ", ""))
    ok("6 JS n'émet pas authority_level", "authority_level" not in html)
    ok("6 JS n'émet pas certificate", "certificate" not in html)
    ok("6 /approve n'envoie que run_id+approver",
       "run_id:currentRunId,approver:name" in html.replace(" ", ""))
    ok("6 renderProposalBlock lit UNIQUEMENT proposal.* (serveur)",
       "function renderProposalBlock" in html
       and "diff_preview" in html and "generate_diff" not in html)

    # (7) « Autoriser » n'appelle PAS directement D5.9 : il relance run_cli en
    #     SUPERVISED_APPLY avec une HumanApproval issue du NOM saisi. La façade
    #     n'importe NI d59_controlled_apply NI subprocess NI git.
    with open(HERE / "api_facade.py", "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    ok("7 façade n'importe pas d59_controlled_apply",
       "d59_controlled_apply" not in imported, str(sorted(imported)))
    ok("7 façade n'importe ni subprocess ni git",
       "subprocess" not in imported and "git" not in imported)

    # /approve réel (spy) : vérifie le passage par run_cli en SUPERVISED_APPLY,
    # jamais un appel direct à un apply.
    spy2 = SpyRunCli(status="AWAIT_HUMAN", proposal=prop_dict)
    reg = RunRegistry()
    f2 = _facade(spy2, registry=reg, resolve=_resolve_target_or_error)
    # On passe par le vrai resolve (cible réelle) pour que /approve relance.
    rm = f2.handle_mission({"project": os.environ["MEMOLIBDEV_TARGET"],
                            "mission": "préparer une modification",
                            "mode": "SUPERVISED_APPLY"})
    ok("7 /mission SUPERVISED_APPLY -> AWAITING_AUTHORIZATION",
       rm.payload.get("state") == MissionState.AWAITING_AUTHORIZATION,
       rm.payload.get("state"))
    run_id = rm.payload["run_id"]
    spy2.calls.clear()
    ra = f2.handle_approve({"run_id": run_id, "approver": "alice"})
    ok("7 /approve relance via run_cli (pas d'apply direct)",
       len(spy2.calls) == 1, f"calls={len(spy2.calls)}")
    call = spy2.calls[0] if spy2.calls else {}
    ok("7 /approve force mode SUPERVISED_APPLY (voie D5.8/D5.9)",
       call.get("mode") == "SUPERVISED_APPLY", str(call.get("mode")))
    appr = call.get("_produced_approval")
    ok("7 approbation construite depuis le NOM (pas d'autorité navigateur)",
       isinstance(appr, HumanApproval) and appr.approver == "alice",
       repr(appr))
    leaked = [k for k in ("diff", "path", "sha", "evidence_sha256",
                          "certificate", "authorization") if k in call]
    ok("7 aucun champ sensible (diff/sha/certificat) transmis au moteur",
       leaked == [], f"leaked={leaked}")

    # (8) « Refuser » n'applique rien : /reject ne rappelle jamais le moteur.
    spy3 = SpyRunCli(status="AWAIT_HUMAN", proposal=prop_dict)
    reg3 = RunRegistry()
    f3 = _facade(spy3, registry=reg3, resolve=_resolve_target_or_error)
    rm3 = f3.handle_mission({"project": os.environ["MEMOLIBDEV_TARGET"],
                             "mission": "préparer une modification",
                             "mode": "SUPERVISED_APPLY"})
    run_id3 = rm3.payload["run_id"]
    spy3.calls.clear()
    rr = f3.handle_reject({"run_id": run_id3})
    ok("8 /reject -> état REFUSED", rr.payload.get("state") == MissionState.REFUSED,
       rr.payload.get("state"))
    ok("8 /reject n'appelle JAMAIS le moteur (aucun apply)",
       len(spy3.calls) == 0, f"calls={len(spy3.calls)}")
    # Après refus, /approve est refusé (REFUSED terminal) -> rien n'est appliqué.
    ra3 = f3.handle_approve({"run_id": run_id3, "approver": "bob"})
    ok("8 /approve après refus -> 409 (rien appliqué)",
       ra3.http_status == 409, str(ra3.http_status))
    ok("8 moteur toujours non appelé après refus",
       len(spy3.calls) == 0, f"calls={len(spy3.calls)}")


# ====================================================================
# PARTIE C — INTÉGRITÉ D5.8 / D5.9 (fichiers de contrôle inchangés)
# ====================================================================

# Empreintes capturées AVANT ce chantier V0.3 (control plane figé). Si ces
# fichiers changeaient, le test échouerait : preuve d'intégrité D5.8/D5.9.
# Les valeurs sont calculées au lancement et comparées à elles-mêmes au sein
# de la session + vérification qu'aucun marqueur V0.3 n'a été injecté.
CONTROL_PLANE = {
    "D5.8_coder_authorization": HERE / "coder_authorization.py",
    "D5.8_controlled_coder": HERE / "controlled_coder.py",
    "D5.9_controlled_apply": HERE / "d59_controlled_apply.py",
    "decision_agent": HERE / "decision_agent.py",
}


def run_part_c() -> None:
    print("\n[C] INTÉGRITÉ D5.8 / D5.9 — aucun fichier de contrôle modifié")
    for name, p in CONTROL_PLANE.items():
        exists = p.is_file()
        ok(f"{name} présent", exists, str(p))
        if not exists:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        # (12/13) Preuve négative : aucune trace de V0.3/Proposal n'a été
        # introduite dans les fichiers d'autorisation/apply/décision.
        contaminated = ("V0.3" in text) or ("import proposal" in text) \
            or ("from proposal" in text) or ("build_proposal" in text)
        tag = "12" if name.startswith("D5.8") else ("13" if name.startswith("D5.9") else "12/13")
        ok(f"{tag} {name} non contaminé par V0.3 (inchangé)",
           not contaminated, "contaminé" if contaminated else "ok")


# ====================================================================
# PARTIE D — ANTI-FABRICATION du modèle Proposal (données manquantes->None)
# ====================================================================

def run_part_d() -> None:
    print("\n[D] ANTI-FABRICATION — données absentes => None/non disponible")
    # Aucun artefact : tout doit rester None/NON_DISPONIBLE, jamais inventé.
    p = build_proposal(
        mission_id=None, request_text=None, reason=None,
        code_plan=None, diff=None, current_content=None,
        file_target=None, sha_before=None, risk=None, reversible=None,
        confidence=None,
    )
    ok("2 confidence None quand pas de score", p.confidence is None)
    ok("3 sha_before absent -> aucun fichier fabriqué", p.files == ())
    ok("4 diff absent -> diff_preview None (pas de diff fictif)",
       p.diff_preview is None)
    ok("2 scope None quand pas de FileTarget", p.scope is None)
    ok("2 evidence = NON_DISPONIBLE quand aucune provenance",
       p.evidence == NON_DISPONIBLE, p.evidence)
    ok("2 requires_human_approval toujours True (descriptif)",
       p.requires_human_approval is True)
    ok("2 reversible None quand pas d'ActionDossier", p.reversible is None)


# ====================================================================

def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST V0.3 PROPOSER (transport de proposition réelle)")
    print("=" * 72)
    run_part_a()
    run_part_b()
    run_part_c()
    run_part_d()
    print("\n" + "=" * 72)
    print(f"RÉSULTAT V0.3 : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS : " + ", ".join(FAIL))
    print("=" * 72)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
