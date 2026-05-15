# Backend mínimo v0.47

**Estado actual:**

**v0.47.4** — Stores JSON mínimos.

**Incluye:**

- `GET /health`;
- `GET /events`;
- `GET /tasks`;
- `GET /notes`;
- stores JSON simples;
- `thread_state_store`.

**Todavía no incluye:**

- `POST /message`;
- GPT;
- engine;
- `payload_builder`;
- acciones de creación desde mensaje.

El backend legacy está archivado en:

`backend_legacy_v046/`

La arquitectura se guía por:

`docs/architecture/backend_minimal_v047/`

**Principio rector:**

Aris no decide semánticamente.

Aris empaqueta, envía, recibe, valida técnicamente y ejecuta.

GPT interpreta y decide.
