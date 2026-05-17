# v0.47.36.2 — Desactivar recent oculto

## 1. Problema

El campo recent contaminaba turnos nuevos. Una petición nueva como "crea una tarea..." se interpretaba como continuación de un update anterior.

## 2. Decisión

Eliminar recent del payload a GPT.

Solo hay:

- open=true → continue;
- open=false → new limpio.

## 3. Conservado

Se conserva la mejora de task/update incompleto:

- update con target pero obj vacío mantiene hilo abierto y pregunta por el valor.

## 4. Eliminado

- recent en payload.
- sección recent en prompt.
- last_recoverable como contexto oculto para GPT.

## 5. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Prueba real:

"crea una tarea para ir al banco el lunes"

debe crear tarea, no intentar update.
