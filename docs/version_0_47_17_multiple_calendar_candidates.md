# v0.47.17 — Resolución segura de varios candidatos en calendario

## 1. Objetivo

Evitar que el sistema modifique, borre o consulte arbitrariamente un evento cuando hay varios candidatos posibles.

## 2. Qué cambia

- Se refuerza `decision_prompt.py` para varios candidatos (`context_response` y **continue** con **`target_selection`**).
- Se conserva `target` / `pending` / `candidates` en hilo abierto (`engine`: fusión técnica de **`original_obj`** cuando **`pending.field`** = **`target_selection`**).
- Se documenta en `payload_builder.py` que **`mode=continue`** expone **`thread.target`**.
- Se ajustan labels, orden estable por id, deduplicación y tope de candidatos en `context_resolver.py`.
- Se añaden smokes de varios candidatos en `scripts/smoke_backend_minimal_v047.py`.

## 3. Qué no cambia

No cambia:

- Flutter.
- `.env`.
- `backend_legacy_v046`.
- contratos estables del payload base.
- delete sin confirmación (sigue el flujo definido en v0.47.15).
- tareas/notas/mail.

## 4. Principio rector

Aris no decide semánticamente.
Aris no elige candidato.
GPT pregunta y decide con la respuesta del usuario.

## 5. Flujo esperado

Usuario:

«cambia la cita con Luis a las 8»

Si hay varios eventos con Luis:

GPT pregunta (sin IDs en texto visible), p. ej.:

«Tengo varias citas con Luis. ¿Cuál quieres modificar: la de mañana a las 10:00 o la del viernes a las 19:00?»

Usuario:

«la del viernes»

GPT fija **target** y continúa el flujo (p. ej. desambigüedad de hora 8 → 08:00/20:00).

## 6. Prueba mínima

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

## 7. Commit sugerido

```bash
git add backend/core/decision_prompt.py backend/core/engine.py backend/core/payload_builder.py backend/core/context_resolver.py scripts/smoke_backend_minimal_v047.py docs/version_0_47_17_multiple_calendar_candidates.md
git commit -m "feat: handle multiple calendar candidates safely v0.47.17"
```

## 8. Tag sugerido

```bash
git tag v0.47.17-multiple-calendar-candidates
```
