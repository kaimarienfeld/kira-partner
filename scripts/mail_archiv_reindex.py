#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mail_archiv_reindex.py — Synchronisiert das lokale Mail-Archiv mit mail_index.db.

Traversiert den Archiv-Ordner (Archiv/konto_/ORDNER/datum_betreff_hash/) und
importiert alle mail.json-Einträge in die mail_index.db.

Idempotent: INSERT OR IGNORE — bereits vorhandene Mails werden nicht doppelt
eingetragen. Aktualisiert nur eml_path und mail_folder_pfad falls leer.

Verwendung:
    python scripts/mail_archiv_reindex.py
    python scripts/mail_archiv_reindex.py --pfad "C:/anderer/pfad"
    python scripts/mail_archiv_reindex.py --trocken   (nur zählen, nichts schreiben)
"""
import json, sqlite3, logging, time, re, html, sys, argparse
from pathlib import Path
from datetime import datetime
from html.parser import HTMLParser

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
CONFIG_FILE   = SCRIPTS_DIR / "config.json"
MAIL_INDEX_DB = KNOWLEDGE_DIR / "mail_index.db"

log = logging.getLogger("mail_archiv_reindex")

# ── Fortschritt-Callback für API-Aufrufe ─────────────────────────────────────
_progress = {"total": 0, "done": 0, "inserted": 0, "updated": 0,
             "errors": 0, "running": False, "finished": False, "msg": ""}


def get_progress():
    return dict(_progress)


# ── HTML → Plaintext ─────────────────────────────────────────────────────────
class _Strip(HTMLParser):
    def __init__(self):
        super().__init__()
        self._t = []
    def handle_data(self, d):
        self._t.append(d)
    def error(self, message):
        pass

def html_to_text(h, max_len=8000):
    if not h:
        return ""
    s = _Strip()
    try:
        s.feed(h)
        txt = " ".join(s._t)
        txt = re.sub(r'\s+', ' ', txt).strip()
        return txt[:max_len]
    except Exception:
        return h[:max_len]


# ── DB-Initialisierung ───────────────────────────────────────────────────────
def _ensure_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mails (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            konto           TEXT,
            konto_label     TEXT,
            betreff         TEXT,
            absender        TEXT,
            absender_short  TEXT,
            an              TEXT,
            cc              TEXT,
            datum           TEXT,
            datum_iso       TEXT,
            message_id      TEXT UNIQUE,
            folder          TEXT,
            hat_anhaenge    INTEGER DEFAULT 0,
            anhaenge        TEXT,
            anhaenge_pfad   TEXT,
            mail_folder_pfad TEXT,
            archiviert_am   TEXT,
            in_reply_to     TEXT,
            mail_references TEXT,
            thread_id       TEXT,
            sync_source     TEXT DEFAULT 'archiv_import',
            text_plain      TEXT,
            eml_path        TEXT,
            fallback_hash   TEXT,
            unread          INTEGER DEFAULT 0
        )
    """)
    # Indizes
    for idx, col in [
        ("idx_message_id",  "mails(message_id)"),
        ("idx_konto_folder","mails(konto, folder)"),
        ("idx_thread",      "mails(thread_id)"),
        ("idx_datum",       "mails(datum_iso)"),
    ]:
        conn.execute(f"CREATE INDEX IF NOT EXISTS {idx} ON {col}")


def _absender_short(absender):
    """'Franziska Wielath <foo@bar.com>' → 'Franziska Wielath'"""
    if not absender:
        return ""
    m = re.match(r'^"?([^"<]+)"?\s*<', absender.strip())
    if m:
        return m.group(1).strip().strip('"')
    m = re.match(r'^([^@\s]+@[^\s]+)$', absender.strip())
    if m:
        return m.group(1)
    return absender[:60]


def _konto_label(email_addr):
    return email_addr.split("@")[0].lower() if email_addr else ""


# ── Archiv-Ordner erkennen ───────────────────────────────────────────────────
def _archiv_konto_name(folder_name):
    """
    'anfrage_raumkult_eu' → 'anfrage@raumkult.eu'
    Heuristik: letzten Teil nach zweitem _ ist Domain-Teil
    """
    parts = folder_name.split("_")
    if len(parts) >= 3:
        # anfrage_raumkult_eu → anfrage @ raumkult.eu
        local = parts[0]
        domain = ".".join(parts[1:])
        return f"{local}@{domain}"
    return folder_name.replace("_", "@", 1)


def _folder_display_name(raw_folder):
    """Roher Ordnername aus Dateisystem → lesbarer Name"""
    mapping = {
        "inbox": "INBOX",
        "posteingang": "INBOX",
        "gesendete elemente": "Gesendete Elemente",
        "gesendet": "Gesendete Elemente",
        "sent items": "Gesendete Elemente",
        "sent": "Gesendete Elemente",
        "entw": "Entwürfe",
        "drafts": "Entwürfe",
    }
    return mapping.get(raw_folder.lower(), raw_folder)


# ── Einzelne Mail importieren ─────────────────────────────────────────────────
def import_mail_json(conn, json_path: Path, folder_name: str, dry_run=False):
    """
    Liest mail.json, importiert in mail_index.db.
    Gibt (action, message_id) zurück: action = 'inserted'|'updated'|'skipped'|'error'
    """
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.debug(f"JSON-Lesefehler {json_path}: {e}")
        return "error", None

    msg_id = (data.get("message_id") or "").strip()
    if not msg_id:
        # Fallback-Hash
        konto = data.get("konto", "")
        absender = data.get("absender", "")
        datum = data.get("datum_iso") or data.get("datum", "")
        betreff = data.get("betreff", "")[:60]
        import hashlib
        raw = f"{konto}|{absender}|{datum}|{betreff}"
        msg_id = "FALLBACK-" + hashlib.sha256(raw.encode('utf-8', errors='replace')).hexdigest()[:20]

    mail_folder = str(json_path.parent)
    eml_path = str(json_path.parent / "mail.eml")
    anhaenge_pfad = str(json_path.parent / "attachments")

    # Text: aus mail.json (kann HTML sein → in Plaintext wandeln)
    raw_text = data.get("text", "")
    text_plain = html_to_text(raw_text) if raw_text else ""

    # Anhänge
    anhaenge_list = data.get("anhaenge") or []
    hat_anhaenge = 1 if (anhaenge_list or data.get("hat_anhaenge")) else 0

    konto = data.get("konto", "")
    konto_label = _konto_label(konto)
    absender = data.get("absender", "")
    datum_iso = data.get("datum_iso") or ""
    # thread_id Berechnung
    in_reply_to = (data.get("in_reply_to") or "").strip()
    mail_refs = (data.get("mail_references") or "").strip()
    if mail_refs:
        refs = [r.strip() for r in mail_refs.split() if r.strip().startswith("<")]
        thread_id = refs[0] if refs else (in_reply_to or msg_id)
    elif in_reply_to:
        thread_id = in_reply_to
    else:
        thread_id = msg_id

    if dry_run:
        return "would_insert", msg_id

    try:
        conn.execute("""
            INSERT OR IGNORE INTO mails
            (konto, konto_label, betreff, absender, absender_short, an, cc,
             datum, datum_iso, message_id, folder,
             hat_anhaenge, anhaenge, anhaenge_pfad, mail_folder_pfad,
             archiviert_am, in_reply_to, mail_references, thread_id,
             sync_source, text_plain, eml_path)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            konto, konto_label,
            data.get("betreff", ""),
            absender,
            _absender_short(absender),
            data.get("an", ""),
            data.get("cc", ""),
            data.get("datum", ""),
            datum_iso,
            msg_id,
            folder_name,
            hat_anhaenge,
            json.dumps(anhaenge_list, ensure_ascii=False),
            data.get("anhaenge_pfad") or anhaenge_pfad,
            data.get("mail_folder_pfad") or mail_folder,
            data.get("archiviert_am") or datetime.now().isoformat(),
            in_reply_to,
            mail_refs,
            thread_id,
            "archiv_import",
            text_plain,
            data.get("eml_pfad") or eml_path,
        ))
        if conn.total_changes > 0:
            return "inserted", msg_id
    except Exception as e:
        log.debug(f"INSERT fehlgeschlagen {msg_id}: {e}")
        return "error", msg_id

    # Bereits vorhanden → eml_path + mail_folder_pfad aktualisieren falls leer
    try:
        conn.execute("""
            UPDATE mails SET
                eml_path = COALESCE(NULLIF(eml_path,''), ?),
                mail_folder_pfad = COALESCE(NULLIF(mail_folder_pfad,''), ?),
                anhaenge_pfad = COALESCE(NULLIF(anhaenge_pfad,''), ?),
                text_plain = CASE WHEN (text_plain IS NULL OR text_plain='') THEN ? ELSE text_plain END
            WHERE message_id=?
        """, (
            data.get("eml_pfad") or eml_path,
            data.get("mail_folder_pfad") or mail_folder,
            data.get("anhaenge_pfad") or anhaenge_pfad,
            text_plain,
            msg_id,
        ))
        return "updated", msg_id
    except Exception as e:
        log.debug(f"UPDATE fehlgeschlagen {msg_id}: {e}")
        return "error", msg_id


# ── Haupt-Reindex ─────────────────────────────────────────────────────────────
def reindex(archiv_pfad=None, dry_run=False, progress_callback=None):
    """
    Traversiert den Archiv-Ordner und importiert alle Mails in mail_index.db.
    Gibt dict mit Statistik zurück.
    """
    global _progress
    _progress.update({"running": True, "finished": False, "done": 0,
                      "inserted": 0, "updated": 0, "errors": 0, "msg": "Starte..."})

    # Archiv-Pfad bestimmen
    if not archiv_pfad:
        try:
            cfg = json.loads(CONFIG_FILE.read_text('utf-8'))
            archiv_pfad = cfg.get("mail_archiv", {}).get("pfad", "")
        except Exception:
            pass
    if not archiv_pfad:
        _progress.update({"running": False, "finished": True, "msg": "Kein Archiv-Pfad konfiguriert"})
        return {"ok": False, "error": "Kein Archiv-Pfad konfiguriert"}

    archiv_root = Path(archiv_pfad)
    if not archiv_root.exists():
        _progress.update({"running": False, "finished": True,
                          "msg": f"Archiv-Pfad nicht gefunden: {archiv_pfad}"})
        return {"ok": False, "error": f"Archiv-Pfad nicht gefunden: {archiv_pfad}"}

    # Alle mail.json Dateien zählen
    all_jsons = list(archiv_root.rglob("mail.json"))
    _progress["total"] = len(all_jsons)
    _progress["msg"] = f"{len(all_jsons)} Mails gefunden..."
    log.info(f"Reindex: {len(all_jsons)} Mails in {archiv_root}")

    if not all_jsons:
        _progress.update({"running": False, "finished": True, "msg": "Keine Mails gefunden"})
        return {"ok": True, "total": 0, "inserted": 0, "updated": 0, "errors": 0}

    conn = None
    if not dry_run:
        conn = sqlite3.connect(str(MAIL_INDEX_DB))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _ensure_db(conn)

    inserted = updated = errors = 0
    BATCH = 500

    for i, json_path in enumerate(all_jsons):
        # Ordner-Namen aus Pfad ableiten
        # Struktur: archiv_root / konto_ordner / ORDNER_NAME / datum_betreff_hash / mail.json
        try:
            rel = json_path.relative_to(archiv_root)
            parts = rel.parts  # (konto_ordner, ORDNER_NAME, mail_folder_name, mail.json)
            folder_raw = parts[1] if len(parts) >= 3 else "INBOX"
            folder_name = _folder_display_name(folder_raw)
        except Exception:
            folder_name = "INBOX"

        if dry_run:
            action, _ = "would_insert", None
            inserted += 1
        else:
            action, _ = import_mail_json(conn, json_path, folder_name, dry_run=False)
            if action == "inserted":
                inserted += 1
            elif action == "updated":
                updated += 1
            elif action == "error":
                errors += 1

        _progress.update({"done": i + 1, "inserted": inserted,
                          "updated": updated, "errors": errors,
                          "msg": f"{i+1}/{len(all_jsons)} verarbeitet"})

        # Batch-Commit
        if not dry_run and (i + 1) % BATCH == 0:
            conn.commit()
            log.info(f"  {i+1}/{len(all_jsons)} — {inserted} neu, {updated} aktualisiert, {errors} Fehler")

    if conn:
        conn.commit()
        conn.close()

    stats = {"ok": True, "total": len(all_jsons), "inserted": inserted,
             "updated": updated, "errors": errors, "dry_run": dry_run}
    _progress.update({"running": False, "finished": True,
                      "msg": f"Fertig: {inserted} neu, {updated} aktualisiert, {errors} Fehler"})
    log.info(f"Reindex abgeschlossen: {stats}")
    return stats


# ── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Mail-Archiv → mail_index.db Re-Index")
    parser.add_argument("--pfad", help="Archiv-Pfad (überschreibt config.json)")
    parser.add_argument("--trocken", action="store_true", help="Nur zählen, nichts schreiben")
    args = parser.parse_args()

    print("=" * 60)
    print("mail_archiv_reindex.py")
    print("=" * 60)

    t0 = time.monotonic()
    result = reindex(archiv_pfad=args.pfad, dry_run=args.trocken)
    elapsed = time.monotonic() - t0

    if result.get("ok"):
        print(f"\nErgebnis:")
        print(f"  Gesamt gefunden:   {result['total']:,}")
        print(f"  Neu importiert:    {result['inserted']:,}")
        print(f"  Pfade aktualisiert:{result['updated']:,}")
        print(f"  Fehler:            {result['errors']:,}")
        print(f"  Dauer:             {elapsed:.1f}s")
        if args.trocken:
            print("\n  (Trockenlauf — nichts geschrieben)")
    else:
        print(f"\nFehler: {result.get('error')}")
        sys.exit(1)
