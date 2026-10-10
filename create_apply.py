import hashlib
from dataclasses import dataclass

@dataclass(frozen=True)
class ApplyResult:
    status: str
    path: str
    sha256: str | None
    rolled_back: bool
    reason: str | None

def apply_create(target, content, verify_fn):
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if target.abs_path.exists():
        return ApplyResult("FAILED", target.rel_path, None, False, "le fichier est apparu entre-temps")
    try:
        target.abs_path.parent.mkdir(parents=True, exist_ok=True)
        target.abs_path.write_text(content, encoding="utf-8")
    except Exception as e:
        return ApplyResult("FAILED", target.rel_path, None, False, f"ecriture : {e}")
    try:
        ok, msg = verify_fn(target.abs_path)
    except Exception as e:
        ok, msg = False, f"verify exception : {e}"
    if ok:
        return ApplyResult("APPLIED", target.rel_path, sha, False, None)
    try:
        target.abs_path.unlink()
    except Exception as e:
        return ApplyResult("FAILED", target.rel_path, None, False, f"rollback echoue : {e}")
    if target.abs_path.exists():
        return ApplyResult("FAILED", target.rel_path, None, False, "rollback : le fichier existe encore")
    return ApplyResult("ROLLED_BACK", target.rel_path, None, True, msg)
