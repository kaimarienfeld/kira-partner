#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dokument_storage.py — Kira Dokumente: Speicher & Ablage (session-eeee)

Verantwortlich für:
  - Externe strukturierte Dateiablage
  - Hash-basierte Dublettenerkennung
  - Metadaten-CRUD in tasks.db (Tabelle: dokumente + dokument_vorlagen)
  - Ordnerstruktur-Management
"""
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"
CONFIG_FILE   = SCRIPTS_DIR / "config.json"

_db_initialized = False

# ── Konfiguration ─────────────────────────────────────────────────────────────

def _load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _get_dok_config() -> dict:
    cfg = _load_config()
    return cfg.get("dokumente", {})

def _get_ablage_pfad() -> Path:
    """Gibt den konfigurierten externen Ablage-Pfad zurück."""
    dok_cfg = _get_dok_config()
    pfad = dok_cfg.get("ablage_pfad", "")
    if pfad:
        return Path(pfad)
    # Fallback: neben Mail-Archiv
    cfg = _load_config()
    archiv = cfg.get("mail_archiv", {}).get("pfad", "")
    if archiv:
        return Path(archiv).parent / "Dokumente"
    return KNOWLEDGE_DIR / "dokumente_ablage"

# ── DB-Schema ─────────────────────────────────────────────────────────────────

def _ensure_tables():
    global _db_initialized
    if _db_initialized:
        return
    with sqlite3.connect(str(TASKS_DB)) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA wal_autocheckpoint=100")
        con.executescript("""
            CREATE TABLE IF NOT EXISTS dokumente (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                titel            TEXT NOT NULL DEFAULT '',
                dateiname        TEXT NOT NULL DEFAULT '',
                dateityp         TEXT DEFAULT '',
                dateigroesse     INTEGER DEFAULT 0,
                hash_sha256      TEXT DEFAULT '',
                externer_pfad    TEXT DEFAULT '',
                quelle           TEXT DEFAULT '',
                quell_id         TEXT DEFAULT '',
                dokumentrolle    TEXT DEFAULT '',
                kategorie        TEXT DEFAULT '',
                tags             TEXT DEFAULT '[]',
                ocr_text         TEXT DEFAULT '',
                klassifizierung  TEXT DEFAULT '{}',
                erfordert_handlung INTEGER DEFAULT 0,
                routing_ziel     TEXT DEFAULT '',
                zielmodul        TEXT DEFAULT '',
                vorgang_id       INTEGER,
                status           TEXT DEFAULT 'neu',
                version          INTEGER DEFAULT 1,
                konfidenz        REAL DEFAULT 0.0,
                erstellt_von     TEXT DEFAULT 'system',
                erstellt_am      TEXT NOT NULL DEFAULT (datetime('now')),
                geaendert_am     TEXT NOT NULL DEFAULT (datetime('now')),
                archiviert_am    TEXT,
                geloescht_am     TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_dokumente_hash ON dokumente(hash_sha256);
            CREATE INDEX IF NOT EXISTS idx_dokumente_vorgang ON dokumente(vorgang_id);
            CREATE INDEX IF NOT EXISTS idx_dokumente_status ON dokumente(status);
            CREATE INDEX IF NOT EXISTS idx_dokumente_quelle ON dokumente(quelle);

            CREATE TABLE IF NOT EXISTS dokument_vorlagen (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                kategorie     TEXT DEFAULT 'frei',
                dokumenttyp   TEXT DEFAULT 'html',
                inhalt        TEXT DEFAULT '',
                briefkopf_id  INTEGER,
                signatur_id   INTEGER,
                platzhalter   TEXT DEFAULT '[]',
                kira_aktiv    INTEGER DEFAULT 0,
                aktiv         INTEGER DEFAULT 1,
                version       INTEGER DEFAULT 1,
                erstellt      TEXT NOT NULL DEFAULT (datetime('now')),
                geaendert     TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS dokument_briefkoepfe (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                logo_pfad     TEXT DEFAULT '',
                firmenname    TEXT DEFAULT '',
                adresse       TEXT DEFAULT '',
                kontakt       TEXT DEFAULT '',
                bankverbindung TEXT DEFAULT '',
                steuernummer  TEXT DEFAULT '',
                html_header   TEXT DEFAULT '',
                html_footer   TEXT DEFAULT '',
                aktiv         INTEGER DEFAULT 1,
                erstellt      TEXT NOT NULL DEFAULT (datetime('now')),
                geaendert     TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
    _db_initialized = True


# ── Hash & Dedup ──────────────────────────────────────────────────────────────

def compute_hash(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def check_duplicate(hash_val: str) -> dict | None:
    """Prüft ob ein Dokument mit diesem Hash bereits existiert."""
    _ensure_tables()
    with sqlite3.connect(str(TASKS_DB)) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT * FROM dokumente WHERE hash_sha256 = ? AND geloescht_am IS NULL LIMIT 1",
            (hash_val,)
        ).fetchone()
        return dict(row) if row else None


# ── Externe Ablage ────────────────────────────────────────────────────────────

def build_ablage_pfad(
    dateiname: str,
    quelle: str = "upload",
    kunde_name: str = "",
    vorgang_id: int = None,
    dokumentrolle: str = "",
) -> Path:
    """Erzeugt den strukturierten Ablage-Pfad für ein Dokument."""
    basis = _get_ablage_pfad()
    jahr = datetime.now().strftime("%Y")

    if vorgang_id and kunde_name:
        ordner = basis / jahr / _safe_name(kunde_name)
    elif kunde_name:
        ordner = basis / jahr / _safe_name(kunde_name)
    else:
        ordner = basis / jahr / "sonstige"

    if dokumentrolle:
        ordner = ordner / _safe_name(dokumentrolle)
    elif quelle in ("mail_anhang", "mail"):
        ordner = ordner / "eingang"
    elif quelle in ("studio", "kira"):
        ordner = ordner / "ausgang"
    else:
        ordner = ordner / "eingang"

    ordner.mkdir(parents=True, exist_ok=True)

    ziel = ordner / dateiname
    if ziel.exists():
        stem = ziel.stem
        suffix = ziel.suffix
        i = 1
        while ziel.exists():
            ziel = ordner / f"{stem}_{i}{suffix}"
            i += 1
    return ziel


def _safe_name(name: str) -> str:
    """Bereinigt Dateinamen für Ordner."""
    import re
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', '_', name)
    return name[:60] or "unbekannt"


def store_file(source_path: Path, target_path: Path, move: bool = False) -> Path:
    """Kopiert oder verschiebt eine Datei in die externe Ablage."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if move:
        shutil.move(str(source_path), str(target_path))
    else:
        shutil.copy2(str(source_path), str(target_path))
    return target_path


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_dokument(
    titel: str,
    dateiname: str = "",
    dateityp: str = "",
    dateigroesse: int = 0,
    hash_sha256: str = "",
    externer_pfad: str = "",
    quelle: str = "upload",
    quell_id: str = "",
    dokumentrolle: str = "",
    kategorie: str = "",
    tags: list = None,
    ocr_text: str = "",
    klassifizierung: dict = None,
    erfordert_handlung: bool = False,
    routing_ziel: str = "",
    zielmodul: str = "",
    vorgang_id: int = None,
    status: str = "neu",
    erstellt_von: str = "system",
) -> int:
    """Legt ein neues Dokument in der DB an, gibt die ID zurück."""
    _ensure_tables()
    with sqlite3.connect(str(TASKS_DB)) as con:
        cur = con.execute("""
            INSERT INTO dokumente (
                titel, dateiname, dateityp, dateigroesse, hash_sha256,
                externer_pfad, quelle, quell_id, dokumentrolle, kategorie,
                tags, ocr_text, klassifizierung, erfordert_handlung,
                routing_ziel, zielmodul, vorgang_id, status, erstellt_von
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            titel, dateiname, dateityp, dateigroesse, hash_sha256,
            externer_pfad, quelle, quell_id, dokumentrolle, kategorie,
            json.dumps(tags or [], ensure_ascii=False),
            ocr_text,
            json.dumps(klassifizierung or {}, ensure_ascii=False),
            1 if erfordert_handlung else 0,
            routing_ziel, zielmodul, vorgang_id, status, erstellt_von,
        ))
        return cur.lastrowid


def get_dokument(dok_id: int) -> dict | None:
    _ensure_tables()
    with sqlite3.connect(str(TASKS_DB)) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM dokumente WHERE id = ?", (dok_id,)).fetchone()
        return dict(row) if row else None


def list_dokumente(
    status: str = None,
    quelle: str = None,
    vorgang_id: int = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    _ensure_tables()
    sql = "SELECT * FROM dokumente WHERE geloescht_am IS NULL"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if quelle:
        sql += " AND quelle = ?"
        params.append(quelle)
    if vorgang_id:
        sql += " AND vorgang_id = ?"
        params.append(vorgang_id)
    sql += " ORDER BY erstellt_am DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with sqlite3.connect(str(TASKS_DB)) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def update_dokument(dok_id: int, **kwargs) -> bool:
    _ensure_tables()
    allowed = {
        "titel", "dateiname", "dateityp", "externer_pfad", "dokumentrolle",
        "kategorie", "tags", "ocr_text", "klassifizierung", "erfordert_handlung",
        "routing_ziel", "zielmodul", "vorgang_id", "status", "version",
        "konfidenz", "archiviert_am", "geloescht_am",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    if "tags" in fields and isinstance(fields["tags"], list):
        fields["tags"] = json.dumps(fields["tags"], ensure_ascii=False)
    if "klassifizierung" in fields and isinstance(fields["klassifizierung"], dict):
        fields["klassifizierung"] = json.dumps(fields["klassifizierung"], ensure_ascii=False)
    fields["geaendert_am"] = datetime.now().isoformat(timespec="seconds")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [dok_id]
    with sqlite3.connect(str(TASKS_DB)) as con:
        con.execute(f"UPDATE dokumente SET {set_clause} WHERE id = ?", values)
    return True


def delete_dokument(dok_id: int, soft: bool = True) -> bool:
    _ensure_tables()
    if soft:
        return update_dokument(dok_id, geloescht_am=datetime.now().isoformat(timespec="seconds"))
    with sqlite3.connect(str(TASKS_DB)) as con:
        con.execute("DELETE FROM dokumente WHERE id = ?", (dok_id,))
    return True


def count_dokumente(status: str = None) -> dict:
    """Gibt Anzahlen nach Status zurück."""
    _ensure_tables()
    with sqlite3.connect(str(TASKS_DB)) as con:
        if status:
            row = con.execute(
                "SELECT COUNT(*) FROM dokumente WHERE status = ? AND geloescht_am IS NULL",
                (status,)
            ).fetchone()
            return {status: row[0]}
        rows = con.execute(
            "SELECT status, COUNT(*) FROM dokumente WHERE geloescht_am IS NULL GROUP BY status"
        ).fetchall()
        return {r[0]: r[1] for r in rows}


# ── Vorlagen CRUD ─────────────────────────────────────────────────────────────

def list_vorlagen(kategorie: str = None, nur_aktive: bool = True) -> list[dict]:
    _ensure_tables()
    sql = "SELECT * FROM dokument_vorlagen"
    params = []
    wheres = []
    if nur_aktive:
        wheres.append("aktiv = 1")
    if kategorie:
        wheres.append("kategorie = ?")
        params.append(kategorie)
    if wheres:
        sql += " WHERE " + " AND ".join(wheres)
    sql += " ORDER BY name"
    with sqlite3.connect(str(TASKS_DB)) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def save_vorlage(data: dict) -> int:
    _ensure_tables()
    vid = data.get("id")
    with sqlite3.connect(str(TASKS_DB)) as con:
        if vid:
            con.execute("""
                UPDATE dokument_vorlagen SET
                    name=?, kategorie=?, dokumenttyp=?, inhalt=?,
                    briefkopf_id=?, signatur_id=?, platzhalter=?,
                    kira_aktiv=?, aktiv=?, geaendert=datetime('now')
                WHERE id=?
            """, (
                data.get("name", ""), data.get("kategorie", "frei"),
                data.get("dokumenttyp", "html"), data.get("inhalt", ""),
                data.get("briefkopf_id"), data.get("signatur_id"),
                json.dumps(data.get("platzhalter", []), ensure_ascii=False),
                1 if data.get("kira_aktiv") else 0,
                1 if data.get("aktiv", True) else 0,
                vid,
            ))
            return vid
        else:
            cur = con.execute("""
                INSERT INTO dokument_vorlagen
                    (name, kategorie, dokumenttyp, inhalt, briefkopf_id, signatur_id,
                     platzhalter, kira_aktiv, aktiv)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("name", "Neue Vorlage"), data.get("kategorie", "frei"),
                data.get("dokumenttyp", "html"), data.get("inhalt", ""),
                data.get("briefkopf_id"), data.get("signatur_id"),
                json.dumps(data.get("platzhalter", []), ensure_ascii=False),
                1 if data.get("kira_aktiv") else 0,
                1 if data.get("aktiv", True) else 0,
            ))
            return cur.lastrowid


def delete_vorlage(vid: int) -> bool:
    _ensure_tables()
    with sqlite3.connect(str(TASKS_DB)) as con:
        con.execute("DELETE FROM dokument_vorlagen WHERE id = ?", (vid,))
    return True


# ── Briefköpfe CRUD ──────────────────────────────────────────────────────────

def list_briefkoepfe() -> list[dict]:
    _ensure_tables()
    with sqlite3.connect(str(TASKS_DB)) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(
            "SELECT * FROM dokument_briefkoepfe WHERE aktiv = 1 ORDER BY name"
        ).fetchall()]


def save_briefkopf(data: dict) -> int:
    _ensure_tables()
    bid = data.get("id")
    with sqlite3.connect(str(TASKS_DB)) as con:
        if bid:
            con.execute("""
                UPDATE dokument_briefkoepfe SET
                    name=?, logo_pfad=?, firmenname=?, adresse=?, kontakt=?,
                    bankverbindung=?, steuernummer=?, html_header=?, html_footer=?,
                    aktiv=?, geaendert=datetime('now')
                WHERE id=?
            """, (
                data.get("name", ""), data.get("logo_pfad", ""),
                data.get("firmenname", ""), data.get("adresse", ""),
                data.get("kontakt", ""), data.get("bankverbindung", ""),
                data.get("steuernummer", ""), data.get("html_header", ""),
                data.get("html_footer", ""), 1 if data.get("aktiv", True) else 0, bid,
            ))
            return bid
        else:
            cur = con.execute("""
                INSERT INTO dokument_briefkoepfe
                    (name, logo_pfad, firmenname, adresse, kontakt,
                     bankverbindung, steuernummer, html_header, html_footer)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("name", "Standard"), data.get("logo_pfad", ""),
                data.get("firmenname", ""), data.get("adresse", ""),
                data.get("kontakt", ""), data.get("bankverbindung", ""),
                data.get("steuernummer", ""), data.get("html_header", ""),
                data.get("html_footer", ""),
            ))
            return cur.lastrowid
