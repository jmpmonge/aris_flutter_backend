#!/usr/bin/env python3
"""Ejecuta los smoke locales del repo."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Backend mínimo v0.47: deben ejecutarse siempre desde la raíz del repo.
SMOKES_BACKEND_MINIMAL = [
    ROOT / "smoke_backend_minimal_v047.py",
]

# Smokes contra piezas antiguas; pueden depender de módulos ya no presentes.
SMOKES_LEGACY = [
    ROOT / "smoke_v0442_time_ambiguity.py",
    ROOT / "smoke_v045b_no_raw_calendar_fallback.py",
    ROOT / "smoke_v045c_create_not_update.py",
    ROOT / "smoke_v046a_decision_engine_contract.py",
]


def _legacy_enabled() -> bool:
    val = os.environ.get("RUN_LEGACY_SMOKES", "").strip().lower()
    return val in ("1", "true", "yes")


def main() -> int:
    scripts = list(SMOKES_BACKEND_MINIMAL)
    if _legacy_enabled():
        scripts.extend(SMOKES_LEGACY)

    if not _legacy_enabled() and any(p.is_file() for p in SMOKES_LEGACY):
        print(
            "[smoke_all] Omitiendo smokes legacy → RUN_LEGACY_SMOKES=1",
            file=sys.stderr,
        )

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
