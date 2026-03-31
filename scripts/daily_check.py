#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rauMKult® Daily Check v4
- Neue Mails scannen und mit mail_classifier klassifizieren
- Unbeantwortete Mails -> Tasks anlegen (via rebuild_all Logik)
- Erinnerungen für offene Tasks
- ntfy.sh + Toast Notifications
- Inkrementelles Update (kein vollständiger Rebuild)
"""
import json, sqlite3, re, subprocess, sys
from pathlib import Path
from datetime import datetime, timedelta
from html.parser import HTMLParser

try:
    from runtime_log import elog as _elog
except Exception:
    def _elog(*a, **k): return ""

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
COWORK_DIR    = SCRIPTS_DIR.parent / "cowork"
STATUS_FILE   = KNOWLEDGE_DIR / "daily_check_status.json"
COWORK_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(SCRIPTS_DIR))
from task_manager import get_due_reminders, increment_reminder, load_config
from llm_classifier import classify_mail, extract_email, is_system_sender, kategorie_to_task_typ
from llm_response_gen import generate_draft

_cfg_dc = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
_archiv_pfad = _cfg_dc.get("mail_archiv", {}).get("pfad", "").strip()
ARCHIV_ROOT = Path(_archiv_pfad) / "Archiv" if _archiv_pfad else Path(
    r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\Archiv"
)
_konten_dc = _cfg_dc.get("mail_archiv", {}).get("konten", [])
MAILBOXEN = (
    [k["email"].replace('@', '_').replace('.', '_').lower()
     for k in _konten_dc if k.get("aktiv", True) and k.get("email")]
    or ["anfrage_raumkult_eu","info_raumkult_eu","invoice_sichtbeton-cire_de",
        "kaimrf_rauMKultSichtbeton_onmicrosoft_com","shop_sichtbeton-cire_de"]
)
KONTO_LABEL = (
    {k["email"]: k.get("konto_label", k["email"].split("@")[0])
     for k in _konten_dc if k.get("aktiv", True) and k.get("email")}
    or {
        "anfrage@raumkult.eu":"anfrage","info@raumkult.eu":"info",
        "invoice@sichtbeton-cire.de":"invoice","shop@sichtbeton-cire.de":"shop",
        "kaimrf@rauMKultSichtbeton.onmicrosoft.com":"intern",
    }
)
EIGENE_DOMAINS = {"raumkult.eu","sichtbeton-cire.de","raumkultsichtbeton.onmicrosoft.com",
                  "invoicefetcher.email"}  # DATEV-Weiterleitung

# Generische Domains — kein cross-domain-Match sinnvoll
_GENERIC_SENT_DOMAINS = {
    "gmail.com","web.de","gmx.de","gmx.net","yahoo.com","yahoo.de",
    "outlook.com","hotmail.com","t-online.de","freenet.de","icloud.com",
    "live.com","posteo.de","protonmail.com","mailbox.org","aol.com",
}

TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"
KUNDEN_DB     = KNOWLEDGE_DIR / "kunden.db"
SENT_DB       = KNOWLEDGE_DIR / "sent_mails.db"
MAIL_INDEX_DB = KNOWLEDGE_DIR / "mail_index.db"

# ── Fortschritt für Nachklassifizierung (thread-safe dict) ───────────────────
_recheck_progress: dict = {
    "running": False, "finished": True,
    "gesamt": 0, "geprueft": 0, "tasks_erstellt": 0,
    "ignoriert": 0, "aktuell": "", "fehler": 0,
}

def get_recheck_progress() -> dict:
    return dict(_recheck_progress)


# ── HTML Helper ───────────────────────────────────────────────────────────────
class _P(HTMLParser):
    def __init__(self): super().__init__(); self.r=[]; self.s=False
    def handle_starttag(self,t,a):
        if t in('style','script','head'): self.s=True
        if t in('br','p','div','li','tr'): self.r.append('\n')
    def handle_endtag(self,t):
        if t in('style','script','head'): self.s=False
    def handle_data(self,d):
        if not self.s and d.strip(): self.r.append(d.strip())
    def text(self): return re.sub(r'\s+',' ',' '.join(self.r)).strip()

def h2t(html):
    if not html: return ""
    try: p=_P(); p.feed(html); return p.text()
    except: return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',html)).strip()


# ── Status ────────────────────────────────────────────────────────────────────
def load_status():
    if STATUS_FILE.exists():
        return json.loads(STATUS_FILE.read_text('utf-8'))
    return {"letzter_lauf":(datetime.now()-timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")}

def save_status(data):
    STATUS_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8')


def resolve_alias(email: str) -> str:
    """Löst E-Mail-Alias auf die Haupt-E-Mail auf (aus kunden_aliases in tasks.db)."""
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


def get_kunden_email(absender, an, folder):
    q = an if ("Gesendete" in folder or "Sent" in folder) else absender
    m = re.search(r'<([^>]+@[^>]+)>',q)
    email = m.group(1).lower() if m else q.lower()
    domain = email.split('@')[-1] if '@' in email else ''
    return None if domain in EIGENE_DOMAINS else email.strip()


# ── Neue Mails scannen ───────────────────────────────────────────────────────
def scan_new_mails(since_dt):
    new_mails = []
    for mbx in MAILBOXEN:
        mbx_path = ARCHIV_ROOT / mbx
        if not mbx_path.exists(): continue
        kl = next((v for k,v in KONTO_LABEL.items() if k.lower() in mbx.replace("_","@",1).lower()), mbx[:8])
        for folder_dir in mbx_path.iterdir():
            if not folder_dir.is_dir(): continue
            fn = folder_dir.name
            for mail_dir in folder_dir.iterdir():
                if not mail_dir.is_dir(): continue
                mj = mail_dir/"mail.json"
                if not mj.exists(): continue
                dn = mail_dir.name
                if len(dn)>=10:
                    try:
                        if datetime.strptime(dn[:10],"%Y-%m-%d") < since_dt - timedelta(days=1): continue
                    except: pass
                try: mail=json.loads(mj.read_text('utf-8'))
                except: continue
                ds = mail.get('datum','') or ''
                try: mdt=datetime.strptime(ds[:19],"%Y-%m-%d %H:%M:%S")
                except: continue
                if mdt <= since_dt: continue
                tp = h2t(mail.get('text','') or '')
                new_mails.append({
                    "konto": next((v for k,v in KONTO_LABEL.items() if k.lower() in (mail.get('konto','') or '').lower()), kl),
                    "betreff":mail.get('betreff','') or '','absender':mail.get('absender','') or '',
                    "an":mail.get('an','') or '','datum':ds,'message_id':mail.get('message_id',''),
                    "hat_anhaenge":bool(mail.get('hat_anhaenge')),'anhaenge':mail.get('anhaenge',[]),
                    "anhaenge_pfad":mail.get('anhaenge_pfad','') or '','text_plain':tp,
                    "folder":fn,'mail_folder_pfad':str(mail_dir),'mailbox':mbx,
                })
    return sorted(new_mails, key=lambda x: x['datum'])


# ── Mail-Nachklassifizierung aus mail_index.db ───────────────────────────────
def recheck_mails(seit_datum: str, bis_datum: str = None, dry_run: bool = False) -> dict:
    """
    Klassifiziert Mails aus mail_index.db, die noch keinen Task haben.

    seit_datum : "YYYY-MM-DD" (inklusiv)
    bis_datum  : "YYYY-MM-DD" oder None (default: heute)
    dry_run    : wenn True, nur zählen — keine Tasks schreiben
    Gibt Stats-Dict zurück: {gesamt, geprueft, tasks_erstellt, ignoriert, fehler}
    """
    global _recheck_progress
    _recheck_progress.update({
        "running": True, "finished": False,
        "gesamt": 0, "geprueft": 0, "tasks_erstellt": 0,
        "ignoriert": 0, "aktuell": "Initialisiere…", "fehler": 0,
    })

    if not bis_datum:
        bis_datum = datetime.now().strftime("%Y-%m-%d")
    seit_ts = seit_datum + " 00:00:00"
    bis_ts  = bis_datum  + " 23:59:59"

    if not MAIL_INDEX_DB.exists():
        _recheck_progress.update({"running": False, "finished": True,
                                   "aktuell": "FEHLER: mail_index.db nicht gefunden"})
        return {"fehler": 1}

    # ── 1. Kandidaten aus mail_index.db laden ─────────────────────────────────
    mail_db  = sqlite3.connect(str(MAIL_INDEX_DB))
    mail_db.row_factory = sqlite3.Row
    tasks_db = sqlite3.connect(str(TASKS_DB))
    tasks_db.row_factory = sqlite3.Row
    kunden_db = sqlite3.connect(str(KUNDEN_DB))
    sent_db   = sqlite3.connect(str(SENT_DB))

    kandidaten = mail_db.execute("""
        SELECT id, konto, konto_label, betreff, absender, an, datum,
               message_id, folder, hat_anhaenge, anhaenge,
               anhaenge_pfad, mail_folder_pfad, text_plain
        FROM mails
        WHERE folder NOT LIKE '%Gesendete%'
          AND folder NOT LIKE '%Sent%'
          AND datum >= ?
          AND datum <= ?
        ORDER BY datum ASC
    """, (seit_ts, bis_ts)).fetchall()
    mail_db.close()

    _recheck_progress["gesamt"] = len(kandidaten)
    if not kandidaten:
        _recheck_progress.update({"running": False, "finished": True,
                                   "aktuell": "Keine Mails im Zeitraum gefunden"})
        return {"gesamt": 0, "geprueft": 0, "tasks_erstellt": 0, "ignoriert": 0, "fehler": 0}

    # ── 2. Bereits vorhandene Tasks (message_id dedup) ────────────────────────
    existing_ids = {
        r[0] for r in tasks_db.execute(
            "SELECT message_id FROM tasks WHERE message_id IS NOT NULL AND message_id != ''"
        ).fetchall()
    }
    deleted_msgids: set = set()
    try:
        deleted_msgids = {
            r[0] for r in tasks_db.execute(
                "SELECT message_id FROM loeschhistorie "
                "WHERE message_id IS NOT NULL AND message_id != ''"
            ).fetchall()
        }
    except Exception:
        pass

    # ── 3. Gesendete-Index (für "schon beantwortet?" Check) ──────────────────
    sent_index: dict  = {}
    sent_domains: dict = {}
    try:
        sent_db.row_factory = sqlite3.Row
        for r in sent_db.execute(
            "SELECT kunden_email, datum FROM gesendete_mails ORDER BY datum"
        ).fetchall():
            em = (r["kunden_email"] or "").lower().strip()
            if not em: continue
            sent_index.setdefault(em, []).append(r["datum"])
            dom = em.split('@')[-1] if '@' in em else ''
            if dom and dom not in _GENERIC_SENT_DOMAINS:
                sent_domains.setdefault(dom, []).append(r["datum"])
    except Exception:
        pass

    stats = {"gesamt": len(kandidaten), "geprueft": 0,
             "tasks_erstellt": 0, "ignoriert": 0, "fehler": 0}

    # ── 4. Jede Mail prüfen und ggf. klassifizieren ───────────────────────────
    for idx, m in enumerate(kandidaten):
        folder = m["folder"] or ""
        absnd  = m["absender"] or ""
        betr   = m["betreff"] or ""
        datum  = m["datum"] or ""
        msgid  = m["message_id"] or ""
        konto  = m["konto_label"] or m["konto"] or ""
        an     = m["an"] or ""

        # Fortschritt-Update (nicht bei jedem Schritt für Performance)
        if idx % 5 == 0:
            _recheck_progress.update({
                "geprueft": stats["geprueft"],
                "tasks_erstellt": stats["tasks_erstellt"],
                "ignoriert": stats["ignoriert"],
                "aktuell": f"{betr[:55]} ({datum[:10]})",
            })

        # Schon vorhandener Task → überspringen
        if msgid and (msgid in existing_ids or msgid in deleted_msgids):
            stats["ignoriert"] += 1
            stats["geprueft"] += 1
            continue

        # Kunden-E-Mail auflösen
        k_email = get_kunden_email(absnd, an, folder)
        if not k_email:
            stats["ignoriert"] += 1
            stats["geprueft"] += 1
            continue
        k_email = resolve_alias(k_email)

        # Eigene Domain überspringen
        dom = k_email.split('@')[-1] if '@' in k_email else ''
        if dom in EIGENE_DOMAINS:
            stats["ignoriert"] += 1
            stats["geprueft"] += 1
            continue

        # Text laden: text_plain aus DB oder aus mail.json auf Disk
        text = m["text_plain"] or ""
        if not text and m["mail_folder_pfad"]:
            try:
                mj_path = Path(m["mail_folder_pfad"]) / "mail.json"
                if mj_path.exists():
                    mdata = json.loads(mj_path.read_text('utf-8', errors='replace'))
                    text = h2t(mdata.get("text", "") or "")[:3000]
            except Exception:
                pass

        # DATEV-Weiterleitungs-Duplikat-Filter
        absnd_dom = absnd.split('@')[-1].lower() if '@' in absnd else ''
        if absnd_dom in EIGENE_DOMAINS:
            anhaenge_pfad = m["anhaenge_pfad"] or ""
            dup = _check_datev_duplicate(betr, text, anhaenge_pfad, konto, tasks_db)
            if dup['action'] == 'skip':
                stats["ignoriert"] += 1
                stats["geprueft"] += 1
                continue

        # Anhaenge-Liste aus JSON-String
        anhaenge_list: list = []
        try:
            raw = m["anhaenge"] or ""
            if raw:
                anhaenge_list = json.loads(raw)
        except Exception:
            pass

        # Klassifizieren
        try:
            cl = classify_mail(
                konto=konto, absender=absnd, betreff=betr, text=text,
                anhaenge=anhaenge_list, folder=folder, is_sent=False,
                mail_datum=datum, kanal="email",
            )
        except Exception as e:
            stats["fehler"] += 1
            stats["geprueft"] += 1
            continue

        kat = cl["kategorie"]

        # Ignorierbare Kategorien → kein Task
        if kat in ("Ignorieren", "Newsletter / Werbung", "Abgeschlossen", "Zur Kenntnis"):
            stats["ignoriert"] += 1
            stats["geprueft"] += 1
            continue
        if kat in ("Shop / System", "Rechnung / Beleg") and not cl["antwort_noetig"]:
            stats["ignoriert"] += 1
            stats["geprueft"] += 1
            continue

        # Schon beantwortet?
        k_email_l = k_email.lower()
        if any(d > datum for d in sent_index.get(k_email_l, [])):
            stats["ignoriert"] += 1
            stats["geprueft"] += 1
            continue
        k_domain = k_email_l.split('@')[-1] if '@' in k_email_l else ''
        if k_domain and k_domain not in _GENERIC_SENT_DOMAINS:
            if any(d > datum for d in sent_domains.get(k_domain, [])):
                stats["ignoriert"] += 1
                stats["geprueft"] += 1
                continue

        # Erneuter Duplikat-Check (falls msgid leer war, nach oben-Filter)
        if msgid and msgid in existing_ids:
            stats["ignoriert"] += 1
            stats["geprueft"] += 1
            continue

        if not dry_run:
            # Entwurf generieren
            entwurf = ""
            claude_prompt = ""
            benoetigt_entwurf = (cl["antwort_noetig"]
                                  or kat in ("Angebotsrueckmeldung", "Antwort erforderlich"))
            if benoetigt_entwurf and k_email:
                try:
                    hint = "Angebotsrueckmeldung" if kat == "Angebotsrueckmeldung" else ""
                    draft = generate_draft(betr, absnd, text, k_email, hint=hint)
                    entwurf = draft.get("entwurf", "")
                    claude_prompt = draft.get("claude_prompt", "")
                except Exception:
                    pass

            # Thread-ID
            thread_id = None
            try:
                cutoff30 = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
                ex_t = tasks_db.execute(
                    "SELECT id, thread_id FROM tasks "
                    "WHERE kunden_email=? AND erstellt_am >= ? ORDER BY id ASC LIMIT 1",
                    (k_email, cutoff30)
                ).fetchone()
                if ex_t:
                    thread_id = ex_t["thread_id"] or f"T{ex_t['id']}"
            except Exception:
                pass

            task_typ = kategorie_to_task_typ(kat)
            try:
                tasks_db.execute("""INSERT INTO tasks
                    (typ, kategorie, titel, zusammenfassung, beschreibung,
                     kunden_email, kunden_name, absender_rolle, empfohlene_aktion,
                     kategorie_grund, message_id, mail_folder_pfad, anhaenge_pfad,
                     antwort_entwurf, claude_prompt, betreff, konto, datum_mail,
                     prioritaet, antwort_noetig, thread_id, konfidenz)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (task_typ, kat, betr[:120] or f"Mail von {k_email}",
                     cl["zusammenfassung"], text[:1000],
                     k_email, "", cl["absender_rolle"],
                     cl["empfohlene_aktion"], cl["kategorie_grund"],
                     msgid, m["mail_folder_pfad"] or "", m["anhaenge_pfad"] or "",
                     entwurf[:4000], claude_prompt[:2000],
                     betr[:120], konto, datum,
                     cl["prioritaet"], 1 if cl["antwort_noetig"] else 0,
                     thread_id, cl.get("konfidenz", "mittel")))
                new_id = tasks_db.execute("SELECT last_insert_rowid()").fetchone()[0]
                if not thread_id:
                    tasks_db.execute("UPDATE tasks SET thread_id=? WHERE id=?",
                                     (f"T{new_id}", new_id))
                tasks_db.commit()  # commit vor Router-Aufruf
                stats["tasks_erstellt"] += 1
                if msgid:
                    existing_ids.add(msgid)
                if kat == "Angebotsrueckmeldung":
                    _try_update_angebot_from_mail(k_email, text, tasks_db)
                # ── Case Engine: Vorgang-Routing (session-nn) ─────────────────
                try:
                    from vorgang_router import route_classified_mail as _vr_route
                    _vr_route(
                        task_id=new_id,
                        classification_result=cl,
                        mail_message_id=msgid,
                        kunden_email=k_email,
                        kunden_name=m.get("kunden_name", ""),
                        konto=konto,
                        betreff=betr,
                    )
                except Exception as _ve:
                    pass  # Router-Fehler stoppen nicht den Recheck
            except Exception as e:
                stats["fehler"] += 1
                print(f"  [recheck] Task-Fehler: {e}")

        stats["geprueft"] += 1

    if not dry_run:
        tasks_db.commit()
        kunden_db.commit()
    tasks_db.close()
    kunden_db.close()
    sent_db.close()

    _recheck_progress.update({
        "running": False, "finished": True,
        "aktuell": "Fertig",
        **{k: stats[k] for k in ("gesamt", "geprueft", "tasks_erstellt", "ignoriert", "fehler")},
    })
    return stats


# ── Angebot-Status Auto-Update ───────────────────────────────────────────────
def _try_update_angebot_from_mail(k_email: str, text: str, tasks_db):
    """
    Wenn eine Angebotsrückmeldung eingeht, versucht diese Funktion via LLM
    zu erkennen ob das Angebot angenommen, abgelehnt oder als Rückfrage einzustufen ist.
    Aktualisiert kunden.db angebote-Tabelle entsprechend.
    """
    try:
        kdb = sqlite3.connect(str(TASKS_DB))
        kdb.row_factory = sqlite3.Row
        angebote = kdb.execute(
            "SELECT id, a_nummer, status FROM angebote WHERE LOWER(kunde_email)=? AND status='offen' ORDER BY erstellt_am DESC LIMIT 1",
            (k_email.lower(),)
        ).fetchall()
        if not angebote:
            kdb.close()
            return

        angebot = dict(angebote[0])
        angebots_nr = angebot.get("a_nummer","")
        ang_id      = angebot.get("id")

        # LLM fragen: Annahme, Absage oder Rückfrage?
        try:
            from kira_llm import chat as kira_chat
            result = kira_chat(
                user_message=(
                    f"[SYSTEM: Angebot-Analyse — antworte NUR mit einem Wort]\n"
                    f"Hat diese Mail das Angebot angenommen, abgelehnt, oder ist es eine Rückfrage?\n"
                    f"Antworte NUR: akzeptiert | abgelehnt | rueckfrage | unklar\n\n"
                    f"Mailtext:\n{text[:1500]}"
                ),
                session_id=None
            )
            antwort = (result.get("antwort","") or "").strip().lower()

            if "akzeptiert" in antwort or "angenommen" in antwort:
                kdb.execute("UPDATE angebote SET status='angenommen', grund_angenommen=? WHERE id=?",
                            ("Auto-erkannt aus Mail", ang_id))
                kdb.commit()
                print(f"  Angebot {angebots_nr}: automatisch als 'angenommen' markiert")
            elif "abgelehnt" in antwort or "absage" in antwort:
                kdb.execute("UPDATE angebote SET status='abgelehnt', grund_abgelehnt=? WHERE id=?",
                            ("Auto-erkannt aus Mail", ang_id))
                kdb.commit()
                print(f"  Angebot {angebots_nr}: automatisch als 'abgelehnt' markiert")
            elif "rueckfrage" in antwort or "rückfrage" in antwort:
                # Keine Status-Änderung, aber Notiz im Task
                pass
            # Bei "unklar": keine Änderung
        except Exception:
            pass
        kdb.close()
    except Exception:
        pass


# ── DATEV-Duplikat-Erkennung ───────────────────────────────────────────────────

def _decode_mime(s: str) -> str:
    """Dekodiert MIME encoded-word Header (=?charset?encoding?text?=)."""
    if not s or '=?' not in s:
        return s or ''
    try:
        import email.header as _eh
        parts = _eh.decode_header(s)
        out = []
        for chunk, enc in parts:
            if isinstance(chunk, bytes):
                out.append(chunk.decode(enc or 'utf-8', errors='replace'))
            else:
                out.append(str(chunk))
        return ' '.join(out)
    except Exception:
        return s


def _norm(s: str) -> str:
    """Normalisiert Text: MIME-dekodiert, lowercase, Whitespace normalisiert."""
    return re.sub(r'\s+', ' ', _decode_mime(s or '')).strip().lower()


def _text_similarity(a: str, b: str) -> float:
    """Jaccard-Wortüberlappung 0.0–1.0."""
    if not a or not b:
        return 0.0
    wa = set(re.sub(r'[^\w]', ' ', a.lower()).split())
    wb = set(re.sub(r'[^\w]', ' ', b.lower()).split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


def _get_attachment_names(folder_path: str) -> set:
    """Dateinamen (lowercase) im Anhangordner."""
    if not folder_path:
        return set()
    try:
        p = Path(folder_path)
        if p.is_dir():
            return {f.name.lower() for f in p.iterdir() if f.is_file()}
    except Exception:
        pass
    return set()


def _log_loeschhistorie(tasks_db, task_id, konto, absender, betreff,
                         datum_mail, anhaenge_info, grund,
                         referenz_task_id, referenz_konto):
    """Schreibt Lösch- oder Behalte-Entscheidungen in loeschhistorie."""
    try:
        tasks_db.execute("""INSERT INTO loeschhistorie
            (geloescht_am, task_id, konto, absender, betreff, datum_mail,
             anhaenge_info, grund, referenz_task_id, referenz_konto)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
             task_id, konto, absender, betreff, datum_mail,
             anhaenge_info, grund, referenz_task_id, referenz_konto))
    except Exception:
        pass


_NO_DUP = {'is_duplicate': False, 'action': 'keep', 'grund': '', 'ref_id': None, 'ref_konto': ''}


def _check_datev_duplicate(betr, text, anhaenge_pfad, konto, tasks_db) -> dict:
    """
    Prüft ob eine Mail eine DATEV-Einzelweiterleitung ist.
    Entscheidungslogik (Priorität):
      1. Betreff-Ähnlichkeit (MIME-dekodiert, normalisiert) ≥ 0.8 gegen Task im anderen Konto
         a. Anhang-Namen kreuzen sich    → SKIP (Duplikat)
         b. Meine Anhang-Datei nicht im Referenz-Task → KEEP (abweichender Inhalt)
         c. Kein eigener Anhang          → SKIP (leere Weiterleitungskopie)
      2. Body-Ähnlichkeit ≥ 0.5 (Fallback wenn Betreff abweicht)
         → gleiche Logik wie 1
    """
    my_files   = _get_attachment_names(anhaenge_pfad)
    norm_betr  = _norm(betr)

    # Kandidaten: Tasks anderer Konten (max. 50 neueste)
    try:
        refs = tasks_db.execute("""
            SELECT id, konto, beschreibung, anhaenge_pfad, betreff
            FROM tasks WHERE konto != ?
            ORDER BY id DESC LIMIT 50
        """, (konto,)).fetchall()
    except Exception:
        return _NO_DUP

    # Besten Kandidaten nach Betreff-Ähnlichkeit finden
    best_ref      = None
    best_betr_sim = 0.0
    best_body_sim = 0.0

    for ref in refs:
        b_sim = _text_similarity(norm_betr, _norm(ref['betreff'] or ''))
        if b_sim > best_betr_sim:
            best_betr_sim = b_sim
            best_body_sim = _text_similarity(text or '', ref['beschreibung'] or '')
            best_ref      = ref

    # Kein Kandidat mit ausreichender Betreff-Übereinstimmung?
    if best_ref is None or best_betr_sim < 0.7:
        # Fallback: Body-Ähnlichkeit als einziges Kriterium
        if text:
            for ref in refs:
                b_sim = _text_similarity(text, ref['beschreibung'] or '')
                if b_sim > best_body_sim:
                    best_body_sim = b_sim
                    best_ref      = ref
                    best_betr_sim = _text_similarity(norm_betr, _norm(ref['betreff'] or ''))
        if best_ref is None or best_body_sim < 0.5:
            return _NO_DUP

    # Entscheidung anhand Anhänge
    ref_files = _get_attachment_names(best_ref['anhaenge_pfad'])
    ref_id    = best_ref['id']
    ref_konto = best_ref['konto']
    hint      = f"Betreff-Ähnl. {best_betr_sim:.0%}, Body-Ähnl. {best_body_sim:.0%}"

    if my_files and ref_files:
        match = my_files & ref_files
        if match:
            return {
                'is_duplicate': True, 'action': 'skip', 'ref_id': ref_id, 'ref_konto': ref_konto,
                'grund': (f"DATEV-Duplikat: Anhang '{next(iter(match))}' bereits in "
                          f"Task #{ref_id} (konto={ref_konto}) — {hint}."),
            }
        # Anhang existiert NICHT im Original → neuer Inhalt → behalten
        return {
            'is_duplicate': False, 'action': 'keep', 'ref_id': ref_id, 'ref_konto': ref_konto,
            'grund': (f"Abweichender Anhang ({', '.join(sorted(my_files))}) — "
                      f"nicht in Referenz-Task #{ref_id} ({ref_konto}) — {hint}. Behalten."),
        }

    if my_files and not ref_files:
        # Original hat keine (mehr) Anhänge, ich habe welche → könnte neuer Inhalt sein
        # Wenn Betreff sehr ähnlich und kein Anhang im Original gespeichert: Duplikat
        if best_betr_sim >= 0.85:
            return {
                'is_duplicate': True, 'action': 'skip', 'ref_id': ref_id, 'ref_konto': ref_konto,
                'grund': (f"DATEV-Duplikat: Anhang-Ordner von Referenz-Task #{ref_id} nicht mehr "
                          f"zugreifbar, Betreff aber nahezu identisch — {hint}."),
            }
        return _NO_DUP

    # Kein eigener Anhang — DATEV-Weiterleitungskopie ohne Datei
    if best_betr_sim >= 0.8 or best_body_sim >= 0.75:
        return {
            'is_duplicate': True, 'action': 'skip', 'ref_id': ref_id, 'ref_konto': ref_konto,
            'grund': (f"DATEV-Duplikat: kein eigener Anhang, {hint}, "
                      f"Referenz-Task #{ref_id} (konto={ref_konto})."),
        }

    return _NO_DUP


# ── Mails klassifizieren und in DBs eintragen ────────────────────────────────
def process_new_mails(new_mails, stats):
    """Klassifiziert neue Mails mit mail_classifier und trägt sie ein."""
    kunden_db = sqlite3.connect(str(KUNDEN_DB))
    sent_db   = sqlite3.connect(str(SENT_DB))
    tasks_db  = sqlite3.connect(str(TASKS_DB))
    tasks_db.row_factory = sqlite3.Row

    # Gesendete Index laden — konto-übergreifend aus sent_mails.db (enthält ALLE Konten)
    # Zusätzlich: cross-domain Matching (muller@firma.de ~ max.muller@firma.de)
    sent_index = {}        # {kunden_email: [datum, ...]}
    sent_domains = {}      # {domain: [datum, ...]}  für cross-domain-Check
    try:
        sent_db.row_factory = sqlite3.Row
        for r in sent_db.execute("SELECT kunden_email, datum FROM gesendete_mails ORDER BY datum").fetchall():
            em = (r["kunden_email"] or "").lower().strip()
            if not em: continue
            sent_index.setdefault(em, []).append(r["datum"])
            # Domain-Index für cross-domain-Match (nicht bei generischen Domains)
            dom = em.split('@')[-1] if '@' in em else ''
            if dom and dom not in _GENERIC_SENT_DOMAINS:
                sent_domains.setdefault(dom, []).append(r["datum"])
    except: pass

    # Load permanently deleted message_ids from loeschhistorie
    deleted_msgids = set()
    try:
        _del_rows = tasks_db.execute(
            "SELECT message_id FROM loeschhistorie WHERE message_id IS NOT NULL AND message_id != ''"
        ).fetchall()
        deleted_msgids = {row[0] for row in _del_rows}
    except Exception:
        pass

    for m in new_mails:
        folder  = m['folder']
        is_sent = "Gesendete" in folder or "Sent" in folder
        k_email = get_kunden_email(m['absender'], m['an'], folder)
        # Alias-Auflösung: bekannte Alias-Adressen auf Haupt-E-Mail mappen
        if k_email:
            k_email = resolve_alias(k_email)
        konto   = m['konto']
        absnd   = m['absender']
        betr    = m['betreff']
        text    = m['text_plain']
        datum   = m['datum']
        msgid   = m['message_id']

        # In kunden.db eintragen
        if k_email:
            try:
                kunden_db.execute("""INSERT OR IGNORE INTO interaktionen
                    (konto_label,betreff,absender,kunden_email,datum,datum_iso,message_id,folder,
                     mail_typ,text_plain,hat_anhaenge,anhaenge_pfad,mail_folder_pfad)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (konto, betr, absnd, k_email, datum, '', msgid, folder,
                     'eingehend' if not is_sent else 'gesendet',
                     text[:4000], 1 if m['hat_anhaenge'] else 0,
                     m['anhaenge_pfad'], m['mail_folder_pfad']))
                stats['kunden'] = stats.get('kunden',0)+1
            except: pass

        # Gesendete in sent_mails.db
        if is_sent and k_email:
            try:
                sent_db.execute("""INSERT OR IGNORE INTO gesendete_mails
                    (konto_label,betreff,an,kunden_email,datum,message_id,text_plain,hat_anhaenge,mail_typ,mail_folder_pfad)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (konto, betr, m['an'], k_email, datum, msgid,
                     text[:6000], 1 if m['hat_anhaenge'] else 0, 'gesendet', m['mail_folder_pfad']))
            except: pass
            continue  # Gesendete -> kein Task

        if not k_email: continue

        # Eigene Domain überspringen (Kunde = eigene Adresse)
        dom = k_email.split('@')[-1] if '@' in k_email else ''
        if dom in EIGENE_DOMAINS: continue

        # DATEV/Weiterleitungs-Filter: Absender ist eigene Adresse (internes Routing)
        # → prüft Body-Ähnlichkeit + Anhang-Dateinamen gegen vorhandene Tasks
        absnd_dom = absnd.split('@')[-1].lower() if '@' in absnd else ''
        if absnd_dom in EIGENE_DOMAINS:
            dup = _check_datev_duplicate(
                betr, text, m.get('anhaenge_pfad', ''), konto, tasks_db
            )
            anhaenge_info = ', '.join(_get_attachment_names(m.get('anhaenge_pfad', ''))) or '–'
            if dup['action'] == 'skip':
                _log_loeschhistorie(
                    tasks_db, None, konto, absnd, betr, datum,
                    anhaenge_info, dup['grund'], dup['ref_id'], dup['ref_konto']
                )
                stats['ignoriert'] = stats.get('ignoriert', 0) + 1
                continue
            elif dup['grund']:
                # Abweichender Anhang → behalten, Grund als Notiz in loeschhistorie
                _log_loeschhistorie(
                    tasks_db, None, konto, absnd, betr, datum,
                    anhaenge_info,
                    'BEHALTEN – ' + dup['grund'],
                    dup['ref_id'], dup['ref_konto']
                )

        # Klassifizieren — Datum übergeben für zeitlichen Angebote-Abgleich
        cl = classify_mail(konto, absnd, betr, text, folder=folder,
                           is_sent=is_sent, mail_datum=datum, kanal="email")
        kat = cl["kategorie"]

        # Ignorieren / Newsletter / Zur Kenntnis -> kein Task
        if kat in ("Ignorieren", "Newsletter / Werbung", "Abgeschlossen", "Zur Kenntnis"):
            stats['ignoriert'] = stats.get('ignoriert',0)+1
            continue

        if kat in ("Shop / System", "Rechnung / Beleg") and not cl["antwort_noetig"]:
            stats['zur_kenntnis'] = stats.get('zur_kenntnis',0)+1
            continue

        # Schon beantwortet? — konto-übergreifend (direkte E-Mail + cross-domain)
        k_email_l = k_email.lower()
        dates = sent_index.get(k_email_l, [])
        if any(d > datum for d in dates):
            continue
        # Cross-domain-Check: wenn Firmen-Domain bekannt und bereits geantwortet
        k_domain = k_email_l.split('@')[-1] if '@' in k_email_l else ''
        if k_domain and k_domain not in _GENERIC_SENT_DOMAINS:
            domain_dates = sent_domains.get(k_domain, [])
            if any(d > datum for d in domain_dates):
                continue

        # Duplikat-Check
        if msgid:
            existing = tasks_db.execute("SELECT id FROM tasks WHERE message_id=?", (msgid,)).fetchone()
            if existing: continue

        # Skip permanently deleted mails
        if msgid and msgid in deleted_msgids:
            continue

        task_typ = kategorie_to_task_typ(kat)

        # Entwurf — auch für Angebotsrückmeldungen
        entwurf = ""
        claude_prompt = ""
        benoetigt_entwurf = (
            cl["antwort_noetig"]
            or kat == "Angebotsrueckmeldung"
            or kat == "Antwort erforderlich"
        )
        if benoetigt_entwurf and k_email:
            try:
                # Für Angebotsrückmeldungen: Hinweis übergeben
                hint = "Angebotsrueckmeldung" if kat == "Angebotsrueckmeldung" else ""
                draft = generate_draft(betr, absnd, text, k_email, hint=hint)
                entwurf = draft.get("entwurf","")
                claude_prompt = draft.get("claude_prompt","")
            except: pass

        # Thread-ID: bestehenden Thread desselben Kunden (letzte 30 Tage) suchen
        thread_id = None
        try:
            from datetime import timedelta as _td
            cutoff30 = (datetime.now() - _td(days=30)).strftime("%Y-%m-%d %H:%M:%S")
            existing_thread = tasks_db.execute(
                "SELECT id, thread_id FROM tasks WHERE kunden_email=? AND erstellt_am >= ? ORDER BY id ASC LIMIT 1",
                (k_email, cutoff30)
            ).fetchone()
            if existing_thread:
                thread_id = existing_thread["thread_id"] or f"T{existing_thread['id']}"
        except: pass

        # Task anlegen
        try:
            tasks_db.execute("""INSERT INTO tasks
                (typ, kategorie, titel, zusammenfassung, beschreibung,
                 kunden_email, kunden_name, absender_rolle, empfohlene_aktion,
                 kategorie_grund, message_id, mail_folder_pfad, anhaenge_pfad,
                 antwort_entwurf, claude_prompt, betreff, konto, datum_mail,
                 prioritaet, antwort_noetig, thread_id, konfidenz)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task_typ, kat, betr[:120] or f"Mail von {k_email}",
                 cl["zusammenfassung"], text[:1000],
                 k_email, "", cl["absender_rolle"],
                 cl["empfohlene_aktion"], cl["kategorie_grund"],
                 msgid, m['mail_folder_pfad'], m['anhaenge_pfad'] or "",
                 entwurf[:4000], claude_prompt[:2000],
                 betr[:120], konto, datum,
                 cl["prioritaet"], 1 if cl["antwort_noetig"] else 0,
                 thread_id, cl.get("konfidenz", "mittel")))
            new_id = tasks_db.execute("SELECT last_insert_rowid()").fetchone()[0]
            # Wenn kein Thread existierte, neuen Thread mit eigener ID starten
            if not thread_id:
                tasks_db.execute("UPDATE tasks SET thread_id=? WHERE id=?",
                                 (f"T{new_id}", new_id))
            stats['tasks_erstellt'] = stats.get('tasks_erstellt',0)+1
            # Auto-Update Angebot-Status bei Angebotsrückmeldung
            if kat == "Angebotsrueckmeldung":
                _try_update_angebot_from_mail(k_email, text, tasks_db)
            # ── Vorgang-Router (Paket 4+5) ────────────────────────────────────
            tasks_db.commit()  # commit vor Router-Aufruf (eigene DB-Connection)
            try:
                from vorgang_router import route_classified_mail as _vr_route
                _vr_route(
                    task_id=new_id,
                    classification_result=cl,
                    mail_message_id=msgid,
                    kunden_email=k_email,
                    kunden_name=m.get('kunden_name', ''),
                    konto=konto,
                    betreff=betr,
                )
            except Exception as _ve:
                pass
        except Exception as e:
            print(f"  Task-Fehler: {e}")

    kunden_db.commit(); kunden_db.close()
    sent_db.commit(); sent_db.close()
    tasks_db.commit(); tasks_db.close()


# ── Notifications ─────────────────────────────────────────────────────────────
def send_ntfy(title: str, message: str, priority: str = "default"):
    config = load_config()
    ntfy_cfg = config.get("ntfy", {})
    if not ntfy_cfg.get("aktiv"): return
    topic  = ntfy_cfg.get("topic_name","")
    server = ntfy_cfg.get("server","https://ntfy.sh")
    if not topic or topic.startswith("raumkult-dein"): return
    try:
        import urllib.request
        url  = f"{server}/{topic}"
        data = message.encode('utf-8')
        req  = urllib.request.Request(url, data=data, method='POST')
        req.add_header("Title", title)
        req.add_header("Priority", priority)
        req.add_header("Tags", "bell")
        urllib.request.urlopen(req, timeout=8)
        print("  ntfy: gesendet")
    except Exception as e:
        print(f"  ntfy: Fehler - {e}")


def send_toast(title: str, message: str):
    url = "http://localhost:8765"
    ps = f"""
try {{
  [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
  [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime] | Out-Null
  $xml = [Windows.Data.Xml.Dom.XmlDocument]::new()
  $xml.LoadXml('<toast launch="{url}"><visual><binding template="ToastGenericImageAndText02"><text id="1">{title}</text><text id="2">{message}</text></binding></visual><actions><action content="Dashboard" arguments="{url}" activationType="protocol"/></actions></toast>')
  $n = [Windows.UI.Notifications.ToastNotification]::new($xml)
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("rauMKult").Show($n)
}} catch {{}}
"""
    try:
        subprocess.run(["powershell.exe","-NoProfile","-NonInteractive",
                        "-ExecutionPolicy","Bypass","-Command",ps],
                       timeout=8, capture_output=True)
    except: pass


# ── Hauptprogramm ─────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().strftime('%H:%M')}] rauMKult Daily Check v4...")
    _t0_job = __import__('time').monotonic()
    _elog('system', 'daily_check_started', 'Daily Check gestartet',
          source='daily_check', modul='daily_check', actor_type='system', status='ok')
    config = load_config()

    status = load_status()
    try: last_run = datetime.strptime(status["letzter_lauf"][:19],"%Y-%m-%d %H:%M:%S")
    except: last_run = datetime.now() - timedelta(days=1)

    # 1. Neue Mails scannen
    new_mails = scan_new_mails(last_run)
    stats = {"gesamt": len(new_mails), "kunden": 0, "tasks_erstellt": 0, "ignoriert": 0, "zur_kenntnis": 0}
    print(f"  Neue Mails: {len(new_mails)}")

    # 2. Klassifizieren und eintragen
    if new_mails:
        process_new_mails(new_mails, stats)
        print(f"  Tasks erstellt: {stats.get('tasks_erstellt',0)}")
        print(f"  Ignoriert: {stats.get('ignoriert',0)}")

    # 3. Fällige Erinnerungen
    due = get_due_reminders()
    for t in due:
        increment_reminder(t["id"])

    # 4. Offene Tasks + Nachfass-Fälligkeiten prüfen
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    open_tasks = db.execute("SELECT kategorie, COUNT(*) c FROM tasks WHERE status='offen' GROUP BY kategorie").fetchall()
    total_open = sum(r['c'] for r in open_tasks)
    n_antwort  = sum(r['c'] for r in open_tasks if r['kategorie'] == 'Antwort erforderlich')
    n_leads    = sum(r['c'] for r in open_tasks if r['kategorie'] == 'Neue Lead-Anfrage')

    # Nachfass-Fälligkeiten für Angebote
    today = datetime.now().strftime("%Y-%m-%d")
    n_nachfass = 0
    try:
        nf_rows = db.execute("SELECT a_nummer, kunde_email FROM angebote WHERE status='offen' AND naechster_nachfass IS NOT NULL AND naechster_nachfass <= ?", (today,)).fetchall()
        n_nachfass = len(nf_rows)
        if n_nachfass > 0:
            print(f"  Nachfass fällig: {n_nachfass} Angebote")
    except: pass

    # Offene Ausgangsrechnungen > 30 Tage
    n_overdue = 0
    try:
        cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        n_overdue = db.execute("SELECT COUNT(*) FROM ausgangsrechnungen WHERE status='offen' AND datum < ?", (cutoff,)).fetchone()[0]
        if n_overdue > 0:
            print(f"  Überfällige Rechnungen (>30 Tage): {n_overdue}")
    except: pass
    db.close()

    # 5. Notifications
    teile = []
    if n_antwort:  teile.append(f"{n_antwort} Antworten nötig")
    if n_leads:    teile.append(f"{n_leads} neue Leads")
    if due:        teile.append(f"{len(due)} Erinnerungen fällig")
    if n_nachfass: teile.append(f"{n_nachfass} Nachfass fällig")
    if n_overdue:  teile.append(f"{n_overdue} Rechnungen überfällig")

    if teile or total_open > 0:
        msg   = " · ".join(teile) if teile else f"{total_open} offene Aufgaben"
        title = f"rauMKult - {total_open} Aufgaben offen"
        send_toast(title, msg)
        send_ntfy(title, msg, priority="high" if n_antwort > 0 else "default")

    save_status({
        "letzter_lauf": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stats": stats,
        "offene_tasks": total_open,
    })

    print(f"  Tasks offen: {total_open} (davon {n_antwort} Antwort nötig)")
    print(f"  Erinnerungen fällig: {len(due)}")
    print(f"[{datetime.now().strftime('%H:%M')}] Fertig.")
    _elog('system', 'daily_check_completed',
          f"Daily Check: {stats.get('gesamt',0)} Mails, {stats.get('tasks_erstellt',0)} Tasks, {total_open} offen",
          source='daily_check', modul='daily_check', actor_type='system', status='ok',
          duration_ms=int((__import__('time').monotonic()-_t0_job)*1000),
          result=f"mails={stats.get('gesamt',0)} tasks={stats.get('tasks_erstellt',0)} offen={total_open}")

    # 6. Archiv-Bereinigung (Gelöschte-Ordner nach einstellbarer Frist)
    try:
        import archiv_cleanup as _ac
        _cs = _ac.run_cleanup()
        if _cs.get("bereinigt", 0) > 0:
            print(f"  Archiv-Bereinigung: {_cs['bereinigt']} Mails bereinigt, "
                  f"{_cs['protokoll']} protokolliert, {_cs['fehler']} Fehler")
    except Exception as _ace:
        print(f"  [WARN] Archiv-Bereinigung übersprungen: {_ace}")

    # 7. Auto-Backup (falls konfiguriert)
    try:
        _backup_cfg = _cfg_dc.get('backup', {})
        if _backup_cfg.get('aktiv', False):
            import shutil as _sh, sqlite3 as _sq_b
            _backup_dir = Path(_backup_cfg.get('pfad', '') or '') if _backup_cfg.get('pfad') else KNOWLEDGE_DIR / 'backups'
            _backup_dir.mkdir(parents=True, exist_ok=True)
            _ts = datetime.now().strftime('%Y-%m-%d_%H-%M')
            _backed = []
            _src_cfg = SCRIPTS_DIR / 'config.json'
            if _src_cfg.exists():
                _sh.copy2(str(_src_cfg), str(_backup_dir / f'{_ts}_config.json'))
                _backed.append('config.json')
            for _dbn in ['tasks.db', 'mail_index.db']:
                _src_db = KNOWLEDGE_DIR / _dbn
                if not _src_db.exists():
                    continue
                _dst_db = _backup_dir / f'{_ts}_{_dbn}'
                try:
                    _sc = _sq_b.connect(str(_src_db))
                    _dc2 = _sq_b.connect(str(_dst_db))
                    _sc.backup(_dc2)
                    _sc.close()
                    _dc2.close()
                    _backed.append(_dbn)
                except Exception:
                    pass
            _keep_n = int(_backup_cfg.get('keep_n', 7))
            _grps = {}
            for _f in sorted(_backup_dir.iterdir()):
                if not _f.is_file():
                    continue
                for _suf in ['_config.json', '_tasks.db', '_mail_index.db']:
                    if _f.name.endswith(_suf):
                        _grps.setdefault(_suf, []).append(_f)
            for _suf, _files in _grps.items():
                for _old in _files[:-_keep_n]:
                    try:
                        _old.unlink()
                    except Exception:
                        pass
            if _backed:
                print(f"  Auto-Backup: {', '.join(_backed)} -> {_backup_dir}")
                _elog('system', 'auto_backup', f'Backup: {", ".join(_backed)}',
                      modul='daily_check', source='daily_check', actor_type='system', status='ok')
    except Exception as _be:
        print(f"  [WARN] Auto-Backup fehlgeschlagen: {_be}")

    # ── Step 8: DB-Autopflege ─────────────────────────────────────────────────
    print("[daily_check] Step 8: DB-Autopflege...")
    try:
        import sqlite3 as _sq_maint
        _maint_db = _sq_maint.connect(str(TASKS_DB))
        _maint_db.execute("PRAGMA journal_mode=WAL")

        # 1. Alte abgeschlossene Tasks archivieren (status=zur_kenntnis oder erledigt + >90 Tage)
        _cfg_maint = _cfg_dc
        _archiv_tage = int(_cfg_maint.get('aufgaben', {}).get('auto_archiv_tage', 90))
        _archiv_cutoff = (datetime.now() - timedelta(days=_archiv_tage)).strftime('%Y-%m-%d')
        _deleted_tasks = _maint_db.execute(
            "DELETE FROM tasks WHERE status IN ('zur_kenntnis','archiviert') AND datum_mail < ? RETURNING id",
            (_archiv_cutoff,)
        ).fetchall()
        _n_del = len(_deleted_tasks)

        # 2. Wissen-Duplikate entfernen (gleicher titel+kategorie, aelteren loeschen)
        _dup_wissen = _maint_db.execute("""
            SELECT id FROM wissen_regeln w1
            WHERE EXISTS (
                SELECT 1 FROM wissen_regeln w2
                WHERE w2.titel=w1.titel AND w2.kategorie=w1.kategorie AND w2.id < w1.id
            )
        """).fetchall()
        _n_wissen_dup = len(_dup_wissen)
        if _dup_wissen:
            _ids = [str(r[0]) for r in _dup_wissen]
            _maint_db.execute(f"DELETE FROM wissen_regeln WHERE id IN ({','.join(_ids)})")

        # 3. VACUUM (nur wenn >2% Freiraum)
        _page_count = _maint_db.execute("PRAGMA page_count").fetchone()[0]
        _freelist   = _maint_db.execute("PRAGMA freelist_count").fetchone()[0]
        _did_vacuum = False
        if _page_count > 0 and _freelist / _page_count > 0.02:
            _maint_db.execute("VACUUM")
            _did_vacuum = True

        _maint_db.commit()
        _maint_db.close()

        # Mail-Index VACUUM
        try:
            _mi_db = _sq_maint.connect(str(KNOWLEDGE_DIR / 'mail_index.db'))
            _mi_freelist = _mi_db.execute("PRAGMA freelist_count").fetchone()[0]
            _mi_pages    = _mi_db.execute("PRAGMA page_count").fetchone()[0]
            if _mi_pages > 0 and _mi_freelist / _mi_pages > 0.02:
                _mi_db.execute("VACUUM")
            _mi_db.close()
        except Exception: pass

        print(f"  DB-Autopflege: {_n_del} alte Tasks entfernt, {_n_wissen_dup} Duplikate bereinigt"
              + (" + VACUUM" if _did_vacuum else ""))
        _elog('system', 'db_autopflege',
              f'Tasks entfernt: {_n_del}, Wissen-Duplikate: {_n_wissen_dup}, Vacuum: {_did_vacuum}',
              modul='daily_check', source='daily_check', actor_type='system', status='ok')
    except Exception as _me:
        print(f"  [WARN] DB-Autopflege fehlgeschlagen: {_me}")


if __name__ == "__main__":
    import argparse
    _p = argparse.ArgumentParser(description="rauMKult Daily Check / Mail-Nachklassifizierung")
    _p.add_argument("--seit", metavar="YYYY-MM-DD",
                    help="Mails ab diesem Datum nachklassifizieren (recheck_mails)")
    _p.add_argument("--bis",  metavar="YYYY-MM-DD", default=None,
                    help="Mails bis zu diesem Datum (optional, default: heute)")
    _p.add_argument("--trocken", action="store_true",
                    help="Dry-run: klassifizieren aber keine Tasks schreiben")
    _args = _p.parse_args()
    if _args.seit:
        print(f"[recheck] Nachklassifizierung: {_args.seit} -> {_args.bis or 'heute'}"
              + (" (DRY-RUN)" if _args.trocken else ""))
        _stats = recheck_mails(_args.seit, _args.bis, _args.trocken)
        print(f"[recheck] Ergebnis: {_stats['geprueft']}/{_stats['gesamt']} geprüft"
              f" · {_stats['tasks_erstellt']} Tasks erstellt"
              f" · {_stats['ignoriert']} ignoriert"
              f" · {_stats['fehler']} Fehler")
    else:
        main()
