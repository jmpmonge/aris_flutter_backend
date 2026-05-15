from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserMessage(BaseModel):
    text: str
    type: str = "user"
    created_at: datetime = Field(default_factory=_utc_now)


class AssistantResponse(BaseModel):
    text: str
    type: str = "assistant"
    ui_hint: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class NotePatchBody(BaseModel):
    content: str


class TaskPatchBody(BaseModel):
    title: str
