#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
angebote_tracker.py — Automatisches Angebots-Tracking für rauMKult®.
Sucht in Mail-Bodies nach Kundenantworten auf offene Angebote.
Schlägt Nachfass-Aktionen vor wenn keine Antwort gefunden wird.
"""
import json, sqlite3, re
from pathlib import Path
from datetime import datetime, timedelta

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"
KUNDEN_DB     = KNOWLEDGE_DIR / "kunden.db"
CONFIG_FILE   = SCRIPTS_DIR / "config.json"


def _load_config():
    try:
        return json.loads(CONFIG_FILE.read_text('utf-8'))
    except:
        return {}


def _get_nachfass_intervalle():
    cfg = _load_config()
    nf = cfg.get("nachfass", {})
    return (
        nf.get("intervall_1_tage", 10),
        nf.get("intervall_2_tage", 21),
        nf.get("intervall_3_tage", 45),
    )


# ── Mail-Suche ───────────────────────────────────────────────────────────────
def find_angebot_responses(a_nummer, kunde_email="", angebot_datum=""):
    """Sucht in kunden.db nach Mails die auf ein Angebot reagieren."""
    if not KUNDEN_DB.exists():
        return []

    db = sqlite3.connect(str(KUNDEN_DB))
    db.row_factory = sqlite3.Row
    results = []

    # 1. Suche nach A-SB Nummer im Mail-Text
    if a_nummer:
        rows = db.execute("""
            SELECT betreff, absender, kunden_email, datum, text_plain, message_id
            FROM interaktionen
            WHERE text_plain LIKE ? OR betreff LIKE ?
            ORDER BY datum DESC LIMIT 10
        """, (f"%{a_nummer}%", f"%{a_nummer}%")).fetchall()
        results.extend(rows)

    # 2. Suche nach Kunden-Email + Angebot-Keywords (nach Angebotsdatum)
    if kunde_email and angebot_datum:
        rows = db.execute("""
            SELECT betreff, absender, kunden_email, datum, text_plain, message_id
            FROM interaktionen
            WHERE kunden_email = ?
              AND datum > ?
              AND (LOWER(text_plain) LIKE '%angebot%'
                   OR LOWER(text_plain) LIKE '%auftrag%'
                   OR LOWER(text_plain) LIKE '%zusage%'
                   OR LOWER(text_plain) LIKE '%absage%'
                   OR LOWER(text_plain) LIKE '%zu teuer%'
                   OR LOWER(text_plain) LIKE '%beauftrag%'
                   OR LOWER(betreff) LIKE '%angebot%')
            ORDER BY datum DESC LIMIT 10
        """, (kunde_email, angebot_datum)).fetchall()
        for r in rows:
            if r['message_id'] not in [x['message_id'] for x in results]:
                results.append(r)

    db.close()
    return [dict(r) for r in results]


# ── LLM-Klassifizierung der Antwort ─────────────────────────────────────────
def classify_response_llm(a_nummer, mail_text, betreff=""):
    """LLM klassifiziert eine Kundenantwort auf ein Angebot."""
    try:
        from kira_llm import chat as kira_chat, get_providers
        if not get_providers():
            raise RuntimeError("Kein Provider")

        prompt = f"""Analysiere diese Kundenmail als Reaktion auf Angebot {a_nummer}:

Betreff: {betreff}
Text: {(mail_text or '')[:1500]}

Klassifiziere als JSON:
{{
  "status": "angenommen" | "abgelehnt" | "nachfrage" | "unklar",
  "grund": "Kurze Begründung (z.B. 'zu teuer', 'anderer Anbieter', 'Projekt verschoben', 'will Änderungen')",
  "confidence": 0.0-1.0
}}"""

        result = kira_chat(
            user_message=f"[SYSTEM: Angebots-Antwort klassifizieren]\n\n{prompt}",
            session_id=None
        )
        if result.get("error"):
            raise RuntimeError(result["error"])

        m = re.search(r'\{[\s\S]*\}', result.get("antwort", ""))
        if m:
            data = json.loads(m.group(0))
            return data
    except:
        pass

    # Fallback: Keyword-Analyse
    text_lower = (mail_text or "").lower()
    if any(kw in text_lower for kw in ['zusage', 'beauftrag', 'auftrag erteilt', 'zugesagt', 'akzeptiert']):
        return {"status": "angenommen", "grund": "Zusage-Keywords erkannt", "confidence": 0.7}
    if any(kw in text_lower for kw in ['absage', 'zu teuer', 'anderer anbieter', 'leider nicht', 'abgelehnt']):
        return {"status": "abgelehnt", "grund": "Absage-Keywords erkannt", "confidence": 0.7}
    if any(kw in text_lower for kw in ['frage', 'änderung', 'anpassung', 'nachfrage', 'klärung']):
        return {"status": "nachfrage", "grund": "Nachfrage-Keywords erkannt", "confidence": 0.6}
    return {"status": "unklar", "grund": "Keine klaren Indikatoren", "confidence": 0.3}


# ── Nachfass-Vorschlag ──────────────────────────────────────────────────────
def suggest_next_action(angebot, tage_offen, nachfass_count):
    """Schlägt nächste Aktion vor basierend auf Alter und Nachfass-Stand."""
    i1, i2, i3 = _get_nachfass_intervalle()

    if nachfass_count == 0 and tage_offen >= i1:
        return {
            "aktion": "nachfass_1",
            "text": f"Freundliche Erinnerung fällig (Angebot seit {tage_offen} Tagen offen, 0/3 Nachfass)",
            "dringend": tage_offen >= i1 + 3
        }
    if nachfass_count == 1 and tage_offen >= i2:
        return {
            "aktion": "nachfass_2",
            "text": f"2. Nachfass fällig (seit {tage_offen} Tagen, 1/3 bereits gesendet)",
            "dringend": tage_offen >= i2 + 5
        }
    if nachfass_count == 2 and tage_offen >= i3:
        return {
            "aktion": "nachfass_3",
            "text": f"Letzter Nachfass fällig (seit {tage_offen} Tagen, 2/3 bereits gesendet)",
            "dringend": True
        }
    if nachfass_count >= 3 and tage_offen >= i3 + 14:
        return {
            "aktion": "archivieren",
            "text": f"Angebot seit {tage_offen} Tagen ohne Antwort nach 3 Nachfass. Archivieren?",
            "dringend": False
        }
    return None


# ── Hauptfunktion ────────────────────────────────────────────────────────────
def check_all_open_angebote():
    """Prüft alle offenen Angebote auf Kundenantworten und Nachfass-Fälligkeit."""
    if not TASKS_DB.exists():
        return {"checked": 0, "updates": [], "nachfass_faellig": [], "alerts": []}

    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row

    angebote = db.execute("""
        SELECT id, a_nummer, datum, kunde_email, kunde_name, betrag_geschaetzt,
               status, nachfass_count, letzter_nachfass
        FROM angebote
        WHERE status = 'offen'
    """).fetchall()

    updates = []
    nachfass_faellig = []
    alerts = []
    today = datetime.now().date()

    for ang in angebote:
        a_nr = ang['a_nummer']
        if not a_nr:
            continue

        datum = ang['datum'] or ""
        try:
            ang_date = datetime.strptime(datum[:10], "%Y-%m-%d").date()
            tage_offen = (today - ang_date).days
        except:
            tage_offen = 0

        kunde_email = ang['kunde_email'] or ""
        nachfass_count = ang['nachfass_count'] or 0

        # 1. Nach Kundenantworten suchen
        responses = find_angebot_responses(a_nr, kunde_email, datum)

        if responses:
            # Beste/neueste Antwort klassifizieren
            best = responses[0]
            classification = classify_response_llm(a_nr, best.get('text_plain', ''), best.get('betreff', ''))

            if classification.get("confidence", 0) >= 0.6:
                new_status = classification["status"]
                if new_status in ("angenommen", "abgelehnt"):
                    # Status aktualisieren
                    db.execute("UPDATE angebote SET status=?, notiz=? WHERE id=?",
                               (new_status, f"Auto-erkannt: {classification.get('grund', '')}", ang['id']))

                    # In Statistik speichern
                    db.execute("""INSERT INTO geschaeft_statistik (typ, referenz_id, ereignis, daten_json, erstellt_am)
                        VALUES (?,?,?,?,?)""",
                        ("angebot", ang['id'], f"status_{new_status}",
                         json.dumps({"a_nummer": a_nr, "kunde": ang['kunde_name'],
                                     "grund": classification.get("grund", ""),
                                     "confidence": classification.get("confidence", 0),
                                     "quelle": "auto_tracker"}, ensure_ascii=False),
                         datetime.now().isoformat()))

                    updates.append({
                        "a_nummer": a_nr,
                        "neuer_status": new_status,
                        "grund": classification.get("grund", ""),
                        "confidence": classification.get("confidence", 0),
                    })
                    continue
                elif new_status == "nachfrage":
                    alerts.append(f"Angebot {a_nr}: Kunde hat Rückfragen — bitte prüfen")

        # 2. Nachfass prüfen (nur wenn keine Antwort gefunden)
        if tage_offen > 0:
            action = suggest_next_action(ang, tage_offen, nachfass_count)
            if action:
                nachfass_faellig.append({
                    "a_nummer": a_nr,
                    "kunde": ang['kunde_name'] or kunde_email,
                    "betrag": ang['betrag_geschaetzt'] or 0,
                    "tage_offen": tage_offen,
                    "nachfass_count": nachfass_count,
                    **action,
                })

    db.commit()
    db.close()

    result = {
        "checked": len(angebote),
        "updates": updates,
        "nachfass_faellig": nachfass_faellig,
        "alerts": alerts,
    }

    # ntfy Push für dringende Nachfass-Fälligkeiten
    dringend = [n for n in nachfass_faellig if n.get("dringend")]
    if dringend or updates:
        _send_angebote_notification(updates, dringend)

    return result


def _send_angebote_notification(updates, dringend):
    """Sendet ntfy Push für Angebote-Updates."""
    try:
        cfg = _load_config()
        ntfy = cfg.get("ntfy", {})
        if not ntfy.get("aktiv"):
            return
        topic = ntfy.get("topic_name", "")
        server = ntfy.get("server", "https://ntfy.sh")
        if not topic:
            return

        parts = []
        for u in updates:
            parts.append(f"{u['a_nummer']}: {u['neuer_status']} ({u['grund'][:30]})")
        for d in dringend:
            parts.append(f"{d['a_nummer']}: Nachfass fällig ({d['tage_offen']}T offen)")

        msg = "Kira Angebote: " + "; ".join(parts[:5])

        import urllib.request
        req = urllib.request.Request(
            f"{server}/{topic}",
            data=msg.encode('utf-8'),
            headers={"Title": "Kira Angebote-Tracker", "Priority": "high"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except:
        pass


# ── Standalone ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except:
            pass

    print("Angebote-Tracker — Prüfe offene Angebote\n")
    result = check_all_open_angebote()

    print(f"Geprüft: {result['checked']} offene Angebote")

    if result['updates']:
        print(f"\nStatus-Updates ({len(result['updates'])}):")
        for u in result['updates']:
            print(f"  {u['a_nummer']}: {u['neuer_status']} — {u['grund']}")

    if result['nachfass_faellig']:
        print(f"\nNachfass fällig ({len(result['nachfass_faellig'])}):")
        for n in result['nachfass_faellig']:
            d = "DRINGEND" if n.get('dringend') else ""
            print(f"  {n['a_nummer']} | {n['kunde'][:25]} | {n['betrag']:.0f} EUR | {n['tage_offen']}T | {n['text']} {d}")

    if result['alerts']:
        print(f"\nAlerts ({len(result['alerts'])}):")
        for a in result['alerts']:
            print(f"  {a}")

    print("\nFertig.")
