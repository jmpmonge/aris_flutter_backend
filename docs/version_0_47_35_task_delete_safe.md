# v0.47.35 — Borrado seguro de tareas

## 1. Objetivo

Permitir borrar tareas con confirmación obligatoria.

## 2. Diseño

GPT interpreta. Aris no borra sin `ready`/`task`/`delete` y `target` válido. Antes debe existir confirmación mediante `ask` con `pending.field` = `delete_confirmation`.

## 3. Flujo

- Usuario pide borrar.
- GPT pide contexto si hace falta.
- GPT pregunta confirmación.
- Usuario confirma.
- GPT devuelve `ready`/`task`/`delete`.
- Aris borra.

## 4. Seguridad

- No borrar sin confirmación.
- No elegir arbitrariamente entre candidatas.
- «sí», «no», «la segunda» no se guardan como notas/tareas.

## 5. Ajuste visual incluido

El icono ⚠ de prioridad alta se muestra en naranja compatible con claro/oscuro.

## 6. Fuera de alcance

- Modificar tareas.
- Borrar varias a la vez.
- Papelera/deshacer.
- Mail.
- Rediseño amplio de UI.

## 7. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Si se toca Flutter:

```bash
cd aris_flutter_v0.22
dart analyze
flutter run -d chrome
```
