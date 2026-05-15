# v0.47.4 — Stores JSON mínimos

## 1. Objetivo

Crear almacenamiento local simple para eventos, tareas, notas e hilo abierto.

## 2. Qué cambia

- Se crea `json_store.py`.
- Se crean `EventsStore`, `TasksStore`, `NotesStore` y `ThreadStateStore`.
- Se añaden endpoints `GET /events`, `GET /tasks` y `GET /notes`.

## 3. Qué no cambia

No cambia:

- `backend_legacy_v046/`
- `aris_flutter_v0.22/`
- `.env`
- GPT
- engine
- `POST /message`
- política contextual

## 4. Archivos tocados

- `backend/storage/json_store.py`
- `backend/storage/events_store.py`
- `backend/storage/tasks_store.py`
- `backend/storage/notes_store.py`
- `backend/storage/thread_state_store.py`
- `backend/main.py`
- `backend/README.md`
- `docs/version_0_47_4_json_stores.md`

## 5. Estado funcional

El backend nuevo debe arrancar y responder:

- `GET /health`
- `GET /events`
- `GET /tasks`
- `GET /notes`

## 6. Prueba mínima

Arranque:

```bash
python3 -m uvicorn backend.main:app --reload
```

Pruebas:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/events
curl http://127.0.0.1:8000/tasks
curl http://127.0.0.1:8000/notes
```

Resultado esperado:

- `/health` devuelve `status` ok.
- `/events` devuelve `[]` si no hay datos.
- `/tasks` devuelve `[]` si no hay datos.
- `/notes` devuelve `[]` si no hay datos.

## 7. Commit sugerido

```bash
git add backend docs/version_0_47_4_json_stores.md
git commit -m "feat: add minimal JSON stores v0.47.4"
```

## 8. Tag sugerido

```bash
git tag v0.47.4-json-stores
```
