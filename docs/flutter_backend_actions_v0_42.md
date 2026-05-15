# Flutter v0.42 — mutaciones tareas y notas (FastAPI)

## Endpoints conectados

| Método | Ruta | Uso en Flutter |
|--------|------|----------------|
| PATCH | `/tasks/{task_id}` | `ApiClient.updateTask` → JSON **`{"title":"…"}`** |
| PATCH | `/tasks/{task_id}/complete` | `ApiClient.completeTask` → cuerpo **`{}`** |
| DELETE | `/tasks/{task_id}` | `ApiClient.deleteTask` |
| PATCH | `/notes/{note_id}` | `ApiClient.updateNote` → JSON **`{"content":"…"}`** |
| DELETE | `/notes/{note_id}` | `ApiClient.deleteNote` |

Implementación HTTP: **`lib/core/api/backend_tasks_notes_http.dart`** (timeout, logs `debugPrint` con URL, status y cuerpo truncado).

## Repositorios

- **`HybridTaskRepository`**: `completeTask`, `updateTask`, `deleteTask`; tras éxito intenta **`GET /tasks`** (`_reloadTasksAfterMutation`) y dispara **`readRevision`**.
- **`HybridNoteRepository`**: `updateNote`, `deleteNote`; tras éxito **`GET /notes`** análogo.
- **`readsFromBackend`**: `true` si el último GET de esa entidad respondió bien (la lista puede estar vacía).

## UI

- **`tasks_screen.dart`**: `PopupMenuButton` Editar/Eliminar; checkbox con flujo servidor vs local; **no** se permite desmarcar tarea en modo servidor (sin endpoint).
- **`notes_screen.dart`**: menú en tarjetas de la lista **Recientes**; diálogos de edición y confirmación de borrado.

## Notas de mapeo

- La API de notas **no** acepta **`title`** en el PATCH; si el usuario edita título y cuerpo, Flutter compone un único **`content`** (título + salto + cuerpo) para cumplir **`NotePatchBody`**.
- La API de tareas **no** acepta **`description`** en el PATCH actual; el cliente **`updateTask`** usa **`title`** (y en capa inferior, si solo hubiera descripción, se usaría como respaldo del `title` no aplica a la UI actual).

## No incluido

- Mutaciones de **eventos**.
- **OpenAI** / motor simbólico en Dart.

Versión app: **`0.42.0+1`** (`pubspec.yaml`, **`AppMeta.versionSemver`**).
