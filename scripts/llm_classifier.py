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
                                  angebote_kontext: str = "", correction_beispiele: str = ""):
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
"""

    corrections_block = ""
    if correction_beispiele:
        corrections_block = f"""
LERNBEISPIELE aus vergangenen Korrekturen (Kais Feedback — bitte beachten!):
{correction_beispiele}
"""

    return f"""Klassifiziere diese E-Mail für rauMKult® Sichtbeton (Betonkosmetik-Fachbetrieb).
{angebote_block}{corrections_block}
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
  "organisation": {{"termin": "...", "rueckruf": true, "frist": "..."}} oder null
}}"""


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
        email = extract_email(absender).lower()
        domain = email.split("@")[1] if "@" in email else ""
        db = sqlite3.connect(str(KUNDEN_DB))
        db.row_factory = sqlite3.Row
        treffer = []

        # Datum-Guard: nur Angebote die VOR oder AM TAG der Mail erstellt wurden
        # Wenn kein Datum: kein Filter (sicher fallback)
        datum_filter = ""
        datum_param  = []
        if mail_datum:
            datum_kurz = str(mail_datum)[:10]
            datum_filter = " AND (erstellt IS NULL OR erstellt <= ?)"
            datum_param  = [datum_kurz]

        # 1. Direkte E-Mail-Übereinstimmung
        rows = db.execute(
            "SELECT angebots_nr, kunde, status, erstellt, betrag FROM angebote "
            f"WHERE status='offen' AND LOWER(kunde_email)=?{datum_filter}",
            [email] + datum_param
        ).fetchall()
        for r in rows:
            tage = ""
            if r['erstellt'] and mail_datum:
                try:
                    from datetime import datetime as _dt
                    diff = (_dt.strptime(str(mail_datum)[:10], "%Y-%m-%d")
                            - _dt.strptime(str(r['erstellt'])[:10], "%Y-%m-%d")).days
                    tage = f", {diff} Tage vor Mail"
                except: pass
            treffer.append(
                f"Angebot {r['angebots_nr']} an {r['kunde']} "
                f"(Angebotsdatum: {(r['erstellt'] or '')[:10]}{tage}, Betrag: {r['betrag']}€) "
                f"→ DIREKTE E-MAIL-ÜBEREINSTIMMUNG"
            )

        # 2. Domain-Match (anderer Account, gleiche Firma)
        if not treffer and domain and domain not in _GENERIC_DOMAINS:
            rows2 = db.execute(
                "SELECT angebots_nr, kunde, status, erstellt FROM angebote "
                f"WHERE status='offen' AND LOWER(kunde_email) LIKE ?{datum_filter}",
                [f"%@{domain}"] + datum_param
            ).fetchall()
            for r in rows2:
                treffer.append(
                    f"Angebot {r['angebots_nr']} an {r['kunde']} "
                    f"(Angebotsdatum: {(r['erstellt'] or '')[:10]}) "
                    f"→ GLEICHE FIRMEN-DOMAIN, anderer Account"
                )

        # 3. Kundenname im Mailtext (Firmenname aus Angeboten in Text suchen)
        if not treffer:
            kandidaten = db.execute(
                "SELECT angebots_nr, kunde, erstellt FROM angebote "
                f"WHERE status='offen' AND kunde IS NOT NULL{datum_filter}",
                datum_param
            ).fetchall()
            text_lower = (text or "")[:3000].lower()
            for r in kandidaten:
                name = (r['kunde'] or "").strip()
                if len(name) >= 5 and name.lower() in text_lower:
                    treffer.append(
                        f"Angebot {r['angebots_nr']} an {r['kunde']} "
                        f"(Angebotsdatum: {(r['erstellt'] or '')[:10]}) "
                        f"→ KUNDENNAME IM MAILTEXT gefunden"
                    )

        db.close()
        return "\n".join(f"  • {t}" for t in treffer[:3])
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

    # ── FAST-PATH 3: Klare Newsletter ──
    if is_newsletter(absender, betreff, text):
        return _classify_rule_based(konto, absender, betreff, text, anhaenge, folder, is_sent)

    # ── FAST-PATH 4: Ausschluss-Betreffs ──
    if is_exclude_subject(betreff):
        return _classify_rule_based(konto, absender, betreff, text, anhaenge, folder, is_sent)

    # ── LLM-Klassifizierung ──
    try:
        from kira_llm import chat as kira_chat, get_providers

        # Prüfe ob überhaupt ein Provider verfügbar
        providers = get_providers()
        if not providers:
            raise RuntimeError("Kein Provider konfiguriert")

        # Kontext-Anreicherung: Angebote-Abgleich + Korrekturen als Lernbeispiele
        angebote_kontext     = _get_angebote_kontext(absender, text, mail_datum=mail_datum)
        correction_beispiele = _get_correction_beispiele()

        prompt = _build_classification_prompt(
            konto, absender, betreff, text, folder, is_sent,
            angebote_kontext=angebote_kontext,
            correction_beispiele=correction_beispiele,
        )

        # Spezieller Chat ohne Tool-Nutzung, kurze Antwort
        result = kira_chat(
            user_message=f"[SYSTEM: Mail-Klassifizierung — antworte NUR als JSON]\n\n{prompt}",
            session_id=None
        )

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

            return {
                "kategorie":        parsed["kategorie"],
                "absender_rolle":   parsed.get("absender_rolle", ""),
                "zusammenfassung":  parsed.get("zusammenfassung", betreff[:100]),
                "antwort_noetig":   bool(parsed.get("antwort_noetig", False)),
                "empfohlene_aktion":parsed.get("empfohlene_aktion", ""),
                "kategorie_grund":  parsed.get("kategorie_grund", "LLM-klassifiziert"),
                "prioritaet":       parsed.get("prioritaet", "mittel"),
                "organisation":     organisation,
                "geschaeft":        geschaeft,
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
