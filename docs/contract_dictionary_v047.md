# Diccionario de contrato Aris v0.47

## 1. Principio

Aris no interpreta semánticamente.
GPT devuelve JSON estructurado.
Aris valida técnicamente y ejecuta.

## 2. Prefijos por dominio

| Prefijo | Dominio | Uso |
|---|---|---|
| cal_ | event/calendar | eventos, citas, reuniones, agenda |
| task_ | task | tareas, pendientes, acciones por hacer |
| note_ | note | notas, ideas, contenido guardado |
| mail_ | mail | reservado para correo |

## 3. Sufijos

| Sufijo | Significado |
|---|---|
| _text | texto natural o visible |
| _iso | fecha civil YYYY-MM-DD |
| _time_text | hora HH:MM |
| _tags | lista de etiquetas |
| _minutes | duración numérica en minutos |

## 4. Calendario / evento

Campos oficiales:

- cal_title
- cal_date_text
- cal_date_iso
- cal_time_text
- cal_people
- cal_location
- cal_description
- cal_duration_minutes

Significado:

cal_date_text y cal_time_text representan fecha/hora de agenda.

Ejemplo:

```json
{
  "cal_title": "cita con el médico",
  "cal_date_text": "lunes",
  "cal_date_iso": "2026-05-18",
  "cal_time_text": "10:00"
}
```

## 5. Tareas

Campos oficiales:

- task_title
- task_description
- task_due_date_text
- task_due_date_iso
- task_due_time_text
- task_priority
- task_tags

Significado:

task_due_date_text y task_due_time_text representan vencimiento, límite o momento previsto de realización de una tarea.

Una tarea con fecha/hora sigue siendo task, no event.

Ejemplo:

```json
{
  "task_title": "ir al banco",
  "task_due_date_text": "lunes",
  "task_due_date_iso": "2026-05-18",
  "task_due_time_text": "10:00",
  "task_priority": "normal",
  "task_tags": ["Banco"]
}
```

## 6. Notas

Campos oficiales:

- note_title
- note_content
- note_tags

Ejemplo:

```json
{
  "note_title": "Idea Aris",
  "note_content": "Separar tareas y eventos con prefijos.",
  "note_tags": ["Aris"]
}
```

## 7. Compatibilidad temporal

Durante v0.47, engine acepta alias antiguos:

Eventos:

- title → cal_title
- date/date_text → cal_date_text
- date_iso/dateISO → cal_date_iso
- time/time_text → cal_time_text
- people/participants → cal_people

Tareas:

- title → task_title
- description → task_description
- date/date_text → task_due_date_text
- date_iso/dateISO → task_due_date_iso
- time/time_text → task_due_time_text
- priority → task_priority
- tags → task_tags

Notas:

- title → note_title
- content → note_content
- tags → note_tags

## 8. Regla de dominio

El dominio se decide por i:

- i = event → usar cal_*
- i = task → usar task_*
- i = note → usar note_*

Aris no cambia un dominio por otro.
Si GPT devuelve i=task, Aris ejecuta task.
Si GPT devuelve i=event, Aris ejecuta event.

## 9. Regla clave

cal_time_text no es task_due_time_text.
task_due_time_text no es cal_time_text.
