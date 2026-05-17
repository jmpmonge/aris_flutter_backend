# v0.47.31 — Toggle directo de tareas desde Flutter

## 1. Objetivo

Permitir que Flutter marque o desmarque tareas mediante un endpoint HTTP directo, sin pasar por GPT.

## 2. Diseño

No hay decisión semántica en servidor para este flujo:

- Flutter conoce `task_id` desde GET `/tasks`.
- El usuario toca el checkbox.
- El backend actualiza el campo `completed` en el JSON persistente.

## 3. Endpoints

### Principal

**PATCH** `/tasks/{task_id}`

Cuerpo JSON (al menos uno de los dos campos):

- `completed` (bool): marcar o desmarcar.
- `title` (string): edición de título (mismo método que ya usaba el cliente para renombrar).

Ejemplos:

```json
{ "completed": true }
```

```json
{ "completed": false }
```

```json
{ "title": "nuevo título" }
```

Respuesta: objeto tarea actualizado (misma forma que en GET `/tasks`).

**404** si el `task_id` no existe.

### Compatibilidad (cliente antiguo)

**PATCH** `/tasks/{task_id}/complete`

Cuerpo: `{}`. Equivale a marcar la tarea como completada (`completed: true`). Misma respuesta que PATCH principal.

## 4. Cliente Flutter (v0.47.31)

`ApiClient.patchTaskCompletion` llama a **PATCH** `/tasks/{id}` con `{"completed": bool}`.

Se deja de usar **PATCH** `/tasks/{id}/complete` con cuerpo vacío por defecto.

## 5. Fuera de alcance

- Borrar tareas (DELETE distinto).
- Completar varias a la vez.
- Mail, GPT.

## 6. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Prueba en dispositivo: lista GET → checkbox → sin mensaje de error rojo; marcar y desmarcar.
