"""Persistencia de eventos en JSON — sin interpretación semántica."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.storage.json_store import (
    load_json_list,
    new_id,
    save_json_list,
    utc_now_iso,
)


def _backend_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


_DATE_ISO_BASIC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _normalize_stored_date_iso(v: Any) -> str | None:
    """Sólo formato YYYY-MM-DD; valores inválidos → None (seguridad al guardar)."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or not _DATE_ISO_BASIC_RE.match(s):
        return None
    return s


class EventsStore:
    """Lista de eventos en backend/data/events.json."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_backend_data_dir() / "events.json")

    def list_events(self) -> list[dict[str, Any]]:
        rows = load_json_list(self._path)
        return [r for r in rows if isinstance(r, dict)]

    def get_event_by_id(self, event_id: str) -> dict[str, Any] | None:
        eid = str(event_id or "").strip()
        if not eid:
            return None
        for ev in self.list_events():
            if isinstance(ev, dict) and str(ev.get("id") or "").strip() == eid:
                return dict(ev)
        return None

    def add_event(self, data: dict[str, Any]) -> dict[str, Any]:
        title = str(data.get("title") or "").strip()
        if not title:
            raise ValueError("title es obligatorio y no puede estar vacío")

        participants_raw = data.get("participants")
        participants: list[str] = []
        if isinstance(participants_raw, list):
            participants = [str(p).strip() for p in participants_raw if str(p).strip()]

        dm_raw = data.get("duration_minutes")
        duration_minutes: int | None = None
        if dm_raw is not None and isinstance(dm_raw, int):
            duration_minutes = dm_raw

        now = utc_now_iso()
        row: dict[str, Any] = {
            "id": new_id(),
            "title": title,
            "date_text": self._opt_str(data.get("date_text")),
            "date_iso": _normalize_stored_date_iso(data.get("date_iso")),
            "time_text": self._opt_str(data.get("time_text")),
            "participants": participants,
            "location": self._opt_str(data.get("location")),
            "description": self._opt_str(data.get("description")),
            "duration_minutes": duration_minutes,
            "created_at": now,
            "updated_at": now,
        }

        items = self.list_events()
        items.append(row)
        save_json_list(self._path, items)
        return row

    def update_event(self, event_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        eid = str(event_id).strip()
        if not eid:
            return None

        items = self.list_events()
        idx = next((i for i, ev in enumerate(items) if str(ev.get("id")) == eid), None)
        if idx is None:
            return None

        cur = dict(items[idx])
        patch = {k: v for k, v in updates.items() if k not in ("id", "created_at")}

        if "title" in patch:
            t = str(patch.get("title") or "").strip()
            if not t:
                raise ValueError("title no puede quedar vacío")
            cur["title"] = t

        if "date_text" in patch:
            cur["date_text"] = self._opt_str(patch.get("date_text"))
        if "date_iso" in patch:
            cur["date_iso"] = _normalize_stored_date_iso(patch.get("date_iso"))
        if "time_text" in patch:
            cur["time_text"] = self._opt_str(patch.get("time_text"))
        if "location" in patch:
            cur["location"] = self._opt_str(patch.get("location"))
        if "description" in patch:
            cur["description"] = self._opt_str(patch.get("description"))

        if "participants" in patch:
            pr = patch.get("participants")
            if isinstance(pr, list):
                cur["participants"] = [str(p).strip() for p in pr if str(p).strip()]
            else:
                cur["participants"] = []

        if "duration_minutes" in patch:
            dm = patch.get("duration_minutes")
            cur["duration_minutes"] = dm if isinstance(dm, int) else None

        cur["updated_at"] = utc_now_iso()
        items[idx] = cur
        save_json_list(self._path, items)
        return cur

    def delete_event(self, event_id: str) -> bool:
        eid = str(event_id).strip()
        if not eid:
            return False
        items = self.list_events()
        new_items = [ev for ev in items if str(ev.get("id")) != eid]
        if len(new_items) == len(items):
            return False
        save_json_list(self._path, new_items)
        return True

    @staticmethod
    def _opt_str(v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None
