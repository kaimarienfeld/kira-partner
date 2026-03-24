#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rauMKult(r) Mail-Datenbank Builder v2
Verarbeitet ALLE Postfaecher, erkennt Kundeninteraktionen kanaluebergreifend.

Ausgabe:
  knowledge/mail_index.db        -> Index aller Mails (Metadaten)
  knowledge/kunden.db            -> Kunden-Interaktionen aus ALLEN Postfaechern
  knowledge/sent_mails.db        -> Gesendete Mails (Stil-Lernbasis)
  knowledge/newsletter.db        -> Newsletter, auto-klassifiziert (relevant/irrelevant)
  knowledge/db_status.json       -> Letzter Build-Zeitpunkt
"""

import os, json, sqlite3, re
from pathlib import Path
from datetime import datetime
from html.parser import HTMLParser

ARCHIV_ROOT = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\Archiv")
KNOWLEDGE_DIR = Path(r"C:\Users\kaimr\.claude\projects\C--Users-kaimr-OneDrive---rauMKult-Sichtbeton-00-rauMKult-Auftr-ge-Anfragen\memory\knowledge")
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

MAILBOXEN = [
    "anfrage_raumkult_eu",
    "info_raumkult_eu",
    "invoice_sichtbeton-cire_de",
    "kaimrf_rauMKultSichtbeton_onmicrosoft_com",
    "shop_sichtbeton-cire_de",
]

# Konto-Mapping fuer lesbare Namen
KONTO_LABEL = {
    "anfrage@raumkult.eu":          "anfrage",
    "info@raumkult.eu":             "info",
    "invoice@sichtbeton-cire.de":   "invoice",
    "shop@sichtbeton-cire.de":      "shop",
    "kaimrf@rauMKultSichtbeton.onmicrosoft.com": "intern",
}

# ── Newsletter-Klassifizierung ─────────────────────────────────────────────────
# RELEVANT: bleibt (Branchenbezug zu Betonkosmetik / Handwerk / Business)
NEWSLETTER_RELEVANT_DOMAINS = [
    "reckli", "basf", "sika", "mapei", "mc-bauchemie", "ardex", "sto",
    "caparol", "knauf", "fischer", "hilti", "festool", "flex-tools",
    "bosch-professional", "makita", "metabo",
    "zdb", "handwerk", "baugewerbe", "bauwirtschaft",
    "architekt", "baunetz", "bauwelt", "detail.de", "competitionline",
    "lexware", "sevdesk", "fastbill", "datev", "meinbuero",
    "ihk", "hwk", "zvh",
    "raumkult", "sichtbeton", "betonkosmetik",
]
NEWSLETTER_RELEVANT_KEYWORDS = [
    "beton", "sichtbeton", "estrich", "putz", "spachtel", "beschichtung",
    "schleifen", "polieren", "impraegnierung", "hydrophobierung",
    "werkzeug", "maschine", "schleifpapier", "vlies", "langhalsschleifer",
    "handwerk", "baugewerbe", "architekt", "baustoff",
    "lexware", "buchhaltung", "rechnung", "steuer",
    "branche", "fachbetrieb", "messe", "fachtagung",
]

# NICHT RELEVANT: wird als abmelden markiert
NEWSLETTER_IRRELEVANT_DOMAINS = [
    "specialchem", "hubspotemail", "klaviyo", "mailchimp",
    "avast", "norton", "kaspersky",
    "booking.com", "airbnb", "trivago",
    "amazon", "ebay", "otto", "zalando", "tchibo",
    "paypal.com",  # nur Marketing-Mails, nicht Transaktionen
    "lieferando", "hellofresh",
]
NEWSLETTER_IRRELEVANT_KEYWORDS = [
    "feigenbaum", "faecher", "palme", "pflanze", "garten",
    "mode", "fashion", "kleidung", "schuhe",
    "reise", "urlaub", "hotel", "flug",
    "kurs", "online-course", "weiterbildung",  # allgemeine, nicht Handwerk
    "gewinnspiel", "lotterie",
    "crypto", "bitcoin", "investment",
]


def classify_newsletter(absender: str, betreff: str, text: str) -> str:
    """
    Entscheidet ob ein Newsletter relevant fuer rauMKult(r) ist.
    Gibt zurueck: 'relevant' | 'irrelevant' | 'unklar'
    """
    combined = (absender + " " + betreff + " " + text[:500]).lower()

    # Direkt irrelevant?
    for domain in NEWSLETTER_IRRELEVANT_DOMAINS:
        if domain in combined:
            return "irrelevant"
    for kw in NEWSLETTER_IRRELEVANT_KEYWORDS:
        if kw in combined:
            return "irrelevant"

    # Direkt relevant?
    for domain in NEWSLETTER_RELEVANT_DOMAINS:
        if domain in combined:
            return "relevant"
    for kw in NEWSLETTER_RELEVANT_KEYWORDS:
        if kw in combined:
            return "relevant"

    return "unklar"


def is_newsletter_or_bulk(absender: str, betreff: str, text: str) -> bool:
    """Erkennt Newsletter / Massen-Mails."""
    s = (absender + " " + betreff + " " + text[:800]).lower()
    triggers = [
        "newsletter", "no-reply", "noreply", "donotreply",
        "unsubscribe", "abmelden", "abbestellen",
        "hubspot", "mailchimp", "sendinblue", "klaviyo", "campaign-archive",
        "%-off", "% off", "% rabatt", "sale!", "angebot!", "reminder:",
        "deals", "promo", "marketing@", "info@email.", "news@",
    ]
    return any(t in s for t in triggers)


# ── HTML -> Text ───────────────────────────────────────────────────────────────
class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self._skip = False
    def handle_starttag(self, tag, attrs):
        if tag in ('style','script','head'): self._skip = True
        if tag in ('br','p','div','tr','li'): self.result.append('\n')
    def handle_endtag(self, tag):
        if tag in ('style','script','head'): self._skip = False
    def handle_data(self, data):
        if not self._skip:
            t = data.strip()
            if t: self.result.append(t)
    def get_text(self):
        return re.sub(r'\s+', ' ', ' '.join(self.result)).strip()

def html_to_text(html: str) -> str:
    if not html: return ""
    try:
        p = HTMLTextExtractor(); p.feed(html); return p.get_text()
    except:
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


# ── Kunden-Erkennung ───────────────────────────────────────────────────────────
def is_kunden_mail(absender: str, betreff: str, text: str, mailbox: str, folder: str) -> bool:
    """Entscheidet ob eine eingehende Mail eine echte Kundeninteraktion ist."""
    # Gesendete immer einbeziehen (das IST Kundeninteraktion)
    if "Gesendete" in folder or "Sent" in folder:
        return True

    # Eigene System-Mails / interne ausschliessen
    eigene = ["noreply@raumkult.eu", "system@", "mailer-daemon", "postmaster"]
    absender_low = absender.lower()
    if any(e in absender_low for e in eigene):
        return False

    # Newsletter rausfiltern
    if is_newsletter_or_bulk(absender, betreff, text[:500]):
        return False

    # Bekannte Kunden-Konten sind sowieso kundenrelevant
    kunden_mailboxen = ["anfrage_raumkult_eu", "info_raumkult_eu", "shop_sichtbeton-cire_de"]
    if mailbox in kunden_mailboxen and "INBOX" in folder:
        return True

    # Betreff-Keywords die auf Kundenkontakt hinweisen
    kunden_keywords = [
        "anfrage", "angebot", "auftrag", "projekt", "treppe", "beton",
        "sichtbeton", "fassade", "wand", "boden", "retusche", "kosmetik",
        "bestellung", "rechnung", "zahlung", "lieferung",
        "reparatur", "sanierung", "renovierung",
    ]
    betreff_low = betreff.lower()
    return any(k in betreff_low for k in kunden_keywords)


def classify_mail_typ(betreff: str, text: str, folder: str) -> str:
    """Klassifiziert den Typ einer Mail."""
    b = betreff.lower()
    t = text.lower()

    if "Gesendete" in folder or "Sent" in folder:
        if "angebot" in b or ("angebot" in t and "preis" in t): return "angebot_gesendet"
        if "rechnung" in b: return "rechnung_gesendet"
        if re.match(r"^(re:|aw:|fwd:|fw:)", b): return "antwort_gesendet"
        if "ablehnung" in t[:300] or ("leider" in t[:200] and "nicht" in t[:300]): return "ablehnung"
        return "sonstige_gesendet"

    if "anfrage" in b or "landing" in b: return "eingehende_anfrage"
    if "bestellung" in b or "order" in b: return "shop_bestellung"
    if "rechnung" in b or "invoice" in b: return "rechnung_eingang"
    if "zahlung" in b or "payment" in b or "ueberweisung" in b.replace("ü","ue"): return "zahlung"
    if re.match(r"^(re:|aw:)", b): return "kunden_antwort"
    return "eingehend_sonstige"


def extract_kontakt(absender: str, an: str, folder: str) -> tuple:
    """Extrahiert Email und Name des Kunden (nicht von uns)."""
    # Bei gesendeten Mails ist der Empfaenger der Kunde
    quelle = an if ("Gesendete" in folder or "Sent" in folder) else absender
    email_match = re.search(r'<([^>]+@[^>]+)>', quelle)
    email = email_match.group(1) if email_match else re.sub(r'.*<|>.*', '', quelle).strip()
    name_match = re.match(r'^"?([^"<]+)"?\s*<', quelle)
    name = name_match.group(1).strip() if name_match else ""
    # Eigene Adressen rausfiltern
    eigene = ["raumkult", "sichtbeton-cire", "rauMKultSichtbeton"]
    if any(e in email for e in eigene):
        return None, None
    return email.lower().strip(), name


# ── Datenbank-Setup ────────────────────────────────────────────────────────────
def setup_databases():
    dbs = {}

    # 1. Mail-Index (alle Mails, nur Metadaten)
    c = sqlite3.connect(str(KNOWLEDGE_DIR / "mail_index.db"))
    c.execute("""CREATE TABLE IF NOT EXISTS mails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        konto TEXT, konto_label TEXT, betreff TEXT,
        absender TEXT, an TEXT, datum TEXT, datum_iso TEXT,
        message_id TEXT UNIQUE, folder TEXT,
        hat_anhaenge INTEGER DEFAULT 0, anhaenge TEXT,
        anhaenge_pfad TEXT, mail_folder_pfad TEXT, archiviert_am TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_datum ON mails(datum)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_konto ON mails(konto_label)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_folder ON mails(folder)")
    c.commit(); dbs["index"] = c

    # 2. Kunden-Datenbank (alle Postfaecher, kanaluebergreifend)
    c = sqlite3.connect(str(KNOWLEDGE_DIR / "kunden.db"))
    c.execute("""CREATE TABLE IF NOT EXISTS interaktionen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        konto_label TEXT, betreff TEXT, absender TEXT,
        kunden_email TEXT, kunden_name TEXT,
        datum TEXT, datum_iso TEXT, message_id TEXT UNIQUE,
        folder TEXT, mail_typ TEXT,
        text_plain TEXT, hat_anhaenge INTEGER DEFAULT 0,
        anhaenge_pfad TEXT, mail_folder_pfad TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_email ON interaktionen(kunden_email)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_typ ON interaktionen(mail_typ)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_datum ON interaktionen(datum)")
    c.commit()

    # Kunden-Stammdaten-Tabelle
    c.execute("""CREATE TABLE IF NOT EXISTS kunden (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        name TEXT,
        erstkontakt TEXT,
        letztkontakt TEXT,
        anzahl_mails INTEGER DEFAULT 0,
        hauptkanal TEXT,
        notiz TEXT
    )""")
    c.commit(); dbs["kunden"] = c

    # 3. Gesendete Mails (Stil-Lernbasis)
    c = sqlite3.connect(str(KNOWLEDGE_DIR / "sent_mails.db"))
    c.execute("""CREATE TABLE IF NOT EXISTS gesendete_mails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        konto_label TEXT, betreff TEXT, an TEXT, kunden_email TEXT,
        datum TEXT, datum_iso TEXT, message_id TEXT UNIQUE,
        text_plain TEXT, hat_anhaenge INTEGER DEFAULT 0,
        mail_typ TEXT, mail_folder_pfad TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_typ ON gesendete_mails(mail_typ)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_datum ON gesendete_mails(datum)")
    c.commit(); dbs["sent"] = c

    # 4. Newsletter-Datenbank
    c = sqlite3.connect(str(KNOWLEDGE_DIR / "newsletter.db"))
    c.execute("""CREATE TABLE IF NOT EXISTS newsletter (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        absender_email TEXT UNIQUE,
        absender_name TEXT,
        konto_label TEXT,
        beispiel_betreff TEXT,
        letztes_datum TEXT,
        anzahl INTEGER DEFAULT 1,
        klassifizierung TEXT,
        abgemeldet INTEGER DEFAULT 0,
        abgemeldet_am TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_klass ON newsletter(klassifizierung)")
    c.commit(); dbs["newsletter"] = c

    return dbs


def update_kunden_stamm(c_kunden, email: str, name: str, datum: str, kanal: str):
    """Aktualisiert Kunden-Stammdaten."""
    c_kunden.execute("""
        INSERT INTO kunden (email, name, erstkontakt, letztkontakt, anzahl_mails, hauptkanal)
        VALUES (?, ?, ?, ?, 1, ?)
        ON CONFLICT(email) DO UPDATE SET
            name = COALESCE(NULLIF(excluded.name,''), name),
            letztkontakt = MAX(letztkontakt, excluded.letztkontakt),
            anzahl_mails = anzahl_mails + 1,
            hauptkanal = CASE WHEN excluded.letztkontakt > letztkontakt THEN excluded.hauptkanal ELSE hauptkanal END
    """, (email, name, datum, datum, kanal))


# ── Hauptverarbeitung ──────────────────────────────────────────────────────────
def process_mailbox(mailbox_name: str, dbs: dict) -> dict:
    mailbox_path = ARCHIV_ROOT / mailbox_name
    if not mailbox_path.exists():
        return {"total": 0, "kunden": 0, "sent": 0, "newsletter": 0}

    stats = {"total": 0, "kunden": 0, "sent": 0, "newsletter": 0}
    newsletter_batch = {}  # email -> data

    for folder_dir in mailbox_path.iterdir():
        if not folder_dir.is_dir(): continue
        folder_name = folder_dir.name

        for mail_dir in folder_dir.iterdir():
            if not mail_dir.is_dir(): continue
            mj = mail_dir / "mail.json"
            if not mj.exists(): continue

            try:
                with open(mj, 'r', encoding='utf-8') as f:
                    mail = json.load(f)
            except:
                continue

            konto       = mail.get('konto', '')
            konto_label = next((v for k,v in KONTO_LABEL.items() if k.lower() in konto.lower()), konto)
            betreff     = mail.get('betreff', '') or ''
            absender    = mail.get('absender', '') or ''
            an          = mail.get('an', '') or ''
            datum       = mail.get('datum', '') or ''
            datum_iso   = mail.get('datum_iso', '') or ''
            message_id  = mail.get('message_id', '') or ''
            hat_anh     = 1 if mail.get('hat_anhaenge') else 0
            anhaenge    = json.dumps(mail.get('anhaenge', []), ensure_ascii=False)
            anh_pfad    = mail.get('anhaenge_pfad', '') or ''
            arch_am     = mail.get('archiviert_am', '') or ''
            text_html   = mail.get('text', '') or ''
            text_plain  = html_to_text(text_html)

            stats["total"] += 1

            # 1. Mail-Index (alle)
            dbs["index"].execute("""
                INSERT OR IGNORE INTO mails
                (konto, konto_label, betreff, absender, an, datum, datum_iso,
                 message_id, folder, hat_anhaenge, anhaenge, anhaenge_pfad,
                 mail_folder_pfad, archiviert_am)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (konto, konto_label, betreff, absender, an, datum, datum_iso,
                  message_id, folder_name, hat_anh, anhaenge, anh_pfad,
                  str(mail_dir), arch_am))

            is_sent = "Gesendete" in folder_name or "Sent" in folder_name

            # 2. Newsletter erkennen (nur INBOX)
            if not is_sent and is_newsletter_or_bulk(absender, betreff, text_plain):
                email_match = re.search(r'<([^>@]+@[^>]+)>', absender)
                nl_email = email_match.group(1).lower() if email_match else absender.lower()[:80]
                klass = classify_newsletter(absender, betreff, text_plain)
                if nl_email not in newsletter_batch:
                    newsletter_batch[nl_email] = {
                        "name": absender[:120], "konto": konto_label,
                        "betreff": betreff[:80], "datum": datum,
                        "anzahl": 1, "klass": klass
                    }
                else:
                    newsletter_batch[nl_email]["anzahl"] += 1
                    if datum > newsletter_batch[nl_email]["datum"]:
                        newsletter_batch[nl_email]["datum"] = datum
                        newsletter_batch[nl_email]["betreff"] = betreff[:80]
                stats["newsletter"] += 1
                continue  # Newsletter nicht als Kunden-Interaktion behandeln

            # 3. Kunden-Interaktionen
            if is_kunden_mail(absender, betreff, text_plain, mailbox_name, folder_name):
                mail_typ = classify_mail_typ(betreff, text_plain, folder_name)
                k_email, k_name = extract_kontakt(absender, an, folder_name)

                if k_email:
                    dbs["kunden"].execute("""
                        INSERT OR IGNORE INTO interaktionen
                        (konto_label, betreff, absender, kunden_email, kunden_name,
                         datum, datum_iso, message_id, folder, mail_typ,
                         text_plain, hat_anhaenge, anhaenge_pfad, mail_folder_pfad)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (konto_label, betreff, absender, k_email, k_name,
                          datum, datum_iso, message_id, folder_name, mail_typ,
                          text_plain[:6000], hat_anh, anh_pfad, str(mail_dir)))

                    update_kunden_stamm(dbs["kunden"], k_email, k_name, datum, konto_label)
                    stats["kunden"] += 1

                # 4. Gesendete Mails (Stil-Lernbasis)
                if is_sent:
                    dbs["sent"].execute("""
                        INSERT OR IGNORE INTO gesendete_mails
                        (konto_label, betreff, an, kunden_email, datum, datum_iso,
                         message_id, text_plain, hat_anhaenge, mail_typ, mail_folder_pfad)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """, (konto_label, betreff, an, k_email, datum, datum_iso,
                          message_id, text_plain[:8000], hat_anh, mail_typ, str(mail_dir)))
                    stats["sent"] += 1

    # Newsletter-Batch in DB schreiben
    for nl_email, data in newsletter_batch.items():
        dbs["newsletter"].execute("""
            INSERT INTO newsletter
            (absender_email, absender_name, konto_label, beispiel_betreff,
             letztes_datum, anzahl, klassifizierung)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(absender_email) DO UPDATE SET
                anzahl = anzahl + excluded.anzahl,
                letztes_datum = MAX(letztes_datum, excluded.letztes_datum),
                beispiel_betreff = CASE WHEN excluded.letztes_datum > letztes_datum
                    THEN excluded.beispiel_betreff ELSE beispiel_betreff END
        """, (nl_email, data["name"], data["konto"], data["betreff"],
              data["datum"], data["anzahl"], data["klass"]))

    return stats


def main():
    print("=" * 60)
    print("rauMKult(r) Mail-Datenbank Builder v2")
    print(f"Start: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)

    dbs = setup_databases()

    totals = {"total": 0, "kunden": 0, "sent": 0, "newsletter": 0}
    for mailbox in MAILBOXEN:
        print(f">> {mailbox}")
        stats = process_mailbox(mailbox, dbs)
        for db in dbs.values(): db.commit()
        print(f"   Mails: {stats['total']} | Kunden: {stats['kunden']} | Gesendet: {stats['sent']} | NL: {stats['newsletter']}")
        for k in totals: totals[k] += stats[k]

    for db in dbs.values(): db.close()

    # Status speichern
    status = {
        "erstellt_am": datetime.now().isoformat(),
        "gesamt_mails": totals["total"],
        "kunden_interaktionen": totals["kunden"],
        "gesendete_mails": totals["sent"],
        "newsletter_gefunden": totals["newsletter"],
    }
    with open(KNOWLEDGE_DIR / "db_status.json", 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("FERTIG")
    for k, v in status.items():
        if k != "erstellt_am": print(f"  {k:30s}: {v}")
    print("=" * 60)


if __name__ == "__main__":
    main()
