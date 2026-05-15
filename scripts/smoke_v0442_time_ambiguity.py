#!/usr/bin/env python3
"""Smoke v0.44.2 — horas ambiguas en eventos (sin arrancar servidor).

Comprueba coerción y `_display_time_text` del motor Calendario. Un E2E con
`sí`/OpenAI opcional puede añadirse cuando haya servidor y clave configurados.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _require_coercion_matches() -> None:
    from backend.core.assistant_engine import _coerce_ambiguous_calendar_time_text

    raw_7 = "quiero poner una cita mañana a las 7 con Luis"
    assert _coerce_ambiguous_calendar_time_text(raw_7, "14:00") == "07:00", (
        '"a las 7" jamás debe quedar como 14:00 (modelo vs literal)'
    )
    assert _coerce_ambiguous_calendar_time_text(raw_7, "19:00") == "07:00", (
        "sin tarde/noche explícita, evitar +12 automático hasta 19:00 para las 7"
    )
    assert _coerce_ambiguous_calendar_time_text(raw_7, "7:00") == "7:00"

    raw_19 = "quiero poner una cita mañana a las 19:00 con Luis"
    assert _coerce_ambiguous_calendar_time_text(raw_19, "19:00") == "19:00"

    raw_14 = "quiero poner una cita mañana a las 14:00 con Luis"
    assert _coerce_ambiguous_calendar_time_text(raw_14, "14:00") == "14:00"

    raw_2 = "quiero una cita mañana a las 2 con Ana"
    assert _coerce_ambiguous_calendar_time_text(raw_2, "14:00") == "02:00", (
        "las 2 + modelo 14:00 sin período → conservar dígito del usuario"
    )

    raw_2t = "cita mañana a las 2 de la tarde"
    assert _coerce_ambiguous_calendar_time_text(raw_2t, "14:00") == "14:00", (
        "con «de la tarde» debe respetarse 14:00"
    )


def _require_display_time() -> None:
    import tempfile

    from backend.core.assistant_engine import AssistantEngine
    from backend.storage.pending_action_store import PendingActionStore

    fd, p = tempfile.mkstemp(prefix="pending_", suffix=".json")
    os.close(fd)
    Path(p).unlink(missing_ok=False)
    try:
        eng = AssistantEngine(PendingActionStore(Path(p)))
        raw = "cita mañana a las 7 con Luis"
        assert eng._display_time_text("7:00", raw) == "7:00"
        assert eng._display_time_text("19:00", raw) == "19:00"
        assert (
            eng._display_time_text("2:00", "cita a las 2 de la tarde") == "14:00"
        )
    finally:
        Path(p).unlink(missing_ok=True)


def main() -> int:
    _require_coercion_matches()
    _require_display_time()
    print("smoke_v0442_time_ambiguity OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
