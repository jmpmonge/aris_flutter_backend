#!/usr/bin/env python3
"""Smoke v0.45c — creación explícita no debe ejecutar update_calendar_event.

Sin servidor; stores bajo tempfile (no escribe en data/). Exige motor unificado
mock (try_structured_user_intent) cuando el backend simula un error GPT
operation=update ante texto de nueva cita.
"""

from __future__ import annotations

import logging
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.disable(logging.CRITICAL)


def _mk_engine_tempdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="aris_smoke_v045c_"))


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


def _unified_update_stub(
    *,
    eid: str,
    updates: dict,
) -> dict:
    empty_cal = {
        "title": None,
        "date_text": None,
        "time_text": None,
        "location": None,
        "participants": [],
        "description": None,
        "duration_minutes": None,
    }
    return {
        "operation": "update_calendar_event",
        "confidence": 0.92,
        "needs_clarification": False,
        "clarification_question": None,
        "reason": "smoke_stub",
        "note": {"content": None},
        "task": {"title": None, "date_text": None, "time_text": None, "priority": None},
        "calendar_event": dict(empty_cal),
        "calendar_query": {
            "requested_field": None,
            "date_text": None,
            "time_text": None,
            "terms": [],
            "target_reference": None,
        },
        "calendar_update": {
            "target_reference": "focused_event",
            "target_event_id": eid,
            "updates": {
                "title": updates.get("title"),
                "date_text": updates.get("date_text"),
                "time_text": updates.get("time_text"),
                "location": updates.get("location"),
                "participants": updates.get("participants") or [],
                "description": updates.get("description"),
                "duration_minutes": updates.get("duration_minutes"),
            },
        },
        "missing_fields": [],
    }


def case_a_explicit_create_never_updates_existing() -> None:
    """Modelo equivocado propone update; texto es nueva cita."""
    from backend.core import assistant_engine as ae

    tmp = _mk_engine_tempdir()
    try:
        eng = _engine_all_temp(tmp)
        old = eng._events.add_event(
            {"title": "cita antigua", "date_text": "jueves", "time_text": "14:00"}
        )
        eid = str(old["id"])
        eng._events.set_focused_event_id(eid)

        stub = _unified_update_stub(
            eid=eid,
            updates={
                "title": "cita con Luis mañana a las 7",
                "date_text": "mañana",
                "time_text": "07:00",
                "participants": ["Luis"],
            },
        )
        wraps = eng._events.update_event
        upd_calls: list[tuple[str, dict]] = []

        def spy_upd(event_id: str, upd: dict):
            upd_calls.append((event_id, dict(upd)))
            return wraps(event_id, upd)

        raw = "quiero poner una cita mañana a las 7 con Luis"
        with patch.object(ae, "try_structured_user_intent", return_value=stub):
            with patch.object(eng._events, "update_event", side_effect=spy_upd):
                reply, intent, stored, uh = eng.process_message(raw)

        assert not reply.startswith("He actualizado el evento"), reply[:80]
        reloaded = eng._events.get_event_by_id(eid)
        assert reloaded is not None
        assert reloaded.get("title") == "cita antigua"
        assert reloaded.get("time_text") == "14:00"
        assert uh is None

        titles = raw.strip()
        for ev in eng._events.get_events():
            assert ev.get("title") != titles, ev
        assert len(upd_calls) == 0
        # El motor no persiste eventos nuevos aquí (lo hace main); basta evento viejo intacto.
        pend = eng._pending.get_pending_action()
        evs = eng._events.get_events()
        assert len(evs) == 1
        assert isinstance(stored, dict)
        assert (stored.get("title") or "").strip() != titles
        assert (stored.get("date_text") or "").strip()
        assert pend is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_b_pon_cita_dom_no_update() -> None:
    tmp = _mk_engine_tempdir()
    try:
        from backend.core import assistant_engine as ae

        eng = _engine_all_temp(tmp)
        old = eng._events.add_event(
            {"title": "otra cosa", "date_text": "lunes", "time_text": "10:00"}
        )
        eid = str(old["id"])
        eng._events.set_focused_event_id(eid)
        stub = _unified_update_stub(
            eid=eid,
            updates={
                "title": "cita",
                "date_text": "domingo",
                "time_text": None,
            },
        )

        wrap_u = eng._events.update_event
        calls: list[tuple[str, dict]] = []

        def spy_u(i: str, u: dict):
            calls.append((i, dict(u)))
            return wrap_u(i, u)

        raw = "pon una cita para el domingo"
        with patch.object(ae, "try_structured_user_intent", return_value=stub):
            with patch.object(eng._events, "update_event", side_effect=spy_u):
                reply, *_rest = eng.process_message(raw)

        assert len(calls) == 0, calls
        assert not reply.startswith("He actualizado el evento"), reply[:80]
        reloaded = eng._events.get_event_by_id(eid)
        assert reloaded and reloaded.get("title") == "otra cosa"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_c_real_update_still_works() -> None:
    from backend.core import assistant_engine as ae

    tmp = _mk_engine_tempdir()
    try:
        eng = _engine_all_temp(tmp)
        old = eng._events.add_event(
            {"title": "cita antigua", "date_text": "jueves", "time_text": "14:00"}
        )
        eid = str(old["id"])
        eng._events.set_focused_event_id(eid)
        stub = _unified_update_stub(
            eid=eid,
            updates={"time_text": "08:00"},
        )
        raw = "cambia la cita antigua a las 8"
        with patch.object(ae, "try_structured_user_intent", return_value=stub):
            reply, intent, _s, _u = eng.process_message(raw)

        assert reply.startswith("He actualizado el evento"), reply[:80]
        assert intent == "consulta"
        upd = eng._events.get_event_by_id(eid)
        assert upd is not None
        assert str(upd.get("time_text", "")).strip() == "08:00"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    case_a_explicit_create_never_updates_existing()
    case_b_pon_cita_dom_no_update()
    case_c_real_update_still_works()
    print("smoke_v045c_create_not_update OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
