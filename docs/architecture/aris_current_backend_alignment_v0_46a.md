# Alineación del backend actual con el contrato v0.46a

Documento de **auditoría**: qué existe hoy, qué es legado, qué se mantiene y qué queda como deuda. El código fuente mandará siempre; esto sirve como mapa cognitivo.

---

## 1. Funciones y piezas relevantes

| Área | Qué es |
|------|--------|
| `AssistantEngine.process_message` | Punto de entrada HTTP indirecto desde `main.message` |
| `_process_fresh` | Prefiltros locales + llamada **GPT** `try_structured_user_intent` + `_dispatch_unified_motor` |
| `_process_fresh_legacy` | Fallback si no hay motor unificado (**sin API key**, fallo GPT, etc.): agenda GPT antigua + keywords **acotadas** en v0.46a |
| `_process_calendar_with_extraction` | Extracción de evento tras análisis estructurado legado / rama calendario; **no devuelve `raw` como `stored_override`** (v0.45b+) |
| `_dispatch_unified_motor` | Switch por `operation` unificado; **limpia `gpt_needs_clarification`** antes de acciones mutadoras (v0.46a) |
| `_dispatch_agenda_motor` | Rama **agenda** del JSON antiguo `try_agenda_intent_analysis` (create/query/update/needs_clarification) |
| `_unified_handle_calendar_create` | Creación calendario desde motor unificado |
| `_unified_handle_calendar_update` | Update; bloqueos v0.21.x + **creación explícita** v0.45c |
| `_unified_handle_clarification` | `needs_clarification`; en v0.46a puede guardar **`pending_kind: gpt_needs_clarification`** con pasos máximos |
| `_clear_gpt_needs_pending_if_any` | v0.46a — quita solo pending GPT antes de ejecutar una acción concreta |
| `_try_complete_pending_calendar` | Completado local de pending de calendario (determinístico + GPT opcional según llamadas internas) |
| `try_structured_user_intent` | **`openai_client`**: GPT motor unificado; acepta `pending_context` (v0.46a) |
| `try_complete_pending_calendar_event` | GPT sobre pending calendario (where used) |
| `try_note_structuring` | Estructura notas vía GPT (usos dispersos) |
| `try_structured_intent_analysis` | Clasificación previa (“consulta”, “calendario”, …) en legacy |
| `build_agenda_context_packet` | Construye paquete de contexto para razonamiento de agenda |
| `EventsStore.add_event` | Alta evento (**str legacy** interno vs **dict** estructurado) |
| `EventsStore.add_calendar_event` | Alias de `add_event(dict)` |
| `PendingActionStore` | `data/pending_action.json`; esquema flexible por versión |
| `FocusStore` | `data/focus.json`; foco multi-entidad (event/task/note) |
| `events_store` agenda context | `last_agenda_context` en EventsStore para follow-ups |

---

## 2. Qué es lógica antigua / legado

- **`_process_fresh_legacy`**: segunda línea cuando `try_structured_user_intent` devuelve `None`; incluye **`try_agenda_intent_analysis`**, keywords de calendario y **`try_structured_intent_analysis`**. Las ramas keyword **nota/tarea** que devolvían `intent` persistible **sin payload** fueron **neutralizadas** en v0.46a (ya no conducen a `POST /message` guardando texto crudo vía tipo de intent).
- **`add_event(str)`**: solo **compatibilidad** interna/tests; **`POST /message` no debe** enviar ese camino tras guards v0.45b/v0.46a.
- **Heurísticas locales fuertes** antes de GPT (`_is_bare_calendar_intent`, día-agenda sintético, agenda follow-ups): **salvavidas** funcionales; el contrato pide minimizar decisión semántica local **sustitutiva** de GPT cuando hay API key — siguen necesarias donde GPT no existe o falla.
- **`main.message` usando `stored_override if not None else body.text`** — sigue vigente pero con **guardas** que omiten persistencia si llega solo `str` en calendario / nota / tarea.

---

## 3. Motor v0.21 (trazas actuales)

- Motor unificado OpenAI con `create_note | create_task | create_calendar_event | query_calendar | update_calendar_event | needs_clarification | general_query`.
- `pending_action` enriquecida para calendario (`calendar_event_completion`, payloads unificados).
- Multi-foco y parches de entidad v0.21.9+.

---

## 4. Ramas que deben mantenerse (corto plazo)

- **`try_structured_user_intent` + `_dispatch_unified_motor`** como **camino principal** con `OPENAI_API_KEY`.
- **Guards v0.45b/v0.45c/v0.46a** en `main.py` y calendario.
- **Consultas de día** y síntesis inferencial ya usadas en producción (`_synthesize_day_agenda`, etc.) — retirar solo con sustituto GPT completo.
- **Pending calendario** existente para completado local (UX estable).

---

## 5. Ramas a desactivar o encapsular

- Creación de “nota/tarea provisional” por **solo keyword** sin dict (eliminada en v0.46a en legacy).
- Cualquier persistencia que use **implicitamente** `body.text` como única carga cuando el intent pretendía ser estructurado.

---

## 6. ¿Dónde se construye el paquete para GPT?

- Principalmente en **`try_structured_user_intent`** (`openai_client.py`): JSON con `mensaje_usuario`, `eventos_candidatos`, `evento_enfocado`, `accion_pendiente_previa_v046a`.
- Agenda / contexto amplio: `build_agenda_context_packet`, `try_agenda_context_reasoning`, etc. (consultas pesadas agenda).

---

## 7. ¿Dónde se interpreta la respuesta GPT?

- **`_normalize_unified_intent`**: valida `operation`, **mapea `status` → `operation`**, `ambiguities`, `assistant_reply`, banderas de confirmación.
- Handlers en **`assistant_engine`** según `operation`.

---

## 8. ¿Dónde se ejecutan acciones?

- **Handlers unificados** (`_unified_handle_*`) que devuelven tuplas `(reply, intent_type, stored_override, ui_hint)`.
- **`main.message`**: traduce `intent_type` + `payload` a `EventsStore` / `TasksStore` / `NotesStore` con **guards defensivos**.

---

## 9. Compatibilidad legacy (no usar en flujo principal)

- `EventsStore.add_event(str)` — solo tests o migraciones.
- Ramas de legacy keyword en `_process_fresh_legacy` — **acotadas**; transición futura: consulta controlada o pending mínima.

---

## 10. Deuda técnica

- **Paquete de entrada completo** (user, message ids, policy explícita, historial) unificado con el JSON del §3 del contrato maestro.
- **`start_datetime` real** con `Europe/Madrid` y contrato hacia Flutter.
- **Mail / draft** sin endpoint.
- **Unificar** `pending_kind` (calendario clásico vs `gpt_needs_clarification`) en un solo modelo de serialización.
- **Reducir** pre-GPT local cuando haya key, sin romper offline.
- **Limpieza** de eventos pobres históricos (fuera de v0.46a).
- **Multiusuario** real y auth.

---

## Referencias

- Contrato: `aris_decision_engine_contract_v0_46a.md`
- Versión: `docs/version_0_46a_decision_engine_contract.md`
