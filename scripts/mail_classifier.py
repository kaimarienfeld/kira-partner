#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mail-Klassifizierung fuer rauMKult / Kira.
Strikt regelbasiert. Keine KI, kein Autoresponder.
Verbindliche Kategorien aus Prompt_01 § 6 + Ausschlusslogik § 7.
"""
import re

# ======================================================================
# 1. SYSTEM-ABSENDER  –  generieren NIEMALS eine Aufgabe
# ======================================================================
SYSTEM_DOMAINS = {
    # ── SaaS / Tools ──
    "ecwid.com","stripe.com","paypal.de","paypal.com","paypal.co.uk",
    "figma.com","anthropic.com","openai.com","descript.com","obsbot.com",
    "stripo.email","memberspot.de","avg.com","avast.com","vevor.com",
    "answerthepublic.com","canva.com","notion.so","dropbox.com","box.com",
    "github.com","gitlab.com","atlassian.com","slack.com","zoom.us",
    "trello.com","asana.com","monday.com","todoist.com","miro.com",
    "airtable.com","grammarly.com","loom.com","calendly.com",
    "typeform.com","surveymonkey.com","hotjar.com","intercom.io",
    "zendesk.com","freshdesk.com","crisp.chat","tawk.to",
    "semrush.com","ahrefs.com","moz.com","hubspot.com","hubspotemail.com",
    # ── Microsoft / Google / Apple ──
    "microsoft.com","office365.com","outlook.com","live.com",
    "google.com","googlemail.com","youtube.com","apple.com","icloud.com",
    # ── Newsletter-Dienste ──
    "mailchimp.com","sendinblue.com","brevo.com","mailerlite.com",
    "constantcontact.com","klaviyo.com","sendgrid.net","sparkpost.com",
    "mailgun.com","postmarkapp.com","mailjet.com","getresponse.com",
    "activecampaign.com","convertkit.com","drip.com","moosend.com",
    # ── E-Commerce-Plattformen ──
    "shopify.com","wix.com","squarespace.com","jimdo.com","ionos.de","strato.de",
    "woocommerce.com","bigcommerce.com","etsy.com","billbee.io",
    # ── Security / Antivirus ──
    "norton.com","mcafee.com","kaspersky.com","bitdefender.com","avira.com",
    # ── Social Media ──
    "facebook.com","facebookmail.com","instagram.com","twitter.com",
    "linkedin.com","xing.com","pinterest.com","tiktok.com","reddit.com",
    # ── Consumer / Shopping ──
    "amazon.de","amazon.com","ebay.de","ebay.com","otto.de","zalando.de",
    "lieferando.de","hellofresh.de","booking.com","airbnb.com",
    # ── Buchhaltung (System-Benachrichtigungen, nicht Kundenmail) ──
    "lexware.de","lexoffice.de","sevdesk.de","fastbill.de","datev.de",
    "belege.lexware.de",
    # ── Hosting / Domain ──
    "secureserver.net","godaddy.com","namecheap.com","cloudflare.com",
    "hetzner.com","ovh.com","1und1.de",
    # ── Versand / Logistik ──
    "dhl.de","dpd.de","gls-group.eu","ups.com","fedex.com","hermes-germany.de",
    # ── Cloud ──
    "azure.com","amazonaws.com","digitalocean.com",
    # ── Bekannte Nicht-Kunden-Absender ──
    "nordicfire.nl","specialchem.com",
    # ── Finanzen / Lending ──
    "iwoca.de","iwoca.com","auxmoney.com","smava.de","finanzcheck.de",
    # ── Entwickler-Tools / IDE ──
    "cursor.com","jetbrains.com","vscode.dev","replit.com","vercel.com",
    "netlify.com","railway.app","render.com",
    # ── Online-Kurse / Marketing-Absender ──
    "jonaskeil.com","udemy.com","skillshare.com","coursera.org",
    # ── Lieferanten-Marketing (keine Kunden) ──
    "guese.de","mewagmbh.de","bellafloor.de",
}

SYSTEM_SENDER_PATTERNS = [
    r"^no[-_.]?reply@",
    r"^noreply@",
    r"^do[-_.]?not[-_.]?reply@",
    r"^notifications?@",
    r"^alerts?@",
    r"^billing@",
    r"^newsletter@",
    r"^marketing@",
    r"^mailer[-_.]?daemon@",
    r"^postmaster@",
    r"^bounced?@",
    r"^system@",
    r"^news@",
    r"^updates?@",
    r"^digest@",
    r"^announcements?@",
    r"^promotions?@",
    r"^deals@",
    r"^offers?@",
    r"^store@",
    r"^order[s_-]?@",
    r"^invoice[s_-]?.*@",
    r"^receipt[s_-]?@",
    r"^statement[s_-]?@",
    r"^confirm(ation)?@",
    r"^verify@",
    r"^security@",
    r"^account@",
    r"^research@",
    r"^versand@",
    r"^notice@",
    r"^feedback@",
]

# ======================================================================
# 2. NEWSLETTER / WERBUNG  –  Keywords
# ======================================================================
NL_KEYWORDS = [
    "newsletter","unsubscribe","abmelden","abbestellen","email preferences",
    "email-einstellungen","view in browser","im browser ansehen","webversion",
    "% off","% rabatt","% discount","promo code","gutscheincode",
    "sonderangebot","flash sale","black friday","cyber monday",
    "limited time","jetzt sichern","jetzt zugreifen","exklusiv fuer",
    "haendlertage","saisonstart","fruehbucher","neuheiten vorstellung",
]

# ======================================================================
# 3. AUSSCHLUSS-BETREFFS  (Prompt 01 § 7)
# ======================================================================
EXCLUDE_SUBJECTS = [
    # Warenkorb / Shop-System
    "warenkorb","shopping cart","abandoned cart","artikel in ihrem",
    "anmelde-link","login-link","anmeldelink","loginlink",
    "ihr konto","your account","konto aktualisieren",
    "passwort zuruecksetzen","password reset","verify your",
    "willkommen beim","welcome to",
    # Tarif / Abo
    "tarif","subscription","abonnement","abo","trial","testphase",
    "verlaenger","renew","erneuert","renewed",
    # Punkte / Praemien
    "punkte","praemie","reward","points","cashback",
    # Reine Bestaetigung
    "bestellung bestaetigt","order confirmed","versandbestaetigung",
    "shipping confirmation","tracking","sendungsverfolgung",
    # Receipts / Quittung
    "your receipt","ihre quittung",
    # System-Security
    "account deletion","loeschung","deactivat","security alert",
    "login attempt","new sign-in","neue anmeldung",
    # Survey / Feedback
    "survey","umfrage","how has your experience","wie war ihr",
    "rate us","bewertung abgeben","review your",
    # Marketing fluff
    "entdecken sie","discover","looking for inspiration",
    "check out","neue features","new feature",
    "update available","jetzt upgraden","upgrade now",
    "entwickler in","webinar","event einladung",
    "sonderaktion","highlights fuer","highlights für",
    "letzte chance","last chance","morgen ist es soweit",
    "workbook","ki-kurs","online-kurs",
    "fruehlingsfr","fruehjahrsaktion","osteraktion",
    "preissteigerung","jetzt entscheiden","jetzt sichern",
    "pv-anlage","photovoltaik",
    "tools across","customizing agents","using agents",
    "development lifecycle","across the development",
    "ratenzahlung steht an","abbuchung fehlgeschlagen",
    "rueckzahlung von",
]

# ======================================================================
# 4. ECHTE KUNDEN-KEYWORDS
# ======================================================================
CUSTOMER_STRONG = [
    # Branchenspezifisch (rauMKult)
    "betonkosmetik","sichtbeton","betontreppe","betonfassade","betonwand",
    "sichtbetonflaeche","ortbeton","fertigteil",
    "hydrophobierung","impraegnierung","versiegelung",
    "kostenvoranschlag","angebot erstellen",
    # Universell — starke Kauf-/Auftragssignale
    "beauftragen","auftrag erteilen","in auftrag geben",
    "wir bestellen","hiermit bestelle","verbindliche bestellung",
    "angebot angenommen","auftrag erteilt","zusage",
    "angebot abgelehnt","absage","leider muessen wir",
]
CUSTOMER_NORMAL = [
    # Branchenspezifisch
    "anfrage","projekt","sanierung","retusche","reparatur","ausbesserung",
    "beton","treppe","fassade","wand","boden","decke",
    "reinigung","oberflaeche","flaeche","qm","quadratmeter",
    "foto","bilder sende","anbei foto",
    # Universell — Anfragen & Kontakt
    "was kostet","wie teuer","preis","kosten","preisliste",
    "termin","zeitraum","verfuegbar","wann koennen","terminvorschlag",
    "baustelle","neubau","umbau","anbau","renovierung","instandsetzung",
    "koennen sie","koennten sie","waere es moeglich",
    "haette gerne","braeuchte","benoetige","suche jemand",
    "angebot","offerte","preisanfrage","kalkulation",
    "besichtigung","begutachtung","vor ort","ortstermin",
    "schadensbild","schaeden","mangel","reklamation",
    "rueckfrage","bezugnehmend auf","in bezug auf",
    "interesse","interessiert","informieren sie mich",
    "zusammenarbeit","kooperation","partnerschaft",
    "empfehlung","empfohlen","referenz",
    "dringend","zeitnah","schnellstmoeglich","asap",
]

# ======================================================================
# 4b. EIGENE KEYWORDS (aus config.json, zur Laufzeit geladen)
# ======================================================================
def _load_eigene_keywords():
    """Lädt benutzerdefinierte Keywords aus config.json."""
    try:
        import json
        from pathlib import Path
        cfg_path = Path(__file__).parent / "config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text("utf-8", errors="replace"))
            mk = cfg.get("mail_klassifizierung", {})
            return mk.get("eigene_keywords", [])
    except Exception:
        pass
    return []


# ======================================================================
# 4c. EIGENE DOMAINS + ADRESSEN (aus config.json, dynamisch)
# ======================================================================
_eigene_cache = {"ts": 0, "emails": set(), "domains": set()}

def load_eigene_config():
    """
    Lädt eigene E-Mail-Adressen und Domains aus config.json.
    Quellen:
      1. combined_postfach.konten → konfigurierte Konten-Adressen
      2. mail_klassifizierung.eigene_domains_extra → manuelle Zusatz-Domains
    Gibt zurück: (eigene_emails: set, eigene_domains: set)
    Cache: 60 Sekunden
    """
    import json, time
    from pathlib import Path
    now = time.time()
    if now - _eigene_cache["ts"] < 60 and _eigene_cache["emails"]:
        return _eigene_cache["emails"], _eigene_cache["domains"]
    try:
        cfg_path = Path(__file__).parent / "config.json"
        cfg = json.loads(cfg_path.read_text("utf-8", errors="replace"))

        # 1. Konfigurierte E-Mail-Konten
        konten = cfg.get("combined_postfach", {}).get("konten", [])
        # Auch aus mail_konto_labels (falls konten leer)
        labels = cfg.get("mail_konto_labels", {})
        alle_emails = set()
        for k in konten:
            alle_emails.add(k.lower().strip())
        for k in labels:
            alle_emails.add(k.lower().strip())

        # 2. Domains aus Adressen ableiten
        domains = set()
        for em in alle_emails:
            if '@' in em:
                domains.add(em.split('@')[-1].lower())

        # 3. Zusätzliche manuelle Domains
        mk = cfg.get("mail_klassifizierung", {})
        extras = mk.get("eigene_domains_extra", [])
        for d in extras:
            domains.add(d.lower().strip())

        _eigene_cache.update({"ts": now, "emails": alle_emails, "domains": domains})
        return alle_emails, domains
    except Exception:
        # Fallback: leere Sets (kein Hardcoding!)
        return set(), set()

# ======================================================================
# 5. RECHNUNGS-KEYWORDS
# ======================================================================
RECHNUNG_KEYWORDS = [
    "rechnung","invoice","beleg","quittung",
    "gutschrift","credit note","storno","erstattung","refund",
    "mahnung","zahlungserinnerung","payment reminder",
    "faellig","due date","zahlungsziel",
]

# ======================================================================
# 6. ORGANISATIONS-PATTERNS
# ======================================================================
DATE_PATTERNS = [
    r'am\s+(\d{1,2}\.\d{1,2}\.\d{2,4})',
    r'bis\s+(?:zum\s+)?(\d{1,2}\.\d{1,2}\.\d{2,4})',
    r'Termin[:\s]+(\d{1,2}\.\d{1,2}\.\d{2,4})',
    r'Frist[:\s]+(\d{1,2}\.\d{1,2}\.\d{2,4})',
    r'Deadline[:\s]+(\d{1,2}\.\d{1,2}\.\d{2,4})',
]
CALLBACK_PATTERNS = [
    r'(?:bitte\s+)?(?:rufen\s+Sie|ruf)\s+(?:mich\s+)?(?:an|zurueck)',
    r'Rueckruf(?:bitte)?',
    r'melden\s+Sie\s+sich',
    r'bitte\s+(?:um\s+)?(?:Rueckmeldung|Rueckruf|Anruf)',
    r'telefonisch\s+(?:erreichbar|erreichen)',
    r'(?:koennen|koennten)\s+Sie\s+(?:mich\s+)?anrufen',
]
DEADLINE_PATTERNS = [
    r'(?:bis|spaetestens)\s+(?:zum\s+)?(\d{1,2}\.\d{1,2}\.\d{2,4})',
    r'Frist\s+(?:endet|laeuft)\s+(?:am\s+)?(\d{1,2}\.\d{1,2}\.\d{2,4})',
]

# ======================================================================
# 7. BETRAG / RECHNUNGSNUMMER
# ======================================================================
BETRAG_PATTERNS = [
    r'(?:EUR|€)\s*(\d{1,6}[.,]\d{2})',
    r'(\d{1,6}[.,]\d{2})\s*(?:EUR|€)',
    r'Betrag[:\s]*(\d{1,6}[.,]\d{2})',
    r'Gesamt[:\s]*(?:EUR|€)?\s*(\d{1,6}[.,]\d{2})',
    r'Rechnungsbetrag[:\s]*(?:EUR|€)?\s*(\d{1,6}[.,]\d{2})',
]
RE_NR_PATTERNS = [
    r'(?:Rechnungs?|Invoice|RE)\s*[-#:.]?\s*([\w/-]{4,25})',
]


# ======================================================================
# HILFSFUNKTIONEN
# ======================================================================
def extract_email(absender: str) -> str:
    m = re.search(r'<([^>]+@[^>]+)>', absender or "")
    return (m.group(1) if m else (absender or "")).lower().strip()

def get_domain(email: str) -> str:
    return email.split('@')[-1].lower() if '@' in email else ''

def _normalize(text: str) -> str:
    """Deutsche Umlaute normalisieren fuer sicheres Matching."""
    return (text.replace('ä','ae').replace('ö','oe').replace('ü','ue')
               .replace('Ä','Ae').replace('Ö','Oe').replace('Ü','Ue')
               .replace('ß','ss'))

def _kw_in(keywords: list, text: str) -> bool:
    return any(kw in text for kw in keywords)


# ======================================================================
# KLASSIFIZIERUNG
# ======================================================================
def is_system_sender(absender: str) -> bool:
    email = extract_email(absender)
    domain = get_domain(email)
    # Direkte Domain
    if domain in SYSTEM_DOMAINS:
        return True
    # Subdomain-Check  (z.B. mail.anthropic.com -> anthropic.com)
    parts = domain.split('.')
    for i in range(1, len(parts)):
        if '.'.join(parts[i:]) in SYSTEM_DOMAINS:
            return True
    # Sender-Pattern
    for pat in SYSTEM_SENDER_PATTERNS:
        if re.match(pat, email, re.IGNORECASE):
            return True
    return False


def is_newsletter(absender: str, betreff: str, text: str) -> bool:
    combined = _normalize((absender + " " + betreff + " " + (text or "")[:600]).lower())
    return _kw_in(NL_KEYWORDS, combined)


def is_exclude_subject(betreff: str) -> bool:
    bl = _normalize(betreff.lower())
    return _kw_in(EXCLUDE_SUBJECTS, bl)


def has_open_question(text: str) -> bool:
    """Prueft ob echte Frage an den Empfaenger vorliegt (nicht Marketing-Fragen)."""
    t = _normalize((text or "")[:3000]).lower()
    # Starke Frage-Patterns (direkt an Empfaenger gerichtet)
    strong = [
        r'(?:koennen|koennten|wuerden|waere|haette)\s+(?:sie|ihr|du)',
        r'(?:brauche|benoetige|suche|haette gerne)',
        r'(?:bitte um|bitte senden|bitte schicken)',
        r'(?:gibt es|ist es moeglich|waere es moeglich)',
        r'(?:wuerde mich freuen|wuerde gerne|moechte gerne)',
        r'(?:koennen sie mir|koennten sie mir)',
    ]
    # Schwache Frage: nur ? reicht nicht (Marketing nutzt auch ?)
    has_strong = any(re.search(p, t) for p in strong)
    if has_strong:
        return True
    # ? nur zaehlen wenn kein typisches Marketing-Muster vorliegt
    if '?' in t:
        marketing_in_text = _kw_in(["unsubscribe","abmelden","newsletter",
            "jetzt sichern","sonderangebot","klicken sie hier","click here",
            "view in browser","im browser ansehen"], t)
        if not marketing_in_text:
            return True
    return False


def classify_absender_rolle(absender: str, betreff: str, text: str,
                            konto: str, is_sent: bool) -> str:
    if is_sent:
        return "Eigene Mail"
    if is_system_sender(absender):
        combined = _normalize((betreff + " " + (text or "")[:300]).lower())
        if _kw_in(RECHNUNG_KEYWORDS, combined):
            return "Rechnung / Beleg"
        if is_newsletter(absender, betreff, text):
            return "Newsletter / Werbung"
        return "System"
    combined = _normalize((betreff + " " + (text or "")[:400]).lower())
    if _kw_in(RECHNUNG_KEYWORDS[:4], combined):
        return "Rechnung / Beleg"
    if konto == "shop":
        return "Shop"
    if konto in ("anfrage","info"):
        bl = _normalize(betreff.lower())
        if bl.startswith("re:") or bl.startswith("aw:"):
            return "Bestandskunde"
        return "Interessent / Lead"
    return "Unbekannt"


# ── Hauptfunktion ─────────────────────────────────────────────────────
def classify_mail(konto: str, absender: str, betreff: str, text: str,
                  anhaenge: list = None, folder: str = "",
                  is_sent: bool = False) -> dict:
    """
    Gibt zurueck:
      kategorie, absender_rolle, zusammenfassung, antwort_noetig,
      empfohlene_aktion, kategorie_grund, prioritaet,
      organisation (dict|None), geschaeft (dict|None)
    """
    email  = extract_email(absender)
    domain = get_domain(email)
    bl     = _normalize(betreff.lower())
    txt_n  = _normalize((text or "")[:3000]).lower()
    comb   = bl + " " + txt_n
    rolle  = classify_absender_rolle(absender, betreff, text, konto, is_sent)

    # ── 1. Gesendete Mails ──
    if is_sent or "Gesendete" in folder or "Sent" in folder:
        return _r("Abgeschlossen", rolle, betreff, False,
                  "Eigene Mail – kein Handlungsbedarf", "Gesendete Mail", "niedrig",
                  routing="archivieren", erfordert_handlung=False)

    # ── 1b. Formular-Benachrichtigungen (noreply@ → Lead) ──
    # Landing-Page/Kontaktformular-Mails von noreply@ enthalten echte Kundenanfragen
    # Diese NICHT als System-Mail behandeln, sondern als Lead
    _is_form = bool(re.search(
        r'(Anfrage\s*\(Landing\)|Kontaktformular|neue\s+Anfrage|Anfrage\s+über)',
        betreff or "", re.IGNORECASE))
    _is_noreply = bool(re.match(r'^no[-_.]?reply@', email))
    if _is_form and _is_noreply:
        prio = "hoch"
        aktion = "Formular-Anfrage prüfen und beantworten"
        if has_open_question(text):
            aktion = "Anfrage enthält konkrete Frage — priorisiert beantworten"
        return _r("Neue Lead-Anfrage", "Interessent / Lead", betreff, True,
                  aktion, "Automatische Formular-Benachrichtigung (Landing Page/Kontaktformular)",
                  prio)

    # ── 2. System-Absender (Prompt 01 § 7) ──
    # Eigene Domains → Kopie-Erkennung (Absender = konfigurierte eigene Adresse → archivieren)
    _eigene_emails, _eigene_domains = load_eigene_config()
    if email in _eigene_emails:
        return _r("Abgeschlossen", "Intern", betreff, False,
                  "Interne Kopie — kein Handlungsbedarf", f"Eigene Domain {domain}", "niedrig",
                  routing="archivieren", erfordert_handlung=False)

    if is_system_sender(absender):
        if _kw_in(["mahnung","zahlungserinnerung","payment reminder","overdue"], comb):
            return _r("Rechnung / Beleg", "Mahnung", betreff, True,
                      "Mahnung pruefen", f"System-Mahnung von {domain}", "hoch",
                      geschaeft=_extr_gesc(betreff, text, "mahnung"),
                      routing="buchhaltung", erfordert_handlung=False)
        if _kw_in(RECHNUNG_KEYWORDS[:4], comb):
            return _r("Rechnung / Beleg", "Rechnung / Beleg", betreff, False,
                      "Zur Kenntnis / Ablegen", f"Beleg von {domain}", "niedrig",
                      geschaeft=_extr_gesc(betreff, text, "beleg"),
                      routing="buchhaltung", erfordert_handlung=False)
        if is_newsletter(absender, betreff, text):
            return _r("Newsletter / Werbung", "Newsletter / Werbung", betreff, False,
                      "Ignorieren", f"Newsletter von {domain}", "niedrig",
                      routing="archivieren", erfordert_handlung=False)
        return _r("Ignorieren", "System", betreff, False,
                  "Ignorieren", f"Systemnachricht von {domain}", "niedrig",
                  routing="archivieren", erfordert_handlung=False)

    # ── 3. Newsletter (auch nicht-System) ──
    if is_newsletter(absender, betreff, text):
        return _r("Newsletter / Werbung", "Newsletter / Werbung", betreff, False,
                  "Ignorieren", "Newsletter-Keywords erkannt", "niedrig",
                  routing="archivieren", erfordert_handlung=False)

    # ── 4. Ausschluss-Betreffs (Prompt 01 § 7) ──
    if is_exclude_subject(betreff):
        return _r("Ignorieren", rolle, betreff, False,
                  "Ignorieren", "Betreff faellt unter Ausschlusslogik", "niedrig",
                  routing="archivieren", erfordert_handlung=False)

    # ── 5. Rechnungen / Belege ──
    if _kw_in(RECHNUNG_KEYWORDS, comb):
        hat_frage = has_open_question(text)
        if hat_frage:
            return _r("Antwort erforderlich", "Rechnung / Beleg", betreff, True,
                      "Rueckfrage zur Rechnung beantworten",
                      "Rechnung/Beleg mit offener Frage", "hoch",
                      geschaeft=_extr_gesc(betreff, text, "rechnung"),
                      routing="task", erfordert_handlung=True)
        return _r("Rechnung / Beleg", "Rechnung / Beleg", betreff, False,
                  "Zur Kenntnis / Ablegen",
                  "Rechnungsbeleg ohne offene Frage", "niedrig",
                  geschaeft=_extr_gesc(betreff, text, "rechnung"),
                  routing="buchhaltung", erfordert_handlung=False)

    # ── 6. Shop ──
    if konto == "shop" or _kw_in(["bestellung","order","bestell","neue bestellung"], bl):
        hat_frage = has_open_question(text)
        if hat_frage:
            return _r("Antwort erforderlich", "Shop", betreff, True,
                      "Shop-Anfrage beantworten", "Shop-Mail mit Frage", "mittel",
                      routing="task", erfordert_handlung=True)
        return _r("Shop / System", "Shop", betreff, False,
                  "Zur Kenntnis", "Shop-Vorgang ohne Frage", "niedrig",
                  routing="archivieren", erfordert_handlung=False)

    # ── 6b. Geschäftskontakt-Filter (CRM) ──
    try:
        from kunden_classifier import ist_geschaeftskontakt
        if not ist_geschaeftskontakt(absender, betreff):
            # Kein Geschäftsfall — als Newsletter/Werbung klassifizieren
            return _r("Newsletter / Werbung", "System / Newsletter", betreff, False,
                      "Keine Aktion nötig",
                      "Kein Geschäftskontakt (CRM-Filter)", "niedrig",
                      routing="archivieren", erfordert_handlung=False)
    except ImportError:
        pass  # kunden_classifier nicht verfügbar — weiter mit alter Logik

    # ── 7. Echte Kundenanfragen (inkl. eigener Keywords aus Einstellungen) ──
    eigene = _load_eigene_keywords()
    strong = sum(1 for kw in CUSTOMER_STRONG if kw in comb)
    normal = sum(1 for kw in CUSTOMER_NORMAL if kw in comb)
    eigene_hits = sum(1 for kw in eigene if kw.lower() in comb) if eigene else 0
    is_customer = (strong >= 1 or (normal >= 2) or eigene_hits >= 1
                   or (konto in ("anfrage",) and normal >= 1))

    if is_customer:
        is_reply = bl.startswith("re:") or bl.startswith("aw:")
        org = _extr_org(text)
        if is_reply:
            kat = "Angebotsrueckmeldung" if "angebot" in comb else "Antwort erforderlich"
            return _r(kat, "Bestandskunde", betreff, True,
                      "Antwort schreiben", "Kunden-Folgemail", "hoch", organisation=org)
        return _r("Neue Lead-Anfrage", "Interessent / Lead", betreff, True,
                  "Mit Kira besprechen – Infos einsammeln",
                  "Neue Kundenanfrage erkannt", "hoch", organisation=org)

    # ── 8. Offene Frage (Fallback) ──
    if has_open_question(text) and konto in ("anfrage","info","intern"):
        return _r("Antwort erforderlich", rolle, betreff, True,
                  "Prüfen und ggf. antworten",
                  "Offene Frage erkannt", "mittel",
                  organisation=_extr_org(text))

    # ── 8b. Substanzielle Mails an Geschäftskonten ──
    # Mails an anfrage@/info@ mit echtem Inhalt sind wahrscheinlich relevant
    if konto in ("anfrage", "info") and len((text or "").strip()) > 100:
        is_reply = bl.startswith("re:") or bl.startswith("aw:")
        if is_reply:
            return _r("Antwort erforderlich", rolle, betreff, True,
                      "Folgemail prüfen und antworten",
                      "Antwort auf eigene Mail (Fallback)", "mittel")
        # Persönliche/geschäftliche Anrede?
        _personal = any(w in comb for w in [
            "hallo", "guten tag", "sehr geehrt", "liebe ", "lieber ",
            "hi ", "moin", "guten morgen",
            "mfg", "mit freundlich", "gruss", "gruess",
            "vielen dank", "danke fuer", "danke für",
            "hochachtungsvoll", "beste gruesse",
        ])
        if _personal:
            return _r("Antwort erforderlich", rolle, betreff, False,
                      "Prüfen – möglicherweise relevant",
                      "Persönliche Mail ohne klare Kategorie (Fallback)", "niedrig")

    # ── 9. Zur Kenntnis ──
    return _r("Zur Kenntnis", rolle, betreff, False,
              "Keine Aktion nötig", "Kein Handlungsbedarf erkannt", "niedrig",
              routing="feed", erfordert_handlung=False)


# ── Ergebnis-Builder ──────────────────────────────────────────────────
def _r(kategorie, rolle, betreff, antwort_noetig, empfohlene_aktion,
       kategorie_grund, prioritaet, organisation=None, geschaeft=None,
       routing=None, erfordert_handlung=None):
    z = betreff[:100].strip()
    for prefix in ("re: ","aw: ","fwd: ","wg: "):
        if z.lower().startswith(prefix):
            z = z[len(prefix):].strip()

    # Routing-Defaults ableiten wenn nicht explizit gesetzt
    if routing is None:
        routing = _default_routing(kategorie, antwort_noetig)
    if erfordert_handlung is None:
        erfordert_handlung = routing == "task"

    return {
        "kategorie":          kategorie,
        "absender_rolle":     rolle,
        "zusammenfassung":    z,
        "antwort_noetig":     antwort_noetig,
        "empfohlene_aktion":  empfohlene_aktion,
        "kategorie_grund":    kategorie_grund,
        "prioritaet":         prioritaet,
        "erfordert_handlung": erfordert_handlung,
        "routing":            routing,
        "organisation":       organisation,
        "geschaeft":          geschaeft,
    }


def _default_routing(kategorie, antwort_noetig):
    """Leitet Routing aus Kategorie ab — Fallback wenn LLM kein Routing liefert."""
    if kategorie in ("Ignorieren", "Newsletter / Werbung", "Abgeschlossen"):
        return "archivieren"
    if kategorie == "Rechnung / Beleg" and not antwort_noetig:
        return "buchhaltung"
    if kategorie in ("Shop / System",) and not antwort_noetig:
        return "archivieren"
    if kategorie == "Zur Kenntnis":
        return "feed"
    if kategorie in ("Antwort erforderlich", "Neue Lead-Anfrage"):
        return "task"
    if kategorie == "Angebotsrueckmeldung":
        return "task"
    return "task"


# ── Organisations-Extraktion ─────────────────────────────────────────
def _extr_org(text: str):
    if not text:
        return None
    t = text[:2000]
    result = {}
    for pat in DATE_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            result["termin"] = m.group(1) if m.lastindex else m.group(0)
            break
    for pat in CALLBACK_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            result["rueckruf"] = True
            break
    for pat in DEADLINE_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            result["frist"] = m.group(1) if m.lastindex else m.group(0)
            break
    return result or None


# ── Geschaefts-Extraktion ────────────────────────────────────────────
def _extr_gesc(betreff: str, text: str, typ: str):
    combined = (betreff or "") + " " + ((text or "")[:2000])
    result = {"typ": typ}
    for pat in RE_NR_PATTERNS:
        m = re.search(pat, combined, re.IGNORECASE)
        if m:
            result["rechnungsnummer"] = m.group(1)
            break
    for pat in BETRAG_PATTERNS:
        m = re.search(pat, combined)
        if m:
            try:
                result["betrag"] = float(m.group(1).replace(',','.'))
            except:
                pass
            break
    return result if len(result) > 1 else None


# ── Kategorie -> Task-Typ Mapping ────────────────────────────────────
KATEGORIE_ZU_TASK_TYP = {
    "Antwort erforderlich":  "unanswered",
    "Neue Lead-Anfrage":     "anfrage",
    "Angebotsrueckmeldung":  "kunden_antwort",
    "Termin / Frist":        "termin",
    "Wiedervorlage":         "wiedervorlage",
    "Rechnung / Beleg":      "rechnung",
    "Shop / System":         "shop",
    "Newsletter / Werbung":  "newsletter",
    "Zur Kenntnis":          "zur_kenntnis",
    "Abgeschlossen":         "erledigt",
    "Ignorieren":            "ignorieren",
}

def kategorie_to_task_typ(kategorie: str) -> str:
    return KATEGORIE_ZU_TASK_TYP.get(kategorie, "sonstige")
