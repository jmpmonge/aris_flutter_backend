# Versión v0.39 — Health check Flutter → FastAPI

## Objetivo

Conectar de forma **mínima y aislada** la app Flutter con el backend mediante **`GET /health`**, para validar conectividad y URL base sin tocar mocks ni otros endpoints.

## Backend

- **Sin cambios** en `aris_backend/`.
- Endpoint usado: `GET http://127.0.0.1:8000/health` → cuerpo JSON `{"status":"ok"}`.

## Flutter — capa API (`lib/core/api/`)

| Archivo | Rol |
|---------|-----|
| `api_config.dart` | `ApiConfig.baseUrl` = `http://127.0.0.1:8000` y `baseUri`. |
| `api_client.dart` | `checkHealth()` delega en ejecución de red; GET/POST/PATCH genéricos siguen sin red. Fábrica `ApiClient.localBackend()` y `ApiClient.provisional()`. |
| `health_check.dart` | Punto único para importación condicional. |
| `health_check_io.dart` | Implementación con `dart:io` / `HttpClient`. |
| `health_check_stub.dart` | Fallback (p. ej. web) sin `dart:io`: devuelve `unsupported_platform` si hay URL. |
| `api_endpoints.dart` | Nueva constante `ApiEndpoints.health` (`/health`) documentada junto al resto provisional. |

**Dependencias:** ninguna nueva; uso de **`dart:io`** solo tras import condicional (`health_check_io.dart`). En web no hay red real hasta decidir estrategia.

## Flutter — repositorio

- `lib/core/repositories/backend_status_repository.dart`: contrato `BackendStatusRepository` e implementación `RemoteBackendStatusRepository` que solo llama a `ApiClient.checkHealth()`.
- `Repositories.backendStatus` instanciado con `ApiClient.localBackend()`.

## UI

- **Ajustes** (`SettingsScreen`): sección **«Servidor FastAPI (desarrollo)»** con:
  - Indicador discreto: *no comprobado*, *Comprobando…*, *Backend conectado*, *Backend sin conexión*.
  - Botón **«Comprobar conexión»**.
  - Texto aclaratorio: la app sigue con **mocks** si el servidor no está activo.

**No se modifica:** Perfil, Home, `/message`, notas/tareas/eventos/historial ni OpenAI desde Flutter.

## Plataforma (HTTP local sin TLS)

| Plataforma | Cambio |
|------------|--------|
| **Android debug** | `android:usesCleartextTraffic="true"` en `android/app/src/debug/AndroidManifest.xml` (mantiene `INTERNET`). |
| **iOS** | `NSAllowsLocalNetworking` en `ios/Runner/Info.plist`. |

### Emulador Android

Desde el emulador, `127.0.0.1` suele apuntar al propio emulador, no al host. Para llegar al FastAPI del PC suele usarse **`10.0.2.2:8000`** (no incluido en `ApiConfig` por defecto: el proyecto fija explícitamente `127.0.0.1` para simulator/dispositivo con túnel o ejecución en macOS Desktop).

## Comportamiento si el backend está apagado

Las llamadas fallan (`no_connection`, `timeout`, etc.) sin propagarse al resto de la app; los datos mostrados siguen siendo los de los **repositorios locales/mock**.

## Próximo paso (v0.40)

Cablear entrada de usuario (p. ej. Home/asistente) con `POST /message` mediante repositorios, sin eliminar mocks hasta decidir estrategia de conmutador.
