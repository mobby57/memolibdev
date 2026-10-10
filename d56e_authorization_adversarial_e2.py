from __future__ import annotations

import copy
import json
from pathlib import Path

import controlled_coder as coder
from project_target import resolve_target


CERT = Path("reports/coder-authorization.json")

if not CERT.is_file():
    raise SystemExit("[FAIL] Certificate absent")

original = json.loads(CERT.read_text(encoding="utf-8"))
target = resolve_target()


def check_rejected(name: str, forged: dict) -> None:
    temp = Path("reports") / f".d56e2-{name}.json"

    temp.write_text(
        json.dumps(forged, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    try:
        authorization = coder.load_coder_authorization(temp)

        result = coder.enforce_coder_authorization(
            authorization,
            target,
            [authorization.path],
        )

        if result["verdict"] == "AUTHORIZED":
            print(f"[FAIL] {name}: falsification ACCEPTED")
            raise SystemExit(1)

        print(f"[PASS] {name}: falsification BLOCKED")

    finally:
        temp.unlink(missing_ok=True)


# ------------------------------------------------------------
# BASELINE
# ------------------------------------------------------------

authorization = coder.load_coder_authorization(CERT)

baseline = coder.enforce_coder_authorization(
    authorization,
    target,
    [authorization.path],
)

if baseline["verdict"] != "AUTHORIZED":
    raise SystemExit("[FAIL] baseline invalid")

print("[PASS] baseline AUTHORIZED")


# ------------------------------------------------------------
# REAL CONTENT / AUTHORIZATION FALSIFICATIONS
# ------------------------------------------------------------

forged = copy.deepcopy(original)
forged["evidence_sha256"] = "0" * 64
check_rejected("evidence-sha256", forged)


forged = copy.deepcopy(original)
forged["provenance_status"] = "EXTERNAL_MODULE"
check_rejected("provenance-status", forged)


forged = copy.deepcopy(original)
forged["provenance_resolved_path"] = "src/evil.ts"
check_rejected("provenance-path", forged)


forged = copy.deepcopy(original)
forged["human_approval"]["approved"] = False
check_rejected("approval-revoked", forged)


forged = copy.deepcopy(original)
forged["status"] = "REJECTED"
check_rejected("authorization-status", forged)


forged = copy.deepcopy(original)
forged["reason"] = "FORGED AUTHORIZATION"
check_rejected("authorization-reason", forged)


print("")
print("============================================================")
print("D5.6-E2 — RESULTAT")
print("============================================================")
print("MemoLib : NON MODIFIE")
print("Ollama  : NON")
print("Git     : NON")
print("============================================================")
