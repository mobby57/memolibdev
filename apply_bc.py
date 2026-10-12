# apply_bc.py — Applique B (modele 7b) + C (eslint clean)
import os, re, subprocess, sys, shutil
from pathlib import Path

DEV = Path(r"C:\Users\moros\MemoLibDev\v3")
MEMOLIB = Path(r"C:\Users\moros\Desktop\memolib")

def title(msg): print(f"\n{'=' * 60}\n {msg}\n{'=' * 60}")
def ok(msg):    print(f"  [OK] {msg}")
def ko(msg):    print(f"  [KO] {msg}")
def info(msg):  print(f"  [..] {msg}")
def warn(msg):  print(f"  [!!] {msg}")

def run(cmd, cwd, timeout=180):
    try:
        r = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=timeout, shell=False)
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"TIMEOUT {timeout}s"
    except FileNotFoundError as e:
        return 127, "", str(e)

def run_shell(cmd, cwd, timeout=180):
    try:
        r = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=timeout, shell=True)
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"TIMEOUT {timeout}s"

# ==================================================================
# B — Modele 7b dans decision_agent.py
# ==================================================================
def fix_b():
    title("B — decision_agent.py : modele 3b -> 7b")

    f = DEV / "decision_agent.py"
    if not f.exists():
        ko(f"{f.name} introuvable")
        return False

    src = f.read_text(encoding="utf-8")

    OLD = 'MODEL = "hf.co/bartowski/Qwen2.5-3B-Instruct-GGUF:Q4_K_M"'
    NEW = 'MODEL = "qwen2.5-coder:7b"'

    if NEW in src and OLD not in src:
        ok("Deja patche (modele 7b)")
        return True

    if OLD not in src:
        warn("Ligne MODEL introuvable")
        for i, line in enumerate(src.splitlines(), 1):
            if "MODEL" in line and "=" in line:
                print(f"    {i}: {line}")
        return False

    # Backup
    backup = f.with_suffix(f.suffix + ".before-model7b")
    shutil.copy2(f, backup)
    ok(f"Backup : {backup.name}")

    # Patch
    src = src.replace(OLD, NEW, 1)
    f.write_text(src, encoding="utf-8")
    ok(f"{f.name} : MODEL -> qwen2.5-coder:7b")

    # Verif import
    code, out, err = run([sys.executable, "-c",
                          "import decision_agent; print(decision_agent.MODEL)"],
                         cwd=DEV, timeout=15)
    if code == 0:
        ok(f"Import OK, MODEL = {out.strip()}")
    else:
        warn(f"Import code={code}: {err[:100]}")
        return False

    return True


# ==================================================================
# C — ESLint cleanup dans memolib
# ==================================================================
def fix_c():
    title("C — ESLint cleanup dans memolib")

    if not MEMOLIB.exists():
        warn(f"{MEMOLIB} introuvable")
        return False

    # 1. Git status
    code, out, _ = run(["git", "status", "--short"], cwd=MEMOLIB)
    if out.strip():
        info(f"Fichiers non commites :")
        for line in out.strip().splitlines()[:5]:
            print(f"    {line}")
    else:
        ok("Working tree propre")

    # 2. ESLint --fix
    info("npm run lint -- --fix (peut prendre 1-2 min)")
    code, out, err = run_shell("npm run lint -- --fix", cwd=MEMOLIB, timeout=300)
    print(f"  exit={code}")

    # 3. Verifier
    info("npm run lint")
    code, out, err = run_shell("npm run lint", cwd=MEMOLIB, timeout=300)
    print(out[-500:] if out else "(vide)")

    if code == 0:
        ok("ESLint : 0 problems")
        return True
    else:
        warn(f"ESLint code={code}")
        return False


# ==================================================================
# Commit B
# ==================================================================
def commit_b():
    title("Commit B")
    run(["git", "add", "decision_agent.py"], cwd=DEV)
    code, out, err = run(["git", "commit", "-m",
                          "fix(decision): modele 7b (meilleure conformite)"],
                         cwd=DEV)
    if code == 0:
        ok("Commit OK")
        code, _, err = run(["git", "push"], cwd=DEV)
        ok("Push OK") if code == 0 else warn(f"Push code={code}")
    else:
        warn(f"Commit : {err[:100]}")


# ==================================================================
# Commit C
# ==================================================================
def commit_c():
    title("Commit C")
    code, out, _ = run(["git", "status", "--short"], cwd=MEMOLIB)
    if not out.strip():
        ok("Rien a commiter")
        return
    run(["git", "add", "-A"], cwd=MEMOLIB)
    code, out, err = run(["git", "commit", "-m",
                          "chore: remove unused eslint-disable directives"],
                         cwd=MEMOLIB)
    if code == 0:
        ok("Commit OK")
        code, _, err = run(["git", "push"], cwd=MEMOLIB)
        ok("Push OK") if code == 0 else warn(f"Push code={code}")
    else:
        warn(f"Commit : {err[:100]}")


# ==================================================================
# MAIN
# ==================================================================
def main():
    print("=" * 60)
    print(" APPLY B + C")
    print("=" * 60)

    b_ok = fix_b()
    c_ok = fix_c()

    print(f"\n B (modele 7b) : {'OK' if b_ok else 'KO'}")
    print(f" C (eslint)    : {'OK' if c_ok else 'KO'}")

    ans = input("\n Commit et push B puis C ? (oui/non) : ").strip().lower()
    if ans != "oui":
        print(" Abandon.")
        return

    if b_ok:
        commit_b()
    if c_ok:
        commit_c()

    print("\n" + "=" * 60)
    print(" TERMINE")
    print("=" * 60)


if __name__ == "__main__":
    main()