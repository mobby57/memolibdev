# fix_analyser_verbs.py — Ajoute les infinitifs manquants au bloc ANALYSER
import re, shutil, sys, subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
F = ROOT / "mission_intent.py"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

# Infinitifs manquants a ajouter
NEW_VERBS = [
    "auditer", "examiner", "diagnostiquer", "inspecter",
    "controler", "contrôler", "surveiller",
    "vérifier",  # avec accent
    "analyser",  # deja present mais on verifie
    "evaluer", "évaluer",  # deja
    "scanner", "passer en revue",
    "revoir", "reviser", "réviser",
]

src = F.read_text(encoding="utf-8")
original = src

# Trouve le bloc "ANALYSER": (...)
pat = re.compile(
    r'("ANALYSER"\s*:\s*\()([^)]+)(\))',
    re.DOTALL,
)

m = pat.search(src)
if not m:
    print("[KO] Bloc 'ANALYSER': (...) introuvable")
    sys.exit(1)

current = m.group(2)
print("=" * 60)
print(" Verbes ANALYSER actuels (extrait) :")
print("=" * 60)
print(current[:400])
print("...")

# Trouve les verbes manquants
missing = []
for v in NEW_VERBS:
    # Cherche le mot entre guillemets dans le bloc
    if f'"{v}"' not in current and f"'{v}'" not in current:
        missing.append(v)

if not missing:
    print()
    print("[OK] Tous les verbes sont deja presents")
    sys.exit(0)

print()
print(f" Verbes a ajouter ({len(missing)}) :")
for v in missing:
    print(f"   + {v}")

answer = input("\nAppliquer le patch ? (oui/non) : ").strip().lower()
if answer != "oui":
    print("Abandon.")
    sys.exit(0)

# Backup
backup = F.with_suffix(F.suffix + f".before-verbpatch-{STAMP}")
shutil.copy2(F, backup)
print(f"[OK] Backup : {backup.name}")

# Construction du nouveau contenu
# On garde l'indentation existante en detectant le prefixe de chaque ligne
lines = current.splitlines()

# Trouver l'indentation de la 1re ligne non vide
indent = "    "  # defaut
for line in lines:
    if line.strip():
        indent = " " * (len(line) - len(line.lstrip()))
        break

# Trouver la derniere ligne non vide et retirer sa virgule finale
last_idx = -1
for i in range(len(lines) - 1, -1, -1):
    if lines[i].strip():
        last_idx = i
        break

# Reconstruire : garder les lignes jusqu'a la derniere, la derniere sans virgule finale
new_lines = lines[:last_idx]
last_line = lines[last_idx].rstrip()
if last_line.endswith(","):
    last_line = last_line[:-1]
new_lines.append(last_line + ",")

# Ajouter les nouveaux verbes
for v in missing:
    new_lines.append(f'{indent}"{v}",')

new_content = "\n".join(new_lines) + "\n"

new_block = m.group(1) + new_content + m.group(3)
src = src[:m.start()] + new_block + src[m.end():]

F.write_text(src, encoding="utf-8")
print(f"[OK] {F.name} patche")

# Test
print()
print("=" * 60)
print(" Test apres patch")
print("=" * 60)

TESTS = [
    "Auditer l authentification OAuth",
    "Verifier l authentification Clerk",
    "Inspecter le module auth",
    "Examiner les routes API",
    "Analyse la documentation",
    "Corrige le bug du middleware",
    "Ajoute un commentaire JSDoc",
]

for text in TESTS:
    r = subprocess.run(
        [sys.executable, "-c",
         f"from mission_intent import analyze_mission; r = analyze_mission({text!r}); print(f'objectif={{r.objectif}} domaine={{r.domaine}}')"],
        cwd=ROOT, capture_output=True, text=True, timeout=15,
    )
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    result = out.splitlines()[-1] if out else (err.splitlines()[-1] if err else "?")
    print(f"  {text:<45} -> {result}")
