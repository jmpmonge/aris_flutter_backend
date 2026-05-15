# Versión v0.38 — Armonización del monorepo

Nota de versión centrada en **documentación y convenciones** del monorepo Aris (Flutter + FastAPI). **Sin cambios funcionales** en la app ni en la API, **sin conexión HTTP real** Flutter → FastAPI en esta entrega.

## Objetivo

Alinear la comprensión del proyecto con la arquitectura definitiva: **cliente Flutter** (mobile-first, mocks/repositorios) y **backend FastAPI** (endpoints, motor simbólico, GPT y almacenes), comunicación futura por **HTTP**, y secreto de claves **solo en backend**.

## Estructura final (documentada)

- **Raíz del repo:** documentación común (`docs/`), `README.md`, `.gitignore`.
- **`aris_backend/`:** API FastAPI y lógica de servidor (sin modificaciones en esta versión).
- **App Flutter:** en la arquitectura se denomina `aris_flutter/`; en este checkout la carpeta existente puede ser **`aris_flutter_v0.22/`** (mismo rol; sin renombrar carpetas en v0.38).

## Decisiones tomadas

- La fuente de verdad del **contrato HTTP** es el código actual de `aris_backend/main.py`, documentado en `docs/contrato_backend_actual.md`.
- La integración se abordará por **fases de versión** (v0.39–v0.44) en `docs/plan_integracion_flutter_backend.md`.
- Las reglas de separación Dart/Python y de no duplicar motor/OpenAI en Flutter quedan en `docs/reglas_monorepo.md` (no hay `.cursor/rules/` en el repo).

## Archivos creados o modificados

| Acción | Ruta |
|--------|------|
| Creado | `README.md` |
| Creado | `.gitignore` |
| Creado | `docs/arquitectura_general.md` |
| Creado | `docs/estructura_monorepo.md` |
| Creado | `docs/contrato_backend_actual.md` |
| Creado | `docs/plan_integracion_flutter_backend.md` |
| Creado | `docs/reglas_monorepo.md` |
| Creado | `docs/version_0_38_harmonizacion_monorepo.md` (este archivo) |

## Qué no se ha cambiado

- Código bajo `aris_flutter_v0.22/lib/` (salvo que no exista documentación interna adicional requerida).
- `aris_backend/core/`, `aris_backend/storage/`, `aris_backend/main.py` y **todos los endpoints** existentes.
- Pantallas, modelos y servicios mock de Flutter.
- Motor simbólico, diseño UI, mocks locales, ni nuevas dependencias externas.

## Riesgos pendientes

- **Nombre de carpeta Flutter:** divergencia entre `aris_flutter/` (documentado) y `aris_flutter_v0.22/` (real) puede confundir a nuevos colaboradores hasta alinearse.
- **Persistencia y despliegue:** pendiente de cierre en fases v0.43–v0.44; hasta entonces el contrato puede evolucionar con el producto.
- **Seguridad:** CORS abierto en desarrollo; revisar antes de producción.

## Siguiente paso recomendado

Implementar **v0.39**: primera integración mínima con **`GET /health`** desde Flutter (capa API/repositorio) para validar URL base y conectividad, sin sustituir aún los mocks del resto de funcionalidades.
