# fix_facts_limits.py — Augmente les plafonds + ajoute des detecteurs
import re, shutil, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
F = ROOT / "analysis_builder.py"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

src = F.read_text(encoding="utf-8")

# 1) Augmenter les limites
changes = [
    ("_MAX_FACTS_PER_FILE = 6", "_MAX_FACTS_PER_FILE = 30"),
    ("_MAX_FACTS_TOTAL = 24", "_MAX_FACTS_TOTAL = 120"),
]

for old, new in changes:
    if new in src:
        print(f"[--] Deja : {new}")
        continue
    if old not in src:
        print(f"[KO] Introuvable : {old}")
        continue
    src = src.replace(old, new, 1)
    print(f"[OK] {old} -> {new}")

# 2) Ajouter detecteurs RETURN et REGEX + async/arrow functions
old_def = '''    ("DEFINITION", re.compile(
        r"^\\s*(async\\s+)?def\\s+\\w+\\s*\\(|^\\s*class\\s+\\w+"
        r"|^\\s*(export\\s+)?(async\\s+)?function\\s+\\w+\\s*\\(")),'''

new_def = '''    ("DEFINITION", re.compile(
        r"^\\s*(async\\s+)?def\\s+\\w+\\s*\\(|^\\s*class\\s+\\w+"
        r"|^\\s*(export\\s+)?(async\\s+)?function\\s+\\w+\\s*\\("
        r"|^\\s*(export\\s+)?(const|let|var)\\s+\\w+\\s*=\\s*(async\\s+)?\\("
        r"|^\\s*(export\\s+)?(const|let|var)\\s+\\w+\\s*=\\s*(async\\s+)?function")),
    ("RETURN", re.compile(r"^\\s*return\\b")),
    ("REGEX", re.compile(r"/[^/\\s][^/\\n]{2,}/[gimsuy]*")),'''

if new_def.split("\n")[0] in src and "RETURN" in src:
    print("[--] Detecteurs deja ajoutes")
elif old_def in src:
    src = src.replace(old_def, new_def, 1)
    print("[OK] Detecteurs DEFINITION/RETURN/REGEX ajoutes")
else:
    print("[KO] Bloc DEFINITION introuvable — detecteurs manuels requis")
    # Affiche le bloc actuel
    m = re.search(r'\("DEFINITION".*?\),', src, re.DOTALL)
    if m:
        print("Bloc actuel :")
        print(m.group(0)[:400])

# 3) Exclure les lignes JSDoc du DOC_LIST (eviter le bruit)
old_doclist = '("DOC_LIST", re.compile(r"^\\s*[-*+]\\s+\\S")),'
new_doclist = '("DOC_LIST", re.compile(r"^\\s*[-+]\\s+\\S|^\\*\\s+\\S")),'

if old_doclist in src and new_doclist not in src:
    src = src.replace(old_doclist, new_doclist, 1)
    print("[OK] DOC_LIST : exclut les JSDoc (` * ` avec espace initial)")
elif new_doclist in src:
    print("[--] DOC_LIST deja ajuste")

backup = F.with_suffix(F.suffix + f".before-facts-{STAMP}")
shutil.copy2(F, backup)
print(f"[OK] Backup : {backup.name}")

F.write_text(src, encoding="utf-8")
print(f"[OK] {F.name} patche")
