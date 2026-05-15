# v0.47.8 — Conectar POST /message

## 1. Objetivo

Conectar el endpoint `POST /message` al engine mínimo.

## 2. Qué cambia

- Se crea o actualiza `backend/models/schemas.py`.
- Se actualiza `backend/main.py`.
- Se instancia `ArisMinimalEngine`.
- Se conecta `POST /message`.
- `/health` pasa a **v0.47.8**.

## 3. Qué no cambia

No cambia:

- `backend_legacy_v046/`
- `aris_flutter_v0.22/`
- `.env`
- política contextual en documentación
- lógica interna de stores
- implementación real de `need_context`
- update/delete complejos en el engine

## 4. Archivos tocados

- `backend/models/schemas.py`
- `backend/main.py`
- `backend/README.md`
- `docs/version_0_47_8_message_endpoint.md`

## 5. Estado funcional

El backend ya puede recibir mensajes por `POST /message`.

Si hay `OPENAI_API_KEY`, el engine podrá llamar a GPT.

Si no hay `OPENAI_API_KEY`, debe responder de forma controlada sin guardar nada.

## 6. Prueba mínima sin API key

Arranque:

```bash
python3 -m uvicorn backend.main:app --reload
```

Prueba:

```bash
curl -X POST http://127.0.0.1:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text":"hola"}'
```

Resultado esperado:

Respuesta controlada, sin error 500.

## 7. Prueba mínima de lectura

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/events
curl http://127.0.0.1:8000/tasks
curl http://127.0.0.1:8000/notes
```

## 8. Commit sugerido

```bash
git add backend/main.py backend/models/schemas.py backend/README.md docs/version_0_47_8_message_endpoint.md
git commit -m "feat: connect minimal message endpoint v0.47.8"
```

## 9. Tag sugerido

```bash
git tag v0.47.8-message-endpoint
```
