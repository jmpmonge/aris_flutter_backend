"""Estado de hilo conversacional — persistencia sin semántica.

Contrato v0.47 (para empaquetar en GPT con mode=continue):
open, intent, object, last_question, pending (y updated_at automático).

Aris solo persiste estos campos; no reinterpreta contenido aquí.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from backend.storage.json_store import load_json_dict, save_json_dict, utc_now_iso


def _backend_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


DEFAULT_THREAD_STATE: dict[str, Any] = {
    "open": False,
    "intent": None,
    "object": None,
    "last_question": None,
    "pending": None,
    "updated_at": None,
}


class ThreadStateStore:
    """Documento único backend/data/thread_state.json."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_backend_data_dir() / "thread_state.json")

    def get_state(self) -> dict[str, Any]:
        raw = load_json_dict(self._path, {})
        state = deepcopy(DEFAULT_THREAD_STATE)
        if isinstance(raw, dict):
            state.update(raw)
        self._normalize_closed_fields(state)
        return state

    def save_state(self, state: dict[str, Any]) -> dict[str, Any]:
        data = dict(state)
        self._normalize_closed_fields(data)
        data["updated_at"] = utc_now_iso()
        save_json_dict(self._path, data)
        return data

    def clear_state(self) -> None:
        save_json_dict(self._path, deepcopy(DEFAULT_THREAD_STATE))

    def is_open(self) -> bool:
        return bool(self.get_state().get("open"))

    def _normalize_closed_fields(self, data: dict[str, Any]) -> None:
        if not data.get("open"):
            data["intent"] = None
            data["object"] = None
            data["last_question"] = None
            data["pending"] = None
