# v0.47.32 — Contrato limpio de ficha de tarea

## 1. Objetivo

Definir una ficha normalizada de tarea equivalente al contrato limpio de evento.

## 2. Diseño

GPT interpreta `raw` + `local_date` + `tz`.

GPT rellena una ficha.

Aris valida técnicamente y guarda.

Aris no decide prioridad, etiquetas, fecha ni hora.

## 3. Ficha

```json
{
  "title": "...",
  "description": "...",
  "date": "...",
  "date_iso": "YYYY-MM-DD",
  "time": "HH:MM",
  "priority": "normal|high",
  "tags": []
}
```

## 4. Prioridad

Solo valores internos:

- `normal`
- `high`

UI futura:

- `normal` no se muestra.
- `high` se muestra como icono ⚠.

## 5. Etiquetas

Temáticas, opcionales.

No se mostrarán en compacto; solo en desplegado.

## 6. Fuera de alcance

- borrar tareas;
- modificar tareas;
- crear manual desde Flutter;
- tarjeta visual;
- mail.

## 7. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```
