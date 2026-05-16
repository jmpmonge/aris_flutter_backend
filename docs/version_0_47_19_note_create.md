# v0.47.19 — Creación básica de notas

## 1. Objetivo

Validar la creación básica de notas cuando GPT devuelve `s=ready`, `i=note`, `a=create`.

## 2. Principio rector

Aris no decide semánticamente. GPT interpreta y decide. Aris valida técnicamente y ejecuta.

## 3. Estado previo detectado

El backend ya incluía la rama **note/create** en `_handle_ready_create()`, `_note_payload()` y **`NotesStore.add_note()`**. Esta versión refuerza el **prompt**, añade **smokes** y **documentación**; **no fue necesario** modificar `engine.py` ni `notes_store.py` para el comportamiento descrito.

## 4. Cambios realizados

| Archivo | Cambio |
|---------|--------|
| `backend/core/decision_prompt.py` | Reglas explícitas para **note/create**. |
| `scripts/smoke_backend_minimal_v047.py` | `smoke_10_note_create_basic()` (title+content; solo content; obj vacío). |
| `backend/core/engine.py` | Sin cambios. |
| `backend/storage/notes_store.py` | Sin cambios. |

## 5. Comportamiento soportado

Ejemplo GPT:

```json
{
  "s": "ready",
  "i": "note",
  "a": "create",
  "obj": {
    "title": "idea para Aris",
    "content": "separar tareas y notas"
  }
}
```

Resultado:

- se crea una nota con **content** (y **title** si aplica);
- no se crea evento ni tarea desde este flujo;
- el backend no clasifica ni normaliza semántica del texto más allá de campos admitidos por el store.

## 6. Fuera de alcance

- update / delete / consulta de notas;
- búsqueda semántica;
- tags automáticos complejos;
- recordatorios nativos;
- conversión nota ↔ tarea ↔ evento desde Aris.

## 7. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Salida esperada: `smoke_backend_minimal_v047: ALL OK`.
