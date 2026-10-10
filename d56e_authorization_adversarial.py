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


def test_reject(name: str, forged: dict) -> None:
    """
    Teste un certificat falsifié sans écrire sur le certificat réel.
    """

    temp = Path("reports") / f".d56e-{name}.json"

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
            raise SystemExit(
                f"[FAIL] {name}: certificat falsifié accepté"
            )

        print(f"[PASS] {name}")
    finally:
        temp.unlink(missing_ok=True)


# ------------------------------------------------------------
# 1. BASELINE
# ------------------------------------------------------------

authorization = coder.load_coder_authorization(CERT)

result = coder.enforce_coder_authorization(
    authorization,
    target,
    [authorization.path],
)

if result["verdict"] != "AUTHORIZED":
    raise SystemExit(
        "[FAIL] baseline certificate no longer authorized"
    )

print("[PASS] baseline certificate AUTHORIZED")


# ------------------------------------------------------------
# 2. FORGED HEAD
# ------------------------------------------------------------

forged = copy.deepcopy(original)
forged["target"]["head"] = (
    "0000000000000000000000000000000000000000"
)

test_reject("forged-head", forged)


# ------------------------------------------------------------
# 3. FORGED FINGERPRINT
# ------------------------------------------------------------

forged = copy.deepcopy(original)
forged["target"]["repository_fingerprint"] = "FORGED-FINGERPRINT"

test_reject("forged-fingerprint", forged)


# ------------------------------------------------------------
# 4. FORGED GIT ROOT
# ------------------------------------------------------------

forged = copy.deepcopy(original)
forged["target"]["git_root"] = "C:/attacker/repository"

test_reject("forged-git-root", forged)


# ------------------------------------------------------------
# 5. FORGED PATH
# ------------------------------------------------------------

forged = copy.deepcopy(original)
forged["path"] = "src/lib/auth/auth.ts"

test_reject("forged-path", forged)


# ------------------------------------------------------------
# 6. FORGED ACTION TARGET
# ------------------------------------------------------------

forged = copy.deepcopy(original)
forged["action"]["target_path"] = "src/lib/auth/auth.ts"

test_reject("forged-action-target", forged)


# ------------------------------------------------------------
# 7. FORGED EVIDENCE STATUS
# ------------------------------------------------------------

forged = copy.deepcopy(original)
forged["evidence_status"] = "ACCEPTED"

# Ici la valeur semble correcte mais le certificat reste
# dépourvu d'une preuve cryptographique liant le champ au
# contenu réel. Le test documente donc le comportement actuel.

test_reject(
    "forged-evidence-status-control",
    forged,
)


# ------------------------------------------------------------
# 8. FORGED APPROVER
# ------------------------------------------------------------

forged = copy.deepcopy(original)
forged["human_approval"]["approver"] = "attacker"

test_reject("forged-approver", forged)


# ------------------------------------------------------------
# 9. FORGED APPROVAL TIMESTAMP
# ------------------------------------------------------------

forged = copy.deepcopy(original)
forged["human_approval"]["approved_at"] = "2099-01-01T00:00:00+00:00"

test_reject("forged-approval-timestamp", forged)


# ------------------------------------------------------------
# 10. FORGED AUTHORITY
# ------------------------------------------------------------

forged = copy.deepcopy(original)
forged["human_approval"]["authority_level"] = "L5_EXECUTE_ACTION"

test_reject("forged-authority", forged)


# ------------------------------------------------------------
# 11. FORGED ACTION ID
# ------------------------------------------------------------

forged = copy.deepcopy(original)
forged["action"]["action_id"] = "ATTACKER-ACTION"

test_reject("forged-action-id", forged)


print("")
print("============================================================")
print("D5.6-E — RESULTAT")
print("============================================================")
print("Le certificat doit être cryptographiquement lié")
print("à son contenu avant de devenir une autorité durable.")
print("")
print("MemoLib : NON MODIFIÉ")
print("Ollama  : NON")
print("Git     : NON")
print("============================================================")
