# v0.47.22 — Continuación segura en creación de eventos

## 1. Objetivo

Evitar que una respuesta de hora en un hilo abierto de **creación** de evento se interprete como **modificación** de evento.

## 2. Bug corregido

Caso detectado:

Usuario:
`cita con el medico el lunes a las 17k`

Aris pregunta por la hora.

Usuario:
`a las 17h`

**Antes:** Aris respondía:
`No sé qué evento quieres modificar. ¿Puedes concretarlo?`

**Ahora:** Debe tratarse como cierre **ready/create** cuando GPT siga el contrato (Aris ejecuta **`add_event`** con la hora canónica).

## 3. Principio rector

Aris no decide semánticamente. GPT interpreta. El contrato del sistema (`decision_prompt`) obliga a distinguir continuación **create + pending.field = time** (sin **`target`** de evento) frente a **`update`** (con **`thread.target`** / **`pending.target`** con UUID).

## 4. Cambios realizados

| Archivo | Cambio |
|---------|--------|
| `backend/core/decision_prompt.py` | Regla explícita `mode = continue`, evento pendiente **create**, **`pending.field` = `time`**, ausencia de **target**/UUID de persistencia vs flujo **update** |
| `scripts/smoke_backend_minimal_v047.py` | `smoke_13_event_create_continue_not_update()` (regresión) |
| `backend/core/engine.py` | Sin cambios |

## 5. Validación

Ejecutado:

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Resultado: OK
