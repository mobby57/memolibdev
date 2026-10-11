# check_fixes.py
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
