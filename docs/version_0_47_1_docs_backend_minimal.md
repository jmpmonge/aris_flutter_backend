# v0.47.1 — Documentación base del backend mínimo

## 1. Objetivo

Crear la base documental para **reconstruir por pasos** el backend mínimo de Aris, separando de forma explícita lo **estable** (contratos, configuración, arquitectura, endpoints y stores previstos) de lo **modificable** (política contextual y prompts para GPT).

## 2. Por qué se crea esta versión

El backend anterior acumuló **demasiada lógica legacy**. Antes de modificar código, se fija una separación clara: **Aris no decide semánticamente**; **GPT interpreta y decide**; Aris **empaqueta, envía, recibe, valida técnicamente y ejecuta**.

Referencia histórica de partida: versión **v0.46a** (commit documental indicado en planificación interna `6d32c43`). Los documentos v0.45/v0.46 permanecen como histórico; la línea **v0.47** define la reconstrucción limpia.

## 3. Archivos creados

- `docs/architecture/backend_minimal_v047/00_readme.md`
- `docs/architecture/backend_minimal_v047/01_contratos_estables.md`
- `docs/architecture/backend_minimal_v047/02_configuracion_estable.md`
- `docs/architecture/backend_minimal_v047/03_arquitectura_minima_estable.md`
- `docs/architecture/backend_minimal_v047/04_politica_contextual_para_gpt.md`
- `docs/architecture/backend_minimal_v047/05_plan_por_pasos.md`
- `docs/version_0_47_1_docs_backend_minimal.md` (este archivo)

## 4. Qué cambia

Solo **documentación**: nueva carpeta bajo `docs/architecture/backend_minimal_v047/` y este documento de versión.

## 5. Qué no cambia

- `backend/` (sin modificaciones en este hito).
- `aris_flutter_v0.22/` (sin modificaciones).
- `.env` (sin modificaciones).
- Endpoints y código existentes (sin modificaciones).
- Stores actuales y cualquier archivo Python del proyecto (sin modificaciones).

## 6. Decisión arquitectónica central

**Aris no decide semánticamente.** Aris **recibe** mensaje crudo, **comprueba** hilo abierto, **construye** payload mínimo, **envía** a GPT, **recibe** JSON, **valida** técnamente la forma y **ejecuta / pregunta / pide contexto / responde / falla** según el estado devuelto por GPT.

**GPT interpreta y decide.**

## 7. Prueba mínima

Comprobar que existen los documentos:

```bash
ls docs/architecture/backend_minimal_v047
```

Deben listarse al menos:

- `00_readme.md`
- `01_contratos_estables.md`
- `02_configuracion_estable.md`
- `03_arquitectura_minima_estable.md`
- `04_politica_contextual_para_gpt.md`
- `05_plan_por_pasos.md`

## 8. Commit sugerido

```bash
git add docs/architecture/backend_minimal_v047 docs/version_0_47_1_docs_backend_minimal.md
git commit -m "docs: define backend minimal architecture v0.47.1"
```

## 9. Tag sugerido

```bash
git tag v0.47.1-docs-backend-minimal
```

**Rama esperada en planificación:** `rebuild-backend-minimal-v047` (documentalmente alineada con este hito; la gestión de ramas es responsabilidad del repositorio).
