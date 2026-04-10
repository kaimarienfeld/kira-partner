#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KIRA Case Engine — Kernmodul (session-nn)
Vorgangslogik: Anlegen, Zuordnen, Status-Übergänge, Verknüpfungen, Kontext.

Statusmaschinen: dict-basiert, transitions-Library-kompatible Schnittstelle
vorbereitet (kann später mit `pip install transitions` umgestellt werden).

Entscheidungsstufen:
  A = still automatisch verarbeiten
  B = Vorschlag erzeugen (SSE-Toast)
  C = Aktivfenster (kritisch / unklar)
"""
import sqlite3, json
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"

# ── Statusmaschinen ───────────────────────────────────────────────────────────
# Struktur: {vorgang_typ: {von_status: [gueltige_nachfolger]}}
# transitions-Library-Vorbereitung: Die Transition-Dicts sind identisch zur
# transitions.Machine-Syntax und können 1:1 übertragen werden.
TRANSITIONS: dict[str, dict[str, list[str]]] = {
    "lead": {
        "neu":                    ["qualifiziert", "kein_bedarf", "archiviert"],
        "qualifiziert":           ["angebot_gesendet", "antwort_vorbereitet", "kein_bedarf"],
        "antwort_vorbereitet":    ["wartet_auf_rueckmeldung", "kein_bedarf"],
        "wartet_auf_rueckmeldung":["angebot_gesendet", "termin_offen", "kein_bedarf", "archiviert"],
        "angebot_gesendet":       ["gewonnen", "verloren", "kein_bedarf"],
        "termin_offen":           ["angebot_gesendet", "kein_bedarf", "archiviert"],
        "gewonnen":               ["abgeschlossen"],
        "kein_bedarf":            ["archiviert"],
        "verloren":               ["archiviert"],
        "abgeschlossen":          [],
        "archiviert":             [],
    },
    "angebot": {
        "neu":             ["offen", "archiviert"],
        "offen":           ["nachgefasst_1", "rueckmeldung", "zurueckgestellt", "verloren", "abgelehnt"],
        "nachgefasst_1":   ["nachgefasst_2", "rueckmeldung", "zurueckgestellt", "verloren"],
        "nachgefasst_2":   ["nachgefasst_3", "rueckmeldung", "zurueckgestellt", "verloren"],
        "nachgefasst_3":   ["rueckmeldung", "nachfass_sommer", "verloren"],
        "nachfass_sommer": ["rueckmeldung", "verloren", "archiviert"],
        "zurueckgestellt": ["offen", "nachgefasst_1", "verloren", "archiviert"],
        "rueckmeldung":    ["gewonnen", "verloren", "abgelehnt"],
        "gewonnen":        ["umgesetzt"],
        "umgesetzt":       ["abgeschlossen"],
        "verloren":        ["archiviert"],
        "abgelehnt":       ["archiviert"],
        "abgeschlossen":   [],
        "archiviert":      [],
    },
    "rechnung": {
        "erkannt":    ["offen", "storniert"],
        "offen":      ["zugeordnet", "ueberfaellig", "storniert"],
        "zugeordnet": ["bezahlt", "ueberfaellig"],
        "ueberfaellig":["mahnung_1", "bezahlt"],
        "mahnung_1":  ["mahnung_2", "bezahlt"],
        "mahnung_2":  ["mahnung_3", "bezahlt"],
        "mahnung_3":  ["streitfall", "bezahlt"],
        "teilbezahlt":["offen", "bezahlt"],
        "bezahlt":    ["erledigt"],
        "streitfall": ["erledigt", "archiviert"],
        "storniert":  ["archiviert"],
        "erledigt":   [],
        "archiviert": [],
    },
    "eingangsrechnung": {
        "eingegangen": ["geprueft", "abgelehnt"],
        "geprueft":    ["freigegeben", "unklar", "abgelehnt"],
        "freigegeben": ["bezahlt"],
        "unklar":      ["geprueft", "abgelehnt"],
        "bezahlt":     ["erledigt"],
        "abgelehnt":   ["archiviert"],
        "erledigt":    [],
        "archiviert":  [],
    },
    "mahnung": {
        "erkannt":   ["bewertet"],
        "bewertet":  ["eskaliert", "ignoriert"],
        "eskaliert": ["erledigt"],
        "ignoriert": ["archiviert"],
        "erledigt":  [],
        "archiviert":[],
    },
    "zahlung": {
        "erkannt":  ["gematcht", "ungeklaert"],
        "gematcht": ["erledigt"],
        "ungeklaert":["gematcht", "archiviert"],
        "erledigt": [],
        "archiviert":[],
    },
    "anfrage": {
        "neu":           ["in_bearbeitung", "geschlossen"],
        "in_bearbeitung":["geantwortet", "weitergeleitet", "geschlossen"],
        "geantwortet":   ["erledigt"],
        "weitergeleitet":["erledigt"],
        "geschlossen":   ["archiviert"],
        "erledigt":      [],
        "archiviert":    [],
    },
    "projekt": {
        "angefragt":   ["beauftragt", "abgebrochen"],
        "beauftragt":  ["laufend"],
        "laufend":     ["abgeschlossen", "abgebrochen"],
        "abgeschlossen":["archiviert"],
        "abgebrochen": ["archiviert"],
        "archiviert":  [],
    },
    "termin": {
        "erkannt":     ["bestaetigt", "abgesagt"],
        "bestaetigt":  ["stattgefunden", "abgesagt"],
        "stattgefunden":["erledigt"],
        "abgesagt":    ["archiviert"],
        "erledigt":    [],
        "archiviert":  [],
    },
    "sonstiger_vorgang": {
        "neu":      ["in_bearbeitung", "archiviert"],
        "in_bearbeitung":["erledigt", "archiviert"],
        "erledigt": [],
        "archiviert":[],
    },
}

# Status die als "abgeschlossen" gelten
ABGESCHLOSSENE_STATUS = {
    "abgeschlossen", "archiviert", "erledigt", "kein_bedarf",
    "verloren", "abgelehnt", "storniert",
}

# Initiale Status pro Typ (= Startzustand)
INITIAL_STATUS = {
    "lead": "neu",
    "angebot": "neu",
    "rechnung": "erkannt",
    "eingangsrechnung": "eingegangen",
    "mahnung": "erkannt",
    "zahlung": "erkannt",
    "anfrage": "neu",
    "projekt": "angefragt",
    "termin": "erkannt",
    "sonstiger_vorgang": "neu",
}

# ── transitions-kompatible Schnittstelle (Vorbereitung für spätere Library) ──
def can_transition(vorgang_typ: str, von_status: str, zu_status: str) -> bool:
    """Prüft ob ein Statusübergang erlaubt ist."""
    return zu_status in TRANSITIONS.get(vorgang_typ, {}).get(von_status, [])

def get_valid_transitions(vorgang_typ: str, current_status: str) -> list[str]:
    """Gibt alle erlaubten Folgestatus zurück."""
    return TRANSITIONS.get(vorgang_typ, {}).get(current_status, [])

def is_final_status(status: str) -> bool:
    """True wenn der Vorgang in einem Endzustand ist."""
    return status in ABGESCHLOSSENE_STATUS

# ── Entscheidungsstufen ───────────────────────────────────────────────────────
def classify_decision_level(
    konfidenz: float,
    kategorie: str,
    vorgang_typ: str,
    ist_bekannter_kunde: bool = False,
    hat_offenen_vorgang: bool = False,
) -> str:
    """
    Bestimmt Entscheidungsstufe A, B oder C.
    A = still automatisch (kein UI-Signal)
    B = Vorschlag zeigen (SSE-Toast)
    C = Aktivfenster (Rückfrage erforderlich)
    """
    # Kritische Typen → immer mindestens B
    kritische_typen = {"mahnung", "zahlung", "eingangsrechnung"}

    if konfidenz >= 0.85 and vorgang_typ not in kritische_typen:
        return "A"
    if konfidenz < 0.45:
        return "C"
    if vorgang_typ in kritische_typen and konfidenz < 0.7:
        return "C"
    return "B"

# ── DB-Helper ─────────────────────────────────────────────────────────────────
def _get_db():
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    return db

def _now() -> str:
    return datetime.now().isoformat(sep=' ', timespec='seconds')

def _next_vorgang_nr(db) -> str:
    """Generiert eindeutige Vorgangsnummer V-YYYY-NNNN."""
    year = datetime.now().year
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM vorgaenge WHERE vorgang_nr LIKE ?",
        (f"V-{year}-%",)
    ).fetchone()
    seq = (row["cnt"] if row else 0) + 1
    return f"V-{year}-{seq:04d}"

# ── Kern-Funktionen ───────────────────────────────────────────────────────────

def create_vorgang(
    typ: str,
    kunden_email: str = None,
    kunden_name: str = None,
    titel: str = None,
    quelle: str = "mail",
    konfidenz: float = 0.7,
    konto: str = None,
    betrag: float = None,
    entscheidungsstufe: str = None,
    notiz: str = None,
) -> int:
    """
    Legt einen neuen Vorgang an.
    Gibt die neue vorgang_id zurück.
    """
    if typ not in TRANSITIONS:
        typ = "sonstiger_vorgang"

    initial_status = INITIAL_STATUS.get(typ, "neu")
    if entscheidungsstufe is None:
        entscheidungsstufe = "B"

    db = _get_db()
    try:
        vorgang_nr = _next_vorgang_nr(db)
        now = _now()
        db.execute("""
            INSERT INTO vorgaenge
                (vorgang_nr, typ, status, titel, kunden_email, kunden_name,
                 konto, betrag, prioritaet, entscheidungsstufe, konfidenz,
                 quelle, erstellt_am, aktualisiert_am, notiz)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            vorgang_nr, typ, initial_status,
            titel or f"{typ.capitalize()} {vorgang_nr}",
            (kunden_email or "").lower(), kunden_name or "",
            konto or "", betrag, "mittel", entscheidungsstufe,
            konfidenz, quelle, now, now, notiz or ""
        ))
        vorgang_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("""
            INSERT INTO vorgang_status_history
                (vorgang_id, alter_status, neuer_status, grund, actor, erstellt_am)
            VALUES (?,?,?,?,?,?)
        """, (vorgang_id, None, initial_status, f"Vorgang angelegt via {quelle}", "system", now))
        db.commit()
        return vorgang_id
    finally:
        db.close()


def find_open_vorgang(
    kunden_email: str,
    typ: str,
    max_alter_tage: int = 180,
) -> int | None:
    """
    Sucht einen offenen Vorgang für kunden_email + typ.
    Gibt vorgang_id zurück oder None wenn keiner gefunden.
    Ältere als max_alter_tage werden ignoriert (de-dup-Schutz).
    """
    if not kunden_email:
        return None
    email = kunden_email.lower()
    db = _get_db()
    try:
        row = db.execute("""
            SELECT id FROM vorgaenge
            WHERE LOWER(kunden_email) = ?
              AND typ = ?
              AND status NOT IN ('abgeschlossen','archiviert','erledigt','verloren',
                                 'abgelehnt','storniert','kein_bedarf')
              AND date(erstellt_am) >= date('now', ? || ' days')
            ORDER BY erstellt_am DESC LIMIT 1
        """, (email, typ, f"-{max_alter_tage}")).fetchone()
        return row["id"] if row else None
    finally:
        db.close()


def link_entity(
    vorgang_id: int,
    entitaet_typ: str,
    entitaet_id: str,
    rolle: str = None,
) -> int:
    """
    Verknüpft eine Entität (task/mail/angebot/rechnung/…) mit einem Vorgang.
    entitaet_typ: 'task' | 'mail' | 'angebot' | 'ausgangsrechnung' |
                  'eingangsrechnung' | 'zahlung' | 'dokument' | 'kira_konv' | 'wissen'
    entitaet_id: ID als String (task.id, message_id, angebot.id, …)
    Gibt link_id zurück.
    """
    db = _get_db()
    try:
        # Duplikat-Schutz
        existing = db.execute("""
            SELECT id FROM vorgang_links
            WHERE vorgang_id=? AND entitaet_typ=? AND entitaet_id=?
        """, (vorgang_id, entitaet_typ, str(entitaet_id))).fetchone()
        if existing:
            return existing["id"]

        db.execute("""
            INSERT INTO vorgang_links (vorgang_id, entitaet_typ, entitaet_id, rolle, erstellt_am)
            VALUES (?,?,?,?,?)
        """, (vorgang_id, entitaet_typ, str(entitaet_id), rolle or "", _now()))
        link_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # aktualisiert_am des Vorgangs updaten
        db.execute("UPDATE vorgaenge SET aktualisiert_am=? WHERE id=?", (_now(), vorgang_id))
        db.commit()
        return link_id
    finally:
        db.close()


def update_status(
    vorgang_id: int,
    neuer_status: str,
    grund: str = "",
    actor: str = "system",
    force: bool = False,
) -> bool:
    """
    Führt einen validierten Statusübergang durch.
    force=True überspringt Validierung (nur für Migrationen/Korrekturen).
    Gibt True zurück wenn Übergang durchgeführt wurde.
    """
    db = _get_db()
    try:
        row = db.execute(
            "SELECT typ, status FROM vorgaenge WHERE id=?", (vorgang_id,)
        ).fetchone()
        if not row:
            return False

        alter_status = row["status"]
        vorgang_typ  = row["typ"]

        if not force and not can_transition(vorgang_typ, alter_status, neuer_status):
            return False

        now = _now()
        db.execute("""
            UPDATE vorgaenge
            SET status=?, aktualisiert_am=?, letzter_status_grund=?,
                abgeschlossen_am=CASE WHEN ? IN ('abgeschlossen','archiviert','erledigt',
                                                   'verloren','abgelehnt','storniert','kein_bedarf')
                                      THEN ? ELSE abgeschlossen_am END
            WHERE id=?
        """, (neuer_status, now, grund, neuer_status, now, vorgang_id))

        db.execute("""
            INSERT INTO vorgang_status_history
                (vorgang_id, alter_status, neuer_status, grund, actor, erstellt_am)
            VALUES (?,?,?,?,?,?)
        """, (vorgang_id, alter_status, neuer_status, grund, actor, now))

        db.commit()
        return True
    finally:
        db.close()


def get_vorgang(vorgang_id: int) -> dict | None:
    """Gibt einen Vorgang als dict zurück."""
    db = _get_db()
    try:
        row = db.execute("SELECT * FROM vorgaenge WHERE id=?", (vorgang_id,)).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def get_vorgang_context(vorgang_id: int) -> dict:
    """
    Vollständiger Kontext eines Vorgangs:
    Vorgang-Daten + alle verknüpften Entitäten + Statushistorie.
    Wird von Kira, API und Aktivfenster genutzt.
    """
    db = _get_db()
    try:
        vorgang = db.execute("SELECT * FROM vorgaenge WHERE id=?", (vorgang_id,)).fetchone()
        if not vorgang:
            return {}

        links = db.execute("""
            SELECT * FROM vorgang_links WHERE vorgang_id=? ORDER BY erstellt_am
        """, (vorgang_id,)).fetchall()

        history = db.execute("""
            SELECT * FROM vorgang_status_history
            WHERE vorgang_id=? ORDER BY erstellt_am DESC LIMIT 20
        """, (vorgang_id,)).fetchall()

        # Tasks aus tasks.db laden
        task_ids = [l["entitaet_id"] for l in links if l["entitaet_typ"] == "task"]
        tasks = []
        if task_ids:
            placeholders = ",".join("?" * len(task_ids))
            rows = db.execute(
                f"SELECT id,typ,kategorie,titel,status,kunden_email,datum_mail FROM tasks WHERE id IN ({placeholders})",
                [int(t) for t in task_ids if str(t).isdigit()]
            ).fetchall()
            tasks = [dict(r) for r in rows]

        return {
            "vorgang":   dict(vorgang),
            "links":     [dict(l) for l in links],
            "history":   [dict(h) for h in history],
            "tasks":     tasks,
            "gueltige_uebergaenge": get_valid_transitions(vorgang["typ"], vorgang["status"]),
        }
    finally:
        db.close()


def create_signal(
    stufe: str,
    titel: str,
    nachricht: str,
    vorgang_id: int = None,
    typ: str = None,
    payload: dict = None,
) -> int:
    """
    Erstellt ein Stufe-A/B/C-Signal in vorgang_signals.
    Stufe B → SSE-Toast; Stufe C → Aktivfenster-Modal.
    Stufe A → kein Signal (wird nicht eingetragen).
    Gibt signal_id zurück (0 bei Stufe A).
    """
    if stufe == "A":
        return 0
    db = _get_db()
    try:
        db.execute("""
            INSERT INTO vorgang_signals
                (vorgang_id, stufe, titel, nachricht, typ, payload_json, angezeigt, erstellt_am)
            VALUES (?,?,?,?,?,?,0,?)
        """, (
            vorgang_id, stufe, titel, nachricht, typ or "",
            json.dumps(payload or {}, ensure_ascii=False), _now()
        ))
        signal_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.commit()
        return signal_id
    finally:
        db.close()


def get_pending_signals(max_count: int = 10) -> list[dict]:
    """Gibt unangezeigte Signale zurück (neueste zuerst)."""
    db = _get_db()
    try:
        rows = db.execute("""
            SELECT * FROM vorgang_signals
            WHERE angezeigt=0
            ORDER BY stufe DESC, erstellt_am DESC
            LIMIT ?
        """, (max_count,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def mark_signal_shown(signal_id: int, aktion: str = "") -> None:
    """Markiert ein Signal als angezeigt."""
    db = _get_db()
    try:
        db.execute(
            "UPDATE vorgang_signals SET angezeigt=1, aktion=? WHERE id=?",
            (aktion, signal_id)
        )
        db.commit()
    finally:
        db.close()


# ── Zentraler Event-Bus (session-gggg) ────────────────────────────────────────
import threading as _threading
import time as _time

_notify_cooldowns: dict[str, float] = {}
_notify_lock = _threading.Lock()


def kira_notify(
    titel: str,
    nachricht: str = "",
    stufe: str = "B",
    typ: str = "",
    modul: str = "",
    vorgang_id: int = None,
    payload: dict = None,
    cooldown_key: str = "",
    cooldown_hours: float = 4.0,
) -> int:
    """
    Zentraler Event-Bus — alle Module rufen diese Funktion auf.
    Wraps create_signal() mit Cooldown + Runtime-Logging.
    Gibt signal_id zurück (0 wenn übersprungen oder Stufe A).
    """
    # Cooldown-Check
    if cooldown_key:
        with _notify_lock:
            now = _time.time()
            last = _notify_cooldowns.get(cooldown_key, 0)
            if now - last < cooldown_hours * 3600:
                return 0
            _notify_cooldowns[cooldown_key] = now

    # Payload mit Modul anreichern
    p = dict(payload or {})
    if modul:
        p["modul"] = modul

    # Signal erstellen
    sig_id = create_signal(
        stufe=stufe,
        titel=titel,
        nachricht=nachricht,
        vorgang_id=vorgang_id,
        typ=typ or modul,
        payload=p,
    )

    # Runtime-Log
    try:
        from runtime_log import elog
        elog("system", "kira_notify", titel,
             source=modul or "case_engine", modul=modul or "case_engine",
             context_type="signal", context_id=str(sig_id),
             status="ok" if sig_id else "skipped")
    except Exception:
        pass

    return sig_id


def get_open_vorgaenge(
    typ: str = None,
    kunden_email: str = None,
    limit: int = 50,
) -> list[dict]:
    """Gibt offene Vorgänge zurück, optional gefiltert."""
    db = _get_db()
    try:
        where = ["status NOT IN ('abgeschlossen','archiviert','erledigt','verloren',"
                 "'abgelehnt','storniert','kein_bedarf')"]
        params: list = []
        if typ:
            where.append("typ=?")
            params.append(typ)
        if kunden_email:
            where.append("LOWER(kunden_email)=?")
            params.append(kunden_email.lower())
        params.append(limit)
        rows = db.execute(
            f"SELECT * FROM vorgaenge WHERE {' AND '.join(where)} "
            "ORDER BY prioritaet DESC, aktualisiert_am DESC LIMIT ?",
            params
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def update_task_vorgang_id(task_id: int, vorgang_id: int) -> None:
    """Setzt vorgang_id-Spalte in der tasks-Tabelle."""
    db = _get_db()
    try:
        db.execute("UPDATE tasks SET vorgang_id=? WHERE id=?", (vorgang_id, task_id))
        db.commit()
    finally:
        db.close()


def get_vorgang_summary_for_kira(limit: int = 5) -> str:
    """
    Kompakte Zusammenfassung offener Vorgänge für Kira-System-Prompt.
    """
    db = _get_db()
    try:
        rows = db.execute("""
            SELECT typ, status, kunden_name, kunden_email, titel, vorgang_nr, aktualisiert_am
            FROM vorgaenge
            WHERE status NOT IN ('abgeschlossen','archiviert','erledigt','verloren',
                                 'abgelehnt','storniert','kein_bedarf')
            ORDER BY aktualisiert_am DESC
            LIMIT ?
        """, (limit,)).fetchall()
        if not rows:
            return ""
        lines = [f"OFFENE VORGÄNGE ({len(rows)})"]
        for r in rows:
            name = r["kunden_name"] or r["kunden_email"] or "?"
            lines.append(f"  [{r['vorgang_nr']}] {r['typ'].upper()} → {r['status']} | {name} | {r['titel']}")
        return "\n".join(lines)
    finally:
        db.close()


# ── Projekt-System (Vorgänge typ='projekt') ──────────────────────────────────

KUNDEN_DB = KNOWLEDGE_DIR / "kunden.db"
MAIL_INDEX_DB = KNOWLEDGE_DIR / "mail_index.db"

_projekt_columns_ensured = False
_crm_tables_ensured = False

def _ensure_crm_tables():
    """Erstellt/migriert alle CRM-Tabellen in kunden.db (idempotent)."""
    global _crm_tables_ensured
    if _crm_tables_ensured:
        return
    if not KUNDEN_DB.exists():
        _crm_tables_ensured = True
        return
    db = sqlite3.connect(str(KUNDEN_DB))
    db.row_factory = sqlite3.Row
    try:
        # ALTER TABLE kunden — neue Spalten
        kunden_neue_spalten = [
            ("firmenname", "TEXT"),
            ("ansprechpartner", "TEXT"),
            ("kundentyp", "TEXT DEFAULT 'unbekannt'"),
            ("status", "TEXT DEFAULT 'aktiv'"),
            ("lexware_id", "TEXT"),
            ("kundenwert", "REAL DEFAULT 0"),
            ("fit_score", "REAL DEFAULT 0"),
            ("zahlungsverhalten_score", "REAL DEFAULT 0"),
            ("risiko_score", "REAL DEFAULT 0"),
            ("metadata_json", "TEXT DEFAULT '{}'"),
            ("aktualisiert_am", "TEXT"),
        ]
        for col, col_type in kunden_neue_spalten:
            try:
                db.execute(f"ALTER TABLE kunden ADD COLUMN {col} {col_type}")
            except Exception:
                pass  # Spalte existiert bereits

        # kunden_identitaeten
        db.execute("""
            CREATE TABLE IF NOT EXISTS kunden_identitaeten (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kunden_id INTEGER NOT NULL,
                typ TEXT NOT NULL DEFAULT 'mail',
                wert TEXT NOT NULL,
                confidence TEXT NOT NULL DEFAULT 'wahrscheinlich',
                verifiziert INTEGER NOT NULL DEFAULT 0,
                quelle TEXT DEFAULT 'auto',
                erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (kunden_id) REFERENCES kunden(id),
                UNIQUE(kunden_id, typ, wert)
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_ki_wert ON kunden_identitaeten(LOWER(wert))")
        db.execute("CREATE INDEX IF NOT EXISTS idx_ki_kunden ON kunden_identitaeten(kunden_id)")

        # kunden_projekte
        db.execute("""
            CREATE TABLE IF NOT EXISTS kunden_projekte (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kunden_id INTEGER NOT NULL,
                projektname TEXT NOT NULL,
                projekttyp TEXT DEFAULT 'standard',
                status TEXT NOT NULL DEFAULT 'planung',
                beginn_am TEXT,
                abschluss_am TEXT,
                beschreibung TEXT,
                auftragswert REAL DEFAULT 0,
                naechste_aktion TEXT,
                erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
                aktualisiert_am TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (kunden_id) REFERENCES kunden(id)
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_kp_kunden ON kunden_projekte(kunden_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_kp_status ON kunden_projekte(status)")

        # kunden_faelle
        db.execute("""
            CREATE TABLE IF NOT EXISTS kunden_faelle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kunden_id INTEGER NOT NULL,
                projekt_id INTEGER,
                fall_typ TEXT NOT NULL DEFAULT 'anfrage',
                titel TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'offen',
                prioritaet TEXT DEFAULT 'normal',
                naechste_aktion TEXT,
                faellig_am TEXT,
                erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
                aktualisiert_am TEXT NOT NULL DEFAULT (datetime('now')),
                confidence_score REAL DEFAULT 0,
                auto_zugeordnet INTEGER DEFAULT 0,
                manuell_geprueft INTEGER DEFAULT 0,
                FOREIGN KEY (kunden_id) REFERENCES kunden(id),
                FOREIGN KEY (projekt_id) REFERENCES kunden_projekte(id)
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_kf_kunden ON kunden_faelle(kunden_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_kf_projekt ON kunden_faelle(projekt_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_kf_status ON kunden_faelle(status)")

        # kunden_aktivitaeten
        db.execute("""
            CREATE TABLE IF NOT EXISTS kunden_aktivitaeten (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kunden_id INTEGER NOT NULL,
                projekt_id INTEGER,
                fall_id INTEGER,
                ereignis_typ TEXT NOT NULL DEFAULT 'manuell',
                quelle_id TEXT,
                quelle_tabelle TEXT,
                zusammenfassung TEXT,
                volltext_auszug TEXT,
                erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
                sichtbar_in_verlauf INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (kunden_id) REFERENCES kunden(id),
                FOREIGN KEY (projekt_id) REFERENCES kunden_projekte(id),
                FOREIGN KEY (fall_id) REFERENCES kunden_faelle(id)
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_ka_kunden ON kunden_aktivitaeten(kunden_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_ka_projekt ON kunden_aktivitaeten(projekt_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_ka_fall ON kunden_aktivitaeten(fall_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_ka_zeit ON kunden_aktivitaeten(erstellt_am)")

        # kunden_classifier_log
        db.execute("""
            CREATE TABLE IF NOT EXISTS kunden_classifier_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                eingabe_typ TEXT NOT NULL,
                eingabe_id TEXT,
                kunden_id_vorschlag INTEGER,
                projekt_id_vorschlag INTEGER,
                fall_typ_vorschlag TEXT,
                confidence TEXT NOT NULL DEFAULT 'unklar',
                reasoning_kurz TEXT,
                llm_modell TEXT,
                erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
                user_bestaetigt INTEGER DEFAULT 0,
                user_korrektur_kunden_id INTEGER,
                user_korrektur_projekt_id INTEGER
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_cl_eingabe ON kunden_classifier_log(eingabe_typ, eingabe_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_cl_zeit ON kunden_classifier_log(erstellt_am)")

        # kunden_ignoriert (Absender die dauerhaft ignoriert werden)
        db.execute("""
            CREATE TABLE IF NOT EXISTS kunden_ignoriert (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                absender_email TEXT UNIQUE NOT NULL,
                absender_domain TEXT,
                grund TEXT DEFAULT 'manuell',
                erstellt_am TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_kig_email ON kunden_ignoriert(LOWER(absender_email))")
        db.execute("CREATE INDEX IF NOT EXISTS idx_kig_domain ON kunden_ignoriert(absender_domain)")

        # --- Identitäts-Graph (session-uu, 2026-04-10) ---
        db.execute("""
            CREATE TABLE IF NOT EXISTS kunden_identitaeten_graph (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identitaet_a_id INTEGER NOT NULL
                    REFERENCES kunden_identitaeten(id) ON DELETE CASCADE,
                identitaet_b_id INTEGER NOT NULL
                    REFERENCES kunden_identitaeten(id) ON DELETE CASCADE,
                confidence REAL NOT NULL DEFAULT 0.0,
                confidence_stufe TEXT NOT NULL
                    CHECK(confidence_stufe IN ('eindeutig','wahrscheinlich','pruefen','unklar')),
                reasoning TEXT,
                entschieden_durch TEXT DEFAULT 'llm'
                    CHECK(entschieden_durch IN ('llm','kai_manuell','lernregel')),
                kai_bestaetigt INTEGER DEFAULT 0,
                kai_abgelehnt INTEGER DEFAULT 0,
                erstellt_am TEXT NOT NULL,
                bestaetigt_am TEXT
            )
        """)
        db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_kig_pair
            ON kunden_identitaeten_graph(
                MIN(identitaet_a_id, identitaet_b_id),
                MAX(identitaet_a_id, identitaet_b_id)
            )""")

        # --- Lernregeln aus Kai-Korrekturen (session-uu, 2026-04-10) ---
        db.execute("""
            CREATE TABLE IF NOT EXISTS kunden_lernregeln (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kunden_id INTEGER REFERENCES kunden(id),
                regel_typ TEXT NOT NULL
                    CHECK(regel_typ IN (
                        'identitaet','projekt_signal','kanal_muster',
                        'ausschluss','projekt_typ'
                    )),
                bedingung_json TEXT NOT NULL,
                aktion_json TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                quelle TEXT DEFAULT 'kai_korrektur'
                    CHECK(quelle IN ('kai_korrektur','llm_schluss','manuell')),
                anwendungen INTEGER DEFAULT 0,
                letzte_anwendung TEXT,
                erstellt_am TEXT NOT NULL,
                aktiv INTEGER DEFAULT 1
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_klr_kunde ON kunden_lernregeln(kunden_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_klr_typ ON kunden_lernregeln(regel_typ, aktiv)")

        # Migration entfernt (session-tt, 2026-04-10):
        # Kunden kommen ausschließlich aus Lexware Office (REGEL-09).
        # Import läuft über kunden_lexware_sync.py.

        db.commit()
        _crm_tables_ensured = True
    finally:
        db.close()


def _ensure_projekt_columns():
    """Erweitert vorgaenge + vorgang_links um projekt-spezifische Felder (einmalig)."""
    global _projekt_columns_ensured
    if _projekt_columns_ensured:
        return
    db = _get_db()
    try:
        migrations = [
            ("vorgaenge", "kontakt_id", "INTEGER"),
            ("vorgaenge", "kunde_email_resolved", "TEXT"),
            ("vorgaenge", "projekt_nr", "TEXT"),
            ("vorgaenge", "adresse", "TEXT"),
            ("vorgang_links", "kanal", "TEXT DEFAULT 'email'"),
        ]
        for table, col, col_type in migrations:
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            except Exception:
                pass  # Spalte existiert bereits
        db.commit()
        _projekt_columns_ensured = True
    finally:
        db.close()


def _next_projekt_nr(db) -> str:
    """Generiert eindeutige Projektnummer P-YYYY-NNN."""
    year = datetime.now().year
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM vorgaenge WHERE projekt_nr LIKE ?",
        (f"P-{year}-%",)
    ).fetchone()
    seq = (row["cnt"] if row else 0) + 1
    return f"P-{year}-{seq:03d}"


def get_or_create_kontakt(email: str, name: str = None) -> int | None:
    """
    Kontakt in kunden.db suchen oder anlegen. Gibt kontakt_id zurück.
    kunden.db = Vorläufer von customer_master (CRM-Vorbereitung).
    """
    if not email:
        return None
    email_clean = email.lower().strip()
    if not KUNDEN_DB.exists():
        return None
    try:
        kdb = sqlite3.connect(str(KUNDEN_DB))
        kdb.row_factory = sqlite3.Row
        row = kdb.execute(
            "SELECT id FROM kunden WHERE LOWER(email) = ?", (email_clean,)
        ).fetchone()
        if row:
            # Letztkontakt aktualisieren
            kdb.execute(
                "UPDATE kunden SET letztkontakt=?, anzahl_mails=anzahl_mails+1 WHERE id=?",
                (_now(), row["id"])
            )
            kdb.commit()
            kid = row["id"]
            kdb.close()
            return kid
        # Neuen Kontakt anlegen
        kdb.execute(
            "INSERT INTO kunden (email, name, erstkontakt, letztkontakt, anzahl_mails, hauptkanal) "
            "VALUES (?,?,?,?,1,'email')",
            (email_clean, name or "", _now(), _now())
        )
        kid = kdb.execute("SELECT last_insert_rowid()").fetchone()[0]
        kdb.commit()
        kdb.close()
        return kid
    except Exception:
        return None


def create_projekt(
    kunde_name: str,
    titel: str,
    kunde_email: str = None,
    typ_detail: str = None,
    adresse: str = None,
    quelle: str = "kira",
    notiz: str = None,
) -> dict:
    """
    Neues Projekt als Vorgang (typ='projekt') anlegen.
    Gibt {'vorgang_id': int, 'projekt_nr': str, 'kontakt_id': int|None} zurück.
    """
    _ensure_projekt_columns()

    # Kontakt-Zuordnung (kunden.db)
    kontakt_id = get_or_create_kontakt(kunde_email, kunde_name) if kunde_email else None

    db = _get_db()
    try:
        vorgang_nr = _next_vorgang_nr(db)
        projekt_nr = _next_projekt_nr(db)
        now = _now()
        initial_status = INITIAL_STATUS.get("projekt", "angefragt")

        beschreibung = ""
        if typ_detail:
            beschreibung = f"Projekttyp: {typ_detail}"
        if adresse:
            beschreibung += f"\nAdresse: {adresse}" if beschreibung else f"Adresse: {adresse}"

        db.execute("""
            INSERT INTO vorgaenge
                (vorgang_nr, typ, status, titel, kunden_email, kunden_name,
                 konto, betrag, prioritaet, entscheidungsstufe, konfidenz,
                 quelle, erstellt_am, aktualisiert_am, notiz,
                 kontakt_id, kunde_email_resolved, projekt_nr, adresse)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            vorgang_nr, "projekt", initial_status,
            titel, (kunde_email or "").lower(), kunde_name or "",
            "", None, "mittel", "B", 0.8,
            quelle, now, now, notiz or "",
            kontakt_id, (kunde_email or "").lower(), projekt_nr, adresse or ""
        ))
        vorgang_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        db.execute("""
            INSERT INTO vorgang_status_history
                (vorgang_id, alter_status, neuer_status, grund, actor, erstellt_am)
            VALUES (?,?,?,?,?,?)
        """, (vorgang_id, None, initial_status, f"Projekt angelegt via {quelle}", "system", now))
        db.commit()

        return {"vorgang_id": vorgang_id, "projekt_nr": projekt_nr, "kontakt_id": kontakt_id}
    finally:
        db.close()


def find_projekt(
    kunde_name: str = None,
    kunde_email: str = None,
    titel_keywords: str = None,
    status: str = "aktiv",
    limit: int = 10,
) -> list[dict]:
    """
    Projekt-Vorgänge suchen. Gibt Liste von Projekt-Dicts zurück.
    status: 'aktiv' (nur offene), 'abgeschlossen', 'alle'
    """
    _ensure_projekt_columns()
    db = _get_db()
    try:
        where = ["typ = 'projekt'"]
        params = []

        if status == "aktiv":
            where.append("status NOT IN ('abgeschlossen','archiviert','abgebrochen')")
        elif status == "abgeschlossen":
            where.append("status IN ('abgeschlossen','archiviert','abgebrochen')")
        # 'alle' → kein Filter

        if kunde_email:
            where.append("LOWER(kunden_email) = ?")
            params.append(kunde_email.lower().strip())
        if kunde_name:
            where.append("LOWER(kunden_name) LIKE ?")
            params.append(f"%{kunde_name.lower()}%")
        if titel_keywords:
            for kw in titel_keywords.split():
                where.append("LOWER(titel) LIKE ?")
                params.append(f"%{kw.lower()}%")

        params.append(limit)
        rows = db.execute(
            f"SELECT * FROM vorgaenge WHERE {' AND '.join(where)} "
            f"ORDER BY aktualisiert_am DESC LIMIT ?",
            params
        ).fetchall()

        return [dict(r) for r in rows]
    finally:
        db.close()


def find_projekte_for_email(email: str, limit: int = 5) -> list[dict]:
    """Alle aktiven Projekte für eine bestimmte E-Mail-Adresse (für Classifier-Kontext)."""
    return find_projekt(kunde_email=email, limit=limit)


def update_projekt(vorgang_id: int, **fields) -> bool:
    """Projekt-Vorgang aktualisieren (Titel, Status, Adresse, Notizen...)."""
    _ensure_projekt_columns()
    allowed = {"titel", "adresse", "notiz", "kunden_name", "kunden_email",
               "kunde_email_resolved", "kontakt_id", "status", "prioritaet"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return False
    db = _get_db()
    try:
        sets = [f"{k}=?" for k in updates]
        sets.append("aktualisiert_am=?")
        vals = list(updates.values()) + [_now(), vorgang_id]
        db.execute(
            f"UPDATE vorgaenge SET {', '.join(sets)} WHERE id=?", vals
        )
        db.commit()
        return True
    finally:
        db.close()


def get_projekt_kontext(vorgang_id: int = None, projekt_nr: str = None) -> dict:
    """
    Vollständigen Projekt-Kontext laden: alle verknüpften Mails, Tasks, Dokumente.
    Suche nach vorgang_id ODER projekt_nr.
    """
    _ensure_projekt_columns()
    db = _get_db()
    try:
        if projekt_nr and not vorgang_id:
            row = db.execute(
                "SELECT id FROM vorgaenge WHERE projekt_nr=? AND typ='projekt'",
                (projekt_nr,)
            ).fetchone()
            if not row:
                return {"fehler": f"Projekt {projekt_nr} nicht gefunden"}
            vorgang_id = row["id"]

        if not vorgang_id:
            return {"fehler": "Weder vorgang_id noch projekt_nr angegeben"}

        projekt = db.execute("SELECT * FROM vorgaenge WHERE id=?", (vorgang_id,)).fetchone()
        if not projekt:
            return {"fehler": f"Vorgang #{vorgang_id} nicht gefunden"}

        # Verknüpfte Entitäten über vorgang_links laden
        links = db.execute(
            "SELECT entitaet_typ, entitaet_id, rolle, kanal, erstellt_am "
            "FROM vorgang_links WHERE vorgang_id=? ORDER BY erstellt_am DESC",
            (vorgang_id,)
        ).fetchall()

        # Entitäten nach Typ gruppieren
        tasks = []
        mails = []
        dokumente = []
        sonstige = []
        for link in links:
            entry = {"id": link["entitaet_id"], "rolle": link["rolle"] or "",
                     "kanal": link["kanal"] or "", "datum": link["erstellt_am"]}
            typ = link["entitaet_typ"]
            if typ == "task":
                # Task-Details laden
                t = db.execute("SELECT id, titel, kategorie, status, prioritaet FROM tasks WHERE id=?",
                               (int(link["entitaet_id"]),)).fetchone()
                if t:
                    entry.update(dict(t))
                tasks.append(entry)
            elif typ == "mail":
                mails.append(entry)
            elif typ == "dokument":
                dokumente.append(entry)
            else:
                entry["typ"] = typ
                sonstige.append(entry)

        # Mail-Details aus mail_index.db laden
        if mails and MAIL_INDEX_DB.exists():
            try:
                mdb = sqlite3.connect(str(MAIL_INDEX_DB))
                mdb.row_factory = sqlite3.Row
                for m in mails:
                    mr = mdb.execute(
                        "SELECT betreff, absender, datum, kategorie FROM mails WHERE message_id=?",
                        (m["id"],)
                    ).fetchone()
                    if mr:
                        m.update({"betreff": mr["betreff"], "absender": mr["absender"],
                                  "datum_mail": mr["datum"], "kategorie": mr["kategorie"]})
                mdb.close()
            except Exception:
                pass

        return {
            "projekt": dict(projekt),
            "tasks": tasks,
            "mails": mails,
            "dokumente": dokumente,
            "sonstige": sonstige,
            "anzahl_links": len(links),
        }
    finally:
        db.close()


def assign_to_projekt(
    vorgang_id: int,
    entitaet_typ: str,
    entitaet_id: str | int,
    kanal: str = "email",
) -> int:
    """
    Entität einem Projekt-Vorgang zuordnen via link_entity().
    Setzt zusätzlich kanal im vorgang_links-Eintrag.
    """
    _ensure_projekt_columns()
    link_id = link_entity(vorgang_id, entitaet_typ, str(entitaet_id), rolle="projekt_zuordnung")

    # kanal-Feld setzen
    db = _get_db()
    try:
        db.execute("UPDATE vorgang_links SET kanal=? WHERE id=?", (kanal, link_id))
        db.commit()
    except Exception:
        pass
    finally:
        db.close()

    return link_id


def get_projekt_summary_for_kira(limit: int = 8) -> str:
    """Kompakte Zusammenfassung aktiver Projekte für Kira-System-Prompt."""
    _ensure_projekt_columns()
    db = _get_db()
    try:
        rows = db.execute("""
            SELECT id, projekt_nr, kunden_name, kunden_email, titel, status, aktualisiert_am
            FROM vorgaenge
            WHERE typ = 'projekt'
              AND status NOT IN ('abgeschlossen','archiviert','abgebrochen')
            ORDER BY aktualisiert_am DESC
            LIMIT ?
        """, (limit,)).fetchall()
        if not rows:
            return ""

        lines = [f"AKTIVE PROJEKTE ({len(rows)})"]
        for r in rows:
            name = r["kunden_name"] or r["kunden_email"] or "?"
            pnr = r["projekt_nr"] or r["id"]
            # Verknüpfte Entitäten zählen
            cnt = db.execute(
                "SELECT COUNT(*) as c FROM vorgang_links WHERE vorgang_id=?",
                (r["id"],)
            ).fetchone()
            n_links = cnt["c"] if cnt else 0
            datum = (r["aktualisiert_am"] or "")[:10]
            lines.append(f"  [{pnr}] {name} — {r['titel']} ({r['status']}, {n_links} Verknüpfungen, {datum})")
        return "\n".join(lines)
    finally:
        db.close()
