# v0.41 — Lecturas desde Flutter hacia backend (GET lista)

## Alcance

- La app Flutter (**`aris_flutter_v0_22`**) consume **`GET /history`**, **`GET /tasks`**, **`GET /notes`** y **`GET /events`** cuando el servidor FastAPI local responde.
- **No** se modificó el backend ni los endpoints; **no** se conectan **`PATCH`**, **`DELETE`**, ni completar tareas contra red.
- **OpenAI**, motor simbólico y lógica de asistente siguen **solo en servidor**; desde Flutter solo se realizan estas lecturas y el **`POST /message`** heredado de v0.40.
- **Mocks y servicios locales** (`ChatService`, `TaskService`, `NoteService`, `CalendarService`, `LocalActionService`, clasificadores) se **mantienen** como fallback o demo cuando la red falla o las listas no aplican.

## Pantallas y datos

| Pantalla        | Lista / comportamiento                                                         |
|----------------|---------------------------------------------------------------------------------|
| Inicio · Reciente | `HybridHistoryRepository.conversationForHome()` — servidor + cola local desde ancla |
| Resumen «Hoy»  | Highlights vía repos híbridos (tareas, notas, eventos)                         |
| Tareas          | Listas HOY / PRÓXIMAS desde `GET /tasks` si OK                                 |
| Notas           | «Recientes» desde `GET /notes` si OK                                           |
| Calendario      | Vistas Día/Semana/Mes desde datos del repo (con fallback local si aplica)      |
| Ajustes         | Texto discreto del origen de las cuatro lecturas (`backendReadsCaption`)       |

Prefetch tras el primer frame (`Repositories.prefetchBackendReads()` desde el shell) dispara los cuatro GET en paralelo y actualiza la leyenda de Ajustes.

## Fallback

- Historial remoto KO → conversación igual que antes con **`ChatService`**.
- Tareas/notas KO → mismos mocks que antes vía **`TaskService`** / **`NoteService`**.
- Calendario: si falta día con datos suficientes, el repositorio híbrido puede seguir usando **`CalendarService`** para mantener vistas simuladas.

## Siguiente paso sugerido (v0.42+)

- Sincronizar mutaciones (**`PATCH`/completar/borrar**) con backoff y revisión optimista desde repositorios, sin exponer secretos ni OpenAI en Flutter.
