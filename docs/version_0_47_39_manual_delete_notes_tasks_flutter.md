# v0.47.39 — Borrado manual de notas y tareas desde Flutter

## 1. Objetivo

Permitir borrar notas y tareas desde la interfaz Flutter usando el `id` real de la tarjeta, sin pasar por GPT.

## 2. Principio

El borrado manual es una acción directa UI → backend:

```
Usuario pulsa «Eliminar» en una tarjeta
  → Flutter muestra diálogo de confirmación (Cancelar / Eliminar)
  → Si confirma: DELETE /notes/{id}  o  DELETE /tasks/{id}
  → Backend borra por id, devuelve {"ok": true, "deleted": <objeto>}
  → Flutter lanza GET /notes o GET /tasks para refrescar
  → Si falla: snackbar de error
```

No se usa GPT, `/message`, `last_focus`, `last_action`, `pending` ni `target_selection`.

## 3. Backend

### Endpoints añadidos (`backend/main.py`)

#### `DELETE /notes/{note_id}`

- Busca nota por `id`.
- Si existe: borra, devuelve `{"ok": true, "deleted": <nota>}` (HTTP 200).
- Si no existe: `404 {"detail": "Not Found"}`.
- No toca `thread_state`.

#### `DELETE /tasks/{task_id}`

- Busca tarea por `id`.
- Si existe: borra, devuelve `{"ok": true, "deleted": <tarea>}` (HTTP 200).
- Si no existe: `404 {"detail": "Not Found"}`.
- No toca `thread_state`.

### Stores (sin cambios)

- `NotesStore.delete_note(id)` ya existía desde v0.47.38.
- `TasksStore.delete_task(id)` ya existía. Ambos devuelven `dict | None`.

## 4. Flutter

### ApiClient (sin cambios)

- `deleteNote(String id)` ya existía.
- `deleteTask(String id)` ya existía.
- Ambos llaman a `backendDeleteTasksNotes` con la ruta correspondiente.

### Repositories (sin cambios)

- `HybridNoteRepository.deleteNote` ya existía: llama ApiClient y refresca con GET.
- `HybridTaskRepository.deleteTask` ya existía: llama ApiClient y refresca con GET.

### UI notas (`features/notes/presentation/notes_screen.dart`) — sin cambios

Ya implementado: `PopupMenuButton` con «Editar» / «Eliminar»; diálogo de confirmación; snackbar de resultado. Solo visible cuando `readsFromBackend == true`.

### UI tareas — cambios en esta versión

**`features/tasks/presentation/widgets/compact_expandable_task_tile.dart`**

- Añadido parámetro opcional `onDelete: VoidCallback?`.
- Si `onDelete != null`, se muestra un `PopupMenuButton` (icono tres puntos) junto al título con la opción «Eliminar».
- Si la tarea está en estado `busy`, el menú queda deshabilitado.

**`features/tasks/presentation/tasks_screen.dart`**

- Añadido método `_deleteBackendTask(TaskModel t)`:
  - Muestra `AlertDialog` («Eliminar tarea» / «¿Quieres eliminar esta tarea?» / Cancelar + Eliminar en rojo).
  - Si confirma: llama `Repositories.task.deleteTask(t.id)`.
  - OK → snackbar «Tarea eliminada.» + refresco automático (GET /tasks en repositorio).
  - Fallo → snackbar «No he podido eliminar la tarea.» (error).
- En `_buildSection`: pasa `onDelete` al tile solo si `readsFromBackend == true`.

## 5. Seguridad

- No se borra por título ni por contenido, solo por `id`.
- El diálogo de confirmación es obligatorio antes de llamar al backend.
- Si el backend no está conectado (`readsFromBackend == false`), el menú de eliminar no aparece.
- No se implementa papelera, restauración, borrado múltiple ni undo.

## 6. Validación

```bash
python3 scripts/smoke_backend_http_v047.py   # ALL OK (incluye casos A–D DELETE)
python3 scripts/smoke_backend_minimal_v047.py  # ALL OK (regresión)
dart analyze lib/features/tasks lib/core/...  # No issues found
```

### Prueba manual (pendiente en dispositivo)

**Notas:**
1. Crear nota desde chat.
2. Ir a Notas → abrir menú de la nota → Eliminar.
3. Cancelar → nota sigue.
4. Eliminar → confirmar → nota desaparece.
5. Logs: `DELETE /notes/{id}` + `GET /notes` sin ese id.

**Tareas:**
1. Crear tarea desde chat o formulario.
2. Ir a Tareas → abrir menú de la tarea → Eliminar.
3. Cancelar → tarea sigue.
4. Eliminar → confirmar → tarea desaparece.
5. Logs: `DELETE /tasks/{id}` + `GET /tasks` sin ese id.
