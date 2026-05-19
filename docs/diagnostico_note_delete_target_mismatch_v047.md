# Diagnóstico — Desalineación target visible/target interno en note/delete

## 1. Caso real

Flujo observado:

1. Existían dos notas:
   - `a8852d00-...` — title: null, content: **"a las 20:00"**
   - `e32b471b-...` — title: **"reflexión sobre neurociencia"**, content: "reflexión sobre neurociencia"

2. Usuario: `"borra la noda de 20:00"`

3. GPT eligió **neurociencia** como target y respondió:
   `"¿Seguro que quieres borrar la nota «reflexión sobre neurociencia»?"`

4. Usuario corrigió: `"no, es otra nota, que se llama \"a las 20:00\""`

5. GPT actualizó el texto visible a:
   `"¿Confirmas que quieres borrar la nota «a las 20:00»?"`
   Pero **no actualizó `pending.target`** — siguió apuntando a `e32b471b-...`.

6. Usuario: `"si"`

7. GPT devolvió `ready/note/delete` con `target = e32b471b-...` (neurociencia).

8. Engine borró `e32b471b-...` (neurociencia) y devolvió GPT's `r`:
   `"He borrado la nota «a las 20:00»."` — respuesta visualmente incorrecta.

**Resultado**: se borró neurociencia; "a las 20:00" sobrevivió. La respuesta visible decía lo contrario.

---

## 2. Estado actual confirmado (datos reales)

### notes.json (post-fallo)

| id | title | content |
|---|---|---|
| `a8852d00-382f-4f47-866b-1595d79b454d` | null | "a las 20:00" |

### thread_state.json (post-fallo)

```json
{
  "open": false,
  "last_action": {
    "status": "executed",
    "domain": "note",
    "action": "delete",
    "id": "e32b471b-13dd-4cae-a0bb-6cf9de5ad086",
    "label": "reflexión sobre neurociencia",
    ...
  }
}
```

`last_action` confirma que el objeto realmente borrado fue `e32b471b-...` ("reflexión sobre neurociencia").

---

## 3. Flujo técnico note/delete actual

```
Usuario: "borra la noda de 20:00"
    ↓
GPT → ask/note/delete
    target       = e32b471b (neurociencia)
    pending.target = e32b471b
    q            = "¿Seguro...neurociencia?"
    ↓
engine._aplicar_resultado_gpt (s=ask)
    → tid = extract_event_target_id(result)
         1. result["target"] = e32b471b  ✓
    → thread_store.save_state({
         target  = e32b471b,
         pending = { field: "delete_confirmation", target: e32b471b }
      })
    ↓
Usuario: "no, es otra nota, que se llama «a las 20:00»"
    ↓
GPT (mode=continue)
    [AQUÍ OCURRE EL FALLO]
    Recibe thread.target = e32b471b, thread.pending.target = e32b471b.
    Interpreta "no, es otra" como corrección del texto visible.
    No hace need_context → no obtiene id de "a las 20:00".
    Devuelve ask/note/delete con:
        q              = "¿Confirmas borrar «a las 20:00»?"  (texto nuevo)
        target         = e32b471b  (MISMO — el único id que conoce)
        pending.target = e32b471b  (MISMO)
    ↓
engine._aplicar_resultado_gpt (s=ask)
    → tid = e32b471b  (igual que antes)
    → thread_store.save_state({
         target  = e32b471b,
         pending = { field: "delete_confirmation", target: e32b471b }
       })
    → q visible cambia, pero el target interno NO
    ↓
Usuario: "si"
    ↓
GPT (mode=continue) → ready/note/delete
    target = e32b471b  (sigue el mismo)
    r      = "He borrado la nota «a las 20:00»."  (texto actualizado → INCORRECTO)
    ↓
engine._handle_ready_delete_note
    tid = extract_event_target_id(result) = e32b471b
    snap = nota neurociencia  (existe)
    cur_state.pending.target = e32b471b == tid → confirmed = True
    delete_note(e32b471b) → OK, devuelve snapshot neurociencia
    _record_successful_delete(domain="note", snapshot=neurociencia_snapshot)
    _reply_del("He borrado la nota «reflexión sobre neurociencia».")
        → r_raw = "He borrado la nota «a las 20:00»."  (GPT's r tiene prioridad)
        → DEVUELVE: "He borrado la nota «a las 20:00»."  ← MIENTE
```

---

## 4. Punto donde se queda el target antiguo

**Archivo**: `backend/core/engine.py`  
**Función**: `_aplicar_resultado_gpt` (líneas ~618–627)

```python
self._thread_store.save_state({
    "open": True,
    "intent": result["i"],
    "action": result.get("a"),
    "object": obj_out,
    "last_question": result["q"],
    "pending": result["pending"],   # ← GPT's pending, con target viejo
    "target": tid,                   # ← extract_event_target_id(result), también viejo
})
```

`save_state` hace `base.update(state)` — el `pending` completo de GPT reemplaza el anterior. Si GPT no cambia `pending.target`, este conserva el id antiguo.

**Archivo**: `backend/core/payload_builder.py`  
**Función**: `extract_event_target_id`

```python
def extract_event_target_id(result):
    tid = normalize_target_id(result.get("target"))
    if tid:
        return tid
    pend = result.get("pending")
    if isinstance(pend, dict):
        return normalize_target_id(pend.get("target"))
    return None
```

Extrae de `result["target"]` o `result["pending"]["target"]` — ambos provenientes de GPT, ninguno validado contra el texto visible.

**Archivo**: `backend/core/engine.py`  
**Función**: `_handle_ready_delete_note` (línea ~900)

```python
return (_reply_del(default_msg), "nota", None, None)
```

`_reply_del` prefiere el `r` de GPT sobre `default_msg` calculado desde `removed.title`. Si GPT miente en `r`, el usuario ve la mentira.

---

## 5. Hipótesis principal

**B + D combinadas**:

> **B)** GPT no actualiza `pending.target` al cambiar la nota visible durante una corrección de objeto en `delete_confirmation`.  
> **D)** El engine usa `r` de GPT para responder, aunque el objeto realmente borrado sea otro.

Causa raíz: el prompt para `delete_confirmation note` (modo `continue`) **solo cubre dos casos** — confirmación y cancelación — pero **no contempla el caso de corrección de objeto** ("no, es otra nota"). GPT improvisa: actualiza el texto visible pero conserva el target anterior porque es el único id que tiene en el hilo.

---

## 6. Evidencias del código

1. **Prompt** (`decision_prompt.py`, línea 977–981): solo define `confirma` → ready y `cancela` → answer. **No hay regla para "corrige el objeto"**.

2. **`_aplicar_resultado_gpt`**: guarda `pending` directamente desde GPT sin validar coherencia entre `pending.target` y `q`/`r`.

3. **`_handle_ready_delete_note`**: el guard `confirmed` verifica `pend.target == tid` pero ambos vienen de la misma fuente (GPT), por lo que pasan aunque apunten al objeto equivocado.

4. **`_reply_del`**: prioriza `r_raw` de GPT sobre `default_msg` construido desde `removed`. Permite que la respuesta visible sea incorrecta.

5. **Sin cross-validation**: el engine no verifica que `removed["id"]` coincida con ningún label en `r` de GPT.

---

## 7. Riesgo

> Una confirmación visible puede no corresponder al objeto realmente borrado.  
> El usuario ve el nombre de una nota y piensa que la borró, pero en realidad se borró otra.

---

## 8. Recomendación futura — v0.47.38.1 (no implementar ahora)

**Propuesta: Confirmación segura de borrado con target coherente**

### Reglas de engine

1. **`_reply_del` no debe usar `r` de GPT**: calcular siempre la respuesta desde `removed` (el objeto real borrado), no desde el texto GPT. Desaparece el riesgo de respuesta engañosa.

2. **Cross-validation post-borrado** (opcional fuerte): si el label del `removed` no contiene ni está contenido en el label que aparecería en la respuesta visible, emitir advertencia técnica o usar `default_msg`.

### Reglas de prompt

3. **Añadir caso "corrección de objeto" en `delete_confirmation note`**: si el usuario dice "no, es otra", "me refiero a", "esa no es", GPT debe:
   - Invalidar el target anterior (no reutilizarlo).
   - Hacer `need_context` con el nuevo criterio para obtener el id correcto.
   - Solo entonces abrir nueva `delete_confirmation` con el nuevo target.

4. **Prohibir explícitamente reutilizar `pending.target` antiguo** cuando el usuario ha corregido el objeto durante una `delete_confirmation`.

### Código mínimo (no implementar ahora)

```python
# En _handle_ready_delete_note, sustituir _reply_del por cálculo real:
label_del = str(removed.get("title") or removed.get("content") or "").strip()[:40]
return (
    f"He borrado la nota «{label_del}»." if label_del else "He borrado la nota.",
    "nota",
    None,
    None,
)
```

---

## 9. Git — sin cambios

```
On branch rebuild-backend-minimal-v047
modified: aris_flutter_v0.22 (no tocar)
untracked: docs/diagnostico_grafo_logica_actual_v047.md
untracked: docs/diagnostico_note_delete_target_mismatch_v047.md (este documento)
```

Ningún archivo fuente modificado en este diagnóstico.
