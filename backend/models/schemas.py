"""Esquemas HTTP mínimos para POST /message y PATCH de dominio."""

from pydantic import BaseModel, Field


class UserMessage(BaseModel):
    text: str


class AssistantResponse(BaseModel):
    text: str
    type: str = Field(default="assistant")
    ui_hint: str | None = None


class TaskToggleCompletedBody(BaseModel):
    """PATCH /tasks/{id} — sólo `completed`; sin GPT ni otros campos en v0.47.31."""

    completed: bool
