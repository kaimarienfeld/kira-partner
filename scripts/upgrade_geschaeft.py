#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Geschäft-Upgrade: Reklassifizierung, Anhänge verknüpfen, Schema erweitern.
Unterscheidet echte Eingangsrechnungen (muss bezahlt werden) von Routine-Zahlungen.
"""
import sqlite3, re, os
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
TASKS_DB  = KNOWLEDGE_DIR / "tasks.db"
KUNDEN_DB = KNOWLEDGE_DIR / "kunden.db"

# Domains/Absender die ROUTINE-Zahlungen sind (schon bezahlt / automatisch)
ROUTINE_DOMAINS = {
    "paypal.de", "paypal.com",
    "mail.anthropic.com", "anthropic.com",
    "ecwid.com",
    "avast.com", "avg.com", "nortonlifelock.com",
    "apple.com", "microsoft.com",
    "google.com", "googleapis.com",
    "amazon.de", "amazon.com",
    "stripe.com",
    "gocardless.com",
    "hetzner.com", "hetzner.de",
    "ionos.de", "ionos.com",
    "strato.de",
    "hosteurope.de",
    "mailbird.com",
    "canva.com",
    "figma.com",
    "adobe.com",
    "notion.so",
    "descript.com",
    "cursor.com", "cursor.sh",
    "obsbot.com",
    "vevor.com", "vevor.de",
    "df.eu",                        # domainFactory Hosting
    "wondershare.com",              # Wondershare Software
    "bausep.de",                    # Bausep Online-Shop
    "iwoca.de", "iwoca.com",        # iwoca Kredit (automatisch)
}

# Absender-Patterns für echte Eingangsrechnungen (von Mitarbeitern/Lieferanten)
ECHTE_RECHNUNG_PATTERNS = [
    "lexware", "belege.lexware", "versand@belege",
    "sevdesk", "fastbill", "datev",
    "hantke", "marcus.hantke",  # Bekannter Mitarbeiter
]

# Betreff-Patterns die auf "schon bezahlt"-Belege hinweisen
ROUTINE_BETREFF = [
    "your receipt", "ihr beleg", "ihre zahlung an",
    "sie haben eine zahlung", "payment confirmation",
    "bevorstehende zahlung", "upcoming payment",
    "subscription", "abo", "verlängerung",
    "renewal", "billing", "invoice from",
]

# Betreff-Patterns die auf echte Eingangsrechnung hinweisen
EINGANG_BETREFF = [
    "rechnung re", "rechnung nr", "rechnung von",
    "invoice re", "zahlungsaufforderung",
]

# Betreff die auf Zahlungserinnerung/Mahnung hinweisen
MAHNUNG_BETREFF = [
    "zahlungserinnerung", "payment reminder",
    "mahnung", "erinnerung an zahlung",
    "überfällig", "overdue", "ausstehende zahlung",
]


def get_email_domain(email):
    if not email or '@' not in email:
        return ""
    return email.split('@')[-1].lower()


def is_routine_domain(domain):
    """Prüft ob Domain (oder Subdomain davon) in ROUTINE_DOMAINS ist."""
    if not domain:
        return False
    if domain in ROUTINE_DOMAINS:
        return True
    # Subdomain-Check: email.apple.com -> apple.com
    parts = domain.split('.')
    for i in range(1, len(parts)):
        parent = '.'.join(parts[i:])
        if parent in ROUTINE_DOMAINS:
            return True
    return False


def classify_geschaeft(typ, betreff, email, betrag):
    """Reklassifiziert einen Geschäftseintrag.
    Returns: (neuer_typ, wichtigkeit)
      wichtigkeit: 'aktiv' (muss handeln), 'routine' (schon bezahlt/unwichtig), 'info' (zur Kenntnis)
    """
    betreff_lower = (betreff or "").lower()
    domain = get_email_domain(email)

    # Zahlungserinnerung / Mahnung -> immer aktiv
    if any(p in betreff_lower for p in MAHNUNG_BETREFF):
        return "zahlungserinnerung", "aktiv"

    # Echte Eingangsrechnung (Lexware, Mitarbeiter, etc.)
    email_lower = (email or "").lower()
    if any(p in email_lower for p in ECHTE_RECHNUNG_PATTERNS):
        return "eingangsrechnung", "aktiv"
    if any(p in betreff_lower for p in EINGANG_BETREFF):
        # Aber nur wenn NICHT von Routine-Domain
        if not is_routine_domain(domain):
            return "eingangsrechnung", "aktiv"

    # Routine-Zahlungen (PayPal, Anthropic, Ecwid, etc.)
    if is_routine_domain(domain):
        return "routine_zahlung", "routine"

    # Routine-Betreff-Erkennung
    if any(p in betreff_lower for p in ROUTINE_BETREFF):
        return "routine_zahlung", "routine"

    # Kundenrechnung (Betreff enthält "Rechnung" aber kein Betrag -> Kunden-Thread)
    if typ == "rechnung" and (not betrag or betrag == 0):
        return "kundenvorgang", "info"

    # Rest: als Beleg/Info behandeln
    if betrag and betrag > 0:
        return "beleg", "info"

    return "sonstiger_vorgang", "info"


def main():
    print("=== Geschäft-Upgrade ===")

    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row

    # 1. Schema erweitern
    print("\n1. Schema erweitern...")
    try:
        db.execute("ALTER TABLE geschaeft ADD COLUMN wichtigkeit TEXT DEFAULT 'info'")
    except: pass
    try:
        db.execute("ALTER TABLE geschaeft ADD COLUMN bewertung TEXT")
    except: pass
    try:
        db.execute("ALTER TABLE geschaeft ADD COLUMN bewertung_grund TEXT")
    except: pass
    try:
        db.execute("ALTER TABLE geschaeft ADD COLUMN anhaenge_pfad TEXT")
    except: pass
    try:
        db.execute("ALTER TABLE geschaeft ADD COLUMN erinnerung_aktiv INTEGER DEFAULT 0")
    except: pass
    try:
        db.execute("ALTER TABLE geschaeft ADD COLUMN naechste_erinnerung TEXT")
    except: pass
    db.commit()
    print("   Schema erweitert")

    # 2. Anhänge verknüpfen (über mail_ref -> message_id in kunden.db)
    print("\n2. Anhänge aus kunden.db verknüpfen...")
    try:
        kdb = sqlite3.connect(str(KUNDEN_DB))
        kdb.row_factory = sqlite3.Row
        anhang_map = {}
        folder_map = {}
        for r in kdb.execute("SELECT message_id, anhaenge_pfad, mail_folder_pfad FROM interaktionen WHERE message_id IS NOT NULL"):
            mid = r["message_id"]
            if mid:
                if r["anhaenge_pfad"]:
                    anhang_map[mid] = r["anhaenge_pfad"]
                if r["mail_folder_pfad"]:
                    folder_map[mid] = r["mail_folder_pfad"]
        kdb.close()

        linked = 0
        for r in db.execute("SELECT id, mail_ref FROM geschaeft WHERE mail_ref IS NOT NULL AND mail_ref != ''"):
            mid = r["mail_ref"]
            anh = anhang_map.get(mid, "")
            folder = folder_map.get(mid, "")
            # Versuche auch attachments Unterordner im mail_folder_pfad
            if not anh and folder:
                att_path = Path(folder) / "attachments"
                if att_path.exists():
                    anh = str(att_path)
            if anh:
                db.execute("UPDATE geschaeft SET anhaenge_pfad=? WHERE id=?", (anh, r["id"]))
                linked += 1
        db.commit()
        print(f"   {linked} Anhänge verknüpft")
    except Exception as e:
        print(f"   Warnung: {e}")

    # 3. Reklassifizieren
    print("\n3. Reklassifiziere Geschäftsvorgänge...")
    rows = db.execute("SELECT * FROM geschaeft").fetchall()
    stats = {"aktiv": 0, "routine": 0, "info": 0}
    for r in rows:
        neuer_typ, wichtigkeit = classify_geschaeft(
            r["typ"], r["betreff"], r["gegenpartei_email"], r["betrag"]
        )
        db.execute("UPDATE geschaeft SET typ=?, wichtigkeit=? WHERE id=?",
                   (neuer_typ, wichtigkeit, r["id"]))
        stats[wichtigkeit] = stats.get(wichtigkeit, 0) + 1
    db.commit()

    print(f"   Aktiv (Handlungsbedarf): {stats['aktiv']}")
    print(f"   Routine (schon bezahlt): {stats['routine']}")
    print(f"   Info (zur Kenntnis):     {stats['info']}")

    # 4. Übersicht
    print("\n4. Neue Verteilung:")
    for r in db.execute("SELECT typ, wichtigkeit, COUNT(*) c FROM geschaeft GROUP BY typ, wichtigkeit ORDER BY wichtigkeit, c DESC"):
        print(f"   {r['wichtigkeit']:8s} | {r['typ']:22s} | {r['c']}")

    # Aktive Eingangsrechnungen anzeigen
    print("\n5. Aktive Eingangsrechnungen:")
    for r in db.execute("SELECT datum, betrag, gegenpartei_email, betreff FROM geschaeft WHERE wichtigkeit='aktiv' ORDER BY datum DESC"):
        betr = (r['betreff'] or '')[:45].encode('ascii', 'replace').decode()
        print(f"   {(r['datum'] or '')[:10]} | {r['betrag'] or 0:>8.2f} EUR | {(r['gegenpartei_email'] or '')[:30]} | {betr}")

    db.close()
    print("\nFertig.")


if __name__ == "__main__":
    main()
