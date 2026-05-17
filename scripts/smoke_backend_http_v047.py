#!/usr/bin/env python3
"""Smokes REST — POST/PATCH /tasks + GET /events date_iso civil (sin OpenAI)."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient

import backend.main as main_mod
from backend.storage.events_store import EventsStore
from backend.storage.tasks_store import TasksStore


def main() -> int:
    with TemporaryDirectory() as d:
        base = Path(d)
        store = TasksStore(path=base / "tasks.json")
        ev_tmp = EventsStore(path=base / "events.json")
        ev_tmp.add_event(
            {
                "title": "smoke iso civil",
                "date_text": "miércoles",
                "date_iso": "2026-05-20",
                "time_text": "10:00",
                "participants": ["Luis"],
            }
        )

        prev_tasks = main_mod.tasks_store
        prev_events = main_mod.events_store
        main_mod.tasks_store = store
        main_mod.events_store = ev_tmp
        try:
            client = TestClient(main_mod.app)

            # --- POST CASO A: mínima ---
            r_a = client.post("/tasks", json={"title": "comprar leche"})
            if r_a.status_code not in (200, 201):
                print(
                    f"FAIL POST mínima: {r_a.status_code} {r_a.text}",
                    file=sys.stderr,
                )
                return 1
            ja = r_a.json()
            if ja.get("title") != "comprar leche":
                print(f"FAIL POST mínima title: {ja!r}", file=sys.stderr)
                return 1
            if ja.get("completed") is not False:
                print(f"FAIL POST mínima completed: {ja!r}", file=sys.stderr)
                return 1
            if ja.get("priority") != "normal":
                print(f"FAIL POST mínima priority: {ja!r}", file=sys.stderr)
                return 1
            if ja.get("tags") != []:
                print(f"FAIL POST mínima tags: {ja!r}", file=sys.stderr)
                return 1
            if not str(ja.get("id") or "").strip():
                print(f"FAIL POST mínima sin id: {ja!r}", file=sys.stderr)
                return 1

            # --- POST CASO B: completa ---
            r_b = client.post(
                "/tasks",
                json={
                    "title": "llamar al banco",
                    "description": "preguntar por los seguros",
                    "date_text": "mañana",
                    "date_iso": "2026-05-18",
                    "time_text": "10:00",
                    "priority": "high",
                    "tags": ["Banco", "Seguro"],
                },
            )
            if r_b.status_code not in (200, 201):
                print(
                    f"FAIL POST completa: {r_b.status_code} {r_b.text}",
                    file=sys.stderr,
                )
                return 1
            jb = r_b.json()
            want = {
                "title": "llamar al banco",
                "description": "preguntar por los seguros",
                "date_text": "mañana",
                "date_iso": "2026-05-18",
                "time_text": "10:00",
                "priority": "high",
                "tags": ["Banco", "Seguro"],
            }
            for k, v in want.items():
                if jb.get(k) != v:
                    print(f"FAIL POST completa campo {k}: {jb!r}", file=sys.stderr)
                    return 1
            if jb.get("completed") is not False:
                print(f"FAIL POST completa completed: {jb!r}", file=sys.stderr)
                return 1

            # --- POST CASO C: title vacío ---
            r_c = client.post("/tasks", json={"title": ""})
            if r_c.status_code not in (400, 422):
                print(
                    f"FAIL POST title vacío esperaba 400/422, fue {r_c.status_code}",
                    file=sys.stderr,
                )
                return 1

            # --- POST CASO D: priority inválida → normal ---
            r_d = client.post(
                "/tasks",
                json={"title": "revisar informe", "priority": "medium"},
            )
            if r_d.status_code not in (200, 201):
                print(
                    f"FAIL POST priority medium: {r_d.status_code} {r_d.text}",
                    file=sys.stderr,
                )
                return 1
            if r_d.json().get("priority") != "normal":
                print(f"FAIL POST priority normalizada: {r_d.json()!r}", file=sys.stderr)
                return 1

            if len(store.list_tasks()) != 3:
                print(
                    f"FAIL conteo tareas tras POSTs: esperaba 3, hay {len(store.list_tasks())}",
                    file=sys.stderr,
                )
                return 1

            # --- PATCH (regresión v0.47.31) ---
            tid = str(ja["id"])
            r_ok = client.patch(f"/tasks/{tid}", json={"completed": True})
            if r_ok.status_code != 200:
                print(
                    f"FAIL PATCH completed true: {r_ok.status_code} {r_ok.text}",
                    file=sys.stderr,
                )
                return 1
            j = r_ok.json()
            if str(j.get("id")) != tid or j.get("completed") is not True:
                print(f"FAIL respuesta PATCH true: {j!r}", file=sys.stderr)
                return 1

            r_off = client.patch(f"/tasks/{tid}", json={"completed": False})
            if r_off.status_code != 200:
                print(
                    f"FAIL PATCH completed false: {r_off.status_code} {r_off.text}",
                    file=sys.stderr,
                )
                return 1
            if r_off.json().get("completed") is not False:
                print(f"FAIL respuesta PATCH false: {r_off.json()!r}", file=sys.stderr)
                return 1

            ghost = "00000000-0000-4000-8000-000000000099"
            r404 = client.patch(f"/tasks/{ghost}", json={"completed": True})
            if r404.status_code != 404:
                print(
                    f"FAIL PATCH id inexistente esperaba 404, fue {r404.status_code}",
                    file=sys.stderr,
                )
                return 1

            r_bad = client.patch(f"/tasks/{tid}", json={"completed": "sí"})
            if r_bad.status_code not in (400, 422):
                print(
                    "FAIL tipo inválido en completed esperaba 400 o 422, "
                    f"fue {r_bad.status_code} {r_bad.text}",
                    file=sys.stderr,
                )
                return 1

            rev = client.get("/events")
            if rev.status_code != 200:
                print(
                    f"FAIL GET /events: {rev.status_code} {rev.text}",
                    file=sys.stderr,
                )
                return 1
            evlist = rev.json()
            if not isinstance(evlist, list) or len(evlist) != 1:
                print(f"FAIL GET /events lista: {evlist!r}", file=sys.stderr)
                return 1
            eo = evlist[0]
            if str(eo.get("date_iso") or "") != "2026-05-20":
                print(f"FAIL GET /events date_iso ausente/mal {eo!r}", file=sys.stderr)
                return 1
            if str(eo.get("time_text") or "") != "10:00":
                print(f"FAIL GET /events time_text {eo!r}", file=sys.stderr)
                return 1
        finally:
            main_mod.tasks_store = prev_tasks
            main_mod.events_store = prev_events

    print("smoke_backend_http_v047: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
