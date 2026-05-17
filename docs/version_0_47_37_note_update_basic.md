# v0.47.37 — Modificación básica de notas

## 1. Objetivo

Permitir `note/update` con `target` y `obj`. Hasta esta versión, `note/update` no existía en el motor; cualquier intento de modificar una nota devolvía "operación no soportada".

## 2. Campos modificables

| Campo prefijado | Alias legacy | Tipo |
|---|---|---|
| `note_title` | `title` | string |
| `note_content` | `content` | string |
| `note_tags` | `tags` | lista |

## 3. Flujo

```
GPT → ready/note/update (target = id, obj = {note_content: "..."})
         ↓
Aris valida target
  No existe → "No encuentro esa nota en tu lista." (cierra hilo)
  Existe + obj vacío → "¿Qué quieres cambiar de esa nota?" (pending.field = note_update_value)
  Existe + obj con campos → update_note → last_focus/last_action
```

## 4. Casos cubiertos

| Caso | Comportamiento |
|---|---|
| Update directo | Modifica y cierra hilo |
| Target inexistente | Mensaje seco, hilo cerrado |
| Target válido, obj vacío | Pregunta qué cambiar, hilo abierto |
| Continuación `note_update_value` | Aplica el valor recibido |
| `need_context` con 1 candidata | Modifica directamente |
| Varias candidatas | Abre `target_selection` |

## 5. Archivos modificados

| Archivo | Cambio |
|---|---|
| `backend/core/engine.py` | Helper `_note_updates_from_obj`; handler `_handle_ready_update_note`; rama `note/update` en `_handle_ready` |
| `backend/core/decision_prompt.py` | Nueva sección "MODIFICAR NOTAS (v0.47.37)" con contrato, reglas, flujo `context_response` y continuaciones |
| `scripts/smoke_backend_minimal_v047.py` | `smoke_35_note_update_basic()` (casos A–F) |

## 6. Store

`notes_store.update_note` ya existía con soporte para `title`, `content` y `tags`. No fue necesario modificarlo.

## 7. Context resolver

`_candidate_from_note` ya incluía `id`, `label`, `title`, `content`, `tags`, `created_at`. No fue necesario modificarlo.

## 8. Fuera de alcance

- `note/delete` no implementado.
- No se implementa búsqueda semántica avanzada.
- No se implementan adjuntos ni editor Flutter.
- mail y RAG fuera de alcance.

## 9. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

35 smokes deben pasar (smoke 35 cubre los casos A–F de esta versión).
