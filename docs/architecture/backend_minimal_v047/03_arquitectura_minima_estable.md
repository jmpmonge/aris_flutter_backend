# Arquitectura mínima estable — backend mínimo v0.47

Describe la **estructura prevista** del backend nuevo y las **responsabilidades** por módulo. Esta arquitectura debe permanecer estable cuando se mejore la “inteligencia” del sistema: los cambios frecuentes deben ir en la capa de **política/prompt**, no en contratos ni stores.

> **Nota v0.47.1:** esto es especificación; el árbol no se implementa en este hito.

---

## Estructura prevista

```
backend/
├── main.py
├── core/
│   ├── config.py
│   ├── contracts.py
│   ├── payload_builder.py
│   ├── openai_client.py
│   ├── engine.py
│   └── decision_prompt.py
├── models/
│   └── schemas.py
├── storage/
│   ├── json_store.py
│   ├── events_store.py
│   ├── tasks_store.py
│   ├── notes_store.py
│   └── thread_state_store.py
└── data/
```

---

## Responsabilidades

### `main.py`

- Expone endpoints HTTP.
- **No interpreta semánticamente** el cuerpo del mensaje.
- **No duplica** la lógica de guardado que corresponde al motor.
- Delega el flujo conversacional en `engine`.

### `engine.py`

- **Orquesta** el ciclo completo del mensaje.
- Carga y guarda **hilo abierto** (`thread_state`).
- Construye el payload vía `payload_builder`.
- Llama a GPT vía `openai_client`.
- **Valida técnicamente** la forma del JSON devuelto (campos obligatorios, enums permitidos, coherencia con stores).
- Ejecuta lecturas/escrituras en stores cuando `s = ready` y los guards lo permiten.
- Actualiza o limpia el hilo según `s`.

### `payload_builder.py`

- Construye el **payload mínimo** (`raw`, `tz`, `locale`, `mode`, `thread`, `rules`).
- Incorpora solo contexto adicional que el contrato permita (p. ej. resultado de `need_context`).
- **No decide semánticamente** qué significa el mensaje.

### `openai_client.py`

- Envía mensajes al modelo según configuración.
- Obtiene texto de respuesta y **extrae JSON** válido.
- **No ejecuta** acciones de dominio ni escribe en stores.

### `decision_prompt.py`

- Contiene la **política contextual modificable** (instrucciones de sistema / plantillas).
- Es el lugar previsto para cambios frecuentes de comportamiento del modelo **sin** alterar contratos estables.

### `contracts.py`

- Define constantes y tipos alineados con `01_contratos_estables.md` (en implementación futura).

### `config.py`

- Carga variables de entorno según `02_configuracion_estable.md`.

### `storage/`

- Persistencia JSON simple.
- **No interpreta semánticamente**; solo CRUD acotado.

### `models/schemas.py`

- Esquemas FastAPI/Pydantic para request/response HTTP y validación superficial de entrada.

---

## Regla central

**La arquitectura mínima estable no debe cambiar** cuando ajustemos la calidad de la decisión del modelo.

Si se mejora la decisión, se tocan principalmente **`decision_prompt.py`** y el documento **`04_politica_contextual_para_gpt.md`**, no los contratos ni la forma de los stores.
