"""
MemoLibDev — 5G : Controlled Coder
==================================

Rôle : à partir d'un PLAN VALIDÉ du Decision Agent (rapport
decision-5f-*.json), générer un UNIFIED DIFF pour les fichiers
RÉELLEMENT sélectionnés — et RIEN D'AUTRE.

Garanties de sûreté (non négociables) :

  1. MemoLib n'est JAMAIS modifié. On lit les fichiers en read-only
     et on produit un .diff. Aucune écriture dans le dépôt réel.
  2. Garde-fou ÉCRITURE : le patch ne peut toucher QUE les fichiers
     présents dans la sélection du plan. Tout chemin hors sélection
     => REJET du patch (équivalent écriture du garde-fou
     anti-hallucination du Decision Agent).
  3. Le patch est vérifié par `git apply --check` dans un SANDBOX
     temporaire (copie des fichiers ciblés), jamais sur MemoLib.
  4. On refuse d'opérer sur un plan dont la validation == REJECT.
  5. Aucun commit, aucun push.

Metering : réutilise le contrat 6A (operation_type="CODE").
"""

from __future__ import annotations

from pathlib import Path

from coder_authorization import (
    ActionDossier,
    AuthorityLevel,
    CoderAuthorization,
    HumanApproval,
    authorization_to_dict,
    validate_authorization,
)
from project_target import resolve_target
from datetime import datetime
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from usage_metering import build_and_record
from project_target import resolve_target, ProjectTargetError


V3 = Path(__file__).resolve().parent

# Cible projet résolue via identité Git obligatoire (pas de fallback).
# NB : ceci NE DONNE AUCUNE permission d'écriture nouvelle. safe_target()
# reste l'unique barrière de confinement, et le Coder ne fait toujours
# que PRODUIRE un .diff (jamais d'application sur la cible).
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
PATCHES = V3 / "patches"

# 5F.3.6 — certificat d'autorisation humaine.
# Le Coder refuse de générer un patch tant qu'il n'existe
# pas une autorisation AUTHORIZED liée à la cible exacte.
AUTHORIZATION_REPORT = REPORTS / "coder-authorization.json"

MODEL = "qwen2.5-coder:7b"
OLLAMA_URL = "http://localhost:11434/api/generate"

# Pour la GÉNÉRATION de patch, on borne le nombre de fichiers envoyés
# au modèle. Les fichiers du plan sont déjà triés par score décroissant
# par le Decision Agent : on garde les plus pertinents. Le garde-fou
# écriture reste calé sur CES fichiers (ceux réellement envoyés).
MAX_CODER_FILES = 4
MAX_CODER_CONTEXT_CHARS = 24000

REPORTS.mkdir(parents=True, exist_ok=True)
PATCHES.mkdir(parents=True, exist_ok=True)


# ============================================================
# 1. CHARGEMENT DU PLAN VALIDÉ
# ============================================================

def load_latest_decision_report() -> Path:
    candidates = sorted(
        REPORTS.glob("decision-5f-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not candidates:
        raise FileNotFoundError(
            "Aucun rapport decision-5f-*.json dans reports/"
        )

    return candidates[0]


def load_coder_authorization(path: Path = AUTHORIZATION_REPORT) -> CoderAuthorization:
    """
    Charge le certificat d'autorisation 5F.3.6.

    Fail closed :
      - fichier absent
      - JSON invalide
      - status différent de AUTHORIZED
      - structure incomplète

    Aucun fallback automatique n'est autorisé.
    """

    if not path.is_file():
        raise RuntimeError(
            "AUTORISATION_ABSENTE: "
            f"{path}"
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"AUTORISATION_JSON_INVALIDE: {exc}"
        ) from exc

    target_data = data.get("target")
    action_data = data.get("action")
    approval_data = data.get("human_approval")

    if not isinstance(target_data, dict):
        raise RuntimeError("AUTORISATION_TARGET_ABSENT")

    if not isinstance(action_data, dict):
        raise RuntimeError("AUTORISATION_ACTION_ABSENTE")

    if not isinstance(approval_data, dict):
        raise RuntimeError("AUTORISATION_HUMAN_APPROVAL_ABSENTE")

    try:
        authorization = CoderAuthorization(
            path=str(data["path"]),
            target=__import__(
                "coder_authorization",
                fromlist=["AuthorizationTarget"],
            ).AuthorizationTarget(
                git_root=str(target_data["git_root"]),
                head=str(target_data["head"]),
                repository_fingerprint=str(
                    target_data["repository_fingerprint"]
                ),
            ),
            evidence_status=str(data["evidence_status"]),
            evidence_sha256=str(data["evidence_sha256"]),
            provenance_status=str(data["provenance_status"]),
            provenance_source_path=data.get(
                "provenance_source_path"
            ),
            provenance_resolved_path=data.get(
                "provenance_resolved_path"
            ),
            action=ActionDossier(
                action_id=str(action_data["action_id"]),
                action_type=str(action_data["action_type"]),
                target_path=str(action_data["target_path"]),
                risk=str(action_data["risk"]),
                reversibility=str(action_data["reversibility"]),
            ),
            human_approval=HumanApproval(
                approved=bool(approval_data["approved"]),
                approver=str(approval_data["approver"]),
                approved_at=str(approval_data["approved_at"]),
                authority_level=str(
                    approval_data["authority_level"]
                ),
            ),
            human_validation_required=bool(
                data["human_validation_required"]
            ),
            status=str(data["status"]),
            reason=str(data["reason"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"AUTORISATION_STRUCTURE_INVALIDE: {exc}"
        ) from exc

    return authorization


def enforce_coder_authorization(
    authorization: CoderAuthorization,
    target,
    allowed_paths: list[str],
) -> dict:
    """
    Barrière d'autorité du Controlled Coder.

    Cette fonction doit réussir AVANT tout appel au modèle Coder.
    """

    if authorization.status != "AUTHORIZED":
        return {
            "verdict": "REJECT",
            "reason": "CoderAuthorization non AUTHORIZED.",
        }

    valid, reason = validate_authorization(
        authorization,
        target,
        authorization.path,
        allowed_paths,
    )

    if not valid:
        return {
            "verdict": "REJECT",
            "reason": reason,
        }

    if authorization.human_approval.approved is not True:
        return {
            "verdict": "REJECT",
            "reason": "Validation humaine absente.",
        }

    if not authorization.human_approval.approver.strip():
        return {
            "verdict": "REJECT",
            "reason": "Approbateur absent.",
        }

    if not authorization.human_approval.approved_at.strip():
        return {
            "verdict": "REJECT",
            "reason": "Timestamp d'approbation absent.",
        }

    if authorization.human_approval.authority_level not in {
        level.value for level in AuthorityLevel
    }:
        return {
            "verdict": "REJECT",
            "reason": "Niveau d'autorité invalide.",
        }

    return {
        "verdict": "AUTHORIZED",
        "reason": (
            "Coder autorisé après validation de la cible, "
            "de l'evidence, de la provenance, du scope, "
            "de l'action et de l'approbation humaine."
        ),
        "authorization": authorization_to_dict(authorization),
    }


def load_plan_report(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))

    validation = report.get("validation", {})
    verdict = validation.get("verdict")

    if verdict == "REJECT":
        raise ValueError(
            "Plan REJETÉ par la validation — le Coder refuse d'opérer. "
            f"Raison : {validation.get('reason')}"
        )

    selection = report.get("selection", {})
    selected = selection.get("selected_files", [])

    if not selected:
        raise ValueError(
            "Le plan ne contient aucun fichier sélectionné."
        )

    return report


def selected_paths(report: dict) -> list[str]:
    files = report["selection"]["selected_files"]

    return [
        item["path"].replace("\\", "/")
        for item in files
    ]


# ============================================================
# 2. LECTURE READ-ONLY DES FICHIERS CIBLES
# ============================================================

def safe_target(relative_path: str) -> Path:
    """
    Résout un chemin DANS MemoLib et vérifie qu'il n'en sort pas
    (anti path-traversal). Interdit .git.
    """

    normalized = relative_path.replace("\\", "/")
    path = (MEMOLIB / normalized).resolve()

    try:
        path.relative_to(MEMOLIB)
    except ValueError:
        raise ValueError(
            f"Chemin hors dépôt interdit : {relative_path}"
        )

    if ".git" in path.parts:
        raise ValueError("Accès .git interdit")

    return path


def read_selected_files(
    paths: list[str],
    max_files: int = MAX_CODER_FILES,
    max_context_chars: int = MAX_CODER_CONTEXT_CHARS,
) -> list[dict]:
    files = []
    total_chars = 0

    for rel in paths:
        if len(files) >= max_files:
            break

        target = safe_target(rel)

        if not target.exists() or not target.is_file():
            # Un fichier sélectionné mais absent : on l'ignore ici,
            # le garde-fou écriture empêchera de toute façon tout
            # patch qui tenterait de le créer hors sélection.
            continue

        content = target.read_text(encoding="utf-8", errors="replace")

        if total_chars + len(content) > max_context_chars and files:
            # On ne dépasse pas le budget de contexte du Coder.
            break

        files.append({
            "path": rel,
            "content": content,
        })
        total_chars += len(content)

    return files


# ============================================================
# 3. GÉNÉRATION DU DIFF (Ollama)
# ============================================================

def build_coder_prompt(
    request: str,
    objective: str,
    files: list[dict],
) -> str:

    blocks = []

    for item in files:
        blocks.append(
            f"===== FICHIER : {item['path']} =====\n{item['content']}"
        )

    files_block = "\n\n".join(blocks)

    allowed = "\n".join(f"  - {item['path']}" for item in files)

    return f"""
Tu es le Controlled Coder de MemoLibDev.

OBJECTIF (issu d'un plan validé) :
{objective or request}

DEMANDE INITIALE :
{request}

FICHIERS AUTORISÉS (les SEULS que tu peux modifier) :
{allowed}

CONTENU RÉEL DES FICHIERS :
{files_block}

RÈGLES ABSOLUES :
- Produis UNIQUEMENT un unified diff (format `git diff` / `diff -u`).
- Les chemins a/ et b/ doivent correspondre EXACTEMENT aux chemins
  autorisés ci-dessus.
- Ne modifie AUCUN autre fichier.
- N'invente aucun fichier, ne crée aucun fichier nouveau.
- Ne supprime aucun fichier.
- Ne touche jamais .git, package-lock.json, ni aucun secret.
- N'ajoute aucune dépendance.
- Ne contourne jamais Clerk ni l'authentification.
- Patch MINIMAL : seulement ce que l'objectif exige.
- Si les preuves sont insuffisantes pour un patch sûr, réponds
  EXACTEMENT : NO_PATCH_POSSIBLE
- Aucun texte, aucune explication hors du diff.
"""


def ask_ollama(prompt: str) -> tuple[str, dict]:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 2048,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = datetime.now()

    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.loads(response.read().decode("utf-8"))

    elapsed = (datetime.now() - started).total_seconds()

    answer = data.get("response", "")
    done_reason = data.get("done_reason")
    generation_complete = done_reason != "length"

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


def strip_code_fences(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    return text


# ============================================================
# 4. GARDE-FOU ÉCRITURE : chemins touchés ⊆ sélection
# ============================================================

DIFF_PATH_RE = re.compile(
    r"^(?:---|\+\+\+)\s+(?:[ab]/)?(.+?)\s*$"
)
DIFF_GIT_RE = re.compile(
    r"^diff --git a/(.+?) b/(.+?)\s*$"
)


def extract_patched_paths(diff_text: str) -> set[str]:
    """
    Extrait tous les chemins de fichiers référencés par le diff.
    Robuste aux en-têtes `diff --git`, `---`, `+++`.
    Ignore /dev/null (création/suppression).
    """

    paths: set[str] = set()

    for line in diff_text.splitlines():
        m = DIFF_GIT_RE.match(line)

        if m:
            for g in m.groups():
                g = g.strip()
                if g and g != "/dev/null":
                    paths.add(g.replace("\\", "/"))
            continue

        if line.startswith("--- ") or line.startswith("+++ "):
            m2 = DIFF_PATH_RE.match(line)

            if m2:
                g = m2.group(1).strip()

                if g and g != "/dev/null":
                    paths.add(g.replace("\\", "/"))

    return paths


def enforce_write_guardrail(
    diff_text: str,
    allowed_paths: list[str],
) -> dict:
    """
    REFUSE tout patch qui touche un fichier hors de la sélection.
    """

    allowed = set(allowed_paths)
    touched = extract_patched_paths(diff_text)

    out_of_scope = sorted(touched - allowed)

    if not touched:
        return {
            "verdict": "REJECT",
            "reason": "Aucun fichier identifiable dans le diff.",
            "touched_files": [],
            "out_of_scope_files": [],
        }

    if out_of_scope:
        return {
            "verdict": "REJECT",
            "reason": "Le patch touche des fichiers hors de la sélection.",
            "touched_files": sorted(touched),
            "out_of_scope_files": out_of_scope,
        }

    return {
        "verdict": "ACCEPTABLE",
        "reason": "Tous les fichiers touchés sont dans la sélection.",
        "touched_files": sorted(touched),
        "out_of_scope_files": [],
    }


# ============================================================
# 5. VÉRIFICATION EN SANDBOX (git apply --check)
# ============================================================

class SandboxBoundaryError(RuntimeError):
    """Violation of the 5G.1 sandbox boundary."""


def _resolved_relative_path(path: str | Path) -> Path:
    """
    Normalise un chemin relatif destiné au sandbox.

    Refuse :
    - chemin absolu ;
    - traversal `..` ;
    - chemin vide.
    """
    raw = str(path).strip()

    if not raw:
        raise SandboxBoundaryError("Sandbox path vide")

    candidate = Path(raw)

    if candidate.is_absolute():
        raise SandboxBoundaryError(
            f"Sandbox path absolu interdit: {raw}"
        )

    normalized = Path(*candidate.parts)

    if ".." in normalized.parts:
        raise SandboxBoundaryError(
            f"Sandbox path traversal interdit: {raw}"
        )

    return normalized


def _assert_patch_outside_target(
    patch_file: Path,
    target_root: Path,
) -> Path:
    """
    Le fichier patch est un artefact de MemoLibDev.
    Il ne doit jamais être situé dans le repository cible.
    """
    patch = Path(patch_file).resolve()
    root = Path(target_root).resolve()

    try:
        patch.relative_to(root)
    except ValueError:
        return patch

    raise SandboxBoundaryError(
        "Le patch_file est situé dans le repository cible MemoLib"
    )


def _assert_sandbox_boundary(
    sandbox: Path,
    target_root: Path,
) -> Path:
    """
    Vérifie que le sandbox est bien distinct du repository cible.
    """
    sandbox_root = Path(sandbox).resolve()
    target = Path(target_root).resolve()

    if sandbox_root == target:
        raise SandboxBoundaryError(
            "Le sandbox ne peut pas être le repository cible"
        )

    try:
        sandbox_root.relative_to(target)
    except ValueError:
        return sandbox_root

    raise SandboxBoundaryError(
        "Le sandbox ne peut pas être situé à l'intérieur de MemoLib"
    )


def _remove_sandbox(sandbox: Path) -> None:
    """
    Supprime le sandbox de manière robuste sous Windows.

    Les fichiers .git/objects peuvent être en lecture seule.
    Toute erreur de suppression est propagée : le Sandbox Gate
    ne doit jamais masquer un échec de cleanup.
    """
    import os
    import stat

    sandbox = Path(sandbox)

    if not sandbox.exists():
        return

    def _onerror(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            raise

    shutil.rmtree(
        sandbox,
        onerror=_onerror,
    )

    if sandbox.exists():
        raise SandboxBoundaryError(
            f"Sandbox cleanup incomplete: {sandbox}"
        )

def verify_patch_in_sandbox(
    diff_text: str,
    touched_paths: set[str],
    patch_file: Path,
) -> dict:
    """
    5G.1 SANDBOX GATE

    Copie UNIQUEMENT les fichiers touchés depuis MemoLib vers
    un dépôt Git temporaire distinct, puis vérifie le patch avec
    `git apply --check`.

    Cette fonction :
    - ne modifie jamais MemoLib ;
    - refuse un patch situé dans MemoLib ;
    - refuse les chemins absolus ;
    - refuse les traversées `..` ;
    - exécute Git uniquement avec cwd=sandbox ;
    - détruit toujours le sandbox.
    """

    target = resolve_target()
    target_root = Path(target.git_root).resolve()

    sandbox = Path(
        tempfile.mkdtemp(prefix="memolibdev-5g-")
    ).resolve()

    try:
        _assert_sandbox_boundary(
            sandbox,
            target_root,
        )

        patch = _assert_patch_outside_target(
            patch_file,
            target_root,
        )

        def run_git(*args):
            return subprocess.run(
                ["git", *args],
                cwd=sandbox,
                text=True,
                capture_output=True,
            )

        init = run_git("init", "-q")

        if init.returncode != 0:
            raise SandboxBoundaryError(
                "Impossible d'initialiser le dépôt Git sandbox"
            )

        run_git(
            "config",
            "user.email",
            "sandbox@memolibdev.local",
        )

        run_git(
            "config",
            "user.name",
            "memolibdev-sandbox",
        )

        copied = []

        for raw_rel in sorted(touched_paths):

            rel = _resolved_relative_path(raw_rel)

            try:
                source = safe_target(str(rel))
            except ValueError as exc:
                raise SandboxBoundaryError(
                    f"Fichier source hors cible: {raw_rel}"
                ) from exc

            source = source.resolve()

            try:
                source.relative_to(target_root)
            except ValueError as exc:
                raise SandboxBoundaryError(
                    f"Source hors repository cible: {raw_rel}"
                ) from exc

            if not source.exists():
                continue

            dest = (sandbox / rel).resolve()

            try:
                dest.relative_to(sandbox)
            except ValueError as exc:
                raise SandboxBoundaryError(
                    f"Destination sandbox hors périmètre: {raw_rel}"
                ) from exc

            dest.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(source, dest)
            copied.append(str(rel).replace("\\", "/"))

        if copied:
            add = run_git("add", "-A")

            if add.returncode != 0:
                raise SandboxBoundaryError(
                    "git add sandbox échoué"
                )

            commit = run_git(
                "commit",
                "-q",
                "-m",
                "sandbox baseline",
            )

            if commit.returncode != 0:
                raise SandboxBoundaryError(
                    "git commit sandbox échoué"
                )

        check = run_git(
            "apply",
            "--check",
            "--verbose",
            str(patch),
        )

        applicable = check.returncode == 0

        stat = run_git(
            "apply",
            "--stat",
            str(patch),
        )

        return {
            "applicable": applicable,
            "returncode": check.returncode,
            "stderr": check.stderr.strip(),
            "stat": stat.stdout.strip(),
            "sandbox_files": copied,
            "sandbox": str(sandbox),
            "target_root": str(target_root),
            "patch_file": str(patch),
        }

    finally:
        _remove_sandbox(sandbox)


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    print("=" * 70)
    print("MEMOLIBDEV — CONTROLLED CODER 5G")
    print("=" * 70)
    print()

    print("[0] CIBLE PROJET (lecture seule)")
    print(TARGET.describe())
    print()

    # Sélection du rapport de plan : argument explicite ou dernier.
    if len(sys.argv) >= 2:
        report_path = Path(sys.argv[1]).resolve()
    else:
        report_path = load_latest_decision_report()

    print("[1] PLAN VALIDÉ")
    print("Rapport :", report_path)

    try:
        report = load_plan_report(report_path)
    except (ValueError, FileNotFoundError) as exc:
        print("REFUS :", exc)
        return 1

    request = report.get("request", "")
    plan = report.get("plan", {})
    objective = plan.get("objective", "") if isinstance(plan, dict) else ""

    allowed_paths = selected_paths(report)

    # --------------------------------------------------------
    # 5F.3.6 — HUMAN AUTHORIZATION GATE
    #
    # IMPORTANT :
    # Ce contrôle intervient AVANT read_selected_files()
    # et surtout AVANT ask_ollama().
    #
    # Aucun certificat = aucun Coder.
    # --------------------------------------------------------

    print("")
    print("=== 5F.3.6 CODER AUTHORIZATION ===")

    try:
        target = resolve_target()
        authorization = load_coder_authorization()
    except Exception as exc:
        print("[BLOCK] Coder non autorisé :", exc)
        print("[BLOCK] Ollama ne sera PAS appelé.")
        print("[BLOCK] Aucun patch ne sera généré.")
        return 2

    authorization_gate = enforce_coder_authorization(
        authorization,
        target,
        allowed_paths,
    )

    print("Authorization :", authorization_gate["verdict"])
    print("Reason        :", authorization_gate["reason"])

    if authorization_gate["verdict"] != "AUTHORIZED":
        print("[BLOCK] CoderAuthorization rejetée.")
        print("[BLOCK] Ollama ne sera PAS appelé.")
        print("[BLOCK] Aucun patch ne sera généré.")
        return 2

    print("[PASS] Human Approval validée.")
    print("[PASS] CoderAuthorization AUTHORIZED.")
    print("[PASS] Cible liée au ProjectTarget.")
    print("[PASS] Scope lié à la sélection déterministe.")

    print("Fichiers autorisés :", len(allowed_paths))
    for p in allowed_paths:
        print("  -", p)

    print()
    print("[2] LECTURE READ-ONLY DES FICHIERS")

    files = read_selected_files(allowed_paths)

    print("Fichiers lus :", len(files), f"(plafond {MAX_CODER_FILES})")

    if not files:
        print("REFUS : aucun fichier lisible dans la sélection.")
        return 1

    # Le garde-fou écriture se cale sur les fichiers RÉELLEMENT envoyés
    # au Coder (sous-ensemble de la sélection, borné par le plafond).
    sent_paths = [f["path"] for f in files]
    for p in sent_paths:
        print("  envoyé:", p)

    print()
    print("[3] GÉNÉRATION DU DIFF (Ollama)")

    prompt = build_coder_prompt(request, objective, files)

    try:
        answer, metadata = ask_ollama(prompt)
    except Exception as exc:
        print("ERREUR Ollama :", exc)
        return 1

    print("Temps :", round(metadata["elapsed_seconds"], 2), "s")
    print("Réponse :", len(answer), "caractères")

    diff_text = strip_code_fences(answer)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    patch_file = PATCHES / f"controlled-coder-{timestamp}.diff"

    no_patch = diff_text.strip() == "NO_PATCH_POSSIBLE"

    print()
    print("[4] GARDE-FOU ÉCRITURE")

    if no_patch:
        guardrail = {
            "verdict": "NO_PATCH_POSSIBLE",
            "reason": "Le Coder n'a pas produit de patch.",
            "touched_files": [],
            "out_of_scope_files": [],
        }
        patch_file.write_text("# NO_PATCH_POSSIBLE\n", encoding="utf-8")
        print("Statut : NO_PATCH_POSSIBLE")
    else:
        guardrail = enforce_write_guardrail(diff_text, sent_paths)
        patch_file.write_text(diff_text + "\n", encoding="utf-8")

        print("Verdict :", guardrail["verdict"])
        print("Fichiers touchés :", guardrail["touched_files"])

        if guardrail["out_of_scope_files"]:
            print("HORS SÉLECTION :", guardrail["out_of_scope_files"])

    print()
    print("[5] VÉRIFICATION SANDBOX (git apply --check)")

    sandbox_result = None

    if guardrail["verdict"] == "ACCEPTABLE":
        sandbox_result = verify_patch_in_sandbox(
            diff_text,
            set(guardrail["touched_files"]),
            patch_file,
        )
        print("Applicable :", sandbox_result["applicable"])
        if sandbox_result["stat"]:
            print(sandbox_result["stat"])
        if not sandbox_result["applicable"] and sandbox_result["stderr"]:
            print("Détail :", sandbox_result["stderr"])
    else:
        print("Ignoré (patch non acceptable).")

    # Statut global
    if no_patch:
        status = "NO_PATCH_POSSIBLE"
    elif guardrail["verdict"] != "ACCEPTABLE":
        status = "REJECTED"
    elif sandbox_result and sandbox_result["applicable"]:
        status = "PATCH_PROPOSED"
    else:
        status = "PATCH_NOT_APPLICABLE"

    print()
    print("[6A] USAGE METERING")

    # Pour le metering, on reconstitue un bloc "selection" minimal
    # cohérent avec le contrat (fichiers = ceux fournis au coder).
    selection_trace = {
        "candidate_count": len(allowed_paths),
        "selected_count": len(files),
        "primary_count": len(files),
        "secondary_count": 0,
        "context_chars": sum(len(f["content"]) for f in files),
        "context_estimated_tokens": sum(len(f["content"]) for f in files) // 4,
    }
    # Le verdict metering reflète le garde-fou écriture + applicabilité.
    metering_validation = {
        "verdict": "REJECT" if status in {"REJECTED"} else guardrail["verdict"],
        "reason": guardrail["reason"],
    }

    operation = build_and_record(
        request=request,
        model=MODEL,
        selection=selection_trace,
        metadata=metadata,
        validation=metering_validation,
        plan={"proposed_steps": []},
        operation_type="CODE",
        agent="controlled_coder",
    )

    print("Opération :", operation["operation_type"], f"({operation['status']})")
    print("ID :", operation["id"])

    # Rapport
    report_out = {
        "created_at": datetime.now().isoformat(),
        "source_plan": str(report_path),
        "request": request,
        "objective": objective,
        "model": MODEL,
        "allowed_paths": allowed_paths,
        "sent_paths": sent_paths,
        "metadata": metadata,
        "status": status,
        "write_guardrail": guardrail,
        "sandbox_check": sandbox_result,
        "patch_file": str(patch_file),
        "operation": operation,
        "repository_modified": False,
        "human_validation_required": True,
    }

    report_file = REPORTS / f"controlled-coder-{timestamp}.json"
    report_file.write_text(
        json.dumps(report_out, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("[6] RÉSULTAT")
    print("Statut global :", status)
    print("Patch :", patch_file)
    print("Rapport :", report_file)
    print()
    print("MEMOLIB N'A PAS ÉTÉ MODIFIÉ.")
    print("AUCUN PATCH APPLIQUÉ.")
    print("AUCUN COMMIT. AUCUN PUSH.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

