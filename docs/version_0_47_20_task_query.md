# v0.47.20 — Consulta básica de tareas

## 1. Objetivo

Permitir consulta básica de tareas mediante el flujo `need_context` + `context_response`.

## 2. Principio rector

Aris no decide semánticamente. GPT interpreta y decide. Aris recupera contexto técnico local (`TasksStore`) y GPT redacta la respuesta en **`answer`**.

## 3. Estado previo detectado

`TasksStore` ya exponía **`list_tasks()`**. El **`engine`** ya orquestaba **`need_context` → resolver_contexto → build_context_response_payload → segunda llamada GPT → `answer`** (igual que calendario). Esta versión añade **`context_resolver`** para **`domain`** **`tasks`** / **`task`** y **`query`** **`list_tasks`**, reglas del **prompt** y **smokes**.

## 4. Cambios realizados

| Archivo | Cambio |
|---------|--------|
| `backend/core/decision_prompt.py` | Consulta **task/query**, **context_response** cuando **intent == task**. |
| `backend/core/context_resolver.py` | Resolución **list_tasks** + filtros triviales opcionales. |
| `scripts/smoke_backend_minimal_v047.py` | `smoke_11_task_query_basic()`. |
| `backend/storage/tasks_store.py` | Sin cambios. |
| `backend/core/engine.py` | Sin cambios. |

## 5. Comportamiento soportado

Ejemplo de petición de contexto GPT:

```json
{
  "s": "need_context",
  "i": "task",
  "a": "query",
  "ctx": {
    "domain": "tasks",
    "query": "list_tasks",
    "filters": {}
  }
}
```

Resultado técnico:

- Aris rellena **candidatos** desde disco (sin inventar datos).
- Tras **`context_response`**, GPT debe responder **`answer`** usando solo esos candidatos.

Filtros implementados sólo cuando vienen explícitos en **`filters`**:

- **`completed`**: igualdad booleana.
- **`date`** o **`date_text`**: igualdad textual sobre **`task.date_text`** (sin resolver fechas civilmente).
- **`priority`**: igualdad textual tras normalización básica (minúsculas).

No se crean, actualizan ni borran tareas en este camino desde Aris más allá de lo que GPT pida fuera del flujo solo-consulta (el prompt prohíbe **`ready`** en **`context_response`**).

## 6. Fuera de alcance

- update / delete / complete de tareas;
- filtros semánticos o vencimientos reales;
- recordatorios / notificaciones;
- consulta de notas;
- búsqueda semántica.

## 7. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Salida esperada: `smoke_backend_minimal_v047: ALL OK`.
