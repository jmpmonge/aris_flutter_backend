# Backend — Prioridad de creación de calendario (v0.45c)

## Introducción

Describe la regla introducida en **v0.45c** para evitar que **`update_calendar_event`** se ejecute cuando el usuario está **creando** o **agendando** una cita/expresamente un evento nuevo. Relacionado con **v0.45a** (auditoría del motor) y **v0.45b** (no guardar raw como evento).

## Marco normativo jerarquizado (referencia)

- Normativa constitucional aplicable según tratamiento de datos.
- LOE / LOMLOE; RD básico; decreto autonómico curricular; decreto de convivencia si procede.
- Orden de evaluación/reclamación en uso institucional.
- Ley 39/2015; Ley 40/2015; reglamento interno cuando exista texto propio.

## Naturaleza jurídica del acto

Cambio de código en la capa de interpretación del asistente (sin acto administrativo autónomo).

## Competencia

`AssistantEngine` en `backend/core/assistant_engine.py`.

## Procedimiento

### Bug observado

Texto: *«quiero poner una cita mañana a las 7 con Luis»*  
Respuesta incorrecta: *«He actualizado el evento: …»* con mutación del evento previamente enfocado.

### Diferencia creación vs actualización

| Creación (v0.45c prioriza) | Actualización (debe seguir a update) |
|----------------------------|--------------------------------------|
| Verbos de alta: quiero poner/crear, pon una cita, agéndame, programa… | Verbos de cambio: cambia, modifica, actualiza, mueve, borra… |
| Sustantivo de cita/reunión/evento/agenda (tras normalizar) | «Añade a María **a la cita**» (extensión de existente) |
| | `ponle` + campo (p. ej. ubicación) sobre evento actual |

### Helper nuevo

**`_looks_like_calendar_create_request(raw) -> bool`**

- Comprueba sustantivo de calendario (`_CALENDAR_NOUNS` y listas alineadas con el motor existente).
- Acepta patrones además de `_looks_like_calendar_action` (p. ej. **«quiero poner una cita»**, donde *poner* no estaba en la lista corta de verbos + sustantivo).
- Excluye consultas de agenda (`qué tengo`, `a qué hora`, …), modificaciones explícitas y «añade … a la cita».

### Guards

1. **En `_process_fresh`**, tras `try_structured_user_intent`: si `operation == "update_calendar_event"` y `_looks_like_calendar_create_request(raw)`, se llama a **`_reroute_calendar_create_from_update`** (evita llegar al handler de update).

2. **En `_unified_handle_calendar_update`** (defensivo): misma condición al inicio.

### `_reroute_calendar_create_from_update`

- Fusiona `calendar_event` (si venía vacío o parcial) con `calendar_update.updates`.
- Construye un `unified` con `operation = "create_calendar_event"` y delega en **`_unified_handle_calendar_create`**.
- Si tras fusionar no hay campos útiles → **`_open_calendar_pending(raw)`**.
- **No** invoca `EventsStore.update_event` ni reenfoca el evento antiguo.

**Nota:** el motor solo **devuelve** el dict a guardar en creación; la persistencia con `add_event` sigue en `main.py` (igual que antes). Los smokes sobre el motor validan ausencia de `update_event` y payload estructurado, no el conteo de filas persistidas hasta integración con `main`.

## Análisis de defectos

El modelo unificado podía favorecer `update_calendar_event` cuando había **evento en foco** o candidatos, ignorando verbos claros de **nueva** cita en el mensaje actual.

## Calificación jurídica

No aplica; fallo **funcional**.

## Propuesta de actuación inspectora

N/A al código. En entornos con políticas de conservación de datos, documentar que la corrección mejora la **trazabilidad semántica** entre intención de alta y de edición.

## Pruebas añadidas

`scripts/smoke_v045c_create_not_update.py`:

- **A:** Evento existente + intent unificado erróneo `update` + texto de creación → **sin** `update_event`, evento antiguo intacto, respuesta **no** «He actualizado…», `stored` dict estructurado (motor).
- **B:** «pon una cita para el domingo» con el mismo error de modelo → **sin** `update_event`.
- **C:** «cambia la cita antigua a las 8» → **sí** actualiza hora; heurística de creación **no** bloquea.

## No se toca

- Flutter, endpoints, `data/events.json` del repo, login, base de datos, calendario externo.

## Limitación

**Datetime real** y normalización temporal completa siguen fuera de alcance.

## Conclusión

La regla fuerte **v0.45c** es: *intención explícita de crear cita/evento → nunca `update_calendar_event` en ese turno*; se reutiliza el flujo de creación o pending, alineado con el motor estructurado heredado de v0.21.
