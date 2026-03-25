#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_rechnungen_detail.py — Extrahiert Rechnungsdaten aus PDFs im Mail-Archiv.
Liest Ausgangsrechnungen und Mahnungen/Erinnerungen, parsed die PDFs und
speichert strukturierte JSON-Daten in rechnungen_detail DB.
"""
import json, sqlite3, re, os
from pathlib import Path
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    print("FEHLER: pdfplumber nicht installiert. pip install pdfplumber")
    exit(1)

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"
DETAIL_DB     = KNOWLEDGE_DIR / "rechnungen_detail.db"

ARCHIV_ROOT = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\Archiv")
INVOICE_SENT = ARCHIV_ROOT / "invoice_sichtbeton-cire_de" / "Gesendete Elemente"
INVOICE_SENT2= ARCHIV_ROOT / "invoice_sichtbeton-cire_de" / "Gesendete Objekte"
SHOP_INBOX   = ARCHIV_ROOT / "shop_sichtbeton-cire_de" / "INBOX"
SHOP_SENT    = ARCHIV_ROOT / "shop_sichtbeton-cire_de" / "Gesendete Elemente"

RE_NUMMER_PAT = re.compile(r'RE-SB\d+', re.IGNORECASE)


def init_detail_db():
    """Erstellt die rechnungen_detail Datenbank."""
    db = sqlite3.connect(str(DETAIL_DB))
    db.execute("""CREATE TABLE IF NOT EXISTS rechnungen_detail (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        re_nummer TEXT UNIQUE,
        typ TEXT DEFAULT 'ausgangsrechnung',
        datum TEXT,
        leistungszeitraum TEXT,
        kunde_nr TEXT,
        kunde_ust_id TEXT,
        kunde_firma TEXT,
        kunde_strasse TEXT,
        kunde_plz TEXT,
        kunde_ort TEXT,
        kunde_land TEXT DEFAULT 'DE',
        kunde_email TEXT,
        projekt_nr TEXT,
        projekt_name TEXT,
        positionen_json TEXT,
        zwischensumme REAL,
        gesamtbetrag REAL,
        mwst_satz REAL,
        mwst_betrag REAL,
        reverse_charge INTEGER DEFAULT 0,
        zahlungsziel_tage INTEGER,
        zahlungsziel_datum TEXT,
        skonto_prozent REAL,
        skonto_betrag REAL,
        skonto_datum TEXT,
        zahlungshinweis TEXT,
        interner_hinweis TEXT,
        pdf_pfad TEXT,
        mail_folder_pfad TEXT,
        mail_message_id TEXT,
        roh_text TEXT,
        erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS mahnungen_detail (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        re_nummer TEXT,
        typ TEXT DEFAULT 'erinnerung',
        stufe INTEGER DEFAULT 1,
        datum TEXT,
        betrag REAL,
        faellig_am TEXT,
        mahngebuehr REAL DEFAULT 0,
        zinsen REAL DEFAULT 0,
        mail_betreff TEXT,
        mail_absender TEXT,
        mail_body TEXT,
        pdf_pfad TEXT,
        mail_folder_pfad TEXT,
        mail_message_id TEXT,
        erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(re_nummer, typ, datum)
    )""")
    db.commit()
    return db


def read_mail_json(mail_dir):
    mj = mail_dir / "mail.json"
    if not mj.exists():
        return None
    try:
        return json.loads(mj.read_text('utf-8'))
    except:
        return None


def extract_email_from_field(field):
    if not field:
        return ""
    m = re.search(r'<([^>]+@[^>]+)>', field)
    return m.group(1).lower() if m else field.strip().lower()


def parse_invoice_pdf(pdf_path):
    """Extrahiert strukturierte Daten aus einer Rechnungs-PDF."""
    result = {
        "re_nummer": "", "datum": "", "leistungszeitraum": "",
        "kunde_nr": "", "kunde_ust_id": "", "kunde_firma": "",
        "kunde_strasse": "", "kunde_plz": "", "kunde_ort": "",
        "projekt_nr": "", "projekt_name": "",
        "positionen": [], "gesamtbetrag": 0, "zwischensumme": 0,
        "reverse_charge": False,
        "zahlungsziel_tage": 0, "zahlungsziel_datum": "",
        "skonto_prozent": 0, "skonto_betrag": 0, "skonto_datum": "",
        "zahlungshinweis": "", "roh_text": ""
    }
    try:
        full_text = ""
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                full_text += text + "\n"
        result["roh_text"] = full_text

        # RE-Nummer
        m = re.search(r'Rechnungsnr\.?:?\s*(RE-SB\d+)', full_text, re.IGNORECASE)
        if m:
            result["re_nummer"] = m.group(1).upper()

        # Datum
        m = re.search(r'Datum:\s*(\d{2}\.\d{2}\.\d{4})', full_text)
        if m:
            try:
                result["datum"] = datetime.strptime(m.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
            except: pass

        # Leistungszeitraum
        m = re.search(r'Leistungszeitraum:\s*(\d{2}\.\d{2}\.\d{4})\s*(?:bis|-)?\s*(\d{2}\.\d{2}\.\d{4})?', full_text)
        if m:
            result["leistungszeitraum"] = m.group(0).strip()

        # Kundennummer
        m = re.search(r'Kundennr\.?:?\s*(\d+)', full_text)
        if m:
            result["kunde_nr"] = m.group(1)

        # Kunden-USt-IdNr
        m = re.search(r'USt-IdNr\.?:?\s*(DE\d+)', full_text)
        if m:
            result["kunde_ust_id"] = m.group(1)

        # Kundenadresse (nach der rauMKult-Absender-Zeile mit Oelsnitz)
        lines = full_text.split('\n')
        addr_start = -1
        for i, line in enumerate(lines):
            # rauMKult + Oelsnitz stehen in EINER Zeile als Absender
            if 'Oelsnitz' in line and ('rauMKult' in line or 'raumkult' in line.lower()):
                addr_start = i + 1
                break
        if addr_start > 0:
            addr_lines = []
            for i in range(addr_start, min(addr_start+5, len(lines))):
                l = lines[i].strip()
                if not l or l.startswith('PNr') or l.startswith('Pos') or 'Rechnung' in l:
                    break
                # Stop at "Für unsere..." or "Sehr geehrte..."
                if l.startswith('F\u00fcr unsere') or l.startswith('Sehr geehrte'):
                    break
                addr_lines.append(l)
            if addr_lines:
                result["kunde_firma"] = addr_lines[0]
                if len(addr_lines) >= 2:
                    result["kunde_strasse"] = addr_lines[1]
                if len(addr_lines) >= 3:
                    plz_match = re.match(r'(\d{4,5})\s+(.+)', addr_lines[2])
                    if plz_match:
                        result["kunde_plz"] = plz_match.group(1)
                        result["kunde_ort"] = plz_match.group(2)
                    else:
                        # Evtl. OT oder Zusatz in Zeile 3
                        result["kunde_ort"] = addr_lines[2]

        # Projekt
        m = re.search(r'PNr\.?\s*([A-Z0-9-]+).*?(?:BV:?\s*(.+?)\.)', full_text, re.DOTALL)
        if m:
            result["projekt_nr"] = m.group(1).strip()
            result["projekt_name"] = m.group(2).strip() if m.group(2) else ""

        # Positionen (Pos. Bezeichnung ANZ ME EZ Rabatt Gesamt)
        pos_pattern = re.compile(r'^(\d+)\s+(.+?)\s+(\d+(?:[.,]\d+)?)\s+\S+\s+([\d.,]+)\s+(?:[\d.,]+\s+)?([\d.,]+)$', re.MULTILINE)
        for pm in pos_pattern.finditer(full_text):
            pos = {
                "pos": int(pm.group(1)),
                "bezeichnung": pm.group(2).strip()[:80],
                "menge": float(pm.group(3).replace(',', '.')),
                "einzelpreis": float(pm.group(4).replace('.', '').replace(',', '.') if '.' in pm.group(4) and ',' in pm.group(4) else pm.group(4).replace(',', '.')),
                "gesamt": float(pm.group(5).replace('.', '').replace(',', '.') if '.' in pm.group(5) and ',' in pm.group(5) else pm.group(5).replace(',', '.'))
            }
            result["positionen"].append(pos)

        # Gesamtbetrag
        m = re.search(r'Gesamtbetrag\*?\s*([\d.,]+)', full_text)
        if m:
            betrag_str = m.group(1).replace('.', '').replace(',', '.')
            try:
                result["gesamtbetrag"] = float(betrag_str)
            except: pass

        # Zwischensumme
        m = re.search(r'Zwischensumme\s*([\d.,]+)', full_text)
        if m:
            try:
                result["zwischensumme"] = float(m.group(1).replace('.', '').replace(',', '.'))
            except: pass

        # Reverse Charge
        if '13b' in full_text or 'Reverse Charge' in full_text:
            result["reverse_charge"] = True

        # Zahlungsziel
        m = re.search(r'Zahlungsziel:\s*(\d+)\s*Tage', full_text)
        if m:
            result["zahlungsziel_tage"] = int(m.group(1))

        # Skonto
        m = re.search(r'(\d+)\s*%\s*Skonto.*?([\d.,]+)\s*[\x80\u20ac€]', full_text)
        if m:
            result["skonto_prozent"] = float(m.group(1))
            try:
                result["skonto_betrag"] = float(m.group(2).replace('.', '').replace(',', '.'))
            except: pass

        # Skonto-Datum
        m = re.search(r'Zahlen Sie bis\s*(\d{2}\.\d{2}\.\d{4})', full_text)
        if m:
            try:
                result["skonto_datum"] = datetime.strptime(m.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
            except: pass

        # Zahlungsziel-Datum
        m = re.search(r'sp.testens\s*(\d{2}\.\d{2}\.\d{4})', full_text)
        if m:
            try:
                result["zahlungsziel_datum"] = datetime.strptime(m.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
            except: pass

        # Zahlungshinweis (alles nach "Zahlungsziel:")
        m = re.search(r'(Zahlungsziel:.*?(?:nachgefordert!|abziehen\.))', full_text, re.DOTALL)
        if m:
            result["zahlungshinweis"] = re.sub(r'\s+', ' ', m.group(1)).strip()

    except Exception as e:
        print(f"  PDF-Fehler: {e}")

    return result


def scan_ausgangsrechnungen(db):
    """Scannt alle Ausgangsrechnungen und extrahiert PDF-Daten."""
    print("\n1. Ausgangsrechnungen aus PDFs extrahieren...")
    folders = [INVOICE_SENT, INVOICE_SENT2]
    count_new, count_skip = 0, 0

    for folder in folders:
        if not folder.exists():
            continue
        for entry in folder.iterdir():
            if not entry.is_dir() or entry.name.startswith('_'):
                continue
            dirname = entry.name.lower()
            if not ('rechnung re-sb' in dirname or 'abschlagsrechnung re-sb' in dirname):
                continue
            # Mahnungen/Erinnerungen ausschließen (die haben eigenes Scanning)
            if 'mahnung' in dirname or 'erinnerung' in dirname:
                continue

            mail = read_mail_json(entry)
            if not mail:
                continue

            betreff = mail.get("betreff", "") or ""
            match = RE_NUMMER_PAT.search(betreff)
            if not match:
                continue
            re_nr = match.group(0).upper()

            # Duplikat-Check
            existing = db.execute("SELECT id FROM rechnungen_detail WHERE re_nummer=?", (re_nr,)).fetchone()
            if existing:
                count_skip += 1
                continue

            # PDF finden
            att_dir = entry / "attachments"
            pdf_path = ""
            if att_dir.exists():
                pdfs = [f for f in att_dir.iterdir() if f.suffix.lower() == '.pdf']
                if pdfs:
                    pdf_path = str(pdfs[0])

            # PDF parsen — suche die richtige Rechnungs-PDF
            data = {}
            if pdf_path:
                data = parse_invoice_pdf(pdf_path)
                # Falls die erste PDF keine Rechnung ist (z.B. Baustoff-Übersicht),
                # probiere weitere PDFs im Ordner
                if not data.get("re_nummer") and att_dir.exists():
                    for alt_pdf in att_dir.iterdir():
                        if alt_pdf.suffix.lower() == '.pdf' and str(alt_pdf) != pdf_path:
                            alt_data = parse_invoice_pdf(str(alt_pdf))
                            if alt_data.get("re_nummer"):
                                data = alt_data
                                pdf_path = str(alt_pdf)
                                break
            if not data.get("re_nummer"):
                data["re_nummer"] = re_nr

            kunde_email = extract_email_from_field(mail.get("an", ""))
            message_id = mail.get("message_id", "")

            try:
                db.execute("""INSERT OR IGNORE INTO rechnungen_detail
                    (re_nummer, typ, datum, leistungszeitraum, kunde_nr, kunde_ust_id,
                     kunde_firma, kunde_strasse, kunde_plz, kunde_ort, kunde_email,
                     projekt_nr, projekt_name, positionen_json, zwischensumme, gesamtbetrag,
                     reverse_charge, zahlungsziel_tage, zahlungsziel_datum,
                     skonto_prozent, skonto_betrag, skonto_datum, zahlungshinweis,
                     pdf_pfad, mail_folder_pfad, mail_message_id, roh_text)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (data.get("re_nummer", re_nr),
                     "abschlagsrechnung" if "abschlags" in betreff.lower() else "ausgangsrechnung",
                     data.get("datum", ""), data.get("leistungszeitraum", ""),
                     data.get("kunde_nr", ""), data.get("kunde_ust_id", ""),
                     data.get("kunde_firma", ""), data.get("kunde_strasse", ""),
                     data.get("kunde_plz", ""), data.get("kunde_ort", ""),
                     kunde_email,
                     data.get("projekt_nr", ""), data.get("projekt_name", ""),
                     json.dumps(data.get("positionen", []), ensure_ascii=False),
                     data.get("zwischensumme", 0), data.get("gesamtbetrag", 0),
                     1 if data.get("reverse_charge") else 0,
                     data.get("zahlungsziel_tage", 0), data.get("zahlungsziel_datum", ""),
                     data.get("skonto_prozent", 0), data.get("skonto_betrag", 0),
                     data.get("skonto_datum", ""), data.get("zahlungshinweis", ""),
                     pdf_path, str(entry), message_id,
                     data.get("roh_text", "")[:5000]))
                count_new += 1
                betrag = data.get("gesamtbetrag", 0)
                print(f"  + {re_nr}: {data.get('kunde_firma','')[:30]} | {betrag:,.2f} EUR".encode('ascii','replace').decode())
            except Exception as e:
                print(f"  ! {re_nr}: Fehler - {e}")

    db.commit()
    print(f"   {count_new} neue Rechnungen extrahiert, {count_skip} bereits vorhanden")

    # Update ausgangsrechnungen in tasks.db mit Beträgen + Kundennamen
    try:
        tdb = sqlite3.connect(str(TASKS_DB))
        for r in db.execute("SELECT re_nummer, gesamtbetrag, kunde_firma FROM rechnungen_detail WHERE gesamtbetrag > 0"):
            tdb.execute("UPDATE ausgangsrechnungen SET betrag_brutto=? WHERE re_nummer=? AND (betrag_brutto IS NULL OR betrag_brutto=0)",
                        (r[1], r[0]))
            if r[2]:
                tdb.execute("UPDATE ausgangsrechnungen SET kunde_name=? WHERE re_nummer=? AND (kunde_name IS NULL OR kunde_name='')",
                            (r[2], r[0]))
        tdb.commit()
        tdb.close()
        print("   Beträge + Kundennamen in tasks.db aktualisiert")
    except Exception as e:
        print(f"   Warnung tasks.db: {e}")

    return count_new


def scan_mahnungen_erinnerungen(db):
    """Scannt shop@sichtbeton-cire.de für Mahnungen/Erinnerungen."""
    print("\n2. Mahnungen/Erinnerungen scannen...")
    search_folders = [SHOP_INBOX, SHOP_SENT]
    if INVOICE_SENT.exists():
        search_folders.append(INVOICE_SENT)
    if INVOICE_SENT2 and INVOICE_SENT2.exists():
        search_folders.append(INVOICE_SENT2)

    count_new = 0
    for folder in search_folders:
        if not folder.exists():
            continue
        for entry in folder.iterdir():
            if not entry.is_dir() or entry.name.startswith('_'):
                continue
            dirname = entry.name.lower()
            is_mahnung = 'mahnung' in dirname and 're-sb' in dirname
            is_erinnerung = 'erinnerung' in dirname and 're-sb' in dirname
            if not (is_mahnung or is_erinnerung):
                continue

            mail = read_mail_json(entry)
            if not mail:
                continue

            betreff = mail.get("betreff", "") or ""
            match = RE_NUMMER_PAT.search(betreff)
            if not match:
                continue
            re_nr = match.group(0).upper()
            # Validierung: RE-Nummern haben 4-6 Ziffern (z.B. RE-SB2567, RE-SB260104)
            # Tippfehler wie RE-SB2600101 (extra 0) korrigieren durch Abgleich mit rechnungen_detail
            re_digits = re.search(r'RE-SB(\d+)', re_nr).group(1)
            if len(re_digits) > 6:
                # Versuche Korrektur: entferne je eine Ziffer und prüfe gegen bekannte Nummern
                existing = {r[0] for r in db.execute("SELECT re_nummer FROM rechnungen_detail").fetchall() if r[0]}
                corrected = False
                for i in range(len(re_digits)):
                    candidate = "RE-SB" + re_digits[:i] + re_digits[i+1:]
                    if candidate in existing:
                        re_nr = candidate
                        corrected = True
                        break
                if not corrected:
                    # Zweites Fallback: direkt auf 6 Ziffern kürzen
                    for length in (6, 5, 4):
                        candidate = "RE-SB" + re_digits[:length]
                        if candidate in existing:
                            re_nr = candidate
                            break
            datum = (mail.get("datum", "") or "")[:10]
            typ = "mahnung" if is_mahnung else "erinnerung"

            # Stufe erkennen
            stufe = 1
            if '2. mahnung' in betreff.lower() or 'zweite' in betreff.lower():
                stufe = 2
            elif '3. mahnung' in betreff.lower() or 'letzte' in betreff.lower():
                stufe = 3
            elif 'mahnung' in betreff.lower() and 'erinnerung' not in betreff.lower():
                stufe = 2  # Mahnung > Erinnerung

            # Body extrahieren (HTML -> Text)
            body = mail.get("text", "") or ""
            # Simple HTML strip
            body_clean = re.sub(r'<[^>]+>', ' ', body)
            body_clean = re.sub(r'\s+', ' ', body_clean).strip()

            # Prüfe ob es von rauMKult ist
            absender = mail.get("absender", "") or ""
            is_from_raumkult = any(d in absender.lower() for d in ['sichtbeton-cire', 'raumkult'])
            if not is_from_raumkult:
                # Prüfe Body
                is_from_raumkult = 'raumkult' in body_clean.lower() or 'sichtbeton' in body_clean.lower()
            if not is_from_raumkult:
                continue

            # PDF in attachments
            pdf_pfad = ""
            att_dir = entry / "attachments"
            if att_dir.exists():
                pdfs = [f for f in att_dir.iterdir() if f.suffix.lower() == '.pdf']
                if pdfs:
                    pdf_pfad = str(pdfs[0])

            # Betrag aus Body extrahieren — verschiedene Formate
            betrag = 0
            # "Zahlbetrag in Höhe von 7.510,60 €"
            m = re.search(r'(?:Zahlbetrag|Betrag|Gesamtbetrag|Rechnungsbetrag)\s*(?:in\s*H.he\s*von\s*)?([\d.,]+)\s*(?:\x80|\u20ac|EUR|€)', body_clean)
            if m:
                try:
                    betrag = float(m.group(1).replace('.', '').replace(',', '.'))
                except: pass
            # Auch aus PDF versuchen wenn vorhanden
            if betrag == 0 and pdf_pfad:
                try:
                    with pdfplumber.open(pdf_pfad) as pdf:
                        for page in pdf.pages:
                            pt = page.extract_text() or ""
                            m2 = re.search(r'(?:Zahlbetrag|Gesamtbetrag|Rechnungsbetrag)\s*(?:in\s*H.he\s*von\s*)?([\d.,]+)\s*(?:\x80|\u20ac|EUR|€)', pt)
                            if m2:
                                betrag = float(m2.group(1).replace('.', '').replace(',', '.'))
                                break
                except: pass

            # Fällig-Datum
            faellig = ""
            m = re.search(r'(?:f.llig|Zahlungsziel|bis zum)\s*(?:am\s*)?(\d{2}\.\d{2}\.\d{4})', body_clean)
            if m:
                try:
                    faellig = datetime.strptime(m.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
                except: pass

            # Duplikat-Check
            existing = db.execute("SELECT id FROM mahnungen_detail WHERE re_nummer=? AND typ=? AND datum=?",
                                  (re_nr, typ, datum)).fetchone()
            if existing:
                continue

            try:
                db.execute("""INSERT INTO mahnungen_detail
                    (re_nummer, typ, stufe, datum, betrag, faellig_am,
                     mail_betreff, mail_absender, mail_body, pdf_pfad,
                     mail_folder_pfad, mail_message_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (re_nr, typ, stufe, datum, betrag, faellig,
                     betreff[:200], absender[:200], body_clean[:4000],
                     pdf_pfad, str(entry), mail.get("message_id", "")))
                count_new += 1
                print(f"  + {typ} {re_nr} ({datum}): Stufe {stufe}".encode('ascii', 'replace').decode())
            except Exception as e:
                print(f"  ! {re_nr}: {e}")

    db.commit()
    print(f"   {count_new} neue Mahnungen/Erinnerungen")
    return count_new


def print_summary(db):
    print("\n" + "="*50)
    print("ZUSAMMENFASSUNG")
    print("="*50)

    # Rechnungen
    for r in db.execute("SELECT typ, COUNT(*), COALESCE(SUM(gesamtbetrag),0) FROM rechnungen_detail GROUP BY typ"):
        print(f"  {r[0]}: {r[1]} ({r[2]:,.2f} EUR)")

    # Mahnungen
    for r in db.execute("SELECT typ, stufe, COUNT(*) FROM mahnungen_detail GROUP BY typ, stufe ORDER BY typ, stufe"):
        print(f"  {r[0]} Stufe {r[1]}: {r[2]}")

    # Top-Kunden
    print("\n  Top-Kunden nach Umsatz:")
    for r in db.execute("SELECT kunde_firma, COUNT(*), SUM(gesamtbetrag) FROM rechnungen_detail WHERE gesamtbetrag>0 GROUP BY kunde_firma ORDER BY SUM(gesamtbetrag) DESC LIMIT 5"):
        name = (r[0] or 'Unbekannt')[:30]
        print(f"    {name}: {r[1]} Rechnungen, {r[2]:,.2f} EUR".encode('ascii','replace').decode())


def main():
    print("=== Rechnungen-Detail-Scanner v1 ===")
    db = init_detail_db()
    scan_ausgangsrechnungen(db)
    scan_mahnungen_erinnerungen(db)
    print_summary(db)
    db.close()
    print("\nFertig.")


if __name__ == "__main__":
    main()
