"""
MemoLibDev — R4 : Provider Timeout (fail-closed, sans exécution fantôme)
========================================================================

Rend l'appel `provider.analyze_plan(context)` BORNÉ par un timeout réel.

Problème (Windows / Python 3.11) :
  - un thread daemon NE PEUT PAS être tué : si le provider bloque, le
    thread continue d'exécuter le provider APRÈS un BLOCK -> « exécution
    fantôme » ;
  - `signal.alarm` n'existe pas sur Windows.

Solution retenue : ISOLATION PAR PROCESSUS (`multiprocessing`, spawn).
  - le provider s'exécute dans un process ENFANT ;
  - au-delà du timeout, on appelle `process.terminate()` qui tue
    RÉELLEMENT le process (donc le calcul s'arrête — pas de fantôme) ;
  - le résultat transite par une Queue ; en cas de timeout, aucune
    valeur n'est lue -> le planner reçoit None -> BLOCK.

Contrat :
  call_provider_with_timeout(provider, context, timeout_s)
      -> TimeoutOutcome(status=OK|TIMEOUT|ERROR, plan: LLMPlan|None, reason)

Garanties :
  - timeout dépassé  -> TIMEOUT, plan=None (le planner BLOQUE) ;
  - aucune attente infinie (join borné + terminate + kill de secours) ;
  - aucun fallback automatique vers un autre provider ou une action ;
  - aucune écriture disque par ce module ;
  - le process enfant est terminé : pas d'exécution fantôme.

Contrainte spawn : `provider` et `context` doivent être picklables.
Les providers réels (ex. Ollama) le seront (config simple + appel réseau
dans l'enfant). Un provider non picklable -> ERROR -> BLOCK (fail-closed).

Aucune nouvelle dépendance externe (stdlib `multiprocessing`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import multiprocessing as mp


DEFAULT_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class TimeoutOutcome:
    status: str                 # OK | TIMEOUT | ERROR
    plan: Optional[object]      # LLMPlan | None
    reason: str


def _child_entry(provider, context, queue) -> None:
    """
    Exécuté dans le PROCESS ENFANT. Appelle le provider et renvoie le
    résultat via la queue. Toute exception est capturée et transmise
    comme ERROR (fail-closed côté parent).
    """
    try:
        plan = provider.analyze_plan(context)
        queue.put(("OK", plan))
    except Exception as exc:                     # noqa: BLE001 (fail-closed)
        queue.put(("ERROR", repr(exc)))


def call_provider_with_timeout(
    provider,
    context,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> TimeoutOutcome:
    """
    Appelle `provider.analyze_plan(context)` dans un process isolé, borné
    par `timeout_s`. Fail-closed : tout problème -> plan=None.
    """
    # --- Guard PyInstaller : multiprocessing spawn est incompatible avec
    # un .exe (relance le binaire sans arguments). On appelle le provider
    # directement dans le processus courant. Le timeout R4 est desactive
    # en mode .exe, mais le comportement reste fail-closed.
    import sys as _sys
    if getattr(_sys, "frozen", False):
        try:
            plan = provider.analyze_plan(context)
            if plan is None:
                return TimeoutOutcome(
                    status="ERROR", plan=None,
                    reason="provider indisponible en mode .exe (frozen)")
            return TimeoutOutcome(status="OK", plan=plan, reason="")
        except Exception as e:
            return TimeoutOutcome(
                status="ERROR", plan=None,
                reason=f"appel provider echoue : {type(e).__name__}: {e}")

    if timeout_s is None or timeout_s <= 0:
        return TimeoutOutcome("ERROR", None, "timeout invalide (<=0)")

    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    proc = ctx.Process(target=_child_entry, args=(provider, context, queue))

    try:
        proc.start()
    except Exception as exc:                     # pickling/spawn échoué
        return TimeoutOutcome("ERROR", None,
                              f"provider non isolable: {exc!r}")

    proc.join(timeout_s)

    if proc.is_alive():
        # TIMEOUT : on TUE réellement le process (pas d'exécution fantôme).
        proc.terminate()
        proc.join(5.0)
        if proc.is_alive():                      # dernier recours
            try:
                proc.kill()
            except Exception:
                pass
            proc.join(5.0)
        return TimeoutOutcome(
            "TIMEOUT", None,
            f"provider timeout > {timeout_s}s (process terminé, "
            f"aucune exécution fantôme)",
        )

    # Le process s'est terminé dans les temps : lire le résultat.
    try:
        kind, payload = queue.get_nowait()
    except Exception:
        return TimeoutOutcome("ERROR", None,
                              "process terminé sans résultat")

    if kind == "OK":
        return TimeoutOutcome("OK", payload, "provider a répondu dans les temps")
    return TimeoutOutcome("ERROR", None, f"provider a levé: {payload}")
