# v0.47.36.10 — Ficha mínima útil y título limpio de evento

## 1. Problema

Se podían crear eventos con título residual o sin identidad mínima. El síntoma visible era una tarjeta de calendario como:

```
20:00  cita param artes
       Luis
```

El título "cita param artes" es basura residual (corrupted "cita para martes"). Otros ejemplos observados:

- "eventa para el jueves"
- "cita para el martes"
- "evento para el jueves"

## 2. Solución

### Normalización técnica de título residual

Si `cal_title` es genérico/residual **y** hay participantes en `cal_people`, Aris normaliza el título a `"cita con <primer participante>"` antes de persistir.

Ejemplo:

```
cal_title = "cita param artes"
cal_people = ["Luis"]
→ title persistido = "cita con Luis"
```

### Títulos útiles se conservan

Si el título ya es útil ("revisión del contrato", "cita con Luis", "dentista"), no se toca.

### Sin identidad → no se persiste, se pregunta

Si no hay participantes, location, description, ni título útil (solo "cita", "evento", "reunión", o cabecera residual), Aris bloquea la creación y pregunta:

> "¿Con quién o sobre qué es la cita?"

## 3. Regla técnica de título genérico/residual

Un título es genérico/residual si (después de normalizar a minúsculas sin acentos):

- Es exactamente: `cita`, `evento`, `reunion`, `quedada`
- O empieza por: `evento para `, `eventa para `, `cita para `, `cita param `, `reunion para `

El prefijo `cita param ` captura la corrupción "cita para martes" → "cita param artes" de reconocimiento de voz/OCR.

## 4. Archivos modificados

| Archivo | Cambio |
|---|---|
| `backend/core/engine.py` | Nuevo prefijo `"cita param "` en `_GENERIC_EVENT_TITLE_PREFIXES`; helper `_normalize_event_title_from_people_if_needed`; aplicación en `_handle_ready_create` antes del chequeo de identidad |
| `backend/core/decision_prompt.py` | Regla de título limpio (v0.47.36.10): ejemplos explícitos de títulos residuales + instrucción de usar `"cita con {persona}"` |
| `scripts/smoke_backend_minimal_v047.py` | `smoke_33_event_minimal_identity_and_title_cleanup()` (casos A–E) |

## 5. Fuera de alcance

- No se modifica Flutter.
- No se modifica tasks ni notes.
- No se implementa parser local ni cálculo de fechas.

## 6. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

33 smokes deben pasar (smoke 33 cubre los casos A–E de esta versión).
