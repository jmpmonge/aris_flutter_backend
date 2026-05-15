import json
from datetime import datetime, timezone
from pathlib import Path


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HistoryStore:
    """Persistencia sencilla del historial en data/history.json (sin base de datos)."""

    def __init__(self, file_path: Path | None = None) -> None:
        if file_path is None:
            root = Path(__file__).resolve().parent.parent.parent
            file_path = root / "data" / "history.json"
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

    def save_interaction(
        self,
        user_text: str,
        assistant_text: str,
        intent_type: str,
        ui_hint: str | None = None,
    ) -> None:
        items = self._load()
        row: dict = {
            "user_text": user_text,
            "assistant_text": assistant_text,
            "intent_type": intent_type,
            "created_at": _utc_iso(),
        }
        if ui_hint:
            row["ui_hint"] = ui_hint
        items.append(row)
        self._save(items)

    def get_history(self) -> list:
        return self._load()
