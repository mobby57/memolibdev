# apply_lazy_fix_v3.py — Remplace les lignes try/except par lazy proxy
# Methode : par numeros de ligne exacts (deterministe)
import shutil, sys, subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

NEW_BLOCK = '''# --- Cible projet : resolution LAZY (evite sys.exit au module-level) ---
# Sans MEMOLIBDEV_TARGET, l'import reste possible ; l'erreur ne survient
# qu'a la premiere utilisation reelle de TARGET ou MEMOLIB (fail-closed).
_TARGET_CACHE = None


def _ensure_target():
    global _TARGET_CACHE
    if _TARGET_CACHE is not None:
        return _TARGET_CACHE
    try:
        _TARGET_CACHE = resolve_target()
    except ProjectTargetError as exc:
        print(f"[TARGET][ERROR] {exc}", file=sys.stderr)
        raise RuntimeError(str(exc)) from exc
    return _TARGET_CACHE


class _TargetProxy:
    """Resout le target au premier acces (lazy)."""
    def __getattr__(self, name):
        return getattr(_ensure_target(), name)
    def __repr__(self):
        return f"<TargetProxy resolved={_TARGET_CACHE is not None}>"


class _MemolibProxy:
    """Resout MEMOLIB (TARGET.path) au premier acces (lazy)."""
    def _p(self):
        return _ensure_target().path
    def __truediv__(self, other):
        return self._p() / other
    def __rtruediv__(self, other):
        return other / self._p()
    def __fspath__(self):
        return str(self._p())
    def __getattr__(self, name):
        return getattr(self._p(), name)
    def __str__(self):
        return str(self._p())
    def __repr__(self):
        return "<MemolibProxy>"


TARGET = _TargetProxy()
MEMOLIB = _MemolibProxy()'''

# (fichier, ligne de debut du try (1-indexee), ligne de fin)
TARGETS = [
    ("controlled_coder.py", 57, 62),
    ("decision_agent.py",   16, 21),
]


def patch(path: Path, start: int, end: int):
    lines = path.read_text(encoding="utf-8").splitlines(keepends=False)

    # Verifications
    if start - 1 >= len(lines):
        print(f"  [KO] {path.name} : fichier trop court")
        return False
    if "try:" not in lines[start - 1]:
        print(f"  [KO] {path.name} : ligne {start} n'est pas 'try:' -> {lines[start-1]!r}")
        return False
    if "sys.exit(2)" not in lines[end - 1]:
        print(f"  [KO] {path.name} : ligne {end} n'est pas 'sys.exit(2)' -> {lines[end-1]!r}")
        return False

    # Backup
    backup = path.with_suffix(path.suffix + f".before-lazyv3-{STAMP}")
    shutil.copy2(path, backup)
    print(f"  [OK] backup : {backup.name}")

    # Remplacement
    new_lines = (
        lines[: start - 1]
        + NEW_BLOCK.splitlines()
        + lines[end:]
    )
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"  [OK] {path.name} : lignes {start}-{end} remplacees par bloc lazy")
    return True


def main():
    print("=" * 60)
    print(" APPLY LAZY FIX v3 (par numeros de ligne)")
    print("=" * 60)

    for name, start, end in TARGETS:
        p = ROOT / name
        if not p.exists():
            print(f"  [--] {name} absent")
            continue
        patch(p, start, end)
        print()

    # Verification : import sans MEMOLIBDEV_TARGET
    print("=" * 60)
    print(" VERIFICATION (sans MEMOLIBDEV_TARGET)")
    print("=" * 60)

    import os
    env = os.environ.copy()
    env.pop("MEMOLIBDEV_TARGET", None)

    for name in ["controlled_coder.py", "decision_agent.py", "agent_loop.py"]:
        module = name.replace(".py", "")
        r = subprocess.run(
            [sys.executable, "-c", f"import {module}; print('OK')"],
            cwd=ROOT, capture_output=True, text=True, timeout=15, env=env,
        )
        status = "OK" if r.returncode == 0 else "ECHEC"
        print(f"  [{status}] import {module}")
        if r.returncode != 0:
            err = (r.stderr or "").splitlines()
            print("       ", err[-1] if err else "")


if __name__ == "__main__":
    main()
