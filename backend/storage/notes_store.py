"""Persistencia de notas en JSON — sin interpretación semántica."""

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


class NotesStore:
    """Lista de notas en backend/data/notes.json."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_backend_data_dir() / "notes.json")

    def list_notes(self) -> list[dict[str, Any]]:
        rows = load_json_list(self._path)
        return [r for r in rows if isinstance(r, dict)]

    def add_note(self, data: dict[str, Any]) -> dict[str, Any]:
        content = str(data.get("content") or "").strip()
        if not content:
            raise ValueError("content es obligatorio y no puede estar vacío")

        tags_raw = data.get("tags")
        tags: list[str] = []
        if isinstance(tags_raw, list):
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]

        now = utc_now_iso()
        row: dict[str, Any] = {
            "id": new_id(),
            "title": self._opt_str(data.get("title")),
            "content": content,
            "tags": tags,
            "created_at": now,
            "updated_at": now,
        }

        items = self.list_notes()
        items.append(row)
        save_json_list(self._path, items)
        return row

    def update_note(self, note_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        nid = str(note_id).strip()
        if not nid:
            return None

        items = self.list_notes()
        idx = next((i for i, n in enumerate(items) if str(n.get("id")) == nid), None)
        if idx is None:
            return None

        cur = dict(items[idx])
        patch = {k: v for k, v in updates.items() if k not in ("id", "created_at")}

        if "content" in patch:
            c = str(patch.get("content") or "").strip()
            if not c:
                raise ValueError("content no puede quedar vacío")
            cur["content"] = c

        if "title" in patch:
            cur["title"] = self._opt_str(patch.get("title"))

        if "tags" in patch:
            tr = patch.get("tags")
            if isinstance(tr, list):
                cur["tags"] = [str(t).strip() for t in tr if str(t).strip()]
            else:
                cur["tags"] = []

        cur["updated_at"] = utc_now_iso()
        items[idx] = cur
        save_json_list(self._path, items)
        return cur

    def delete_note(self, note_id: str) -> bool:
        nid = str(note_id).strip()
        if not nid:
            return False
        items = self.list_notes()
        new_items = [n for n in items if str(n.get("id")) != nid]
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
