# v0.47.29 — Blindaje de continuaciones conversacionales

## 1. Objetivo

Evitar que respuestas breves dentro de un hilo abierto se guarden accidentalmente como notas, tareas o eventos nuevos.

## 2. Diseño

Si `mode = continue`, GPT debe interpretar `raw` como respuesta al hilo abierto salvo cambio de tema inequívoco.

Aris no decide semánticamente.

Aris solo envía thread y ejecuta la respuesta estructurada.

## 3. Casos protegidos

- `"a las 20:00"` no debe convertirse en nota.

- `"el lunes a las 15h"` no debe convertirse en nota o tarea.

- `"sí"` no debe convertirse en nota durante confirmación.

- `"la segunda"` no debe convertirse en nota durante selección de candidato.

## 4. Fuera de alcance

- mail;

- completar tareas;

- borrar tareas;

- modificar notas;

- cambios Flutter.

## 5. Validación

Smokes:

```
python3 scripts/smoke_backend_minimal_v047.py
```

Prueba manual recomendada:

- `"pon una cita con el médico"`

- `"el lunes a las 15h"`

Debe crear evento, no nota ni tarea.
