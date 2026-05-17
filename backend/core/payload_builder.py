"""Construcción del payload mínimo para GPT — solo empaquetado, sin semántica."""

from __future__ import annotations

import copy
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Europe/Madrid"
DEFAULT_LOCALE = "es-ES"

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b"
)
_ID_EQUALS_RE = re.compile(r"id\s*=\s*[a-fA-F0-9\-]{8,}", re.IGNORECASE)

_TECH_TOKEN_RES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pat, re.IGNORECASE), "")
    for pat in (
        r"\bpending\b",
        r"\bthread_state\b",
        r"\bpolicy\b",
        r"\bschema\b",
        r"\bJSON\b",
        r"\bdebug\b",
        r"\bmax_clarification\b",
        r"\bclarification_step\b",
    )
)

_ALLOWED_S = frozenset({"ready", "ask", "need_context", "answer", "fail"})
_ALLOWED_I = frozenset({"event", "task", "note", "mail", "general", "unknown"})
_ALLOWED_A_STR = frozenset(
    {"create", "update", "delete", "query", "complete", "draft", "answer"}
)

FAIL_DEFAULT: dict[str, Any] = {
    "s": "fail",
    "i": "unknown",
    "a": None,
    "obj": {},
    "target": None,
    "q": None,
    "r": "No estoy captando toda la información necesaria. ¿Podrías escribirlo de nuevo de forma más concreta?",
    "pending": None,
    "ctx": None,
}


def _local_calendar_date_iso(tz_name: str) -> str:
    """Fecha civil YYYY-MM-DD del reloj en `tz`; no interpreta el raw del usuario."""
    z = ZoneInfo(tz_name)
    return datetime.now(z).date().isoformat()


def build_payload(raw_text: str, thread_state: dict[str, Any] | None) -> dict[str, Any]:
    """Empaqueta texto y hilo abierto sin semántica.

    Si **open=true**: **mode=continue** y **thread** incluye **intent**, **object**,
    **last_question**, **pending** y **target** (puede ser null).
    """
    raw = (raw_text or "").strip()

    base: dict[str, Any] = {
        "raw": raw,
        "tz": DEFAULT_TIMEZONE,
        "locale": DEFAULT_LOCALE,
        "local_date": _local_calendar_date_iso(DEFAULT_TIMEZONE),
    }

    if isinstance(thread_state, dict) and thread_state.get("open") is True:
        base["mode"] = "continue"
        base["thread"] = {
            "intent": thread_state.get("intent"),
            "object": thread_state.get("object"),
            "last_question": thread_state.get("last_question"),
            "pending": thread_state.get("pending"),
            "target": thread_state.get("target"),
        }
        base["rules"] = {
            "hide_internal": True,
        }
    else:
        base["mode"] = "new"
        base["thread"] = None
        base["rules"] = {
            "hide_internal": True,
        }

    return base


def build_context_response_payload(
    *,
    peticion_original: str,
    respuesta_gpt_previa: dict[str, Any],
    contexto_encontrado: dict[str, Any],
) -> dict[str, Any]:
    """Segunda llamada a GPT: petición original + resultado previo + contexto técnico."""
    raw_po = (peticion_original or "").strip()
    return {
        "raw": raw_po,
        "tz": DEFAULT_TIMEZONE,
        "locale": DEFAULT_LOCALE,
        "local_date": _local_calendar_date_iso(DEFAULT_TIMEZONE),
        "mode": "context_response",
        "thread": {
            "intent": respuesta_gpt_previa.get("i"),
            "action": respuesta_gpt_previa.get("a"),
            "object": respuesta_gpt_previa.get("obj"),
            "last_gpt_status": "need_context",
            "ctx_requested": respuesta_gpt_previa.get("ctx"),
            "original_raw": raw_po,
        },
        "context": contexto_encontrado,
        "rules": {
            "hide_internal": True,
            "context_is_response_to_previous_need_context": True,
        },
    }


def normalize_target_id(val: Any) -> str | None:
    """Extrae identificador de evento/objeto desde campo target (string u objeto {\"id\"})."""
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip()
        return s or None
    if isinstance(val, dict):
        tid = val.get("id")
        if tid is None:
            tid = val.get("event_id")
        if isinstance(tid, str):
            xs = tid.strip()
            return xs or None
    return None


def extract_event_target_id(result: dict[str, Any]) -> str | None:
    """Igual que campo top-level target o pending.target tras normalizar."""
    tid = normalize_target_id(result.get("target"))
    if tid:
        return tid
    pend = result.get("pending")
    if isinstance(pend, dict):
        return normalize_target_id(pend.get("target"))
    return None


def sanitize_visible_text(text: str | None) -> str:
    """Quita fugas técnicas típicas sin intentar interpretar el mensaje."""
    if text is None:
        return ""
    s = str(text).strip()
    if not s:
        return ""

    s = _UUID_RE.sub("", s)
    s = _ID_EQUALS_RE.sub("", s)
    for rx, repl in _TECH_TOKEN_RES:
        s = rx.sub(repl, s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_gpt_response(data: dict[str, Any] | None) -> dict[str, Any]:
    """Normaliza la respuesta compacta esperada del modelo."""
    if not isinstance(data, dict):
        return copy.deepcopy(FAIL_DEFAULT)

    s_raw = data.get("s")
    s_val = str(s_raw).strip().lower() if isinstance(s_raw, str) else None
    if s_val not in _ALLOWED_S:
        return copy.deepcopy(FAIL_DEFAULT)

    i_raw = data.get("i")
    i_val = str(i_raw).strip().lower() if isinstance(i_raw, str) else None
    if i_val not in _ALLOWED_I:
        i_val = "unknown"

    a_norm = _normalize_a(data.get("a"))

    obj_raw = data.get("obj")
    obj_val: dict[str, Any] = obj_raw if isinstance(obj_raw, dict) else {}

    target_val: str | None = normalize_target_id(data.get("target"))

    pending_raw = data.get("pending")
    pending_val: dict[str, Any] | None = (
        pending_raw if isinstance(pending_raw, dict) else None
    )

    ctx_raw = data.get("ctx")
    ctx_val: dict[str, Any] | None = ctx_raw if isinstance(ctx_raw, dict) else None

    q_raw = data.get("q")
    q_str = sanitize_visible_text(q_raw if isinstance(q_raw, str) else None)
    q_val = q_str if q_str else None

    r_raw = data.get("r")
    r_str = sanitize_visible_text(r_raw if isinstance(r_raw, str) else None)
    r_val = r_str if r_str else None

    return {
        "s": s_val,
        "i": i_val,
        "a": a_norm,
        "obj": obj_val,
        "target": target_val,
        "q": q_val,
        "r": r_val,
        "pending": pending_val,
        "ctx": ctx_val,
    }


def _normalize_a(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, str) and val.strip().lower() == "null":
        return None
    if isinstance(val, str):
        av = val.strip().lower()
        if av in _ALLOWED_A_STR:
            return av
    return None
