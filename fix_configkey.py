# fix_configkey.py — Resserre le pattern CONFIG_KEY
import re, shutil, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
F = ROOT / "analysis_builder.py"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

src = F.read_text(encoding="utf-8")

OLD = '''    ("CONFIG_KEY", re.compile(
        r"^\\s*[\\"']?[A-Za-z0-9_.-]+[\\"']?\\s*[:=]\\s*", )),'''

NEW = '''    ("CONFIG_KEY", re.compile(
        # Ne matche que les VRAIES cles de config :
        #   UPPER_SNAKE = ... / "key": "value" / KEY: valeur
        r"^\\s*(?:[\\"'][A-Za-z_][A-Za-z0-9_-]*[\\"']\\s*:|"
        r"[A-Z][A-Z0-9_]{2,}\\s*[:=])", )),'''

if NEW.split("\n")[1] in src:
    print("[--] Deja patche")
    sys.exit(0)

if OLD not in src:
    print("[KO] Bloc CONFIG_KEY introuvable")
    m = re.search(r'\("CONFIG_KEY".*?\),', src, re.DOTALL)
    if m:
        print("Bloc actuel :")
        print(m.group(0))
    sys.exit(1)

backup = F.with_suffix(F.suffix + f".before-configkey-{STAMP}")
shutil.copy2(F, backup)
print(f"[OK] Backup : {backup.name}")

src = src.replace(OLD, NEW, 1)
F.write_text(src, encoding="utf-8")
print("[OK] CONFIG_KEY resserre")
