# API de mensajes Flutter ↔ FastAPI · v0.40

Última revisión contra `backend/main.py`, `backend/models/assistant_message.py`.

## Endpoint

| Método | Ruta |
|--------|------|
| `POST` | `/message` |

URL absoluta desarrollo habitual: **`http://127.0.0.1:8000/message`** (véase **`ApiConfig` / `ApiEndpoints.message`**).

## Request body (JSON)

Mínimo requerido por el modelo servidor:

```json
{ "text": "tu mensaje" }
```

Recomendado en cliente (explicita papel de usuario):

```json
{
  "text": "tu mensaje",
  "type": "user"
}
```

| Campo | Tipo | Notas |
|-------|------|--------|
| `text` | string | **Nombre exacto** del campo en backend (no usar `content`/`message` como campo principal sin cambiar servidor). |
| `type` | string | Opcional para el servidor (`"user"` por defecto). |

## Respuesta esperada (`AssistantResponse`)

| Campo JSON | Dart (`AssistantResponseModel`) |
|-------------|--------------------------------|
| `text` | `text` |
| `type` | `type` (opcional si el cliente tolera falta). |
| `ui_hint` | `uiHint` |

Campos extra del backend (p. ej. `created_at`) se ignoran en la UI actual.

### `ui_hint`

Se guardan en el modelo pero la UI sólo muestra texto auxiliar discreto (`confirm_rescue` → texto fijo aclaratorio). Una botonera de confirmación puede entrar en v0.41+.

## Código Flutter relevante

| Pieza | Ruta |
|-------|------|
| `POST` sobre red | `lib/core/api/message_post.dart` (`package:http`; Web + móvil desde v0.40.1) |
| Firma cliente | `ApiClient.sendMessage` |
| Persistencia temporal de hilos Reciente | `ChatService.*` nuevos métodos + existentes mocks |
| Orquestación | `DefaultAssistantRepository.sendMessage` |
| UI envío Inicio | `AppNavigationShell` + `ChatInputBar` |

## Errores / offline

- No se lanzan excepciones hasta la UI por fallo HTTP: **`ApiResult`** desde capa cliente y repositorio.
- Tras cualquier fallo razonado de llamada (`no_connection`, `timeout`, HTTP error, parsing), el usuario sigue interactuando; en Reciente aparece mensaje **`ChatService.backendOfflineFriendlyReply`**.
- **Flutter no llama a OpenAI.**

## Pendiente próximas versiones

- Histórico y agendas desde `GET /history`, `GET/tasks`, `/notes`, `/events`.
- Comportamiento de `confirm_rescue` más rico cuando el producto lo exija.
