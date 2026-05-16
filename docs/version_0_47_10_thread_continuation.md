# v0.47.10 — Continuación correcta del hilo abierto

## 1. Objetivo

Validar que una respuesta del usuario a una pregunta previa (desambiguación de hora) se interpreta como **continuación** del hilo (**`mode: "continue"`**), no como una petición nueva desde cero, y que GPT **cierra** el **`pending`** con **`s = ready`** y **`time`** canónico (p. ej. **`19:00`**) compatible con **`thread.pending.options`**.

## 2. Caso probado

**Primer mensaje:**

`quiero poner una cita mañana a las 7 con Luis`

**Respuesta esperada:**

`¿Te refieres a las 7:00 o a las 19:00?`

Estado esperado en `thread_state.json`: **`open: true`**, **`pending.options`**: `["07:00", "19:00"]`.

**Segundo mensaje:**

`a las 19`

**Respuesta esperada:**

`He guardado la cita con Luis para mañana a las 19:00.`

Esperado: **un único evento**, **`time_text`**: **`19:00`**, **`open: false`** en **`thread_state`**, sin nueva pregunta ni **¿19 o 20?**.

## 3. Qué cambia

Archivos modificados en esta iteración:

- [`backend/core/decision_prompt.py`](../backend/core/decision_prompt.py): sección explícita **REGLA CRÍTICA — mode = continue** (preservar **`thread.object`**, emparejar **`raw`** con una opción de **`pending.options`**, **`ready`/`create`**, **`pending: null`**, prohibido re-preguntar hora o **¿19 o 20?**); aclaraciones en reglas obligatorias 6–7; matiz sobre el primer turno ambiguo frente al turno continuo.
- [`backend/core/payload_builder.py`](../backend/core/payload_builder.py): en **`mode == "continue"`**, nueva clave **`rules.continuation`** (solo texto de política hacia GPT, sin parsing local del **`raw`**). El empacado **`mode`/`thread`** ya cumplía el contrato (no se envía **`new`** cuando **`open`** es verdadero).

Sin cambios de comportamiento solicitados aquí pero ya alineados con el resultado esperado:

- [`backend/core/engine.py`](../backend/core/engine.py) — **`ready` + event + create`**: **`_event_payload`** mapea **`title`**, **`date`/`date_text`**, **`time`/`time_text`**, **`people`/`participants`**; tras guardar borra **`thread_state`** (**`clear_state`**).
- [`backend/storage/thread_state_store.py`](../backend/storage/thread_state_store.py) — doc del contrato **`open`/`intent`/`object`/`last_question`/`pending`**.
- [`backend/main.py`](../backend/main.py) — versión **`v0.47.10`** en **`GET /health`**.
- [`backend/README.md`](../backend/README.md) — línea de estado **v0.47.10**.

## 4. Qué no cambia

No cambia:

- Flutter.
- `.env`.
- `backend_legacy_v046`.
- `need_context` real (solo el marcador en engine existente).
- update/delete complejos.
- forma estructural de endpoints HTTP (`/health`, `/message`, `/events`, …).
- diseño principal de stores JSON (`EventsStore`, etc.), salvo el efecto de un **`create`** correcto cuando GPT devuelve **`ready`**.

## 5. Resultado esperado

- Se crea **un solo** evento al confirmar **`a las 19`** cuando el hilo tiene **`["07:00","19:00"]`** pendientes (depende del modelo aplicando este prompt/reglas).
- El evento almacena **`time_text`** coherente con la opción elegida (p. ej. **`19:00`**).
- Se limpia el hilo abierto (**`open: false`** y campos nulos tras **`clear_state`** por implementación actual).
- No se muestra JSON ni fugas internas típicas al usuario (**`sanitize_visible_text`** en **`r`**).

## 6. Pruebas manuales

```bash
python3 -m uvicorn backend.main:app --reload
```

Opcionalmente limpiar datos:

```bash
rm -f backend/data/events.json backend/data/thread_state.json
```

**Primer mensaje:**

```bash
curl -X POST http://127.0.0.1:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text":"quiero poner una cita mañana a las 7 con Luis"}'
```

```bash
cat backend/data/thread_state.json
```

**Segundo mensaje:**

```bash
curl -X POST http://127.0.0.1:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text":"a las 19"}'
```

```bash
curl http://127.0.0.1:8000/events
cat backend/data/thread_state.json
```

## 7. Commit sugerido

```bash
git add backend/core/decision_prompt.py backend/core/payload_builder.py backend/core/engine.py backend/storage/thread_state_store.py backend/main.py backend/README.md docs/version_0_47_10_thread_continuation.md
git commit -m "test: validate thread continuation v0.47.10"
```

## 8. Tag sugerido

```bash
git tag v0.47.10-thread-continuation
```
