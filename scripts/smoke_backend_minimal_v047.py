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
            if "raw_text" in ev:
                raise AssertionError(
                    "smoke2: el evento no debe persistirse con raw_text como dominio final"
                )
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


def smoke_6_delete_confirmation() -> None:
    """v0.47.15: ask delete_confirmation → tras sí, ready/delete borra."""
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        row = engine._events.add_event(
            {
                "title": "cita con Luis",
                "date_text": "mañana",
                "time_text": "20:00",
                "participants": ["Luis"],
            }
        )
        eid = str(row["id"])
        q_txt = (
            "¿Confirmas que quieres borrar la cita con Luis de mañana a las 20:00?"
        )
        r_confirm: dict[str, Any] = {
            "s": "ask",
            "i": "event",
            "a": "delete",
            "obj": {},
            "target": eid,
            "q": q_txt,
            "r": None,
            "pending": {
                "field": "delete_confirmation",
                "options": ["sí", "no"],
                "target": eid,
            },
            "ctx": None,
        }
        r_del: dict[str, Any] = {
            "s": "ready",
            "i": "event",
            "a": "delete",
            "obj": {},
            "target": eid,
            "q": None,
            "r": "He borrado la cita con Luis.",
            "pending": None,
            "ctx": None,
        }
        seq = iter([r_confirm, r_del])

        def fake_ask(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq)

        with patch.object(engine_mod, "ask_gpt", side_effect=fake_ask):
            t1, _, _, _ = engine.process_message("borra la cita con Luis")
        _assert_no_uuid_in_visible(t1, "smoke6_ask")
        if t1.strip() != q_txt:
            raise AssertionError(f"smoke6 texto confirmación: {t1!r}")
        if len(engine._events.list_events()) != 1:
            raise AssertionError("smoke6: no debía borrarse antes de confirmar")
        st = engine._thread_store.get_state()
        if not st.get("open"):
            raise AssertionError("smoke6: hilo debía quedar abierto")
        pend = st.get("pending") or {}
        if pend.get("field") != "delete_confirmation":
            raise AssertionError(f"smoke6 pending.field: {pend!r}")
        if pend.get("options") != ["sí", "no"]:
            raise AssertionError(f"smoke6 pending.options: {pend!r}")
        tid_top = str(st.get("target") or "").strip()
        tid_pend = str(pend.get("target") or "").strip()
        if tid_top != eid and tid_pend != eid:
            raise AssertionError("smoke6: target debe almacenarse para continuar")

        with patch.object(engine_mod, "ask_gpt", return_value=r_del):
            t2, _, _, _ = engine.process_message("sí")
        _assert_no_uuid_in_visible(t2, "smoke6_ready")
        if "He borrado la cita con Luis." not in t2:
            raise AssertionError(f"smoke6 respuesta tras borrar: {t2!r}")
        if engine._events.list_events():
            raise AssertionError("smoke6: el evento debía borrarse")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke6: hilo debe cerrarse")

    print("smoke 6 OK (confirmación borrado evento)")


def smoke_7_8_multiple_candidates_update() -> None:
    """v0.47.17: need_context + ask target_selection → continue + ask hora sin ready."""
    r_need: dict[str, Any] = {
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
            "query": "events_by_person",
            "filters": {"people": ["Luis"]},
        },
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        ev1 = engine._events.add_event(
            {
                "title": "cita con Luis",
                "date_text": "mañana",
                "time_text": "10:00",
                "participants": ["Luis"],
            }
        )
        ev2 = engine._events.add_event(
            {
                "title": "cita con Luis",
                "date_text": "viernes",
                "time_text": "19:00",
                "participants": ["Luis"],
            }
        )
        id1 = str(ev1["id"])
        id2 = str(ev2["id"])
        q_sel = (
            "Tengo varias citas con Luis. ¿Cuál quieres modificar: "
            "la de mañana a las 10:00 o la del viernes a las 19:00?"
        )
        r_pick: dict[str, Any] = {
            "s": "ask",
            "i": "event",
            "a": "update",
            "obj": {"time": "8"},
            "target": None,
            "q": q_sel,
            "r": None,
            "pending": {
                "field": "target_selection",
                "candidates": [
                    {"id": id1, "label": "cita con Luis · mañana · 10:00"},
                    {"id": id2, "label": "cita con Luis · viernes · 19:00"},
                ],
                "original_action": "update",
                "original_obj": {"time": "8"},
            },
            "ctx": None,
        }
        seq1 = iter([r_need, r_pick])

        def fake1(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq1)

        with patch.object(engine_mod, "ask_gpt", side_effect=fake1):
            t1, _, _, _ = engine.process_message(
                "cambia la cita con Luis a las 8"
            )
        _assert_no_uuid_in_visible(t1, "smoke7")
        if t1.strip() != q_sel:
            raise AssertionError(f"smoke7 pregunta selección: {t1!r}")
        evs = engine._events.list_events()
        if len(evs) != 2:
            raise AssertionError("smoke7: debía haber dos eventos")
        by_id = {str(e.get("id")): e for e in evs}
        if str(by_id[id1].get("time_text")) != "10:00":
            raise AssertionError("smoke7: evento 1 no debía modificarse")
        if str(by_id[id2].get("time_text")) != "19:00":
            raise AssertionError("smoke7: evento 2 no debía modificarse")
        st7 = engine._thread_store.get_state()
        if not st7.get("open"):
            raise AssertionError("smoke7: hilo abierto")
        p7 = st7.get("pending") or {}
        if p7.get("field") != "target_selection":
            raise AssertionError(f"smoke7 pending: {p7!r}")

        r_time: dict[str, Any] = {
            "s": "ask",
            "i": "event",
            "a": "update",
            "obj": {"time": "8"},
            "target": id2,
            "q": "¿Quieres cambiarla a las 8:00 o a las 20:00?",
            "r": None,
            "pending": {
                "field": "time",
                "options": ["08:00", "20:00"],
                "target": id2,
                "update_field": "time",
            },
            "ctx": None,
        }
        with patch.object(engine_mod, "ask_gpt", return_value=r_time):
            t2, _, _, _ = engine.process_message("la del viernes")
        _assert_no_uuid_in_visible(t2, "smoke8")
        if "8:00" not in t2 and "20:00" not in t2:
            raise AssertionError(f"smoke8 pregunta hora: {t2!r}")
        evs2 = engine._events.list_events()
        by_id2 = {str(e.get("id")): e for e in evs2}
        if str(by_id2[id1].get("time_text")) != "10:00":
            raise AssertionError("smoke8: evento 1 intacto")
        if str(by_id2[id2].get("time_text")) != "19:00":
            raise AssertionError("smoke8: evento 2 aún sin persistir el cambio")
        st8 = engine._thread_store.get_state()
        if not st8.get("open"):
            raise AssertionError("smoke8: hilo abierto (pendiente hora)")
        p8 = st8.get("pending") or {}
        if p8.get("field") != "time":
            raise AssertionError(f"smoke8 pending: {p8!r}")
        if str(st8.get("target") or "").strip() != id2 and str(p8.get("target") or "").strip() != id2:
            raise AssertionError("smoke8: target id2")

    print("smoke 7-8 OK (varios candidatos update)")


def smoke_9_task_create_basic() -> None:
    """v0.47.18: creación básica de tareas (ready/task/create)."""
    # Caso A: tarea con fecha textual
    r_a: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "create",
        "obj": {
            "title": "comprar leche",
            "date": "mañana",
        },
        "target": None,
        "q": None,
        "r": "He creado la tarea «comprar leche» para mañana.",
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_a):
            ta, _, _, _ = engine.process_message("recuérdame comprar leche mañana")
        if "comprar leche" not in ta and r_a["r"] not in ta:
            raise AssertionError(f"smoke9A respuesta: {ta!r}")
        ts = engine._tasks.list_tasks()
        if len(ts) != 1:
            raise AssertionError(f"smoke9A: una tarea esperada, hay {len(ts)}")
        tsk = ts[0]
        if tsk.get("title") != "comprar leche":
            raise AssertionError(f"smoke9A title: {tsk!r}")
        if str(tsk.get("date_text")) != "mañana":
            raise AssertionError(f"smoke9A date_text: {tsk!r}")
        if tsk.get("completed") is not False:
            raise AssertionError("smoke9A completed debe ser False")
        if "raw_text" in tsk:
            raise AssertionError("smoke9A no raw_text en tarea")
        if engine._events.list_events() or engine._notes.list_notes():
            raise AssertionError("smoke9A no evento ni nota")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke9A hilo cerrado")

    # Caso B: sin fecha
    r_b: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "create",
        "obj": {
            "title": "llamar al dentista",
        },
        "target": None,
        "q": None,
        "r": "He creado la tarea «llamar al dentista».",
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_b):
            tb, _, _, _ = engine.process_message(
                "crea una tarea para llamar al dentista"
            )
        if len(engine._tasks.list_tasks()) != 1:
            raise AssertionError("smoke9B: una tarea")
        tsk_b = engine._tasks.list_tasks()[0]
        if tsk_b.get("title") != "llamar al dentista":
            raise AssertionError(f"smoke9B title: {tsk_b!r}")
        if tsk_b.get("date_text") is not None:
            raise AssertionError("smoke9B date_text debe ser None")
        if tsk_b.get("time_text") is not None:
            raise AssertionError("smoke9B time_text debe ser None")
        if tsk_b.get("completed") is not False:
            raise AssertionError("smoke9B completed")
        if "¿Te refieres a las" in tb or "7:00" in tb:
            raise AssertionError("smoke9B no debe preguntar hora ambigua de evento")
        if engine._events.list_events():
            raise AssertionError("smoke9B sin eventos")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke9B hilo cerrado")

    # Caso C: sin título en obj
    r_c: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "create",
        "obj": {},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_c):
            tc, _, _, _ = engine.process_message("crea una tarea")
        if engine._tasks.list_tasks():
            raise AssertionError("smoke9C no debe crear tarea")
        low = (tc or "").lower()
        if "título" not in low and "no he podido guardar" not in low:
            raise AssertionError(f"smoke9C mensaje error esperado: {tc!r}")
        if engine._events.list_events() or engine._notes.list_notes():
            raise AssertionError("smoke9C sin evento ni nota")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke9C hilo cerrado")

    print("smoke 9 OK (task create básico)")


def main() -> int:
    try:
        smoke_1_2_ambiguous_then_continue()
        smoke_3_4()
        smoke_5_query()
        smoke_6_delete_confirmation()
        smoke_7_8_multiple_candidates_update()
        smoke_9_task_create_basic()
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print("smoke_backend_minimal_v047: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
