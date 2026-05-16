# v0.47.13 — Consulta de eventos

## 1. Objetivo

Permitir **consultas básicas** sobre eventos del almacén local usando el flujo ya existente **`need_context`** → **`resolver_contexto`** → **`context_response`** → segunda decisión GPT, donde el modelo debe cerrar típicamente con **`s = answer`** y texto en **`r`**, sin tocar **`EventsStore`** más que en **lectura** para armar **`context.candidatos`**.

## 2. Casos probados (objetivo de producto)

- «qué tengo mañana»
- «qué citas tengo con Luis»
- «a qué hora tengo la cita con Luis»

(El texto exacto de la respuesta depende del modelo y del [`decision_prompt.py`](../backend/core/decision_prompt.py). Aris garantiza sólo transporte técnico y sanitización superficial de **`q`**/**`r`**.)

## 3. Qué cambia

- [`backend/core/decision_prompt.py`](../backend/core/decision_prompt.py): reglas cuando el usuario **pregunta por agenda**/citas (**`need_context`**, **`i = event`**, **`a = query`**) con **`ctx`** calendar (`events_by_date` / `events_by_person`); en **`mode = context_response`**, bifurcación explícita por **`thread.action = query`** → responder **`answer`**, usar **`count`**/**candidatos**, frase modelo para **`count = 0`**, prohibición de jargon interno visible.
- [`backend/core/context_resolver.py`](../backend/core/context_resolver.py): comparación táctica **`events_by_date`** con **`casefold`** y espacios colapsados (encaja **`mañana`**, **`hoy`**, nombres de día **lunes … domingo** si coinciden con **`date_text`** guardado literalmente —**sin** capa de fechas civiles); docstring de referencia.
- [`backend/core/engine.py`](../backend/core/engine.py): camino defensivo **`ready` + `query`** (sólo lectura: contesta **`r`**, limpia hilo, **no** persiste); el flujo esperado principal sigue siendo **`s = answer`** tras **`context_response`**.
- [`backend/main.py`](../backend/main.py): **`/health`** → **`v0.47.13`**.
- [`backend/README.md`](../backend/README.md): línea **v0.47.13**.

El flujo **`need_context` + segunda llamada** viene de **v0.47.11**; **v0.47.13** documenta el **uso consultivo**.

## 4. Qué no cambia

No cambia:

- Flutter.
- `.env`.
- `backend_legacy_v046`.
- **delete**.
- **mail**.
- Consultas equivalentes sobre **tareas**/**notas**.
- **`update`/create** cuando ya estaban definidos (**v0.47.12** y anteriores).
- Contratos JSON compactos de primer nivel (**`raw`**, **`mode`**, **`thread`**, **`rules`**, …).

## 5. Principio rector

Aris no clasifica aquí si la frase «es» o «no» consulta: **GPT** elige **`need_context`** y el **`ctx`**. Aris ejecuta sólo **`resolver_contexto`** y vuelve a pasar resultado al modelo (**`context`**); la redacción final es **GPT**.

## 6. Pruebas manuales

Preparación sugerida: un evento con **title** «cita con Luis», **`date_text`**: **mañana**, **`time_text`**: **20:00**, **`participants`**: **["Luis"]**.

```bash
python3 -m uvicorn backend.main:app --reload
```

```bash
curl -X POST http://127.0.0.1:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text":"qué tengo mañana"}'

curl -X POST http://127.0.0.1:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text":"qué citas tengo con Luis"}'

curl -X POST http://127.0.0.1:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text":"a qué hora tengo la cita con Luis"}'

curl http://127.0.0.1:8000/events
```

**Esperado:** respuestas conversacionales (sin JSON bruto visible al usuario típico) y **`GET /events`** sin modificaciones cuando el modelo responda **`answer`** (o **`ready`/`query`** legítimos).

## 7. Commit sugerido

```bash
git add backend/core/decision_prompt.py backend/core/context_resolver.py backend/core/engine.py docs/version_0_47_13_event_query.md backend/main.py backend/README.md
git commit -m "feat: support event queries v0.47.13"
```

## 8. Tag sugerido

```bash
git tag v0.47.13-event-query
```
