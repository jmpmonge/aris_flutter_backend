# Versión 0.44.2 — Horas ambiguas en eventos (backend)

## Problema

Mensajes como «quiero poner una cita mañana a las 7 con Luis» podían acabar persistidos o mostrados con una hora errónea (p. ej. **14:00**), por inferencias automáticas de tarde (**+12 h**) cuando el modelo o la heurística de presentación aplicaban conversiones indebidas.

## Alcance

- **Sólo backend** (`backend/core/assistant_engine.py`, `backend/storage/events_store.py`): sin cambiar endpoints ni cliente Flutter en esta corrección.
- Smokes locales: [`scripts/smoke_v0442_time_ambiguity.py`](../scripts/smoke_v0442_time_ambiguity.py) y agrupador [`scripts/smoke_all.py`](../scripts/smoke_all.py).

## Cambio principal

Se elimina la regla «**solo por aparecer «a las N» en el texto, sumar 12**» en `_display_time_text`. La persistencia antes de crear eventos pendientes/definitivos usa `_coerce_ambiguous_calendar_time_text` para alinear lo que viene del modelo con el **literal «a las H»** del usuario cuando **no** hay indicación explícita de mañana/tarde/noche o am/pm.

## Resultado esperado

- **`a las 7`** → no debe guardarse **`14:00`** por ese mecanismo; se corrige p. ej. desde **`14:00`**/**`19:00`** del modelo hacia **`07:xx`** cuando el texto del usuario lleva **`a las 7`** sin período explícito.
- **`a las 19:00`** y **`a las 14:00`** explícitos se respetan.
- Detalle técnico: [`docs/backend_time_parsing_v0_44_2.md`](backend_time_parsing_v0_44_2.md).

## Pendiente (post v0.44.2)

- **Cliente Flutter (v0.44.3+):** `approximateEventStart` debe construir la hora con `DateTime` **local**, sin `DateTime.utc(...).toLocal()`, para que `time_text` civil no se desplace por huso (ver `backend_date_hints.dart`).

- Parseo robusto **datetime + zona horaria** y contrato opcional **`start_at` ISO con offset** en backend.

