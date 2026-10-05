"""
Test 5G — garde-fou écriture + extraction de chemins + sandbox.
NE sollicite PAS Ollama. Vérifie la sécurité du Controlled Coder.
"""

from controlled_coder import (
    extract_patched_paths,
    enforce_write_guardrail,
    verify_patch_in_sandbox,
)
from pathlib import Path
import tempfile

ALLOWED = ["src/lib/clerk-auth.ts", "src/middleware/auth.ts"]

# --- 1. Diff légitime, dans la sélection -----------------------
GOOD_DIFF = """diff --git a/src/lib/clerk-auth.ts b/src/lib/clerk-auth.ts
index 1111111..2222222 100644
--- a/src/lib/clerk-auth.ts
+++ b/src/lib/clerk-auth.ts
@@ -1,3 +1,4 @@
 export const x = 1;
+export const y = 2;
 export const z = 3;
"""

# --- 2. Diff MALVEILLANT : touche un fichier hors sélection ----
EVIL_DIFF = """diff --git a/src/lib/clerk-auth.ts b/src/lib/clerk-auth.ts
--- a/src/lib/clerk-auth.ts
+++ b/src/lib/clerk-auth.ts
@@ -1 +1,2 @@
 a
+b
diff --git a/.env b/.env
--- a/.env
+++ b/.env
@@ -1 +1,2 @@
 SECRET=1
+BACKDOOR=1
"""

# --- 3. Diff vide / non identifiable ---------------------------
EMPTY_DIFF = "juste du texte, aucun diff"


def test_extraction():
    paths = extract_patched_paths(GOOD_DIFF)
    assert paths == {"src/lib/clerk-auth.ts"}, paths

    evil = extract_patched_paths(EVIL_DIFF)
    assert evil == {"src/lib/clerk-auth.ts", ".env"}, evil
    print("extraction OK :", sorted(evil))


def test_guardrail_accepts_in_scope():
    g = enforce_write_guardrail(GOOD_DIFF, ALLOWED)
    assert g["verdict"] == "ACCEPTABLE", g
    assert g["touched_files"] == ["src/lib/clerk-auth.ts"]
    assert g["out_of_scope_files"] == []
    print("garde-fou ACCEPTE le patch in-scope : OK")


def test_guardrail_rejects_out_of_scope():
    g = enforce_write_guardrail(EVIL_DIFF, ALLOWED)
    assert g["verdict"] == "REJECT", g
    assert ".env" in g["out_of_scope_files"], g
    print("garde-fou REJETTE le patch touchant .env : OK ->", g["out_of_scope_files"])


def test_guardrail_rejects_empty():
    g = enforce_write_guardrail(EMPTY_DIFF, ALLOWED)
    assert g["verdict"] == "REJECT", g
    print("garde-fou REJETTE un diff non identifiable : OK")


def test_sandbox_applicable():
    # Sandbox réel : crée un fichier, applique un diff cohérent.
    tmp = Path(tempfile.mkdtemp(prefix="5g-selftest-"))
    try:
        src = tmp / "demo.txt"
        src.write_text("line1\nline2\nline3\n", encoding="utf-8")

        diff = (
            "diff --git a/demo.txt b/demo.txt\n"
            "--- a/demo.txt\n"
            "+++ b/demo.txt\n"
            "@@ -1,3 +1,4 @@\n"
            " line1\n"
            "+inserted\n"
            " line2\n"
            " line3\n"
        )
        patch = tmp / "p.diff"
        patch.write_text(diff, encoding="utf-8")

        # On teste la vérif git apply --check sur un sandbox autonome.
        import subprocess, shutil

        sandbox = Path(tempfile.mkdtemp(prefix="5g-sbx-"))
        try:
            def g(*a):
                return subprocess.run(["git", *a], cwd=sandbox, text=True, capture_output=True)
            g("init", "-q")
            g("config", "user.email", "t@t.local")
            g("config", "user.name", "t")
            shutil.copy2(src, sandbox / "demo.txt")
            g("add", "-A")
            g("commit", "-q", "-m", "base")
            check = g("apply", "--check", str(patch))
            assert check.returncode == 0, check.stderr
            print("sandbox git apply --check : APPLICABLE OK")
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    import shutil
    test_extraction()
    test_guardrail_accepts_in_scope()
    test_guardrail_rejects_out_of_scope()
    test_guardrail_rejects_empty()
    test_sandbox_applicable()
    print()
    print("TOUS LES TESTS 5G (sécurité) PASSENT.")
