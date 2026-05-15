# Backend — Calendario sin fallback «raw» (v0.45b)

## Introducción

Este documento describe el comportamiento del backend tras **v0.45b**: diferencia entre **payload `dict` estructurado** y **cadena bruta (`str`)**, y por qué **nunca** debe persistirse un evento usando solo el texto del usuario cuando el motor no ha estructurado la cita.

Contexto previo: auditoría del motor en **v0.45a** (`backend_calendar_engine_audit_v0_45a.md`).

## Marco normativo jerarquizado (referencia)

- Normativa constitucional aplicable en materia de datos y comunicaciones (según ámbito de tratamiento).
- LOE / LOMLOE; RD básico; decreto autonómico curricular; decreto de convivencia si procede.
- Orden de evaluación / reclamación aplicable al uso institucional.
- Ley 39/2015 y Ley 40/2015 — referencia para procedimiento administrativo y régimen jurídico del sector público en entornos formales.
- Reglamento interno del centro u organismo titular.

*(La lista cumple plantilla documental; la implementación técnica siguiente no constituye por sí acto administrativo.)*

## Naturaleza jurídica del acto

No aplica acto singular: se documenta un **cambio de software** en la capa de persistencia del asistente.

## Competencia

Backend Python (`backend/core/assistant_engine.py`, `backend/main.py`).

## Procedimiento técnico

### Flujo antes del bug

En ramas donde `try_calendar_event_extraction` devolvía `None` o `not_calendar`, podía devolverse:

```text
("He preparado este evento provisional.", "calendario", raw, None)
```

`main.py` interpretaba `stored_override == raw`, construía `payload` como cadena y ejecutaba `events_store.add_event(str(payload))`, creando registros del estilo:

```json
{
  "id": "...",
  "title": "quiero poner una cita mañana a las 7 con Luis",
  "created_at": "..."
}
```

### Flujo corregido

| Situación | Comportamiento |
|-----------|----------------|
| Extracción `None` y texto parece calendario | `pending_action` mínima (`calendar_event_completion`), respuesta de aclaración, **`stored_override = None`** |
| Extracción `None` y no parece calendario | Respuesta de aclaración / consulta, **`stored_override = None`** |
| `intent == "not_calendar"` | Mensaje prudente pidiendo día, hora, con quién/dónde; **`intent_type`** típicamente `ambiguo`; **`stored_override = None`** |
| `_calendar_direct_save_ok(cal)` | **`stored_override`** es **`dict`** con `title`, `date_text`, `time_text`, `participants`, etc. |
| Datos útiles pero incompletos | `pending_action` con `_pending_calendar_payload`; **sin guardar evento** aún |

### Payload `str` vs `dict`

- **`dict`**: resultado de `_store_payload_from_cal` o equivalente estructurado; es el único tipo que debe llevar a **`events_store.add_event`** en la rama calendario de `main.message`.
- **`str`**: texto usuario o texto sin estructura de evento; **no** debe persistirse como nuevo evento en esta rama.

### Guard defensivo en `main.py`

Aunque una futura regresión devolviera `intent_type == "calendario"` con payload `str`:

- No se llama a `add_event`.
- Se emite **`logging.warning`** identificable (mensaje defensivo v0.45b).

## Análisis de defectos (histórico)

- **Inconsistencia semántica**: el cliente y el contrato v0.21 esperan campos estructurados, no un título igual al mensaje completo.
- **Contaminación de GET `/events`**: crecimiento de entradas no útiles para UI ni para lógica posterior.

## Calificación jurídica

No procede calificación jurídica del código; el defecto era **funcional / de modelo de datos**.

## Propuesta de actuación inspectora

No aplicable al código fuente; en despliegios institucionales, revisar que las políticas de conservación de datos y la información mostrada al usuario sean coherentes con la Ley Orgánica de Protección de Datos y normativa sectorial vigente.

## Qué ocurre si GPT falla (`None`)

No se guarda evento desde texto bruto; se prioriza **pending** o **mensaje de aclaración**, según heurísticas locales (`keywords`, `_looks_like_calendar_*`).

## Qué ocurre si GPT devuelve `not_calendar`

No se interpreta como evento persistible; se pide aclaración sin crear entrada en `events_store`.

## Pruebas

- Script: `scripts/smoke_v045b_no_raw_calendar_fallback.py`
- Casos: extracción `None` + pending; entrada «cita»; extracción estructurada simulada + `add_event(dict)`; `EventsStore.add_event` con dict; **guard defensivo** en `main.message`.
- Agregado a `scripts/smoke_all.py`.

## Limitación explícita

**Aún no se introduce datetime real** ni normalización temporal completa; `date_text` / `time_text` siguen siendo texto orientativo para la UI y futuras mejoras.

## Conclusión

La regla operativa es: **sin extracción estructurada suficiente, no hay nuevo evento persistido desde el mensaje crudo**. Los eventos estructurados válidos siguen guardándose como hasta ahora; **GET `/events`** no debe crecer con títulos pobres nuevos por fallos de GPT.
