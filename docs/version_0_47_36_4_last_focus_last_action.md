# v0.47.36.4 — last_focus, last_action y confirmación por efecto real

## 1. Problema

GPT podía saltar de tarea a evento en continuaciones como «cambia el día» y podía afirmar «he cambiado la cita» sin que hubiese prueba técnica de ejecución.

## 2. Solución

Añadir:

- **last_focus**: último objeto tocado con persistencia OK.
- **last_action**: última acción realmente ejecutada (store OK).

Ambos campos solo se exponen en el payload en **mode=new** con hilo cerrado; en **mode=continue** se envían explícitamente como **null**.

## 3. Regla de seguridad

Aris no confirma mutaciones si el backend no ejecutó nada acorde en ese turno.

GPT propone. Aris ejecuta. El store confirma. Solo entonces se muestra éxito coherente con el efecto.

## 4. last_focus

Sirve para anáforas:

- «cámbiala»
- «ponla a las 10»
- «cambia el día»
- «márcala como hecha»

## 5. last_action

Sirve para preguntas:

- «qué has cambiado?»
- «qué cita has cambiado?»
- «qué tarea has modificado?»

## 6. Prohibición técnica (answer sin ejecución en el turno)

**s=answer** no debe afirmar una mutación nueva no ejecutada; hay filtro textual con excepción cuando la respuesta se apoya inequívocamente en **last_action** ejecutada (p. ej. cita actual con la misma hora o etiqueta técnica del resultado persistido).

## 7. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```
