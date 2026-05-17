"""Orquestador mínimo Aris: payload → GPT → normalización → stores/hilo."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from backend.core.context_resolver import resolver_contexto
from backend.core.openai_client import ask_gpt
from backend.core.payload_builder import (
    build_context_response_payload,
    build_payload,
    extract_event_target_id,
    normalize_gpt_response,
    sanitize_visible_text,
)
from backend.storage.events_store import EventsStore
from backend.storage.json_store import utc_now_iso
from backend.storage.notes_store import NotesStore
from backend.storage.tasks_store import TasksStore
from backend.storage.thread_state_store import ThreadStateStore

_MSG_EMPTY = "Escribe un mensaje con contenido."
_MSG_NO_GPT = (
    "Ahora no puedo interpretar acciones complejas. Inténtalo de nuevo en un momento."
)
_MSG_UNSUPPORTED = "Todavía no puedo completar esa acción con seguridad."
_MSG_UNSUPPORTED_MODIFY = (
    "Todavía no puedo completar esa modificación con seguridad."
)
_MSG_NEED_MORE_CTX = (
    "Necesito un dato más para encontrarlo. ¿Puedes concretarlo?"
)
_MSG_MAIL_DRAFT = "He preparado un borrador de correo."
_MSG_OK = "De acuerdo."
_MSG_FAIL_FALLBACK = (
    "No estoy captando toda la información necesaria. ¿Podrías escribirlo de nuevo "
    "de forma más concreta?"
)
_MSG_ANSWER_FALSE_MUTATION = "No he ejecutado ningún cambio en este turno."
_MAX_CONTEXT_NEED_CONTEXT_DEPTH = 8

_DATE_ISO_BASIC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Subcadenas (español) que no deben figurar como **consulta informática** cuando no hubo
# mutación persistida (**s**=answer sin ejecución de store previa en ese turno).
_MUTATION_CLAIM_HINTS: tuple[str, ...] = (
    "he creado",
    "he guardado",
    "he actualizado",
    "he cambiado",
    "he modificado",
    "he borrado",
    "he eliminado",
    "he quitado",
    "he completado",
    "he marcado",
    "ya he creado",
    "ya he cambiado",
    "ya está cambiado",
    "queda cambiado",
    "queda actualizado",
)

_MUTATION_CLAIM_NEGATION_MARKERS: tuple[str, ...] = (
    "no he cambiado",
    "no he modificado",
    "no he creado",
    "no he actualizado",
    "no he guardado",
    "no he borrado",
    "no he eliminado",
    "no he completado",
    "no he marcado",
)


class ArisMinimalEngine:
    """Empaqueta contexto, llama a GPT y aplica efectos según respuesta normalizada."""

    def __init__(
        self,
        events_store: EventsStore,
        tasks_store: TasksStore,
        notes_store: NotesStore,
        thread_store: ThreadStateStore,
    ) -> None:
        self._events = events_store
        self._tasks = tasks_store
        self._notes = notes_store
        self._thread_store = thread_store

    @staticmethod
    def _answer_claims_fresh_success_mutation(reply: str) -> bool:
        """Indica texto de **consulta** con afirmación operativa plausible sin ejecución."""
        lc = (reply or "").casefold()
        if any(m in lc for m in _MUTATION_CLAIM_NEGATION_MARKERS):
            return False
        return any(pat in lc for pat in _MUTATION_CLAIM_HINTS)

    def _answer_grounded_on_last_execution(self, reply: str) -> bool:
        """True si el texto **answer** remite de forma coherente a **last_action**."""
        lc = (reply or "").casefold()
        la = self._thread_store.get_state().get("last_action")
        if not isinstance(la, dict):
            return False
        if str(la.get("status")) != "executed":
            return False

        domain = str(la.get("domain") or "")

        mentions_cal = any(
            x in lc
            for x in (
                "cita",
                "evento",
                "agenda",
                "calendario",
            )
        )
        if mentions_cal and domain != "event":
            return False

        if ("tarea" in lc or "tareas" in lc) and domain != "task":
            return False

        lbl = str(la.get("label") or "").strip().casefold()
        if len(lbl) >= 4 and lbl in lc:
            return True

        res_raw = la.get("result")
        if isinstance(res_raw, dict):
            tm = str(res_raw.get("time_text") or "").strip().casefold()
            if tm and tm in lc:
                return True
            dt_txt = str(res_raw.get("date_text") or "").strip().casefold()
            if len(dt_txt) >= 3 and dt_txt in lc:
                return True
            tit = str(res_raw.get("title") or "").strip().casefold()
            if len(tit) >= 4 and tit in lc:
                return True
        return False

    @staticmethod
    def _focus_label(domain: str, row: dict[str, Any]) -> str:
        if domain == "note":
            t = str(row.get("title") or "").strip()
            if t:
                return t
            c = str(row.get("content") or "").strip()
            return (c[:120] if c else str(row.get("id") or ""))
        return str(row.get("title") or "").strip() or str(row.get("id") or "")

    def _record_successful_mutation(
        self,
        *,
        domain: str,
        action: str,
        row: dict[str, Any],
        changed_fields: dict[str, Any],
    ) -> None:
        """Huella tras store OK: cierra hilo y persiste ``last_focus`` + ``last_action``."""
        now = utc_now_iso()
        label = self._focus_label(domain, row)
        rid = str(row.get("id") or "")
        lf = {
            "domain": domain,
            "id": rid,
            "label": label,
            "object": deepcopy(row),
            "updated_at": now,
        }
        la = {
            "status": "executed",
            "domain": domain,
            "action": action,
            "id": rid,
            "label": label,
            "changed_fields": deepcopy(changed_fields),
            "result": deepcopy(row),
            "created_at": now,
        }
        self._thread_store.clear_state()
        self._thread_store.save_state({"last_focus": lf, "last_action": la})

    def _record_successful_delete(self, *, domain: str, snapshot: dict[str, Any]) -> None:
        tid = str(snapshot.get("id") or "")
        self._thread_store.discard_focus_matching(domain, tid)
        self._thread_store.clear_state()
        now = utc_now_iso()
        label = self._focus_label(domain, snapshot)
        la = {
            "status": "executed",
            "domain": domain,
            "action": "delete",
            "id": tid,
            "label": label,
            "changed_fields": {},
            "result": deepcopy(snapshot),
            "created_at": now,
        }
        self._thread_store.save_state({"last_action": la})

    def process_message(self, text: str) -> tuple[str, str, dict[str, Any] | None, str | None]:
        raw_in = (text or "").strip()
        if not raw_in:
            return (_MSG_EMPTY, "consulta", None, None)

        thread_state = self._thread_store.get_state()
        peticion_raiz = self._peticion_raiz_para_contexto(raw_in, thread_state)

        payload = build_payload(raw_in, thread_state)
        gpt_raw = ask_gpt(payload)
        if gpt_raw is None:
            return (_MSG_NO_GPT, "consulta", None, None)

        result = normalize_gpt_response(gpt_raw)
        if result["s"] == "need_context":
            return self._flujo_need_context(peticion_raiz, result, depth=0)
        return self._aplicar_resultado_gpt(result, peticion_raiz)

    def _peticion_raiz_para_contexto(
        self, raw_in: str, thread_state: dict[str, Any]
    ) -> str:
        if isinstance(thread_state, dict) and thread_state.get("open") is True:
            pend = thread_state.get("pending")
            if isinstance(pend, dict) and pend.get("field") == "context":
                po = pend.get("peticion_original")
                if isinstance(po, str) and po.strip():
                    return po.strip()
        return raw_in

    def _flujo_need_context(
        self,
        peticion_original: str,
        primera: dict[str, Any],
        *,
        depth: int = 0,
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        if depth >= _MAX_CONTEXT_NEED_CONTEXT_DEPTH:
            self._thread_store.clear_state()
            return (_MSG_NEED_MORE_CTX, "ambiguo", None, None)

        ctx_sol = primera.get("ctx") if isinstance(primera.get("ctx"), dict) else {}

        contexto_encontrado = resolver_contexto(
            ctx_sol,
            events_store=self._events,
            tasks_store=self._tasks,
            notes_store=self._notes,
        )

        payload_ctx = build_context_response_payload(
            peticion_original=(peticion_original or "").strip(),
            respuesta_gpt_previa=primera,
            contexto_encontrado=contexto_encontrado,
        )

        segunda_raw = ask_gpt(payload_ctx)
        if segunda_raw is None:
            self._thread_store.save_state(
                {
                    "open": True,
                    "intent": primera["i"],
                    "action": primera.get("a"),
                    "object": primera["obj"],
                    "last_question": _MSG_NEED_MORE_CTX,
                    "pending": {
                        "field": "context",
                        "ctx": primera["ctx"],
                        "contexto_encontrado": contexto_encontrado,
                        "peticion_original": (peticion_original or "").strip(),
                    },
                    "target": extract_event_target_id(primera),
                }
            )
            return (_MSG_NEED_MORE_CTX, "ambiguo", None, None)

        segunda = normalize_gpt_response(segunda_raw)

        if segunda["s"] == "need_context":
            return self._flujo_need_context(
                peticion_original,
                segunda,
                depth=depth + 1,
            )

        return self._aplicar_resultado_gpt(segunda, peticion_original)

    def _aplicar_resultado_gpt(
        self,
        result: dict[str, Any],
        peticion_raiz: str,
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        s = result["s"]

        if s == "ask":
            tid = extract_event_target_id(result)
            obj_out: dict[str, Any] = (
                dict(result["obj"]) if isinstance(result.get("obj"), dict) else {}
            )
            pend_raw = result.get("pending")
            if isinstance(pend_raw, dict) and pend_raw.get("field") == "target_selection":
                oo = pend_raw.get("original_obj")
                if isinstance(oo, dict) and oo:
                    merged = dict(oo)
                    merged.update(obj_out)
                    obj_out = merged
            self._thread_store.save_state(
                {
                    "open": True,
                    "intent": result["i"],
                    "action": result.get("a"),
                    "object": obj_out,
                    "last_question": result["q"],
                    "pending": result["pending"],
                    "target": tid,
                }
            )
            q = result["q"]
            reply = sanitize_visible_text(q) if isinstance(q, str) else ""
            return (reply or "¿Puedes concretar?", "ambiguo", None, None)

        if s == "answer":
            self._thread_store.clear_state()
            r_raw = result.get("r")
            reply = (
                sanitize_visible_text(r_raw) if isinstance(r_raw, str) else ""
            )
            if reply and (
                ArisMinimalEngine._answer_claims_fresh_success_mutation(reply)
                and not self._answer_grounded_on_last_execution(reply)
            ):
                return (_MSG_ANSWER_FALSE_MUTATION, "consulta", None, None)
            return (reply or _MSG_OK, "consulta", None, None)

        if s == "fail":
            self._thread_store.clear_state()
            return (_MSG_FAIL_FALLBACK, "consulta", None, None)

        if s == "need_context":
            return self._flujo_need_context(peticion_raiz, result, depth=0)

        if s == "ready":
            return self._handle_ready(result)

        self._thread_store.clear_state()
        return (_MSG_FAIL_FALLBACK, "consulta", None, None)

    def _handle_ready(
        self, result: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        a = result["a"]
        i = result["i"]
        obj = result["obj"]

        if a == "answer":
            self._thread_store.clear_state()
            r_raw = result.get("r")
            reply = (
                sanitize_visible_text(r_raw) if isinstance(r_raw, str) else ""
            )
            if reply and (
                ArisMinimalEngine._answer_claims_fresh_success_mutation(reply)
                and not self._answer_grounded_on_last_execution(reply)
            ):
                return (_MSG_ANSWER_FALSE_MUTATION, "consulta", None, None)
            return (reply or _MSG_OK, "consulta", None, None)

        if a == "create":
            return self._handle_ready_create(result, i, obj)

        if a == "query":
            self._thread_store.clear_state()
            r = result.get("r")
            reply = sanitize_visible_text(r) if isinstance(r, str) else ""
            return (reply or _MSG_OK, "consulta", None, None)

        if a == "update":
            if i == "event":
                return self._handle_ready_update_event(result)
            if i == "task":
                return self._handle_ready_update_task(result)
            self._thread_store.clear_state()
            return (_MSG_UNSUPPORTED_MODIFY, "consulta", None, None)

        if a == "delete":
            if i == "event":
                return self._handle_ready_delete_event(result)
            if i == "task":
                return self._handle_ready_delete_task(result)
            self._thread_store.clear_state()
            return (_MSG_UNSUPPORTED, "consulta", None, None)

        if a == "complete":
            if i == "task":
                return self._handle_ready_complete_task(result)
            self._thread_store.clear_state()
            return (_MSG_UNSUPPORTED, "consulta", None, None)

        # draft u otros — no ejecutar aquí (query tratado más arriba)
        self._thread_store.clear_state()
        return (_MSG_UNSUPPORTED, "consulta", None, None)

    def _handle_ready_delete_event(
        self, result: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        r_raw = result.get("r")

        def _reply_del(default: str) -> str:
            if isinstance(r_raw, str):
                cleaned = sanitize_visible_text(r_raw)
                if cleaned:
                    return cleaned
            return default

        tid = extract_event_target_id(result)
        if not tid:
            self._thread_store.clear_state()
            return (
                "No sé qué evento quieres borrar. ¿Puedes concretarlo?",
                "consulta",
                None,
                None,
            )

        snap_evt = self._events.get_event_by_id(tid)
        if snap_evt is None:
            self._thread_store.clear_state()
            return (
                "No encuentro ese evento en tu agenda local.",
                "consulta",
                None,
                None,
            )

        snapshot = dict(snap_evt)

        if not self._events.delete_event(tid):
            self._thread_store.clear_state()
            return (
                "No encuentro ese evento en tu agenda local.",
                "consulta",
                None,
                None,
            )

        self._record_successful_delete(domain="event", snapshot=snapshot)
        return (_reply_del("He borrado el evento."), "calendario", None, None)

    def _handle_ready_delete_task(
        self, result: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        """Ejecuta borrado persistido sólo tras **ready**/ **task**/ **delete** con **target** válido."""
        r_raw = result.get("r")

        def _reply_del(default: str) -> str:
            if isinstance(r_raw, str):
                cleaned = sanitize_visible_text(r_raw)
                if cleaned:
                    return cleaned
            return default

        tid = extract_event_target_id(result)
        if not tid:
            self._thread_store.clear_state()
            return (
                "No sé qué tarea quieres borrar. ¿Puedes concretarla?",
                "consulta",
                None,
                None,
            )

        cur = next(
            (t for t in self._tasks.list_tasks() if str(t.get("id")) == tid),
            None,
        )
        if cur is None:
            self._thread_store.clear_state()
            return (
                "No encuentro esa tarea en tu lista.",
                "consulta",
                None,
                None,
            )

        removed = self._tasks.delete_task(tid)
        if removed is None:
            self._thread_store.clear_state()
            return (
                "No he podido borrar esa tarea.",
                "consulta",
                None,
                None,
            )

        self._record_successful_delete(domain="task", snapshot=dict(removed))
        return (_reply_del("He borrado la tarea."), "tarea", None, None)

    def _handle_ready_complete_task(
        self, result: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        r_raw = result.get("r")

        def _reply_done(default: str) -> str:
            if isinstance(r_raw, str):
                cleaned = sanitize_visible_text(r_raw)
                if cleaned:
                    return cleaned
            return default

        tid = extract_event_target_id(result)
        if not tid:
            self._thread_store.clear_state()
            return (
                "No sé qué tarea quieres completar. ¿Puedes concretarla?",
                "consulta",
                None,
                None,
            )

        cur = next(
            (t for t in self._tasks.list_tasks() if str(t.get("id")) == tid),
            None,
        )
        if cur is None:
            self._thread_store.clear_state()
            return (
                "No encuentro esa tarea en tu lista.",
                "consulta",
                None,
                None,
            )

        updated = self._tasks.complete_task(tid)
        if updated is None:
            self._thread_store.clear_state()
            return (
                "No he podido completar esa tarea.",
                "consulta",
                None,
                None,
            )

        self._record_successful_mutation(
            domain="task",
            action="complete",
            row=updated,
            changed_fields={"completed": True},
        )
        return (
            _reply_done("He marcado la tarea como completada."),
            "tarea",
            updated,
            None,
        )

    @staticmethod
    def _requested_field_meta_task(obj: dict[str, Any]) -> str | None:
        """Claves sólo-estructura que GPT puede enviar (**no** implican parche persistido solo)."""
        for key in ("requested_field", "_field_requested"):
            if key not in obj:
                continue
            rv = obj.get(key)
            if rv is None:
                continue
            s = str(rv).strip().lower()
            return s if s else None
        return None

    @staticmethod
    def _followup_pending_field_task_update(requested: str | None) -> str:
        allowed = frozenset(
            {"description", "date", "time", "title", "tags", "date_text", "time_text"}
        )
        if requested in allowed:
            if requested == "date_text":
                return "date"
            if requested == "time_text":
                return "time"
            return requested
        return "update_value"

    def _prompt_task_missing_value(self, pend_field: str, title_hint: str | None) -> str:
        ttl = (title_hint or "").strip()
        noun = (
            f"la tarea «{ttl}»" if ttl else "esa tarea"
        )
        if pend_field == "description":
            return f"¿Qué descripción quieres ponerle a {noun}?"
        if pend_field in ("date", "date_text"):
            return f"¿Para qué día quieres cambiar {noun}?"
        if pend_field in ("time", "time_text"):
            return f"¿A qué hora quieres cambiar {noun}?"
        if pend_field == "title":
            return f"¿Qué nuevo título quieres ponerle a {noun}?"
        if pend_field == "tags":
            return f"¿Qué etiquetas quieres ponerle a {noun}?"
        return "¿Qué quieres cambiar de esa tarea?"

    def _handle_ready_update_task(
        self, result: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        r_raw = result.get("r")

        def _reply_saved(default: str) -> str:
            if isinstance(r_raw, str):
                cleaned = sanitize_visible_text(r_raw)
                if cleaned:
                    return cleaned
            return default

        obj_raw = result.get("obj")
        obj: dict[str, Any] = obj_raw if isinstance(obj_raw, dict) else {}
        tid = extract_event_target_id(result)
        meta_req = ArisMinimalEngine._requested_field_meta_task(obj)
        updates_eff = self._task_updates_from_obj(obj)
        hinted = meta_req or any(
            k in obj for k in ("requested_field", "_field_requested")
        )

        # --- Falta target: mantén hilo operativo ---
        if not tid:
            if updates_eff or hinted:
                msg = (
                    "No sé qué tarea quieres modificar. ¿Puedes concretarla?"
                )
                pend: dict[str, Any] = {
                    "field": "missing_target",
                    "original_action": "update",
                }
                self._thread_store.save_state(
                    {
                        "open": True,
                        "intent": "task",
                        "action": "update",
                        "object": dict(obj),
                        "last_question": msg,
                        "pending": pend,
                        "target": None,
                    }
                )
                return (msg, "ambiguo", None, None)

            msg_empty = (
                "No sé qué tarea quieres modificar ni qué quieres cambiar. "
                "¿Puedes concretarlo?"
            )
            self._thread_store.clear_state()
            return (msg_empty, "consulta", None, None)

        cur = next(
            (t for t in self._tasks.list_tasks() if str(t.get("id")) == tid),
            None,
        )
        if cur is None:
            self._thread_store.clear_state()
            return (
                "No encuentro esa tarea en tu lista.",
                "consulta",
                None,
                None,
            )

        # --- Obj vacío o sin patch persistible: esperar valor (hilo abierto) ---
        if not updates_eff:
            pfield = ArisMinimalEngine._followup_pending_field_task_update(meta_req)
            title_hint = str(cur.get("title") or "").strip() or None
            prompt = self._prompt_task_missing_value(pfield, title_hint)
            pend_w: dict[str, Any] = {
                "field": pfield,
                "target": tid,
                "original_action": "update",
            }
            preserved = dict(obj)
            self._thread_store.save_state(
                {
                    "open": True,
                    "intent": "task",
                    "action": "update",
                    "object": preserved,
                    "last_question": prompt,
                    "pending": pend_w,
                    "target": tid,
                }
            )
            return (prompt, "ambiguo", None, None)

        try:
            updated = self._tasks.update_task(tid, updates_eff)
        except ValueError:
            self._thread_store.clear_state()
            return ("No he podido actualizar esa tarea.", "consulta", None, None)

        if updated is None:
            self._thread_store.clear_state()
            return ("No he podido actualizar esa tarea.", "consulta", None, None)

        cf_track: dict[str, Any] = dict(updates_eff)
        if isinstance(obj, dict):
            for key, val in obj.items():
                if isinstance(key, str) and key.startswith("task_") and val is not None:
                    cf_track[key] = val
        self._record_successful_mutation(
            domain="task",
            action="update",
            row=updated,
            changed_fields=cf_track,
        )
        return (
            _reply_saved("He actualizado la tarea."),
            "tarea",
            updated,
            None,
        )

    def _handle_ready_update_event(
        self, result: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        r_raw = result.get("r")

        def _reply_saved(default: str) -> str:
            if isinstance(r_raw, str):
                cleaned = sanitize_visible_text(r_raw)
                if cleaned:
                    return cleaned
            return default

        obj_raw = result.get("obj")
        obj: dict[str, Any] = obj_raw if isinstance(obj_raw, dict) else {}

        tid = extract_event_target_id(result)
        if not tid:
            self._thread_store.clear_state()
            return (
                "No sé qué evento quieres modificar. ¿Puedes concretarlo?",
                "consulta",
                None,
                None,
            )

        if self._events.get_event_by_id(tid) is None:
            self._thread_store.clear_state()
            return (
                "No encuentro ese evento en tu agenda local.",
                "consulta",
                None,
                None,
            )

        updates = self._event_updates_from_obj(obj)
        if not updates:
            self._thread_store.clear_state()
            return (
                "No he captado qué dato quieres cambiar.",
                "consulta",
                None,
                None,
            )

        try:
            updated = self._events.update_event(tid, updates)
        except ValueError:
            self._thread_store.clear_state()
            return ("No he podido modificar ese evento.", "consulta", None, None)

        if updated is None:
            self._thread_store.clear_state()
            return ("No he podido modificar ese evento.", "consulta", None, None)

        cf_evt: dict[str, Any] = dict(updates)
        if isinstance(obj, dict):
            for key, val in obj.items():
                if isinstance(key, str) and key.startswith("cal_") and val is not None:
                    cf_evt.setdefault(key, val)
        self._record_successful_mutation(
            domain="event",
            action="update",
            row=dict(updated),
            changed_fields=cf_evt,
        )
        return (
            _reply_saved("He actualizado el evento."),
            "calendario",
            updated,
            None,
        )

    def _handle_ready_create(
        self,
        result: dict[str, Any],
        i: str,
        obj: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        r_raw = result.get("r")

        def _reply_saved(default: str) -> str:
            if isinstance(r_raw, str):
                cleaned = sanitize_visible_text(r_raw)
                if cleaned:
                    return cleaned
            return default

        if i == "event":
            ev_payload = self._event_payload(obj)
            if ev_payload is None:
                self._thread_store.clear_state()
                return ("No he podido guardar el evento: falta un título.", "consulta", None, None)
            try:
                saved = self._events.add_event(ev_payload)
            except ValueError:
                self._thread_store.clear_state()
                return ("No he podido guardar el evento.", "consulta", None, None)
            self._record_successful_mutation(
                domain="event",
                action="create",
                row=saved,
                changed_fields=dict(ev_payload),
            )
            return (
                _reply_saved("He guardado la cita."),
                "calendario",
                saved,
                None,
            )

        if i == "task":
            task_payload = self._task_payload(obj)
            if task_payload is None:
                self._thread_store.clear_state()
                return ("No he podido guardar la tarea: falta un título.", "consulta", None, None)
            try:
                saved = self._tasks.add_task(task_payload)
            except ValueError:
                self._thread_store.clear_state()
                return ("No he podido guardar la tarea.", "consulta", None, None)
            self._record_successful_mutation(
                domain="task",
                action="create",
                row=saved,
                changed_fields=dict(task_payload),
            )
            return (_reply_saved("He guardado la tarea."), "tarea", saved, None)

        if i == "note":
            note_payload = self._note_payload(obj)
            if note_payload is None:
                self._thread_store.clear_state()
                return ("No he podido guardar la nota: falta contenido.", "consulta", None, None)
            try:
                saved = self._notes.add_note(note_payload)
            except ValueError:
                self._thread_store.clear_state()
                return ("No he podido guardar la nota.", "consulta", None, None)
            self._record_successful_mutation(
                domain="note",
                action="create",
                row=saved,
                changed_fields=dict(note_payload),
            )
            return (_reply_saved("He guardado la nota."), "nota", saved, None)

        if i == "mail":
            self._thread_store.clear_state()
            return (_reply_saved(_MSG_MAIL_DRAFT), "mail", dict(obj), None)

        self._thread_store.clear_state()
        return (_MSG_UNSUPPORTED, "consulta", None, None)

    @staticmethod
    def _event_updates_from_obj(obj: dict[str, Any]) -> dict[str, Any]:
        """Campos admitidos por events_store.update_event; omitir vacíos."""
        out: dict[str, Any] = {}

        iso_keys_evt = ("cal_date_iso", "date_iso", "dateISO")

        if "cal_title" in obj or "title" in obj:
            raw_t = (
                obj.get("cal_title")
                if "cal_title" in obj
                else obj.get("title")
            )
            if raw_t is None or (
                isinstance(raw_t, str) and raw_t.strip() == ""
            ):
                raw_t = obj.get("title") if "cal_title" in obj else None
            if raw_t is not None and str(raw_t).strip():
                out["title"] = str(raw_t).strip()

        dt_val = None
        if "cal_date_text" in obj:
            dt_val = obj.get("cal_date_text")
        elif "date_text" in obj:
            dt_val = obj.get("date_text")
        elif "date" in obj:
            dt_val = obj.get("date")
        if dt_val is not None and str(dt_val).strip():
            out["date_text"] = str(dt_val).strip()

        tm_val = None
        if "cal_time_text" in obj:
            tm_val = obj.get("cal_time_text")
        elif "time_text" in obj:
            tm_val = obj.get("time_text")
        elif "time" in obj:
            tm_val = obj.get("time")
        if tm_val is not None and str(tm_val).strip():
            out["time_text"] = str(tm_val).strip()

        if (
            "cal_people" in obj
            or "people" in obj
            or "participants" in obj
        ):
            pr = obj.get("cal_people")
            if pr is None and "people" in obj:
                pr = obj.get("people")
            if pr is None and "participants" in obj:
                pr = obj.get("participants")
            parts: list[str] = []
            if isinstance(pr, str):
                s = pr.strip()
                if s:
                    parts = [s]
            elif isinstance(pr, list):
                parts = [str(p).strip() for p in pr if str(p).strip()]
            if parts:
                out["participants"] = parts

        if "cal_location" in obj:
            loc = obj.get("cal_location")
            if loc is not None and str(loc).strip():
                out["location"] = str(loc).strip()
        elif "location" in obj:
            loc = obj.get("location")
            if loc is not None and str(loc).strip():
                out["location"] = str(loc).strip()

        if "cal_description" in obj:
            desc = obj.get("cal_description")
            if desc is not None and str(desc).strip():
                out["description"] = str(desc).strip()
        elif "description" in obj:
            desc = obj.get("description")
            if desc is not None and str(desc).strip():
                out["description"] = str(desc).strip()

        if "cal_duration_minutes" in obj:
            dm = obj.get("cal_duration_minutes")
            if isinstance(dm, int):
                out["duration_minutes"] = dm
        elif "duration_minutes" in obj:
            dm = obj.get("duration_minutes")
            if isinstance(dm, int):
                out["duration_minutes"] = dm

        if any(k in obj for k in iso_keys_evt):
            cand = ArisMinimalEngine._coerce_date_iso_from_keys(obj, iso_keys_evt)
            if cand is not None:
                out["date_iso"] = cand
            else:

                def _blank_di(v: Any) -> bool:
                    return v is None or (
                        isinstance(v, str) and str(v).strip() == ""
                    )

                had_nonempty = False
                for ik in iso_keys_evt:
                    if ik in obj and not _blank_di(obj.get(ik)):
                        had_nonempty = True
                if not had_nonempty:
                    out["date_iso"] = None

        return out

    @staticmethod
    def _coerce_date_iso_raw(raw: Any) -> str | None:
        if raw is None:
            return None
        s = str(raw).strip()
        if not s or not _DATE_ISO_BASIC_RE.match(s):
            return None
        try:
            y = int(s[0:4])
            mo = int(s[5:7])
            d = int(s[8:10])
        except ValueError:
            return None
        if y < 1970 or y > 2199 or mo < 1 or mo > 12 or d < 1 or d > 31:
            return None
        return s

    @staticmethod
    def _coerce_date_iso_from_keys(obj: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        """Primer valor ISO válido hallado en ``obj`` según orden de prioridad ``keys``."""
        if not isinstance(obj, dict):
            return None
        for key in keys:
            if key not in obj:
                continue
            got = ArisMinimalEngine._coerce_date_iso_raw(obj.get(key))
            if got is not None:
                return got
        return None

    @staticmethod
    def _event_payload(obj: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(obj, dict):
            return None
        raw_title = obj.get("cal_title")
        if raw_title is None or str(raw_title).strip() == "":
            raw_title = obj.get("title")
        title = str(raw_title or "").strip()
        if not title:
            return None

        parts_raw = obj.get("cal_people")
        if parts_raw is None:
            parts_raw = obj.get("people")
        if parts_raw is None:
            parts_raw = obj.get("participants")
        participants: list[str] = []
        if isinstance(parts_raw, list):
            participants = [str(p).strip() for p in parts_raw if str(p).strip()]

        dm_raw = obj.get("cal_duration_minutes")
        if dm_raw is None:
            dm_raw = obj.get("duration_minutes")
        duration_minutes: int | None = dm_raw if isinstance(dm_raw, int) else None

        date_text = obj.get("cal_date_text")
        if date_text is None or str(date_text).strip() == "":
            date_text = obj.get("date_text")
        if date_text is None or str(date_text).strip() == "":
            date_text = obj.get("date")

        time_text = obj.get("cal_time_text")
        if time_text is None or str(time_text).strip() == "":
            time_text = obj.get("time_text")
        if time_text is None or str(time_text).strip() == "":
            time_text = obj.get("time")

        loc = obj.get("cal_location")
        if loc is None:
            loc = obj.get("location")
        location = (
            str(loc).strip() if loc is not None and str(loc).strip() else None
        )

        desc = obj.get("cal_description")
        if desc is None:
            desc = obj.get("description")
        description = (
            str(desc).strip() if desc is not None and str(desc).strip() else None
        )

        date_iso_store = ArisMinimalEngine._coerce_date_iso_from_keys(
            obj, ("cal_date_iso", "date_iso", "dateISO")
        )

        out: dict[str, Any] = {
            "title": title,
            "date_text": str(date_text).strip() if date_text is not None else None,
            "time_text": str(time_text).strip() if time_text is not None else None,
            "date_iso": date_iso_store,
            "participants": participants,
            "location": location,
            "description": description,
            "duration_minutes": duration_minutes,
        }
        for k in ("date_text", "time_text", "location", "description"):
            if out.get(k) == "":
                out[k] = None
        return out

    @staticmethod
    def _task_updates_from_obj(obj: dict[str, Any]) -> dict[str, Any]:
        """Campos permitidos para persistir vía **task**/ **update** — sin semántica GPT extra."""
        if not isinstance(obj, dict):
            return {}
        out: dict[str, Any] = {}
        iso_keys_task = ("task_due_date_iso", "date_iso", "dateISO")

        if "task_title" in obj or "title" in obj:
            raw_t = (
                obj.get("task_title")
                if "task_title" in obj
                else obj.get("title")
            )
            if raw_t is None or (
                isinstance(raw_t, str) and raw_t.strip() == ""
            ):
                raw_t = obj.get("title") if "task_title" in obj else None
            t = str(raw_t or "").strip()
            if t:
                out["title"] = t

        if "task_description" in obj or "description" in obj:
            if "task_description" in obj:
                dv = obj.get("task_description")
            else:
                dv = obj.get("description")
            if dv is None:
                out["description"] = None
            else:
                s = str(dv).strip()
                out["description"] = s if s else None

        if (
            "task_due_date_text" in obj
            or "date_text" in obj
            or "date" in obj
        ):
            if "task_due_date_text" in obj:
                dt_val = obj.get("task_due_date_text")
            elif "date_text" in obj:
                dt_val = obj.get("date_text")
            else:
                dt_val = obj.get("date")
            if dt_val is None:
                out["date_text"] = None
            else:
                ds = str(dt_val).strip()
                out["date_text"] = ds if ds else None

        if any(k in obj for k in iso_keys_task):
            cand = ArisMinimalEngine._coerce_date_iso_from_keys(
                obj, iso_keys_task
            )
            if cand is not None:
                out["date_iso"] = cand
            else:

                def _blank_di_task(v: Any) -> bool:
                    return v is None or (
                        isinstance(v, str) and str(v).strip() == ""
                    )

                had_nonempty_task = False
                for ik in iso_keys_task:
                    if ik in obj and not _blank_di_task(obj.get(ik)):
                        had_nonempty_task = True
                if not had_nonempty_task:
                    out["date_iso"] = None

        if (
            "task_due_time_text" in obj
            or "time_text" in obj
            or "time" in obj
        ):
            if "task_due_time_text" in obj:
                tm = obj.get("task_due_time_text")
            elif "time_text" in obj:
                tm = obj.get("time_text")
            else:
                tm = obj.get("time")
            if tm is None:
                out["time_text"] = None
            else:
                ts = str(tm).strip()
                out["time_text"] = ts if ts else None

        if "task_priority" in obj or "priority" in obj:
            pr = (
                obj.get("task_priority")
                if "task_priority" in obj
                else obj.get("priority")
            )
            if pr is None or str(pr).strip() == "":
                out["priority"] = "normal"
            else:
                ps = str(pr).strip().lower()
                out["priority"] = "high" if ps == "high" else "normal"

        if "task_tags" in obj or "tags" in obj:
            traw = (
                obj.get("task_tags")
                if "task_tags" in obj
                else obj.get("tags")
            )
            if isinstance(traw, list):
                out["tags"] = [
                    str(x).strip() for x in traw if str(x).strip()
                ]
            else:
                out["tags"] = []

        return out

    @staticmethod
    def _task_payload(obj: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(obj, dict):
            return None
        raw_title = obj.get("task_title")
        if raw_title is None or str(raw_title).strip() == "":
            raw_title = obj.get("title")
        title = str(raw_title or "").strip()
        if not title:
            return None

        date_text = obj.get("task_due_date_text")
        if date_text is None or str(date_text).strip() == "":
            date_text = obj.get("date_text")
        if date_text is None or str(date_text).strip() == "":
            date_text = obj.get("date")

        time_text = obj.get("task_due_time_text")
        if time_text is None or str(time_text).strip() == "":
            time_text = obj.get("time_text")
        if time_text is None or str(time_text).strip() == "":
            time_text = obj.get("time")

        description: str | None = None
        if "task_description" in obj:
            dsc = obj.get("task_description")
        elif "description" in obj:
            dsc = obj.get("description")
        else:
            dsc = None
        if dsc is not None:
            ds = str(dsc).strip()
            if ds:
                description = ds

        date_iso_store = ArisMinimalEngine._coerce_date_iso_from_keys(
            obj, ("task_due_date_iso", "date_iso", "dateISO")
        )

        pr_src = obj.get("task_priority")
        if pr_src is None:
            pr_src = obj.get("priority")
        if pr_src is None or str(pr_src).strip() == "":
            priority_eff = "normal"
        else:
            ps = str(pr_src).strip().lower()
            priority_eff = "high" if ps == "high" else "normal"

        tags_for_store: list[str] = []
        traw = obj.get("task_tags")
        if traw is None:
            traw = obj.get("tags")
        if isinstance(traw, list):
            tags_for_store = [
                str(x).strip() for x in traw if str(x).strip()
            ]

        out: dict[str, Any] = {
            "title": title,
            "description": description,
            "date_text": str(date_text).strip() if date_text else None,
            "time_text": str(time_text).strip() if time_text else None,
            "date_iso": date_iso_store,
            "priority": priority_eff,
            "tags": tags_for_store,
        }
        for k in ("date_text", "time_text"):
            if out.get(k) == "":
                out[k] = None
        return out

    @staticmethod
    def _note_payload(obj: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(obj, dict):
            return None
        if "note_title" in obj:
            title_raw = obj.get("note_title")
        else:
            title_raw = obj.get("title")
        title = str(title_raw).strip() if title_raw is not None else ""

        if "note_content" in obj:
            content_raw = obj.get("note_content")
        else:
            content_raw = obj.get("content")
        content = str(content_raw).strip() if content_raw is not None else ""

        if not content and title:
            content = title
        if not content:
            return None

        tags_raw = (
            obj.get("note_tags")
            if "note_tags" in obj
            else obj.get("tags")
        )
        tags: list[str] = []
        if isinstance(tags_raw, list):
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]

        out: dict[str, Any] = {"title": title or None, "content": content, "tags": tags}
        return out
