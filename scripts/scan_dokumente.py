#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_dokumente.py — Ordner-basierter Dokumenten-Scanner für rauMKult®.
Scannt Rechnungen, Angebote, Mahnungen, Zahlungserinnerungen und Zahlungseingänge
aus dedizierten OneDrive-Ordnern (NICHT aus dem Mail-Archiv).

Hybrid-Extraktion: Regex für strukturierte Felder, LLM für Lücken.
Dedup: Sync-Tool erzeugt _1, _2 Suffixe — höchste Nummer gewinnt.
"""
import json, sqlite3, re, os, hashlib, sys
from pathlib import Path
from datetime import datetime, date
from html.parser import HTMLParser

# Windows Console UTF-8
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except: pass

try:
    import pdfplumber
except ImportError:
    print("FEHLER: pdfplumber nicht installiert. pip install pdfplumber")
    exit(1)

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"
DETAIL_DB     = KNOWLEDGE_DIR / "rechnungen_detail.db"

DOCS_ROOT     = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\00_rauMKult\Rechnungen-Zahlungen")
RECHNUNGEN_DIR   = DOCS_ROOT / "Rechnungen Leistung"
ZAHLUNGEN_DIR    = DOCS_ROOT / "Zahlung eingegangen Leistung"
MAHNUNGEN_DIR    = DOCS_ROOT / "Mahnungen Leistung"
ERINNERUNGEN_DIR = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\00_rauMKult\Zahlungserinnerungen Leistung")
ANGEBOTE_DIR     = DOCS_ROOT / "Angebote Leistung"

RE_PAT = re.compile(r'RE-SB\d+', re.IGNORECASE)
A_PAT  = re.compile(r'A-SB\d+', re.IGNORECASE)


def normalize_re_nr(re_nr):
    """Normalisiert RE-Nummern: RE-SB2600101 → RE-SB260101 (6 Ziffern Standard).
    rauMKult RE-Nummern haben Format RE-SBYYxxxx (2-stellig Jahr + 4-stellig lfd).
    Wenn 7+ Ziffern und führende 0 nach dem Jahr → entfernen.
    """
    m = re.match(r'(RE-SB)(\d+)', re_nr, re.IGNORECASE)
    if not m:
        return re_nr
    prefix = m.group(1).upper()
    digits = m.group(2)
    # Standard: 6 Ziffern (YYxxxx). Wenn 7 Ziffern: wahrscheinlich YY0xxxx → YYxxxx
    if len(digits) == 7:
        # Prüfe ob Ziffer 3 eine 0 ist (z.B. 2600101 → 260101)
        if digits[2] == '0':
            digits = digits[:2] + digits[3:]
    return prefix + digits


# ── HTML-Stripper ────────────────────────────────────────────────────────────
class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []
    def handle_data(self, d):
        self._parts.append(d)
    def get_text(self):
        return ' '.join(self._parts)

def strip_html(html):
    s = _HTMLStripper()
    s.feed(html or "")
    return s.get_text()


# ── Dedup ────────────────────────────────────────────────────────────────────
def dedup_files(directory, suffix=".pdf"):
    """Gruppiert Dateien nach Basis-Name, höchste _N Zahl gewinnt.
    Returns: {basis_name: winning_path}
    """
    if not directory.exists():
        return {}

    files = [f for f in directory.iterdir() if f.is_file() and f.suffix.lower() == suffix]
    groups = {}  # basis -> [(nummer, path)]

    for f in files:
        stem = f.stem  # ohne .pdf
        # Pattern: basename oder basename_N
        m = re.match(r'^(.+?)(?:_(\d+))?$', stem)
        if m:
            basis = m.group(1)
            nummer = int(m.group(2)) if m.group(2) else 0
            groups.setdefault(basis, []).append((nummer, f))

    result = {}
    for basis, variants in groups.items():
        # Höchste Nummer gewinnt
        variants.sort(key=lambda x: x[0], reverse=True)
        result[basis] = variants[0][1]

    return result


def file_hash(path):
    """SHA256 der Datei für Änderungserkennung."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


# ── PDF-Extraktion ───────────────────────────────────────────────────────────
def extract_pdf_text(pdf_path):
    """Extrahiert Volltext aus PDF."""
    try:
        text = ""
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
        return text
    except Exception as e:
        print(f"  PDF-Fehler {pdf_path.name}: {e}")
        return ""


def parse_betrag(s):
    """Parst deutsche Betragsformate: '3.573,73' → 3573.73"""
    if not s:
        return 0.0
    s = s.strip().replace(' ', '')
    # Format: 1.234,56 oder 1234,56 oder 1234.56
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except:
        return 0.0


def parse_invoice_regex(text):
    """Regex-basierte Extraktion aus Rechnungs-PDF. Übernommen aus scan_rechnungen_detail.py."""
    result = {
        "re_nummer": "", "datum": "", "leistungszeitraum": "",
        "kunde_nr": "", "kunde_ust_id": "", "kunde_firma": "",
        "kunde_strasse": "", "kunde_plz": "", "kunde_ort": "",
        "projekt_nr": "", "projekt_name": "",
        "positionen": [], "gesamtbetrag": 0, "zwischensumme": 0,
        "mwst_satz": 0, "mwst_betrag": 0,
        "reverse_charge": False,
        "zahlungsziel_tage": 0, "zahlungsziel_datum": "",
        "skonto_prozent": 0, "skonto_betrag": 0, "skonto_datum": "",
        "zahlungshinweis": "", "roh_text": text
    }

    # RE-Nummer
    m = re.search(r'Rechnungsnr\.?:?\s*(RE-SB\d+)', text, re.IGNORECASE)
    if m:
        result["re_nummer"] = m.group(1).upper()

    # Datum
    m = re.search(r'Datum:\s*(\d{2}\.\d{2}\.\d{4})', text)
    if m:
        try:
            result["datum"] = datetime.strptime(m.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
        except: pass

    # Leistungszeitraum
    m = re.search(r'Leistungszeitraum:\s*(\d{2}\.\d{2}\.\d{4})\s*(?:bis|-)?\s*(\d{2}\.\d{2}\.\d{4})?', text)
    if m:
        result["leistungszeitraum"] = m.group(0).strip()

    # Kundennummer
    m = re.search(r'Kundennr\.?:?\s*(\d+)', text)
    if m:
        result["kunde_nr"] = m.group(1)

    # USt-IdNr
    m = re.search(r'USt-IdNr\.?:?\s*(DE\d+)', text)
    if m:
        result["kunde_ust_id"] = m.group(1)

    # Kundenadresse (nach rauMKult + Oelsnitz Zeile)
    lines = text.split('\n')
    addr_start = -1
    for i, line in enumerate(lines):
        if 'Oelsnitz' in line and ('rauMKult' in line or 'raumkult' in line.lower()):
            addr_start = i + 1
            break
    if addr_start > 0:
        addr_lines = []
        for i in range(addr_start, min(addr_start + 5, len(lines))):
            l = lines[i].strip()
            if not l or l.startswith('PNr') or l.startswith('Pos') or 'Rechnung' in l:
                break
            if l.startswith('Für unsere') or l.startswith('Sehr geehrte'):
                break
            addr_lines.append(l)
        if addr_lines:
            result["kunde_firma"] = addr_lines[0]
            if len(addr_lines) >= 2:
                result["kunde_strasse"] = addr_lines[1]
            if len(addr_lines) >= 3:
                plz_m = re.match(r'(\d{4,5})\s+(.+)', addr_lines[2])
                if plz_m:
                    result["kunde_plz"] = plz_m.group(1)
                    result["kunde_ort"] = plz_m.group(2)
                else:
                    result["kunde_ort"] = addr_lines[2]

    # Projekt
    m = re.search(r'PNr\.?\s*([A-Z0-9-]+).*?(?:BV:?\s*(.+?)\.)', text, re.DOTALL)
    if m:
        result["projekt_nr"] = m.group(1).strip()
        result["projekt_name"] = m.group(2).strip() if m.group(2) else ""

    # Positionen
    pos_pattern = re.compile(
        r'^(\d+)\s+(.+?)\s+(\d+(?:[.,]\d+)?)\s+\S+\s+([\d.,]+)\s+(?:[\d.,]+\s+)?([\d.,]+)$',
        re.MULTILINE
    )
    for pm in pos_pattern.finditer(text):
        bez = pm.group(2).strip()[:120]
        # IBAN-Zeilen, Bankdaten etc. filtern
        if any(skip in bez for skip in ['IBAN', 'BIC', 'Sparkasse', 'Volksbank', 'Commerzbank',
                                         'Deutsche Bank', 'Oelsnitz IBAN', 'DE13', 'DE36', 'DE74']):
            continue
        pos = {
            "pos": int(pm.group(1)),
            "bezeichnung": bez,
            "menge": parse_betrag(pm.group(3)),
            "einzelpreis": parse_betrag(pm.group(4)),
            "gesamt": parse_betrag(pm.group(5))
        }
        result["positionen"].append(pos)

    # Gesamtbetrag
    m = re.search(r'Gesamtbetrag\*?\s*([\d.,]+)', text)
    if m:
        result["gesamtbetrag"] = parse_betrag(m.group(1))

    # Zwischensumme
    m = re.search(r'Zwischensumme\s*([\d.,]+)', text)
    if m:
        result["zwischensumme"] = parse_betrag(m.group(1))

    # MwSt
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*%\s*(?:MwSt|Mehrwertsteuer|Umsatzsteuer)\s*([\d.,]+)', text)
    if m:
        result["mwst_satz"] = parse_betrag(m.group(1))
        result["mwst_betrag"] = parse_betrag(m.group(2))

    # Reverse Charge
    if '13b' in text or 'Reverse Charge' in text:
        result["reverse_charge"] = True

    # Zahlungsziel
    m = re.search(r'Zahlungsziel:\s*(\d+)\s*Tage', text)
    if m:
        result["zahlungsziel_tage"] = int(m.group(1))

    # Skonto
    m = re.search(r'(\d+)\s*%\s*Skonto.*?([\d.,]+)\s*[\x80\u20ac€]', text)
    if m:
        result["skonto_prozent"] = float(m.group(1))
        result["skonto_betrag"] = parse_betrag(m.group(2))

    # Skonto-Datum
    m = re.search(r'Zahlen Sie bis\s*(\d{2}\.\d{2}\.\d{4})', text)
    if m:
        try:
            result["skonto_datum"] = datetime.strptime(m.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
        except: pass

    # Zahlungsziel-Datum
    m = re.search(r'sp.testens\s*(\d{2}\.\d{2}\.\d{4})', text)
    if m:
        try:
            result["zahlungsziel_datum"] = datetime.strptime(m.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
        except: pass

    # Zahlungshinweis
    m = re.search(r'(Zahlungsziel:.*?(?:nachgefordert!|abziehen\.))', text, re.DOTALL)
    if m:
        result["zahlungshinweis"] = re.sub(r'\s+', ' ', m.group(1)).strip()

    return result


# ── DB Initialisierung ───────────────────────────────────────────────────────
def init_detail_db():
    """Erstellt/aktualisiert rechnungen_detail.db mit allen Tabellen."""
    db = sqlite3.connect(str(DETAIL_DB))
    db.row_factory = sqlite3.Row

    db.executescript("""
        CREATE TABLE IF NOT EXISTS rechnungen_detail (
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
            pdf_hash TEXT,
            quelle TEXT DEFAULT 'ordner',
            llm_extrahiert INTEGER DEFAULT 0,
            roh_text TEXT,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS mahnungen_detail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            re_nummer TEXT,
            typ TEXT DEFAULT 'erinnerung',
            stufe INTEGER DEFAULT 1,
            datum TEXT,
            betrag REAL,
            faellig_am TEXT,
            mahngebuehr REAL DEFAULT 0,
            zinsen REAL DEFAULT 0,
            pdf_pfad TEXT,
            pdf_hash TEXT,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(re_nummer, typ, datum)
        );

        CREATE TABLE IF NOT EXISTS rechnungs_positionen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            re_nummer TEXT NOT NULL,
            pos_nr INTEGER,
            bezeichnung TEXT,
            bezeichnung_normiert TEXT,
            menge REAL,
            einheit TEXT,
            einzelpreis REAL,
            gesamtpreis REAL,
            kategorie TEXT,
            datum TEXT,
            kunde_firma TEXT,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS zahlungseingaenge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            re_nummer TEXT,
            datum TEXT,
            betrag REAL,
            kunde TEXT,
            projekt TEXT,
            match_status TEXT DEFAULT 'unmatched',
            match_rechnung_id INTEGER,
            betrag_differenz REAL DEFAULT 0,
            quelle_pfad TEXT,
            message_id TEXT UNIQUE,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS angebote_detail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            a_nummer TEXT UNIQUE,
            datum TEXT,
            kunde_firma TEXT,
            kunde_strasse TEXT,
            kunde_plz TEXT,
            kunde_ort TEXT,
            projekt_name TEXT,
            positionen_json TEXT,
            gesamtbetrag REAL,
            mwst_betrag REAL,
            gueltig_bis TEXT,
            pdf_pfad TEXT,
            pdf_hash TEXT,
            llm_extrahiert INTEGER DEFAULT 0,
            roh_text TEXT,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Neue Spalten nachrüsten (falls alte DB existiert)
    for col, typ in [("pdf_hash", "TEXT"), ("quelle", "TEXT DEFAULT 'ordner'"),
                     ("llm_extrahiert", "INTEGER DEFAULT 0"),
                     ("mwst_satz", "REAL"), ("mwst_betrag", "REAL")]:
        try:
            db.execute(f"ALTER TABLE rechnungen_detail ADD COLUMN {col} {typ}")
        except: pass
    for col, typ in [("pdf_hash", "TEXT")]:
        try:
            db.execute(f"ALTER TABLE mahnungen_detail ADD COLUMN {col} {typ}")
        except: pass

    db.commit()
    return db


def init_tasks_db_tables():
    """Stellt sicher, dass ausgangsrechnungen + angebote Tabellen existieren."""
    db = sqlite3.connect(str(TASKS_DB))
    db.executescript("""
        CREATE TABLE IF NOT EXISTS ausgangsrechnungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            re_nummer TEXT UNIQUE,
            datum TEXT,
            kunde_email TEXT,
            kunde_name TEXT,
            betrag_netto REAL,
            betrag_brutto REAL,
            betreff TEXT,
            mail_ref TEXT,
            anhaenge_pfad TEXT,
            status TEXT DEFAULT 'offen',
            bezahlt_am TEXT,
            mahnung_count INTEGER DEFAULT 0,
            letzte_mahnung TEXT,
            notiz TEXT,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ar_status ON ausgangsrechnungen(status);

        CREATE TABLE IF NOT EXISTS angebote (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            a_nummer TEXT UNIQUE,
            datum TEXT,
            kunde_email TEXT,
            kunde_name TEXT,
            betrag_geschaetzt REAL,
            betreff TEXT,
            mail_ref TEXT,
            anhaenge_pfad TEXT,
            status TEXT DEFAULT 'offen',
            nachfass_count INTEGER DEFAULT 0,
            letzter_nachfass TEXT,
            naechster_nachfass TEXT,
            notiz TEXT,
            grund_abgelehnt TEXT,
            grund_angenommen TEXT,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ang_status ON angebote(status);

        CREATE TABLE IF NOT EXISTS geschaeft_statistik (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            typ TEXT,
            referenz_id INTEGER,
            ereignis TEXT,
            daten_json TEXT,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.commit()
    db.close()


# ── Scanner: Rechnungen ─────────────────────────────────────────────────────
def scan_rechnungen(detail_db):
    """Scannt alle Rechnungs-PDFs aus dem Ordner."""
    print("\n═══ RECHNUNGEN SCANNEN ═══")
    winners = dedup_files(RECHNUNGEN_DIR, ".pdf")
    print(f"  {len(winners)} unique Rechnungen aus {sum(1 for f in RECHNUNGEN_DIR.iterdir() if f.suffix.lower()=='.pdf')} Dateien")

    count_new, count_skip, count_update = 0, 0, 0

    for basis, pdf_path in sorted(winners.items()):
        # RE-Nummer aus Dateiname
        m = RE_PAT.search(basis)
        if not m:
            continue
        re_nr = normalize_re_nr(m.group(0))

        # Datum aus Dateiname
        dm = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', basis)
        datum_file = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" if dm else ""

        # Hash prüfen — überspringen wenn unverändert
        h = file_hash(pdf_path)
        existing = detail_db.execute("SELECT id, pdf_hash FROM rechnungen_detail WHERE re_nummer=?", (re_nr,)).fetchone()
        if existing and existing['pdf_hash'] == h:
            count_skip += 1
            continue

        # PDF parsen
        text = extract_pdf_text(pdf_path)
        if not text.strip():
            print(f"  WARNUNG: Kein Text in {pdf_path.name}")
            continue

        data = parse_invoice_regex(text)
        if not data["re_nummer"]:
            data["re_nummer"] = re_nr
        if not data["datum"]:
            data["datum"] = datum_file

        # Typ erkennen
        typ = "ausgangsrechnung"
        if "abschlags" in basis.lower():
            typ = "abschlagsrechnung"

        # Upsert in rechnungen_detail
        detail_db.execute("""INSERT OR REPLACE INTO rechnungen_detail
            (re_nummer, typ, datum, leistungszeitraum, kunde_nr, kunde_ust_id,
             kunde_firma, kunde_strasse, kunde_plz, kunde_ort,
             projekt_nr, projekt_name, positionen_json, zwischensumme, gesamtbetrag,
             mwst_satz, mwst_betrag, reverse_charge,
             zahlungsziel_tage, zahlungsziel_datum,
             skonto_prozent, skonto_betrag, skonto_datum, zahlungshinweis,
             pdf_pfad, pdf_hash, quelle, roh_text)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data["re_nummer"], typ, data["datum"], data["leistungszeitraum"],
             data["kunde_nr"], data["kunde_ust_id"],
             data["kunde_firma"], data["kunde_strasse"], data["kunde_plz"], data["kunde_ort"],
             data["projekt_nr"], data["projekt_name"],
             json.dumps(data["positionen"], ensure_ascii=False),
             data["zwischensumme"], data["gesamtbetrag"],
             data["mwst_satz"], data["mwst_betrag"],
             1 if data["reverse_charge"] else 0,
             data["zahlungsziel_tage"], data["zahlungsziel_datum"],
             data["skonto_prozent"], data["skonto_betrag"], data["skonto_datum"],
             data["zahlungshinweis"],
             str(pdf_path), h, "ordner", text))

        # Positionen in Positions-DB
        detail_db.execute("DELETE FROM rechnungs_positionen WHERE re_nummer=?", (data["re_nummer"],))
        for pos in data["positionen"]:
            detail_db.execute("""INSERT INTO rechnungs_positionen
                (re_nummer, pos_nr, bezeichnung, menge, einzelpreis, gesamtpreis,
                 datum, kunde_firma)
                VALUES (?,?,?,?,?,?,?,?)""",
                (data["re_nummer"], pos.get("pos", 0), pos.get("bezeichnung", ""),
                 pos.get("menge", 0), pos.get("einzelpreis", 0), pos.get("gesamt", 0),
                 data["datum"], data["kunde_firma"]))

        if existing:
            count_update += 1
        else:
            count_new += 1

        print(f"  {'UPDATE' if existing else 'NEU'}: {re_nr} | {data['datum']} | {data['kunde_firma'][:30]} | {data['gesamtbetrag']:.2f} EUR | {len(data['positionen'])} Pos.")

    detail_db.commit()
    print(f"  → {count_new} neu, {count_update} aktualisiert, {count_skip} unverändert")
    return count_new + count_update


# ── Scanner: Mahnungen + Zahlungserinnerungen ────────────────────────────────
def scan_mahnungen(detail_db):
    """Scannt Mahnungen und Zahlungserinnerungen."""
    print("\n═══ MAHNUNGEN & ZAHLUNGSERINNERUNGEN SCANNEN ═══")
    count = 0

    for label, directory in [("Mahnungen", MAHNUNGEN_DIR), ("Zahlungserinnerungen", ERINNERUNGEN_DIR)]:
        winners = dedup_files(directory, ".pdf")
        print(f"  {label}: {len(winners)} unique Dateien")

        for basis, pdf_path in sorted(winners.items()):
            # RE-Nummer aus Dateiname
            m = RE_PAT.search(basis)
            if not m:
                continue
            re_nr = normalize_re_nr(m.group(0))

            # Datum aus Dateiname
            dm = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', basis)
            datum = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" if dm else ""

            # Typ + Stufe
            name_lower = basis.lower()
            if 'mahnung' in name_lower:
                typ = 'mahnung'
                stufe = 2
                if '2' in name_lower or 'zweite' in name_lower:
                    stufe = 3
            else:
                typ = 'erinnerung'
                stufe = 1

            h = file_hash(pdf_path)

            # Betrag aus PDF versuchen
            text = extract_pdf_text(pdf_path)
            betrag = 0
            bm = re.search(r'(?:Gesamtbetrag|Betrag|Forderung)\s*:?\s*([\d.,]+)\s*(?:EUR|€)', text)
            if bm:
                betrag = parse_betrag(bm.group(1))

            try:
                detail_db.execute("""INSERT OR REPLACE INTO mahnungen_detail
                    (re_nummer, typ, stufe, datum, betrag, pdf_pfad, pdf_hash)
                    VALUES (?,?,?,?,?,?,?)""",
                    (re_nr, typ, stufe, datum, betrag, str(pdf_path), h))
                count += 1
                print(f"  {typ.upper()} Stufe {stufe}: {re_nr} | {datum} | {betrag:.2f} EUR")
            except sqlite3.IntegrityError:
                pass  # Duplikat

    detail_db.commit()
    print(f"  → {count} Mahnungen/Erinnerungen verarbeitet")
    return count


# ── Scanner: Angebote ────────────────────────────────────────────────────────
def scan_angebote(detail_db):
    """Scannt alle Angebots-PDFs. Filtert AGB, Preislisten, Begleitschreiben etc."""
    print("\n═══ ANGEBOTE SCANNEN ═══")
    winners = dedup_files(ANGEBOTE_DIR, ".pdf")

    # Nur echte Angebote (mit A-SB Nummer im Namen oder Angebot_ Prefix)
    SKIP_PATTERNS = [
        'allgemeine geschäftsbedingungen', 'agb', 'preisliste', 'preise ',
        'broschüre', 'informations-', 'treppen mikrozement',
        'ablaufplan', 'zusatz_z_angebot', 'begleitschreiben',
        '①', '1025_001',  # Legacy-Dateien ohne A-SB
    ]

    count = 0
    for basis, pdf_path in sorted(winners.items()):
        name_lower = basis.lower()

        # Skip Beilagen/Dokumente
        if any(p in name_lower for p in SKIP_PATTERNS):
            continue

        # A-SB Nummer?
        m = A_PAT.search(basis)
        if not m:
            # Akzeptiere auch 250731-AB-rauMKult Muster
            if not re.match(r'\d{6}-AB-', basis):
                continue

        a_nr = m.group(0).upper() if m else basis.split('.')[0]

        # Datum aus Dateiname
        dm = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', basis)
        datum = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" if dm else ""

        # Freigabe-Variante?
        is_freigabe = '-freigabe' in name_lower

        h = file_hash(pdf_path)
        existing = detail_db.execute("SELECT id, pdf_hash FROM angebote_detail WHERE a_nummer=?", (a_nr,)).fetchone()
        if existing and existing['pdf_hash'] == h:
            continue

        # PDF parsen (vereinfacht — Angebote haben anderes Layout)
        text = extract_pdf_text(pdf_path)
        kunde_firma = ""
        gesamtbetrag = 0

        # Kundenfirma aus Adressblock (gleicher Pattern wie Rechnungen)
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if 'Oelsnitz' in line and ('rauMKult' in line or 'raumkult' in line.lower()):
                if i + 1 < len(lines):
                    kunde_firma = lines[i + 1].strip()
                break

        # Gesamtbetrag
        bm = re.search(r'Gesamtbetrag\*?\s*([\d.,]+)', text)
        if bm:
            gesamtbetrag = parse_betrag(bm.group(1))

        # Positionen extrahieren (gleicher Regex wie Rechnungen)
        positionen = []
        pos_pattern = re.compile(
            r'^(\d+)\s+(.+?)\s+(\d+(?:[.,]\d+)?)\s+\S+\s+([\d.,]+)\s+(?:[\d.,]+\s+)?([\d.,]+)$',
            re.MULTILINE
        )
        for pm in pos_pattern.finditer(text):
            positionen.append({
                "pos": int(pm.group(1)),
                "bezeichnung": pm.group(2).strip()[:120],
                "menge": parse_betrag(pm.group(3)),
                "einzelpreis": parse_betrag(pm.group(4)),
                "gesamt": parse_betrag(pm.group(5))
            })

        detail_db.execute("""INSERT OR REPLACE INTO angebote_detail
            (a_nummer, datum, kunde_firma, projekt_name, positionen_json,
             gesamtbetrag, pdf_pfad, pdf_hash, roh_text)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (a_nr, datum, kunde_firma, "",
             json.dumps(positionen, ensure_ascii=False),
             gesamtbetrag, str(pdf_path), h, text[:5000]))

        count += 1
        suffix = " (FREIGABE)" if is_freigabe else ""
        print(f"  {'UPDATE' if existing else 'NEU'}: {a_nr} | {datum} | {kunde_firma[:30]} | {gesamtbetrag:.2f} EUR | {len(positionen)} Pos.{suffix}")

    detail_db.commit()
    print(f"  → {count} Angebote verarbeitet")
    return count


# ── Scanner: Zahlungseingänge ────────────────────────────────────────────────
def scan_zahlungen(detail_db):
    """Liest Zahlungs-JSON-Dateien und extrahiert RE-Nr + Betrag."""
    print("\n═══ ZAHLUNGSEINGÄNGE SCANNEN ═══")
    if not ZAHLUNGEN_DIR.exists():
        print("  Ordner nicht gefunden")
        return 0

    json_files = [f for f in ZAHLUNGEN_DIR.iterdir() if f.suffix.lower() == '.json']
    print(f"  {len(json_files)} JSON-Dateien gefunden")

    count = 0
    for jf in sorted(json_files):
        try:
            data = json.loads(jf.read_text('utf-8'))
        except:
            print(f"  FEHLER: {jf.name} nicht lesbar")
            continue

        message_id = data.get("message_id", "")
        # Bereits verarbeitet?
        if message_id:
            existing = detail_db.execute("SELECT id FROM zahlungseingaenge WHERE message_id=?", (message_id,)).fetchone()
            if existing:
                continue

        # HTML-Body parsen
        html = data.get("text", "")
        plain = strip_html(html)

        # RE-Nummer
        m = re.search(r'Rechnungsnummer\s*<strong>(RE-SB\d+)</strong>', html)
        if not m:
            m = RE_PAT.search(plain)
        raw_nr = m.group(1) if m and m.lastindex else (m.group(0) if m else "")
        re_nr = normalize_re_nr(raw_nr) if raw_nr else ""

        # Betrag
        bm = re.search(r'in Höhe von\s*<strong>([\d.,]+)\s*€', html)
        if not bm:
            bm = re.search(r'in Höhe von\s*([\d.,]+)\s*€', plain)
        betrag = parse_betrag(bm.group(1)) if bm else 0

        # Projekt
        pm = re.search(r'Leistung\s*<strong>(.+?)</strong>', html)
        projekt = pm.group(1).strip() if pm else ""

        # Datum
        dm_match = re.search(r'am\s*<strong>(\d{2}\.\d{2}\.\d{4})</strong>', html)
        datum = ""
        if dm_match:
            try:
                datum = datetime.strptime(dm_match.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
            except: pass
        if not datum:
            datum = data.get("datum", "")[:10]

        # Kunde (aus "an" Feld)
        kunde = data.get("an", "").replace('<', '').replace('>', '').strip()

        detail_db.execute("""INSERT OR IGNORE INTO zahlungseingaenge
            (re_nummer, datum, betrag, kunde, projekt, quelle_pfad, message_id)
            VALUES (?,?,?,?,?,?,?)""",
            (re_nr, datum, betrag, kunde, projekt, str(jf), message_id))
        count += 1
        print(f"  ZAHLUNG: {re_nr} | {datum} | {betrag:.2f} EUR | {kunde[:30]} | {projekt[:30]}")

    detail_db.commit()
    print(f"  → {count} Zahlungen verarbeitet")
    return count


# ── Zahlungen zu Rechnungen matchen ─────────────────────────────────────────
def match_zahlungen(detail_db):
    """Ordnet Zahlungseingänge den Rechnungen zu. Meldet Abweichungen."""
    print("\n═══ ZAHLUNGEN MATCHEN ═══")
    zahlungen = detail_db.execute("SELECT * FROM zahlungseingaenge WHERE match_status='unmatched'").fetchall()

    alerts = []
    matched = 0

    for z in zahlungen:
        re_nr = z['re_nummer']
        if not re_nr:
            detail_db.execute("UPDATE zahlungseingaenge SET match_status='not_found' WHERE id=?", (z['id'],))
            alerts.append(f"Zahlung {z['datum']} über {z['betrag']:.2f} EUR: Keine RE-Nummer gefunden!")
            continue

        # Rechnung in rechnungen_detail suchen
        rechnung = detail_db.execute("SELECT * FROM rechnungen_detail WHERE re_nummer=?", (re_nr,)).fetchone()
        if not rechnung:
            detail_db.execute("UPDATE zahlungseingaenge SET match_status='not_found' WHERE id=?", (z['id'],))
            alerts.append(f"Zahlung für {re_nr}: Rechnung nicht in DB gefunden!")
            continue

        # Betrag vergleichen
        differenz = abs(z['betrag'] - rechnung['gesamtbetrag'])
        if differenz < 0.01:
            status = 'matched'
        elif z['betrag'] > 0 and rechnung['gesamtbetrag'] > 0:
            status = 'mismatch'
            alerts.append(f"Zahlung für {re_nr}: {z['betrag']:.2f} EUR erhalten, Rechnung: {rechnung['gesamtbetrag']:.2f} EUR (Diff: {differenz:.2f} EUR)")
        else:
            status = 'matched'

        detail_db.execute("""UPDATE zahlungseingaenge
            SET match_status=?, match_rechnung_id=?, betrag_differenz=?
            WHERE id=?""",
            (status, rechnung['id'], differenz, z['id']))
        matched += 1

    detail_db.commit()

    if alerts:
        print("  ⚠️  ALERTS:")
        for a in alerts:
            print(f"    • {a}")
    print(f"  → {matched} Zahlungen gematcht, {len(alerts)} Alerts")
    return alerts


# ── Sync in tasks.db ─────────────────────────────────────────────────────────
def sync_to_tasks_db(detail_db):
    """Synchronisiert Rechnungen und Angebote nach tasks.db."""
    print("\n═══ SYNC → tasks.db ═══")

    tdb = sqlite3.connect(str(TASKS_DB))
    tdb.row_factory = sqlite3.Row

    # Ausgangsrechnungen sync
    rechnungen = detail_db.execute("SELECT * FROM rechnungen_detail").fetchall()
    count_ar = 0
    for r in rechnungen:
        # Bestehenden Status respektieren (nicht bezahlte zurücksetzen!)
        existing = tdb.execute("SELECT id, status FROM ausgangsrechnungen WHERE re_nummer=?", (r['re_nummer'],)).fetchone()
        if existing:
            # Nur Beträge/Daten updaten, NICHT Status überschreiben
            tdb.execute("""UPDATE ausgangsrechnungen
                SET datum=?, kunde_name=?, betrag_netto=?, betrag_brutto=?, anhaenge_pfad=?
                WHERE re_nummer=?""",
                (r['datum'], r['kunde_firma'], r['zwischensumme'], r['gesamtbetrag'],
                 r['pdf_pfad'], r['re_nummer']))
        else:
            tdb.execute("""INSERT OR IGNORE INTO ausgangsrechnungen
                (re_nummer, datum, kunde_name, betrag_netto, betrag_brutto, anhaenge_pfad, status)
                VALUES (?,?,?,?,?,?,?)""",
                (r['re_nummer'], r['datum'], r['kunde_firma'],
                 r['zwischensumme'], r['gesamtbetrag'], r['pdf_pfad'], 'offen'))
        count_ar += 1

    # Zahlungseingänge → Rechnungen als bezahlt markieren
    bezahlt = detail_db.execute("SELECT * FROM zahlungseingaenge WHERE match_status='matched'").fetchall()
    for z in bezahlt:
        ar = tdb.execute("SELECT id, status FROM ausgangsrechnungen WHERE re_nummer=?", (z['re_nummer'],)).fetchone()
        if ar and ar['status'] == 'offen':
            tdb.execute("UPDATE ausgangsrechnungen SET status='bezahlt', bezahlt_am=? WHERE id=?",
                        (z['datum'], ar['id']))
            print(f"  ✓ {z['re_nummer']} als bezahlt markiert ({z['datum']})")

    # Mahnungen → mahnung_count erhöhen
    mahnungen = detail_db.execute("SELECT re_nummer, COUNT(*) as cnt, MAX(datum) as letzte FROM mahnungen_detail GROUP BY re_nummer").fetchall()
    for m in mahnungen:
        tdb.execute("UPDATE ausgangsrechnungen SET mahnung_count=?, letzte_mahnung=? WHERE re_nummer=?",
                    (m['cnt'], m['letzte'], m['re_nummer']))

    # Angebote sync
    angebote = detail_db.execute("SELECT * FROM angebote_detail").fetchall()
    count_ang = 0
    for a in angebote:
        existing = tdb.execute("SELECT id, status FROM angebote WHERE a_nummer=?", (a['a_nummer'],)).fetchone()
        if existing:
            tdb.execute("""UPDATE angebote
                SET datum=?, kunde_name=?, betrag_geschaetzt=?, anhaenge_pfad=?
                WHERE a_nummer=?""",
                (a['datum'], a['kunde_firma'], a['gesamtbetrag'], a['pdf_pfad'], a['a_nummer']))
        else:
            # Altes Angebot (vor Feb 2026)? → 'bearbeitet'
            status = 'offen'
            if a['datum'] and a['datum'] < '2026-02-01':
                status = 'bearbeitet'
            tdb.execute("""INSERT OR IGNORE INTO angebote
                (a_nummer, datum, kunde_name, betrag_geschaetzt, anhaenge_pfad, status)
                VALUES (?,?,?,?,?,?)""",
                (a['a_nummer'], a['datum'], a['kunde_firma'],
                 a['gesamtbetrag'], a['pdf_pfad'], status))
        count_ang += 1

    tdb.commit()
    tdb.close()
    print(f"  → {count_ar} Rechnungen, {count_ang} Angebote in tasks.db synchronisiert")


# ── Zusammenfassung ──────────────────────────────────────────────────────────
def print_summary(detail_db):
    """Druckt eine Zusammenfassung aller gescannten Daten."""
    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)

    r_count = detail_db.execute("SELECT COUNT(*) FROM rechnungen_detail").fetchone()[0]
    r_total = detail_db.execute("SELECT COALESCE(SUM(gesamtbetrag),0) FROM rechnungen_detail").fetchone()[0]
    print(f"  Rechnungen:     {r_count:3d}  |  Gesamtvolumen: {r_total:>12,.2f} EUR")

    p_count = detail_db.execute("SELECT COUNT(*) FROM rechnungs_positionen").fetchone()[0]
    print(f"  Positionen:     {p_count:3d}  |  (Für Preisvergleiche)")

    m_count = detail_db.execute("SELECT COUNT(*) FROM mahnungen_detail").fetchone()[0]
    print(f"  Mahnungen:      {m_count:3d}")

    z_count = detail_db.execute("SELECT COUNT(*) FROM zahlungseingaenge").fetchone()[0]
    z_matched = detail_db.execute("SELECT COUNT(*) FROM zahlungseingaenge WHERE match_status='matched'").fetchone()[0]
    z_total = detail_db.execute("SELECT COALESCE(SUM(betrag),0) FROM zahlungseingaenge").fetchone()[0]
    print(f"  Zahlungen:      {z_count:3d}  |  {z_matched} gematcht  |  {z_total:>12,.2f} EUR")

    a_count = detail_db.execute("SELECT COUNT(*) FROM angebote_detail").fetchone()[0]
    a_total = detail_db.execute("SELECT COALESCE(SUM(gesamtbetrag),0) FROM angebote_detail").fetchone()[0]
    print(f"  Angebote:       {a_count:3d}  |  Gesamtvolumen: {a_total:>12,.2f} EUR")

    # Top-Positionen nach Häufigkeit
    top_pos = detail_db.execute("""
        SELECT bezeichnung, COUNT(*) as cnt, AVG(einzelpreis) as avg_preis,
               MIN(einzelpreis) as min_preis, MAX(einzelpreis) as max_preis
        FROM rechnungs_positionen
        WHERE einzelpreis > 0
        GROUP BY bezeichnung
        ORDER BY cnt DESC
        LIMIT 5
    """).fetchall()
    if top_pos:
        print(f"\n  TOP-5 Positionen (Häufigkeit):")
        for p in top_pos:
            print(f"    {p[0][:50]:50s}  {p[1]}x  Ø {p[2]:>8.2f}  ({p[3]:.2f} – {p[4]:.2f}) EUR")

    print("=" * 60)


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  scan_dokumente.py — rauMKult® Dokumenten-Scanner      ║")
    print("║  Quelle: OneDrive Ordner (NICHT Mail-Archiv)           ║")
    print("╚══════════════════════════════════════════════════════════╝")

    detail_db = init_detail_db()
    init_tasks_db_tables()

    scan_rechnungen(detail_db)
    scan_mahnungen(detail_db)
    scan_angebote(detail_db)
    scan_zahlungen(detail_db)
    alerts = match_zahlungen(detail_db)

    sync_to_tasks_db(detail_db)
    print_summary(detail_db)

    detail_db.close()

    if alerts:
        print(f"\n⚠️  {len(alerts)} Zahlungs-Alerts — Kai informieren!")
        # TODO: ntfy Push senden

    print("\nFertig.")


if __name__ == "__main__":
    main()
