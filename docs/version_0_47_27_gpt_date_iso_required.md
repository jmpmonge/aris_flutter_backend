# v0.47.27 — GPT debe devolver date_iso cuando la fecha civil sea clara

## 1. Objetivo

Hacer que GPT devuelva **date_iso** cuando pueda determinar la fecha civil usando **raw**, **local_date**, **tz** y contexto del hilo cuando aplique.

## 2. Diseño

Aris **no** calcula fechas.

GPT interpreta.

Aris guarda **date_iso** si viene bien formado (**YYYY-MM-DD**).

Flutter usa **date_iso** para situar el evento en calendario civil y conserva **date_text** para la etiqueta natural.

## 3. Ejemplo

Si **local_date** = **2026-05-17** (referencia sólo técnica; el backend no interpreta el mensaje):

Usuario:

`cita con el médico el lunes a las 20h`

GPT debe devolver (extracto):

```json
{
  "date": "lunes",
  "date_iso": "2026-05-18",
  "time": "20:00"
}
```

Backend debe persistir (**date_text**/ **time_text** tras mapeo del motor):

- **date_text**: `lunes`
- **date_iso**: `2026-05-18`
- **time_text**: `20:00`

## 4. Fuera de alcance

- Parser local de fechas en backend.
- Parser local de fechas en Flutter.
- Cálculo local de próximo día de semana o «mañana» en Aris.
- Recurrencias.
- Recordatorios.

## 5. Validación

Smokes:

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Prueba manual con **GPT real** (los mocks no sustituyen al modelo):

- `cita con el médico el lunes a las 20h` → esperar **date_text** textual + **date_iso** coherente con **local_date** + **tz** + interpretación correcta del lunes.
- `cita con Laura mañana a las 13h` → esperar **date_text** tipo «mañana» + **date_iso** día siguiente civil + **13:00** en **time_text**.

Si GPT omite **date_iso** con fechas claras, revisar de nuevo **`backend/core/decision_prompt.py`** (regla **date_iso** cuando la fecha civil sea clara).
