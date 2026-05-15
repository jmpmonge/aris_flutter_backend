# v0.47.2 — Archivar backend legacy

## 1. Objetivo

Archivar el backend anterior para iniciar la reconstrucción limpia del backend mínimo.

## 2. Por qué se hace

El backend anterior acumuló demasiada lógica legacy:

- motores antiguos de calendario;
- pending_action histórico;
- lógica de foco;
- lógica local de clasificación;
- rutas de fallback;
- contratos mezclados.

Para evitar seguir parcheando, se archiva completo y se crea una carpeta `backend/` nueva desde cero.

## 3. Qué cambia

- `backend/` se mueve a `backend_legacy_v046/`.
- Se crea un nuevo `backend/` mínimo.
- `backend/` contiene solo `__init__.py` y `README.md`.

## 4. Qué no cambia

No cambia:

- `aris_flutter_v0.22/`
- `.env`
- `docs/architecture/backend_minimal_v047/`
- datos de frontend
- configuración global
- rama de trabajo

## 5. Archivos/carpetas afectados

- `backend_legacy_v046/`
- `backend/`
- `docs/version_0_47_2_archive_legacy_backend.md`

## 6. Estado funcional

Después de este paso, el backend nuevo todavía **no es funcional**.

No debe esperarse que uvicorn arranque todavía.

El backend funcional se creará en **v0.47.3**.

## 7. Prueba mínima

Comprobar:

```bash
ls backend
ls backend_legacy_v046
```

Resultado esperado:

**backend:**

- `__init__.py`
- `README.md`

**backend_legacy_v046:**

- contiene el backend antiguo completo.

## 8. Commit sugerido

```bash
git add backend backend_legacy_v046 docs/version_0_47_2_archive_legacy_backend.md
git commit -m "chore: archive legacy backend v0.47.2"
```

## 9. Tag sugerido

```bash
git tag v0.47.2-archive-legacy-backend
```
