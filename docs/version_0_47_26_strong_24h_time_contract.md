# v0.47.26 — Blindaje fuerte de horas 13–23

## 1. Objetivo

Evitar que GPT pregunte por horas inequívocas en formato 24 h, especialmente 20h.

## 2. Bug detectado

El usuario decía:

"cita con el médico el lunes a las 20h"

y GPT preguntaba como si hubiera duda entre 8:00 y 20:00.

## 3. Diseño correcto

Aris no decide semánticamente. GPT decide si hay duda real. El contrato prohíbe preguntar cuando la hora está expresada inequívocamente como 13–23.

## 4. Regla aplicada

- 13–23 son inequívocas en reloj 24 h.
- 20h = 20:00.
- «a las 20» = 20:00.
- Solo 1–12 sin aclaración pueden ser ambiguas.

## 5. Validación

Smokes:

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Prueba manual con GPT real (backend arrancado, variables de OpenAI válidas):

- "cita con el médico el lunes a las 20h" → no debe preguntar; debe crear evento para lunes a las 20:00.
- "cita con el médico el lunes a las 20" → no debe preguntar; mismo resultado esperado.
- "cita con el médico el lunes a las 8" → puede preguntar 8:00 / 20:00.

Opcional (no ejecutado por CI):

```bash
BACKEND=http://127.0.0.1:8000 python3 scripts/manual_gpt_contract_check_v047.py
```

## 6. Fuera de alcance

- parser local backend;
- parser local Flutter;
- normalización civil de fechas;
- cambios UI.
