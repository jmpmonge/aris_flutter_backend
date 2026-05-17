"""Estado de hilo conversacional — persistencia sin semántica.

Contrato para **GPT** (**mode=continue**): cuando **open** es **true**, persiste intent,
action, object, last_question, pending y **target**.

Cuando **open** es **false**, **last_focus** y **last_action** conservan huella técnica
(no abren hilo) de último objeto tocado y última mutación ejecutada con éxito.
**clear_state** cierra campos del hilo pero **no borra** last_focus/last_action.
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
    "action": None,
    "object": None,
    "last_question": None,
    "pending": None,
    "target": None,
    "last_focus": None,
    "last_action": None,
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
            for k, v in raw.items():
                state[k] = v
        self._normalize_closed_fields(state)
        return state

    def save_state(self, state: dict[str, Any]) -> dict[str, Any]:
        base = deepcopy(DEFAULT_THREAD_STATE)
        prev = load_json_dict(self._path, {})
        if isinstance(prev, dict):
            for k, v in prev.items():
                if k in DEFAULT_THREAD_STATE:
                    base[k] = v
        base.update(state)
        self._normalize_closed_fields(base)
        base["updated_at"] = utc_now_iso()
        save_json_dict(self._path, base)
        return base

    def clear_state(self) -> None:
        """Cierra **hilo** operativo (**open**/intent/pending/…) sin borrar last_focus."""
        prev = load_json_dict(self._path, {})
        lf = prev.get("last_focus") if isinstance(prev, dict) else None
        la = prev.get("last_action") if isinstance(prev, dict) else None
        base = deepcopy(DEFAULT_THREAD_STATE)
        base["last_focus"] = lf
        base["last_action"] = la
        base.update(
            {
                "open": False,
                "intent": None,
                "action": None,
                "object": None,
                "last_question": None,
                "pending": None,
                "target": None,
            }
        )
        base["updated_at"] = utc_now_iso()
        save_json_dict(self._path, base)

    def is_open(self) -> bool:
        return bool(self.get_state().get("open"))

    def set_last_focus(self, blob: dict[str, Any] | None) -> None:
        self.save_state({"last_focus": blob})

    def set_last_action(self, blob: dict[str, Any] | None) -> None:
        self.save_state({"last_action": blob})

    def discard_focus_matching(self, domain: str, obj_id: str) -> None:
        st = self.get_state()
        lf = st.get("last_focus")
        if isinstance(lf, dict) and str(lf.get("domain")) == str(
            domain
        ) and str(lf.get("id")) == str(obj_id):
            self.save_state({"last_focus": None})

    def _normalize_closed_fields(self, data: dict[str, Any]) -> None:
        data.pop("last_recoverable", None)
        if not data.get("open"):
            data["intent"] = None
            data["action"] = None
            data["object"] = None
            data["last_question"] = None
            data["pending"] = None
            data["target"] = None
