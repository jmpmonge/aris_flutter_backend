# Versión 0.45c — Prioridad creación frente a `update_calendar_event`

## Introducción

Tras **v0.45b** (sin persistir eventos desde texto bruto) quedaba otro fallo de enrutado: el motor unificado podía clasificar como **`update_calendar_event`** un mensaje que en realidad era **creación explícita** de cita (p. ej. con un `focused_event_id` antiguo). El usuario recibía «**He actualizado el evento…**» y se mutaba un evento existente, en contra de la intención expresada.

**v0.45c** fuerza la **redirección a creación** (flujo `create_calendar_event` o `pending`) cuando el texto muestra intención inequívoca de **nueva** cita o evento.

## Marco normativo jerarquizado (referencia general)

- Normativa constitucional (protección de datos y garantías aplicables al tratamiento de información).
- LOE / LOMLOE; RD básico; decreto autonómico curricular; decreto de convivencia cuando proceda.
- Orden de evaluación / reclamación en despliegues educativos formales.
- Ley 39/2015 y Ley 40/2015 (referencia documental y competencias en el ámbito público).
- Reglamento interno del centro u organismo titular.

*(La lista es plantilla de referencia institucional; el cambio técnico no constituye por sí un acto administrativo.)*

## Naturaleza jurídica del acto

Actualización de software (lógica del asistente backend), sin alterar contratos HTTP ni datos existentes en reposo salvo el comportamiento ante mensajes nuevos.

## Competencia

Backend `backend/core/assistant_engine.py` (sin cambios en Flutter ni en endpoints).

## Procedimiento (técnico)

1. **`_looks_like_calendar_create_request(raw)`** — Heurística nueva: combina sustantivos de calendario (`cita`, `reunión`, …) con verbos/frases de **creación** («quiero poner una cita», «pon una cita», «agéndame…», etc.) y excluye patrones de **modificación** («cambia la cita», «actualiza el evento», …), consultas («qué tengo mañana»), «añade a X a la cita» y `ponle …` (añadir campo a existente).

2. **`_process_fresh`** — Si `operation == "update_calendar_event"` y la heurística es positiva, **no** se despacha el update; se llama a **`_reroute_calendar_create_from_update`**.

3. **`_unified_handle_calendar_update`** — Mismo guard como red defensiva.

4. **`_reroute_calendar_create_from_update`** — Fusiona `calendar_event` y `calendar_update.updates` en un objeto de creación; si no hay datos útiles, **`_open_calendar_pending(raw)`** (sin guardar texto crudo como evento; el guard de v0.45b en `main` sigue aplicando a `str`).

## Análisis del defecto

Confusión entre **corrección/edición** de un evento focalizado y **alta** de una nueva cita cuando el mensaje llevaba verbos de agenda y datos completos.

## Calificación técnica

Error de **clasificación / prioridad de intención** en el motor unificado, mitigado de forma determinista en el backend.

## Propuesta de seguimiento

- Mantener `scripts/smoke_v045c_create_not_update.py` en `smoke_all`.
- Revisar en el futuro prompts del motor unificado solo si la heurística genera falsos positivos/negativos medibles.

## Pruebas

- `scripts/smoke_v045c_create_not_update.py` (motor mockeado: `update_calendar_event` + texto de creación → sin `update_event`; update real «cambia…» → sí actualiza).
- Inclusión en `scripts/smoke_all.py`.

## Alcance y límites

- **No** se modifica Flutter ni rutas HTTP.
- **No** se limpian ni migran eventos históricos en `data/`.
- **Datetime real / ISO** sigue pendiente (igual que en versiones previas).

## Conclusión

Un mensaje que **huele a nueva cita** ya no ejecuta **`update_calendar_event`** ni modifica el evento enfocado antes de tiempo; la respuesta tipo «He actualizado el evento» no debe producirse en esos casos.

Ver detalle técnico: [`backend_calendar_create_priority_v0_45c.md`](backend_calendar_create_priority_v0_45c.md).
