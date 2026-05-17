# v0.47.21 — Consulta básica de notas

## 1. Objetivo

Permitir consulta básica de notas mediante el flujo `need_context` + `context_response`.

## 2. Principio rector

Aris no decide semánticamente. GPT interpreta y decide. Aris recupera contexto técnico local y GPT redacta la respuesta.

## 3. Estado previo detectado

`engine.py` ya soportaba el flujo `need_context` / `context_response` y pasaba `notes_store` a `resolver_contexto`. `NotesStore` ya exponía `list_notes()` y `add_note()`. Esta versión añade la resolución técnica de contexto para notas (`domain` `notes` / `query` `list_notes`), reglas en el prompt orientadas a GPT, smokes (`smoke_12_note_query_basic`) y esta documentación.

## 4. Cambios realizados

| Archivo | Cambio |
|---------|--------|
| `backend/core/decision_prompt.py` | Reglas explícitas para note/query y `context_response` de notas |
| `backend/core/context_resolver.py` | Soporte mínimo para ctx `domain=notes`, `query=list_notes` |
| `scripts/smoke_backend_minimal_v047.py` | Smoke de consulta básica de notas |
| `backend/storage/notes_store.py` | Sin cambios |
| `backend/core/engine.py` | Sin cambios |

## 5. Comportamiento soportado

Ejemplo inicial:

```json
{
  "s": "need_context",
  "i": "note",
  "a": "query",
  "ctx": {
    "domain": "notes",
    "query": "list_notes",
    "filters": {}
  }
}
```

Resultado:

- Aris recupera notas locales (solo lectura).
- GPT recibe `context_response` con `dominio` / `consulta` / `filtros` / `candidatos` / `count`.
- GPT responde con `s=answer`.
- No se crean, modifican ni borran notas en este flujo.

## 6. Fuera de alcance

- update de notas;
- delete de notas;
- búsqueda semántica;
- embeddings;
- etiquetas automáticas complejas;
- consulta de mail;
- conversión nota/tarea/evento.

## 7. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Resultado esperado: `smoke_backend_minimal_v047: ALL OK` (incluye smoke 12).
