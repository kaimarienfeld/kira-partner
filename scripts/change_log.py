#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mikrogranulares append-only Änderungslog — change_log.py
=========================================================
Zentrale Schnittstelle für change_log.jsonl.

Verwendung (Kurzform):
    from change_log import clog
    clog(feature_id="ui-geschaeft-02-kpi", modul="geschaeft",
         action="css_class_added", scope="css",
         location="CSS /* ═══ Geschaeft ═══ */ — .gh-kpi-card",
         files=["scripts/server.py"],
         summary="Neue CSS-Klasse .gh-kpi-card hinzugefügt",
         details=["3-spaltige KPI-Karte mit alarm-State", "cursor:pointer, transition"],
         result="success", status_before="fehlte", status_after="done",
         test_status="visual_ok")

result-Werte (Pflicht):
    success | partial_success | partial_failure | failed | reverted | skipped

test_status-Werte:
    not_tested | visual_ok | functional_ok | failed | skipped

action-Beispiele (micro):
    css_class_added | css_class_changed | css_class_removed
    html_element_added | html_element_changed | html_element_removed
    js_function_added | js_function_changed | event_handler_added
    python_function_added | python_function_changed | python_function_removed
    api_endpoint_added | api_endpoint_changed
    button_added | filter_added | tab_added | tab_wired
    kira_context_added | status_badge_added | layout_changed
    config_changed | file_updated | file_migrated | bugfix
    attempt_failed | attempt_partial | reverted
"""
import json
from pathlib import Path
from datetime import datetime

SCRIPTS_DIR = Path(__file__).parent
CHANGE_LOG  = SCRIPTS_DIR.parent / "change_log.jsonl"

# Session-ID — wird einmal pro Server-Start gesetzt, danach konstant
_SESSION_ID: str = ""


def set_session(session_id: str) -> None:
    """Setzt die Session-ID für alle nachfolgenden Einträge."""
    global _SESSION_ID
    _SESSION_ID = session_id


def _current_session() -> str:
    global _SESSION_ID
    if not _SESSION_ID:
        _SESSION_ID = "session-" + datetime.now().strftime("%Y-%m-%d") + "-auto"
    return _SESSION_ID


# ── Haupt-Append-Funktion ─────────────────────────────────────────────────────

def append(entry: dict) -> bool:
    """
    Hängt einen validierten Eintrag an change_log.jsonl an.
    Wirft NIE eine Exception. Gibt True bei Erfolg zurück.
    """
    try:
        now = datetime.now().isoformat(timespec='seconds')
        details = entry.get("details", [])
        if isinstance(details, str):
            details = [details]

        e = {
            "timestamp":     entry.get("timestamp",     now),
            "session_id":    entry.get("session_id",    _current_session()),
            "feature_id":    entry.get("feature_id",    ""),
            "modul":         entry.get("modul",          ""),
            "action":        entry.get("action",         ""),
            "scope":         entry.get("scope",          ""),
            "files":         entry.get("files",          []),
            "location":      entry.get("location",       ""),
            "summary":       entry.get("summary",        ""),
            "details":       details,
            "result":        entry.get("result",         "success"),
            "status_before": entry.get("status_before",  ""),
            "status_after":  entry.get("status_after",   ""),
            "test_status":   entry.get("test_status",    "not_tested"),
            "follow_up":     entry.get("follow_up",      []),
            "related_todos": entry.get("related_todos",  []),
        }
        line = json.dumps(e, ensure_ascii=False, separators=(',', ':')) + "\n"
        with open(CHANGE_LOG, "a", encoding="utf-8") as f:
            f.write(line)
        return True
    except Exception:
        return False


# ── Kurzform ──────────────────────────────────────────────────────────────────

def clog(
    feature_id: str,
    modul: str,
    action: str,
    summary: str,
    *,
    scope: str = "",
    location: str = "",
    files: list = None,
    details=None,
    result: str = "success",
    status_before: str = "",
    status_after: str = "",
    test_status: str = "not_tested",
    follow_up: list = None,
    related_todos: list = None,
    session_id: str = "",
) -> bool:
    """
    Kurzform für append(). Bevorzugte API.
    details kann str ODER list sein — wird bei str automatisch gewrapped.
    """
    if isinstance(details, str):
        details = [details]
    entry = {
        "feature_id":    feature_id,
        "modul":         modul,
        "action":        action,
        "scope":         scope,
        "location":      location,
        "files":         files or [],
        "summary":       summary,
        "details":       details or [],
        "result":        result,
        "status_before": status_before,
        "status_after":  status_after,
        "test_status":   test_status,
        "follow_up":     follow_up or [],
        "related_todos": related_todos or [],
    }
    if session_id:
        entry["session_id"] = session_id
    return append(entry)


# ── Lese-Funktionen ───────────────────────────────────────────────────────────

def get_entries(
    limit: int = 50,
    offset: int = 0,
    modul: str = "",
    feature_id: str = "",
    result: str = "",
    action: str = "",
    search: str = "",
) -> dict:
    """
    Liest gefilterte Einträge aus change_log.jsonl.
    Gibt Einträge neueste-zuerst zurück.
    """
    try:
        raw = [l for l in CHANGE_LOG.read_text("utf-8").split("\n") if l.strip()]
        total_raw = len(raw)
        parsed = []
        for line in reversed(raw):
            try:
                e = json.loads(line)
            except Exception:
                continue
            if modul      and e.get("modul")      != modul:      continue
            if feature_id and e.get("feature_id") != feature_id: continue
            if result     and e.get("result")     != result:     continue
            if action     and e.get("action")     != action:     continue
            if search:
                det = e.get("details", [])
                det_str = " ".join(det) if isinstance(det, list) else str(det)
                haystack = (
                    e.get("summary",  "") + " " +
                    e.get("location", "") + " " +
                    det_str
                ).lower()
                if search.lower() not in haystack:
                    continue
            parsed.append(e)
        total_filtered = len(parsed)
        page = parsed[offset: offset + limit]
        return {"entries": page, "total": total_filtered, "total_raw": total_raw}
    except Exception:
        return {"entries": [], "total": 0, "total_raw": 0}


def get_stats() -> dict:
    """Statistik-Zusammenfassung für UI-Header."""
    try:
        raw = [l for l in CHANGE_LOG.read_text("utf-8").split("\n") if l.strip()]
        entries = []
        for line in raw:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
        total = len(entries)
        last  = entries[-1].get("timestamp", "")[:10] if entries else ""
        by_result: dict = {}
        by_modul:  dict = {}
        for e in entries:
            r = e.get("result", "")
            m = e.get("modul",  "")
            if r: by_result[r] = by_result.get(r, 0) + 1
            if m: by_modul[m]  = by_modul.get(m,  0) + 1
        moduls   = sorted({e.get("modul",      "") for e in entries if e.get("modul",      "")})
        results  = sorted({e.get("result",     "") for e in entries if e.get("result",     "")})
        features = sorted({e.get("feature_id", "") for e in entries if e.get("feature_id", "")})
        actions  = sorted({e.get("action",     "") for e in entries if e.get("action",     "")})
        return {
            "total":      total,
            "last":       last,
            "by_result":  by_result,
            "by_modul":   by_modul,
            "moduls":     moduls,
            "results":    results,
            "features":   features,
            "actions":    actions,
        }
    except Exception:
        return {
            "total": 0, "last": "", "by_result": {}, "by_modul": {},
            "moduls": [], "results": [], "features": [], "actions": [],
        }
