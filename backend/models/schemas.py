"""Esquemas HTTP mínimos para POST /message y PATCH de dominio."""

from typing import Any

from pydantic import BaseModel, Field, model_validator


class UserMessage(BaseModel):
    text: str


class AssistantResponse(BaseModel):
    text: str
    type: str = Field(default="assistant")
    ui_hint: str | None = None


class TaskPatchBody(BaseModel):
    """PATCH /tasks/{id} — sin GPT: título y/o completado."""

    completed: bool | None = None
    title: str | None = None

    @model_validator(mode="after")
    def at_least_one_field(self):
        has_title = self.title is not None and str(self.title).strip() != ""
        has_completed = self.completed is not None
        if not has_title and not has_completed:
            raise ValueError("Indica completed y/o title.")
        return self

    def to_store_updates(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.completed is not None:
            out["completed"] = self.completed
        if self.title is not None and str(self.title).strip():
            out["title"] = str(self.title).strip()
        return out
