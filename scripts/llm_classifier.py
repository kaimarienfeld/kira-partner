#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llm_classifier.py — LLM-gestützte Mail-Klassifizierung für rauMKult®.
Strategie: Fast-Path (regelbasiert) → LLM → Fallback (regelbasiert).
Drop-in-Replacement für mail_classifier.classify_mail().
"""
import base64, json, math, re, sqlite3, tempfile, zipfile
from datetime import datetime
from pathlib import Path

# Bestehender Klassifizierer als Fallback
from mail_classifier import (
    classify_mail as _classify_rule_based,
    is_system_sender, is_newsletter, is_exclude_subject,
    extract_email, kategorie_to_task_typ,
    KATEGORIE_ZU_TASK_TYP,
    _extr_org, _extr_gesc
)
from task_manager import get_active_profile

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
                                  mail_verlauf: str = "", anhaenge: list = None,
                                  lexware_kontext: str = "",
                                  anhang_texte: str = ""):
    """Prompt für die LLM-Klassifizierung, inkl. Angebote-Kontext und Lernbeispiele."""
    text_snippet = (text or "")[:6000]

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

    lexware_block = ""
    if lexware_kontext:
        lexware_block = f"""
{lexware_kontext}
→ Nutze diese Daten: Offene Rechnungen/Angebote beeinflussen die Priorität.
  Bekannter Lexware-Kunde → wahrscheinlich Bestandskunde, nicht Spam.
  Überfällige Rechnungen + Mail vom Kunden → könnte Zahlungsbezug haben.
"""

    # ── Profil-basierte Benutzer-Identität laden ──
    profil = get_active_profile()
    team = profil.get("team", [])
    hauptbenutzer = team[0] if team else {}
    benutzer_name = hauptbenutzer.get("name", "")
    benutzer_rolle = hauptbenutzer.get("rolle", "")
    benutzer_anreden = ", ".join(hauptbenutzer.get("anrede_varianten", []))
    benutzer_konten = ", ".join(hauptbenutzer.get("email_konten", []))
    firma_name = profil.get("firma_name", "")
    firma_branche = profil.get("firma_branche", "")
    firma_beschreibung = profil.get("firma_beschreibung", "")

    # Team-Mitglieder-Block (alle Namen + Anreden)
    team_block = ""
    if len(team) > 1:
        team_lines = []
        for tm in team[1:]:
            tm_anreden = ", ".join(tm.get("anrede_varianten", []))
            team_lines.append(f"  - {tm.get('name', '')} ({tm.get('rolle', '')}){f' — Anreden: {tm_anreden}' if tm_anreden else ''}")
        team_block = "\nWeitere Team-Mitglieder:\n" + "\n".join(team_lines)

    return f"""Klassifiziere diese E-Mail für {benutzer_name or 'den Benutzer'}{f' ({benutzer_rolle})' if benutzer_rolle else ''} bei {firma_name}{f' ({firma_branche})' if firma_branche else ''}.
{firma_beschreibung}

BENUTZER-IDENTITÄT:
- E-Mail-Konten des Benutzers: {benutzer_konten}
{f'- Bekannte Anreden: {benutzer_anreden}' if benutzer_anreden else ''}{team_block}
Wenn die E-Mail den Benutzer persönlich anspricht (z.B. {benutzer_anreden or benutzer_name}), ist sie an ihn gerichtet — das ist KEINE anonyme Werbung.
Prüfe genau ob sie geschäftsrelevant ist, bevor du "Ignorieren" vergibst.

{angebote_block}{corrections_block}{wissen_block}{profil_block}{verlauf_block}{lexware_block}
MAIL-DATEN:
- Konto: {konto}
- Absender: {absender}
- Betreff: {betreff}
- Ordner: {folder}
- Anhaenge: {', '.join(str(a) for a in (anhaenge or [])) or 'Keine'}
{anhang_texte}
- Text (Auszug): {text_snippet}

WICHTIG — Lies die E-Mail KOMPLETT und gründlich. Achte besonders auf:
- Termine, Fristen, Fälligkeiten (auch beiläufig erwähnt, z.B. "nächste Rate am 4.5.")
- Ob jemand auf eine Antwort wartet
- Beträge, Raten, Zahlungsziele
- Kontext: Eigene Zahlung? Kundenzahlung? Dienstleister?
- Ob der Benutzer persönlich angesprochen wird

Wenn im Mail-Verlauf gesendete Mails des Benutzers stehen (←):
- Hat der Benutzer etwas zugesagt? ("Ich melde mich", "schicke Ihnen", "komme auf Sie zurück")
- Wartet der Gesprächspartner seit >3 Tagen auf Antwort?
→ Trage in "vorgeschlagene_aktionen" ein (typ: "nachfass").

KATEGORIEN (wähle GENAU eine):
1. "Antwort erforderlich" — Kunde/Partner erwartet eine Antwort, offene Fragen
2. "Neue Lead-Anfrage" — Erstanfrage von Interessenten
3. "Angebotsrueckmeldung" — Reaktion auf ein gesendetes Angebot (Zusage, Absage, Rückfragen)
4. "Rechnung / Beleg" — Rechnungen, Belege, Zahlungsbestätigungen, Mahnungen
5. "Shop / System" — Shop-Bestellungen, Systembenachrichtigungen
6. "Newsletter / Werbung" — Newsletter, Werbung, Marketing-Mails
7. "Zur Kenntnis" — Informativ, kein Handlungsbedarf
8. "Abgeschlossen" — Bereits erledigt (Danke-Mails, Bestätigungen ohne Frage)
9. "Ignorieren" — Spam, irrelevante Systemmails

REGELN:
- {firma_branche or 'Branche des Unternehmens beachten'}
- Erstanfragen mit konkretem Projekt → Neue Lead-Anfrage
- Re:/AW: mit Bezug auf Angebote → Angebotsrueckmeldung
- Mails von bekanntem Angebots-Kunden (auch anderer Account!) → Angebotsrueckmeldung
- Bei Unsicherheit: lieber "Antwort erforderlich" als "Ignorieren"
- ANHAENGE BERUECKSICHTIGEN: PDF/ZIP/Bild-Anhaenge koennen Rechnungen, Angebote, Fotos, Vertraege enthalten.

ROUTING-ENTSCHEIDUNG (PFLICHT — vor der Klassifizierung überlegen!):
Muss der Benutzer PERSÖNLICH handeln? Oder kann das System die Mail automatisch verarbeiten?
- Eingangsrechnungen, Belege, Zahlungsbestätigungen → KEIN Task, sondern Buchhaltung
- System-Mails, Login-Infos, Bestellbestätigungen → KEIN Task, archivieren
- Newsletter, Werbung, Marketing → KEIN Task, archivieren
- Angebotsabsagen → KEIN Task, sondern Kira-Vorschlag
- Nur wenn der Benutzer PERSÖNLICH antworten/entscheiden/handeln muss → Task

Antworte NUR als JSON:
{{
  "kategorie": "...",
  "absender_rolle": "Interessent / Lead" | "Bestandskunde" | "Rechnung / Beleg" | "Newsletter / Werbung" | "Shop" | "System" | "Intern",
  "zusammenfassung": "1 Satz was die Mail will",
  "antwort_noetig": true/false,
  "empfohlene_aktion": "Was der Benutzer tun sollte",
  "kategorie_grund": "Warum diese Kategorie",
  "prioritaet": "hoch" | "mittel" | "niedrig",
  "konfidenz": "hoch" | "mittel" | "niedrig",
  "erfordert_handlung": true/false,
  "routing": "task" | "buchhaltung" | "feed" | "kira_vorschlag" | "archivieren",
  "mit_termin": true/false,
  "manuelle_pruefung": true/false,
  "beantwortet": true/false,
  "organisation": {{"termin": "...", "rueckruf": true, "frist": "..."}} oder null,
  "angebot_aktion": "angenommen" | "abgelehnt" | "rueckfrage" | null,
  "angebot_nummer": "ANF-2026-001" | null,
  "vorgeschlagene_aktionen": [
    {{"typ": "erinnerung|nachfass|termin", "text": "Kurzbeschreibung", "datum": "YYYY-MM-DD oder null", "prioritaet": "hoch|mittel|niedrig"}}
  ],
  "erkannte_termine": [
    {{"text": "Beschreibung", "datum": "YYYY-MM-DD", "typ": "zahlung|frist|treffen|deadline"}}
  ],
  "mail_zusammenhang": "1-Satz-Kontext der Mail im Geschäftszusammenhang"
}}

erfordert_handlung=true NUR wenn der Benutzer persönlich etwas tun muss (antworten, entscheiden, unterschreiben).
routing: "task" = echte Aufgabe, "buchhaltung" = Rechnung/Beleg zur Prüfung, "feed" = Dashboard-Info, "kira_vorschlag" = Kira bereitet Aktion vor, "archivieren" = nur ablegen.
mit_termin=true wenn Mail konkretes Datum, Besichtigungstermin oder Terminvereinbarung enthält.

vorgeschlagene_aktionen: Aktionen die der Benutzer durchführen sollte. Auch bei "Ignorieren"/"Zur Kenntnis": wenn Termine, Fristen oder Beträge den Benutzer betreffen → hier eintragen!
erkannte_termine: Alle Termine, Fristen, Fälligkeiten aus der Mail (auch beiläufig erwähnte).
mail_zusammenhang: Kurze Einordnung der Mail (z.B. "Rückzahlung Darlehen — nächste Rate fällig")."""


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

    # Routing-Felder validieren
    VALID_ROUTING = ("task", "buchhaltung", "feed", "kira_vorschlag", "archivieren")
    routing = data.get("routing", "task")
    if routing not in VALID_ROUTING:
        data["routing"] = "task"
    else:
        data["routing"] = routing

    # erfordert_handlung: Default True (sicherer Fallback)
    if "erfordert_handlung" not in data:
        data["erfordert_handlung"] = True
    else:
        data["erfordert_handlung"] = bool(data["erfordert_handlung"])

    # Geschaeft-Daten aus Text extrahieren (Regex, schnell + zuverlässig)
    data.setdefault("geschaeft", None)

    # Neue Felder: Aktionen, Termine, Zusammenhang (Kira Intelligenz-Upgrade)
    data.setdefault("vorgeschlagene_aktionen", [])
    data.setdefault("erkannte_termine", [])
    data.setdefault("mail_zusammenhang", "")

    # Validierung: Listen müssen Listen sein
    if not isinstance(data.get("vorgeschlagene_aktionen"), list):
        data["vorgeschlagene_aktionen"] = []
    if not isinstance(data.get("erkannte_termine"), list):
        data["erkannte_termine"] = []

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


def _get_lexware_kontext(email: str) -> str:
    """Lädt Lexware-Daten (Belege, Kontakt, offene Rechnungen) für eine E-Mail-Adresse."""
    if not email:
        return ""
    email = email.lower().strip()
    try:
        tdb = sqlite3.connect(str(TASKS_DB))
        tdb.row_factory = sqlite3.Row
        parts = []

        # 1. Lexware-Kontakt finden (per E-Mail oder Domain-Match)
        domain = email.split('@')[-1] if '@' in email else ''
        kontakt = tdb.execute(
            "SELECT name, email, lexware_id FROM lexware_kontakte WHERE LOWER(email)=? LIMIT 1",
            (email,)
        ).fetchone()
        if not kontakt and domain:
            kontakt = tdb.execute(
                "SELECT name, email, lexware_id FROM lexware_kontakte WHERE LOWER(email) LIKE ? LIMIT 1",
                (f'%@{domain}',)
            ).fetchone()

        if kontakt:
            kid = kontakt["lexware_id"]
            parts.append(f"Lexware-Kunde: {kontakt['name']} ({kontakt['email']})")

            # 2. Belege für diesen Kontakt
            belege = tdb.execute("""
                SELECT typ, nummer, status, brutto, datum, waehrung
                FROM lexware_belege
                WHERE kontakt_id=?
                ORDER BY datum DESC LIMIT 8
            """, (kid,)).fetchall()

            if belege:
                offene = [b for b in belege if b["status"] in ("open", "overdue", "draft")]
                bezahlt = [b for b in belege if b["status"] in ("paid", "paidoff")]
                rechnungen = [b for b in belege if b["typ"] == "invoice"]
                angebote_lx = [b for b in belege if b["typ"] == "quotation"]

                beleg_info = []
                if offene:
                    summe = sum((b["brutto"] or 0) for b in offene)
                    beleg_info.append(f"{len(offene)} offene Belege ({summe:,.2f} EUR)")
                if bezahlt:
                    beleg_info.append(f"{len(bezahlt)} bezahlt")
                if rechnungen:
                    beleg_info.append(f"{len(rechnungen)} Rechnungen")
                if angebote_lx:
                    acc = [a for a in angebote_lx if a["status"] == "accepted"]
                    beleg_info.append(f"{len(angebote_lx)} Angebote ({len(acc)} angenommen)")

                parts.append("Belege: " + ", ".join(beleg_info))

                # Letzte Belege einzeln (kompakt)
                for b in belege[:4]:
                    st_map = {"open": "offen", "overdue": "überfällig", "paid": "bezahlt",
                              "paidoff": "abgezahlt", "accepted": "angenommen",
                              "rejected": "abgelehnt", "draft": "Entwurf"}
                    st = st_map.get(b["status"], b["status"] or "?")
                    parts.append(f"  {b['typ']:10s} {b['nummer'] or '':15s} {b['brutto'] or 0:>10.2f} EUR  {st:12s}  {(b['datum'] or '')[:10]}")
        else:
            # Kein Lexware-Kontakt gefunden — kurze Info
            # Trotzdem nach Domain suchen in geschaeft-Tabelle
            if domain:
                gesc = tdb.execute(
                    "SELECT COUNT(*) c FROM geschaeft WHERE LOWER(gegenpartei_email) LIKE ?",
                    (f'%@{domain}',)
                ).fetchone()
                if gesc and gesc["c"] > 0:
                    parts.append(f"Geschäftsbeziehung: {gesc['c']} Belege von Domain {domain}")

        tdb.close()
        if not parts:
            return ""
        return "LEXWARE-DATEN:\n" + "\n".join(parts)
    except Exception:
        return ""


# ── Anhang-Text-Extraktion für Klassifizierung ─────────────────────────────

_BILD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}
_BILD_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".tiff": "image/tiff", ".tif": "image/tiff", ".bmp": "image/bmp",
    ".webp": "image/webp",
}

def _ensure_anhang_cache_table():
    """Erstellt anhang_text_cache Tabelle in mail_index.db falls nicht vorhanden."""
    try:
        db = sqlite3.connect(str(MAIL_INDEX_DB))
        db.execute("""CREATE TABLE IF NOT EXISTS anhang_text_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT NOT NULL,
            dateiname TEXT NOT NULL,
            extrahierter_text TEXT,
            ist_bild_ohne_text INTEGER DEFAULT 0,
            bild_base64 TEXT,
            bild_media_type TEXT,
            dateigroesse INTEGER,
            extrahiert_am TEXT,
            UNIQUE(message_id, dateiname)
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_atc_msgid ON anhang_text_cache(message_id)")
        db.commit()
        db.close()
    except Exception:
        pass

_ensure_anhang_cache_table()


def _load_anhang_config() -> dict:
    """Lädt anhang_extraktion Config mit Defaults."""
    try:
        cfg = json.loads((SCRIPTS_DIR / "config.json").read_text("utf-8"))
        return cfg.get("anhang_extraktion", {})
    except Exception:
        return {}


def _extract_attachment_texts(anhaenge: list, anhaenge_pfad: str,
                               message_id: str = "") -> dict:
    """
    Extrahiert Text aus Mail-Anhängen für die LLM-Klassifizierung.
    Nutzt dokument_pipeline.py für PDF/DOCX/OCR. Cached Ergebnisse in DB.
    Bei Bildern ohne OCR-Text → base64-Bild für Vision-Fallback.

    Returns: {"text_block": str, "vision_images": [...], "stats": {...}}
    """
    empty = {"text_block": "", "vision_images": [], "stats": {}}
    cfg = _load_anhang_config()
    if not cfg.get("aktiv", False):
        return empty
    if not anhaenge or not anhaenge_pfad:
        return empty

    att_dir = Path(anhaenge_pfad)
    if not att_dir.exists():
        return empty

    # Lazy import — dokument_pipeline ist im gleichen scripts/ Ordner
    try:
        from dokument_pipeline import extract_text, extract_text_image, is_supported as dp_is_supported
    except ImportError:
        return empty

    max_size = cfg.get("max_dateigroesse_mb", 20) * 1024 * 1024
    max_per = cfg.get("max_text_zeichen_pro_anhang", 3000)
    max_total = cfg.get("max_text_zeichen_gesamt", 8000)
    vision_on = cfg.get("vision_fallback", True)
    vision_max_kb = cfg.get("vision_max_bild_kb", 500) * 1024
    zip_on = cfg.get("zip_entpacken", True)
    zip_max_files = cfg.get("zip_max_dateien", 10)
    zip_max_size = cfg.get("zip_max_groesse_mb", 50) * 1024 * 1024
    ocr_on = cfg.get("ocr_aktiv", True)

    text_parts = []
    vision_images = []
    stats = {"extracted": 0, "skipped": 0, "ocr_failed": 0, "vision": 0}
    total_chars = 0

    # DB-Verbindung für Cache
    try:
        cache_db = sqlite3.connect(str(MAIL_INDEX_DB))
        cache_db.row_factory = sqlite3.Row
    except Exception:
        cache_db = None

    for fname in anhaenge:
        if total_chars >= max_total:
            break
        fname = str(fname).strip()
        if not fname:
            continue

        fp = att_dir / fname
        suffix = Path(fname).suffix.lower()

        # ── Cache prüfen ──
        cached = None
        if cache_db and message_id:
            try:
                cached = cache_db.execute(
                    "SELECT extrahierter_text, ist_bild_ohne_text, bild_base64, bild_media_type "
                    "FROM anhang_text_cache WHERE message_id=? AND dateiname=?",
                    (message_id, fname)
                ).fetchone()
            except Exception:
                pass

        if cached:
            if cached["extrahierter_text"]:
                txt = cached["extrahierter_text"][:max_per]
                text_parts.append(f"\U0001F4CE {fname}:\n  {txt}")
                total_chars += len(txt)
                stats["extracted"] += 1
            elif cached["ist_bild_ohne_text"] and vision_on and cached["bild_base64"]:
                vision_images.append({
                    "data": cached["bild_base64"],
                    "media_type": cached["bild_media_type"] or "image/jpeg",
                    "name": fname,
                })
                text_parts.append(f"\U0001F4CE {fname} (Bild \u2014 wird visuell analysiert)")
                stats["vision"] += 1
            continue

        # ── Datei existiert? ──
        if not fp.exists():
            stats["skipped"] += 1
            continue

        # ── Dateigröße ──
        try:
            fsize = fp.stat().st_size
        except Exception:
            stats["skipped"] += 1
            continue
        if fsize > max_size:
            text_parts.append(f"\U0001F4CE {fname} (\u00fcbersprungen \u2014 {fsize // 1024 // 1024} MB > {max_size // 1024 // 1024} MB)")
            stats["skipped"] += 1
            continue

        extracted_text = ""
        is_bild_ohne_text = False
        bild_b64 = None
        bild_mt = None

        # ── ZIP ──
        if suffix == ".zip" and zip_on:
            try:
                extracted_text = _extract_zip_contents(fp, zip_max_files, zip_max_size, max_per)
            except Exception:
                extracted_text = ""

        # ── Bild ──
        elif suffix in _BILD_EXTENSIONS:
            if ocr_on:
                try:
                    extracted_text = extract_text_image(fp)
                except Exception:
                    extracted_text = ""

            if not extracted_text.strip() and vision_on and fsize <= vision_max_kb:
                # Kein Text per OCR → Vision-Fallback
                try:
                    raw = fp.read_bytes()
                    bild_b64 = base64.b64encode(raw).decode("ascii")
                    bild_mt = _BILD_MEDIA_TYPES.get(suffix, "image/jpeg")
                    is_bild_ohne_text = True
                except Exception:
                    pass

        # ── PDF / DOCX / TXT / CSV ──
        elif dp_is_supported(fp):
            try:
                extracted_text = extract_text(fp)
            except Exception:
                extracted_text = ""

        else:
            stats["skipped"] += 1
            continue

        # ── Cache schreiben ──
        if cache_db and message_id:
            try:
                cache_db.execute(
                    "INSERT OR REPLACE INTO anhang_text_cache "
                    "(message_id, dateiname, extrahierter_text, ist_bild_ohne_text, "
                    "bild_base64, bild_media_type, dateigroesse, extrahiert_am) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (message_id, fname,
                     extracted_text[:50000] if extracted_text else None,
                     1 if is_bild_ohne_text else 0,
                     bild_b64, bild_mt, fsize,
                     datetime.now().isoformat())
                )
                cache_db.commit()
            except Exception:
                pass

        # ── Ergebnis sammeln ──
        if extracted_text.strip():
            txt = extracted_text.strip()[:max_per]
            text_parts.append(f"\U0001F4CE {fname}:\n  {txt}")
            total_chars += len(txt)
            stats["extracted"] += 1
        elif is_bild_ohne_text and bild_b64:
            vision_images.append({"data": bild_b64, "media_type": bild_mt, "name": fname})
            text_parts.append(f"\U0001F4CE {fname} (Bild \u2014 wird visuell analysiert)")
            stats["vision"] += 1
        else:
            stats["ocr_failed"] += 1

    if cache_db:
        try:
            cache_db.close()
        except Exception:
            pass

    if not text_parts and not vision_images:
        return empty

    # Gesamt-Text kürzen
    block = "ANHANG-INHALTE (extrahierter Text):\n" + "\n".join(text_parts)
    if len(block) > max_total + 200:
        block = block[:max_total + 200] + "\n[... gekürzt]"

    return {"text_block": block, "vision_images": vision_images, "stats": stats}


def _extract_zip_contents(zip_path: Path, max_files: int, max_size: int, max_per: int) -> str:
    """Extrahiert Text aus Dateien innerhalb eines ZIP-Archivs."""
    from dokument_pipeline import extract_text as dp_extract, is_supported as dp_ok
    parts = []
    with zipfile.ZipFile(str(zip_path), 'r') as zf:
        total = sum(i.file_size for i in zf.infolist() if not i.is_dir())
        if total > max_size:
            return f"[ZIP zu gro\u00df: {total // 1024 // 1024} MB]"
        inner = [i for i in zf.infolist() if not i.is_dir()][:max_files]
        with tempfile.TemporaryDirectory() as tmpdir:
            for info in inner:
                try:
                    extracted = Path(zf.extract(info, tmpdir))
                    if dp_ok(extracted):
                        txt = dp_extract(extracted)
                        if txt.strip():
                            parts.append(f"  [{info.filename}]: {txt.strip()[:max_per]}")
                except Exception:
                    continue
    return "\n".join(parts)


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


def _get_kira_wissen(limit: int = 50) -> str:
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
              AND kategorie IN ('klassifizierung','vorschlag','gelernt','kira','auto_gelernt','stil')
            ORDER BY erstellt_am DESC LIMIT ?
        """, (limit,)).fetchall()
        db.close()
        if not rows:
            return ""
        lines = []
        for r in rows:
            titel  = (r["titel"] or "")[:60]
            inhalt = (r["inhalt"] or "")[:200]
            lines.append(f"  • {titel}: {inhalt}")
        return "\n".join(lines)
    except Exception:
        return ""


def _get_correction_beispiele(limit: int = 30) -> str:
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


def _get_kira_wissen_relevant(absender: str, betreff: str, text: str,
                               max_chars: int = 12000) -> str:
    """Lädt ALLE aktiven Wissensregeln, scored nach Relevanz zur aktuellen Mail."""
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        rows = db.execute("""
            SELECT id, kategorie, titel, inhalt, erstellt_am
            FROM wissen_regeln
            WHERE status = 'aktiv'
              AND kategorie IN ('klassifizierung','vorschlag','gelernt','kira','auto_gelernt','stil')
        """).fetchall()
        db.close()
        if not rows:
            return ""

        abs_lower = (absender or "").lower()
        abs_domain = abs_lower.split("@")[-1] if "@" in abs_lower else ""
        mail_words = set((betreff + " " + (text or "")[:500]).lower().split())

        scored = []
        for r in rows:
            regel_text = ((r["titel"] or "") + " " + (r["inhalt"] or "")).lower()
            regel_words = set(regel_text.split())

            # Keyword-Overlap (Jaccard-ähnlich)
            overlap = len(mail_words & regel_words)
            union = len(mail_words | regel_words) or 1
            kw_score = overlap / union

            # Domain-Match
            domain_score = 1.0 if abs_domain and abs_domain in regel_text else 0.0

            # Absender-Match
            abs_score = 1.0 if abs_lower and abs_lower in regel_text else 0.0

            # Aktualität (logarithmisch, max 1.0)
            try:
                days_old = (datetime.now() - datetime.fromisoformat(r["erstellt_am"][:19])).days
            except Exception:
                days_old = 365
            time_score = 1.0 / (1.0 + math.log1p(days_old / 30))

            total = kw_score * 0.35 + domain_score * 0.25 + abs_score * 0.15 + time_score * 0.10
            if r["kategorie"] == "klassifizierung":
                total += 0.15

            scored.append((total, r))

        scored.sort(key=lambda x: x[0], reverse=True)

        lines = []
        chars_used = 0
        for score, r in scored:
            titel = (r["titel"] or "")[:80]
            inhalt = (r["inhalt"] or "")[:200]
            line = f"  • {titel}: {inhalt}"
            if chars_used + len(line) > max_chars:
                break
            lines.append(line)
            chars_used += len(line)

        return "\n".join(lines)
    except Exception:
        return ""


def _get_correction_beispiele_relevant(absender: str, betreff: str, text: str,
                                        max_chars: int = 6000) -> str:
    """Lädt Korrekturen scored nach Relevanz zur aktuellen Mail."""
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        rows = db.execute("""
            SELECT c.alter_typ, c.neuer_typ, c.notiz, c.erstellt_am,
                   t.betreff, t.zusammenfassung, t.absender_rolle, t.kunden_email
            FROM corrections c
            LEFT JOIN tasks t ON t.id = c.task_id
            WHERE c.alter_typ != c.neuer_typ
        """).fetchall()
        db.close()
        if not rows:
            return ""

        abs_lower = (absender or "").lower()
        abs_domain = abs_lower.split("@")[-1] if "@" in abs_lower else ""
        betr_lower = (betreff or "").lower()

        scored = []
        for r in rows:
            score = 0.0
            corr_email = (r["kunden_email"] or "").lower()
            corr_domain = corr_email.split("@")[-1] if "@" in corr_email else ""
            if abs_domain and corr_domain == abs_domain:
                score += 0.4
            if abs_lower and corr_email == abs_lower:
                score += 0.3

            corr_betr = (r["betreff"] or "").lower()
            if corr_betr and betr_lower:
                corr_words = set(corr_betr.split())
                betr_words = set(betr_lower.split())
                overlap = len(corr_words & betr_words)
                if overlap > 0:
                    score += 0.2 * min(overlap / max(len(corr_words), 1), 1.0)

            try:
                days = (datetime.now() - datetime.fromisoformat(r["erstellt_am"][:19])).days
            except Exception:
                days = 365
            score += 0.1 / (1.0 + math.log1p(days / 30))

            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)

        lines = []
        chars_used = 0
        for sc, r in scored:
            betr_short = (r["betreff"] or "")[:60]
            zusamm = (r["zusammenfassung"] or "")[:60]
            kontext = betr_short or zusamm
            notiz = f' (Grund: {r["notiz"]})' if r["notiz"] else ""
            line = f'  • "{kontext}" → war: {r["alter_typ"]} → richtig: {r["neuer_typ"]}{notiz}'
            if chars_used + len(line) > max_chars:
                break
            lines.append(line)
            chars_used += len(line)

        return "\n".join(lines)
    except Exception:
        return ""


def classify_mail_llm(konto: str, absender: str, betreff: str, text: str,
                      anhaenge: list = None, folder: str = "",
                      is_sent: bool = False, mail_datum: str = "",
                      kanal: str = "email",
                      anhaenge_pfad: str = "") -> dict:
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

        # Kontext-Anreicherung: Angebote + Korrekturen + Wissen + Kundenprofil + Verlauf + Lexware
        kunden_email_raw     = extract_email(absender)
        angebote_kontext     = _get_angebote_kontext(absender, text, mail_datum=mail_datum)
        correction_beispiele = _get_correction_beispiele_relevant(absender, betreff, text)
        kira_wissen          = _get_kira_wissen_relevant(absender, betreff, text)
        kunden_profil        = _get_kunden_profil(kunden_email_raw)
        mail_verlauf         = _get_mail_verlauf_kontext(kunden_email_raw)
        lexware_kontext      = _get_lexware_kontext(kunden_email_raw)

        # Anhang-Text-Extraktion (PDF/DOCX/ZIP/OCR + Vision-Fallback)
        anhang_result = _extract_attachment_texts(
            anhaenge=anhaenge or [], anhaenge_pfad=anhaenge_pfad,
            message_id=mail_datum,
        )
        anhang_texte = anhang_result.get("text_block", "")
        vision_images = anhang_result.get("vision_images", [])

        prompt = _build_classification_prompt(
            konto, absender, betreff, text, folder, is_sent,
            angebote_kontext=angebote_kontext,
            correction_beispiele=correction_beispiele,
            kira_wissen=kira_wissen,
            kunden_profil=kunden_profil,
            mail_verlauf=mail_verlauf,
            lexware_kontext=lexware_kontext,
            anhaenge=anhaenge,
            anhang_texte=anhang_texte,
        )

        # Klassifizierungs-Aufruf (Haiku, 768 max_tokens) — mit Vision wenn Bilder vorhanden
        result = classify_direct(prompt, max_tokens=768, vision_images=vision_images or None)

        if result.get("error"):
            if result.get("all_providers_failed"):
                # ALLE Provider tot → Pause-Signal statt regelbasiertem Fallback
                fb = _classify_rule_based(konto, absender, betreff, text, anhaenge, folder, is_sent)
                fb["_llm_fallback"] = True
                fb["_all_providers_failed"] = True
                return fb
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
                "erfordert_handlung": parsed.get("erfordert_handlung", True),
                "routing":            parsed.get("routing", "task"),
                "mit_termin":         1 if parsed.get("mit_termin") else 0,
                "manuelle_pruefung":  1 if parsed.get("manuelle_pruefung") else 0,
                "beantwortet":        1 if parsed.get("beantwortet") else 0,
                "organisation":       organisation,
                "geschaeft":          geschaeft,
                "angebot_aktion":     angebot_aktion,
                "angebot_nummer":     angebot_nummer,
            }

    except Exception as e:
        # LLM fehlgeschlagen — Fallback MIT Logging
        import logging
        _log = logging.getLogger("llm_classifier")
        _log.warning(f"LLM-Klassifizierung fehlgeschlagen, Fallback auf Regeln: {e}")
        try:
            from runtime_log import elog as _elog_lc
            _elog_lc('system', 'llm_classify_fallback',
                     f"LLM-Fehler: {str(e)[:200]} | {betreff[:80]}",
                     source='llm_classifier', modul='llm_classifier',
                     submodul='classify', actor_type='system', status='warnung',
                     error_message=str(e)[:500])
        except Exception:
            pass

    # ── FALLBACK: Regelbasierte Klassifizierung ──
    fb_result = _classify_rule_based(konto, absender, betreff, text, anhaenge, folder, is_sent)
    fb_result["_llm_fallback"] = True
    return fb_result


# Re-Export für Kompatibilität
def classify_mail(konto: str, absender: str, betreff: str, text: str,
                  anhaenge: list = None, folder: str = "",
                  is_sent: bool = False, mail_datum: str = "",
                  kanal: str = "email",
                  anhaenge_pfad: str = "") -> dict:
    """Alias — Drop-in-Replacement, bereit für Multi-Kanal (kanal='whatsapp' etc.)."""
    return classify_mail_llm(konto, absender, betreff, text, anhaenge, folder,
                             is_sent, mail_datum=mail_datum, kanal=kanal,
                             anhaenge_pfad=anhaenge_pfad)
