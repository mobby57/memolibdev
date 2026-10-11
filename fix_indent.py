# fix_indent.py — Reindente les verbes ajoutes dans ANALYSER
import re
from pathlib import Path

F = Path("mission_intent.py")
src = F.read_text(encoding="utf-8")

# Trouve le bloc ANALYSER
pat = re.compile(r'("ANALYSER"\s*:\s*\()([^)]+)(\))', re.DOTALL)
m = pat.search(src)

if not m:
    print("[KO] Bloc introuvable")
    raise SystemExit(1)

# Determine l'indentation dominante du bloc existant
lines = m.group(2).splitlines()
indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
if not indents:
    print("[KO] Bloc vide")
    raise SystemExit(1)
# Prend l'indent max (les continuations sont indentees)
target_indent = max(indents)
indent = " " * target_indent

# Reindente chaque ligne du bloc
new_lines = []
for line in lines:
    stripped = line.strip()
    if stripped:
        new_lines.append(indent + stripped)
    else:
        new_lines.append(line)

new_block = m.group(1) + "\n".join(new_lines) + m.group(3)
src = src[:m.start()] + new_block + src[m.end():]

F.write_text(src, encoding="utf-8")
print(f"[OK] {F.name} reindente (indent={target_indent} espaces)")
