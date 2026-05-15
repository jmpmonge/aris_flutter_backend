# Backend — Contrato PATCH/DELETE eventos (v0.43)

## Endpoints nuevos

| Método | Ruta | Cuerpo / respuesta |
|--------|------|---------------------|
| **PATCH** | `/events/{event_id}` | JSON según **`EventPatchBody`** (parcial); respuesta — evento actualizado (dict igual que en **`GET /events`**). |
| **DELETE** | `/events/{event_id}` | Sin cuerpo; éxito **`{"status": "deleted", "id": "<event_id>"}`**. |

El **`GET /events`** existente permanece igual (lista sin cambios semánticos).

## `EventPatchBody` (solo campos presentes cuentan; `extra` forbids)

Todos los campos son **opcionales** (`null` puede omitirse o enviarse y se trata como “no actualizar ese valor” donde aplique tras la validación interna):

| Campo | Tipo en modelo | Validación destacada (`build_event_updates_from_patch`) |
|-------|-----------------|-----------------------------------------------------------|
| `title` | `str \| None` | Si llega texto, debe ser no vacío tras `strip`. |
| `date_text` | `str \| None` | Igual que arriba. |
| `time_text` | `str \| None` | Igual. |
| `location` | `str \| None` | Solo actualiza si, tras strip, no es vacío. |
| `participants` | `list[str] \| None` | Lista de strings no vacíos después de strip; debe quedar ≥1 entrada. |
| `description` | `str \| None` | Como `location`: solo si strip no vacío. |
| `duration_minutes` | `int \| None` | Entero positivo (`> 0`). |
| `confidence` | `float \| None` | Float en **[0, 1]**. |
| `needs_confirmation` | `bool \| None` | Se pasa como bool al store. |
| `missing_fields` | `list[str] \| None` | Lista de strings sin vacíos; ≥1 entrada. |
| `source_text` | `str \| None` | Como `description`. |

Restricciones globales:

- No se acepta un patch **vacío** (`{}` o solo valores que tras filtrado no aplican cambio).
- No se modifican **`id`** ni **`created_at`** desde el PATCH (el cliente no debe enviarlas; **`EventsStore.update_event`** las ignora).
- **`EventsStore`** sigue fusionando **`participants`**, normalizando tipos conocidos y fijando **`updated_at`**.

## HTTP

- **404** **`detail`**: "Evento no encontrado".
- **400** **`detail`**: texto en español (validación cliente/patch).

## Pruebas manuales rápidas (curl)

Servidor típico: `http://127.0.0.1:8000`.

1. **`GET /events`** — obtener listado y un **`id`** real.

2. **PATCH**:

```bash
curl -s -X PATCH "http://127.0.0.1:8000/events/<EVENT_ID>" \
  -H "Content-Type: application/json" \
  -d '{"title":"Nuevo título","date_text":"mañana","time_text":"09:30"}'
```

3. **DELETE**:

```bash
curl -s -X DELETE "http://127.0.0.1:8000/events/<EVENT_ID>"
```

4. Volver a **`GET /events`** y comprobar que el recurso existe actualizado o ha desaparecido.

## Nota sobre Flutter

Hasta **[v0.44 planeada]** la capa **`CalendarScreen` / cliente HTTP** puede seguir usando solo **`GET /events`**; estas mutaciones están listas para integración puntual cuando se defina el flujo UX.
