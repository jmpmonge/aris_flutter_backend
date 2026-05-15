import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_REPO_ROOT / ".env")

from backend.core.openai_client import (
    DEFAULT_USER_ID,
    build_agenda_context_packet,
    try_agenda_context_reasoning,
    try_agenda_intent_analysis,
    try_calendar_event_extraction,
    try_complete_pending_calendar_event,
    try_consult_response,
    try_note_structuring,
    try_pending_reply_analysis,
    try_resolve_calendar_query,
    try_structured_intent_analysis,
    try_structured_user_intent,
)
from backend.storage.events_store import EventsStore
from backend.storage.focus_store import FocusStore
from backend.storage.notes_store import NotesStore
from backend.storage.pending_action_store import PendingActionStore
from backend.storage.tasks_store import TasksStore

logger = logging.getLogger(__name__)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_accents(s: str) -> str:
    nkfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nkfd if unicodedata.category(c) != "Mn")


_ALLOWED_PENDING_DECISIONS = frozenset(
    {
        "confirm",
        "cancel",
        "save_as_note",
        "save_as_task",
        "save_as_event",
        "needs_clarification",
        "unknown",
    }
)


def _normalize_exact_local_reply(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    norm = _strip_accents(raw.lower())
    norm = re.sub(r"[^\w\s]+", " ", norm)
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm


def _pending_resolve_dict(
    decision: str,
    confidence: float,
    reason: str,
    clarification_question: str | None,
    source: str,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "confidence": confidence,
        "reason": reason,
        "clarification_question": clarification_question,
        "source": source,
    }


def resolve_pending_reply(text: str, pending_action: dict[str, Any]) -> dict[str, Any]:
    """
    Resuelve la respuesta del usuario cuando hay pending_action.
    Solo casos inequívocos en local; el resto pasa por OpenAI (try_pending_reply_analysis).
    """
    raw = (text or "").strip()
    if not raw:
        return _pending_resolve_dict("unknown", 0.0, "texto vacío", None, "local")

    norm = _normalize_exact_local_reply(raw)
    if not norm:
        return _pending_resolve_dict("unknown", 0.0, "sin contenido útil", None, "local")

    local_confirm = frozenset({"si", "vale", "correcto", "confirmo", "adelante"})
    local_cancel = frozenset({"no", "cancelar", "cancela", "olvidalo", "dejalo"})
    tipo_map = {
        "como nota": "save_as_note",
        "como tarea": "save_as_task",
        "como evento": "save_as_event",
        "como calendario": "save_as_event",
    }

    if norm in local_confirm:
        return _pending_resolve_dict(
            "confirm", 1.0, "coincidencia local inequívoca", None, "local"
        )
    if norm in local_cancel:
        return _pending_resolve_dict(
            "cancel", 1.0, "coincidencia local inequívoca", None, "local"
        )
    if norm in tipo_map:
        d = tipo_map[norm]
        return _pending_resolve_dict(
            d, 1.0, "cambio de tipo local inequívoco (solo «como …»)", None, "local"
        )

    parsed = try_pending_reply_analysis(raw, pending_action)
    if parsed is None:
        logger.warning(
            "Respuesta pendiente: OpenAI no disponible o análisis fallido; se pide aclaración"
        )
        return _pending_resolve_dict(
            "needs_clarification",
            0.0,
            "sin análisis OpenAI (clave ausente, error o respuesta inválida)",
            None,
            "local",
        )

    decision = str(parsed["decision"]).strip().lower()
    conf = float(parsed["confidence"])
    reason = str(parsed["reason"] or "")
    cq_raw = parsed.get("clarification_question")
    cq = str(cq_raw).strip() if isinstance(cq_raw, str) else None
    if cq == "":
        cq = None

    if decision not in _ALLOWED_PENDING_DECISIONS:
        logger.info(
            "Respuesta pendiente: decisión %r fuera del conjunto permitido; needs_clarification",
            decision,
        )
        return _pending_resolve_dict(
            "needs_clarification",
            conf,
            f"decisión inválida del modelo: {decision}",
            cq,
            "openai",
        )

    if conf < 0.70:
        logger.info(
            "Respuesta pendiente: confidence %.2f < 0.70; needs_clarification (modelo decía %s)",
            conf,
            decision,
        )
        return _pending_resolve_dict(
            "needs_clarification",
            conf,
            reason,
            cq,
            "openai",
        )

    return _pending_resolve_dict(
        decision,
        conf,
        reason,
        cq,
        "openai",
    )


_UNKNOWN_PENDING_REPLY = (
    "No he entendido si quieres guardarlo, cancelarlo o cambiar el tipo. "
    "¿Quieres guardarlo como nota, tarea o evento, o prefieres cancelar?"
)


_CLARIFY_PENDING_REPLY = (
    "No lo he guardado todavía. ¿Quieres guardarlo como nota, tarea o evento, o prefieres cancelar?"
)


UI_HINT_CONFIRM_RESCUE = "confirm_rescue"


# v0.21.3 — Detección de mensajes contextuales sobre una respuesta previa de agenda.
# Tokens normalizados (sin acentos, minúsculas). Coincidencia por *prefijo* para cubrir
# variantes como "reestructúramelo", "reestructúralo", "reestructura", etc.
_AGENDA_FOLLOWUP_TOKEN_PREFIXES: tuple[str, ...] = (
    "reestructur",
    "estructur",
    "ordena",
    "ordename",
    "ordenam",
    "ordenalo",
    "resum",
    "explica",
    "explicam",
    "aclar",
    "agrup",
    "duplic",
    "prioriz",
    "revis",
    "organiza",
    "organizam",
    "simplifi",
    "ponlo",
    "hazlo",
    "rehazlo",
)

# Frases multi-palabra que también disparan follow-up.
_AGENDA_FOLLOWUP_PHRASES: tuple[str, ...] = (
    "quita duplicados",
    "quita los duplicados",
    "sin duplicados",
    "no lo entiendo",
    "no entiendo",
    "que significa",
    "que significa eso",
    "hazlo mas claro",
    "ponlo claro",
    "ponlo en claro",
    "hazlo mejor",
    "explicalo mejor",
)


# v0.21.4b — Detección de intención de calendario en mensajes mínimos / vagos.
# El motor unificado puede clasificar "agéndame una cita para" como needs_clarification;
# en ese caso debemos crear una pending mínima de calendario.
_CALENDAR_INTENT_WORDS: tuple[str, ...] = (
    "cita",
    "citame",
    "agenda",
    "agendame",
    "agendamela",
    "agendar",
    "reunion",
    "evento",
    "encuentro",
    "programa",
    "programame",
    "programar",
    "anotame una cita",
    "anota una cita",
    "guardame una cita",
    "guarda una cita",
    "apuntame una cita",
    "apunta una cita",
)


def _looks_like_calendar_intent(text: str) -> bool:
    if not text:
        return False
    t = _strip_accents(text.lower())
    t = re.sub(r"[^\w\s]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return False
    return any(w in t for w in _CALENDAR_INTENT_WORDS)


# v0.21.4b — Patrones simples para extraer fecha/hora en el fallback local.
_DAY_HINTS_RE = re.compile(
    r"(?:^|\W)((?:el|este|esta|para\s+(?:el|la))\s+)?"
    r"(hoy|ma[nñ]ana|pasado\s+ma[nñ]ana|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)"
    r"(?=\W|$)",
    flags=re.IGNORECASE,
)
_TIME_HINTS_RE = re.compile(
    r"\ba\s+las?\s+(\d{1,2})(?:[:.](\d{2}))?\b",
    flags=re.IGNORECASE,
)


def _parse_time_text_hh_mm(time_text: str) -> tuple[int, int] | None:
    """Parsea 'H', 'H:MM', 'HH:MM' a enteros; None si no coincide."""
    s = (time_text or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return h, mi
        return None
    m = re.match(r"^(\d{1,2})$", s)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            return h, 0
    return None


def _raw_calendar_time_period_explicit(raw: str) -> bool:
    """True si hay indicación inequívoca de mañana/tarde/noche o am/pm (v0.44.2)."""
    ru = _strip_accents((raw or "").lower())
    if re.search(r"(de la|por la)\s+ma[nñ]ana\b", ru):
        return True
    if any(
        x in ru
        for x in (
            "esta tarde",
            "por la tarde",
            "de la tarde",
            "esta noche",
            "por la noche",
            "de la noche",
            "medianoche",
        )
    ):
        return True
    if re.search(r"\b\d{1,2}\s*[:.]\s*\d{2}\s*(am|pm|a[\s.]?m[\s.]?|p[\s.]?m[\s.]?)\b", ru):
        return True
    return False


def _coerce_ambiguous_calendar_time_text(raw: str, time_text: str) -> str:
    """v0.44.2 — Corrige inferencias +12 o 7→14 cuando el literal del usuario es claro.

    Sin periodo explícito (mañana/tarde/noche/am/pm), si el modelo devuelve
    mh == lh + 12 con lh ≤ 11, se conserva lh y los minutos del modelo.

    También corrige el bug habitual «a las siete» → 14:00 en el modelo.
    """
    tt = (time_text or "").strip()
    if not tt:
        return tt
    m_time = _TIME_HINTS_RE.search(raw or "")
    if not m_time:
        return tt
    if _raw_calendar_time_period_explicit(raw or ""):
        return tt

    lh = int(m_time.group(1))
    try:
        lmm = int(m_time.group(2) or "00")
    except ValueError:
        lmm = 0
    lmm = max(0, min(59, lmm))

    if lh >= 12:
        return tt

    parsed = _parse_time_text_hh_mm(tt)
    if not parsed:
        return tt
    mh, mm = parsed

    if mh == lh + 12:
        return f"{lh:02d}:{mm:02d}"
    # Modelo suele equivocarse con las siete y entregar 14:00 (sin ser +12 desde 14h).
    if lh == 7 and mh == 14:
        return f"07:{mm:02d}"
    return tt


def _coerce_calendar_time_twice_sources(
    current_reply: str, original_turn: str, time_text: str
) -> str:
    """Aplica corrección ante turno actual y ante el texto original que abrió el pending."""
    tt = _coerce_ambiguous_calendar_time_text(current_reply or "", time_text)
    return _coerce_ambiguous_calendar_time_text(original_turn or "", tt)


def _calendar_time_text_after_user_message(raw: str, time_val: Any) -> Any:
    """Aplica v0.44.2 a un time_text opcional antes de pending/persistencia."""
    if time_val is None:
        return None
    s = str(time_val).strip()
    if not s:
        return None
    return _coerce_ambiguous_calendar_time_text(raw or "", s)


# v0.21.4c — Detección estricta: el usuario quiere agendar PERO no aporta datos.
# Sirve para interceptar antes del motor unificado y no perder la intención si
# GPT clasifica el mensaje como general_query o pregunta de aclaración.
_CALENDAR_ACTION_VERBS: tuple[str, ...] = (
    "agenda",
    "agendame",
    "agendamela",
    "agendamelo",
    "agendar",
    "anota",
    "anotame",
    "apunta",
    "apuntame",
    "guarda",
    "guardame",
    "programa",
    "programame",
    "programar",
    "ponme",
    "ponme una",
    "metele",
)
_CALENDAR_NOUNS: tuple[str, ...] = (
    "cita",
    "reunion",
    "evento",
    "encuentro",
    "agenda",
)


def _looks_like_calendar_action(text: str) -> bool:
    """Más estricto que `_looks_like_calendar_intent`: requiere verbo + sustantivo
    o un verbo específico de agenda (agéndame/agendar)."""
    if not text:
        return False
    t = _strip_accents(text.lower())
    t = re.sub(r"[^\w\s]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return False
    tokens = t.split()
    if not tokens:
        return False
    # Verbo de agendar por sí solo es suficiente.
    if any(tok.startswith("agenda") or tok.startswith("agendam") for tok in tokens):
        return True
    if any(tok in ("agendar", "agendalo", "agendamela", "agendamelo") for tok in tokens):
        return True
    if any(tok.startswith("programa") for tok in tokens) and any(n in t for n in _CALENDAR_NOUNS):
        return True
    # Verbo de guardar/anotar/apuntar + sustantivo de calendario.
    short_verbs = ("anota", "anotame", "apunta", "apuntame", "guarda", "guardame", "ponme", "metele")
    if any(tok in short_verbs or tok.startswith("anotam") or tok.startswith("apuntam") or tok.startswith("guardam") for tok in tokens):
        if any(n in t for n in _CALENDAR_NOUNS):
            return True
    return False


def _is_bare_calendar_intent(text: str) -> bool:
    """True si el mensaje es claramente «agéndame una cita» (sin fecha, hora, persona ni lugar).

    v0.21.10 — También acepta sustantivos funcionales aislados ("cita",
    "una cita", "evento", "reunión") sin verbo.
    """
    raw = text or ""
    # Pista de fecha/hora/con/en → ya no es bare.
    if _DAY_HINTS_RE.search(raw) or _TIME_HINTS_RE.search(raw):
        return False
    if re.search(r"\bcon\s+\S", raw, flags=re.IGNORECASE):
        return False
    if re.search(r"\ben\s+\S", raw, flags=re.IGNORECASE):
        return False
    if _looks_like_calendar_action(raw):
        return True
    # v0.21.10 — sustantivo desnudo "cita"/"evento"/"reunión"/"encuentro".
    return _bare_intent_kind(raw) == "calendar"


# ---------------------------------------------------------------------------
# v0.21.4d — Detección de intención de NOTA en mensajes mínimos / vagos.
#
# Sirve para abrir una pending_action de nota cuando el usuario solo dice
# "quiero una nota" / "apúntame una nota" sin contenido. No pisa la detección
# de calendario: solo se evalúa después.
# ---------------------------------------------------------------------------

_NOTE_ACTION_VERBS: tuple[str, ...] = (
    "anota",
    "anotame",
    "apunta",
    "apuntame",
    "guarda",
    "guardame",
    "crea",
    "creame",
    "haz",
    "hazme",
    "registra",
    "registrame",
    "quiero",
    "quisiera",
    "necesito",
    "ponme",
    "anademe",
    "añademe",
    "anade",
    "añade",
)
_NOTE_NOUNS: tuple[str, ...] = ("nota", "notita", "apunte", "anotacion")

# v0.21.10 — Sustantivos funcionales aislados que disparan bare intent
# aunque NO haya verbo ("nota" sola, "cita" sola, "tarea" sola). El
# usuario expresa intención pero no aporta contenido.
_BARE_NOTE_NOUNS_STRICT: tuple[str, ...] = (
    "nota",
    "notita",
    "apunte",
    "anotacion",
)
_BARE_CALENDAR_NOUNS_STRICT: tuple[str, ...] = (
    "cita",
    "reunion",
    "evento",
    "encuentro",
)
_BARE_TASK_NOUNS_STRICT: tuple[str, ...] = (
    "tarea",
    "tareita",
    "pendiente",
)
# Verbos opcionales tolerados delante del sustantivo en una intención
# "bare" (mensaje sin contenido). El usuario puede decir "quiero una
# tarea" o "crear nota" o simplemente "nota": todo eso queda como bare.
_BARE_INTENT_VERBS: tuple[str, ...] = (
    "quiero",
    "quisiera",
    "necesito",
    "crear",
    "crea",
    "creame",
    "haz",
    "hazme",
    "hacer",
    "anota",
    "anotame",
    "apunta",
    "apuntame",
    "guarda",
    "guardame",
    "registra",
    "registrame",
    "ponme",
    "agenda",
    "agendame",
    "agendamela",
    "agendamelo",
    "agendar",
    "programa",
    "programame",
    "programar",
    "poner",
    "pon",
    "pongo",
    "pongame",
    "ponemela",
    "ponemelo",
    "fija",
    "fijame",
    "fijar",
    "establece",
    "establecer",
    "establezca",
    "coloca",
    "colocame",
    "colocar",
    "mete",
    "meter",
    "meteme",
)
# Tokens "funcionales" tolerados (artículos, demostrativos, conectores).
_BARE_INTENT_FILLER: frozenset[str] = frozenset({
    "una", "un", "la", "el", "las", "los",
    "esa", "ese", "esta", "este", "esto",
    "por", "favor", "porfavor", "porfa",
    "me", "te", "nos", "os", "se",
    "que",
})


def _normalize_for_bare(text: str) -> list[str]:
    """Tokeniza el texto sin acentos, sin puntuación, en minúsculas."""
    t = _strip_accents((text or "").lower())
    t = re.sub(r"[^\w\s]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.split() if t else []


def _bare_intent_kind(text: str) -> str | None:
    """v0.21.10 — Si el mensaje es una **intención bare** (sustantivo
    funcional aislado, opcionalmente precedido por un verbo de creación y
    rellenos como "una", "por favor"…), devuelve el `kind` detectado:

    - ``"note"`` para nota/notita/apunte/anotacion
    - ``"calendar"`` para cita/reunion/evento/encuentro
    - ``"task"`` para tarea/pendiente

    Devuelve ``None`` si no es bare o si hay contenido real más allá del
    sustantivo (entonces lo gestiona el motor unificado).
    """
    tokens = _normalize_for_bare(text)
    if not tokens or len(tokens) > 5:
        return None

    found_kind: str | None = None
    found_idx: int | None = None
    for i, tok in enumerate(tokens):
        if tok in _BARE_NOTE_NOUNS_STRICT:
            kind = "note"
        elif tok in _BARE_CALENDAR_NOUNS_STRICT:
            kind = "calendar"
        elif tok in _BARE_TASK_NOUNS_STRICT:
            kind = "task"
        else:
            continue
        # Solo aceptamos UNA pista de sustantivo funcional. Si aparecen
        # dos kinds distintos en el mismo mensaje no es bare.
        if found_kind and kind != found_kind:
            return None
        found_kind = kind
        found_idx = i

    if found_kind is None or found_idx is None:
        return None

    # El resto de tokens debe ser ruido funcional (verbo de creación,
    # artículos, rellenos). Si hay algo "de contenido" (un sustantivo
    # ajeno o un tema), NO es bare.
    for j, tok in enumerate(tokens):
        if j == found_idx:
            continue
        if tok in _BARE_INTENT_FILLER:
            continue
        if tok in _BARE_INTENT_VERBS:
            continue
        if tok.startswith("anotam") or tok.startswith("apuntam"):
            continue
        if tok.startswith("guardam") or tok.startswith("registram"):
            continue
        if tok.startswith("agend"):
            continue
        if tok.startswith("program"):
            continue
        # Token "de contenido" → no es bare.
        return None

    return found_kind


def _looks_like_note_action(text: str) -> bool:
    if not text:
        return False
    t = _strip_accents(text.lower())
    t = re.sub(r"[^\w\s]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return False
    tokens = t.split()
    if not tokens:
        return False
    if not any(n in t for n in _NOTE_NOUNS):
        return False
    if any(
        tok in _NOTE_ACTION_VERBS
        or tok.startswith("anotam")
        or tok.startswith("apuntam")
        or tok.startswith("guardam")
        or tok.startswith("creame")
        or tok.startswith("registram")
        for tok in tokens
    ):
        return True
    return False


# v0.21.4d — Frases que indican que el usuario solo está dando un TEMA, no contenido.
_NOTE_TOPIC_PREFIXES: tuple[str, ...] = (
    "una reflexion sobre",
    "una reflexion acerca de",
    "una idea sobre",
    "una idea acerca de",
    "algo sobre",
    "algo acerca de",
    "una nota sobre",
    "una nota acerca de",
    "un apunte sobre",
    "un apunte acerca de",
    "sobre el tema de",
    "sobre el tema",
    "tema:",
    "titulo:",
    "el titulo es",
)
_NOTE_EXPLICIT_TITLE_RE = re.compile(
    r"\bt[ií]tulo\s*[:\-]\s*(.+?)(?:[\.,;]\s*contenido\s*[:\-]\s*(.+))?$",
    flags=re.IGNORECASE,
)
_NOTE_EXPLICIT_CONTENT_RE = re.compile(
    r"\bcontenido\s*[:\-]\s*(.+)$",
    flags=re.IGNORECASE,
)


def _is_bare_note_intent(text: str) -> bool:
    """True si el mensaje es claramente "quiero una nota" sin contenido.

    v0.21.10 — También acepta sustantivos funcionales aislados ("nota",
    "una nota", "apunte", "anotación") sin verbo.
    """
    raw = (text or "").strip()
    norm = _strip_accents(raw.lower())
    norm = re.sub(r"[^\w\s]+", " ", norm)
    norm = re.sub(r"\s+", " ", norm).strip()
    if not norm:
        return False
    if _looks_like_note_action(text):
        tokens = norm.split()
        # Mensajes "vacíos" como: "quiero una nota", "crea una nota",
        # "apuntame una nota".
        if len(tokens) <= 5:
            return True
        # Si el usuario añade "sobre" / "acerca de" / "que…", entonces ya
        # aporta tema o contenido: lo maneja el motor estructurado.
        if any(
            k in norm for k in (" sobre ", " acerca ", " que ", " donde ", " cuando ")
        ):
            return False
        return True
    # v0.21.10 — sustantivo desnudo "nota"/"apunte"/"anotacion" sin verbo.
    return _bare_intent_kind(raw) == "note"


def _is_bare_task_intent(text: str) -> bool:
    """v0.21.10 — True si el mensaje es claramente intención mínima de tarea
    ("tarea", "una tarea", "crear tarea", "quiero una tarea", "pendiente")
    sin título.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    norm = _strip_accents(raw.lower())
    norm = re.sub(r"[^\w\s]+", " ", norm)
    norm = re.sub(r"\s+", " ", norm).strip()
    if not norm:
        return False
    # Si el usuario aporta tema/título ("una tarea sobre X", "crear tarea X")
    # NO es bare: lo maneja el motor estructurado.
    if any(
        k in norm for k in (" sobre ", " acerca ", " que ", " donde ", " cuando ")
    ):
        return False
    return _bare_intent_kind(raw) == "task"


# ---------------------------------------------------------------------------
# v0.21.5b — Detección de "respuesta a revisión de duplicados".
#
# Cuando ARIS acaba de avisar de duplicados o solapamientos en la agenda y
# preguntó si revisarlos, la siguiente respuesta del usuario suele ser una
# DECISIÓN sobre qué mantener/borrar. No debe interpretarse como
# update_calendar_event ni provocar modificaciones automáticas: por ahora
# v0.21.5 no implementa borrado/fusión confirmado.
# ---------------------------------------------------------------------------

_DUP_REVIEW_REPLY_PATTERNS: tuple[str, ...] = (
    r"\bmant[eé]n\b",
    r"\bmantengamos\b",
    r"\bd[eé]jate?\s+solo\b",
    r"\bd[eé]jame\s+solo\b",
    r"\bdeja\s+solo\b",
    r"\bquita\s+(?:los?\s+)?duplicad",
    r"\belimina\s+(?:los?\s+)?duplicad",
    r"\bborra\s+(?:los?\s+)?duplicad",
    r"\bquita\s+(?:los?\s+)?repetid",
    r"\belimina\s+(?:los?\s+)?repetid",
    r"\bborra\s+(?:los?\s+)?repetid",
    r"\bfusiona\b",
    r"\bunifica\b",
    r"\breestructura\b",
    r"\bordena\b",
    r"\brevisemos\b",
    r"\brev[ií]salo\b",
    r"\blimpia\b",
    r"\bquedate?\s+con\b",
    r"\bqu[eé]date?\s+con\b",
    r"\bhazlo\b",
    r"\badelante\b",
    r"\bs[ií]\s+(?:adelante|hazlo|hagamos|por\s+favor|por\s+supuesto)\b",
)
_DUP_REVIEW_REPLY_RE = re.compile(
    "|".join(_DUP_REVIEW_REPLY_PATTERNS),
    flags=re.IGNORECASE,
)


def _is_duplicate_review_reply(text: str) -> bool:
    """True si el mensaje parece una decisión sobre duplicados/conflictos pendientes."""
    raw = (text or "").strip()
    if not raw:
        return False
    norm = _strip_accents(raw.lower())
    return bool(_DUP_REVIEW_REPLY_RE.search(norm))


def _is_agenda_followup_message(text: str) -> bool:
    """True si el mensaje parece pedir reestructurar/resumir/aclarar la última respuesta de agenda."""
    raw = (text or "").strip()
    if not raw:
        return False
    norm = _strip_accents(raw.lower())
    norm = re.sub(r"[^\w\s]+", " ", norm)
    norm = re.sub(r"\s+", " ", norm).strip()
    if not norm:
        return False

    for phrase in _AGENDA_FOLLOWUP_PHRASES:
        if phrase in norm:
            return True

    tokens = norm.split()
    if not tokens:
        return False
    # Mensajes cortos (1–4 palabras) suelen ser follow-ups; igualmente comprobamos por prefijos.
    for tok in tokens:
        for pref in _AGENDA_FOLLOWUP_TOKEN_PREFIXES:
            if tok.startswith(pref):
                return True
    return False


class AssistantEngine:
    """Reglas locales guardan directo; OpenAI sugiere acciones con confirmación vía pending_action."""

    _KW_NOTA = ("nota", "apunta", "guarda", "guardar")
    _KW_TAREA = ("tarea", "recuérdame", "pendiente")
    _KW_CALENDARIO = ("cita", "calendario", "evento", "reunión")

    _CONSULTA_LOCAL = (
        "He entendido tu consulta. Más adelante la conectaré con el núcleo de IA."
    )

    _ORDERED_DAY_HINTS = (
        "pasado manana",
        "manana",
        "hoy",
        "lunes",
        "martes",
        "miercoles",
        "jueves",
        "viernes",
        "sabado",
        "domingo",
    )

    def __init__(
        self,
        pending_store: PendingActionStore,
        focus_store: FocusStore | None = None,
        tasks_store: TasksStore | None = None,
        notes_store: NotesStore | None = None,
    ) -> None:
        # v0.21.9 — Foco operativo multi-entidad y referencias a stores de
        # tareas/notas para que el motor pueda actualizar entidades existentes
        # (p. ej. añadir `description` a una tarea recién creada).
        self._pending = pending_store
        self._events = EventsStore()
        self._focus = focus_store if focus_store is not None else FocusStore()
        self._tasks = tasks_store if tasks_store is not None else TasksStore()
        self._notes = notes_store if notes_store is not None else NotesStore()

    # ------------------------------------------------------------------
    # v0.21.9 — Foco operativo multi-entidad.
    # ------------------------------------------------------------------

    def note_entity_persisted(
        self,
        kind: str,
        entity_id: str,
        label: str | None = None,
        operation: str | None = None,
    ) -> None:
        """Hook público para que el dispatcher externo (main.py) registre la
        última entidad persistida como foco operativo.

        Se invoca después de `tasks_store.add_task`, `notes_store.add_note` o
        `events_store.add_event` con el ID real. Si `kind` no es válido o
        falta `entity_id`, no hace nada.
        """
        try:
            self._focus.set_focus(
                kind=kind,
                entity_id=entity_id,
                label=label,
                operation=operation,
                user_id=DEFAULT_USER_ID,
            )
            logger.info(
                "v0.21.9 focus actualizado: kind=%s id=%s label=%r op=%s",
                kind,
                str(entity_id)[:8],
                (label or "")[:40],
                operation,
            )
        except Exception:
            logger.exception("note_entity_persisted: fallo al actualizar focus")

    def _current_focus(self) -> dict[str, Any]:
        """Atajo: devuelve el foco operativo actual (dict, nunca None)."""
        try:
            return self._focus.get_focus(user_id=DEFAULT_USER_ID)
        except Exception:
            logger.exception("get_focus falló; devuelvo foco vacío")
            return {
                "user_id": DEFAULT_USER_ID,
                "last_focused_kind": None,
                "last_focused_id": None,
                "last_focused_label": None,
                "last_operation": None,
                "last_focused_at": None,
            }

    # Heurísticas locales para enrutar mensajes pronominales/contextuales.

    _TASK_NOTE_MENTION_RE = re.compile(
        r"\b(tareas?|notas?)\b",
        flags=re.IGNORECASE,
    )

    _CALENDAR_MENTION_RE = re.compile(
        r"\b(evento|eventos|cita|citas|reuni[oó]n|reuniones|calendario|agenda)\b",
        flags=re.IGNORECASE,
    )

    # «ponle contenido», «ponerle contenido», «añade descripción»,
    # «agrégale información», «incluye texto», etc.
    # Nota: los textos se normalizan con `_strip_accents` antes de aplicar
    # estos regex, por eso aquí solo aparecen caracteres ASCII.
    _CONTENT_REQUEST_RE = re.compile(
        r"\b(?:pon|poner|pongal|anad|agreg|incluy|complet|describ)"
        r"[a-z]*"  # cola flexible: -er, -le, -amos, …
        r"\s+"
        r"(?:el\s+|la\s+|un\s+|una\s+|mas\s+|con\s+|algun\s+|le\s+)?"
        r"(?:contenido|descripcion|texto|detalles?|info(?:rmacion)?|notas?)\b",
        flags=re.IGNORECASE,
    )

    _CONTENT_LACK_RE = re.compile(
        r"\b(?:le\s+falta|necesita|no\s+tiene|falta(?:n|le)?)\s+"
        r"(?:mas\s+|algun\s+|un\s+|el\s+|la\s+)?"
        r"(?:contenido|descripcion|texto|detalles?|info(?:rmacion)?)\b",
        flags=re.IGNORECASE,
    )

    # «no es a la cita, es a la tarea», «eso era para la tarea», «es a la nota».
    # El grupo final captura el destino real ("tarea"/"nota") para que el
    # enrutado funcione aunque la frase también mencione "cita/evento".
    _REASSIGN_TO_TASK_NOTE_RE = re.compile(
        r"\b(?:es|era|va|son|eran|van)\s+"
        r"(?:para|a|al|del|de)\s+"
        r"(?:la|el|las|los)?\s*"
        r"(tareas?|notas?)\b",
        flags=re.IGNORECASE,
    )

    def _mentions_calendar_word(self, raw: str) -> bool:
        return bool(self._CALENDAR_MENTION_RE.search(raw or ""))

    def _mentions_task_or_note_only(self, raw: str) -> bool:
        """True si el mensaje menciona explícitamente "tarea"/"nota" pero NO
        menciona "evento/cita/reunión/calendario/agenda"."""
        text = raw or ""
        if not self._TASK_NOTE_MENTION_RE.search(text):
            return False
        return not self._CALENDAR_MENTION_RE.search(text)

    def _mentions_task_only(self, raw: str) -> bool:
        if not re.search(r"\btareas?\b", raw or "", flags=re.IGNORECASE):
            return False
        return not self._CALENDAR_MENTION_RE.search(raw or "")

    def _mentions_note_only(self, raw: str) -> bool:
        if not re.search(r"\bnotas?\b", raw or "", flags=re.IGNORECASE):
            return False
        return not self._CALENDAR_MENTION_RE.search(raw or "")

    def _is_pronominal_content_request(self, raw: str) -> bool:
        """True si el usuario pide que se añada/complete contenido o
        descripción a "lo último". Ej.: "ponle contenido", "añade descripción",
        "le falta contenido", "tienes que ponerle contenido"."""
        text = _strip_accents((raw or "").lower())
        if self._CONTENT_REQUEST_RE.search(text):
            return True
        if self._CONTENT_LACK_RE.search(text):
            return True
        return False

    def _is_reassign_to_task_or_note(self, raw: str) -> bool:
        """True si el usuario aclara que el contexto era una tarea/nota
        ("no es a la cita, es a la tarea")."""
        return bool(self._REASSIGN_TO_TASK_NOTE_RE.search(raw or ""))

    def _reassign_destination(self, raw: str) -> str | None:
        """Devuelve "task"/"note" si la frase reasigna a tarea/nota; None si no.

        Se queda con la ÚLTIMA aparición de la regla (la más cercana al final
        del mensaje), para casos como "no es a la cita, es a la tarea" donde
        el destino real es "tarea"."""
        matches = list(self._REASSIGN_TO_TASK_NOTE_RE.finditer(raw or ""))
        if not matches:
            return None
        last = matches[-1].group(1).lower()
        if last.startswith("tarea"):
            return "task"
        if last.startswith("nota"):
            return "note"
        return None

    def _maybe_route_by_focus(
        self, raw: str
    ) -> tuple[str, str, str | dict | None, str | None] | None:
        """v0.21.9 — Enrutado por foco operativo multi-entidad.

        Tres entradas que se manejan aquí (cuando NO hay pending_action y antes
        del motor unificado):

        a) "ponle contenido / añade descripción" + foco==task: abrimos pending
           de descripción de tarea sobre la tarea focalizada.
        b) "no es a la cita, es a la tarea / es a la nota": el usuario corrige
           el destinatario explícitamente; redirigimos al foco de tarea/nota.
        c) Mención explícita y exclusiva de "tarea/nota" (sin "evento/cita"):
           si hay foco de ese kind, evitamos que el motor unificado lo
           interprete como update_calendar_event.

        Devuelve `None` si no aplica.
        """
        focus = self._current_focus()
        kind = focus.get("last_focused_kind")
        eid = focus.get("last_focused_id")
        label = (focus.get("last_focused_label") or "").strip()

        # Caso a) — Pronominal de contenido sobre la última entidad.
        if self._is_pronominal_content_request(raw):
            if kind == "task" and eid:
                task = self._tasks.get_task_by_id(str(eid))
                title = (task.get("title") if task else label) or label or "tarea"
                logger.info(
                    "v0.21.9 focus route: pronominal content sobre tarea %s",
                    str(eid)[:8],
                )
                return self._open_task_description_pending(raw, str(eid), title)
            if kind == "note" and eid:
                # Notas ya tienen content; el flujo de "añade contenido a la
                # nota" se documenta como pendiente (no se implementa aquí).
                logger.info(
                    "v0.21.9 focus route: pronominal content sobre nota %s "
                    "(no implementado, derivo a aclaración)",
                    str(eid)[:8],
                )
                return (
                    f"La nota «{label or 'reciente'}» ya tiene contenido. "
                    "¿Quieres que abra una nota nueva con ese texto?",
                    "consulta",
                    None,
                    None,
                )
            # Si no hay foco de tarea/nota, dejamos que el flujo normal siga.

        # Caso b) — Reasignación explícita "es a la tarea / es a la nota".
        # Tomamos como destino la ÚLTIMA mención reasignada, para frases
        # como "no es a la cita, es a la tarea" (destino real = "tarea").
        dest = self._reassign_destination(raw)
        if dest == "task":
            if kind == "task" and eid:
                task = self._tasks.get_task_by_id(str(eid))
                title = (task.get("title") if task else label) or label or "tarea"
                logger.info(
                    "v0.21.9 focus route: reassign → tarea %s",
                    str(eid)[:8],
                )
                return self._open_task_description_pending(raw, str(eid), title)
            logger.info("v0.21.9 focus route: reassign → tarea pero sin foco")
            return (
                "No tengo una tarea reciente clara. ¿A qué tarea te refieres?",
                "consulta",
                None,
                None,
            )
        if dest == "note":
            if kind == "note" and eid:
                logger.info(
                    "v0.21.9 focus route: reassign → nota %s",
                    str(eid)[:8],
                )
                return (
                    f"De acuerdo, lo aplico a la nota «{label or 'reciente'}». "
                    "¿Qué quieres añadir?",
                    "consulta",
                    None,
                    None,
                )
            return (
                "No tengo una nota reciente clara. ¿A qué nota te refieres?",
                "consulta",
                None,
                None,
            )

        # Caso c) — Mención explícita de "tarea/nota" sin mención de calendario.
        if self._mentions_task_or_note_only(raw):
            if self._mentions_task_only(raw) and kind == "task" and eid:
                task = self._tasks.get_task_by_id(str(eid))
                title = (task.get("title") if task else label) or label or "tarea"
                logger.info(
                    "v0.21.9 focus route: mención exclusiva de tarea → foco tarea %s",
                    str(eid)[:8],
                )
                return self._open_task_description_pending(raw, str(eid), title)
            # Si no hay foco coincidente, NO bloqueamos aquí; lo gestiona
            # _unified_handle_calendar_update con su propio guard.

        return None

    def _display_time_text(self, time_text: Any, raw_user: str) -> str | None:
        """Hora para respuesta al usuario (v0.44.2 — sin +12 solo por «a las N»).

        Solo se ajusta a tarde si el mensaje indica explícitamente tarde/noche;
        «de la mañana» conserva 01–11 como reloj civil.
        La coerción ante modelos que devuelven H+12 está en
        `_coerce_ambiguous_calendar_time_text` al persistir.
        """
        if time_text is None:
            return None
        s = str(time_text).strip()
        if not s:
            return None
        m = re.match(r"^(\d{1,2}):(\d{2})$", s)
        if not m:
            return s
        h = int(m.group(1))
        mi = m.group(2)
        ru = _strip_accents((raw_user or "").lower())
        if 1 <= h <= 11:
            if re.search(r"(de la|por la) ma[nñ]ana", ru):
                return f"{h:02d}:{mi}"
            if any(
                x in ru
                for x in (
                    " esta tarde",
                    "esta tarde",
                    "por la tarde",
                    " de la tarde",
                    "de la tarde",
                    " esta noche",
                    "esta noche",
                    " de la noche",
                    "de la noche",
                    "medianoche",
                )
            ):
                return f"{h + 12}:{mi}"
        return s

    def _saved_calendar_ack(self, payload: dict[str, Any], raw: str) -> str:
        title = str(payload.get("title") or "Evento").strip()
        title_norm = _strip_accents(title.lower())
        date_t = str(payload.get("date_text") or "").strip()
        tt_disp = self._display_time_text(payload.get("time_text"), raw)
        loc = payload.get("location")
        loc_s = str(loc).strip() if loc else ""
        parts: list[str] = [f"He guardado el evento «{title}»"]
        if date_t:
            parts.append(f"para {date_t}")
        if tt_disp:
            parts.append(f"a las {tt_disp}")
        elif payload.get("time_text"):
            parts.append(f"a las {payload.get('time_text')}")
        # v0.21.7c — no duplicar lugar si ya está en el título.
        if loc_s:
            comparator = self._strip_location_article(loc_s) or loc_s
            if _strip_accents(comparator.lower()) not in title_norm:
                parts.append(f"en {loc_s}")
        # v0.21.11 — participantes deduplicados (con la misma lógica de
        # v0.21.7c): si todos aparecen ya en el título, no repetir.
        pp = payload.get("participants")
        has_p = isinstance(pp, list) and len(pp) > 0
        remaining_names: list[str] = []
        if has_p:
            names = [str(p).strip() for p in pp if p and str(p).strip()]
            remaining_names = [
                n for n in names if _strip_accents(n.lower()) not in title_norm
            ]
            if remaining_names:
                if len(remaining_names) == 1:
                    parts.append(f"con {remaining_names[0]}")
                else:
                    parts.append(
                        "con "
                        + ", ".join(remaining_names[:-1])
                        + f" y {remaining_names[-1]}"
                    )
        msg = " ".join(parts) + "."
        if date_t and (tt_disp or payload.get("time_text")):
            add: list[str] = []
            if not has_p:
                add.append("No tengo guardado con quién es.")
            if not loc_s:
                add.append("No tengo guardado el lugar.")
            if add:
                msg += " " + " ".join(add)
        return msg

    def _updated_event_ack(self, event: dict[str, Any], raw: str) -> str:
        # v0.21.7c — usamos un summary que no repite participantes ni lugar
        # cuando ya aparecen en el título, evitando "cita con Luis ... con Luis".
        s = self._format_event_summary_dedup(event)
        return f"He actualizado el evento: {s}."

    def _format_event_summary_dedup(self, event: dict[str, Any]) -> str:
        """Como `EventsStore.format_event_summary`, pero filtra participantes y
        lugar que ya aparecen literalmente en el título. v0.21.7c."""
        title = str(event.get("title") or "").strip() or "evento"
        title_norm = _strip_accents(title.lower())
        parts: list[str] = [title]
        if event.get("date_text"):
            parts.append(str(event.get("date_text")).strip())
        tt = event.get("time_text")
        if tt:
            parts.append(f"a las {str(tt).strip()}")
        loc = event.get("location")
        if loc:
            loc_s = str(loc).strip()
            loc_clean = self._strip_location_article(loc_s)
            comparator = loc_clean or loc_s
            if comparator and _strip_accents(comparator.lower()) not in title_norm:
                parts.append(f"en {loc_s}")
        pp = event.get("participants")
        if isinstance(pp, list) and pp:
            names = [str(p).strip() for p in pp if p and str(p).strip()]
            remaining = [
                n for n in names if _strip_accents(n.lower()) not in title_norm
            ]
            if remaining:
                parts.append(f"con {', '.join(remaining)}")
        if len(parts) == 1:
            return title
        return f"{parts[0]} {' '.join(parts[1:])}".strip()

    @staticmethod
    def _title_contains_all_names(title: str, names: list[Any]) -> bool:
        if not names:
            return False
        t = _strip_accents((title or "").lower())
        return all(
            _strip_accents(str(n).strip().lower()) in t
            for n in names
            if str(n).strip()
        )

    def _references_last_event(self, raw: str) -> bool:
        t = _strip_accents((raw or "").lower())
        patterns = (
            r"\b(la|lo)\b.{0,40}guardad",
            r"has guardad",
            r"acabas de",
            r"lo de antes",
            r"lo que acabas",
            r"ese evento",
            r"esa cita",
            r"ultimo evento",
            r"ultima cita",
        )
        return any(re.search(p, t) for p in patterns)

    def _agenda_question_axis(self, raw: str) -> str:
        t = _strip_accents((raw or "").lower())
        if re.search(r"donde", t):
            return "lugar"
        if re.search(r"a que hora|que hora", t):
            return "hora"
        if re.search(r"cuando", t):
            return "cuando"
        return "general"

    def _day_hints_in_message(self, raw: str) -> list[str]:
        t = _strip_accents((raw or "").lower()).replace("ñ", "n")
        found: list[str] = []
        for ph in self._ORDERED_DAY_HINTS:
            if ph in t:
                found.append(ph)
        return found

    def _day_hint_display(self, hint: str) -> str:
        h = hint.strip().lower()
        mapping = {
            "manana": "mañana",
            "pasado manana": "pasado mañana",
            "miercoles": "miércoles",
            "sabado": "sábado",
        }
        return mapping.get(h, hint)

    def _event_matches_day_hint(self, ev: dict[str, Any], hint: str) -> bool:
        hn = EventsStore._normalize_search_text(hint.replace("ñ", "n"))
        if not hn:
            return False
        for key in ("date_text", "source_text", "title", "time_text"):
            val = ev.get(key)
            if not isinstance(val, str):
                continue
            blob = EventsStore._normalize_search_text(val.replace("ñ", "n"))
            if hn in blob:
                return True
        return False

    def _is_day_scope_question(self, raw: str) -> bool:
        t = _strip_accents((raw or "").lower())
        return bool(re.search(r"que tengo|tengo algo", t)) and bool(
            self._day_hints_in_message(raw)
        )

    def _is_agenda_overview_question(self, raw: str) -> bool:
        t = _strip_accents((raw or "").lower())
        if "proxima cita" in t:
            return True
        if "hay en mi agenda" in t:
            return True
        if "que hay en mi agenda" in t:
            return True
        if "en mi agenda" in t and re.search(r"que hay|que tengo", t):
            return True
        return False

    def _agenda_line_for_calendar(self, ev: dict[str, Any], raw: str) -> str:
        title = str(ev.get("title") or "Evento").strip()
        tt_raw = ev.get("time_text")
        tt = self._display_time_text(tt_raw, raw) if tt_raw else None
        if tt:
            return f"{title} a las {tt}"
        return title

    def _agenda_reply_day_list(
        self, raw: str, matched: list[dict[str, Any]], day_label: str
    ) -> str:
        if not matched:
            return (
                f"Para {day_label} no tienes eventos anotados en la agenda local."
            )
        lines = [self._agenda_line_for_calendar(ev, raw) for ev in matched]
        return f"Para {day_label} tienes: " + "; ".join(lines) + "."

    def _agenda_reply_overview(self, events: list[dict[str, Any]], raw: str) -> str:
        if not events:
            return "No tienes eventos guardados en la agenda local."
        tail = events[-5:]
        lines = [self._agenda_line_for_calendar(ev, raw) for ev in tail]
        return "En tu agenda local: " + "; ".join(lines) + "."

    def _agenda_search_query_from_text(self, raw: str) -> str:
        return (raw or "").strip()

    def _agenda_reply_multiple_clarify(self, matches: list[dict[str, Any]]) -> str:
        titles = [
            f"«{str(m.get('title') or 'Evento').strip()}»" for m in matches[:6]
        ]
        return (
            "He encontrado varios eventos que podrían encajar: "
            + ", ".join(titles)
            + ". ¿A cuál te refieres?"
        )

    def _agenda_reply_single(
        self, raw: str, ev: dict[str, Any], *, last_ref: bool
    ) -> str:
        title = str(ev.get("title") or "Evento").strip()
        date_t = str(ev.get("date_text") or "").strip()
        loc = ev.get("location")
        loc_s = str(loc).strip() if loc else ""
        tt_raw = ev.get("time_text")
        tt = self._display_time_text(tt_raw, raw) if tt_raw else None
        axis = self._agenda_question_axis(raw)

        if last_ref:
            if axis == "hora":
                parts = ["La he guardado"]
                if date_t:
                    parts.append(f"para {date_t}")
                if tt:
                    parts.append(f"a las {tt}")
                elif tt_raw:
                    parts.append(f"a las {tt_raw}")
                return " ".join(parts) + "."
            parts = ["La he guardado"]
            if date_t:
                parts.append(f"para {date_t}")
            if tt:
                parts.append(f"a las {tt}")
            elif tt_raw:
                parts.append(f"a las {tt_raw}")
            if loc_s:
                parts.append(f"en {loc_s}")
            return " ".join(parts) + "."

        if axis == "lugar":
            if not loc_s:
                return "No tengo un lugar guardado para ese evento."
            sub: list[str] = []
            if date_t:
                sub.append(date_t)
            if tt or tt_raw:
                sub.append(f"a las {tt or tt_raw}")
            extra = f" ({', '.join(sub)})" if sub else ""
            return f"«{title}» es en {loc_s}{extra}."

        if axis == "hora":
            if not (tt or tt_raw):
                if date_t:
                    return (
                        f"Para «{title}» no tengo hora guardada; el día es {date_t}."
                    )
                return f"«{title}» está en tu agenda, pero no tengo hora guardada."
            tshow = tt or str(tt_raw)
            if date_t:
                return f"«{title}» es {date_t} a las {tshow}."
            return f"«{title}» está a las {tshow}."

        if axis == "cuando":
            chunks: list[str] = []
            if date_t:
                chunks.append(date_t)
            if tt or tt_raw:
                chunks.append(f"a las {tt or tt_raw}")
            if not chunks:
                return (
                    f"Tengo «{title}» en la agenda, pero sin día u hora concretos guardados."
                )
            return f"«{title}» es {' '.join(chunks)}."

        body: list[str] = []
        if date_t:
            body.append(date_t)
        if tt or tt_raw:
            body.append(f"a las {tt or tt_raw}")
        if loc_s:
            body.append(f"en {loc_s}")
        if body:
            return f"«{title}» es {' '.join(body)}."
        return (
            f"Solo tengo «{title}» en la agenda local, sin fecha, hora ni lugar guardados."
        )

    def _agenda_candidates(self, raw: str) -> list[dict[str, Any]]:
        found = self._events.search_events(raw, limit=8)
        if found:
            return found
        all_e = self._events.get_events()
        if not all_e:
            return []
        return all_e[-min(5, len(all_e)) :]

    def _appointment_like(self, title: str, ed: dict[str, Any]) -> bool:
        blob = _strip_accents(
            f"{title} {ed.get('description') or ''}"
        ).lower().replace("ñ", "n")
        keys = (
            "cita",
            "reunion",
            "medico",
            "médico",
            "dentista",
            "hospital",
            "visita",
            "consulta",
        )
        return any(k.replace("ñ", "n") in blob for k in keys)

    def _payload_from_agenda_ed(self, raw: str, m: dict[str, Any]) -> dict[str, Any]:
        ed = m.get("event_data") or {}
        tt_raw = ed.get("time_text")
        tt_eff = _calendar_time_text_after_user_message(raw, tt_raw)
        payload: dict[str, Any] = {
            "title": str(ed.get("title") or "").strip() or "Evento",
            "date_text": ed.get("date_text"),
            "time_text": tt_eff if tt_eff is not None else tt_raw,
            "location": ed.get("location"),
            "description": ed.get("description"),
            "participants": list(ed.get("participants") or []),
            "duration_minutes": ed.get("duration_minutes"),
            "source_text": raw[:4000],
            "confidence": m.get("confidence"),
            "missing_fields": list(m.get("missing_fields") or []),
        }
        return {k: v for k, v in payload.items() if v is not None and v != []}

    def _agenda_pending_payload(self, raw: str, m: dict[str, Any]) -> dict[str, Any]:
        ed = m.get("event_data") or {}
        title = str(ed.get("title") or "").strip()
        tt_raw_ag = ed.get("time_text")
        tt_eff_ag = _calendar_time_text_after_user_message(raw, tt_raw_ag)
        return {
            "original_text": raw,
            "suggested_intent": "calendario",
            "clean_content": title or raw,
            "title": ed.get("title"),
            "date_text": ed.get("date_text"),
            "time_text": tt_eff_ag if tt_eff_ag is not None else tt_raw_ag,
            "location": ed.get("location"),
            "description": ed.get("description"),
            "participants": list(ed.get("participants") or []),
            "duration_minutes": ed.get("duration_minutes"),
            "confidence": m.get("confidence"),
            "missing_fields": list(m.get("missing_fields") or []),
            "created_at": _utc_iso(),
            "calendar_structured": True,
        }

    def _map_requested_field(self, raw: str, analysis: dict[str, Any]) -> str:
        rf = analysis.get("requested_field")
        if rf and rf != "unknown":
            return str(rf)
        t = _strip_accents((raw or "").lower()).replace("ñ", "n")
        if "con quien" in t or "con quién" in (raw or "").lower():
            return "participants"
        ax = self._agenda_question_axis(raw)
        return {"lugar": "location", "hora": "time", "cuando": "date", "general": "summary"}.get(
            ax, "summary"
        )

    def _resolve_query_target(
        self, raw: str, analysis: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        tid = analysis.get("target_event_id")
        if tid:
            ev = self._events.get_event_by_id(str(tid))
            if ev:
                return ev, []
        if self._references_last_event(raw):
            le = self._events.get_last_event()
            if le:
                return le, []
        fe = self._events.get_focused_event()
        if fe:
            return fe, []
        cand = self._events.search_events(raw, limit=8)
        if len(cand) == 1:
            return cand[0], cand
        if len(cand) > 1:
            return None, cand
        return None, []

    def _resolve_update_target(
        self, raw: str, analysis: dict[str, Any]
    ) -> dict[str, Any] | None:
        tid = analysis.get("target_event_id")
        if tid:
            ev = self._events.get_event_by_id(str(tid))
            if ev:
                return ev
        fe = self._events.get_focused_event()
        if fe:
            return fe
        if self._references_last_event(raw):
            return self._events.get_last_event()
        cand = self._events.search_events(raw, limit=5)
        if len(cand) == 1:
            return cand[0]
        return None

    def _updates_from_event_data(self, ed: dict[str, Any]) -> dict[str, Any]:
        u: dict[str, Any] = {}
        for k in ("title", "date_text", "time_text", "location", "description"):
            v = ed.get(k)
            if v is not None and str(v).strip():
                u[k] = str(v).strip()
        parts = ed.get("participants")
        if isinstance(parts, list) and parts:
            u["participants"] = [str(p).strip() for p in parts if p and str(p).strip()]
        if ed.get("duration_minutes") is not None:
            u["duration_minutes"] = ed["duration_minutes"]
        return u

    def _reply_participants_query(self, raw: str, ev: dict[str, Any]) -> str:
        title = str(ev.get("title") or "Evento").strip()
        date_t = str(ev.get("date_text") or "").strip()
        loc = str(ev.get("location") or "").strip()
        tt_raw = ev.get("time_text")
        tt = self._display_time_text(tt_raw, raw) if tt_raw else None
        pp = ev.get("participants")
        has_p = isinstance(pp, list) and len(pp) > 0
        bits = [f"Tienes «{title}»"]
        if date_t:
            bits.append(date_t)
        if tt or tt_raw:
            bits.append(f"a las {tt or tt_raw}")
        if loc:
            bits.append(f"en {loc}")
        core = " ".join(bits)
        if has_p:
            names = ", ".join(str(p).strip() for p in pp if p)
            return f"{core}, con {names}."
        return f"{core}, pero no tengo guardado con quién es."

    def _reply_query_with_field(
        self, raw: str, ev: dict[str, Any], field: str, last_ref: bool
    ) -> str:
        if field == "participants":
            return self._reply_participants_query(raw, ev)
        if field == "location":
            if last_ref:
                loc_s = str(ev.get("location") or "").strip()
                if loc_s:
                    return f"La he guardado en {loc_s}."
                return "No tengo un lugar guardado para ese evento."
            loc_s = str(ev.get("location") or "").strip()
            if not loc_s:
                return "No tengo un lugar guardado para ese evento."
            t = str(ev.get("title") or "Evento").strip()
            return f"«{t}» es en {loc_s}."
        if field == "time":
            if last_ref:
                date_t = str(ev.get("date_text") or "").strip()
                tt_raw = ev.get("time_text")
                tt = self._display_time_text(tt_raw, raw) if tt_raw else None
                parts = ["La he guardado"]
                if date_t:
                    parts.append(f"para {date_t}")
                if tt:
                    parts.append(f"a las {tt}")
                elif tt_raw:
                    parts.append(f"a las {tt_raw}")
                return " ".join(parts) + "."
            return self._agenda_reply_single(raw, ev, last_ref=False)
        if field == "date":
            return self._agenda_reply_single(raw, ev, last_ref=False)
        if field == "summary":
            return f"Tienes {EventsStore.format_event_summary(ev)}."
        return self._agenda_reply_single(raw, ev, last_ref=last_ref)

    def _dispatch_agenda_motor(
        self, raw: str, motor: dict[str, Any]
    ) -> tuple[str, str, str | dict | None, None]:
        ci = motor["calendar_intent"]
        if ci == "create_event":
            return self._agenda_handle_create(raw, motor)
        if ci == "query_agenda":
            return self._agenda_handle_query(raw, motor)
        if ci == "update_event":
            return self._agenda_handle_update(raw, motor)
        if ci == "needs_clarification":
            return self._agenda_handle_clarification(raw, motor)
        return (self._CONSULTA_LOCAL, "consulta", None, None)

    def _agenda_handle_clarification(
        self, raw: str, motor: dict[str, Any]
    ) -> tuple[str, str, None, None]:
        msg = motor.get("answer") or "¿Puedes concretar día u hora?"
        return (msg, "consulta", None, None)

    def _agenda_handle_create(
        self, raw: str, motor: dict[str, Any]
    ) -> tuple[str, str, str | dict | None, None]:
        conf = float(motor.get("confidence", 0))
        ed = motor.get("event_data") or {}
        title = str(ed.get("title") or "").strip()
        date_text = str(ed.get("date_text") or "").strip()
        time_text = str(ed.get("time_text") or "").strip()
        if not title:
            msg = motor.get("answer") or "¿Qué evento quieres anotar?"
            return (msg, "consulta", None, None)
        if not date_text:
            msg = motor.get("answer") or "¿Qué día es?"
            self._pending.save_pending_action(self._agenda_pending_payload(raw, motor))
            return (msg, "ambiguo", None, None)
        ap = self._appointment_like(title, ed)
        if not time_text:
            if ap:
                msg = motor.get("answer") or "¿A qué hora es?"
            else:
                msg = motor.get("answer") or "¿A qué hora, o es para todo el día?"
            self._pending.save_pending_action(self._agenda_pending_payload(raw, motor))
            return (msg, "ambiguo", None, None)
        if conf < 0.80:
            self._pending.save_pending_action(self._agenda_pending_payload(raw, motor))
            msg = (
                motor.get("answer")
                or f"He entendido «{title}» para {date_text} a las {time_text}. ¿Lo guardo?"
            )
            return (msg, "ambiguo", None, None)
        payload = self._payload_from_agenda_ed(raw, motor)
        reply = self._saved_calendar_ack(payload, raw)
        return (reply, "calendario", payload, None)

    def _agenda_handle_query(
        self, raw: str, motor: dict[str, Any]
    ) -> tuple[str, str, None, None]:
        all_ev = self._events.get_events()
        if not all_ev:
            return ("No tienes eventos guardados en la agenda local.", "consulta", None, None)

        if self._is_day_scope_question(raw):
            hints = self._day_hints_in_message(raw)
            if hints:
                # v0.21.5 — síntesis inferencial también en el flujo de respaldo.
                label = self._day_hint_display(hints[0])
                return self._synthesize_day_agenda(raw, label, hints)

        if self._is_agenda_overview_question(raw):
            reply = self._agenda_reply_overview(all_ev, raw)
            return (reply, "consulta", None, None)

        target, cand = self._resolve_query_target(raw, motor)
        last_ref = self._references_last_event(raw)
        field = self._map_requested_field(raw, motor)

        if target is None and len(cand) > 1:
            return (self._agenda_reply_multiple_clarify(cand), "consulta", None, None)
        if target is None:
            if motor.get("answer"):
                return (str(motor["answer"]), "consulta", None, None)
            return ("No encuentro ese evento en tu agenda local.", "consulta", None, None)

        if target.get("id"):
            self._events.set_focused_event_id(str(target["id"]))
        reply = self._reply_query_with_field(raw, target, field, last_ref=last_ref)
        return (reply, "consulta", None, None)

    def _agenda_handle_update(
        self, raw: str, motor: dict[str, Any]
    ) -> tuple[str, str, None, None]:
        ev = self._resolve_update_target(raw, motor)
        if ev is None or not ev.get("id"):
            msg = "No sé a qué evento te refieres. ¿Puedes decirme cuál quieres actualizar?"
            return (msg, "consulta", None, None)
        ed = motor.get("event_data") or {}
        updates = self._updates_from_event_data(ed)
        if not updates:
            msg = motor.get("answer") or "No he captado qué quieres cambiar."
            return (msg, "consulta", None, None)
        updated = self._events.update_event(str(ev["id"]), updates)
        if not updated:
            return ("No he podido actualizar ese evento.", "consulta", None, None)
        self._events.set_focused_event_id(str(updated["id"]))
        reply = self._updated_event_ack(updated, raw)
        return (reply, "consulta", None, None)

    def _word_tokens(self, text: str) -> set[str]:
        folded = _strip_accents((text or "").lower())
        return set(re.findall(r"[a-z0-9]+", folded))

    def _keywords_match(self, text: str, keywords: tuple[str, ...]) -> bool:
        """True si alguna palabra clave aparece como token completo (evita falsos positivos)."""
        words = self._word_tokens(text)
        for kw in keywords:
            k = _strip_accents(kw.lower())
            token = re.sub(r"[^a-z0-9]+", "", k)
            if token and token in words:
                return True
        return False

    def process_message(self, text: str) -> tuple[str, str, str | dict | None, str | None]:
        """
        Devuelve (respuesta, intent_type, texto_para_guardar | None, ui_hint | None).
        ui_hint == "confirm_rescue" solo si hubo pending_action y la respuesta del usuario
        no se resolvió (needs_clarification o unknown).
        """
        raw = (text or "").strip()
        if not raw:
            return ("Escribe un mensaje con contenido.", "consulta", None, None)

        logger.info("Procesando mensaje de usuario")

        pending = self._pending.get_pending_action()
        if pending:
            return self._process_pending_reply(raw, pending)

        return self._process_fresh(raw)

    def _pending_content(self, pending: dict) -> str:
        content = (pending.get("clean_content") or pending.get("original_text") or "").strip()
        if not content:
            content = (pending.get("original_text") or "").strip()
        return content

    def _process_pending_reply(
        self, raw: str, pending: dict
    ) -> tuple[str, str, str | None, str | None]:
        logger.info(
            "pending_action activa (suggested_intent=%s)",
            pending.get("suggested_intent"),
        )
        preview = str(pending.get("clean_content") or pending.get("original_text") or "")
        logger.debug("pending clean_content preview: %.120s", preview)

        # v0.21.4 — Si la pending es de calendario con campos críticos faltantes,
        # interpretamos el mensaje como completado del evento antes que como
        # confirmación/cancelación genérica.
        if self._pending_calendar_needs_completion(pending):
            handled = self._try_complete_pending_calendar(raw, pending)
            if handled is not None:
                return handled

        # v0.21.4d — Si la pending es de nota estructurada, interpretamos el
        # mensaje como completado del título/contenido (no como nota nueva ni
        # como confirmación genérica). Nunca cae a GPT general.
        if self._pending_is_note_completion(pending):
            handled = self._try_complete_pending_note(raw, pending)
            if handled is not None:
                return handled

        # v0.21.9 — Pending de descripción de tarea: el siguiente mensaje es
        # el contenido literal, no se interpreta como nuevo intent.
        if self._pending_is_task_description_completion(pending):
            handled = self._try_complete_pending_task_description(raw, pending)
            if handled is not None:
                return handled

        # v0.21.10 — Pending de creación de tarea sin título: el siguiente
        # mensaje aporta el título. "sí" no guarda basura.
        if self._pending_is_task_completion(pending):
            handled = self._try_complete_pending_task(raw, pending)
            if handled is not None:
                return handled

        resolved = resolve_pending_reply(raw, pending)
        category = resolved["decision"]
        logger.info(
            "resolve_pending_reply: decision=%s source=%s confidence=%.2f",
            category,
            resolved["source"],
            resolved["confidence"],
        )
        logger.debug("resolve_pending_reply: reason=%s", str(resolved.get("reason", ""))[:200])

        if category == "needs_clarification":
            cq = resolved.get("clarification_question")
            msg = (cq.strip() if isinstance(cq, str) else "") or _CLARIFY_PENDING_REPLY
            logger.info(
                "Solicitando aclaración; pending_action conservada; ui_hint=%s",
                UI_HINT_CONFIRM_RESCUE,
            )
            return (msg, "ambiguo", None, UI_HINT_CONFIRM_RESCUE)

        if category == "unknown":
            logger.info(
                "decisión unknown; pending_action conservada; ui_hint=%s",
                UI_HINT_CONFIRM_RESCUE,
            )
            return (_UNKNOWN_PENDING_REPLY, "ambiguo", None, UI_HINT_CONFIRM_RESCUE)

        if category == "cancel":
            self._pending.clear_pending_action()
            logger.info("Acción pendiente cancelada (decisión cancel)")
            return ("De acuerdo, no lo guardo.", "consulta", None, None)

        content = self._pending_content(pending)

        if category == "confirm":
            suggested = pending.get("suggested_intent")
            if suggested not in ("nota", "tarea", "calendario"):
                suggested = self._infer_intent_from_text(
                    str(pending.get("clean_content") or pending.get("original_text") or "")
                )
            if suggested == "calendario" and self._pending_is_rich_calendar(pending):
                payload_dict = self._event_dict_from_pending(pending)
                self._pending.clear_pending_action()
                logger.info(
                    "Acción pendiente confirmada: calendario estructurado title=%s",
                    (payload_dict.get("title") or "")[:80],
                )
                return (
                    self._saved_calendar_ack(payload_dict, str(pending.get("original_text") or "")),
                    "calendario",
                    payload_dict,
                    None,
                )
            self._pending.clear_pending_action()
            logger.info("Acción pendiente confirmada: tipo=%s (decisión confirm)", suggested)
            return self._confirmation_saved_reply(suggested, content)

        if category == "save_as_note":
            self._pending.clear_pending_action()
            logger.info("Acción pendiente confirmada: tipo=nota")
            return self._confirmation_saved_reply("nota", content)

        if category == "save_as_task":
            self._pending.clear_pending_action()
            logger.info("Acción pendiente confirmada: tipo=tarea")
            return self._confirmation_saved_reply("tarea", content)

        if category == "save_as_event":
            if self._pending_is_rich_calendar(pending):
                payload_dict = self._event_dict_from_pending(pending)
                self._pending.clear_pending_action()
                logger.info(
                    "Acción pendiente: save_as_event calendario estructurado title=%s",
                    (payload_dict.get("title") or "")[:80],
                )
                return (
                    self._saved_calendar_ack(
                        payload_dict, str(pending.get("original_text") or "")
                    ),
                    "calendario",
                    payload_dict,
                    None,
                )
            self._pending.clear_pending_action()
            logger.info("Acción pendiente confirmada: tipo=calendario (texto simple)")
            return self._confirmation_saved_reply("calendario", content)

        logger.warning("resolve_pending_reply: categoría inesperada %r; se trata como unknown", category)
        return (_UNKNOWN_PENDING_REPLY, "ambiguo", None, UI_HINT_CONFIRM_RESCUE)

    def _confirmation_saved_reply(
        self, intent: str, content: str
    ) -> tuple[str, str, str | dict | None, None]:
        if intent not in ("nota", "tarea", "calendario"):
            intent = "nota"
        label = {"nota": "nota", "tarea": "tarea", "calendario": "evento"}[intent]
        return (f"Confirmado. Lo he guardado como {label}.", intent, content, None)

    def _unified_candidates(self, raw: str) -> list[dict[str, Any]]:
        """Candidatos para el motor unificado: búsqueda + cola de la agenda."""
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for ev in self._events.search_events(raw, limit=8):
            eid = str(ev.get("id", ""))
            if eid and eid not in seen:
                seen.add(eid)
                out.append(ev)
        all_e = self._events.get_events()
        for ev in all_e[-5:]:
            eid = str(ev.get("id", ""))
            if eid and eid not in seen:
                seen.add(eid)
                out.append(ev)
        return out

    def _unified_pending_payload(self, raw: str, ev: dict[str, Any]) -> dict[str, Any]:
        """Convierte calendar_event del contrato unificado en un pending_action enriquecido.

        v0.21.7b: si `title` viene vacío, se conserva como `None` (en vez de
        rellenarse con "cita") para que `missing_fields` lo capture y el flujo
        de completado pregunte por el título en el siguiente turno.
        """
        title_raw = (ev.get("title") or "").strip()
        title_eff = title_raw or None
        tt_eff = _calendar_time_text_after_user_message(raw, ev.get("time_text"))
        payload: dict[str, Any] = {
            "original_text": raw,
            "suggested_intent": "calendario",
            "pending_kind": "calendar_event_completion",
            "clean_content": title_raw or raw,
            "title": title_eff,
            "date_text": ev.get("date_text"),
            "time_text": tt_eff if tt_eff is not None else ev.get("time_text"),
            "location": ev.get("location"),
            "description": ev.get("description"),
            "participants": list(ev.get("participants") or []),
            "duration_minutes": ev.get("duration_minutes"),
            "confidence": None,
            "missing_fields": [],
            "created_at": _utc_iso(),
            "calendar_structured": True,
        }
        payload["missing_fields"] = self._pending_calendar_missing_fields(payload)
        return payload

    def _minimal_calendar_pending_payload(self, raw: str) -> dict[str, Any]:
        """Crea una pending_action mínima de calendario para mensajes vagos
        del tipo "agéndame una cita para".

        v0.21.10 — Detecta si el sustantivo desnudo era "evento", "reunión" o
        "encuentro" para usarlo como título inicial en lugar de "cita".
        """
        tokens = _normalize_for_bare(raw)
        title = "cita"
        for tok in tokens:
            if tok in _BARE_CALENDAR_NOUNS_STRICT:
                # "reunion" → mostramos "reunión" al usuario.
                title = "reunión" if tok == "reunion" else tok
                break
        payload: dict[str, Any] = {
            "original_text": raw,
            "suggested_intent": "calendario",
            "pending_kind": "calendar_event_completion",
            "clean_content": title,
            "title": title,
            "date_text": None,
            "time_text": None,
            "location": None,
            "description": None,
            "participants": [],
            "duration_minutes": None,
            "confidence": None,
            "missing_fields": [],
            "created_at": _utc_iso(),
            "calendar_structured": True,
        }
        payload["missing_fields"] = self._pending_calendar_missing_fields(payload)
        return payload

    # ------------------------------------------------------------------
    # v0.21.4d — Notas estructuradas: pending de nota y completado.
    # ------------------------------------------------------------------

    def _minimal_note_pending_payload(self, raw: str) -> dict[str, Any]:
        """Pending mínima para "quiero una nota" sin tema ni contenido."""
        return {
            "original_text": raw,
            "suggested_intent": "nota",
            "pending_kind": "note_completion",
            "title": None,
            "content": None,
            "clean_content": None,
            "missing_fields": ["title_or_content"],
            "confidence": None,
            "created_at": _utc_iso(),
            "note_structured": True,
        }

    def _pending_is_note_completion(self, pending: dict) -> bool:
        if not isinstance(pending, dict):
            return False
        if (pending.get("pending_kind") or "") == "note_completion":
            return True
        if (
            (pending.get("suggested_intent") or "") == "nota"
            and pending.get("note_structured") is True
        ):
            return True
        return False

    # ------------------------------------------------------------------
    # v0.21.10 — Tareas mínimas (pending_kind="task_completion") cuando el
    # usuario dice solo "tarea" / "una tarea" sin título.
    # ------------------------------------------------------------------

    def _minimal_task_pending_payload(self, raw: str) -> dict[str, Any]:
        """Pending mínima para 'tarea' / 'una tarea' / 'quiero una tarea'."""
        return {
            "original_text": raw,
            "suggested_intent": "tarea",
            "pending_kind": "task_completion",
            "title": None,
            "description": None,
            "date_text": None,
            "time_text": None,
            "priority": None,
            "clean_content": None,
            "missing_fields": ["title"],
            "confidence": None,
            "created_at": _utc_iso(),
            "task_structured": True,
        }

    def _pending_is_task_completion(self, pending: dict) -> bool:
        if not isinstance(pending, dict):
            return False
        if (pending.get("pending_kind") or "") == "task_completion":
            return True
        if (
            (pending.get("suggested_intent") or "") == "tarea"
            and pending.get("task_structured") is True
            and not (pending.get("title") or "").strip()
        ):
            return True
        return False

    def _open_task_pending(
        self, raw: str
    ) -> tuple[str, str, None, None]:
        """Crea pending_action de tarea vacía y pregunta por el título."""
        action = self._minimal_task_pending_payload(raw)
        self._pending.save_pending_action(action)
        logger.info(
            "v0.21.10 pending tarea mínima creada (raw=%r, missing=%s)",
            raw[:80],
            action.get("missing_fields"),
        )
        return (
            "¿Cuál es el título de la tarea que quieres crear?",
            "ambiguo",
            None,
            None,
        )

    _AFFIRMATIVE_SHORT_RE = re.compile(
        r"^(si|sip|sii|claro|vale|ok|okay|de acuerdo|por supuesto|"
        r"perfecto|adelante|hazlo|venga)$",
        flags=re.IGNORECASE,
    )

    _CANCEL_SHORT_RE = re.compile(
        r"^(no|nope|cancel(?:a|ar|alo)?|anula(?:r|lo)?|"
        r"dejal[oa]|olvida(?:lo)?|nada)$",
        flags=re.IGNORECASE,
    )

    def _is_affirmative_short(self, raw: str) -> bool:
        text = _strip_accents((raw or "").strip().lower())
        return bool(self._AFFIRMATIVE_SHORT_RE.match(text))

    def _is_cancel_short(self, raw: str) -> bool:
        text = _strip_accents((raw or "").strip().lower())
        return bool(self._CANCEL_SHORT_RE.match(text))

    def _try_complete_pending_task(
        self, raw: str, pending: dict[str, Any]
    ) -> Optional[tuple[str, str, str | dict | None, str | None]]:
        """Interpreta el siguiente mensaje como título de la tarea pendiente.

        - "sí" / "vale" / "ok" sobre pending vacío NO guarda; pide título.
        - "cancela" / "no" cierra la pending.
        - Si el texto contiene "tarea sobre X" / "crear una tarea sobre X",
          extrae X como título.
        - En otro caso, usa el texto literal (capitalizado) como título.
        """
        text = (raw or "").strip()
        if not text:
            return (
                "¿Cuál es el título de la tarea que quieres crear?",
                "ambiguo",
                None,
                None,
            )

        if self._is_cancel_short(text):
            self._pending.clear_pending_action()
            return ("De acuerdo, no creo la tarea.", "consulta", None, None)

        if self._is_affirmative_short(text):
            return (
                "Necesito que me digas el título de la tarea.",
                "ambiguo",
                None,
                None,
            )

        # Si el usuario repite "tarea sobre X" / "crear una tarea sobre X",
        # extraemos X como título.
        norm = _strip_accents(text.lower())
        norm = re.sub(r"[^\w\s]+", " ", norm)
        norm = re.sub(r"\s+", " ", norm).strip()
        title_candidate = text
        m = re.search(
            r"\btarea\s+(?:sobre|acerca\s+de|de|para)\s+(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if m:
            title_candidate = m.group(1).strip()
        else:
            # Quitar muletillas iniciales ("quiero crear una tarea X" → "X").
            stripped = re.sub(
                r"^(?:quiero|quisiera|necesito|crear|creame|crea|"
                r"hazme|haz|haz una|haz la|por\s+favor)\s+",
                "",
                text,
                flags=re.IGNORECASE,
            ).strip()
            stripped = re.sub(
                r"^(?:una|un|la|el)\s+", "", stripped, flags=re.IGNORECASE
            ).strip()
            stripped = re.sub(
                r"^tarea\s+(?:sobre|acerca\s+de|de|para)?\s*",
                "",
                stripped,
                flags=re.IGNORECASE,
            ).strip()
            if stripped and stripped.lower() != "tarea":
                title_candidate = stripped

        title_candidate = title_candidate.strip().strip(".,;:!¿?").strip()
        if not title_candidate or title_candidate.lower() == "tarea":
            return (
                "¿Cuál es el título de la tarea que quieres crear?",
                "ambiguo",
                None,
                None,
            )

        # Capitalizar solo la primera letra si está toda en minúsculas.
        # Sin punto final (es un título, no contenido).
        title = title_candidate.strip().strip(".,;:!¿?\"'«»").strip()
        if not title:
            title = title_candidate
        if title and title[:1].islower():
            title = title[:1].upper() + title[1:]

        self._pending.clear_pending_action()
        logger.info(
            "v0.21.10: pending task_completion → tarea creada title=%r",
            title[:80],
        )
        return (
            f"He creado la tarea «{title}».",
            "tarea",
            {"title": title},
            None,
        )

    # ------------------------------------------------------------------
    # v0.21.9 — Tareas estructuradas con descripción opcional.
    # ------------------------------------------------------------------

    def _task_description_pending_payload(
        self,
        task_id: str,
        task_title: str,
        original_text: str,
    ) -> dict[str, Any]:
        """Pending para "ponle contenido / añade descripción" sobre una
        tarea recién creada o focalizada."""
        return {
            "original_text": original_text,
            "suggested_intent": "tarea",
            "pending_kind": "task_description_completion",
            "task_id": str(task_id),
            "task_title": str(task_title or "").strip() or "Tarea",
            "missing_fields": ["description"],
            "confidence": None,
            "created_at": _utc_iso(),
            "task_structured": True,
        }

    def _pending_is_task_description_completion(self, pending: dict) -> bool:
        if not isinstance(pending, dict):
            return False
        return (pending.get("pending_kind") or "") == "task_description_completion"

    def _try_complete_pending_task_description(
        self, raw: str, pending: dict[str, Any]
    ) -> Optional[tuple[str, str, str | dict | None, str | None]]:
        """El siguiente mensaje del usuario es el contenido literal de la
        descripción de la tarea (no se interpreta como nuevo intent)."""
        text = (raw or "").strip()
        task_id = str(pending.get("task_id") or "").strip()
        task_title = str(pending.get("task_title") or "Tarea").strip()
        if not task_id:
            self._pending.clear_pending_action()
            return (
                "He perdido la referencia a la tarea. ¿Puedes decirme a qué tarea?",
                "consulta",
                None,
                None,
            )

        # Heurísticas mínimas de cancelación.
        low = _strip_accents(text.lower())
        if low in {"cancelar", "anular", "deja", "deja", "no quiero",
                   "no, dejalo", "no, déjalo"}:
            self._pending.clear_pending_action()
            return ("De acuerdo, no añado contenido.", "consulta", None, None)

        # Si el usuario vuelve a corregir el destinatario ("no es a la
        # tarea, es a la cita") mantenemos la pending por una vuelta y
        # respondemos con prudencia.
        if self._mentions_calendar_word(text) and not self._TASK_NOTE_MENTION_RE.search(
            text
        ):
            return (
                f"Tengo abierto contenido para la tarea «{task_title}». "
                "Si prefieres aplicarlo a un evento, dímelo claramente.",
                "ambiguo",
                None,
                None,
            )

        if not text:
            return (
                f"¿Qué contenido quieres añadir a la tarea «{task_title}»?",
                "ambiguo",
                None,
                None,
            )

        polished = self._polish_user_content(text) if hasattr(self, "_polish_user_content") else text
        updated = self._tasks.update_task(task_id, {"description": polished})
        if not updated:
            self._pending.clear_pending_action()
            return (
                f"No he encontrado la tarea «{task_title}». ¿Quieres crearla de nuevo?",
                "consulta",
                None,
                None,
            )
        self._pending.clear_pending_action()
        # Mantenemos el foco en la tarea recién actualizada.
        try:
            self._focus.set_focus(
                kind="task",
                entity_id=task_id,
                label=updated.get("title") or task_title,
                operation="update_task",
                user_id=DEFAULT_USER_ID,
            )
        except Exception:
            logger.exception("focus update tras descripción de tarea falló")
        return (
            f"He actualizado la tarea «{updated.get('title') or task_title}».",
            "consulta",
            None,
            None,
        )

    def _open_task_description_pending(
        self, raw: str, task_id: str, task_title: str
    ) -> tuple[str, str, None, None]:
        """Abre pending de descripción de tarea y pide contenido."""
        action = self._task_description_pending_payload(task_id, task_title, raw)
        self._pending.save_pending_action(action)
        logger.info(
            "v0.21.9: pending task_description abierta task_id=%s title=%r",
            task_id[:8],
            task_title[:40],
        )
        return (
            f"¿Qué contenido quieres añadir a la tarea «{task_title}»?",
            "ambiguo",
            None,
            None,
        )

    def _open_note_pending(
        self, raw: str
    ) -> tuple[str, str, None, None]:
        """Crea pending_action de nota vacía y pregunta."""
        action = self._minimal_note_pending_payload(raw)
        self._pending.save_pending_action(action)
        logger.info(
            "Pending nota mínima creada (raw=%r, missing=%s)",
            raw[:80],
            action.get("missing_fields"),
        )
        return (
            "¿Qué título o contenido quieres guardar como nota?",
            "ambiguo",
            None,
            None,
        )

    def _note_pending_question_for_missing(self, pending: dict[str, Any]) -> str:
        title = (pending.get("title") or "").strip() if pending.get("title") else ""
        if title:
            return (
                f"Perfecto. Tomo como título «{title}». "
                "¿Qué contenido quieres guardar?"
            )
        return "¿Qué título o contenido quieres guardar como nota?"

    @staticmethod
    def _polish_user_content(text: str) -> str:
        s = (text or "").strip()
        if not s:
            return s
        s = re.sub(
            r"^(eh|pues|bueno|este|emm+|ehh+|mmm+)\s*[,\.\s]+",
            "",
            s,
            flags=re.IGNORECASE,
        )
        s = s.strip()
        if not s:
            return s
        if s[0].islower():
            s = s[0].upper() + s[1:]
        if not s.endswith((".", "!", "?", "…")):
            s += "."
        return s

    @staticmethod
    def _capitalize_title(text: str) -> str:
        s = (text or "").strip()
        if not s:
            return s
        s = s.strip(" .,;:\"'«»")
        if not s:
            return ""
        if s[0].islower():
            s = s[0].upper() + s[1:]
        return s

    @staticmethod
    def _infer_title_from_topic(text: str) -> Optional[str]:
        """Si el texto es solo un TEMA, devuelve un título inferido. Si no, None."""
        raw = (text or "").strip()
        if not raw:
            return None
        norm = _strip_accents(raw.lower())
        norm = re.sub(r"\s+", " ", norm).strip()
        if not norm:
            return None
        # Patrones de tema: "una reflexion sobre X", "una idea sobre X", etc.
        topic_patterns = [
            (r"^una?\s+reflexi[oó]n\s+(?:sobre|acerca\s+de|de)\s+(.+)$", "Reflexión sobre {}"),
            (r"^una?\s+idea\s+(?:sobre|acerca\s+de|de)\s+(.+)$", "Idea sobre {}"),
            (r"^algo\s+(?:sobre|acerca\s+de|de)\s+(.+)$", "Nota sobre {}"),
            (r"^una?\s+nota\s+(?:sobre|acerca\s+de|de)\s+(.+)$", "Nota sobre {}"),
            (r"^un\s+apunte\s+(?:sobre|acerca\s+de|de)\s+(.+)$", "Apunte sobre {}"),
        ]
        # Usamos el texto original sin acentos quitados para no perder la grafía
        # en el resultado, pero el match se hace sobre la versión normalizada.
        for pat, tpl in topic_patterns:
            m = re.match(pat, norm)
            if m:
                # Recuperar la porción equivalente del texto original.
                start_idx = m.start(1)
                # `start_idx` corresponde a `norm`; lo más seguro es ubicar el
                # primer "sobre"/"acerca"/"de" en el texto original.
                m2 = re.search(
                    r"(sobre|acerca\s+de|de)\s+(.+)$",
                    raw,
                    flags=re.IGNORECASE,
                )
                tail = (m2.group(2).strip() if m2 else raw)
                tail = tail.rstrip(" .,;")
                if not tail:
                    return None
                return tpl.format(tail)
        return None

    @staticmethod
    def _looks_like_topic_only(text: str) -> bool:
        """Heurística: ¿es solo un TEMA (sin verbo / sin afirmación)?"""
        raw = (text or "").strip()
        if not raw:
            return False
        norm = _strip_accents(raw.lower())
        for pref in _NOTE_TOPIC_PREFIXES:
            if norm.startswith(pref):
                return True
        return False

    def _local_note_structuring_fallback(
        self, user_text: str, pending_note: Optional[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        """Fallback determinista cuando GPT no responde.
        No inventa contenido: solo detecta cancel, título+contenido explícitos,
        tema/título o contenido literal."""
        text = (user_text or "").strip()
        if not text:
            return None

        norm = _strip_accents(text.lower()).strip()
        # Cancelación.
        if norm in {
            "no",
            "no.",
            "cancela",
            "cancelar",
            "olvidalo",
            "olvídalo",
            "dejalo",
            "déjalo",
            "no lo guardes",
            "no guardes",
            "nada",
        } or norm.startswith("no lo guardes") or norm.startswith("no guardes"):
            return {
                "intent": "cancel",
                "title": None,
                "content": None,
                "confidence": 1.0,
                "missing_fields": [],
                "reason": "fallback local: cancelación literal",
            }

        # Título y contenido explícitos: "título: X. contenido: Y".
        m = _NOTE_EXPLICIT_TITLE_RE.search(text)
        if m:
            title = self._capitalize_title(m.group(1).strip().rstrip(". "))
            content_part = (m.group(2) or "").strip()
            if not content_part:
                cm = _NOTE_EXPLICIT_CONTENT_RE.search(text)
                if cm:
                    content_part = cm.group(1).strip()
            if title and content_part:
                return {
                    "intent": "note_title_and_content",
                    "title": title,
                    "content": self._polish_user_content(content_part),
                    "confidence": 0.95,
                    "missing_fields": [],
                    "reason": "fallback local: título+contenido explícitos",
                }
            if title and not content_part:
                return {
                    "intent": "note_title_only",
                    "title": title,
                    "content": None,
                    "confidence": 0.9,
                    "missing_fields": ["content"],
                    "reason": "fallback local: título explícito sin contenido",
                }

        # Si la pending ya tiene title, asumimos que esto es CONTENIDO.
        pending_title = ""
        if isinstance(pending_note, dict):
            pending_title = (pending_note.get("title") or "").strip()
        if pending_title:
            return {
                "intent": "note_content",
                "title": None,
                "content": self._polish_user_content(text),
                "confidence": 0.8,
                "missing_fields": [],
                "reason": "fallback local: pending con título → contenido",
            }

        # Si el mensaje parece un TEMA: inferimos título y NO contenido.
        if self._looks_like_topic_only(text):
            inferred = self._infer_title_from_topic(text)
            if inferred:
                return {
                    "intent": "note_title_only",
                    "title": self._capitalize_title(inferred),
                    "content": None,
                    "confidence": 0.75,
                    "missing_fields": ["content"],
                    "reason": "fallback local: tema detectado, título inferido",
                }

        # En caso de duda, preferimos pedir aclaración a inventar.
        # Solo si el mensaje es razonablemente afirmativo y no parece un tema,
        # devolvemos note_content con título inferido conservador.
        words = re.findall(r"\w+", text)
        if len(words) >= 6 and not self._looks_like_topic_only(text):
            # Título conservador: primeras 6 palabras.
            head = " ".join(words[:6])
            inferred_title = self._capitalize_title(head)
            return {
                "intent": "note_content",
                "title": inferred_title or None,
                "content": self._polish_user_content(text),
                "confidence": 0.55,
                "missing_fields": [],
                "reason": "fallback local: contenido sin título → inferido conservador",
            }

        return {
            "intent": "needs_clarification",
            "title": None,
            "content": None,
            "confidence": 0.0,
            "missing_fields": ["title_or_content"],
            "reason": "fallback local: no se pudo decidir",
        }

    def _apply_note_completion_updates(
        self, pending: dict[str, Any], result: dict[str, Any]
    ) -> dict[str, Any]:
        intent = (result.get("intent") or "").strip().lower()
        new_title = (result.get("title") or "").strip() if result.get("title") else ""
        new_content = (result.get("content") or "").strip() if result.get("content") else ""

        merged: dict[str, Any] = dict(pending)
        if intent == "note_title_only":
            if new_title:
                merged["title"] = new_title
            merged["content"] = None
        elif intent == "note_content":
            if new_content:
                merged["content"] = new_content
            if new_title and not (merged.get("title") or "").strip():
                merged["title"] = new_title
        elif intent == "note_title_and_content":
            if new_title:
                merged["title"] = new_title
            if new_content:
                merged["content"] = new_content

        missing: list[str] = []
        if not (merged.get("title") or "").strip() and not (merged.get("content") or "").strip():
            missing.append("title_or_content")
        else:
            if not (merged.get("content") or "").strip():
                missing.append("content")
        merged["missing_fields"] = missing
        merged["pending_kind"] = "note_completion"
        merged["suggested_intent"] = "nota"
        merged["note_structured"] = True
        return merged

    def _save_pending_note_now(
        self, pending: dict[str, Any]
    ) -> tuple[str, str, dict, None]:
        title = (pending.get("title") or "").strip()
        content = (pending.get("content") or "").strip()
        payload = {
            "title": title or None,
            "content": content or title,
        }
        self._pending.clear_pending_action()
        label = title or content or "(sin título)"
        logger.info(
            "Nota estructurada guardada: title=%s content_len=%d",
            (title or "")[:80],
            len(content or ""),
        )
        return (f"He guardado la nota «{label}».", "nota", payload, None)

    def _try_complete_pending_note(
        self, raw: str, pending: dict[str, Any]
    ) -> Optional[tuple[str, str, str | dict | None, str | None]]:
        """Interpreta el mensaje como completado de la pending de nota.
        Devuelve None solo si el mensaje no es procesable como tal."""
        # v0.21.10 — "sí" / "vale" / "ok" sobre una pending de nota vacía NO
        # debe guardar nada. Pedimos contenido.
        if self._is_affirmative_short(raw):
            has_title = bool((pending.get("title") or "").strip())
            has_content = bool((pending.get("content") or "").strip())
            if not has_title and not has_content:
                return (
                    "Necesito que me digas qué quieres guardar como nota.",
                    "ambiguo",
                    None,
                    None,
                )
        if self._is_cancel_short(raw):
            self._pending.clear_pending_action()
            return ("De acuerdo, no creo la nota.", "consulta", None, None)
        # v0.21.10 — Si el usuario repite el sustantivo basura ("nota",
        # "una nota", "apunte"...) sobre una pending vacía, no creamos
        # una nota con content="nota".
        if (
            _bare_intent_kind(raw) == "note"
            and not (pending.get("title") or "").strip()
            and not (pending.get("content") or "").strip()
        ):
            return (
                "Necesito que me digas qué quieres guardar como nota.",
                "ambiguo",
                None,
                None,
            )
        result = try_note_structuring(raw, pending)
        if result is None:
            result = self._local_note_structuring_fallback(raw, pending)
        if result is None:
            return None

        intent = (result.get("intent") or "").strip().lower()
        logger.info(
            "Pending nota: try_note_structuring intent=%s conf=%.2f",
            intent,
            float(result.get("confidence", 0) or 0),
        )

        if intent == "cancel":
            self._pending.clear_pending_action()
            return ("De acuerdo, no lo guardo.", "consulta", None, None)

        if intent == "other" or intent == "needs_clarification":
            msg = self._note_pending_question_for_missing(pending)
            return (msg, "ambiguo", None, None)

        merged = self._apply_note_completion_updates(pending, result)
        title = (merged.get("title") or "").strip()
        content = (merged.get("content") or "").strip()

        if title and content:
            return self._save_pending_note_now(merged)

        # Solo título → conservamos pending y pedimos contenido.
        self._pending.save_pending_action(merged)
        msg = self._note_pending_question_for_missing(merged)
        return (msg, "ambiguo", None, None)

    def _unified_payload_from_event(
        self, raw: str, ev: dict[str, Any], confidence: float
    ) -> dict[str, Any]:
        title = str(ev.get("title") or "").strip() or "Evento"
        tt_eff = _calendar_time_text_after_user_message(raw, ev.get("time_text"))
        payload: dict[str, Any] = {
            "title": title,
            "date_text": ev.get("date_text"),
            "time_text": tt_eff if tt_eff is not None else ev.get("time_text"),
            "location": ev.get("location"),
            "description": ev.get("description"),
            "participants": list(ev.get("participants") or []),
            "duration_minutes": ev.get("duration_minutes"),
            "source_text": raw[:4000],
            "confidence": confidence,
            "needs_confirmation": False,
            "missing_fields": [],
        }
        return {k: v for k, v in payload.items() if v is not None and v != []}

    _GENERIC_CAL_TITLES = frozenset(
        {"cita", "reunion", "reunión", "evento", "encuentro"}
    )

    # v0.21.7c — Preposiciones/conectores que dejan el título "colgado" si son
    # la última palabra: «cita con», «reunión en», «evento de», …
    _FRAGMENTARY_TITLE_TAIL_RE = re.compile(
        r"\b(con|sin|para|en|al|del|de|por|hasta|desde|entre|hacia|sobre|tras|"
        r"durante|segun|según)\s*$",
        flags=re.IGNORECASE,
    )

    def _is_generic_calendar_title(self, title: str) -> bool:
        t = _strip_accents((title or "").strip().lower())
        return t.replace("ñ", "n") in {"cita", "reunion", "evento", "encuentro"}

    def _is_fragmentary_calendar_title(self, title: str) -> bool:
        """True si el título queda colgado en una preposición/conector,
        p.ej. «cita con», «reunión en», «evento de». v0.21.7c."""
        t = (title or "").strip()
        if not t:
            return False
        return bool(self._FRAGMENTARY_TITLE_TAIL_RE.search(t))

    def _fragmentary_title_tail(self, title: str) -> str | None:
        """Devuelve la preposición/conector final del título fragmentario, o
        None si no lo es."""
        m = self._FRAGMENTARY_TITLE_TAIL_RE.search((title or "").strip())
        return m.group(1).lower() if m else None

    def _ack_calendar_with_missing(
        self,
        payload: dict[str, Any],
        raw: str,
        *,
        missing_participants: bool,
        missing_location: bool,
    ) -> str:
        msg = self._saved_calendar_ack(payload, raw)
        if not (missing_participants or missing_location):
            return msg
        # _saved_calendar_ack ya añade los avisos cuando hay date+time; si no, los añadimos aquí.
        if "No tengo guardado" in msg:
            return msg
        adds: list[str] = []
        if missing_participants:
            adds.append("No tengo guardado con quién es.")
        if missing_location:
            adds.append("No tengo guardado el lugar.")
        return msg + " " + " ".join(adds)

    def _unified_handle_note(
        self, raw: str, unified: dict[str, Any]
    ) -> tuple[str, str, str | dict | None, None]:
        note = unified.get("note") or {}
        content = str(note.get("content") or "").strip()
        gpt_title = str(note.get("title") or "").strip() if note.get("title") else ""
        conf = float(unified.get("confidence", 0))

        # v0.21.10 — Blindaje: si GPT devuelve un content que en realidad es
        # un sustantivo funcional aislado ("nota", "una nota", "apunte",
        # "anotación", "tarea"), NO confirmamos: abrimos pending estructurada
        # de nota para que el usuario aporte título o contenido real.
        if content and _bare_intent_kind(content) is not None:
            logger.info(
                "v0.21.10: create_note con content basura (%r) → pending estructurada",
                content[:40],
            )
            return self._open_note_pending(raw)

        # v0.21.4d — Si GPT no devuelve contenido, abrimos pending estructurada
        # de nota en lugar de pedir como consulta libre.
        if not content:
            action = self._minimal_note_pending_payload(raw)
            self._pending.save_pending_action(action)
            return (
                "¿Qué título o contenido quieres guardar como nota?",
                "ambiguo",
                None,
                None,
            )

        # v0.21.4d — Si el mensaje parece SOLO un tema/título (aunque GPT haya
        # rellenado content), tratamos el texto como TÍTULO y pedimos contenido.
        if self._looks_like_topic_only(raw):
            inferred = self._infer_title_from_topic(raw) or self._capitalize_title(content)
            pending = self._minimal_note_pending_payload(raw)
            pending["title"] = self._capitalize_title(inferred or content)
            pending["content"] = None
            pending["missing_fields"] = ["content"]
            self._pending.save_pending_action(pending)
            return (
                self._note_pending_question_for_missing(pending),
                "ambiguo",
                None,
                None,
            )

        if conf < 0.70:
            msg = (
                unified.get("clarification_question")
                or f"¿Quieres que lo guarde como nota: «{content}»?"
            )
            self._pending.save_pending_action(
                {
                    "original_text": raw,
                    "suggested_intent": "nota",
                    "clean_content": content,
                    "confidence": conf,
                    "created_at": _utc_iso(),
                }
            )
            return (msg, "ambiguo", None, None)

        title = self._capitalize_title(gpt_title) if gpt_title else None
        polished_content = self._polish_user_content(content)
        payload: dict[str, Any] = {
            "title": title or None,
            "content": polished_content,
        }
        label = title or polished_content
        return (f"He guardado la nota «{label}».", "nota", payload, None)

    def _unified_handle_task(
        self, raw: str, unified: dict[str, Any]
    ) -> tuple[str, str, str | dict | None, None]:
        task = unified.get("task") or {}
        title = (task.get("title") or "").strip() if task.get("title") else ""

        # v0.21.10 — Blindaje: si GPT devuelve title basura ("tarea", "una
        # tarea", "pendiente"), abrimos pending estructurada de tarea.
        if title and _bare_intent_kind(title) == "task":
            logger.info(
                "v0.21.10: create_task con title basura (%r) → pending estructurada",
                title[:40],
            )
            return self._open_task_pending(raw)

        if not title:
            # v0.21.10 — Sin título, abrimos pending estructurada (no pregunta suelta).
            return self._open_task_pending(raw)
        conf = float(unified.get("confidence", 0))
        if conf < 0.70:
            msg = (
                unified.get("clarification_question")
                or f"¿Quieres que lo guarde como tarea: «{title}»?"
            )
            self._pending.save_pending_action(
                {
                    "original_text": raw,
                    "suggested_intent": "tarea",
                    "clean_content": title,
                    "date_text": task.get("date_text"),
                    "time_text": task.get("time_text"),
                    "confidence": conf,
                    "created_at": _utc_iso(),
                }
            )
            return (msg, "ambiguo", None, None)

        date_text = (task.get("date_text") or "").strip() if task.get("date_text") else ""
        time_text = (task.get("time_text") or "").strip() if task.get("time_text") else ""
        priority = (task.get("priority") or "").strip() if task.get("priority") else ""

        parts = [f"He creado la tarea «{title}»"]
        if date_text:
            parts.append(f"para {date_text}")
        if time_text:
            tt_disp = self._display_time_text(time_text, raw) or time_text
            parts.append(f"a las {tt_disp}")
        reply = " ".join(parts) + "."

        store_payload: str | dict[str, Any]
        if date_text or time_text or priority:
            store_payload = {
                "title": title,
                "date_text": date_text or None,
                "time_text": time_text or None,
                "priority": priority or None,
            }
        else:
            store_payload = title
        return (reply, "tarea", store_payload, None)

    def _unified_handle_calendar_create(
        self, raw: str, unified: dict[str, Any]
    ) -> tuple[str, str, str | dict | None, None]:
        ev = unified.get("calendar_event") or {}
        title = (ev.get("title") or "").strip() if ev.get("title") else ""
        date_text = (ev.get("date_text") or "").strip() if ev.get("date_text") else ""
        _tt_src = ev.get("time_text")
        time_text = ""
        if _tt_src is not None and str(_tt_src).strip():
            time_text = (
                _calendar_time_text_after_user_message(raw, _tt_src) or str(_tt_src)
            ).strip()
        location = (ev.get("location") or "").strip() if ev.get("location") else ""
        participants = list(ev.get("participants") or [])
        conf = float(unified.get("confidence", 0))

        # v0.21.10 — Blindaje: si title es un sustantivo bare ("cita", "evento",
        # "reunión") Y no hay datos reales (fecha/hora/lugar/personas),
        # abrimos pending de calendario estructurada. No guardamos basura.
        if (
            title
            and _bare_intent_kind(title) == "calendar"
            and not date_text
            and not time_text
            and not location
            and not participants
        ):
            logger.info(
                "v0.21.10: create_calendar_event con title bare (%r) y sin datos → pending",
                title[:40],
            )
            return self._open_calendar_pending(raw)

        if not title:
            # v0.21.7b — Si hay datos útiles (date/time/location/participants/description),
            # NO devolvemos una pregunta suelta: abrimos pending de calendario enriquecida
            # con los slots ya recogidos. Sin pending, el siguiente mensaje del usuario
            # iría al motor unificado y, con un `focused_event_id` previo, podría
            # interpretarse como `update_calendar_event` sobre otro evento.
            description = (ev.get("description") or "").strip() if ev.get("description") else ""
            has_useful = bool(
                date_text or time_text or location or participants or description
            )
            if has_useful:
                action = self._unified_pending_payload(raw, ev)
                self._pending.save_pending_action(action)
                logger.info(
                    "v0.21.7b: create_calendar_event sin título con datos parciales; "
                    "pending creada (missing=%s)",
                    action.get("missing_fields"),
                )
                msg = self._calendar_pending_question_for_missing(action)
                return (msg, "ambiguo", None, None)
            msg = (
                unified.get("clarification_question")
                or "¿Qué evento quieres anotar?"
            )
            return (msg, "consulta", None, None)

        # A. Sin día: nunca guardar.
        if not date_text:
            self._pending.save_pending_action(self._unified_pending_payload(raw, ev))
            # v0.21.4b/c — Pregunta comprensiva (propia, no la de GPT) cuando además
            # faltan hora y lugar/persona y el título es genérico. Evita preguntas
            # parciales tipo "¿Para cuándo deseas agendar la cita?".
            generic = self._is_generic_calendar_title(title)
            wide_open = generic and not time_text and not location and not participants
            if wide_open:
                msg = f"¿Para qué día, a qué hora y con quién o dónde es la {title}?"
            else:
                msg = (
                    unified.get("clarification_question")
                    or f"¿Qué día es «{title}»?"
                )
            return (msg, "ambiguo", None, None)

        # B. Sin hora: si parece cita/reunión/visita, pedir hora.
        if not time_text:
            if self._appointment_like(title, ev) or self._is_generic_calendar_title(title):
                msg = (
                    unified.get("clarification_question")
                    or f"Tengo «{title}» para {date_text}. ¿A qué hora es?"
                )
                self._pending.save_pending_action(self._unified_pending_payload(raw, ev))
                return (msg, "ambiguo", None, None)
            # tarea/visita ligera: permitir guardar sin hora si confianza alta
            if conf < 0.80:
                msg = (
                    unified.get("clarification_question")
                    or f"He entendido «{title}» para {date_text}. ¿A qué hora, o es para todo el día?"
                )
                self._pending.save_pending_action(self._unified_pending_payload(raw, ev))
                return (msg, "ambiguo", None, None)
            payload = self._unified_payload_from_event(raw, ev, conf)
            return (
                self._saved_calendar_ack(payload, raw),
                "calendario",
                payload,
                None,
            )

        # C. Título genérico + sin location y sin participantes: pedir.
        generic = self._is_generic_calendar_title(title)
        has_loc = bool(location)
        has_part = bool(participants)
        if generic and not has_loc and not has_part:
            msg = (
                unified.get("clarification_question")
                or f"Tengo día y hora: {date_text} a las {self._display_time_text(time_text, raw) or time_text}. ¿Con quién o dónde es la {title}?"
            )
            self._pending.save_pending_action(self._unified_pending_payload(raw, ev))
            return (msg, "ambiguo", None, None)

        if conf < 0.80:
            tt_disp = self._display_time_text(time_text, raw) or time_text
            msg = (
                unified.get("clarification_question")
                or f"He entendido «{title}» para {date_text} a las {tt_disp}. ¿Lo guardo?"
            )
            self._pending.save_pending_action(self._unified_pending_payload(raw, ev))
            return (msg, "ambiguo", None, None)

        payload = self._unified_payload_from_event(raw, ev, conf)
        reply = self._ack_calendar_with_missing(
            payload,
            raw,
            missing_participants=not has_part,
            missing_location=not has_loc,
        )
        return (reply, "calendario", payload, None)

    def _resolve_target_reference(
        self, ref: str | None, terms_text: str
    ) -> dict[str, Any] | None:
        if ref == "focused_event":
            return self._events.get_focused_event()
        if ref == "last_event":
            return self._events.get_last_event()
        if ref == "matching_event":
            cand = self._events.search_events(terms_text or "", limit=1)
            return cand[0] if cand else None
        return None

    # ------------------------------------------------------------------
    # v0.21.5 — Síntesis inferencial de agenda.
    # ------------------------------------------------------------------

    def _synthesize_day_agenda(
        self,
        raw: str,
        day_label: str,
        day_hints: list[str],
    ) -> tuple[str, str, None, None]:
        """
        Sintetiza la respuesta a "qué tengo {día}".

        - Toma TODOS los eventos del día (incluidas las entradas «pregunta-like»
          para que el motor pueda marcarlas como sospechosas).
        - Si solo hay 0/1 evento real, responde con el formato simple anterior.
        - Si hay varios, llama al motor de razonamiento estructurado
          `try_agenda_context_reasoning`. Si éste pide `request_more_data`,
          amplía la ventana de candidatos UNA vez (toda la agenda) y reintenta.
        - Si GPT no responde o no es útil, usa el fallback local determinista
          que agrupa duplicados, marca solapamientos y separa sospechosas.

        Nunca borra ni fusiona eventos.
        """
        # 1) Candidatos del día (incluye question-like para reportarlas como sospechosas).
        day_events: list[dict[str, Any]] = []
        seen: set[str] = set()
        for h in day_hints:
            for ev in self._events.events_for_day_hint(h, include_question_like=True):
                eid = str(ev.get("id") or "")
                key = eid or f"{ev.get('title')}|{ev.get('time_text')}|{ev.get('date_text')}"
                if key in seen:
                    continue
                seen.add(key)
                day_events.append(ev)

        real_events = [e for e in day_events if not EventsStore.is_question_like(e)]
        suspicious = [e for e in day_events if EventsStore.is_question_like(e)]

        logger.info(
            "v0.21.5 síntesis día=%s: candidatos=%d (reales=%d, sospechosos=%d)",
            day_label,
            len(day_events),
            len(real_events),
            len(suspicious),
        )

        # 2) Sin eventos: respuesta clara.
        if not real_events and not suspicious:
            ans = f"No tienes eventos guardados para {day_label}."
            self._save_agenda_context(
                last_operation="query_calendar",
                last_topic=f"eventos de {day_label}",
                last_answer_summary=ans,
                candidate_events=[],
            )
            return (ans, "consulta", None, None)

        # 3) 1 evento real → respuesta directa simple, sin lista cruda.
        if len(real_events) == 1 and not suspicious:
            only = real_events[0]
            if only.get("id"):
                self._events.set_focused_event_id(str(only["id"]))
            ans = self._single_event_day_reply(only, day_label, raw)
            self._save_agenda_context(
                last_operation="query_calendar",
                last_topic=f"eventos de {day_label}",
                last_answer_summary=ans,
                candidate_events=[only],
            )
            return (ans, "consulta", None, None)

        # 4) Varios eventos o sospechosos → síntesis GPT estructurado o fallback local.
        ans, has_dups, has_conflicts = self._synthesize_with_motor(
            raw=raw,
            day_label=day_label,
            day_events=day_events,
            real_events=real_events,
            suspicious=suspicious,
        )
        # foco en el último evento real, por compatibilidad con flujos existentes.
        if real_events and real_events[-1].get("id"):
            self._events.set_focused_event_id(str(real_events[-1]["id"]))
        self._save_agenda_context(
            last_operation="query_calendar",
            last_topic=f"eventos de {day_label}",
            last_answer_summary=ans,
            candidate_events=day_events,
            duplicates_pending=has_dups,
            conflicts_pending=has_conflicts,
        )
        return (ans, "consulta", None, None)

    def _synthesize_with_motor(
        self,
        *,
        raw: str,
        day_label: str,
        day_events: list[dict[str, Any]],
        real_events: list[dict[str, Any]],
        suspicious: list[dict[str, Any]],
    ) -> tuple[str, bool, bool]:
        """Devuelve (answer, duplicates_pending, conflicts_pending)."""
        focused = self._events.get_focused_event()
        last_ctx = {
            "last_operation": "query_calendar",
            "last_topic": f"eventos de {day_label}",
            "last_answer_summary": None,
            "has_pending_action": False,
        }
        packet = build_agenda_context_packet(
            user_text=raw,
            events=day_events,
            focused_event=focused,
            last_agenda_context=last_ctx,
            max_relevant_events=max(8, len(day_events)),
            user_id=DEFAULT_USER_ID,
        )
        result = try_agenda_context_reasoning(packet)

        # 4.a) request_more_data → un único reintento con toda la agenda local.
        if result is not None and result.get("operation") == "request_more_data":
            logger.info(
                "v0.21.5 síntesis: GPT pidió request_more_data; reintentando con toda la agenda."
            )
            all_events = self._events.get_events() or []
            extended = list(day_events)
            seen_ids = {str(e.get("id")) for e in extended if e.get("id")}
            for ev in all_events:
                if not isinstance(ev, dict):
                    continue
                eid = str(ev.get("id") or "")
                if eid and eid in seen_ids:
                    continue
                extended.append(ev)
                seen_ids.add(eid)
            packet2 = build_agenda_context_packet(
                user_text=raw,
                events=extended,
                focused_event=focused,
                last_agenda_context=last_ctx,
                max_relevant_events=max(16, len(extended)),
                user_id=DEFAULT_USER_ID,
            )
            retry = try_agenda_context_reasoning(packet2)
            if retry is not None:
                result = retry

        if result is not None:
            op = result.get("operation")
            answer = (result.get("answer") or "").strip()
            groups = result.get("detected_groups") or []
            conflicts = result.get("conflicts") or []
            susp = result.get("suspicious_entries") or []
            has_dups = bool(isinstance(groups, list) and len(groups) > 0)
            has_conflicts = bool(isinstance(conflicts, list) and len(conflicts) > 0)
            logger.info(
                "v0.21.5 síntesis: operation=%s grupos=%d conflictos=%d sospechosos=%d",
                op,
                len(groups) if isinstance(groups, list) else 0,
                len(conflicts) if isinstance(conflicts, list) else 0,
                len(susp) if isinstance(susp, list) else 0,
            )
            if op in (
                "query_agenda",
                "summarize_agenda",
                "restructure_agenda",
                "ask_clarification",
            ) and answer:
                # Si hay duplicados/conflictos y la respuesta no pregunta,
                # añadimos sugerencia de revisión.
                if (has_dups or has_conflicts) and "?" not in answer:
                    answer = (
                        answer.rstrip(".")
                        + ". ¿Quieres que revisemos cuál debe quedar?"
                    )
                return (answer, has_dups, has_conflicts)
            if op == "request_more_data":
                return (
                    (
                        f"Para {day_label} veo varias entradas y necesito un detalle "
                        "más para resumirlas. ¿Quieres que mire un día concreto u "
                        "otra cita en particular?"
                    ),
                    False,
                    False,
                )

        # 4.b) Fallback local: agrupar duplicados, detectar solapamientos, separar sospechosos.
        return self._local_day_synthesis(
            day_label=day_label,
            real_events=real_events,
            suspicious=suspicious,
        )

    def _single_event_day_reply(
        self, ev: dict[str, Any], day_label: str, raw: str
    ) -> str:
        title = str(ev.get("title") or "Evento").strip()
        tt_raw = ev.get("time_text")
        tt = self._display_time_text(tt_raw, raw) if tt_raw else None
        if tt:
            return f"Para {day_label} tienes {title.lower()} a las {tt}."
        return f"Para {day_label} tienes {title.lower()}."

    @staticmethod
    def _short_title(ev: dict[str, Any]) -> str:
        title = str(ev.get("title") or "Evento").strip()
        # Limpia palabras de "ruido" del título para la síntesis: hora interna,
        # "mañana" / "hoy" / día de la semana al final, y conectores sueltos.
        cleaned = title
        cleaned = re.sub(
            r"\s*\ba\s+las?\s+\d{1,2}([:.]\d{2})?\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\b\d{1,2}[:.]\d{2}\b", "", cleaned)
        cleaned = re.sub(
            r"\b(hoy|ma[nñ]ana|pasado\s+ma[nñ]ana|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;:")
        if not cleaned:
            cleaned = title
        return cleaned[:80]

    def _local_day_synthesis(
        self,
        *,
        day_label: str,
        real_events: list[dict[str, Any]],
        suspicious: list[dict[str, Any]],
    ) -> tuple[str, bool, bool]:
        """Síntesis determinista cuando no hay GPT.
        Agrupa duplicados por (título normalizado, hora normalizada). Detecta
        solapamientos por misma hora con títulos distintos. Marca sospechosos."""
        # Agrupar duplicados.
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        # Mantenemos el orden de aparición para ofrecer una respuesta estable.
        order: list[tuple[str, str]] = []
        for ev in real_events:
            tnorm = EventsStore.normalize_title_text(ev.get("title"))
            hnorm = EventsStore.normalize_time_text(ev.get("time_text"))
            key = (tnorm, hnorm)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(ev)

        if not order and suspicious:
            return (
                (
                    f"Para {day_label} no veo eventos claros, solo "
                    f"{len(suspicious)} entrada(s) que parecen preguntas "
                    "guardadas por error. ¿Quieres que revisemos cuál debe quedar?"
                ),
                False,
                False,
            )

        descriptions: list[str] = []
        duplicate_warnings: list[str] = []
        # Solapamientos por hora con títulos distintos.
        by_time: dict[str, set[str]] = {}
        for (tnorm, hnorm), items in groups.items():
            display_title = self._short_title(items[0]).lower()
            if hnorm:
                # `hnorm` ya está en formato HH:MM compacto. Lo usamos como hora.
                pretty_time = hnorm
                desc = f"{display_title} a las {pretty_time}"
                descriptions.append(desc)
                if len(items) > 1:
                    duplicate_warnings.append(
                        f"{len(items)} entradas que parecen referirse a "
                        f"{display_title} a las {pretty_time}"
                    )
                by_time.setdefault(hnorm, set()).add(display_title)
            else:
                descriptions.append(display_title)
                if len(items) > 1:
                    duplicate_warnings.append(
                        f"{len(items)} entradas que parecen referirse a {display_title}"
                    )

        conflict_notes: list[str] = []
        for hnorm, titles in by_time.items():
            if len(titles) > 1:
                conflict_notes.append(
                    "posible solapamiento a las "
                    + hnorm
                    + ": "
                    + " y ".join(sorted(titles))
                )

        # Construir respuesta.
        parts: list[str] = []
        if len(descriptions) == 1:
            parts.append(f"Para {day_label} veo {descriptions[0]}")
        else:
            head = ", ".join(descriptions[:-1])
            tail = descriptions[-1]
            parts.append(f"Para {day_label} veo {head} y {tail}")

        extras: list[str] = []
        if duplicate_warnings:
            extras.append("Hay " + "; y ".join(duplicate_warnings))
        if conflict_notes:
            extras.append("Detecto " + "; ".join(conflict_notes))
        if suspicious:
            extras.append(
                f"Además hay {len(suspicious)} entrada(s) que parecen "
                "preguntas guardadas por error"
            )

        msg = ". ".join([p.rstrip(".") for p in parts + extras if p]) + "."
        has_dups = bool(duplicate_warnings)
        has_conflicts = bool(conflict_notes)
        if has_dups or has_conflicts:
            msg += " ¿Quieres que revisemos cuál debe quedar?"
        return (msg, has_dups, has_conflicts)

    def _unified_handle_calendar_query(
        self, raw: str, unified: dict[str, Any]
    ) -> tuple[str, str, None, None]:
        all_ev = self._events.get_events()
        if not all_ev:
            self._save_agenda_context(
                last_operation="query_calendar",
                last_topic=raw[:120],
                last_answer_summary="No hay eventos guardados.",
                candidate_events=[],
            )
            return (
                "No tienes eventos guardados en la agenda local.",
                "consulta",
                None,
                None,
            )

        cq = unified.get("calendar_query") or {}
        terms = [str(t).strip() for t in (cq.get("terms") or []) if str(t).strip()]
        date_t = (cq.get("date_text") or "").strip() if cq.get("date_text") else ""
        terms_text = " ".join(terms + ([date_t] if date_t else []) + [raw]).strip()

        # 1. Pregunta sobre día → síntesis inferencial (v0.21.5).
        if date_t and self._day_hints_in_message(date_t):
            hints = self._day_hints_in_message(date_t)
            label = self._day_hint_display(hints[0])
            return self._synthesize_day_agenda(raw, label, hints)

        # 2. Construir candidatos: foco/último/búsqueda.
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        ref = cq.get("target_reference")
        ref_event = self._resolve_target_reference(ref, terms_text)
        if ref_event:
            eid = str(ref_event.get("id", ""))
            if eid:
                seen.add(eid)
                candidates.append(ref_event)
        for term in terms:
            for ev in self._events.search_events(term, limit=5):
                eid = str(ev.get("id", ""))
                if eid and eid not in seen and not EventsStore.is_question_like(ev):
                    seen.add(eid)
                    candidates.append(ev)
        if not candidates:
            for ev in self._events.search_events(raw, limit=5):
                eid = str(ev.get("id", ""))
                if eid and eid not in seen and not EventsStore.is_question_like(ev):
                    seen.add(eid)
                    candidates.append(ev)
        # Si seguimos sin candidatos, prueba foco/último como respaldo.
        if not candidates:
            for ev in (self._events.get_focused_event(), self._events.get_last_event()):
                if ev and not EventsStore.is_question_like(ev):
                    eid = str(ev.get("id", ""))
                    if eid and eid not in seen:
                        seen.add(eid)
                        candidates.append(ev)

        focused = self._events.get_focused_event()

        resolved = try_resolve_calendar_query(raw, cq, candidates, focused)
        if resolved is not None:
            result = resolved["result"]
            if result == "answer":
                sid = resolved.get("selected_event_id")
                if sid:
                    self._events.set_focused_event_id(str(sid))
                ans = resolved.get("answer") or "No tengo más información."
                self._save_agenda_context(
                    last_operation="query_calendar",
                    last_topic=raw[:120],
                    last_answer_summary=ans,
                    candidate_events=candidates,
                )
                return (ans, "consulta", None, None)
            if result == "multiple_matches":
                ans = resolved.get("answer") or self._agenda_reply_multiple_clarify(
                    candidates
                )
                self._save_agenda_context(
                    last_operation="query_calendar",
                    last_topic=raw[:120],
                    last_answer_summary=ans,
                    candidate_events=candidates,
                )
                return (ans, "consulta", None, None)
            if result == "not_found":
                ans = resolved.get("answer") or "No encuentro ese evento en tu agenda local."
                self._save_agenda_context(
                    last_operation="query_calendar",
                    last_topic=raw[:120],
                    last_answer_summary=ans,
                    candidate_events=candidates,
                )
                return (ans, "consulta", None, None)
            if result == "needs_clarification":
                ans = resolved.get("answer") or "¿Puedes concretar a qué evento te refieres?"
                self._save_agenda_context(
                    last_operation="query_calendar",
                    last_topic=raw[:120],
                    last_answer_summary=ans,
                    candidate_events=candidates,
                )
                return (ans, "consulta", None, None)

        # Fallback local determinista si OpenAI no responde.
        if not candidates:
            ans = "No encuentro ese evento en tu agenda local."
            self._save_agenda_context(
                last_operation="query_calendar",
                last_topic=raw[:120],
                last_answer_summary=ans,
                candidate_events=[],
            )
            return (ans, "consulta", None, None)
        if len(candidates) > 1:
            ans = self._agenda_reply_multiple_clarify(candidates)
            self._save_agenda_context(
                last_operation="query_calendar",
                last_topic=raw[:120],
                last_answer_summary=ans,
                candidate_events=candidates,
            )
            return (ans, "consulta", None, None)
        target = candidates[0]
        if target.get("id"):
            self._events.set_focused_event_id(str(target["id"]))
        field = self._map_requested_field(raw, {"requested_field": cq.get("requested_field")})
        last_ref = self._references_last_event(raw)
        reply = self._reply_query_with_field(raw, target, field, last_ref=last_ref)
        self._save_agenda_context(
            last_operation="query_calendar",
            last_topic=raw[:120],
            last_answer_summary=reply,
            candidate_events=[target],
        )
        return (reply, "consulta", None, None)

    def _unified_handle_calendar_update(
        self, raw: str, unified: dict[str, Any]
    ) -> tuple[str, str, None, None]:
        # v0.21.9 — Bloqueo determinista: si el mensaje menciona explícitamente
        # "tarea/nota" y NO menciona "evento/cita/reunión/calendario", no
        # ejecutamos update_calendar_event aunque el motor unificado lo
        # proponga. El motor puede engañarse cuando hay un focused_event_id
        # antiguo y el usuario aclara que se refería a otra entidad.
        if self._mentions_task_or_note_only(raw):
            focus = self._current_focus()
            kind = focus.get("last_focused_kind")
            eid = focus.get("last_focused_id")
            label = (focus.get("last_focused_label") or "").strip()
            logger.info(
                "v0.21.9: update_calendar_event bloqueado por mención exclusiva "
                "de tarea/nota; foco kind=%s id=%s",
                kind,
                (str(eid)[:8] if eid else None),
            )
            if self._mentions_task_only(raw) and kind == "task" and eid:
                task = self._tasks.get_task_by_id(str(eid))
                title = (task.get("title") if task else label) or label or "tarea"
                return self._open_task_description_pending(raw, str(eid), title)
            if self._mentions_task_only(raw):
                return (
                    "No tengo una tarea reciente clara. ¿A qué tarea te refieres?",
                    "consulta",
                    None,
                    None,
                )
            if self._mentions_note_only(raw):
                return (
                    "No tengo una nota reciente clara para aplicar ese cambio.",
                    "consulta",
                    None,
                    None,
                )

        # v0.21.5b — Salvavidas: si la conversación viene de una respuesta de
        # agenda con duplicados/conflictos pendientes, no aplicamos updates por
        # mucho que el motor unificado lo proponga. Esto bloquea el caso real
        # de "mantén solo la cita con el médico" → motor → update_calendar_event.
        ctx = self._events.get_last_agenda_context(user_id=DEFAULT_USER_ID)
        if ctx and (ctx.get("duplicates_pending") or ctx.get("conflicts_pending")):
            logger.info(
                "v0.21.5b: update_calendar_event bloqueado porque hay "
                "duplicates_pending=%s / conflicts_pending=%s",
                bool(ctx.get("duplicates_pending")),
                bool(ctx.get("conflicts_pending")),
            )
            msg = (
                "Antes de modificar nada, conviene resolver los duplicados o "
                "solapamientos que vimos. No voy a editar eventos sin una "
                "limpieza confirmada paso a paso. ¿Quieres que primero "
                "revisemos cuál debe quedar?"
            )
            return (msg, "consulta", None, None)

        cup = unified.get("calendar_update") or {}
        target: dict[str, Any] | None = None
        tid = cup.get("target_event_id")
        if tid:
            target = self._events.get_event_by_id(str(tid))
        if target is None:
            target = self._resolve_target_reference(
                cup.get("target_reference"),
                " ".join(str(v) for v in (cup.get("updates") or {}).values() if v),
            )
        if target is None and self._references_last_event(raw):
            target = self._events.get_last_event()
        if target is None:
            cand = self._events.search_events(raw, limit=3)
            cand = [c for c in cand if not EventsStore.is_question_like(c)]
            if len(cand) == 1:
                target = cand[0]
        if target is None or not target.get("id"):
            return (
                "No sé a qué evento te refieres. ¿Puedes decirme cuál quieres actualizar?",
                "consulta",
                None,
                None,
            )

        upd_raw = cup.get("updates") or {}
        updates = self._updates_from_event_data(upd_raw)
        if not updates:
            return (
                unified.get("clarification_question") or "No he captado qué quieres cambiar.",
                "consulta",
                None,
                None,
            )
        updated = self._events.update_event(str(target["id"]), updates)
        if not updated:
            return ("No he podido actualizar ese evento.", "consulta", None, None)
        self._events.set_focused_event_id(str(updated["id"]))
        ack = self._updated_event_ack(updated, raw)
        self._save_agenda_context(
            last_operation="update_calendar_event",
            last_topic=raw[:120],
            last_answer_summary=ack,
            candidate_events=[updated],
            focused_event_id=str(updated["id"]),
        )
        return (ack, "consulta", None, None)

    def _unified_handle_clarification(
        self, raw: str, unified: dict[str, Any]
    ) -> tuple[str, str, str | dict | None, str | None]:
        # v0.21.4b/c — Si el mensaje tiene clara intención de calendario, no
        # perdemos el hilo: guardamos una pending mínima y usamos SIEMPRE la
        # pregunta comprensiva (no la de GPT, que suele ser parcial).
        if _is_bare_calendar_intent(raw):
            return self._open_calendar_pending(raw)
        # v0.21.4d — Salvavidas para notas: "quiero una nota" → pending nota.
        if _is_bare_note_intent(raw):
            return self._open_note_pending(raw)
        # v0.21.10 — Salvavidas para tareas: "tarea" / "una tarea" → pending tarea.
        if _is_bare_task_intent(raw):
            return self._open_task_pending(raw)
        if _looks_like_calendar_intent(raw):
            action = self._minimal_calendar_pending_payload(raw)
            self._pending.save_pending_action(action)
            logger.info(
                "needs_clarification + intención de calendario: pending mínima creada "
                "(pending_kind=calendar_event_completion, missing=%s)",
                action.get("missing_fields"),
            )
            msg = self._calendar_pending_question_for_missing(action)
            return (msg, "ambiguo", None, None)

        msg = (
            unified.get("clarification_question")
            or "¿Puedes concretar un poco más?"
        )
        return (msg, "consulta", None, None)

    def _unified_handle_general(
        self, raw: str, unified: dict[str, Any]
    ) -> tuple[str, str, str | dict | None, str | None]:
        # v0.21.4c — Salvavidas: si el motor unificado declara general_query pero
        # el mensaje es claramente "agéndame una cita" sin datos, no caemos a GPT
        # general; abrimos pending de calendario y preguntamos lo que falta.
        if _is_bare_calendar_intent(raw):
            logger.info(
                "general_query con intención clara de calendario: pending mínima creada."
            )
            return self._open_calendar_pending(raw)
        # v0.21.4d — Salvavidas equivalente para notas.
        if _is_bare_note_intent(raw):
            logger.info(
                "general_query con intención clara de nota: pending mínima creada."
            )
            return self._open_note_pending(raw)
        # v0.21.10 — Salvavidas equivalente para tareas.
        if _is_bare_task_intent(raw):
            logger.info(
                "general_query con intención clara de tarea: pending mínima creada."
            )
            return self._open_task_pending(raw)
        reply = try_consult_response(raw)
        if reply:
            return (reply, "consulta", None, None)
        return (self._CONSULTA_LOCAL, "consulta", None, None)

    def _open_calendar_pending(
        self, raw: str
    ) -> tuple[str, str, None, None]:
        """Abre una pending_action mínima de calendario y devuelve la pregunta
        comprensiva. Compartido por la intercepción temprana y el salvavidas
        post-motor."""
        action = self._minimal_calendar_pending_payload(raw)
        self._pending.save_pending_action(action)
        logger.info(
            "Pending calendario mínima creada (raw=%r, missing=%s)",
            raw[:80],
            action.get("missing_fields"),
        )
        msg = self._calendar_pending_question_for_missing(action)
        return (msg, "ambiguo", None, None)

    def _dispatch_unified_motor(
        self, raw: str, unified: dict[str, Any]
    ) -> tuple[str, str, str | dict | None, str | None]:
        op = unified["operation"]
        if op == "create_note":
            return self._unified_handle_note(raw, unified)
        if op == "create_task":
            return self._unified_handle_task(raw, unified)
        if op == "create_calendar_event":
            return self._unified_handle_calendar_create(raw, unified)
        if op == "query_calendar":
            return self._unified_handle_calendar_query(raw, unified)
        if op == "update_calendar_event":
            return self._unified_handle_calendar_update(raw, unified)
        if op == "needs_clarification":
            return self._unified_handle_clarification(raw, unified)
        return self._unified_handle_general(raw, unified)

    # ------------------------------------------------------------------
    # v0.21.3 — Helpers de contexto operativo de agenda (follow-ups).
    # ------------------------------------------------------------------

    def _save_agenda_context(
        self,
        *,
        last_operation: str,
        last_topic: str | None,
        last_answer_summary: str,
        candidate_events: list[dict[str, Any]] | None = None,
        focused_event_id: str | None = None,
        duplicates_pending: bool = False,
        conflicts_pending: bool = False,
    ) -> None:
        cand_ids = [
            str(e.get("id"))
            for e in (candidate_events or [])
            if isinstance(e, dict) and e.get("id")
        ]
        fe_id = focused_event_id
        if fe_id is None:
            fe_id = self._events.get_focused_event_id()
        try:
            self._events.set_last_agenda_context(
                user_id=DEFAULT_USER_ID,
                last_operation=last_operation,
                last_topic=last_topic,
                last_answer_summary=last_answer_summary,
                candidate_event_ids=cand_ids,
                focused_event_id=fe_id,
                duplicates_pending=duplicates_pending,
                conflicts_pending=conflicts_pending,
            )
            logger.debug(
                "agenda_context guardado: op=%s candidatos=%d focused=%s",
                last_operation,
                len(cand_ids),
                bool(fe_id),
            )
        except Exception:
            logger.exception("No se pudo guardar last_agenda_context")

    def _agenda_followup_candidate_events(
        self, ctx: dict[str, Any]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for eid in ctx.get("candidate_event_ids") or []:
            sid = str(eid).strip()
            if not sid or sid in seen:
                continue
            ev = self._events.get_event_by_id(sid)
            if ev and not EventsStore.is_question_like(ev):
                seen.add(sid)
                out.append(ev)
        if not out:
            # Respaldo: cola de la agenda (eventos más recientes), saltando preguntas guardadas.
            for ev in (self._events.get_events() or [])[-8:]:
                if isinstance(ev, dict) and not EventsStore.is_question_like(ev):
                    sid = str(ev.get("id") or "")
                    if sid and sid not in seen:
                        seen.add(sid)
                        out.append(ev)
        return out

    def _handle_agenda_followup(
        self, raw: str
    ) -> tuple[str, str, str | dict | None, str | None] | None:
        """
        Maneja un follow-up del usuario sobre la última respuesta de agenda.
        Devuelve la respuesta lista o None si decide no responder por esta vía.
        """
        ctx = self._events.get_last_agenda_context(user_id=DEFAULT_USER_ID)
        if not ctx:
            logger.info("Follow-up de agenda detectado, pero NO hay contexto reciente.")
            return (
                "No tengo una respuesta de agenda reciente que reestructurar. "
                "¿Quieres que revise tu agenda?",
                "consulta",
                None,
                None,
            )

        candidates = self._agenda_followup_candidate_events(ctx)
        focused = self._events.get_focused_event()
        last_agenda_context = {
            "last_operation": ctx.get("last_operation"),
            "last_topic": ctx.get("last_topic"),
            "last_answer_summary": ctx.get("last_answer_summary"),
            "has_pending_action": False,  # llegamos aquí solo si no hay pending_action.
        }

        packet = build_agenda_context_packet(
            user_text=raw,
            events=candidates,
            focused_event=focused,
            last_agenda_context=last_agenda_context,
            user_id=ctx.get("user_id") or DEFAULT_USER_ID,
        )
        logger.info(
            "Follow-up de agenda: enviando ficha (candidatos=%d, focused=%s)",
            len(candidates),
            bool(focused),
        )

        result = try_agenda_context_reasoning(packet)
        if result is None:
            logger.warning(
                "Follow-up de agenda: GPT no disponible o respuesta inválida; "
                "respuesta prudente."
            )
            return (
                "Por ahora no puedo reestructurar esa respuesta. "
                "¿Quieres que vuelva a consultar tu agenda?",
                "consulta",
                None,
                None,
            )

        op = result["operation"]
        answer = (result.get("answer") or "").strip()
        logger.info(
            "Follow-up de agenda: operation=%s conf=%.2f",
            op,
            float(result.get("confidence", 0)),
        )

        if op == "not_calendar":
            logger.info("Follow-up de agenda: GPT declara not_calendar; flujo normal.")
            return None

        if op in ("restructure_agenda", "summarize_agenda"):
            if not answer:
                answer = (
                    "He revisado tu agenda reciente y agrupado posibles duplicados. "
                    "¿Quieres que te diga cuál revisar primero?"
                )
            # Si GPT detecta duplicados/conflictos y no hay pregunta, sugerimos revisar.
            extras = result.get("detected_groups") or result.get("conflicts") or []
            if extras and "?" not in answer:
                answer = answer.rstrip(".") + ". ¿Quieres que revisemos cuál debe quedar?"
            self._save_agenda_context(
                last_operation=op,
                last_topic=ctx.get("last_topic"),
                last_answer_summary=answer,
                candidate_events=candidates,
            )
            return (answer, "consulta", None, None)

        if op == "ask_clarification":
            msg = answer or "¿Puedes concretar qué te gustaría que ajuste de tu agenda?"
            return (msg, "consulta", None, None)

        if op == "request_more_data":
            req = (result.get("data_request") or "").strip()
            missing = result.get("missing_fields") or []
            base = answer or "Necesito un detalle más para reestructurar tu agenda."
            if req:
                base = base.rstrip(".") + f". {req}"
            elif missing:
                base = base.rstrip(".") + " (" + ", ".join(missing) + ")"
            return (base, "consulta", None, None)

        # query_agenda, update_event, create_event u otras dentro del esquema:
        # en v0.21.3 NO ejecutamos cambios desde este flujo. Si hay answer, la
        # devolvemos como resumen prudente; si no, derivamos al flujo normal.
        if answer:
            return (answer, "consulta", None, None)
        logger.info(
            "Follow-up de agenda: operación %s sin answer; se delega al flujo normal.",
            op,
        )
        return None

    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # v0.21.5b — Guard contra modificaciones automáticas tras una respuesta
    # de agenda que detectó duplicados o solapamientos.
    # ------------------------------------------------------------------

    def _duplicate_review_guard(
        self, raw: str
    ) -> tuple[str, str, str | dict | None, str | None] | None:
        """
        Si la última respuesta de agenda marcó duplicados/conflictos pendientes
        y el mensaje actual parece una decisión sobre ellos, responde con un
        mensaje prudente y NO toca datos. Devuelve None si no aplica.
        """
        if not _is_duplicate_review_reply(raw):
            return None
        ctx = self._events.get_last_agenda_context(user_id=DEFAULT_USER_ID)
        if not ctx:
            return None
        if not (ctx.get("duplicates_pending") or ctx.get("conflicts_pending")):
            return None

        n_candidates = len(ctx.get("candidate_event_ids") or [])
        logger.info(
            "v0.21.5b dup_guard: duplicates_pending=%s conflicts_pending=%s "
            "candidatos=%d raw=%r",
            bool(ctx.get("duplicates_pending")),
            bool(ctx.get("conflicts_pending")),
            n_candidates,
            raw[:80],
        )

        msg = (
            "Por ahora no voy a tocar tu agenda local sin una limpieza "
            "confirmada paso a paso. No borro, no fusiono ni edito eventos "
            "para resolver duplicados o solapamientos. Si quieres, abrimos esa "
            "limpieza confirmada como nueva versión (borrado «soft», "
            "reversible). Mientras tanto, puedes editar o eliminar entradas "
            "desde la sección de eventos."
        )
        # Mantenemos la marca de duplicates/conflicts y los ids previos del
        # contexto para que siguientes intentos del usuario sigan cayendo aquí.
        try:
            self._events.set_last_agenda_context(
                user_id=DEFAULT_USER_ID,
                last_operation="query_calendar",
                last_topic=ctx.get("last_topic"),
                last_answer_summary=msg,
                candidate_event_ids=list(ctx.get("candidate_event_ids") or []),
                focused_event_id=ctx.get("focused_event_id"),
                duplicates_pending=bool(ctx.get("duplicates_pending")),
                conflicts_pending=bool(ctx.get("conflicts_pending")),
            )
        except Exception:
            logger.exception("dup_guard: fallo al persistir last_agenda_context")
        return (msg, "consulta", None, None)

    def _process_fresh(self, raw: str) -> tuple[str, str, str | dict | None, str | None]:
        # v0.21.5b — Si la última respuesta de agenda detectó duplicados o
        # solapamientos y propuso revisarlos, las respuestas del usuario tipo
        # "mantén X / borra los duplicados / sí reestructura / hazlo" NO deben
        # alcanzar el motor unificado: éste podría clasificarlas como
        # update_calendar_event y modificar datos sin permiso explícito.
        dup_guard = self._duplicate_review_guard(raw)
        if dup_guard is not None:
            return dup_guard

        # v0.21.9 — Enrutado por foco operativo multi-entidad ANTES del motor
        # unificado. Si el usuario:
        #   a) pide "ponle contenido / añade descripción" sobre lo último, o
        #   b) menciona explícitamente "tarea"/"nota" sin mencionar evento/
        #      cita/reunión/calendario,
        # y el foco actual es una tarea (o una nota), redirigimos sin pasar
        # por el motor unificado. Esto evita que un `focused_event_id` viejo
        # se interprete como `update_calendar_event`.
        focus_route = self._maybe_route_by_focus(raw)
        if focus_route is not None:
            return focus_route

        # v0.21.3 — Antes del motor unificado, intercepta follow-ups de agenda
        # ("reestructúramelo", "ordénamelo", "resúmelo", "quita duplicados", etc.).
        if _is_agenda_followup_message(raw):
            logger.info("Mensaje contextual de agenda detectado: %r", raw[:80])
            followup = self._handle_agenda_followup(raw)
            if followup is not None:
                return followup

        # v0.21.4c — Si el mensaje es claramente "agéndame una cita" pero no aporta
        # fecha, hora, persona ni lugar, NO consultamos GPT: creamos una pending
        # mínima de calendario y preguntamos lo que falta de forma comprensiva.
        # Esto evita que GPT clasifique como general_query y pierda la intención.
        if _is_bare_calendar_intent(raw):
            return self._open_calendar_pending(raw)

        # v0.21.4d — Si el mensaje es claramente "quiero una nota" / "apúntame una
        # nota" sin tema ni contenido, abrimos una pending de nota mínima y
        # pedimos título o contenido. No pasamos por GPT para evitar que invente.
        if _is_bare_note_intent(raw):
            return self._open_note_pending(raw)

        # v0.21.10 — Bare intent de tarea: "tarea" / "una tarea" / "quiero una
        # tarea" / "pendiente". Abre pending de tarea con missing=["title"].
        if _is_bare_task_intent(raw):
            return self._open_task_pending(raw)

        # v0.21.5 — Si el mensaje es claramente "qué tengo {día}" (consulta de
        # agenda sobre un día concreto), llamamos directamente a la síntesis
        # inferencial. Esto garantiza una respuesta agrupada y útil aunque GPT
        # no esté disponible, y evita listas crudas del JSON.
        if self._is_day_scope_question(raw):
            hints = self._day_hints_in_message(raw)
            if hints:
                label = self._day_hint_display(hints[0])
                logger.info(
                    "v0.21.5: pregunta de día interceptada (%r → %s)", raw[:80], label
                )
                return self._synthesize_day_agenda(raw, label, hints)

        unified = try_structured_user_intent(
            raw,
            self._unified_candidates(raw),
            self._events.get_focused_event(),
        )
        if unified is not None:
            op = unified["operation"]
            logger.info(
                "Motor unificado: operation=%s conf=%.2f",
                op,
                float(unified.get("confidence", 0)),
            )
            if op == "general_query":
                logger.info("Motor unificado: general_query → consulta general")
                return self._unified_handle_general(raw, unified)
            return self._dispatch_unified_motor(raw, unified)

        logger.info("Motor unificado: no disponible; flujo de respaldo")
        return self._process_fresh_legacy(raw)

    def _process_fresh_legacy(self, raw: str) -> tuple[str, str, str | dict | None, str | None]:
        motor = try_agenda_intent_analysis(
            raw,
            self._agenda_candidates(raw),
            self._events.get_focused_event(),
        )
        if motor is not None:
            ci = motor["calendar_intent"]
            logger.info(
                "Motor agenda GPT: calendar_intent=%s conf=%.2f",
                ci,
                float(motor.get("confidence", 0)),
            )
            if ci != "not_calendar":
                return self._dispatch_agenda_motor(raw, motor)
            logger.info("Motor agenda GPT: not_calendar → flujo estándar")
        else:
            logger.info("Motor agenda GPT: sin resultado; flujo estándar")

        if self._keywords_match(raw, self._KW_NOTA):
            logger.info("Clasificación local: nota")
            return (
                "He guardado esta nota provisionalmente.",
                "nota",
                None,
                None,
            )
        if self._keywords_match(raw, self._KW_TAREA):
            logger.info("Clasificación local: tarea")
            return (
                "He creado esta tarea provisional.",
                "tarea",
                None,
                None,
            )
        if self._keywords_match(raw, self._KW_CALENDARIO):
            logger.info("Clasificación local: calendario (palabra clave); extracción GPT legada")
            return self._process_calendar_with_extraction(raw)

        logger.info(
            "Clasificación local: consulta general (sin agenda local previa ni keywords directas)"
        )
        key_ok = bool((os.getenv("OPENAI_API_KEY") or "").strip())
        logger.info("OPENAI_API_KEY presente: %s", key_ok)
        logger.debug("Llamando a análisis estructurado OpenAI")
        analysis = try_structured_intent_analysis(raw)
        if analysis is None:
            logger.warning(
                "OpenAI no disponible o análisis estructurado fallido; usando fallback local"
            )
            reply = try_consult_response(raw)
            if reply:
                return (reply, "consulta", None, None)
            logger.warning("Sin respuesta de consulta OpenAI; usando mensaje local de refuerzo")
            logger.info("Fallback a consulta local")
            return (self._CONSULTA_LOCAL, "consulta", None, None)

        intent = analysis["intent"]
        clean = (analysis.get("clean_content") or "").strip()
        query_text = clean or raw

        logger.debug(
            "Resultado análisis estructurado: %s",
            {
                "intent": intent,
                "confidence": analysis.get("confidence"),
                "date_text": analysis.get("date_text"),
                "clean_content_preview": (clean or raw)[:200],
                "reason_preview": (str(analysis.get("reason") or ""))[:150],
            },
        )

        if intent == "consulta":
            reply = try_consult_response(query_text)
            if reply:
                return (reply, "consulta", None, None)
            logger.warning("Consulta OpenAI sin respuesta; usando mensaje local de refuerzo")
            logger.info("Fallback a consulta local")
            return (self._CONSULTA_LOCAL, "consulta", None, None)

        if intent == "calendario":
            logger.info("Análisis estructurado: calendario; extracción GPT")
            return self._process_calendar_with_extraction(raw)

        suggested = self._suggested_intent_from_analysis(analysis, raw)
        date_text = analysis.get("date_text")
        try:
            confidence = float(analysis.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0

        action = {
            "original_text": raw,
            "suggested_intent": suggested,
            "clean_content": clean or raw,
            "date_text": date_text,
            "confidence": confidence,
            "created_at": _utc_iso(),
        }
        self._pending.save_pending_action(action)
        logger.info("Acción pendiente guardada: tipo=%s", suggested)
        tipo_preg = self._tipo_pregunta(suggested)
        contenido = action["clean_content"]
        reply = (
            f"He entendido que podría ser {tipo_preg}: «{contenido}». ¿Quieres que lo guarde?"
        )
        return (reply, "ambiguo", None, None)

    def _calendar_direct_save_ok(self, cal: dict[str, Any]) -> bool:
        if cal.get("intent") != "calendar_event":
            return False
        if not (str(cal.get("title") or "").strip()):
            return False
        if not (str(cal.get("date_text") or "").strip()):
            return False
        try:
            conf = float(cal.get("confidence", 0))
        except (TypeError, ValueError):
            return False
        if conf < 0.80:
            return False
        if bool(cal.get("needs_confirmation", True)):
            return False
        return True

    def _store_payload_from_cal(self, raw: str, cal: dict[str, Any]) -> dict[str, Any]:
        title = str(cal.get("title") or "").strip() or "Evento"
        tt_src = cal.get("time_text")
        tt_eff = _calendar_time_text_after_user_message(raw, tt_src)
        payload: dict[str, Any] = {
            "title": title,
            "date_text": cal.get("date_text"),
            "time_text": tt_eff if tt_eff is not None else tt_src,
            "location": cal.get("location"),
            "description": cal.get("description"),
            "participants": list(cal.get("participants") or []),
            "duration_minutes": cal.get("duration_minutes"),
            "source_text": (str(cal.get("source_text") or "").strip() or raw),
            "confidence": cal.get("confidence"),
            "needs_confirmation": False,
            "missing_fields": list(cal.get("missing_fields") or []),
        }
        return {k: v for k, v in payload.items() if v is not None and v != []}

    def _pending_calendar_payload(self, raw: str, cal: dict[str, Any]) -> dict[str, Any]:
        title = str(cal.get("title") or "").strip()
        tt_src = cal.get("time_text")
        tt_eff = _calendar_time_text_after_user_message(raw, tt_src)
        return {
            "original_text": raw,
            "suggested_intent": "calendario",
            "clean_content": title or raw,
            "title": cal.get("title"),
            "date_text": cal.get("date_text"),
            "time_text": tt_eff if tt_eff is not None else tt_src,
            "location": cal.get("location"),
            "description": cal.get("description"),
            "participants": list(cal.get("participants") or []),
            "duration_minutes": cal.get("duration_minutes"),
            "confidence": cal.get("confidence"),
            "missing_fields": list(cal.get("missing_fields") or []),
            "created_at": _utc_iso(),
            "calendar_structured": True,
        }

    def _calendar_pending_question(self, cal: dict[str, Any]) -> str:
        title = str(cal.get("title") or "").strip() or "este evento"
        missing = list(cal.get("missing_fields") or [])
        if missing:
            return (
                f"He entendido «{title}» como posible cita, pero necesito aclarar "
                f"({', '.join(missing)}). ¿Puedes concretar día u hora?"
            )
        return (
            f"He entendido «{title}» como evento. ¿Confirmas que lo guarde en el calendario local?"
        )

    def _process_calendar_with_extraction(
        self, raw: str
    ) -> tuple[str, str, str | dict | None, None]:
        cal = try_calendar_event_extraction(raw)
        if cal is None:
            logger.warning(
                "Calendario: extracción GPT no disponible o fallida; fallback add_event con texto crudo"
            )
            return ("He preparado este evento provisional.", "calendario", raw, None)

        if cal.get("intent") == "not_calendar":
            logger.info(
                "Calendario: GPT indica not_calendar; fallback add_event con texto crudo"
            )
            return ("He preparado este evento provisional.", "calendario", raw, None)

        if self._calendar_direct_save_ok(cal):
            payload = self._store_payload_from_cal(raw, cal)
            logger.info(
                "Calendario: guardado directo estructurado title=%s",
                (payload.get("title") or "")[:80],
            )
            return (
                self._saved_calendar_ack(payload, raw),
                "calendario",
                payload,
                None,
            )

        action = self._pending_calendar_payload(raw, cal)
        self._pending.save_pending_action(action)
        logger.info(
            "Calendario: pending_action por confirmación o datos insuficientes confidence=%s",
            cal.get("confidence"),
        )
        reply = self._calendar_pending_question(cal)
        return (reply, "ambiguo", None, None)

    # ------------------------------------------------------------------
    # v0.21.4 — Completado de pending_action de calendario.
    # ------------------------------------------------------------------

    _LOCAL_CONFIRM_TOKENS = frozenset(
        {"si", "vale", "correcto", "confirmo", "adelante", "guardalo", "guardalo ya"}
    )
    _LOCAL_CANCEL_TOKENS = frozenset(
        {"no", "cancelar", "cancela", "olvidalo", "dejalo", "no lo guardes"}
    )
    _PARTICIPANT_ARTICLE_RE = re.compile(
        r"^(el|la|los|las|al|del|un|una)\s+", flags=re.IGNORECASE
    )
    # v0.21.7b — Verbos de acción típicos al principio de un completado, para
    # inferir un título cuando el pending todavía no tiene uno.
    _ACTION_VERB_RE = re.compile(
        r"\b(?:voy\s+a|vamos\s+a|tengo\s+que|quiero|me\s+voy\s+a|me\s+toca)\s+"
        r"(quedar|reunirme|comer|cenar|desayunar|tomar|hablar|"
        r"llamar|recoger|llevar|visitar|ver(?:me|le|la|lo)?)\b",
        flags=re.IGNORECASE,
    )
    _ACTION_VERB_NORMALIZATION = {
        "reunirme": "reunión",
        "verme": "ver",
        "verle": "ver",
        "verla": "ver",
        "verlo": "ver",
    }

    def _pending_calendar_needs_completion(self, pending: dict) -> bool:
        """True si la pending es de calendario y aún admite completado de datos.

        v0.21.4b: NO depende de `_pending_is_rich_calendar`; cualquier pending de
        calendario con `pending_kind == "calendar_event_completion"` o con campos
        críticos vacíos o con título genérico se considera completable.
        """
        if not isinstance(pending, dict):
            return False
        if pending.get("suggested_intent") != "calendario":
            return False
        if pending.get("pending_kind") == "calendar_event_completion":
            return True
        if self._pending_calendar_missing_fields(pending):
            return True
        title = (pending.get("title") or "").strip()
        if title and self._is_generic_calendar_title(title):
            return True
        return False

    def _pending_calendar_missing_fields(self, pending: dict) -> list[str]:
        """Devuelve la lista de campos críticos que faltan para poder guardar el evento."""
        missing: list[str] = []
        title = (pending.get("title") or "").strip()
        date_t = (pending.get("date_text") or "").strip()
        time_t = (pending.get("time_text") or "").strip()
        loc = (pending.get("location") or "").strip()
        parts = pending.get("participants")
        has_parts = isinstance(parts, list) and len(parts) > 0

        if not title:
            missing.append("title")
        if not date_t:
            missing.append("date_text")
        if not time_t:
            missing.append("time_text")
        # Título genérico (cita/reunión/evento/encuentro) o fragmentario
        # («cita con», «reunión en», «evento de») exige location o participantes.
        # v0.21.7c: añadida la condición de fragmentario.
        if (
            title
            and (
                self._is_generic_calendar_title(title)
                or self._is_fragmentary_calendar_title(title)
            )
            and not loc
            and not has_parts
        ):
            missing.append("participants_or_location")
        return missing

    def _calendar_pending_missing_summary(self, pending: dict) -> str:
        """Texto natural en plural con los campos que faltan, p. ej.:
        "para qué día, a qué hora y con quién o dónde"."""
        parts_phr: list[str] = []
        if not (pending.get("date_text") or "").strip():
            parts_phr.append("para qué día")
        if not (pending.get("time_text") or "").strip():
            parts_phr.append("a qué hora")
        title = (pending.get("title") or "").strip()
        # v0.21.7c: incluir también títulos fragmentarios.
        if title and (
            self._is_generic_calendar_title(title)
            or self._is_fragmentary_calendar_title(title)
        ):
            participants = pending.get("participants") or []
            has_parts = isinstance(participants, list) and len(participants) > 0
            has_loc = bool((pending.get("location") or "").strip())
            if not has_parts and not has_loc:
                parts_phr.append("con quién o dónde")
        if not parts_phr:
            return ""
        if len(parts_phr) == 1:
            return parts_phr[0]
        return ", ".join(parts_phr[:-1]) + " y " + parts_phr[-1]

    def _calendar_pending_question_for_missing(self, pending: dict) -> str:
        # v0.21.10 — Pregunta inicial adaptada al sustantivo cuando se abre
        # la pending desde un bare intent ("cita" / "evento" / "reunión")
        # y todavía no hay fecha, hora, lugar ni participantes.
        title_raw = (pending.get("title") or "").strip().lower()
        title_norm = _strip_accents(title_raw)
        date_t = (pending.get("date_text") or "").strip()
        time_t = (pending.get("time_text") or "").strip()
        loc = (pending.get("location") or "").strip() if pending.get("location") else ""
        parts = pending.get("participants") or []
        all_empty = not date_t and not time_t and not loc and not parts
        if all_empty and title_norm in {"cita", "reunion", "evento", "encuentro"}:
            if title_norm == "evento":
                return (
                    "¿Para qué día, a qué hora y qué detalles quieres guardar "
                    "para el evento?"
                )
            if title_norm == "reunion":
                return "¿Para qué día, a qué hora y con quién es la reunión?"
            # cita / encuentro
            return f"¿Para qué día, a qué hora y con quién o dónde es la {title_raw}?"

        # v0.21.7b — Si falta el título pero hay fecha y/u hora, preguntamos
        # directamente por el título con contexto natural. Antes caíamos en
        # "¿Algún dato más que añadir?", que no se entiende como petición de
        # título.
        missing = self._pending_calendar_missing_fields(pending)
        if "title" in missing:
            tt_disp = self._display_time_text(time_t, "") or time_t
            if date_t and tt_disp:
                return f"¿Qué título quieres para el evento de {date_t} a las {tt_disp}?"
            if date_t:
                return f"¿Qué título quieres para el evento de {date_t}?"
            if tt_disp:
                return f"¿Qué título quieres para el evento de las {tt_disp}?"
            return "¿Qué título quieres para el evento?"

        summary = self._calendar_pending_missing_summary(pending)
        title = (pending.get("title") or "evento").strip() or "evento"
        if not summary:
            return "¿Algún dato más que añadir?"
        cap = summary[0].upper() + summary[1:]
        # v0.21.7c: tratamos también los títulos fragmentarios como genéricos
        # para que la pregunta suene natural ("¿Con quién o dónde es la cita con?"
        # → "¿Con quién o dónde es la cita?").
        if self._is_generic_calendar_title(title) or self._is_fragmentary_calendar_title(title):
            display_title = self._title_without_trailing_connector(title)
            return f"¿{cap} es la {display_title}?"
        return f"¿{cap} es «{title}»?"

    @staticmethod
    def _title_without_trailing_connector(title: str) -> str:
        """Devuelve el título quitando una preposición colgante final,
        usado solo para presentación. p.ej. 'cita con' -> 'cita'."""
        return re.sub(
            r"\b(?:con|sin|para|en|al|del|de|por|hasta|desde|entre|hacia|sobre|"
            r"tras|durante|segun|según)\s*$",
            "",
            (title or "").strip(),
            flags=re.IGNORECASE,
        ).strip() or (title or "").strip()

    def _calendar_pending_premature_confirm_msg(self, pending: dict) -> str:
        """Mensaje cuando el usuario confirma sin completar lo mínimo."""
        summary = self._calendar_pending_missing_summary(pending)
        title = (pending.get("title") or "evento").strip() or "evento"
        if not summary:
            return "Hace falta un detalle antes de guardar. ¿Algún dato más?"
        if self._is_generic_calendar_title(title):
            return f"Necesito saber {summary} es la {title}."
        return f"Necesito saber {summary} es «{title}»."

    def _strip_participant_article(self, name: str) -> str:
        s = (name or "").strip()
        if not s:
            return s
        return self._PARTICIPANT_ARTICLE_RE.sub("", s, count=1).strip()

    def _strip_location_article(self, loc: str) -> str:
        s = (loc or "").strip()
        if not s:
            return s
        return self._PARTICIPANT_ARTICLE_RE.sub("", s, count=1).strip()

    def _format_participants(self, participants: list[Any]) -> str:
        names = [str(p).strip() for p in (participants or []) if str(p).strip()]
        if not names:
            return ""
        if len(names) == 1:
            return names[0]
        return ", ".join(names[:-1]) + " y " + names[-1]

    def _merge_participants(
        self, existing: list[Any], new: list[Any]
    ) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for p in (existing or []) + (new or []):
            s = str(p).strip()
            if not s:
                continue
            key = _strip_accents(s.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out

    def _polish_title_with_participants(
        self, title: str, participants: list[Any]
    ) -> str:
        if not title or not self._is_generic_calendar_title(title):
            return title or "Evento"
        cleaned = [self._strip_participant_article(str(p)) for p in (participants or [])]
        cleaned = [c for c in cleaned if c]
        if not cleaned:
            return title
        return f"{title} con {' y '.join(cleaned)}"

    def _local_complete_pending_fallback(
        self, raw: str, pending: dict
    ) -> dict[str, Any] | None:
        """
        Fallback determinista mínimo cuando GPT no está disponible.

        Cubre patrones obvios: "sí"/"no" exactos, frases con "en X" / "con X",
        y extracción simple de fecha/hora (v0.21.4b).

        Devuelve estructura compatible con `try_complete_pending_calendar_event`.
        """
        norm = _normalize_exact_local_reply(raw)
        if not norm:
            return None

        if norm in self._LOCAL_CONFIRM_TOKENS:
            return {
                "intent": "confirm",
                "updates": {
                    "title": None, "date_text": None, "time_text": None,
                    "location": None, "participants": [],
                    "description": None, "duration_minutes": None,
                },
                "confidence": 0.95,
                "missing_fields": [],
                "reason": "local exact confirm",
            }
        if norm in self._LOCAL_CANCEL_TOKENS:
            return {
                "intent": "cancel",
                "updates": {
                    "title": None, "date_text": None, "time_text": None,
                    "location": None, "participants": [],
                    "description": None, "duration_minutes": None,
                },
                "confidence": 0.95,
                "missing_fields": [],
                "reason": "local exact cancel",
            }

        # Preservamos mayúsculas (Luis, María, etc.) para que el título quede natural.
        text = (raw or "").strip()
        loc: str | None = None
        participants: list[str] = []

        # "con <persona>" hasta fin/coma o hasta " en " / " a la(s) ".
        m_con = re.search(r"\bcon\s+([^,.;]+)", text, flags=re.IGNORECASE)
        if m_con:
            cand = m_con.group(1).strip()
            cand = re.split(r"\s+(?:en|a\s+la)\b", cand, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if cand:
                participants.append(cand)
        # "en <lugar>" hasta fin/coma o hasta " con " / " a la(s) ".
        m_en = re.search(r"\ben\s+([^,.;]+)", text, flags=re.IGNORECASE)
        if m_en:
            cand = m_en.group(1).strip()
            cand = re.split(r"\s+(?:con|a\s+la)\b", cand, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if cand:
                loc = cand

        # Fecha: día de la semana, "hoy", "mañana", "pasado mañana".
        date_text: str | None = None
        m_day = _DAY_HINTS_RE.search(text)
        if m_day:
            article = (m_day.group(1) or "").strip()
            day = (m_day.group(2) or "").strip()
            date_text = (f"{article} {day}".strip() if article else day) or None

        # Hora: "a las 2", "a las 14:00", "a las 2:30".
        time_text: str | None = None
        m_time = _TIME_HINTS_RE.search(text)
        if m_time:
            h = int(m_time.group(1))
            mins = m_time.group(2) or "00"
            time_text = f"{h}:{mins}"

        # v0.21.7b — Si el pending no tiene título y el mensaje contiene un
        # verbo de acción típico ("voy a quedar", "tengo que llamar", ...),
        # inferimos un título corto. Si además hay participantes, lo
        # convertimos en "quedar con Luis", "llamar a María", etc.
        title_new: str | None = None
        pending_has_title = bool((pending.get("title") or "").strip())
        if not pending_has_title:
            m_v = self._ACTION_VERB_RE.search(text)
            if m_v:
                verb = m_v.group(1).lower()
                verb = self._ACTION_VERB_NORMALIZATION.get(verb, verb)
                if participants:
                    names = " y ".join(self._strip_participant_article(p) for p in participants)
                    title_new = f"{verb} con {names}" if names else verb
                else:
                    title_new = verb

        if not (loc or participants or date_text or time_text or title_new):
            return None

        return {
            "intent": "complete_pending_event",
            "updates": {
                "title": title_new,
                "date_text": date_text,
                "time_text": time_text,
                "location": loc,
                "participants": participants,
                "description": None,
                "duration_minutes": None,
            },
            "confidence": 0.55,
            "missing_fields": [],
            "reason": "local regex fallback",
        }

    def _apply_completion_updates(
        self, pending: dict, updates: dict[str, Any], raw: str
    ) -> dict[str, Any]:
        """Fusiona `updates` con `pending` sin perder datos previos."""
        merged = dict(pending)

        def _set_if_missing(key: str) -> None:
            if updates.get(key) and not (merged.get(key) or "").strip():
                merged[key] = updates[key]

        # title: solo sustituir si el actual era genérico/vacío y el nuevo no lo es.
        new_title = (updates.get("title") or "").strip()
        cur_title = (merged.get("title") or "").strip()
        if new_title and (
            not cur_title or self._is_generic_calendar_title(cur_title)
        ) and not self._is_generic_calendar_title(new_title):
            merged["title"] = new_title

        _set_if_missing("date_text")
        _set_if_missing("time_text")

        # location: si llega nueva, sustituir aunque hubiera una.
        if updates.get("location"):
            merged["location"] = updates["location"]

        # participants: unión sin duplicados.
        new_parts = updates.get("participants") or []
        if new_parts:
            merged["participants"] = self._merge_participants(
                merged.get("participants") or [], new_parts
            )

        # description: si nueva, anexar a la existente o usar de cero.
        new_desc = (updates.get("description") or "").strip()
        if new_desc:
            cur_desc = (merged.get("description") or "").strip()
            merged["description"] = (cur_desc + ". " + new_desc).strip(". ") if cur_desc else new_desc

        if updates.get("duration_minutes") is not None and not merged.get("duration_minutes"):
            merged["duration_minutes"] = updates["duration_minutes"]

        # Mejorar título genérico si ya hay participantes.
        cur_title2 = (merged.get("title") or "").strip()
        if self._is_generic_calendar_title(cur_title2):
            polished = self._polish_title_with_participants(
                cur_title2, merged.get("participants") or []
            )
            if polished and polished != cur_title2:
                merged["title"] = polished

        # v0.21.7c — Si el título quedó "colgado" en una preposición ("cita con",
        # "reunión en", "evento de"…) y ahora tenemos participants/location,
        # fusionamos en el propio título sin duplicar.
        cur_title3 = (merged.get("title") or "").strip()
        tail = self._fragmentary_title_tail(cur_title3)
        if tail:
            if tail == "con" and merged.get("participants"):
                names = self._format_participants(merged["participants"])
                if names and not self._title_contains_all_names(
                    cur_title3, merged["participants"]
                ):
                    merged["title"] = f"{cur_title3} {names}"
            elif tail in {"en", "al", "hacia"} and (merged.get("location") or "").strip():
                loc_clean = self._strip_location_article(str(merged["location"]))
                if loc_clean and loc_clean.lower() not in cur_title3.lower():
                    merged["title"] = f"{cur_title3} {loc_clean}"

        # Acumulamos historia textual.
        prev_orig = str(merged.get("original_text") or "").strip()
        merged["original_text"] = (prev_orig + " || " + raw).strip(" |") if prev_orig else raw
        merged["clean_content"] = (merged.get("title") or merged.get("clean_content") or "").strip() or raw
        # Mantener la marca de estructura.
        merged["calendar_structured"] = True
        # v0.21.7c — Refrescamos `missing_fields` para reflejar el estado real
        # tras la fusión (p.ej. al pasar de `title=null` a `title="cita con"`
        # ahora falta `participants_or_location` en vez de `title`).
        merged["missing_fields"] = self._pending_calendar_missing_fields(merged)
        return merged

    def _calendar_ready_to_save(self, pending: dict) -> bool:
        return not self._pending_calendar_missing_fields(pending)

    def _try_complete_pending_calendar(
        self, raw: str, pending: dict
    ) -> tuple[str, str, str | dict | None, str | None] | None:
        """
        Intercepta el flujo cuando hay pending_action de calendario incompleta.

        Devuelve la respuesta lista o None si decide derivar al flujo estándar
        (`resolve_pending_reply`).
        """
        logger.info(
            "pending_action calendario incompleta detectada (missing=%s)",
            self._pending_calendar_missing_fields(pending),
        )

        # v0.21.10 — "sí" / "vale" / "ok" sobre pending de calendario que
        # solo tiene un sustantivo desnudo como título ("cita"/"evento"/
        # "reunión") NO debe guardar nada: pedimos los datos que faltan.
        if self._is_affirmative_short(raw):
            title_norm = _strip_accents(
                (pending.get("title") or "").strip().lower()
            )
            date_t = (pending.get("date_text") or "").strip()
            time_t = (pending.get("time_text") or "").strip()
            loc = (pending.get("location") or "").strip() if pending.get("location") else ""
            parts = pending.get("participants") or []
            all_empty = not date_t and not time_t and not loc and not parts
            if all_empty and title_norm in {"cita", "reunion", "evento", "encuentro"}:
                msg = self._calendar_pending_question_for_missing(pending)
                return (msg, "ambiguo", None, None)

        result = try_complete_pending_calendar_event(raw, pending)
        if result is None:
            result = self._local_complete_pending_fallback(raw, pending)
        if result is None:
            logger.info(
                "pending_action calendario: sin GPT y sin patrón local; flujo estándar."
            )
            return None

        intent = result["intent"]
        updates = result.get("updates") or {}
        logger.info(
            "complete_pending_calendar: intent=%s conf=%.2f updates_keys=%s",
            intent,
            float(result.get("confidence", 0)),
            [k for k, v in updates.items() if v not in (None, "", [], {})],
        )

        if intent == "cancel":
            self._pending.clear_pending_action()
            logger.info("pending_action calendario cancelada por usuario.")
            return ("De acuerdo, no lo guardo.", "consulta", None, None)

        if intent == "other":
            logger.info("pending_action calendario: respuesta no relacionada; flujo estándar.")
            return None

        if intent == "needs_clarification":
            msg = self._calendar_pending_question_for_missing(pending)
            return (msg, "ambiguo", None, None)

        if intent == "confirm":
            if self._calendar_ready_to_save(pending):
                return self._save_pending_calendar_now(pending, raw)
            logger.info(
                "pending_action calendario: confirmación con datos insuficientes; "
                "se vuelve a preguntar."
            )
            msg = self._calendar_pending_premature_confirm_msg(pending)
            return (msg, "ambiguo", None, None)

        # intent == "complete_pending_event": fusionar y decidir.
        merged = self._apply_completion_updates(pending, updates, raw)
        tt_m = (merged.get("time_text") or "").strip()
        if tt_m:
            ot = str(pending.get("original_text") or "")
            merged["time_text"] = _coerce_calendar_time_twice_sources(raw, ot, tt_m)

        if self._calendar_ready_to_save(merged):
            return self._save_pending_calendar_now(merged, raw)

        # Persistimos la pending fusionada y seguimos preguntando.
        self._pending.save_pending_action(merged)
        logger.info(
            "pending_action calendario actualizada; aún faltan %s.",
            self._pending_calendar_missing_fields(merged),
        )
        msg = self._calendar_pending_question_for_missing(merged)
        return (msg, "ambiguo", None, None)

    def _save_pending_calendar_now(
        self, pending: dict, raw: str
    ) -> tuple[str, str, dict[str, Any], None]:
        payload_dict = self._event_dict_from_pending(pending)
        # Normalizamos location quitando artículos si conviene para el ack ("hospital"
        # en lugar de "el hospital") sin romper el dato guardado.
        self._pending.clear_pending_action()
        original = str(pending.get("original_text") or raw)
        logger.info(
            "pending_action calendario completada y guardada: title=%s",
            (payload_dict.get("title") or "")[:80],
        )
        ack = self._saved_calendar_ack(payload_dict, original)
        return (ack, "calendario", payload_dict, None)

    # ------------------------------------------------------------------

    def _pending_is_rich_calendar(self, pending: dict) -> bool:
        if pending.get("suggested_intent") != "calendario":
            return False
        if pending.get("calendar_structured") is True:
            return True
        if pending.get("date_text"):
            return True
        if pending.get("time_text"):
            return True
        if pending.get("location"):
            return True
        parts = pending.get("participants")
        return isinstance(parts, list) and len(parts) > 0

    def _event_dict_from_pending(self, pending: dict) -> dict[str, Any]:
        title = (
            str(pending.get("title") or "").strip()
            or str(pending.get("clean_content") or "").strip()
            or str(pending.get("original_text") or "").strip()
            or "Evento"
        )
        raw_src = str(pending.get("original_text") or "")
        tt_p = pending.get("time_text")
        tt_eff = None
        if tt_p is not None and str(tt_p).strip():
            tt_eff = _coerce_ambiguous_calendar_time_text(
                raw_src, str(tt_p).strip()
            )
        payload: dict[str, Any] = {
            "title": title,
            "date_text": pending.get("date_text"),
            "time_text": tt_eff if tt_eff is not None else tt_p,
            "location": pending.get("location"),
            "description": pending.get("description"),
            "participants": list(pending.get("participants") or [])
            if isinstance(pending.get("participants"), list)
            else [],
            "duration_minutes": pending.get("duration_minutes"),
            "source_text": str(pending.get("original_text") or "")[:4000],
            "confidence": pending.get("confidence"),
            "needs_confirmation": False,
            "missing_fields": [],
        }
        return {k: v for k, v in payload.items() if v is not None and v != []}

    def _suggested_intent_from_analysis(self, analysis: dict, raw: str) -> str:
        intent = str(analysis.get("intent", "")).strip().lower()
        if intent in ("nota", "tarea", "calendario"):
            return intent
        blob = (analysis.get("clean_content") or raw).lower()
        return self._infer_intent_from_text(blob)

    def _infer_intent_from_text(self, blob: str) -> str:
        t = blob.lower()
        if any(k in t for k in self._KW_CALENDARIO):
            return "calendario"
        if any(k in t for k in self._KW_TAREA):
            return "tarea"
        return "nota"

    def _tipo_pregunta(self, intent: str) -> str:
        return {
            "nota": "una nota",
            "tarea": "una tarea",
            "calendario": "un evento",
        }.get(intent, "una nota")
