# Contrato del backend (estado actual)

Referencia: implementación en `backend/main.py`. Todas las rutas están montadas en la **raíz** de la app FastAPI (sin prefijo tipo `/api/v1` en el código actual).

El backend incluye **motor simbólico** (`AssistantEngine`), **pending actions**, almacenes de historial/notas/tareas/eventos y **GPT/OpenAI controlado desde el servidor** (no expuesto al cliente móvil).

## Resumen de endpoints

| Método | Endpoint | Uso | Estado | Consumidor futuro en Flutter |
|--------|----------|-----|--------|------------------------------|
| GET | `/health` | Comprobación de vida del servicio (`{"status": "ok"}`). | Expuesto, estable para “ping”. | Pantalla ajustes / capa API (diagnóstico de conectividad) — v0.39 |
| POST | `/message` | Envía texto del usuario; el motor clasifica intención, puede crear nota/tarea/evento y persiste interacción en historial. Respuesta `AssistantResponse` (texto del asistente + `ui_hint` opcional). | Núcleo conversacional; depende de motor + GPT en backend. | Entrada principal tipo “asistente” / Home vía repositorio — v0.40 |
| GET | `/history` | Lista el historial de interacciones guardadas. | Operativo. | Feed o pantalla de historial del asistente — v0.41 |
| GET | `/notes` | Lista notas almacenadas. | Operativo. | Lista de notas / sincronización — v0.41 |
| PATCH | `/notes/{note_id}` | Actualiza contenido de una nota (`NotePatchBody`: `content` obligatorio no vacío). | Operativo. | Edición de notas — v0.42 |
| DELETE | `/notes/{note_id}` | Elimina una nota. | Operativo. | Borrado de notas — v0.42 |
| GET | `/tasks` | Lista tareas. | Operativo. | Lista de tareas — v0.41 |
| PATCH | `/tasks/{task_id}` | Actualiza título (`TaskPatchBody`: `title` obligatorio no vacío). | Operativo. | Edición de tareas — v0.42 |
| PATCH | `/tasks/{task_id}/complete` | Marca tarea como completada. | Operativo. | Completar tarea — v0.42 |
| DELETE | `/tasks/{task_id}` | Elimina una tarea. | Operativo. | Borrado de tareas — v0.42 |
| GET | `/events` | Lista eventos de calendario almacenados. | Operativo. | Lectura vista calendario — v0.41 |
| PATCH | `/events/{event_id}` | Actualización parcial (`EventPatchBody`). Reutiliza `EventsStore.update_event`. **v0.43**. | Operativo. | Pendiente cliente — **plan v0.44** |
| DELETE | `/events/{event_id}` | Elimina un evento (`EventsStore.delete_event`). **v0.43**. | Operativo. | Pendiente cliente — **plan v0.44** |

## Cuerpos de petición relevantes

- **POST `/message`:** JSON con modelo `UserMessage` — al menos `{ "text": "..." }` (campos por defecto: `type: "user"`, `created_at` generado en servidor si no se envía). Siguiendo como **vía principal inteligente** para crear agenda junto al motor/OpenAI en servidor (no cliente).
- **PATCH `/notes/{note_id}`:** `{ "content": "..." }` — contenido no puede quedar vacío tras recortar espacios.
- **PATCH `/tasks/{task_id}`:** `{ "title": "..." }` — título no puede quedar vacío tras recortar espacios.
- **PATCH `/events/{event_id}`:** campos opcionales según `EventPatchBody` (ver **`docs/backend_events_contract_v0_43.md`**). Patch completamente vacío → **400**. Validación en capa modelo antes de delegar en el store; **`id`** y **`created_at`** no se modifican. **Flutter no integra estas rutas en la v0.43.**

## CORS

En el código actual se permite CORS amplio (`allow_origins=["*"]`), adecuado para desarrollo; endurecer en despliegue real según política de seguridad.

## Relación con Flutter

La app Flutter consume según roadmap por versión (**health**, **mensaje**, listas CRUD donde esté cerrado el contrato). **En v0.43 solo se amplía backend** (`PATCH`/`DELETE` eventos): **CalendarScreen y `ApiClient` no se han modificado.** La integración de edición/borrado de eventos queda objetivo plausible **v0.44** cuando se enlacen estos endpoints desde el cliente. Los mocks siguen siendo válidos donde no hay integración; ver **`plan_integracion_flutter_backend.md`**.
