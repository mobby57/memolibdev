from decision_agent import inspect_repository, build_prompt
from decision_selector import select_relevant_files
import json
import urllib.request
import time

REQUEST = """Vérifier la configuration OAuth Clerk de MemoLib.
Identifier les fichiers réellement pertinents, les preuves disponibles,
les éventuelles incohérences et les tests nécessaires.
Ne rien modifier."""

print("=" * 70)
print("MEMOLIBDEV — BENCHMARK 5F / QWEN 7B / 16K")
print("=" * 70)

files = inspect_repository()

selection = select_relevant_files(files, REQUEST)
selected = selection["selected"]

print(f"Repository : {len(files)}")
print(f"Candidats : {selection['candidate_count']}")
print(f"Primary : {selection['primary_count']}")
print(f"Secondary : {selection['secondary_count']}")
print(f"Contexte : {selection['context_chars']} caractères")

context = build_prompt(REQUEST, "\n\n".join(
    f"===== {item['path']} =====\n{item['content']}"
    for item in selected
))

payload = {
    "model": "memolibdev-qwen7b-16k",
    "prompt": context,
    "stream": False,
    "format": "json",
    "options": {
        "temperature": 0,
        "num_ctx": 16384,
        "num_predict": 2048
    }
}

data = json.dumps(payload).encode("utf-8")

request = urllib.request.Request(
    "http://localhost:11434/api/generate",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST",
)

print("\nAppel du modèle...")
start = time.perf_counter()

with urllib.request.urlopen(request, timeout=900) as response:
    result = json.loads(response.read().decode("utf-8"))

elapsed = time.perf_counter() - start
answer = result.get("response", "")

print(f"Temps : {elapsed:.2f} secondes")
print(f"Réponse : {len(answer)} caractères")
print(f"Done reason : {result.get('done_reason')}")
print(f"Prompt eval count : {result.get('prompt_eval_count')}")
print(f"Eval count : {result.get('eval_count')}")
print("\n=== REPONSE MODELE ===")
print(answer)
print("\n=== FIN BENCHMARK ===")
