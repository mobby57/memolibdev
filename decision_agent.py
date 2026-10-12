from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import sys
import urllib.request

from decision_selector import select_relevant_files
from usage_metering import build_and_record
from project_target import resolve_target, ProjectTargetError


V3 = Path(__file__).resolve().parent

# --- Cible projet : resolution LAZY (evite sys.exit au module-level) ---
# Sans MEMOLIBDEV_TARGET, l'import reste possible ; l'erreur ne survient
# qu'a la premiere utilisation reelle de TARGET ou MEMOLIB (fail-closed).
_TARGET_CACHE = None


def _ensure_target():
    global _TARGET_CACHE
    if _TARGET_CACHE is not None:
        return _TARGET_CACHE
    try:
        _TARGET_CACHE = resolve_target()
    except ProjectTargetError as exc:
        print(f"[TARGET][ERROR] {exc}", file=sys.stderr)
        raise RuntimeError(str(exc)) from exc
    return _TARGET_CACHE


class _TargetProxy:
    """Resout le target au premier acces (lazy)."""
    def __getattr__(self, name):
        return getattr(_ensure_target(), name)
    def __repr__(self):
        return f"<TargetProxy resolved={_TARGET_CACHE is not None}>"


class _MemolibProxy:
    """Resout MEMOLIB (TARGET.path) au premier acces (lazy)."""
    def _p(self):
        return _ensure_target().path
    def __truediv__(self, other):
        return self._p() / other
    def __rtruediv__(self, other):
        return other / self._p()
    def __fspath__(self):
        return str(self._p())
    def __getattr__(self, name):
        return getattr(self._p(), name)
    def __str__(self):
        return str(self._p())
    def __repr__(self):
        return "<MemolibProxy>"


TARGET = _TargetProxy()
MEMOLIB = _MemolibProxy()

REPORTS = V3 / "reports"

MODEL = "qwen2.5-coder:7b"
OLLAMA_URL = "http://localhost:11434/api/generate"

REPORTS.mkdir(parents=True, exist_ok=True)


def safe_relative_path(path: Path) -> str:
    return str(path.relative_to(MEMOLIB)).replace("\\", "/")


def inspect_repository() -> list[dict]:
    """
    Inspection READ-ONLY robuste du dépôt MemoLib.

    Ne traverse jamais les junctions, symlinks ou autres reparse points.
    Les erreurs filesystem sont enregistrées au lieu de faire planter
    l'agent.
    """

    results = []
    inspection_issues = []

    allowed_extensions = {
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".json",
        ".md",
        ".py",
    }

    ignored_parts = {
        ".git",
        "node_modules",
        ".next",
        "dist",
        "build",
    }

    def walk(directory: Path) -> None:
        try:
            entries = list(directory.iterdir())
        except Exception as exc:
            inspection_issues.append({
                "path": safe_relative_path(directory),
                "type": "directory_access_error",
                "error": str(exc),
            })
            return

        for path in entries:
            try:
                if path.name in ignored_parts:
                    continue

                if path.is_dir():
                    try:
                        if path.is_symlink():
                            inspection_issues.append({
                                "path": safe_relative_path(path),
                                "type": "symlink_skipped",
                            })
                            continue

                        attributes = path.stat().st_file_attributes

                        if attributes & 0x400:
                            inspection_issues.append({
                                "path": safe_relative_path(path),
                                "type": "reparse_point_skipped",
                            })
                            continue

                    except (OSError, AttributeError) as exc:
                        inspection_issues.append({
                            "path": safe_relative_path(path),
                            "type": "reparse_check_error",
                            "error": str(exc),
                        })
                        continue

                    walk(path)
                    continue

                if not path.is_file():
                    continue

                if path.suffix.lower() not in allowed_extensions:
                    continue

                relative = safe_relative_path(path)

                content = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

                results.append({
                    "path": relative,
                    "size": len(content),
                    "content": content[:12000],
                })

            except Exception as exc:
                inspection_issues.append({
                    "path": safe_relative_path(path),
                    "type": "entry_access_error",
                    "error": str(exc),
                })

    walk(MEMOLIB)

    results.append({
        "_inspection_metadata": True,
        "inspection_issues": inspection_issues,
        "files_count": len(results),
    })

    return results


def build_context(files: list[dict]) -> str:
    """
    Construit le contexte LLM à partir des fichiers inspectés.

    Les métadonnées d'inspection ne sont jamais envoyées comme fichiers.
    """

    parts = []

    for item in files:
        if item.get("_inspection_metadata"):
            continue

        path = item.get("path")
        content = item.get("content", "")

        if not path:
            continue

        parts.append(
            f"""
===== FICHIER : {path} =====

{content}
"""
        )

    return "\n".join(parts)


def ask_ollama(prompt: str) -> tuple[str, dict]:

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "num_predict": 1024,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST",
    )

    started = datetime.now()

    with urllib.request.urlopen(
        request,
        timeout=240
    ) as response:

        data = json.loads(
            response.read().decode("utf-8")
        )

    elapsed = (
        datetime.now() - started
    ).total_seconds()

    answer = data.get(
        "response",
        ""
    )

    done_reason = data.get(
        "done_reason"
    )

    generation_complete = (
        done_reason != "length"
    )

    metadata = {
        "elapsed_seconds": elapsed,
        "model": MODEL,
        "done": data.get("done"),
        "done_reason": done_reason,
        "generation_complete": generation_complete,
        "generation_truncated": not generation_complete,
        "eval_count": data.get("eval_count"),
        "prompt_eval_count": data.get("prompt_eval_count"),
        "response_chars": len(answer),
    }

    return answer, metadata


def build_prompt(
    request_text: str,
    context: str,
) -> str:

    return f"""
Tu es le Decision Agent de MemoLibDev.

Tu NE MODIFIES JAMAIS le dépôt.

Tu dois uniquement analyser la demande et produire
un PLAN DE TRAVAIL contrôlé.

DEMANDE UTILISATEUR :
{request_text}

CONTEXTE DU DÉPÔT :
{context}

RÈGLES ABSOLUES :

1. Ne cite que des fichiers réellement présents dans le contexte.
2. N'invente aucun fichier.
3. Ne prétends pas avoir inspecté un fichier absent.
4. Ne produis aucun patch.
5. Ne produis aucun code de remplacement.
6. Ne demande jamais de git commit.
7. Ne demande jamais de git push.
8. Ne demande jamais de git pull.
9. Si les preuves sont insuffisantes, indique-le.
10. Toute modification future devra être soumise à validation humaine.

Retourne UNIQUEMENT un JSON valide avec cette structure :

{{
  "status": "PLAN_PROPOSE",
  "summary": "",
  "objective": "",
  "files_inspected": [],
  "files_relevant": [],
  "evidence": [],
  "proposed_steps": [],
  "risks": [],
  "tests_required": [],
  "human_validation_required": true
}}

Statuts autorisés :

PLAN_PROPOSE
INSUFFICIENT_EVIDENCE
NEEDS_REVIEW
"""


def validate_plan(
    plan: dict,
    selected_files: set[str],
) -> dict:
    """
    Validation anti-hallucination (option A — 5F.2).

    Les fichiers cités par le modèle doivent appartenir à l'ensemble
    des fichiers RÉELLEMENT ENVOYÉS dans le contexte (sélection
    déterministe), et non à l'ensemble plus large des fichiers
    inspectés. C'est volontairement plus strict : le modèle ne peut
    pas citer un fichier qu'il n'a jamais vu.
    """

    cited = []

    def collect_path(value) -> None:
        """
        Extrait un chemin de fichier qu'il soit fourni comme chaîne
        brute OU comme objet {"file": ...} / {"path": ...}.

        Le modèle renvoie fréquemment des objets structurés plutôt
        que de simples chaînes ; ignorer ces objets viderait le
        garde-fou anti-hallucination de toute substance.
        """

        if isinstance(value, str):
            cited.append(value.replace("\\", "/"))
            return

        if isinstance(value, dict):
            raw = value.get("file") or value.get("path")

            if isinstance(raw, str):
                cited.append(raw.replace("\\", "/"))

    for field in (
        "files_inspected",
        "files_relevant",
    ):

        values = plan.get(field, [])

        if isinstance(values, list):

            for value in values:
                collect_path(value)

    unknown = sorted(
        set(cited) - selected_files
    )

    if unknown:

        return {
            "verdict": "REJECT",
            "reason": "Le plan cite des fichiers hors du contexte sélectionné.",
            "unknown_files": unknown,
        }

    if plan.get(
        "human_validation_required"
    ) is not True:

        return {
            "verdict": "REJECT",
            "reason": "La validation humaine obligatoire est absente.",
            "unknown_files": [],
        }

    if plan.get("status") not in {
        "PLAN_PROPOSE",
        "INSUFFICIENT_EVIDENCE",
        "NEEDS_REVIEW",
    }:

        return {
            "verdict": "REJECT",
            "reason": "Statut de plan non autorisé.",
            "unknown_files": [],
        }

    return {
        "verdict": "ACCEPTABLE",
        "reason": "Plan structurellement valide.",
        "unknown_files": [],
    }


def main() -> int:
    print("=== CIBLE PROJET ===")
    print(f"Target      : {TARGET.path}")
    print(f"Git root    : {TARGET.git_root}")
    print(f"Branch      : {TARGET.branch}")
    print(f"HEAD        : {TARGET.head}")
    print(f"Fingerprint : {TARGET.fingerprint}")
    print()

    if len(sys.argv) < 2:

        print(
            'Usage : python decision_agent.py "demande"'
        )

        return 1

    request_text = " ".join(
        sys.argv[1:]
    )

    print("=" * 70)
    print("MEMOLIBDEV — DECISION AGENT 5F")
    print("=" * 70)
    print()

    print("[0] CIBLE PROJET (lecture seule)")
    print(TARGET.describe())
    print()

    print("[1] INSPECTION READ-ONLY")

    files = inspect_repository()

    print(
        f"Fichiers inspectés : {len(files)}"
    )

    print()
    print("[1b] SÉLECTION DÉTERMINISTE (5F.2)")

    selection = select_relevant_files(
        files,
        request_text,
    )

    selected_items = selection["selected"]

    print(
        f"Candidats scorés   : {selection['candidate_count']}"
    )
    print(
        f"Fichiers retenus   : {len(selected_items)}"
        f" (primary={selection['primary_count']},"
        f" secondary={selection['secondary_count']})"
    )
    print(
        f"Contexte           : {selection['context_chars']} caractères"
        f" (~{selection['context_estimated_tokens']} tokens)"
    )

    for item in selected_items:
        print(
            f"  [{item['score']:>4}] {item['category']:<9} {item['path']}"
        )

    context = build_context(selected_items)

    print()
    print(
        f"Contexte construit : {len(context)} caractères"
    )

    print()
    print("[2] ANALYSE OLLAMA")

    prompt = build_prompt(
        request_text,
        context,
    )

    try:

        answer, metadata = ask_ollama(
            prompt
        )

    except Exception as exc:

        print(
            "ERREUR Ollama :",
            exc
        )

        return 1

    print(
        "Temps :",
        metadata["elapsed_seconds"],
        "s"
    )

    print(
        "Réponse :",
        len(answer),
        "caractères"
    )

    print()
    print("[3] PARSING DU PLAN")

    try:

        plan = json.loads(answer)

    except Exception as exc:

        print(
            "ERREUR : réponse JSON invalide"
        )

        print(exc)

        return 1

    selected_paths = {
        item["path"].replace("\\", "/")
        for item in selected_items
    }

    validation = validate_plan(
        plan,
        selected_paths,
    )

    if metadata["generation_truncated"]:

        validation["verdict"] = "REVIEW"

        validation["reason"] = (
            "Réponse Ollama tronquée."
        )

    selection_trace = {
        "candidate_count": selection["candidate_count"],
        "selected_count": len(selected_items),
        "primary_count": selection["primary_count"],
        "secondary_count": selection["secondary_count"],
        "context_chars": selection["context_chars"],
        "context_estimated_tokens": selection["context_estimated_tokens"],
        "max_context_chars": selection["max_context_chars"],
        "request_terms": selection["request_terms"],
        "selected_files": [
            {
                "path": item["path"],
                "category": item["category"],
                "score": item["score"],
                "size": item["size"],
                "reasons": item["reasons"],
            }
            for item in selected_items
        ],
    }

    operation = build_and_record(
        request=request_text,
        model=MODEL,
        selection=selection_trace,
        metadata=metadata,
        validation=validation,
        plan=plan,
        operation_type="DECISION",
        agent="decision_agent",
    )

    report = {
        "created_at": datetime.now().isoformat(),
        "request": request_text,
        "model": MODEL,
        "metadata": metadata,
        "selection": selection_trace,
        "plan": plan,
        "validation": validation,
        "operation": operation,
        "repository_modified": False,
        "human_validation_required": True,
    }

    timestamp = datetime.now().strftime(
        "%Y%m%d-%H%M%S"
    )

    output = (
        REPORTS
        / f"decision-5f-{timestamp}.json"
    )

    output.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print("[4] VALIDATION")

    print(
        json.dumps(
            validation,
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print("[5] PLAN")

    print(
        json.dumps(
            plan,
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print("[6A] USAGE METERING")

    _usage = operation["usage"]

    print(
        f"Opération          : {operation['operation_type']}"
        f" ({operation['status']})"
    )
    print(
        f"ID                 : {operation['id']}"
    )
    print(
        f"Tokens (prompt/out): {_usage['prompt_tokens']}"
        f" / {_usage['output_tokens']}"
        f" (total {_usage['total_tokens']})"
    )
    print(
        f"Fichiers sélection : {_usage['selected_files']}"
        f" / {_usage['candidate_files']} candidats"
    )
    print(
        f"Durée              : {_usage['duration_seconds']:.2f} s"
    )
    print(
        "Crédits            : non calculés (6A = mesure seule,"
        " pas de billing)"
    )

    print()
    print("Rapport :", output)
    print()
    print("MEMOLIB N'A PAS ÉTÉ MODIFIÉ.")
    print("AUCUN PATCH.")
    print("AUCUN COMMIT.")
    print("AUCUN PUSH.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

