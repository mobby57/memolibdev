# doctor.py — Diagnostic MemoLibDev v3 (v2 securisee, ne bloque jamais)
import os, re, subprocess, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

SEP = "=" * 70
SUB = "-" * 70

def title(msg): print(f"\n{SEP}\n {msg}\n{SEP}")
def sub(msg):   print(f"\n{SUB}\n {msg}\n{SUB}")
def ok(msg):    print(f"  [OK] {msg}")
def ko(msg):    print(f"  [KO] {msg}")
def info(msg):  print(f"  [..] {msg}")
def warn(msg):  print(f"  [!!] {msg}")

def run(cmd, timeout=60):
    """Execute une commande avec timeout et stdin ferme. Ne bloque jamais."""
    try:
        r = subprocess.run(
            cmd, cwd=ROOT, text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            shell=isinstance(cmd, str),
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"TIMEOUT apres {timeout}s"
    except FileNotFoundError:
        return 127, "", f"commande introuvable: {cmd}"
    except Exception as e:
        return 1, "", f"erreur: {e}"

# ============================================================
def inventaire():
    title("1) INVENTAIRE PROJET")
    py_files = sorted(ROOT.glob("*.py"))
    test_files = sorted(ROOT.glob("test_*.py")) + sorted(ROOT.glob("*_test.py"))
    backups = sorted(ROOT.glob("*.before-*"))
    gi = ROOT / ".gitignore"
    ignored = []
    if gi.exists():
        ignored = [l.strip() for l in gi.read_text(encoding="utf-8").splitlines()
                   if l.strip() and not l.startswith("#")]
    print(f"  Fichiers .py        : {len(py_files)}")
    print(f"  Fichiers de test    : {len(test_files)}")
    print(f"  Backups (*.before-*): {len(backups)}")
    print(f"  Regles .gitignore   : {len(ignored)}")
    return py_files, test_files, backups

# ============================================================
def git_state():
    title("2) ETAT GIT")
    code, out, _ = run(["git", "status", "--short"], timeout=15)
    if out.strip():
        warn("Fichiers non commités :")
        print("    " + out.replace("\n", "\n    "))
    else:
        ok("Working tree propre")

    code, out, _ = run(["git", "log", "--oneline", "-5"], timeout=15)
    sub("5 derniers commits")
    print("    " + out.replace("\n", "\n    "))

    code, out, _ = run(["git", "branch", "-vv"], timeout=15)
    sub("Branche locale vs remote")
    print("    " + out.replace("\n", "\n    "))

# ============================================================
def check_fixes():
    title("3) VERIFICATION FIXES (A + B)")
    cf = ROOT / "check_fixes.py"
    if not cf.exists():
        ko("check_fixes.py introuvable")
        return False
    code, out, err = run([sys.executable, str(cf)], timeout=30)
    print(out)
    if err.strip():
        print("  stderr :", err)
    if code == 0:
        ok("Fix A + Fix B : OK")
        return True
    ko("Fix A ou Fix B en echec")
    return False

# ============================================================
def inspect_intent():
    title("4) INSPECTION mission_intent.py")
    f = ROOT / "mission_intent.py"
    if not f.exists():
        ko("mission_intent.py introuvable"); return
    src = f.read_text(encoding="utf-8")
    checks = [
        ("import re",            bool(re.search(r"^\s*import\s+re\b", src, re.M))),
        ("helper _term_pattern", "_term_pattern" in src),
        ("regex IGNORECASE",     "IGNORECASE" in src),
        ("term* : auth",         '"auth*"' in src),
        ("term* : route",        '"route*"' in src),
        ("term* : test",         '"test*"' in src),
    ]
    for label, cond in checks:
        (ok if cond else ko)(label)

# ============================================================
def inspect_builder():
    title("5) INSPECTION analysis_builder.py")
    f = ROOT / "analysis_builder.py"
    if not f.exists():
        ko("analysis_builder.py introuvable"); return
    src = f.read_text(encoding="utf-8")
    required = {"REDIRECT","ROUTE","CONDITION","ERROR_HANDLING",
                "LOCALE","DEFINITION","DOC_HEADING"}
    found = {c for c in required if f'"{c}"' in src}
    missing = required - found
    print(f"  Categories attendues : {len(required)}")
    print(f"  Categories trouvees  : {len(found)}")
    if missing:
        ko(f"MANQUANT : {sorted(missing)}")
    else:
        ok("_BEHAVIORAL_CATEGORIES complet")

# ============================================================
def run_tests(skip=False):
    title("6) TESTS PROJET")
    if skip:
        info("Etape ignoree (--skip-tests)")
        return True

    # Collecte seule, timeout court
    info("Collecte pytest (timeout 30s)...")
    code, out, err = run([sys.executable, "-m", "pytest", "--collect-only", "-q"],
                         timeout=30)
    if code == 124:
        warn("pytest --collect-only TIMEOUT — import bloquant")
        return False
    if code == 127:
        info("pytest non installe")
        return True
    if code == 5:
        info("pytest : aucun test collecte")
        return True
    if code != 0:
        warn(f"pytest --collect-only code={code}")
        print((out or err)[:400])
        return False

    nb = len([l for l in out.splitlines() if "::" in l])
    ok(f"pytest : {nb} test(s) collecte(s)")

    # Execution avec timeout, sans -x pour tout voir
    info("Execution pytest (timeout 90s)...")
    code, out, err = run([sys.executable, "-m", "pytest", "-q", "--no-header"],
                         timeout=90)
    if code == 124:
        warn("pytest : TIMEOUT (test bloquant)")
        return False
    if code == 0:
        ok("pytest : OK")
        print("\n".join(out.splitlines()[-3:]))
        return True
    warn(f"pytest : echecs (code={code})")
    print((out or err)[:800])
    return False

# ============================================================
def check_files():
    title("8) FICHIERS CLES")
    for name in ["mission_intent.py", "analysis_builder.py",
                 "check_fixes.py", ".gitignore"]:
        f = ROOT / name
        (ok if f.exists() else warn)(name)

# ============================================================
def cleanup_backups(dry_run=True):
    title(f"7) BACKUPS {'(simulation)' if dry_run else '(suppression)'}")
    backups = sorted(ROOT.glob("*.before-*"))
    if not backups:
        ok("Aucun backup a traiter"); return
    for b in backups:
        ts = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        size = b.stat().st_size
        print(f"  {ts}  {size:>7} o  {b.name}")
    if dry_run:
        info(f"{len(backups)} fichier(s) — relancer avec --cleanup pour supprimer")
    else:
        for b in backups:
            b.unlink()
        ok(f"{len(backups)} backup(s) supprime(s)")

# ============================================================
def main():
    clean   = "--cleanup"    in sys.argv
    skip    = "--skip-tests" in sys.argv or "--no-tests" in sys.argv

    print(f"\n{SEP}")
    print(f" DOCTOR — MemoLibDev v3")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" {ROOT}")
    print(f" Options : {'--cleanup ' if clean else ''}{'--skip-tests' if skip else ''}".rstrip())
    print(SEP)

    inventaire()
    git_state()
    fixes_ok = check_fixes()
    inspect_intent()
    inspect_builder()
    tests_ok = run_tests(skip=skip)
    check_files()
    cleanup_backups(dry_run=not clean)

    title("RESUME")
    print(f"  Fixes A+B       : {'OK' if fixes_ok else 'KO'}")
    print(f"  Tests projet    : {'OK' if tests_ok else 'KO'}{' (ignores)' if skip else ''}")
    print(f"  Mode cleanup    : {'oui' if clean else 'non (--cleanup pour supprimer)'}")

    if fixes_ok and tests_ok:
        print("\n  >>> ETAT GLOBAL : OK <<<")
        sys.exit(0)
    print("\n  >>> ETAT GLOBAL : A CORRIGER <<<")
    sys.exit(1)

if __name__ == "__main__":
    main()
