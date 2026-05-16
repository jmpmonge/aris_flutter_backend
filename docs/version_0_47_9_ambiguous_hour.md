# v0.47.9 — Validar hora ambigua 7/19

## 1. Objetivo

Validar el primer caso crítico del backend mínimo: creación de cita con hora ambigua («a las 7» sin mañana/tarde/noche ni hora 24 h inequívoca). GPT debe devolver **`s = ask`** con pregunta cerrada y **`pending.options`**, sin **`s = ready`**, sin inventar ni elegir hora antes de preguntar.

## 2. Caso probado

Usuario:

`quiero poner una cita mañana a las 7 con Luis`

Respuesta esperada visible al usuario:

`¿Te refieres a las 7:00 o a las 19:00?`

Estado de hilo (`thread_state.json`) esperado: **`open`: true**, **`intent`**: `event`, **`object`** con datos parciales (p. ej. título/fecha/`time`: `"7"`/personas), **`pending`**: campo `time`, **`options`**: `["07:00", "19:00"]`. No debe crearse evento hasta desambiguación.

## 3. Qué cambia

Archivos modificados en esta iteración:

- [`backend/core/decision_prompt.py`](../backend/core/decision_prompt.py): bloque **REGLA CRÍTICA** para hora coloquial ambigua (`ask`, no `ready`, no inventar hora, `pending`/`q` esperados para 7 ↔ 07:00/19:00; espejo conceptual para las 8).
- [`backend/core/openai_client.py`](../backend/core/openai_client.py): `response_format={"type":"json_object"}` en Chat Completions para estabilizar el JSON técnico.
- [`backend/core/payload_builder.py`](../backend/core/payload_builder.py): regla en `rules` para turno `new`: `colloquial_hour_ambiguity` (solo empaquetado hacia GPT, sin interpretación local del mensaje).
- [`backend/main.py`](../backend/main.py): versión **`v0.47.9`** en `/health`.
- [`backend/README.md`](../backend/README.md): referencia breve al alcance **v0.47.9**.

No se modifican en esta versión específica (contrato ya cubierta o sin cambios):

- [`backend/core/engine.py`](../backend/core/engine.py) — ante **`s == "ask"`** ya persiste `open`, `intent`, `object`, `last_question`, `pending` y responde con `q` saneada; no ejecuta creación en stores.
- [`backend/storage/thread_state_store.py`](../backend/storage/thread_state_store.py) — ya persiste **`intent`**, **`object`**, **`last_question`**, **`pending`**, **`updated_at`**.

## 4. Qué no cambia

No cambia:

- Flutter.
- `.env`.
- `backend_legacy_v046`.
- stores de eventos/tareas/notas (salvo efectos esperados cuando el modelo devuelva `ready` en otro caso).
- contrato de endpoints HTTP.
- `need_context` real (solo el marcador de engine existente).
- update/delete complejos.

## 5. Resultado esperado

- No se crea evento todavía con hora ambigua sin desambiguar.
- Se guarda hilo abierto con `intent` / `object` / `last_question` / `pending`.
- La pregunta visible no muestra datos técnicos (JSON interno, nombres de campos tipo `pending`, etc.).
- No se muestran IDs ni JSON crudo en la respuesta al usuario.

Sin `OPENAI_API_KEY` (o ante fallo de GPT): **`POST /message`** no debe devolver error 500; respuesta controlada del motor; sin creación de evento.

## 6. Pruebas manuales

Arranque:

```bash
python3 -m uvicorn backend.main:app --reload
```

Mensaje (con API Key configurada en el entorno):

```bash
curl -X POST http://127.0.0.1:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text":"quiero poner una cita mañana a las 7 con Luis"}'
```

Respuesta esperada (cuerpo aproximado):

```json
{
  "text": "¿Te refieres a las 7:00 o a las 19:00?",
  "type": "assistant",
  "ui_hint": null
}
```

Comprobación sin nuevo evento hasta confirmar hora:

```bash
curl http://127.0.0.1:8000/events
```

Estado del hilo:

```bash
cat backend/data/thread_state.json
```

## 7. Commit sugerido

```bash
git add backend/core/decision_prompt.py backend/core/engine.py backend/core/payload_builder.py backend/core/openai_client.py backend/storage/thread_state_store.py backend/main.py backend/README.md docs/version_0_47_9_ambiguous_hour.md
git commit -m "test: validate ambiguous hour flow v0.47.9"
```

(Ajustar `git add` si algún archivo no hubiera cambiado en tu copia.)

## 8. Tag sugerido

```bash
git tag v0.47.9-ambiguous-hour
```
