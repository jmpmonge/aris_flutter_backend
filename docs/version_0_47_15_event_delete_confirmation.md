# v0.47.15 — Borrado de eventos con confirmación

## 1. Objetivo

Permitir borrar eventos existentes solo con confirmación explícita.

## 2. Qué cambia

- Se ajusta `backend/core/decision_prompt.py` para borrado seguro (pregunta de confirmación, `pending` con `delete_confirmation`, `need_context` + `context_response` para delete sin ejecutar antes de tiempo).
- Se soporta `ready/event/delete` en `backend/core/engine.py` (solo si hay `target` válido que exista en el store).
- Se verifica `delete_event` en `EventsStore` (ya estaba disponible).
- Se añade smoke de borrado en `scripts/smoke_backend_minimal_v047.py`.

## 3. Qué no cambia

No cambia:

- Flutter.
- `.env`.
- `backend_legacy_v046`.
- delete de tareas/notas.
- mail.
- contratos estables (`raw`, `mode`, `thread`).
- necesidad de `need_context` estructural cuando GPT lo pida.

## 4. Principio rector

Aris no decide semánticamente. Aris solo ejecuta un borrado si GPT devuelve `ready`/`delete` con `target` claro y el flujo guiado previo viene del modelo (confirmación tras `ask`/`delete_confirmation`).

## 5. Flujo esperado

Usuario:

«borra la cita con Luis»

Aris/GPT:

«¿Confirmas que quieres borrar la cita con Luis de mañana a las 20:00?»

Usuario:

"sí"

Aris:

«He borrado la cita con Luis.»

## 6. Pruebas manuales

Servidor FastAPI arrancando desde la raíz del repo (`uvicorn` u otro), con datos en `backend/data/` o vacío menos el evento de prueba (puede crearse antes vía `_events`/API si existiera).

Registrar un evento (título «cita con Luis», `date_text`: mañana, `time_text`: 20:00, participantes Luis) y ejecutar:

```bash
curl -X POST http://127.0.0.1:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text":"borra la cita con Luis"}'
```

Comprobar: respuesta de confirmación; **no** borrar aún.

```bash
curl http://127.0.0.1:8000/events
```

El evento debe seguir listado.

```bash
curl -X POST http://127.0.0.1:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text":"sí"}'
```

Respuesta esperable (según modelo): texto tipo «He borrado…».

```bash
curl http://127.0.0.1:8000/events
```

El evento debe haber desaparecido.

```bash
cat backend/data/thread_state.json
```

`open` debe ser `false` (o estado cerrado equivalente tras normalización).

**Nota:** Los textos exactos los elige GPT; Aris ejecuta sólo ante `ready`/`event`/`delete` con UUID válido y limpia hilo tras borrar.

## 7. Smoke

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

## 8. Commit sugerido

```bash
git add backend/core/decision_prompt.py backend/core/engine.py backend/storage/events_store.py scripts/smoke_backend_minimal_v047.py docs/version_0_47_15_event_delete_confirmation.md
git commit -m "feat: support event delete confirmation v0.47.15"
```

*(Incluye también `backend/main.py` si subes etiqueta `/health`.)*

## 9. Tag sugerido

```bash
git tag v0.47.15-event-delete-confirmation
```
