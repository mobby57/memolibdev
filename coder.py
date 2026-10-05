from pathlib import Path
from datetime import datetime
import json
import sys
import urllib.request

ROOT = Path(r"C:\Users\moros\Desktop\memolib").resolve()
V3 = Path(r"C:\Users\moros\MemoLibDev\v3").resolve()

PATCHES = V3 / "patches"
REPORTS = V3 / "reports"

MODEL = "qwen2.5-coder:7b"
OLLAMA_URL = "http://localhost:11434/api/generate"

PATCHES.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)


def safe_file(relative_path):
    path = (ROOT / relative_path).resolve()

    try:
        path.relative_to(ROOT)
    except ValueError:
        raise ValueError("Chemin hors dépôt interdit")

    if ".git" in path.parts:
        raise ValueError("Accès .git interdit")

    return path


def ask_ollama(prompt):
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
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


def main():
    if len(sys.argv) < 2:
        print('Usage : python coder.py "demande"')
        sys.exit(1)

    request_text = " ".join(sys.argv[1:])

    target = safe_file("src/proxy.ts")

    if not target.exists():
        print("ERREUR : src/proxy.ts introuvable")
        sys.exit(1)

    content = target.read_text(encoding="utf-8")

    prompt = f"""
Tu es le Coder de MemoLibDev.

Demande :
{request_text}

Fichier réel fourni :
src/proxy.ts

Contenu :
```typescript
{content}

Règles :

produire uniquement un unified diff ;
ne jamais inventer de fichier ;
ne modifier que le fichier fourni ;
ne jamais modifier .git ;
ne jamais supprimer de fichier ;
ne pas modifier package-lock.json ;
ne pas ajouter de dépendance ;
ne pas modifier de secret ;
ne pas contourner Clerk ou l'authentification ;
l'absence de auth() n'est pas à elle seule une preuve de vulnérabilité ;
si les preuves sont insuffisantes, retourner exactement NO_PATCH_POSSIBLE ;
patch minimal ;

aucun texte hors du diff.
"""

    print("=" * 60)
    print(" MEMOLIBDEV V3 — CODER")
    print("=" * 60)
    print()
    print("Modèle :", MODEL)
    print("Fichier :", target)
    print()

    try:
        response = ask_ollama(prompt)
    except Exception as exc:
        print("ERREUR Ollama :", exc)
        sys.exit(1)

    response = response.strip()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    patch_file = PATCHES / f"coder-{timestamp}.diff"
    report_file = REPORTS / f"coder-{timestamp}.json"

    if response == "NO_PATCH_POSSIBLE":
        status = "NO_PATCH_POSSIBLE"
        patch_file.write_text(
            "# NO_PATCH_POSSIBLE\n",
            encoding="utf-8"
        )
    else:
        status = "PATCH_PROPOSED"

        if response.startswith("```"):
            lines = response.splitlines()

            if lines:
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            response = "\n".join(lines).strip()

        patch_file.write_text(
            response + "\n",
            encoding="utf-8"
        )

    report = {
        "created_at": datetime.now().isoformat(),
        "model": MODEL,
        "request": request_text,
        "target": "src/proxy.ts",
        "status": status,
        "patch": str(patch_file),
        "human_validation_required": True,
        "repository_modified": False
    }

    report_file.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("Statut :", status)
    print("Patch :", patch_file)
    print("Rapport:", report_file)
    print()
    print("MemoLib n'a PAS été modifié.")


if __name__ == "__main__":
    main()
