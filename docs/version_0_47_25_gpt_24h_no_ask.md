# v0.47.25 — GPT no pregunta horas 24h inequívocas

## 1. Objetivo

Evitar que GPT pregunte por ambigüedad cuando el usuario expresa una hora inequívoca en formato 24h, como 13h, 15h o 17h.

## 2. Bug detectado

El usuario decía:

"cita con el médico el lunes a las 13h"

o:

"cita con el médico el lunes a las 15h"

y GPT seguía preguntando si se refería a la 1/13 o a las 3/15.

## 3. Diseño correcto

Aris no decide semánticamente. GPT decide si hay duda real.

Si GPT entiende que la hora es inequívoca, debe devolver ready/event/create.

Si GPT tiene duda real, debe devolver ask.

## 4. Regla aplicada

- 13–23 como hora son formato 24h inequívoco.
- 13h = 13:00.
- 15h = 15:00.
- 17h = 17:00.
- Solo 1–12 sin marca clara pueden requerir pregunta.

## 5. Fuera de alcance

- parser local backend;
- parser local Flutter;
- normalización civil de fechas;
- cambios de UI;
- cambios de stores.

## 6. Validación

Ejecutado:

python3 scripts/smoke_backend_minimal_v047.py

Resultado esperado: OK.
