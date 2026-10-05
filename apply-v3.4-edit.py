from pathlib import Path

path = Path(r"C:\Users\moros\MemoLibDev\v3\orchestrator-v3.3.py")
text = path.read_text(encoding="utf-8")

def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: occurrence attendue=1, trouvée={count}"
        )
    text = text.replace(old, new, 1)

# 1. SHA256 helper
marker = "def run(cmd, cwd, timeout=300):"

if "def sha256_file(path):" not in text:
    helper = '''def sha256_file(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


'''
    replace_once(
        marker,
        helper + marker,
        "insertion sha256_file"
    )

# 2. Capturer le HEAD Git avant toute opération
old = '''    print("[1] VÉRIFICATION GIT")
    status = git_status()
'''

new = '''    print("[1] VÉRIFICATION GIT")

    head_before = run(
        ["git", "rev-parse", "HEAD"],
        ROOT,
        60
    )

    if head_before["returncode"] != 0:
        print("STOP — impossible de déterminer le HEAD Git.")
        report["overall_status"] = "STOP"
        report["reason"] = "git_head_unavailable"
        report["steps"].append({
            "name": "git_head",
            "status": "FAIL",
            "details": head_before
        })
        output = save_report(report)
        print("Rapport :", output)
        sys.exit(2)

    git_head_before = head_before["stdout"].strip()

    status = git_status()
'''

replace_once(old, new, "git_head_before")

# 3. Ajouter le SHA et la taille du patch après sa détection
old = '''    print("Patch :", patch)

    report["steps"].append({
        "name": "patch_detection",
        "status": "PASS",
        "patch": str(patch)
    })
'''

new = '''    print("Patch :", patch)

    patch_sha256 = sha256_file(patch)
    patch_size = patch.stat().st_size

    print("SHA256 :", patch_sha256)
    print("Taille :", patch_size, "octets")

    report["steps"].append({
        "name": "patch_detection",
        "status": "PASS",
        "patch": str(patch),
        "sha256": patch_sha256,
        "size": patch_size
    })
'''

replace_once(old, new, "patch metadata")

# 4. Enrichir la vérification git_apply_check
old = '''    report["steps"].append({
        "name": "git_apply_check",
        "status": "PASS"
    })
'''

new = '''    report["steps"].append({
        "name": "git_apply_check",
        "status": "PASS",
        "patch_applicable": True
    })
'''

replace_once(old, new, "patch_applicable")

# 5. Enrichir tests_before
old = '''    report["steps"].append({
        "name": "tests_before",
        "status": "PASS" if before_ok else "FAIL",
        "returncode": before["returncode"],
        "stdout": before["stdout"],
        "stderr": before["stderr"]
    })
'''

new = '''    report["steps"].append({
        "name": "tests_before",
        "status": "PASS" if before_ok else "FAIL",
        "returncode": before["returncode"],
        "stdout": before["stdout"],
        "stderr": before["stderr"]
    })

    report["git_head_before"] = git_head_before
    report["patch_sha256"] = patch_sha256
    report["patch_size"] = patch_size
    report["patch_applicable"] = True
    report["tests_before_exit_code"] = before["returncode"]
'''

replace_once(old, new, "traceability metadata")

# 6. Marquer explicitement les garde-fous V3.4
old = '''    report["overall_status"] = "READY_FOR_HUMAN_APPROVAL"
    report["next_step"] = "HUMAN_APPROVAL"
    report["human_approval_required"] = True
'''

new = '''    report["automatic_apply"] = False
    report["automatic_commit"] = False
    report["automatic_push"] = False
    report["automatic_production"] = False
    report["human_approval_required"] = True

    report["overall_status"] = "READY_FOR_HUMAN_APPROVAL"
    report["next_step"] = "HUMAN_APPROVAL"
'''

replace_once(old, new, "V3.4 safety flags")

path.write_text(text, encoding="utf-8")
print("V3.4 modification OK")
