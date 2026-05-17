# v0.47.30 — Completar tarea básica

## 1. Objetivo

Permitir marcar tareas como completadas mediante `ready`/`task`/`complete`.

## 2. Diseño

GPT interpreta.

Aris ejecuta `complete_task(target)` en el store.

Si falta `target`, Aris no completa nada.

Si hay ambigüedad, GPT debe pedir contexto (`need_context`) o preguntar (`ask` con `target_selection`).

## 3. Flujo

- Usuario pide completar tarea.

- GPT puede devolver `need_context` (`domain`: `tasks`, `query`: `list_tasks`, filtros p. ej. `completed`: `false`, `title` opcional).

- Aris devuelve candidatos técnicos en `context_response`.

- GPT devuelve `ready`/`task`/`complete` con `target` o `ask` con `target_selection` (`original_action`: `complete`).

- Aris ejecuta la completación y limpia el hilo.

## 4. Fuera de alcance

- borrar tareas;

- modificar tareas;

- completar varias a la vez;

- mail;

- notificaciones.

## 5. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```
