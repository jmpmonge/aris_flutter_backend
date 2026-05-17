# v0.47.36.6 — Normalizador mínimo de ask/create completo

## 1. Problema

GPT podía devolver **`ask`/`create`** para confirmar una creación **no destructiva** que ya estaba técnicamente completa en **`obj`** (ej. pregunta del tipo «¿Te refieres a…?»).

## 2. Solución

Tras **`normalize_gpt_response`**, un normalizador en **`engine.py`** convierte **`s=ask`**, **`a=create`**, **`i` ∈ {event,task,note}** en **`s=ready`** cuando la ficha **`obj`** cumple criterios técnicos mínimos (**sin leer **`raw`** del usuario**).

## 3. Alcance

Solo **create**.

No altera:** update**, **delete**, **complete**, **query**, **fail**, **need_context** fuera del punto de llamada (**no** redefine flujos de contexto más allá del segundo GPT normalizado).

## 4. Readiness (réplica técnica)

- **Event/create completo**: título (**`cal_title`** o **`title`**), día civil válido (**`cal_date_iso`**, **`date_iso`** o **`dateISO`** mediante coerción existente), hora (**`cal_time_text`**, **`time_text`** o **`time`** no vacíos).
- **Task/create completo**: **`task_title`** o **`title`** no vacío.
- **Note/create completo**: misma viabilidad que **`_note_payload`** (contenido o título reusado como contenido).

**Pending** sin ascenso cuando **`GPT`** marcó ciclo aclaratorio (`pending.field` distinto de **ausente**/**vacío**/ **confirmation**/ **confirm**) o valores bloqueantes: **`target_selection`**, **`delete_confirmation`**, **`context`**.

## 5. Principio

Aris **no** interpreta el texto natural del usuario; solo revisa **`obj`** ya estructurado por GPT.

## 6. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```
