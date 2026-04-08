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
    "offen":        "Offen",
    "erledigt":     "Erledigt",
    "ignorieren":   "Ignoriert",
    "spaeter":      "Erinnere später",
    "zur_kenntnis": "Zur Kenntnis genommen",
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
    try:
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
    finally:
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
    try:
        db.execute("UPDATE tasks SET erinnerungen=erinnerungen+1, naechste_erinnerung=? WHERE id=?",
                   (naechste, task_id))
        db.commit()
    finally:
        db.close()


def load_config() -> dict:
    try:
        return json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
    except Exception:
        return {}


def get_active_profile(config=None) -> dict:
    """Gibt das aktive Benutzerprofil zurück. Fallback auf Legacy-Felder.

    Zentrale Funktion — alle Module importieren diese statt hardcoded Werte.
    Rückgabe-Struktur:
    {
        "firma_name": str,
        "firma_branche": str,
        "firma_beschreibung": str,
        "team": [{"name": str, "rolle": str, "email_konten": [str],
                  "anrede_varianten": [str], "ist_admin": bool}],
        "eigene_domains": [str],
        "social_media": {}
    }
    """
    if not config:
        config = load_config()
    bp = config.get("benutzer_profile", {})
    aktiv = bp.get("aktives_profil", "profil_1")
    profil = bp.get("profile", {}).get(aktiv)
    if profil and profil.get("team"):
        return profil
    # Fallback: Legacy-Felder zu Profil-Struktur konvertieren
    konten = []
    cp = config.get("combined_postfach", {})
    if isinstance(cp, dict):
        konten = cp.get("konten", [])
    inhaber_name = config.get("firma_inhaber", "")
    return {
        "firma_name": config.get("firma_name", ""),
        "firma_branche": config.get("firma_branche", ""),
        "firma_beschreibung": config.get("firma_beschreibung", ""),
        "team": [{
            "name": inhaber_name,
            "rolle": "Inhaber",
            "email_konten": konten if isinstance(konten, list) else [],
            "anrede_varianten": [],
            "ist_admin": True
        }],
        "eigene_domains": config.get("mail_klassifizierung", {}).get("eigene_domains_extra", []),
        "social_media": {}
    }
