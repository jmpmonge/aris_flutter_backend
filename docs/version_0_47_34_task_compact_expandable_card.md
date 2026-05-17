# v0.47.34 — Tarjeta de tarea compacta/desplegable

## 1. Objetivo

Unificar visualmente las tareas en una sola lista compacta con despliegue.

## 2. Diseño

- Una sola lista.
- Sin origen Aris/manual.
- Sin simulado.
- Compacto por defecto.
- Descripción y tags solo desplegados.
- Priority `normal` invisible.
- Priority `high` como ⚠.

## 3. Formato compacto

```
☐ título
   fecha · hora · ⚠
```

## 4. Formato desplegado

```
☐ título
   fecha · hora · ⚠

descripción

tags

acciones si existen
```

## 5. Fuera de alcance

- crear tarea manual (ya en v0.47.33);
- editar;
- borrar;
- filtros;
- mail;
- cambios GPT.

## 6. Validación

- `dart analyze`
- `flutter run -d chrome`
- prueba manual visual
