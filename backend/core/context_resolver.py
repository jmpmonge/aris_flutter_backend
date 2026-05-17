"""Resolución técnica de solicitudes de contexto estructuradas — sin semántica del raw del usuario.

Calendar: **`events_*`** sólo igualan **date_text** / personas / tiempo almacenados (sin resolver calendarios).
Tasks: **`list_tasks`** con filtros triviales opcionales (**completed**, **title** (subcadena **casefold** en título), **date**/**date_text**, **date_iso**, **priority**, **tag**/**tags**) sin interpretación semántica extra.
Notes: **`list_notes`** con filtros triviales opcionales (**text**/**content**, **title**, **tag**/**tags**) sólo igualdad textual o subcadena (**casefold**) sin interpretación semántica.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_CAND_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _opt_candidate_date_iso(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or not _CAND_ISO.match(s):
        return None
    return s


_MAX_CALENDAR_CANDIDATES = 5
_MAX_TASK_CANDIDATES = 50
_MAX_NOTE_CANDIDATES = 50

_DOMINIO_CALENDARIO_EN = "calendar"
_DOMINIOS_TAREAS_EN = frozenset({"tasks", "task"})
_QUERY_TAREA_LIST_TASKS = "list_tasks"
_DOMINIOS_NOTAS_EN = frozenset({"notes", "note"})
_QUERY_NOTA_LIST_NOTES = "list_notes"
_CONSULTAS_SOPORTADAS = frozenset(
    {
        "events_by_person",
        "events_by_date",
        "events_by_person_and_time",
    },
)

_compatible_time_7: frozenset[str] = frozenset({"7", "07:00", "19:00"})
_compatible_time_8: frozenset[str] = frozenset({"8", "08:00", "20:00"})


def resolver_contexto(
    solicitud_contexto: dict[str, Any] | None,
    *,
    events_store,
    tasks_store=None,
    notes_store=None,
) -> dict[str, Any]:
    """Recibe una solicitud de contexto (p. ej. ctx de GPT) y devuelve candidatos."""
    sc = solicitud_contexto if isinstance(solicitud_contexto, dict) else {}

    filtros_entrada: dict[str, Any] = {}
    dominio_consulta_en = str(sc.get("domain") or "").strip().lower()
    consulta_raw = sc.get("query")
    consulta = str(consulta_raw).strip() if consulta_raw is not None else ""
    fraw = sc.get("filters")
    if isinstance(fraw, dict):
        filtros_entrada = dict(fraw)

    dominio_etiqueta = str(sc.get("domain") or "").strip()
    candidatos_serializados: list[dict[str, Any]] = []
    if dominio_consulta_en == _DOMINIO_CALENDARIO_EN:
        candidatos_raw = _resolver_calendario(
            consulta, filtros_entrada, events_store
        )
        candidatos_raw = _unique_stable_limit(candidatos_raw, _MAX_CALENDAR_CANDIDATES)
        candidatos_serializados = [
            _candidate_from_event(ev) for ev in candidatos_raw
        ]
    elif dominio_consulta_en in _DOMINIOS_TAREAS_EN:
        candidatos_raw = _resolver_tareas_list(
            consulta, filtros_entrada, tasks_store
        )
        candidatos_raw = _unique_stable_limit(candidatos_raw, _MAX_TASK_CANDIDATES)
        candidatos_serializados = [_candidate_from_task(t) for t in candidatos_raw]
    elif dominio_consulta_en in _DOMINIOS_NOTAS_EN:
        candidatos_raw = _resolver_notas_list(
            consulta, filtros_entrada, notes_store
        )
        candidatos_raw = _unique_stable_limit(candidatos_raw, _MAX_NOTE_CANDIDATES)
        candidatos_serializados = [_candidate_from_note(n) for n in candidatos_raw]

    return {
        "dominio": dominio_etiqueta or dominio_consulta_en or "",
        "consulta": consulta,
        "filtros": filtros_entrada.copy(),
        "candidatos": candidatos_serializados,
        "count": len(candidatos_serializados),
    }


def _resolver_calendario(
    consulta: str,
    filtros: dict[str, Any],
    events_store,
) -> list[dict[str, Any]]:
    if str(consulta or "").strip() not in _CONSULTAS_SOPORTADAS:
        return []
    q = consulta.strip()
    events_all = (
        events_store.list_events() if hasattr(events_store, "list_events") else []
    )
    people = _filtro_people(filtros)
    date_needle = filtros.get("date")
    time_needle = filtros.get("time")

    if q == "events_by_person":
        return [ev for ev in events_all if _matchea_person(ev, people)]

    if q == "events_by_date":
        if date_needle is None or str(date_needle).strip() == "":
            return []
        return [
            ev
            for ev in events_all
            if _matchea_fecha_ev(ev, str(date_needle).strip())
        ]

    if q == "events_by_person_and_time":
        out: list[dict[str, Any]] = []
        for ev in events_all:
            if not _matchea_person(ev, people):
                continue
            if time_needle is None or str(time_needle).strip() == "":
                continue
            if _matchea_tiempo(ev, time_needle):
                out.append(ev)
        return out

    return []


def _unique_stable_limit(
    rows: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Sin interpretación semántica: id único, orden estable por id, tope de recuento."""
    by_id: dict[str, dict[str, Any]] = {}
    for ev in rows:
        if not isinstance(ev, dict):
            continue
        eid = str(ev.get("id") or "").strip()
        if not eid or eid in by_id:
            continue
        by_id[eid] = ev
    sorted_ids = sorted(by_id.keys())
    out: list[dict[str, Any]] = []
    for i in sorted_ids:
        out.append(by_id[i])
        if len(out) >= limit:
            break
    return out


def _resolver_tareas_list(
    consulta: str,
    filtros: dict[str, Any],
    tasks_store,
) -> list[dict[str, Any]]:
    if str(consulta or "").strip() != _QUERY_TAREA_LIST_TASKS:
        return []
    lista = (
        tasks_store.list_tasks() if tasks_store is not None and hasattr(tasks_store, "list_tasks") else []
    )
    out: list[dict[str, Any]] = []
    for t in lista:
        if not isinstance(t, dict):
            continue
        if _FILTRO_COMPLETED in filtros:
            if bool(t.get("completed")) != bool(filtros.get(_FILTRO_COMPLETED)):
                continue
        title_f = filtros.get("title")
        if title_f is not None and str(title_f).strip():
            needle = str(title_f).strip().casefold()
            ttitle = str(t.get("title") or "").strip().casefold()
            if needle not in ttitle:
                continue
        date_needle = filtros.get("date")
        if date_needle is None or str(date_needle).strip() == "":
            date_needle = filtros.get("date_text")
        if date_needle is not None and str(date_needle).strip() != "":
            td = _task_date_text_plain(t.get("date_text"))
            if td is None:
                continue
            if _normalize_date_text_compare(str(date_needle)) != _normalize_date_text_compare(td):
                continue
        prio_f = filtros.get("priority")
        if prio_f is not None and str(prio_f).strip() != "":
            tp = t.get("priority")
            if tp is None or str(tp).strip() == "":
                continue
            if _norm_basico(tp) != _norm_basico(prio_f):
                continue
        iso_needle = filtros.get("date_iso")
        if iso_needle is not None and str(iso_needle).strip() != "":
            opt_needle = _opt_candidate_date_iso(iso_needle)
            if opt_needle is None:
                continue
            t_iso = _opt_candidate_date_iso(t.get("date_iso"))
            if t_iso != opt_needle:
                continue
        etiquetas_pedidas = _etiquetas_filtro_pedidas(filtros)
        if etiquetas_pedidas and not _nota_etiquetas_coinciden(
            t.get("tags"),
            etiquetas_pedidas,
        ):
            continue
        out.append(t)
    return out


_FILTRO_COMPLETED = "completed"


def _task_date_text_plain(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _candidate_from_task(t: dict[str, Any]) -> dict[str, Any]:
    eid = str(t.get("id") or "").strip()
    titulo = str(t.get("title") or "").strip()

    dt = _task_date_text_plain(t.get("date_text"))

    tm_raw = t.get("time_text")
    tm = (
        str(tm_raw).strip()
        if tm_raw is not None and str(tm_raw).strip()
        else ""
    )

    parts: list[str] = []
    if titulo:
        parts.append(titulo)
    if dt:
        parts.append(dt)
    if tm:
        parts.append(tm)
    label = " · ".join(parts)

    pr = t.get("priority")
    priority_out = (
        str(pr).strip()
        if pr is not None and str(pr).strip()
        else None
    )

    desc_raw = t.get("description")
    description_out = (
        str(desc_raw).strip()
        if desc_raw is not None and str(desc_raw).strip()
        else None
    )

    tags_out: list[str] = []
    tr = t.get("tags")
    if isinstance(tr, list):
        tags_out = [str(x).strip() for x in tr if str(x).strip()]

    di = _opt_candidate_date_iso(t.get("date_iso"))

    return {
        "id": eid,
        "label": label,
        "title": titulo or None,
        "description": description_out,
        "date_text": dt,
        "date_iso": di,
        "time_text": tm if tm else None,
        "priority": priority_out,
        "tags": tags_out,
        "completed": bool(t.get("completed")),
    }


def _resolver_notas_list(
    consulta: str,
    filtros: dict[str, Any],
    notes_store,
) -> list[dict[str, Any]]:
    if str(consulta or "").strip() != _QUERY_NOTA_LIST_NOTES:
        return []
    lista = (
        notes_store.list_notes()
        if notes_store is not None and hasattr(notes_store, "list_notes")
        else []
    )
    out: list[dict[str, Any]] = []
    for n in lista:
        if not isinstance(n, dict):
            continue
        if not _nota_pasa_filtros_tecnicos(n, filtros):
            continue
        out.append(n)
    return out


def _note_title_plain(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _etiquetas_filtro_pedidas(filtros: dict[str, Any]) -> list[str]:
    out: list[str] = []
    raw_tag = filtros.get("tag")
    if raw_tag is not None and str(raw_tag).strip():
        out.append(str(raw_tag).strip())
    rt = filtros.get("tags")
    if isinstance(rt, str):
        s = rt.strip()
        if s:
            out.append(s)
    elif isinstance(rt, list):
        for x in rt:
            sx = str(x).strip()
            if sx:
                out.append(sx)
    return out


def _nota_etiquetas_coinciden(note_tags: Any, etiquetas_pedidas: list[str]) -> bool:
    if not etiquetas_pedidas:
        return True
    if not isinstance(note_tags, list):
        return False
    note_fold = {
        str(t).strip().casefold() for t in note_tags if str(t).strip()
    }
    for ped in etiquetas_pedidas:
        if ped.casefold() not in note_fold:
            return False
    return True


def _nota_pasa_filtros_tecnicos(n: dict[str, Any], filtros: dict[str, Any]) -> bool:
    needle_text = filtros.get("text")
    if needle_text is None:
        needle_text = filtros.get("content")
    if needle_text is not None and str(needle_text).strip():
        ncf = str(needle_text).strip().casefold()
        tit_cf = str(n.get("title") or "").strip().casefold()
        cnt_cf = str(n.get("content") or "").strip().casefold()
        if ncf not in tit_cf and ncf not in cnt_cf:
            return False

    tit_fil = filtros.get("title")
    if tit_fil is not None and str(tit_fil).strip():
        nt = _note_title_plain(n.get("title"))
        if nt is None:
            return False
        nf = str(tit_fil).strip().casefold()
        ntc = nt.casefold()
        if nf != ntc and nf not in ntc:
            return False

    ped_tags = _etiquetas_filtro_pedidas(filtros)
    if ped_tags and not _nota_etiquetas_coinciden(n.get("tags"), ped_tags):
        return False

    return True


def _candidate_from_note(n: dict[str, Any]) -> dict[str, Any]:
    eid = str(n.get("id") or "").strip()
    titulo = _note_title_plain(n.get("title"))
    contenido = str(n.get("content") or "").strip()

    tags_out: list[str] = []
    tr = n.get("tags")
    if isinstance(tr, list):
        tags_out = [str(t).strip() for t in tr if str(t).strip()]

    parts: list[str] = []
    if titulo:
        parts.append(titulo)
    if contenido:
        parts.append(contenido)
    label = " · ".join(parts)

    cre = n.get("created_at")
    created_at = str(cre).strip() if cre is not None and str(cre).strip() else ""

    return {
        "id": eid,
        "label": label,
        "title": titulo or None,
        "content": contenido,
        "tags": tags_out,
        "created_at": created_at if created_at else None,
    }


def _filtro_people(filtros: dict[str, Any]) -> list[str]:
    raw = filtros.get("people")
    return _lista_normalizada(raw)


def _lista_normalizada(raw: Any) -> list[str]:
    out: list[str] = []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, list):
        for x in raw:
            sx = str(x).strip()
            if sx:
                out.append(sx)
    return out


def _titulo_txt(ev: dict[str, Any]) -> str:
    return _norm_basico(ev.get("title"))


def _date_txt(ev: dict[str, Any]) -> str | None:
    dt = ev.get("date_text")
    if dt is None:
        return None
    s = str(dt).strip()
    return s or None


def _participant_strs(ev: dict[str, Any]) -> list[str]:
    raw = ev.get("participants")
    if isinstance(raw, list):
        return [str(p).strip() for p in raw if str(p).strip()]
    return []


def _norm_basico(v: Any) -> str:
    return str(v or "").strip().lower()


def _matchea_person(ev: dict[str, Any], personas: Iterable[str]) -> bool:
    people_list = list(personas)
    if not people_list:
        return False
    titulo = _titulo_txt(ev)
    parts = [_norm_basico(p) for p in _participant_strs(ev)]
    for p in people_list:
        pn = _norm_basico(p)
        if not pn:
            continue
        if pn in titulo:
            return True
        for parte in parts:
            if not parte:
                continue
            if pn in parte or parte in pn:
                return True
    return False


def _normalize_date_text_compare(s: str) -> str:
    return " ".join(str(s).strip().split()).casefold()


def _matchea_fecha_ev(ev: dict[str, Any], filt_fecha: str) -> bool:
    ev_d = _date_txt(ev)
    if ev_d is None:
        return False
    return _normalize_date_text_compare(filt_fecha) == _normalize_date_text_compare(
        ev_d
    )


def _valor_t_normalizado(tiempo_evento: str | None) -> str | None:
    if tiempo_evento is None:
        return None
    s = str(tiempo_evento).strip().lower()
    return s or None


def _matchea_tiempo(ev: dict[str, Any], filtro_tiempo: Any) -> bool:
    f = _norm_basico(str(filtro_tiempo))
    if not f:
        return False
    ev_raw = ev.get("time_text")
    if ev_raw is None or str(ev_raw).strip() == "":
        return False
    t_ev = _valor_t_normalizado(str(ev_raw).strip())

    if f == "7":
        compat = _compatible_time_7
        return t_ev in compat if t_ev else False
    if f == "8":
        compat = _compatible_time_8
        return t_ev in compat if t_ev else False
    return t_ev == f if t_ev else False


def _candidate_from_event(ev: dict[str, Any]) -> dict[str, Any]:
    eid = str(ev.get("id") or "").strip()
    titulo = str(ev.get("title") or "").strip()
    dte = _date_txt(ev)

    tte_raw = ev.get("time_text")
    tte = (
        str(tte_raw).strip()
        if tte_raw is not None and str(tte_raw).strip()
        else ""
    )

    parts: list[str] = []
    if titulo:
        parts.append(titulo)
    if dte:
        parts.append(str(dte).strip())
    if tte:
        parts.append(str(tte).strip())
    label = " · ".join(parts)

    participants = [
        x for x in _participant_strs(ev) if x
    ]

    return {
        "id": eid,
        "label": label,
        "title": titulo or None,
        "date_text": dte,
        "date_iso": _opt_candidate_date_iso(ev.get("date_iso")),
        "time_text": (tte if tte else None),
        "participants": participants,
    }
