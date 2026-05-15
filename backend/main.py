"""API FastAPI mínima — Aris backend v0.47.8 (POST /message → engine)."""

from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.engine import ArisMinimalEngine
from backend.models.schemas import AssistantResponse, UserMessage
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
        "version": "v0.47.8",
    }


@app.get("/events")
def list_events() -> list[dict[str, Any]]:
    return events_store.list_events()


@app.get("/tasks")
def list_tasks() -> list[dict[str, Any]]:
    return tasks_store.list_tasks()


@app.get("/notes")
def list_notes() -> list[dict[str, Any]]:
    return notes_store.list_notes()


@app.post("/message")
def post_message(body: UserMessage) -> AssistantResponse:
    reply_text, _intent_type, _stored_payload, ui_hint = engine.process_message(body.text)
    return AssistantResponse(text=reply_text, type="assistant", ui_hint=ui_hint)
