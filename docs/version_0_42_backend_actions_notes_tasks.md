# v0.42 — Acciones reales desde Flutter contra FastAPI (tareas y notas)

## Alcance

- **`aris_flutter_v0_22`** ejecuta **`PATCH`/`DELETE`** sobre tareas y notas cuando **`readsFromBackend`** es verdadero (último **`GET /tasks`** o **`GET /notes`** fue correcto para ese repositorio).
- Contratos **`Pydantic`** en **`backend/models/assistant_message.py`**:
  - **`TaskPatchBody`**: sólo **`title: str`**.
  - **`NotePatchBody`**: sólo **`content: str`**.
- Rutas en **`backend/main.py`**: **`PATCH/DELETE`** de tareas y notas; **`PATCH /tasks/{id}/complete`** sin cuerpo de negocio en FastAPI (el cliente envía **`{}`**).
- **No** se conectan edición/borrado de **eventos**; **OpenAI** y motor simbólico siguen **solo en servidor**.

## Pantallas

- **Tareas**: completar (servidor), editar título, eliminar; menú contextual si hay lista servidor.
- **Notas**: editar y eliminar en **Recientes** si hay lista servidor.

## Errores y fallback

- Si **`GET`** previo falló (**`readsFromBackend` false**), las acciones de servidor **no** se ofrecen para esas listas (tareas: checkbox local; notas: sin menú en recientes del servidor).
- Si la mutación falla (red, HTTP no 2xx, validación), la UI muestra un **SnackBar** con el mensaje acordado y **no** se simula éxito.

## Siguiente paso

- Eventos **`PATCH/DELETE`** cuando el backend exponga contrato estable; desmarcar tarea completada en servidor si se añade soporte.
