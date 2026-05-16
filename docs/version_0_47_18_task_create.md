# v0.47.18 — Creación básica de tareas

## 1. Objetivo

Validar la creación básica de tareas cuando GPT devuelve `s=ready`, `i=task`, `a=create`.

## 2. Principio rector

Aris no decide semánticamente. GPT interpreta y decide. Aris valida técnicamente y ejecuta.

## 3. Estado previo detectado

El backend ya incluía soporte para **task/create** en `_handle_ready_create()` / `_task_payload()` y **`TasksStore.add_task()`**. Esta versión refuerza el **decision prompt**, añade **smokes** y **documentación**; no fue necesario cambiar `engine.py` ni `tasks_store.py` para el comportamiento descrito.

## 4. Cambios realizados

| Archivo | Cambio |
|---------|--------|
| `backend/core/decision_prompt.py` | Sección **CREACIÓN DE TAREAS** con ejemplos y reglas; sin alterar la regla crítica de eventos con hora ambigua. |
| `scripts/smoke_backend_minimal_v047.py` | `smoke_9_task_create_basic()`: tarea con fecha, sin fecha, y rechazo sin título. |
| `backend/core/engine.py` | Sin cambios (ya cumplía task/create). |
| `backend/storage/tasks_store.py` | Sin cambios (ya cumplía `add_task`). |

## 5. Comportamiento soportado

Ejemplo de salida GPT:

```json
{
  "s": "ready",
  "i": "task",
  "a": "create",
  "obj": {
    "title": "comprar leche",
    "date": "mañana"
  }
}
```

Resultado técnico:

- se crea una tarea;
- la fecha textual queda en `date_text`;
- `completed` queda en `false`;
- no se crea evento ni nota desde este flujo;
- el backend no interpreta semánticamente fechas u horas.

## 6. Fuera de alcance

- update / delete / consulta de tareas;
- completar tareas;
- recordatorios reales;
- notificaciones;
- selección de candidatos de tareas;
- normalización semántica de fechas;
- conversión tarea ↔ evento.

## 7. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Resultado esperado: `smoke_backend_minimal_v047: ALL OK`.
