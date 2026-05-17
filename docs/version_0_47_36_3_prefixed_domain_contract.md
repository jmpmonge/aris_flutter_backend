# v0.47.36.3 — Contrato prefijado por dominio

## 1. Objetivo

Separar el contrato GPT por dominio para reducir confusión entre tareas, eventos y notas.

## 2. Prefijos

- cal_* para eventos/calendario.
- task_* para tareas.
- note_* para notas.

## 3. Sufijos

- _text
- _iso
- _time_text
- _tags
- _minutes

## 4. Compatibilidad

Engine acepta campos nuevos y alias antiguos.
Stores no se migran todavía.

## 5. Tareas con fecha/hora

task_due_date_text y task_due_time_text representan vencimiento o momento previsto de tarea.
No convierten una tarea en evento.

## 6. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```
