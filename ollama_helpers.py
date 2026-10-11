
# ollama_helpers.py — Skip conditionnel Ollama
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/tags"


def ollama_available(timeout=2):
    """Retourne True si Ollama repond en <timeout secondes."""
    try:
        urllib.request.urlopen(OLLAMA_URL, timeout=timeout)
        return True
    except Exception:
        return False


def ollama_has_model(model_name):
    """Verifie qu'un modele est present (ex: 'qwen:7b')."""
    import json
    try:
        r = urllib.request.urlopen(OLLAMA_URL, timeout=3)
        data = json.loads(r.read())
        names = [m.get("name", "") for m in data.get("models", [])]
        return any(model_name in n for n in names)
    except Exception:
        return False
