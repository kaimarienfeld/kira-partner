#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kira_proaktiv.py — KIRAs autonomer Geschäfts-Scanner.

Läuft im Hintergrund (alle 15 Min via mail_monitor), scannt ALLE Geschäftsvorgänge
und erstellt automatisch Handlungsempfehlungen + Tasks wenn nötig.

Prüft:
- Überfällige Rechnungen (14, 30, 45+ Tage)
- Angebote die nachgefasst werden sollten (7, 14, 30 Tage)
- Leads ohne Antwort (2, 5 Tage)
- Offene Tasks die eskalieren
- Eingehende Mails ohne Bearbeitung
- Unbekannte Kunden mit mehrfacher Kontaktaufnahme (Leads erkennen)
- WhatsApp/Instagram-Nachrichten (wenn aktiv)
- Proaktiver Tagesstart-Briefing (morgens 07:30)

Jede erkannte Situation erzeugt entweder:
a) Einen automatischen Task in tasks.db
b) Eine Push-Benachrichtigung via ntfy
c) Einen Eintrag im Runtime-Log für KIRA
"""
import json, sqlite3, logging
from pathlib import Path
from datetime import datetime, date, timedelta

try:
    from activity_log import log as _alog
except Exception:
    def _alog(*a, **k): pass

try:
    from runtime_log import elog as _elog
except Exception:
    def _elog(*a, **k): return ""

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"
KUNDEN_DB     = KNOWLEDGE_DIR / "kunden.db"
MAIL_INDEX_DB = KNOWLEDGE_DIR / "mail_index.db"
CONFIG_FILE   = SCRIPTS_DIR / "config.json"

log = logging.getLogger("kira_proaktiv")
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter('%(asctime)s [kira_proaktiv] %(levelname)s: %(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.INFO)

# Status-Datei: verhindert Spam-Aktionen (gleiche Aktion nicht 2x am Tag)
SCAN_STATE_FILE = KNOWLEDGE_DIR / "proaktiv_state.json"


# ── Scan-State ────────────────────────────────────────────────────────────────
def _load_state() -> dict:
    try:
        if SCAN_STATE_FILE.exists():
            return json.loads(SCAN_STATE_FILE.read_text('utf-8'))
    except Exception:
        pass
    return {}


def _save_state(state: dict):
    try:
        SCAN_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), 'utf-8')
    except Exception:
        pass


def _already_done(state: dict, key: str, ttl_hours: int = 24) -> bool:
    """Prüft ob diese Aktion heute schon durchgeführt wurde."""
    if key not in state:
        return False
    try:
        ts = datetime.fromisoformat(state[key])
        return (datetime.now() - ts).total_seconds() < ttl_hours * 3600
    except Exception:
        return False


def _mark_done(state: dict, key: str):
    state[key] = datetime.now().isoformat()


# ── Push-Notification ─────────────────────────────────────────────────────────
def _push(title: str, msg: str, priority: str = "default"):
    try:
        config = json.loads(CONFIG_FILE.read_text('utf-8'))
        ntfy = config.get("ntfy", {})
        if not ntfy.get("aktiv"):
            return
        # Arbeitszeit-Check
        az_von = ntfy.get("arbeitszeit_von", "06:00")
        az_bis = ntfy.get("arbeitszeit_bis", "20:00")
        now_t = datetime.now().strftime("%H:%M")
        if ntfy.get("arbeitszeit_aktiv") and not (az_von <= now_t <= az_bis):
            return
        if ntfy.get("urlaub_modus"):
            return
        topic = ntfy.get("topic_name", "")
        server = ntfy.get("server", "https://ntfy.sh").rstrip("/")
        if not topic:
            return
        import urllib.request
        req = urllib.request.Request(
            f"{server}/{topic}",
            data=msg.encode('utf-8'),
            headers={"Title": title, "Priority": priority},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        log.debug(f"Push fehlgeschlagen: {e}")


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
def _task_exists(db, key: str) -> bool:
    """Prüft ob ein auto-generierter Task mit diesem Key schon existiert."""
    row = db.execute(
        "SELECT id FROM tasks WHERE message_id=? AND status NOT IN ('erledigt','ignorieren')",
        (key,)
    ).fetchone()
    return row is not None


def _create_auto_task(db, typ: str, titel: str, zusammenfassung: str,
                      empfohlene_aktion: str, prioritaet: str,
                      kunden_email: str = "", key: str = ""):
    """Erstellt einen automatisch generierten Task (Duplikat-sicher via key)."""
    if key and _task_exists(db, key):
        return False
    try:
        db.execute("""
            INSERT INTO tasks
            (typ, kategorie, titel, zusammenfassung, beschreibung,
             kunden_email, empfohlene_aktion, konto,
             status, prioritaet, antwort_noetig, message_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            typ, "Kira-Proaktiv", titel[:200], zusammenfassung[:500],
            zusammenfassung[:2000], kunden_email,
            empfohlene_aktion[:300], "kira-auto",
            "offen", prioritaet, 0, key
        ))
        db.commit()
        return True
    except Exception as e:
        log.debug(f"Task-Erstellung fehlgeschlagen: {e}")
        return False


# ── Scan 1: Überfällige Rechnungen ───────────────────────────────────────────
def scan_ueberfaellige_rechnungen(db, state: dict) -> list:
    """Scannt offene Ausgangsrechnungen auf Überfälligkeit."""
    aktionen = []
    today = date.today()
    try:
        rows = db.execute("""
            SELECT id, re_nummer, datum, kunde_name, kunde_email, betrag_brutto
            FROM ausgangsrechnungen
            WHERE status='offen' AND datum IS NOT NULL
            ORDER BY datum ASC
        """).fetchall()
    except Exception:
        return []

    for r in rows:
        try:
            re_datum = datetime.strptime(str(r['datum'])[:10], "%Y-%m-%d").date()
            tage_offen = (today - re_datum).days
        except Exception:
            continue

        if tage_offen < 14:
            continue

        prio = "hoch" if tage_offen >= 30 else "mittel"
        stufe = "3. Mahnstufe" if tage_offen >= 45 else ("2. Mahnstufe" if tage_offen >= 30 else "Zahlungserinnerung")
        key = f"re-faellig-{r['re_nummer']}-{stufe.replace(' ','')}"

        if not _already_done(state, key, ttl_hours=72):
            titel = f"{stufe}: {r['re_nummer']} — {r['kunde_name'] or r['kunde_email'] or '?'}"
            zusammen = (f"Rechnung {r['re_nummer']} ist {tage_offen} Tage offen. "
                       f"Betrag: {r['betrag_brutto'] or 0:,.2f} EUR. "
                       f"Empfehlung: {stufe} senden.")
            created = _create_auto_task(
                db, "Mahnung", titel, zusammen,
                f"{stufe} erstellen und per Mail senden",
                prio, r['kunde_email'] or "", key
            )
            if created:
                _mark_done(state, key)
                aktionen.append({"typ": "rechnung_faellig", "re_nummer": r['re_nummer'],
                                 "tage": tage_offen, "stufe": stufe, "prio": prio})
                _elog('system', 'proaktiv_rechnung_faellig',
                      f"Rechnung {r['re_nummer']} seit {tage_offen} Tagen offen",
                      source='kira_proaktiv', modul='kira_proaktiv', actor_type='system',
                      status='warnung', context_type='rechnung', context_id=r['re_nummer'])

    return aktionen


# ── Scan 2: Angebote die nachgefasst werden sollten ──────────────────────────
def scan_angebot_nachfass(db, state: dict) -> list:
    """Scannt offene Angebote auf fällige Nachfass-Aktionen."""
    aktionen = []
    today = date.today()
    try:
        config = json.loads(CONFIG_FILE.read_text('utf-8'))
        nf_cfg = config.get("nachfass", {})
        intervall_1 = nf_cfg.get("intervall_1_tage", 7)
        intervall_2 = nf_cfg.get("intervall_2_tage", 14)
        intervall_3 = nf_cfg.get("intervall_3_tage", 30)
    except Exception:
        intervall_1, intervall_2, intervall_3 = 7, 14, 30

    try:
        rows = db.execute("""
            SELECT id, a_nummer, datum, kunde_name, kunde_email, betrag_geschaetzt,
                   nachfass_count, naechster_nachfass
            FROM angebote WHERE status='offen'
            ORDER BY datum ASC
        """).fetchall()
    except Exception:
        return []

    for r in rows:
        naechster = r['naechster_nachfass'] or ""
        if naechster and naechster > str(today):
            continue  # noch nicht fällig

        try:
            ang_datum = datetime.strptime(str(r['datum'])[:10], "%Y-%m-%d").date()
            tage_offen = (today - ang_datum).days
        except Exception:
            continue

        nf_count = r['nachfass_count'] or 0
        if nf_count >= 3:
            continue  # bereits 3x nachgefasst

        # Fällig?
        grenzen = [intervall_1, intervall_2, intervall_3]
        if tage_offen < grenzen[nf_count]:
            continue

        key = f"ang-nachfass-{r['a_nummer']}-nf{nf_count+1}"
        if not _already_done(state, key, ttl_hours=48):
            titel = f"Nachfass {nf_count+1}/3: {r['a_nummer']} — {r['kunde_name'] or r['kunde_email'] or '?'}"
            betrag = f"{r['betrag_geschaetzt']:,.2f} EUR" if r['betrag_geschaetzt'] else "Betrag unbekannt"
            zusammen = (f"Angebot {r['a_nummer']} ist {tage_offen} Tage offen ({betrag}). "
                       f"Nachfass {nf_count+1} ist fällig.")
            created = _create_auto_task(
                db, "Nachfass", titel, zusammen,
                f"Höfliche Nachfass-Mail senden (Vorlage nutzen)",
                "mittel", r['kunde_email'] or "", key
            )
            if created:
                _mark_done(state, key)
                aktionen.append({"typ": "angebot_nachfass", "a_nummer": r['a_nummer'],
                                 "tage": tage_offen, "nachfass": nf_count+1})
                _elog('system', 'proaktiv_nachfass',
                      f"Angebot {r['a_nummer']} — Nachfass {nf_count+1} fällig",
                      source='kira_proaktiv', modul='kira_proaktiv', actor_type='system',
                      status='ok', context_type='angebot', context_id=r['a_nummer'])

    return aktionen


# ── Scan 3: Leads ohne Antwort ────────────────────────────────────────────────
def scan_leads_ohne_antwort(db, state: dict) -> list:
    """Prüft neue Lead-Anfragen auf fehlende Antworten."""
    aktionen = []
    today = date.today()
    try:
        config = json.loads(CONFIG_FILE.read_text('utf-8'))
        tage_grenze = config.get("aufgaben", {}).get("unanswered_check_days", 2)
    except Exception:
        tage_grenze = 2

    try:
        rows = db.execute("""
            SELECT id, betreff, kunden_email, datum_mail, kategorie
            FROM tasks
            WHERE kategorie IN ('Neue Lead-Anfrage', 'Antwort erforderlich')
              AND status='offen'
              AND antwort_noetig=1
              AND beantwortet=0
              AND datum_mail IS NOT NULL
            ORDER BY datum_mail ASC
        """).fetchall()
    except Exception:
        return []

    for r in rows:
        try:
            mail_datum = datetime.strptime(str(r['datum_mail'])[:10], "%Y-%m-%d").date()
            tage_warten = (today - mail_datum).days
        except Exception:
            continue

        if tage_warten < tage_grenze:
            continue

        key = f"lead-offen-{r['id']}-t{tage_warten // 2}"  # alle 2 Tage erinnern
        if not _already_done(state, key, ttl_hours=48):
            prio = "hoch" if tage_warten >= 5 else "mittel"
            titel = f"Lead wartet {tage_warten} Tage: {(r['betreff'] or '')[:60]}"
            zusammen = (f"Anfrage von {r['kunden_email'] or '?'} wartet seit {tage_warten} Tagen "
                       f"auf Antwort. Kategorie: {r['kategorie']}.")
            created = _create_auto_task(
                db, "Lead-Erinnerung", titel, zusammen,
                "Antwort verfassen und senden — Kunde könnte abspringen",
                prio, r['kunden_email'] or "",
                f"lead-erinnerung-{r['id']}"
            )
            if created:
                _mark_done(state, key)
                aktionen.append({"typ": "lead_offen", "task_id": r['id'], "tage": tage_warten})

    return aktionen


# ── Scan 4: Tagesstart-Briefing ───────────────────────────────────────────────
def scan_tagesstart_briefing(db, state: dict) -> dict:
    """
    Generiert morgens ein kompaktes Briefing für KIRA.
    Wird als Runtime-Log Event gespeichert damit KIRA es im Kontext hat.
    """
    now = datetime.now()
    briefing_key = f"tagesstart-{now.strftime('%Y-%m-%d')}"
    if _already_done(state, briefing_key, ttl_hours=20):
        return {}

    # Nur morgens zwischen 06:00 und 10:00
    if not (6 <= now.hour <= 10):
        return {}

    today_str = date.today().isoformat()
    briefing_teile = []

    try:
        # Offene Rechnungen
        re_offen = db.execute(
            "SELECT COUNT(*) FROM ausgangsrechnungen WHERE status='offen'"
        ).fetchone()[0]
        re_summe = db.execute(
            "SELECT COALESCE(SUM(betrag_brutto),0) FROM ausgangsrechnungen WHERE status='offen'"
        ).fetchone()[0]
        if re_offen:
            briefing_teile.append(f"Rechnungen offen: {re_offen} ({re_summe:,.2f} EUR)")

        # Angebote fällig
        ang_faellig = db.execute(
            "SELECT COUNT(*) FROM angebote WHERE status='offen' AND (naechster_nachfass IS NULL OR naechster_nachfass<=?)",
            (today_str,)
        ).fetchone()[0]
        if ang_faellig:
            briefing_teile.append(f"Angebote zum Nachfassen: {ang_faellig}")

        # Offene Tasks
        tasks_offen = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE status='offen'"
        ).fetchone()[0]
        if tasks_offen:
            briefing_teile.append(f"Offene Aufgaben: {tasks_offen}")

        # Neue Mails seit gestern
        if MAIL_INDEX_DB.exists():
            gestern = (date.today() - timedelta(days=1)).isoformat()
            neue_mails = sqlite3.connect(str(MAIL_INDEX_DB)).execute(
                "SELECT COUNT(*) FROM mails WHERE datum_iso >= ? AND folder LIKE '%INBOX%'",
                (gestern,)
            ).fetchone()[0]
            if neue_mails:
                briefing_teile.append(f"Neue Mails seit gestern: {neue_mails}")

    except Exception:
        pass

    if not briefing_teile:
        return {}

    briefing_text = "TAGESSTART-BRIEFING: " + " | ".join(briefing_teile)
    _elog('kira', 'tagesstart_briefing', briefing_text,
          source='kira_proaktiv', modul='kira_proaktiv', actor_type='system',
          status='ok')
    _push("Kira Tagesstart", briefing_text, priority="default")
    _mark_done(state, briefing_key)
    return {"briefing": briefing_text}


# ── Scan 5: Neue Kunden aus Mails erkennen ───────────────────────────────────
def scan_neue_kunden_erkennen(db, state: dict) -> list:
    """
    Erkennt potenzielle neue Kunden die noch nicht in kunden.db sind
    aber mehrfach über verschiedene Kanäle Kontakt hatten.
    """
    aktionen = []
    try:
        # Tasks mit kunden_email die noch nicht als Kunde erfasst sind
        rows = db.execute("""
            SELECT kunden_email, COUNT(*) as n, MIN(datum_mail) as erstkontakt, MAX(datum_mail) as letzter
            FROM tasks
            WHERE kunden_email != '' AND kunden_email IS NOT NULL
            GROUP BY kunden_email
            HAVING n >= 2
        """).fetchall()

        kdb = sqlite3.connect(str(KUNDEN_DB))
        for r in rows:
            email = r['kunden_email']
            key = f"neukunde-erkannt-{email}"
            if _already_done(state, key, ttl_hours=168):  # 1x pro Woche
                continue
            # Prüfen ob schon in kunden.db
            exists = kdb.execute(
                "SELECT 1 FROM interaktionen WHERE LOWER(kunden_email)=? LIMIT 1",
                (email.lower(),)
            ).fetchone()
            if not exists:
                _mark_done(state, key)
                aktionen.append({"typ": "neukunde", "email": email, "kontakte": r['n']})
        kdb.close()
    except Exception:
        pass
    return aktionen


# ── Haupt-Scan ────────────────────────────────────────────────────────────────
def run_proaktiver_scan() -> dict:
    """
    Führt alle Scans durch. Wird von mail_monitor.py alle 15 Min aufgerufen.
    Gibt Zusammenfassung aller ausgelösten Aktionen zurück.
    """
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        state = _load_state()
        ergebnisse = {}

        # Alle Scans ausführen
        re_faellig = scan_ueberfaellige_rechnungen(db, state)
        if re_faellig:
            ergebnisse['rechnungen_faellig'] = re_faellig
            _push("Kira: Offene Rechnungen",
                  f"{len(re_faellig)} Rechnung(en) überfällig",
                  priority="high")

        ang_nachfass = scan_angebot_nachfass(db, state)
        if ang_nachfass:
            ergebnisse['angebote_nachfass'] = ang_nachfass

        leads = scan_leads_ohne_antwort(db, state)
        if leads:
            ergebnisse['leads_offen'] = leads

        briefing = scan_tagesstart_briefing(db, state)
        if briefing:
            ergebnisse['tagesstart'] = briefing

        neue_kunden = scan_neue_kunden_erkennen(db, state)
        if neue_kunden:
            ergebnisse['neue_kunden'] = neue_kunden

        db.close()
        _save_state(state)

        if ergebnisse:
            _alog("Kira Proaktiv", "Scan", str(ergebnisse)[:200], "ok")
            _elog('system', 'proaktiv_scan', f"Scan: {len(ergebnisse)} Bereiche mit Aktionen",
                  source='kira_proaktiv', modul='kira_proaktiv', actor_type='system',
                  status='ok', result=json.dumps({k: len(v) if isinstance(v, list) else 1
                                                   for k, v in ergebnisse.items()},
                                                  ensure_ascii=False))

        return {"ok": True, "ergebnisse": ergebnisse}

    except Exception as e:
        log.error(f"Proaktiver Scan fehlgeschlagen: {e}")
        return {"ok": False, "error": str(e)}


# ── Channel-Adapter Framework ─────────────────────────────────────────────────
def verarbeite_kanal_eingang(
    kanal: str,
    absender: str,
    text: str,
    betreff: str = "",
    anhaenge: list = None,
    meta: dict = None,
) -> dict:
    """
    Universal-Eingang für alle Kanäle: Mail, WhatsApp, Instagram, Manuell.
    Nutzt denselben Classifier-Pfad mit kanal-spezifischem Kontext.

    kanal: "email" | "whatsapp" | "instagram" | "manuell" | "shop" | "telefon"

    Gibt zurück: {ok, kategorie, task_id, empfohlene_aktion, angebot_aktion}
    """
    try:
        from llm_classifier import classify_mail, extract_email
        meta = meta or {}

        # Kanal-spezifische Anpassungen
        if kanal == "whatsapp":
            betreff = betreff or f"WhatsApp: {text[:60]}"
        elif kanal == "instagram":
            betreff = betreff or f"Instagram DM: {text[:60]}"
        elif kanal == "manuell":
            betreff = betreff or f"Manuell: {text[:60]}"
        elif kanal == "telefon":
            betreff = betreff or f"Telefonnotiz: {text[:60]}"
        elif kanal == "shop":
            betreff = betreff or f"Shop-Bestellung: {text[:60]}"

        konto = meta.get("konto", "info@raumkult.eu")
        folder = meta.get("folder", "INBOX")

        result = classify_mail(
            konto=konto,
            absender=absender,
            betreff=betreff,
            text=text,
            anhaenge=anhaenge or [],
            folder=folder,
            is_sent=False,
            mail_datum=meta.get("datum", ""),
            kanal=kanal,
        )

        # Auto-Angebots-Aktion
        auto_aktion = {}
        if result.get("angebot_aktion"):
            from mail_monitor import _auto_angebot_aktion
            ke = extract_email(absender)
            auto_aktion = _auto_angebot_aktion(result, ke, betreff, meta.get("id", ""))

        # Task erstellen
        db = sqlite3.connect(str(TASKS_DB))
        task_id = None
        kategorie = result.get("kategorie", "Zur Kenntnis")
        skip = {"Ignorieren", "Newsletter / Werbung", "Abgeschlossen"}
        if kategorie not in skip:
            from mail_classifier import kategorie_to_task_typ
            typ = kategorie_to_task_typ(kategorie)
            try:
                db.execute("""
                    INSERT INTO tasks
                    (typ, kategorie, titel, zusammenfassung, beschreibung,
                     kunden_email, empfohlene_aktion, kategorie_grund,
                     betreff, konto, status, prioritaet, antwort_noetig,
                     message_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    typ, kategorie, betreff[:200],
                    result.get("zusammenfassung", ""),
                    text[:2000],
                    extract_email(absender),
                    result.get("empfohlene_aktion", ""),
                    result.get("kategorie_grund", ""),
                    betreff, kanal,
                    "offen", result.get("prioritaet", "mittel"),
                    1 if result.get("antwort_noetig") else 0,
                    f"{kanal}-{meta.get('id','')}"
                ))
                db.commit()
                task_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            except Exception:
                pass

        db.close()

        _elog('system', 'kanal_eingang', f"[{kanal}] {kategorie}: {betreff[:60]}",
              source='kira_proaktiv', modul='kira_proaktiv', actor_type='system',
              status='ok', context_type='kanal', context_id=kanal,
              result=json.dumps({"kategorie": kategorie, "task_id": task_id,
                                  "angebot_aktion": auto_aktion}, ensure_ascii=False)[:500])

        return {
            "ok": True,
            "kanal": kanal,
            "kategorie": kategorie,
            "task_id": task_id,
            "empfohlene_aktion": result.get("empfohlene_aktion", ""),
            "angebot_aktion": auto_aktion,
            "zusammenfassung": result.get("zusammenfassung", ""),
        }

    except Exception as e:
        log.error(f"Kanal-Eingang [{kanal}] fehlgeschlagen: {e}")
        return {"ok": False, "kanal": kanal, "error": str(e)}


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print("=" * 60)
    print("kira_proaktiv.py — Autonomer Business-Scanner")
    print("=" * 60)
    result = run_proaktiver_scan()
    if result.get("ok"):
        erg = result.get("ergebnisse", {})
        if erg:
            print(f"\n{len(erg)} Bereiche mit Aktionen:")
            for k, v in erg.items():
                n = len(v) if isinstance(v, list) else 1
                print(f"  {k}: {n} Aktion(en)")
        else:
            print("\nKeine Aktionen nötig — alles im grünen Bereich.")
    else:
        print(f"\nFehler: {result.get('error')}")
        sys.exit(1)
