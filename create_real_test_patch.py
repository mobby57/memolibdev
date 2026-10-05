from pathlib import Path
import difflib

ROOT = Path(r"C:\Users\moros\Desktop\memolib")
SOURCE = ROOT / "src/__init__.py"
OUTPUT = Path(r"C:\Users\moros\MemoLibDev\v3\patches\real-memolib-test.diff")

if not SOURCE.exists():
    raise SystemExit(f"ERREUR : fichier introuvable : {SOURCE}")

original = SOURCE.read_text(encoding="utf-8")

if not original.endswith("\n"):
    original += "\n"

modified = original + "# MemoLibDev V3 PATCH TEST - NON APPLIQUÉ\n"

diff = difflib.unified_diff(
    original.splitlines(keepends=True),
    modified.splitlines(keepends=True),
    fromfile="a/src/__init__.py",
    tofile="b/src/__init__.py"
)

patch = "".join(diff)

if not patch:
    raise SystemExit("ERREUR : aucun patch généré")

OUTPUT.write_text(patch, encoding="utf-8")

print("Patch créé :", OUTPUT)
print()
print(patch)
