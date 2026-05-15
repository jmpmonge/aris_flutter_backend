#!/usr/bin/env python3
"""Ejecuta los smoke locales del repo (añadir nuevos imports aquí)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    scripts = [
        ROOT / "smoke_v0442_time_ambiguity.py",
    ]
    for s in scripts:
        if not s.is_file():
            print(f"[smoke_all] SKIP (no existe {s})", file=sys.stderr)
            continue
        r = subprocess.run([sys.executable, str(s)], cwd=str(ROOT.parent))
        if r.returncode != 0:
            print(f"[smoke_all] FAIL {s}", file=sys.stderr)
            return r.returncode
    print("smoke_all OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
