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
```

Resultado esperado:

- El smoke termina con `smoke_backend_minimal_v047: ALL OK`.
- Si se han generado `events.json`, `tasks.json`, `notes.json` o `thread_state.json` bajo `backend/data/`, **no deben aparecer** como ficheros nuevos rastreados por Git (`git status` debe mantenerlos ignorados).

## 7. Archivos preservados en el repo

En `backend/data/` siguen versionados **`backend/data/.gitignore`** y **`backend/data/.gitkeep`** (reglas `!.gitignore` y `!.gitkeep` en ese ignore), para que la carpeta exista en clones sin tener que crear JSON de ejemplo.

## 8. Commit de referencia (v0.47.16)

```bash
git add backend/data/.gitignore docs/version_0_47_16_repo_hygiene.md backend/data/.gitkeep
git commit -m "$(cat <<'EOF'
chore: ignore backend local data files v0.47.16
EOF
)"
```

## 9. Tag de referencia

```bash
git tag v0.47.16-repo-hygiene
```
