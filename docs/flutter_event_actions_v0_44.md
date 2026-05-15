# Guía rápida — acciones evento en Flutter v0.44

## Endpoints

| Función cliente | HTTP | Body / notas |
|-----------------|------|----------------|
| `ApiClient.updateEvent` | PATCH `/events/{id}` | JSON **snake_case**; omitir claves `null`; cuerpo nunca `{}`. |
| `ApiClient.deleteEvent` | DELETE `/events/{id}` | Sin body. |

Mapeo **Dart → JSON**:

- `dateText` → `date_text`
- `timeText` → `time_text`
- `durationMinutes` → `duration_minutes` (solo si `> 0`)
- `needsConfirmation` → `needs_confirmation`
- `missingFields` → `missing_fields`
- `sourceText` → `source_text`
- **`confidence`** solo se envía si está en **`[0, 1]`** (omitido si viene fuera de rango)

## Participantes

- En UI son un solo campo de texto (**"Ana, Luis"**).
- Al guardar: **`split(',')`**, **`trim`**, eliminar vacíos → **`list<String>`** en PATCH.

## Refresco tras mutación

- Tras PATCH/DELETE con éxito, **`HybridCalendarRepository`** vuelve a llamar **`GET /events`**; si ese GET puntual falla, se registra **`debugPrint`** y se conserva cache previa (**`readsFromBackend`** no se fuerza a falso ahí).

## Fallback

Si **`refreshFromBackend`** inicial falló, **`readsFromBackend` false`** → vistas mezcladas con mocks; **sin** menú PATCH/DELETE en esas filas (salvo falsos positivos evitados con **`mock_`** ids).
