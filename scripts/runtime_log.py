#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runtime_log.py — Kira Runtime Event Store
==========================================
Vollstaendiges, lueckenloses Ereignisprotokoll fuer das gesamte Kira-System.
Zwei Tabellen: events (Metadaten) + event_payloads (Vollkontext).

Event-Typen:
  ui       — Browser-Events: Panel, Kira oeffnen, Status-Aenderung, Formular
  kira     — Kira-Chat, Tool-Aufruf, Kontext-Uebergabe, Entwurf, Vorschlag
  llm      — Provider, Modell, Tokens, Dauer, Fallback, Fehler
  system   — Server-Start/-Stop, Hintergrundjobs, Mail-Monitor, daily_check
  settings — Einstellungaenderungen mit Vor-/Nachwert

Verwendung:
    from runtime_log import elog, eget, eget_payload, estats

    eid = elog('kira', 'chat_completed', 'Kira beantwortet Frage zu RE-2026-001',
        session_id='abc', modul='kira', context_type='rechnung', context_id='42',
        provider='Anthropic', model='claude-sonnet-4',
        token_in=1500, token_out=300, duration_ms=2100,
        user_input='Was ist der Status von RE-2026-001?',
        assistant_output='Die Rechnung RE-2026-001...')

    payload = eget_payload(eid)  # dict mit allen Vollkontext-Inhalten
"""

import json
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime
from threading import Lock

SCRIPTS_DIR = Path(__file__).parent
EVENTS_DB   = SCRIPTS_DIR.parent / "knowledge" / "runtime_events.db"
CONFIG_FILE = SCRIPTS_DIR / "config.json"

_lock = Lock()
_db_initialized = False  # True nach erstem Schema-Setup — verhindert wiederholte COMMITs

# ── Config ────────────────────────────────────────────────────────────────────

def _get_cfg() -> dict:
    """Liest runtime_log-Konfiguration. Cachefrei — immer frisch lesen."""
    try:
        c = json.loads(CONFIG_FILE.read_text("utf-8"))
        return c.get("runtime_log", {})
    except Exception:
        return {}


def _is_enabled(event_type: str, status: str = "ok") -> bool:
    cfg = _get_cfg()
    # Fehler immer loggen (wenn konfiguriert)
    if status in ("fehler", "error", "partial_failure"):
        if cfg.get("fehler_immer_loggen", True):
            return True
    # Gesamt-Schalter
    if not cfg.get("aktiv", True):
        return False
    type_flags = {
        "ui":       cfg.get("ui_events",            True),
        "kira":     cfg.get("kira_events",           True),
        "llm":      cfg.get("llm_events",            True),
        "system":   cfg.get("hintergrund_events",    True),
        "settings": cfg.get("settings_events",       True),
    }
    return type_flags.get(event_type, True)


def _vollkontext_aktiv() -> bool:
    return _get_cfg().get("vollkontext_speichern", True)


# ── DB-Schema ────────────────────────────────────────────────────────────────

def _ensure_db(db: sqlite3.Connection) -> None:
    global _db_initialized
    # Verbindungs-Einstellungen (per Connection, kein Commit nötig)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA wal_autocheckpoint=100")  # Checkpoint alle 100 Pages (~400 KB) statt 1000
    if _db_initialized:
        return  # Schema existiert bereits — kein erneutes CREATE + COMMIT
    db.execute("""CREATE TABLE IF NOT EXISTS events (
        id               TEXT    PRIMARY KEY,
        ts               TEXT    NOT NULL,
        session_id       TEXT,
        event_type       TEXT    NOT NULL,
        source           TEXT,
        modul            TEXT,
        submodul         TEXT,
        actor_type       TEXT    DEFAULT 'system',
        context_type     TEXT,
        context_id       TEXT,
        action           TEXT    NOT NULL,
        status           TEXT    DEFAULT 'ok',
        result           TEXT,
        summary          TEXT,
        provider         TEXT,
        model            TEXT,
        token_in         INTEGER DEFAULT 0,
        token_out        INTEGER DEFAULT 0,
        duration_ms      INTEGER,
        error_code       TEXT,
        error_message    TEXT,
        follow_up        INTEGER DEFAULT 0,
        related_event_id TEXT,
        has_payload      INTEGER DEFAULT 0
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS event_payloads (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id     TEXT    NOT NULL,
        payload_type TEXT    NOT NULL,
        content      TEXT
    )""")
    for name, col in [
        ("idx_ev_ts",      "ts DESC"),
        ("idx_ev_type",    "event_type"),
        ("idx_ev_session", "session_id"),
        ("idx_ev_modul",   "modul"),
        ("idx_ev_ctx",     "context_type, context_id"),
        ("idx_ev_action",  "action"),
        ("idx_ev_status",  "status"),
    ]:
        try:
            db.execute(f"CREATE INDEX IF NOT EXISTS {name} ON events({col})")
        except Exception:
            pass
    try:
        db.execute("CREATE INDEX IF NOT EXISTS idx_ep_eid ON event_payloads(event_id)")
    except Exception:
        pass
    db.commit()
    _db_initialized = True


# ── Haupt-Schreib-Funktion ────────────────────────────────────────────────────

def elog(
    event_type: str,
    action: str,
    summary: str = "",
    *,
    session_id: str = None,
    source: str = None,
    modul: str = None,
    submodul: str = None,
    actor_type: str = "system",
    context_type: str = None,
    context_id = None,
    status: str = "ok",
    result: str = None,
    provider: str = None,
    model: str = None,
    token_in: int = 0,
    token_out: int = 0,
    duration_ms: int = None,
    error_code: str = None,
    error_message: str = None,
    follow_up: bool = False,
    related_event_id: str = None,
    # Vollkontext-Payloads
    user_input: str = None,
    assistant_output: str = None,
    context_snapshot = None,
    entity_snapshot = None,
    settings_before = None,
    settings_after = None,
    mail_body: str = None,
    thread_excerpt: str = None,
    raw_request = None,
    raw_response = None,
) -> str:
    """
    Schreibt einen Runtime-Event-Eintrag.
    Gibt die event_id zurueck (leerer String bei Fehler oder Unterdrückung).
    Wirft NIE eine Exception.
    """
    if not _is_enabled(event_type, status):
        return ""

    event_id = str(uuid.uuid4())
    now = datetime.now().isoformat(timespec="milliseconds")

    # Payloads aufbereiten
    payloads: dict = {}
    if _vollkontext_aktiv():
        def _j(v):
            if v is None: return None
            if isinstance(v, str): return v
            try: return json.dumps(v, ensure_ascii=False)
            except Exception: return str(v)

        if user_input:                    payloads["user_input"]         = user_input
        if assistant_output:              payloads["assistant_output"]   = assistant_output
        if context_snapshot is not None:  payloads["context_snapshot"]   = _j(context_snapshot)
        if entity_snapshot  is not None:  payloads["entity_snapshot"]    = _j(entity_snapshot)
        if settings_before  is not None:  payloads["settings_before"]    = _j(settings_before)
        if settings_after   is not None:  payloads["settings_after"]     = _j(settings_after)
        if mail_body:                     payloads["mail_body"]           = mail_body
        if thread_excerpt:                payloads["thread_excerpt"]      = thread_excerpt
        if raw_request      is not None:  payloads["raw_request"]         = _j(raw_request)
        if raw_response     is not None:  payloads["raw_response"]        = _j(raw_response)

    try:
        with _lock:
            db = sqlite3.connect(str(EVENTS_DB), timeout=5)
            _ensure_db(db)
            db.execute(
                """INSERT INTO events
                   (id, ts, session_id, event_type, source, modul, submodul, actor_type,
                    context_type, context_id, action, status, result, summary,
                    provider, model, token_in, token_out, duration_ms,
                    error_code, error_message, follow_up, related_event_id, has_payload)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id, now, session_id, event_type, source, modul, submodul, actor_type,
                    context_type, str(context_id) if context_id is not None else None,
                    action, status,
                    str(result)[:500]       if result        else None,
                    str(summary)[:500]      if summary       else None,
                    provider, model,
                    token_in or 0, token_out or 0, duration_ms,
                    error_code,
                    str(error_message)[:1000] if error_message else None,
                    1 if follow_up else 0,
                    related_event_id,
                    1 if payloads else 0,
                ),
            )
            for ptype, content in payloads.items():
                if content is not None:
                    db.execute(
                        "INSERT INTO event_payloads (event_id, payload_type, content) VALUES (?,?,?)",
                        (event_id, ptype, content),
                    )
            db.commit()
            db.close()
    except Exception:
        return ""

    return event_id


# ── Lese-Funktionen ───────────────────────────────────────────────────────────

def eget(
    limit: int = 50,
    offset: int = 0,
    event_type: str = None,
    modul: str = None,
    session_id: str = None,
    context_type: str = None,
    context_id: str = None,
    status: str = None,
    action: str = None,
    source: str = None,
    provider: str = None,
    search: str = None,
    include_payloads: bool = False,
) -> dict:
    """Liest Events mit optionalen Filtern. Neueste zuerst."""
    try:
        db = sqlite3.connect(str(EVENTS_DB), timeout=5)
        db.row_factory = sqlite3.Row
        _ensure_db(db)

        where, params = [], []
        if event_type:   where.append("event_type=?");   params.append(event_type)
        if modul:        where.append("modul=?");         params.append(modul)
        if session_id:   where.append("session_id=?");    params.append(session_id)
        if context_type: where.append("context_type=?"); params.append(context_type)
        if context_id:   where.append("context_id=?");   params.append(str(context_id))
        if status:       where.append("status=?");        params.append(status)
        if action:       where.append("action=?");        params.append(action)
        if source:       where.append("source=?");        params.append(source)
        if provider:     where.append("provider=?");      params.append(provider)
        if search:
            where.append("(summary LIKE ? OR result LIKE ? OR action LIKE ? OR context_id LIKE ?)")
            s = f"%{search}%"
            params += [s, s, s, s]

        wc = (" WHERE " + " AND ".join(where)) if where else ""
        total = db.execute(f"SELECT COUNT(*) FROM events{wc}", params).fetchone()[0]
        rows  = db.execute(
            f"SELECT * FROM events{wc} ORDER BY ts DESC LIMIT ? OFFSET ?",
            params + [limit, offset]
        ).fetchall()

        entries = [dict(r) for r in rows]

        if include_payloads:
            for e in entries:
                if e.get("has_payload"):
                    pr = db.execute(
                        "SELECT payload_type, content FROM event_payloads WHERE event_id=?",
                        (e["id"],),
                    ).fetchall()
                    e["payloads"] = {r["payload_type"]: r["content"] for r in pr}
                else:
                    e["payloads"] = {}

        db.close()
        return {"entries": entries, "total": total}
    except Exception:
        return {"entries": [], "total": 0}


def eget_payload(event_id: str) -> dict:
    """Laedt alle Payloads fuer einen Event."""
    try:
        db = sqlite3.connect(str(EVENTS_DB), timeout=5)
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT payload_type, content FROM event_payloads WHERE event_id=?",
            (event_id,),
        ).fetchall()
        db.close()
        return {r["payload_type"]: r["content"] for r in rows}
    except Exception:
        return {}


def estats() -> dict:
    """Statistiken fuer UI-Header und Einstellungen-Anzeige."""
    try:
        db = sqlite3.connect(str(EVENTS_DB), timeout=5)
        _ensure_db(db)

        total = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        fehler = db.execute(
            "SELECT COUNT(*) FROM events WHERE status IN ('fehler','error','partial_failure')"
        ).fetchone()[0]
        last_row = db.execute("SELECT ts FROM events ORDER BY ts DESC LIMIT 1").fetchone()
        last = last_row[0] if last_row else None

        today = datetime.now().strftime("%Y-%m-%d")
        heute = db.execute(
            "SELECT COUNT(*) FROM events WHERE ts LIKE ?", (f"{today}%",)
        ).fetchone()[0]
        sessions = db.execute(
            "SELECT COUNT(DISTINCT session_id) FROM events WHERE session_id IS NOT NULL"
        ).fetchone()[0]
        with_payload = db.execute(
            "SELECT COUNT(*) FROM events WHERE has_payload=1"
        ).fetchone()[0]

        by_type: dict = {}
        for row in db.execute("SELECT event_type, COUNT(*) FROM events GROUP BY event_type"):
            by_type[row[0]] = row[1]

        by_modul: dict = {}
        for row in db.execute(
            "SELECT modul, COUNT(*) FROM events WHERE modul IS NOT NULL GROUP BY modul ORDER BY 2 DESC LIMIT 20"
        ):
            by_modul[row[0]] = row[1]

        types    = sorted(by_type.keys())
        moduls   = sorted(by_modul.keys())
        sources  = [r[0] for r in db.execute(
            "SELECT DISTINCT source FROM events WHERE source IS NOT NULL ORDER BY source"
        ).fetchall()]
        providers = [r[0] for r in db.execute(
            "SELECT DISTINCT provider FROM events WHERE provider IS NOT NULL ORDER BY provider"
        ).fetchall()]

        # Events-DB Dateigröße
        db_path = EVENTS_DB
        try:
            db_bytes = db_path.stat().st_size
            if   db_bytes < 1024:       db_size = f"{db_bytes} B"
            elif db_bytes < 1024**2:    db_size = f"{db_bytes/1024:.1f} KB"
            else:                       db_size = f"{db_bytes/1024**2:.2f} MB"
        except Exception:
            db_size = "?"

        db.close()
        return {
            "total":        total,
            "fehler":       fehler,
            "last":         last,
            "heute":        heute,
            "sessions":     sessions,
            "with_payload": with_payload,
            "by_type":      by_type,
            "by_modul":     by_modul,
            "types":        types,
            "moduls":       moduls,
            "sources":      sources,
            "providers":    providers,
            "db_size":      db_size,
        }
    except Exception:
        return {
            "total": 0, "fehler": 0, "last": None, "heute": 0, "sessions": 0,
            "with_payload": 0, "by_type": {}, "by_modul": {}, "types": [], "moduls": [],
            "sources": [], "providers": [], "db_size": "?",
        }


def get_recent_for_kira(limit: int = 30, session_id: str = None) -> str:
    """
    Gibt die letzten Events als lesbaren Text zurueck — fuer Kiras Systemkontext.
    Kira kann so Konversations-Historie, Tool-Nutzung und Hintergrund-Ereignisse sehen.
    """
    try:
        data = eget(limit=limit, session_id=session_id)
        entries = data.get("entries", [])
        if not entries:
            return ""
        lines = ["LETZTE SYSTEM-EREIGNISSE (Runtime-Log):"]
        for e in entries:
            ts      = (e.get("ts") or "")[:16]
            et      = e.get("event_type", "?")
            action  = e.get("action", "?")
            summary = e.get("summary", "")
            status  = e.get("status", "ok")
            ctx     = (f" [{e['context_type']}:{e['context_id']}]"
                       if e.get("context_type") and e.get("context_id") else "")
            tok     = (f" | {e['token_in']}\u2192{e['token_out']} Tok"
                       if e.get("token_in") else "")
            prov    = f" [{e['provider']}/{e['model']}]" if e.get("provider") else ""
            line    = f"  {ts} [{et}] {action}{ctx}{prov}: {summary}{tok}"
            if status not in ("ok", "success"):
                line += f" \u26a0 {status}"
            lines.append(line)
        return "\n".join(lines)
    except Exception:
        return ""


def _clear_all() -> None:
    """Löscht alle Events aus der DB. Nur für manuelle Bereinigung via UI."""
    with _lock:
        try:
            db = sqlite3.connect(str(EVENTS_DB), timeout=10)
            _ensure_db(db)
            db.execute("DELETE FROM events")
            db.execute("DELETE FROM event_payloads")
            db.commit()  # Commit BEFORE VACUUM — VACUUM needs exclusive lock and may fail in WAL mode
            db.close()
        except Exception:
            pass
        try:
            db2 = sqlite3.connect(str(EVENTS_DB), timeout=5)
            db2.execute("VACUUM")
            db2.close()
        except Exception:
            pass  # VACUUM is best-effort; DELETEs already committed above


# ── Config-Defaults sicherstellen ─────────────────────────────────────────────

def ensure_config_defaults() -> None:
    """
    Stellt sicher, dass config.json einen 'runtime_log'-Block enthaelt.
    Wird beim Server-Start aufgerufen.
    """
    try:
        c = json.loads(CONFIG_FILE.read_text("utf-8"))
    except Exception:
        c = {}
    if "runtime_log" not in c:
        c["runtime_log"] = {
            "aktiv":                True,
            "ui_events":            True,
            "kira_events":          True,
            "llm_events":           True,
            "hintergrund_events":   True,
            "settings_events":      True,
            "fehler_immer_loggen":  True,
            "vollkontext_speichern": True,
            "kira_darf_lesen":      True,
        }
        try:
            CONFIG_FILE.write_text(json.dumps(c, ensure_ascii=False, indent=2), "utf-8")
        except Exception:
            pass
