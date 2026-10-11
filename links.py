# links.py — Liste toutes les URLs du projet, groupees
import re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
SKIP = {".venv", "venv", "__pycache__", ".git", "node_modules", ".pytest_cache", "_backups"}

URL_RE = re.compile(r"https?://[^\s'\"`\)\]]+")

buckets = defaultdict(list)

for p in ROOT.rglob("*.py"):
    if any(part in p.parts for part in SKIP):
        continue
    if ".pre-" in p.name or ".before-" in p.name:
        continue  # ignorer les backups
    try:
        src = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for m in URL_RE.finditer(src):
        url = m.group(0)
        if "localhost" in url or "127.0.0.1" in url:
            buckets["LOCAL"].append((p.name, url))
        elif "github.com" in url:
            buckets["GITHUB"].append((p.name, url))
        else:
            buckets["EXTERNE"].append((p.name, url))

for cat in ("LOCAL", "GITHUB", "EXTERNE"):
    items = sorted(set(buckets[cat]))
    if not items:
        continue
    print(f"\n=== {cat} ({len(items)}) ===")
    seen = set()
    for fname, url in items:
        if url in seen:
            continue
        seen.add(url)
        print(f"  {url}  ({fname})")
