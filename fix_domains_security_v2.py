# fix_domains_security_v2.py — Enrichit la liste SECURITE existante
import re, shutil, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
F = ROOT / "mission_intent.py"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

src = F.read_text(encoding="utf-8")

# Termes a ajouter
NEW_TERMS = [
    "isolation", "zero-trust", "zero trust", "anonymisation",
    "anonymiser", "anonymise", "anonymized", "pii",
    "confidentialite", "confidentialité", "privacy",
    "tenant", "tenant-isolation", "multi-tenant",
    "token", "tokens", "sanitize", "sanitization",
    "injection", "xss", "csrf", "guard", "guardrail",
    "protect", "protection", "permission", "permissions",
    "rbac", "authorization", "autorisation",
    "zero-trust architecture", "trust boundary",
]

# Trouve le bloc SECURITE
m = re.search(
    r'("SECURITE"\s*:\s*\()([^)]+)(\))',
    src, re.DOTALL,
)
if not m:
    print("[KO] Bloc SECURITE introuvable")
    sys.exit(1)

current = m.group(2)

# Verifie quels termes manquent
missing = []
for t in NEW_TERMS:
    if f'"{t}"' not in current and f"'{t}'" not in current:
        missing.append(t)

if not missing:
    print("[--] Tous les termes sont deja presents")
    sys.exit(0)

print(f"[..] Termes a ajouter ({len(missing)}) :")
for t in missing[:10]:
    print(f"     + {t}")
if len(missing) > 10:
    print(f"     ... +{len(missing)-10} autres")

# Reconstruit le bloc
lines = current.splitlines()
indent = "                 "
for line in lines:
    if line.strip():
        indent = " " * (len(line) - len(line.lstrip()))
        break

# Derniere ligne non vide : retire la virgule finale
last_idx = -1
for i in range(len(lines)-1, -1, -1):
    if lines[i].strip():
        last_idx = i
        break

new_lines = lines[:last_idx]
last_line = lines[last_idx].rstrip()
if last_line.endswith(","):
    last_line = last_line[:-1]
new_lines.append(last_line + ",")

# Ajoute les nouveaux termes
for t in missing:
    new_lines.append(f'{indent}"{t}",')

# Retire la derniere virgule
new_lines[-1] = new_lines[-1].rstrip(",")

new_content = "\n".join(new_lines) + "\n"

new_block = m.group(1) + new_content + m.group(3)
src = src[:m.start()] + new_block + src[m.end():]

backup = F.with_suffix(F.suffix + f".before-securite2-{STAMP}")
shutil.copy2(F, backup)
print(f"\n[OK] Backup : {backup.name}")

F.write_text(src, encoding="utf-8")
print(f"[OK] {F.name} patche (SECURITE enrichi)")
