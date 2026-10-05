from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\Users\moros\Desktop\memolib").resolve()
OUT = Path(__file__).resolve().parent / "reports"

MAX_FILE_SIZE = 120_000


def safe_path(relative: str) -> Path | None:
    candidate = (ROOT / relative).resolve()

    try:
        candidate.relative_to(ROOT)
    except ValueError:
        return None

    return candidate


def inspect_file(relative: str) -> dict:
    path = safe_path(relative)

    result = {
        "requested_path": relative,
        "exists": False,
        "valid_path": path is not None,
        "size": 0,
        "lines": 0,
        "imports": [],
        "symbols": [],
        "security_markers": [],
        "content": None,
    }

    if path is None or not path.exists() or not path.is_file():
        return result

    result["exists"] = True
    result["size"] = path.stat().st_size

    if result["size"] > MAX_FILE_SIZE:
        result["error"] = "Fichier trop volumineux pour inspection directe."
        return result

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        result["error"] = "Fichier non UTF-8."
        return result

    result["lines"] = len(content.splitlines())

    result["imports"] = re.findall(
        r"^\s*(?:import|export)\s+.*?(?:from\s+)?['\"]([^'\"]+)['\"]",
        content,
        re.MULTILINE,
    )

    result["symbols"] = re.findall(
        r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z0-9_$]+)",
        content,
        re.MULTILINE,
    )

    markers = [
        "clerkMiddleware",
        "auth(",
        "currentUser",
        "getAuth",
        "verifyToken",
        "Authorization",
        "Bearer",
        "publicRoutes",
        "protectedRoutes",
        "matcher",
        "tenant",
        "workspace",
        "session",
    ]

    for marker in markers:
        if marker in content:
            result["security_markers"].append(marker)

    result["content"] = content

    return result


def main() -> None:
    # Windows : force la sortie UTF-8 pour éviter les erreurs cp1252.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    if len(sys.argv) < 2:
        print(
            'Usage : python inspector.py "chemin1" "chemin2" ...'
        )
        sys.exit(1)

    requested = sys.argv[1:]

    print()
    print("=" * 60)
    print(" MEMOLIBDEV V3 — INSPECTOR")
    print("=" * 60)
    print()
    print(f"Dépôt : {ROOT}")
    print()

    results = []

    for relative in requested:
        print(f"[INSPECT] {relative}")

        result = inspect_file(relative)
        results.append(result)

        if result["exists"]:
            print(
                f"  OK — {result['lines']} lignes — "
                f"{result['size']} octets"
            )
        else:
            print("  NON TROUVÉ")

    report = {
        "created_at": datetime.now().isoformat(),
        "repository": str(ROOT),
        "read_only": True,
        "files": results,
    }

    OUT.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = OUT / f"inspection-{timestamp}.json"

    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print(f"Rapport : {output}")
    print()

    print("=== FICHIERS RÉELLEMENT DISPONIBLES ===")

    for result in results:
        if result["exists"]:
            print(f"  ✓ {result['requested_path']}")
        else:
            print(f"  ✗ {result['requested_path']}")

    print()
    print("=== MARQUEURS SÉCURITÉ ===")

    for result in results:
        if result["exists"] and result["security_markers"]:
            print()
            print(result["requested_path"])

            for marker in result["security_markers"]:
                print(f"  - {marker}")


if __name__ == "__main__":
    main()
