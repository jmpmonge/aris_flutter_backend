#!/usr/bin/env python3
"""Smoke v0.45b — no crear eventos calendario desde texto bruto (sin servidor).

Usa PendingActionStore y EventsStore en rutas temporales e inyecta el motor con
stores bajo tempfile para no escribir en data/. Sin OPENAI_API_KEY la extracción
GPT suele devolver None (complementado con mocks donde haga falta).
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Evitar ruido en stdout del smoke
logging.disable(logging.CRITICAL)


def _mk_engine_tempdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="aris_smoke_v045b_"))


def _engine_all_temp(base: Path):
    from backend.core.assistant_engine import AssistantEngine
    from backend.storage.events_store import EventsStore
    from backend.storage.focus_store import FocusStore
    from backend.storage.notes_store import NotesStore
    from backend.storage.pending_action_store import PendingActionStore
    from backend.storage.tasks_store import TasksStore

    eng = AssistantEngine(
        PendingActionStore(base / "pending_action.json"),
        focus_store=FocusStore(base / "focus.json"),
        tasks_store=TasksStore(base / "tasks.json"),
        notes_store=NotesStore(base / "notes.json"),
    )
    eng._events = EventsStore(base / "events.json")
    return eng


def case1_extraction_none_opens_pending_no_poor_event() -> None:
    from backend.core import assistant_engine as ae

    tmp = _mk_engine_tempdir()
    try:
        eng = _engine_all_temp(tmp)
        raw = "quiero poner una cita mañana a las 7 con Luis"

        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with patch.object(ae, "try_calendar_event_extraction", return_value=None):
                reply, intent, stored, uh = eng._process_calendar_with_extraction(raw)

        assert intent == "ambiguo", intent
        assert stored is None
        assert uh is None
        pend = eng._pending.get_pending_action()
        assert pend is not None
        assert pend.get("pending_kind") == "calendar_event_completion"
        events = eng._events.get_events()
        assert events == [], events
        assert "provisional" not in reply.lower()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case2_short_cita_pending_via_process_message() -> None:
    """«cita» sin fecha/hora → pending mínima; ningún evento con title literal «cita»."""
    tmp = _mk_engine_tempdir()
    try:
        eng = _engine_all_temp(tmp)

        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            reply, intent, stored, uh = eng.process_message("cita")

        assert intent == "ambiguo"
        assert stored is None
        pend = eng._pending.get_pending_action()
        assert pend is not None
        assert pend.get("suggested_intent") == "calendario"
        events = eng._events.get_events()
        assert len(events) == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case3_structured_dict_not_raw_if_saved_like_main() -> None:
    from backend.core import assistant_engine as ae

    tmp = _mk_engine_tempdir()
    try:
        eng = _engine_all_temp(tmp)
        raw = "quiero poner una cita mañana a las 7 con Luis"
        cal = {
            "intent": "calendar_event",
            "title": "Cita con Luis",
            "date_text": "mañana",
            "time_text": "07:00",
            "participants": ["Luis"],
            "confidence": 0.95,
            "needs_confirmation": False,
            "missing_fields": [],
            "reason": "smoke",
        }

        with patch.object(ae, "try_calendar_event_extraction", return_value=cal):
            reply, intent, stored, uh = eng._process_calendar_with_extraction(raw)

        assert intent == "calendario"
        assert isinstance(stored, dict), type(stored)
        assert stored.get("title") == "Cita con Luis"
        assert stored.get("date_text") == "mañana"
        assert stored.get("time_text")
        assert isinstance(stored.get("participants"), list)

        # Simula main.py: solo persistir dict estructurado
        saved = eng._events.add_event(stored)
        assert saved.get("title") != raw
        events = eng._events.get_events()
        assert len(events) == 1
        assert events[0].get("title") == "Cita con Luis"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case4_add_event_dict_on_store() -> None:
    tmp = _mk_engine_tempdir()
    try:
        from backend.storage.events_store import EventsStore

        store = EventsStore(tmp / "ev.json")
        ev = store.add_event(
            {
                "title": "Test smoke",
                "date_text": "mañana",
                "time_text": "12:00",
            }
        )
        assert ev.get("title") == "Test smoke"
        assert ev.get("date_text") == "mañana"
        loaded = store.get_events()
        assert len(loaded) == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case5_main_defensive_calendar_str_no_add_event() -> None:
    """main.message no debe llamar add_event si intent calendario y payload es str."""
    import backend.main as main_mod
    from backend.models.assistant_message import UserMessage

    mock_add = MagicMock(return_value={"id": "fake", "title": "x"})
    mock_history = MagicMock()
    with patch.object(main_mod.events_store, "add_event", mock_add):
        with patch.object(main_mod.history_store, "save_interaction", mock_history):
            with patch.object(
                main_mod.engine,
                "process_message",
                return_value=("Respuesta test", "calendario", "texto crudo no estructurado", None),
            ):
                main_mod.message(UserMessage(text="entrada usuario"))

    mock_add.assert_not_called()
    mock_history.assert_called_once()


def main() -> int:
    case1_extraction_none_opens_pending_no_poor_event()
    case2_short_cita_pending_via_process_message()
    case3_structured_dict_not_raw_if_saved_like_main()
    case4_add_event_dict_on_store()
    case5_main_defensive_calendar_str_no_add_event()
    print("smoke_v045b_no_raw_calendar_fallback OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
