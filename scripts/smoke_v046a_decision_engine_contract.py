#!/usr/bin/env python3
"""Smoke v0.46a — contrato motor decisión (sin red; mocks + normalización).

Ejercita `_normalize_unified_intent` y rutas del `AssistantEngine` con
`try_structured_user_intent` parcheado. No requiere OPENAI_API_KEY.

Cuando exista API key, los casos con GPT real pueden añadirse aparte; aquí
solo comprobaciones deterministas del contrato v0.46a.
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

_MAX_STEP = 3


def _tmp_engine():
    from backend.core.assistant_engine import AssistantEngine
    from backend.storage.events_store import EventsStore
    from backend.storage.focus_store import FocusStore
    from backend.storage.notes_store import NotesStore
    from backend.storage.pending_action_store import PendingActionStore
    from backend.storage.tasks_store import TasksStore

    tmp = Path(tempfile.mkdtemp(prefix="aris_smoke_046a_"))
    eng = AssistantEngine(
        PendingActionStore(tmp / "pending.json"),
        FocusStore(tmp / "focus.json"),
        TasksStore(tmp / "tasks.json"),
        NotesStore(tmp / "notes.json"),
    )
    eng._events = EventsStore(tmp / "events.json")
    return eng, tmp


def test_normalize_ambiguous_hour() -> None:
    from backend.core.openai_client import _normalize_unified_intent

    raw = {
        "operation": "create_calendar_event",
        "status": "needs_clarification",
        "confidence": 0.9,
        "calendar_event": {
            "title": "cita con Luis",
            "date_text": "mañana",
            "time_text": "8",
            "participants": ["Luis"],
        },
        "ambiguities": [
            {
                "field": "time_text",
                "options": ["08:00", "20:00"],
                "reason": "hora ambigua",
            }
        ],
        "clarification_question": "¿8:00 o 20:00?",
        "needs_clarification": False,
        "note": {},
        "task": {},
        "calendar_query": {},
        "calendar_update": {"updates": {}},
        "missing_fields": [],
    }
    out = _normalize_unified_intent(raw)
    assert out is not None
    assert out["operation"] == "needs_clarification"
    assert out["ambiguities"]
    assert "08:00" in str(out["ambiguities"])


def test_normalize_clear_2000() -> None:
    from backend.core.openai_client import _normalize_unified_intent

    raw = {
        "operation": "create_calendar_event",
        "status": "ready",
        "confidence": 0.95,
        "calendar_event": {
            "title": "cita con Luis",
            "date_text": "mañana",
            "time_text": "20:00",
            "participants": ["Luis"],
        },
        "needs_clarification": False,
        "note": {},
        "task": {},
        "calendar_query": {},
        "calendar_update": {"updates": {}},
        "missing_fields": [],
    }
    out = _normalize_unified_intent(raw)
    assert out is not None
    assert out["operation"] == "create_calendar_event"
    ce = out["calendar_event"]
    assert ce.get("title") != "quiero poner una cita mañana a las 20:00 con Luis"
    assert ce.get("time_text") == "20:00"
    assert "Luis" in (ce.get("participants") or [])


def test_multi_candidate_update_becomes_clarify() -> None:
    from backend.core import assistant_engine as ae

    eng, tmp = _tmp_engine()
    try:
        eng._events.add_event(
            {"title": "cita con Luis", "date_text": "lunes", "time_text": "10:00"}
        )
        eng._events.add_event(
            {"title": "cita con Juan", "date_text": "lunes", "time_text": "18:00"}
        )
        stub = {
            "operation": "needs_clarification",
            "status": "needs_clarification",
            "confidence": 0.7,
            "clarification_question": "¿Cuál de las dos citas del lunes?",
            "reason": "multiples",
            "note": {},
            "task": {},
            "calendar_event": {},
            "calendar_query": {},
            "calendar_update": {"updates": {}},
            "missing_fields": [],
            "ambiguities": [],
        }
        calls: list[tuple] = []

        def spy_u(eid: str, u: dict):
            calls.append((eid, u))
            return eng._events.get_event_by_id(eid)

        raw = "cambia la cita del lunes"
        with patch.object(ae, "try_structured_user_intent", return_value=stub):
            with patch.object(eng._events, "update_event", side_effect=spy_u):
                reply, intent, *_ = eng.process_message(raw)
        assert not calls
        assert "lunes" in reply.lower() or "cual" in reply.lower() or "?" in reply
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_update_clear_target() -> None:
    from backend.core import assistant_engine as ae

    eng, tmp = _tmp_engine()
    try:
        ev = eng._events.add_event(
            {
                "title": "cita con Juan",
                "date_text": "lunes",
                "time_text": "18:00",
            }
        )
        eid = str(ev["id"])
        eng._events.set_focused_event_id(eid)
        stub = {
            "operation": "update_calendar_event",
            "status": "ready",
            "confidence": 0.95,
            "calendar_event": {},
            "note": {},
            "task": {},
            "calendar_query": {},
            "calendar_update": {
                "target_event_id": eid,
                "target_reference": "focused_event",
                "updates": {"time_text": "20:00"},
            },
            "missing_fields": [],
        }
        raw = "cambia la cita con Juan del lunes a las 20:00"
        with patch.object(ae, "try_structured_user_intent", return_value=stub):
            eng.process_message(raw)
        upd = eng._events.get_event_by_id(eid)
        assert upd and str(upd.get("time_text")) == "20:00"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_explicit_create_no_update() -> None:
    from backend.core import assistant_engine as ae

    eng, tmp = _tmp_engine()
    try:
        old = eng._events.add_event(
            {"title": "vieja", "date_text": "sábado", "time_text": "12:00"}
        )
        eid = str(old["id"])
        eng._events.set_focused_event_id(eid)
        stub = {
            "operation": "update_calendar_event",
            "status": "ready",
            "confidence": 0.9,
            "calendar_event": {},
            "note": {},
            "task": {},
            "calendar_query": {},
            "calendar_update": {
                "target_event_id": eid,
                "updates": {"title": "nueva", "date_text": "domingo"},
            },
            "missing_fields": [],
        }
        wrap = eng._events.update_event
        log: list = []

        def spy(i: str, u: dict):
            log.append((i, u))
            return wrap(i, u)

        raw = "pon una cita para el domingo"
        with patch.object(ae, "try_structured_user_intent", return_value=stub):
            with patch.object(eng._events, "update_event", side_effect=spy):
                eng.process_message(raw)
        assert len(log) == 0
        re = eng._events.get_event_by_id(eid)
        assert re and re.get("title") == "vieja"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_note_structured_dict() -> None:
    eng, tmp = _tmp_engine()
    try:
        stub = {
            "operation": "create_note",
            "status": "ready",
            "confidence": 0.95,
            "note": {"content": "comprar leche desnatada y pan"},
            "task": {},
            "calendar_event": {},
            "calendar_query": {},
            "calendar_update": {"updates": {}},
            "missing_fields": [],
        }
        raw = (
            "anota para el hogar: mañana pasar por el súper a comprar "
            "leche desnatada y pan integral antes de mediodía"
        )
        _r, intent, stored, _ = eng._unified_handle_note(raw, stub)
        assert intent == "nota"
        assert isinstance(stored, dict)
        assert "leche" in (stored.get("content") or "").lower()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_task_structured() -> None:
    eng, tmp = _tmp_engine()
    try:
        stub = {
            "operation": "create_task",
            "status": "ready",
            "confidence": 0.9,
            "task": {
                "title": "revisar el informe de ventas",
                "date_text": "mañana",
            },
            "note": {},
            "calendar_event": {},
            "calendar_query": {},
            "calendar_update": {"updates": {}},
            "missing_fields": [],
        }
        raw = "crea una tarea para revisar el informe de ventas mañana antes de comer"
        _r, intent, stored, _ = eng._unified_handle_task(raw, stub)
        assert intent == "tarea"
        assert isinstance(stored, dict)
        assert "revisar" in (stored.get("title") or "").lower()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_needs_confirmation_status() -> None:
    from backend.core.openai_client import _normalize_unified_intent

    raw = {
        "operation": "update_calendar_event",
        "status": "needs_confirmation",
        "confidence": 0.85,
        "clarification_question": "¿Confirmas borrar la cita con Luis?",
        "needs_clarification": False,
        "note": {},
        "task": {},
        "calendar_event": {},
        "calendar_query": {},
        "calendar_update": {"updates": {}},
        "missing_fields": [],
    }
    out = _normalize_unified_intent(raw)
    assert out is not None
    assert out["operation"] == "needs_clarification"
    assert out.get("requires_explicit_confirmation") is True


def test_gpt_pending_continuation_payload() -> None:
    """pending_context llega en el dict de usuario (parcheado OpenAI no hace falta)."""
    from backend.core.openai_client import _compact_pending_context_for_gpt

    p = {
        "pending_kind": "gpt_needs_clarification",
        "question": "¿8 o 20?",
        "clarification_step": 1,
        "ambiguities": [{"field": "time_text"}],
        "noise": "x" * 5000,
    }
    c = _compact_pending_context_for_gpt(p)
    assert "noise" not in c
    assert c.get("question") == "¿8 o 20?"


def test_clarification_step_cap() -> None:
    from backend.core.openai_client import DEFAULT_USER_ID

    eng, tmp = _tmp_engine()
    try:
        eng._pending.save_pending_action(
            {
                "pending_kind": "gpt_needs_clarification",
                "clarification_step": _MAX_STEP,
                "question": "?",
                "user_id": DEFAULT_USER_ID,
            }
        )
        unified = {"operation": "needs_clarification", "confidence": 0.5}
        reply, intent, *_ = eng._unified_handle_clarification(
            "sigue sin estar claro", unified  # type: ignore[arg-type]
        )
        assert intent == "consulta"
        assert (
            "variadas aclaraciones" in reply.lower()
            or "frase" in reply.lower()
            or "plantear" in reply.lower()
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    test_normalize_ambiguous_hour()
    test_normalize_clear_2000()
    test_multi_candidate_update_becomes_clarify()
    test_update_clear_target()
    test_explicit_create_no_update()
    test_note_structured_dict()
    test_task_structured()
    test_delete_needs_confirmation_status()
    test_gpt_pending_continuation_payload()
    test_clarification_step_cap()
    print("smoke_v046a_decision_engine_contract OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
