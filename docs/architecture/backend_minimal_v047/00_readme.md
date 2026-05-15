# Backend mínimo v0.47 — Índice (`00_readme`)

Esta carpeta recoge la **reconstrucción documental limpia** del backend mínimo de Aris en la línea **v0.47**. Parte de referencia histórica: **v0.45** y **v0.46** (p. ej. commit de partida `6d32c43` / contrato v0.46a) quedan como **histórico**; aquí se fija lo que debe ser estable al **reconstruir por pasos**.

## Regla principal

**Aris no decide** en el sentido semántico del producto.

- Aris **no interpreta** si un mensaje es nota, tarea, evento, correo o consulta.
- Aris **no elige** crear, modificar, consultar, borrar o preguntar por significado.
- Aris **no resuelve** ambigüedades por significado.

Aris solo: **recibe el mensaje crudo**, **comprueba si hay hilo abierto**, **construye un payload mínimo**, **añade solo el contexto necesario**, **envía el paquete a GPT**, **recibe una respuesta estructurada**, **valida técnicamente la forma** de esa respuesta y **ejecuta, pregunta o guarda hilo** según lo que GPT haya devuelto.

**GPT interpreta y decide.**

## Esquema rector

```
USUARIO
  ↓
Mensaje crudo
  ↓
ARIS
  - recibe raw_text
  - comprueba si hay hilo abierto
  - construye payload mínimo
  - añade solo el contexto necesario
  ↓
GPT
  - interpreta el mensaje
  - clasifica la intención
  - decide la acción
  - detecta ambigüedades
  - pide contexto si lo necesita
  - devuelve JSON estructurado
  ↓
ARIS
  - recibe JSON
  - valida técnicamente la forma
  - no reinterpreta semánticamente
  ↓
Según respuesta de GPT:
  - ready        → Aris ejecuta/guarda
  - ask          → Aris pregunta y guarda hilo abierto
  - need_context → Aris busca contexto mínimo y reenvía
  - answer       → Aris responde sin guardar
  - fail         → Aris pide reformulación y limpia hilo
```

Los códigos exactos de estado en el contrato compacto (`s`) están definidos en `01_contratos_estables.md`.

## Separación estable vs modificable

### Parte estable

- Contratos de entrada/salida y de hilo.
- Configuración (variables y valores por defecto documentados).
- Endpoints mínimos acordados.
- Stores y forma de persistencia acordada.
- Estructura base del árbol de módulos.
- Formato del payload y formato de salida GPT (campos obligatorios y semántica técnica de validación).

### Parte modificable

- Política contextual para GPT (guías de comportamiento).
- Prompt de decisión.
- Reglas de hora ambigua en redacción/prompt.
- Reglas de continuación del hilo.
- Reglas de recovery.
- Reglas de petición de contexto (`need_context`).

La política modificable está centralizada conceptualmente en `04_politica_contextual_para_gpt.md` (y en una futura implementación podrá vivir en `decision_prompt.py` sin alterar contratos ni stores).

## Documentos en esta carpeta

| Archivo | Contenido |
|---------|-----------|
| `01_contratos_estables.md` | Contratos que no deben moverse sin decisión grande |
| `02_configuracion_estable.md` | Variables de entorno y valores por defecto |
| `03_arquitectura_minima_estable.md` | Árbol de carpetas y responsabilidades |
| `04_politica_contextual_para_gpt.md` | Guías modificables para GPT |
| `05_plan_por_pasos.md` | Roadmap v0.47.x |

Versión índice del trabajo solo-docs: `docs/version_0_47_1_docs_backend_minimal.md`.
