# Versión 0.44.1 — UI de eventos provisionales y `confirm_rescue`

## Resumen

El backend puede responder a `POST /message` con un **evento descrito en texto** que aún **no existe** en `GET /events` hasta que el usuario confirme (flujo de acción pendiente / rescate). En esa situación el contrato expone `ui_hint` (p. ej. `confirm_rescue`). Flutter **v0.44.1** muestra confirmación explícita y **refresca las lecturas** del backend tras cada mensaje exitoso.

## Respuesta de `POST /message` (sin inventar campos)

Campos ya modelados en la app: `text`, `type`, `ui_hint`, `created_at`.

- Si `ui_hint == "confirm_rescue"`: se muestra la tarjeta **Necesito confirmación** con **Guardar** (`{"text":"sí"}`) y **Cancelar** (`{"text":"no"}`) vía el mismo `POST /message`.
- Si el texto sugiere algo **provisional** y `ui_hint` es **null**: nota discreta *«Puede requerir confirmación.»* (heurística por palabras *provisional / provisoria*). El siguiente paso recomendado es que el backend envíe siempre `ui_hint` cuando haya acción pendiente.

## Historial (`GET /history`) y persistencia de `ui_hint`

Para que la tarjeta de confirmación **no desaparezca** al mezclar historial remoto + cola local, el backend **persiste** `ui_hint` en cada fila del historial cuando viene informado (misma forma `GET /history`, sin nuevo endpoint).

## Refresco tras mensaje

Tras una respuesta **exitosa** de `POST /message`, la app ejecuta `Repositories.prefetchBackendReads()`:

- `GET /history`
- `GET /tasks`
- `GET /notes`
- `GET /events`

**Calendario:** `CalendarScreen` ya escucha `Repositories.calendar.readRevision`; al completar `calendar.refreshFromBackend()` se notifica y la vista se reconstruye con datos del servidor.

## Fuente de verdad

No se crea el evento en Flutter cuando el estado es provisional: el listado del calendario sigue viniendo del backend.

## Referencia de implementación

- `aris_flutter_v0.22/lib/core/repositories/assistant_repository.dart`
- `aris_flutter_v0.22/lib/core/repositories/repositories.dart`
- `aris_flutter_v0.22/lib/shared/widgets/recent_conversation_card.dart`
- `aris_flutter_v0.22/lib/features/home/presentation/home_screen.dart`
- `backend/storage/history_store.py`, `backend/main.py`
