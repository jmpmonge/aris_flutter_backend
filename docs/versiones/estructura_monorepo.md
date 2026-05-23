# Estructura del monorepo

## Árbol lógico (arquitectura objetivo)

```text
aris_flutter_backend/
├── aris_flutter/          # App móvil Flutter (convención de nombre)
├── aris_backend/          # API FastAPI, motor simbólico, GPT, stores
├── docs/                  # Documentación transversal
├── README.md
└── .gitignore
```

En checkout actuales, la carpeta de la app puede denominarse **`aris_flutter_v0.22/`** en lugar de `aris_flutter/`, por histórico de versionado, **sin implicar** un segundo producto: es el mismo rol (cliente Flutter).

## `aris_flutter/` (app móvil)

- Código Dart: pantallas, widgets, estado, **repositorios** (mock o futuro HTTP).
- `pubspec.yaml` y artefactos de construcción Flutter (`.dart_tool/`, `build/`, etc. — ignorados en git).
- **No** contiene motor simbólico Python ni credenciales de OpenAI.

## `aris_backend/` (FastAPI)

- `main.py`: definición de la app FastAPI y rutas HTTP actuales.
- Paquetes de dominio (p. ej. `core/`, `models/`, `storage/`): motor simbólico, modelo de mensajes, almacenes en memoria o disco, pending actions.
- Entorno Python (`.venv/`, `venv/`, etc.) ignorado; datos locales de desarrollo bajo políticas de `.gitignore`.

## Documentación (`docs/`)

Centraliza decisiones de arquitectura, contrato HTTP, plan de integración y notas de versión en **`docs/versiones/`**. Las versiones recientes del cliente Flutter (v0.49+) están en **`aris_flutter_v0.22/docs/versions/`**. Ver `docs/README.md`.

## Qué no implica esta estructura

- No hay un único “proyecto” de build: Flutter y Python se construyen y despliegan por separado.
- No se asume que el backend empaquete la app ni al revés.
