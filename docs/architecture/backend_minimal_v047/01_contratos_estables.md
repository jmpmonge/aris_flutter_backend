# Contratos estables — backend mínimo v0.47

Documento de **contratos estables**: definen la frontera entre el orquestador (Aris) y el motor semántico (GPT), y entre el backend y el cliente HTTP. Cambiarlos implica decisión grande, migración y coordinación.

---

## 1. Principio

- Aris **no** rellena el significado del mensaje: solo **empaqueta**, **valida forma** y **aplica** efectos permitidos cuando GPT devuelve una respuesta conforme al contrato.
- GPT devuelve **JSON** interpretable por el backend según el contrato de salida.
- Los **stores** y los **endpoints mínimos** son parte del contrato estable de persistencia y superficie HTTP.

---

## 2. Contrato de entrada a GPT

Payload **mínimo** conceptual (los nombres de campo pueden mapearse a JSON anidado en implementación).

### Campos raíz

| Campo | Rol |
|-------|-----|
| `raw` | Texto del usuario en este turno |
| `tz` | Zona horaria del usuario |
| `locale` | Locale del usuario |
| `mode` | `new` \| `continue` |
| `thread` | Estado del hilo abierto o `null` |
| `rules` | Parámetros no semánticos de guía para GPT (política contextual serializada) |

### Primer turno (`mode: new`)

| Campo | Valor ejemplo / nota |
|-------|----------------------|
| `raw` | Mensaje del usuario |
| `tz` | `Europe/Madrid` |
| `locale` | `es-ES` |
| `mode` | `new` |
| `thread` | `null` |
| `rules` | Ver abajo |

**`rules` (ejemplo primer turno)**

- `hours`: franja orientativa `08:00`–`22:00`
- `ambiguous_hour`: `ask_closed_question`
- `hide_internal`: `true`

### Continuación (`mode: continue`)

| Campo | Valor ejemplo / nota |
|-------|----------------------|
| `raw` | Respuesta del usuario |
| `tz` | `Europe/Madrid` |
| `locale` | `es-ES` |
| `mode` | `continue` |
| `thread` | Objeto con al menos: `intent`, `object`, `last_question`, `pending` |
| `rules` | Ver abajo |

**`rules` (ejemplo continuación)**

- `ambiguous_hour`: `do_not_reopen_if_option_matches`
- `hide_internal`: `true`

La política detallada de redacción vive en `04_politica_contextual_para_gpt.md`; aquí solo se fija **qué campos existen** y **cuándo**.

---

## 3. Contrato de salida GPT (compacto)

Objeto JSON con campos **mínimos** propuestos (nombres cortos para especificación; la implementación puede usar alias siempre que exista mapeo estable).

| Campo | Significado |
|-------|-------------|
| `s` | Estado: `ready` \| `ask` \| `need_context` \| `answer` \| `fail` |
| `i` | Intención dominio: `event` \| `task` \| `note` \| `mail` \| `general` \| `unknown` |
| `a` | Acción: `create` \| `update` \| `delete` \| `query` \| `complete` \| `draft` \| `answer` \| `null` |
| `obj` | Objeto propuesto (campos según dominio; puede estar vacío si no aplica) |
| `target` | Referencia técnica al objeto en store (p. ej. `id`) cuando aplique |
| `q` | Texto de pregunta mostrable al usuario (nunca internals) |
| `r` | Texto de respuesta mostrable al usuario |
| `pending` | Datos para el hilo abierto que el usuario no ve tal cual |
| `ctx` | Petición de contexto mínimo cuando `s = need_context` |

**Semántica estable de `s`**

- `ready`: Aris puede ejecutar persistencia / efecto permitido tras validación técnica.
- `ask`: Aris muestra `q` (y opcionalmente `r`) y **guarda** hilo abierto.
- `need_context`: Aris obtiene contexto acotado según `ctx` y **reenvía** a GPT sin reinterpretar semántica del usuario.
- `answer`: Aris devuelve texto (`r` / `q` según convención implementada); sin guardar entidad nueva salvo contrato explícito futuro.
- `fail`: Aris muestra mensaje de reformulación y **limpia** hilo según política.

---

## 4. Contrato de hilo abierto

Persistencia local del **estado conversacional** entre turnos (no es interpretación semántica del backend).

| Campo | Rol |
|-------|-----|
| `open` | Booleano: hay hilo activo |
| `intent` | Dominio/concepto que GPT asignó en el último paso ejecutable |
| `object` | Snapshot parcial del objeto en construcción (según dominio) |
| `last_question` | Última pregunta mostrada al usuario |
| `pending` | Opciones, campos faltantes, ambigüedad, etc. (estructura acordada) |
| `updated_at` | Marca temporal ISO |

---

## 5. Contrato de stores

Esquema **lógico** de documentos JSON. Los nombres de fichero son implementación (p. ej. `events.json`).

### Eventos

- `id`
- `title`
- `date_text`
- `time_text`
- `participants`
- `location`
- `description`
- `duration_minutes`
- `created_at`
- `updated_at`

### Tareas

- `id`
- `title`
- `description`
- `date_text`
- `time_text`
- `priority`
- `completed`
- `created_at`
- `updated_at`

### Notas

- `id`
- `title`
- `content`
- `tags`
- `created_at`
- `updated_at`

---

## 6. Contrato de endpoints

### Endpoints mínimos (primer esqueleto)

- `GET /health`
- `POST /message`
- `GET /events`
- `GET /tasks`
- `GET /notes`

### Endpoints posteriores (no obligatorios en el primer esqueleto)

- `PATCH /events/{event_id}`
- `DELETE /events/{event_id}`
- `PATCH /tasks/{task_id}`
- `PATCH /tasks/{task_id}/complete`
- `DELETE /tasks/{task_id}`
- `PATCH /notes/{note_id}`
- `DELETE /notes/{note_id}`

---

## 7. Qué no debe cambiar sin decisión grande

- Separación **orquestador vs interpretación** (GPT decide significado).
- Existencia de **payload mínimo** con `raw`, `tz`, `locale`, `mode`, `thread`, `rules`.
- Estados de salida `s` y su mapa a **ejecutar / preguntar / pedir contexto / responder / fallar**.
- Contrato de **hilo abierto** como mecanismo de continuación sin que Aris “entienda” el texto libre.
- **Shape** de los documentos en stores (campos anteriores) y **endpoints mínimos** listados.

Cualquier cambio que mezcle política contextual en los contratos estables debe evitarse: la política va en documento y módulo **modificables** (`04_politica_contextual_para_gpt.md`, futuro `decision_prompt.py`).
