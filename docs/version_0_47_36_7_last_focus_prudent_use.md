# v0.47.36.7 — Uso prudente de last_focus

## 1. Problema

`last_focus` podía dominar una petición nueva clara. Ejemplo: «eventa para el jueves a las 20h con Pedro» se interpretaba como continuidad de una cita anterior.

## 2. Solución

`last_focus` es solo un referente posible.

Se usa directamente en anáforas:

- cámbiala
- ponla a las 10
- esa cita

No domina fichas nuevas claras:

- cita con Pedro el jueves a las 20
- evento para el jueves con Pedro
- reunión con Marco mañana

## 3. Pregunta de duda

Si hay duda entre foco anterior y ficha nueva, la pregunta debe mostrar ambas alternativas completas.

## 4. cal_title

El título debe ser limpio. Fecha y hora van en `cal_date_text` / `cal_time_text`; personas en `cal_people`.

## 5. Fuera de alcance

- parser local
- cálculo local de fecha
- cambios Flutter
- `recent`

## 6. Validación

```bash
python3 scripts/smoke_backend_minimal_v047.py
```
