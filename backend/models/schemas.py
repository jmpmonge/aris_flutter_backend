"""Esquemas HTTP mínimos para POST /message y PATCH de dominio."""

from pydantic import BaseModel, Field, field_validator


class UserMessage(BaseModel):
    text: str


class AssistantResponse(BaseModel):
    text: str
    type: str = Field(default="assistant")
    ui_hint: str | None = None


class TaskToggleCompletedBody(BaseModel):
    """PATCH /tasks/{id} — sólo `completed`; sin GPT ni otros campos en v0.47.31."""

    completed: bool


class TaskCreateBody(BaseModel):
    """POST /tasks — ficha técnica desde Flutter; sin GPT."""

    title: str = Field(min_length=1)
    description: str | None = None
    date_text: str | None = None
    date_iso: str | None = None
    time_text: str | None = None
    priority: str | None = None
    tags: list[str] | None = None

    @field_validator("title", mode="before")
    @classmethod
    def _strip_title(cls, v: object) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator(
        "description",
        "date_text",
        "date_iso",
        "time_text",
        mode="before",
    )
    @classmethod
    def _strip_optional_str(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            return []
        return [str(x).strip() for x in v if str(x).strip()]
