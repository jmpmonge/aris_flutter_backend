# v0.47.24 — Flutter respeta date_text textual en eventos

## Bug

Backend devuelve correctamente `date_text = "lunes"`, pero la app Flutter situaba/colocaba el evento como el día civil corriente (p. ej. domingo cuando `DateTime.now()` caía domingo).

## Causa

[`BackendDateTimeHints.approximateEventStart`](aris_flutter_v0.22/lib/core/models/backend_date_hints.dart), usado desde [`BackendEventMapper`](aris_flutter_v0.22/lib/core/models/backend_event_mapper.dart), caía en `created_at` o en el día de la semana siguiente a `fallbackDay` cuando `parseDateFlexible` no interpretaba `"lunes"`. El repo de calendario agrupaba por [`EventModel.start`](aris_flutter_v0.22/lib/core/models/event_model.dart), igual que las vistas día/semana/mes.

## Solución

1. **`resolveEventInstant`**: si `date_text` no vacío y no es fecha civil parseable (`parseDateFlexible` null), usa un día civil **centinela** y **`hasCivilCalendarDate = false`**, sin `created_at`.
2. **`EventModel.hasCivilCalendarDate`**: el repositorio y las vistas sólo relacionan estos eventos con columnas día/semana/mes civiles cuando es `true`.
3. **`HybridCalendarRepository`**: listas explícitas de eventos sólo texto vía **`textualOnlyDateBackendEvents`** y merge en **`getTodayEvents`** / resumen **`getHomeHighlightEvents`**.
4. **UI**: secciones «**Fecha en texto · servidor**» en vista día, semana y mes con líneas `lunes · 17:00 · título`.
5. **Test**: [`test/backend_event_mapper_test.dart`](aris_flutter_v0.22/test/backend_event_mapper_test.dart).

## Fuera de alcance

- resolver el próximo lunes en calendario civil;
- calendario civil completo;
- cambios de contrato en backend GPT;
- interpretación semántica local de weekday en servidor.

## Validación manual

1. Backend y Flutter en ejecución.
2. Mensaje: `cita con el médico el lunes a las 17h`
3. `ApiClient.getEvents` / JSON: `date_text: "lunes"`, `time_text: "17:00"`.
4. En Flutter: aparece etiqueta **`lunes · 17:00`** en la zona «Fecha en texto · servidor» (y en resumen HOME con la línea **`lunes · 17:00 · …`**), no como cita sólo civil del día corriente.
