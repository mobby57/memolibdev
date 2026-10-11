# fix_context_explicit_v3.py — Corrige le nom du champ preview
import shutil, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
F = ROOT / "context" / "context_builder.py"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

src = F.read_text(encoding="utf-8")

# Cherche le bloc v2 (avec content=)
old = '''            # Methode 1 : dataclasses.replace sur le template
            if _dc.is_dataclass(template):
                try:
                    new_obj = _dc.replace(
                        template,
                        path=p,
                        content=content,
                        size=full.stat().st_size,
                    )
                except Exception:
                    new_obj = None

            # Methode 2 : type(template) avec **vars()
            if new_obj is None:
                try:
                    fields = vars(template).copy()
                    fields.update({
                        "path": p,
                        "content": content,
                        "size": full.stat().st_size,
                    })
                    new_obj = type(template)(**fields)
                except Exception:
                    new_obj = None

            # Methode 3 : SimpleNamespace en dernier recours
            if new_obj is None:
                from types import SimpleNamespace
                new_obj = SimpleNamespace(
                    path=p, content=content,
                    size=full.stat().st_size,
                )'''

new = '''            # InspectedFile est une dataclass frozen :
            #   path: str, size: int, preview: str
            # Le contenu complet va dans "preview" (utilise par le scoring).
            try:
                new_obj = _dc.replace(
                    template,
                    path=p,
                    size=full.stat().st_size,
                    preview=content,
                )
            except Exception:
                # Fallback : SimpleNamespace avec les memes champs
                from types import SimpleNamespace
                new_obj = SimpleNamespace(
                    path=p,
                    size=full.stat().st_size,
                    preview=content,
                )'''

if old not in src:
    print("[KO] Bloc v2 introuvable")
    print("     Verifie que fix_context_explicit_v2.py a bien tourne")
    sys.exit(1)

backup = F.with_suffix(F.suffix + f".before-v3-{STAMP}")
shutil.copy2(F, backup)
print(f"[OK] Backup : {backup.name}")

src = src.replace(old, new, 1)
F.write_text(src, encoding="utf-8")
print(f"[OK] {F.name} patche v3 (champ preview)")
