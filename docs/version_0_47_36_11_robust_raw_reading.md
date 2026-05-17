# v0.47.36.11 — Lectura robusta del raw

## 1. Problema

El usuario puede escribir con errores de teclado o dictado:

- "eventa" (→ evento/cita)
- "co luis" (→ con Luis)
- "a la 14h" (→ a las 14:00)
- "miercolas" (→ miércoles)
- "cita param artes" (posible → "cita para martes", pero no seguro)

El sistema no debe guardar fragmentos incomprensibles como `cal_title`. Tampoco debe ignorar silenciosamente una corrección que podría cambiar fecha, persona o dominio.

## 2. Solución

**Corrección obvia**: si la corrección es inequívoca y no cambia ningún dato operativo, GPT la aplica internamente sin preguntar.

**Corrección dudosa**: si la corrección puede cambiar fecha, hora, persona, dominio, acción o título, GPT formula una hipótesis y pregunta confirmación con `pending.field = "raw_correction_confirmation"`.

Regla principal: nunca guardar como `cal_title` / `task_title` / `note_title` un fragmento no comprensible con seguridad.

## 3. Flujo de corrección dudosa

```
raw = "cita param artes con Luis a las 20"
         ↓
GPT detecta "param artes" como posible "para martes" (dudoso)
         ↓
ask / event / create
  obj = {cal_title: "cita con Luis", cal_time_text: "20:00", cal_people: ["Luis"]}
  q = "¿Te refieres a una cita con Luis para el martes a las 20:00?"
  pending.field = "raw_correction_confirmation"
         ↓
Usuario: "sí"
         ↓
GPT → ready / event / create con obj completo (añade cal_date_text, cal_date_iso)
         ↓
Aris crea evento
```

## 4. Reglas de continuación

Si `mode=continue` y `thread.pending.field == "raw_correction_confirmation"`:

- Confirmación → `ready` con `thread.object` como base
- Corrección de dato → fusión + `ready` si queda completo
- Negación → pregunta reformulación

## 5. Archivos modificados

| Archivo | Cambio |
|---|---|
| `backend/core/decision_prompt.py` | Nueva sección "LECTURA ROBUSTA DEL MENSAJE CRUDO" (v0.47.36.11); regla de continuación `raw_correction_confirmation` en CONTRATO DE CONTINUACIÓN |
| `scripts/smoke_backend_minimal_v047.py` | `smoke_34_robust_raw_reading_contract()` (casos A–C) |

## 6. Fuera de alcance

- No se implementa preprocesador local del raw.
- No se añade segunda llamada a GPT para corrección.
- No se modifican stores ni Flutter.

## 7. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

34 smokes deben pasar (smoke 34 cubre los casos A–C de esta versión).
