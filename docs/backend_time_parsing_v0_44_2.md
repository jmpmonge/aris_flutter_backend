# Parseo horario en backend (v0.44.2)

## Por qué no se debe convertir «a las 7» en 14:00

«**Siete**» en español es casi siempre **7:00** en reloj de 24 h **salvo que** el usuario diga tarde/noche («de la tarde», «de la noche», «esta tarde», am/pm, etc.). Una heurística que sumaba 12 solo por aparecer **`a las 7`** (o porque el modelo devolvía **14:00** / **19:00**) producía errores perceptibles como **la cita aparece a las 14**.

La regla aplicada desde **v0.44.2** es:

1. **`_display_time_text`** sólo aplicaba **+12** si el texto deja claro tarde/noche («de la tarde», «esta tarde», «de la noche», …); **ya no** fuerza tarde sólo por **`a las N`**.
2. **`_coerce_ambiguous_calendar_time_text`** corrige valores **persistidos** respecto del literal `\ba\s+las?\s+(\d+)…`:
   - sin período explícito (mañana/tarde/noche/am/pm…), si el modelo dice **`lh+12`** (p. ej. **19:00** para **las 7**), se sustituye por **`lh:MM`** con los mismos minutos del modelo.
   - si el modelo dice **14:00** con **las siete** en el mismo mensaje (**bug típico**), se corrige a **07:MM**.
3. **`GET /events` no cambia** de forma ni campos.

## Ejemplos (con textos naturales coherentes)

| Mensaje usuario (extracto hora) | `time_text` modelo (incorrecto típico) | Tras coerción (persistencia) |
|---------------------------------|-------------------------------------------|-------------------------------|
| a las **7**, sin tarde/noche    | **14:00**                                 | **07:00**                     |
| a las **7**, sin tarde/noche    | **19:00**                                 | **07:00**                     |
| a las **19:00**                 | **19:00**                                 | **19:00**                     |
| a las **14:00**                 | **14:00**                                 | **14:00**                     |
| a las **2**, sin período       | **14:00**                                 | **02:00**                     |
| a las **2 de la tarde**        | **14:00**                                 | **14:00** (período explícito) |

La coerción se aplica también al fusionar **`pending`** (segundo mensaje **`sí`**) usando texto original + turno actual; ver `_coerce_calendar_time_twice_sources`.

## Funciones donde interviene la regla

- `assistant_engine.py`: `_coerce_ambiguous_calendar_time_text`, `_coerce_calendar_time_twice_sources`, `_calendar_time_text_after_user_message`, `_display_time_text`, payloads unificados/agenda y `_event_dict_from_pending`.
- `events_store.py`: `normalize_time_text` **no interpreta tarde vs mañana** (sólo formateo comparativo HH:MM); la docstring aclara cómo debe usarse junto al motor.

## Qué falta para ser definitivo en producción

- **Zona horaria** declarada (`Europe/Madrid`, etc.) y/o **`OffsetDateTime`** en API.
- Desambiguación explícita en diálogo («¿7 de la mañana o de la tarde?») si el producto lo exige.

## Cliente Flutter

En `aris_flutter_v0.22/lib/core/models/backend_date_hints.dart`, `approximateEventStart` usa **`DateTime(y, m, d, h, mi)`** (hora civil local) para no aplicar el desfase `utc`→`toLocal()` sobre un `time_text` que el backend trata como hora local nominal, no como instante UTC.

## Pruebas locales

```bash
python3 scripts/smoke_v0442_time_ambiguity.py
python3 scripts/smoke_all.py
```

