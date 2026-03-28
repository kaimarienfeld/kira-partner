#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llm_response_gen.py — LLM-gestützte Antwort-Generierung für rauMKult®.
Generiert Antwort-Entwürfe in Kais Stil basierend auf:
- sent_mails.db (522 gesendete Mails als Stil-Referenz)
- stil_guide.md (Dos & Don'ts)
- wissen_regeln (feste Geschäftsregeln)
Fallback: response_gen.py Templates.
"""
import json, sqlite3, re
from pathlib import Path

from response_gen import generate_draft as _generate_draft_template

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
SENT_DB       = KNOWLEDGE_DIR / "sent_mails.db"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"
STIL_GUIDE    = KNOWLEDGE_DIR / "stil_guide.md"


def _load_style_references(kunden_email="", betreff="", n=5):
    """Lädt ähnliche gesendete Mails als Stil-Referenz."""
    if not SENT_DB.exists():
        return []

    db = sqlite3.connect(str(SENT_DB))
    db.row_factory = sqlite3.Row
    refs = []

    # 1. Mails an gleichen Kunden
    if kunden_email:
        rows = db.execute(
            "SELECT betreff, text_plain FROM gesendete_mails WHERE kunden_email=? AND text_plain != '' ORDER BY datum DESC LIMIT ?",
            (kunden_email, min(n, 3))
        ).fetchall()
        refs.extend(rows)

    # 2. Mails mit ähnlichem Betreff (Keywords)
    if len(refs) < n and betreff:
        keywords = [w for w in betreff.lower().split() if len(w) > 3 and w not in ('re:', 'aw:', 'fwd:')]
        for kw in keywords[:3]:
            if len(refs) >= n:
                break
            rows = db.execute(
                "SELECT betreff, text_plain FROM gesendete_mails WHERE LOWER(betreff) LIKE ? AND text_plain != '' ORDER BY datum DESC LIMIT 2",
                (f"%{kw}%",)
            ).fetchall()
            for r in rows:
                if len(refs) < n and r['text_plain'] not in [x['text_plain'] for x in refs]:
                    refs.append(r)

    # 3. Auffüllen mit neuesten Mails
    if len(refs) < n:
        rows = db.execute(
            "SELECT betreff, text_plain FROM gesendete_mails WHERE text_plain != '' ORDER BY datum DESC LIMIT ?",
            (n - len(refs),)
        ).fetchall()
        for r in rows:
            if r['text_plain'] not in [x['text_plain'] for x in refs]:
                refs.append(r)

    db.close()
    return [{"betreff": r["betreff"], "text": r["text_plain"][:600]} for r in refs[:n]]


def _load_stil_guide():
    """Lädt den Stil-Guide."""
    if STIL_GUIDE.exists():
        try:
            return STIL_GUIDE.read_text('utf-8')[:3000]
        except:
            pass
    return ""


def _load_wissen_regeln():
    """Lädt feste Regeln aus wissen_regeln."""
    if not TASKS_DB.exists():
        return ""
    try:
        db = sqlite3.connect(str(TASKS_DB))
        rows = db.execute(
            "SELECT titel, inhalt FROM wissen_regeln WHERE kategorie IN ('fest','stil','preis') AND status='aktiv'"
        ).fetchall()
        db.close()
        return "\n".join(f"- {r[0]}: {r[1]}" for r in rows)
    except:
        return ""


def _build_response_prompt(betreff, absender, text, kunden_email, stil_refs, stil_guide, regeln):
    """Baut den LLM-Prompt für die Antwort-Generierung."""
    refs_text = ""
    if stil_refs:
        refs_text = "\n\nBEISPIEL-MAILS VON KAI (dein Stil-Vorbild):\n"
        for i, ref in enumerate(stil_refs, 1):
            refs_text += f"\n--- Mail {i}: {ref['betreff']} ---\n{ref['text']}\n"

    return f"""Schreibe eine Antwort auf diese Kundenmail im Namen von Kai Marienfeld (rauMKult® Sichtbeton).

EINGEHENDE MAIL:
Betreff: {betreff}
Von: {absender}
Text:
{(text or '')[:1500]}

STIL-REGELN:
{stil_guide[:1500] if stil_guide else 'Klar, direkt, handwerklich, kein Corporate-Sprech.'}

GESCHÄFTS-REGELN:
{regeln or '- Keine Preise in der Erstantwort\n- Immer Fotos anfordern wenn nicht vorhanden\n- Anrede nach Kundensprache (du/Sie)'}
{refs_text}

ANWEISUNGEN:
1. Schreibe wie Kai — nicht wie eine KI. Kein "gerne", kein "fundierte Einschätzung", kein "selbstverständlich".
2. Kurz und klar. Max 8-10 Zeilen für den Hauptteil.
3. Anrede aus dem Kontext ableiten (du/Sie).
4. KEINE Preise im Erstkontakt — stattdessen Informationen einsammeln.
5. Wenn Fotos fehlen: nach Fotos fragen + SharePoint-Link erwähnen.
6. Grußformel: "Viele Grüße, Kai" (du) oder "Mit freundlichen Grüßen, Kai Marienfeld" (Sie)

FORMAT deiner Antwort:
A) KUNDENANTWORT (direkt copy/paste-fertig):
[Hier die Antwort]

B) INTERNE NOTIZ:
[1-2 Sätze was Kai beachten sollte, z.B. "Kunde klingt preissensibel" oder "Hat bereits Fotos — direkte Einschätzung möglich"]"""


def generate_draft_llm(betreff: str, absender: str, text: str, kunden_email: str = "",
                       hint: str = "") -> dict:
    """
    LLM-gestützte Antwort-Generierung. Gleiche Signatur wie response_gen.generate_draft().
    hint: optionaler Kontext-Hinweis, z.B. "Angebotsrueckmeldung"
    """
    try:
        from kira_llm import chat as kira_chat, get_providers

        providers = get_providers()
        if not providers:
            raise RuntimeError("Kein Provider")

        # Stil-Daten laden
        stil_refs = _load_style_references(kunden_email, betreff)
        stil_guide = _load_stil_guide()
        regeln = _load_wissen_regeln()

        prompt = _build_response_prompt(betreff, absender, text, kunden_email,
                                        stil_refs, stil_guide, regeln)

        # Hint für Angebotsrückmeldungen einfügen
        if hint == "Angebotsrueckmeldung":
            prompt = ("KONTEXT: Diese Mail ist eine Angebotsrückmeldung (Kund:in reagiert auf ein gesendetes Angebot).\n"
                      "Erstelle eine passende Bestätigung (Annahme, Absage oder Rückfragen klären).\n\n") + prompt

        result = kira_chat(
            user_message=f"[SYSTEM: Antwort-Entwurf generieren]\n\n{prompt}",
            session_id=None
        )

        if result.get("error"):
            raise RuntimeError(result["error"])

        antwort = result.get("antwort", "")

        # A) und B) Teile extrahieren
        entwurf = antwort
        hinweis = ""

        m = re.search(r'A\)\s*(?:KUNDENANTWORT)?:?\s*\n([\s\S]*?)(?:B\)\s*(?:INTERNE NOTIZ)?:?\s*\n|$)', antwort)
        if m:
            entwurf = m.group(1).strip()
            m2 = re.search(r'B\)\s*(?:INTERNE NOTIZ)?:?\s*\n([\s\S]*)', antwort)
            if m2:
                hinweis = f"🤖 Kira: {m2.group(1).strip()}"

        antwort_betreff = betreff if betreff.lower().startswith('re:') else f"Re: {betreff}"

        return {
            "betreff":       antwort_betreff,
            "an":            kunden_email,
            "entwurf":       entwurf,
            "hinweis":       hinweis or "🤖 LLM-generierter Entwurf — bitte prüfen.",
            "projekt_typ":   "",
            "situation":     "llm_generated",
            "claude_prompt": "",  # Nicht mehr nötig — LLM hat direkt generiert
        }

    except Exception:
        pass

    # ── FALLBACK: Template-basiert ──
    return _generate_draft_template(betreff, absender, text, kunden_email)


# Alias für Drop-in-Replacement
def generate_draft(betreff: str, absender: str, text: str, kunden_email: str = "",
                   hint: str = "") -> dict:
    return generate_draft_llm(betreff, absender, text, kunden_email, hint=hint)
