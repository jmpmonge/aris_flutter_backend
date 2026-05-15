# Arquitectura general — Aris (monorepo)

## Visión

Aris separa claramente **presentación móvil** (Flutter) de **lógica de negocio, razonamiento simbólico e integración con modelos de lenguaje** (FastAPI). El backend es la **única** pieza que debe conocer detalles del motor simbólico, pending actions y políticas de llamada a GPT/OpenAI.

## Límites entre proyectos

| Capa | Tecnología | Responsabilidad |
|------|------------|-----------------|
| Cliente | Flutter (Dart) | UI/UX mobile-first, navegación, estado de pantalla, llamadas HTTP a la API cuando exista integración. |
| Servidor | FastAPI (Python) | Endpoints REST, motor simbólico, almacenes, pending actions, uso controlado de GPT, persistencia de datos del asistente. |

**Reglas estrictas:**

- Flutter **no** importa ni ejecuta Python.
- El backend **no** importa ni ejecuta Dart.
- Flutter **no** debe llamar a la API de OpenAI ni almacenar allí claves secretas; las claves permanecen en el **entorno del backend**.
- Flutter **no** debe reimplementar el motor simbólico: cualquier interpretación “inteligente” de mensajes de usuario para crear tareas, notas o eventos debe provenir del backend.

## Comunicación

- **Actual (v0.38):** ningún flujo de producto en Flutter depende aún del backend; los mocks locales siguen siendo la fuente de datos de la app.
- **Objetivo:** cliente ↔ servidor mediante **HTTP** (JSON), con contrato documentado en `contrato_backend_actual.md` y evolución por fases en `plan_integracion_flutter_backend.md`.

## Datos y mocks

Mientras dure la transición, la app puede conservar **repositorios con implementaciones mock**. La regla de diseño es: **no mezclar** llamadas reales al backend con mocks en la misma capa sin pasar por una abstracción de repositorio y una decisión explícita de “origen de datos” (ver `docs/reglas_monorepo.md`).

## Seguridad y configuración

- Variables sensibles (OpenAI, etc.) solo en archivos ignorados por git en el backend (p. ej. `.env` en la raíz del repo o bajo `aris_backend/`, según despliegue).
- No exponer secretos en el cliente móvil ni en repositorios públicos.
