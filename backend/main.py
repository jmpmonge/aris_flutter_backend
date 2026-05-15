import logging
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")

from backend.core.logging_setup import configure_logging

configure_logging()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.core.assistant_engine import AssistantEngine
from backend.models.assistant_message import (
    AssistantResponse,
    EventPatchBody,
    NotePatchBody,
    TaskPatchBody,
    UserMessage,
    build_event_updates_from_patch,
)
from backend.storage.events_store import EventsStore
from backend.storage.focus_store import FocusStore
from backend.storage.history_store import HistoryStore
from backend.storage.notes_store import NotesStore
from backend.storage.pending_action_store import PendingActionStore
from backend.storage.tasks_store import TasksStore

logger = logging.getLogger(__name__)

app = FastAPI()
pending_store = PendingActionStore()
history_store = HistoryStore()
notes_store = NotesStore()
tasks_store = TasksStore()
events_store = EventsStore()
focus_store = FocusStore()
engine = AssistantEngine(
    pending_store,
    focus_store=focus_store,
    tasks_store=tasks_store,
    notes_store=notes_store,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/message")
def message(body: UserMessage):
    reply_text, intent_type, stored_override, ui_hint = engine.process_message(body.text)
    payload = stored_override if stored_override is not None else body.text
    if intent_type == "nota":
        saved_note: dict | None = None
        if isinstance(payload, dict):
            # v0.21.4d — Si trae title o content, lo guardamos estructurado.
            title = (payload.get("title") or "").strip() if payload.get("title") else ""
            content = (payload.get("content") or "").strip() if payload.get("content") else ""
            if title or content:
                saved_note = notes_store.add_note(
                    {"title": title or None, "content": content or body.text}
                )
            else:
                saved_note = notes_store.add_note(body.text)
        elif isinstance(payload, str):
            # v0.46a — Contrato GPT-orquestado: no persistir nota desde texto plano único.
            logger.warning(
                "main.message: intent nota con payload str omitido (defensivo v0.46a)"
            )
        else:
            saved_note = None
        # v0.21.9 — Foco multi-entidad.
        if isinstance(saved_note, dict) and saved_note.get("id"):
            engine.note_entity_persisted(
                kind="note",
                entity_id=str(saved_note["id"]),
                label=(saved_note.get("title") or saved_note.get("content") or "")[:80],
                operation="create_note",
            )
    elif intent_type == "tarea":
        saved_task: dict | None = None
        if isinstance(payload, dict):
            saved_task = tasks_store.add_task(payload)
        elif isinstance(payload, str):
            logger.warning(
                "main.message: intent tarea con payload str omitido (defensivo v0.46a)"
            )
        else:
            logger.warning(
                "main.message: intent tarea con payload no dict/str omitido (%s)",
                type(payload).__name__,
            )
        if isinstance(saved_task, dict) and saved_task.get("id"):
            engine.note_entity_persisted(
                kind="task",
                entity_id=str(saved_task["id"]),
                label=saved_task.get("title"),
                operation="create_task",
            )
    elif intent_type == "calendario":
        saved: dict | None = None
        if isinstance(payload, dict):
            saved = events_store.add_event(payload)
        elif isinstance(payload, str):
            # v0.45b + contrato v0.46a: no persistir texto bruto como evento.
            logger.warning(
                "main.message: intent calendario con payload str omitido (defensivo)"
            )
        else:
            logger.warning(
                "main.message: intent calendario con payload no dict/str omitido (%s)",
                type(payload).__name__,
            )
        if isinstance(saved, dict) and saved.get("id"):
            events_store.set_focused_event_id(str(saved["id"]))
            # v0.21.9 — También actualizamos el foco multi-entidad.
            engine.note_entity_persisted(
                kind="event",
                entity_id=str(saved["id"]),
                label=saved.get("title"),
                operation="create_event",
            )
    history_store.save_interaction(body.text, reply_text, intent_type, ui_hint)
    return AssistantResponse(text=reply_text, type="assistant", ui_hint=ui_hint)


@app.get("/history")
def history():
    return history_store.get_history()


@app.get("/notes")
def notes():
    return notes_store.get_notes()


@app.patch("/notes/{note_id}")
def patch_note(note_id: str, body: NotePatchBody):
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(
            status_code=400,
            detail="El contenido de la nota no puede estar vacío.",
        )
    updated = notes_store.update_note(note_id, content)
    if updated is None:
        raise HTTPException(status_code=404, detail="Nota no encontrada")
    return updated


@app.get("/tasks")
def tasks():
    return tasks_store.get_tasks()


@app.get("/events")
def events():
    return events_store.get_events()


@app.patch("/events/{event_id}")
def patch_event(event_id: str, body: EventPatchBody):
    """Actualiza parcialmente un evento (v0.43). Ver `EventPatchBody` y `build_event_updates_from_patch`."""
    try:
        updates = build_event_updates_from_patch(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    updated = events_store.update_event(event_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    return updated


@app.delete("/events/{event_id}")
def delete_event_route(event_id: str):
    """Elimina el evento por id; misma forma de respuesta que notas/tareas (v0.43)."""
    if not events_store.delete_event(event_id):
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    return {"status": "deleted", "id": event_id}


@app.patch("/tasks/{task_id}")
def patch_task(task_id: str, body: TaskPatchBody):
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(
            status_code=400,
            detail="El título de la tarea no puede estar vacío.",
        )
    updated = tasks_store.update_task(task_id, title)
    if updated is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return updated


@app.patch("/tasks/{task_id}/complete")
def complete_task(task_id: str):
    task = tasks_store.complete_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return task


@app.delete("/notes/{note_id}")
def delete_note(note_id: str):
    if not notes_store.delete_note(note_id):
        raise HTTPException(status_code=404, detail="Nota no encontrada")
    return {"status": "deleted", "id": note_id}


@app.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    if not tasks_store.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return {"status": "deleted", "id": task_id}
