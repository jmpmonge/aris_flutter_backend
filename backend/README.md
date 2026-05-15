# Backend mínimo v0.47

**Estado actual:**

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

- `need_context` real (solo marcador en engine);
- update/delete complejos;
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
