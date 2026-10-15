import json
from dataclasses import dataclass

class CreateParseError(ValueError):
    pass

@dataclass(frozen=True)
class CreateIntent:
    path: str
    format: str
    content: str

ALLOWED_FORMATS = {"md", "txt", "json", "csv", "html", "xml", "yaml", "yml",
                   "pdf", "docx", "xlsx", "pptx", "py", "js", "ts"}

def parse_create_intent(line):
    if not line or not line.strip():
        raise CreateParseError("ligne vide")
    line = line.strip()
    if not line.startswith("{"):
        raise CreateParseError("doit commencer par {")
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        raise CreateParseError(f"JSON invalide : {e}")
    if not isinstance(obj, dict):
        raise CreateParseError("doit etre un objet JSON")
    if obj.get("action") != "CREATE":
        raise CreateParseError("action != CREATE")
    path = obj.get("path")
    fmt = obj.get("format")
    content = obj.get("content")
    if not isinstance(path, str) or not path:
        raise CreateParseError("path manquant")
    if not isinstance(fmt, str) or fmt not in ALLOWED_FORMATS:
        raise CreateParseError(f"format invalide : {fmt}")
    if not isinstance(content, str):
        raise CreateParseError("content manquant")
    return CreateIntent(path=path, format=fmt, content=content)
