# auto_fix.py — version corrigee
import re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INTENT = ROOT / "mission_intent.py"
CHECK = ROOT / "check_fixes.py"
BACKUP = ROOT / "mission_intent.py.before-term-pattern"

CHECK_CODE = r"""# check_fixes.py
import sys
from mission_intent import _match_category
from analysis_builder import _BEHAVIORAL_CATEGORIES

TABLE = {
    "UI":     ("ui",),
    "AUTH":   ("auth*",),
    "ROUTES": ("route*", "middleware"),
    "DOC":    ("documentation", "doc"),
    "TESTS":  ("test*",),
}

CASES_A = [
    ("Verifier si le domaine UI est impose",           "UI"),
    ("Analyser le resultat issu de la classification", "UNKNOWN"),
    ("Documente le module auth",                       "AUTH"),
    ("Corrige le bug du middleware",                   "ROUTES"),
    ("Analyse la documentation du projet",             "DOC"),
    ("Le fichier est issu du test",                    "TESTS"),
    ("Ceci est puis",                                  "UNKNOWN"),
    ("Il suis la route",                               "ROUTES"),
    ("Le resultat est issu du calcul",                 "UNKNOWN"),
    ("Regarde le uikit",                               "UNKNOWN"),
]

ko_a = 0
for text, expected in CASES_A:
    got = _match_category(text, TABLE)
    ok = (got == expected)
    if not ok: ko_a += 1
    print(f"  [{'OK' if ok else 'KO'}] {text!r} -> {got} (attendu {expected})")
print(f"  -> {len(CASES_A) - ko_a}/{len(CASES_A)} OK")

REQUIRED_B = {"REDIRECT","ROUTE","CONDITION","ERROR_HANDLING","LOCALE","DEFINITION","DOC_HEADING"}
current = set(_BEHAVIORAL_CATEGORIES)
missing = REQUIRED_B - current
extra   = current - REQUIRED_B
print(f"  MANQUANT : {sorted(missing)}")
print(f"  EN TROP  : {sorted(extra)}")
sys.exit(0 if (ko_a == 0 and not missing and not extra) else 1)
"""

TERM_HELPER = '''

def _term_pattern(term: str) -> str:
    """Mot entier par defaut, prefixe si le terme finit par '*'."""
    if term.endswith("*"):
        return r"\\b" + re.escape(term[:-1])
    return r"\\b" + re.escape(term) + r"\\b"
'''

OLD_REGEX = 'if re.search(r"\\b" + re.escape(term), text):'
NEW_REGEX = 'if re.search(_term_pattern(term), text, flags=re.IGNORECASE):'
TERM_STAR_MAP = {"auth": "auth*", "route": "route*", "test": "test*"}

def run(cmd): return subprocess.run(cmd, cwd=ROOT, text=True)
def step(msg): print("\n" + "="*60 + f"\n {msg}\n" + "="*60)

def patch_intent():
    step("1) Patch de mission_intent.py")
    if not INTENT.exists():
        print(f"  [KO] {INTENT} introuvable"); return False
    src = INTENT.read_text(encoding="utf-8")
    shutil.copy2(INTENT, BACKUP)
    print(f"  -> backup : {BACKUP.name}")

    # import re
    if not re.search(r"^\s*import\s+re\b", src, flags=re.MULTILINE):
        m = re.search(r"^(import .+|from .+ import .+)$", src, flags=re.MULTILINE)
        src = (src[:m.end()] + "\nimport re" + src[m.end():]) if m else ("import re\n" + src)
        print("  -> import re ajoute")

    # helper
    if "_term_pattern" not in src:
        idx = src.find("def _match_category")
        if idx == -1:
            print("  [KO] _match_category introuvable"); return False
        src = src[:idx] + TERM_HELPER.lstrip("\n") + "\n\n" + src[idx:]
        print("  -> helper _term_pattern ajoute")

    # regex
    if OLD_REGEX in src:
        src = src.replace(OLD_REGEX, NEW_REGEX)
        print("  -> regex remplacee")
    elif NEW_REGEX in src:
        print("  -> regex deja patchee")
    else:
        m = re.search(r'if\s+re\.search\(r"\\\\b"\s*\+\s*re\.escape\(term\)[^:]*\):', src)
        if m:
            src = src.replace(m.group(0), NEW_REGEX)
            print("  -> regex remplacee (fallback)")
        else:
            print("  [KO] ligne regex introuvable"); return False

    INTENT.write_text(src, encoding="utf-8")
    return True

def update_table():
    step("2) Mise a jour table TABLE (term*)")
    src = INTENT.read_text(encoding="utf-8")
    changed = False
    for old_term, new_term in TERM_STAR_MAP.items():
        pattern = r'"' + re.escape(old_term) + r'"'
        if re.search(pattern + r"(?!\*)", src):
            src = re.sub(pattern + r"(?!\*)", f'"{new_term}"', src)
            print(f"  -> '{old_term}' -> '{new_term}'")
            changed = True
    if changed:
        INTENT.write_text(src, encoding="utf-8")
        print("  -> TABLE mise a jour")
    else:
        print("  -> rien a changer")

def write_check():
    step("3) Ecriture de check_fixes.py")
    CHECK.write_text(CHECK_CODE, encoding="utf-8")
    print(f"  -> {CHECK.name} ecrit")

def run_check():
    step("4) Execution des tests")
    return run([sys.executable, str(CHECK)]).returncode == 0

def git_status():
    step("5) Etat Git")
    run(["git", "status", "--short"])
    run(["git", "diff", "--stat"])

def rollback():
    step("Rollback")
    if BACKUP.exists():
        shutil.copy2(BACKUP, INTENT)
        BACKUP.unlink()
        print("  -> mission_intent.py restaure")

def main():
    if not patch_intent():
        sys.exit(1)
    update_table()
    write_check()
    if not run_check():
        print("\n[!] Tests en echec apres patch.")
        if input("Rollback ? (O/n) : ").strip().lower() not in ("n", "non", "no"):
            rollback()
        sys.exit(1)
    git_status()
    print("\nTermine.")

if __name__ == "__main__":
    main()
