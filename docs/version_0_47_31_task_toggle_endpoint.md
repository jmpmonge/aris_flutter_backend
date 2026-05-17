# v0.47.31 — Toggle directo de tareas desde Flutter

## 1. Objetivo

Permitir que Flutter marque o desmarque tareas directamente en el backend sin pasar por GPT.

## 2. Diseño

No hay decisión semántica:

- Flutter ya tiene `task_id` (p. ej. desde GET `/tasks`).
- El usuario toca el checkbox.
- El backend actualiza sólo el booleano `completed`.
- GPT no interviene; no hay interpretación de texto.

## 3. Endpoint

**PATCH** `/tasks/{task_id}`

Body (único campo permitido en esta versión):

```json
{ "completed": true }
```

También admite:

```json
{ "completed": false }
```

Respuesta: objeto tarea completo persistido (misma forma que en GET `/tasks`).

Errores:

- **404** si la tarea no existe.
- **422** / **400** si el body no es un booleano válido para `completed` (p. ej. `"completed": "sí"`).

No existe en v0.47.31 endpoint REST para cambiar **título** u otros campos de la tarea (queda fuera de alcance).

## 4. Fuera de alcance

- Borrar tareas.
- Modificar título, descripción, fecha, hora, prioridad o etiquetas por REST en esta versión.
- Crear tarea manual por REST desde Flutter (`v0.47.32` u otra versión).
- Completar varias tareas a la vez.
- Mail, cambios en contrato GPT.

## 5. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
python3 scripts/smoke_backend_http_v047.py
```

En app: pantalla Tareas con datos GET → checkbox marcar/desmarcar → sin mensaje rojo de error de red/backend.
