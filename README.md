# Aris (monorepo Flutter + FastAPI)

Monorepo que agrupa el **cliente móvil Flutter** y el **backend FastAPI** de Aris. Ambos proyectos conviven en el mismo repositorio pero son **código independiente** (Dart y Python no se mezclan). La comunicación prevista es **HTTP**; en la versión actual **aún no hay integración en tiempo de ejecución** entre la app y la API.

## Qué es Aris

Aris es un asistente **mobile-first** con capacidades de agenda, tareas, notas e interacción conversacional. El **núcleo operativo e inteligente** (motor simbólico, pending actions, integración controlada con modelos de lenguaje) reside en **FastAPI**. Flutter actúa como **cliente visual** y, en esta fase de producto, **sigue utilizando datos mock locales** en pantallas y repositorios hasta completar la integración real contra la API.

## Contenido del repositorio

| Ruta | Rol |
|------|-----|
| **`aris_backend/`** | Aplicación **FastAPI**: endpoints REST, motor simbólico, cliente GPT/OpenAI, almacenes en memoria/disco según implementación, pending actions. Las **claves de OpenAI** deben configurarse solo en el entorno del backend (nunca en Flutter). |
| **`aris_flutter/`** (convención) / **`aris_flutter_v0.22/`** (carpeta en este checkout) | App **Flutter** (iOS/Android…). No duplica el motor simbólico ni llama a OpenAI directamente. |

> **Nota de estructura:** la arquitectura objetivo nombra la app `aris_flutter/`. En este repositorio la carpeta de la app puede aparecer como `aris_flutter_v0.22/` hasta un eventual alineado de nombres **sin mover** código en esta versión de documentación.

## Cómo arrancar Flutter

```bash
cd aris_flutter_v0.22
flutter pub get
flutter run
```

(Si tu copia de trabajo usa ya la carpeta `aris_flutter/`, sustituye el `cd` por esa ruta.)

## Cómo arrancar FastAPI

Desde el entorno Python del backend (entorno virtual recomendado), instala las dependencias según el proyecto (p. ej. `requirements.txt` cuando exista) y levanta la app, por ejemplo:

```bash
cd aris_backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Ajusta host/puerto según tu configuración. La documentación de endpoints vigente está en `docs/contrato_backend_actual.md`.

## Integración y estado actual

- **Contrato HTTP:** comunicación futura por HTTP/JSON (REST).
- **Estado v0.38:** Flutter **no** está cableado al backend; **no** se han añadido llamadas de red obligatorias en la UI.
- **Mocks:** la app mantiene **repositorios y mocks locales** mientras se ejecuta el plan de integración por versiones (ver `docs/plan_integracion_flutter_backend.md`).

## Documentación

| Documento | Descripción |
|-----------|-------------|
| `docs/arquitectura_general.md` | Visión, límites y principios entre cliente y servidor. |
| `docs/estructura_monorepo.md` | Árbol lógico y convenciones de carpetas. |
| `docs/contrato_backend_actual.md` | Endpoints actuales (método, ruta, uso, estado). |
| `docs/plan_integracion_flutter_backend.md` | Hitos por versión hasta despliegue local/dev. |
| `docs/reglas_monorepo.md` | Reglas de arquitectura (equivalente a reglas de editor si no hay `.cursor/rules/`). |
| `docs/version_0_38_harmonizacion_monorepo.md` | Notas de la versión v0.38. |
