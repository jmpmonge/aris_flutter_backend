"""OpenAI opcional: consultas conversacionales y análisis estructurado de intención."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_REPO_ROOT / ".env")

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Eres ARIS, asistente personal. Responde siempre en español, de forma breve y útil "
    "(como mucho unas pocas frases). Sin intros largas ni disculpas innecesarias."
)

_INTENT_ALLOWED = frozenset({"nota", "tarea", "calendario", "consulta", "ambiguo"})

_PENDING_REPLY_DECISIONS = frozenset(
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

_PENDING_REPLY_SYSTEM = """Eres un analizador de respuestas cortas para ARIS (asistente personal).
El usuario ya recibió una pregunta de confirmación sobre guardar algo (nota, tarea o evento).
Ahora responde sobre esa acción PENDIENTE.

Tu salida debe ser SIEMPRE un único objeto JSON válido (sin markdown ni texto fuera del JSON).

Campos obligatorios:
- "decision": exactamente uno de: confirm, cancel, save_as_note, save_as_task, save_as_event, needs_clarification, unknown
- "confidence": número entre 0 y 1 (cuán seguro estás de la decisión respecto al texto del usuario).
- "reason": una frase breve en español para depuración (por qué eliges esa decisión).
- "clarification_question": string con UNA pregunta breve al usuario en español si decision es
  needs_clarification o unknown y conviene acotar opciones; si no aplica, usa null.

Contexto real:
- El texto del usuario puede venir de RECONOCIMIENTO DE VOZ: sin comas, palabras pegadas
  (ej. "siguardalo" puede ser "sí, guárdalo"), o "si guardalo".
- "coma" en el texto puede ser pausa o "coma" literal ambigua (ej. "si coma quiero…" puede ser "sí, quiero…").
- "si" sin tilde suele equivaler a "sí" cuando encaja confirmación.
- Frases con "no" + "quiero" + "guardar/guardes" + tipo (tarea/nota/evento) pueden ser CANCELACIÓN
  o CONFIRMACIÓN con matiz ("No, quiero…" mal transcrito). Si no estás seguro, usa needs_clarification.

Criterios de decisión:
- "confirm": el usuario confirma guardar tal como se sugirió (sí, vale, adelante, guárdalo sin cambiar tipo…).
- "cancel": rechaza guardar (no, olvídalo, déjalo, cancelar…).
- "save_as_note" / "save_as_task" / "save_as_event": quiere guardar pero CAMBIANDO el tipo explícitamente
  (como tarea, como evento, hazlo nota, mejor calendario…). "save_as_event" incluye calendario.
- "needs_clarification": el mensaje es ambiguo y conviene preguntar de nuevo (no decidas entre confirm/cancel).
- "unknown": no entiendes la intención respecto a guardar/cancelar/cambiar tipo (ruido, otro tema, intraducible).

Sé conservador: si hay duda fuerte entre confirmar y cancelar, o sobre el tipo, usa needs_clarification con confidence baja."""

_CALENDAR_EVENT_SYSTEM = """Eres un extractor de EVENTOS DE CALENDARIO para ARIS (asistente personal).
Solo INTERPRETAS el texto del usuario; no ejecutas acciones. Tu salida debe ser SIEMPRE un único
objeto JSON válido (sin markdown ni texto fuera del JSON).

Campos obligatorios:
- "intent": exactamente "calendar_event" o "not_calendar".
- "title": string corto y limpio del evento, o null si no aplica o no es calendario.
- "date_text": fecha en lenguaje natural relativo o absoluto (ej. "mañana", "el viernes", "14/05/2026"), o null.
- "time_text": hora textual (ej. "16:00", "a las 4", "por la tarde"), o null si no hay hora.
- "location": lugar si se menciona explícitamente; null si no hay (NO inventar).
- "description": detalles útiles adicionales o null.
- "participants": lista de nombres de personas mencionadas; [] si ninguna.
- "duration_minutes": entero minutos si el usuario indica duración; null si no.
- "source_text": copia fiel del mensaje del usuario (o muy cercana).
- "confidence": número entre 0 y 1 (cuán seguro estás de la extracción).
- "needs_confirmation": true si falta información importante (ej. sin fecha clara) o el evento es dudoso; false solo si es claro.
- "missing_fields": lista de strings con nombres de campos ausentes que importan (ej. "date_text", "time_text"); [] si ninguno.
- "reason": una frase breve en español para depuración.

Reglas:
- El texto puede venir de VOZ: falta de puntuación, errores leves de transcripción.
- NO inventes lugar, hora ni participantes que no estén implícitos en el texto.
- Si no hay hora, "time_text" debe ser null.
- Si la fecha es relativa ("mañana", "el lunes"), consérvala en "date_text" como texto; NO conviertas a ISO/fecha absoluta.
- Si el mensaje NO trata de un evento o cita (pregunta general, organización abstracta, etc.), intent = "not_calendar" y el resto mayormente null o vacío razonable.
- Si falta fecha para algo que parece evento, needs_confirmation = true y lista "date_text" en missing_fields si aplica.
- Devuelve SOLO JSON válido."""

_AGENDA_INTENTS = frozenset(
    {
        "create_event",
        "query_agenda",
        "update_event",
        "needs_clarification",
        "not_calendar",
    }
)

_REQUESTED_FIELDS = frozenset(
    {"time", "date", "location", "participants", "summary", "unknown"}
)

_AGENDA_MOTOR_SYSTEM = """Eres el MOTOR DE AGENDA LOCAL de ARIS (asistente personal).
Solo INTERPRETAS el mensaje del usuario; no ejecutas acciones ni escribes en disco.
Tu salida debe ser SIEMPRE un único objeto JSON válido (sin markdown ni texto fuera del JSON).

Campos obligatorios del objeto raíz:
- "calendar_intent": exactamente uno de: create_event, query_agenda, update_event, needs_clarification, not_calendar
- "target_event_id": id del evento en candidatos/enfoque si aplica; si no, null
- "requested_field": uno de: time, date, location, participants, summary, unknown; o null si no aplica
- "event_data": objeto con:
  - "title": string o null
  - "date_text": string o null (fechas relativas como texto: "mañana", "el viernes"; NO ISO)
  - "time_text": string o null
  - "location": string o null (NO inventar)
  - "participants": lista de strings (vacía si ninguno)
  - "description": string o null
  - "duration_minutes": entero o null
- "answer": string o null (respuesta corta sugerida al usuario en español; puede ser null si basta con datos locales)
- "missing_fields": lista de strings (ej. "date_text", "time_text")
- "confidence": número entre 0 y 1
- "reason": breve frase en español para depuración

Reglas:
- El texto puede ser VOZ: sin puntuación, errores leves de transcripción.
- NO inventes lugar, hora, fecha ni participantes que el usuario no haya dicho o no se desprendan claramente.
- Si no hay hora en el mensaje, event_data.time_text = null.
- Si no hay lugar, event_data.location = null.
- Si el usuario PREGUNTA por su agenda, citas, horarios, lugares o «qué tengo», calendar_intent = query_agenda.
- Si el usuario QUIERE CREAR un evento/cita/reunión, calendar_intent = create_event y rellena event_data.
- Si el usuario COMPLETA o CORRIGE un evento existente (p. ej. "será con el médico", "es en el hospital"),
  calendar_intent = update_event; indica target_event_id si lo tienes claro entre candidatos; si no, null.
- Si falta dato crítico para decidir, calendar_intent = needs_clarification.
- Si el mensaje NO trata de agenda/calendario/citas, calendar_intent = not_calendar (resto razonablemente vacío o null).
- Usa la lista "eventos_candidatos" y "evento_enfocado" del mensaje de usuario solo como referencia de ids y campos existentes.

Devuelve SOLO JSON válido."""

_UNIFIED_OPERATIONS = frozenset(
    {
        "create_note",
        "create_task",
        "create_calendar_event",
        "query_calendar",
        "update_calendar_event",
        "needs_clarification",
        "general_query",
    }
)

_TARGET_REFS = frozenset({"last_event", "focused_event", "matching_event"})

_UNIFIED_INTENT_SYSTEM = """Eres el MOTOR ESTRUCTURADO de ARIS (asistente personal local).
Solo INTERPRETAS el mensaje del usuario; NO ejecutas acciones ni escribes en disco.
Tu salida debe ser SIEMPRE un único objeto JSON válido (sin markdown ni texto fuera del JSON).

Recibes en el mensaje de usuario un objeto JSON con:
- "mensaje_usuario": texto a interpretar (puede ser voz transcrita).
- "eventos_candidatos": lista de eventos locales que podrían ser referidos (resumen reducido).
- "evento_enfocado": evento sobre el que el usuario hablaba en mensajes recientes; puede ser null.
- "accion_pendiente_previa_v046a" (opcional): resumen de pending_action cuando el usuario continúa una aclaración; respétalo y avanza clarification_step sólo cuando corresponda.

Debes devolver EXACTAMENTE este esquema:

{
  "operation": "create_note" | "create_task" | "create_calendar_event" | "query_calendar" | "update_calendar_event" | "needs_clarification" | "general_query",
  "confidence": 0.0,
  "needs_clarification": false,
  "clarification_question": null,
  "reason": "...",
  "note": { "content": null },
  "task": { "title": null, "date_text": null, "time_text": null, "priority": null },
  "calendar_event": {
    "title": null, "date_text": null, "time_text": null, "location": null,
    "participants": [], "description": null, "duration_minutes": null
  },
  "calendar_query": {
    "requested_field": "time" | "date" | "location" | "participants" | "summary" | "unknown" | null,
    "date_text": null, "time_text": null, "terms": [],
    "target_reference": "last_event" | "focused_event" | "matching_event" | null
  },
  "calendar_update": {
    "target_reference": "last_event" | "focused_event" | "matching_event" | null,
    "target_event_id": null,
    "updates": {
      "title": null, "date_text": null, "time_text": null, "location": null,
      "participants": [], "description": null, "duration_minutes": null
    }
  },
  "missing_fields": [],
  "status": "ready | needs_clarification | needs_confirmation | general_answer | failed",
  "ambiguities": [],
  "assistant_reply": null
}

El campo opcional pero recomendado "status" alinea ARIS con el contrato maestro v0.46a:
- "ready": la operation indicada puede ejecutarse (si Aris ya tiene datos mínimos) o debe seguir reglas locales de pendientes.
- "needs_clarification": DEBES usar operation="needs_clarification"; rellena clarification_question O assistant_reply con la pregunta.
- "needs_confirmation": mismo operation="needs_clarification"; el usuario debe confirmar antes de borrar o cambios delicados (p. ej. borrado de eventos).
- "general_answer": operation="general_query"; rellena assistant_reply si quieres una respuesta textual sin crear entidades.
- "failed": operation="needs_clarification"; pide reformulación breve sin inventar datos.

"ambiguities" (lista de objetos): si hora o dato es ambiguo, describe field, options y reason. Ej.: hora "8" sin mañana/tarde explícita en franja 08:00–22:00 → opciones 08:00 y 20:00.

Reglas (v0.46a):
- El texto puede venir de VOZ: sin puntuación, errores leves de transcripción; "coma" puede ser pausa dictada; "si" puede ser "sí".
- NO INVENTES fecha, hora, lugar, ids de eventos ni participantes que no estén en el mensaje o en candidatos/foco explícitos.
- NO inventes un viernes/12:00 u otra fecha fija si el usuario no la dijo.
- Si falta un dato, deja null (o lista vacía).
- Si el usuario PIDE CREAR un evento (cita/reunión/visita/etc.), operation = "create_calendar_event"; rellena calendar_event con lo que SÍ está claro. NUNCA clasifiques creación explícita como update_calendar_event aunque haya evento_enfocado.
- Si el usuario PREGUNTA por su agenda (qué tengo, a qué hora, dónde, con quién, cuándo, listar día…), operation = "query_calendar"; rellena calendar_query (requested_field, terms, date_text si aplica, target_reference si corresponde) y NO uses create_*.
- Si el usuario COMPLETA o CORRIGE un evento existente y NO es creación explícita, operation = "update_calendar_event"; calendar_update.target_event_id solo si el id está en candidatos o es inequívoco; si hay varios candidatos igualmente plausibles, operation="needs_clarification" y lista los eventos en ambiguities o en clarification_question — NO ejecutes actualización hasta aclaración.
- Si el usuario pide borrar un evento, NO devuelvas borrado directo como listo sin confirmación: status="needs_confirmation" y clarification_question explícita.
- Si el usuario pide guardar una NOTA, operation = "create_note"; note con title/content limpios, no el mensaje entero sin estructurar si puedes extraer título/cuerpo.
- Si el usuario pide crear una TAREA, operation = "create_task"; task.title y campos opcionales.
- Hora ambigua tipo "a las 8" sin contexto mañana/tarde: status="needs_clarification", ambiguities con opciones 08:00 y 20:00 salvo que el mensaje indique explícitamente mañana/tarde/noche o formato 24h inequívoco.
- Si hay "accion_pendiente_previa" en el mensaje (continuación de aclaración), integra esa información; respeta max_clarification_steps indicado allí.
- Una pregunta sobre la agenda NUNCA debe interpretarse como creación de evento.
- Devuelve SOLO JSON válido."""

_CALENDAR_QUERY_RESULTS = frozenset(
    {"answer", "multiple_matches", "not_found", "needs_clarification"}
)

_CALENDAR_QUERY_RESOLVER_SYSTEM = """Eres el RESOLUTOR DE CONSULTAS DE AGENDA de ARIS.
Solo respondes en base a los datos LOCALES suministrados en el mensaje (eventos candidatos y evento enfocado).
NO inventes información que no esté en esos datos.

Recibirás un JSON con:
- "mensaje_usuario": pregunta del usuario.
- "calendar_query": estructura con requested_field, date_text, time_text, terms, target_reference.
- "eventos_candidatos": lista de eventos locales (cada uno con id, title, date_text, time_text, location, participants, description).
- "evento_enfocado": objeto del evento enfocado o null.

Devuelve EXACTAMENTE este JSON:

{
  "result": "answer" | "multiple_matches" | "not_found" | "needs_clarification",
  "selected_event_id": null,
  "matching_event_ids": [],
  "answer": "...",
  "confidence": 0.0,
  "reason": "..."
}

Reglas:
- Responde SIEMPRE en español, en una o dos frases.
- Si hay un único candidato claro: result = "answer", selected_event_id = id del candidato, answer con la información solicitada.
- Si hay varios candidatos plausibles y no puedes elegir: result = "multiple_matches", matching_event_ids con los ids, answer pidiendo aclaración por título.
- Si no hay ningún candidato compatible: result = "not_found", answer = "No encuentro ese evento en tu agenda local."
- Si requested_field falta en el evento elegido: indícalo en la respuesta (p. ej. "No tengo guardado con quién es" o "No tengo un lugar guardado para ese evento.").
- Si la pregunta es por un DÍA (mañana, el viernes...), lista los eventos de ese día tal como aparezcan en candidatos; si no hay eventos compatibles, result = "not_found".
- Si la pregunta es "a qué hora", usa time_text del candidato; "dónde", location; "con quién", participants; "cuándo", date_text + time_text.
- Si necesitas más datos del usuario, result = "needs_clarification".
- No menciones eventos que no estén en candidatos.
- Devuelve SOLO JSON válido."""

_INTENT_ANALYSIS_SYSTEM = """Eres un analizador de intención para ARIS (asistente personal).
Tu salida debe ser SIEMPRE un único objeto JSON válido (sin markdown ni texto fuera del JSON).

Campos obligatorios:
- "intent": exactamente uno de: nota, tarea, calendario, consulta, ambiguo
- "clean_content": texto útil en español, conservando el sentido del usuario (sin inventar hechos).
  Si es acción concreta, resume lo esencial; si es pregunta general, reformula clara.
- "date_text": referencia temporal explícita en lenguaje natural (ej. "mañana", "el viernes",
  "hoy por la tarde"), o null si no la hay.
- "confidence": número entre 0 y 1 (cuán seguro estás de intent y clasificación).
- "needs_confirmation": true si habría que preguntar al usuario antes de guardar una acción
  (nota/tarea/evento); false solo si la intención es inequívoca.
- "reason": una frase breve en español para depuración (por qué elegiste intent y needs_confirmation).

Criterios:
- "consulta": pregunta de conocimiento, opinión o conversación sin compromiso de organizable.
- "nota": información para recordar sin fecha/hora de compromiso fuerte ni obligación.
- "tarea": algo que la persona debe hacer; deber, pendiente, obligación.
- "calendario": cita, reunión, evento con horario o lugar, visita (médico, dentista con cita), etc.
- "ambiguo": encaja varios anteriores y no conviene decidir sin el usuario.

Si la frase es ambigua entre tarea, evento/calendario o nota, usa intent "ambiguo" o
needs_confirmation true con el intent más probable."""


def try_consult_response(user_text: str) -> Optional[str]:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None

    model = (os.getenv("OPENAI_MODEL") or "gpt-5.5").strip() or "gpt-5.5"
    text = (user_text or "").strip()
    if not text:
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": text},
            ],
            max_tokens=400,
            temperature=0.6,
        )
        raw = completion.choices[0].message.content
        if raw is None:
            logger.warning("Consulta OpenAI: contenido de respuesta vacío")
            return None
        out = str(raw).strip()
        return out or None
    except Exception:
        logger.exception("Error en OpenAI: consulta conversacional fallida")
        return None


def _normalize_analysis(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    intent = str(data.get("intent", "")).strip().lower()
    if intent not in _INTENT_ALLOWED:
        return None
    clean = data.get("clean_content")
    clean_content = (str(clean).strip() if clean is not None else "") or ""

    raw_date = data.get("date_text")
    if raw_date is None or raw_date == "":
        date_text = None
    else:
        date_text = str(raw_date).strip() or None

    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        return None
    confidence = max(0.0, min(1.0, confidence))

    needs_confirmation = bool(data.get("needs_confirmation", True))
    reason = str(data.get("reason", "")).strip() or "—"

    return {
        "intent": intent,
        "clean_content": clean_content,
        "date_text": date_text,
        "confidence": confidence,
        "needs_confirmation": needs_confirmation,
        "reason": reason,
    }


def _normalize_pending_reply_analysis(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    decision = str(data.get("decision", "")).strip().lower()
    if not decision:
        return None

    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        return None
    confidence = max(0.0, min(1.0, confidence))

    reason = str(data.get("reason", "")).strip() or "—"
    raw_cq = data.get("clarification_question")
    if raw_cq is None or raw_cq == "":
        clarification_question = None
    else:
        clarification_question = str(raw_cq).strip() or None

    return {
        "decision": decision,
        "confidence": confidence,
        "reason": reason,
        "clarification_question": clarification_question,
    }


def try_pending_reply_analysis(
    user_text: str, pending_action: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Interpreta la respuesta del usuario ante una acción pendiente. Sin clave o error → None."""
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None

    model = (os.getenv("OPENAI_MODEL") or "gpt-5.5").strip() or "gpt-5.5"
    text = (user_text or "").strip()
    if not text:
        return None

    pending_payload: dict[str, Any] = {
        "original_text": pending_action.get("original_text"),
        "suggested_intent": pending_action.get("suggested_intent"),
        "clean_content": pending_action.get("clean_content"),
        "date_text": pending_action.get("date_text"),
        "confidence": pending_action.get("confidence"),
    }
    for key in (
        "time_text",
        "location",
        "description",
        "participants",
        "missing_fields",
        "title",
        "duration_minutes",
    ):
        if key in pending_action and pending_action.get(key) is not None:
            pending_payload[key] = pending_action.get(key)
    user_block = (
        "Acción pendiente (JSON):\n"
        f"{json.dumps(pending_payload, ensure_ascii=False)}\n\n"
        "Respuesta actual del usuario (puede ser voz transcrita, sin puntuación):\n"
        f"{text}"
    )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _PENDING_REPLY_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            response_format={"type": "json_object"},
            max_tokens=400,
            temperature=0.15,
        )
        raw = completion.choices[0].message.content
        if raw is None:
            logger.warning("Análisis respuesta pendiente: contenido vacío del modelo")
            return None
        try:
            data = json.loads(str(raw).strip())
        except json.JSONDecodeError as err:
            logger.warning("Análisis respuesta pendiente: JSON inválido: %s", err)
            return None
        if not isinstance(data, dict):
            logger.warning("Análisis respuesta pendiente: la respuesta JSON no es un objeto")
            return None
        out = _normalize_pending_reply_analysis(data)
        if out is None:
            logger.warning("Análisis respuesta pendiente: normalización rechazada")
        else:
            logger.info(
                "Análisis respuesta pendiente OpenAI: decision=%s confidence=%.2f",
                out["decision"],
                out["confidence"],
            )
            logger.debug("Análisis respuesta pendiente: reason=%s", out["reason"][:200])
        return out
    except Exception:
        logger.exception("Error en OpenAI: análisis de respuesta pendiente fallido")
        return None


def try_structured_intent_analysis(user_text: str) -> Optional[dict[str, Any]]:
    """Análisis JSON de intención. Sin clave, error de API o JSON inválido → None."""
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None

    model = (os.getenv("OPENAI_MODEL") or "gpt-5.5").strip() or "gpt-5.5"
    text = (user_text or "").strip()
    if not text:
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _INTENT_ANALYSIS_SYSTEM},
                {
                    "role": "user",
                    "content": f"Mensaje del usuario a analizar:\n{text}",
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=600,
            temperature=0.2,
        )
        raw = completion.choices[0].message.content
        if raw is None:
            logger.warning("Análisis estructurado: contenido de respuesta vacío del modelo")
            return None
        try:
            data = json.loads(str(raw).strip())
        except json.JSONDecodeError as err:
            logger.warning(
                "Análisis estructurado: no se pudo parsear JSON del modelo: %s",
                err,
            )
            return None
        if not isinstance(data, dict):
            logger.warning("Análisis estructurado: la respuesta JSON no es un objeto")
            return None
        out = _normalize_analysis(data)
        if out is None:
            logger.warning(
                "Análisis estructurado: normalización rechazada (intent o campos inválidos)"
            )
        return out
    except Exception:
        logger.exception("Error en OpenAI: análisis estructurado fallido")
        return None


def _normalize_calendar_extraction(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    intent_raw = str(data.get("intent", "")).strip().lower()
    if intent_raw not in ("calendar_event", "not_calendar"):
        return None

    def _opt_str(key: str) -> Optional[str]:
        v = data.get(key)
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    title = _opt_str("title")
    date_text = _opt_str("date_text")
    time_text = _opt_str("time_text")
    location = _opt_str("location")
    description = _opt_str("description")
    source_text = _opt_str("source_text") or ""

    raw_parts = data.get("participants")
    participants: list[str] = []
    if isinstance(raw_parts, list):
        for p in raw_parts:
            if p is None:
                continue
            ps = str(p).strip()
            if ps:
                participants.append(ps)

    duration_minutes: Optional[int] = None
    raw_dur = data.get("duration_minutes")
    if raw_dur is not None and raw_dur != "":
        try:
            duration_minutes = int(raw_dur)
        except (TypeError, ValueError):
            duration_minutes = None

    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        return None
    confidence = max(0.0, min(1.0, confidence))

    needs_confirmation = bool(data.get("needs_confirmation", True))

    raw_miss = data.get("missing_fields")
    missing_fields: list[str] = []
    if isinstance(raw_miss, list):
        for m in raw_miss:
            if m is None:
                continue
            ms = str(m).strip()
            if ms:
                missing_fields.append(ms)

    reason = str(data.get("reason", "")).strip() or "—"

    return {
        "intent": intent_raw,
        "title": title,
        "date_text": date_text,
        "time_text": time_text,
        "location": location,
        "description": description,
        "participants": participants,
        "duration_minutes": duration_minutes,
        "source_text": source_text,
        "confidence": confidence,
        "needs_confirmation": needs_confirmation,
        "missing_fields": missing_fields,
        "reason": reason,
    }


def _compact_event_for_agenda_prompt(ev: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(ev, dict):
        return {}
    out: dict[str, Any] = {"id": ev.get("id")}
    for key in (
        "title",
        "date_text",
        "time_text",
        "location",
        "description",
        "participants",
        "duration_minutes",
    ):
        if key in ev and ev[key] is not None:
            out[key] = ev[key]
    return out


# ---------------------------------------------------------------------------
# v0.21.1 / v0.21.1b — Ficha operativa de agenda (context packet).
#
# Constructor SIN efectos secundarios para futuras llamadas estructuradas a GPT.
# No se integra todavía en el flujo principal del motor: queda disponible para
# que próximas subfases lo pasen como `messages[user]` en lugar del texto crudo.
#
# v0.21.1b: modulariza el contrato en constantes públicas y añade bloque `user`
# (preparación multiusuario sin login ni base de datos).
# ---------------------------------------------------------------------------

# Identidad por defecto (mientras no exista login real)
DEFAULT_USER_ID = "local_default_user"
DEFAULT_LOCALE = "es-ES"
DEFAULT_TIMEZONE = "Europe/Madrid"

AGENDA_CONTEXT_DEFAULT_DOMAIN = "agenda"
AGENDA_CONTEXT_RELEVANT_EVENTS_DEFAULT = 8

AGENDA_CONTEXT_ALLOWED_OPERATIONS: tuple[str, ...] = (
    "create_event",
    "query_agenda",
    "update_event",
    "restructure_agenda",
    "summarize_agenda",
    "ask_clarification",
    "request_more_data",
    "not_calendar",
)

AGENDA_CONTEXT_LIMITS: tuple[str, ...] = (
    "No inventar eventos.",
    "No inventar fecha, hora, lugar ni participantes.",
    "No borrar ni fusionar eventos sin confirmación.",
    "No responder desde conocimiento general si el mensaje pertenece a agenda.",
    "Usar solo los eventos proporcionados cuando se consulte la agenda.",
)

AGENDA_CONTEXT_INSTRUCTIONS: dict[str, Any] = {
    "task": "interpret_agenda_message",
    "infer": True,
    "do_not_dump_raw_data": True,
    "detect_duplicates": True,
    "detect_conflicts": True,
    "detect_suspicious_entries": True,
    "ask_if_missing_required_data": True,
}

AGENDA_CONTEXT_OUTPUT_SCHEMA: dict[str, Any] = {
    "operation": (
        "create_event | query_agenda | update_event | restructure_agenda | "
        "summarize_agenda | ask_clarification | request_more_data | not_calendar"
    ),
    "confidence": 0.0,
    "answer": None,
    "event_data": {},
    "query": {},
    "updates": {},
    "detected_groups": [],
    "conflicts": [],
    "suspicious_entries": [],
    "needs_more_data": False,
    "data_request": None,
    "missing_fields": [],
    "reason": "",
}

# Aliases internos para no romper imports antiguos.
_AGENDA_CONTEXT_RELEVANT_EVENTS_DEFAULT = AGENDA_CONTEXT_RELEVANT_EVENTS_DEFAULT
_AGENDA_CONTEXT_ALLOWED_OPERATIONS = AGENDA_CONTEXT_ALLOWED_OPERATIONS
_AGENDA_CONTEXT_LIMITS = AGENDA_CONTEXT_LIMITS


def _deep_copy_constants() -> tuple[list[str], list[str], dict[str, Any], dict[str, Any]]:
    """Copias defensivas de las constantes para que el llamador no pueda mutarlas."""
    return (
        list(AGENDA_CONTEXT_ALLOWED_OPERATIONS),
        list(AGENDA_CONTEXT_LIMITS),
        dict(AGENDA_CONTEXT_INSTRUCTIONS),
        {
            k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
            for k, v in AGENDA_CONTEXT_OUTPUT_SCHEMA.items()
        },
    )


def _resolve_user_block(
    user_id: Optional[str], user_profile: Optional[dict[str, Any]]
) -> dict[str, Any]:
    """Bloque `user` de la ficha. Provisional (sin login) hasta que exista identidad real."""
    uid = (str(user_id).strip() if user_id else "") or DEFAULT_USER_ID
    profile = user_profile if isinstance(user_profile, dict) else {}

    def _str_or_default(key: str, default: Optional[str]) -> Optional[str]:
        v = profile.get(key)
        if v is None:
            return default
        s = str(v).strip()
        return s or default

    return {
        "user_id": uid,
        "display_name": _str_or_default("display_name", None),
        "timezone": _str_or_default("timezone", DEFAULT_TIMEZONE),
        "locale": _str_or_default("locale", DEFAULT_LOCALE),
    }


def build_agenda_context_packet(
    user_text: str,
    events: Optional[list[dict[str, Any]]] = None,
    focused_event: Optional[dict[str, Any]] = None,
    last_agenda_context: Optional[dict[str, Any]] = None,
    max_relevant_events: int = AGENDA_CONTEXT_RELEVANT_EVENTS_DEFAULT,
    user_id: Optional[str] = None,
    user_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Construye la ficha operativa breve que se pasará a GPT en próximas subfases.
    No hace llamadas, no consulta disco. Solo arma el dict en memoria.

    `user_id` y `user_profile` son opcionales: si faltan, se usa
    `DEFAULT_USER_ID` y los valores por defecto de zona/locale.
    """
    msg = (user_text or "").strip()

    ev_list = events or []
    cap = max_relevant_events if max_relevant_events and max_relevant_events > 0 else 0
    capped: list[dict[str, Any]] = []
    for ev in ev_list[:cap]:
        if isinstance(ev, dict):
            compact = _compact_event_for_agenda_prompt(ev)
            # Preserva user_id del evento si ya lo trae (multiusuario futuro).
            if ev.get("user_id") is not None:
                compact["user_id"] = ev.get("user_id")
            capped.append(compact)

    last_ctx = last_agenda_context if isinstance(last_agenda_context, dict) else {}
    focused = focused_event if isinstance(focused_event, dict) else None
    has_pending_action = bool(last_ctx.get("has_pending_action", False))
    focused_event_id = focused.get("id") if focused else None

    user_block = _resolve_user_block(user_id, user_profile)
    allowed_ops, limits, instruction, output_schema = _deep_copy_constants()

    packet: dict[str, Any] = {
        "user_message": msg,
        "user": user_block,
        "context": {
            "domain": AGENDA_CONTEXT_DEFAULT_DOMAIN,
            "last_operation": last_ctx.get("last_operation"),
            "last_topic": last_ctx.get("last_topic"),
            "last_answer_summary": last_ctx.get("last_answer_summary"),
        },
        "conversation_state": {
            "has_pending_action": has_pending_action,
            "has_focused_event": focused is not None,
            "focused_event_id": focused_event_id,
        },
        "relevant_data": {
            "events": capped,
        },
        "instruction": instruction,
        "allowed_operations": allowed_ops,
        "limits": limits,
        "output_schema": output_schema,
    }

    logger.debug(
        "context_packet construido: user_id=%s, eventos=%d, hay_foco=%s, has_pending=%s",
        user_block["user_id"],
        len(capped),
        focused is not None,
        has_pending_action,
    )
    return packet


# ---------------------------------------------------------------------------
# v0.21.2 — Razonamiento estructurado sobre la ficha operativa.
#
# Envía el `context_packet` producido por build_agenda_context_packet(...) a GPT
# y devuelve un dict Python que respeta el `output_schema`. Solo razonamiento:
# no ejecuta acciones ni toca disco.
# ---------------------------------------------------------------------------

_AGENDA_CTX_REASONING_SYSTEM = """Eres el MOTOR ESTRUCTURADO DE AGENDA de ARIS (asistente personal local).
No eres un chat general. Tu única entrada útil es la ficha operativa JSON que recibes en el mensaje del usuario.
Tu única salida válida es UN ÚNICO objeto JSON (sin markdown, sin texto fuera del JSON).

Debes basarte SOLO en:
- ficha["user_message"]
- ficha["context"]
- ficha["conversation_state"]
- ficha["relevant_data"] (incluye los eventos que se te pasan; no inventes otros)
- ficha["allowed_operations"]
- ficha["limits"]
- ficha["output_schema"] (estructura exacta a devolver)

Reglas:
- NO uses conocimiento general ajeno a la ficha.
- NO inventes eventos, fechas, horas, lugares ni participantes.
- NO devuelvas texto crudo si el usuario pide una síntesis: agrupa en `detected_groups` y resume en `answer`.
- Detecta duplicados probables (mismo título/fecha/hora con variantes de mayúsculas o formato) → `detected_groups`.
- Detecta solapamientos (misma fecha y horas que chocan) → `conflicts`.
- Detecta entradas sospechosas (texto tipo pregunta guardado como evento, sin fecha clara, basura) → `suspicious_entries`.
- Si faltan datos para decidir con seguridad, usa `request_more_data` con `data_request` y `missing_fields`.
- Si el mensaje es ambiguo, usa `ask_clarification` y propón en `answer` una pregunta breve.
- Si el mensaje NO trata sobre agenda, usa `not_calendar`.

`operation` debe ser EXACTAMENTE uno de:
- create_event
- query_agenda
- update_event
- restructure_agenda
- summarize_agenda
- ask_clarification
- request_more_data
- not_calendar

Devuelve siempre TODAS las claves del `output_schema`, con `null` o listas/objetos vacíos cuando no apliquen.
`confidence` ∈ [0, 1]. `reason` es una frase breve en español para depuración.
"""


def _coerce_float_in_range(value: Any, lo: float = 0.0, hi: float = 1.0, default: float = 0.0) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _ensure_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_agenda_reasoning_result(result: Any) -> Optional[dict[str, Any]]:
    """
    Validación mínima del JSON devuelto por GPT para la ficha operativa.
    Asegura estructura básica para que el backend no rompa. Devuelve dict normalizado o None.
    """
    if not isinstance(result, dict):
        logger.warning("agenda_reasoning: resultado no es dict (%s)", type(result).__name__)
        return None

    op_raw = str(result.get("operation", "")).strip()
    if op_raw not in AGENDA_CONTEXT_ALLOWED_OPERATIONS:
        logger.warning(
            "agenda_reasoning: operación no permitida '%s' → fallback ask_clarification",
            op_raw,
        )
        operation = "ask_clarification"
    else:
        operation = op_raw

    confidence = _coerce_float_in_range(result.get("confidence"), 0.0, 1.0, 0.0)

    answer_raw = result.get("answer")
    if answer_raw is None:
        answer: Optional[str] = None
    else:
        answer = str(answer_raw).strip() or None

    reason_raw = result.get("reason")
    reason = str(reason_raw).strip() if reason_raw is not None else ""

    data_request_raw = result.get("data_request")
    if data_request_raw is None:
        data_request: Optional[str] = None
    else:
        data_request = str(data_request_raw).strip() or None

    needs_more_data = bool(result.get("needs_more_data", False))

    normalized: dict[str, Any] = {
        "operation": operation,
        "confidence": confidence,
        "answer": answer,
        "event_data": _ensure_dict(result.get("event_data")),
        "query": _ensure_dict(result.get("query")),
        "updates": _ensure_dict(result.get("updates")),
        "detected_groups": _ensure_list(result.get("detected_groups")),
        "conflicts": _ensure_list(result.get("conflicts")),
        "suspicious_entries": _ensure_list(result.get("suspicious_entries")),
        "needs_more_data": needs_more_data,
        "data_request": data_request,
        "missing_fields": [
            str(x).strip() for x in _ensure_list(result.get("missing_fields")) if str(x).strip()
        ],
        "reason": reason,
    }
    return normalized


def try_agenda_context_reasoning(
    context_packet: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """
    Envía la ficha operativa a GPT y devuelve un dict Python normalizado.

    Sin API key, error de OpenAI, JSON inválido o validación rechazada → None.
    No ejecuta acciones: solo razonamiento.
    """
    if not isinstance(context_packet, dict):
        logger.warning("agenda_reasoning: context_packet no es dict")
        return None

    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        logger.debug("agenda_reasoning: sin OPENAI_API_KEY; se omite la llamada")
        return None

    model = (os.getenv("OPENAI_MODEL") or "gpt-5.5").strip() or "gpt-5.5"

    user_block_dbg = context_packet.get("user") if isinstance(context_packet.get("user"), dict) else {}
    relevant = context_packet.get("relevant_data") or {}
    events_dbg = relevant.get("events") if isinstance(relevant, dict) else []
    n_events = len(events_dbg) if isinstance(events_dbg, list) else 0
    user_id_dbg = user_block_dbg.get("user_id") if isinstance(user_block_dbg, dict) else None

    logger.debug(
        "agenda_reasoning: llamando a GPT (model=%s, user_id=%s, eventos=%d)",
        model,
        user_id_dbg,
        n_events,
    )

    try:
        payload = json.dumps(context_packet, ensure_ascii=False)
    except (TypeError, ValueError):
        logger.exception("agenda_reasoning: context_packet no serializable a JSON")
        return None

    user_block = (
        "Ficha operativa de agenda (JSON). Razona y devuelve SOLO un JSON "
        "que cumpla output_schema:\n"
        f"{payload}"
    )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _AGENDA_CTX_REASONING_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            response_format={"type": "json_object"},
            max_tokens=900,
            temperature=0.2,
        )
        raw = completion.choices[0].message.content
        if raw is None:
            logger.warning("agenda_reasoning: contenido vacío del modelo")
            return None
        try:
            data = json.loads(str(raw).strip())
        except json.JSONDecodeError as err:
            logger.warning("agenda_reasoning: JSON inválido del modelo: %s", err)
            return None
        out = validate_agenda_reasoning_result(data)
        if out is None:
            logger.warning("agenda_reasoning: validación rechazada")
            return None
        logger.debug(
            "agenda_reasoning OK: user_id=%s eventos=%d operation=%s confidence=%.2f",
            user_id_dbg,
            n_events,
            out["operation"],
            out["confidence"],
        )
        return out
    except Exception:
        logger.exception("agenda_reasoning: fallo al llamar a OpenAI")
        return None


# ---------------------------------------------------------------------------
# v0.21.4 — Completar pending_action de calendario sin perder datos.
#
# El usuario está respondiendo a una pregunta de ARIS sobre datos faltantes de un
# evento pendiente. Esta función interpreta la respuesta SOLO como completado del
# pending (no como nueva nota/tarea/evento).
# ---------------------------------------------------------------------------

_COMPLETE_PENDING_INTENTS = frozenset(
    {"complete_pending_event", "confirm", "cancel", "needs_clarification", "other"}
)

_COMPLETE_PENDING_SYSTEM = """Eres el COMPLETADOR DE EVENTO PENDIENTE de ARIS (asistente personal local).

Existe una pending_action de calendario a la que le faltan algunos datos.
El usuario acaba de responder. NO interpretes su mensaje como nota, tarea ni
evento nuevo independiente: SIEMPRE asumes que está respondiendo para COMPLETAR
el evento pendiente.

Tu salida es UN ÚNICO JSON válido (sin markdown ni texto fuera del JSON):

{
  "intent": "complete_pending_event" | "confirm" | "cancel" | "needs_clarification" | "other",
  "updates": {
    "title": null,
    "date_text": null,
    "time_text": null,
    "location": null,
    "participants": [],
    "description": null,
    "duration_minutes": null
  },
  "confidence": 0.0,
  "missing_fields": [],
  "reason": ""
}

Reglas:
- Si el usuario dice "sí" / "vale" / "adelante" / "guárdalo": intent = "confirm" y updates vacío.
- Si dice "no" / "cancela" / "olvídalo" / "déjalo": intent = "cancel".
- Si aporta datos del evento (lugar, persona, hora, día, título mejor):
  intent = "complete_pending_event" y rellena SOLO los campos que aporte el usuario.
- Si responde algo no relacionado con el evento pendiente: intent = "other".
- NO inventes ubicaciones, personas, fechas, horas ni participantes.
- "en X" → location = "X" (sin las palabras "en " "a "). Conserva artículos naturales: "en el hospital" → location = "el hospital" o "hospital" (cualquiera coherente).
- "con X" / "con el X" → participants += ["X"]. Si menciona varios separados por "y" o ",", añade todos.
- "mañana", "el viernes", etc. → date_text como texto literal (sin convertir a ISO).
- "a las 3", "a las 15:00" → time_text en forma natural ("15:00" o "3").
- No mezcles location y participants: "en el hospital con el doctor carrera"
  ⇒ location="hospital" (o "el hospital"), participants=["doctor carrera"] (o "el doctor carrera").
- Devuelve "missing_fields" con los nombres de campo que aún no tienes ni en pending ni en updates,
  entre: ["title", "date_text", "time_text", "location", "participants"].
- "reason": una frase breve en español para depuración.

Devuelve SOLO JSON válido."""


def _normalize_complete_pending(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not isinstance(data, dict):
        return None
    intent_raw = str(data.get("intent", "")).strip().lower()
    if intent_raw not in _COMPLETE_PENDING_INTENTS:
        intent_raw = "needs_clarification"

    try:
        conf = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    if conf < 0:
        conf = 0.0
    if conf > 1:
        conf = 1.0

    upd_raw = data.get("updates")
    upd = upd_raw if isinstance(upd_raw, dict) else {}

    def _s(key: str) -> Optional[str]:
        v = upd.get(key)
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    raw_parts = upd.get("participants")
    participants: list[str] = []
    if isinstance(raw_parts, list):
        for p in raw_parts:
            if p is None:
                continue
            s = str(p).strip()
            if s:
                participants.append(s)

    duration: Optional[int] = None
    raw_dur = upd.get("duration_minutes")
    if raw_dur is not None and raw_dur != "":
        try:
            duration = int(raw_dur)
        except (TypeError, ValueError):
            duration = None

    missing = data.get("missing_fields")
    missing_norm: list[str] = []
    if isinstance(missing, list):
        for m in missing:
            s = str(m).strip()
            if s:
                missing_norm.append(s)

    reason = str(data.get("reason") or "").strip()

    return {
        "intent": intent_raw,
        "updates": {
            "title": _s("title"),
            "date_text": _s("date_text"),
            "time_text": _s("time_text"),
            "location": _s("location"),
            "participants": participants,
            "description": _s("description"),
            "duration_minutes": duration,
        },
        "confidence": conf,
        "missing_fields": missing_norm,
        "reason": reason,
    }


def try_complete_pending_calendar_event(
    user_text: str,
    pending_action: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """
    Interpreta la respuesta del usuario como COMPLETADO de la pending_action de calendario.

    Devuelve dict normalizado o None ante: sin API key, error de OpenAI, JSON inválido,
    validación rechazada o entrada vacía.
    """
    text = (user_text or "").strip()
    if not text:
        return None
    if not isinstance(pending_action, dict):
        return None

    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        logger.debug("complete_pending_calendar: sin OPENAI_API_KEY")
        return None

    model = (os.getenv("OPENAI_MODEL") or "gpt-5.5").strip() or "gpt-5.5"

    pending_view = {
        "title": pending_action.get("title"),
        "date_text": pending_action.get("date_text"),
        "time_text": pending_action.get("time_text"),
        "location": pending_action.get("location"),
        "participants": list(pending_action.get("participants") or []),
        "description": pending_action.get("description"),
        "duration_minutes": pending_action.get("duration_minutes"),
        "missing_fields": list(pending_action.get("missing_fields") or []),
        "original_text": pending_action.get("original_text"),
    }
    try:
        pending_payload = json.dumps(pending_view, ensure_ascii=False)
    except (TypeError, ValueError):
        logger.exception("complete_pending_calendar: pending no serializable")
        return None

    user_block = (
        "Pending_action de calendario (datos ya conocidos, en JSON):\n"
        f"{pending_payload}\n\n"
        "Respuesta actual del usuario (puede venir de voz transcrita):\n"
        f"{text}"
    )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _COMPLETE_PENDING_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            response_format={"type": "json_object"},
            max_tokens=500,
            temperature=0.15,
        )
        raw = completion.choices[0].message.content
        if raw is None:
            logger.warning("complete_pending_calendar: contenido vacío del modelo")
            return None
        try:
            data = json.loads(str(raw).strip())
        except json.JSONDecodeError as err:
            logger.warning("complete_pending_calendar: JSON inválido: %s", err)
            return None
        out = _normalize_complete_pending(data)
        if out is None:
            logger.warning("complete_pending_calendar: normalización rechazada")
            return None
        logger.debug(
            "complete_pending_calendar OK: intent=%s confidence=%.2f location=%s participants=%d",
            out["intent"],
            out["confidence"],
            bool(out["updates"].get("location")),
            len(out["updates"].get("participants") or []),
        )
        return out
    except Exception:
        logger.exception("complete_pending_calendar: fallo en OpenAI")
        return None


# ---------------------------------------------------------------------------
# v0.21.4d — Notas estructuradas: título inferido, contenido NO inventado.
#
# Distinguir TEMA/TÍTULO (lo que la nota trata) de CONTENIDO REAL (lo que la
# nota dice). GPT puede inferir el título a partir del tema, pero nunca
# inventa, desarrolla, explica ni amplía el contenido.
# ---------------------------------------------------------------------------

_NOTE_STRUCT_INTENTS = frozenset(
    {
        "note_title_only",
        "note_content",
        "note_title_and_content",
        "cancel",
        "needs_clarification",
        "other",
    }
)

_NOTE_STRUCT_SYSTEM = """Eres el ESTRUCTURADOR DE NOTAS de ARIS (asistente personal local).

El usuario está creando una NOTA. Tu única tarea es separar TÍTULO y CONTENIDO
sin inventar nada. No expliques, no desarrolles, no amplíes, no resumas el
contenido. NO uses tu conocimiento general para completar la nota.

Tu salida es UN ÚNICO JSON válido (sin markdown ni texto fuera del JSON):

{
  "intent": "note_title_only" | "note_content" | "note_title_and_content" | "cancel" | "needs_clarification" | "other",
  "title": null,
  "content": null,
  "confidence": 0.0,
  "missing_fields": [],
  "reason": ""
}

Cómo distinguir tema/título y contenido:
- Es TEMA/TÍTULO cuando el usuario solo nombra ASUNTO o ÁREA, sin afirmar nada
  concreto sobre él. Ej.: "una reflexión sobre X", "una idea sobre X",
  "algo sobre X", "una nota sobre X". El usuario indica DE QUÉ va la nota,
  no QUÉ dice.
- Es CONTENIDO cuando hay una AFIRMACIÓN, descripción, hipótesis o frase con
  verbo principal que dice algo concreto. Ej.: "podría tratarse de…",
  "X es Y porque…", "X funciona como…", "mañana llamo a Z para…".
- Si hay duda, prefiere "needs_clarification" o "note_title_only".

Reglas duras:
- NO inventes contenido. Si el usuario solo da un TEMA, intent = "note_title_only"
  y content = null.
- Si hay contenido real, copia el texto del usuario en "content" haciendo solo
  cambios mínimos: mayúscula inicial, punto final, eliminar muletilla inicial
  muy evidente ("eh,", "pues,", "bueno,"). No reescribas, no resumas, no
  expandas. Conserva el sentido y casi las palabras.
- Si el usuario aporta "título: X. contenido: Y" (o "title: X" / "content: Y"),
  intent = "note_title_and_content".
- Si el usuario dice "no" / "cancela" / "olvídalo" / "no lo guardes":
  intent = "cancel".
- Si el mensaje no parece dirigido a la nota: intent = "other".

Inferencia de título (solo desde el texto del usuario, sin añadir ideas):
- Para TEMA: convierte "una reflexión sobre X" → "Reflexión sobre X";
  "una idea sobre X" → "Idea sobre X"; "algo sobre X" → "X" o "Nota sobre X".
- Para CONTENIDO sin título explícito: genera un título corto (3–8 palabras)
  basado SOLO en sustantivos/claves del propio contenido. No añadas conceptos
  externos.
- Capitaliza solo la primera palabra; mantén nombres propios.
- Sin comillas, sin punto final.

"missing_fields": lista los campos aún sin valor:
- Si solo title: ["content"].
- Si solo content: [] (porque title puede inferirse).
- Si nada: ["title_or_content"].

"reason": una frase breve en español para depuración.

Si hay un pending de nota con un "title" ya guardado y el nuevo mensaje aporta
contenido, intent = "note_content" y NO repitas el título: solo devuelve
"content". El backend reutilizará el título pendiente.

Devuelve SOLO JSON válido."""


def _normalize_note_struct(data: Any) -> Optional[dict[str, Any]]:
    if not isinstance(data, dict):
        return None
    intent_raw = str(data.get("intent", "")).strip().lower()
    if intent_raw not in _NOTE_STRUCT_INTENTS:
        intent_raw = "needs_clarification"

    try:
        conf = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))

    def _s(key: str) -> Optional[str]:
        v = data.get(key)
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    missing = data.get("missing_fields")
    missing_norm: list[str] = []
    if isinstance(missing, list):
        for m in missing:
            s = str(m).strip()
            if s:
                missing_norm.append(s)

    reason = str(data.get("reason") or "").strip()

    return {
        "intent": intent_raw,
        "title": _s("title"),
        "content": _s("content"),
        "confidence": conf,
        "missing_fields": missing_norm,
        "reason": reason,
    }


def try_note_structuring(
    user_text: str,
    pending_note: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """
    Estructura el mensaje del usuario como título/contenido de nota.

    Devuelve dict normalizado o None ante: sin API key, error de OpenAI,
    JSON inválido o entrada vacía. El llamador (assistant_engine) debe tener
    un fallback local si esta función devuelve None.
    """
    text = (user_text or "").strip()
    if not text:
        return None

    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        logger.debug("note_structuring: sin OPENAI_API_KEY")
        return None

    model = (os.getenv("OPENAI_MODEL") or "gpt-5.5").strip() or "gpt-5.5"

    pending_view: dict[str, Any] = {}
    if isinstance(pending_note, dict):
        pending_view = {
            "title": pending_note.get("title"),
            "content": pending_note.get("content"),
            "missing_fields": list(pending_note.get("missing_fields") or []),
            "original_text": pending_note.get("original_text"),
        }
    try:
        pending_payload = json.dumps(pending_view, ensure_ascii=False)
    except (TypeError, ValueError):
        pending_payload = "{}"

    user_block = (
        "Pending_action de nota (datos ya conocidos, en JSON):\n"
        f"{pending_payload}\n\n"
        "Mensaje actual del usuario (puede venir de voz transcrita):\n"
        f"{text}"
    )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _NOTE_STRUCT_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            response_format={"type": "json_object"},
            max_tokens=500,
            temperature=0.1,
        )
        raw = completion.choices[0].message.content
        if raw is None:
            logger.warning("note_structuring: contenido vacío del modelo")
            return None
        try:
            data = json.loads(str(raw).strip())
        except json.JSONDecodeError as err:
            logger.warning("note_structuring: JSON inválido: %s", err)
            return None
        out = _normalize_note_struct(data)
        if out is None:
            logger.warning("note_structuring: normalización rechazada")
            return None
        logger.debug(
            "note_structuring OK: intent=%s confidence=%.2f title=%s content=%s",
            out["intent"],
            out["confidence"],
            bool(out.get("title")),
            bool(out.get("content")),
        )
        return out
    except Exception:
        logger.exception("note_structuring: fallo en OpenAI")
        return None


def _normalize_agenda_motor(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    ci = str(data.get("calendar_intent", "")).strip().lower()
    if ci not in _AGENDA_INTENTS:
        return None
    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        return None
    confidence = max(0.0, min(1.0, confidence))

    raw_rf = data.get("requested_field")
    if raw_rf is None or raw_rf == "":
        requested_field = None
    else:
        rf = str(raw_rf).strip().lower()
        requested_field = rf if rf in _REQUESTED_FIELDS else "unknown"

    raw_tid = data.get("target_event_id")
    if raw_tid is None or raw_tid == "":
        target_event_id = None
    else:
        target_event_id = str(raw_tid).strip() or None

    raw_ed = data.get("event_data")
    if not isinstance(raw_ed, dict):
        raw_ed = {}

    def _os(k: str) -> Optional[str]:
        v = raw_ed.get(k)
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    title = _os("title")
    date_text = _os("date_text")
    time_text = _os("time_text")
    location = _os("location")
    description = _os("description")

    raw_parts = raw_ed.get("participants")
    participants: list[str] = []
    if isinstance(raw_parts, list):
        for p in raw_parts:
            if p is None:
                continue
            ps = str(p).strip()
            if ps:
                participants.append(ps)

    duration_minutes: Optional[int] = None
    raw_dur = raw_ed.get("duration_minutes")
    if raw_dur is not None and raw_dur != "":
        try:
            duration_minutes = int(raw_dur)
        except (TypeError, ValueError):
            duration_minutes = None

    raw_miss = data.get("missing_fields")
    missing_fields: list[str] = []
    if isinstance(raw_miss, list):
        for m in raw_miss:
            if m is None:
                continue
            ms = str(m).strip()
            if ms:
                missing_fields.append(ms)

    raw_ans = data.get("answer")
    if raw_ans is None or raw_ans == "":
        answer = None
    else:
        answer = str(raw_ans).strip() or None

    reason = str(data.get("reason", "")).strip() or "—"

    event_data = {
        "title": title,
        "date_text": date_text,
        "time_text": time_text,
        "location": location,
        "description": description,
        "participants": participants,
        "duration_minutes": duration_minutes,
    }

    return {
        "calendar_intent": ci,
        "target_event_id": target_event_id,
        "requested_field": requested_field,
        "event_data": event_data,
        "answer": answer,
        "missing_fields": missing_fields,
        "confidence": confidence,
        "reason": reason,
    }


def try_agenda_intent_analysis(
    user_text: str,
    candidate_events: Optional[list[dict[str, Any]]] = None,
    focused_event: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """
    Motor de agenda: interpreta creación, consulta, actualización o fuera de agenda.
    Sin API key o error → None (el llamador trata como not_calendar).
    """
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        logger.info("Motor agenda GPT: sin OPENAI_API_KEY; omitido")
        return None

    model = (os.getenv("OPENAI_MODEL") or "gpt-5.5").strip() or "gpt-5.5"
    text = (user_text or "").strip()
    if not text:
        return None

    cands = candidate_events or []
    compact_c = [_compact_event_for_agenda_prompt(ev) for ev in cands if isinstance(ev, dict)]
    compact_f = (
        _compact_event_for_agenda_prompt(focused_event)
        if isinstance(focused_event, dict)
        else None
    )
    payload = {
        "eventos_candidatos": compact_c,
        "evento_enfocado": compact_f,
        "mensaje_usuario": text,
    }
    user_block = json.dumps(payload, ensure_ascii=False)

    logger.info(
        "Motor agenda GPT: llamada al modelo (candidatos=%d, hay_foco=%s)",
        len(compact_c),
        compact_f is not None,
    )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _AGENDA_MOTOR_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            response_format={"type": "json_object"},
            max_tokens=900,
            temperature=0.12,
        )
        raw = completion.choices[0].message.content
        if raw is None:
            logger.warning("Motor agenda GPT: contenido vacío del modelo")
            return None
        try:
            pdata = json.loads(str(raw).strip())
        except json.JSONDecodeError as err:
            logger.warning("Motor agenda GPT: JSON inválido: %s", err)
            return None
        if not isinstance(pdata, dict):
            logger.warning("Motor agenda GPT: respuesta no es objeto JSON")
            return None
        out = _normalize_agenda_motor(pdata)
        if out is None:
            logger.warning("Motor agenda GPT: normalización rechazada")
            return None
        logger.info(
            "Motor agenda GPT: calendar_intent=%s confidence=%.2f target_id=%s",
            out["calendar_intent"],
            out["confidence"],
            out.get("target_event_id"),
        )
        logger.debug("MaG reason=%s", str(out.get("reason", ""))[:200])
        return out
    except Exception:
        logger.exception("Error en OpenAI: motor agenda fallido")
        return None


def _opt_str_from(d: dict[str, Any], key: str) -> Optional[str]:
    if not isinstance(d, dict):
        return None
    v = d.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _opt_int_from(d: dict[str, Any], key: str) -> Optional[int]:
    if not isinstance(d, dict):
        return None
    v = d.get(key)
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _opt_str_list_from(d: dict[str, Any], key: str) -> list[str]:
    if not isinstance(d, dict):
        return []
    raw = d.get(key)
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for p in raw:
        if p is None:
            continue
        s = str(p).strip()
        if s:
            out.append(s)
    return out


def _ambiguities_from_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("ambiguities")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def _normalize_unified_intent(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    ambiguities = _ambiguities_from_payload(data)

    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        return None
    confidence = max(0.0, min(1.0, confidence))
    needs_clar = bool(data.get("needs_clarification", False))
    cq = _opt_str_from(data, "clarification_question")
    assistant_reply = _opt_str_from(data, "assistant_reply")

    status_raw = str(data.get("status", "")).strip().lower()
    op_raw = str(data.get("operation", "")).strip().lower()

    if assistant_reply and not cq:
        cq = assistant_reply

    requires_confirmation = False
    if status_raw == "needs_confirmation":
        requires_confirmation = True

    op = op_raw
    if status_raw == "general_answer":
        op = "general_query"
    elif status_raw in ("needs_clarification", "needs_confirmation", "failed"):
        op = "needs_clarification"
        needs_clar = True
        if status_raw == "failed" and not cq:
            cq = "¿Puedes reformular tu mensaje con más detalle?"

    if op not in _UNIFIED_OPERATIONS:
        return None

    reason = str(data.get("reason", "")).strip() or "—"

    note_raw = data.get("note") if isinstance(data.get("note"), dict) else {}
    task_raw = data.get("task") if isinstance(data.get("task"), dict) else {}
    cev_raw = data.get("calendar_event") if isinstance(data.get("calendar_event"), dict) else {}
    cqy_raw = data.get("calendar_query") if isinstance(data.get("calendar_query"), dict) else {}
    cup_raw = data.get("calendar_update") if isinstance(data.get("calendar_update"), dict) else {}

    note = {"content": _opt_str_from(note_raw, "content")}
    task = {
        "title": _opt_str_from(task_raw, "title"),
        "date_text": _opt_str_from(task_raw, "date_text"),
        "time_text": _opt_str_from(task_raw, "time_text"),
        "priority": _opt_str_from(task_raw, "priority"),
    }
    calendar_event = {
        "title": _opt_str_from(cev_raw, "title"),
        "date_text": _opt_str_from(cev_raw, "date_text"),
        "time_text": _opt_str_from(cev_raw, "time_text"),
        "location": _opt_str_from(cev_raw, "location"),
        "participants": _opt_str_list_from(cev_raw, "participants"),
        "description": _opt_str_from(cev_raw, "description"),
        "duration_minutes": _opt_int_from(cev_raw, "duration_minutes"),
    }

    rf = _opt_str_from(cqy_raw, "requested_field")
    if rf is not None:
        rf = rf.lower()
        if rf not in _REQUESTED_FIELDS:
            rf = "unknown"
    tr_q = _opt_str_from(cqy_raw, "target_reference")
    if tr_q is not None and tr_q not in _TARGET_REFS:
        tr_q = None
    calendar_query = {
        "requested_field": rf,
        "date_text": _opt_str_from(cqy_raw, "date_text"),
        "time_text": _opt_str_from(cqy_raw, "time_text"),
        "terms": _opt_str_list_from(cqy_raw, "terms"),
        "target_reference": tr_q,
    }

    tr_u = _opt_str_from(cup_raw, "target_reference")
    if tr_u is not None and tr_u not in _TARGET_REFS:
        tr_u = None
    upd_raw = cup_raw.get("updates") if isinstance(cup_raw.get("updates"), dict) else {}
    updates = {
        "title": _opt_str_from(upd_raw, "title"),
        "date_text": _opt_str_from(upd_raw, "date_text"),
        "time_text": _opt_str_from(upd_raw, "time_text"),
        "location": _opt_str_from(upd_raw, "location"),
        "participants": _opt_str_list_from(upd_raw, "participants"),
        "description": _opt_str_from(upd_raw, "description"),
        "duration_minutes": _opt_int_from(upd_raw, "duration_minutes"),
    }
    calendar_update = {
        "target_reference": tr_u,
        "target_event_id": _opt_str_from(cup_raw, "target_event_id"),
        "updates": updates,
    }

    missing_fields = _opt_str_list_from(data, "missing_fields")

    return {
        "operation": op,
        "confidence": confidence,
        "needs_clarification": needs_clar,
        "clarification_question": cq,
        "assistant_reply": assistant_reply,
        "gpt_status": status_raw or None,
        "ambiguities": ambiguities,
        "requires_explicit_confirmation": requires_confirmation,
        "reason": reason,
        "note": note,
        "task": task,
        "calendar_event": calendar_event,
        "calendar_query": calendar_query,
        "calendar_update": calendar_update,
        "missing_fields": missing_fields,
    }


def _compact_pending_context_for_gpt(p: dict[str, Any]) -> dict[str, Any]:
    """Quita ruido de la pending antes de meterla en el prompt (v0.46a)."""
    keep = (
        "pending_kind",
        "question",
        "gpt_clarification_question",
        "original_text",
        "original_text_last",
        "suggested_intent",
        "gpt_operation",
        "clarification_step",
        "max_clarification_steps",
        "ambiguities",
        "missing_fields",
        "requires_explicit_confirmation",
        "structured_calendar_hint",
        "structured_task_hint",
        "structured_note_hint",
        "reason_gpt",
    )
    out: dict[str, Any] = {}
    if not isinstance(p, dict):
        return out
    for k in keep:
        if k in p and p[k] is not None:
            out[k] = p[k]
    out.setdefault("max_clarification_steps", 3)
    return out


def try_structured_user_intent(
    user_text: str,
    candidate_events: Optional[list[dict[str, Any]]] = None,
    focused_event: Optional[dict[str, Any]] = None,
    *,
    pending_context: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """
    Motor estructurado unificado (v0.46a): GPT clasifica intención y devuelve JSON
    alineado con `docs/architecture/aris_decision_engine_contract_v0_46a.md`.

    Sin API key o error → None (el llamador usa fallback acotado).

    ``pending_context`` opcional: pending_action previa para continuar aclaraciones
    (se envía como ``accion_pendiente_previa_v046a`` en el JSON de usuario).
    """
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        logger.info("Motor unificado GPT: sin OPENAI_API_KEY; omitido")
        return None

    model = (os.getenv("OPENAI_MODEL") or "gpt-5.5").strip() or "gpt-5.5"
    text = (user_text or "").strip()
    if not text:
        return None

    cands = candidate_events or []
    compact_c = [
        _compact_event_for_agenda_prompt(ev) for ev in cands if isinstance(ev, dict)
    ]
    compact_f = (
        _compact_event_for_agenda_prompt(focused_event)
        if isinstance(focused_event, dict)
        else None
    )
    payload: dict[str, Any] = {
        "mensaje_usuario": text,
        "eventos_candidatos": compact_c,
        "evento_enfocado": compact_f,
    }
    if pending_context:
        payload["accion_pendiente_previa_v046a"] = _compact_pending_context_for_gpt(
            pending_context
        )
    user_block = json.dumps(payload, ensure_ascii=False)

    logger.info(
        "Motor unificado GPT: llamada (candidatos=%d, hay_foco=%s, pending_v046a=%s)",
        len(compact_c),
        compact_f is not None,
        pending_context is not None,
    )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _UNIFIED_INTENT_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            response_format={"type": "json_object"},
            max_tokens=1100,
            temperature=0.1,
        )
        raw = completion.choices[0].message.content
        if raw is None:
            logger.warning("Motor unificado GPT: contenido vacío")
            return None
        try:
            pdata = json.loads(str(raw).strip())
        except json.JSONDecodeError as err:
            logger.warning("Motor unificado GPT: JSON inválido: %s", err)
            return None
        if not isinstance(pdata, dict):
            logger.warning("Motor unificado GPT: respuesta no es objeto JSON")
            return None
        out = _normalize_unified_intent(pdata)
        if out is None:
            logger.warning("Motor unificado GPT: normalización rechazada")
            return None
        logger.info(
            "Motor unificado GPT: operation=%s confidence=%.2f",
            out["operation"],
            out["confidence"],
        )
        logger.debug("Motor unificado: reason=%s", str(out.get("reason", ""))[:200])
        return out
    except Exception:
        logger.exception("Error en OpenAI: motor unificado fallido")
        return None


def _normalize_calendar_query_result(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    result = str(data.get("result", "")).strip().lower()
    if result not in _CALENDAR_QUERY_RESULTS:
        return None
    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        return None
    confidence = max(0.0, min(1.0, confidence))
    answer = _opt_str_from(data, "answer") or ""
    selected = _opt_str_from(data, "selected_event_id")
    matching = _opt_str_list_from(data, "matching_event_ids")
    reason = str(data.get("reason", "")).strip() or "—"
    return {
        "result": result,
        "selected_event_id": selected,
        "matching_event_ids": matching,
        "answer": answer,
        "confidence": confidence,
        "reason": reason,
    }


def try_resolve_calendar_query(
    user_text: str,
    calendar_query: dict[str, Any],
    candidate_events: list[dict[str, Any]],
    focused_event: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Resuelve una consulta de agenda usando solo eventos locales suministrados."""
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        logger.info("Resolutor agenda GPT: sin OPENAI_API_KEY; omitido")
        return None

    model = (os.getenv("OPENAI_MODEL") or "gpt-5.5").strip() or "gpt-5.5"
    text = (user_text or "").strip()
    if not text:
        return None

    compact_c = [
        _compact_event_for_agenda_prompt(ev)
        for ev in (candidate_events or [])
        if isinstance(ev, dict)
    ]
    compact_f = (
        _compact_event_for_agenda_prompt(focused_event)
        if isinstance(focused_event, dict)
        else None
    )
    payload = {
        "mensaje_usuario": text,
        "calendar_query": calendar_query or {},
        "eventos_candidatos": compact_c,
        "evento_enfocado": compact_f,
    }
    user_block = json.dumps(payload, ensure_ascii=False)

    logger.info(
        "Resolutor agenda GPT: llamada (candidatos=%d, hay_foco=%s)",
        len(compact_c),
        compact_f is not None,
    )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _CALENDAR_QUERY_RESOLVER_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            response_format={"type": "json_object"},
            max_tokens=700,
            temperature=0.15,
        )
        raw = completion.choices[0].message.content
        if raw is None:
            logger.warning("Resolutor agenda GPT: contenido vacío")
            return None
        try:
            pdata = json.loads(str(raw).strip())
        except json.JSONDecodeError as err:
            logger.warning("Resolutor agenda GPT: JSON inválido: %s", err)
            return None
        if not isinstance(pdata, dict):
            logger.warning("Resolutor agenda GPT: respuesta no es objeto JSON")
            return None
        out = _normalize_calendar_query_result(pdata)
        if out is None:
            logger.warning("Resolutor agenda GPT: normalización rechazada")
            return None
        logger.info(
            "Resolutor agenda GPT: result=%s confidence=%.2f",
            out["result"],
            out["confidence"],
        )
        return out
    except Exception:
        logger.exception("Error en OpenAI: resolutor de agenda fallido")
        return None


def try_calendar_event_extraction(user_text: str) -> Optional[dict[str, Any]]:
    """Extrae estructura de evento de calendario con GPT. Sin clave o error → None."""
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        logger.info("Extracción calendario GPT: sin OPENAI_API_KEY; omitida")
        return None

    model = (os.getenv("OPENAI_MODEL") or "gpt-5.5").strip() or "gpt-5.5"
    text = (user_text or "").strip()
    if not text:
        logger.info("Extracción calendario GPT: texto vacío; omitida")
        return None

    logger.info("Extracción calendario GPT: llamada al modelo")
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _CALENDAR_EVENT_SYSTEM},
                {
                    "role": "user",
                    "content": f"Mensaje del usuario (puede ser voz transcrita):\n{text}",
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=700,
            temperature=0.15,
        )
        raw = completion.choices[0].message.content
        if raw is None:
            logger.warning("Extracción calendario GPT: contenido vacío del modelo")
            return None
        try:
            pdata = json.loads(str(raw).strip())
        except json.JSONDecodeError as err:
            logger.warning("Extracción calendario GPT: JSON inválido: %s", err)
            return None
        if not isinstance(pdata, dict):
            logger.warning("Extracción calendario GPT: respuesta no es objeto JSON")
            return None
        out = _normalize_calendar_extraction(pdata)
        if out is None:
            logger.warning("Extracción calendario GPT: normalización rechazada")
            return None
        logger.info(
            "Extracción calendario GPT: intent=%s confidence=%.2f needs_confirmation=%s",
            out["intent"],
            out["confidence"],
            out["needs_confirmation"],
        )
        logger.debug(
            "Extracción calendario GPT: title=%s date_text=%s time_text=%s",
            (out.get("title") or "")[:80],
            (out.get("date_text") or "")[:80],
            (out.get("time_text") or "")[:80],
        )
        return out
    except Exception:
        logger.exception("Error en OpenAI: extracción de calendario fallida")
        return None
