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
        "social_media": {},
        "leistungen": {
            "website_url": str,
            "letzte_aktualisierung": str,
            "katalog": [{"name": str, "beschreibung": str, "stichworte": [str],
                         "zielgruppe": str, "ist_kernleistung": bool}],
            "nicht_leistungen": [str],
            "quelle": str
        }
    }
    """
    if not config:
        config = load_config()
    bp = config.get("benutzer_profile", {})
    aktiv = bp.get("aktives_profil", "profil_1")
    profil = bp.get("profile", {}).get(aktiv)
    if profil and profil.get("team"):
        # Sicherstellen dass leistungen-Feld existiert
        if "leistungen" not in profil:
            profil["leistungen"] = {"katalog": [], "nicht_leistungen": [], "website_url": "", "quelle": ""}
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
        "social_media": {},
        "leistungen": {"katalog": [], "nicht_leistungen": [], "website_url": "", "quelle": ""}
    }


# ── Standard-Kategorien ──────────────────────────────────────────────────────
STANDARD_KATEGORIEN = [
    {"name": "Antwort erforderlich", "ist_standard": True, "farbe": "#ef4444", "css_class": "kat-antwort"},
    {"name": "Neue Lead-Anfrage", "ist_standard": True, "farbe": "#f97316", "css_class": "kat-lead"},
    {"name": "Angebotsrückmeldung", "ist_standard": True, "farbe": "#eab308", "css_class": "kat-angebot"},
    {"name": "Rechnung / Beleg", "ist_standard": True, "farbe": "#22c55e", "css_class": "kat-rechnung"},
    {"name": "Shop / System", "ist_standard": True, "farbe": "#6366f1", "css_class": "kat-shop"},
    {"name": "Newsletter / Werbung", "ist_standard": True, "farbe": "#94a3b8", "css_class": "kat-newsletter"},
    {"name": "Zur Kenntnis", "ist_standard": True, "farbe": "#06b6d4", "css_class": "kat-kenntnis"},
    {"name": "Abgeschlossen", "ist_standard": True, "farbe": "#10b981", "css_class": "kat-abgeschlossen"},
    {"name": "Ignorieren", "ist_standard": True, "farbe": "#64748b", "css_class": "kat-ignorieren"},
]


def _ensure_kategorien_table():
    """Erstellt die kategorien-Tabelle in tasks.db falls nicht vorhanden, seed Standard-Kategorien."""
    db_path = KNOWLEDGE_DIR / "tasks.db"
    if not db_path.exists():
        return
    db = sqlite3.connect(str(db_path))
    db.execute("""CREATE TABLE IF NOT EXISTS kategorien (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL UNIQUE,
        ist_standard    INTEGER DEFAULT 0,
        ist_dynamisch   INTEGER DEFAULT 0,
        lernphase       INTEGER DEFAULT 1,
        anzahl_zuweisungen INTEGER DEFAULT 0,
        erstellt_am     TEXT DEFAULT CURRENT_TIMESTAMP,
        promoted_am     TEXT,
        beschreibung    TEXT,
        farbe           TEXT,
        css_class       TEXT
    )""")
    # Standard-Kategorien seeden (falls leer)
    existing = db.execute("SELECT COUNT(*) FROM kategorien").fetchone()[0]
    if existing == 0:
        for k in STANDARD_KATEGORIEN:
            db.execute(
                "INSERT OR IGNORE INTO kategorien (name, ist_standard, ist_dynamisch, lernphase, farbe, css_class) "
                "VALUES (?,1,0,0,?,?)",
                (k["name"], k.get("farbe", ""), k.get("css_class", "")))
    db.commit()
    db.close()


_kategorien_cache = None
_kategorien_cache_ts = 0


def get_kategorien(include_lernphase=True) -> list:
    """Gibt alle aktiven Kategorien zurück (Standard + dynamische). Cached 60s."""
    global _kategorien_cache, _kategorien_cache_ts
    import time
    now = time.time()
    if _kategorien_cache is not None and (now - _kategorien_cache_ts) < 60:
        if include_lernphase:
            return _kategorien_cache
        return [k for k in _kategorien_cache if not k.get("lernphase")]

    _ensure_kategorien_table()
    db_path = KNOWLEDGE_DIR / "tasks.db"
    if not db_path.exists():
        return [{"name": k["name"], "ist_standard": True, "lernphase": False} for k in STANDARD_KATEGORIEN]
    try:
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT * FROM kategorien ORDER BY ist_standard DESC, anzahl_zuweisungen DESC").fetchall()
        db.close()
        result = [dict(r) for r in rows]
        _kategorien_cache = result
        _kategorien_cache_ts = now
        if include_lernphase:
            return result
        return [k for k in result if not k.get("lernphase")]
    except Exception:
        return [{"name": k["name"], "ist_standard": True, "lernphase": False} for k in STANDARD_KATEGORIEN]


def add_dynamische_kategorie(name: str, beschreibung: str = "") -> dict:
    """Legt eine neue dynamische Kategorie an (Lernphase). Gibt die Kategorie zurück."""
    global _kategorien_cache
    _ensure_kategorien_table()
    db_path = KNOWLEDGE_DIR / "tasks.db"
    db = sqlite3.connect(str(db_path))
    now = datetime.now().isoformat()
    # Prüfen ob schon existiert
    existing = db.execute("SELECT * FROM kategorien WHERE name=?", (name,)).fetchone()
    if existing:
        db.execute("UPDATE kategorien SET anzahl_zuweisungen = anzahl_zuweisungen + 1 WHERE name=?", (name,))
        db.commit()
        # Promotion prüfen: 5+ Zuweisungen → Lernphase beenden
        row = db.execute("SELECT * FROM kategorien WHERE name=?", (name,)).fetchone()
        if row and row[5] >= 5 and row[4] == 1:  # anzahl_zuweisungen >= 5 und lernphase = 1
            db.execute("UPDATE kategorien SET lernphase=0, promoted_am=? WHERE name=?", (now, name))
            db.commit()
        db.close()
        _kategorien_cache = None  # Cache invalidieren
        return {"name": name, "ist_neu": False}
    # Neu anlegen
    db.execute(
        "INSERT INTO kategorien (name, ist_standard, ist_dynamisch, lernphase, anzahl_zuweisungen, erstellt_am, beschreibung) "
        "VALUES (?,0,1,1,1,?,?)",
        (name, now, beschreibung))
    db.commit()
    db.close()
    _kategorien_cache = None
    return {"name": name, "ist_neu": True, "lernphase": True}
