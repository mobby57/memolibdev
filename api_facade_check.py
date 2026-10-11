"""
MemoLibDev — Test de l'API façade (api_facade) : API + fail-closed
==================================================================

Prouve que l'API est une FAÇADE MINCE sans autorité propre. Tous les tests
tournent SANS socket, SANS Ollama et SANS apply réel : on injecte un
`run_cli` espion et un `resolve_fn` factice. Ainsi on vérifie le
COMPORTEMENT de la façade (ce qu'elle transmet, ce qu'elle refuse, ce
qu'elle traduit), pas le moteur (déjà prouvé par ailleurs).

Liste imposée (toutes couvertes) :
  A1  /mission valide -> résultat
  A2  ANALYSER (READ_ONLY) -> intention UI "Comprendre"
  A3  PROPOSE -> "Proposer"
  A4  SUPERVISED_APPLY -> "Agir"
  A5  projet invalide -> fail-closed
  A6  mission invalide -> fail-closed
  A7  mode invalide -> fail-closed
  A8  absence de run -> /approve bloque
  A9  run_id inconnu -> /approve bloque
  A10 /approve ne peut pas fabriquer une autorisation (approver obligatoire)
  A11 aucun diff/path/SHA accepté depuis le body d'approbation
  A12 aucune écriture involontaire (le run_cli espion n'écrit jamais)
  A13 aucun commit/push (rapport committed/pushed = False)
  A14 PURETÉ façade : api_facade n'importe NI subprocess NI git ;
      /mission ne fabrique jamais d'approbation (approval_fn -> None)
  A15 /approve construit une HumanApproval UNIQUEMENT depuis le nom saisi

Aucun moteur gelé touché. Aucun apply/commit/push réel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import ast
import os

from api_facade import ApiFacade, RunRegistry, ApiResult, API_MODES
from coder_authorization import HumanApproval


PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


# ------------------------------------------------------------------
# Doublures : on ne dépend NI du moteur NI d'Ollama NI du disque.
# ------------------------------------------------------------------

@dataclass
class FakeReport:
    """Imite AgentReport.to_dict() minimal, SANS commit/push."""
    final_state: str = "AWAIT_HUMAN"
    reason: str = "raison technique du moteur"
    committed: bool = False
    pushed: bool = False
    steps: tuple = ()

    def to_dict(self) -> dict:
        return {
            "final_state": self.final_state,
            "reason": self.reason,
            "committed": self.committed,
            "pushed": self.pushed,
            "steps": [],
        }


@dataclass
class FakeCliResult:
    status: str
    message: str = ""
    report: Optional[object] = None
    question: Optional[str] = None


@dataclass
class FakeTarget:
    """Imite ProjectTarget pour le strict usage de la façade (git_root)."""
    git_root: str = "/fake/repo"
    fingerprint: str = "fp-fake"


class SpyRunCli:
    """
    Espion de run_cli : enregistre les appels et renvoie un CliResult
    factice. N'ÉCRIT RIEN, ne commit/push jamais. Prouve ce que la façade
    transmet au moteur (mode, mission, approval_fn, input_fn).
    """

    def __init__(self, status: str = "AWAIT_HUMAN") -> None:
        self.calls: list[dict] = []
        self._status = status

    def __call__(self, **kwargs) -> FakeCliResult:
        # Matérialise ce que la façade a injecté pour approval_fn/input_fn.
        approval_fn = kwargs.get("approval_fn")
        input_fn = kwargs.get("input_fn")
        produced_approval = approval_fn("prompt") if approval_fn else "<none>"
        produced_input = input_fn("prompt") if input_fn else "<none>"
        record = dict(kwargs)
        record["_produced_approval"] = produced_approval
        record["_produced_input"] = produced_input
        self.calls.append(record)
        return FakeCliResult(
            status=self._status,
            message="façade test",
            report=FakeReport(final_state=self._status),
        )


def fake_resolve_ok(project):
    """resolve_fn factice : projet valide -> FakeTarget."""
    if not isinstance(project, str) or not project.strip():
        return None, ApiResult(400, {"error": "BAD_REQUEST", "reason": "project vide"})
    return FakeTarget(git_root=project.strip()), None


def fake_resolve_invalid(project):
    """resolve_fn factice : projet TOUJOURS invalide (fail-closed)."""
    return None, ApiResult(400, {"error": "INVALID_PROJECT",
                                 "reason": "cible non résolue (fake)"})


def _facade(spy: SpyRunCli, resolve=fake_resolve_ok,
            registry: Optional[RunRegistry] = None) -> ApiFacade:
    return ApiFacade(
        registry=registry,
        provider_factory=None,            # pas d'Ollama
        verify=lambda repo: (True, "verify léger (test)"),
        run_cli_fn=spy,
        resolve_fn=resolve,
    )


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST api_facade (API + fail-closed)")
    print("=" * 72)

    # ========================================================
    # A1 — /mission valide -> résultat (200 + run_id + status + vue)
    # ========================================================
    print("\n[A1] /mission valide -> résultat")
    spy = SpyRunCli(status="AWAIT_HUMAN")
    f = _facade(spy)
    r = f.handle_mission({"project": "/repo", "mission": "analyser la connexion",
                          "mode": "READ_ONLY"})
    ok("A1 http 200", r.http_status == 200, str(r.http_status))
    ok("A1 run_id présent", bool(r.payload.get("run_id")))
    ok("A1 status remonté", r.payload.get("status") == "AWAIT_HUMAN")
    ok("A1 vue présente", isinstance(r.payload.get("vue"), dict))
    ok("A1 run_cli appelé une fois", len(spy.calls) == 1)
    ok("A1 mission transmise", spy.calls[0]["mission"] == "analyser la connexion")

    # ========================================================
    # A2/A3/A4 — vocabulaire UI additif par mode
    # ========================================================
    print("\n[A2/A3/A4] intention UI par mode")
    for mode, verbe in (("READ_ONLY", "Comprendre"),
                        ("PROPOSE", "Proposer"),
                        ("SUPERVISED_APPLY", "Agir")):
        spy = SpyRunCli(status="AWAIT_HUMAN")
        f = _facade(spy)
        r = f.handle_mission({"project": "/repo", "mission": "mission suffisante ici",
                              "mode": mode})
        intention = r.payload.get("vue", {}).get("intention_ui")
        ok(f"{mode} -> {verbe}", intention == verbe, f"obtenu={intention}")
        # Le niveau de contrôle technique (brique B) reste INCHANGÉ (H2).
        niveau = r.payload.get("vue", {}).get("niveau_de_controle")
        ok(f"{mode} niveau technique conservé", niveau in
           ("Observer", "Préparer", "Tester", "Modifier"), f"niveau={niveau}")

    # ========================================================
    # A5 — projet invalide -> fail-closed
    # ========================================================
    print("\n[A5] projet invalide -> fail-closed")
    spy = SpyRunCli()
    f = _facade(spy, resolve=fake_resolve_invalid)
    r = f.handle_mission({"project": "/nope", "mission": "mission suffisante ici",
                          "mode": "READ_ONLY"})
    ok("A5 http 400", r.http_status == 400, str(r.http_status))
    ok("A5 run_cli PAS appelé (aucune écriture)", len(spy.calls) == 0)

    # ========================================================
    # A6 — mission invalide -> fail-closed
    # ========================================================
    print("\n[A6] mission invalide -> fail-closed")
    for bad in ("", "   ", None, 123):
        spy = SpyRunCli()
        f = _facade(spy)
        r = f.handle_mission({"project": "/repo", "mission": bad, "mode": "READ_ONLY"})
        ok(f"A6 mission={bad!r} -> 400", r.http_status == 400, str(r.http_status))
        ok(f"A6 mission={bad!r} -> run_cli non appelé", len(spy.calls) == 0)

    # ========================================================
    # A7 — mode invalide -> fail-closed
    # ========================================================
    print("\n[A7] mode invalide -> fail-closed")
    for bad in ("APPLY", "ADMIN", "", "read_only", "DELETE"):
        spy = SpyRunCli()
        f = _facade(spy)
        r = f.handle_mission({"project": "/repo", "mission": "mission suffisante ici",
                              "mode": bad})
        ok(f"A7 mode={bad!r} -> 400", r.http_status == 400, str(r.http_status))
        ok(f"A7 mode={bad!r} -> run_cli non appelé", len(spy.calls) == 0)

    # ========================================================
    # A8 — absence de run -> /approve bloque
    # ========================================================
    print("\n[A8] absence de run -> /approve bloque")
    spy = SpyRunCli()
    f = _facade(spy)
    r = f.handle_approve({"approver": "alice"})   # pas de run_id
    ok("A8 http 400", r.http_status == 400, str(r.http_status))
    ok("A8 error NO_RUN", r.payload.get("error") == "NO_RUN", str(r.payload))
    ok("A8 run_cli non appelé", len(spy.calls) == 0)

    # ========================================================
    # A9 — run_id inconnu -> /approve bloque
    # ========================================================
    print("\n[A9] run_id inconnu -> /approve bloque")
    spy = SpyRunCli()
    f = _facade(spy)
    r = f.handle_approve({"run_id": "deadbeef-inconnu", "approver": "alice"})
    ok("A9 http 404", r.http_status == 404, str(r.http_status))
    ok("A9 error UNKNOWN_RUN", r.payload.get("error") == "UNKNOWN_RUN", str(r.payload))
    ok("A9 run_cli non appelé", len(spy.calls) == 0)

    # ========================================================
    # A10 — /approve ne peut pas fabriquer une autorisation.
    #   (a) hors-séquence : un run READ_ONLY est en PROPOSAL_READY,
    #       /approve y est refusé (409 INVALID_STATE) AVANT tout moteur ;
    #   (b) approbation anonyme interdite sur un run réellement en
    #       AWAITING_AUTHORIZATION (SUPERVISED_APPLY -> AWAIT_HUMAN).
    # ========================================================
    print("\n[A10] /approve : hors-séquence + approbation anonyme refusés")
    # (a) hors-séquence (READ_ONLY -> PROPOSAL_READY)
    spy = SpyRunCli(status="AWAIT_HUMAN")
    reg = RunRegistry()
    f = _facade(spy, registry=reg)
    rm = f.handle_mission({"project": "/repo", "mission": "mission suffisante ici",
                           "mode": "READ_ONLY"})
    run_id_ro = rm.payload["run_id"]
    ok("A10a état = PROPOSAL_READY",
       rm.payload.get("state") == "PROPOSAL_READY", str(rm.payload.get("state")))
    ok("A10a can_approve == False", rm.payload.get("can_approve") is False)
    spy.calls.clear()
    r = f.handle_approve({"run_id": run_id_ro, "approver": "alice"})
    ok("A10a /approve hors-séquence -> 409", r.http_status == 409, str(r.http_status))
    ok("A10a INVALID_STATE", r.payload.get("error") == "INVALID_STATE", str(r.payload))
    ok("A10a run_cli NON appelé (bloqué avant moteur)", len(spy.calls) == 0)

    # (b) approbation anonyme sur un run réellement en AWAITING_AUTHORIZATION
    for bad in (None, "", "   "):
        spy = SpyRunCli(status="AWAIT_HUMAN")
        reg = RunRegistry()
        f = _facade(spy, registry=reg)
        rm = f.handle_mission({"project": "/repo", "mission": "mission suffisante ici",
                               "mode": "SUPERVISED_APPLY"})
        ok(f"A10b état = AWAITING_AUTHORIZATION ({bad!r})",
           rm.payload.get("state") == "AWAITING_AUTHORIZATION",
           str(rm.payload.get("state")))
        run_id = rm.payload["run_id"]
        spy.calls.clear()
        r = f.handle_approve({"run_id": run_id, "approver": bad})
        ok(f"A10b approver={bad!r} -> 400", r.http_status == 400, str(r.http_status))
        ok(f"A10b approver={bad!r} -> NO_APPROVER",
           r.payload.get("error") == "NO_APPROVER", str(r.payload))
        ok(f"A10b approver={bad!r} -> run_cli non appelé", len(spy.calls) == 0)

    # ========================================================
    # A11 — aucun diff/path/SHA accepté depuis le body d'approbation.
    #       Run réellement en AWAITING_AUTHORIZATION (SUPERVISED_APPLY).
    # ========================================================
    print("\n[A11] /approve ignore diff/path/sha/certificat/autorisation du body")
    spy = SpyRunCli(status="AWAIT_HUMAN")
    reg = RunRegistry()
    f = _facade(spy, registry=reg)
    rm = f.handle_mission({"project": "/repo", "mission": "mission suffisante ici",
                           "mode": "SUPERVISED_APPLY"})
    run_id = rm.payload["run_id"]
    spy.calls.clear()
    poisoned = {
        "run_id": run_id,
        "approver": "alice",
        # Tentatives d'injection d'autorité -> doivent être IGNORÉES.
        "diff": "--- a/secret\n+++ b/secret\n@@ pwn @@",
        "path": "../../etc/passwd",
        "sha": "0" * 64,
        "evidence_sha256": "f" * 64,
        "certificate": {"status": "AUTHORIZED"},
        "authorization": {"status": "AUTHORIZED"},
        "approved": True,
        "authority_level": "L6_CRITICAL_ACTION",
    }
    r = f.handle_approve(poisoned)
    ok("A11 http 200 (relance via run_cli)", r.http_status == 200, str(r.http_status))
    ok("A11 run_cli appelé", len(spy.calls) == 1)
    call = spy.calls[0] if spy.calls else {}
    # La façade ne transmet AUCUN de ces champs à run_cli (run_cli n'a pas
    # ces paramètres). On vérifie qu'aucune clé sensible n'a fuité.
    leaked = [k for k in ("diff", "path", "sha", "evidence_sha256",
                          "certificate", "authorization")
              if k in call]
    ok("A11 aucun champ sensible transmis à run_cli", leaked == [], f"leaked={leaked}")
    # L'approbation transmise est construite depuis le NOM, pas depuis body.
    appr = call.get("_produced_approval")
    ok("A11 approbation = depuis le nom (pas body)",
       isinstance(appr, HumanApproval) and appr.approver == "alice",
       repr(appr))
    # Le mode forcé est SUPERVISED_APPLY (passe par D5.8/D5.9).
    ok("A11 mode SUPERVISED_APPLY", call.get("mode") == "SUPERVISED_APPLY",
       str(call.get("mode")))
    # Le niveau d'autorité n'est PAS celui du body (L6) : la façade impose L3.
    ok("A11 authority_level non pris du body",
       isinstance(appr, HumanApproval) and appr.authority_level != "L6_CRITICAL_ACTION",
       getattr(appr, "authority_level", None))

    # ========================================================
    # A12 — aucune écriture involontaire : le run_cli espion n'écrit jamais,
    #       et /mission ne déclenche jamais la voie d'apply (approval=None).
    # ========================================================
    print("\n[A12] aucune écriture involontaire via /mission")
    spy = SpyRunCli(status="AWAIT_HUMAN")
    f = _facade(spy)
    f.handle_mission({"project": "/repo", "mission": "mission suffisante ici",
                      "mode": "SUPERVISED_APPLY"})
    call = spy.calls[0]
    ok("A12 /mission -> approval_fn renvoie None",
       call["_produced_approval"] is None, repr(call["_produced_approval"]))
    ok("A12 /mission -> input_fn renvoie '' (pas de devinette)",
       call["_produced_input"] == "", repr(call["_produced_input"]))

    # ========================================================
    # A13 — aucun commit/push (rapport committed/pushed = False)
    # ========================================================
    print("\n[A13] aucun commit/push + technique caché du navigateur")
    spy = SpyRunCli(status="APPLIED")
    reg = RunRegistry()
    f = _facade(spy, registry=reg)
    r = f.handle_mission({"project": "/repo", "mission": "mission suffisante ici",
                          "mode": "READ_ONLY"})
    # (1) Le niveau technique n'est JAMAIS exposé au navigateur.
    ok("A13 'technique' absent de la vue publique",
       "technique" not in r.payload["vue"], str(list(r.payload["vue"].keys())))
    # (2) Le journal technique côté SERVEUR prouve l'absence de commit/push.
    rec = reg.get(r.payload["run_id"])
    tech = (rec.technical_log[-1] if rec and rec.technical_log else {})
    ok("A13 committed == False (journal serveur)",
       tech.get("committed") is False, str(tech.get("committed")))
    ok("A13 pushed == False (journal serveur)",
       tech.get("pushed") is False, str(tech.get("pushed")))

    # ========================================================
    # A14 — PURETÉ façade : pas de subprocess/git importés ; /mission ne
    #       fabrique jamais d'approbation.
    # ========================================================
    print("\n[A14] pureté façade (analyse statique de api_facade.py)")
    with open(os.path.join(os.path.dirname(__file__), "api_facade.py"),
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
    ok("A14 pas d'import subprocess", "subprocess" not in imported, str(sorted(imported)))
    ok("A14 pas d'import git", "git" not in imported)
    # /mission ne fabrique jamais d'approbation (déjà vérifié A12), on
    # réaffirme ici que la seule approbation provient de /approve.

    # ========================================================
    # A15 — /approve : HumanApproval construite UNIQUEMENT depuis le nom
    # ========================================================
    print("\n[A15] /approve -> HumanApproval depuis le nom saisi uniquement")
    spy = SpyRunCli(status="AWAIT_HUMAN")
    reg = RunRegistry()
    f = _facade(spy, registry=reg)
    rm = f.handle_mission({"project": "/repo", "mission": "mission suffisante ici",
                           "mode": "SUPERVISED_APPLY"})
    run_id = rm.payload["run_id"]
    spy.calls.clear()
    r = f.handle_approve({"run_id": run_id, "approver": "  bob  "})
    appr = spy.calls[0]["_produced_approval"]
    ok("A15 approved=True", isinstance(appr, HumanApproval) and appr.approved is True)
    ok("A15 approver = nom trimé", isinstance(appr, HumanApproval)
       and appr.approver == "bob", getattr(appr, "approver", None))
    ok("A15 approved_at renseigné", isinstance(appr, HumanApproval)
       and bool(appr.approved_at))

    # ========================================================
    # Bilan
    # ========================================================
    print("\n" + "=" * 72)
    print(f"RÉSULTAT : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
