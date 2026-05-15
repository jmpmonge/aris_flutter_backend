"""Persistencia de tareas en JSON — sin interpretación semántica."""

from __future__ import annotations

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
            "time_text": self._opt_str(data.get("time_text")),
            "priority": self._opt_str(data.get("priority")),
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
        if "priority" in patch:
            cur["priority"] = self._opt_str(patch.get("priority"))
        if "completed" in patch:
            cur["completed"] = bool(patch.get("completed"))

        cur["updated_at"] = utc_now_iso()
        items[idx] = cur
        save_json_list(self._path, items)
        return cur

    def complete_task(self, task_id: str) -> dict[str, Any] | None:
        return self.update_task(task_id, {"completed": True})

    def delete_task(self, task_id: str) -> bool:
        tid = str(task_id).strip()
        if not tid:
            return False
        items = self.list_tasks()
        new_items = [t for t in items if str(t.get("id")) != tid]
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
