"""Esquemas HTTP mínimos para POST /message."""

from pydantic import BaseModel, Field


class UserMessage(BaseModel):
    text: str


class AssistantResponse(BaseModel):
    text: str
    type: str = Field(default="assistant")
    ui_hint: str | None = None
