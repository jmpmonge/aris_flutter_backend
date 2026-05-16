#!/usr/bin/env python3
"""Smokes de regresión del backend mínimo v0.47 — sin llamadas reales a OpenAI."""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import backend.core.engine as engine_mod
from backend.core.engine import ArisMinimalEngine
from backend.storage.events_store import EventsStore
from backend.storage.notes_store import NotesStore
from backend.storage.tasks_store import TasksStore
from backend.storage.thread_state_store import ThreadStateStore

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b"
)


def _assert_no_uuid_in_visible(text: str, label: str) -> None:
    if _UUID_RE.search(text or ""):
        raise AssertionError(f"{label}: no se esperaba UUID visible en: {text!r}")


def _make_engine(base: Path) -> ArisMinimalEngine:
    return ArisMinimalEngine(
        events_store=EventsStore(path=base / "events.json"),
        tasks_store=TasksStore(path=base / "tasks.json"),
        notes_store=NotesStore(path=base / "notes.json"),
        thread_store=ThreadStateStore(path=base / "thread_state.json"),
    )


def smoke_1_2_ambiguous_then_continue() -> None:
    """v0.47.9 + v0.47.10: ask hora ambigua → ready create tras continuar."""
    r1: dict[str, Any] = {
        "s": "ask",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con Luis",
            "date": "mañana",
            "time": "7",
            "people": ["Luis"],
        },
        "target": None,
        "q": "¿Te refieres a las 7:00 o a las 19:00?",
        "r": None,
        "pending": {"field": "time", "options": ["07:00", "19:00"]},
        "ctx": None,
    }
    r2: dict[str, Any] = {
        "s": "ready",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con Luis",
            "date": "mañana",
            "time": "19:00",
            "people": ["Luis"],
        },
        "target": None,
        "q": None,
        "r": "He guardado la cita con Luis para mañana a las 19:00.",
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        seq = iter([r1, r2])

        def fake_ask_gpt(_payload: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq)

        with patch.object(engine_mod, "ask_gpt", side_effect=fake_ask_gpt):
            t1, _, _, _ = engine.process_message(
                "quiero poner una cita mañana a las 7 con Luis"
            )
            if t1.strip() != "¿Te refieres a las 7:00 o a las 19:00?":
                raise AssertionError(f"smoke1 texto visible: {t1!r}")
            if engine._events.list_events():
                raise AssertionError("smoke1: no debía crearse evento")
            st1 = engine._thread_store.get_state()
            if not st1.get("open"):
                raise AssertionError("smoke1: thread debía estar abierto")
            pend = st1.get("pending") or {}
            if pend.get("options") != ["07:00", "19:00"]:
                raise AssertionError(f"smoke1 pending.options: {pend!r}")

            t2, _, saved, _ = engine.process_message("a las 19")
            if "¿19 o 20" in (t2 or "").lower():
                raise AssertionError("smoke2: no debe aparecer «¿19 o 20?»")
            evs = engine._events.list_events()
            if len(evs) != 1:
                raise AssertionError(f"smoke2: un evento esperado, hay {len(evs)}")
            ev = evs[0]
            if str(ev.get("time_text")) != "19:00":
                raise AssertionError(f"smoke2 time_text: {ev.get('time_text')!r}")
            if "Luis" not in (ev.get("participants") or []):
                raise AssertionError(f"smoke2 participants: {ev.get('participants')!r}")
            st2 = engine._thread_store.get_state()
            if st2.get("open"):
                raise AssertionError("smoke2: thread debía cerrarse")

    print("smoke 1-2 OK (hora ambigua + continuación create)")


def smoke_3_4_need_context_update_flow(eid: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Devuelve las dos respuestas fake para need_context + ask update."""
    r1: dict[str, Any] = {
        "s": "need_context",
        "i": "event",
        "a": "update",
        "obj": {"time": "8"},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": {
            "domain": "calendar",
            "query": "events_by_person_and_time",
            "filters": {"people": ["Luis"], "time": "7"},
        },
    }
    r2: dict[str, Any] = {
        "s": "ask",
        "i": "event",
        "a": "update",
        "obj": {"time": "8"},
        "target": eid,
        "q": "¿Quieres cambiarla a las 8:00 o a las 20:00?",
        "r": None,
        "pending": {
            "field": "time",
            "options": ["08:00", "20:00"],
            "target": eid,
            "update_field": "time",
        },
        "ctx": None,
    }
    return r1, r2


def smoke_3_4() -> None:
    """v0.47.11 + v0.47.12: context_response ask update → ready update."""
    r5: dict[str, Any] = {
        "s": "ready",
        "i": "event",
        "a": "update",
        "obj": {"time": "20:00"},
        "target": None,
        "q": None,
        "r": "He cambiado la cita con Luis a las 20:00.",
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        row = engine._events.add_event(
            {
                "title": "cita con Luis",
                "date_text": "mañana",
                "time_text": "19:00",
                "participants": ["Luis"],
            }
        )
        eid = str(row["id"])
        r1, r2 = smoke_3_4_need_context_update_flow(eid)
        r5 = dict(r5)
        r5["target"] = eid

        seq = iter([r1, r2])

        def fake_ask_gpt_3(_payload: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq)

        with patch.object(engine_mod, "ask_gpt", side_effect=fake_ask_gpt_3):
            t3, _, _, _ = engine.process_message(
                "cambia la cita con Luis de las 7 a las 8"
            )
        _assert_no_uuid_in_visible(t3, "smoke3")
        if "¿Quieres cambiarla a las 8:00 o a las 20:00?" not in (t3 or ""):
            raise AssertionError(f"smoke3 pregunta cerrada: {t3!r}")
        ev_mid = engine._events.list_events()[0]
        if str(ev_mid.get("time_text")) != "19:00":
            raise AssertionError(
                f"smoke3: evento no debía modificarse aún, time_text={ev_mid.get('time_text')!r}"
            )
        st3 = engine._thread_store.get_state()
        if not st3.get("open"):
            raise AssertionError("smoke3: hilo debía quedar abierto")
        if (st3.get("pending") or {}).get("options") != ["08:00", "20:00"]:
            raise AssertionError(f"smoke3 pending: {st3.get('pending')!r}")

        with patch.object(engine_mod, "ask_gpt", return_value=r5):
            t4, _, upd, _ = engine.process_message("a las 20")

        if str(upd.get("time_text")) != "20:00":
            raise AssertionError(f"smoke4 time_text: {upd!r}")
        if len(engine._events.list_events()) != 1:
            raise AssertionError("smoke4: no debe duplicarse el evento")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke4: hilo debía cerrarse")

    print("smoke 3-4 OK (need_context + ask update + update real)")


def smoke_5_query() -> None:
    """v0.47.13: need_context query + answer — sin mutar eventos."""
    r1: dict[str, Any] = {
        "s": "need_context",
        "i": "event",
        "a": "query",
        "obj": {},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": {
            "domain": "calendar",
            "query": "events_by_person",
            "filters": {"people": ["Luis"]},
        },
    }
    r2: dict[str, Any] = {
        "s": "answer",
        "i": "event",
        "a": "query",
        "obj": {},
        "target": None,
        "q": None,
        "r": "Tienes una cita con Luis mañana a las 20:00.",
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        engine._events.add_event(
            {
                "title": "cita con Luis",
                "date_text": "mañana",
                "time_text": "20:00",
                "participants": ["Luis"],
            }
        )
        before = [dict(x) for x in engine._events.list_events()]
        seq = iter([r1, r2])

        def fake_ask_gpt(_payload: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq)

        with patch.object(engine_mod, "ask_gpt", side_effect=fake_ask_gpt):
            t5, _, _, _ = engine.process_message(
                "a qué hora tengo la cita con Luis"
            )
        _assert_no_uuid_in_visible(t5, "smoke5")
        if "20:00" not in (t5 or "") and "20" not in (t5 or ""):
            raise AssertionError(f"smoke5: se esperaba hora en respuesta: {t5!r}")
        after = engine._events.list_events()
        if len(after) != len(before):
            raise AssertionError("smoke5: no debe crearse/borrarse eventos")
        if after[0].get("time_text") != before[0].get("time_text"):
            raise AssertionError("smoke5: no debe modificarse el evento")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke5: hilo debía cerrarse tras answer")

    print("smoke 5 OK (consulta eventos need_context + answer)")


def main() -> int:
    try:
        smoke_1_2_ambiguous_then_continue()
        smoke_3_4()
        smoke_5_query()
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print("smoke_backend_minimal_v047: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
