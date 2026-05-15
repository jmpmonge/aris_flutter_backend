"""Orquestador mínimo Aris: payload → GPT → normalización → stores/hilo."""

from __future__ import annotations

from typing import Any

from backend.core.openai_client import ask_gpt
from backend.core.payload_builder import (
    build_payload,
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
_MSG_NEED_MORE_CTX = (
    "Necesito un dato más para encontrarlo. ¿Puedes concretarlo?"
)
_MSG_MAIL_DRAFT = "He preparado un borrador de correo."
_MSG_OK = "De acuerdo."
_MSG_FAIL_FALLBACK = (
    "No estoy captando toda la información necesaria. ¿Podrías escribirlo de nuevo "
    "de forma más concreta?"
)


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
        payload = build_payload(raw_in, thread_state)

        gpt_raw = ask_gpt(payload)
        if gpt_raw is None:
            return (_MSG_NO_GPT, "consulta", None, None)

        result = normalize_gpt_response(gpt_raw)
        s = result["s"]

        if s == "ask":
            self._thread_store.save_state(
                {
                    "open": True,
                    "intent": result["i"],
                    "object": result["obj"],
                    "last_question": result["q"],
                    "pending": result["pending"],
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
            self._thread_store.save_state(
                {
                    "open": True,
                    "intent": result["i"],
                    "object": result["obj"],
                    "last_question": _MSG_NEED_MORE_CTX,
                    "pending": {"field": "context", "ctx": result["ctx"]},
                }
            )
            return (_MSG_NEED_MORE_CTX, "ambiguo", None, None)

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

        # update/delete/query/complete/draft u otros — no ejecutar en v0.47.7
        self._thread_store.clear_state()
        return (_MSG_UNSUPPORTED, "consulta", None, None)

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

        out: dict[str, Any] = {
            "title": title,
            "date_text": str(date_text).strip() if date_text is not None else None,
            "time_text": str(time_text).strip() if time_text is not None else None,
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
