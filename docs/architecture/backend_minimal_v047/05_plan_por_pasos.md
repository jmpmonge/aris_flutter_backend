# Plan por pasos — v0.47.x (reconstrucción backend mínimo)

Roadmap para reconstruir el backend por hitos. Cada hito posterior a v0.47.1 debe tener su **`docs/version_0_47_X_*.md`** asociado con: qué cambia, qué no cambia, archivos tocados, prueba mínima, commit sugerido y tag sugerido.

---

## v0.47.1 — Documentación base

- **Alcance:** solo documentación.
- **Código:** ninguno.

**Documento de versión:** `docs/version_0_47_1_docs_backend_minimal.md`

---

## v0.47.2 — Archivar backend actual

- Mover `backend/` a `backend_legacy_v046/`.
- No borrar nada.
- Carpeta nueva `backend/` solo con `__init__.py` y `README.md` hasta v0.47.3.

**Documento de versión:** `docs/version_0_47_2_archive_legacy_backend.md`

---

## v0.47.3 — Esqueleto backend nuevo

- Crear árbol vacío según `03_arquitectura_minima_estable.md`.
- `main.py` mínimo y `GET /health` únicamente.
- Sin integración GPT.

**Documento de versión:** `docs/version_0_47_3_backend_skeleton.md`

---

## v0.47.4 — Stores JSON

- Implementar persistencia: eventos, tareas, notas, `thread_state`.
- Endpoints `GET` de listado según contrato estable.

**Documento de versión:** `docs/version_0_47_4_json_stores.md`

---

## v0.47.5 — Payload builder

- Construir payload `new` / `continue` según `01_contratos_estables.md`.
- Sin llamada GPT.

**Documento de versión:** `docs/version_0_47_5_payload_builder.md` (sugerido)

---

## v0.47.6 — Cliente OpenAI

- `openai_client.py`: llamada al modelo y extracción de JSON.
- Sin ejecutar acciones de dominio.

**Documento de versión:** `docs/version_0_47_6_openai_client.md` (sugerido)

---

## v0.47.7 — Engine

- Orquestación mínima: cargar hilo, construir payload, llamar cliente, validar forma.

**Documento de versión:** `docs/version_0_47_7_engine.md` (sugerido)

---

## v0.47.8 — POST /message

- Conectar `POST /message` al engine.
- Persistir evento/tarea/nota cuando GPT devuelva `s = ready` y pase validación técnica.

**Documento de versión:** `docs/version_0_47_8_post_message.md` (sugerido)

---

## v0.47.9 — Validar hora ambigua

- Caso: «quiero poner una cita mañana a las 7 con Luis» → pregunta cerrada **7:00 / 19:00** (según política en `04_politica_contextual_para_gpt.md`).

**Documento de versión:** `docs/version_0_47_9_ambiguous_hour.md` (sugerido)

---

## v0.47.10 — Validar continuación

- Caso: tras opciones con **19:00**, usuario «a las 19» → evento guardado con **19:00**.

**Documento de versión:** `docs/version_0_47_10_continuation.md` (sugerido)

---

## Plantilla para cada `docs/version_0_47_X_*.md`

Cada documento de versión debe declarar explícitamente:

1. Qué cambia.
2. Qué no cambia.
3. Archivos tocados.
4. Prueba mínima.
5. Commit sugerido.
6. Tag sugerido.
