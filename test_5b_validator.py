from __future__ import annotations

import json
import time
import urllib.request

from interface.app import MemoLibDevApp
from validator_lab import validate_claim


MODEL = "hf.co/bartowski/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"
OLLAMA_URL = "http://localhost:11434/api/generate"

REQUEST = """
Analyse la cohérence de l'architecture d'authentification et OAuth
dans le code réel inspecté.

Objectif :
déterminer s'il existe une anomalie réellement démontrable.

Attention :
- plusieurs appels à auth() ne constituent PAS automatiquement une anomalie ;
- distinguer authentification utilisateur Clerk et gestion de tokens OAuth ;
- ne pas confondre co-occurrence et contradiction ;
- ne pas inventer de fichier ;
- citer uniquement les fichiers réellement fournis ;
- si la preuve est insuffisante, répondre NON_PROBLEMATIQUE ou INSUFFISANT.

Réponse courte et structurée :

STATUT:
CONFIRME | POSSIBLE | NON_PROBLEMATIQUE | INSUFFISANT

FICHIERS:
- chemins exacts

PROBLEME:
une phrase maximum

PREUVE:
éléments directement visibles dans le code

RAISONNEMENT:
pourquoi il s'agit réellement d'une contradiction,
ou pourquoi ce n'est pas une contradiction.
"""


def ollama(prompt: str) -> dict:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 120,
        },
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.perf_counter()

    with urllib.request.urlopen(request, timeout=180) as response:
        raw = response.read().decode("utf-8")

    elapsed = time.perf_counter() - start

    result = json.loads(raw)
    result["_elapsed"] = elapsed

    return result


def main() -> None:
    print("=" * 70)
    print("TEST 5B — OLLAMA + VALIDATOR")
    print("=" * 70)

    app = MemoLibDevApp()

    print()
    print("[1] CANDIDATS")

    candidates = app._candidate_files(REQUEST)

    print(f"Fichiers candidats : {len(candidates)}")

    for index, path in enumerate(candidates, 1):
        print(f"{index:02d}. {path}")

    print()
    print("[2] INSPECTION")

    inspection = app._run_inspector(candidates)

    files = (
        inspection.get("files", [])
        if isinstance(inspection, dict)
        else inspection
    )

    print(f"Fichiers inspectés : {len(files)}")

    print()
    print("[3] CONTEXTE")

    context = app._build_context(files)

    print(f"Contexte : {len(context)} caractères")

    print()
    print("[4] OLLAMA")

    prompt = REQUEST + "\n\nCODE INSPECTÉ :\n" + context

    print(f"Prompt : {len(prompt)} caractères")
    print(f"Modèle : {MODEL}")

    try:
        result = ollama(prompt)
    except Exception as exc:
        print()
        print("ERREUR OLLAMA")
        print(type(exc).__name__, str(exc))
        return

    response = result.get("response", "")

    print()
    print(f"Temps Ollama : {result.get('_elapsed', 0):.2f}s")

    print()
    print("=" * 70)
    print("RÉPONSE OLLAMA")
    print("=" * 70)
    print(response)

    inspected_files = [
        str(item.get("requested_path", ""))
        for item in files
        if isinstance(item, dict)
    ]

    print()
    print("=" * 70)
    print("VALIDATOR")
    print("=" * 70)

    validation = validate_claim(
        model_response=response,
        inspected_files=inspected_files,
        context=context,
    )

    print()
    print(json.dumps(validation, indent=2, ensure_ascii=False))

    print()
    print("=" * 70)
    print("INTERPRÉTATION")
    print("=" * 70)

    if validation["verdict"] == "REJECT":
        print("❌ Réponse rejetée par le Validator.")

    elif validation["verdict"] == "REVIEW":
        print("⚠️ Réponse envoyée en REVIEW humaine.")

    else:
        print("✅ Réponse suffisamment ancrée pour continuer.")

    print()
    print("AUCUNE MODIFICATION DE MEMOLIB.")
    print("AUCUN COMMIT.")
    print("AUCUN PUSH.")
    print("AUCUNE APPLICATION AUTOMATIQUE.")


if __name__ == "__main__":
    main()
