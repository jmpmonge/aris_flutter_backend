# Configuración estable — backend mínimo v0.47

Este documento define la **configuración estable prevista**: variables de entorno y valores por defecto que el motor usará para construir payloads y llamar al modelo. **No contiene lógica semántica** y **no decide acciones**.

---

## Variables previstas

| Variable | Propósito |
|----------|-----------|
| `OPENAI_API_KEY` | Autenticación con el proveedor del modelo |
| `OPENAI_MODEL` | Identificador del modelo de chat |
| `ARIS_TIMEZONE` | Zona horaria por defecto del usuario local |
| `ARIS_LOCALE` | Locale por defecto |
| `ARIS_DATA_DIR` | Directorio raíz de ficheros JSON de datos |
| `ARIS_ENGINE_VERSION` | Etiqueta de versión del motor (trazabilidad, logs) |

---

## Valores por defecto (documentales)

| Variable | Valor por defecto |
|----------|-------------------|
| `OPENAI_MODEL` | `gpt-4o-mini` |
| `ARIS_TIMEZONE` | `Europe/Madrid` |
| `ARIS_LOCALE` | `es-ES` |
| `ARIS_DATA_DIR` | `backend/data` |
| `ARIS_ENGINE_VERSION` | `minimal_v047` |

`OPENAI_API_KEY` no tiene valor por defecto en documentación: debe aportarse en despliegue.

---

## Aclaraciones v0.47.1

- **No se toca `.env`** en v0.47.1: este hito es solo documentación.
- La **lectura efectiva** de estas variables corresponde a una fase posterior (p. ej. `config.py`).
- La configuración **solo proporciona valores estables** al motor (timezone, locale, rutas, modelo).
- La configuración **no** clasifica intents, **no** elige operaciones y **no** sustituye a GPT.

---

## Relación con contratos

Los valores `ARIS_TIMEZONE` y `ARIS_LOCALE` alimentan los campos `tz` y `locale` del **contrato de entrada a GPT** salvo que en el futuro exista perfil de usuario real que los sobreescriba.
