# find_blocker.py — Detecte les motifs qui bloquent les tests
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATTERNS = {
    "input()":            r"\binput\s*\(",
    "while True":         r"while\s+True\s*:",
    "time.sleep long":    r"time\.sleep\s*\(\s*\d{2,}",
    "requests.get/post":  r"requests\.(get|post|put|delete)\s*\(",
    "socket":             r"\bsocket\.\w+",
    "http.client":        r"http\.client",
    "urlopen":            r"urlopen\s*\(",
    "subprocess":         r"subprocess\.\w+\s*\(",
    "os.system":          r"os\.system\s*\(",
    "asyncio.run":        r"asyncio\.run\s*\(",
}

hits = {k: [] for k in PATTERNS}
SKIP = {".venv", "venv", "__pycache__", ".git", "node_modules", ".pytest_cache"}

for py in ROOT.rglob("*.py"):
    if any(part in py.parts for part in SKIP):
        continue
    try:
        lines = py.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        continue
    for i, line in enumerate(lines, 1):
        for name, pat in PATTERNS.items():
            if re.search(pat, line):
                hits[name].append((py.relative_to(ROOT), i, line.strip()))

for name, items in hits.items():
    if not items:
        continue
    print(f"\n=== {name} ({len(items)}) ===")
    for path, ln, line in items[:15]:
        print(f"  {path}:{ln}  {line[:90]}")
    if len(items) > 15:
        print(f"  ... +{len(items)-15} autres")
