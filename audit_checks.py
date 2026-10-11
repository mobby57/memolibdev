# audit_checks.py — v3 (whitelist CI)
import subprocess, sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Scripts a tester en CI (autonomes, pas de reseau)
CI_CHECKS = [
    "api_facade_check.py",
]

# Scripts one-shot (a lancer manuellement, pas en CI)
ONE_SHOT = [
    "d54_adversarial_check.py",
    "test_5f_qwen7b_check.py",
    "test_5g1_integration_v4_check.py",
    "test_5g1_integration_v5_check.py",
]

results = []

print("=" * 70)
print(" AUDIT DES SCRIPTS _check.py")
print("=" * 70)
print()

print("  [CI] Tests autonomes :")
for name in CI_CHECKS:
    p = ROOT / name
    if not p.exists():
        print(f"    [--] {name} absent")
        continue
    try:
        r = subprocess.run(
            [sys.executable, str(p)],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        pass_n = fail_n = 0
        for line in (r.stdout or "").splitlines():
            if "PASS /" in line and "FAIL" in line:
                parts = line.replace("PASS", "").replace("FAIL", "").split("/")
                try:
                    pass_n = int(parts[0].split(":")[-1].strip())
                    fail_n = int(parts[1].split()[0].strip())
                except Exception:
                    pass
        status = "OK" if r.returncode == 0 else "KO"
        results.append({
            "script": name, "kind": "CI", "status": status,
            "code": r.returncode, "pass": pass_n, "fail": fail_n,
        })
        print(f"    [{status}] {name:<40} PASS={pass_n} FAIL={fail_n}")
    except subprocess.TimeoutExpired:
        results.append({"script": name, "kind": "CI", "status": "TIMEOUT"})
        print(f"    [TO] {name}")

print()
print("  [ONESHOT] Scripts manuels (pas de CI) :")
for name in ONE_SHOT:
    p = ROOT / name
    if not p.exists():
        print(f"    [--] {name} absent")
        continue
    results.append({"script": name, "kind": "ONESHOT", "status": "SKIP"})
    print(f"    [--] {name:<40} (lance manuellement)")

manifest = ROOT / "checks_manifest.json"
manifest.write_text(json.dumps(results, indent=2), encoding="utf-8")

ci_ok = sum(1 for r in results if r.get("kind") == "CI" and r["status"] == "OK")
ci_total = sum(1 for r in results if r.get("kind") == "CI")

print()
print(f"  CI : {ci_ok}/{ci_total} OK")
print(f"  One-shot : {len(ONE_SHOT)} script(s) disponibles")
print(f"  Manifest : {manifest.name}")
