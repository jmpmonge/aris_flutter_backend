# Contrato del backend (estado actual)

Referencia: implementación en `aris_backend/main.py`. Todas las rutas están montadas en la **raíz** de la app FastAPI (sin prefijo tipo `/api/v1` en el código actual).

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
| GET | `/events` | Lista eventos de calendario almacenados. | Operativo. | Vista calendario / eventos — v0.41 |

## Cuerpos de petición relevantes

- **POST `/message`:** JSON con modelo `UserMessage` — al menos `{ "text": "..." }` (campos por defecto: `type: "user"`, `created_at` generado en servidor si no se envía).
- **PATCH `/notes/{note_id}`:** `{ "content": "..." }` — contenido no puede quedar vacío tras recortar espacios.
- **PATCH `/tasks/{task_id}`:** `{ "title": "..." }` — título no puede quedar vacío tras recortar espacios.

## CORS

En el código actual se permite CORS amplio (`allow_origins=["*"]`), adecuado para desarrollo; endurecer en despliegue real según política de seguridad.

## Relación con Flutter (v0.38)

Ningún flujo de la app Flutter está obligado a consumir estos endpoints todavía. Los mocks locales siguen siendo válidos hasta las versiones de integración indicadas en `plan_integracion_flutter_backend.md`.
