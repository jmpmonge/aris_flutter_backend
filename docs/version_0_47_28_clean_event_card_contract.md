# v0.47.28 — Contrato limpio de ficha de evento

## 1. Objetivo

Eliminar reglas mecánicas de ambigüedad horaria y sustituirlas por **un único contrato** de **ficha de evento**, donde solo **GPT** decide si debe **preguntar** o devolver **ready**.

## 2. Diseño

**Aris** no decide semánticamente sobre horas ni fechas.

GPT recibe **raw**, **tz**, **locale**, **local_date** y **thread** (si hay hilo abierto).

El payload **rules** sólo marca **hide_internal**; ya **no envía políticas locales** tipo franjas u horas cerradas (**08:00–22:00**, `ambiguous_hour`, etc.) para no condicionar al modelo frente al contrato en el prompt principal.

GPT decide:

- **ready** cuando tiene certeza suficiente;
- **ask** cuando tiene **duda real**.

Aris sólo valida formato técnico y persiste (`engine`/`events_store` sin cambiar semántica).

## 3. Formato de ficha de evento (`obj`)

```json
{
  "title": "...",
  "date": "...",
  "date_iso": "YYYY-MM-DD",
  "time": "HH:MM",
  "people": [],
  "location": null,
  "description": null,
  "duration_minutes": null
}
```

Persistencia servidor (mapeada en código): **`title`**, **`date`/`date_text` → `date_text`**, **`date_iso`/ `dateISO` → `date_iso`**, **`time`/`time_text` → `time_text`**, **`people`/`participants`**, **`location`**, **`description`**, **`duration_minutes`**.

## 4. Reglas eliminadas (prompt / payload técnico)

- Prioridad **13–23** sobre **ask**.
- Franjas tipo **1–12** obligatorios con **pairs** («7 ↔ 07/19», «8 ↔ 08/20», «5 ↔ 05/17»…).
- Pregunta **literales** impuestos tipo «¿Te refieres a las 7…?» obligatorios.
- Obligaciones de **pending.options** como plantillas fijas.
- En **`payload_builder.rules`**, claves **`hours`**, **`ambiguous_hour`**, **`colloquial_hour_ambiguity`**, continuación específica de hora (**v0.47.27−**).

## 5. Nueva regla única en producto/prompt

**GPT pregunta solo si tiene duda real** sobre el dato que falta (`q` natural, `pending` opcional incluso sin `options`).

## 6. Validación

Smokes:

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Prueba manual con **GPT real** (los mocks sólo chequean ejecución de JSON/hilo/evento):

1. `"cita con el médico el lunes a las 15h"` → **sin** nueva capa ritual de preguntas **si** GPT ya cierra día/hora; evento with **`date_iso`** + **`15:00`** si el modelo lo devuelve.
2. `"cita con el médico el lunes a las 20h"` → coherencia similar con mock de **lista** cuando GPT **ready**.
3. `"pon una cita con el médico"` → esperable **ask** por fecha/hora; **sin** crear evento hasta nuevo **ready**.
4. Continuación `"el lunes a las 15h"` → **create** agenda, **no** nota/tarea/update arbitrario.

