# Pendiente backend — compactación semántica de eventos para vista Semana

## Idea

Como cada evento ya se crea o interpreta con GPT, el backend podrá guardar también una representación compacta específica para la vista Semana.

No se calculará en tiempo de render.
Se calculará una sola vez al crear o actualizar el evento.

## Campos propuestos

- `icono_semana`
- `texto_semana`

## Objetivo

Permitir que la vista Semana muestre cada evento con una representación muy compacta, consistente y estable:
- icono + texto corto
- sin depender de lógica local compleja en frontend
- sin volver a consultar GPT al renderizar

## Ejemplo

```json
{
  "title": "Café con Laura",
  "icono_semana": "coffee",
  "texto_semana": "Café"
}