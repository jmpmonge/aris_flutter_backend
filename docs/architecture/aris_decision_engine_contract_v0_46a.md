# Contrato maestro — Motor de decisión Aris (v0.46a)

Este documento fija la lógica **definitiva de referencia**: qué decide GPT, qué hace Aris, y qué comportamientos están **prohibidos**. Las implementaciones concretas del backend pueden evolucionar siempre que respeten este contrato.

---

## 1. Principio general

- **Aris** es **orquestador**, **almacén** y **ejecutor** técnico: recibe texto, monta contexto, llama a GPT, interpreta JSON, escribe en ficheros locales y responde al cliente.
- **GPT** es el **intérprete semántico** y **decisor principal** de significado del mensaje actual (intención, slots, ambigüedades, siguiente paso).
- **Aris no persiste entidades nuevas** (evento/tarea/nota) si GPT no ha devuelto una decisión ejecutable conforme al esquema (equivalente a `status` listo para acción **y** datos mínimos verificados).
- **Aris no actualiza** entidades si no hay **target** identificable (`entity_id` o desambiguación previa cerrada por GPT).
- **Aris no borra** entidades ni ejecuta efectos irreversibles **sin confirmación explícita** encapsulada (p. ej. `needs_confirmation` en el JSON y flujo de pending).

La validación de Aris es **técnica y conservadora**:

- JSON parseable y campos permitidos.
- `operation` / `intent_type` válidos para el ejecutor actual.
- Coherencia con stores existentes.
- Sin `raw_text` completo como título/contenido final de una entidad estructurada.

---

## 2. Grafo general de decisión (textual)

```
Usuario
  ↓
Aris recibe raw_text
  ↓
Aris carga contexto:
    user_id · timezone · locale
    pending_action (si existe)
    foco operativo multi-entidad
    candidatos agenda / tareas / notas
    historial reciente (si aplica)
    políticas (ambiguidad horaria, máx. aclaraciones, …)
  ↓
Aris construye paquete JSON → envía a GPT (motor estructurado)
  ↓
GPT devuelve JSON único
  ↓
status (semántico; ver §4):
    ready          → ejecutar acción si datos mínimos OK
    needs_clarification → guardar pending + pregunta
    needs_confirmation  → guardar pending + texto de confirmación
    general_answer    → responder texto sin persistir entidad nueva
    failed             → reformulación; sin inventar datos
  ↓
Aris actualiza stores / pending / focus / agenda_context según reglas
  ↓
Respuesta HTTP al cliente (Flutter u otro)
```

---

## 3. Paquete de entrada recomendado (GPT)

```json
{
  "user": {
    "user_id": "local_default_user",
    "timezone": "Europe/Madrid",
    "locale": "es-ES"
  },
  "message": {
    "text_id": "uuid",
    "raw_text": "...",
    "created_at": "ISO"
  },
  "conversation_state": {
    "has_pending_action": false,
    "pending_action": null,
    "clarification_step": 0,
    "max_clarification_steps": 3,
    "focused_entity": null
  },
  "available_data": {
    "events": [],
    "tasks": [],
    "notes": [],
    "mails": []
  },
  "allowed_operations": [],
  "policy": {
    "working_hours": { "start": "08:00", "end": "22:00" },
    "ambiguous_hour_policy": "ask_if_multiple_plausible",
    "max_clarification_steps": 3
  }
}
```

En el backend actual, un subconjunto se envía como `mensaje_usuario`, `eventos_candidatos`, `evento_enfocado` y, desde v0.46a, `accion_pendiente_previa_v046a` si hay pending GPT.

---

## 4. JSON de salida obligatorio (evolución hacia GPT)

Esquema **objetivo** (mapeado hoy sobre `operation` + campos opcionales `status`, `ambiguities`, `assistant_reply`):

```json
{
  "status": "ready | needs_clarification | needs_confirmation | general_answer | failed",
  "intent_type": "calendar_event | task | note | mail | general_query | unknown",
  "operation": "create | update | delete | query | complete | cancel | clarify",
  "confidence": 0.0,
  "reason": "string",
  "data": {},
  "target": { "entity_type": null, "entity_id": null },
  "candidates": [],
  "missing_fields": [],
  "ambiguities": [],
  "question": null,
  "action": null,
  "assistant_reply": null
}
```

**Implementación v0.46a**: el ejecutor sigue usando el esquema `create_note | create_task | create_calendar_event | …`; el campo `status` opcional **reorienta** `operation` hacia `needs_clarification` o `general_query` en `openai_client._normalize_unified_intent`.

---

## 5. Tipos de intención

| intent_type        | Significado breve |
|--------------------|-------------------|
| `calendar_event`   | Alta, consulta o cambio de agenda local |
| `task`             | Tarea con título y metadatos opcionales |
| `note`             | Nota de texto |
| `mail`             | Borrador de correo (sin envío real hasta exista endpoint) |
| `general_query`    | Respuesta conversacional sin mutación de entidad |
| `unknown`          | No clasificable; pedir reformulación |

---

## 6. Operaciones permitidas (catálogo de producto)

| Operación (producto) | Rol |
|----------------------|-----|
| `create_event`       | Persistir evento estructurado |
| `update_event`       | Parche sobre evento con `id` claro |
| `delete_event`       | Solo con confirmación explícita |
| `query_events`       | Lectura / resumen |
| `create_task`        | Nueva tarea |
| `update_task`        | Parche tarea |
| `complete_task`      | Marcar hecha |
| `delete_task`        | Con confirmación |
| `create_note`        | Nueva nota |
| `update_note`        | Parche nota |
| `delete_note`        | Con confirmación |
| `draft_mail`         | Borrador |
| `general_answer`     | Texto sin persistir |
| `ask_clarification`  | Pending + pregunta |
| `ask_confirmation`   | Pending + confirmación |

El backend actual expresa muchas de estas como `operation` del motor unificado legacy (`create_calendar_event`, `update_calendar_event`, …).

---

## 7. Campos por tipo (referencia)

**Calendar**

```json
{
  "title": null,
  "date_text": null,
  "time_text": null,
  "start_datetime": null,
  "timezone": "Europe/Madrid",
  "participants": [],
  "location": null,
  "description": null,
  "duration_minutes": null
}
```

*(Hoy Aris usa `date_text` / `time_text` textuales; `start_datetime` real queda pendiente.)*

**Task**

```json
{
  "title": null,
  "description": null,
  "date_text": null,
  "time_text": null,
  "priority": null,
  "completed": false
}
```

**Note**

```json
{
  "title": null,
  "content": null,
  "tags": []
}
```

**Mail**

```json
{
  "to": [],
  "subject": null,
  "body": null,
  "draft_only": true,
  "send_now": false
}
```

---

## 8. Política de horas ambiguas

- Franja habitual de agenda: **08:00–22:00** (orientativa).
- Si el usuario dice **«a las 8»** sin «de la mañana/tarde», **am/pm** u horario 24 h inequívoco, son plausibles **08:00** y **20:00**.
- GPT debe devolver **`status: needs_clarification`**, **`ambiguities`** con `field: time_text`, `options: ["08:00","20:00"]` y **`question`** clara.
- Si el texto incluye «de la mañana», «de la tarde», «de la noche», o formato **20:00** / «8 de la tarde», GPT puede fijar hora sin ambigüedad.
- **Aris no elige por su cuenta** entre 08:00 y 20:00 sin señal explícita del usuario (ni heurísticas agresivas que sustituyan a GPT en v0.46a).

**Ejemplo (esperado de GPT)**

Entrada: *«quiero poner una cita mañana a las 8 con Luis»*

```json
{
  "operation": "needs_clarification",
  "status": "needs_clarification",
  "confidence": 0.85,
  "calendar_event": {
    "title": "cita con Luis",
    "date_text": "mañana",
    "time_text": "8",
    "participants": ["Luis"]
  },
  "ambiguities": [
    {
      "field": "time_text",
      "options": ["08:00", "20:00"],
      "reason": "La hora 8 puede ser mañana o tarde."
    }
  ],
  "clarification_question": "¿Te refieres a las 8:00 o a las 20:00?",
  "reason": "ambigüedad horaria"
}
```

---

## 9. Pending action

- Conserva interpretación **parcial** (slots detectados).
- El siguiente mensaje del usuario debe enviarse a GPT junto con el **compacto de pending** (`accion_pendiente_previa_v046a`).
- GPT decide si ya hay **ready** u otra ronda de aclaración.
- **`clarification_step`** incremental; por defecto máximo **3** pasos (`max_clarification_steps`).
- Tras agotarse, GPT/Aris deben cerrar con **opciones finitas** o pedir reformulación global (sin bucle abierto eterno).

Campos típicos en pending (v0.46a): `user_id`, `original_text_last`, `pending_kind`, `question`, `ambiguities`, `missing_fields`, `clarification_step`, `structured_*_hint`, `requires_explicit_confirmation`.

---

## 10. Reglas de creación

- Solo persistir evento si el flujo termina con **payload estructurado `dict`** coherente (título + reglas locales de fecha/hora ya existentes).
- No usar **`raw_text` completo** como único título almacenado.
- Tarea / nota análogas: **dict** o pending, nunca “todo el mensaje” como única dimensión semántica sin estructura.

---

## 11. Reglas de actualización

- Requiere **target** inequívoco (`entity_id` en candidatos o referencia resuelta).
- Varios candidatos igualmente plausibles → **`needs_clarification`** con lista, **sin** `update`.
- **Creación explícita** (verbos + sustantivo de cita/evento) **nunca** se convierte en `update` por el simple hecho del foco previo (v0.45c + este contrato).

---

## 12. Reglas de borrado

- **Nunca** `delete` directo en un solo turno ambiguo.
- GPT propone **`needs_confirmation`**; Aris guarda pending y espera confirmación explícita.

---

## 13. Prohibiciones absolutas

- **NUNCA** guardar `raw_text` como evento final.
- **NUNCA** guardar `raw_text` como tarea o nota final si GPT no devolvió acción ejecutable con estructura suficiente.
- **NUNCA** actualizar un evento si el mensaje es **creación explícita**.
- **NUNCA** inventar **viernes / 12:00** u otra fecha concreta sin datos del usuario.
- **NUNCA** colocar en un calendario **externo** real un evento que solo tenga `date_text`/`time_text` (el cliente no debe “inventar” instante absoluto).
- **NUNCA** perder `pending_action` al formular una pregunta (salvo transición explícita a otro pending o cancelación).
- **NUNCA** ejecutar **delete** sin confirmación explícita.

---

## 14. Ejemplos completos (resumen)

| Caso | status / operation esperado |
|------|-----------------------------|
| **A** Cita hora ambigua | `needs_clarification` + `ambiguities` hora |
| **B** Cita hora clara (`20:00`) | `ready` / `create_calendar_event` con dict |
| **C** Update varios candidatos | `needs_clarification` + candidatos en texto o `ambiguities` |
| **D** Update target claro | `update_calendar_event` con `target_event_id` |
| **E** Tarea | `create_task` con título |
| **F** Nota | `create_note` con contenido estructurado |
| **G** Mail | `draft_mail` o `general_query` hasta exista API |
| **H** Consulta general | `general_answer` / `general_query` + `assistant_reply` |

---

## Referencias cruzadas

- Alineación implementación actual: `aris_current_backend_alignment_v0_46a.md`
- Notas de versión: `docs/version_0_46a_decision_engine_contract.md`
