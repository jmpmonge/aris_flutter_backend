# v0.47.6 — Cliente GPT mínimo

## 1. Objetivo

Crear la capa mínima que envía el payload a GPT y recupera una respuesta JSON.

## 2. Qué cambia

- Se crea `backend/core/decision_prompt.py`.
- Se crea `backend/core/openai_client.py`.
- Se define `MINIMAL_DECISION_SYSTEM_PROMPT`.
- Se implementa `ask_gpt(payload)`.
- Se implementa extracción robusta de JSON (`_extract_json_object`).

## 3. Qué no cambia

No cambia:

- `backend/main.py`
- `backend/storage/`
- `backend/models/`
- `backend_legacy_v046/`
- `aris_flutter_v0.22/`
- `.env`
- `POST /message`
- engine
- stores
- endpoints

## 4. Archivos tocados

- `backend/core/decision_prompt.py`
- `backend/core/openai_client.py`
- `docs/version_0_47_6_minimal_gpt_client.md`

## 5. Estado funcional

El backend no cambia externamente.

Todavía no hay engine.

Todavía no hay `POST /message`.

Todavía no se ejecutan acciones.

## 6. Prueba mínima

Prueba sin API key:

- `ask_gpt(payload)` devuelve `None` si `OPENAI_API_KEY` no existe.

Prueba local de extracción:

- `_extract_json_object` extrae JSON directo.
- `_extract_json_object` extrae JSON si viene texto alrededor.
- `_extract_json_object` devuelve `None` si no hay JSON válido.

Ejemplo:

```bash
cd /path/to/repo && python3 -c "
import os
os.environ.pop('OPENAI_API_KEY', None)
from backend.core.openai_client import ask_gpt, _extract_json_object
assert ask_gpt({'raw':'hola','tz':'Europe/Madrid','locale':'es-ES','mode':'new','thread':None,'rules':{}}) is None
assert _extract_json_object('{\"a\":1}') == {'a': 1}
assert _extract_json_object('Aquí va:\\n{\"b\":2}\\nfin') == {'b': 2}
assert _extract_json_object('no json') is None
print('OK')
"
```

## 7. Commit sugerido

```bash
git add backend/core/decision_prompt.py backend/core/openai_client.py docs/version_0_47_6_minimal_gpt_client.md
git commit -m "feat: add minimal GPT client v0.47.6"
```

## 8. Tag sugerido

```bash
git tag v0.47.6-minimal-gpt-client
```
