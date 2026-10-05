from pathlib import Path
from datetime import datetime
import json
import sys
import urllib.request

V3 = Path(r"C:\Users\moros\MemoLibDev\v3").resolve()
REPORTS = V3 / "reports"

MODEL = "hf.co/bartowski/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"
OLLAMA_URL = "http://localhost:11434/api/generate"

REPORTS.mkdir(parents=True, exist_ok=True)


def ask_ollama(prompt):
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0
        }
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        data = json.loads(response.read().decode("utf-8"))

    return data.get("response", "")


def save_report(patch_path, review):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = REPORTS / f"review-{timestamp}.json"

    report = {
        "created_at": datetime.now().isoformat(),
        "model": MODEL,
        "patch": str(patch_path),
        "review": review,
        "human_validation_required": True,
        "repository_modified": False
    }

    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return output


def main():
    if len(sys.argv) != 2:
        print("Usage : python reviewer.py chemin-vers-patch.diff")
        sys.exit(1)

    patch_path = Path(sys.argv[1]).resolve()

    if not patch_path.exists():
        print("ERREUR : patch introuvable")
        sys.exit(1)

    if patch_path.suffix not in {".diff", ".patch"}:
        print("ERREUR : seuls .diff et .patch sont acceptés")
        sys.exit(1)

    patch = patch_path.read_text(encoding="utf-8")

    print("=" * 60)
    print(" MEMOLIBDEV V3 — REVIEWER")
    print("=" * 60)
    print()
    print("Modèle :", MODEL)
    print("Patch  :", patch_path)
    print()

    if "NO_PATCH_POSSIBLE" in patch:
        review = {
            "status": "NO_PATCH_POSSIBLE",
            "confidence": 100,
            "summary": "Le Coder n'a pas produit de patch applicable.",
            "security_risks": [],
            "functional_risks": [],
            "scope_risks": [],
            "required_tests": [],
            "reason": "NO_PATCH_POSSIBLE"
        }

        output = save_report(patch_path, review)

        print("Statut :", review["status"])
        print("Rapport :", output)
        print()
        print("MemoLib n'a PAS été modifié.")
        return

    prompt = f"""
Tu es le Reviewer de MemoLibDev.

Analyse UNIQUEMENT le patch fourni.

PATCH :
{patch}

Règles :
- ne suppose jamais qu'un fichier existe sans preuve ;
- ne considère pas l'absence de auth() comme preuve d'une vulnérabilité ;
- vérifie la portée exacte du patch ;
- recherche les risques de sécurité ;
- recherche les risques IDOR, tenant et workspace ;
- recherche les régressions ;
- recherche les secrets ;
- vérifie que le patch est minimal ;
- si les preuves sont insuffisantes, utilise NEEDS_REVIEW ;
- ne propose aucune modification.

Retourne uniquement un JSON valide :

{{
  "status": "APPROVED",
  "confidence": 0,
  "summary": "",
  "security_risks": [],
  "functional_risks": [],
  "scope_risks": [],
  "required_tests": [],
  "reason": ""
}}

Les seuls statuts autorisés sont :
APPROVED
REJECTED
NEEDS_REVIEW

APPROVED signifie seulement que le patch semble techniquement acceptable
avec les informations disponibles.

APPROVED ne signifie jamais autorisation humaine.
"""


    try:
        response = ask_ollama(prompt)
        review = json.loads(response)
    except Exception as exc:
        review = {
            "status": "NEEDS_REVIEW",
            "confidence": 0,
            "summary": "Reviewer non exploitable.",
            "security_risks": [],
            "functional_risks": [],
            "scope_risks": [],
            "required_tests": [],
            "reason": str(exc)
        }

    output = save_report(patch_path, review)

    print("Statut     :", review.get("status"))
    print("Confiance  :", review.get("confidence"))
    print("Résumé     :", review.get("summary"))
    print()
    print("Rapport :", output)
    print()
    print("MemoLib n'a PAS été modifié.")
    print("Validation humaine toujours obligatoire.")


if __name__ == "__main__":
    main()
