# audit_sys_exit.py — Trouve les sys.exit() au module-level
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKIP = {".venv", "venv", "__pycache__", ".git", "_backups"}

print("=" * 70)
print(" AUDIT sys.exit() au module-level")
print("=" * 70)

found = 0
for p in sorted(ROOT.glob("*.py")):
    if any(part in p.parts for part in SKIP):
        continue
    if ".pre-" in p.name or ".before-" in p.name:
        continue
    try:
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        continue
    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        if "sys.exit(" in line and indent == 0:
            print(f"  {p.name}:{i}  {line.strip()[:80]}")
            found += 1

print()
print(f"  {found} occurrence(s) trouvee(s)")
