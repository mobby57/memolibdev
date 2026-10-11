from __future__ import annotations

import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

from validator_lab import validate_claim


# ============================================================
# CONFIGURATION — IDENTIQUE À APP.PY
# ============================================================

V3_ROOT = Path(__file__).resolve().parent
MEMOLIB_ROOT = Path(r"C:\Users\moros\Desktop\memolib").resolve()
REPORTS_DIR = V3_ROOT / "reports"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "hf.co/bartowski/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"

MAX_CONTEXT_CHARS = 8000
MAX_FILES = 12
MAX_FILE_CONTEXT_CHARS = 2500
MAX_WEB_CONTEXT_CHARS = 4000


# ============================================================
# OUTILS
# ============================================================

def latest_inspection() -> Path:
    files = sorted(
        REPORTS_DIR.glob("inspection-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not files:
        raise RuntimeError("Aucune inspection trouvée.")

    return files[0]


def load_inspection(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise RuntimeError("Inspection invalide.")

    if not data.get("read_only", False):
        raise RuntimeError("Inspection non marquée read_only.")

    return data


# ============================================================
# REPRODUCTION EXACTE DE _build_context()
# ============================================================

def build_context(inspection: list[dict]) -> str:

    eligible = []

    for index, item in enumerate(inspection):

        if not item.get("exists"):
            continue

        relative = item.get(
            "requested_path",
            "inconnu"
        )

        content = item.get(
            "content",
            ""
        )

        if not content:
            continue

        lowered = relative.lower()

        # Ne jamais envoyer de secrets.
        if any(
            secret_name in lowered
            for secret_name in [
                ".env",
                "secret",
                "credential",
                "credentials",
                "private-key",
                "private_key",
            ]
        ):
            continue

        is_test = (
            "/__tests__/" in lowered
            or "/tests/" in lowered
            or lowered.endswith(".test.ts")
            or lowered.endswith(".test.tsx")
            or lowered.endswith(".spec.ts")
            or lowered.endswith(".spec.tsx")
        )

        is_middleware = (
            lowered.endswith("/middleware.ts")
            or lowered.endswith("/middleware.js")
            or lowered.endswith("/middleware.tsx")
            or lowered.endswith("/middleware.jsx")
            or "/middleware/" in lowered
        )

        is_proxy = (
            lowered.endswith("/proxy.ts")
            or lowered.endswith("/proxy.js")
            or lowered.endswith("/proxy.tsx")
            or lowered.endswith("/proxy.jsx")
        )

        is_clerk = (
            "clerk" in lowered
            or "clerk-auth" in lowered
            or "clerk_auth" in lowered
            or "clerk-token" in lowered
        )

        is_auth = (
            "/auth/" in lowered
            or "/authentication/" in lowered
            or "/auth." in lowered
            or lowered.endswith("/auth.ts")
            or lowered.endswith("/auth.js")
        )

        is_oauth = (
            "oauth" in lowered
        )

        is_session = (
            "session" in lowered
        )

        is_config = (
            lowered.endswith("package.json")
        )

        is_api_route = (
            "/api/" in lowered
            and "/route." in lowered
        )

        is_login = (
            "/login/" in lowered
            or lowered.endswith("/login/page.tsx")
            or lowered.endswith("/login/page.ts")
        )

        score = 0

        if not is_test:
            score += 100
        else:
            score -= 200

        if is_proxy:
            score += 500

        if is_middleware:
            score += 480

        if is_clerk:
            score += 300

        if is_auth:
            score += 260

        if is_session:
            score += 180

        if is_config:
            score += 220

        if is_oauth:
            score += 70

        if is_api_route:
            score += 40

        if is_login:
            score += 20

        for keyword in re.findall(
            r"[A-Za-zÀ-ÿ0-9_./\\-]+",
            "auth clerk middleware",
        ):
            if len(keyword) >= 3 and keyword in lowered:
                score += 25

        eligible.append(
            {
                "score": score,
                "index": index,
                "item": item,
                "path": relative,
                "lower": lowered,
                "content": content,
                "is_test": is_test,
                "is_middleware": is_middleware,
                "is_proxy": is_proxy,
                "is_clerk": is_clerk,
                "is_auth": is_auth,
                "is_oauth": is_oauth,
                "is_config": is_config,
            }
        )

    eligible.sort(
        key=lambda entry: (
            -entry["score"],
            entry["index"],
        )
    )

    critical = []
    used_paths = set()

    for entry in eligible:

        if entry["is_test"]:
            continue

        critical_match = (
            entry["is_proxy"]
            or entry["is_middleware"]
            or entry["is_clerk"]
            or entry["is_auth"]
        )

        if not critical_match:
            continue

        path_key = entry["path"].lower()

        if path_key in used_paths:
            continue

        critical.append(entry)
        used_paths.add(path_key)

    critical = critical[:5]

    selected = list(critical)

    for entry in eligible:

        if len(selected) >= MAX_FILES:
            break

        path_key = entry["path"].lower()

        if path_key in used_paths:
            continue

        selected.append(entry)
        used_paths.add(path_key)

    chunks = []
    total = 0

    critical_limit = 1600
    normal_limit = 1000

    for entry in selected:

        if total >= MAX_CONTEXT_CHARS:
            break

        relative = entry["path"]
        content = entry["content"]

        if entry in critical:
            file_limit = critical_limit
        else:
            file_limit = normal_limit

        excerpt = content[:file_limit]

        block = (
            f"\n===== FICHIER RÉEL : {relative} =====\n"
            f"{excerpt}\n"
            f"===== FIN : {relative} =====\n"
        )

        remaining = MAX_CONTEXT_CHARS - total

        if len(block) > remaining:

            if remaining < 500:
                break

            excerpt = content[
                :max(0, remaining - 120)
            ]

            block = (
                f"\n===== FICHIER RÉEL : {relative} =====\n"
                f"{excerpt}\n"
                f"===== FIN : {relative} =====\n"
            )

        if not block.strip():
            continue

        chunks.append(block)
        total += len(block)

    return "".join(chunks)


# ============================================================
# PROMPT IDENTIQUE À APP.PY
# ============================================================

def build_prompt(request: str, paths: list[dict], context: str) -> str:

    file_list = "\n".join(
        f"- {item.get('requested_path', 'inconnu')}"
        for item in paths
        if isinstance(item, dict)
    )

    web_context = ""

    prompt = f"""
Tu es MemoLibDev, agent de développement local
pour le projet MemoLib.

Tu fonctionnes actuellement en MODE CONSEIL / AUDIT.

RÈGLES ABSOLUES :
- ne modifie aucun fichier ;
- ne propose jamais de faux chemins ;
- utilise uniquement les fichiers réellement fournis ;
- ne prétends jamais avoir exécuté une modification ;
- ne lance aucun git commit ;
- ne lance aucun git push ;
- aucune action production ;
- ne demande jamais de secret ;
- ne révèle jamais de valeur de secret ;
- distingue clairement faits observés, hypothèses et recommandations ;
- toute modification devra être validée humainement.

DÉPÔT :
{MEMOLIB_ROOT}

FICHIERS CIBLÉS PAR MEMOLIBDEV :
{file_list if file_list else "Aucun fichier ciblé."}

CONTENU RÉEL INSPECTÉ :
{context if context else "Aucun contenu exploitable n'a été récupéré."}

SOURCES WEB PUBLIQUES :
{web_context if web_context else "Aucune source Web exploitable n'a été récupérée."}

RÈGLES DE FUSION LOCAL + WEB :

1. Les fichiers inspectés localement constituent la seule preuve
   de l'état réel du dépôt MemoLib.

2. Une source Web ne peut jamais prouver qu'un fichier local,
   une route locale, une variable d'environnement locale ou une
   configuration locale existe.

3. Les informations Web servent uniquement à compléter le diagnostic
   avec de la documentation, des migrations, des versions, des API,
   des recommandations techniques ou des informations publiques.

4. Si une information locale et une information Web semblent
   contradictoires, signale la contradiction explicitement.

5. Ne présente jamais une recommandation Web comme un fait observé
   dans MemoLib.

6. Cite les URL Web pertinentes dans ta réponse lorsque tu t'appuies
   dessus.

7. Si aucune source Web ne permet de répondre correctement,
   indique-le au lieu d'inventer.

DEMANDE UTILISATEUR :
{request}

Réponds en français.

Structure ta réponse ainsi :

1. DIAGNOSTIC
2. FICHIERS RÉELLEMENT OBSERVÉS
3. CONSTATS FACTUELS
4. HYPOTHÈSES
5. VÉRIFICATIONS COMPLÉMENTAIRES
6. PROCHAINE ÉTAPE

RÈGLE DE PREUVE OBLIGATOIRE :

Pour CHAQUE constat factuel important, utilise obligatoirement ce format :

STATUT: CONFIRME

FICHIER:
<un chemin EXACT provenant uniquement des fichiers réellement fournis>

PREUVE:
<un élément technique concret réellement observable dans le contenu inspecté :
fonction, appel, condition, variable, route, middleware, statut HTTP,
configuration ou extrait court>

CONSTAT:
<ce que cette preuve permet réellement d'affirmer>

LIMITE:
<ce que la preuve ne permet pas de conclure, si nécessaire>

Un constat factuel sans preuve technique concrète doit être classé
dans HYPOTHÈSES ou VÉRIFICATIONS COMPLÉMENTAIRES, et non dans
CONSTATS FACTUELS.

RÈGLES STRICTES DE GROUNDING :

- Chaque FICHIER utilisé dans une preuve doit appartenir aux fichiers
  réellement fournis et inspectés.
- Ne cite jamais un fichier uniquement parce que son nom semble logique.
- Ne prétends jamais avoir inspecté un fichier qui n'est pas fourni.
- Si un fichier supplémentaire serait nécessaire, mentionne-le
  uniquement dans VÉRIFICATIONS COMPLÉMENTAIRES.
- Ne transforme jamais une recommandation en constat factuel.
- Ne considère jamais la simple présence d'un nom de fonction ou d'un
  fichier comme une preuve suffisante : relie la preuve au constat.
- N'invente aucun extrait de code.
- Si aucune preuve suffisante n'existe, indique explicitement :
  PREUVE: insuffisante.

Pour les HYPOTHÈSES, utilise :

STATUT: POSSIBLE

et explique clairement qu'il s'agit d'une hypothèse non démontrée
par les fichiers inspectés.

Pour les éléments qui nécessitent une inspection supplémentaire,
utilise VÉRIFICATIONS COMPLÉMENTAIRES et indique le fichier ou
l'information supplémentaire nécessaire, sans prétendre l'avoir
inspecté.

Si les fichiers fournis ne permettent pas de conclure,
dis-le explicitement.

Ne fabrique aucun fichier, chemin ou configuration.
"""

import pytest
from ollama_helpers import ollama_available, ollama_has_model

pytestmark = pytest.mark.skipif(
    not ollama_available(),
    reason="Ollama non disponible (lancer 'ollama serve')"
)



    return prompt


# ============================================================
# OLLAMA
# ============================================================

def call_ollama(prompt: str) -> tuple[str, dict]:

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 1024
        }
    }

    request_http = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    started = datetime.now()

    with urllib.request.urlopen(
        request_http,
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
        "Réponse Ollama vide."
    )

    generation_complete = data.get("done_reason") != "length"

    return answer, {
        "elapsed_seconds": elapsed,
        "model": MODEL,
        "url": OLLAMA_URL,
        "temperature": 0,
        "stream": False,
        "prompt_chars": len(prompt),
        "response_chars": len(answer),

        # Métadonnées natives Ollama — observation uniquement.
        "done": data.get("done"),
        "done_reason": data.get("done_reason"),
        "generation_complete": generation_complete,
        "generation_truncated": not generation_complete,
        "eval_count": data.get("eval_count"),
        "eval_duration": data.get("eval_duration"),
        "prompt_eval_count": data.get("prompt_eval_count"),
        "prompt_eval_duration": data.get("prompt_eval_duration"),
        "load_duration": data.get("load_duration"),
        "total_duration": data.get("total_duration"),
    }


# ============================================================
# TEST 5E
# ============================================================

def main():

    print("=" * 70)
    print("MEMOLIBDEV — TEST 5E")
    print("VALIDATION D'UNE RÉPONSE OLLAMA RÉELLE")
    print("=" * 70)

    inspection_path = latest_inspection()

    print()
    print("[1] INSPECTION")
    print(f"Fichier : {inspection_path.name}")

    inspection_data = load_inspection(
        inspection_path
    )

    files = inspection_data.get(
        "files",
        []
    )

    print(f"Fichiers inspectés : {len(files)}")

    print()
    print("[2] BUILD CONTEXT")
    context = build_context(files)

    print(f"Contexte : {len(context)} caractères")

    print()
    print("[3] FICHIERS UTILISÉS PAR LE PROMPT")

    for item in files:
        if isinstance(item, dict):
            print(
                f"- {item.get('requested_path', 'inconnu')}"
            )

    request = (
        "Audite la cohérence de l'authentification "
        "Clerk et OAuth dans les fichiers fournis. "
        "Détermine ce qui est factuellement observable "
        "et ce qui nécessite une vérification complémentaire."
    )

    print()
    print("[4] PROMPT")
    prompt = build_prompt(
        request,
        files,
        context
    )

    print(f"Prompt : {len(prompt)} caractères")

    print()
    print("[5] OLLAMA")
    print(f"Model : {MODEL}")
    print("Temperature : 0")
    print("Timeout : 240 secondes")

    try:

        answer, meta = call_ollama(
            prompt
        )

    except Exception as exc:

        print()
        print("ERREUR OLLAMA")
        print(str(exc))
        print()
        print("AUCUNE MODIFICATION DE MEMOLIB.")
        return 1

    print()
    print(f"Temps Ollama : {meta['elapsed_seconds']:.2f}s")
    print(f"Réponse : {meta['response_chars']} caractères")

    print()
    print("=" * 70)
    print("RÉPONSE OLLAMA RÉELLE")
    print("=" * 70)
    print(answer)

    print()
    print("=" * 70)
    print("VALIDATOR 5D.1")
    print("=" * 70)

    validation = validate_claim(
        model_response=answer,
        context=context,
        inspected_files=[
            item.get("requested_path", "")
            for item in files
            if isinstance(item, dict)
        ],
    )

    # Contrôle de complétude de génération Ollama.
    # Une réponse interrompue par la limite de tokens ne peut pas
    # être considérée comme pleinement acceptable.
    generation_complete = meta.get(
        "generation_complete",
        True
    )

    generation_truncated = meta.get(
        "generation_truncated",
        False
    )

    if generation_truncated:
        validation["verdict"] = "REVIEW"
        validation["generation_complete"] = False
        validation["generation_truncated"] = True
        validation.setdefault("reasons", []).append(
            "La réponse Ollama est tronquée : "
            "done_reason=length."
        )
    else:
        validation["generation_complete"] = generation_complete
        validation["generation_truncated"] = False

    print(
        json.dumps(
            validation,
            ensure_ascii=False,
            indent=2
        )
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d-%H%M%S"
    )

    report_path = (
        REPORTS_DIR
        / f"test-5e-real-{timestamp}.json"
    )

    report = {
        "test": "5E",
        "created_at": datetime.now().isoformat(),
        "read_only": True,
        "repository": str(MEMOLIB_ROOT),
        "inspection": inspection_path.name,
        "model": MODEL,
        "ollama": meta,
        "request": request,
        "context_chars": len(context),
        "prompt_chars": len(prompt),
        "answer": answer,
        "validation": validation,
    }

    report_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print()
    print("=" * 70)
    print("RAPPORT")
    print("=" * 70)
    print(report_path)

    print()
    print("AUCUNE MODIFICATION DE MEMOLIB.")
    print("AUCUN COMMIT.")
    print("AUCUN PUSH.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())