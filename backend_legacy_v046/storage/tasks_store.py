import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TasksStore:
    """Tareas en data/tasks.json (sin base de datos)."""

    def __init__(self, file_path: Path | None = None) -> None:
        if file_path is None:
            root = Path(__file__).resolve().parent.parent.parent
            file_path = root / "data" / "tasks.json"
        self._path = file_path

    def _ensure_parent(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list:
        if not self._path.is_file():
            return []
        with open(self._path, encoding="utf-8") as fp:
            return json.load(fp)

    def _save(self, items: list) -> None:
        self._ensure_parent()
        with open(self._path, "w", encoding="utf-8") as fp:
            json.dump(items, fp, ensure_ascii=False, indent=2)

    def add_task(self, task_data: "str | dict[str, Any]") -> dict:
        """Crea una tarea. Acepta str (legado: solo título) o dict con campos opcionales.

        v0.21.9 — Se acepta también `description` opcional.
        Compatibilidad: las tareas antiguas sin `description` siguen siendo
        válidas. Solo se persiste `description` si trae texto.
        """
        items = self._load()
        if isinstance(task_data, str):
            title = (task_data or "").strip() or "Tarea"
            task: dict[str, Any] = {
                "id": str(uuid.uuid4()),
                "title": title,
                "completed": False,
                "created_at": _utc_iso(),
            }
        else:
            data = task_data or {}
            title = (str(data.get("title") or "")).strip() or "Tarea"
            task = {
                "id": str(uuid.uuid4()),
                "title": title,
                "completed": False,
                "created_at": _utc_iso(),
            }
            for k in ("date_text", "time_text", "priority", "description"):
                v = data.get(k)
                if v is None:
                    continue
                s = str(v).strip()
                if s:
                    task[k] = s
        items.append(task)
        self._save(items)
        return task

    def get_tasks(self) -> list:
        return self._load()

    def get_task_by_id(self, task_id: str) -> dict | None:
        for t in self._load():
            if str(t.get("id", "")) == str(task_id):
                return t
        return None

    def complete_task(self, task_id: str) -> dict | None:
        items = self._load()
        for t in items:
            if t.get("id") == task_id:
                t["completed"] = True
                self._save(items)
                return t
        return None

    def delete_task(self, task_id: str) -> bool:
        items = self._load()
        kept = [t for t in items if t.get("id") != task_id]
        if len(kept) == len(items):
            return False
        self._save(kept)
        return True

    def update_task(
        self, task_id: str, title_or_updates: "str | dict[str, Any]"
    ) -> dict | None:
        """Actualiza una tarea.

        v0.21.9 — Acepta:
          - `str` legado: actualiza solo el `title` (compat con PATCH /tasks/{id}).
          - `dict`: aplica los campos no nulos de un subconjunto permitido
            (`title`, `description`, `date_text`, `time_text`, `priority`,
            `completed`). Los campos a `None`/"" se ignoran (no se borran
            los anteriores para no romper datos previos).
        """
        items = self._load()
        for t in items:
            if t.get("id") != task_id:
                continue
            if isinstance(title_or_updates, str):
                t["title"] = title_or_updates
            else:
                updates = title_or_updates or {}
                for k in (
                    "title",
                    "description",
                    "date_text",
                    "time_text",
                    "priority",
                ):
                    if k not in updates:
                        continue
                    v = updates.get(k)
                    if v is None:
                        continue
                    s = str(v).strip()
                    if s:
                        t[k] = s
                if "completed" in updates and isinstance(updates["completed"], bool):
                    t["completed"] = updates["completed"]
            t["updated_at"] = _utc_iso()
            self._save(items)
            return t
        return None
