# v0.44 — Flutter: acciones contra eventos (PATCH/DELETE `/events`)

## Alcance

- **`aris_flutter_v0_22`** conecta **`PATCH /events/{event_id}`** y **`DELETE /events/{event_id}`** cuando **`readsFromBackend`** es verdadero tras un **`GET /events`** correcto.
- **Sin** crear eventos desde Flutter vía nuevo POST:** la alta “inteligente” sigue en **`POST /message`** en servidor.
- **Sin** Google/Apple Calendar ni proveedor externo.
- **Mocks** (`mock_*` en cliente, **`CalendarService`**) no lanzan PATCH/DELETE; solo eventos cargados desde el backend muestran el menú de acciones.

## UX y mensajes

- Éxito: **"Evento actualizado."** / **"Evento eliminado."**
- Fallo/sin servidor para mutaciones en modo backend:** textos solicitados contra conexión con el backend.

## Archivos tocados

- `lib/core/api/api_client.dart`
- `lib/core/api/api_endpoints.dart`
- `lib/core/models/event_model.dart` / `backend_event_mapper.dart`
- `lib/core/repositories/calendar_repository.dart`
- `lib/features/calendar/presentation/calendar_event_sheet.dart`
- `lib/features/calendar/presentation/calendar_body_views.dart`

## Pendiente opcional

- Exponer en el mismo diálogo campos opcionales ya contemplados por API cliente (**confidence**, **durationMinutes**, **`needs_confirmation`**, etc.).
