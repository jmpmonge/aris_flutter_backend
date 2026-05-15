# v0.43 — Contrato backend: PATCH y DELETE de eventos

## Objetivo

Exponer en FastAPI rutas **`PATCH /events/{event_id}`** y **`DELETE /events/{event_id}`** usando la lógica existente **`EventsStore.update_event`** y un nuevo **`EventsStore.delete_event`**, sin modificar **`GET /events`**, **`POST /message`**, ni el motor/OpenAI.

## Cambios realizados

- **`backend/models/assistant_message.py`**
  - Modelo **`EventPatchBody`** (campos opcionales; **`extra`** prohibido para claves extrañas).
  - **`build_event_updates_from_patch`** — validaciones mínimas (patch no vacío, reglas sobre `title`/`date_text`/`time_text`/`participants`/`duration_minutes`/`confidence`, etc.) y construcción del dict para el store (**no** modifica **`id`** ni **`created_at`**; **`updated_at`** lo sigue estableciendo el store).

- **`backend/storage/events_store.py`**
  - **`delete_event(event_id)`**: patrón análogo a notas/tareas; si el evento enfocado coincide, se borra **`agenda_focus`**.

- **`backend/main.py`**
  - **`PATCH /events/{event_id}`** → validación → **`events_store.update_event`**
  - **`DELETE /events/{event_id}`** → **`events_store.delete_event`**; respuesta **`{"status":"deleted","id":"<id>"}`**

## Errores

| Código | Caso típico |
|--------|----------------|
| **400** | Patch vacío, campos rechazados en validación (**`detail`** con mensaje claro). |
| **404** | Evento inexistente al actualizar o borrar (**`detail`**: "Evento no encontrado"). |

## Integración cliente

- **Flutter v0.43:** no tocado por diseño de esta iteración.
- **v0.44 (planes):** conectar **`CalendarScreen`** / repositorio de calendario a estas rutas cuando proceda.

## Rutas establecidas (recordatorio)

La creación inteligente de eventos sigue siendo principalmente **`POST /message`** (motor en servidor).

## Swagger

Al arrancar la app FastAPI, las rutas aparecen como **`PATCH`** y **`DELETE`** bajo **`/events/{event_id}`**.
