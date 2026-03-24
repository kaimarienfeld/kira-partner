#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task Manager für rauMKult® Assistenz – v2 (neues Schema)
Verwaltet Tasks in tasks.db (Schema wird von rebuild_all.py erstellt).
"""
import sqlite3, json
from pathlib import Path
from datetime import datetime, timedelta

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
SCRIPTS_DIR   = Path(__file__).parent

TASK_STATUS = {
    "offen":      "Offen",
    "erledigt":   "Erledigt",
    "ignorieren": "Ignoriert",
    "spaeter":    "Erinnere später",
}

# ── Datenbank Setup ────────────────────────────────────────────────────────────
def get_tasks_db():
    """Verbindet sich mit tasks.db. Schema wird von rebuild_all.py erstellt."""
    db = sqlite3.connect(str(KNOWLEDGE_DIR / "tasks.db"))
    db.row_factory = sqlite3.Row
    return db


def update_task_status(task_id: int, status: str, notiz: str = "") -> bool:
    """Aktualisiert den Status einer Aufgabe."""
    if status not in TASK_STATUS:
        return False
    db = get_tasks_db()
    now = datetime.now().isoformat()
    erledigt = now if status == "erledigt" else None

    config = load_config()
    stunden = config.get("aufgaben", {}).get("erinnerung_intervall_stunden", 24)
    naechste = None if status in ("erledigt", "ignorieren") else \
               (datetime.now() + timedelta(hours=stunden)).isoformat()

    db.execute("""UPDATE tasks SET status=?, aktualisiert_am=?, erledigt_am=?,
                  naechste_erinnerung=?, notiz=CASE WHEN ?!='' THEN ? ELSE notiz END
                  WHERE id=?""",
               (status, now, erledigt, naechste,
                notiz, notiz, task_id))
    db.commit()
    db.close()
    return True


def get_open_tasks(kategorien: list = None) -> list:
    """Gibt alle offenen Aufgaben zurück, optional gefiltert nach Kategorie."""
    db = get_tasks_db()
    where = "WHERE status = 'offen'"
    params = []
    if kategorien:
        placeholders = ",".join("?" * len(kategorien))
        where += f" AND kategorie IN ({placeholders})"
        params = kategorien
    rows = db.execute(
        f"SELECT * FROM tasks {where} ORDER BY prioritaet DESC, datum_mail DESC",
        params
    ).fetchall()
    result = [dict(r) for r in rows]
    db.close()
    return result


def get_due_reminders() -> list:
    """Gibt Aufgaben zurück, bei denen eine Erinnerung fällig ist."""
    db = get_tasks_db()
    now = datetime.now().isoformat()
    rows = db.execute("""SELECT * FROM tasks
                         WHERE status = 'offen'
                         AND naechste_erinnerung IS NOT NULL
                         AND naechste_erinnerung <= ?
                         ORDER BY datum_mail""", (now,)).fetchall()
    result = [dict(r) for r in rows]
    db.close()
    return result


def increment_reminder(task_id: int):
    """Erhöht Erinnerungszähler und setzt nächste Erinnerung."""
    config = load_config()
    stunden = config.get("aufgaben", {}).get("erinnerung_intervall_stunden", 24)
    naechste = (datetime.now() + timedelta(hours=stunden)).isoformat()
    db = get_tasks_db()
    db.execute("UPDATE tasks SET erinnerungen=erinnerungen+1, naechste_erinnerung=? WHERE id=?",
               (naechste, task_id))
    db.commit()
    db.close()


def load_config() -> dict:
    try:
        return json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
    except:
        return {}
