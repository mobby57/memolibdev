"""
MemoLibDev — Test de la MACHINE D'ÉTAT serveur (api_facade)
===========================================================

Prouve que le SERVEUR — pas le navigateur — gouverne la séquence d'une
mission. Même un client hostile qui appelle directement /approve ne peut
PAS franchir un état qui ne le permet pas.

Séquence légitime (SUPERVISED_APPLY) :
    ANALYZING -> AWAITING_AUTHORIZATION -> (AUTHORIZED/EXECUTING/VERIFYING)
      -> COMPLETED | ROLLED_BACK | BLOCKED | FAILED
Refus :
    AWAITING_AUTHORIZATION -> REFUSED
Lecture (READ_ONLY/PROPOSE) :
    ANALYZING -> PROPOSAL_READY  (jamais approuvable)

Épreuves :
  S1  /mission READ_ONLY -> PROPOSAL_READY, can_approve=False
  S2  /approve direct sur PROPOSAL_READY -> 409 INVALID_STATE (hors-séquence)
  S3  /mission SUPERVISED_APPLY -> AWAITING_AUTHORIZATION, can_approve=True
  S4  /approve valide depuis AWAITING_AUTHORIZATION -> transition exécutée
  S5  double /approve (double-submit) -> le 2e est refusé (409)
  S6  /approve APRÈS /reject -> 409 (REFUSED est terminal)
  S7  /reject hors AWAITING_AUTHORIZATION -> 409
  S8  /approve sur run inconnu -> 404 ; /reject sur run inconnu -> 404
  S9  historique d'état cohérent et monotone (pas de retour en arrière)
  S10 le garde séquentiel ne REMPLACE pas D5.8/D5.9 : quand l'état autorise,
      c'est bien le MOTEUR (run_cli) qui est appelé et qui décide.

Aucun moteur gelé touché. Espions uniquement (pas d'Ollama, pas d'apply).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from api_facade import ApiFacade, RunRegistry, ApiResult, MissionState


PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


# --- doublures (aucun moteur réel) ---

@dataclass
class FakeReport:
    final_state: str = "AWAIT_HUMAN"
    reason: str = "raison moteur"
    committed: bool = False
    pushed: bool = False
    steps: tuple = ()

    def to_dict(self) -> dict:
        return {"final_state": self.final_state, "reason": self.reason,
                "committed": self.committed, "pushed": self.pushed, "steps": []}


@dataclass
class FakeCliResult:
    status: str
    message: str = ""
    report: Optional[object] = None
    question: Optional[str] = None


@dataclass
class FakeTarget:
    git_root: str = "/fake/repo"
    fingerprint: str = "fp"


class SpyRunCli:
    def __init__(self, status: str = "AWAIT_HUMAN") -> None:
        self.calls: list[dict] = []
        self._status = status

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        return FakeCliResult(status=self._status, message="x",
                             report=FakeReport(final_state=self._status))


def fake_resolve_ok(project):
    if not isinstance(project, str) or not project.strip():
        return None, ApiResult(400, {"error": "BAD_REQUEST", "reason": "vide"})
    return FakeTarget(git_root=project.strip()), None


def facade(status="AWAIT_HUMAN"):
    reg = RunRegistry()
    spy = SpyRunCli(status=status)
    f = ApiFacade(registry=reg, provider_factory=None,
                  verify=lambda r: (True, "ok"),
                  run_cli_fn=spy, resolve_fn=fake_resolve_ok)
    return f, reg, spy


def mission(f, mode):
    return f.handle_mission({"project": "/repo",
                             "mission": "mission suffisamment longue ici",
                             "mode": mode})


def main() -> int:
    print("=" * 72)
    print("MEMOLIBDEV — TEST machine d'état serveur")
    print("=" * 72)

    # S1 — READ_ONLY -> PROPOSAL_READY, non approuvable
    print("\n[S1] READ_ONLY -> PROPOSAL_READY")
    f, reg, spy = facade()
    r = mission(f, "READ_ONLY")
    ok("S1 state=PROPOSAL_READY", r.payload.get("state") == MissionState.PROPOSAL_READY,
       str(r.payload.get("state")))
    ok("S1 can_approve=False", r.payload.get("can_approve") is False)
    ok("S1 can_reject=False", r.payload.get("can_reject") is False)

    # S2 — /approve direct sur PROPOSAL_READY -> 409 (hors-séquence)
    print("\n[S2] /approve direct sans aperçu d'action -> 409")
    run_id = r.payload["run_id"]
    napprove_calls = len(spy.calls)
    ra = f.handle_approve({"run_id": run_id, "approver": "attacker"})
    ok("S2 http 409", ra.http_status == 409, str(ra.http_status))
    ok("S2 INVALID_STATE", ra.payload.get("error") == "INVALID_STATE", str(ra.payload))
    ok("S2 moteur NON rappelé par /approve",
       len(spy.calls) == napprove_calls, f"calls={len(spy.calls)}")

    # S3 — SUPERVISED_APPLY -> AWAITING_AUTHORIZATION, approuvable
    print("\n[S3] SUPERVISED_APPLY -> AWAITING_AUTHORIZATION")
    f, reg, spy = facade()
    r = mission(f, "SUPERVISED_APPLY")
    ok("S3 state=AWAITING_AUTHORIZATION",
       r.payload.get("state") == MissionState.AWAITING_AUTHORIZATION,
       str(r.payload.get("state")))
    ok("S3 can_approve=True", r.payload.get("can_approve") is True)
    ok("S3 can_reject=True", r.payload.get("can_reject") is True)

    # S4 — /approve valide -> transition exécutée (moteur appelé)
    print("\n[S4] /approve valide depuis AWAITING_AUTHORIZATION")
    run_id = r.payload["run_id"]
    before = len(spy.calls)
    ra = f.handle_approve({"run_id": run_id, "approver": "alice"})
    ok("S4 http 200", ra.http_status == 200, str(ra.http_status))
    ok("S4 moteur appelé (run_cli)", len(spy.calls) == before + 1)
    ok("S4 state progressé hors AWAITING_AUTHORIZATION",
       ra.payload.get("state") != MissionState.AWAITING_AUTHORIZATION,
       str(ra.payload.get("state")))
    ok("S4 can_approve=False après exécution",
       ra.payload.get("can_approve") is False)

    # S5 — double /approve : le 2e refusé (anti double-submit)
    print("\n[S5] double /approve -> 2e refusé")
    f, reg, spy = facade()
    r = mission(f, "SUPERVISED_APPLY")
    run_id = r.payload["run_id"]
    r1 = f.handle_approve({"run_id": run_id, "approver": "alice"})
    calls_after_first = len(spy.calls)
    r2 = f.handle_approve({"run_id": run_id, "approver": "alice"})
    ok("S5 1er /approve 200", r1.http_status == 200, str(r1.http_status))
    ok("S5 2e /approve 409", r2.http_status == 409, str(r2.http_status))
    ok("S5 2e INVALID_STATE", r2.payload.get("error") == "INVALID_STATE", str(r2.payload))
    ok("S5 moteur NON rappelé au 2e /approve",
       len(spy.calls) == calls_after_first, f"calls={len(spy.calls)}")

    # S6 — /approve APRÈS /reject -> 409 (REFUSED terminal)
    print("\n[S6] /reject puis /approve -> 409")
    f, reg, spy = facade()
    r = mission(f, "SUPERVISED_APPLY")
    run_id = r.payload["run_id"]
    rj = f.handle_reject({"run_id": run_id})
    ok("S6 /reject 200", rj.http_status == 200, str(rj.http_status))
    ok("S6 state=REFUSED", rj.payload.get("state") == MissionState.REFUSED,
       str(rj.payload.get("state")))
    before = len(spy.calls)
    ra = f.handle_approve({"run_id": run_id, "approver": "alice"})
    ok("S6 /approve après refus 409", ra.http_status == 409, str(ra.http_status))
    ok("S6 moteur NON appelé après refus", len(spy.calls) == before)

    # S7 — /reject hors AWAITING_AUTHORIZATION -> 409
    print("\n[S7] /reject sur PROPOSAL_READY -> 409")
    f, reg, spy = facade()
    r = mission(f, "READ_ONLY")   # PROPOSAL_READY
    rj = f.handle_reject({"run_id": r.payload["run_id"]})
    ok("S7 http 409", rj.http_status == 409, str(rj.http_status))
    ok("S7 INVALID_STATE", rj.payload.get("error") == "INVALID_STATE", str(rj.payload))

    # S8 — run inconnu -> 404 pour /approve et /reject
    print("\n[S8] run inconnu -> 404")
    f, reg, spy = facade()
    ra = f.handle_approve({"run_id": "inexistant", "approver": "alice"})
    rj = f.handle_reject({"run_id": "inexistant"})
    ok("S8 /approve inconnu 404", ra.http_status == 404, str(ra.http_status))
    ok("S8 /approve UNKNOWN_RUN", ra.payload.get("error") == "UNKNOWN_RUN")
    ok("S8 /reject inconnu 404", rj.http_status == 404, str(rj.http_status))
    ok("S8 /reject UNKNOWN_RUN", rj.payload.get("error") == "UNKNOWN_RUN")

    # S9 — historique monotone (pas de retour en arrière)
    print("\n[S9] historique d'état cohérent")
    f, reg, spy = facade()
    r = mission(f, "SUPERVISED_APPLY")
    run_id = r.payload["run_id"]
    f.handle_approve({"run_id": run_id, "approver": "alice"})
    rec = reg.get(run_id)
    hist = rec.history
    ok("S9 commence par ANALYZING", hist[0] == MissionState.ANALYZING, str(hist))
    ok("S9 passe par AWAITING_AUTHORIZATION",
       MissionState.AWAITING_AUTHORIZATION in hist, str(hist))
    ok("S9 passe par EXECUTING", MissionState.EXECUTING in hist, str(hist))
    ok("S9 se termine en état terminal",
       hist[-1] in (MissionState.COMPLETED, MissionState.ROLLED_BACK,
                    MissionState.BLOCKED, MissionState.FAILED), str(hist))

    # S10 — le garde séquentiel ne remplace pas le moteur : quand l'état
    #       autorise, c'est run_cli (le moteur) qui est appelé et décide.
    print("\n[S10] garde séquentiel non-autoritaire (le moteur décide)")
    f, reg, spy = facade(status="BLOCKED")   # le moteur peut toujours bloquer
    r = mission(f, "SUPERVISED_APPLY")
    run_id = r.payload["run_id"]
    before = len(spy.calls)
    ra = f.handle_approve({"run_id": run_id, "approver": "alice"})
    ok("S10 moteur appelé même en état autorisé", len(spy.calls) == before + 1)
    ok("S10 verdict suit le MOTEUR (BLOCKED -> state BLOCKED)",
       ra.payload.get("state") == MissionState.BLOCKED, str(ra.payload.get("state")))
    ok("S10 can_approve=False (moteur a tranché)",
       ra.payload.get("can_approve") is False)

    print("\n" + "=" * 72)
    print(f"RÉSULTAT MACHINE D'ÉTAT : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ÉCHECS :", ", ".join(FAIL))
    print("=" * 72)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
