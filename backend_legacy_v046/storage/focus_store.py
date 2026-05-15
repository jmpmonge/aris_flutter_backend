"""FocusStore — Foco operativo multi-entidad de ARIS (v0.21.9).

Recuerda cuál fue la última entidad activa (evento / tarea / nota) para que
los mensajes pronominales o contextuales del usuario se apliquen a la
entidad correcta y no recaigan siempre sobre el último evento focalizado.

Persistencia: `data/focus.json` (sin base de datos, sin login real).

Forma del documento:
{
  "user_id": "local_default_user",
  "last_focused_kind": "event" | "task" | "note" | null,
  "last_focused_id": "..." | null,
  "last_focused_label": "..." | null,
  "last_operation": "create_task | update_task | create_event | ..." | null,
  "last_focused_at": "iso-utc" | null
}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_USER_ID = "local_default_user"

_ALLOWED_KINDS = frozenset({"event", "task", "note"})


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FocusStore:
    """Foco operativo global. Por ahora monousuario (`DEFAULT_USER_ID`).

    No hay multiusuario real: el campo `user_id` se mantiene para preparar
    una migración futura sin romper el formato.
    """

    def __init__(self, file_path: Path | None = None) -> None:
        if file_path is None:
            root = Path(__file__).resolve().parent.parent.parent
            file_path = root / "data" / "focus.json"
        self._path = file_path

    def _ensure_parent(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _empty(self, user_id: str) -> dict[str, Any]:
        return {
            "user_id": user_id or DEFAULT_USER_ID,
            "last_focused_kind": None,
            "last_focused_id": None,
            "last_focused_label": None,
            "last_operation": None,
            "last_focused_at": None,
        }

    def get_focus(self, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
        """Devuelve el foco actual. Si no existe, devuelve la forma vacía
        (nunca `None`) para simplificar el uso."""
        uid = user_id or DEFAULT_USER_ID
        if not self._path.is_file():
            return self._empty(uid)
        try:
            with open(self._path, encoding="utf-8") as fp:
                data = json.load(fp)
        except (json.JSONDecodeError, OSError):
            return self._empty(uid)
        if not isinstance(data, dict):
            return self._empty(uid)
        doc_uid = str(data.get("user_id") or "").strip() or DEFAULT_USER_ID
        if uid and doc_uid != uid:
            return self._empty(uid)
        kind = data.get("last_focused_kind")
        if kind is not None and kind not in _ALLOWED_KINDS:
            kind = None
        return {
            "user_id": doc_uid,
            "last_focused_kind": kind,
            "last_focused_id": (str(data.get("last_focused_id")).strip()
                                if data.get("last_focused_id") else None),
            "last_focused_label": (str(data.get("last_focused_label")).strip()
                                   if data.get("last_focused_label") else None),
            "last_operation": (str(data.get("last_operation")).strip()
                               if data.get("last_operation") else None),
            "last_focused_at": data.get("last_focused_at"),
        }

    def set_focus(
        self,
        kind: str | None,
        entity_id: str | None,
        label: str | None = None,
        operation: str | None = None,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict[str, Any]:
        """Fija el foco operativo. Si `kind` no es válido, se limpia el foco."""
        uid = user_id or DEFAULT_USER_ID
        k = (kind or "").strip().lower() or None
        if k not in _ALLOWED_KINDS:
            return self.clear_focus(uid)
        eid = (str(entity_id).strip() if entity_id else "") or None
        if not eid:
            return self.clear_focus(uid)
        payload: dict[str, Any] = {
            "user_id": uid,
            "last_focused_kind": k,
            "last_focused_id": eid,
            "last_focused_label": (str(label).strip() if label else None) or None,
            "last_operation": (str(operation).strip() if operation else None) or None,
            "last_focused_at": _utc_iso(),
        }
        self._ensure_parent()
        with open(self._path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
        return payload

    def clear_focus(self, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
        """Limpia el foco operativo en disco y devuelve la forma vacía."""
        if self._path.is_file():
            try:
                self._path.unlink()
            except OSError:
                pass
        return self._empty(user_id or DEFAULT_USER_ID)
