# v0.47.14 — Smokes de regresión del backend mínimo

## 1. Objetivo

Añadir **pruebas smoke** automatizadas (sin OpenAI real) para proteger los flujos **v0.47.9**–**v0.47.13** del backend mínimo frente a regresiones futuras.

## 2. Qué cambia

- Se crea [`scripts/smoke_backend_minimal_v047.py`](../scripts/smoke_backend_minimal_v047.py): **monkeypatch** de **`backend.core.engine.ask_gpt`**, stores bajo **`tempfile.TemporaryDirectory`**, cinco escenarios encadenados (hora ambigua, continuación **`create`**, **`need_context` + `context_response`** con **`update`**, **`update` real**, consulta **`query` + `answer`**).
- Se actualiza [`scripts/smoke_all.py`](../scripts/smoke_all.py): por defecto solo ejecuta el smoke **v0.47**; los smokes más antiguos se pueden activar con `RUN_LEGACY_SMOKES=1` (suelen romper contra el árbol mínimo si importan módulos eliminados).

## 3. Qué no cambia

No cambia:

- Flutter.
- `.env`.
- `backend_legacy_v046`.
- Endpoints REST.
- Contratos JSON externos estables como familia **`raw`**/**`mode`**/**`thread`**.
- Lógica de negocio nueva en engine/stores más allá de lo ya existente (**este hito sólo suma tests**).

## 4. Flujos cubiertos

| Área | Comportamiento comprobado |
|------|---------------------------|
| v0.47.9 | **`ask`** hora ambigua, sin evento nuevo, **`pending.options`** |
| v0.47.10 | **`ready`/`create`** tras «a las 19», **`time_text`** y cierre de hilo |
| v0.47.11–12 | **`need_context`→`context_response`→ask `update`** sin persistir hasta **`ready`/`update`** |
| Consulta | **`need_context`/`query`** + **`answer`** sin mutar **`events`** |

Comprobaciones transversales: **no UUID** en texto visible en los pasos marcados; no duplicación de evento en **`update`**; hilo **`open`**/**cerrado** según corresponda.

## 5. Prueba mínima

Desde la raíz del repositorio:

```bash
python3 scripts/smoke_backend_minimal_v047.py
```

Salida esperada final:

```text
smoke_backend_minimal_v047: ALL OK
```

Opcional: suite **`smoke_all`** (solo backend mínimo por defecto):

```bash
python3 scripts/smoke_all.py
```

Para incluir además los smokes legacy del repo:

```bash
RUN_LEGACY_SMOKES=1 python3 scripts/smoke_all.py
```

## 6. Commit sugerido

```bash
git add scripts/smoke_backend_minimal_v047.py scripts/smoke_all.py docs/version_0_47_14_backend_smokes.md backend/main.py backend/README.md
git commit -m "test: add backend minimal smoke tests v0.47.14"
```

## 7. Tag sugerido

```bash
git tag v0.47.14-backend-smokes
```
