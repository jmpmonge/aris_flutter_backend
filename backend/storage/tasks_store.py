"""Persistencia de tareas en JSON — sin interpretación semántica."""

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


def _normalize_task_date_iso(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or not _DATE_ISO_BASIC_RE.match(s):
        return None
    try:
        y = int(s[0:4])
        mo = int(s[5:7])
        d = int(s[8:10])
    except ValueError:
        return None
    if y < 1970 or y > 2199 or mo < 1 or mo > 12 or d < 1 or d > 31:
        return None
    return s


def _normalize_task_priority(v: Any) -> str:
    if v is None:
        return "normal"
    s = str(v).strip().lower()
    if s == "high":
        return "high"
    return "normal"


def _normalize_task_tags(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    seen_cf: set[str] = set()
    out: list[str] = []
    for raw in v:
        s = str(raw).strip()
        if not s:
            continue
        cf = s.casefold()
        if cf in seen_cf:
            continue
        seen_cf.add(cf)
        out.append(s)
    return out


class TasksStore:
    """Lista de tareas en backend/data/tasks.json."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_backend_data_dir() / "tasks.json")

    def list_tasks(self) -> list[dict[str, Any]]:
        rows = load_json_list(self._path)
        return [r for r in rows if isinstance(r, dict)]

    def add_task(self, data: dict[str, Any]) -> dict[str, Any]:
        title = str(data.get("title") or "").strip()
        if not title:
            raise ValueError("title es obligatorio y no puede estar vacío")

        completed_raw = data.get("completed")
        completed = bool(completed_raw) if completed_raw is not None else False

        now = utc_now_iso()
        row: dict[str, Any] = {
            "id": new_id(),
            "title": title,
            "description": self._opt_str(data.get("description")),
            "date_text": self._opt_str(data.get("date_text")),
            "date_iso": _normalize_task_date_iso(data.get("date_iso")),
            "time_text": self._opt_str(data.get("time_text")),
            "priority": _normalize_task_priority(data.get("priority")),
            "tags": _normalize_task_tags(data.get("tags")),
            "completed": completed,
            "created_at": now,
            "updated_at": now,
        }

        items = self.list_tasks()
        items.append(row)
        save_json_list(self._path, items)
        return row

    def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        tid = str(task_id).strip()
        if not tid:
            return None

        items = self.list_tasks()
        idx = next((i for i, t in enumerate(items) if str(t.get("id")) == tid), None)
        if idx is None:
            return None

        cur = dict(items[idx])
        patch = {k: v for k, v in updates.items() if k not in ("id", "created_at")}

        if "title" in patch:
            t = str(patch.get("title") or "").strip()
            if not t:
                raise ValueError("title no puede quedar vacío")
            cur["title"] = t

        if "description" in patch:
            cur["description"] = self._opt_str(patch.get("description"))
        if "date_text" in patch:
            cur["date_text"] = self._opt_str(patch.get("date_text"))
        if "time_text" in patch:
            cur["time_text"] = self._opt_str(patch.get("time_text"))
        if "date_iso" in patch:
            cur["date_iso"] = _normalize_task_date_iso(patch.get("date_iso"))
        if "priority" in patch:
            cur["priority"] = _normalize_task_priority(patch.get("priority"))
        if "tags" in patch:
            cur["tags"] = _normalize_task_tags(patch.get("tags"))
        if "completed" in patch:
            cur["completed"] = bool(patch.get("completed"))

        cur["updated_at"] = utc_now_iso()
        items[idx] = cur
        save_json_list(self._path, items)
        return cur

    def complete_task(self, task_id: str) -> dict[str, Any] | None:
        return self.update_task(task_id, {"completed": True})

    def delete_task(self, task_id: str) -> dict[str, Any] | None:
        """Elimina por id estable; sin semántica. Devuelve la fila borrada o None."""
        tid = str(task_id).strip()
        if not tid:
            return None
        items = self.list_tasks()
        idx = next((i for i, t in enumerate(items) if str(t.get("id")) == tid), None)
        if idx is None:
            return None
        removed = dict(items[idx])
        del items[idx]
        save_json_list(self._path, items)
        return removed

    @staticmethod
    def _opt_str(v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None
