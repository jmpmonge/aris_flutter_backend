# v0.47.23 — Hora 24h inequívoca y fecha textual

## 1. Objetivo

Evitar que horas en formato 24 h, como «17h», se traten como ambiguas, y conservar días textuales como «lunes» sin sustituirlos por el día corriente ni por otro nombre de día.

## 2. Bugs detectados

### Bug 1

Usuario:
`cita con el médico el lunes a las 17h`

**Antes:** Aris podía preguntar si era 17h o 5h.

**Ahora:** GPT debe clasificar esa hora como inequívoca en 24 h y devolver `ready/create` con `time` tipo `17:00` cuando el resto de datos esté claro (**sin ask** sobre 5 ↔ 17).

### Bug 2

Usuario:
`cita con el médico el lunes a las 17h`

**Antes:** La cita podía quedar con un día textual incorrecto respecto al enunciado (p. ej. sustitución por día actual).

**Ahora:** Debe mantenerse en `obj` el literal **`lunes`** (u otro día que el usuario dijo) en `date`/`date_text` coherente con Aris; sin resolución civil de calendario en backend en esta versión.

## 3. Principio rector

Aris no decide semánticamente. GPT interpreta. Aris valida y persiste los campos devueltos. No se añade parser local de fechas/horas en el backend.

## 4. Cambios realizados

| Archivo | Cambio |
|---------|--------|
| `backend/core/decision_prompt.py` | Reglas explícitas: hora 24 h inequívoca (prioridad antes de ambigüedad 1–12); conservación de día de semana textual; continuación cuando `pending.field = time` con respuesta `17h`/`17`/etc.; regla CREACIÓN DE TAREAS alineada con 24 h vs ambiguo |
| `scripts/smoke_backend_minimal_v047.py` | `smoke_14_event_24h_time_and_weekday_text()` |
| `backend/core/engine.py` | Sin cambios |

## 5. Fuera de alcance

- parser local de fechas en backend;
- normalización civil calendario;
- cambios de frontend;
- nuevos endpoints;
- recordatorios reales.

## 6. Validación

Ejecutar:

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Resultado esperado: `smoke_backend_minimal_v047: ALL OK`.
