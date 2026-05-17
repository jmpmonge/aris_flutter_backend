# v0.47.36.9 — Recuperación segura de event/update con target inexistente

## 1. Problema

GPT puede devolver `event/update` con un `target` UUID que no existe en el store local cuando la frase del usuario en realidad describe una cita nueva (p. ej. "cita para el martes a la 14h con Luis"). En ese caso, el motor respondía únicamente:

> "No encuentro ese evento en tu agenda local."

La conversación quedaba cerrada sin posibilidad de recuperación, aunque el `obj` recibido de GPT contenía datos suficientes para crear el evento.

## 2. Solución

Si `event/update` apunta a un `target` inexistente pero el `obj` contiene una ficha creable (fecha civil ISO, hora, identidad mínima), Aris pregunta al usuario si quiere crear una nueva cita con esos datos.

Ejemplo:

> "No encuentro esa cita para modificarla. ¿Quieres crear una nueva cita con Luis para el martes a las 14:00?"

## 3. Seguridad

Aris **no convierte automáticamente** `update` → `create`. Solo pregunta. La acción de creación solo se ejecuta si el usuario confirma en el turno siguiente y GPT devuelve `ready/event/create`.

## 4. Criterios para ficha creable

Para que Aris ofrezca la creación alternativa, el `obj` de GPT debe cumplir **todos**:

- `date_iso` válido (formato `YYYY-MM-DD`).
- `time_text` presente (no vacío).
- Identidad mínima de evento (`_event_create_has_minimal_identity`): participantes, ubicación, descripción, o título útil no genérico.

Si no se cumplen todos, Aris mantiene el comportamiento anterior: "No encuentro ese evento en tu agenda local."

## 5. Flujo

```
GPT → ready/event/update (target = UUID-inexistente, obj = ficha)
         ↓
Aris detecta target inexistente
         ↓
¿Ficha creable?
  NO → "No encuentro ese evento en tu agenda local." (cierra hilo)
  SÍ → Guarda objeto en thread.object (cal_*)
       pending.field = "create_instead_confirmation"
       thread.open = true, intent=event, action=create, target=null
       Responde: "No encuentro esa cita para modificarla. ¿Quieres crear una nueva cita ...?"
         ↓
Usuario: "sí"
         ↓
GPT → ready/event/create (usa thread.object como obj)
         ↓
Aris crea evento → cierra hilo, actualiza last_focus/last_action
```

## 6. Archivos modificados

| Archivo | Cambio |
|---|---|
| `backend/core/engine.py` | Nuevo bloque en `_handle_ready_update_event` para detección; helpers `_build_create_instead_event_question`, `_prefixed_event_obj_from_payload`; constante `_MSG_EVENT_NOT_FOUND` |
| `backend/core/decision_prompt.py` | Nueva regla en CONTRATO DE CONTINUACIÓN para `pending.field = "create_instead_confirmation"` |
| `scripts/smoke_backend_minimal_v047.py` | `smoke_32_event_update_missing_target_can_offer_create_instead()` (casos A–E) |

## 7. Fuera de alcance

- `event/delete` con target inexistente **no** ofrece crear (acción destructiva, semántica diferente).
- No se implementa conversión automática `update` → `create`.
- No se implementa parser local de fechas.
- No se implementan cambios en Flutter ni en otros dominios (tasks, notes).

## 8. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Todos los 32 smokes deben pasar (smoke 32 cubre los casos A–E de esta versión).

## 9. Validación manual (GPT real)

1. Enviar: `"cita para el martes a la 14h con luis"`
   - Si GPT devuelve `event/create` directamente: correcto.
   - Si GPT se equivoca y devuelve `event/update` con target inexistente: Aris debe responder preguntando si crear, **no** responder solo "No encuentro ese evento".

2. Responder: `"sí"`
   - Aris debe crear la cita con Luis, `date_iso` no nulo, visible en calendario civil.

3. Probar update real: `"cambia la cita con Luis a las 15"`
   - Si la cita existe, debe actualizarse sin ofrecer crear nueva.
