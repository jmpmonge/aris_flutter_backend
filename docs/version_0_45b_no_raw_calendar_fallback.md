# Versión 0.45b — Eliminación del fallback crudo en calendario

## Introducción

En **v0.45a** se documentó el flujo real del motor de calendario heredado de **v0.21**. En **v0.45b** se corrige un comportamiento inconsistente con ese motor: cuando la extracción estructurada fallaba o clasificaba `not_calendar`, el backend podía persistir el mensaje del usuario como título de evento mediante `stored_override` en texto plano y `events_store.add_event(str)`, generando eventos «pobres» que contradecían el modelo estructurado.

Este documento resume el cambio de comportamiento, las pruebas añadidas y las limitaciones vigentes.

## Marco normativo jerarquizado (referencia general)

La siguiente lista cumple la plantilla de referencia institucional aplicable a documentación técnica vinculada a tratamiento de información en entornos educativos o administrativos; **no sustituye** dictamen jurídico sobre el producto ARIS.

- **Normativa constitucional** (art. 18 CE y desarrollo — protección de datos y secreto de las comunicaciones, en la medida aplicable).
- **LOE / LOMLOE** — marco educativo general cuando el despliegue afecte a centros docentes.
- **RD básico** — desarrollo reglamentario del currículo que aplique al contexto de uso.
- **Decreto autonómico curricular** — desarrollo competencial autonómico correspondiente.
- **Decreto de convivencia** — cuando proceda según comunidad autónoma y tipo de centro.
- **Orden de evaluación / reclamación** — procedimiento académico-administrativo aplicable al uso institucional.
- **Ley 39/2015** — procedimiento administrativo común electrónico (referencia para trazabilidad y documentación).
- **Ley 40/2015** — régimen jurídico del sector público (referencia para organización y competencias formales).
- **Reglamento interno** — aplicación según el centro u organismo titular del despliegue (texto propio cuando exista).

## Naturaleza del cambio (técnico)

Actualización del **motor de decisiones del asistente** y refuerzo **defensivo** en la capa HTTP para que **no se persista un evento de calendario** cuando el único payload disponible sea la cadena bruta del usuario sin extracción estructurada válida.

## Competencia

Responsabilidad del equipo backend dentro del monorepo ARIS (Flutter no modificado en esta versión).

## Procedimiento adoptado en código

1. **`assistant_engine._process_calendar_with_extraction`**
   - Si `try_calendar_event_extraction` devuelve `None`: sin `stored_override`; si el texto parece intención de calendario, se abre `pending_action` mínima (`calendar_event_completion`); si no, respuesta de aclaración con `intent_type` coherente (`consulta` / `ambiguo` según heurísticas).
   - Si `intent == "not_calendar"`: mensaje prudente de aclaración, `intent_type` `ambiguo`, sin persistir evento ni texto crudo como override estructurado.
   - Se mantienen las ramas de guardado directo cuando `_calendar_direct_save_ok` y las de `pending` con `_pending_calendar_payload` cuando hay datos útiles pero insuficientes.

2. **`main.message`**
   - Guard **defensivo**: si `intent_type == "calendario"` y el payload efectivo es `str`, **no** se llama a `events_store.add_event`; se registra advertencia en log.

## Análisis del defecto anterior

El defecto combinaba:

- Tupla de retorno `(..., "calendario", raw, None)` en ramas de fallo de extracción.
- En `main.py`, uso de `stored_override if not None else body.text`, lo que terminaba en `add_event(str)` y un objeto evento con `title` igual al mensaje completo.

## Calificación técnica

**Bug de persistencia inconsistente con el contrato v0.21** (modelo estructurado vs. texto libre).

## Propuesta de seguimiento (no inspectoría)

- Mantener smoke `scripts/smoke_v045b_no_raw_calendar_fallback.py` en CI o ejecución manual previa a releases.
- Futura evolución: datetime real / ISO (fuera del alcance de v0.45b).

## Pruebas añadidas

- `scripts/smoke_v045b_no_raw_calendar_fallback.py` (sin `OPENAI_API_KEY` obligatoria; mocks y stores temporales).
- Integración en `scripts/smoke_all.py`.

## Limitaciones

- **No se introduce datetime real** ni resolución de zona horaria completa en esta versión.
- No se borran eventos ya guardados en ficheros existentes del usuario.
- No hay base de datos ni calendario externo.

## Conclusión

**v0.45b** alinea la persistencia de eventos con la regla: **solo payload `dict` estructurado** tras extracción válida (o completación vía pending); **nunca** el texto bruto como único contenido persistido como evento nuevo cuando falla GPT o declara `not_calendar`.

---

Ver también: [`backend_calendar_no_raw_fallback_v0_45b.md`](backend_calendar_no_raw_fallback_v0_45b.md).
