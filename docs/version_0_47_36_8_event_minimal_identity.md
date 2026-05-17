# v0.47.36.8 — Ficha mínima útil de evento

## 1. Problema

Se podían crear citas con fecha y hora pero sin identidad suficiente (por ejemplo “cita” el jueves a las 20, sin persona, asunto, lugar ni descripción).

## 2. Solución

`event`/`create` requiere identidad mínima:

- `cal_people` no vacío; o
- `cal_location`; o
- `cal_description`; o
- `cal_title` útil.

## 3. Título genérico

No basta con títulos como:

- “cita”
- “evento”
- “reunión”
- “evento para el jueves”

si no hay persona, lugar o descripción que aporte contexto.

## 4. Continuación

Si falta identidad, Aris pregunta: **¿Con quién o sobre qué es la cita?**

La réplica puede completar el hilo abierto y crear el evento.

## 5. Principio

GPT interpreta. Aris valida solo la ficha estructurada recibida (calidad técnica, sin parsing del `raw`).

## 6. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```
