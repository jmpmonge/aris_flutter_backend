import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class NotesStore:
    """Notas en data/notes.json (sin base de datos)."""

    def __init__(self, file_path: Path | None = None) -> None:
        if file_path is None:
            root = Path(__file__).resolve().parent.parent.parent
            file_path = root / "data" / "notes.json"
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

    def add_note(self, note_data: "str | dict") -> dict:
        """
        Crea una nota. Si `note_data` es str: comportamiento legado (solo `content`).
        Si es dict: nota estructurada con `title` y/o `content` (v0.21.4d).

        Compatibilidad: GET /notes sigue devolviendo el listado tal cual, incluyendo
        notas antiguas sin `title`.
        """
        items = self._load()
        if isinstance(note_data, str):
            note = {
                "id": str(uuid.uuid4()),
                "content": note_data,
                "created_at": _utc_iso(),
            }
            items.append(note)
            self._save(items)
            return note

        if not isinstance(note_data, dict):
            note_data = {"content": str(note_data)}

        title = note_data.get("title")
        content = note_data.get("content")
        title_s = str(title).strip() if title else ""
        content_s = str(content).strip() if content else ""

        note: dict = {
            "id": str(uuid.uuid4()),
            "created_at": _utc_iso(),
        }
        if title_s:
            note["title"] = title_s
        # Para conservar la compatibilidad con frontend y endpoints, siempre
        # rellenamos `content` con algo: si solo hay título, se usa el título.
        note["content"] = content_s or title_s
        items.append(note)
        self._save(items)
        return note

    def get_notes(self) -> list:
        return self._load()

    def delete_note(self, note_id: str) -> bool:
        items = self._load()
        kept = [n for n in items if n.get("id") != note_id]
        if len(kept) == len(items):
            return False
        self._save(kept)
        return True

    def update_note(self, note_id: str, content: str, title: str | None = None) -> dict | None:
        items = self._load()
        for n in items:
            if n.get("id") == note_id:
                n["content"] = content
                if title is not None:
                    t = str(title).strip()
                    if t:
                        n["title"] = t
                    elif "title" in n:
                        n.pop("title", None)
                n["updated_at"] = _utc_iso()
                self._save(items)
                return n
        return None
