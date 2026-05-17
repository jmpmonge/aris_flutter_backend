# v0.47.36.5 — Integración civil de eventos con cal_date_iso

## 1. Problema

Los eventos con día textual claro podían guardarse solo con `date_text` y `time_text`, sin `date_iso`, y Flutter los mostraba como «Fecha en texto · servidor».

## 2. Solución

Reforzar en el prompt del motor semántico que los eventos de calendario con fecha civil decidida deben llevar **`cal_date_iso`** (además del texto natural **`cal_date_text`**). El backend ya mapea **`cal_date_iso`** → **`date_iso`** en persistencia.

## 3. Regla

- **`cal_date_text`** conserva el literal del usuario.
- **`cal_date_iso`** (YYYY-MM-DD) permite integración en rejilla día civil en cliente.
- **`cal_time_text`** sitúa la franja horaria cuando aplica.

## 4. Sin semántica local en backend

Aris no calcula «el próximo miércoles» a partir del texto solo con reglas locales. **GPT** usa **`raw`** + **`local_date`** + **`tz`** para cerrar **`cal_date_iso`**.

Refuerzo técnico opcional en `engine`: si el objeto GPT trae **`cal_date_iso`/alias válido** y por cualquier causa el payload interno llegara sin **`date_iso`**, se reinyecta antes de llamar al store (**no conversión desde «miércoles» localmente**).

## 5. Validación

- `python3 scripts/smoke_backend_minimal_v047.py` (caso **`smoke_28_…`**).
- `python3 scripts/smoke_backend_http_v047.py` — **GET /events** debe devolver **`date_iso`** no null en el ejemplo sembrado.

Si **GET /events** es correcto y Flutter sigue en modo textual-only, el fallo estaría en el mapper Flutter (tracking separado, p.ej. v0.47.36.6).
