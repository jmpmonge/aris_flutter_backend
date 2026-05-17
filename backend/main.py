"""API FastAPI mínima — Aris backend (POST /message → engine; POST/PATCH `/tasks`)."""

from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.core.engine import ArisMinimalEngine
from backend.models.schemas import (
    AssistantResponse,
    TaskCreateBody,
    TaskToggleCompletedBody,
    UserMessage,
)
from backend.storage.events_store import EventsStore
from backend.storage.notes_store import NotesStore
from backend.storage.tasks_store import TasksStore
from backend.storage.thread_state_store import ThreadStateStore

_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

events_store = EventsStore()
tasks_store = TasksStore()
notes_store = NotesStore()
thread_store = ThreadStateStore()

engine = ArisMinimalEngine(
    events_store=events_store,
    tasks_store=tasks_store,
    notes_store=notes_store,
    thread_store=thread_store,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "backend": "minimal",
        "version": "v0.47.31",
    }


@app.get("/events")
def list_events() -> list[dict[str, Any]]:
    return events_store.list_events()


@app.get("/tasks")
def list_tasks() -> list[dict[str, Any]]:
    return tasks_store.list_tasks()


@app.post("/tasks", status_code=201)
def create_task(body: TaskCreateBody) -> dict[str, Any]:
    """Crea una tarea sin GPT ni thread_state; sólo validación técnica y persistencia."""
    payload: dict[str, Any] = {
        "title": body.title,
        "description": body.description,
        "date_text": body.date_text,
        "date_iso": body.date_iso,
        "time_text": body.time_text,
        "priority": body.priority,
        "tags": body.tags if body.tags is not None else [],
    }
    try:
        return tasks_store.add_task(payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.patch("/tasks/{task_id}")
def patch_task(task_id: str, body: TaskToggleCompletedBody) -> dict[str, Any]:
    """Marca o desmarca `completed`; sin GPT; sin otros campos en esta versión."""
    row = tasks_store.update_task(task_id, {"completed": body.completed})
    if row is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return row


@app.get("/notes")
def list_notes() -> list[dict[str, Any]]:
    return notes_store.list_notes()


@app.post("/message")
def post_message(body: UserMessage) -> AssistantResponse:
    reply_text, _intent_type, _stored_payload, ui_hint = engine.process_message(body.text)
    return AssistantResponse(text=reply_text, type="assistant", ui_hint=ui_hint)
