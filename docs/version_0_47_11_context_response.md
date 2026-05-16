# v0.47.11 — Respuesta de contexto para GPT

## 1. Objetivo

Implementar el flujo interno por el que Aris **responde a una decisión `need_context` de GPT** sin interpretar por su cuenta la petición del usuario: ejecuta solo una **consulta técnica estructurada** al almacén de eventos y **reaenvía la petición original** al modelo en un segundo turno con **`mode = "context_response"`**.

## 2. Idea central

**`need_context` no tiene por qué “cerrar” la conversación hacia fuera.**

Aris registra los datos previos necesarios y, antes de responder al usuario, puede:

1. Resolver la solicitud **`ctx`** vía **`resolver_contexto`** (solo calendario).
2. Construir un payload **`build_context_response_payload`** (`raw` = petición raíz preservada).
3. Llamar de nuevo a **`ask_gpt`** y tratar esa segunda salida igual que cualquier otra (**`ready` / `ask` / `answer` / `fail` / `need_context`** recursivo con tope).

## 3. Qué cambia

- Se crea [`backend/core/context_resolver.py`](../backend/core/context_resolver.py) (`resolver_contexto`): consultas **calendar** **`events_by_person`**, **`events_by_date`**, **`events_by_person_and_time`**; salida **`dominio`**, **`consulta`**, **`filtros`**, **`candidatos`**, **`count`**. Comparaciones técnicas (personas/fecha/`time` compatibles **`7`**/**`8`** según especificación **sin decidir cuál hora correcta semántica**).
- [`backend/core/payload_builder.py`](../backend/core/payload_builder.py): **`build_context_response_payload`** más descripción **`mode`/intro** en el prompt cuando aplica **`context_response`** (`context` empacado desde el objeto devuelto por el resolver).
- [`backend/core/decision_prompt.py`](../backend/core/decision_prompt.py): reglas explícitas para **`mode = context_response`** y matiz ejemplo **«cambia la cita … de las 7 a las 8»** con candidatos **19:00** (`ask` ante **«a las 8»**, sin **`update`** real en v0.47.11).
- [`backend/core/engine.py`](../backend/core/engine.py): **`need_context`** abre **`_flujo_need_context`** (segunda llamada GPT, **`peticion_original`** / **`peticion_raiz`** estable desde **`pending`** si el hilo quedó en contexto pendiente); **`ready` + `update`** contesta **`Todavía no puedo completar esa modificación con seguridad.`** sin persistir cambios.

## 4. Qué no cambia

No cambia:

- Flutter.
- `.env`.
- `backend_legacy_v046`.
- **Update real** de eventos (**v0.47.12+** previsto).
- **Delete**.
- **`need_context` resuelto desde tareas/notas** (`tasks_store`/`notes_store` sólo llegan hasta el firma futuro; el resolver los ignora hoy).
- Contratos externos compactos GPT (**`raw`**, **`mode`**, **`thread`**, **`rules`**, **`s`/`i`/`a`/`ctx`/`obj`**, …).
- Endpoints REST estructurales del backend mínimo.

## 5. Flujo (resumen)

Usuario:

`cambia la cita con Luis de las 7 a las 8`

GPT (**1.ª llamada**):

`s = need_context`

`ctx` ≈ `{ "domain": "calendar", "query": "events_by_person_and_time", "filters": { "people": ["Luis"], "time": "7" } }`

Aris (`resolver_contexto`):

Encuentra en **`events_store`** candidatos compatibles con el filtro **técnico `time`** (p. ej. evento con **19:00**).

Aris (**2.ª llamada GPT**, `mode = context_response`):

Reenvía la **misma petición original** más **`thread.ctx_requested`** y **`context.candidatos`**.

GPT (**2.ª salida esperada típica** en esta versión):

Puede responder **`ask`** con pregunta cerrada del tipo «¿… a las **8:00** o a las **20:00**?» (ambigüedad de la nueva hora), **sin ejecutar modificaciones** porque el backend aún bloquea **`update`** con mensaje seguro cuando el modelo emite **`ready`+`update`**.

## 6. Prueba manual sugerida

Crear antes un evento (p. ej. con Luis mañana a **19:00**, vía **`POST /message`** anterior o alta directa si procede tu entorno).

```bash
python3 -m uvicorn backend.main:app --reload
```

```bash
curl -X POST http://127.0.0.1:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text":"cambia la cita con Luis de las 7 a las 8"}'
```

**Esperado aproximado en v0.47.11 (dependiendo del modelo):**

- Aris **no** aplica **`update`** todavía ante **`ready`**+**`update`**.
- Puede mostrarse una **pregunta** razonada (p. ej. **8:00** vs **20:00**) sin **UUIDs**/JSON fugados al texto visible.
- **`raw`** de la segunda ronda conserva literalmente la **petición raíz**.

## 7. Commit sugerido

```bash
git add backend/core/context_resolver.py backend/core/payload_builder.py backend/core/decision_prompt.py backend/core/engine.py docs/version_0_47_11_context_response.md backend/main.py backend/README.md
git commit -m "feat: add context response flow v0.47.11"
```

(Ajusta la lista **`git add`** si en tu máquina no hubieras tocado algunos ficheros.)

## 8. Tag sugerido

```bash
git tag v0.47.11-context-response
```
