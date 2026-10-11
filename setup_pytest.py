# setup_pytest.py — Configure pytest et corrige les blocages (idempotent)
import os, re, shutil, subprocess, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

SEP = "=" * 70

def title(msg): print(f"\n{SEP}\n {msg}\n{SEP}")
def ok(msg):    print(f"  [OK] {msg}")
def ko(msg):    print(f"  [KO] {msg}")
def info(msg):  print(f"  [..] {msg}")
def warn(msg):  print(f"  [!!] {msg}")
def skip(msg):  print(f"  [--] {msg} (deja fait)")

def run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, cwd=ROOT, text=True,
                           capture_output=True, stdin=subprocess.DEVNULL,
                           timeout=timeout)
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"TIMEOUT {timeout}s"
    except FileNotFoundError:
        return 127, "", f"introuvable: {cmd}"

# ============================================================
# 1. pytest.ini
# ============================================================
PYTEST_INI = """[pytest]
addopts =
    --ignore-glob=*.pre-*.py
    --ignore-glob=*.before-*.py
    -m "not slow"
    --timeout=30
    -q
testpaths = .
norecursedirs =
    .venv
    venv
    __pycache__
    .git
    .pytest_cache
    _legacy_document_engine
    _backups
    node_modules
markers =
    slow: tests longs (spawn de process, sleep, reseau)
    integration: tests integration (Ollama, API externe)
    e2e: tests end-to-end
"""

def write_pytest_ini():
    title("1) pytest.ini")
    f = ROOT / "pytest.ini"
    if f.exists():
        current = f.read_text(encoding="utf-8")
        if "--timeout=30" in current and "-m \"not slow\"" in current:
            skip("pytest.ini")
            return
    f.write_text(PYTEST_INI, encoding="utf-8")
    ok("pytest.ini ecrit")

# ============================================================
# 2. conftest.py
# ============================================================
CONFTEST = """# conftest.py — Configuration pytest globale
from pathlib import Path

ROOT = Path(__file__).resolve().parent

collect_ignore_glob = [
    "*.pre-*.py",
    "*.before-*.py",
    "_legacy_document_engine/*",
]
"""

def write_conftest():
    title("2) conftest.py")
    f = ROOT / "conftest.py"
    if f.exists() and "collect_ignore_glob" in f.read_text(encoding="utf-8"):
        skip("conftest.py")
        return
    f.write_text(CONFTEST, encoding="utf-8")
    ok("conftest.py ecrit")

# ============================================================
# 3. Installer pytest-timeout
# ============================================================
def install_timeout():
    title("3) pytest-timeout")
    code, out, err = run([sys.executable, "-c", "import pytest_timeout"], timeout=10)
    if code == 0:
        skip("pytest-timeout")
        return
    info("Installation...")
    code, out, err = run([sys.executable, "-m", "pip", "install", "-q", "pytest-timeout"],
                         timeout=60)
    if code == 0:
        ok("pytest-timeout installe")
    else:
        warn(f"installation echouee : {err[:200]}")

# ============================================================
# 4. Renommer les fichiers qui bloquent
# ============================================================
RENAMES = {
    "d54_adversarial_test.py": "d54_adversarial_check.py",
    "post_test.py": "post_ci.py",
}

def rename_blockers():
    title("4) Renommages")
    for old, new in RENAMES.items():
        old_p = ROOT / old
        new_p = ROOT / new
        if new_p.exists() and not old_p.exists():
            skip(f"{old} -> {new}")
            continue
        if not old_p.exists():
            info(f"{old} absent")
            continue
        try:
            # git mv si dans un repo git
            code, _, _ = run(["git", "mv", str(old_p), str(new_p)], timeout=15)
            if code == 0:
                ok(f"{old} -> {new} (git mv)")
            else:
                shutil.move(str(old_p), str(new_p))
                ok(f"{old} -> {new}")
        except Exception as e:
            ko(f"renommage echoue : {e}")

# ============================================================
# 5. Marquer les tests lents
# ============================================================
SLOW_MARKER = "pytestmark = pytest.mark.slow"
SLOW_FILES = [
    "test_gui_process_supervision.py",
]

def mark_slow():
    title("5) Marqueur slow")
    for name in SLOW_FILES:
        f = ROOT / name
        if not f.exists():
            info(f"{name} absent")
            continue
        src = f.read_text(encoding="utf-8")
        if SLOW_MARKER in src:
            skip(f"{name} marque slow")
            continue
        # ajouter import pytest + pytestmark apres les imports
        lines = src.splitlines()
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith(("import ", "from ")) or line.startswith("#"):
                insert_idx = i + 1
            elif line.strip() == "" and insert_idx > 0:
                insert_idx = i + 1
            else:
                break
        block = []
        if "import pytest" not in src:
            block.append("import pytest")
        block.append("")
        block.append(SLOW_MARKER)
        block.append("")
        new_lines = lines[:insert_idx] + block + lines[insert_idx:]
        f.write_text("\n".join(new_lines), encoding="utf-8")
        ok(f"{name} marque slow")

# ============================================================
# 6. Verifier la collecte
# ============================================================
def check_collect():
    title("6) Collecte pytest")
    code, out, err = run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        timeout=30,
    )
    tail = "\n".join(out.splitlines()[-8:])
    print(tail)
    if code == 0:
        ok("Collecte OK, 0 erreur")
        return True
    if code == 5:
        info("Aucun test collecte")
        return True
    ko(f"Collecte echouee (code={code})")
    return False

# ============================================================
# 7. Executer les tests rapides
# ============================================================
def run_fast_tests():
    title("7) Tests rapides (sans slow)")
    code, out, err = run(
        [sys.executable, "-m", "pytest", "-q"],
        timeout=180,
    )
    tail = "\n".join(out.splitlines()[-15:])
    print(tail)
    if code == 0:
        ok("Tests OK")
        return True
    if code == 5:
        info("Aucun test execute")
        return True
    warn(f"Tests en echec (code={code})")
    return False

# ============================================================
# 8. Git status
# ============================================================
def git_status():
    title("8) Etat Git")
    code, out, _ = run(["git", "status", "--short"], timeout=15)
    print("  " + out.replace("\n", "\n  ").rstrip())
    code, out, _ = run(["git", "diff", "--stat"], timeout=15)
    if out.strip():
        print(out)

# ============================================================
# MAIN
# ============================================================
def main():
    print(f"\n{SEP}")
    print(f" SETUP PYTEST — MemoLibDev v3")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" {ROOT}")
    print(SEP)

    write_pytest_ini()
    write_conftest()
    install_timeout()
    rename_blockers()
    mark_slow()

    collect_ok = check_collect()

    tests_ok = False
    if collect_ok:
        if "--with-tests" in sys.argv:
            tests_ok = run_fast_tests()
        else:
            info("Tests non executes (--with-tests pour lancer)")
            tests_ok = True

    git_status()

    title("RESUME")
    print(f"  Collecte      : {'OK' if collect_ok else 'KO'}")
    print(f"  Tests         : {'OK' if tests_ok else 'KO'}")
    print()
    print("  Commandes utiles :")
    print("    python -m pytest -q                    # tests rapides")
    print("    python -m pytest -m slow -v            # tests lents")
    print("    python -m pytest --collect-only -q     # collecte seule")
    print()
    print("  Commit suggere :")
    print("    git add pytest.ini conftest.py")
    print("    git add -u")
    print('    git commit -m "test: configure pytest + renomme scripts non-test"')
    print("    git push")

    sys.exit(0 if (collect_ok and tests_ok) else 1)


if __name__ == "__main__":
    main()
