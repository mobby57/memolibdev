# fix_domains_security.py — Ajoute SECURITE et DATA aux domaines
import re, shutil, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
F = ROOT / "mission_intent.py"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

src = F.read_text(encoding="utf-8")

# Vérifier si SECURITE existe déjà
if '"SECURITE"' in src or "'SECURITE'" in src:
    print("[--] Domaine SECURITE deja present")
    # Cherche sa liste actuelle
    m = re.search(r'"SECURITE"\s*:\s*\(([^)]+)\)', src, re.DOTALL)
    if m:
        print("Liste actuelle SECURITE :")
        print(m.group(1)[:200])
    sys.exit(0)

# Ajoute un domaine SECURITE s'il n'existe pas
# On cherche le dict _DOMAINES
m = re.search(r'(_DOMAINES\s*=\s*\{)(.*?)(\n\})', src, re.DOTALL)
if not m:
    print("[KO] _DOMAINES introuvable")
    sys.exit(1)

NEW_DOMAIN = '''
    "SECURITE": ("securite", "sécurité", "security", "auth", "authentification",
                 "isolation", "zero-trust", "zero trust", "anonymisation",
                 "anonymiser", "anonymise", "chiffrement", "encryption",
                 "rgpd", "gdpr", "pii", "confidentialite", "confidentialité",
                 "permission", "rbac", "tenant", "tenant-isolation",
                 "sanitize", "sanitization", "injection", "xss", "csrf",
                 "guard", "guardrail", "protect", "protection",
                 "secret", "secrets", "credentials", "token"),
'''

# Insère avant la dernière entrée du dict
content = m.group(2)
# Retire le dernier \n
content_rstripped = content.rstrip()
# Ajoute notre domaine
new_content = content_rstripped + "\n" + NEW_DOMAIN

src = src[:m.start(2)] + new_content + src[m.end(2):]

backup = F.with_suffix(F.suffix + f".before-securite-{STAMP}")
shutil.copy2(F, backup)
print(f"[OK] Backup : {backup.name}")

F.write_text(src, encoding="utf-8")
print(f"[OK] {F.name} patche (domaine SECURITE ajoute)")
