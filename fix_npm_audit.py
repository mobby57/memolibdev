# fix_npm_audit.py — Traite les vulnerabilites npm avec rollback
import subprocess, sys, shutil
from pathlib import Path
from datetime import datetime

MEMOLIB = Path(r"C:\Users\moros\Desktop\memolib")

def title(msg): print(f"\n{'=' * 60}\n {msg}\n{'=' * 60}")
def ok(msg):    print(f"  [OK] {msg}")
def ko(msg):    print(f"  [KO] {msg}")
def info(msg):  print(f"  [..] {msg}")
def warn(msg):  print(f"  [!!] {msg}")

def run_shell(cmd, timeout=300):
    try:
        r = subprocess.run(cmd, cwd=MEMOLIB, text=True, capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=timeout, shell=True,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"TIMEOUT {timeout}s"

def main():
    print("=" * 60)
    print(" FIX NPM AUDIT — memolib")
    print("=" * 60)

    # 0. Verifier working tree propre
    title("0) Verification working tree")
    code, out, _ = run_shell("git status --short")
    if out.strip():
        warn(f"Fichiers non commites :")
        for line in out.strip().splitlines()[:10]:
            print(f"    {line}")
        answer = input("  Continuer quand meme ? (oui/non) : ").strip().lower()
        if answer != "oui":
            print("  Abandon.")
            return
    else:
        ok("Working tree propre")

    # 1. Backup
    title("1) Backup")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for f in ["package.json", "package-lock.json"]:
        p = MEMOLIB / f
        if p.exists():
            backup = p.with_suffix(p.suffix + f".before-audit-{stamp}")
            shutil.copy2(p, backup)
            ok(f"Backup : {backup.name}")

    # 2. Audit initial
    title("2) npm audit (initial)")
    code, out, _ = run_shell("npm audit", timeout=120)
    print(out[:2000] if out else "(vide)")
    if "found 0 vulnerabilities" in out:
        ok("Deja 0 vulnerabilites")
        return

    # 3. Audit fix
    title("3) npm audit fix")
    info("Peut prendre 1-2 min")
    code, out, err = run_shell("npm audit fix", timeout=600)
    print(out[-1500:] if out else "(vide)")
    if err.strip():
        print(f"  stderr : {err[:300]}")

    # 4. Audit apres
    title("4) npm audit (apres)")
    code, out, _ = run_shell("npm audit", timeout=120)
    print(out[:1500] if out else "(vide)")

    # 5. Tests
    title("5) Non-regression")
    all_ok = True
    for label, cmd, timeout in [
        ("type-check", "npm run type-check", 300),
        ("lint",       "npm run lint",       300),
        ("test:ci",    "npm run test:ci",    600),
    ]:
        info(f"{label}...")
        code, out, err = run_shell(cmd, timeout=timeout)
        if code == 0:
            ok(f"{label} OK")
        else:
            ko(f"{label} code={code}")
            print(f"    {(out or err)[-300:]}")
            all_ok = False

    # 6. Decision
    title("6) Decision")
    if not all_ok:
        warn("Un test a echoue. Rollback ?")
        answer = input("  Rollback (oui/non) : ").strip().lower()
        if answer == "oui":
            for f in ["package.json", "package-lock.json"]:
                src = MEMOLIB / (f + f".before-audit-{stamp}")
                if src.exists():
                    shutil.copy2(src, MEMOLIB / f)
                    ok(f"Restaure : {f}")
            info("Relance 'npm install' pour synchroniser :")
            print("    cd C:\\Users\\moros\\Desktop\\memolib")
            print("    npm install")
        return

    # 7. Commit
    title("7) Commit")
    code, out, _ = run_shell("git status --short")
    print(out.strip() if out.strip() else "(clean)")

    answer = input("\n  Commit + push ? (oui/non) : ").strip().lower()
    if answer != "oui":
        print("  Abandon. Les fichiers restent modifies localement.")
        return

    run_shell("git add package.json package-lock.json")
    code, out, err = run_shell('git commit -m "fix(deps): npm audit fix (vulnerabilites)"')
    if code == 0:
        ok("Commit OK")
        code, _, err = run_shell("git push")
        ok("Push OK") if code == 0 else warn(f"Push code={code}")
    else:
        warn(f"Commit : {err[:200]}")

    title("TERMINE")


if __name__ == "__main__":
    main()