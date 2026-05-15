# Política contextual para GPT — parte modificable (v0.47)

Este documento define la **parte modificable** del sistema: guías para que **GPT** decida mejor. **No es una decisión de Aris.** Aris **no** usa estas reglas para clasificar o resolver significado por su cuenta; las **inyecta en el prompt** o las **serializa en `rules`** del payload cuando corresponda.

---

## 1. Principio

- La política contextual orienta al modelo sobre tono, formato de preguntas, horas ambiguas, continuación y recovery.
- Cambiar esta política **no debe obligar** a cambiar contratos estables (`01_contratos_estables.md`) ni la forma de los stores.
- Cualquier texto visible al usuario debe cumplir las reglas de **visibilidad** de la sección 4.

---

## 2. Hora ambigua

### “A las 7”

- Opciones plausibles en formato 24 h: **07:00** y **19:00**.
- GPT debe preguntar de forma **cerrada**:

  «¿Te refieres a las 7:00 o a las 19:00?»

### “A las 8”

- Opciones plausibles: **08:00** y **20:00**.
- GPT debe preguntar de forma **cerrada**:

  «¿Te refieres a las 8:00 o a las 20:00?»

La franja `hours` del payload (`08:00`–`22:00`) es orientativa para el razonamiento del modelo; **Aris no elige** la hora por significado.

---

## 3. Continuación

- Si `mode = continue`, GPT debe interpretar el mensaje como **respuesta al hilo abierto** (pregunta anterior, `pending`, etc.).
- Si `pending.options` incluye explícitamente **19:00** y el usuario dice «a las 19», GPT debe **cerrar** con **19:00** sin reabrir ambigüedad artificial.
- No debe preguntar en ese caso cosas como «¿19 o 20?» cuando la opción ya está acotada por el propio hilo.

La regla técnica en payload (`rules.ambiguous_hour = do_not_reopen_if_option_matches` en continuación) refuerza esta guía para el modelo.

---

## 4. Visibilidad

Los campos **`q`** y **`r`** (y cualquier texto mostrado al usuario) **nunca** deben incluir:

- IDs internos o UUIDs crudos.
- JSON completo de la respuesta del modelo.
- Nombres de estructuras: `pending`, `thread_state`, `policy`, `schema`, etc.
- Mensajes de depuración o trazas internas.

---

## 5. Need context

Si GPT no puede aplicar una acción porque **falta identificar** un objeto en el mundo del usuario, debe devolver:

- `s = need_context`
- `ctx`: petición **concreta** de lo que falta cargar.

**Ejemplo ilustrativo:**

```json
{
  "domain": "calendar",
  "query": "events_by_date",
  "filters": { "date": "lunes" }
}
```

Aris ejecutará esa petición de forma **mecánica** (consulta acotada al store), ampliará el payload y **reenviará** a GPT sin reinterpretar el texto libre del usuario.

---

## 6. Recovery

Si tras los intentos acordados el modelo considera que no puede avanzar de forma segura:

«No estoy captando toda la información necesaria. ¿Podrías escribirlo de nuevo de forma más concreta?»

Aris puede **limpiar el hilo** según el contrato de salida (`s = fail`) y política implementada.

---

## 7. Borrado y acciones destructivas

- Las acciones **destructivas** (borrado, vaciados irreversibles, etc.) requieren **confirmación explícita** en el flujo (`ask` / estado dedicado según implementación).
- Aris solo ejecuta borrado tras validación técnica **y** secuencia de confirmación conforme al contrato.

---

## 8. Qué puede cambiar en este documento

Sin tocar contratos estables se puede actualizar:

- Redacción de preguntas cerradas para otras horas coloquiales.
- Umbrales de recovery (cuántos `ask` antes de `fail`).
- Detalle de plantillas en `decision_prompt.py`.
- Contenido de `rules` serializado (siempre que el **shape** del payload en `01_contratos_estables.md` se mantenga).
