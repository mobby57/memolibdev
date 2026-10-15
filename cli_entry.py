#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Point d'entree pour MemoLibDev-cli.exe (standalone)."""
import sys
from pathlib import Path

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    sys.path.insert(0, sys._MEIPASS)
else:
    sys.path.insert(0, str(Path(__file__).parent))

from memolibdev_cli import main

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERREUR: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        raise SystemExit(1)
