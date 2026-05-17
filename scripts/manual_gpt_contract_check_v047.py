#!/usr/bin/env python3
"""Comprueba contra un backend vivo (GPT real). No forma parte de los smokes.

Requisitos:
  - uvicorn ejecutando POST /message (véase backend/main.py)
  - .env del repo con API key válida donde lo espere OpenAI client

Ejemplo:

  BACKEND=http://127.0.0.1:8000 python3 scripts/manual_gpt_contract_check_v047.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    p = argparse.ArgumentParser(description="Prueba manual GPT v0.47 contra /message.")
    p.add_argument(
        "--backend",
        default=os.environ.get("BACKEND", "http://127.0.0.1:8000"),
        help="Raíz URL del backend (ej. http://127.0.0.1:8000)",
    )
    args = p.parse_args()
    base = args.backend.rstrip("/")

    phrases = [
        "cita con el médico el lunes a las 20h",
        "cita con el médico el lunes a las 20",
        "cita con el médico el lunes a las 8",
    ]

    for text in phrases:
        url = f"{base}/message"
        payload = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        print(f"\n=== ENTRADA: {text!r} ===")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace") if e.fp else ""
            print(f"HTTP {e.code}: {msg}", file=sys.stderr)
            return 1
        except OSError as e:
            print(f"Error red: {e}", file=sys.stderr)
            print("¿Está uvicorn escuchando y BACKEND bien puesto?", file=sys.stderr)
            return 2

        try:
            parsed = json.loads(body)
            print(json.dumps(parsed, ensure_ascii=False, indent=2))
        except json.JSONDecodeError:
            print(body)

    print("\nInterpretación rápida: las dos primeras no deberían contener ¿Te refieres; la tercera puede.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
