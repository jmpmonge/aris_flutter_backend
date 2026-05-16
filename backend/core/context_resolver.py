"""Resolución técnica de solicitudes de contexto estructuradas — sin semántica del raw del usuario.

events_by_date: comparación sólo contra **date_text** del evento (sin convertir calendarios).
Los valores habituales en filtros/date deben coincidir como texto con lo almacenado; p.ej.:
**hoy**, **mañana**, **lunes** … **domingo** si así figura en **date_text**.
"""

from __future__ import annotations

from typing import Any, Iterable

_MAX_CALENDAR_CANDIDATES = 5

_DOMINIO_CALENDARIO_EN = "calendar"
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
    del tasks_store, notes_store

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
        "time_text": (tte if tte else None),
        "participants": participants,
    }
