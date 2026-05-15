# Versión 0.46a — Contrato del motor de decisión (GPT-orquestado)

## Objetivo

Fijar **documentación maestra** y **alinear** el backend con el principio: **GPT decide semánticamente**; **Aris valida y ejecuta** sin persistir entidades crudas ni decisiones fuertes locales que contradigan al modelo cuando la API está disponible.

## Problema que resuelve

- Mezcla histórica de ramas legacy (keywords, payloads `str`, updates erróneos, foco excesivo).
- Falta de un **contrato** único compartido entre prompts, código y futuros clientes.

## Documentos creados

- `docs/architecture/aris_decision_engine_contract_v0_46a.md` — contrato maestro.
- `docs/architecture/aris_current_backend_alignment_v0_46a.md` — mapa del código vs contrato.

## Archivos tocados

- `backend/core/openai_client.py` — prompt unificado (`status`, `ambiguities`, reglas borrado/creación/hora); `_normalize_unified_intent`; `try_structured_user_intent(..., pending_context=...)`; compacto de pending.
- `backend/core/assistant_engine.py` — pending `gpt_needs_clarification`, pasos máximos, continuación sin borrar step; limpieza de pending antes de acciones; legacy keyword nota/tarea neutralizado; `assistant_reply` en `general`.
- `backend/main.py` — guards defensivos **nota/tarea** con `payload` `str` (v0.46a), además de calendario (v0.45b).
- `scripts/smoke_v046a_decision_engine_contract.py` — pruebas sin red (normalización + motor mockeado).
- `scripts/smoke_all.py` — registro del smoke.

## Cambios funcionales (resumen)

1. El motor unificado puede enviar **`status`** y **`ambiguities`**; se normalizan a `operation`/`needs_clarification` coherente.
2. **`needs_clarification`** del motor puede persistir pending **`gpt_needs_clarification`** con `clarification_step` y metadatos.
3. Si hay pending **`gpt_needs_clarification`**, el siguiente mensaje (con API key) llama a GPT **incluyendo** contexto previo compacto.
4. Antes de ejecutar operaciones mutadoras vía `_dispatch_unified_motor`, se **elimina** solo esa pending GPT (no se pierde cadena de pasos en rondas solo-clarificación).
5. Legacy **sin motor unificado** ya no devuelve intents nota/tarea que empujen a persistir texto crudo “provisional”.

## Reglas prohibidas (reafirmadas)

Ver §13 del contrato maestro; refuerzo en código: **no** `add_event`/`add_note`/`add_task` desde `str` en `POST /message` para intents estructurados.

## Pruebas

- `python3 scripts/smoke_v046a_decision_engine_contract.py`
- `python3 scripts/smoke_all.py`

## Pendiente explícito

- **`start_datetime`** real con timezone **Europe/Madrid** y contrato hacia API/Flutter.
- **Limpieza** de eventos pobres antiguos en datos locales (sin borrado automático en v0.46a).
- **Flutter** debe mostrar eventos solo textuales **sin** inventar fecha absoluta (documentado; código Flutter fuera de alcance salvo doc).
- **Multiusuario** real y login.
- **Correo**: sin envío real hasta endpoint; contrato reservado en doc maestro.

## Marco normativo (referencia administrativa genérica)

CE, LOE/LOMLOE, RD básico, decreto autonómico/convivencia si aplica, orden de evaluación/reclamación, Ley 39/2015, Ley 40/2015, reglamento interno del centro — **referencia de gobernanza documental**; el cambio es técnico.
