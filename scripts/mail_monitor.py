#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mail_monitor.py — Echtzeit-Mail-Monitor für Kira Dashboard.
Pollt alle 5 Postfächer via IMAP/OAuth2 und verarbeitet neue Mails sofort.
Nutzt den Token-Cache des Mail-Archivers (gemeinsamer OAuth2-Login).

Extrahiert und adaptiert aus raumkult_mail_archiver_v3.81.py.
"""
import json, os, sys, threading, imaplib, email, email.header, email.utils
import re, hashlib, base64, time, logging, webbrowser, sqlite3
from datetime import datetime
from pathlib import Path
from html.parser import HTMLParser
try:
    from activity_log import log as _alog
except Exception:
    def _alog(*a, **k): pass

try:
    from runtime_log import elog as _elog
except Exception:
    def _elog(*a, **k): return ""

try:
    import msal
    MSAL_OK = True
except ImportError:
    MSAL_OK = False

SCRIPTS_DIR    = Path(__file__).parent
KNOWLEDGE_DIR  = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB       = KNOWLEDGE_DIR / "tasks.db"
KUNDEN_DB      = KNOWLEDGE_DIR / "kunden.db"
MAIL_INDEX_DB  = KNOWLEDGE_DIR / "mail_index.db"
CONFIG_FILE    = SCRIPTS_DIR / "config.json"

# Archiver-Pfade (Token-Cache teilen!)
ARCHIVER_DIR  = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv")
ARCHIVER_CFG  = ARCHIVER_DIR / "raumkult_config.json"
TOKEN_DIR     = ARCHIVER_DIR / "tokens"

# Monitor State
STATE_FILE    = KNOWLEDGE_DIR / "mail_monitor_state.json"

IMAP_TIMEOUT  = 60
OAUTH_SCOPES  = ["https://outlook.office.com/IMAP.AccessAsUser.All"]
OAUTH_SCOPE_VERSION = "v4_office_com"

ORDNER_AUSSCHLIESSEN = [
    "spam", "junk", "trash", "papierkorb", "gelöschte", "deleted",
    "geloeschte", "outbox", "entwürfe", "entwurfe", "drafts",
    "archive", "archiv", "sent items", "unerwünscht", "unerwuenscht",
]
ORDNER_EINSCHLIESSEN = [
    "inbox", "posteingang", "eingang",
    "sent", "gesendete", "gesendet",
]

log = logging.getLogger("mail_monitor")

# ── Monitor-Status (thread-safe) ────────────────────────────────────────────
_status = {
    "running": False,
    "last_poll": None,
    "mails_processed": 0,
    "errors": [],
    "last_error": None,
}
_status_lock = threading.Lock()
_stop_event = threading.Event()


def get_monitor_status():
    with _status_lock:
        return dict(_status)


def _update_status(**kwargs):
    with _status_lock:
        _status.update(kwargs)


# ── HTML-Stripper ────────────────────────────────────────────────────────────
class _Strip(HTMLParser):
    def __init__(self):
        super().__init__()
        self._t = []
    def handle_data(self, d):
        self._t.append(d)
    def get(self):
        return ' '.join(self._t)

def strip_html(h):
    s = _Strip()
    s.feed(h or "")
    return s.get()


# ── OAuth2 / IMAP (extrahiert aus Mail-Archiver) ────────────────────────────
def _token_cache_path(email_addr):
    TOKEN_DIR.mkdir(exist_ok=True)
    safe = email_addr.replace("@", "_").replace(".", "_")
    return TOKEN_DIR / f"{safe}_token.json"


def _msal_app(konto):
    if not MSAL_OK:
        raise RuntimeError("msal nicht installiert: pip install msal")
    client_id = konto.get("oauth2_client_id", "").strip()
    tenant_id = konto.get("oauth2_tenant_id", "common").strip() or "common"
    if not client_id:
        raise RuntimeError(f"Keine OAuth2 Client-ID für {konto['email']}")

    cache = msal.SerializableTokenCache()
    cache_path = _token_cache_path(konto["email"])
    if cache_path.exists():
        cache.deserialize(cache_path.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=cache,
    )
    return app, cache, cache_path


def _save_token_cache(cache, path):
    if cache.has_state_changed:
        path.write_text(cache.serialize(), encoding="utf-8")


def get_oauth2_token(konto):
    """Holt OAuth2 Access Token (aus Cache oder Device-Flow)."""
    app, cache, cache_path = _msal_app(konto)
    email_addr = konto["email"]

    # Scope-Version prüfen
    version_path = cache_path.parent / (cache_path.stem + "_version.txt")
    if version_path.exists() and version_path.read_text().strip() != OAUTH_SCOPE_VERSION:
        log.info(f"Scope geändert, Token-Reset für {email_addr}")
        if cache_path.exists():
            cache_path.unlink()
        if version_path.exists():
            version_path.unlink()
        app, cache, cache_path = _msal_app(konto)

    # 1. Silent (aus Cache)
    accounts = app.get_accounts(username=email_addr)
    if accounts:
        result = app.acquire_token_silent(OAUTH_SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_token_cache(cache, cache_path)
            version_path.write_text(OAUTH_SCOPE_VERSION)
            return result["access_token"]

    # 2. Device-Code-Flow
    log.info(f"OAuth2 Login erforderlich für {email_addr}")
    flow = app.initiate_device_flow(scopes=OAUTH_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device-Flow fehlgeschlagen: {flow.get('error_description', '?')}")

    url = flow["verification_uri"]
    code = flow["user_code"]
    log.warning(f"OAUTH2 LOGIN: {email_addr} → {url} Code: {code}")

    # Browser öffnen
    try:
        webbrowser.open(url)
    except:
        pass

    # Warten (bis 5 Min)
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"OAuth2 fehlgeschlagen: {result.get('error_description', '?')}")

    _save_token_cache(cache, cache_path)
    version_path.write_text(OAUTH_SCOPE_VERSION)
    log.info(f"OAuth2 OK für {email_addr}")
    return result["access_token"]


def imap_connect(konto):
    """IMAP-Verbindung via OAuth2."""
    server = konto.get("imap_server", "outlook.office365.com")
    port = int(konto.get("imap_port", 993))
    use_ssl = konto.get("imap_ssl", True)
    email_addr = konto["email"]

    token = get_oauth2_token(konto)
    auth_string = f"user={email_addr}\x01auth=Bearer {token}\x01\x01".encode("utf-8")

    if use_ssl:
        imap = imaplib.IMAP4_SSL(server, port)
    else:
        imap = imaplib.IMAP4(server, port)
        try:
            imap.starttls()
        except:
            pass

    try:
        imap.sock.settimeout(IMAP_TIMEOUT)
    except:
        pass

    imap.authenticate("XOAUTH2", lambda x: auth_string)
    return imap


def _ordner_erlaubt(name):
    n = name.lower().strip()
    for a in ORDNER_AUSSCHLIESSEN:
        if a in n:
            return False
    for e in ORDNER_EINSCHLIESSEN:
        if e in n:
            return True
    return False


# ── Mail-Parsing (vereinfacht, kein Archiv-Speichern) ───────────────────────
def _decode_hdr(v):
    if not v:
        return ""
    parts = email.header.decode_header(v)
    res = []
    for p, cs in parts:
        if isinstance(p, bytes):
            try:
                res.append(p.decode(cs or 'utf-8', errors='replace'))
            except:
                res.append(p.decode('latin-1', errors='replace'))
        else:
            res.append(str(p))
    return " ".join(res)


def _extract_text(msg):
    plain = ""
    html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp:
                continue
            try:
                cs = part.get_content_charset() or 'utf-8'
                pl = part.get_payload(decode=True)
                if pl:
                    if ct == "text/plain":
                        plain += pl.decode(cs, errors='replace')
                    elif ct == "text/html":
                        html += pl.decode(cs, errors='replace')
            except:
                pass
    else:
        try:
            cs = msg.get_content_charset() or 'utf-8'
            pl = msg.get_payload(decode=True)
            if pl:
                if msg.get_content_type() == "text/plain":
                    plain = pl.decode(cs, errors='replace')
                else:
                    html = pl.decode(cs, errors='replace')
        except:
            pass
    return plain if plain else strip_html(html)


def _extract_attachments(msg):
    """Gibt Liste von Anhang-Dateinamen zurück (ohne zu speichern)."""
    names = []
    if not msg.is_multipart():
        return names
    for part in msg.walk():
        fn = part.get_filename()
        if fn:
            names.append(_decode_hdr(fn))
    return names


def _fallback_msg_id(konto_label, absender, an, datum_iso, betreff):
    """Erzeugt Fallback-ID wenn Message-ID fehlt."""
    raw = f"{konto_label}|{absender}|{an}|{datum_iso}|{(betreff or '')[:60]}"
    return "FALLBACK-" + hashlib.sha256(raw.encode('utf-8', errors='replace')).hexdigest()[:20]


def _compute_thread_id(msg_id, in_reply_to, references):
    """
    Berechnet thread_id: älteste bekannte Message-ID im Thread.
    Wenn In-Reply-To oder References vorhanden → die erste Reference ist Thread-Anker.
    Sonst → msg_id selbst ist Thread-Anker (neue Konversation).
    """
    if references:
        # References enthält älteste zuerst (RFC 2822)
        refs = [r.strip() for r in references.split() if r.strip().startswith("<")]
        if refs:
            return refs[0]
    if in_reply_to and in_reply_to.strip():
        return in_reply_to.strip()
    return msg_id or ""


def parse_raw_mail(raw_bytes, konto_label):
    """Parst RFC822-Bytes in ein dict. Extrahiert jetzt auch Threading-Header."""
    msg = email.message_from_bytes(raw_bytes)
    betreff = _decode_hdr(msg.get("Subject", ""))
    absender = _decode_hdr(msg.get("From", ""))
    an = _decode_hdr(msg.get("To", ""))
    cc = _decode_hdr(msg.get("Cc", ""))
    datum_str = msg.get("Date", "")
    msg_id = (msg.get("Message-ID", "") or "").strip()
    in_reply_to = (msg.get("In-Reply-To", "") or "").strip()
    mail_references = (msg.get("References", "") or "").strip()

    datum_obj = None
    datum_fmt = datum_str
    try:
        datum_obj = email.utils.parsedate_to_datetime(datum_str)
        datum_fmt = datum_obj.strftime("%Y-%m-%d %H:%M:%S")
    except:
        pass

    datum_iso = datum_obj.isoformat() if datum_obj else None

    # Fallback-ID wenn keine Message-ID
    if not msg_id:
        msg_id = _fallback_msg_id(konto_label, absender, an, datum_iso or datum_fmt, betreff)

    thread_id = _compute_thread_id(msg_id, in_reply_to, mail_references)
    text = _extract_text(msg)
    anhaenge = _extract_attachments(msg)

    return {
        "konto": konto_label,
        "betreff": betreff,
        "absender": absender,
        "an": an,
        "cc": cc,
        "datum": datum_fmt,
        "datum_iso": datum_iso,
        "message_id": msg_id,
        "in_reply_to": in_reply_to,
        "mail_references": mail_references,
        "thread_id": thread_id,
        "text": text[:6000],
        "anhaenge": anhaenge,
        "hat_anhaenge": len(anhaenge) > 0,
    }


# ── UID State ────────────────────────────────────────────────────────────────
def _load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text('utf-8'))
        except:
            pass
    return {}


def _save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), 'utf-8')


# ── Verarbeitung ─────────────────────────────────────────────────────────────
def _process_mail(mail_data, konto_label, folder_name):
    """Verarbeitet eine neue Mail: Klassifizierung + Task-Erstellung."""
    import sqlite3
    from llm_classifier import classify_mail
    from llm_response_gen import generate_draft

    betreff = mail_data.get("betreff", "")
    absender = mail_data.get("absender", "")
    text = mail_data.get("text", "")
    msg_id = mail_data.get("message_id", "")
    is_sent = "sent" in folder_name.lower() or "gesendete" in folder_name.lower()

    # Duplikat-Check
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    existing = db.execute("SELECT id FROM tasks WHERE message_id=?", (msg_id,)).fetchone()
    if existing:
        db.close()
        return None

    # Klassifizierung
    t0 = time.monotonic()
    result = classify_mail(konto_label, absender, betreff, text,
                          anhaenge=mail_data.get("anhaenge", []),
                          folder=folder_name, is_sent=is_sent)
    kat_ms = int((time.monotonic() - t0) * 1000)

    kategorie = result.get("kategorie", "Zur Kenntnis")
    konfidenz = result.get("konfidenz", "?")

    # Automatische Angebot-Aktion (Annahme/Ablehnung automatisch buchen)
    if kategorie == "Angebotsrueckmeldung" and result.get("angebot_aktion"):
        kunden_email_m = re.search(r'<([^>]+@[^>]+)>', absender)
        ke = kunden_email_m.group(1).lower() if kunden_email_m else absender.strip().lower()
        auto_result = _auto_angebot_aktion(result, ke, betreff, msg_id)
        if auto_result.get("aktion_durchgefuehrt"):
            result["_auto_aktion"] = auto_result

    _alog("Klassifizierung", f"→ {kategorie}",
          f"{absender[:60]} | {betreff[:80]} | Konfidenz: {konfidenz}",
          "warnung" if konfidenz == "niedrig" else "ok",
          dauer_ms=kat_ms)
    _elog('kira', 'mail_classified', f"{betreff[:100]}",
          source='mail_monitor', modul='mail_monitor', submodul='klassifizierung',
          actor_type='system', status='warnung' if konfidenz=='niedrig' else 'ok',
          duration_ms=kat_ms, context_type='mail', context_id=msg_id,
          result=f"{kategorie} | {konfidenz} | {absender[:60]}")

    # Nur handlungsrelevante Kategorien als Task anlegen
    skip_kategorien = ["Ignorieren", "Newsletter / Werbung", "Abgeschlossen"]
    if kategorie in skip_kategorien:
        db.close()
        return result

    # Antwort-Entwurf generieren
    entwurf = None
    if result.get("antwort_noetig"):
        try:
            kunden_email_m = re.search(r'<([^>]+@[^>]+)>', absender)
            kunden_email = kunden_email_m.group(1).lower() if kunden_email_m else absender.strip().lower()
            entwurf = generate_draft(betreff, absender, text, kunden_email)
        except:
            pass

    # Task erstellen
    from mail_classifier import kategorie_to_task_typ
    typ = kategorie_to_task_typ(kategorie)
    prio = result.get("prioritaet", "mittel")

    try:
        db.execute("""INSERT INTO tasks
            (typ, kategorie, titel, zusammenfassung, beschreibung,
             kunden_email, absender_rolle, empfohlene_aktion, kategorie_grund,
             betreff, konto, datum_mail, message_id,
             antwort_entwurf, claude_prompt,
             status, prioritaet, antwort_noetig,
             mit_termin, manuelle_pruefung, beantwortet)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (typ, kategorie, betreff[:200],
             result.get("zusammenfassung", ""),
             text[:2000],
             re.search(r'<([^>]+@[^>]+)>', absender).group(1).lower() if re.search(r'<([^>]+@[^>]+)>', absender) else "",
             result.get("absender_rolle", ""),
             result.get("empfohlene_aktion", ""),
             result.get("kategorie_grund", ""),
             betreff, konto_label,
             mail_data.get("datum", ""),
             msg_id,
             entwurf.get("entwurf", "") if entwurf else "",
             entwurf.get("claude_prompt", "") if entwurf else "",
             "offen", prio,
             1 if result.get("antwort_noetig") else 0,
             result.get("mit_termin", 0),
             result.get("manuelle_pruefung", 0),
             result.get("beantwortet", 0)))
        db.commit()
        task_id_new = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        _alog("Mail", "Neue Mail → Task",
              f"{konto_label} | {kategorie} | {betreff[:80]}",
              "ok", task_id=task_id_new)
        _elog('system', 'task_created', f"Task aus Mail: {kategorie} | {betreff[:80]}",
              source='mail_monitor', modul='mail_monitor', submodul='task_erstellung',
              actor_type='system', status='ok', context_type='mail', context_id=msg_id,
              result=str(task_id_new))
    except Exception as e:
        log.error(f"Task-Erstellung fehlgeschlagen: {e}")
        _alog("Mail", "Task-Erstellung fehlgeschlagen", f"{betreff[:80]}", "fehler", fehler=str(e)[:300])
        _elog('system', 'task_creation_failed', f"Task fehlgeschlagen: {betreff[:80]}",
              source='mail_monitor', modul='mail_monitor', submodul='task_erstellung',
              actor_type='system', status='fehler', context_type='mail', context_id=msg_id,
              error_message=str(e)[:300])
    finally:
        db.close()

    # In kunden.db speichern
    try:
        kdb = sqlite3.connect(str(KUNDEN_DB))
        kunden_email_m = re.search(r'<([^>]+@[^>]+)>', absender)
        ke = kunden_email_m.group(1).lower() if kunden_email_m else absender.strip().lower()
        kdb.execute("""INSERT OR IGNORE INTO interaktionen
            (konto_label, betreff, absender, kunden_email, datum, message_id, text_plain)
            VALUES (?,?,?,?,?,?,?)""",
            (konto_label, betreff, absender, ke,
             mail_data.get("datum", ""), msg_id, text[:6000]))
        kdb.commit()
        kdb.close()
    except:
        pass

    # In mail_index.db speichern (zentraler Index aller Mails)
    _index_mail(mail_data, konto_label, folder_name)

    return result


def _save_to_archive(mail_data: dict, raw_bytes: bytes, konto_label: str, folder_name: str) -> str:
    """
    Speichert eine neue Mail im lokalen Archiv-Ordner.
    Struktur: archiv_root/konto_folder/FOLDER/YYYY-MM-DD_betreff_hash8/
      - mail.json  — Metadaten + Text
      - mail.eml   — Roh-MIME
      - attachments/ — extrahierte Anhänge
    Gibt den mail_folder_pfad zurück, oder "" bei Fehler / Deaktiviert.
    """
    try:
        config = json.loads(CONFIG_FILE.read_text('utf-8'))
        ma = config.get('mail_archiv', {})
        if not ma.get('neue_mails_archivieren', True):
            return ""
        archiv_pfad = ma.get('pfad', '').strip()
        if not archiv_pfad:
            return ""
        archiv_root = Path(archiv_pfad)
        if not archiv_root.exists():
            return ""
    except Exception:
        return ""

    try:
        # Konto-Ordner: anfrage@raumkult.eu → anfrage_raumkult_eu
        konto_folder = konto_label.replace('@', '_').replace('.', '_').lower()
        # Ordner: INBOX bleibt INBOX
        safe_folder = re.sub(r'[<>:"/\\|?*]', '_', folder_name)
        # Mail-Unterordner: YYYY-MM-DD_betreff_hash8
        datum_part = (mail_data.get('datum_iso') or mail_data.get('datum', ''))[:10] or datetime.now().strftime('%Y-%m-%d')
        betreff_clean = re.sub(r'[^a-zA-Z0-9\u00c0-\u024f\s_-]', '', mail_data.get('betreff', 'nosubject'))
        betreff_clean = re.sub(r'\s+', '_', betreff_clean.strip())[:40]
        msg_id = mail_data.get('message_id', '')
        hash8 = hashlib.sha256((msg_id or datum_part).encode('utf-8', errors='replace')).hexdigest()[:8]
        mail_dir = archiv_root / konto_folder / safe_folder / f"{datum_part}_{betreff_clean}_{hash8}"
        mail_dir.mkdir(parents=True, exist_ok=True)

        eml_path = mail_dir / 'mail.eml'
        json_path = mail_dir / 'mail.json'

        # Überspringen falls bereits vorhanden
        if json_path.exists():
            return str(mail_dir)

        # mail.eml speichern
        eml_path.write_bytes(raw_bytes)

        # Anhänge extrahieren
        anhaenge_info = []
        att_dir = mail_dir / 'attachments'
        try:
            raw_msg = email.message_from_bytes(raw_bytes)
            if raw_msg.is_multipart():
                for part in raw_msg.walk():
                    fn = part.get_filename()
                    disp = str(part.get('Content-Disposition', ''))
                    if fn and 'attachment' in disp:
                        fn_safe = _decode_hdr(fn)
                        fn_disk = re.sub(r'[<>:"/\\|?*]', '_', fn_safe)[:80]
                        payload = part.get_payload(decode=True)
                        if payload:
                            att_dir.mkdir(exist_ok=True)
                            (att_dir / fn_disk).write_bytes(payload)
                            anhaenge_info.append(fn_safe)
        except Exception:
            pass

        # mail.json speichern (gleiche Struktur wie Archiver)
        mail_json = {
            'konto': mail_data.get('konto', konto_label),
            'betreff': mail_data.get('betreff', ''),
            'absender': mail_data.get('absender', ''),
            'an': mail_data.get('an', ''),
            'cc': mail_data.get('cc', ''),
            'datum': mail_data.get('datum', ''),
            'datum_iso': mail_data.get('datum_iso', ''),
            'message_id': msg_id,
            'in_reply_to': mail_data.get('in_reply_to', ''),
            'mail_references': mail_data.get('mail_references', ''),
            'text': mail_data.get('text', ''),
            'hat_anhaenge': bool(anhaenge_info or mail_data.get('hat_anhaenge')),
            'anhaenge': anhaenge_info or mail_data.get('anhaenge', []),
            'anhaenge_pfad': str(att_dir) if anhaenge_info else '',
            'eml_pfad': str(eml_path),
            'mail_folder_pfad': str(mail_dir),
            'archiviert_am': datetime.now().isoformat(),
            'sync_source': 'live_sync',
        }
        json_path.write_text(json.dumps(mail_json, ensure_ascii=False, indent=2), 'utf-8')
        return str(mail_dir)
    except Exception as e:
        log.debug(f"Archiv-Speichern fehlgeschlagen: {e}")
        return ""


def _index_mail(mail_data: dict, konto_label: str, folder_name: str):
    """
    Schreibt eine Mail in mail_index.db (zentraler Index).
    Idempotent: INSERT OR IGNORE verhindert Duplikate.
    Quelle: 'live_sync' (vom IMAP-Monitor in Echtzeit abgerufen).
    Liest eml_path und mail_folder_pfad aus mail_data falls vorhanden.
    """
    if not MAIL_INDEX_DB.exists():
        return  # DB noch nicht initialisiert → still überspringen

    try:
        conn = sqlite3.connect(str(MAIL_INDEX_DB))
        conn.execute("PRAGMA journal_mode=WAL")
        eml_path = mail_data.get('eml_path', '')
        mail_folder_pfad = mail_data.get('mail_folder_pfad', '')
        conn.execute("""
            INSERT OR IGNORE INTO mails
            (konto, konto_label, betreff, absender, an, cc,
             datum, datum_iso, message_id, folder,
             hat_anhaenge, anhaenge,
             in_reply_to, mail_references, thread_id,
             sync_source, text_plain, archiviert_am,
             eml_path, mail_folder_pfad)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            mail_data.get("konto", konto_label),
            konto_label,
            mail_data.get("betreff", ""),
            mail_data.get("absender", ""),
            mail_data.get("an", ""),
            mail_data.get("cc", ""),
            mail_data.get("datum", ""),
            mail_data.get("datum_iso", ""),
            mail_data.get("message_id", ""),
            folder_name,
            1 if mail_data.get("hat_anhaenge") else 0,
            json.dumps(mail_data.get("anhaenge", []), ensure_ascii=False),
            mail_data.get("in_reply_to", ""),
            mail_data.get("mail_references", ""),
            mail_data.get("thread_id", ""),
            "live_sync",
            mail_data.get("text", "")[:8000],
            datetime.now().isoformat(),
            eml_path,
            mail_folder_pfad,
        ))
        # Falls bereits vorhanden: eml_path + mail_folder_pfad nachfüllen wenn leer
        if eml_path or mail_folder_pfad:
            conn.execute("""
                UPDATE mails SET
                    eml_path = COALESCE(NULLIF(eml_path,''), ?),
                    mail_folder_pfad = COALESCE(NULLIF(mail_folder_pfad,''), ?)
                WHERE message_id=?
            """, (eml_path, mail_folder_pfad, mail_data.get("message_id", "")))
        conn.commit()
        conn.close()
    except Exception as e:
        log.debug(f"mail_index.db Schreiben fehlgeschlagen: {e}")


def _auto_angebot_aktion(result: dict, kunden_email: str, betreff: str, msg_id: str):
    """
    Führt automatische Datenbankaktionen aus wenn der Classifier eine Angebotsrückmeldung
    erkannt hat. Aktualisiert Angebot-Status und erstellt passenden Folge-Task.
    Gibt dict zurück: {aktion_durchgefuehrt, angebot_nummer, neue_aufgabe}
    """
    angebot_aktion = result.get("angebot_aktion")
    angebot_nummer = result.get("angebot_nummer")
    if not angebot_aktion:
        return {}

    try:
        import sqlite3 as _sq
        db = _sq.connect(str(TASKS_DB))
        db.row_factory = _sq.Row

        # Angebot finden: zuerst per Nummer, dann per E-Mail
        ang = None
        if angebot_nummer:
            ang = db.execute(
                "SELECT * FROM angebote WHERE a_nummer=? AND status='offen'",
                (angebot_nummer,)
            ).fetchone()
        if not ang and kunden_email:
            ang = db.execute(
                "SELECT * FROM angebote WHERE LOWER(kunde_email)=? AND status='offen' ORDER BY datum DESC LIMIT 1",
                (kunden_email.lower(),)
            ).fetchone()
        if not ang:
            db.close()
            return {}

        ang_id = ang["id"]
        ang_nr = ang["a_nummer"]
        kunde = ang["kunde_name"] or kunden_email

        if angebot_aktion == "angenommen":
            db.execute(
                "UPDATE angebote SET status='angenommen', grund_angenommen=? WHERE id=?",
                (f"Mail: {betreff[:200]}", ang_id)
            )
            # Folge-Task: Rechnung schreiben
            db.execute("""
                INSERT INTO tasks
                (typ, kategorie, titel, zusammenfassung, beschreibung,
                 kunden_email, empfohlene_aktion, betreff, konto,
                 status, prioritaet, antwort_noetig, message_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                "Rechnung", "Angebotsrueckmeldung",
                f"Rechnung schreiben: {kunde}",
                f"Angebot {ang_nr} von {kunde} wurde angenommen.",
                f"Angebot {ang_nr} wurde angenommen. Rechnung erstellen und senden.",
                kunden_email, "Rechnung erstellen und an Kunden senden",
                betreff[:200], "auto",
                "offen", "hoch", 0,
                f"auto-annahme-{msg_id[:40]}"
            ))
            _alog("Angebot", f"Angenommen: {ang_nr}",
                  f"{kunde} | Angebot angenommen → Rechnung-Task erstellt", "ok")
            _elog('system', 'angebot_angenommen', f"Angebot {ang_nr} angenommen von {kunde}",
                  source='mail_monitor', modul='mail_monitor', submodul='auto_aktion',
                  actor_type='system', status='ok', context_type='angebot', context_id=ang_nr)

        elif angebot_aktion == "abgelehnt":
            db.execute(
                "UPDATE angebote SET status='abgelehnt', grund_abgelehnt=? WHERE id=?",
                (f"Mail: {betreff[:200]}", ang_id)
            )
            _alog("Angebot", f"Abgelehnt: {ang_nr}",
                  f"{kunde} | Angebot abgelehnt", "warnung")
            _elog('system', 'angebot_abgelehnt', f"Angebot {ang_nr} abgelehnt von {kunde}",
                  source='mail_monitor', modul='mail_monitor', submodul='auto_aktion',
                  actor_type='system', status='warnung', context_type='angebot', context_id=ang_nr)

        elif angebot_aktion == "rueckfrage":
            # Nur loggen, kein Status-Update — Rückfrage = Angebot bleibt offen
            _alog("Angebot", f"Rückfrage: {ang_nr}",
                  f"{kunde} | Rückfrage zu Angebot", "ok")

        db.commit()
        db.close()
        return {"aktion_durchgefuehrt": angebot_aktion, "angebot_nummer": ang_nr, "kunde": kunde}

    except Exception as e:
        log.error(f"_auto_angebot_aktion Fehler: {e}")
        return {}


def _send_notification(new_tasks):
    """Sendet ntfy Push für neue Aufgaben."""
    if not new_tasks:
        return
    try:
        config = json.loads(CONFIG_FILE.read_text('utf-8'))
        ntfy = config.get("ntfy", {})
        if not ntfy.get("aktiv"):
            return
        topic = ntfy.get("topic_name", "")
        server = ntfy.get("server", "https://ntfy.sh")
        if not topic:
            return

        import urllib.request
        count = len(new_tasks)
        kategorien = {}
        for t in new_tasks:
            k = t.get("kategorie", "?")
            kategorien[k] = kategorien.get(k, 0) + 1
        detail = ", ".join(f"{v}x {k}" for k, v in kategorien.items())
        msg = f"Kira: {count} neue Mail(s) - {detail}"

        req = urllib.request.Request(
            f"{server}/{topic}",
            data=msg.encode('utf-8'),
            headers={"Title": "Kira Mail-Monitor", "Priority": "high" if any(t.get("antwort_noetig") for t in new_tasks) else "default"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log.error(f"ntfy Fehler: {e}")


# ── Konten laden ─────────────────────────────────────────────────────────────
def _load_accounts():
    """Lädt Konten aus dem Archiver-Config."""
    if not ARCHIVER_CFG.exists():
        log.error(f"Archiver-Config nicht gefunden: {ARCHIVER_CFG}")
        return []

    try:
        cfg = json.loads(ARCHIVER_CFG.read_text('utf-8'))
        konten = cfg.get("konten", [])
        return [k for k in konten if k.get("aktiv", True)]
    except Exception as e:
        log.error(f"Config-Fehler: {e}")
        return []


def _konto_label(email_addr):
    """Erzeugt Label aus E-Mail: anfrage@raumkult.eu → anfrage"""
    return email_addr.split("@")[0].lower()


# ── Poll-Zyklus ──────────────────────────────────────────────────────────────
def poll_all_accounts():
    """Ein Poll-Zyklus über alle Konten."""
    konten = _load_accounts()
    if not konten:
        log.warning("Keine aktiven Konten gefunden")
        return []

    state = _load_state()
    all_new_tasks = []

    for konto in konten:
        if _stop_event.is_set():
            break

        email_addr = konto["email"]
        label = _konto_label(email_addr)
        konto_state = state.get(email_addr, {})

        try:
            imap = imap_connect(konto)
        except Exception as e:
            log.error(f"IMAP-Verbindung fehlgeschlagen für {email_addr}: {e}")
            _update_status(last_error=f"{email_addr}: {e}")
            continue

        try:
            # Ordner auflisten
            status_ok, folder_list = imap.list()
            folders = []
            for entry in (folder_list or []):
                if isinstance(entry, bytes):
                    parts = entry.decode(errors='replace').split('"/"')
                    if parts:
                        folders.append(parts[-1].strip().strip('"'))

            for folder_name in folders:
                if _stop_event.is_set():
                    break
                if not _ordner_erlaubt(folder_name):
                    continue

                folder_key = f"{email_addr}:{folder_name}"
                last_uid = konto_state.get(folder_name, {}).get("last_uid", 0)

                try:
                    s, d = imap.select(f'"{folder_name}"', readonly=True)
                    if s != "OK":
                        continue

                    # Neue UIDs suchen
                    if last_uid > 0:
                        sr, ud = imap.uid("SEARCH", f"UID {last_uid + 1}:*")
                        if sr == "OK" and ud[0]:
                            new_uids = [u for u in ud[0].split() if u and int(u) > last_uid]
                        else:
                            new_uids = []
                    else:
                        # Erster Lauf: nur die letzten 20 Mails
                        sr, ud = imap.uid("SEARCH", "ALL")
                        if sr == "OK" and ud[0]:
                            all_uids = ud[0].split()
                            new_uids = all_uids[-20:] if len(all_uids) > 20 else all_uids
                        else:
                            new_uids = []

                    if not new_uids:
                        continue

                    log.info(f"  {label}/{folder_name}: {len(new_uids)} neue UIDs")

                    # Batch-Fetch
                    max_uid = last_uid
                    BATCH = 50
                    for i in range(0, len(new_uids), BATCH):
                        if _stop_event.is_set():
                            break
                        batch = new_uids[i:i + BATCH]
                        uid_range = b",".join(batch)
                        try:
                            fs, data = imap.uid("FETCH", uid_range, "(RFC822)")
                        except Exception as fe:
                            log.error(f"  Fetch-Fehler: {fe}")
                            break

                        if fs != "OK" or not data:
                            continue

                        for item in data:
                            if not isinstance(item, tuple) or len(item) < 2:
                                continue
                            raw = item[1]
                            if not isinstance(raw, bytes):
                                continue

                            mail_data = parse_raw_mail(raw, label)
                            # Ins Archiv speichern (JSON+EML+Anhänge)
                            pfad = _save_to_archive(mail_data, raw, label, folder_name)
                            if pfad:
                                mail_data['mail_folder_pfad'] = pfad
                                mail_data['eml_path'] = str(Path(pfad) / 'mail.eml')
                            result = _process_mail(mail_data, label, folder_name)
                            if result and result.get("kategorie") not in ("Ignorieren", "Newsletter / Werbung", "Abgeschlossen"):
                                all_new_tasks.append(result)

                        # Max UID tracken
                        batch_max = max(int(u) for u in batch)
                        if batch_max > max_uid:
                            max_uid = batch_max

                    # State updaten
                    if max_uid > last_uid:
                        if email_addr not in konto_state:
                            konto_state = {}
                        konto_state.setdefault(folder_name, {})["last_uid"] = max_uid

                except Exception as e:
                    log.error(f"  Ordner {folder_name}: {e}")

            state[email_addr] = konto_state

        except Exception as e:
            log.error(f"Konto {email_addr}: {e}")
            _update_status(last_error=f"{email_addr}: {e}")
        finally:
            try:
                imap.logout()
            except:
                pass

    _save_state(state)

    if all_new_tasks:
        _send_notification(all_new_tasks)

    with _status_lock:
        _status["last_poll"] = datetime.now().isoformat()
        _status["mails_processed"] += len(all_new_tasks)

    return all_new_tasks


# ── Monitor-Loop ─────────────────────────────────────────────────────────────
def run_monitor(interval_sec=300):
    """Endlos-Loop: Pollt alle Konten im Intervall."""
    _update_status(running=True)
    log.info(f"Mail-Monitor gestartet (Intervall: {interval_sec}s)")

    while not _stop_event.is_set():
        try:
            new_tasks = poll_all_accounts()
            if new_tasks:
                log.info(f"Monitor: {len(new_tasks)} neue Aufgaben erstellt")
        except Exception as e:
            log.error(f"Monitor-Fehler: {e}")
            _update_status(last_error=str(e))

        # Warten mit Stop-Check
        _stop_event.wait(timeout=interval_sec)

    _update_status(running=False)
    log.info("Mail-Monitor gestoppt")


def start_monitor_thread(interval_sec=None):
    """Startet den Monitor als Daemon-Thread. Aufgerufen von server.py."""
    if not MSAL_OK:
        log.warning("msal nicht installiert — Mail-Monitor deaktiviert")
        return None

    if not ARCHIVER_CFG.exists():
        log.warning(f"Archiver-Config nicht gefunden — Mail-Monitor deaktiviert")
        return None

    # Intervall aus Config laden
    if interval_sec is None:
        try:
            cfg = json.loads(CONFIG_FILE.read_text('utf-8'))
            interval_sec = cfg.get("mail_monitor", {}).get("intervall_sekunden", 900)
        except:
            interval_sec = 900

    _stop_event.clear()
    t = threading.Thread(target=run_monitor, args=(interval_sec,), daemon=True, name="MailMonitor")
    t.start()
    _elog('system', 'monitor_started', f"Mail-Monitor gestartet (Intervall: {interval_sec}s)",
          source='mail_monitor', modul='mail_monitor', actor_type='system', status='ok')
    return t


def stop_monitor():
    """Stoppt den Monitor."""
    _elog('system', 'monitor_stopped', 'Mail-Monitor gestoppt',
          source='mail_monitor', modul='mail_monitor', actor_type='system', status='ok')
    _stop_event.set()


# ── Standalone Test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except:
            pass

    print("Mail-Monitor — Einmaliger Poll-Test")
    print(f"Token-Ordner: {TOKEN_DIR}")
    print(f"Archiver-Config: {ARCHIVER_CFG}")

    konten = _load_accounts()
    print(f"Aktive Konten: {len(konten)}")
    for k in konten:
        print(f"  - {k['email']} ({k.get('auth_methode', '?')})")

    print("\nStarte Poll...")
    new_tasks = poll_all_accounts()
    print(f"\nFertig. {len(new_tasks)} neue Aufgaben.")
