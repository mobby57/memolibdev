"""
MemoLibDev — api_facade : API locale FAÇADE (mince, sans autorité propre)
=========================================================================

Façade HTTP locale posée AU-DESSUS de `run_cli` (memolibdev_cli), lui-même
posé au-dessus du moteur validé `run_from_mission` -> D5.8 -> D5.9. Zéro
dépendance : uniquement la stdlib (`http.server`).

RÈGLE D'ARCHITECTURE ABSOLUE (gravée, non négociable) :
    « L'API est une façade. Elle ne possède AUCUNE autorité de sécurité. »

Si on supprime ce fichier, le moteur MemoLibDev continue EXACTEMENT comme
avant : rien ici n'est requis par la chaîne de sécurité.

Ce que l'API NE PEUT PAS fabriquer (par construction) :
    - un diff ;
    - un chemin (path) autorisé ;
    - un SHA / un certificat ;
    - une autorisation (D5.8) ;
    - une approbation humaine (HumanApproval.approved=True).

Elle TRANSPORTE seulement des entrées (project, mission, mode) et, pour
l'approbation, le NOM d'un approbateur saisi côté client — exactement comme
le ferait `_real_approval` de la CLI. L'autorité reste chez D5.8/D5.9.

Garde-fous :
    - AUCUN subprocess vers le moteur : import Python direct de run_cli ;
    - AUCUN git/apply/commit/push ici : délégué à run_cli -> D5.9 ;
    - fail-closed : toute entrée invalide (projet/mission/mode) -> erreur,
      jamais de devinette, jamais d'écriture ;
    - /mission ne fournit NI action NI approval -> la chaîne s'arrête avant
      toute écriture (AWAIT_HUMAN) ;
    - /approve ne fabrique pas l'autorisation : il relance run_cli en
      SUPERVISED_APPLY avec une HumanApproval issue du NOM saisi ; les
      champs sensibles (diff/path/SHA) d'un éventuel body sont IGNORÉS.

Routes :
    POST /mission   {project, mission, mode}      -> vue UI + technique
    POST /approve   {run_id, approver}            -> relance SUPERVISED_APPLY

Le serveur n'écoute QUE sur 127.0.0.1 (local).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable, Optional
import json
import threading
import uuid

from project_target import resolve_target, ProjectTarget, ProjectTargetError
from coder_authorization import HumanApproval, AuthorityLevel
from memolibdev_cli import run_cli, CliResult
from humanize_ui import humanize_ui


# Modes exposés par l'API. SANDBOX est accepté (étape interne) mais le
# vocabulaire UI le rend invisible. L'API ne définit PAS ses propres modes :
# elle réutilise ceux de la CLI/moteur.
API_MODES = ("READ_ONLY", "PROPOSE", "SANDBOX", "SUPERVISED_APPLY")


class MissionState:
    """États serveur. Le navigateur ne peut pas les faire progresser seul."""

    ANALYZING = "ANALYZING"
    PROPOSAL_READY = "PROPOSAL_READY"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    REFUSED = "REFUSED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    QUESTION = "QUESTION"


# ------------------------------------------------------------------
# Registre de runs EN MÉMOIRE (pas de persistance, pas d'autorité).
# Il ne stocke QUE project+mission d'un /mission, pour que /approve
# puisse relancer SUPERVISED_APPLY SANS que le client ne refournisse
# (ni ne forge) la cible. Aucun diff/SHA/path/certificat n'y est stocké.
# ------------------------------------------------------------------

@dataclass
class _RunRecord:
    run_id: str
    project: str          # racine de dépôt (chaîne telle que résolue)
    mission: str
    mode: str
    state: str = MissionState.ANALYZING
    result_status: Optional[str] = None
    technical_log: list[dict] = field(default_factory=list)
    history: list[str] = field(default_factory=lambda: [MissionState.ANALYZING])
    # V0.4.1 : binding de la proposition présentée (depuis le rapport moteur).
    # Permet à /approve de lier la décision humaine au diff EXACT proposé.
    # Jamais fourni par le client : capturé du rapport serveur.
    proposal_id: Optional[str] = None
    diff_sha256: Optional[str] = None


class RunRegistry:
    """Registre thread-safe, purement mémoire. Zéro autorité."""

    def __init__(self) -> None:
        self._runs: dict[str, _RunRecord] = {}
        self._lock = threading.Lock()

    def create(self, *, project: str, mission: str, mode: str) -> str:
        run_id = uuid.uuid4().hex
        with self._lock:
            self._runs[run_id] = _RunRecord(
                run_id=run_id, project=project, mission=mission, mode=mode,
            )
        return run_id

    def get(self, run_id: str) -> Optional[_RunRecord]:
        with self._lock:
            return self._runs.get(run_id)

    def finish_analysis(self, run_id: str, *, mode: str, status: str,
                        technical: Optional[dict]) -> Optional[_RunRecord]:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None or record.state != MissionState.ANALYZING:
                return None
            if status == "AWAIT_HUMAN":
                state = (MissionState.PROPOSAL_READY if mode == "READ_ONLY"
                         else MissionState.AWAITING_AUTHORIZATION)
            elif status == "QUESTION":
                state = MissionState.QUESTION
            elif status in ("BLOCKED", "NO_PATCH_POSSIBLE"):
                state = MissionState.BLOCKED
            else:
                state = MissionState.FAILED
            record.state = state
            record.result_status = status
            record.history.append(state)
            if technical is not None:
                record.technical_log.append(technical)
                # V0.4.1 : capturer le binding de la proposition présentée
                # (proposal_id + diff_sha256) depuis le rapport serveur, pour
                # que /approve lie la décision humaine au diff EXACT. Jamais
                # fourni/forgé par le client.
                prop = technical.get("proposal") if isinstance(technical, dict) else None
                if isinstance(prop, dict):
                    record.proposal_id = prop.get("proposal_id")
                    record.diff_sha256 = prop.get("diff_sha256")
            return record

    def begin_approval(self, run_id: str) -> Optional[_RunRecord]:
        """Transition atomique : un double-clic ne peut lancer qu'un seul apply."""
        with self._lock:
            record = self._runs.get(run_id)
            if record is None or record.state != MissionState.AWAITING_AUTHORIZATION:
                return None
            record.state = MissionState.AUTHORIZED
            record.history.append(MissionState.AUTHORIZED)
            record.state = MissionState.EXECUTING
            record.history.append(MissionState.EXECUTING)
            return record

    def finish_execution(self, run_id: str, *, status: str,
                         technical: Optional[dict]) -> Optional[_RunRecord]:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None or record.state != MissionState.EXECUTING:
                return None
            record.history.append(MissionState.VERIFYING)
            if status == "APPLIED":
                state = MissionState.COMPLETED
            elif status == "ROLLED_BACK":
                state = MissionState.ROLLED_BACK
            elif status in ("BLOCKED", "NO_PATCH_POSSIBLE"):
                state = MissionState.BLOCKED
            else:
                state = MissionState.FAILED
            record.state = state
            record.result_status = status
            record.history.append(state)
            if technical is not None:
                record.technical_log.append(technical)
            return record

    def reject(self, run_id: str) -> Optional[_RunRecord]:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None or record.state != MissionState.AWAITING_AUTHORIZATION:
                return None
            record.state = MissionState.REFUSED
            record.history.append(MissionState.REFUSED)
            return record


# ------------------------------------------------------------------
# Résultat d'une opération de façade (status HTTP + payload).
# ------------------------------------------------------------------

@dataclass
class ApiResult:
    http_status: int
    payload: dict


def _bad_request(reason: str) -> ApiResult:
    """Fail-closed : entrée invalide -> 400, aucune écriture."""
    return ApiResult(400, {"error": "BAD_REQUEST", "reason": reason})


def _resolve_target_or_error(project: str) -> tuple[Optional[ProjectTarget], Optional[ApiResult]]:
    """
    Résout la cible via le MOTEUR (project_target.resolve_target). L'API ne
    fabrique jamais une cible : si la résolution échoue -> fail-closed.
    """
    if not isinstance(project, str) or not project.strip():
        return None, _bad_request("champ 'project' manquant ou vide")
    import os
    os.environ["MEMOLIBDEV_TARGET"] = project.strip()
    try:
        target = resolve_target()
    except ProjectTargetError as exc:
        return None, ApiResult(400, {"error": "INVALID_PROJECT", "reason": str(exc)})
    return target, None


# ------------------------------------------------------------------
# Façade : la LOGIQUE (testable sans socket). Chaque handler délègue
# intégralement à run_cli. Aucune autorité propre.
# ------------------------------------------------------------------

class ApiFacade:
    """
    Logique de façade pure vis-à-vis de la sécurité : elle ne fait que
    construire les entrées de run_cli et traduire la sortie en vue UI.

    `provider_factory` et `verify` sont injectables pour les tests (afin de
    ne dépendre ni d'Ollama ni d'un vrai apply). En production, un provider
    réel et un verify léger sont fournis par le lanceur.
    """

    def __init__(
        self,
        *,
        registry: Optional[RunRegistry] = None,
        provider_factory: Optional[Callable[[str], object]] = None,
        verify: Optional[Callable[[Path], tuple[bool, str]]] = None,
        run_cli_fn: Callable = run_cli,
        resolve_fn: Callable = _resolve_target_or_error,
        model: str = "qwen2.5-coder:7b",
        provider_timeout_s: float = 180.0,
    ) -> None:
        self.registry = registry or RunRegistry()
        self._provider_factory = provider_factory
        self._verify = verify or (lambda repo: (True, "verify léger (API)"))
        self._run_cli = run_cli_fn
        self._resolve = resolve_fn
        self._model = model
        self._provider_timeout_s = provider_timeout_s

    # -- helpers ----------------------------------------------------

    def _provider(self, model: str):
        if self._provider_factory is None:
            return None
        return self._provider_factory(model)

    @staticmethod
    def _technical(result: CliResult) -> Optional[dict]:
        report = getattr(result, "report", None)
        if report is not None and hasattr(report, "to_dict"):
            return report.to_dict()
        return None

    @staticmethod
    def _public_view(result: CliResult, *, mode: str, mission: str) -> tuple[dict, dict]:
        """Sépare le journal technique serveur de la vue consommée par le navigateur."""
        view = humanize_ui(result, mode=mode, mission=mission)
        technical = view.pop("technique", None)
        # V0.3 : exposer la PROPOSITION descriptive à l'UI (sans le reste du
        # journal technique). La proposition est produite par le Core (§4.7)
        # et transportée dans report.to_dict()["proposal"]. On la REMONTE
        # telle quelle dans la vue publique : elle est DESCRIPTIVE et ne
        # contient aucun secret (pas d'env/credential/token). Elle n'accorde
        # aucun pouvoir : can_approve reste gouverné par l'état serveur, et
        # l'application reste exclusivement D5.9. La façade ne FABRIQUE ni ne
        # RECALCULE la proposition : si le Core n'en a pas produit, c'est None.
        proposal = technical.get("proposal") if isinstance(technical, dict) else None
        view["proposal"] = proposal
        preview = {
            "fichier_concerne": technical.get("scope") if technical else None,
            "pourquoi": view["pourquoi"],
            "resultat_attendu": view["resultat"],
            # Transport additif pour l'aperçu « Agir/Proposer ».
            "proposal": proposal,
        }
        return view, preview

    @staticmethod
    def _response(run_id: str, record: _RunRecord, result: CliResult,
                  view: dict, preview: dict) -> ApiResult:
        return ApiResult(200, {
            "run_id": run_id,
            "status": result.status,
            "state": record.state,
            "can_approve": record.state == MissionState.AWAITING_AUTHORIZATION,
            "can_reject": record.state == MissionState.AWAITING_AUTHORIZATION,
            "preview": preview,
            "vue": view,
        })

    # -- /mission ---------------------------------------------------

    def handle_mission(self, body: dict) -> ApiResult:
        """
        POST /mission {project, mission, mode}.

        Délègue à run_cli. NE fournit NI action NI approbation : la chaîne
        s'arrête donc avant toute écriture (AWAIT_HUMAN) pour les modes qui
        pourraient écrire. Fail-closed sur project/mission/mode invalides.
        """
        if not isinstance(body, dict):
            return _bad_request("corps JSON invalide")

        mission = body.get("mission")
        mode = body.get("mode", "READ_ONLY")
        project = body.get("project")

        # Fail-closed : mission invalide.
        if not isinstance(mission, str) or not mission.strip():
            return _bad_request("champ 'mission' manquant ou vide")

        # Fail-closed : mode invalide (l'API ne devine pas un mode).
        if mode not in API_MODES:
            return _bad_request(f"mode invalide: {mode!r} (attendus: {list(API_MODES)})")

        # Fail-closed : projet invalide (résolu par le moteur, pas forgé).
        target, err = self._resolve(project)
        if err is not None:
            return err

        # /mission n'approuve jamais et ne clarifie pas en interactif :
        #   - input_fn renvoie "" => pas de devinette (clarification -> QUESTION) ;
        #   - approval_fn renvoie None => AUCUNE approbation fabriquée.
        def _no_input(_prompt: str) -> str:
            return ""

        def _no_approval(_prompt: str) -> Optional[HumanApproval]:
            return None

        run_id = self.registry.create(
            project=str(target.git_root), mission=mission.strip(), mode=mode,
        )
        result: CliResult = self._run_cli(
            mission=mission.strip(),
            target=target,
            mode=mode,
            model=self._model,
            approver=None,
            provider=self._provider(self._model),
            verify=self._verify,
            input_fn=_no_input,
            approval_fn=_no_approval,
            provider_timeout_s=self._provider_timeout_s,
        )
        technical = self._technical(result)
        record = self.registry.finish_analysis(
            run_id, mode=mode, status=result.status, technical=technical,
        )
        if record is None:
            return ApiResult(409, {"error": "INVALID_STATE",
                                   "reason": "transition d'analyse refusée"})
        view, preview = self._public_view(result, mode=mode, mission=mission.strip())
        return self._response(run_id, record, result, view, preview)

    # -- /approve ---------------------------------------------------

    def handle_approve(self, body: dict) -> ApiResult:
        """
        POST /approve {run_id, approver}.

        L'API NE FABRIQUE PAS d'autorisation : elle construit une
        HumanApproval(approved=True, approver=<nom saisi>) — comme
        _real_approval de la CLI — puis relance run_cli en SUPERVISED_APPLY.
        D5.8/D5.9 restent seuls juges.

        Fail-closed :
          - run_id absent/inconnu -> bloqué ;
          - approver absent/vide -> bloqué (pas d'approbation anonyme) ;
          - tout champ sensible du body (diff/path/sha/certificate/...) est
            IGNORÉ : l'API ne peut pas injecter d'autorité par le corps.
        """
        if not isinstance(body, dict):
            return _bad_request("corps JSON invalide")

        run_id = body.get("run_id")
        approver = body.get("approver")

        # Fail-closed : absence de run / run_id inconnu -> bloque.
        if not isinstance(run_id, str) or not run_id.strip():
            return ApiResult(400, {"error": "NO_RUN", "reason": "run_id manquant"})
        run_id = run_id.strip()
        record = self.registry.begin_approval(run_id)
        if record is None:
            known = self.registry.get(run_id)
            if known is None:
                return ApiResult(404, {"error": "UNKNOWN_RUN",
                                       "reason": f"run_id inconnu: {run_id}"})
            return ApiResult(409, {"error": "INVALID_STATE",
                                   "reason": f"approbation impossible depuis {known.state}"})

        # Fail-closed : approbation anonyme interdite.
        if not isinstance(approver, str) or not approver.strip():
            return ApiResult(400, {"error": "NO_APPROVER",
                                   "reason": "approver manquant : aucune "
                                             "approbation anonyme"})

        # NOTE SÉCURITÉ : on IGNORE délibérément tout champ sensible du body.
        # L'API ne peut pas fabriquer diff/path/SHA/certificat/autorisation.
        # Rien de ce qui suit ne lit body["diff"], body["path"], body["sha"],
        # body["certificate"] ou body["authorization"].

        # Reconstruit la cible depuis le run enregistré (jamais depuis le
        # body d'approbation) via le moteur.
        target, err = self._resolve(record.project)
        if err is not None:
            return err

        # Approbation issue UNIQUEMENT du nom saisi (comme _real_approval).
        # approval_fn est la SEULE source d'une HumanApproval ; run_cli la
        # transmet telle quelle à D5.8/D5.9.
        import datetime

        def _approval_from_name(_prompt: str) -> Optional[HumanApproval]:
            return HumanApproval(
                approved=True,
                approver=approver.strip(),
                approved_at=datetime.datetime.now().astimezone().isoformat(),
                authority_level=AuthorityLevel.L3_PROPOSE.value,
                # V0.4.1 : lier la décision humaine au binding de la
                # proposition PRÉSENTÉE (capturé du rapport serveur lors du
                # /mission). Jamais lu du body client. Si la ré-exécution
                # SUPERVISED_APPLY produit un diff différent (source dérivée,
                # patch altéré), le gate 4.8bis BLOQUE : nouvelle décision
                # humaine requise.
                proposal_id=record.proposal_id,
                expected_diff_sha256=record.diff_sha256,
            )

        def _no_input(_prompt: str) -> str:
            return ""

        result: CliResult = self._run_cli(
            mission=record.mission,
            target=target,
            mode="SUPERVISED_APPLY",        # l'apply passe par D5.8/D5.9
            model=self._model,
            approver=approver.strip(),
            provider=self._provider(self._model),
            verify=self._verify,
            input_fn=_no_input,
            approval_fn=_approval_from_name,
            provider_timeout_s=self._provider_timeout_s,
        )
        technical = self._technical(result)
        finished = self.registry.finish_execution(
            run_id, status=result.status, technical=technical,
        )
        if finished is None:
            return ApiResult(409, {"error": "INVALID_STATE",
                                   "reason": "transition d'exécution refusée"})
        view, preview = self._public_view(
            result, mode="SUPERVISED_APPLY", mission=record.mission,
        )
        return self._response(run_id, finished, result, view, preview)

    def handle_reject(self, body: dict) -> ApiResult:
        """POST /reject {run_id}: refus terminal, sans appeler le moteur."""
        if not isinstance(body, dict):
            return _bad_request("corps JSON invalide")
        run_id = body.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            return ApiResult(400, {"error": "NO_RUN", "reason": "run_id manquant"})
        record = self.registry.reject(run_id.strip())
        if record is None:
            known = self.registry.get(run_id.strip())
            if known is None:
                return ApiResult(404, {"error": "UNKNOWN_RUN",
                                       "reason": f"run_id inconnu: {run_id}"})
            return ApiResult(409, {"error": "INVALID_STATE",
                                   "reason": f"refus impossible depuis {known.state}"})
        return ApiResult(200, {
            "run_id": record.run_id,
            "state": record.state,
            "status": record.result_status,
            "can_approve": False,
            "can_reject": False,
        })


# ------------------------------------------------------------------
# Couche HTTP : traduit requête <-> ApiFacade. Aucune logique métier.
# ------------------------------------------------------------------

def make_handler(facade: ApiFacade, static_provider=None):
    """
    Fabrique un handler BaseHTTPRequestHandler lié à une façade.

    `static_provider` (optionnel) : callable `path -> (content_type, bytes)`
    ou `None`. S'il est None (DÉFAUT), le handler se comporte EXACTEMENT
    comme avant : seules les routes POST /mission et /approve existent, et
    tout GET renvoie 404. Ce paramètre est le SEUL point d'extension pour
    servir un front statique (web_mvp) ; il ne porte AUCUNE logique de
    sécurité (il ne peut que renvoyer des octets statiques). Supprimer le
    front = rappeler make_handler sans cet argument => Core identique.
    """

    class _Handler(BaseHTTPRequestHandler):
        server_version = "MemoLibDevApiFacade/1.0"

        def _send(self, result: ApiResult) -> None:
            data = json.dumps(result.payload).encode("utf-8")
            self.send_response(result.http_status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_static(self, content_type: str, body: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> tuple[Optional[dict], Optional[ApiResult]]:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length > 0 else b""
            if not raw:
                return {}, None
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                return None, _bad_request(f"JSON invalide: {exc}")
            if not isinstance(parsed, dict):
                return None, _bad_request("le corps doit être un objet JSON")
            return parsed, None

        def do_GET(self) -> None:  # noqa: N802 (API http.server)
            # Sans front injecté, AUCUN GET n'est servi (comportement
            # historique strict). Le front ne peut servir que du statique.
            if static_provider is None:
                self._send(ApiResult(404, {"error": "NOT_FOUND",
                                           "reason": f"route inconnue: {self.path}"}))
                return
            served = static_provider(self.path)
            if served is None:
                self._send(ApiResult(404, {"error": "NOT_FOUND",
                                           "reason": f"route inconnue: {self.path}"}))
                return
            content_type, body = served
            self._send_static(content_type, body)

        def do_POST(self) -> None:  # noqa: N802 (API http.server)
            body, err = self._read_json()
            if err is not None:
                self._send(err)
                return
            if self.path == "/mission":
                self._send(facade.handle_mission(body))
            elif self.path == "/approve":
                self._send(facade.handle_approve(body))
            elif self.path == "/reject":
                self._send(facade.handle_reject(body))
            else:
                self._send(ApiResult(404, {"error": "NOT_FOUND",
                                           "reason": f"route inconnue: {self.path}"}))

        def log_message(self, *_args) -> None:  # silence stdout
            return

    return _Handler


def serve(host: str = "127.0.0.1", port: int = 8765,
          facade: Optional[ApiFacade] = None,
          static_provider=None) -> None:
    """
    Lance le serveur local (127.0.0.1 par défaut). En production, injecter
    une façade avec un provider_factory réel. Bloquant.

    `static_provider` (optionnel) : si fourni (par web_mvp), sert un front
    statique sur GET. None (défaut) => aucun GET servi (Core identique).
    """
    facade = facade or ApiFacade()
    httpd = HTTPServer((host, port), make_handler(facade, static_provider))
    print(f"MemoLibDev API façade — http://{host}:{port} (local, mince)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
