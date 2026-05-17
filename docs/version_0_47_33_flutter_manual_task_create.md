# v0.47.33 — Crear tarea manual desde Flutter en backend

## 1. Objetivo

Unificar tareas creadas por chat y tareas creadas manualmente: todas se guardan en backend.

## 2. Diseño

No hay decisión semántica.

Flutter envía una ficha de tarea.

Backend valida técnicamente y guarda.

## 3. Endpoint

POST /tasks

Body:

```json
{
  "title": "...",
  "description": "...",
  "date_text": "...",
  "date_iso": "YYYY-MM-DD",
  "time_text": "HH:MM",
  "priority": "normal|high",
  "tags": []
}
```

## 4. UI

No distinguir visualmente Aris/manual.

No usar tareas simuladas permanentes para el flujo manual.

Una sola lista (`GET /tasks`).

## 5. Fuera de alcance

- edición amplia;
- borrado;
- tarjeta compacta/desplegable final;
- mail;
- GPT.

## 6. Validación

- `python3 scripts/smoke_backend_minimal_v047.py`
- `python3 scripts/smoke_backend_http_v047.py`
- creación manual desde Flutter persiste en `GET /tasks`
