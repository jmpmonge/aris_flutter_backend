# Plan de integración Flutter ↔ FastAPI

Este plan **no** introduce cambios funcionales por sí mismo: ordena hitos de producto para conectar el cliente móvil con el backend por **HTTP**, respetando repositorios, motor simbólico solo en servidor y claves OpenAI solo en backend.

## Principios transversales

- Toda llamada HTTP debe pasar por una capa tipo **cliente API / repositorios**, no desde widgets directamente.
- Sustituir mocks por backend real **de forma explícita** (feature flags o implementación de repositorio), sin mezclar fuentes en la misma pantalla sin criterio.
- **No** añadir dependencias de OpenAI en Flutter; **no** duplicar el motor simbólico en Dart.

## Fases propuestas

### v0.39 — Conectar Flutter con `GET /health`

- Objetivo: validar conectividad y base URL configurable.
- Entregable típico: llamada de prueba desde capa API o pantalla de ajustes (según diseño ya existente).

### v0.40 — Conectar input de Home con `POST /message`

- Objetivo: enviar mensajes de usuario al asistente remoto y mostrar la respuesta del `AssistantResponse`.
- El procesamiento lingüístico y creación de entidades sigue ocurriendo **solo** en FastAPI.

### v0.41 — Cargar `history`, `tasks`, `notes`, `events` desde FastAPI

- Objetivo: lectura unificada de listas para alimentar las pantallas correspondientes.
- Mantiene mocks como respaldo o detrás de conmutador hasta estabilizar.

### v0.42 — Completar / eliminar / editar tareas y notas

- Objetivo: usar `PATCH` y `DELETE` de notas y tareas, y `PATCH .../complete` para tareas.
- Coherencia con el estado local y manejo de errores HTTP (404, 400).

### v0.43 — Decidir persistencia estable del backend

- Objetivo: cerrar estrategia de almacenamiento (SQLite, ficheros, otros) y copias de seguridad; fuera del alcance exacto de esta nota técnica.

### v0.44 — Preparar despliegue local / dev

- Objetivo: scripts o documentación de arranque coordinado (Flutter + API), variables de entorno, puertos y checklist de verificación (`/health` + flujo mínimo).

## Fuera de alcance inmediato

- Cambiar el diseño de pantallas Flutter existentes solo por integración (salvo lo indispensable).
- Modificar endpoints o el motor simbólico salvo correcciones acordadas en otra tarea.
