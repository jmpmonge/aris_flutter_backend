"""Cliente OpenAI mínimo: envía payload JSON y recupera objeto JSON — sin ejecutar acciones."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from backend.core.decision_prompt import MINIMAL_DECISION_SYSTEM_PROMPT


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not isinstance(text, str):
        return None
    t = text.strip()
    if not t:
        return None
    try:
        data = json.loads(t)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    frag = t[start : end + 1]
    try:
        data = json.loads(frag)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def ask_gpt(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Llama al modelo con el payload como mensaje usuario; devuelve dict o None."""
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None

    model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"
    user_content = json.dumps(payload, ensure_ascii=False)

    try:
        client = OpenAI(api_key=key)

        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": MINIMAL_DECISION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
        except Exception:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": MINIMAL_DECISION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
            )
        raw = completion.choices[0].message.content
        if raw is None:
            return None
        return _extract_json_object(str(raw).strip())
    except Exception:
        return None
