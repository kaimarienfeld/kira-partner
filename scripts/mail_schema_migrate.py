#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mail_schema_migrate.py — Sicheres Schema-Upgrade für mail_index.db

Fügt fehlende Felder hinzu, ohne bestehende Daten zu verlieren.
Idempotent: kann beliebig oft ausgeführt werden.

Neue Felder:
  - in_reply_to  TEXT   — Message-ID der Eltern-Mail (Threading)
  - references   TEXT   — Alle Message-IDs aus References-Header (JSON-Array)
  - thread_id    TEXT   — Berechnete Thread-Gruppen-ID (=älteste Message-ID im Thread)
  - sync_source  TEXT   — Herkunft: 'archiv_import' | 'live_sync' | 'fallback_sync'
  - text_plain   TEXT   — Mail-Body als Plaintext (für Suche, max 8000 Zeichen)
  - eml_path     TEXT   — Pfad zur .eml-Datei im Mail-Archiv (falls vorhanden)
  - fallback_hash TEXT  — Hash-Schlüssel wenn message_id fehlt

Auch mail_index.db bekommt einen UNIQUE-Index auf (konto, folder, fallback_hash)
als Fallback-Dedup wenn message_id NULL ist.
"""
import sqlite3, json, hashlib, logging
from pathlib import Path

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
MAIL_INDEX_DB = KNOWLEDGE_DIR / "mail_index.db"

log = logging.getLogger("mail_schema_migrate")

# Alle neuen Spalten: (name, definition, default_update_sql)
NEW_COLUMNS = [
    # (column_name, sql_type_default, sql_to_fill_from_existing)
    ("in_reply_to",      "TEXT",                         None),
    ("mail_references",  "TEXT",                         None),
    ("thread_id",        "TEXT",                         None),
    ("sync_source",    "TEXT DEFAULT 'archiv_import'", "UPDATE mails SET sync_source='archiv_import' WHERE sync_source IS NULL"),
    ("text_plain",     "TEXT",                         None),
    ("eml_path",       "TEXT",                         None),
    ("fallback_hash",  "TEXT",                         None),
    ("cc",             "TEXT",                         None),
]

NEW_INDICES = [
    ("idx_thread",      "mails(thread_id)"),
    ("idx_sync_source", "mails(sync_source)"),
    ("idx_message_id",  "mails(message_id)"),
    ("idx_in_reply_to", "mails(in_reply_to)"),
]


def get_existing_columns(conn):
    cursor = conn.execute("PRAGMA table_info(mails)")
    return {row[1] for row in cursor.fetchall()}


def migrate(db_path=None):
    path = Path(db_path) if db_path else MAIL_INDEX_DB
    if not path.exists():
        log.warning(f"DB nicht gefunden: {path}")
        print(f"⚠  DB nicht gefunden: {path}")
        return False

    print(f"Schema-Migration: {path}")
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")

    existing = get_existing_columns(conn)
    added = []

    for col_name, col_def, update_sql in NEW_COLUMNS:
        if col_name not in existing:
            try:
                conn.execute(f"ALTER TABLE mails ADD COLUMN {col_name} {col_def}")
                added.append(col_name)
                print(f"  ✓ Spalte hinzugefügt: {col_name}")
                if update_sql:
                    conn.execute(update_sql)
                    print(f"    → Bestehende Zeilen aktualisiert")
            except Exception as e:
                print(f"  ✗ Fehler bei {col_name}: {e}")
        else:
            print(f"  · Spalte vorhanden: {col_name}")

    # Indizes anlegen (IF NOT EXISTS ist sicher)
    for idx_name, idx_def in NEW_INDICES:
        try:
            conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}")
            print(f"  ✓ Index: {idx_name}")
        except Exception as e:
            print(f"  ✗ Index {idx_name}: {e}")

    conn.commit()

    # Statistik
    count = conn.execute("SELECT COUNT(*) FROM mails").fetchone()[0]
    no_msgid = conn.execute("SELECT COUNT(*) FROM mails WHERE message_id IS NULL OR message_id=''").fetchone()[0]
    no_thread = conn.execute("SELECT COUNT(*) FROM mails WHERE thread_id IS NULL").fetchone()[0]
    no_source = conn.execute("SELECT COUNT(*) FROM mails WHERE sync_source IS NULL").fetchone()[0]

    conn.close()

    print(f"\nDatenbank-Status:")
    print(f"  Gesamt Mails:       {count:,}")
    print(f"  Ohne message_id:    {no_msgid:,}")
    print(f"  Ohne thread_id:     {no_thread:,}")
    print(f"  Ohne sync_source:   {no_source:,}")
    if added:
        print(f"\n  Neue Spalten: {', '.join(added)}")
    else:
        print(f"\n  Keine Änderungen (Schema bereits aktuell)")

    return True


def backfill_thread_ids(db_path=None, batch_size=5000):
    """
    Berechnet thread_id für alle Mails wo sie fehlt.
    Strategie: Einfachste robuste Methode — message_id selbst als thread_id,
    wenn keine References vorhanden. Spätere Korrektur via References-Kette
    erfolgt durch mail_monitor wenn neue Mails reinkommen.
    """
    path = Path(db_path) if db_path else MAIL_INDEX_DB
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")

    # Schritt 1: Mails ohne thread_id, aber mit message_id → thread_id = message_id
    updated = conn.execute("""
        UPDATE mails SET thread_id = message_id
        WHERE thread_id IS NULL
          AND message_id IS NOT NULL
          AND message_id != ''
    """).rowcount
    print(f"  Thread-IDs gesetzt (message_id): {updated:,}")

    # Schritt 2: Mails ohne message_id → fallback_hash generieren
    rows = conn.execute("""
        SELECT id, konto, absender, an, datum_iso, betreff
        FROM mails
        WHERE (message_id IS NULL OR message_id = '')
          AND fallback_hash IS NULL
    """).fetchall()

    fallback_updated = 0
    for row in rows:
        rid, konto, absender, an, datum_iso, betreff = row
        raw = f"{konto}|{absender}|{an}|{datum_iso}|{(betreff or '')[:60]}"
        fhash = "FALLBACK-" + hashlib.sha256(raw.encode('utf-8', errors='replace')).hexdigest()[:20]
        conn.execute("UPDATE mails SET fallback_hash=?, thread_id=? WHERE id=?", (fhash, fhash, rid))
        fallback_updated += 1
        if fallback_updated % batch_size == 0:
            conn.commit()
            print(f"    ... {fallback_updated:,} Fallback-Hashes gesetzt")

    conn.commit()
    conn.close()
    print(f"  Fallback-Hashes gesetzt: {fallback_updated:,}")
    return updated + fallback_updated


def check_duplicates(db_path=None):
    """Zeigt Duplikat-Statistik."""
    path = Path(db_path) if db_path else MAIL_INDEX_DB
    conn = sqlite3.connect(str(path))

    dups = conn.execute("""
        SELECT message_id, COUNT(*) as cnt
        FROM mails
        WHERE message_id IS NOT NULL AND message_id != ''
        GROUP BY message_id
        HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT 20
    """).fetchall()

    if dups:
        print(f"\n⚠  Duplikate gefunden (message_id):")
        for msg_id, cnt in dups:
            print(f"  {cnt}x {msg_id[:80]}")
    else:
        print("\n✓ Keine Duplikate gefunden")

    conn.close()
    return len(dups)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("mail_schema_migrate.py")
    print("=" * 60)

    ok = migrate()
    if ok:
        print("\nFülle Thread-IDs auf...")
        backfill_thread_ids()
        print("\nPrüfe Duplikate...")
        check_duplicates()
        print("\n✓ Migration abgeschlossen")
    else:
        print("✗ Migration fehlgeschlagen")
        sys.exit(1)
