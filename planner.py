from pathlib import Path
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime

ROOT = Path(r"C:\Users\moros\Desktop\memolib")
OUT = Path(__file__).resolve().parent / "reports"

MODEL = "hf.co/bartowski/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"
OLLAMA_URL = "http://localhost:11434/api/generate"

MAX_CONTEXT = 24000


SYSTEM_PROMPT = """
Tu es le PLANNER de MemoLibDev.

Projet cible :
MemoLib — plateforme juridique intelligente.

Tu analyses une demande de développement et proposes un PLAN.
Tu ne modifies jamais le projet.

REGLES ABSOLUES :
- aucune modification de fichier
- aucun git commit
- aucun git push
- aucun git pull
- aucune suppression
- aucune action production
- ne jamais inventer un fichier
- ne jamais affirmer qu'une vulnérabilité existe sans preuve
- distinguer fait, hypothèse et vérification nécessaire
- human_validation_required doit toujours être true

Réponds UNIQUEMENT avec un JSON valide :

{
  "task": "...",
  "understanding": "...",
  "scope": [],
  "files_to_inspect": [],
  "files_allowed_to_modify": [],
  "risks": [],
  "tests_required": [],
  "verification_steps": [],
  "human_validation_required": true
}
"""


def call_ollama(prompt):
    payload = {
        "model": MODEL,
        "prompt": SYSTEM_PROMPT + "\n\nDEMANDE:\n" + prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "num_predict": 1200
        },
        "keep_alive": "10m"
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))

    return json.loads(data["response"])


def main():
    if len(sys.argv) < 2:
        print('Usage : python planner.py "demande"')
        sys.exit(1)

    task = " ".join(sys.argv[1:])

    print()
    print("=== MEMOLIBDEV V3 — PLANNER ===")
    print(f"Modèle : {MODEL}")
    print(f"Demande : {task}")
    print()

    try:
        plan = call_ollama(task)
    except Exception as exc:
        print(f"ERREUR Ollama : {exc}")
        sys.exit(1)

    OUT.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = OUT / f"plan-{timestamp}.json"

    plan["_meta"] = {
        "created_at": datetime.now().isoformat(),
        "model": MODEL,
        "read_only": True,
        "human_validation_required": True
    }

    output.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("=== PLAN PRODUIT ===")
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    print()
    print(f"Rapport : {output}")


if __name__ == "__main__":
    main()

