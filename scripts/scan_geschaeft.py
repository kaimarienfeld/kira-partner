#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_geschaeft.py — Scanner für Ausgangsrechnungen, Angebote, Mahnungen.
Liest Mail-Archiv und füllt die Tabellen in tasks.db.
"""
import json, sqlite3, re, os
from pathlib import Path
from datetime import datetime, timedelta

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"
KUNDEN_DB     = KNOWLEDGE_DIR / "kunden.db"

ARCHIV_ROOT = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\Archiv")
INVOICE_SENT = ARCHIV_ROOT / "invoice_sichtbeton-cire_de" / "Gesendete Elemente"
INVOICE_SENT2= ARCHIV_ROOT / "invoice_sichtbeton-cire_de" / "Gesendete Objekte"
INFO_SENT    = ARCHIV_ROOT / "info_raumkult_eu" / "Gesendete Elemente"
ANFRAGE_SENT = ARCHIV_ROOT / "anfrage_raumkult_eu" / "Gesendete Elemente"

# Alle Mailbox-INBOXen für Response-Suche
ALL_INBOXES = [
    ARCHIV_ROOT / "invoice_sichtbeton-cire_de" / "INBOX",
    ARCHIV_ROOT / "info_raumkult_eu" / "INBOX",
    ARCHIV_ROOT / "anfrage_raumkult_eu" / "INBOX",
    ARCHIV_ROOT / "shop_sichtbeton-cire_de" / "INBOX",
    ARCHIV_ROOT / "kaimrf_rauMKultSichtbeton_onmicrosoft_com" / "INBOX",
]

RE_NUMMER_PAT = re.compile(r'RE-SB\d+', re.IGNORECASE)
A_NUMMER_PAT  = re.compile(r'A-SB\d+', re.IGNORECASE)
CUTOFF_BEZAHLT = "2026-02-01"  # Alles davor = bezahlt/bearbeitet


def read_mail_json(mail_dir):
    """Liest mail.json aus einem Mail-Ordner."""
    mj = mail_dir / "mail.json"
    if not mj.exists():
        return None
    try:
        return json.loads(mj.read_text('utf-8'))
    except:
        return None


def extract_email_from_field(field):
    """Extrahiert E-Mail-Adresse aus 'Name <email>' Format."""
    if not field:
        return ""
    m = re.search(r'<([^>]+@[^>]+)>', field)
    return m.group(1).lower() if m else field.strip().lower()


def extract_name_from_field(field):
    """Extrahiert Name aus 'Name <email>' Format."""
    if not field:
        return ""
    m = re.match(r'"?([^"<]+)"?\s*<', field)
    return m.group(1).strip() if m else ""


def find_attachments_path(mail_dir):
    """Findet den Anhang-Pfad für ein Mail-Verzeichnis."""
    att = mail_dir / "attachments"
    if att.exists() and att.is_dir():
        return str(att)
    return ""


def scan_sent_folders(patterns, folders):
    """Scannt mehrere Gesendete-Ordner nach Mails deren Verzeichnisname patterns matcht."""
    results = []
    for folder in folders:
        if not folder.exists():
            continue
        for entry in folder.iterdir():
            if not entry.is_dir() or entry.name.startswith('_'):
                continue
            dirname = entry.name
            if any(p.lower() in dirname.lower() for p in patterns):
                mail = read_mail_json(entry)
                if mail:
                    mail['_dir'] = entry
                    mail['_dirname'] = dirname
                    results.append(mail)
    return results


def scan_ausgangsrechnungen(db):
    """Scannt Gesendete für Ausgangsrechnungen (RE-SB)."""
    print("\n1. Ausgangsrechnungen scannen...")
    mails = scan_sent_folders(
        ["Rechnung RE-SB", "Abschlagsrechnung RE-SB"],
        [INVOICE_SENT, INVOICE_SENT2]
    )

    count_new, count_skip = 0, 0
    for m in mails:
        betreff = m.get("betreff", "") or ""
        match = RE_NUMMER_PAT.search(betreff)
        if not match:
            continue
        re_nr = match.group(0).upper()

        # Duplikat-Check
        existing = db.execute("SELECT id FROM ausgangsrechnungen WHERE re_nummer=?", (re_nr,)).fetchone()
        if existing:
            count_skip += 1
            continue

        datum = m.get("datum", "") or ""
        kunde_email = extract_email_from_field(m.get("an", ""))
        kunde_name = extract_name_from_field(m.get("an", ""))
        mail_ref = m.get("message_id", "")
        anh_pfad = find_attachments_path(m['_dir'])

        # Status: Vor Cutoff = bezahlt
        status = "bezahlt" if datum[:10] < CUTOFF_BEZAHLT else "offen"

        db.execute("""INSERT INTO ausgangsrechnungen
            (re_nummer, datum, kunde_email, kunde_name, betreff, mail_ref, anhaenge_pfad, status)
            VALUES (?,?,?,?,?,?,?,?)""",
            (re_nr, datum, kunde_email, kunde_name, betreff, mail_ref, anh_pfad, status))
        count_new += 1

    db.commit()
    print(f"   {count_new} neue Rechnungen, {count_skip} übersprungen (Duplikate)")
    return count_new


def scan_angebote(db):
    """Scannt Gesendete für Angebote (A-SB)."""
    print("\n2. Angebote scannen...")

    # Angebote aus invoice-Ordner
    mails = scan_sent_folders(
        ["Angebot von rauMKult", "Angebot A-SB"],
        [INVOICE_SENT, INVOICE_SENT2]
    )

    count_new, count_skip = 0, 0
    for m in mails:
        betreff = m.get("betreff", "") or ""
        match = A_NUMMER_PAT.search(betreff)
        if not match:
            continue
        a_nr = match.group(0).upper()

        # Duplikat-Check
        existing = db.execute("SELECT id FROM angebote WHERE a_nummer=?", (a_nr,)).fetchone()
        if existing:
            count_skip += 1
            continue

        datum = m.get("datum", "") or ""
        kunde_email = extract_email_from_field(m.get("an", ""))
        kunde_name = extract_name_from_field(m.get("an", ""))
        mail_ref = m.get("message_id", "")
        anh_pfad = find_attachments_path(m['_dir'])

        # Status: Vor Cutoff = bearbeitet
        status = "bearbeitet" if datum[:10] < CUTOFF_BEZAHLT else "offen"

        db.execute("""INSERT INTO angebote
            (a_nummer, datum, kunde_email, kunde_name, betreff, mail_ref, anhaenge_pfad, status)
            VALUES (?,?,?,?,?,?,?,?)""",
            (a_nr, datum, kunde_email, kunde_name, betreff, mail_ref, anh_pfad, status))
        count_new += 1

    db.commit()
    print(f"   {count_new} neue Angebote, {count_skip} übersprungen")

    # Nachfass-Erinnerungen aus info-Ordner verknüpfen
    print("   Nachfass-Mails suchen...")
    follow_ups = scan_sent_folders(
        ["Erinnerung", "Nachfass"],
        [INFO_SENT, ANFRAGE_SENT]
    )
    linked = 0
    for m in follow_ups:
        betreff = m.get("betreff", "") or ""
        match = A_NUMMER_PAT.search(betreff)
        if not match:
            continue
        a_nr = match.group(0).upper()
        datum = m.get("datum", "") or ""
        row = db.execute("SELECT id, nachfass_count, letzter_nachfass FROM angebote WHERE a_nummer=?", (a_nr,)).fetchone()
        if row:
            new_count = (row[1] or 0) + 1
            # Nur hochzählen wenn Datum neuer
            if not row[2] or datum > row[2]:
                db.execute("UPDATE angebote SET nachfass_count=?, letzter_nachfass=? WHERE id=?",
                           (new_count, datum, row[0]))
                linked += 1
    db.commit()
    print(f"   {linked} Nachfass-Mails verknüpft")
    return count_new


def scan_mahnungen(db):
    """Scannt Gesendete für Zahlungserinnerungen/Mahnungen an Kunden."""
    print("\n3. Zahlungserinnerungen/Mahnungen scannen...")
    mails = scan_sent_folders(
        ["Erinnerung RE-SB", "Mahnung"],
        [INVOICE_SENT, INVOICE_SENT2]
    )

    linked = 0
    for m in mails:
        betreff = m.get("betreff", "") or ""
        match = RE_NUMMER_PAT.search(betreff)
        if not match:
            continue
        re_nr = match.group(0).upper()
        datum = m.get("datum", "") or ""
        is_mahnung = "mahnung" in betreff.lower()

        row = db.execute("SELECT id, mahnung_count FROM ausgangsrechnungen WHERE re_nummer=?", (re_nr,)).fetchone()
        if row:
            new_count = (row[1] or 0) + 1
            db.execute("UPDATE ausgangsrechnungen SET mahnung_count=?, letzte_mahnung=? WHERE id=?",
                       (new_count, datum, row[0]))
            linked += 1

    db.commit()
    print(f"   {linked} Mahnungen mit Rechnungen verknüpft")


def cross_reference_responses(db):
    """Sucht in allen INBOXen nach Antworten auf Angebote."""
    print("\n4. Antworten auf Angebote suchen...")
    angebote = db.execute("SELECT id, a_nummer, kunde_email FROM angebote WHERE status='offen'").fetchall()
    if not angebote:
        print("   Keine offenen Angebote zum Prüfen")
        return

    # Lade alle Kunden-Emails aus INBOXen
    inbox_mails = {}
    for inbox in ALL_INBOXES:
        if not inbox.exists():
            continue
        for entry in inbox.iterdir():
            if not entry.is_dir() or entry.name.startswith('_'):
                continue
            mail = read_mail_json(entry)
            if mail:
                absender_email = extract_email_from_field(mail.get("absender", ""))
                if absender_email:
                    inbox_mails.setdefault(absender_email, []).append({
                        "betreff": mail.get("betreff", ""),
                        "datum": mail.get("datum", ""),
                    })

    found = 0
    for ang in angebote:
        a_nr = ang[1]
        email = ang[2]
        if not email:
            continue
        responses = inbox_mails.get(email, [])
        for resp in responses:
            betr = resp["betreff"].lower()
            # Direkte Referenz auf Angebotsnummer
            if a_nr.lower() in betr:
                found += 1
                break
            # Allgemeine Antwort-Keywords
            if any(kw in betr for kw in ["angebot", "auftrag", "zusage", "beauftrag"]):
                found += 1
                break

    print(f"   {found} mögliche Antworten gefunden (manuelle Prüfung empfohlen)")


def set_nachfass_schedule(db):
    """Setzt naechster_nachfass für offene Angebote ohne Nachfass."""
    print("\n5. Nachfass-Zeitplan setzen...")
    try:
        config = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
    except:
        config = {}
    nf = config.get("nachfass", {})
    intervall_1 = nf.get("intervall_1_tage", 10)

    rows = db.execute("""SELECT id, datum, nachfass_count FROM angebote
                         WHERE status='offen' AND naechster_nachfass IS NULL""").fetchall()
    updated = 0
    for r in rows:
        try:
            datum = datetime.strptime(r[1][:10], "%Y-%m-%d")
            nachfass_count = r[2] or 0
            if nachfass_count == 0:
                next_date = datum + timedelta(days=intervall_1)
            else:
                next_date = datetime.now() + timedelta(days=intervall_1)
            db.execute("UPDATE angebote SET naechster_nachfass=? WHERE id=?",
                       (next_date.strftime("%Y-%m-%d"), r[0]))
            updated += 1
        except:
            continue
    db.commit()
    print(f"   {updated} Nachfass-Termine gesetzt")


def print_summary(db):
    """Druckt Zusammenfassung."""
    print("\n" + "="*50)
    print("ZUSAMMENFASSUNG")
    print("="*50)

    # Ausgangsrechnungen
    for r in db.execute("SELECT status, COUNT(*) c, COALESCE(SUM(betrag_brutto),0) s FROM ausgangsrechnungen GROUP BY status ORDER BY status"):
        print(f"  Ausgangsrechnungen [{r[0]}]: {r[1]} ({r[2]:,.2f} EUR)")

    # Angebote
    for r in db.execute("SELECT status, COUNT(*) c FROM angebote GROUP BY status ORDER BY status"):
        print(f"  Angebote [{r[0]}]: {r[1]}")

    # Mahnungen
    row = db.execute("SELECT COUNT(*) FROM ausgangsrechnungen WHERE mahnung_count > 0").fetchone()
    print(f"  Rechnungen mit Mahnungen: {row[0]}")

    # Offene Positionen
    offen = db.execute("SELECT COUNT(*), COALESCE(SUM(betrag_brutto),0) FROM ausgangsrechnungen WHERE status='offen'").fetchone()
    print(f"\n  OFFENE RECHNUNGEN: {offen[0]} ({offen[1]:,.2f} EUR)")

    ang_offen = db.execute("SELECT COUNT(*) FROM angebote WHERE status='offen'").fetchone()
    print(f"  OFFENE ANGEBOTE: {ang_offen[0]}")


def main():
    print("=== Geschäft-Scanner v1 ===")
    print(f"Archiv: {ARCHIV_ROOT}")

    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row

    scan_ausgangsrechnungen(db)
    scan_angebote(db)
    scan_mahnungen(db)
    cross_reference_responses(db)
    set_nachfass_schedule(db)
    print_summary(db)

    db.close()
    print("\nFertig.")


if __name__ == "__main__":
    main()
