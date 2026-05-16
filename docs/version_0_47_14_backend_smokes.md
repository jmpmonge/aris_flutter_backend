# v0.47.14 — Smokes de regresión del backend mínimo

## 1. Objetivo

Crear pruebas smoke para proteger los flujos básicos del backend mínimo.

## 2. Qué cambia

- Se crea [`scripts/smoke_backend_minimal_v047.py`](../scripts/smoke_backend_minimal_v047.py).
- Se crea o actualiza [`scripts/smoke_all.py`](../scripts/smoke_all.py): invoca el smoke del backend mínimo (por defecto solo ese; `RUN_LEGACY_SMOKES=1` añade scripts antiguos opcionales si siguen presentes en el repo).
- Se documentan los flujos protegidos (este documento).

## 3. Qué no cambia

No cambia:

- Flutter.
- `.env`.
- `backend_legacy_v046`.
- endpoints.
- contratos estables.
- stores.
- lógica funcional nueva.

## 4. Flujos protegidos

- hora ambigua;
- continuación;
- need_context + context_response;
- update de evento;
- consulta de eventos.

Comprobaciones encajadas con el principio rector (Aris empaqueta/ejecuta; GPT decide): sin UUID en texto visible donde aplica; hilos abiertos/cerrados según el flujo; consultas sin mutar `events`; tras `create`, el evento persistido no lleva `raw_text` como objeto de dominio.

## 5. Prueba mínima

Ejecutar:

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Resultado esperado:

```text
smoke_backend_minimal_v047: ALL OK
```

Suite agregadora (mínimo backend v0.47):

```bash
python3 scripts/smoke_all.py
```

## 6. Commit sugerido

```bash
git add scripts/smoke_backend_minimal_v047.py scripts/smoke_all.py docs/version_0_47_14_backend_smokes.md
git commit -m "test: add backend minimal smoke tests v0.47.14"
```

*(Opcionalmente incluir otros ficheros tocados en el mismo hito, por ejemplo `backend/main.py` / `backend/README.md` si se actualiza la etiqueta de versión en documentación visible.)*

## 7. Tag sugerido

```bash
git tag v0.47.14-backend-smokes
```
