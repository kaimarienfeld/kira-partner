#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llm_classifier.py — LLM-gestützte Mail-Klassifizierung für rauMKult®.
Strategie: Fast-Path (regelbasiert) → LLM → Fallback (regelbasiert).
Drop-in-Replacement für mail_classifier.classify_mail().
"""
import json, re, sqlite3
from pathlib import Path

# Bestehender Klassifizierer als Fallback
from mail_classifier import (
    classify_mail as _classify_rule_based,
    is_system_sender, is_newsletter, is_exclude_subject,
    extract_email, kategorie_to_task_typ,
    KATEGORIE_ZU_TASK_TYP,
    _extr_org, _extr_gesc
)

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"
KUNDEN_DB     = KNOWLEDGE_DIR / "kunden.db"
MAIL_INDEX_DB = KNOWLEDGE_DIR / "mail_index.db"

# Generische E-Mail-Domains (kein Firmen-Domain-Match sinnvoll)
_GENERIC_DOMAINS = {
    "gmail.com","web.de","gmx.de","gmx.net","yahoo.com","yahoo.de",
    "outlook.com","hotmail.com","t-online.de","freenet.de","icloud.com",
    "live.com","posteo.de","protonmail.com","mailbox.org","aol.com",
}

# Alle gültigen Kategorien
KATEGORIEN = [
    "Antwort erforderlich",
    "Neue Lead-Anfrage",
    "Angebotsrueckmeldung",
    "Rechnung / Beleg",
    "Shop / System",
    "Newsletter / Werbung",
    "Zur Kenntnis",
    "Abgeschlossen",
    "Ignorieren",
]

PRIORITAETEN = ["hoch", "mittel", "niedrig"]


def _build_classification_prompt(konto, absender, betreff, text, folder, is_sent,
                                  angebote_kontext: str = "", correction_beispiele: str = "",
                                  kira_wissen: str = "", kunden_profil: str = "",
                                  mail_verlauf: str = ""):
    """Prompt für die LLM-Klassifizierung, inkl. Angebote-Kontext und Lernbeispiele."""
    text_snippet = (text or "")[:2000]

    angebote_block = ""
    if angebote_kontext:
        angebote_block = f"""
⚠️  OFFENE ANGEBOTE ZUM ABSENDER (alle älter als diese Mail):
{angebote_kontext}
→ PFLICHT: Lies den Mailtext sorgfältig — nur wenn der INHALT auf ein Angebot, Auftrag,
  Preis, Projekt oder eine Zusammenarbeit Bezug nimmt: Kategorie = "Angebotsrueckmeldung".
  Reine Danke-Mails oder unrelated Themen → andere passende Kategorie wählen.
→ Wenn Kategorie="Angebotsrueckmeldung": Setze auch angebot_aktion UND angebot_nummer!
  angebot_aktion: "angenommen" wenn Kunde Projekt/Auftrag bestätigt/annimmt
                  "abgelehnt" wenn Kunde ablehnt, absagt, kein Interesse
                  "rueckfrage" wenn Rückfragen, Änderungswünsche, Verhandlung
"""

    corrections_block = ""
    if correction_beispiele:
        corrections_block = f"""
LERNBEISPIELE aus vergangenen Korrekturen (Kais Feedback — bitte beachten!):
{correction_beispiele}
"""

    wissen_block = ""
    if kira_wissen:
        wissen_block = f"""
WISSEN (von Kira gelernte Erkenntnisse zur Klassifizierung):
{kira_wissen}
"""

    profil_block = ""
    if kunden_profil:
        profil_block = f"\n{kunden_profil}\n"

    verlauf_block = ""
    if mail_verlauf:
        verlauf_block = f"""
BISHERIGER MAIL-VERLAUF MIT DIESEM ABSENDER (älteste zuerst):
{mail_verlauf}
"""

    return f"""Klassifiziere diese E-Mail für rauMKult® Sichtbeton (Betonkosmetik-Fachbetrieb).
{angebote_block}{corrections_block}{wissen_block}{profil_block}{verlauf_block}
MAIL-DATEN:
- Konto: {konto}
- Absender: {absender}
- Betreff: {betreff}
- Ordner: {folder}
- Text (Auszug): {text_snippet}

KATEGORIEN (wähle GENAU eine):
1. "Antwort erforderlich" — Kunde/Partner erwartet eine Antwort, offene Fragen
2. "Neue Lead-Anfrage" — Erstanfrage von Interessenten (Betonkosmetik, Sichtbeton, Betonretusche etc.)
3. "Angebotsrueckmeldung" — Reaktion auf ein gesendetes Angebot (Zusage, Absage, Rückfragen)
4. "Rechnung / Beleg" — Rechnungen, Belege, Zahlungsbestätigungen, Mahnungen
5. "Shop / System" — Shop-Bestellungen, Systembenachrichtigungen
6. "Newsletter / Werbung" — Newsletter, Werbung, Marketing-Mails
7. "Zur Kenntnis" — Informativ, kein Handlungsbedarf
8. "Abgeschlossen" — Bereits erledigt (Danke-Mails, Bestätigungen ohne Frage)
9. "Ignorieren" — Spam, irrelevante Systemmails

REGELN:
- rauMKult macht Betonkosmetik: Sichtbeton, Betonretusche, Betonbeschichtung, Mikrozement
- Erstanfragen mit konkretem Projekt → Neue Lead-Anfrage
- Re:/AW: mit Bezug auf Angebote → Angebotsrueckmeldung
- Mails von bekanntem Angebots-Kunden (auch anderer Account!) → Angebotsrueckmeldung
- Bei Unsicherheit: lieber "Antwort erforderlich" als "Ignorieren"

Antworte NUR als JSON:
{{
  "kategorie": "...",
  "absender_rolle": "Interessent / Lead" | "Bestandskunde" | "Rechnung / Beleg" | "Newsletter / Werbung" | "Shop" | "System" | "Intern",
  "zusammenfassung": "1 Satz was die Mail will",
  "antwort_noetig": true/false,
  "empfohlene_aktion": "Was Kai tun sollte",
  "kategorie_grund": "Warum diese Kategorie",
  "prioritaet": "hoch" | "mittel" | "niedrig",
  "konfidenz": "hoch" | "mittel" | "niedrig",
  "mit_termin": true/false,
  "manuelle_pruefung": true/false,
  "beantwortet": true/false,
  "organisation": {{"termin": "...", "rueckruf": true, "frist": "..."}} oder null,
  "angebot_aktion": "angenommen" | "abgelehnt" | "rueckfrage" | null,
  "angebot_nummer": "ANF-2026-001" | null
}}

mit_termin=true wenn Mail konkretes Datum, Besichtigungstermin oder Terminvereinbarung enthält.
manuelle_pruefung=true wenn Kira unsicher ist oder der Fall ungewöhnlich komplex ist.
beantwortet=true wenn diese Mail eine Antwort AUF eine vorangegangene eigene Mail ist (Re:/AW: + Inhalts-Bezug)."""


def _parse_llm_response(text):
    """Extrahiert JSON aus LLM-Antwort."""
    # Versuche JSON-Block zu finden
    m = re.search(r'\{[\s\S]*\}', text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None

    # Validierung
    kat = data.get("kategorie", "")
    if kat not in KATEGORIEN:
        # Fuzzy-Match
        for k in KATEGORIEN:
            if k.lower() in kat.lower() or kat.lower() in k.lower():
                data["kategorie"] = k
                break
        else:
            return None

    prio = data.get("prioritaet", "mittel")
    if prio not in PRIORITAETEN:
        data["prioritaet"] = "mittel"

    konfidenz = data.get("konfidenz", "mittel")
    if konfidenz not in ("hoch", "mittel", "niedrig"):
        data["konfidenz"] = "mittel"
    else:
        data["konfidenz"] = konfidenz

    # Geschaeft-Daten aus Text extrahieren (Regex, schnell + zuverlässig)
    data.setdefault("geschaeft", None)

    return data


def _get_angebote_kontext(absender: str, text: str, mail_datum: str = "") -> str:
    """
    Prüft ob offene Angebote zum Absender existieren.
    Drei Ebenen: direkte E-Mail → Firmen-Domain → Kundenname im Text.
    Filtert Angebote die NACH dem Maildatum erstellt wurden (zeitliche Kausalität).
    """
    try:
        email = _resolve_alias(extract_email(absender).lower())
        domain = email.split("@")[1] if "@" in email else ""
        # angebote liegt in tasks.db (nicht kunden.db)
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        treffer = []

        # Datum-Guard: nur Angebote die VOR oder AM TAG der Mail erstellt wurden
        datum_filter = ""
        datum_param  = []
        if mail_datum:
            datum_kurz = str(mail_datum)[:10]
            datum_filter = " AND (erstellt_am IS NULL OR erstellt_am <= ?)"
            datum_param  = [datum_kurz]

        # 1. Direkte E-Mail-Übereinstimmung
        rows = db.execute(
            "SELECT a_nummer, kunde_name, status, erstellt_am, betrag_geschaetzt FROM angebote "
            f"WHERE status='offen' AND LOWER(kunde_email)=?{datum_filter}",
            [email] + datum_param
        ).fetchall()
        for r in rows:
            tage = ""
            if r['erstellt_am'] and mail_datum:
                try:
                    from datetime import datetime as _dt
                    diff = (_dt.strptime(str(mail_datum)[:10], "%Y-%m-%d")
                            - _dt.strptime(str(r['erstellt_am'])[:10], "%Y-%m-%d")).days
                    tage = f", {diff} Tage vor Mail"
                except: pass
            treffer.append(
                f"Angebot {r['a_nummer']} an {r['kunde_name']} "
                f"(Datum: {(r['erstellt_am'] or '')[:10]}{tage}, ca. {r['betrag_geschaetzt']}€) "
                f"→ DIREKTE E-MAIL-ÜBEREINSTIMMUNG"
            )

        # 2. Domain-Match (anderer Account, gleiche Firma)
        if not treffer and domain and domain not in _GENERIC_DOMAINS:
            rows2 = db.execute(
                "SELECT a_nummer, kunde_name, status, erstellt_am FROM angebote "
                f"WHERE status='offen' AND LOWER(kunde_email) LIKE ?{datum_filter}",
                [f"%@{domain}"] + datum_param
            ).fetchall()
            for r in rows2:
                treffer.append(
                    f"Angebot {r['a_nummer']} an {r['kunde_name']} "
                    f"(Datum: {(r['erstellt_am'] or '')[:10]}) "
                    f"→ GLEICHE FIRMEN-DOMAIN, anderer Account"
                )

        # 3. Kundenname im Mailtext
        if not treffer:
            kandidaten = db.execute(
                "SELECT a_nummer, kunde_name, erstellt_am FROM angebote "
                f"WHERE status='offen' AND kunde_name IS NOT NULL{datum_filter}",
                datum_param
            ).fetchall()
            text_lower = (text or "")[:3000].lower()
            for r in kandidaten:
                name = (r['kunde_name'] or "").strip()
                if len(name) >= 5 and name.lower() in text_lower:
                    treffer.append(
                        f"Angebot {r['a_nummer']} an {r['kunde_name']} "
                        f"(Datum: {(r['erstellt_am'] or '')[:10]}) "
                        f"→ KUNDENNAME IM MAILTEXT gefunden"
                    )

        db.close()
        return "\n".join(f"  • {t}" for t in treffer[:3])
    except Exception:
        return ""


def _resolve_alias(email: str) -> str:
    """Löst bekannte E-Mail-Aliase auf die Haupt-Adresse auf."""
    if not email:
        return email
    try:
        db = sqlite3.connect(str(TASKS_DB))
        row = db.execute(
            "SELECT haupt_email FROM kunden_aliases WHERE LOWER(alias_email)=?",
            (email.lower(),)
        ).fetchone()
        db.close()
        if row:
            return row[0]
    except: pass
    return email


def _get_kunden_profil(email: str) -> str:
    """
    Erstellt ein kurzes Kundenprofil aus bisherigen Tasks und Interaktionen.
    Gibt einen Prompt-Block zurück, der dem LLM die Kundenhistorie zeigt.
    """
    if not email:
        return ""
    email = _resolve_alias(email.lower().strip())
    try:
        profil_parts = []

        # Aus tasks.db: Anzahl früherer Tasks, letztes Datum, letzte Kategorie
        tdb = sqlite3.connect(str(TASKS_DB))
        tdb.row_factory = sqlite3.Row
        task_rows = tdb.execute(
            "SELECT kategorie, datum_mail FROM tasks WHERE LOWER(kunden_email)=? ORDER BY datum_mail DESC LIMIT 5",
            (email,)
        ).fetchall()
        tdb.close()
        if task_rows:
            n = len(task_rows)
            letztes = (task_rows[0]["datum_mail"] or "")[:10]
            letzte_kat = task_rows[0]["kategorie"] or ""
            profil_parts.append(
                f"{n} frühere{'r' if n==1 else ''} Kontakt{'e' if n>1 else ''}, letzter: {letztes}, Kategorie: {letzte_kat}"
                f" → wahrscheinlich {'Bestandskunde' if n >= 2 else 'Interessent'}"
            )

        # Aus kunden.db: Interaktionen
        kdb = sqlite3.connect(str(KUNDEN_DB))
        kdb.row_factory = sqlite3.Row
        try:
            inter = kdb.execute(
                "SELECT COUNT(*) c FROM interaktionen WHERE LOWER(kunden_email)=?",
                (email,)
            ).fetchone()
            if inter and inter["c"] > 0:
                profil_parts.append(f"{inter['c']} gespeicherte Interaktionen in kunden.db")
        except: pass
        kdb.close()

        if not profil_parts:
            return ""
        return "KUNDENPROFIL: " + " | ".join(profil_parts)
    except Exception:
        return ""


def _get_mail_verlauf_kontext(absender_email: str, max_mails: int = 8) -> str:
    """
    Lädt die letzten Mails von/an diesen Absender aus mail_index.db.
    Gibt dem LLM vollständigen Kontext über bisherige Kommunikation.
    Zeigt sowohl empfangene als auch gesendete Mails (Konversation).
    """
    if not absender_email or not MAIL_INDEX_DB.exists():
        return ""
    try:
        email_clean = absender_email.lower().strip()
        domain = email_clean.split("@")[1] if "@" in email_clean else ""
        conn = sqlite3.connect(str(MAIL_INDEX_DB))
        conn.row_factory = sqlite3.Row

        # Mails vom Absender (empfangen)
        rows_von = conn.execute("""
            SELECT betreff, datum_iso, datum, folder, text_plain, absender_short, absender
            FROM mails
            WHERE LOWER(absender) LIKE ?
            ORDER BY datum_iso DESC LIMIT ?
        """, (f"%{email_clean}%", max_mails)).fetchall()

        # Gesendete Mails an diesen Kunden (Antworten, Angebote)
        rows_an = conn.execute("""
            SELECT betreff, datum_iso, datum, folder, text_plain, absender_short, absender
            FROM mails
            WHERE (folder LIKE '%Gesendete%' OR folder LIKE '%Sent%')
              AND LOWER(an) LIKE ?
            ORDER BY datum_iso DESC LIMIT 5
        """, (f"%{email_clean}%",)).fetchall()

        # Falls wenig direkte Treffer: Domain-Suche
        if len(rows_von) < 2 and domain and domain not in {
            "gmail.com","web.de","gmx.de","gmx.net","yahoo.com","hotmail.com","outlook.com"
        }:
            rows_domain = conn.execute("""
                SELECT betreff, datum_iso, datum, folder, text_plain, absender_short, absender
                FROM mails
                WHERE LOWER(absender) LIKE ?
                  AND LOWER(absender) NOT LIKE ?
                ORDER BY datum_iso DESC LIMIT 5
            """, (f"%@{domain}%", f"%{email_clean}%")).fetchall()
            rows_von = list(rows_von) + list(rows_domain)

        conn.close()

        if not rows_von and not rows_an:
            return ""

        # Alle Mails nach Datum sortieren (kombinierter Verlauf)
        all_mails = []
        for r in rows_von:
            all_mails.append(("→ Empfangen", r))
        for r in rows_an:
            all_mails.append(("← Gesendet", r))

        all_mails.sort(key=lambda x: (x[1]["datum_iso"] or x[1]["datum"] or ""), reverse=False)
        # Nur die letzten max_mails zeigen
        all_mails = all_mails[-max_mails:]

        lines = []
        for richtung, r in all_mails:
            dt = (r["datum_iso"] or r["datum"] or "")[:16]
            ab = r["absender_short"] or r["absender"] or "?"
            betr = (r["betreff"] or "")[:80]
            preview = (r["text_plain"] or "")[:200].replace("\n", " ")
            lines.append(f"  {dt} {richtung}: {betr}")
            if preview:
                lines.append(f"    ↳ {preview}")

        return "\n".join(lines)
    except Exception:
        return ""


def _get_kira_wissen(limit: int = 10) -> str:
    """
    Lädt Kiras gelernte Erkenntnisse aus wissen_regeln, die für die
    Mail-Klassifizierung relevant sind (Kategorien: klassifizierung, vorschlag, gelernt).
    """
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        rows = db.execute("""
            SELECT kategorie, titel, inhalt, erstellt_am
            FROM wissen_regeln
            WHERE status = 'aktiv'
              AND kategorie IN ('klassifizierung','vorschlag','gelernt','kira')
            ORDER BY erstellt_am DESC LIMIT ?
        """, (limit,)).fetchall()
        db.close()
        if not rows:
            return ""
        lines = []
        for r in rows:
            titel  = (r["titel"] or "")[:60]
            inhalt = (r["inhalt"] or "")[:120]
            lines.append(f"  • {titel}: {inhalt}")
        return "\n".join(lines)
    except Exception:
        return ""


def _get_correction_beispiele(limit: int = 12) -> str:
    """
    Lädt die letzten Korrekturen als Few-Shot-Lernbeispiele für den LLM-Prompt.
    So lernt der Classifier aus Kais Korrekturen.
    """
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        rows = db.execute("""
            SELECT c.alter_typ, c.neuer_typ, c.notiz,
                   t.betreff, t.zusammenfassung, t.absender_rolle
            FROM corrections c
            LEFT JOIN tasks t ON t.id = c.task_id
            WHERE c.alter_typ != c.neuer_typ
            ORDER BY c.erstellt_am DESC LIMIT ?
        """, (limit,)).fetchall()
        db.close()
        if not rows:
            return ""
        lines = []
        for r in rows:
            betreff = (r["betreff"] or "")[:60]
            zusamm  = (r["zusammenfassung"] or "")[:60]
            kontext = betreff or zusamm
            notiz   = f' (Grund: {r["notiz"]})' if r["notiz"] else ""
            lines.append(
                f'  • "{kontext}" → war: {r["alter_typ"]} → richtig: {r["neuer_typ"]}{notiz}'
            )
        return "\n".join(lines)
    except Exception:
        return ""


def classify_mail_llm(konto: str, absender: str, betreff: str, text: str,
                      anhaenge: list = None, folder: str = "",
                      is_sent: bool = False, mail_datum: str = "",
                      kanal: str = "email") -> dict:
    """
    kanal: "email" | "whatsapp" | "instagram" | "sms" | ...
    Alle Kanäle durchlaufen dieselbe LLM-Pipeline.
    """
    """
    LLM-gestützte Mail-Klassifizierung mit Fast-Path und Fallback.
    Gleiche Signatur und Return-Format wie mail_classifier.classify_mail().
    """

    # ── FAST-PATH 1: Gesendete Mails (kein LLM nötig) ──
    if is_sent or "Gesendete" in folder or "Sent" in folder:
        return _classify_rule_based(konto, absender, betreff, text, anhaenge, folder, is_sent)

    # ── FAST-PATH 2: System-Sender (300+ Domains, deterministisch) ──
    if is_system_sender(absender):
        return _classify_rule_based(konto, absender, betreff, text, anhaenge, folder, is_sent)

    # ── FAST-PATH 3: Newsletter — nur wenn eindeutig Consumer/generisch ──
    # B2B-Newsletters (Lieferanten, Fachverbände, Materiallieferanten) können relevant sein
    if is_newsletter(absender, betreff, text):
        sender_email = extract_email(absender).lower()
        sender_domain = sender_email.split('@')[-1] if '@' in sender_email else ''
        # Generische Massen-Newsletter-Domains → Regelbasiert (kein LLM nötig)
        _generic_newsletter_domains = {
            "mailchimp.com", "klaviyo.com", "sendinblue.com", "mailjet.com",
            "constantcontact.com", "newsletter2go.com", "cleverreach.com",
            "emarsys.com", "salesmanago.com", "hubspot.com", "marketo.com",
            "pardot.com", "campaignmonitor.com", "drip.com", "convertkit.com",
            "aweber.com", "getresponse.com",
        }
        # Prüfe ob Domain generisch klingt (kein Firmenname erkennbar)
        is_generic_nl_domain = (
            sender_domain in _generic_newsletter_domains
            or sender_domain in _GENERIC_DOMAINS
            or any(x in sender_domain for x in ("newsletter","noreply","no-reply","marketing","promo"))
        )
        if is_generic_nl_domain:
            return _classify_rule_based(konto, absender, betreff, text, anhaenge, folder, is_sent)
        # B2B-Domain → LLM entscheiden lassen (könnte Fachinfo sein)

    # ── FAST-PATH 4: Ausschluss-Betreffs ──
    if is_exclude_subject(betreff):
        return _classify_rule_based(konto, absender, betreff, text, anhaenge, folder, is_sent)

    # ── LLM-Klassifizierung ──
    try:
        from kira_llm import classify_direct, get_providers

        # Prüfe ob überhaupt ein Provider verfügbar
        providers = get_providers()
        if not providers:
            raise RuntimeError("Kein Provider konfiguriert")

        # Kontext-Anreicherung: Angebote-Abgleich + Korrekturen + Kira-Wissen + Kundenprofil + Mail-Verlauf
        kunden_email_raw     = extract_email(absender)
        angebote_kontext     = _get_angebote_kontext(absender, text, mail_datum=mail_datum)
        correction_beispiele = _get_correction_beispiele()
        kira_wissen          = _get_kira_wissen()
        kunden_profil        = _get_kunden_profil(kunden_email_raw)
        mail_verlauf         = _get_mail_verlauf_kontext(kunden_email_raw)

        prompt = _build_classification_prompt(
            konto, absender, betreff, text, folder, is_sent,
            angebote_kontext=angebote_kontext,
            correction_beispiele=correction_beispiele,
            kira_wissen=kira_wissen,
            kunden_profil=kunden_profil,
            mail_verlauf=mail_verlauf,
        )

        # Leichtgewichtiger Direkt-Aufruf (Haiku, 512 max_tokens, kein System-Prompt)
        result = classify_direct(prompt, max_tokens=512)

        if result.get("error"):
            raise RuntimeError(result["error"])

        antwort = result.get("antwort", "")
        parsed = _parse_llm_response(antwort)

        if parsed:
            # Geschaeft-Daten ergänzen (Regex ist hier zuverlässiger als LLM)
            geschaeft = None
            if parsed["kategorie"] == "Rechnung / Beleg":
                geschaeft = _extr_gesc(betreff, text, "rechnung")
            organisation = parsed.get("organisation")
            if isinstance(organisation, dict) and not any(organisation.values()):
                organisation = None

            angebot_aktion = parsed.get("angebot_aktion") or None
            angebot_nummer = parsed.get("angebot_nummer") or None
            # Validierung
            if angebot_aktion not in ("angenommen", "abgelehnt", "rueckfrage", None):
                angebot_aktion = None

            return {
                "kategorie":          parsed["kategorie"],
                "absender_rolle":     parsed.get("absender_rolle", ""),
                "zusammenfassung":    parsed.get("zusammenfassung", betreff[:100]),
                "antwort_noetig":     bool(parsed.get("antwort_noetig", False)),
                "empfohlene_aktion":  parsed.get("empfohlene_aktion", ""),
                "kategorie_grund":    parsed.get("kategorie_grund", "LLM-klassifiziert"),
                "prioritaet":         parsed.get("prioritaet", "mittel"),
                "konfidenz":          parsed.get("konfidenz", "mittel"),
                "mit_termin":         1 if parsed.get("mit_termin") else 0,
                "manuelle_pruefung":  1 if parsed.get("manuelle_pruefung") else 0,
                "beantwortet":        1 if parsed.get("beantwortet") else 0,
                "organisation":       organisation,
                "geschaeft":          geschaeft,
                "angebot_aktion":     angebot_aktion,
                "angebot_nummer":     angebot_nummer,
            }

    except Exception as e:
        # LLM fehlgeschlagen — Fallback
        pass

    # ── FALLBACK: Regelbasierte Klassifizierung ──
    return _classify_rule_based(konto, absender, betreff, text, anhaenge, folder, is_sent)


# Re-Export für Kompatibilität
def classify_mail(konto: str, absender: str, betreff: str, text: str,
                  anhaenge: list = None, folder: str = "",
                  is_sent: bool = False, mail_datum: str = "",
                  kanal: str = "email") -> dict:
    """Alias — Drop-in-Replacement, bereit für Multi-Kanal (kanal='whatsapp' etc.)."""
    return classify_mail_llm(konto, absender, betreff, text, anhaenge, folder,
                             is_sent, mail_datum=mail_datum, kanal=kanal)
