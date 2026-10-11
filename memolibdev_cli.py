"""
MemoLibDev — CLI opérationnelle
================================

Point d'entrée en ligne de commande, branché EXCLUSIVEMENT sur le moteur
validé `agent_loop.run_from_mission(...)`. La CLI n'exécute AUCUNE logique
d'apply/git/production : elle orchestre les entrées (projet, mission,
mode, approbation) et délègue tout à la chaîne D5/D6 existante.

Modes (READ_ONLY par défaut) :
  READ_ONLY        : contexte + proposition (diff candidat). Aucune
                     écriture possible : la voie d'apply n'est pas prise.
  PROPOSE          : identique à READ_ONLY, formaté pour décision humaine.
  SANDBOX          : exécute la chaîne complète sur une COPIE du projet
                     (jamais la cible réelle) ; apply/verify/rollback y
                     opèrent sur la copie.
  SUPERVISED_APPLY : exécute la chaîne sur la cible réelle, UNIQUEMENT
                     après approbation humaine explicite saisie. La CLI
                     ne fabrique JAMAIS l'approbation.

Garde-fous :
  - jamais de second moteur : seul run_from_mission est appelé ;
  - jamais d'apply/git/commit/push/déploiement depuis la CLI ;
  - D5.8 (authorize) et D5.9 (controlled apply) restent obligatoires et
    inchangés ; SUPERVISED_APPLY passe par eux via run_from_mission ;
  - fail-closed : mission ambiguë -> QUESTION, pas de devinette ;
  - approbation absente -> AWAIT_HUMAN/BLOCK, aucune écriture.

Clarification interactive :
  Si le contexte ne permet pas de déterminer un périmètre fiable
  (aucun fichier pertinent, score trop faible, mission trop courte),
  la CLI pose UNE question et attend la réponse, puis enrichit la
  mission et reconstruit le contexte.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

from project_target import resolve_target, ProjectTarget, ProjectTargetError
from context.context_builder import build_mission_context
from coder_authorization import ActionDossier, HumanApproval, AuthorityLevel
from agent_loop import run_from_mission


DEFAULT_MODEL = "qwen2.5-coder:1.5b-base"
MODES = ("READ_ONLY", "PROPOSE", "SANDBOX", "SUPERVISED_APPLY")

# Seuils déterministes de clarification.
MIN_MISSION_WORDS = 3
MIN_TOP_SCORE = 4


def _safe(s: str) -> str:
    enc = (sys.stdout.encoding or "utf-8")
    try:
        return s.encode(enc, errors="replace").decode(enc, errors="replace")
    except Exception:
        return s.encode("ascii", errors="replace").decode("ascii")


def _git(root: Path, *a) -> str:
    return subprocess.run(["git", "-C", str(root), *a], text=True,
                          capture_output=True, encoding="utf-8",
                          errors="replace").stdout.strip()


@dataclass
class CliResult:
    status: str                 # OK | QUESTION | BLOCKED | AWAIT_HUMAN | APPLIED | ROLLED_BACK | ERROR
    message: str
    report: Optional[object] = None
    question: Optional[str] = None


# ----------------------------------------------------------------
# Clarification déterministe
# ----------------------------------------------------------------

def _needs_clarification(mission_text: str, target: ProjectTarget) -> Optional[str]:
    """
    Détermine, de façon déterministe, si la mission est trop ambiguë pour
    déterminer un périmètre fiable. Retourne la QUESTION à poser, ou None.
    N'écrit rien (lecture seule).
    """
    words = [w for w in mission_text.split() if len(w) > 2]
    if len(words) < MIN_MISSION_WORDS:
        return ("La mission est trop courte pour déterminer un périmètre. "
                "Peux-tu préciser le fichier, le symbole ou le comportement "
                "concerné ?")

    # Construction read-only d'un contexte sonde.
    ctx = build_mission_context("clarify-probe", mission_text, target,
                                max_files=8, max_context_chars=20000)
    if not ctx.relevant_files:
        return ("Je n'ai identifié aucun fichier pertinent pour cette "
                "mission. Peux-tu préciser le module, le chemin ou la "
                "fonctionnalité concernée ?")

    top = ctx.relevant_files[0].score
    if top < MIN_TOP_SCORE:
        candidates = ", ".join(rf.path for rf in ctx.relevant_files[:3])
        return ("La mission est ambiguë : plusieurs interprétations sont "
                f"possibles (candidats : {candidates}). "
                "Peux-tu préciser le fichier ou le comportement exact ?")
    return None


# ----------------------------------------------------------------
# Cœur CLI (injectable pour les tests)
# ----------------------------------------------------------------

def run_cli(
    *,
    mission: str,
    target: ProjectTarget,
    mode: str,
    model: str,
    approver: Optional[str],
    provider,                                   # objet AIProvider (ou None)
    verify: Callable[[Path], tuple[bool, str]],
    input_fn: Callable[[str], str],             # pour la clarification
    approval_fn: Callable[[str], Optional[HumanApproval]],  # pour l'apply
    provider_timeout_s: Optional[float],
    _clarify_rounds: int = 0,
) -> CliResult:
    """
    Orchestration CLI. Ne contient AUCUNE logique d'apply : délègue à
    run_from_mission. READ_ONLY/PROPOSE ne prennent jamais la voie d'apply.
    """
    if mode not in MODES:
        return CliResult("ERROR", f"mode inconnu: {mode}")

    # 0. Aiguillage : mission de type "document" -> rediriger vers le GUI docs
    # Regle : ne refuser que si un VERBE de production de document est present
    # ET qu'aucun VERBE de code n'est present.
    import re as _re
    _ml = mission.lower()

    _verbes_doc = ("genere", "génère", "produis", "produit", "redige", "rédige",
                   "cree un rapport", "crée un rapport", "fais un rapport",
                   "fais-moi un rapport", "etablis", "établis")
    _verbes_code = ("ajoute", "modifie", "corrige", "refactorise", "documente",
                    "code", "module", "fonction", "classe", "test",
                    "importe", "exporte", "cree une page", "crée une page",
                    "bug", "fix", "implement", "implémente")

    _a_verbe_doc = any(v in _ml for v in _verbes_doc)
    _a_verbe_code = any(v in _ml for v in _verbes_code)

    if _a_verbe_doc and not _a_verbe_code:
        return CliResult(
            "WRONG_TOOL",
            "[WRONG_TOOL] Cette mission semble demander la production d'un document. "
            "Utilisez plutot memolibdev_doc_gui.py ou create_doc.py --type <facture|devis|...>. "
            "Le CLI est reserve a l'analyse et la modification de code.",
        )

    # 1. Clarification (fail-closed : on ne devine pas).
    question = _needs_clarification(mission, target)
    if question is not None:
        if _clarify_rounds >= 3:
            return CliResult("BLOCKED",
                             "Mission toujours ambiguë après clarifications.")
        answer = input_fn(_safe(question) + "\n> ")
        if not answer or not answer.strip():
            return CliResult("QUESTION", "En attente de clarification.",
                             question=question)
        enriched = f"{mission.strip()} — précision: {answer.strip()}"
        return run_cli(
            mission=enriched, target=target, mode=mode, model=model,
            approver=approver, provider=provider, verify=verify,
            input_fn=input_fn, approval_fn=approval_fn,
            provider_timeout_s=provider_timeout_s,
            _clarify_rounds=_clarify_rounds + 1,
        )

    # 2. READ_ONLY / PROPOSE : proposition seulement, JAMAIS d'apply.
    #    On n'appelle pas la voie d'apply de run_from_mission : on passe
    #    human_approval=None => la chaîne s'arrête à AWAIT_HUMAN avant
    #    toute écriture. En plus, en READ_ONLY/PROPOSE on ne fournit
    #    jamais d'action/approval.
    if mode in ("READ_ONLY", "PROPOSE"):
        # READ_ONLY : analyse pure via context (pas de planner LLM).
        # PROPOSE   : planner LLM -> REPLACE -> diff propose.
        _provider_for_run = None if mode == "READ_ONLY" else provider
        res = run_from_mission(
            f"CLI-{mode}", mission, target, None, verify,
            action=None, human_approval=None,     # <= pas d'apply possible
            provider=_provider_for_run, provider_timeout_s=provider_timeout_s,
        )
        rep = res.report

        # Affichage enrichi en mode PROPOSE (lecture seule, aucun apply).
        if mode == "PROPOSE":
            proposal = getattr(rep, "proposal", None)
            if proposal is not None:
                print()
                print("=" * 60)
                print(" PROPOSITION")
                print("=" * 60)
                if getattr(proposal, "summary", None):
                    print(f"Resume    : {proposal.summary}")
                if getattr(proposal, "scope", None):
                    print(f"Fichier   : {proposal.scope}")
                if getattr(proposal, "confidence", None):
                    print(f"Confiance : {proposal.confidence}")
                if getattr(proposal, "risk", None):
                    print(f"Risque    : {proposal.risk}")
                if getattr(proposal, "reason", None):
                    print(f"Raison    : {proposal.reason}")

                files = getattr(proposal, "files", ()) or ()
                if files:
                    print(f"Fichiers  : {len(files)} concerne(s)")
                    for f in files:
                        p = getattr(f, "path", None)
                        sha = getattr(f, "sha_before", None)
                        if p:
                            print(f"  - {p}  (sha_before={sha or 'N/A'})")

                diff = getattr(proposal, "diff_preview", None)
                if diff:
                    print()
                    print("--- DIFF PROPOSE ---")
                    print(diff)
                    print("--- FIN DIFF ---")
                else:
                    print()
                    print("(aucun diff_preview disponible)")

                print()
                print("Aucune modification effectuee.")
                print("=" * 60)

        return CliResult(
            status=rep.final_state,                # AWAIT_HUMAN ou BLOCKED
            message=f"[{mode}] {rep.reason}",
            report=rep,
        )

    # 3. SANDBOX : copie du projet, apply sur la COPIE (jamais la cible).
    if mode == "SANDBOX":
        return _run_sandbox(mission, target, model, approver, provider,
                            verify, approval_fn, provider_timeout_s)

    # 4. SUPERVISED_APPLY : cible réelle, approbation humaine OBLIGATOIRE,
    #    LIÉE à la proposition exacte (V0.4.2/V0.4.3 : binding obligatoire).
    if mode == "SUPERVISED_APPLY":
        # --- Phase PROPOSER : produire la proposition (aucune écriture) ---
        # human_approval=None => la chaîne s'arrête en AWAIT_HUMAN APRÈS §4.7,
        # exposant proposal_id + diff_sha256 (octets exacts du diff candidat).
        probe = run_from_mission(
            "CLI-SUPERVISED_APPLY-propose", mission, target, None, verify,
            action=None, human_approval=None,
            provider=provider, provider_timeout_s=provider_timeout_s,
        )
        prep = probe.report
        if prep.final_state != "AWAIT_HUMAN" or prep.proposal is None:
            # BLOCKED / NO_PATCH_POSSIBLE / QUESTION : rien à approuver.
            return CliResult(status=prep.final_state,
                             message=f"[SUPERVISED_APPLY/propose] {prep.reason}",
                             report=prep)
        proposal = prep.proposal
        target_file = proposal.scope

        # --- Présentation humaine : identité + empreinte du diff proposé ---
        prompt = (
            f"SUPERVISED_APPLY sur {target.git_root}\n"
            f"  proposition : {proposal.proposal_id}\n"
            f"  fichier     : {target_file}\n"
            f"  diff_sha256 : {proposal.diff_sha256}\n"
            f"  confiance   : {proposal.confidence}\n"
            f"Approuver CETTE proposition ? (nom de l'approbateur)")
        approval = approval_fn(prompt)
        if approval is None or approval.approved is not True \
                or not approval.approver.strip():
            return CliResult("AWAIT_HUMAN",
                             "Approbation humaine absente/incomplète : "
                             "aucun apply. (D5.8/D5.9 + binding exigent une "
                             "approbation réelle liée à la proposition.)")

        # --- Liaison de la décision humaine à LA proposition présentée ---
        # bind_approval ne fabrique rien : il attache proposal_id +
        # expected_diff_sha256 à l'approbation humaine réelle. Le gate
        # §4.8bis revérifiera le hash des octets exacts du diff produit.
        from coder_authorization import bind_approval
        try:
            bound = bind_approval(approval, proposal)
        except ValueError as exc:
            return CliResult("BLOCKED",
                             f"[SUPERVISED_APPLY] liaison impossible : {exc}")

        action = ActionDossier(
            action_id="CLI-APPLY-001", action_type="PROPOSE_CODE_PATCH",
            target_path=target_file, risk="MEDIUM",
            reversibility="REVERSIBLE_SANDBOX")

        # --- Phase APPLIQUER : binding vérifié puis D5.9 (seul à écrire) ---
        res = run_from_mission(
            "CLI-SUPERVISED_APPLY", mission, target, None, verify,
            action=action, human_approval=bound,
            provider=provider, provider_timeout_s=provider_timeout_s,
        )
        rep = res.report
        return CliResult(status=rep.final_state,
                         message=f"[SUPERVISED_APPLY] {rep.reason}",
                         report=rep)

    return CliResult("ERROR", f"mode non géré: {mode}")


def _run_sandbox(mission, target, model, approver, provider, verify,
                 approval_fn, provider_timeout_s) -> CliResult:
    """
    Copie le dépôt cible dans un répertoire temporaire et exécute la
    chaîne sur la COPIE. La cible réelle n'est jamais touchée.
    """
    src = target.git_root
    tmp = Path(tempfile.mkdtemp(prefix="memolibdev-sandbox-")).resolve()
    dst = tmp / src.name
    try:
        shutil.copytree(src, dst)
        # Re-résoudre la cible sur la copie (HEAD/fingerprint recalculés).
        head = _git(dst, "rev-parse", "HEAD")
        head_short = _git(dst, "rev-parse", "--short", "HEAD")
        branch = _git(dst, "rev-parse", "--abbrev-ref", "HEAD")
        import hashlib
        fp = hashlib.sha256(f"{dst}|{branch}|{head}".encode()).hexdigest()[:16]
        sandbox_target = ProjectTarget(
            path=dst, git_root=dst, head=head_short, head_full=head,
            branch=branch, fingerprint=fp, env_var=target.env_var)

        # --- Phase PROPOSER sur la COPIE (aucune écriture) ---
        probe = run_from_mission(
            "CLI-SANDBOX-propose", mission, sandbox_target, None, verify,
            action=None, human_approval=None,
            provider=provider, provider_timeout_s=provider_timeout_s,
        )
        prep = probe.report
        if prep.final_state != "AWAIT_HUMAN" or prep.proposal is None:
            return CliResult(status=prep.final_state,
                             message=f"[SANDBOX copie={dst}/propose] {prep.reason}",
                             report=prep)
        proposal = prep.proposal
        target_file = proposal.scope

        approval = approval_fn(
            f"SANDBOX (copie) — proposition {proposal.proposal_id} "
            f"fichier={target_file} diff_sha256={proposal.diff_sha256}\n"
            f"Approuver CETTE proposition sur la copie ? (nom de l'approbateur)")
        if approval is None or approval.approved is not True:
            return CliResult("AWAIT_HUMAN",
                             "Approbation absente : aucun apply même en "
                             "sandbox.")

        # Liaison obligatoire de l'approbation à la proposition de la copie.
        from coder_authorization import bind_approval
        try:
            bound = bind_approval(approval, proposal)
        except ValueError as exc:
            return CliResult("BLOCKED",
                             f"[SANDBOX] liaison impossible : {exc}")

        action = ActionDossier(
            action_id="CLI-SANDBOX-001", action_type="PROPOSE_CODE_PATCH",
            target_path=target_file, risk="MEDIUM",
            reversibility="REVERSIBLE_SANDBOX")
        res = run_from_mission(
            "CLI-SANDBOX", mission, sandbox_target, None, verify,
            action=action, human_approval=bound,
            provider=provider, provider_timeout_s=provider_timeout_s,
        )
        rep = res.report
        return CliResult(
            status=rep.final_state,
            message=f"[SANDBOX copie={dst}] {rep.reason}",
            report=rep)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------
# Entrée réelle (I/O console)
# ----------------------------------------------------------------

def _real_input(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def _real_approval(prompt: str) -> Optional[HumanApproval]:
    """
    Construit une HumanApproval UNIQUEMENT à partir d'une saisie humaine
    réelle. Jamais fabriquée. Un refus/vide -> None.
    """
    print(_safe(prompt))
    name = _real_input("approbateur (vide = refuser) > ").strip()
    if not name:
        return None
    confirm = _real_input("confirmer l'application ? (oui/non) > ").strip().lower()
    if confirm not in ("oui", "o", "yes", "y"):
        return None
    import datetime
    return HumanApproval(
        approved=True, approver=name,
        approved_at=datetime.datetime.now().astimezone().isoformat(),
        authority_level=AuthorityLevel.L3_PROPOSE.value)


def _make_provider(model: str):
    """Instancie l'OllamaProvider réel (le seul provider de prod)."""
    from llm.ollama_provider import OllamaProvider
    return OllamaProvider(model=model, http_timeout=180.0)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="memolibdev",
        description="Agent de développement contrôlé (fail-closed).")
    p.add_argument("--project", help="Racine du dépôt cible "
                   "(sinon MEMOLIBDEV_TARGET).")
    p.add_argument("--mission", required=True, help="Mission en langage naturel.")
    p.add_argument("--mode", choices=MODES, default="READ_ONLY",
                   help="Mode d'exécution (défaut READ_ONLY).")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Modèle Ollama.")
    p.add_argument("--approver", help="Nom de l'approbateur (apply/sandbox).")
    p.add_argument("--timeout", type=float, default=180.0,
                   help="Timeout provider (s).")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    # Résolution cible : --project prime, sinon MEMOLIBDEV_TARGET.
    if args.project:
        os.environ["MEMOLIBDEV_TARGET"] = args.project
    try:
        target = resolve_target()
    except ProjectTargetError as e:
        print(_safe(f"[STOP] Cible non résolue : {e}"))
        return 2

    print("=" * 60)
    print(f"MemoLibDev CLI — mode {args.mode} (READ_ONLY par défaut)")
    print(f"Projet : {target.git_root}  (HEAD {target.head})")
    print(f"Modèle : {args.model}")
    print("=" * 60)

    provider = None
    if args.mode != "READ_ONLY":
        provider = _make_provider(args.model)
        if not provider.available:
            print(_safe(f"[STOP] Ollama/modèle {args.model} indisponible."))
            return 3

    def verify(repo: Path) -> tuple[bool, str]:
        # VERIFY reel : analyse tous les fichiers modifies ou nouveaux.
        import subprocess as _sp
        from verify_project import verify_project
        try:
            r = _sp.run(
                ["git", "status", "--porcelain", "-z"],
                cwd=str(repo), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=10,
            )
            if r.returncode != 0:
                return (False, f"verify: git status a echoue: {r.stderr.strip()}")
            changed = [
                record[3:]
                for record in r.stdout.split("\0")
                if len(record) >= 4 and record[3:]
            ]
        except (OSError, _sp.SubprocessError) as exc:
            return (False, f"verify: git status impossible: {exc}")
        if not changed:
            return (False, "verify: aucun fichier modifie")
        return verify_project(repo, changed, run_tests=True)

    result = run_cli(
        mission=args.mission, target=target, mode=args.mode, model=args.model,
        approver=args.approver, provider=provider, verify=verify,
        input_fn=_real_input, approval_fn=_real_approval,
        provider_timeout_s=args.timeout)

    print("\n" + "-" * 60)
    print(f"STATUT : {result.status}")
    print(_safe(result.message))
    if result.report is not None:
        print(f"commit={result.report.committed} push={result.report.pushed}")
    print("-" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
