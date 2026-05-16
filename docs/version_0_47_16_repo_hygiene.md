# v0.47.16 — Higiene Git y datos locales

## 1. Objetivo

Evitar que los datos locales generados por el backend mínimo entren accidentalmente en Git.

## 2. Qué cambia

- Se añade `backend/data/.gitignore`.
- Se ignoran los JSON locales generados en ejecución.
- Se deja preparada la carpeta `backend/data/` para datos locales sin contaminar commits.

## 3. Qué no cambia

No cambia:

- backend funcional;
- engine;
- stores;
- prompt;
- endpoints;
- Flutter;
- `.env`;
- backend legacy.

## 4. Datos ignorados

Los siguientes archivos son datos locales de ejecución y no deben versionarse:

- `backend/data/events.json`
- `backend/data/tasks.json`
- `backend/data/notes.json`
- `backend/data/thread_state.json`

## 5. Motivo

Durante las pruebas manuales y smokes, el backend puede generar archivos JSON locales.

Estos archivos sirven para ejecución local, pero no deben formar parte del repositorio porque pueden contener datos temporales o estados de prueba.

## 6. Prueba mínima

Ejecutar:

```bash
python3 scripts/smoke_backend_minimal_v047.py
git status