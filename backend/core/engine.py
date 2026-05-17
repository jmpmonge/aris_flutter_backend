"""Orquestador mínimo Aris: payload → GPT → normalización → stores/hilo."""

from __future__ import annotations

import re
from typing import Any

from backend.core.context_resolver import resolver_contexto
from backend.core.openai_client import ask_gpt
from backend.core.payload_builder import (
    build_context_response_payload,
    build_payload,
    extract_event_target_id,
    normalize_gpt_response,
    sanitize_visible_text,
)
from backend.storage.events_store import EventsStore
from backend.storage.notes_store import NotesStore
from backend.storage.tasks_store import TasksStore
from backend.storage.thread_state_store import ThreadStateStore

_MSG_EMPTY = "Escribe un mensaje con contenido."
_MSG_NO_GPT = (
    "Ahora no puedo interpretar acciones complejas. Inténtalo de nuevo en un momento."
)
_MSG_UNSUPPORTED = "Todavía no puedo completar esa acción con seguridad."
_MSG_UNSUPPORTED_MODIFY = (
    "Todavía no puedo completar esa modificación con seguridad."
)
_MSG_NEED_MORE_CTX = (
    "Necesito un dato más para encontrarlo. ¿Puedes concretarlo?"
)
_MSG_MAIL_DRAFT = "He preparado un borrador de correo."
_MSG_OK = "De acuerdo."
_MSG_FAIL_FALLBACK = (
    "No estoy captando toda la información necesaria. ¿Podrías escribirlo de nuevo "
    "de forma más concreta?"
)
_MAX_CONTEXT_NEED_CONTEXT_DEPTH = 8

_DATE_ISO_BASIC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ArisMinimalEngine:
    """Empaqueta contexto, llama a GPT y aplica efectos según respuesta normalizada."""

    def __init__(
        self,
        events_store: EventsStore,
        tasks_store: TasksStore,
        notes_store: NotesStore,
        thread_store: ThreadStateStore,
    ) -> None:
        self._events = events_store
        self._tasks = tasks_store
        self._notes = notes_store
        self._thread_store = thread_store

    def process_message(self, text: str) -> tuple[str, str, dict[str, Any] | None, str | None]:
        raw_in = (text or "").strip()
        if not raw_in:
            return (_MSG_EMPTY, "consulta", None, None)

        thread_state = self._thread_store.get_state()
        peticion_raiz = self._peticion_raiz_para_contexto(raw_in, thread_state)

        payload = build_payload(raw_in, thread_state)
        gpt_raw = ask_gpt(payload)
        if gpt_raw is None:
            return (_MSG_NO_GPT, "consulta", None, None)

        result = normalize_gpt_response(gpt_raw)
        if result["s"] == "need_context":
            return self._flujo_need_context(peticion_raiz, result, depth=0)
        return self._aplicar_resultado_gpt(result, peticion_raiz)

    def _peticion_raiz_para_contexto(
        self, raw_in: str, thread_state: dict[str, Any]
    ) -> str:
        if isinstance(thread_state, dict) and thread_state.get("open") is True:
            pend = thread_state.get("pending")
            if isinstance(pend, dict) and pend.get("field") == "context":
                po = pend.get("peticion_original")
                if isinstance(po, str) and po.strip():
                    return po.strip()
        return raw_in

    def _flujo_need_context(
        self,
        peticion_original: str,
        primera: dict[str, Any],
        *,
        depth: int = 0,
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        if depth >= _MAX_CONTEXT_NEED_CONTEXT_DEPTH:
            self._thread_store.clear_state()
            return (_MSG_NEED_MORE_CTX, "ambiguo", None, None)

        ctx_sol = primera.get("ctx") if isinstance(primera.get("ctx"), dict) else {}

        contexto_encontrado = resolver_contexto(
            ctx_sol,
            events_store=self._events,
            tasks_store=self._tasks,
            notes_store=self._notes,
        )

        payload_ctx = build_context_response_payload(
            peticion_original=(peticion_original or "").strip(),
            respuesta_gpt_previa=primera,
            contexto_encontrado=contexto_encontrado,
        )

        segunda_raw = ask_gpt(payload_ctx)
        if segunda_raw is None:
            self._thread_store.save_state(
                {
                    "open": True,
                    "intent": primera["i"],
                    "object": primera["obj"],
                    "last_question": _MSG_NEED_MORE_CTX,
                    "pending": {
                        "field": "context",
                        "ctx": primera["ctx"],
                        "contexto_encontrado": contexto_encontrado,
                        "peticion_original": (peticion_original or "").strip(),
                    },
                }
            )
            return (_MSG_NEED_MORE_CTX, "ambiguo", None, None)

        segunda = normalize_gpt_response(segunda_raw)

        if segunda["s"] == "need_context":
            return self._flujo_need_context(
                peticion_original,
                segunda,
                depth=depth + 1,
            )

        return self._aplicar_resultado_gpt(segunda, peticion_original)

    def _aplicar_resultado_gpt(
        self,
        result: dict[str, Any],
        peticion_raiz: str,
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        s = result["s"]

        if s == "ask":
            tid = extract_event_target_id(result)
            obj_out: dict[str, Any] = (
                dict(result["obj"]) if isinstance(result.get("obj"), dict) else {}
            )
            pend_raw = result.get("pending")
            if isinstance(pend_raw, dict) and pend_raw.get("field") == "target_selection":
                oo = pend_raw.get("original_obj")
                if isinstance(oo, dict) and oo:
                    merged = dict(oo)
                    merged.update(obj_out)
                    obj_out = merged
            self._thread_store.save_state(
                {
                    "open": True,
                    "intent": result["i"],
                    "object": obj_out,
                    "last_question": result["q"],
                    "pending": result["pending"],
                    "target": tid,
                }
            )
            q = result["q"]
            reply = sanitize_visible_text(q) if isinstance(q, str) else ""
            return (reply or "¿Puedes concretar?", "ambiguo", None, None)

        if s == "answer":
            self._thread_store.clear_state()
            r = result["r"]
            reply = sanitize_visible_text(r) if isinstance(r, str) else ""
            return (reply or _MSG_OK, "consulta", None, None)

        if s == "fail":
            self._thread_store.clear_state()
            r = result["r"]
            reply = sanitize_visible_text(r) if isinstance(r, str) else ""
            return (reply or _MSG_FAIL_FALLBACK, "consulta", None, None)

        if s == "need_context":
            return self._flujo_need_context(peticion_raiz, result, depth=0)

        if s == "ready":
            return self._handle_ready(result)

        self._thread_store.clear_state()
        return (_MSG_FAIL_FALLBACK, "consulta", None, None)

    def _handle_ready(
        self, result: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        a = result["a"]
        i = result["i"]
        obj = result["obj"]

        if a == "answer":
            self._thread_store.clear_state()
            r = result["r"]
            reply = sanitize_visible_text(r) if isinstance(r, str) else ""
            return (reply or _MSG_OK, "consulta", None, None)

        if a == "create":
            return self._handle_ready_create(result, i, obj)

        if a == "query":
            self._thread_store.clear_state()
            r = result.get("r")
            reply = sanitize_visible_text(r) if isinstance(r, str) else ""
            return (reply or _MSG_OK, "consulta", None, None)

        if a == "update":
            if i == "event":
                return self._handle_ready_update_event(result)
            self._thread_store.clear_state()
            return (_MSG_UNSUPPORTED_MODIFY, "consulta", None, None)

        if a == "delete":
            if i == "event":
                return self._handle_ready_delete_event(result)
            self._thread_store.clear_state()
            return (_MSG_UNSUPPORTED, "consulta", None, None)

        # complete/draft u otros — no ejecutar aquí (query tratado más arriba)
        self._thread_store.clear_state()
        return (_MSG_UNSUPPORTED, "consulta", None, None)

    def _handle_ready_delete_event(
        self, result: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        r_raw = result.get("r")

        def _reply_del(default: str) -> str:
            if isinstance(r_raw, str):
                cleaned = sanitize_visible_text(r_raw)
                if cleaned:
                    return cleaned
            return default

        tid = extract_event_target_id(result)
        if not tid:
            self._thread_store.clear_state()
            return (
                "No sé qué evento quieres borrar. ¿Puedes concretarlo?",
                "consulta",
                None,
                None,
            )

        if self._events.get_event_by_id(tid) is None:
            self._thread_store.clear_state()
            return (
                "No encuentro ese evento en tu agenda local.",
                "consulta",
                None,
                None,
            )

        if not self._events.delete_event(tid):
            self._thread_store.clear_state()
            return (
                "No encuentro ese evento en tu agenda local.",
                "consulta",
                None,
                None,
            )

        self._thread_store.clear_state()
        return (_reply_del("He borrado el evento."), "calendario", None, None)

    def _handle_ready_update_event(
        self, result: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        r_raw = result.get("r")

        def _reply_saved(default: str) -> str:
            if isinstance(r_raw, str):
                cleaned = sanitize_visible_text(r_raw)
                if cleaned:
                    return cleaned
            return default

        obj_raw = result.get("obj")
        obj: dict[str, Any] = obj_raw if isinstance(obj_raw, dict) else {}

        tid = extract_event_target_id(result)
        if not tid:
            self._thread_store.clear_state()
            return (
                "No sé qué evento quieres modificar. ¿Puedes concretarlo?",
                "consulta",
                None,
                None,
            )

        if self._events.get_event_by_id(tid) is None:
            self._thread_store.clear_state()
            return (
                "No encuentro ese evento en tu agenda local.",
                "consulta",
                None,
                None,
            )

        updates = self._event_updates_from_obj(obj)
        if not updates:
            self._thread_store.clear_state()
            return (
                "No he captado qué dato quieres cambiar.",
                "consulta",
                None,
                None,
            )

        try:
            updated = self._events.update_event(tid, updates)
        except ValueError:
            self._thread_store.clear_state()
            return ("No he podido modificar ese evento.", "consulta", None, None)

        if updated is None:
            self._thread_store.clear_state()
            return ("No he podido modificar ese evento.", "consulta", None, None)

        self._thread_store.clear_state()
        return (
            _reply_saved("He actualizado el evento."),
            "calendario",
            updated,
            None,
        )

    def _handle_ready_create(
        self,
        result: dict[str, Any],
        i: str,
        obj: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        r_raw = result.get("r")

        def _reply_saved(default: str) -> str:
            if isinstance(r_raw, str):
                cleaned = sanitize_visible_text(r_raw)
                if cleaned:
                    return cleaned
            return default

        if i == "event":
            ev_payload = self._event_payload(obj)
            if ev_payload is None:
                self._thread_store.clear_state()
                return ("No he podido guardar el evento: falta un título.", "consulta", None, None)
            try:
                saved = self._events.add_event(ev_payload)
            except ValueError:
                self._thread_store.clear_state()
                return ("No he podido guardar el evento.", "consulta", None, None)
            self._thread_store.clear_state()
            return (
                _reply_saved("He guardado la cita."),
                "calendario",
                saved,
                None,
            )

        if i == "task":
            task_payload = self._task_payload(obj)
            if task_payload is None:
                self._thread_store.clear_state()
                return ("No he podido guardar la tarea: falta un título.", "consulta", None, None)
            try:
                saved = self._tasks.add_task(task_payload)
            except ValueError:
                self._thread_store.clear_state()
                return ("No he podido guardar la tarea.", "consulta", None, None)
            self._thread_store.clear_state()
            return (_reply_saved("He guardado la tarea."), "tarea", saved, None)

        if i == "note":
            note_payload = self._note_payload(obj)
            if note_payload is None:
                self._thread_store.clear_state()
                return ("No he podido guardar la nota: falta contenido.", "consulta", None, None)
            try:
                saved = self._notes.add_note(note_payload)
            except ValueError:
                self._thread_store.clear_state()
                return ("No he podido guardar la nota.", "consulta", None, None)
            self._thread_store.clear_state()
            return (_reply_saved("He guardado la nota."), "nota", saved, None)

        if i == "mail":
            self._thread_store.clear_state()
            return (_reply_saved(_MSG_MAIL_DRAFT), "mail", dict(obj), None)

        self._thread_store.clear_state()
        return (_MSG_UNSUPPORTED, "consulta", None, None)

    @staticmethod
    def _event_updates_from_obj(obj: dict[str, Any]) -> dict[str, Any]:
        """Campos admitidos por events_store.update_event; omitir vacíos."""
        out: dict[str, Any] = {}

        if "title" in obj:
            tv = obj.get("title")
            if tv is not None and str(tv).strip():
                out["title"] = str(tv).strip()

        dt_val = None
        if "date_text" in obj:
            dt_val = obj.get("date_text")
        elif "date" in obj:
            dt_val = obj.get("date")
        if dt_val is not None and str(dt_val).strip():
            out["date_text"] = str(dt_val).strip()

        tm_val = None
        if "time_text" in obj:
            tm_val = obj.get("time_text")
        elif "time" in obj:
            tm_val = obj.get("time")
        if tm_val is not None and str(tm_val).strip():
            out["time_text"] = str(tm_val).strip()

        if "people" in obj or "participants" in obj:
            pr = obj.get("people")
            if pr is None and "participants" in obj:
                pr = obj.get("participants")
            parts: list[str] = []
            if isinstance(pr, str):
                s = pr.strip()
                if s:
                    parts = [s]
            elif isinstance(pr, list):
                parts = [str(p).strip() for p in pr if str(p).strip()]
            if parts:
                out["participants"] = parts

        if "location" in obj:
            loc = obj.get("location")
            if loc is not None and str(loc).strip():
                out["location"] = str(loc).strip()

        if "description" in obj:
            desc = obj.get("description")
            if desc is not None and str(desc).strip():
                out["description"] = str(desc).strip()

        if "duration_minutes" in obj:
            dm = obj.get("duration_minutes")
            if isinstance(dm, int):
                out["duration_minutes"] = dm

        if "date_iso" in obj or "dateISO" in obj:
            cand = ArisMinimalEngine._coerce_date_iso_from_obj(obj)
            if cand is not None:
                out["date_iso"] = cand
            else:
                def _blank_di(v: Any) -> bool:
                    return v is None or (
                        isinstance(v, str) and str(v).strip() == ""
                    )

                had_nonempty = False
                if "date_iso" in obj and not _blank_di(obj.get("date_iso")):
                    had_nonempty = True
                if "dateISO" in obj and not _blank_di(obj.get("dateISO")):
                    had_nonempty = True
                if not had_nonempty:
                    out["date_iso"] = None

        return out

    @staticmethod
    def _coerce_date_iso_raw(raw: Any) -> str | None:
        if raw is None:
            return None
        s = str(raw).strip()
        if not s or not _DATE_ISO_BASIC_RE.match(s):
            return None
        try:
            y = int(s[0:4])
            mo = int(s[5:7])
            d = int(s[8:10])
        except ValueError:
            return None
        if y < 1970 or y > 2199 or mo < 1 or mo > 12 or d < 1 or d > 31:
            return None
        return s

    @staticmethod
    def _coerce_date_iso_from_obj(obj: dict[str, Any]) -> str | None:
        if not isinstance(obj, dict):
            return None
        for key in ("date_iso", "dateISO"):
            if key not in obj:
                continue
            got = ArisMinimalEngine._coerce_date_iso_raw(obj.get(key))
            if got is not None:
                return got
        return None

    @staticmethod
    def _event_payload(obj: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(obj, dict):
            return None
        title = str(obj.get("title") or "").strip()
        if not title:
            return None

        parts_raw = obj.get("people")
        if parts_raw is None:
            parts_raw = obj.get("participants")
        participants: list[str] = []
        if isinstance(parts_raw, list):
            participants = [str(p).strip() for p in parts_raw if str(p).strip()]

        dm_raw = obj.get("duration_minutes")
        duration_minutes: int | None = dm_raw if isinstance(dm_raw, int) else None

        date_text = obj.get("date_text")
        if date_text is None or str(date_text).strip() == "":
            date_text = obj.get("date")
        time_text = obj.get("time_text")
        if time_text is None or str(time_text).strip() == "":
            time_text = obj.get("time")

        loc = obj.get("location")
        location = (
            str(loc).strip() if loc is not None and str(loc).strip() else None
        )
        desc = obj.get("description")
        description = (
            str(desc).strip() if desc is not None and str(desc).strip() else None
        )

        date_iso_store = ArisMinimalEngine._coerce_date_iso_from_obj(obj)

        out: dict[str, Any] = {
            "title": title,
            "date_text": str(date_text).strip() if date_text is not None else None,
            "time_text": str(time_text).strip() if time_text is not None else None,
            "date_iso": date_iso_store,
            "participants": participants,
            "location": location,
            "description": description,
            "duration_minutes": duration_minutes,
        }
        for k in ("date_text", "time_text", "location", "description"):
            if out.get(k) == "":
                out[k] = None
        return out

    @staticmethod
    def _task_payload(obj: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(obj, dict):
            return None
        title = str(obj.get("title") or "").strip()
        if not title:
            return None

        date_text = obj.get("date_text") or obj.get("date")
        time_text = obj.get("time_text") or obj.get("time")

        return {
            "title": title,
            "description": (
                str(obj["description"]).strip()
                if obj.get("description") is not None
                and str(obj.get("description")).strip()
                else None
            ),
            "date_text": str(date_text).strip() if date_text else None,
            "time_text": str(time_text).strip() if time_text else None,
            "priority": (
                str(obj["priority"]).strip()
                if obj.get("priority") is not None and str(obj.get("priority")).strip()
                else None
            ),
        }

    @staticmethod
    def _note_payload(obj: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(obj, dict):
            return None
        title_raw = obj.get("title")
        title = str(title_raw).strip() if title_raw is not None else ""

        content_raw = obj.get("content")
        content = str(content_raw).strip() if content_raw is not None else ""

        if not content and title:
            content = title
        if not content:
            return None

        tags_raw = obj.get("tags")
        tags: list[str] = []
        if isinstance(tags_raw, list):
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]

        out: dict[str, Any] = {"title": title or None, "content": content, "tags": tags}
        return out
