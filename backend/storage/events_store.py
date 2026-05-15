import json
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _strip_accents(s: str) -> str:
    nkfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nkfd if unicodedata.category(c) != "Mn")


_QUESTION_LIKE_PREFIXES = (
    "puedes decirme",
    "podrias decirme",
    "podrías decirme",
    "que tengo",
    "qué tengo",
    "a que hora",
    "a qué hora",
    "donde",
    "dónde",
    "con quien",
    "con quién",
    "cuando",
    "cuándo",
    "tengo algo",
    "hay algo",
    "que hay",
    "qué hay",
    "cual es",
    "cuál es",
    "que citas tengo",
    "qué citas tengo",
)


_AGENDA_SEARCH_STOPWORDS = frozenset(
    {
        "a",
        "al",
        "algo",
        "como",
        "con",
        "cuando",
        "cuanto",
        "de",
        "del",
        "donde",
        "el",
        "en",
        "es",
        "esta",
        "estas",
        "este",
        "esto",
        "ha",
        "han",
        "has",
        "hay",
        "he",
        "hora",
        "la",
        "las",
        "le",
        "les",
        "lo",
        "los",
        "me",
        "mi",
        "mis",
        "no",
        "o",
        "por",
        "para",
        "que",
        "quien",
        "se",
        "si",
        "son",
        "su",
        "sus",
        "te",
        "tu",
        "tus",
        "un",
        "una",
        "unos",
        "unas",
    }
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventsStore:
    """Eventos de calendario en data/events.json (sin base de datos)."""

    def __init__(self, file_path: Path | None = None) -> None:
        if file_path is None:
            root = Path(__file__).resolve().parent.parent.parent
            file_path = root / "data" / "events.json"
        self._path = file_path

    def _focus_path(self) -> Path:
        return self._path.parent / "agenda_focus.json"

    def _agenda_context_path(self) -> Path:
        # v0.21.3 — última respuesta de agenda para follow-ups del usuario.
        return self._path.parent / "agenda_context.json"

    def get_last_agenda_context(
        self, user_id: str = "local_default_user"
    ) -> dict[str, Any] | None:
        """
        Devuelve el último `last_agenda_context` guardado para `user_id`.

        Estructura mínima esperada:
        {
            "user_id": "...",
            "last_operation": "query_calendar | update_calendar_event | ...",
            "last_topic": "string corto",
            "last_answer_summary": "string corto",
            "candidate_event_ids": ["id1", "id2", ...],
            "focused_event_id": "id | null",
            "saved_at": "iso-utc",
        }

        Devuelve None si no hay nada o el contenido no es válido.
        """
        p = self._agenda_context_path()
        if not p.is_file():
            return None
        try:
            with open(p, encoding="utf-8") as fp:
                data = json.load(fp)
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict):
            return None
        uid_doc = str(data.get("user_id") or "").strip() or "local_default_user"
        if user_id and uid_doc != user_id:
            return None
        return data

    def set_last_agenda_context(
        self,
        *,
        user_id: str = "local_default_user",
        last_operation: str | None = None,
        last_topic: str | None = None,
        last_answer_summary: str | None = None,
        candidate_event_ids: list[str] | None = None,
        focused_event_id: str | None = None,
        duplicates_pending: bool = False,
        conflicts_pending: bool = False,
    ) -> dict[str, Any]:
        """Guarda el último contexto de agenda (sobrescribe). Mínimo y sin efectos secundarios.

        v0.21.5b — `duplicates_pending` y `conflicts_pending` marcan que la
        última respuesta de agenda detectó duplicados o solapamientos y propuso
        revisarlos. Sirve para que el motor unificado NO interprete la siguiente
        respuesta del usuario (p. ej. "mantén la cita con el médico") como una
        actualización de evento.
        """
        self._ensure_parent()
        payload: dict[str, Any] = {
            "user_id": user_id or "local_default_user",
            "last_operation": last_operation,
            "last_topic": (last_topic or "").strip()[:160] or None,
            "last_answer_summary": (last_answer_summary or "").strip()[:400] or None,
            "candidate_event_ids": [
                str(x).strip() for x in (candidate_event_ids or []) if str(x).strip()
            ][:12],
            "focused_event_id": str(focused_event_id).strip() if focused_event_id else None,
            "duplicates_pending": bool(duplicates_pending),
            "conflicts_pending": bool(conflicts_pending),
            "saved_at": _utc_iso(),
        }
        with open(self._agenda_context_path(), "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
        return payload

    def clear_last_agenda_context(self) -> None:
        p = self._agenda_context_path()
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass

    @staticmethod
    def _normalize_search_text(value: str) -> str:
        """Texto en minúsculas, sin acentos ni signos; espacios colapsados."""
        raw = (value or "").strip().lower()
        if not raw:
            return ""
        norm = _strip_accents(raw)
        norm = re.sub(r"[^\w\s]+", " ", norm)
        norm = re.sub(r"\s+", " ", norm).strip()
        return norm

    @staticmethod
    def is_question_like(event: dict[str, Any]) -> bool:
        """True si el evento parece ser una pregunta guardada por error (legado)."""
        if not isinstance(event, dict):
            return False
        for key in ("title", "source_text"):
            v = event.get(key)
            if not isinstance(v, str):
                continue
            n = EventsStore._normalize_search_text(v)
            if not n:
                continue
            for p in _QUESTION_LIKE_PREFIXES:
                pn = EventsStore._normalize_search_text(p)
                if pn and n.startswith(pn):
                    return True
        return False

    def _event_search_blob(self, event: dict[str, Any]) -> str:
        parts: list[str] = []
        for key in (
            "title",
            "date_text",
            "time_text",
            "location",
            "description",
            "source_text",
        ):
            val = event.get(key)
            if isinstance(val, str) and val.strip():
                n = self._normalize_search_text(val)
                if n:
                    parts.append(n)
        participants = event.get("participants")
        if isinstance(participants, list):
            for p in participants:
                if isinstance(p, str) and p.strip():
                    n = self._normalize_search_text(p)
                    if n:
                        parts.append(n)
        return " ".join(parts)

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

    def get_focused_event_id(self) -> str | None:
        p = self._focus_path()
        if not p.is_file():
            return None
        try:
            with open(p, encoding="utf-8") as fp:
                data = json.load(fp)
            eid = data.get("focused_event_id")
            if eid is None or eid == "":
                return None
            return str(eid).strip() or None
        except (json.JSONDecodeError, OSError):
            return None

    def set_focused_event_id(self, event_id: str | None) -> None:
        self._ensure_parent()
        p = self._focus_path()
        if not event_id:
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass
            return
        with open(p, "w", encoding="utf-8") as fp:
            json.dump(
                {"focused_event_id": str(event_id)},
                fp,
                ensure_ascii=False,
                indent=2,
            )

    def get_focused_event(self) -> dict[str, Any] | None:
        eid = self.get_focused_event_id()
        if not eid:
            return None
        return self.get_event_by_id(eid)

    def get_event_by_id(self, event_id: str) -> dict[str, Any] | None:
        for ev in self._load():
            if str(ev.get("id", "")) == str(event_id):
                return ev
        return None

    def add_event(self, event_data: str | dict[str, Any]) -> dict[str, Any]:
        """
        Crea un evento. Si event_data es str, comportamiento legado (solo título).
        Si es dict, evento estructurado (v0.21+).
        """
        if isinstance(event_data, str):
            items = self._load()
            event = {
                "id": str(uuid.uuid4()),
                "title": (event_data or "").strip() or "Evento",
                "created_at": _utc_iso(),
            }
            items.append(event)
            self._save(items)
            return event
        return self._add_structured_event(event_data)

    def _add_structured_event(self, data: dict[str, Any]) -> dict[str, Any]:
        items = self._load()
        title = (
            str(data.get("title", "")).strip() if data.get("title") is not None else ""
        ) or "Evento"
        event: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "title": title,
            "created_at": _utc_iso(),
        }
        optional_keys = (
            "date_text",
            "time_text",
            "location",
            "description",
            "participants",
            "duration_minutes",
            "source_text",
            "confidence",
            "needs_confirmation",
            "missing_fields",
        )
        for k in optional_keys:
            if k not in data:
                continue
            val = data[k]
            if val is None:
                continue
            if k == "participants" and isinstance(val, list):
                event[k] = val
            elif k == "missing_fields" and isinstance(val, list):
                event[k] = val
            elif k in ("duration_minutes", "confidence"):
                event[k] = val
            elif k == "needs_confirmation":
                event[k] = bool(val)
            else:
                s = str(val).strip()
                if s:
                    event[k] = s
        items.append(event)
        self._save(items)
        return event

    def add_calendar_event(self, data: dict[str, Any]) -> dict[str, Any]:
        """Alias de compatibilidad con versiones anteriores del backend."""
        return self.add_event(data)

    def get_events(self) -> list:
        return self._load()

    def get_last_event(self) -> dict[str, Any] | None:
        items = self._load()
        if not items:
            return None
        return items[-1]

    def events_for_day_hint(
        self,
        hint: str,
        include_question_like: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Devuelve los eventos cuyos campos textuales contienen la pista de día.

        v0.21.5 — Pensado para la síntesis inferencial de agenda: por defecto
        incluye entradas «pregunta-like» para que el motor pueda marcarlas como
        sospechosas (`suspicious_entries`) en lugar de descartarlas en silencio.
        """
        h = (hint or "").strip()
        if not h:
            return []
        hn = self._normalize_search_text(h.replace("ñ", "n"))
        if not hn:
            return []
        items = self._load()
        out: list[dict[str, Any]] = []
        for ev in items:
            if not isinstance(ev, dict):
                continue
            if not include_question_like and EventsStore.is_question_like(ev):
                continue
            for key in ("date_text", "source_text", "title", "time_text"):
                val = ev.get(key)
                if not isinstance(val, str):
                    continue
                blob = self._normalize_search_text(val.replace("ñ", "n"))
                if hn in blob:
                    out.append(ev)
                    break
        return out

    @staticmethod
    def normalize_time_text(value: Any) -> str:
        """
        Normaliza una hora textual a forma comparable (HH:MM en 24h aproximado).

        v0.21.5 — usado para agrupar duplicados y detectar solapamientos sin
        depender de un parser real de datetime.
        """
        if value is None:
            return ""
        s = str(value).strip().lower()
        if not s:
            return ""
        s = _strip_accents(s)
        s = s.replace(",", " ").replace(";", " ")
        s = re.sub(r"\b(a\s+las?|las?|hora|horas|h)\b", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        m = re.search(r"(\d{1,2})[:.h](\d{2})", s)
        if m:
            hh = int(m.group(1))
            mm = int(m.group(2))
        else:
            m = re.search(r"\b(\d{1,2})\b", s)
            if not m:
                return ""
            hh = int(m.group(1))
            mm = 0
        if hh > 23:
            return ""
        if mm > 59:
            return ""
        # 1..7 sin "de la mañana/tarde" se deja tal cual; no asumimos 13-19.
        return f"{hh:02d}:{mm:02d}"

    @staticmethod
    def normalize_title_text(value: Any) -> str:
        """Título normalizado (sin acentos, sin signos, sin stopwords cortas) para detectar duplicados."""
        if value is None:
            return ""
        s = _strip_accents(str(value).lower())
        s = re.sub(r"[^\w\s]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        if not s:
            return ""
        tokens = [t for t in s.split() if len(t) >= 3 and t not in _AGENDA_SEARCH_STOPWORDS]
        return " ".join(tokens) if tokens else s

    def search_events(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Búsqueda simple por texto en campos conocidos (compat. eventos antiguos).
        Penaliza eventos «pregunta-like» (títulos/source_text que parecen preguntas
        guardadas por error en versiones anteriores) para que no se prioricen.
        """
        q_norm = self._normalize_search_text(query)
        if not q_norm:
            return []
        items = self._load()
        token_candidates = re.findall(r"[a-z0-9]+", q_norm)
        tokens = [
            t
            for t in token_candidates
            if len(t) >= 2 and t not in _AGENDA_SEARCH_STOPWORDS
        ]
        scored: list[tuple[float, int, dict[str, Any]]] = []
        seen: set[str] = set()
        for idx, ev in enumerate(items):
            eid = str(ev.get("id", "")) or f"idx-{idx}"
            if eid in seen:
                continue
            blob = self._event_search_blob(ev)
            if not blob:
                continue
            score = 0.0
            if q_norm in blob:
                score += 3.0
            if tokens:
                token_hits = sum(1 for t in tokens if t in blob)
                score += token_hits
            if score <= 0:
                continue
            if EventsStore.is_question_like(ev):
                score -= 5.0
            seen.add(eid)
            scored.append((score, idx, ev))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [ev for score, _i, ev in scored if score > 0][:limit]

    def update_event(
        self, event_id: str, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Fusiona updates en el evento; no borra campos con valores vacíos omitidos."""
        items = self._load()
        for i, ev in enumerate(items):
            if str(ev.get("id", "")) != str(event_id):
                continue
            for k, val in (updates or {}).items():
                if k in ("id", "created_at"):
                    continue
                if val is None:
                    continue
                if k == "participants" and isinstance(val, list):
                    merged: list[str] = []
                    prev = ev.get("participants")
                    if isinstance(prev, list):
                        for p in prev:
                            if isinstance(p, str) and p.strip():
                                merged.append(p.strip())
                    for p in val:
                        if p is None:
                            continue
                        ps = str(p).strip()
                        if ps and ps not in merged:
                            merged.append(ps)
                    ev["participants"] = merged
                elif k == "missing_fields" and isinstance(val, list):
                    ev[k] = [str(x).strip() for x in val if str(x).strip()]
                elif k == "duration_minutes":
                    try:
                        ev[k] = int(val)
                    except (TypeError, ValueError):
                        pass
                elif k == "needs_confirmation":
                    ev[k] = bool(val)
                elif k == "confidence":
                    try:
                        ev[k] = float(val)
                    except (TypeError, ValueError):
                        pass
                else:
                    s = str(val).strip()
                    if s:
                        ev[k] = s
            ev["updated_at"] = _utc_iso()
            items[i] = ev
            self._save(items)
            return ev
        return None

    def delete_event(self, event_id: str) -> bool:
        """Elimina un evento por id. Analogía con NotesStore y TasksStore."""
        sid = str(event_id).strip()
        if not sid:
            return False
        items = self._load()
        kept = [e for e in items if str(e.get("id", "")) != sid]
        if len(kept) == len(items):
            return False
        self._save(kept)
        if self.get_focused_event_id() == sid:
            self.set_focused_event_id(None)
        return True

    @staticmethod
    def format_event_summary(event: dict[str, Any]) -> str:
        """Frase compacta tipo «cita mañana a las 14:30 en hospital»."""
        t = str(event.get("title") or "").strip() or "evento"
        parts: list[str] = [t]
        if event.get("date_text"):
            parts.append(str(event.get("date_text")).strip())
        tt = event.get("time_text")
        if tt:
            parts.append(f"a las {str(tt).strip()}")
        loc = event.get("location")
        if loc:
            parts.append(f"en {str(loc).strip()}")
        pp = event.get("participants")
        if isinstance(pp, list) and pp:
            names = ", ".join(str(p).strip() for p in pp if p and str(p).strip())
            if names:
                parts.append(f"con {names}")
        if len(parts) == 1:
            return t
        return f"{parts[0]} {' '.join(parts[1:])}".strip()
