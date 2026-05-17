# v0.47.36 — Modificación básica de tareas

## 1. Objetivo

Permitir actualizar campos básicos de una tarea existente.

## 2. Diseño

GPT interpreta. Aris valida target y campos permitidos. Aris ejecuta `update_task`.

## 3. Campos actualizables

- title
- description
- date_text/date
- date_iso
- time_text/time
- priority normal/high
- tags

## 4. Seguridad

- No actualizar sin target.
- No modificar varias tareas en un único ready.
- Si hay varios candidatos, `target_selection`.
- No crear nota/tarea con réplicas de selección («la segunda», …).

## 5. Fuera de alcance

- Borrar tareas.
- Completar tareas.
- Mail.
- Edición visual Flutter avanzada.

## 6. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```
