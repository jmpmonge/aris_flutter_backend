from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class EventPatchBody(BaseModel):
    """Cuerpo parcial PATCH `/events/{id}`.

    Solo se aplican los campos presentes en el JSON; `null` equivale a “no enviar”.
    La validación estricta y el dict aplicable a EventsStore.update_event están en
    build_event_updates_from_patch.

    Versión backend: **v0.43** — Flutter sin conectar a estas acciones aún (v0.44).
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    date_text: str | None = None
    time_text: str | None = None
    location: str | None = None
    participants: list[str] | None = None
    description: str | None = None
    duration_minutes: int | None = None
    confidence: float | None = None
    needs_confirmation: bool | None = None
    missing_fields: list[str] | None = None
    source_text: str | None = None


def build_event_updates_from_patch(body: EventPatchBody) -> dict[str, Any]:
    """Valida EventPatchBody y construye updates para EventsStore.update_event (sin id ni created_at)."""
    raw = body.model_dump(exclude_unset=True)
    updates: dict[str, Any] = {}

    if not raw:
        raise ValueError("El patch no puede estar vacío.")

    allowed = frozenset(
        EventPatchBody.model_fields.keys(),
    )

    # Campos texto que solo se propagan si, tras strip, tienen contenido salvo restricciones
    # explícitas (title/date_text/time_text no pueden estar vacíos si llegan definidos como string).
    for key in list(raw.keys()):
        if key not in allowed:
            continue
        val = raw[key]

        if val is None:
            continue

        if key == "title":
            s = str(val).strip()
            if not s:
                raise ValueError("Si se envía title, no puede estar vacío.")
            updates[key] = s

        elif key == "date_text":
            s = str(val).strip()
            if not s:
                raise ValueError(
                    "Si se envía date_text, no puede estar vacío."
                )
            updates[key] = s

        elif key == "time_text":
            s = str(val).strip()
            if not s:
                raise ValueError(
                    "Si se envía time_text, no puede estar vacío."
                )
            updates[key] = s

        elif key == "location":
            s = str(val).strip()
            if s:
                updates[key] = s

        elif key == "description":
            s = str(val).strip()
            if s:
                updates[key] = s

        elif key == "source_text":
            s = str(val).strip()
            if s:
                updates[key] = s

        elif key == "participants":
            if not isinstance(val, list):
                raise ValueError(
                    "participants debe ser una lista de texto."
                )
            cleaned: list[str] = []
            for p in val:
                ps = str(p).strip()
                if not ps:
                    raise ValueError(
                        "Los participantes no pueden tener cadenas vacías."
                    )
                cleaned.append(ps)
            if not cleaned:
                raise ValueError(
                    "Si se envía participants, debe tener al menos un elemento no vacío."
                )
            updates[key] = cleaned

        elif key == "missing_fields":
            if not isinstance(val, list):
                raise ValueError(
                    "missing_fields debe ser una lista de texto."
                )
            cleaned_ms = []
            for x in val:
                s = str(x).strip()
                if not s:
                    raise ValueError(
                        "missing_fields no debe contener cadenas vacías."
                    )
                cleaned_ms.append(s)
            if not cleaned_ms:
                raise ValueError(
                    "Si se envía missing_fields, debe haber al menos un campo listado."
                )
            updates[key] = cleaned_ms

        elif key == "duration_minutes":
            try:
                mins = int(val)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    "duration_minutes debe ser un número entero."
                ) from e
            if mins <= 0:
                raise ValueError(
                    "duration_minutes debe ser un número entero positivo."
                )
            updates[key] = mins

        elif key == "confidence":
            try:
                cf = float(val)
            except (TypeError, ValueError) as e:
                raise ValueError("confidence debe ser un número.") from e
            if not 0 <= cf <= 1:
                raise ValueError(
                    "confidence debe estar entre 0 y 1 (ambos inclusivos)."
                )
            updates[key] = cf

        elif key == "needs_confirmation":
            updates[key] = bool(val)

    if not updates:
        raise ValueError(
            "El patch debe incluir al menos un campo válido para actualizar "
            "(no pueden quedar todas las claves omitidas tras validar)."
        )

    return updates
