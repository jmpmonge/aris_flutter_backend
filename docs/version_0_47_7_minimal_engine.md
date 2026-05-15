# v0.47.7 — Engine mínimo

## 1. Objetivo

Crear el orquestador mínimo de Aris.

## 2. Qué cambia

- Se crea `backend/core/engine.py`.
- Se implementa `ArisMinimalEngine`.
- Se implementa `process_message`.
- Se integran `payload_builder`, `openai_client` y stores.
- Se gestionan estados `ready`, `ask`, `need_context`, `answer` y `fail`.

## 3. Qué no cambia

No cambia:

- `backend/main.py`
- `POST /message`
- Flutter
- `.env`
- `backend_legacy_v046`
- contratos estables en documentación
- forma de los stores y endpoints HTTP existentes

## 4. Archivos tocados

- `backend/core/engine.py`
- `docs/version_0_47_7_minimal_engine.md`

## 5. Estado funcional

El engine existe, pero todavía **no está conectado** a `main.py`.

No cambia el comportamiento externo del backend.

## 6. Prueba mínima

Pruebas recomendadas mediante mock de `ask_gpt`:

1. Si `ask_gpt` devuelve `ask`: se guarda hilo abierto; no se crea evento (comprobar `thread_store.is_open()` y lista de eventos vacía si no había datos).
2. Si `ask_gpt` devuelve `ready` / `event` / `create` con `obj` válido: se guarda evento y se limpia el hilo.
3. Si `ask_gpt` devuelve `fail`: se limpia el hilo y la respuesta es mensaje de reformulación.
4. Si `ask_gpt` devuelve `None`: no se guarda nada nuevo en stores ni en hilo (tras motor sin llamada).

Ejemplo con `unittest.mock.patch`:

```bash
cd /path/to/repo && python3 -c "
import tempfile
from pathlib import Path
from unittest.mock import patch

from backend.core.engine import ArisMinimalEngine
from backend.storage.events_store import EventsStore
from backend.storage.notes_store import NotesStore
from backend.storage.tasks_store import TasksStore
from backend.storage.thread_state_store import ThreadStateStore

tmp = tempfile.mkdtemp()
ev = EventsStore(Path(tmp)/'e.json')
tk = TasksStore(Path(tmp)/'t.json')
nt = NotesStore(Path(tmp)/'n.json')
th = ThreadStateStore(Path(tmp)/'thread.json')
eng = ArisMinimalEngine(ev, tk, nt, th)

g_ask = {'s':'ask','i':'event','a':'create','obj':{'title':'x'},'target':None,'q':'¿Hora?','r':None,'pending':{},'ctx':None}
with patch('backend.core.engine.ask_gpt', return_value=g_ask):
    r, intent, *_ = eng.process_message('test')
assert intent == 'ambiguo' and eng._thread_store.is_open()

g_ready = {'s':'ready','i':'event','a':'create','obj':{'title':'Reunión','date':'mañana'},'target':None,'q':None,'r':'OK','pending':None,'ctx':None}
with patch('backend.core.engine.ask_gpt', return_value=g_ready):
    r2, intent2, saved, *_ = eng.process_message('sigue')
assert intent2 == 'calendario' and saved and not eng._thread_store.is_open()

eng2 = ArisMinimalEngine(ev, tk, nt, ThreadStateStore(Path(tmp)/'thread2.json'))
with patch('backend.core.engine.ask_gpt', return_value=None):
    r3, intent3, *_ = eng2.process_message('x')
assert intent3 == 'consulta' and 'no puedo interpretar' in r3.lower()

print('OK')
"
```

## 7. Commit sugerido

```bash
git add backend/core/engine.py docs/version_0_47_7_minimal_engine.md
git commit -m "feat: add minimal Aris engine v0.47.7"
```

## 8. Tag sugerido

```bash
git tag v0.47.7-minimal-engine
```
