from dataclasses import dataclass
from pathlib import Path

class CreateTargetError(ValueError):
    pass

BLOCKED_EXT = {".exe", ".bat", ".cmd", ".ps1", ".sh", ".dll", ".so",
               ".dylib", ".scr", ".vbs", ".jar", ".msi", ".com", ".pif",
               ".lnk", ".reg", ".hta"}

ALLOWED_EXT = {".md", ".txt", ".json", ".csv", ".html", ".xml", ".yaml",
               ".yml", ".pdf", ".docx", ".xlsx", ".pptx", ".py", ".js",
               ".ts", ".go", ".rs", ".css", ".svg"}

@dataclass(frozen=True)
class CreateTarget:
    abs_path: Path
    rel_path: str
    exists_before: bool

def resolve_create_target(git_root, rel_path):
    git_root = Path(git_root).resolve()
    p = Path(rel_path)
    if p.is_absolute():
        raise CreateTargetError("chemin absolu interdit")
    if ".." in p.parts:
        raise CreateTargetError("'..' interdit")
    candidate = (git_root / p).resolve()
    try:
        candidate.relative_to(git_root)
    except ValueError:
        raise CreateTargetError(f"hors git_root : {candidate}")
    if ".git" in candidate.parts:
        raise CreateTargetError("ecriture dans .git interdite")
    ext = candidate.suffix.lower()
    if not ext:
        raise CreateTargetError("extension obligatoire")
    if ext in BLOCKED_EXT:
        raise CreateTargetError(f"extension bloquee : {ext}")
    if ext not in ALLOWED_EXT:
        raise CreateTargetError(f"extension non autorisee : {ext}")
    if candidate.exists():
        raise CreateTargetError(f"le fichier existe deja : {candidate}")
    return CreateTarget(abs_path=candidate, rel_path=str(p).replace("\\", "/"), exists_before=False)
