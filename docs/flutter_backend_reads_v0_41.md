# Flutter v0.41 — mapeo de lecturas GET (FastAPI)

## Endpoints conectados (solo GET)

| Método | Ruta       | Cliente Flutter        |
|--------|------------|------------------------|
| GET    | `/history` | `ApiClient.getHistory` → `HybridHistoryRepository` |
| GET    | `/tasks`   | `ApiClient.getTasks` → `HybridTaskRepository` |
| GET    | `/notes`   | `ApiClient.getNotes` → `HybridNoteRepository` |
| GET    | `/events`  | `ApiClient.getEvents` → `HybridCalendarRepository` |

La base URL sigue **`ApiConfig.baseUrl`** (`http://127.0.0.1:8000` por defecto en desarrollo).

## Formato de datos (referencia `backend/`)

### `/history`

Lista de objetos con al menos:

- **`user_text`**, **`assistant_text`**, **`created_at`** (ISO), opcional **`intent_type`**.

Flutter expande cada fila en dos **`ChatMessageModel`** (usuario + Aris) con ids sintéticos.

### `/tasks`

Objetos con **`id`**, **`title`**, **`completed`**, **`created_at`**; pueden existir **`description`**, **`date_text`**, **`time_text`**, **`priority`**.

Los mappers son tolerantes si falta algo; partición HOY / PRÓXIMAS según fecha normalizada donde sea posible.

### `/notes`

Objetos con **`id`**, **`content`**, **`created_at`**; **`title`** opcional según registros legacy vs estructurados.

Flutter mapea a **`NoteModel`** (título desde `title` o primer tramo del contenido cuando haga falta).

### `/events`

Objetos con campos típicos de agenda (p. ej. **`title`**, **`date_text`**, **`time_text`**, **`location`**, **`participants`** según persistencia servidor); cualquier campo ausente usa valor seguro en UI.

## Qué no está conectado

- **`PATCH`** / **`DELETE`** en notas, tareas y eventos.
- Marcar tarea como completada hacia servidor (el checkbox en Tareas solo afecta al estado copiado en memoria en cliente).
- Cualquier llamada **OpenAI** o motor simbólico desde Dart.

## Comportamiento de red y depuración

- Las peticiones usan **`package:http`**; errores HTTP o JSON inválido no bloquean la app.
- Temporalmente **`debugPrint`** registra URL, código de estado, cuerpo (truncado) y error capturado en la utilidad **`backend_get_json_list`**.

Versión aplicación: **`0.41.0+1`** (`pubspec.yaml`, **`AppMeta.versionSemver`**).
