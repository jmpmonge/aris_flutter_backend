# v0.47.36.1 — Estado recuperable de operaciones incompletas

## 1. Objetivo

Evitar que una operación incompleta se pierda cuando todavía no se ha ejecutado, cancelado o sustituido por otra intención clara.

## 2. Principio

Aris no decide semánticamente. Aris solo conserva estado técnico de una operación incompleta para que GPT pueda continuarla.

## 3. Cambios

- `task`/ `update` con **target válido** y **`obj`** sin patches persistibles: **no** se cierra el hilo duro; se pregunta por el valor faltante (**Aris**) y se deja **`open` = true**.
- **`ready`/task/update sin target**: si **`obj`** trae algo persistible u hint estructural, se abre el hilo con **`pending.field` = missing_target**.
- Persistencia opcional **`last_recoverable`**: ante cierres vía **`answer`**/**fail** cuando había **`task`/update incompleta**, u operaciones **`update`** no ejecutadas con motivo recuperable (**tarea no encontrada**, errores de store).
- **`build_payload`** añade **`recent`** sólo cuando **no** hay **`thread`** activo (**mode = `new`**) y existe **`last_recoverable`**.
- **`mode = continue`** y **`thread`** incluyen **`action`** persistida.

## 4. Ejemplo

Usuario:

> cambia la descripción de la tarea del banco

Aris/GPT (contrato esperado):

> ¿Qué descripción quieres ponerle a la tarea «llamar al banco»?

Usuario:

> preguntar por los seguros vinculados

→ Aris actualiza **`description`** tras **`ready`/task/update** con **`target`** válido.

## 5. Fuera de alcance

- Semántica local sobre el texto del usuario.
- Parser local.
- Cambios Flutter.
- Mail.
- Notas avanzadas.

## 6. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```
