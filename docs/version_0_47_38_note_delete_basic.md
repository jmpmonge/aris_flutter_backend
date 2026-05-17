# v0.47.38 — Borrado básico de notas

## 1. Objetivo

Permitir `note/delete` con confirmación obligatoria antes de ejecutar el borrado.

## 2. Seguridad

No se borra ninguna nota sin confirmación explícita del usuario. Si GPT devuelve `ready/note/delete` directamente sin que haya un hilo de confirmación abierto, el motor abre la confirmación en lugar de borrar.

## 3. Flujo

```
Usuario: "borra la nota de Aris"
         ↓
GPT → ask/note/delete (pending.field = delete_confirmation, target = id)
         ↓
Aris guarda hilo abierto, muestra pregunta de confirmación
         ↓
Usuario: "sí"
         ↓
GPT → ready/note/delete (target = id)
         ↓
Aris verifica hilo con delete_confirmation para ese target
  Confirmado → delete_note → last_action delete → cierra hilo
  Sin confirmación → pregunta de nuevo (guard adicional del engine)
```

## 4. Comportamiento en casos límite

| Caso | Resultado |
|---|---|
| `ask/delete` con confirmación | Abre hilo, nota intacta |
| `ready/delete` tras confirmación | Borra nota |
| `ready/delete` sin confirmación previa | Pide confirmación (guard engine) |
| Target inexistente | "No encuentro esa nota en tu lista." |
| Usuario cancela | "De acuerdo, no borro la nota." |
| Varias candidatas | Abre `target_selection` |

## 5. Archivos modificados

| Archivo | Cambio |
|---|---|
| `backend/storage/notes_store.py` | `delete_note` ahora devuelve snapshot `dict \| None` (antes devolvía `bool`) |
| `backend/core/engine.py` | Handler `_handle_ready_delete_note` con guard de confirmación; rama `note/delete` en `_handle_ready` |
| `backend/core/decision_prompt.py` | Nueva sección "BORRADO SEGURO DE NOTAS (v0.47.38)" con contrato, reglas y continuaciones de confirmación y `target_selection` |
| `scripts/smoke_backend_minimal_v047.py` | `smoke_36_note_delete_basic()` (casos A–F) |

## 6. Fuera de alcance

- No se implementa papelera ni restauración de notas.
- No se permite borrado múltiple.
- Flutter no tocado.
- mail fuera de alcance.

## 7. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

36 smokes deben pasar (smoke 36 cubre los casos A–F de esta versión).
