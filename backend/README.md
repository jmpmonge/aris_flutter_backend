# Backend mínimo v0.47

**Estado actual:**

**v0.47.15** — Borrado de eventos: **`ready`** + **`event`** + **`delete`** con **`target`** validado (`delete_event`), confirmación vía GPT (`pending`: **`delete_confirmation`**); véase [`docs/version_0_47_15_event_delete_confirmation.md`](../docs/version_0_47_15_event_delete_confirmation.md).

**Previo:**

**v0.47.14** — Smokes locales [`scripts/smoke_backend_minimal_v047.py`](../scripts/smoke_backend_minimal_v047.py) (sin OpenAI real) integrados en **`smoke_all`** (este corre solo ese smoke por defecto; `RUN_LEGACY_SMOKES=1` activa scripts legacy opcionales).

**Previo:**

**v0.47.13** — Consultas de agenda vía **`need_context`** + **`context_response`** (GPT **`answer`**) sin modificar **`events`**; fecha en resolver por **`date_text`** (**hoy**/**mañana**/días de la semana como texto guardado).

**v0.47.12** — **Update real** de eventos: **`ready`** + **`event`** + **`update`** + **`target`** (`get_event_by_id` / `update_event`), hilo con **`target`** en **`continue`**.

**v0.47.11** — Tras **`need_context`**, segunda llamada interna GPT con **`mode: context_response`**, **`context_resolver`** (calendario) y preservación de la petición raíz.

**v0.47.10** — Continuación de hilo (`mode=continue`) tras desambigüedad de hora (**a las 19** → **`ready`** + evento **`19:00`**, sin re-preguntar ni **¿19 o 20?**).

**v0.47.9** — `POST /message` validado ante hora coloquial ambigua (7:00 ↔ 19:00 vía GPT/prompt/normalización).

**v0.47.8** — `POST /message` conectado.

**Incluye:**

- `GET /health`;
- `GET /events`;
- `GET /tasks`;
- `GET /notes`;
- `POST /message`;
- `ArisMinimalEngine`;
- cliente GPT mínimo;
- payload mínimo;
- stores JSON.

**Todavía no incluye:**

- **delete** u otras acciones GPT más allá de **create**/ **update-event** donde aplique el motor actual;
- **update**/ **delete**/ **resolver de contexto** equivalente para **tareas**/ **notas**;
- integración Flutter revisada;
- calendario externo real;
- envío real de correo.

El backend legacy está archivado en:

`backend_legacy_v046/`

La arquitectura se guía por:

`docs/architecture/backend_minimal_v047/`

**Principio rector:**

Aris no decide semánticamente.

Aris empaqueta, envía, recibe, valida técnicamente y ejecuta.

GPT interpreta y decide.
