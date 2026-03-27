#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aktivitätsprotokoll — schreibt Einträge in tasks.db.aktivitaeten
Verwendung: from activity_log import log as alog
            alog("Mail", "Neue Mail", "kunde@x.de: Anfrage", "ok")
"""
import json, sqlite3
from pathlib import Path
from datetime import datetime, timedelta

SCRIPTS_DIR = Path(__file__).parent
TASKS_DB    = SCRIPTS_DIR.parent / "knowledge" / "tasks.db"
CONFIG_FILE = SCRIPTS_DIR / "config.json"

# Fallback-Werte — werden durch config.json überschrieben
# 0 = niemals löschen (Standard: Einträge dauerhaft behalten)
_DEFAULT_MAX = 0
_DEFAULT_DAYS = 0


def _get_limits():
    """Liest max_eintraege und tage aus config.json. 0 = kein Limit."""
    try:
        c = json.loads(CONFIG_FILE.read_text('utf-8'))
        p = c.get("protokoll", {})
        return (
            int(p.get("max_eintraege", _DEFAULT_MAX)),
            int(p.get("tage", _DEFAULT_DAYS)),
        )
    except Exception:
        return (_DEFAULT_MAX, _DEFAULT_DAYS)

def _ensure_table(db):
    db.execute("""CREATE TABLE IF NOT EXISTS aktivitaeten (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        zeitstempel  TEXT    NOT NULL,
        bereich      TEXT    NOT NULL,
        aktion       TEXT    NOT NULL,
        details      TEXT,
        status       TEXT    DEFAULT 'ok',
        fehler_text  TEXT,
        task_id      INTEGER,
        dauer_ms     INTEGER
    )""")
    try:
        db.execute("CREATE INDEX IF NOT EXISTS idx_akt_zeit    ON aktivitaeten(zeitstempel DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_akt_bereich ON aktivitaeten(bereich)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_akt_status  ON aktivitaeten(status)")
    except Exception:
        pass

def _cleanup(db):
    max_entries, keep_days = _get_limits()
    # Nach Alter löschen (wenn keep_days > 0)
    if keep_days > 0:
        cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat(timespec='seconds')
        db.execute("DELETE FROM aktivitaeten WHERE zeitstempel < ?", (cutoff,))
    # Nach Anzahl trimmen (wenn max_entries > 0)
    if max_entries > 0:
        count = db.execute("SELECT COUNT(*) FROM aktivitaeten").fetchone()[0]
        if count > max_entries:
            db.execute("""DELETE FROM aktivitaeten WHERE id IN (
                SELECT id FROM aktivitaeten ORDER BY zeitstempel ASC LIMIT ?)""",
                (count - max_entries + 500,))


def log(bereich, aktion, details="", status="ok", fehler="", task_id=None, dauer_ms=None):
    """Schreibt einen Aktivitätseintrag. Wirft NIE eine Exception."""
    try:
        db = sqlite3.connect(str(TASKS_DB), timeout=3)
        _ensure_table(db)
        db.execute(
            """INSERT INTO aktivitaeten
               (zeitstempel, bereich, aktion, details, status, fehler_text, task_id, dauer_ms)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                datetime.now().isoformat(timespec='seconds'),
                str(bereich)[:60],
                str(aktion)[:120],
                str(details or "")[:600],
                str(status),
                str(fehler)[:600] if fehler else None,
                task_id,
                dauer_ms,
            )
        )
        db.commit()
        # Trimmen alle 100 Einträge (liest config frisch)
        total = db.execute("SELECT COUNT(*) FROM aktivitaeten").fetchone()[0]
        if total > 0 and total % 100 == 0:
            _cleanup(db)
            db.commit()
        db.close()
    except Exception:
        pass  # Protokoll darf die App NIE crashen


def get_entries(limit=200, offset=0, bereich=None, status=None):
    """Liest Protokoll-Einträge (für API)."""
    try:
        db = sqlite3.connect(str(TASKS_DB), timeout=3)
        db.row_factory = sqlite3.Row
        _ensure_table(db)
        where, params = [], []
        if bereich:
            where.append("bereich=?"); params.append(bereich)
        if status:
            where.append("status=?"); params.append(status)
        sql = "SELECT * FROM aktivitaeten"
        if where: sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY zeitstempel DESC LIMIT ? OFFSET ?"
        rows = db.execute(sql, params + [limit, offset]).fetchall()
        db.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_stats():
    """Kurze Statistik für das Header-Widget."""
    try:
        db = sqlite3.connect(str(TASKS_DB), timeout=3)
        _ensure_table(db)
        total  = db.execute("SELECT COUNT(*) FROM aktivitaeten").fetchone()[0]
        fehler = db.execute("SELECT COUNT(*) FROM aktivitaeten WHERE status='fehler'").fetchone()[0]
        letzte = db.execute("SELECT zeitstempel FROM aktivitaeten ORDER BY id DESC LIMIT 1").fetchone()
        db.close()
        return {"total": total, "fehler": fehler, "letzte": letzte[0] if letzte else None}
    except Exception:
        return {"total": 0, "fehler": 0, "letzte": None}
