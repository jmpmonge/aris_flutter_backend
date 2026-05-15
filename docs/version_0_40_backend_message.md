# v0.40 — Mensaje desde Flutter hacia backend (`POST /message`)

## Alcance

- El **input principal de Inicio** (barra inferior de chat del shell de navegación) envía texto al FastAPI mediante **`POST /message`** cuando la app tiene red y compila contra `dart:io`.
- **No** se modificó el backend, **no** se conectaron listas (`GET /tasks`, `/notes`, `/events`, `/history`).
- **OpenAI**, motor simbólico y **pending actions** siguen ejecutándose **solo en servidor**.

## Contrato revisado desde `backend/` (solo lectura)

### Request (`UserMessage` en `backend/models/assistant_message.py`)

Campo obligatorio:

- **`text`**: contenido enviado por el usuario.

Campos opcionales con valores por defecto en servidor:

- **`type`** (por defecto `"user"`).

En Flutter solo se serializa **`text`** + **`type": "user"`**; **`created_at`** lo rellena Pydantic si hiciera falta.

### Response (`AssistantResponse`)

- **`text`** (string): respuesta mostrada como burbuja de Aris.
- **`type`** (string, habitualmente `"assistant"`).
- **`ui_hint`** (`str | None`): hints de UX generados por el motor en backend.

El cliente mapea `ui_hint` → **`AssistantResponseModel.uiHint`**.

## Comportamiento de la app

1. Usuario pulsa enviar → se limpia el campo y aparece **`Consultando…`** en la zona Reciente (`awaitingBackend`), con spinner discreto en la tarjeta.
2. Respuesta **`200`** y JSON válido → se muestra **`text`**; si llega **`ui_hint`**, línea pegada bajo la burbuja (caso destacado **`confirm_rescue`**: texto fijo aclaratorio; sin botones todavía).
3. Backend apagado, timeout o HTTP no 2xx → burbuja con: *«No puedo conectar con el backend ahora mismo. Mantengo el modo local.»* (mensaje configurado en `ChatService`).
4. **Fallback local “rico”**: no se re-ejecuta `IntentClassifier` en este flujo ante fallo; se priorizó mensaje corto único sobre duplicar lógica. Siguen disponibles **`ChatService.sendLocalMessage`**, clasificadores y **`LocalActionService`** para otros usos/demo.
5. **Tarjeta RECIENTE**: misma **`recentConversationBodyMaxHeight`** que antes; lista con scroll interno; no usar listas nuevas desde API.

## Configuración

- Base URL como en v0.39: **`ApiConfig.baseUrl`** → `http://127.0.0.1:8000`.

## Siguiente paso sugerido (v0.41)

Integrar **`GET /history`** (y a posteriori tareas/notas/eventos según roadmap) usando repositorios, sin sustituir aún todas las vistas mock hasta cerrar modelo de estado.
