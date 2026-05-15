# v0.47.5 — Payload builder mínimo

## 1. Objetivo

Crear el constructor del payload mínimo que Aris enviará a GPT.

## 2. Qué cambia

- Se crea `backend/core/payload_builder.py`.
- Se implementa `build_payload`.
- Se implementa `sanitize_visible_text`.
- Se implementa `normalize_gpt_response`.

## 3. Qué no cambia

No cambia:

- `backend_legacy_v046/`
- `aris_flutter_v0.22/`
- `.env`
- GPT
- engine
- `POST /message`
- stores
- endpoints

## 4. Archivos tocados

- `backend/core/payload_builder.py`
- `docs/version_0_47_5_payload_builder.md`

## 5. Estado funcional

El backend no cambia su comportamiento externo.

No hay llamada GPT todavía.

## 6. Prueba mínima

Desde Python, comprobar:

- `build_payload("hola", None)` devuelve `mode = "new"`.
- `build_payload("a las 19", {"open": True, ...})` devuelve `mode = "continue"`.
- `normalize_gpt_response(None)` devuelve `s = "fail"`.
- `sanitize_visible_text` no deja IDs ni nombres técnicos visibles.

Ejemplo:

```bash
cd /path/to/repo && python3 -c "
from backend.core.payload_builder import build_payload, normalize_gpt_response, sanitize_visible_text
assert build_payload('hola', None)['mode'] == 'new'
assert build_payload('a las 19', {'open': True, 'intent': 'event'})['mode'] == 'continue'
assert normalize_gpt_response(None)['s'] == 'fail'
t = sanitize_visible_text('Ver pending id=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
assert 'pending' not in t.lower()
assert 'bbbb' not in t
print('OK')
"
```

## 7. Commit sugerido

```bash
git add backend/core/payload_builder.py docs/version_0_47_5_payload_builder.md
git commit -m "feat: add minimal payload builder v0.47.5"
```

## 8. Tag sugerido

```bash
git tag v0.47.5-payload-builder
```
