# Acciones pendientes en Flutter (v0.44.1)

## Diferencia: evento provisional vs evento guardado

| Concepto | Comportamiento esperado |
|----------|-------------------------|
| **Provisional / pendiente** | La respuesta de Aris puede describir la cita, pero **`GET /events` aún no** incluye ese evento hasta que el backend lo materialice tras confirmación (o tras otra transición interna del motor). |
| **Guardado** | El evento aparece en **`GET /events`** y por tanto en **`CalendarScreen`** y resúmenes que lean el repositorio de calendario. |

Flutter **no** fabrica eventos locales a partir solo del texto provisional.

## Cómo se confirma (`confirm_rescue`)

1. La última respuesta del asistente trae **`ui_hint: "confirm_rescue"`**.
2. En **Inicio**, bajo la burbuja de Aris, se muestra la tarjeta con **Guardar** y **Cancelar**.
3. **Guardar** → `POST /message` con cuerpo `{"text": "sí"}`.
4. **Cancelar** → `POST /message` con `{"text": "no"}`.
5. Tras cualquier **`POST /message` exitoso**, la app refresca historia, tareas, notas y eventos; la nueva respuesta se añade al hilo como siempre.

## Cuándo se refresca `GET /events`

- Después de **cada** `POST /message` que termina bien (respuesta parseable con texto usable).
- Eso coincide con las demás lecturas en `prefetchBackendReads()`, para no diferir actualizaciones al cambiar de pestaña.

## Limitación si `ui_hint` es null

Si el backend solo devuelve texto tipo «evento provisional…» pero **`ui_hint` omitido**:

- Flutter muestra la nota *«Puede requerir confirmación.»* (solo si el texto contiene *provisional* o *provisoria*, para no hacer heurísticas frágiles).
- **No** se muestran botones Guardar/Cancelar, porque dependen explícitamente de `confirm_rescue`.

## Siguiente paso recomendado (contrato)

Para UX consistente, el backend debería enviar **`ui_hint`** en todas las respuestas donde exista una acción pendiente de confirmación, no solo en casos reconocibles por palabras en el texto.
