# Reglas del monorepo (Flutter + FastAPI)

> Equivalente funcional a una regla de editor en `.cursor/rules/`: en este repositorio **no** existe la carpeta `.cursor/rules/`, por lo que estas reglas viven aquí.

## Separación de proyectos

- **`aris_flutter`** (o la carpeta equivalente del cliente, p. ej. `aris_flutter_v0.22/`) y **`aris_backend`** son **proyectos distintos** dentro del mismo repositorio.
- **Flutter no importa Python.** El código Dart no debe referenciar módulos, rutas ni ejecutables del backend salvo como documentación en comentarios.
- **El backend no importa Dart.** No generar ni parsear código Flutter desde Python.

## Comunicación

- La integración entre app y API será por **HTTP** (JSON).
- **FastAPI** concentra el **motor simbólico**, **pending actions** y **GPT/OpenAI** (u otros proveedores) con políticas definidas en servidor.

## Cliente móvil

- **Flutter no llama a OpenAI** ni incluye claves de API de modelos de lenguaje.
- **No duplicar el motor simbólico en Flutter.** La interpretación de intenciones y efectos sobre tareas/notas/eventos debe obtenerse del backend (p. ej. vía `POST /message` y endpoints de lectura/escritura).

## Datos y mocks

- **No mezclar mocks con el backend real** sin pasar por **repositories** (o abstracción equivalente): una implementación mock y otra HTTP deben ser intercambiables sin ensuciar la UI.

## Referencias

- Visión global: `arquitectura_general.md`
- Endpoints vigentes: `contrato_backend_actual.md`
- Hitos: `plan_integracion_flutter_backend.md`
