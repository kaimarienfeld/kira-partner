"""
kunden_mail_retroaktiv.py — Retroaktiver Mail-Scan gegen Lexware-Kundenliste

Session: session-tt (2026-04-10)

Scannt mail_index.db und verknüpft vorhandene Mails mit Lexware-Kunden.
Erstellt kunden_aktivitaeten für jede zugeordnete Mail.

Ablauf:
  1. Alle E-Mails/Domains aus kunden_identitaeten laden (nur Lexware-Quellen)
  2. Alle Mails aus mail_index.db lesen
  3. Absender-Match → kunden_aktivitaeten erstellen
  4. anzahl_mails + letztkontakt + erstkontakt aktualisieren

Aufruf:
  python kunden_mail_retroaktiv.py [--dry-run] [--seit YYYY-MM-DD] [--bis YYYY-MM-DD]
"""

import sqlite3
import json
import logging
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger("kunden_mail_retroaktiv")

SCRIPTS_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
KUNDEN_DB = KNOWLEDGE_DIR / "kunden.db"
MAIL_INDEX_DB = KNOWLEDGE_DIR / "mail_index.db"


def _extract_email(absender: str) -> str:
    """Extrahiert E-Mail aus 'Name <email>' oder plain email."""
    m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", absender or "")
    return m.group(0).lower() if m else (absender or "").lower().strip()


def _extract_domain(email: str) -> str:
    """Extrahiert Domain aus E-Mail."""
    parts = email.split("@")
    return parts[1].lower() if len(parts) == 2 else ""


def scan_mails(dry_run: bool = False, seit: str = None, bis: str = None) -> dict:
    """
    Scannt mail_index.db und ordnet Mails Lexware-Kunden zu.

    Returns:
        dict: {"mails_gesamt": N, "zugeordnet": N, "aktivitaeten_erstellt": N,
               "kunden_aktualisiert": N, "nicht_zugeordnet": N, "details": [...]}
    """
    stats = {
        "mails_gesamt": 0,
        "zugeordnet": 0,
        "aktivitaeten_erstellt": 0,
        "kunden_aktualisiert": 0,
        "nicht_zugeordnet": 0,
        "kunden_mailcount": {},
        "details": [],
    }

    if not KUNDEN_DB.exists() or not MAIL_INDEX_DB.exists():
        stats["details"].append("DB-Dateien fehlen")
        return stats

    # 1. Identitäten laden (Lexware-Quellen)
    kdb = sqlite3.connect(str(KUNDEN_DB))
    kdb.row_factory = sqlite3.Row

    # Email → kunden_id Mapping
    email_map: dict[str, int] = {}
    domain_map: dict[str, int] = {}

    for row in kdb.execute(
        "SELECT kunden_id, typ, LOWER(wert) as wert FROM kunden_identitaeten WHERE quelle = 'lexware'"
    ).fetchall():
        if row["typ"] == "mail":
            email_map[row["wert"]] = row["kunden_id"]
        elif row["typ"] == "domain":
            domain_map[row["wert"]] = row["kunden_id"]

    stats["details"].append(f"Identitäten geladen: {len(email_map)} Emails, {len(domain_map)} Domains")

    # Bereits vorhandene Aktivitäten laden (Dedup)
    existing_activities = set()
    for row in kdb.execute(
        "SELECT quelle_id FROM kunden_aktivitaeten WHERE quelle_tabelle = 'mail'"
    ).fetchall():
        existing_activities.add(row["quelle_id"])

    # 2. Mails lesen
    mdb = sqlite3.connect(str(MAIL_INDEX_DB))
    mdb.row_factory = sqlite3.Row

    query = "SELECT id, absender, betreff, datum, datum_iso, konto FROM mails WHERE 1=1"
    params = []
    if seit:
        query += " AND datum_iso >= ?"
        params.append(seit)
    if bis:
        query += " AND datum_iso <= ?"
        params.append(bis)
    query += " ORDER BY datum_iso ASC"

    mails = mdb.execute(query, params).fetchall()
    stats["mails_gesamt"] = len(mails)
    mdb.close()

    # 3. Matching
    kunden_stats: dict[int, dict] = defaultdict(lambda: {
        "count": 0, "erstkontakt": None, "letztkontakt": None
    })

    aktivitaeten_batch = []

    for mail in mails:
        absender_email = _extract_email(mail["absender"])
        if not absender_email:
            stats["nicht_zugeordnet"] += 1
            continue

        # Exakter Email-Match
        kunden_id = email_map.get(absender_email)

        # Domain-Match als Fallback
        if not kunden_id:
            domain = _extract_domain(absender_email)
            if domain:
                kunden_id = domain_map.get(domain)

        if not kunden_id:
            stats["nicht_zugeordnet"] += 1
            continue

        stats["zugeordnet"] += 1
        mail_id = str(mail["id"])

        # Statistik pro Kunde
        ks = kunden_stats[kunden_id]
        ks["count"] += 1
        datum = mail["datum_iso"] or mail["datum"] or ""
        if datum:
            if not ks["erstkontakt"] or datum < ks["erstkontakt"]:
                ks["erstkontakt"] = datum
            if not ks["letztkontakt"] or datum > ks["letztkontakt"]:
                ks["letztkontakt"] = datum

        # Aktivität erstellen (Dedup)
        if mail_id not in existing_activities:
            betreff = mail["betreff"] or "(kein Betreff)"
            zusammenfassung = f"Mail von {absender_email}: {betreff[:100]}"
            aktivitaeten_batch.append((
                kunden_id, None, None,  # kunden_id, projekt_id, fall_id
                "mail",  # ereignis_typ
                mail_id,  # quelle_id
                "mail",  # quelle_tabelle
                zusammenfassung,
                "",  # volltext_auszug (leer, spart Platz)
                datum or datetime.now().isoformat(timespec="seconds"),
                1,  # sichtbar_in_verlauf
            ))
            stats["aktivitaeten_erstellt"] += 1

    stats["kunden_mailcount"] = {
        str(kid): ks["count"] for kid, ks in kunden_stats.items()
    }

    if dry_run:
        stats["details"].append(f"[DRY-RUN] {stats['zugeordnet']} Mails zugeordnet, "
                                f"{stats['aktivitaeten_erstellt']} Aktivitäten, "
                                f"{len(kunden_stats)} Kunden betroffen")
        kdb.close()
        return stats

    # 4. Aktivitäten in Batch einfügen
    if aktivitaeten_batch:
        kdb.executemany("""
            INSERT INTO kunden_aktivitaeten
            (kunden_id, projekt_id, fall_id, ereignis_typ, quelle_id, quelle_tabelle,
             zusammenfassung, volltext_auszug, erstellt_am, sichtbar_in_verlauf)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, aktivitaeten_batch)

    # 5. Kunden-Statistiken aktualisieren
    for kid, ks in kunden_stats.items():
        kdb.execute("""
            UPDATE kunden SET
                anzahl_mails = ?,
                erstkontakt = CASE WHEN erstkontakt IS NULL OR erstkontakt > ? THEN ? ELSE erstkontakt END,
                letztkontakt = CASE WHEN letztkontakt IS NULL OR letztkontakt < ? THEN ? ELSE letztkontakt END,
                aktualisiert_am = datetime('now')
            WHERE id = ?
        """, (ks["count"], ks["erstkontakt"], ks["erstkontakt"],
              ks["letztkontakt"], ks["letztkontakt"], kid))
        stats["kunden_aktualisiert"] += 1

    kdb.commit()
    kdb.close()

    # Runtime-Log
    try:
        from runtime_log import elog
        elog("mail_retroaktiv_scan",
             f"Retroaktiver Scan: {stats['zugeordnet']}/{stats['mails_gesamt']} Mails zugeordnet, "
             f"{stats['aktivitaeten_erstellt']} Aktivitäten, {stats['kunden_aktualisiert']} Kunden",
             json.dumps(stats, ensure_ascii=False, default=str))
    except Exception:
        pass

    return stats


# CLI-Aufruf
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    dry_run = "--dry-run" in sys.argv or "--trocken" in sys.argv
    seit = None
    bis = None

    for i, arg in enumerate(sys.argv):
        if arg == "--seit" and i + 1 < len(sys.argv):
            seit = sys.argv[i + 1]
        if arg == "--bis" and i + 1 < len(sys.argv):
            bis = sys.argv[i + 1]

    if dry_run:
        print("=== DRY-RUN: Keine Aenderungen ===\n")

    print(f"Zeitraum: {seit or 'Anfang'} bis {bis or 'heute'}")
    result = scan_mails(dry_run=dry_run, seit=seit, bis=bis)

    print(f"\n=== Ergebnis ===")
    print(f"  Mails gesamt:            {result['mails_gesamt']}")
    print(f"  Zugeordnet:              {result['zugeordnet']}")
    print(f"  Aktivitaeten erstellt:   {result['aktivitaeten_erstellt']}")
    print(f"  Kunden aktualisiert:     {result['kunden_aktualisiert']}")
    print(f"  Nicht zugeordnet:        {result['nicht_zugeordnet']}")

    if result.get("kunden_mailcount"):
        print(f"\n  Top-10 Kunden nach Mails:")
        sorted_k = sorted(result["kunden_mailcount"].items(),
                          key=lambda x: x[1], reverse=True)[:10]
        for kid, count in sorted_k:
            print(f"    Kunde #{kid}: {count} Mails")

    if result["details"]:
        print(f"\n  Details:")
        for d in result["details"][:10]:
            print(f"    {d}")
