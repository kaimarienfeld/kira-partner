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
import json, os, sqlite3, logging, threading
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
_state_lock = threading.Lock()  # Thread-Safety innerhalb desselben Prozesses


# ── Scan-State ────────────────────────────────────────────────────────────────
def _load_state() -> dict:
    with _state_lock:
        try:
            if SCAN_STATE_FILE.exists():
                return json.loads(SCAN_STATE_FILE.read_text('utf-8'))
        except Exception:
            pass
        return {}


def _save_state(state: dict):
    """Atomischer Schreibvorgang via temp-Datei + os.replace — verhindert Korruption."""
    with _state_lock:
        try:
            tmp_path = SCAN_STATE_FILE.with_suffix('.json.tmp')
            tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), 'utf-8')
            os.replace(str(tmp_path), str(SCAN_STATE_FILE))
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
        # Priorität aus Config übernehmen (falls gesetzt), sonst Argument-Default
        effective_priority = ntfy.get("prioritaet", priority) or priority
        import urllib.request
        req = urllib.request.Request(
            f"{server}/{topic}",
            data=msg.encode('utf-8'),
            headers={"Title": title, "Priority": effective_priority},
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
    Zeitfenster + aktiv-Toggle aus kira_proaktiv-Einstellungen.
    """
    try:
        _cfg_b = json.loads(CONFIG_FILE.read_text('utf-8')).get("kira_proaktiv", {})
        if not _cfg_b.get("morgen_briefing_aktiv", True):
            return {}
        _brief_uhr = _cfg_b.get("morgen_briefing_uhrzeit", "07:00")
        _brief_h, _brief_m = (int(x) for x in _brief_uhr.split(":"))
    except Exception:
        _brief_h, _brief_m = 7, 0

    now = datetime.now()
    briefing_key = f"tagesstart-{now.strftime('%Y-%m-%d')}"
    if _already_done(state, briefing_key, ttl_hours=20):
        return {}

    # Zeitfenster: ab konfigurierter Uhrzeit, 3h Zeitraum
    start_min = _brief_h * 60 + _brief_m
    now_min = now.hour * 60 + now.minute
    if not (start_min <= now_min <= start_min + 180):
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

    try:
        # Kira-Entwürfe zur Freigabe
        pending_mails = db.execute(
            "SELECT COUNT(*) FROM mail_approve_queue WHERE status='pending'"
        ).fetchone()[0]
        if pending_mails:
            briefing_teile.append(f"Kira-Entwürfe zur Freigabe: {pending_mails}")
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


def scan_angebot_followup_vorgang(db, state: dict) -> list:
    """
    Scan 7 (Paket 4, session-oo): Angebote-Vorgaenge die seit > 7 Tagen auf Antwort warten.
    Erstellt Mail-Entwurf in mail_approve_queue und Stufe-B-Signal.
    """
    aktionen = []
    try:
        from case_engine import get_open_vorgaenge
        vorgaenge = get_open_vorgaenge(typ="angebot", limit=20)
    except Exception:
        return []

    now = datetime.now()
    for v in vorgaenge:
        if v.get("status") != "angebot_versendet":
            continue
        try:
            aktualisiert = datetime.fromisoformat(str(v["aktualisiert_am"])[:19])
            tage_alt = (now - aktualisiert).days
        except Exception:
            continue
        if tage_alt < 7:
            continue

        key = f"angebot-followup-vorgang-{v['id']}-{tage_alt // 7}"
        if _already_done(state, key, ttl_hours=48):
            continue

        email      = v.get("kunden_email", "")
        name       = v.get("kunden_name") or email or "?"
        titel      = v.get("titel", "Angebot")
        vorgang_nr = v.get("vorgang_nr", "")

        # Mail-Entwurf in approve_queue erstellen
        try:
            betreff    = f"Nachfass: {titel}"
            body_text  = (
                f"Sehr geehrte(r) {name},\n\n"
                f"ich melde mich bezueglich unserem Angebot {vorgang_nr} ({titel}).\n"
                f"Das Angebot liegt nun seit {tage_alt} Tagen bei Ihnen vor — "
                f"haben Sie Rueckfragen oder kann ich Ihnen weiterhelfen?\n\n"
                f"Mit freundlichen Gruessen\nKai Marienfeld\nrauMKult Sichtbeton"
            )
            db.execute("""
                INSERT INTO mail_approve_queue
                    (an, betreff, body_plain, vorgang_id, erstellt_von, status, ablauf_am)
                VALUES (?,?,?,?,'kira_proaktiv','pending',
                        datetime('now','+3 days'))
            """, (email, betreff, body_text, v["id"]))
            db.commit()
        except Exception:
            pass

        # Stufe-B-Signal
        try:
            from case_engine import kira_notify
            kira_notify(
                titel=f"Angebot-Nachfass: {name}",
                nachricht=f"{vorgang_nr} seit {tage_alt} Tagen ohne Antwort",
                stufe="B", modul="kira_proaktiv", typ="angebot_followup",
                vorgang_id=v["id"],
                cooldown_key=f"ang-nachfass-{v['id']}", cooldown_hours=48,
            )
        except Exception:
            pass

        _mark_done(state, key)
        aktionen.append({"vorgang_id": v["id"], "vorgang_nr": vorgang_nr,
                         "tage": tage_alt, "email": email})
        _elog('system', 'angebot_followup_draft',
              f"Angebot {vorgang_nr} seit {tage_alt} Tagen — Mail-Entwurf erstellt",
              source='kira_proaktiv', modul='kira_proaktiv', actor_type='system', status='ok')

    return aktionen


def scan_mahnung_eskalation(db, state: dict) -> list:
    """
    Scan 8 (Paket 4, session-oo): Mahnungs-Vorgaenge die seit > 14 Tagen offen sind.
    Erstellt Stufe-B-Signal fuer User-Entscheidung.
    """
    aktionen = []
    try:
        from case_engine import get_open_vorgaenge
        vorgaenge = get_open_vorgaenge(typ="mahnung", limit=20)
    except Exception:
        return []

    now = datetime.now()
    for v in vorgaenge:
        if v.get("status") not in ("mahnung_versendet", "mahnung_1"):
            continue
        try:
            aktualisiert = datetime.fromisoformat(str(v["aktualisiert_am"])[:19])
            tage_alt = (now - aktualisiert).days
        except Exception:
            continue
        if tage_alt < 14:
            continue

        key = f"mahnung-eskalation-{v['id']}-{tage_alt // 14}"
        if _already_done(state, key, ttl_hours=72):
            continue

        name       = v.get("kunden_name") or v.get("kunden_email") or "?"
        vorgang_nr = v.get("vorgang_nr", "")

        try:
            from case_engine import kira_notify
            kira_notify(
                titel=f"Mahnung eskalieren: {name}",
                nachricht=f"{vorgang_nr} seit {tage_alt} Tagen ohne Reaktion. Nächste Stufe?",
                stufe="B", modul="kira_proaktiv", typ="mahnung_eskalation",
                vorgang_id=v["id"],
                cooldown_key=f"mahnung-{v['id']}", cooldown_hours=72,
            )
        except Exception:
            pass

        _mark_done(state, key)
        aktionen.append({"vorgang_id": v["id"], "vorgang_nr": vorgang_nr,
                         "tage": tage_alt, "name": name})
        _elog('system', 'mahnung_eskalation_signal',
              f"Mahnung {vorgang_nr} seit {tage_alt} Tagen — Eskalations-Signal erstellt",
              source='kira_proaktiv', modul='kira_proaktiv', actor_type='system', status='ok')

    return aktionen


def scan_autonomy_decision(db, state: dict) -> list:
    """
    Scan 9 — Autonomy-Decision-Loop (Paket 4, session-oo).
    Laesst Kira alle offenen Vorgaenge analysieren und schlaegt naechste Aktionen vor.
    TTL: 60 Minuten.
    """
    if _already_done(state, "autonomy_decision", ttl_hours=1):
        return []

    try:
        from case_engine import get_open_vorgaenge, get_valid_transitions
        vorgaenge = get_open_vorgaenge(limit=15)
    except Exception:
        return []

    if not vorgaenge:
        return []

    # Kompakte Vorgang-Liste fuer LLM
    vorgang_liste = ""
    for v in vorgaenge[:10]:
        vorgang_liste += (
            f"- ID={v['id']} | {v['vorgang_nr']} | Typ={v['typ']} | "
            f"Status={v['status']} | Kunde={v.get('kunden_name') or v.get('kunden_email','?')} | "
            f"Titel={v.get('titel','')[:60]}\n"
        )

    prompt = (
        "Analysiere diese offenen Vorgaenge und schlage fuer jeden die wichtigste naechste Aktion vor.\n"
        "Antworte als JSON-Liste: [{\"vorgang_id\": N, \"aktion\": \"...\", \"konfidenz\": 0.0-1.0}]\n"
        "Beispiel-Aktionen: 'Nachfass-Mail senden', 'Mahnung erstellen', 'Angebot nachfassen', 'Termin vereinbaren'\n\n"
        f"Vorgaenge:\n{vorgang_liste}\n\n"
        "Nur Aktionen vorschlagen die wirklich sinnvoll sind. Konfidenz < 0.5 = weglassen."
    )

    try:
        from kira_llm import chat as _kira_chat
        import json as _json
        result = _kira_chat(prompt)
        text = (result.get("text") or "").strip()
        # JSON aus Antwort extrahieren
        start = text.find("[")
        end   = text.rfind("]") + 1
        if start < 0 or end <= start:
            return []
        vorschlaege = _json.loads(text[start:end])
    except Exception:
        return []

    aktionen = []
    for vs in vorschlaege:
        vid  = vs.get("vorgang_id")
        aktion = vs.get("aktion", "")
        konfidenz = float(vs.get("konfidenz", 0))
        if not vid or not aktion or konfidenz < 0.5:
            continue

        # Entscheidungsstufe anhand Konfidenz
        if konfidenz >= 0.85:
            stufe = "A"  # Stumm: Task erstellen
        elif konfidenz >= 0.60:
            stufe = "B"  # Toast
        else:
            stufe = "C"  # Modal

        if stufe == "A":
            # Task automatisch erstellen
            try:
                db.execute("""
                    INSERT INTO tasks (kategorie, titel, status, kunden_email, konfidenz, vorgang_id)
                    SELECT 'vorgang_aktion', ?, 'offen', kunden_email, ?, id
                    FROM vorgaenge WHERE id=?
                """, (f"Aktion: {aktion}", konfidenz, vid))
                db.commit()
            except Exception:
                pass
        else:
            # Signal erstellen
            try:
                from case_engine import kira_notify
                kira_notify(
                    titel=f"Kira-Vorschlag: {aktion}",
                    nachricht=f"Vorgang {vid} | Konfidenz: {konfidenz:.0%}",
                    stufe=stufe, modul="kira_proaktiv", typ="autonomy_decision",
                    vorgang_id=vid,
                    cooldown_key=f"autonomy-{vid}", cooldown_hours=24,
                )
            except Exception:
                pass

        aktionen.append({"vorgang_id": vid, "aktion": aktion,
                         "konfidenz": konfidenz, "stufe": stufe})
        _elog('system', 'autonomy_vorschlag',
              f"Vorgang {vid}: {aktion} (Konfidenz {konfidenz:.0%}, Stufe {stufe})",
              source='kira_proaktiv', modul='kira_proaktiv', actor_type='kira_autonom',
              status='ok')

    if aktionen:
        _mark_done(state, "autonomy_decision")
    return aktionen


def scan_tages_memory_summary(db, state: dict) -> dict:
    """
    Taegliche Memory-Summary (Paket 3, session-oo).
    Fasst alle Kira-Konversationen des Tages zusammen, speichert in wissen_regeln.
    TTL: 23h — laeuft hoechstens einmal pro Tag.
    """
    state_key = "tages_summary"
    if _already_done(state, state_key, ttl_hours=23):
        return {}

    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        rows = db.execute(
            "SELECT rolle, nachricht FROM kira_konversationen "
            "WHERE erstellt_am >= ? ORDER BY id",
            (today_str + "T00:00:00",)
        ).fetchall()
    except Exception:
        return {}

    if len(rows) < 4:
        return {}

    conv_text = ""
    for r in rows:
        rolle   = "Kai" if r["rolle"] == "user" else "Kira"
        snippet = (r["nachricht"] or "")[:200].replace('\n', ' ')
        conv_text += f"{rolle}: {snippet}\n"
        if len(conv_text) > 3000:
            conv_text = conv_text[:3000] + "..."
            break

    try:
        from kira_llm import chat as _kira_chat
        prompt = (
            f"Fasse die 3 wichtigsten Entscheidungen und offenen Punkte aus diesen "
            f"Gespraechen vom {today_str} zusammen (max 3 Stichpunkte, je max 80 Zeichen):\n\n"
            f"{conv_text}\n\nFormat: - Punkt 1\n- Punkt 2\n- Punkt 3"
        )
        result = _kira_chat(prompt)
        summary_text = (result.get("text") or "").strip()
        if not summary_text:
            return {}
    except Exception:
        return {}

    try:
        db.execute("""
            INSERT INTO wissen_regeln (titel, inhalt, kategorie, erstellt_am, quelle)
            VALUES (?, ?, 'tages_summary', ?, 'kira_proaktiv')
        """, (f"Tages-Summary {today_str}", summary_text, datetime.now().isoformat()))
        db.commit()
        _mark_done(state, state_key)
        _elog('system', 'tages_summary_erstellt', f"Memory-Summary {today_str} gespeichert",
              source='kira_proaktiv', modul='kira_proaktiv', actor_type='system', status='ok')
        return {"datum": today_str, "summary": summary_text[:100]}
    except Exception:
        return {}


def scan_offene_eingangsrechnungen(db, state: dict) -> list:
    """Erinnert an offene Eingangsrechnungen die bald oder bereits fällig sind."""
    today = date.today()
    today_str = today.isoformat()
    ergebnisse = []
    try:
        rows = db.execute("""
            SELECT id, rechnungsnummer, gegenpartei, gegenpartei_email, betrag,
                   datum, faelligkeit_datum, betreff
            FROM geschaeft
            WHERE typ IN ('eingangsrechnung','zahlungserinnerung')
              AND (bewertung IS NULL OR bewertung != 'erledigt')
            ORDER BY faelligkeit_datum ASC, datum ASC
        """).fetchall()
    except Exception:
        return []

    for r in rows:
        gid = r['id']
        state_key = f"eingangsre_erinnerung_{gid}"
        last = state.get(state_key, {})
        last_datum = last.get("datum", "")
        # Max. 1x täglich pro Eingangsrechnung erinnern
        if last_datum == today_str:
            continue

        partner = r['gegenpartei'] or r['gegenpartei_email'] or 'Unbekannt'
        re_nr   = r['rechnungsnummer'] or 'ohne Nummer'
        faell   = (r['faelligkeit_datum'] or '')[:10]
        betrag  = r['betrag']
        betrag_str = f"{betrag:,.2f} EUR" if betrag else "Betrag unbekannt"

        # Klassifikation: wie dringend?
        if faell:
            try:
                faell_dt = date.fromisoformat(faell)
                tage_bis = (faell_dt - today).days
            except Exception:
                tage_bis = None
        else:
            try:
                datum_dt = date.fromisoformat((r['datum'] or today_str)[:10])
                tage_bis = None
                # Ohne Fälligkeit: Erinnern nach 30 Tagen
                alter = (today - datum_dt).days
                if alter < 30:
                    continue
            except Exception:
                continue

        # Nur erinnern wenn fällig in <7 Tagen oder bereits überfällig
        if tage_bis is not None and tage_bis > 7:
            continue

        if tage_bis is not None and tage_bis < 0:
            prioritaet = "high"
            status_str = f"ÜBERFÄLLIG seit {abs(tage_bis)} Tagen"
        elif tage_bis is not None:
            prioritaet = "default"
            status_str = f"fällig in {tage_bis} Tag(en)"
        else:
            prioritaet = "default"
            status_str = "seit >30 Tagen offen (kein Fälligkeitsdatum)"

        msg = f"{partner} | {re_nr} | {betrag_str} | {status_str}"
        ergebnisse.append({"id": gid, "partner": partner, "re_nr": re_nr,
                           "betrag": betrag_str, "status": status_str})
        state[state_key] = {"datum": today_str, "partner": partner}
        # Runtime-Log-Eintrag
        _elog('kira', 'eingangsrechnung_erinnerung', msg,
              source='kira_proaktiv', modul='kira_proaktiv',
              actor_type='kira_autonom', status='ok')

    if ergebnisse:
        _save_state(state)
        _push(
            f"Kira: {len(ergebnisse)} Eingangsrechnung(en) offen",
            "\n".join(e["partner"] + " — " + e["status"] for e in ergebnisse[:3]),
            priority="default"
        )
    return ergebnisse


def scan_auto_backup(state: dict) -> dict:
    """Tägliches Auto-Backup von config.json + tasks.db + mail_index.db (session-tt)."""
    try:
        cfg = json.loads(CONFIG_FILE.read_text('utf-8'))
        backup_cfg = cfg.get('backup', {})
        if not backup_cfg.get('aktiv', False):
            return {}
    except Exception:
        return {}

    if _already_done(state, "auto_backup", ttl_hours=23):
        return {}

    try:
        import shutil as _sh, sqlite3 as _sq_bk
        backup_dir = Path(backup_cfg.get('pfad', '') or '') if backup_cfg.get('pfad') else KNOWLEDGE_DIR / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y-%m-%d_%H-%M')
        backed = []
        # config.json
        if (SCRIPTS_DIR / 'config.json').exists():
            _sh.copy2(str(SCRIPTS_DIR / 'config.json'), str(backup_dir / f'{ts}_config.json'))
            backed.append('config.json')
        # SQLite DBs via .backup() API
        for _db_name in ['tasks.db', 'mail_index.db']:
            _src = KNOWLEDGE_DIR / _db_name
            if not _src.exists(): continue
            _dst = backup_dir / f'{ts}_{_db_name}'
            try:
                sc = _sq_bk.connect(str(_src))
                dc = _sq_bk.connect(str(_dst))
                sc.backup(dc)
                sc.close(); dc.close()
                backed.append(_db_name)
            except Exception: pass
        # Alte Backups aufräumen
        keep_n = int(backup_cfg.get('keep_n', 7))
        for suffix in ['_config.json', '_tasks.db', '_mail_index.db']:
            files = sorted(f for f in backup_dir.iterdir() if f.is_file() and f.name.endswith(suffix))
            for old in files[:-keep_n]:
                try: old.unlink()
                except: pass
        _elog('system', 'backup_erstellt', f'Auto-Backup: {", ".join(backed)} → {backup_dir.name}/',
              source='kira_proaktiv', modul='kira_proaktiv', actor_type='system', status='ok')
        _mark_done(state, "auto_backup")
        return {'gesichert': backed, 'pfad': str(backup_dir), 'ts': ts}
    except Exception as e:
        _elog('system', 'backup_fehler', str(e), source='kira_proaktiv', status='fehler')
        return {}


def scan_lexware_zahlungsabgleich(db, state: dict) -> dict:
    """Gleicht Lexware-Belege (paid/paidoff) mit offenen Ausgangsrechnungen ab (alle 6h)."""
    if _already_done(state, "lexware_zahlungsabgleich", ttl_hours=6):
        return {}
    try:
        rows = db.execute("""
            SELECT a.id, a.re_nummer, lb.status as lx_status
            FROM ausgangsrechnungen a
            JOIN lexware_belege lb ON lb.nummer = a.re_nummer
            WHERE a.status = 'offen'
              AND lb.status IN ('paid', 'paidoff', 'sepadebit')
              AND lb.typ = 'invoice'
        """).fetchall()
        markiert = 0
        nummern = []
        for r in rows:
            db.execute("UPDATE ausgangsrechnungen SET status='bezahlt', bezahlt_am=datetime('now') WHERE id=?", (r["id"],))
            nummern.append(r["re_nummer"] or "?")
            markiert += 1
        if markiert > 0:
            db.commit()
            _elog('system', 'zahlungsabgleich',
                 f'{markiert} Rechnung(en) als bezahlt markiert: {", ".join(nummern[:5])}',
                 source='kira_proaktiv', modul='lexware', actor_type='system', status='ok')
        _mark_done(state, "lexware_zahlungsabgleich")
        return {"markiert": markiert, "nummern": nummern} if markiert > 0 else {}
    except Exception:
        return {}


# ── Scan 13: Offene Zusagen + Fällige Commitments ───────────────────────────
def scan_offene_zusagen(db, state: dict) -> list:
    """
    Zwei Teile:
    1) Fällige Commitments aus mail_commitments signalisieren
    2) Bald fällige Commitments als Vorwarnung
    """
    signale = []
    try:
        # Tabelle existiert?
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mail_commitments'").fetchall()]
        if "mail_commitments" not in tables:
            return signale

        heute = date.today().isoformat()

        # Teil 1: Überfällige + heute fällige Commitments
        rows = db.execute("""
            SELECT id, typ, text, datum_faellig, absender, betreff, erstellt_am
            FROM mail_commitments
            WHERE status='offen' AND datum_faellig IS NOT NULL AND datum_faellig <= ?
            ORDER BY datum_faellig
            LIMIT 20
        """, (heute,)).fetchall()

        for row in rows:
            row = dict(row)
            tage_ueber = (date.today() - date.fromisoformat(row["datum_faellig"])).days
            label = f"seit {tage_ueber} Tag(en) überfällig" if tage_ueber > 0 else "heute fällig"
            text_kurz = (row.get("text") or "")[:80]
            absender_kurz = (row.get("absender") or "").split("<")[0].strip()[:40]

            signale.append({
                "id": row["id"],
                "typ": row.get("typ", ""),
                "text": text_kurz,
                "absender": absender_kurz,
                "betreff": (row.get("betreff") or "")[:60],
                "datum_faellig": row["datum_faellig"],
                "label": label,
                "stufe": "B"
            })

            # Stufe-B Signal via kira_notify
            try:
                from case_engine import kira_notify
                kira_notify(
                    event_type="zusage_faellig",
                    titel=f"⏰ {text_kurz}" if text_kurz else f"⏰ Zusage an {absender_kurz}",
                    text=f"{label} — {row.get('betreff', '')}",
                    stufe="B",
                    cooldown_key=f"zusage_{row['id']}",
                    cooldown_h=12
                )
            except Exception:
                pass

        # Teil 2: Vorwarnungen (Erinnerungsdatum erreicht, aber noch nicht fällig)
        vorwarnungen = db.execute("""
            SELECT id, typ, text, datum_faellig, datum_erinnerung, absender, betreff
            FROM mail_commitments
            WHERE status='offen' AND datum_erinnerung IS NOT NULL
              AND datum_erinnerung <= ? AND (datum_faellig IS NULL OR datum_faellig > ?)
            ORDER BY datum_erinnerung
            LIMIT 10
        """, (heute, heute)).fetchall()

        for row in vorwarnungen:
            row = dict(row)
            text_kurz = (row.get("text") or "")[:80]
            signale.append({
                "id": row["id"],
                "typ": row.get("typ", ""),
                "text": text_kurz,
                "datum_faellig": row.get("datum_faellig"),
                "label": f"fällig am {row.get('datum_faellig', '?')}",
                "stufe": "A"
            })

        if signale:
            _elog('system', 'zusagen_scan',
                  f"{len(signale)} offene Zusage(n) gefunden ({len(rows)} fällig, {len(vorwarnungen)} Vorwarnungen)",
                  source='kira_proaktiv', modul='zusagen', actor_type='system', status='ok')

        _mark_done(state, "offene_zusagen")
    except Exception as e:
        log.error(f"scan_offene_zusagen: {e}")
    return signale


# ── Haupt-Scan ────────────────────────────────────────────────────────────────
def run_proaktiver_scan() -> dict:
    """
    Führt alle Scans durch. Wird von mail_monitor.py alle 15 Min aufgerufen.
    Gibt Zusammenfassung aller ausgelösten Aktionen zurück.
    """
    # Proaktiven Scan nur ausführen wenn in Einstellungen aktiviert
    try:
        _cfg = json.loads(CONFIG_FILE.read_text('utf-8'))
        if not _cfg.get("kira_proaktiv", {}).get("aktiv", True):
            return {"ergebnisse": {}, "skipped": "proaktiv_deaktiviert"}
    except Exception:
        pass

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

        # Scan 6: Taegliche Memory-Summary (Paket 3, session-oo)
        mem_summary = scan_tages_memory_summary(db, state)
        if mem_summary:
            ergebnisse['tages_memory_summary'] = mem_summary

        # Scan 7: Angebot-Followup via Vorgang-Layer (Paket 4, session-oo)
        angebot_followup = scan_angebot_followup_vorgang(db, state)
        if angebot_followup:
            ergebnisse['angebot_followup_vorgang'] = angebot_followup

        # Scan 8: Mahnung-Eskalation (Paket 4, session-oo)
        mahnung_esk = scan_mahnung_eskalation(db, state)
        if mahnung_esk:
            ergebnisse['mahnung_eskalation'] = mahnung_esk

        # Scan 9: Autonomy-Decision-Loop (Paket 4, session-oo)
        autonomy = scan_autonomy_decision(db, state)
        if autonomy:
            ergebnisse['autonomy_decision'] = autonomy

        # Scan 10: Offene Eingangsrechnungen (session-qq)
        eingang_offen = scan_offene_eingangsrechnungen(db, state)
        if eingang_offen:
            ergebnisse['eingangsrechnungen_offen'] = eingang_offen

        # Scan 11: Auto-Backup (session-tt)
        backup_result = scan_auto_backup(state)
        if backup_result:
            ergebnisse['auto_backup'] = backup_result

        # Scan 12: Lexware-Zahlungsabgleich (alle 6h)
        zahl_abgl = scan_lexware_zahlungsabgleich(db, state)
        if zahl_abgl:
            ergebnisse['lexware_zahlungsabgleich'] = zahl_abgl
            if zahl_abgl.get('markiert', 0) > 0:
                _push("Kira: Zahlungsabgleich",
                      f'{zahl_abgl["markiert"]} Rechnung(en) automatisch als bezahlt markiert')

        # Scan 13: Offene Zusagen + fällige Commitments
        zusagen = scan_offene_zusagen(db, state)
        if zusagen:
            ergebnisse['offene_zusagen'] = zusagen
            n_faellig = len([s for s in zusagen if s.get("stufe") == "B"])
            if n_faellig:
                _push("Kira: Offene Zusagen",
                      f"{n_faellig} Zusage(n) fällig oder überfällig")

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

        # Signal für Activity-Drawer
        try:
            from case_engine import kira_notify
            kira_notify(
                titel=f"{kanal.title()}: {kategorie}",
                nachricht=f"Von {absender[:30]} — {betreff[:60]}",
                stufe="B", modul="kira_proaktiv", typ=f"kanal_{kanal}",
                cooldown_key=f"kanal-{kanal}-{meta.get('id','')}", cooldown_hours=24,
            )
        except Exception:
            pass

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
