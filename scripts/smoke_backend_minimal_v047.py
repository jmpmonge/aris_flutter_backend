#!/usr/bin/env python3
"""Smokes de regresión del backend mínimo v0.47 — sin llamadas reales a OpenAI."""

from __future__ import annotations

import json
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
from backend.core.payload_builder import build_payload
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


def _assert_ask_question_visible(tv: str, label: str) -> None:
    """Si el mock GPT devolvió ask, visible debe tener pregunta (sin exigir paráfrasis fija)."""
    if not (tv or "").strip():
        raise AssertionError(f"{label}: texto visible vacío en ask")
    if "?" not in tv:
        raise AssertionError(f"{label}: esperada interrogación visible: {tv!r}")


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
            _assert_ask_question_visible(t1, "smoke1")
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
        _assert_ask_question_visible(t3, "smoke3")
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
        if "8" not in (t2 or "") and "20" not in (t2 or ""):
            raise AssertionError(f"smoke8 debe mencionar horas en pregunta: {t2!r}")
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


def smoke_10_note_create_basic() -> None:
    """v0.47.19: creación básica de notas (ready/note/create)."""
    r_a: dict[str, Any] = {
        "s": "ready",
        "i": "note",
        "a": "create",
        "obj": {
            "title": "idea para Aris",
            "content": "separar tareas y notas",
        },
        "target": None,
        "q": None,
        "r": "He guardado la nota «idea para Aris».",
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_a):
            ta, _, _, _ = engine.process_message(
                "guarda una nota: idea para Aris, separar tareas y notas"
            )
        if "idea para Aris" not in ta and r_a["r"] not in ta:
            raise AssertionError(f"smoke10A respuesta: {ta!r}")
        notes = engine._notes.list_notes()
        if len(notes) != 1:
            raise AssertionError(f"smoke10A una nota esperada: {notes!r}")
        n_a = notes[0]
        if n_a.get("title") != "idea para Aris":
            raise AssertionError(f"smoke10A title: {n_a!r}")
        if n_a.get("content") != "separar tareas y notas":
            raise AssertionError(f"smoke10A content: {n_a!r}")
        if "raw_text" in n_a:
            raise AssertionError("smoke10A sin raw_text en nota")
        if engine._events.list_events() or engine._tasks.list_tasks():
            raise AssertionError("smoke10A sin eventos ni tareas")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke10A hilo cerrado")

    r_b: dict[str, Any] = {
        "s": "ready",
        "i": "note",
        "a": "create",
        "obj": {
            "content": "Aris debe responder corto por defecto",
        },
        "target": None,
        "q": None,
        "r": "He guardado la nota.",
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_b):
            engine.process_message(
                "apunta esta idea: Aris debe responder corto por defecto"
            )
        notes_b = engine._notes.list_notes()
        if len(notes_b) != 1:
            raise AssertionError("smoke10B una nota")
        nb = notes_b[0]
        if str(nb.get("content") or "").strip() != (
            "Aris debe responder corto por defecto"
        ):
            raise AssertionError(f"smoke10B content: {nb!r}")
        tit = nb.get("title")
        if tit is not None and str(tit).strip() != "":
            raise AssertionError(f"smoke10B title debería ser vacío/None: {tit!r}")
        if engine._events.list_events() or engine._tasks.list_tasks():
            raise AssertionError("smoke10B sin eventos ni tareas")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke10B hilo cerrado")

    r_c: dict[str, Any] = {
        "s": "ready",
        "i": "note",
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
            tc, _, _, _ = engine.process_message("guarda una nota")
        if engine._notes.list_notes():
            raise AssertionError("smoke10C no crear nota")
        low_c = (tc or "").lower()
        if (
            "contenido" not in low_c
            and "no he podido guardar" not in low_c
        ):
            raise AssertionError(f"smoke10C error esperado: {tc!r}")
        if engine._events.list_events() or engine._tasks.list_tasks():
            raise AssertionError("smoke10C sin evento ni tarea")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke10C hilo cerrado")

    print("smoke 10 OK (note create básico)")


def smoke_11_task_query_basic() -> None:
    """v0.47.20: need_context task/query → context_response + answer."""
    r_need_all: dict[str, Any] = {
        "s": "need_context",
        "i": "task",
        "a": "query",
        "obj": {},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": {
            "domain": "tasks",
            "query": "list_tasks",
            "filters": {},
        },
    }
    r_ans_two: dict[str, Any] = {
        "s": "answer",
        "i": "task",
        "a": "query",
        "obj": {},
        "target": None,
        "q": None,
        "r": (
            "Tienes estas tareas: comprar leche para mañana "
            "y llamar al dentista."
        ),
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        engine._tasks.add_task(
            {"title": "comprar leche", "date_text": "mañana"}
        )
        engine._tasks.add_task({"title": "llamar al dentista"})
        before = sorted(
            [(str(x.get("id")), x.get("title")) for x in engine._tasks.list_tasks()],
            key=lambda p: p[0],
        )
        seq = iter([r_need_all, r_ans_two])

        def fak(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq)

        with patch.object(engine_mod, "ask_gpt", side_effect=fak):
            t1, _, _, _ = engine.process_message("¿Qué tareas tengo?")
        if "comprar leche" not in t1 or "llamar al dentista" not in t1:
            raise AssertionError(f"smoke11A: {t1!r}")
        _assert_no_uuid_in_visible(t1, "smoke11A")
        after = sorted(
            [(str(x.get("id")), x.get("title")) for x in engine._tasks.list_tasks()],
            key=lambda p: p[0],
        )
        if before != after:
            raise AssertionError(f"smoke11A persistencia cambió: {after!r}")
        if len(after) != 2:
            raise AssertionError("smoke11A dos tareas")
        if engine._events.list_events() or engine._notes.list_notes():
            raise AssertionError("smoke11A sin event/nota")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke11A hilo cerrado")

    r_ans_none: dict[str, Any] = {
        "s": "answer",
        "i": "task",
        "a": "query",
        "obj": {},
        "target": None,
        "q": None,
        "r": "No encuentro tareas con esos datos.",
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        seq2 = iter([r_need_all, r_ans_none])

        def fak2(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq2)

        with patch.object(engine_mod, "ask_gpt", side_effect=fak2):
            tb, _, _, _ = engine.process_message("¿Qué tareas tengo?")
        if (
            "No encuentro tareas" not in tb
            and r_ans_none["r"] != tb.strip()
        ):
            raise AssertionError(f"smoke11B vacío: {tb!r}")
        if engine._tasks.list_tasks():
            raise AssertionError("smoke11B sin crear tareas")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke11B hilo cerrado")

    r_need_m: dict[str, Any] = {
        "s": "need_context",
        "i": "task",
        "a": "query",
        "obj": {},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": {
            "domain": "tasks",
            "query": "list_tasks",
            "filters": {"date": "mañana"},
        },
    }
    r_ans_m: dict[str, Any] = {
        "s": "answer",
        "i": "task",
        "a": "query",
        "obj": {},
        "target": None,
        "q": None,
        "r": "Para mañana tienes la tarea comprar leche.",
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        engine._tasks.add_task(
            {"title": "comprar leche", "date_text": "mañana"}
        )
        engine._tasks.add_task(
            {"title": "llamar al dentista", "date_text": "viernes"}
        )
        before_c = [(str(x["id"]), x["title"]) for x in engine._tasks.list_tasks()]
        seq3 = iter([r_need_m, r_ans_m])

        def fak3(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq3)

        with patch.object(engine_mod, "ask_gpt", side_effect=fak3):
            tc, _, _, _ = engine.process_message(
                "¿Qué tareas tengo mañana?"
            )
        if "comprar leche" not in tc:
            raise AssertionError(f"smoke11C: {tc!r}")
        if "dentista" in tc.lower():
            raise AssertionError("smoke11C no debe mezclar otra fecha en mock corto")
        _assert_no_uuid_in_visible(tc, "smoke11C")
        after_c = {(str(x["id"]), x["title"]) for x in engine._tasks.list_tasks()}
        if {(b[0], b[1]) for b in before_c} != after_c:
            raise AssertionError("smoke11C tareas modificadas")

    print("smoke 11 OK (consulta de tareas básica)")


def smoke_12_note_query_basic() -> None:
    """v0.47.21: need_context note/query → context_response + answer."""
    r_need_all: dict[str, Any] = {
        "s": "need_context",
        "i": "note",
        "a": "query",
        "obj": {},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": {
            "domain": "notes",
            "query": "list_notes",
            "filters": {},
        },
    }
    r_ans_two: dict[str, Any] = {
        "s": "answer",
        "i": "note",
        "a": "query",
        "obj": {},
        "target": None,
        "q": None,
        "r": "Tienes estas notas: idea para Aris y voz.",
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        engine._notes.add_note(
            {"title": "idea para Aris", "content": "separar tareas y notas"}
        )
        engine._notes.add_note(
            {"title": "voz", "content": "probar respuesta corta por defecto"}
        )
        before = sorted(
            [(str(x.get("id")), x.get("title")) for x in engine._notes.list_notes()],
            key=lambda p: p[0],
        )
        seq = iter([r_need_all, r_ans_two])

        def fak(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq)

        with patch.object(engine_mod, "ask_gpt", side_effect=fak):
            t1, _, _, _ = engine.process_message("¿Qué notas tengo?")
        if "idea para Aris" not in t1 or "voz" not in t1:
            raise AssertionError(f"smoke12A: {t1!r}")
        _assert_no_uuid_in_visible(t1, "smoke12A")
        after = sorted(
            [(str(x.get("id")), x.get("title")) for x in engine._notes.list_notes()],
            key=lambda p: p[0],
        )
        if before != after:
            raise AssertionError(f"smoke12A persistencia cambió: {after!r}")
        if len(after) != 2:
            raise AssertionError("smoke12A dos notas")
        if engine._events.list_events() or engine._tasks.list_tasks():
            raise AssertionError("smoke12A sin evento ni tarea")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke12A hilo cerrado")

    r_ans_none: dict[str, Any] = {
        "s": "answer",
        "i": "note",
        "a": "query",
        "obj": {},
        "target": None,
        "q": None,
        "r": "No encuentro notas con esos datos.",
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        seq2 = iter([r_need_all, r_ans_none])

        def fak2(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq2)

        with patch.object(engine_mod, "ask_gpt", side_effect=fak2):
            tb, _, _, _ = engine.process_message("¿Qué notas tengo?")
        if (
            "No encuentro notas" not in tb
            and r_ans_none["r"] != tb.strip()
        ):
            raise AssertionError(f"smoke12B vacío: {tb!r}")
        if engine._notes.list_notes():
            raise AssertionError("smoke12B sin crear notas")
        if engine._events.list_events() or engine._tasks.list_tasks():
            raise AssertionError("smoke12B sin evento ni tarea")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke12B hilo cerrado")

    r_need_txt: dict[str, Any] = {
        "s": "need_context",
        "i": "note",
        "a": "query",
        "obj": {},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": {
            "domain": "notes",
            "query": "list_notes",
            "filters": {
                "text": "Aris",
            },
        },
    }
    r_ans_txt: dict[str, Any] = {
        "s": "answer",
        "i": "note",
        "a": "query",
        "obj": {},
        "target": None,
        "q": None,
        "r": "Sobre Aris tienes la nota idea para Aris.",
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        engine._notes.add_note(
            {"title": "idea para Aris", "content": "separar tareas y notas"}
        )
        engine._notes.add_note(
            {"title": "voz", "content": "probar respuesta corta por defecto"}
        )
        before_c = {
            (str(x["id"]), x.get("title")) for x in engine._notes.list_notes()
        }
        seq3 = iter([r_need_txt, r_ans_txt])

        def fak3(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq3)

        with patch.object(engine_mod, "ask_gpt", side_effect=fak3):
            tc, _, _, _ = engine.process_message(
                "¿Tengo alguna nota sobre Aris?"
            )
        if "Aris" not in tc:
            raise AssertionError(f"smoke12C: {tc!r}")
        _assert_no_uuid_in_visible(tc, "smoke12C")
        after_c = {
            (str(x["id"]), x.get("title")) for x in engine._notes.list_notes()
        }
        if before_c != after_c:
            raise AssertionError("smoke12C notas modificadas")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke12C hilo cerrado")

    print("smoke 12 OK (consulta de notas básica)")


def smoke_13_event_create_continue_not_update() -> None:
    """v0.47.22: crear evento tras ask hora ambigua — debe ser ready/create, no update."""
    r1: dict[str, Any] = {
        "s": "ask",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "time": "17k",
        },
        "target": None,
        "q": "¿Te refieres a las 17:00 o a las 5:00?",
        "r": None,
        "pending": {
            "field": "time",
            "options": ["17:00", "05:00"],
        },
        "ctx": None,
    }
    r2: dict[str, Any] = {
        "s": "ready",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "time": "17:00",
        },
        "target": None,
        "q": None,
        "r": (
            "He guardado la cita con el médico para el lunes "
            "a las 17:00."
        ),
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        seq = iter([r1, r2])

        def fak(_payload: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq)

        with patch.object(engine_mod, "ask_gpt", side_effect=fak):
            t1, _, _, _ = engine.process_message(
                "cita con el medico el lunes a las 17k"
            )

        _assert_ask_question_visible(t1, "smoke13A")

        if engine._events.list_events():
            raise AssertionError("smoke13A evento antes de tiempo")

        st1 = engine._thread_store.get_state()
        if not st1.get("open"):
            raise AssertionError(f"smoke13A thread debía estar abierto: {st1!r}")
        if st1.get("intent") != "event":
            raise AssertionError(f"smoke13A intent debía event: {st1!r}")
        pend = st1.get("pending") or {}
        if pend.get("field") != "time":
            raise AssertionError(f"smoke13A pending.field time: {pend!r}")
        if pend.get("options") != ["17:00", "05:00"]:
            raise AssertionError(f"smoke13A pending.options: {pend!r}")
        if st1.get("target"):
            raise AssertionError(f"smoke13A target debía absent/null: {st1!r}")

        with patch.object(engine_mod, "ask_gpt", side_effect=lambda _p: r2):
            t2, _, _, _ = engine.process_message("a las 17h")

        msg_mod = (
            "no sé qué evento quieres modificar"
        ).lower()
        if msg_mod in (t2 or "").lower():
            raise AssertionError(f"smoke13B no debe sonar a update: {t2!r}")

        evs = engine._events.list_events()
        if len(evs) != 1:
            raise AssertionError(f"smoke13B un evento: {evs!r}")
        ev = evs[0]
        if str(ev.get("title")) != "cita con el médico":
            raise AssertionError(f"smoke13B title {ev.get('title')!r}")
        if str(ev.get("date_text")) != "lunes":
            raise AssertionError(f"smoke13B date_text {ev.get('date_text')!r}")
        if str(ev.get("time_text")) != "17:00":
            raise AssertionError(f"smoke13B time_text {ev.get('time_text')!r}")
        if engine._tasks.list_tasks() or engine._notes.list_notes():
            raise AssertionError("smoke13B sin tarea ni nota")
        st2 = engine._thread_store.get_state()
        if st2.get("open"):
            raise AssertionError("smoke13B thread debía cerrarse")

    print("smoke 13 OK (creación evento continúa como create tras hora pendiente)")


def smoke_14_event_24h_time_and_weekday_text() -> None:
    """v0.47.23: 17h lista → sin ask; día «lunes» persiste tras continuar desde 5↔17."""
    r_direct: dict[str, Any] = {
        "s": "ready",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "time": "17:00",
        },
        "target": None,
        "q": None,
        "r": (
            "He guardado la cita con el médico para el lunes "
            "a las 17:00."
        ),
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_direct):
            tv, _, _, _ = engine.process_message(
                "cita con el médico el lunes a las 17h"
            )
        low = (tv or "").lower()
        if "¿te refieres" in low:
            raise AssertionError(f"smoke14A no debe preguntar: {tv!r}")
        if "5:00" in (tv or "") or "05:00" in (tv or ""):
            raise AssertionError(f"smoke14A no debe mezcla 5:00: {tv!r}")
        evs = engine._events.list_events()
        if len(evs) != 1:
            raise AssertionError(f"smoke14A un evento: {evs!r}")
        ev = evs[0]
        if str(ev.get("title")) != "cita con el médico":
            raise AssertionError(ev.get("title"))
        dt = ev.get("date_text")
        if str(dt) != "lunes":
            raise AssertionError(f"smoke14A date_text debe lunes: {dt!r}")
        if str(dt).lower() in ("domingo", "hoy"):
            raise AssertionError(f"smoke14A date_text ilegal {dt!r}")
        if str(ev.get("time_text")) != "17:00":
            raise AssertionError(ev.get("time_text"))
        if engine._tasks.list_tasks() or engine._notes.list_notes():
            raise AssertionError("smoke14A sin tarea/nota")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke14A hilo cerrado")

    r_ask_amb: dict[str, Any] = {
        "s": "ask",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "time": "5",
        },
        "target": None,
        "q": "¿Te refieres a las 5:00 o a las 17:00?",
        "r": None,
        "pending": {"field": "time", "options": ["05:00", "17:00"]},
        "ctx": None,
    }
    r_continue: dict[str, Any] = {
        "s": "ready",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "time": "17:00",
        },
        "target": None,
        "q": None,
        "r": (
            "He guardado la cita con el médico para el lunes "
            "a las 17:00."
        ),
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        seq = iter([r_ask_amb, r_continue])

        def fak(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq)

        with patch.object(engine_mod, "ask_gpt", side_effect=fak):
            t1, _, _, _ = engine.process_message(
                "cita con el médico el lunes a las 5"
            )
        if engine._events.list_events():
            raise AssertionError("smoke14B1 sin evento antes")
        st1 = engine._thread_store.get_state()
        if not st1.get("open"):
            raise AssertionError(st1)
        ob = st1.get("object") or {}
        if not isinstance(ob, dict) or ob.get("date") != "lunes":
            raise AssertionError(f"smoke14B1 object.date lunes: {ob!r}")
        if st1.get("target"):
            raise AssertionError(f"smoke14B1 sin target UUID: {st1!r}")

        with patch.object(engine_mod, "ask_gpt", return_value=r_continue):
            t2, _, _, _ = engine.process_message("a las 17h")

        msg_mod = "no sé qué evento quieres modificar"
        if msg_mod in (t2 or "").lower():
            raise AssertionError(f"smoke14B2: {t2!r}")

        evs2 = engine._events.list_events()
        if len(evs2) != 1:
            raise AssertionError(evs2)
        evb = evs2[0]
        if str(evb.get("date_text")) != "lunes":
            raise AssertionError(f"smoke14B2 date_text {evb.get('date_text')!r}")
        if str(evb.get("time_text")) != "17:00":
            raise AssertionError(evb.get("time_text"))
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("cerrar hilo smoke14B")

    print("smoke 14 OK (17h lista + día lunes estable)")


def smoke_15_gpt_contract_clean_event_timing() -> None:
    """v0.47.28: mocks deterministas — ready persist sin ask pedida; ambiguo abre pending."""

    r_13_ready: dict[str, Any] = {
        "s": "ready",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "time": "13:00",
        },
        "target": None,
        "q": None,
        "r": (
            "He guardado la cita con el médico para el lunes "
            "a las 13:00."
        ),
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_13_ready):
            tv, _, _, _ = engine.process_message(
                "cita con el médico el lunes a las 13h"
            )
        low = (tv or "").lower()
        if "¿te refieres" in low:
            raise AssertionError(f"smoke15A no debe preguntar: {tv!r}")
        if "1:00" in (tv or ""):
            raise AssertionError(f"smoke15A no debe mezcla 1:00: {tv!r}")
        evs_a = engine._events.list_events()
        if len(evs_a) != 1:
            raise AssertionError(f"smoke15A un evento: {evs_a!r}")
        ev_a = evs_a[0]
        if str(ev_a.get("date_text")) != "lunes":
            raise AssertionError(f"smoke15A date_text {ev_a.get('date_text')!r}")
        if str(ev_a.get("time_text")) != "13:00":
            raise AssertionError(f"smoke15A time_text {ev_a.get('time_text')!r}")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke15A hilo cerrado")
        if engine._tasks.list_tasks() or engine._notes.list_notes():
            raise AssertionError("smoke15A sin tarea/nota")

    r_15_ready: dict[str, Any] = {
        "s": "ready",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "time": "15:00",
        },
        "target": None,
        "q": None,
        "r": (
            "He guardado la cita con el médico para el lunes "
            "a las 15:00."
        ),
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_15_ready):
            tv_b, _, _, _ = engine.process_message(
                "cita con el médico el lunes a las 15h"
            )
        low_b = (tv_b or "").lower()
        if "¿te refieres" in low_b:
            raise AssertionError(f"smoke15B no debe preguntar: {tv_b!r}")
        if "3:00" in (tv_b or ""):
            raise AssertionError(f"smoke15B no debe mezcla 3:00: {tv_b!r}")
        evs_b = engine._events.list_events()
        if len(evs_b) != 1:
            raise AssertionError(f"smoke15B un evento: {evs_b!r}")
        ev_b = evs_b[0]
        if str(ev_b.get("date_text")) != "lunes":
            raise AssertionError(f"smoke15B date_text {ev_b.get('date_text')!r}")
        if str(ev_b.get("time_text")) != "15:00":
            raise AssertionError(f"smoke15B time_text {ev_b.get('time_text')!r}")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke15B hilo cerrado")

    r_5_ask: dict[str, Any] = {
        "s": "ask",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "time": "5",
        },
        "target": None,
        "q": "¿Te refieres a las 5:00 o a las 17:00?",
        "r": None,
        "pending": {"field": "time", "options": ["05:00", "17:00"]},
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_5_ask):
            tv_c, _, _, _ = engine.process_message(
                "cita con el médico el lunes a las 5"
            )
        _assert_ask_question_visible(tv_c, "smoke15C")
        if engine._events.list_events():
            raise AssertionError("smoke15C sin evento todavía")
        st_c = engine._thread_store.get_state()
        if not st_c.get("open"):
            raise AssertionError(f"smoke15C hilo abierto: {st_c!r}")
        pend_c = st_c.get("pending") or {}
        if pend_c.get("field") != "time":
            raise AssertionError(f"smoke15C pending.field time: {pend_c!r}")

    print(
        "smoke 15 OK (ready sin ask cuando mock-ready; pending time si mock ask)"
    )


def smoke_16_event_continue_variants_mocked() -> None:
    """v0.47.26 + v0.47.28: mocks listas persisten sin ask pedida por smokes."""

    r_20_ready: dict[str, Any] = {
        "s": "ready",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "time": "20:00",
        },
        "target": None,
        "q": None,
        "r": (
            "He guardado la cita con el médico para el lunes "
            "a las 20:00."
        ),
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_20_ready):
            tv, _, _, _ = engine.process_message(
                "cita con el médico el lunes a las 20h"
            )
        low = (tv or "").lower()
        out = tv or ""
        if "¿te refieres" in low:
            raise AssertionError(f"smoke16A no debe preguntar: {tv!r}")
        if "20:00 or" in out.lower():
            raise AssertionError(f"smoke16A no debe frase tipo '20:00 or': {tv!r}")
        evs_a = engine._events.list_events()
        if len(evs_a) != 1:
            raise AssertionError(f"smoke16A un evento: {evs_a!r}")
        ev_a = evs_a[0]
        if str(ev_a.get("date_text")) != "lunes":
            raise AssertionError(f"smoke16A date_text {ev_a.get('date_text')!r}")
        if str(ev_a.get("time_text")) != "20:00":
            raise AssertionError(f"smoke16A time_text {ev_a.get('time_text')!r}")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke16A hilo debía estar cerrado")
        if engine._tasks.list_tasks() or engine._notes.list_notes():
            raise AssertionError("smoke16A sin tarea/nota")

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_20_ready):
            tv_b, _, _, _ = engine.process_message(
                "cita con el médico el lunes a las 20"
            )
        low_b = (tv_b or "").lower()
        if "¿te refieres" in low_b:
            raise AssertionError(f"smoke16B no debe preguntar: {tv_b!r}")
        out_b = tv_b or ""
        if "20:00 or" in out_b.lower():
            raise AssertionError(f"smoke16B frase tipo or: {tv_b!r}")
        evs_b = engine._events.list_events()
        if len(evs_b) != 1:
            raise AssertionError(f"smoke16B un evento: {evs_b!r}")
        ev_b = evs_b[0]
        if str(ev_b.get("date_text")) != "lunes":
            raise AssertionError(ev_b.get("date_text"))
        if str(ev_b.get("time_text")) != "20:00":
            raise AssertionError(ev_b.get("time_text"))
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke16B hilo debía estar cerrado")

    r_8_ask: dict[str, Any] = {
        "s": "ask",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "time": "8",
        },
        "target": None,
        "q": "¿Te refieres a las 8:00 o a las 20:00?",
        "r": None,
        "pending": {"field": "time", "options": ["08:00", "20:00"]},
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_8_ask):
            tv_c, _, _, _ = engine.process_message(
                "cita con el médico el lunes a las 8"
            )
        _assert_ask_question_visible(tv_c, "smoke16C")
        if engine._events.list_events():
            raise AssertionError("smoke16C sin evento aún")
        st_c = engine._thread_store.get_state()
        if not st_c.get("open"):
            raise AssertionError(f"smoke16C hilo debía quedar abierto: {st_c!r}")
        if (st_c.get("pending") or {}).get("field") != "time":
            raise AssertionError(f"smoke16C pending.field time: {st_c.get('pending')!r}")

    print("smoke 16 OK (variantes GPT mockeadas; ask cuando mock lo pide)")


def smoke_17_event_create_with_date_iso() -> None:
    """v0.47.27: GPT debe devolver date_iso con fecha clara — mock valida persistencia."""

    r_with_iso: dict[str, Any] = {
        "s": "ready",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "date_iso": "2026-05-18",
            "time": "20:00",
        },
        "target": None,
        "q": None,
        "r": (
            "He guardado la cita con el médico para el lunes "
            "a las 20:00."
        ),
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_with_iso):
            engine.process_message("cita con el médico el lunes a las 20h")
        evs = engine._events.list_events()
        if len(evs) != 1:
            raise AssertionError(f"smoke17A esperaba 1 evento: {evs!r}")
        ev = evs[0]
        if str(ev.get("title")) != "cita con el médico":
            raise AssertionError(ev.get("title"))
        if str(ev.get("date_text")) != "lunes":
            raise AssertionError(ev.get("date_text"))
        if str(ev.get("date_iso")) != "2026-05-18":
            raise AssertionError(f"smoke17A date_iso {ev.get('date_iso')!r}")
        if str(ev.get("time_text")) != "20:00":
            raise AssertionError(ev.get("time_text"))
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke17A hilo debía estar cerrado")
        if engine._tasks.list_tasks() or engine._notes.list_notes():
            raise AssertionError("smoke17A sin tarea/nota")

    r_without_iso: dict[str, Any] = {
        "s": "ready",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita",
            "date": "lunes",
            "time": "20:00",
        },
        "target": None,
        "q": None,
        "r": "He guardado la cita para el lunes a las 20:00.",
        "pending": None,
        "ctx": None,
    }

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_without_iso):
            engine.process_message("cita para el lunes a las 20h")
        evs_b = engine._events.list_events()
        if len(evs_b) != 1:
            raise AssertionError(evs_b)
        eb = evs_b[0]
        if str(eb.get("date_text")) != "lunes":
            raise AssertionError(eb.get("date_text"))
        if eb.get("date_iso") is not None:
            raise AssertionError(f"smoke17B date_iso debía absent/None {eb.get('date_iso')!r}")
        if str(eb.get("time_text")) != "20:00":
            raise AssertionError(eb.get("time_text"))
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke17B hilo debía estar cerrado")
        if engine._tasks.list_tasks() or engine._notes.list_notes():
            raise AssertionError("smoke17B sin tarea/nota")

    print("smoke 17 OK (create con date_iso y sin él)")


def smoke_18_clean_event_card_contract() -> None:
    """v0.47.28: ficha mock + hilo incompleto/continuar/duda tiempo — sólo ejecuta GPT JSON."""

    obj_full: dict[str, Any] = {
        "title": "cita con el médico",
        "date": "lunes",
        "date_iso": "2026-05-18",
        "time": "15:00",
        "people": [],
        "location": None,
        "description": None,
        "duration_minutes": None,
    }

    r_ready_a: dict[str, Any] = {
        "s": "ready",
        "i": "event",
        "a": "create",
        "obj": obj_full,
        "target": None,
        "q": None,
        "r": (
            "He guardado la cita con el médico para el lunes "
            "a las 15:00."
        ),
        "pending": None,
        "ctx": None,
    }

    # Caso A
    with tempfile.TemporaryDirectory() as d_a:
        base = Path(d_a)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_ready_a):
            engine.process_message("cita con el médico el lunes a las 15h")
        evsa = engine._events.list_events()
        if len(evsa) != 1:
            raise AssertionError(f"smoke18A eventos={evsa!r}")
        ev = evsa[0]
        if str(ev.get("title")) != "cita con el médico":
            raise AssertionError(ev.get("title"))
        if str(ev.get("date_text")) != "lunes":
            raise AssertionError(ev.get("date_text"))
        if str(ev.get("date_iso")) != "2026-05-18":
            raise AssertionError(ev.get("date_iso"))
        if str(ev.get("time_text")) != "15:00":
            raise AssertionError(ev.get("time_text"))
        if engine._tasks.list_tasks() or engine._notes.list_notes():
            raise AssertionError("smoke18A sin tarea/nota")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke18A hilo cerrado")

    r_inc_ask: dict[str, Any] = {
        "s": "ask",
        "i": "event",
        "a": "create",
        "obj": {"title": "cita con el médico"},
        "target": None,
        "q": "¿Qué día y a qué hora quieres poner la cita?",
        "r": None,
        "pending": {"field": "date_time"},
        "ctx": None,
    }

    # Caso B
    with tempfile.TemporaryDirectory() as d_b:
        base = Path(d_b)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_inc_ask):
            tb, _, _, _ = engine.process_message(
                "pon una cita con el médico"
            )
        _assert_ask_question_visible(tb, "smoke18B")
        if engine._events.list_events():
            raise AssertionError("smoke18B sin crear evento aún")
        stb = engine._thread_store.get_state()
        if not stb.get("open"):
            raise AssertionError(f"smoke18B hilo abierto: {stb!r}")
        if str(stb.get("intent")) != "event":
            raise AssertionError(stb.get("intent"))
        ob = stb.get("object") or {}
        if not isinstance(ob, dict) or ob.get("title") != "cita con el médico":
            raise AssertionError(f"smoke18B object.title: {ob!r}")
        if (stb.get("pending") or {}).get("field") != "date_time":
            raise AssertionError(f"smoke18B pending.field: {stb.get('pending')!r}")

    # Casos C/D comparten mocks de ask distintos
    r_gap_ask_time: dict[str, Any] = {
        "s": "ask",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "date_iso": "2026-05-18",
            "time": "3",
        },
        "target": None,
        "q": "¿Te refieres a las 3:00 o a las 15:00?",
        "r": None,
        "pending": {"field": "time"},
        "ctx": None,
    }

    # Caso C
    with tempfile.TemporaryDirectory() as d_c:
        base = Path(d_c)
        engine = _make_engine(base)
        seq_c = iter([r_inc_ask, r_ready_a])

        def fc(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq_c)

        with patch.object(engine_mod, "ask_gpt", side_effect=fc):
            tc1, _, _, _ = engine.process_message(
                "pon una cita con el médico"
            )
        _assert_ask_question_visible(tc1, "smoke18C1")
        if engine._events.list_events():
            raise AssertionError("smoke18C1 sin evento")
        if not engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke18C1 abierto")

        with patch.object(engine_mod, "ask_gpt", return_value=r_ready_a):
            tc2, _, _, _ = engine.process_message(
                "el lunes a las 15h"
            )
        if "no sé qué evento" in (tc2 or "").lower():
            raise AssertionError(f"smoke18C2 no debe oler a update: {tc2!r}")
        evsc = engine._events.list_events()
        if len(evsc) != 1:
            raise AssertionError(f"smoke18C eventos={evsc!r}")
        if str(evsc[0].get("date_iso")) != "2026-05-18":
            raise AssertionError(evsc[0].get("date_iso"))
        if str(evsc[0].get("time_text")) != "15:00":
            raise AssertionError(evsc[0].get("time_text"))
        if engine._notes.list_notes() or engine._tasks.list_tasks():
            raise AssertionError("smoke18C sólo evento")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke18C cerrar hilo")

    # Caso D
    with tempfile.TemporaryDirectory() as d_d:
        base = Path(d_d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_gap_ask_time):
            td, _, _, _ = engine.process_message(
                "cita con el médico el lunes a las 3"
            )
        _assert_ask_question_visible(td, "smoke18D")
        if engine._events.list_events():
            raise AssertionError("smoke18D sin evento persistido")
        std = engine._thread_store.get_state()
        if not std.get("open"):
            raise AssertionError(std)
        pdd = std.get("pending") or {}
        if pdd.get("field") != "time":
            raise AssertionError(pdd)

    print(
        "smoke 18 OK (contrato ficha mock: lista, incompleta, continuación, duda tiempo)"
    )


def _assert_empty_notes_tasks(engine: ArisMinimalEngine, label: str) -> None:
    notes = engine._notes.list_notes()
    tasks = engine._tasks.list_tasks()
    if notes:
        raise AssertionError(f"{label}: notes_store debe vacío, hay {notes!r}")
    if tasks:
        raise AssertionError(f"{label}: tasks_store debe vacío, hay {tasks!r}")


def smoke_19_continue_guard_no_note_task() -> None:
    """v0.47.29: en hilo abierto, mocks coherentes no crean nota/tarea en continuaciones."""
    # ----- CASO A: hora tras cita con día fijado -----
    r_a1: dict[str, Any] = {
        "s": "ask",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "date_iso": "2026-05-18",
        },
        "target": None,
        "q": "¿A qué hora quieres poner la cita?",
        "r": None,
        "pending": {"field": "time"},
        "ctx": None,
    }
    r_a2: dict[str, Any] = {
        "s": "ready",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "date_iso": "2026-05-18",
            "time": "20:00",
            "people": [],
            "location": None,
            "description": None,
            "duration_minutes": None,
        },
        "target": None,
        "q": None,
        "r": "He guardado la cita con el médico para el lunes a las 20:00.",
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        seq_a = iter([r_a1, r_a2])

        def fa(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq_a)

        with patch.object(engine_mod, "ask_gpt", side_effect=fa):
            engine.process_message(
                "pon una cita con el médico el lunes"
            )
        if engine._events.list_events():
            raise AssertionError("smoke19A1: sin evento tras primer turno")
        st1 = engine._thread_store.get_state()
        if not st1.get("open"):
            raise AssertionError("smoke19A1: hilo abierto")
        if str(st1.get("intent")) != "event":
            raise AssertionError(st1.get("intent"))
        pend1 = st1.get("pending") or {}
        if pend1.get("field") != "time":
            raise AssertionError(f"smoke19A1 pending: {pend1!r}")
        _assert_empty_notes_tasks(engine, "smoke19A1")

        with patch.object(engine_mod, "ask_gpt", return_value=r_a2):
            engine.process_message("a las 20:00")

        evsa = engine._events.list_events()
        if len(evsa) != 1:
            raise AssertionError(f"smoke19A2 eventos: {evsa!r}")
        ev_a = evsa[0]
        if str(ev_a.get("date_iso")) != "2026-05-18":
            raise AssertionError(ev_a.get("date_iso"))
        if str(ev_a.get("time_text")) != "20:00":
            raise AssertionError(ev_a.get("time_text"))
        _assert_empty_notes_tasks(engine, "smoke19A2")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke19A2: hilo cerrado")

    # ----- CASO B: fecha+hora en una sola réplica -----
    r_b1: dict[str, Any] = {
        "s": "ask",
        "i": "event",
        "a": "create",
        "obj": {"title": "cita con el médico"},
        "target": None,
        "q": "¿Qué día y a qué hora quieres poner la cita?",
        "r": None,
        "pending": {"field": "date_time"},
        "ctx": None,
    }
    r_b2: dict[str, Any] = {
        "s": "ready",
        "i": "event",
        "a": "create",
        "obj": {
            "title": "cita con el médico",
            "date": "lunes",
            "date_iso": "2026-05-18",
            "time": "15:00",
            "people": [],
            "location": None,
            "description": None,
            "duration_minutes": None,
        },
        "target": None,
        "q": None,
        "r": "He guardado la cita con el médico para el lunes a las 15:00.",
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        seq_b = iter([r_b1, r_b2])

        def fb(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq_b)

        with patch.object(engine_mod, "ask_gpt", side_effect=fb):
            engine.process_message("pon una cita con el médico")
            engine.process_message("el lunes a las 15h")
        evsb = engine._events.list_events()
        if len(evsb) != 1:
            raise AssertionError(f"smoke19B eventos: {evsb!r}")
        _assert_empty_notes_tasks(engine, "smoke19B")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke19B hilo cerrado")
        for row in engine._notes.list_notes():
            c = str(row.get("content") or "")
            if "el lunes a las 15h" in c or c.strip() == "el lunes a las 15h":
                raise AssertionError(f"smoke19B no nota con input: {row!r}")

    # ----- CASO C: delete_confirmation + «sí» -----
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        row = engine._events.add_event(
            {
                "title": "cita con el médico",
                "date_text": "lunes",
                "date_iso": "2026-05-18",
                "time_text": "15:00",
                "participants": [],
            }
        )
        eid = str(row["id"])
        q_c = (
            "¿Confirmas que quieres borrar la cita con el médico del "
            "lunes a las 15:00?"
        )
        r_c1: dict[str, Any] = {
            "s": "ask",
            "i": "event",
            "a": "delete",
            "obj": {},
            "target": eid,
            "q": q_c,
            "r": None,
            "pending": {
                "field": "delete_confirmation",
                "options": ["sí", "no"],
                "target": eid,
            },
            "ctx": None,
        }
        r_c2: dict[str, Any] = {
            "s": "ready",
            "i": "event",
            "a": "delete",
            "obj": {},
            "target": eid,
            "q": None,
            "r": "He borrado la cita.",
            "pending": None,
            "ctx": None,
        }
        seq_c = iter([r_c1, r_c2])

        def fc(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq_c)

        with patch.object(engine_mod, "ask_gpt", side_effect=fc):
            engine.process_message("borra la cita")
        if not engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke19C hilo esperado tras ask delete")
        with patch.object(engine_mod, "ask_gpt", return_value=r_c2):
            engine.process_message("sí")
        if engine._events.list_events():
            raise AssertionError("smoke19C evento debe borrarse")
        for row_n in engine._notes.list_notes():
            if str(row_n.get("content") or "").strip() in ("sí", "si"):
                raise AssertionError(f"smoke19C sin nota sí: {row_n!r}")
        if engine._tasks.list_tasks():
            raise AssertionError("smoke19C sin tarea")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke19C hilo cerrado")

    # ----- CASO D: target_selection «la segunda» -----
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
                "time_text": "17:00",
                "participants": ["Luis"],
            }
        )
        id1 = str(ev1["id"])
        id2 = str(ev2["id"])
        q_d = (
            "Tengo varias citas con Luis. ¿Cuál quieres modificar: "
            "la de mañana a las 10:00 o la del viernes a las 17:00?"
        )
        r_d1: dict[str, Any] = {
            "s": "ask",
            "i": "event",
            "a": "update",
            "obj": {"time": "9"},
            "target": None,
            "q": q_d,
            "r": None,
            "pending": {
                "field": "target_selection",
                "candidates": [
                    {"id": id1, "label": "cita con Luis · mañana · 10:00"},
                    {"id": id2, "label": "cita con Luis · viernes · 17:00"},
                ],
                "original_action": "update",
                "original_obj": {"time": "9"},
            },
            "ctx": None,
        }
        r_d2: dict[str, Any] = {
            "s": "ready",
            "i": "event",
            "a": "update",
            "target": id2,
            "obj": {"time": "11:00"},
            "q": None,
            "r": "He cambiado la hora.",
            "pending": None,
            "ctx": None,
        }
        seq_d = iter([r_d1, r_d2])

        def fd(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq_d)

        with patch.object(engine_mod, "ask_gpt", side_effect=fd):
            engine.process_message("cambia la cita con Luis")
            engine.process_message("la segunda")

        notes_d = engine._notes.list_notes()
        for rn in notes_d:
            cn = str(rn.get("content") or "").strip().lower()
            if "segunda" in cn or cn == "la segunda":
                raise AssertionError(f"smoke19D no nota selección: {rn!r}")
        if engine._tasks.list_tasks():
            raise AssertionError("smoke19D sin tareas")
        ev_after = engine._events.list_events()
        by_id = {str(e.get("id")): e for e in ev_after}
        if str(by_id[id1].get("time_text")) != "10:00":
            raise AssertionError("smoke19D ev1 intacto")
        if str(by_id[id2].get("time_text")) != "11:00":
            raise AssertionError("smoke19D ev2 actualizado")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke19D hilo debe cerrarse tras ready/update")

    print("smoke 19 OK (guardia continuaciones sin nota/tarea accidental)")


def smoke_20_task_complete_basic() -> None:
    """v0.47.30: completar tarea vía ready/task/complete + need_context / selección."""
    r_vis_done = (
        "He marcado la tarea «comprar leche» como completada."
    )

    # --- CASO A: target claro ---
    with tempfile.TemporaryDirectory() as d_a:
        base = Path(d_a)
        engine = _make_engine(base)
        row = engine._tasks.add_task(
            {"title": "comprar leche", "date_text": "mañana"}
        )
        tid = str(row["id"])
        r_a: dict[str, Any] = {
            "s": "ready",
            "i": "task",
            "a": "complete",
            "obj": {},
            "target": tid,
            "q": None,
            "r": r_vis_done,
            "pending": None,
            "ctx": None,
        }
        with patch.object(engine_mod, "ask_gpt", return_value=r_a):
            tv, _, saved, _ = engine.process_message(
                "marca comprar leche como hecha"
            )
        if "completada" not in (tv or "").lower():
            raise AssertionError(f"smoke20A visible: {tv!r}")
        if engine._events.list_events():
            raise AssertionError("smoke20A sin eventos")
        if engine._notes.list_notes():
            raise AssertionError("smoke20A sin notas")
        tasks_a = engine._tasks.list_tasks()
        by_id_a = {str(t.get("id")): t for t in tasks_a}
        ta = by_id_a.get(tid)
        if ta is None:
            raise AssertionError("smoke20A tarea debe existir")
        if ta.get("completed") is not True:
            raise AssertionError("smoke20A completed=True")
        if saved is None or saved.get("completed") is not True:
            raise AssertionError(f"smoke20A saved: {saved!r}")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke20A hilo cerrado")

    # --- CASO B: sin target ---
    r_b: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "complete",
        "obj": {},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d_b:
        base = Path(d_b)
        engine = _make_engine(base)
        engine._tasks.add_task({"title": "persistir incompleta"})
        with patch.object(engine_mod, "ask_gpt", return_value=r_b):
            tb, _, _, _ = engine.process_message(
                "marca una tarea como hecha"
            )
        if (
            "concret" not in (tb or "").lower()
            and "qué tarea" not in (tb or "").lower()
        ):
            raise AssertionError(f"smoke20B debía pedir concreción: {tb!r}")
        if any(
            bool(t.get("completed")) for t in engine._tasks.list_tasks()
        ):
            raise AssertionError("smoke20B ninguna debe completarse")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke20B hilo debe cerrarse")

    # --- CASO C: need_context + segunda llamada ---
    r_c1: dict[str, Any] = {
        "s": "need_context",
        "i": "task",
        "a": "complete",
        "obj": {"title": "comprar leche"},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": {
            "domain": "tasks",
            "query": "list_tasks",
            "filters": {"completed": False, "title": "comprar leche"},
        },
    }
    with tempfile.TemporaryDirectory() as d_c:
        base = Path(d_c)
        engine = _make_engine(base)
        rc = engine._tasks.add_task(
            {"title": "comprar leche", "date_text": "mañana"}
        )
        tid_c = str(rc["id"])
        r_c2: dict[str, Any] = {
            "s": "ready",
            "i": "task",
            "a": "complete",
            "obj": {},
            "target": tid_c,
            "q": None,
            "r": r_vis_done,
            "pending": None,
            "ctx": None,
        }
        seq_c = iter([r_c1, r_c2])

        def fc(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq_c)

        with patch.object(engine_mod, "ask_gpt", side_effect=fc):
            engine.process_message("marca comprar leche como hecha")
        tsk = engine._tasks.list_tasks()
        match = next(
            (t for t in tsk if str(t.get("id")) == tid_c), None
        )
        if not match or match.get("completed") is not True:
            raise AssertionError(f"smoke20C completed: {match!r}")
        if engine._events.list_events() or engine._notes.list_notes():
            raise AssertionError("smoke20C sin evento/nota")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke20C hilo cerrado")

    # --- CASO D + E: selección ---
    q_sel = (
        "Tengo varias tareas parecidas. ¿Cuál quieres completar: "
        "llamar a Luis o llamar al dentista?"
    )
    r_d1: dict[str, Any] = {
        "s": "need_context",
        "i": "task",
        "a": "complete",
        "obj": {"title": "llamar"},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": {
            "domain": "tasks",
            "query": "list_tasks",
            "filters": {"completed": False, "title": "llamar"},
        },
    }

    with tempfile.TemporaryDirectory() as d_de:
        base = Path(d_de)
        engine = _make_engine(base)
        t_luis = engine._tasks.add_task({"title": "llamar a Luis"})
        t_den = engine._tasks.add_task({"title": "llamar al dentista"})
        id1 = str(t_luis["id"])
        id2 = str(t_den["id"])
        r_d2: dict[str, Any] = {
            "s": "ask",
            "i": "task",
            "a": "complete",
            "obj": {},
            "target": None,
            "q": q_sel,
            "r": None,
            "pending": {
                "field": "target_selection",
                "candidates": [
                    {"id": id1, "label": "llamar a Luis"},
                    {"id": id2, "label": "llamar al dentista"},
                ],
                "original_action": "complete",
            },
            "ctx": None,
        }
        r_d3: dict[str, Any] = {
            "s": "ready",
            "i": "task",
            "a": "complete",
            "obj": {},
            "target": id2,
            "q": None,
            "r": (
                "He marcado la tarea «llamar al dentista» como completada."
            ),
            "pending": None,
            "ctx": None,
        }
        seq_de = iter([r_d1, r_d2])

        def fde(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq_de)

        with patch.object(engine_mod, "ask_gpt", side_effect=fde):
            t1, _, _, _ = engine.process_message("marca llamar como hecha")
        _assert_no_uuid_in_visible(t1, "smoke20D")
        if t1.strip() != q_sel:
            raise AssertionError(f"smoke20D pregunta: {t1!r}")
        if any(bool(t.get("completed")) for t in engine._tasks.list_tasks()):
            raise AssertionError("smoke20D nadie completado aún")
        st_d = engine._thread_store.get_state()
        if not st_d.get("open"):
            raise AssertionError(f"smoke20D abierto: {st_d!r}")
        if (st_d.get("pending") or {}).get("field") != "target_selection":
            raise AssertionError(f"smoke20D pending {st_d!r}")

        with patch.object(engine_mod, "ask_gpt", return_value=r_d3):
            t2, _, _, _ = engine.process_message("la del dentista")
        _assert_no_uuid_in_visible(t2, "smoke20E")
        lst = engine._tasks.list_tasks()
        by = {str(x.get("id")): x for x in lst}
        if by[id2].get("completed") is not True:
            raise AssertionError(f"smoke20E dentista {by[id2]!r}")
        if by[id1].get("completed") is True:
            raise AssertionError("smoke20E Luis sigue pendiente")
        needle = "la del dentista"
        for rn in engine._notes.list_notes():
            if needle in str(rn.get("content") or ""):
                raise AssertionError(f"smoke20E nota accidental {rn!r}")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke20E hilo cerrado")

    print("smoke 20 OK (complete tarea mock + need_context / selección)")


def smoke_21_clean_task_card_contract() -> None:
    """v0.47.32: crear tarea desde contrato GPT (ficha normalizada date_iso/tags/priority)."""

    raw_user = "__smoke_clean_task_contract__"

    # --- CASO A ---
    r_a: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "create",
        "obj": {
            "title": "llamar al banco",
            "description": "preguntar por los seguros",
            "date": "mañana",
            "date_iso": "2026-05-18",
            "time": "10:00",
            "priority": "normal",
            "tags": ["Banco", "Seguro"],
        },
        "target": None,
        "q": None,
        "r": "He creado la tarea «llamar al banco».",
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_a):
            engine.process_message(raw_user)
        ts = engine._tasks.list_tasks()
        if len(ts) != 1:
            raise AssertionError(f"smoke21A: una tarea, hay {len(ts)}")
        task = ts[0]
        if task.get("title") != "llamar al banco":
            raise AssertionError(f"smoke21A title: {task!r}")
        if task.get("description") != "preguntar por los seguros":
            raise AssertionError(f"smoke21A description: {task!r}")
        if str(task.get("date_text")) != "mañana":
            raise AssertionError(f"smoke21A date_text: {task!r}")
        if str(task.get("date_iso")) != "2026-05-18":
            raise AssertionError(f"smoke21A date_iso: {task!r}")
        if str(task.get("time_text")) != "10:00":
            raise AssertionError(f"smoke21A time_text: {task!r}")
        if task.get("priority") != "normal":
            raise AssertionError(f"smoke21A priority: {task!r}")
        if task.get("tags") != ["Banco", "Seguro"]:
            raise AssertionError(f"smoke21A tags: {task!r}")
        if task.get("completed") is not False:
            raise AssertionError("smoke21A completed")
        if engine._events.list_events() or engine._notes.list_notes():
            raise AssertionError("smoke21A sin evento ni nota")

    # --- CASO B ---
    r_b: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "create",
        "obj": {
            "title": "enviar la solicitud",
            "description": None,
            "date": "mañana",
            "date_iso": "2026-05-18",
            "time": None,
            "priority": "high",
            "tags": [],
        },
        "target": None,
        "q": None,
        "r": "He creado la tarea «enviar la solicitud».",
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_b):
            engine.process_message(raw_user)
        tb = engine._tasks.list_tasks()[0]
        if tb.get("priority") != "high":
            raise AssertionError(f"smoke21B priority: {tb!r}")

    # --- CASO C ---
    r_c: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "create",
        "obj": {
            "title": "comprar leche",
            "priority": "normal",
            "tags": [],
        },
        "target": None,
        "q": None,
        "r": "He creado la tarea «comprar leche».",
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_c):
            engine.process_message(raw_user)
        tc = engine._tasks.list_tasks()[0]
        if tc.get("title") != "comprar leche":
            raise AssertionError(f"smoke21C title: {tc!r}")
        if tc.get("priority") != "normal":
            raise AssertionError(f"smoke21C priority: {tc!r}")
        if tc.get("tags") != []:
            raise AssertionError(f"smoke21C tags: {tc!r}")
        if tc.get("date_text") is not None:
            raise AssertionError(f"smoke21C date_text: {tc!r}")
        if tc.get("date_iso") is not None:
            raise AssertionError(f"smoke21C date_iso: {tc!r}")
        if tc.get("time_text") is not None:
            raise AssertionError(f"smoke21C time_text: {tc!r}")

    # --- CASO D: prioridad inválida ---
    r_d: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "create",
        "obj": {
            "title": "revisar informe",
            "priority": "medium",
            "tags": ["Trabajo"],
        },
        "target": None,
        "q": None,
        "r": "He creado la tarea «revisar informe».",
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_d):
            engine.process_message(raw_user)
        td = engine._tasks.list_tasks()[0]
        if td.get("priority") != "normal":
            raise AssertionError(f"smoke21D priority normalizada: {td!r}")

    print("smoke 21 OK (contrato limpio ficha de tarea v0.47.32)")


def smoke_22_task_delete_safe() -> None:
    """v0.47.35: borrar tareas vía ready/task/delete; GPT pide confirmación (borrado no semántico en Aris)."""
    r_vis_done = "He borrado la tarea «comprar leche»."

    # --- CASO A: ready/delete con target borra ---
    with tempfile.TemporaryDirectory() as d_a:
        base = Path(d_a)
        engine = _make_engine(base)
        row = engine._tasks.add_task({"title": "comprar leche"})
        tid = str(row["id"])
        r_a: dict[str, Any] = {
            "s": "ready",
            "i": "task",
            "a": "delete",
            "obj": {},
            "target": tid,
            "q": None,
            "r": r_vis_done,
            "pending": None,
            "ctx": None,
        }
        with patch.object(engine_mod, "ask_gpt", return_value=r_a):
            t1, cat, _, _ = engine.process_message("confirmo")
        _assert_no_uuid_in_visible(t1, "smoke22A")
        if r_vis_done not in (t1 or ""):
            raise AssertionError(f"smoke22A visible: {t1!r}")
        if cat != "tarea":
            raise AssertionError(f"smoke22A categoría: {cat!r}")
        if engine._tasks.list_tasks():
            raise AssertionError("smoke22A: tarea debía borrarse")
        if engine._notes.list_notes():
            raise AssertionError("smoke22A sin notas")
        if engine._events.list_events():
            raise AssertionError("smoke22A sin eventos")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke22A hilo cerrado")

    # --- CASO B: sin target no borra ---
    r_b: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "delete",
        "obj": {},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d_b:
        base = Path(d_b)
        engine = _make_engine(base)
        engine._tasks.add_task({"title": "persistir"})
        with patch.object(engine_mod, "ask_gpt", return_value=r_b):
            tb, _, _, _ = engine.process_message("cualquier cosa")
        if "concret" not in (tb or "").lower():
            raise AssertionError(f"smoke22B: {tb!r}")
        if not engine._tasks.list_tasks():
            raise AssertionError("smoke22B tarea debe seguir")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke22B hilo cerrado")

    # --- CASOS C + D: need_context → ask confirmación; luego sí → borra ---
    q_c = (
        "¿Confirmas que quieres borrar la tarea «comprar leche»?"
    )
    r_c1: dict[str, Any] = {
        "s": "need_context",
        "i": "task",
        "a": "delete",
        "obj": {},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": {
            "domain": "tasks",
            "query": "list_tasks",
            "filters": {"title": "comprar leche"},
        },
    }

    with tempfile.TemporaryDirectory() as d_cd:
        base = Path(d_cd)
        engine = _make_engine(base)
        rc_row = engine._tasks.add_task({"title": "comprar leche"})
        tid_cd = str(rc_row["id"])
        r_c2_eff: dict[str, Any] = {
            "s": "ask",
            "i": "task",
            "a": "delete",
            "obj": {},
            "target": tid_cd,
            "q": q_c,
            "r": None,
            "pending": {
                "field": "delete_confirmation",
                "target": tid_cd,
                "original_action": "delete",
                "options": ["sí", "no"],
            },
            "ctx": None,
        }
        r_d_ready_eff: dict[str, Any] = {
            "s": "ready",
            "i": "task",
            "a": "delete",
            "obj": {},
            "target": tid_cd,
            "q": None,
            "r": r_vis_done,
            "pending": None,
            "ctx": None,
        }

        seq_cd = iter([r_c1, r_c2_eff])

        def f_cd(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq_cd)

        with patch.object(engine_mod, "ask_gpt", side_effect=f_cd):
            tc, _, _, _ = engine.process_message("__borrar_comprar_leche__")
        _assert_no_uuid_in_visible(tc, "smoke22C")
        if tc.strip() != q_c:
            raise AssertionError(f"smoke22C q: {tc!r}")
        if not engine._tasks.list_tasks():
            raise AssertionError("smoke22C tarea intacta")
        st_c = engine._thread_store.get_state()
        if not st_c.get("open"):
            raise AssertionError("smoke22C hilo abierto")
        penc = st_c.get("pending") or {}
        if penc.get("field") != "delete_confirmation":
            raise AssertionError(f"smoke22C pending {penc!r}")

        with patch.object(engine_mod, "ask_gpt", return_value=r_d_ready_eff):
            td, _, _, _ = engine.process_message("sí")
        _assert_no_uuid_in_visible(td, "smoke22D")
        if engine._tasks.list_tasks():
            raise AssertionError("smoke22D borrada")
        for rn in engine._notes.list_notes():
            c = str(rn.get("content") or "")
            if c.strip().lower() in ("sí", "si"):
                raise AssertionError(f"smoke22D nota sí: {rn!r}")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke22D hilo cerrado")

    # --- CASO E: no cancela borrado ---
    with tempfile.TemporaryDirectory() as d_e:
        base = Path(d_e)
        engine = _make_engine(base)
        te = engine._tasks.add_task({"title": "se queda"})
        tid_e = str(te["id"])
        q_e = "¿Confirmas borrar?"
        engine._thread_store.save_state(
            {
                "open": True,
                "intent": "task",
                "object": {},
                "last_question": q_e,
                "pending": {
                    "field": "delete_confirmation",
                    "target": tid_e,
                    "original_action": "delete",
                },
                "target": tid_e,
            }
        )
        r_e: dict[str, Any] = {
            "s": "answer",
            "i": "task",
            "a": "delete",
            "obj": {},
            "target": None,
            "q": None,
            "r": "De acuerdo, no borro la tarea.",
            "pending": None,
            "ctx": None,
        }
        with patch.object(engine_mod, "ask_gpt", return_value=r_e):
            te_out, _, _, _ = engine.process_message("no")
        _assert_no_uuid_in_visible(te_out, "smoke22E")
        if not engine._tasks.list_tasks():
            raise AssertionError("smoke22E tarea debe existir")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke22E hilo cerrado")
        for rn in engine._notes.list_notes():
            tx = str(rn.get("content") or "").lower()
            if tx.strip() == "no":
                raise AssertionError(f"smoke22E nota no: {rn!r}")

    # --- CASOS F + G: varias → selección → confirmación (no borra aún en G) ---
    q_sel = (
        "He encontrado varias tareas parecidas. ¿Cuál quieres borrar?"
    )
    r_f1: dict[str, Any] = {
        "s": "need_context",
        "i": "task",
        "a": "delete",
        "obj": {},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": {
            "domain": "tasks",
            "query": "list_tasks",
            "filters": {"title": "llamar"},
        },
    }
    q_g = (
        "¿Confirmas que quieres borrar la tarea «llamar al dentista»?"
    )
    with tempfile.TemporaryDirectory() as d_fg:
        base = Path(d_fg)
        engine = _make_engine(base)
        t_luis = engine._tasks.add_task({"title": "llamar a Luis"})
        t_den = engine._tasks.add_task({"title": "llamar al dentista"})
        id1 = str(t_luis["id"])
        id2 = str(t_den["id"])
        r_f2: dict[str, Any] = {
            "s": "ask",
            "i": "task",
            "a": "delete",
            "obj": {},
            "target": None,
            "q": q_sel,
            "r": None,
            "pending": {
                "field": "target_selection",
                "original_action": "delete",
                "candidates": [
                    {"id": id1, "label": "llamar a Luis"},
                    {"id": id2, "label": "llamar al dentista"},
                ],
            },
            "ctx": None,
        }
        seq_fg = iter([r_f1, r_f2])

        def f_fg(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq_fg)

        with patch.object(engine_mod, "ask_gpt", side_effect=f_fg):
            tf, _, _, _ = engine.process_message("__borrar_llamar__")
        _assert_no_uuid_in_visible(tf, "smoke22F")
        if tf.strip() != q_sel:
            raise AssertionError(f"smoke22F: {tf!r}")
        if len(engine._tasks.list_tasks()) != 2:
            raise AssertionError("smoke22F ambas intactas")
        st_f = engine._thread_store.get_state()
        if not st_f.get("open"):
            raise AssertionError("smoke22F hilo abierto")
        if (st_f.get("pending") or {}).get("field") != "target_selection":
            raise AssertionError(f"smoke22F pending {st_f!r}")

        r_g_step: dict[str, Any] = {
            "s": "ask",
            "i": "task",
            "a": "delete",
            "obj": {},
            "target": id2,
            "q": q_g,
            "r": None,
            "pending": {
                "field": "delete_confirmation",
                "target": id2,
                "original_action": "delete",
            },
            "ctx": None,
        }
        needle = "la del dentista"
        with patch.object(engine_mod, "ask_gpt", return_value=r_g_step):
            tg, _, _, _ = engine.process_message(needle)
        _assert_no_uuid_in_visible(tg, "smoke22G")
        if len(engine._tasks.list_tasks()) != 2:
            raise AssertionError("smoke22G nadie borrado")
        by = {str(x.get("id")): x for x in engine._tasks.list_tasks()}
        if by[id1].get("title") != "llamar a Luis":
            raise AssertionError("smoke22G Luis")
        if by[id2].get("title") != "llamar al dentista":
            raise AssertionError("smoke22G dentista")
        st_g = engine._thread_store.get_state()
        if not st_g.get("open"):
            raise AssertionError("smoke22G hilo abierto")
        pg = st_g.get("pending") or {}
        if pg.get("field") != "delete_confirmation":
            raise AssertionError(f"smoke22G pending {pg!r}")
        if str(pg.get("target") or "").strip() != id2:
            raise AssertionError("smoke22G target dentist")
        for rn in engine._notes.list_notes():
            if needle in str(rn.get("content") or ""):
                raise AssertionError(f"smoke22G nota accidental {rn!r}")

    print("smoke 22 OK (borrado seguro de tareas v0.47.35)")


def smoke_23_task_update_basic() -> None:
    """v0.47.36: ready/task/update persiste campos vía update_task."""
    r_prior = "He marcado la tarea «llamar al banco» como prioritaria."

    # --- CASO A: update directo priority ---
    with tempfile.TemporaryDirectory() as d_a:
        base = Path(d_a)
        engine = _make_engine(base)
        row = engine._tasks.add_task(
            {"title": "llamar al banco", "priority": "normal"}
        )
        tid = str(row["id"])
        r_a: dict[str, Any] = {
            "s": "ready",
            "i": "task",
            "a": "update",
            "obj": {"priority": "high"},
            "target": tid,
            "q": None,
            "r": r_prior,
            "pending": None,
            "ctx": None,
        }
        with patch.object(engine_mod, "ask_gpt", return_value=r_a):
            tv, cat, _, _ = engine.process_message("__upd_a__")
        if r_prior not in (tv or ""):
            raise AssertionError(f"smoke23A: {tv!r}")
        if cat != "tarea":
            raise AssertionError(f"smoke23A cat: {cat!r}")
        lst = engine._tasks.list_tasks()
        if len(lst) != 1:
            raise AssertionError("smoke23A una sola tarea")
        if str(lst[0].get("id")) != tid or lst[0].get("priority") != "high":
            raise AssertionError(f"smoke23A task: {lst[0]!r}")
        if engine._notes.list_notes() or engine._events.list_events():
            raise AssertionError("smoke23A sin nota/evento")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke23A hilo cerrado")

    # --- CASO B: varios campos ---
    r_b_vis = "He actualizado la tarea «llamar al banco»."
    r_b: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "update",
        "obj": {
            "description": "preguntar por los seguros",
            "date": "mañana",
            "date_iso": "2026-05-18",
            "time": "10:00",
            "tags": ["Banco", "Seguro"],
        },
        "target": "<fill>",
        "q": None,
        "r": r_b_vis,
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d_b:
        base = Path(d_b)
        engine = _make_engine(base)
        rb_row = engine._tasks.add_task({"title": "llamar al banco"})
        tid_b = str(rb_row["id"])
        r_bf = dict(r_b)
        r_bf["target"] = tid_b
        with patch.object(engine_mod, "ask_gpt", return_value=r_bf):
            tb, _, saved, _ = engine.process_message("__upd_b__")
        if r_b_vis not in (tb or ""):
            raise AssertionError(f"smoke23B: {tb!r}")
        t = saved or engine._tasks.list_tasks()[0]
        if t.get("description") != "preguntar por los seguros":
            raise AssertionError(f"smoke23B desc {t!r}")
        if str(t.get("date_text")) != "mañana":
            raise AssertionError(f"smoke23B date_text {t!r}")
        if str(t.get("date_iso")) != "2026-05-18":
            raise AssertionError(f"smoke23B iso {t!r}")
        if str(t.get("time_text")) != "10:00":
            raise AssertionError(f"smoke23B time {t!r}")
        tags = list(t.get("tags") or [])
        if tags != ["Banco", "Seguro"]:
            raise AssertionError(f"smoke23B tags {tags!r}")

    # --- CASO C: sin target ---
    r_c_m: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "update",
        "obj": {"priority": "high"},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as d_c:
        base = Path(d_c)
        engine = _make_engine(base)
        engine._tasks.add_task({"title": "persistir prioridad"})
        with patch.object(engine_mod, "ask_gpt", return_value=r_c_m):
            tc, _, _, _ = engine.process_message("x")
        if (
            "concret" not in (tc or "").lower()
            and "modificar" not in (tc or "").lower()
        ):
            raise AssertionError(f"smoke23C: {tc!r}")
        if any(
            str(t.get("priority") or "") == "high"
            for t in engine._tasks.list_tasks()
        ):
            raise AssertionError("smoke23C no high")
        st_cf = engine._thread_store.get_state()
        if not st_cf.get("open"):
            raise AssertionError(f"smoke23C debe dejar el hilo abierto: {st_cf!r}")
        if str(st_cf.get("intent")) != "task":
            raise AssertionError(f"smoke23C intent task: {st_cf!r}")
        if (st_cf.get("pending") or {}).get("field") != "missing_target":
            raise AssertionError(f"smoke23C pending missing_target {st_cf!r}")

    # --- CASO D: obj vacío ---
    with tempfile.TemporaryDirectory() as d_d:
        base = Path(d_d)
        engine = _make_engine(base)
        rd = engine._tasks.add_task({"title": "sin cambios"})
        tid_d = str(rd["id"])
        r_d: dict[str, Any] = {
            "s": "ready",
            "i": "task",
            "a": "update",
            "obj": {},
            "target": tid_d,
            "q": None,
            "r": None,
            "pending": None,
            "ctx": None,
        }
        with patch.object(engine_mod, "ask_gpt", return_value=r_d):
            td, _, _, _ = engine.process_message("z")
        if "qué quieres cambiar" not in (td or "").lower():
            raise AssertionError(f"smoke23D: {td!r}")
        st = engine._tasks.list_tasks()[0]
        if st.get("title") != "sin cambios":
            raise AssertionError("smoke23D título intacto")
        std = engine._thread_store.get_state()
        if not std.get("open"):
            raise AssertionError(f"smoke23D debe dejar el hilo abierto {std!r}")
        if (std.get("pending") or {}).get("field") != "update_value":
            raise AssertionError(f"smoke23D pending update_value {std!r}")

    # --- CASO E: need_context → ready ---
    r_e1: dict[str, Any] = {
        "s": "need_context",
        "i": "task",
        "a": "update",
        "obj": {"priority": "high"},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": {
            "domain": "tasks",
            "query": "list_tasks",
            "filters": {"title": "llamar al banco"},
        },
    }
    with tempfile.TemporaryDirectory() as d_e:
        base = Path(d_e)
        engine = _make_engine(base)
        er = engine._tasks.add_task(
            {"title": "llamar al banco", "priority": "normal"}
        )
        tid_e = str(er["id"])
        r_e2: dict[str, Any] = {
            "s": "ready",
            "i": "task",
            "a": "update",
            "obj": {"priority": "high"},
            "target": tid_e,
            "q": None,
            "r": r_prior,
            "pending": None,
            "ctx": None,
        }
        seq_e = iter([r_e1, r_e2])

        def fe(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq_e)

        with patch.object(engine_mod, "ask_gpt", side_effect=fe):
            engine.process_message("__prioritaria_banco__")
        te = engine._tasks.list_tasks()[0]
        if te.get("priority") != "high":
            raise AssertionError(f"smoke23E {te!r}")

    # --- CASOS F + G: selección + update ---
    q_sel = "He encontrado varias tareas. ¿Cuál quieres modificar?"
    r_f1: dict[str, Any] = {
        "s": "need_context",
        "i": "task",
        "a": "update",
        "obj": {"priority": "high"},
        "target": None,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": {
            "domain": "tasks",
            "query": "list_tasks",
            "filters": {"title": "llamar"},
        },
    }
    with tempfile.TemporaryDirectory() as d_fg:
        base = Path(d_fg)
        engine = _make_engine(base)
        t_luis = engine._tasks.add_task({"title": "llamar a Luis"})
        t_banco = engine._tasks.add_task({"title": "llamar al banco"})
        id1 = str(t_luis["id"])
        id2 = str(t_banco["id"])
        r_f2: dict[str, Any] = {
            "s": "ask",
            "i": "task",
            "a": "update",
            "obj": {},
            "target": None,
            "q": q_sel,
            "r": None,
            "pending": {
                "field": "target_selection",
                "original_action": "update",
                "original_obj": {"priority": "high"},
                "candidates": [
                    {"id": id1, "label": "llamar a Luis"},
                    {"id": id2, "label": "llamar al banco"},
                ],
            },
            "ctx": None,
        }
        seq_f = iter([r_f1, r_f2])

        def ff(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq_f)

        with patch.object(engine_mod, "ask_gpt", side_effect=ff):
            tf, _, _, _ = engine.process_message("__prior_llamar__")
        _assert_no_uuid_in_visible(tf, "smoke23F")
        if tf.strip() != q_sel:
            raise AssertionError(f"smoke23F q: {tf!r}")
        for t in engine._tasks.list_tasks():
            if t.get("priority") == "high":
                raise AssertionError("smoke23F nadie prioritario aún")
        st_f = engine._thread_store.get_state()
        if not st_f.get("open"):
            raise AssertionError("smoke23F abierto")
        if (st_f.get("pending") or {}).get("field") != "target_selection":
            raise AssertionError(f"smoke23F pend {st_f!r}")

        needle = "la del banco"
        r_g: dict[str, Any] = {
            "s": "ready",
            "i": "task",
            "a": "update",
            "obj": {"priority": "high"},
            "target": id2,
            "q": None,
            "r": r_prior,
            "pending": None,
            "ctx": None,
        }
        with patch.object(engine_mod, "ask_gpt", return_value=r_g):
            tg, _, _, _ = engine.process_message(needle)
        _assert_no_uuid_in_visible(tg, "smoke23G")
        by_id = {str(x.get("id")): x for x in engine._tasks.list_tasks()}
        if by_id[id2].get("priority") != "high":
            raise AssertionError("smoke23G banco high")
        if by_id[id1].get("priority") != "normal":
            raise AssertionError(f"smoke23G Luis sigue normal {by_id[id1]!r}")
        for rn in engine._notes.list_notes():
            if needle in str(rn.get("content") or ""):
                raise AssertionError(f"smoke23G nota {rn!r}")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke23G cerrado")

    print("smoke 23 OK (actualización básica de tareas v0.47.36)")


def normalize_target_from_state(st: dict[str, Any]) -> str | None:
    """Helper smoke: mismo criterio que extract_event_target_id sobre estado persistido."""
    from backend.core.payload_builder import extract_event_target_id

    shim = {"target": st.get("target"), "pending": st.get("pending")}
    return extract_event_target_id(shim)


def smoke_24_recoverable_task_update_state() -> None:
    """Hilo incompleto en task/update (obj vacío, continuance, selección GPT). Sin ``recent`` en payload."""
    r_tpl_empty_patch: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "update",
        "obj": {},
        "target": "",
        "q": None,
        "r": None,
        "pending": None,
        "ctx": None,
    }

    # --- CASO A: obj vacío con target válido ---
    with tempfile.TemporaryDirectory() as d_a:
        base = Path(d_a)
        engine = _make_engine(base)
        tb = engine._tasks.add_task({"title": "llamar al banco"})
        idb = str(tb["id"])
        r_a: dict[str, Any] = {
            "s": "ready",
            "i": "task",
            "a": "update",
            "obj": {},
            "target": idb,
            "q": None,
            "r": None,
            "pending": None,
            "ctx": None,
        }
        with patch.object(engine_mod, "ask_gpt", return_value=r_a):
            t1, _, _, _ = engine.process_message("llamar al banco")
        if "qué quieres cambiar" not in (t1 or "").lower():
            raise AssertionError(f"smoke24A: {t1!r}")
        st_a = engine._thread_store.get_state()
        if not st_a.get("open"):
            raise AssertionError(f"smoke24A cerrado {st_a!r}")
        if str(st_a.get("intent")) != "task":
            raise AssertionError(f"smoke24A intent {st_a!r}")
        if str(st_a.get("action")) != "update":
            raise AssertionError(f"smoke24A action {st_a!r}")
        if normalize_target_from_state(st_a) != idb:
            raise AssertionError(f"smoke24A target {st_a!r}")
        pend_a = st_a.get("pending") or {}
        if pend_a.get("field") != "update_value":
            raise AssertionError(f"smoke24A pending.field {pend_a!r}")

    # --- CASO B: continuación completa ---
    r_b_vis = "He actualizado la descripción de la tarea «llamar al banco»."
    with tempfile.TemporaryDirectory() as d_b:
        base = Path(d_b)
        engine = _make_engine(base)
        tb = engine._tasks.add_task({"title": "llamar al banco"})
        id_bb = str(tb["id"])
        r_a2 = dict(r_tpl_empty_patch)
        r_a2["target"] = id_bb
        r_bf = {
            "s": "ready",
            "i": "task",
            "a": "update",
            "obj": {"description": "preguntar por los seguros vinculados"},
            "target": id_bb,
            "q": None,
            "r": r_b_vis,
            "pending": None,
            "ctx": None,
        }

        seq = iter([r_a2, r_bf])

        def fb(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq)

        with patch.object(engine_mod, "ask_gpt", side_effect=fb):
            engine.process_message("primer turno vacío obj")
            t2b, _, _, _ = engine.process_message(
                "preguntar por los seguros vinculados"
            )
        if r_b_vis not in (t2b or ""):
            raise AssertionError(f"smoke24B resp {t2b!r}")
        row = engine._tasks.list_tasks()[0]
        if row.get("description") != "preguntar por los seguros vinculados":
            raise AssertionError(f"smoke24B desc {row!r}")
        if engine._notes.list_notes():
            raise AssertionError("smoke24B sin nota")
        st_b_end = engine._thread_store.get_state()
        if st_b_end.get("open"):
            raise AssertionError("smoke24B hilo debe cerrarse")

    # --- CASOS E + F: selección única sin lista + siguiente turno ejecuta ---
    q_desc = (
        "¿Qué descripción quieres ponerle a la tarea «llamar al banco»?"
    )
    with tempfile.TemporaryDirectory() as d_ef:
        base = Path(d_ef)
        engine = _make_engine(base)
        engine._tasks.add_task({"title": "comprar leche"})
        t_bn = engine._tasks.add_task({"title": "llamar al banco"})
        ib = str(t_bn["id"])
        r_e1 = {
            "s": "need_context",
            "i": "task",
            "a": "update",
            "obj": {"requested_field": "description"},
            "target": None,
            "q": None,
            "r": None,
            "pending": None,
            "ctx": {
                "domain": "tasks",
                "query": "list_tasks",
                "filters": {"title": "banco"},
            },
        }
        r_e2 = {
            "s": "ask",
            "i": "task",
            "a": "update",
            "obj": {"requested_field": "description"},
            "target": ib,
            "q": q_desc,
            "r": None,
            "pending": {
                "field": "description",
                "target": ib,
                "original_action": "update",
            },
            "ctx": None,
        }
        seq_ef = iter([r_e1, r_e2])

        def fef(_p: dict[str, Any]) -> dict[str, Any] | None:
            return next(seq_ef)

        with patch.object(engine_mod, "ask_gpt", side_effect=fef):
            tef1, _, _, _ = engine.process_message(
                "cambia la descripción de la tarea del banco"
            )
        _assert_no_uuid_in_visible(tef1, "smoke24E")
        low = "comprar leche"
        if low in (tef1 or "").lower():
            raise AssertionError(f"smoke24E mención superflua leche {tef1!r}")
        if tef1.strip() != q_desc:
            raise AssertionError(f"smoke24E q {tef1!r}")
        st_ef = engine._thread_store.get_state()
        if not st_ef.get("open"):
            raise AssertionError(f"smoke24E abierto {st_ef!r}")
        if normalize_target_from_state(st_ef) != ib:
            raise AssertionError("smoke24E target ib")
        peg = st_ef.get("pending") or {}
        if peg.get("field") != "description":
            raise AssertionError(f"smoke24E pend {peg!r}")
        for rn in engine._notes.list_notes():
            raise AssertionError(f"smoke24E nota {rn!r}")

        r_f = {
            "s": "ready",
            "i": "task",
            "a": "update",
            "obj": {"description": "preguntar por seguros"},
            "target": ib,
            "q": None,
            "r": "Listo.",
            "pending": None,
            "ctx": None,
        }
        with patch.object(engine_mod, "ask_gpt", return_value=r_f):
            engine.process_message("preguntar por seguros")

        lst = engine._tasks.list_tasks()
        by_tt = {str(x.get("title")): x for x in lst}
        if (
            str(by_tt["llamar al banco"].get("description"))
            != "preguntar por seguros"
        ):
            raise AssertionError("smoke24F banco actualizado")
        if by_tt["comprar leche"].get("description"):
            raise AssertionError("smoke24F leche sin tocar desc")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke24F cerrado")

    print("smoke 24 OK (task/update incompleto y continuación)")


def smoke_25_disable_hidden_recent_recovery() -> None:
    """v0.47.36.2 — sin ``recent`` en payload; no contaminación ``mode=new``."""
    from backend.storage.json_store import load_json_dict

    stale: dict[str, Any] = {
        "open": False,
        "last_recoverable": {
            "recoverable": True,
            "intent": "task",
            "action": "update",
            "target": "old-id",
            "object": {"priority": "high"},
            "pending": {"field": "missing_target"},
        },
    }
    pl_a = build_payload("crea una tarea para ir al banco el lunes", stale)
    if pl_a.get("mode") != "new":
        raise AssertionError(f"smoke25A mode {pl_a!r}")
    if pl_a.get("thread") is not None:
        raise AssertionError(f"smoke25A thread {pl_a!r}")
    if "recent" in pl_a:
        raise AssertionError(f"smoke25A recent key {pl_a!r}")

    r_create: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "create",
        "obj": {
            "title": "ir al banco",
            "date": "lunes",
            "date_iso": "2026-05-18",
            "priority": "normal",
            "tags": ["Banco"],
        },
        "target": None,
        "q": None,
        "r": "He creado la tarea «ir al banco» para el lunes.",
        "pending": None,
        "ctx": None,
    }

    # --- CASO B: alta nueva no se contamina por JSON viejo ---
    stale_blob = stale["last_recoverable"].copy()
    stale_blob["target"] = "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee"
    with tempfile.TemporaryDirectory() as td_b:
        base = Path(td_b)
        tpath = base / "thread_state.json"
        tpath.parent.mkdir(parents=True, exist_ok=True)
        tpath.write_text(
            json.dumps({"open": False, "last_recoverable": stale_blob}),
            encoding="utf-8",
        )
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_create):
            vis, _, created, _ = engine.process_message(
                "crea una tarea para ir al banco el lunes"
            )
        if created is None or str(created.get("title") or "") != "ir al banco":
            raise AssertionError(f"smoke25B tarea {created!r}")
        if str(created.get("date_text") or "").lower() != "lunes":
            raise AssertionError(f"smoke25B date_text {created!r}")
        tl = (vis or "").lower()
        if "¿te refieres" in tl or "prioridad" in tl and "alta" in tl:
            raise AssertionError(f"smoke25B texto contaminado {vis!r}")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke25B debe cerrarse")
        raw_ts = load_json_dict(tpath, {})
        lr = raw_ts.get("last_recoverable")
        if lr is not None and lr != {}:
            raise AssertionError(f"smoke25B archivo sin recoverable limpio {raw_ts!r}")

    ib = "11111111-2222-4333-a444-555555555555"
    q_banco = (
        "¿Qué descripción quieres ponerle a la tarea «llamar al banco»?"
    )
    st_continue: dict[str, Any] = {
        "open": True,
        "intent": "task",
        "action": "update",
        "target": ib,
        "object": {"requested_field": "description"},
        "last_question": q_banco,
        "pending": {
            "field": "description",
            "target": ib,
            "original_action": "update",
        },
    }
    pl_c = build_payload("preguntar por los seguros", st_continue)
    if pl_c.get("mode") != "continue":
        raise AssertionError(f"smoke25C mode {pl_c!r}")
    th_c = pl_c.get("thread")
    if not isinstance(th_c, dict):
        raise AssertionError(f"smoke25C thread {pl_c!r}")
    if th_c.get("target") != ib:
        raise AssertionError(f"smoke25C target {th_c!r}")
    pend_c = th_c.get("pending") or {}
    if pend_c.get("field") != "description":
        raise AssertionError(f"smoke25C pending {pend_c!r}")
    if "recent" in pl_c:
        raise AssertionError(f"smoke25C recent {pl_c!r}")

    r_tpl_empty: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "update",
        "obj": {},
        "target": "",
        "q": None,
        "r": None,
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as td_d:
        base = Path(td_d)
        engine = _make_engine(base)
        tb = engine._tasks.add_task({"title": "llamar al banco"})
        idb = str(tb["id"])
        r_d = dict(r_tpl_empty)
        r_d["target"] = idb
        with patch.object(engine_mod, "ask_gpt", return_value=r_d):
            td1, _, _, _ = engine.process_message("turno vacuum obj")
        if "qué quieres cambiar" not in (td1 or "").lower():
            raise AssertionError(f"smoke25D: {td1!r}")
        st_d = engine._thread_store.get_state()
        if not st_d.get("open"):
            raise AssertionError(f"smoke25D cerrado {st_d!r}")
        pend_d = st_d.get("pending") or {}
        if pend_d.get("field") != "update_value":
            raise AssertionError(f"smoke25D pend {pend_d!r}")

    bad_tgt = "99999999-aaaa-4bbb-bccc-dddddddddddd"
    r_fail: dict[str, Any] = {
        "s": "ready",
        "i": "task",
        "a": "update",
        "obj": {"priority": "high"},
        "target": bad_tgt,
        "q": None,
        "r": None,
        "pending": None,
        "ctx": None,
    }
    with tempfile.TemporaryDirectory() as td_e:
        base = Path(td_e)
        engine = _make_engine(base)
        with patch.object(engine_mod, "ask_gpt", return_value=r_fail):
            te, _, _, _ = engine.process_message("sube prioridad falsa")
        if "No encuentro" not in (te or ""):
            raise AssertionError(f"smoke25E msg {te!r}")
        if engine._thread_store.get_state().get("open"):
            raise AssertionError("smoke25E cerrado")

        tpl = load_json_dict(base / "thread_state.json", {})
        if tpl.get("last_recoverable") not in (None, {}):
            raise AssertionError(f"smoke25E recoverable archivo {tpl!r}")

        pl_e2 = build_payload(
            "crea una tarea para ir al banco el lunes",
            engine._thread_store.get_state(),
        )
        if "recent" in pl_e2:
            raise AssertionError(f"smoke25E recent {pl_e2!r}")
        if pl_e2.get("mode") != "new":
            raise AssertionError(f"smoke25E mode2 {pl_e2!r}")

    print("smoke 25 OK (recent oculto desactivado v0.47.36.2)")


def main() -> int:
    try:
        smoke_1_2_ambiguous_then_continue()
        smoke_3_4()
        smoke_5_query()
        smoke_6_delete_confirmation()
        smoke_7_8_multiple_candidates_update()
        smoke_9_task_create_basic()
        smoke_10_note_create_basic()
        smoke_11_task_query_basic()
        smoke_12_note_query_basic()
        smoke_13_event_create_continue_not_update()
        smoke_14_event_24h_time_and_weekday_text()
        smoke_15_gpt_contract_clean_event_timing()
        smoke_16_event_continue_variants_mocked()
        smoke_17_event_create_with_date_iso()
        smoke_18_clean_event_card_contract()
        smoke_19_continue_guard_no_note_task()
        smoke_20_task_complete_basic()
        smoke_21_clean_task_card_contract()
        smoke_22_task_delete_safe()
        smoke_23_task_update_basic()
        smoke_24_recoverable_task_update_state()
        smoke_25_disable_hidden_recent_recovery()
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print("smoke_backend_minimal_v047: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
