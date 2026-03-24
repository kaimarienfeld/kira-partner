#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antwort-Entwurf Generator für rauMKult®
Template-basiert. Für KI-Qualität -> Claude direkt nutzen.
"""
import re

def extract_name(absender: str, text: str) -> str:
    """Extrahiert Kundenname aus Absender oder Mailtext."""
    m = re.match(r'^"?([A-ZÄÖÜ][a-zäöüß]+ [A-ZÄÖÜ][a-zäöüß]+)"?\s*<', absender)
    if m:
        parts = m.group(1).strip().split()
        return parts[0] if parts else ""
    for pattern in [r'(?:Ich bin|bin|Mein Name ist|Name:)\s+([A-ZÄÖÜ][a-zäöüß]+ [A-ZÄÖÜ][a-zäöüß]+)',
                    r'(?:Mit freundlichen Grüßen|Viele Grüße|Gruß)\s*,?\s*([A-ZÄÖÜ][a-zäöüß]+)',
                    r'^([A-ZÄÖÜ][a-zäöüß]+)\s+[A-ZÄÖÜ][a-zäöüß]+\s*$']:
        m2 = re.search(pattern, text, re.MULTILINE)
        if m2:
            return m2.group(1)
    return ""

def detect_anrede(absender: str, text: str) -> tuple:
    """Erkennt ob Du oder Sie, und den Vornamen."""
    name = extract_name(absender, text)
    text_lower = text.lower()
    # Wenn Kunde duzt
    du_patterns = ['ich wollte fragen', 'kannst du', 'hast du', 'weißt du',
                   'machst du', 'kannst mir', 'danke dir']
    if any(p in text_lower for p in du_patterns):
        return "du", name
    return "sie", name

def detect_projekt_typ(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ['treppe', 'stufen', 'stiege', 'tritt', 'treppenstufe']): return "treppe"
    if any(k in t for k in ['fassade', 'außenwand', 'aussenwand', 'außenfläche']): return "fassade"
    if any(k in t for k in ['wand', 'innenwand', 'wandfläche']): return "wand"
    if any(k in t for k in ['boden', 'bodenplatte', 'estrich', 'bodenfläche']): return "boden"
    if any(k in t for k in ['decke', 'betondecke']): return "decke"
    if any(k in t for k in ['fertigteil', 'betonfertigteil', 'ft']): return "fertigteil"
    return "allgemein"

def detect_mail_situation(text: str, betreff: str) -> str:
    """Erkennt die Situation der Mail."""
    t = (text + betreff).lower()
    if any(k in t for k in ['preis', 'kosten', 'wie viel', 'wieviel', 'was kostet', 'angebot']): return "preis_anfrage"
    if any(k in t for k in ['foto', 'bild', 'hänge an', 'anbei', 'im anhang']): return "mit_fotos"
    if any(k in t for k in ['wann', 'termin', 'verfügbar', 'zeitraum', 'zeitfenster']): return "termin"
    if any(k in t for k in ['aw:', 're:', 'danke', 'rückmeldung', 'feedback']): return "folgemail"
    return "erstanfrage"

def generate_draft(betreff: str, absender: str, text: str, kunden_email: str = "") -> dict:
    """
    Generiert einen Antwort-Entwurf.
    Gibt zurück: {
      'betreff': str,
      'anrede': str,
      'text': str,
      'hinweis': str,
      'claude_prompt': str  (zum Einfügen in Claude für bessere Antwort)
    }
    """
    anrede_typ, vorname = detect_anrede(absender, text)
    projekt = detect_projekt_typ(text)
    situation = detect_mail_situation(text, betreff)

    if anrede_typ == "du":
        anrede = f"Hallo{' ' + vorname if vorname else ''},"
        gruss = "Viele Grüße\nKai"
    else:
        anrede = f"Sehr geehrte{'r Herr' if 'herr' in absender.lower() else ' Frau'}{' ' + vorname if vorname else ''},"
        gruss = "Mit freundlichen Grüßen\nKai Marienfeld\nStaatl. gepr. Bautechniker (Hochbau)\nrauMKult® – pure surface art"

    antwort_betreff = betreff if betreff.lower().startswith('re:') else f"Re: {betreff}"

    # Haupttext je nach Situation
    if situation == "preis_anfrage":
        hinweis = "⚠️ Preis-Anfrage — in Erstantwort KEINE Preise nennen. Claude für bessere Antwort nutzen."
        haupttext = _preis_template(anrede_typ, projekt, text)
    elif situation == "mit_fotos":
        hinweis = "📷 Fotos vorhanden — direkte Einschätzung möglich. Claude für detaillierte Antwort nutzen."
        haupttext = _fotos_template(anrede_typ, projekt, text)
    elif situation == "termin":
        hinweis = "📅 Termin-Anfrage — ggf. Kalender checken."
        haupttext = _termin_template(anrede_typ)
    elif situation == "folgemail":
        hinweis = "↩️ Folgemail — Kontext der Vormail prüfen."
        haupttext = _folge_template(anrede_typ, text)
    else:
        hinweis = "📋 Erstanfrage — Infos einsammeln, noch keine Preise."
        haupttext = _erstanfrage_template(anrede_typ, projekt, text)

    entwurf = f"{anrede}\n\n{haupttext}\n\n{gruss}"

    # Claude-Prompt für bessere Antwort
    claude_prompt = (
        f"Bitte schreibe eine passende Antwort auf diese Kundenanfrage:\n\n"
        f"BETREFF: {betreff}\n"
        f"VON: {absender}\n\n"
        f"MAIL-INHALT:\n{text[:800]}\n\n"
        f"Anweisungen:\n"
        f"- Stil: Kai Marienfeld / rauMKult® (direkt, handwerklich, kein KI-Sound)\n"
        f"- Anrede: {'Du' if anrede_typ == 'du' else 'Sie'}\n"
        f"- Projekt: {projekt}\n"
        f"- Keine Preise in der Erstantwort\n"
        f"- Format: A) Kundenantwort (copy/paste) B) Interne Notiz"
    )

    return {
        "betreff":       antwort_betreff,
        "an":            kunden_email,
        "entwurf":       entwurf,
        "hinweis":       hinweis,
        "projekt_typ":   projekt,
        "situation":     situation,
        "claude_prompt": claude_prompt,
    }


def _erstanfrage_template(anrede_typ: str, projekt: str, text: str) -> str:
    projekt_labels = {
        "treppe": "Betontreppe", "fassade": "Betonfassade", "wand": "Betonwand",
        "boden": "Betonboden", "decke": "Betondecke", "fertigteil": "Betonfertigteil",
        "allgemein": "Sichtbetonfläche"
    }
    p = projekt_labels.get(projekt, "Sichtbetonfläche")

    if anrede_typ == "du":
        return (
            f"danke für deine Anfrage zur {p}.\n\n"
            f"Damit ich dir eine saubere Einschätzung geben kann, brauche ich noch ein paar Angaben:\n\n"
            f"- Wo liegt die Fläche genau (Ort / PLZ)?\n"
            f"- Welche Maße hat die Fläche? Bei Treppen: Anzahl Stufen + Breite\n"
            f"- Was soll gemacht werden – nur kosmetisch, oder gibt es konkrete Schäden?\n"
            f"- Zieloptik: natürlich/dezent oder sehr homogen?\n"
            f"- Bis wann soll es fertig sein?\n\n"
            f"Am hilfreichsten wären ein paar Fotos – Gesamtansicht + Nahaufnahmen der Problemstellen.\n"
            f"Du kannst sie hier hochladen: [Anfrage MEDIEN Upload](https://raumkultsichtbeton-my.sharepoint.com/:f:/g/personal/kaimrf_raumkultsichtbeton_onmicrosoft_com/IgAWE3ByeoxETY4VJ249vhYXAW59otX-lXJcpl2F74hws4k)"
        )
    else:
        return (
            f"vielen Dank für Ihre Anfrage zur {p}.\n\n"
            f"Damit ich Ihnen eine saubere Einschätzung geben kann, benötige ich noch folgende Angaben:\n\n"
            f"- Ort / PLZ des Projekts\n"
            f"- Maße der Fläche (bei Treppen: Stufenanzahl + Breite)\n"
            f"- Art der Bearbeitung – rein kosmetisch oder konkrete Schäden?\n"
            f"- Gewünschte Zieloptik: natürlich/dezent oder sehr homogen?\n"
            f"- Wann soll die Arbeit fertig sein?\n\n"
            f"Fotos sind sehr hilfreich: Gesamtansicht und Nahaufnahmen der Problemstellen.\n"
            f"Sie können diese hier hochladen: [Anfrage MEDIEN Upload](https://raumkultsichtbeton-my.sharepoint.com/:f:/g/personal/kaimrf_raumkultsichtbeton_onmicrosoft_com/IgAWE3ByeoxETY4VJ249vhYXAW59otX-lXJcpl2F74hws4k)"
        )


def _fotos_template(anrede_typ: str, projekt: str, text: str) -> str:
    if anrede_typ == "du":
        return (
            "danke für deine Anfrage und die Fotos.\n\n"
            "Ich habe mir die Bilder angeschaut. "
            "Grundsätzlich ist das eine typische Aufgabe für Betonkosmetik – "
            "ich würde das nach folgender Vorgehensweise angehen: [Einschätzung nach Fotoanalyse einfügen]\n\n"
            "Damit ich dir den Aufwand konkret benennen kann, wäre es hilfreich zu wissen:\n"
            "- Wo liegt das Projekt (PLZ)?\n"
            "- Wann soll es fertig sein?\n"
            "- Hast du schon eine grobe Budgetvorstellung?"
        )
    else:
        return (
            "vielen Dank für Ihre Anfrage und die mitgesendeten Fotos.\n\n"
            "Ich habe mir die Bilder angeschaut. "
            "Das ist eine typische Aufgabe für Betonkosmetik – "
            "die Vorgehensweise wäre: [Einschätzung nach Fotoanalyse einfügen]\n\n"
            "Damit ich Ihnen den Aufwand konkret nennen kann:\n"
            "- Wo liegt das Projekt (PLZ)?\n"
            "- Bis wann wäre der Wunschtermin?\n"
            "- Haben Sie eine grobe Budgetvorstellung?"
        )


def _preis_template(anrede_typ: str, projekt: str, text: str) -> str:
    if anrede_typ == "du":
        return (
            "danke für deine Anfrage.\n\n"
            "Einen konkreten Preis kann ich dir erst nach Sichtung der Fläche bzw. "
            "nach Fotos und genauen Angaben nennen – bei Betonkosmetik hängt der Aufwand "
            "stark vom Zustand, der Zugänglichkeit und der gewünschten Zieloptik ab.\n\n"
            "Schick mir gern ein paar Fotos und folgende Angaben:\n"
            "- Ort / PLZ\n"
            "- Maße der Fläche\n"
            "- Was genau soll gemacht werden?\n"
            "- Zieloptik?\n\n"
            "Dann kann ich dir eine realistische Einschätzung geben."
        )
    else:
        return (
            "vielen Dank für Ihre Anfrage.\n\n"
            "Einen verbindlichen Preis kann ich erst nach Sichtung der Unterlagen nennen – "
            "bei Betonkosmetik ist der Aufwand immer individuell und hängt vom Zustand, "
            "der Zugänglichkeit und der gewünschten Zieloptik ab.\n\n"
            "Für eine erste Einschätzung benötige ich:\n"
            "- Ort / PLZ\n"
            "- Maße der Fläche\n"
            "- Fotos (Gesamtansicht + Nahaufnahmen)\n"
            "- Gewünschte Zieloptik\n\n"
            "Dann kann ich Ihnen eine realistische Orientierung geben."
        )


def _termin_template(anrede_typ: str) -> str:
    if anrede_typ == "du":
        return (
            "danke für deine Nachricht.\n\n"
            "Lass uns kurz telefonieren, dann können wir das schnell klären.\n"
            "Du kannst direkt einen Termin buchen: [Terminlink einfügen]\n"
            "Oder ruf mich an: +49 160 99195118"
        )
    else:
        return (
            "vielen Dank für Ihre Nachricht.\n\n"
            "Am einfachsten klären wir das kurz telefonisch.\n"
            "Sie können direkt einen Termin buchen: [Terminlink einfügen]\n"
            "Oder rufen Sie mich an: +49 160 99195118"
        )


def _folge_template(anrede_typ: str, text: str) -> str:
    if anrede_typ == "du":
        return (
            "danke für deine Rückmeldung.\n\n"
            "[Hier auf den spezifischen Inhalt eingehen]\n\n"
            "Melde dich, wenn du weitere Fragen hast."
        )
    else:
        return (
            "vielen Dank für Ihre Rückmeldung.\n\n"
            "[Hier auf den spezifischen Inhalt eingehen]\n\n"
            "Bei weiteren Fragen stehe ich gern zur Verfügung."
        )


# ── Nachfass-Vorlagen für Angebote ──────────────────────────────────────────

def generate_nachfass(stufe: int, a_nummer: str, kunde_name: str, kunde_email: str,
                      betreff_original: str = "") -> dict:
    """
    Generiert Nachfass-Mail für ein offenes Angebot.
    stufe: 1 (freundlich), 2 (konkreter), 3 (letzter Check-in)
    Returns: {betreff, entwurf, claude_prompt}
    """
    vorname = kunde_name.split()[0] if kunde_name else ""
    anrede = f"Hallo{' ' + vorname if vorname else ''}," if vorname else "Sehr geehrte Damen und Herren,"
    gruss = ("Mit freundlichen Grüßen\nKai Marienfeld\n"
             "Staatl. gepr. Bautechniker (Hochbau)\n"
             "rauMKult® – pure surface art")

    if stufe == 1:
        betreff = f"Kurze Rückfrage zu Ihrem Angebot {a_nummer}"
        text = (
            f"{anrede}\n\n"
            f"ich wollte kurz nachfragen, ob Sie sich das Angebot {a_nummer} "
            f"anschauen konnten und ob es noch offene Fragen gibt.\n\n"
            f"Ich stehe gern für Rückfragen zur Verfügung – telefonisch "
            f"oder per Mail.\n\n{gruss}"
        )
    elif stufe == 2:
        betreff = f"Ihr Angebot {a_nummer} – gibt es offene Fragen?"
        text = (
            f"{anrede}\n\n"
            f"ich melde mich nochmal bezüglich des Angebots {a_nummer}.\n\n"
            f"Falls es offene Punkte gibt oder sich die Anforderungen geändert haben, "
            f"passe ich das Angebot gern an. Auch beim Projektzeitplan kann ich "
            f"flexibel reagieren, solange ich rechtzeitig Bescheid weiß.\n\n"
            f"Lassen Sie mich wissen, wie der aktuelle Stand ist.\n\n{gruss}"
        )
    else:
        betreff = f"Angebot {a_nummer} – letzter Check-in"
        text = (
            f"{anrede}\n\n"
            f"ich möchte mich ein letztes Mal zum Angebot {a_nummer} melden.\n\n"
            f"Falls das Projekt aktuell nicht mehr ansteht – kein Problem. "
            f"Sollte sich in Zukunft etwas ergeben, können Sie sich jederzeit "
            f"bei mir melden.\n\n"
            f"Wenn das Angebot noch aktuell ist und ich etwas aktualisieren soll, "
            f"lassen Sie es mich gern wissen.\n\n{gruss}"
        )

    claude_prompt = (
        f"Schreibe eine Nachfass-Mail (Stufe {stufe}/3) für das Angebot {a_nummer}.\n"
        f"Kunde: {kunde_name or kunde_email}\n"
        f"Original-Betreff: {betreff_original}\n\n"
        f"Stil: Kai Marienfeld / rauMKult® (direkt, handwerklich, nicht aufdringlich)\n"
        f"Stufe 1: Freundlich nachfragen, ob es Fragen gibt\n"
        f"Stufe 2: Konkreter, Anpassungen anbieten, Zeitplan erwähnen\n"
        f"Stufe 3: Letzter Check-in, Tür offen lassen"
    )

    return {
        "betreff": betreff,
        "an": kunde_email,
        "entwurf": text,
        "claude_prompt": claude_prompt,
    }
