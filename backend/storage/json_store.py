"""Utilidades JSON sin semántica de dominio."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def load_json_list(path: Path | str) -> list[Any]:
    p = Path(path)
    if not p.is_file():
        return []
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        return list(data) if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_json_list(path: Path | str, items: list[Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(items, ensure_ascii=False, indent=2)
    p.write_text(payload + "\n", encoding="utf-8")


def load_json_dict(path: Path | str, default: dict[str, Any]) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return dict(default)
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        return dict(data) if isinstance(data, dict) else dict(default)
    except (OSError, json.JSONDecodeError):
        return dict(default)


def save_json_dict(path: Path | str, data: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    p.write_text(payload + "\n", encoding="utf-8")
