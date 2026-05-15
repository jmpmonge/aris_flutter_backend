import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PendingActionStore:
    """Una acción pendiente de confirmación en data/pending_action.json (sin base de datos)."""

    def __init__(self, file_path: Path | None = None) -> None:
        if file_path is None:
            root = Path(__file__).resolve().parent.parent.parent
            file_path = root / "data" / "pending_action.json"
        self._path = file_path

    def _ensure_parent(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get_pending_action(self) -> dict[str, Any] | None:
        if not self._path.is_file():
            return None
        with open(self._path, encoding="utf-8") as fp:
            data = json.load(fp)
        if data is None or data == {}:
            return None
        if not isinstance(data, dict):
            return None
        return data

    def save_pending_action(self, action: dict[str, Any]) -> None:
        payload = dict(action)
        if "created_at" not in payload or not payload["created_at"]:
            payload["created_at"] = _utc_iso()
        self._ensure_parent()
        with open(self._path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)

    def clear_pending_action(self) -> None:
        self._ensure_parent()
        with open(self._path, "w", encoding="utf-8") as fp:
            json.dump(None, fp)
