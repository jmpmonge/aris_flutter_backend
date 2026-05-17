#!/usr/bin/env python3
"""Smokes REST v0.47.31 — PATCH /tasks/{id} (solo `completed`). Sin OpenAI."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient

import backend.main as main_mod
from backend.storage.tasks_store import TasksStore


def main() -> int:
    with TemporaryDirectory() as d:
        base = Path(d)
        store = TasksStore(path=base / "tasks.json")
        row = store.add_task({"title": "comprar leche", "date_text": "mañana"})
        tid = str(row["id"])

        previous = main_mod.tasks_store
        main_mod.tasks_store = store
        try:
            client = TestClient(main_mod.app)

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
            if len(store.list_tasks()) != 1:
                print("FAIL no debe crear tareas nuevas", file=sys.stderr)
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
        finally:
            main_mod.tasks_store = previous

    print("smoke_backend_http_v047: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
