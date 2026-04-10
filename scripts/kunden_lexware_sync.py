"""
kunden_lexware_sync.py — Lexware Office → kunden.db Synchronisation

Session: session-tt (2026-04-10)

REGEL-09: Lexware ist die EINZIGE Kunden-Stammdatenquelle.
Kunden kommen ausschließlich aus Lexware Office — NICHT aus dem Mail-Archiv.

Ablauf:
  1. Liest alle Kontakte aus tasks.db/lexware_kontakte (bereits via lexware_client synchronisiert)
  2. Für jeden Kontakt: INSERT/UPDATE in kunden.db/kunden
  3. Alle E-Mail-Adressen → kunden_identitaeten (confidence='eindeutig', quelle='lexware')
  4. Logging via elog()

Aufruf:
  - Direkt: python kunden_lexware_sync.py [--dry-run]
  - Aus server.py: POST /api/crm/lexware-sync
  - Background: kira_proaktiv.py (6h-Intervall)
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("kunden_lexware_sync")

SCRIPTS_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
KUNDEN_DB = KNOWLEDGE_DIR / "kunden.db"
TASKS_DB = KNOWLEDGE_DIR / "tasks.db"

# Config lesen
CONFIG_PATH = SCRIPTS_DIR / "config.json"


def _load_config():
    """Lädt config.json."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _elog(event_type, summary, details=None):
    """Runtime-Log Eintrag — nutzt elog() wenn verfügbar."""
    try:
        from runtime_log import elog
        elog(event_type, summary, details)
    except ImportError:
        logger.info(f"[{event_type}] {summary}")


def _extract_emails(payload: dict) -> list[str]:
    """Extrahiert alle E-Mail-Adressen aus einem Lexware-Kontakt-Payload.

    Quellen (Reihenfolge):
      1. emailAddresses.business[]
      2. emailAddresses.private[]
      3. emailAddresses.other[]
      4. company.contactPersons[].emailAddress
    """
    emails = set()

    email_addrs = payload.get("emailAddresses") or {}
    for category in ["business", "private", "other"]:
        for addr in email_addrs.get(category, []):
            if addr and addr.strip():
                emails.add(addr.strip().lower())

    # contactPersons können eigene E-Mails haben
    company = payload.get("company") or {}
    for cp in company.get("contactPersons", []):
        addr = cp.get("emailAddress", "")
        if addr and addr.strip():
            emails.add(addr.strip().lower())

    return sorted(emails)


def _extract_name(payload: dict) -> str:
    """Extrahiert den Anzeigenamen aus einem Lexware-Kontakt."""
    company = payload.get("company")
    if company:
        return company.get("name", "").strip()

    person = payload.get("person")
    if person:
        parts = [
            person.get("salutation", ""),
            person.get("firstName", ""),
            person.get("lastName", ""),
        ]
        return " ".join(p for p in parts if p).strip()

    return ""


def _extract_ansprechpartner(payload: dict) -> str:
    """Extrahiert den Hauptansprechpartner."""
    company = payload.get("company") or {}
    for cp in company.get("contactPersons", []):
        if cp.get("primary"):
            parts = [cp.get("firstName", ""), cp.get("lastName", "")]
            name = " ".join(p for p in parts if p).strip()
            if name:
                return name
    # Falls kein primary, erster nehmen
    for cp in company.get("contactPersons", []):
        parts = [cp.get("firstName", ""), cp.get("lastName", "")]
        name = " ".join(p for p in parts if p).strip()
        if name:
            return name
    return ""


def _extract_kundentyp(payload: dict) -> str:
    """Ermittelt Kundentyp: geschaeft wenn company vorhanden, sonst privat."""
    if payload.get("company"):
        return "geschaeft"
    return "privat"


def sync_lexware_kunden(dry_run: bool = False) -> dict:
    """
    Synchronisiert Lexware-Kontakte aus tasks.db → kunden.db.

    Returns:
        dict: {"neu": N, "aktualisiert": N, "identitaeten_neu": N,
               "uebersprungen": N, "fehler": N, "details": [...]}
    """
    stats = {
        "neu": 0,
        "aktualisiert": 0,
        "identitaeten_neu": 0,
        "uebersprungen": 0,
        "fehler": 0,
        "details": [],
    }

    if not TASKS_DB.exists():
        stats["details"].append("tasks.db nicht gefunden")
        return stats
    if not KUNDEN_DB.exists():
        stats["details"].append("kunden.db nicht gefunden")
        return stats

    # Lese alle Lexware-Kontakte aus tasks.db
    tasks_db = sqlite3.connect(str(TASKS_DB))
    tasks_db.row_factory = sqlite3.Row
    try:
        kontakte = tasks_db.execute(
            "SELECT lexware_id, name, email, kundennummer, telefon, mobil, "
            "ustid, steuernummer, notiz, adresse_json, payload_json "
            "FROM lexware_kontakte"
        ).fetchall()
    finally:
        tasks_db.close()

    if not kontakte:
        stats["details"].append("Keine Lexware-Kontakte in tasks.db gefunden")
        return stats

    # kunden.db öffnen
    kunden_db = sqlite3.connect(str(KUNDEN_DB))
    kunden_db.row_factory = sqlite3.Row
    now = datetime.now().isoformat(timespec="seconds")

    try:
        for k in kontakte:
            lex_id = k["lexware_id"]
            if not lex_id:
                stats["uebersprungen"] += 1
                continue

            # Payload parsen für erweiterte Infos
            try:
                payload = json.loads(k["payload_json"]) if k["payload_json"] else {}
            except (json.JSONDecodeError, TypeError):
                payload = {}

            # Archivierte Kontakte überspringen
            if payload.get("archived"):
                stats["uebersprungen"] += 1
                stats["details"].append(f"Archiviert übersprungen: {k['name']}")
                continue

            name = _extract_name(payload) or k["name"] or ""
            ansprechpartner = _extract_ansprechpartner(payload)
            kundentyp = _extract_kundentyp(payload)
            emails = _extract_emails(payload)
            # UNIQUE constraint auf kunden.email → NULL statt leerer String
            primary_email = emails[0] if emails else (k["email"] or None)

            # Kundennummer
            kundennummer = k["kundennummer"] or ""

            if dry_run:
                stats["details"].append(
                    f"[DRY-RUN] {name} (KNr {kundennummer}, {len(emails)} E-Mails, typ={kundentyp})"
                )
                stats["neu"] += 1
                stats["identitaeten_neu"] += len(emails)
                continue

            # Prüfe ob Kunde bereits existiert (via lexware_id)
            existing = kunden_db.execute(
                "SELECT id FROM kunden WHERE lexware_id = ?", (lex_id,)
            ).fetchone()

            metadata = json.dumps({
                "kundennummer": kundennummer,
                "telefon": k["telefon"] or "",
                "mobil": k["mobil"] or "",
                "ustid": k["ustid"] or "",
                "steuernummer": k["steuernummer"] or "",
                "adresse": json.loads(k["adresse_json"]) if k["adresse_json"] else {},
                "notiz": k["notiz"] or "",
                "sync_am": now,
            }, ensure_ascii=False)

            if existing:
                # UPDATE
                kunden_db.execute("""
                    UPDATE kunden SET
                        name = ?,
                        email = ?,
                        firmenname = ?,
                        ansprechpartner = ?,
                        kundentyp = ?,
                        status = 'aktiv',
                        aktualisiert_am = ?,
                        metadata_json = ?
                    WHERE lexware_id = ?
                """, (
                    name, primary_email,
                    name if kundentyp == "geschaeft" else "",
                    ansprechpartner, kundentyp, now,
                    metadata, lex_id,
                ))
                kunden_id = existing["id"]
                stats["aktualisiert"] += 1
            else:
                # Bei Email-Duplikaten: Email auf NULL setzen und über lexware_id identifizieren
                insert_email = primary_email
                if primary_email:
                    dup_check = kunden_db.execute(
                        "SELECT id FROM kunden WHERE email = ?", (primary_email,)
                    ).fetchone()
                    if dup_check:
                        insert_email = None
                        stats["details"].append(
                            f"Email-Duplikat: {primary_email} bereits bei Kunde #{dup_check['id']}, "
                            f"{name} ohne primary_email angelegt"
                        )

                cur = kunden_db.execute("""
                    INSERT INTO kunden (
                        email, name, erstkontakt, letztkontakt, anzahl_mails,
                        hauptkanal, notiz, firmenname, ansprechpartner,
                        kundentyp, status, lexware_id, kundenwert,
                        fit_score, zahlungsverhalten_score, risiko_score,
                        metadata_json, aktualisiert_am
                    ) VALUES (?, ?, ?, ?, 0, 'mail', ?, ?, ?, ?, 'aktiv', ?, 0, 0, 0, 0, ?, ?)
                """, (
                    insert_email, name, now, now,
                    k["notiz"] or "",
                    name if kundentyp == "geschaeft" else "",
                    ansprechpartner, kundentyp, lex_id,
                    metadata, now,
                ))
                kunden_id = cur.lastrowid
                stats["neu"] += 1
                # Nachqualifizierung für neue Kunden starten
                if not dry_run:
                    try:
                        kunden_db.commit()  # erst committen damit ID sicher
                        from kunden_classifier import _nachqualifizierung_starten
                        _nachqualifizierung_starten(kunden_id)
                    except Exception as nq_err:
                        logger.debug(f"Nachqualifizierung fuer {kunden_id}: {nq_err}")

            # E-Mail-Identitäten synchronisieren
            for email_addr in emails:
                try:
                    kunden_db.execute("""
                        INSERT OR IGNORE INTO kunden_identitaeten
                            (kunden_id, typ, wert, confidence, verifiziert, quelle, erstellt_am)
                        VALUES (?, 'mail', ?, 'eindeutig', 1, 'lexware', ?)
                    """, (kunden_id, email_addr, now))
                    if kunden_db.total_changes:
                        stats["identitaeten_neu"] += 1
                except Exception as e:
                    logger.warning(f"Identität {email_addr} für Kunde {kunden_id}: {e}")

            # Telefon als Identität
            for tel_type, tel_val in [("telefon", k["telefon"]), ("mobil", k["mobil"])]:
                if tel_val and tel_val.strip():
                    try:
                        kunden_db.execute("""
                            INSERT OR IGNORE INTO kunden_identitaeten
                                (kunden_id, typ, wert, confidence, verifiziert, quelle, erstellt_am)
                            VALUES (?, 'telefon', ?, 'eindeutig', 1, 'lexware', ?)
                        """, (kunden_id, tel_val.strip(), now))
                    except Exception:
                        pass

            # Domain als Identität (für geschäftliche Mails)
            for email_addr in emails:
                if "@" in email_addr:
                    domain = email_addr.split("@")[1]
                    # Nur bei geschäftlichen Domains (nicht gmail, web.de etc.)
                    freemail = {"gmail.com", "web.de", "gmx.de", "gmx.net", "yahoo.de",
                                "yahoo.com", "hotmail.com", "outlook.com", "outlook.de",
                                "t-online.de", "googlemail.com", "icloud.com", "me.com",
                                "aol.com", "mail.de", "freenet.de", "posteo.de"}
                    if domain not in freemail:
                        try:
                            kunden_db.execute("""
                                INSERT OR IGNORE INTO kunden_identitaeten
                                    (kunden_id, typ, wert, confidence, verifiziert, quelle, erstellt_am)
                                VALUES (?, 'domain', ?, 'wahrscheinlich', 0, 'lexware', ?)
                            """, (kunden_id, domain, now))
                        except Exception:
                            pass

        if not dry_run:
            kunden_db.commit()
            _elog("lexware_sync_abgeschlossen",
                  f"Lexware-Sync: {stats['neu']} neu, {stats['aktualisiert']} aktualisiert, "
                  f"{stats['identitaeten_neu']} Identitäten",
                  json.dumps(stats, ensure_ascii=False))

    except Exception as e:
        stats["fehler"] += 1
        stats["details"].append(f"Fehler: {e}")
        logger.error(f"Lexware-Sync Fehler: {e}", exc_info=True)
    finally:
        kunden_db.close()

    return stats


def get_sync_status() -> dict:
    """Gibt Status der letzten Synchronisation zurück."""
    if not KUNDEN_DB.exists():
        return {"kunden": 0, "identitaeten": 0, "letzte_sync": None}

    db = sqlite3.connect(str(KUNDEN_DB))
    try:
        kunden = db.execute(
            "SELECT COUNT(*) FROM kunden WHERE lexware_id IS NOT NULL AND lexware_id != ''"
        ).fetchone()[0]
        identitaeten = db.execute(
            "SELECT COUNT(*) FROM kunden_identitaeten WHERE quelle = 'lexware'"
        ).fetchone()[0]
        letzte = db.execute(
            "SELECT MAX(aktualisiert_am) FROM kunden WHERE lexware_id IS NOT NULL"
        ).fetchone()[0]
        return {
            "kunden": kunden,
            "identitaeten": identitaeten,
            "letzte_sync": letzte,
        }
    finally:
        db.close()


# CLI-Aufruf
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    dry_run = "--dry-run" in sys.argv or "--trocken" in sys.argv

    if dry_run:
        print("=== DRY-RUN: Keine Änderungen ===\n")

    result = sync_lexware_kunden(dry_run=dry_run)

    print(f"\n=== Ergebnis ===")
    print(f"  Neue Kunden:       {result['neu']}")
    print(f"  Aktualisiert:      {result['aktualisiert']}")
    print(f"  Neue Identitäten:  {result['identitaeten_neu']}")
    print(f"  Übersprungen:      {result['uebersprungen']}")
    print(f"  Fehler:            {result['fehler']}")

    if result["details"]:
        print(f"\n  Details:")
        for d in result["details"][:20]:
            print(f"    {d}")

    if not dry_run:
        status = get_sync_status()
        print(f"\n=== Aktueller Stand ===")
        print(f"  Kunden (Lexware):  {status['kunden']}")
        print(f"  Identitäten:       {status['identitaeten']}")
        print(f"  Letzte Sync:       {status['letzte_sync']}")
