# v0.47.12 — Update real de evento

## 1. Objetivo

Permitir que Aris ejecute **técnicamente** una modificación de **evento** cuando GPT devuelve **`s = ready`**, **`i = event`**, **`a = update`**, **`target`** con id existente y **`obj`** sólo con campos cambiados ya interpretados/decididos por el modelo —sin que el backend elija entre candidatos ambiguos ni interprete por su cuenta el texto libre más allá de mapeo y validaciones estrictas.

## 2. Qué cambia

- [`backend/core/engine.py`](../backend/core/engine.py): **`_handle_ready_update_event`**, **`_event_updates_from_obj`**; en **`ready`/`event`/`update`** se valida **`target`**, existe el evento, hay **updates** no vacíos, se llama **`EventsStore.update_event`**, se limpia **`thread_state`**, respuesta **`r`** saneada o mensaje corto por defecto. En **`s = ask`**, el **`ThreadStateStore`** guarda opcionalmente **`target`** (**`extract_event_target_id`**) junto **`pending`**/ **`object`** ya devueltos por GPT —Aris **no inventa** `target`/opciones si el modelo no los envía (el contrato GPT se refuerza en el prompt).
- [`backend/storage/events_store.py`](../backend/storage/events_store.py): **`get_event_by_id(event_id) -> dict | None`**.
- [`backend/core/payload_builder.py`](../backend/core/payload_builder.py): **`normalize_target_id`**, **`extract_event_target_id`**; **`normalize_gpt_response`** conserva **`target`** como **string id** cuando viene como cadena única o objeto `{"id": "..."}`; **`build_payload`** incluye **`thread.target`** en **`continue`** si está persistido.
- [`backend/storage/thread_state_store.py`](../backend/storage/thread_state_store.py): clave opcional **`target`** y limpieza al cerrar hilo.
- [`backend/core/decision_prompt.py`](../backend/core/decision_prompt.py): contrato y ejemplos **update** / **ask** posteriores a **context_response**; continuación **«a las 20»** → **ready/update** con **`time` = "20:00"**; eliminado el aviso de que Aris bloquea **update** (sustituido por ejecución **v0.47.12+**).
- [`backend/main.py`](../backend/main.py): **`/health`** → **`v0.47.12`**.
- [`backend/README.md`](../backend/README.md): línea **v0.47.12** y ajuste del apartado «Todavía no incluye».

## 3. Qué no cambia

No cambia:

- Flutter.
- `.env`.
- `backend_legacy_v046`.
- **delete**.
- update de **tareas**/**notas** desde este flujo GPT.
- need_context **`resolver`** fuera del **dominio calendario** (v0.47.11).
- contratos externos de tipo **`raw`/`mode`/`thread`/`s`/`ctx`** en la misma familia compacta que hitos previos (`new`/`continue`/`context_response`).
- endpoints estructurales HTTP.

## 4. Principio rector

Aris no decide semánticamente. Aris sólo ejecuta cuando GPT ha **estructurado** **target**, **payload de cambios** (**`obj`**) y **estados** esperados (**`ready`** vs **`ask`**) según política del prompt.

## 5. Flujo probado (manual conceptual)

Usuario:

`cambia la cita con Luis de las 7 a las 8`

GPT puede devolver **`need_context`** → Aris enriquece y reenvía (v0.47.11) → GPT puede **preguntar** **8:00** vs **20:00**.

Usuario:

`a las 20`

GPT debe devolver **`ready`**/**`update`** con **`target`** = id del evento y **`obj.time`** (**o** **`time_text`**) **`"20:00"`**.

Aris:

- Llama **`update_event`**.
- Cierra hilo (**`open: false`** tras **`clear_state`**).

## 6. Pruebas manuales

Prepara un evento con **Luis**, **mañana**, **19:00**, etc. Luego:

```bash
python3 -m uvicorn backend.main:app --reload
```

```bash
curl -X POST http://127.0.0.1:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text":"cambia la cita con Luis de las 7 a las 8"}'
```

Si el modelo pregunta (p. ej. **8 vs 20**):

```bash
curl -X POST http://127.0.0.1:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text":"a las 20"}'
```

Comprueba lista y hilo:

```bash
curl http://127.0.0.1:8000/events
cat backend/data/thread_state.json
```

**Esperado (si GPT cumple contrato):** un evento único actualizado (**`time_text`: `20:00`**), **`open: false`** en **`thread_state`**. El comportamiento visible exacto sigue dependiendo del modelo aplicando **`decision_prompt`**.

## 7. Commit sugerido

```bash
git add backend/core/decision_prompt.py backend/core/engine.py backend/core/payload_builder.py backend/storage/events_store.py backend/storage/thread_state_store.py docs/version_0_47_12_event_update.md backend/main.py backend/README.md
git commit -m "feat: support event update flow v0.47.12"
```

## 8. Tag sugerido

```bash
git tag v0.47.12-event-update
```
