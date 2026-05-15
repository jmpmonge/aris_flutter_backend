# v0.47.3 — Esqueleto backend mínimo

## 1. Objetivo

Crear un backend nuevo mínimo con FastAPI y endpoint `/health`.

## 2. Qué cambia

- Se crea `backend/main.py`.
- Se crea estructura base `backend/core`, `backend/models`, `backend/storage`, `backend/data`.
- Se crea `backend/requirements.txt`.
- Se mantiene `backend_legacy_v046` sin tocar.

## 3. Qué no cambia

No cambia:

- `backend_legacy_v046/`
- `aris_flutter_v0.22/`
- `.env`
- `docs/architecture/backend_minimal_v047/`
- lógica GPT
- stores
- endpoints funcionales de datos

## 4. Archivos tocados

- `backend/main.py`
- `backend/requirements.txt`
- `backend/README.md`
- `backend/core/__init__.py`
- `backend/models/__init__.py`
- `backend/storage/__init__.py`
- `backend/data/.gitkeep`
- `docs/version_0_47_3_backend_skeleton.md`

## 5. Estado funcional

El backend nuevo ya debe arrancar con uvicorn.

Endpoint disponible:

`GET /health`

## 6. Prueba mínima

Comando:

```bash
python3 -m uvicorn backend.main:app --reload
```

Prueba:

```bash
curl http://127.0.0.1:8000/health
```

Resultado esperado:

```json
{
  "status": "ok",
  "backend": "minimal",
  "version": "v0.47.3"
}
```

## 7. Commit sugerido

```bash
git add backend docs/version_0_47_3_backend_skeleton.md
git commit -m "feat: create minimal backend skeleton v0.47.3"
```

## 8. Tag sugerido

```bash
git tag v0.47.3-backend-skeleton
```
