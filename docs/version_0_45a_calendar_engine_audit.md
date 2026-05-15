# Versión 0.45a — Auditoría motor calendario (sin cambios de código)

## Objetivo

Registrar con precisión cómo el backend actual mezcla el **motor estructurado v0.21** (`try_structured_user_intent`, `_unified_handle_calendar_create`, pending `calendar_event_completion`) con **fallbacks legados** (`_process_fresh_legacy`, `_process_calendar_with_extraction`, `try_calendar_event_extraction`), hasta llegar a **`events_store.add_event`**.

## Archivos revisados

| Área | Archivo |
|------|---------|
| Orquestación motor | [`backend/core/assistant_engine.py`](../backend/core/assistant_engine.py) |
| Cliente OpenAI / contratos JSON | [`backend/core/openai_client.py`](../backend/core/openai_client.py) |
| Persistencia eventos | [`backend/storage/events_store.py`](../backend/storage/events_store.py) |
| Cableado HTTP | [`backend/main.py`](../backend/main.py) |

## Hallazgos (resumen)

1. **Dos mundos paralelos**: mensaje fresco puede ir por **motor unificado GPT** → `_dispatch_unified_motor` → `_unified_handle_calendar_create`, o si GPT unificado **no existe** (`None` sin clave o error), por **`_process_fresh_legacy`** hasta keywords «calendario» y **`_process_calendar_with_extraction`**.
2. **Extracción legada frágil**: `_process_calendar_with_extraction` ante **`None`** o **`not_calendar`** devuelve **`intent_type="calendario"`** y **`stored_override=raw`**.
3. **`main.py`** interpreta cualquier **`stored_override`** no-dict en rama calendario como **`add_event(str)`**, generando eventos solo con **`title` = texto completo** del usuario.
4. **Otro riesgo**: confirmaciones **`save_as_event` / `_confirmation_saved_reply`** para calendario **no enriquecido** también pasan **string** a `main.py` → mismo patrón de título monolítico.
5. **`build_agenda_context_packet` / `try_agenda_context_reasoning`**: usados en síntesis/revisión de agenda (follow-ups, duplicados, etc.), no sustituyen el flujo de creación vía `POST /message` para la frase tipo cita salvo rutas específicas documentadas en la auditoría larga.

## Qué no se ha hecho en 0.45a

- Ningún cambio en código de producción, prompts, Flutter, endpoints ni datos bajo `data/`.
- No se ha ejecutado borrado ni migración de eventos.

## Documento detallado

Ver tablas y diagrama completos en [`docs/backend_calendar_engine_audit_v0_45a.md`](backend_calendar_engine_audit_v0_45a.md).

## Decisión recomendada para v0.45b

1. **Eliminar o acotar** el retorno **`("calendario", raw)`** en `_process_calendar_with_extraction`; sustituir por **pending estructurada** o **`ambiguo`** sin persistir.
2. **Unificar política `stored_override`**: para calendario, solo **`dict`** o **`None`** en caminos nuevos; deprecar **`str`** salvo compat explícita.
3. Opcional: reutilizar **heurística local** ya presente en completado de pending para crear un **dict mínimo** cuando GPT falla pero el texto tiene señales de día/hora/persona.
