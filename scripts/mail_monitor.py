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
    import kira_proaktiv as _proaktiv
    PROAKTIV_OK = True
except Exception:
    _proaktiv = None
    PROAKTIV_OK = False

try:
    from runtime_log import elog as _elog
except Exception:
    def _elog(*a, **k): return ""

try:
    import msal
    MSAL_OK = True
except ImportError:
    MSAL_OK = False

def _parse_amount(raw: str) -> float:
    """
    Universeller Betrags-Parser: erkennt DE/EN/gemischte Formate korrekt.

    Beispiele:
      '109.48'      → 109.48   (EN: Punkt = Dezimal)
      '109,48'      → 109.48   (DE: Komma = Dezimal)
      '1,234.56'    → 1234.56  (EN: Komma = Tausender, Punkt = Dezimal)
      '1.234,56'    → 1234.56  (DE: Punkt = Tausender, Komma = Dezimal)
      '1234'        → 1234.0
      '10.948,00'   → 10948.0  (DE: Punkt = Tausender)
      '10,948.00'   → 10948.0  (EN: Komma = Tausender)
      '$109.48'     → 109.48
      '4.960,62 €'  → 4960.62
    """
    if not raw:
        return 0.0
    s = str(raw).strip()
    # Waehrungszeichen und Leerzeichen entfernen
    for c in ('€', '$', '£', 'EUR', 'USD', 'CHF', '\u00a0', '\u202f'):
        s = s.replace(c, '')
    s = s.strip()
    if not s:
        return 0.0
    # Nur Ziffern, Punkte, Kommas und Minus behalten
    cleaned = re.sub(r'[^\d.,-]', '', s)
    if not cleaned:
        return 0.0
    has_dot = '.' in cleaned
    has_comma = ',' in cleaned
    if has_dot and has_comma:
        # Beide vorhanden: das LETZTE Trennzeichen ist der Dezimaltrenner
        last_dot = cleaned.rfind('.')
        last_comma = cleaned.rfind(',')
        if last_comma > last_dot:
            # DE-Format: 1.234,56 → Punkt=Tausender, Komma=Dezimal
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            # EN-Format: 1,234.56 → Komma=Tausender, Punkt=Dezimal
            cleaned = cleaned.replace(',', '')
    elif has_comma and not has_dot:
        # Nur Komma: pruefen ob Tausender oder Dezimal
        parts = cleaned.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            # 109,48 oder 1234,5 → Komma = Dezimal (DE)
            cleaned = cleaned.replace(',', '.')
        elif len(parts) == 2 and len(parts[1]) == 3:
            # 10,948 → Komma = Tausender (EN) oder 10,948 als Dezimal?
            # Wenn Teil vor Komma < 4 Stellen: Tausender-Trennzeichen
            cleaned = cleaned.replace(',', '')
        else:
            # Mehrere Kommas: 1,234,567 → EN Tausender
            cleaned = cleaned.replace(',', '')
    elif has_dot and not has_comma:
        # Nur Punkt: pruefen ob Tausender oder Dezimal
        parts = cleaned.split('.')
        if len(parts) == 2 and len(parts[1]) <= 2:
            # 109.48 → Punkt = Dezimal (EN)
            pass  # schon korrekt
        elif len(parts) == 2 and len(parts[1]) == 3:
            # 10.948 → Punkt = Tausender (DE)
            cleaned = cleaned.replace('.', '')
        else:
            # Mehrere Punkte: 1.234.567 → DE Tausender
            # Oder 1.234.567,89 (aber comma-Fall oben gefangen)
            if len(parts) > 2:
                cleaned = cleaned.replace('.', '')
            # else: single dot with >3 decimals — treat as decimal
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

SCRIPTS_DIR    = Path(__file__).parent
KNOWLEDGE_DIR  = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB       = KNOWLEDGE_DIR / "tasks.db"
KUNDEN_DB      = KNOWLEDGE_DIR / "kunden.db"
MAIL_INDEX_DB  = KNOWLEDGE_DIR / "mail_index.db"
CONFIG_FILE    = SCRIPTS_DIR / "config.json"

# Archiver-Pfade (Token-Cache teilen!)
_archiver_pfad = ""
try:
    _archiver_pfad = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8')).get("mail_archiv", {}).get("pfad", "").strip()
except Exception:
    pass
_ARCHIVER_FALLBACK = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv")
_archiver_base = Path(_archiver_pfad) if _archiver_pfad else _ARCHIVER_FALLBACK
# raumkult_config.json liegt im Archiv-Root, nicht im Archiv-Unterordner.
# Falls config.json auf einen Unterordner (z.B. .../Mail Archiv/Archiv) zeigt:
# Eine Ebene hochgehen falls raumkult_config.json dort nicht existiert.
if not (_archiver_base / "raumkult_config.json").exists() and (_archiver_base.parent / "raumkult_config.json").exists():
    ARCHIVER_DIR = _archiver_base.parent
else:
    ARCHIVER_DIR = _archiver_base
ARCHIVER_CFG  = ARCHIVER_DIR / "raumkult_config.json"
TOKEN_DIR     = ARCHIVER_DIR / "tokens"

# Monitor State
STATE_FILE    = KNOWLEDGE_DIR / "mail_monitor_state.json"

IMAP_TIMEOUT  = 60
OAUTH_SCOPES  = [
    "https://outlook.office.com/IMAP.AccessAsUser.All",
    "https://outlook.office.com/SMTP.Send",
]
OAUTH_SCOPE_VERSION = "v5_imap_smtp"  # Geändert → erzwingt Token-Refresh bei allen Konten

# ── Zentrale KIRA Microsoft Entra App ───────────────────────────────────────
KIRA_MS_CLIENT_ID    = "a0591b2d-86c3-4bc1-adf0-a10e197da07f"
KIRA_MS_TENANT_ID    = "common"
# Redirect-URI für System-Browser-Flow (loopback).
# In Azure Portal unter App a0591b2d → Authentication → Mobile and desktop applications
# muss http://localhost eingetragen sein (ohne Port — Microsoft akzeptiert dann alle Ports).
KIRA_MS_REDIRECT_URI = "http://localhost"

# ── Provider-Erkennung ───────────────────────────────────────────────────────
_DOMAIN_PROVIDER = {
    "outlook.com": "microsoft", "hotmail.com": "microsoft",
    "live.com": "microsoft", "live.de": "microsoft",
    "outlook.de": "microsoft", "msn.com": "microsoft",
    "gmail.com": "google", "googlemail.com": "google",
    "yahoo.com": "yahoo", "yahoo.de": "yahoo",
    "ymail.com": "yahoo",
    "aol.com": "aol",
    "gmx.de": "gmx", "gmx.net": "gmx", "gmx.com": "gmx",
    "web.de": "web_de",
    "t-online.de": "t_online",
    "icloud.com": "imap", "me.com": "imap",
}
_PROVIDER_SETTINGS = {
    "microsoft": {"imap_server": "outlook.office365.com", "imap_port": 993, "imap_ssl": True, "auth": "oauth2_microsoft"},
    "google":    {"imap_server": "imap.gmail.com",         "imap_port": 993, "imap_ssl": True, "auth": "oauth2_google"},
    "yahoo":     {"imap_server": "imap.mail.yahoo.com",    "imap_port": 993, "imap_ssl": True, "auth": "imap_password"},
    "aol":       {"imap_server": "imap.aol.com",           "imap_port": 993, "imap_ssl": True, "auth": "imap_password"},
    "gmx":       {"imap_server": "imap.gmx.net",           "imap_port": 993, "imap_ssl": True, "auth": "imap_password"},
    "web_de":    {"imap_server": "imap.web.de",            "imap_port": 993, "imap_ssl": True, "auth": "imap_password"},
    "t_online":  {"imap_server": "secureimap.t-online.de", "imap_port": 993, "imap_ssl": True, "auth": "imap_password"},
    "imap":      {"imap_server": "",                       "imap_port": 993, "imap_ssl": True, "auth": "imap_password"},
}

def detect_provider(email_addr: str) -> dict:
    """Erkennt Anbieter aus E-Mail-Domain und gibt Einstellungen zurück."""
    domain = email_addr.split("@")[-1].lower() if "@" in email_addr else ""
    if domain.endswith(".onmicrosoft.com"):
        provider = "microsoft"
    else:
        provider = _DOMAIN_PROVIDER.get(domain, "imap")
    settings = dict(_PROVIDER_SETTINGS.get(provider, _PROVIDER_SETTINGS["imap"]))
    settings["provider"] = provider
    settings["domain"] = domain
    return settings


def _provider_stage1(domain: str, email_addr: str) -> dict:
    """Stufe 1: Domain-Heuristik + bekannte Provider."""
    provider = _DOMAIN_PROVIDER.get(domain, None)
    if domain.endswith(".onmicrosoft.com"):
        provider = "microsoft"
    if provider:
        s = dict(_PROVIDER_SETTINGS.get(provider, _PROVIDER_SETTINGS["imap"]))
        s.update({"stage": 1, "provider": provider, "confidence": "high", "reason": "known_domain"})
        return s
    return {"stage": 1, "provider": None, "confidence": "low", "reason": "unknown_domain"}


def _provider_stage2(domain: str) -> dict:
    """Stufe 2: DNS MX + Autodiscover HTTP-Check."""
    import subprocess, urllib.request as _ur
    result = {"stage": 2, "provider": None, "confidence": "low"}

    # MX-Record via nslookup prüfen (Windows)
    try:
        out = subprocess.run(
            ["nslookup", "-type=MX", domain],
            capture_output=True, text=True, timeout=5, creationflags=0x08000000
        ).stdout.lower()
        ms_mx_hints = ["protection.outlook.com", "mail.protection.outlook.com", "microsoft.com", "outlook.com"]
        if any(h in out for h in ms_mx_hints):
            s = dict(_PROVIDER_SETTINGS["microsoft"])
            s.update({"stage": 2, "provider": "microsoft", "confidence": "high", "reason": "mx_microsoft"})
            return s
    except Exception:
        pass

    # Autodiscover HTTP-Check
    autodiscover_urls = [
        f"https://autodiscover.{domain}/autodiscover/autodiscover.xml",
        f"https://autodiscover-s.outlook.com/autodiscover/autodiscover.xml",
    ]
    for url in autodiscover_urls:
        try:
            req = _ur.Request(url, method="HEAD")
            with _ur.urlopen(req, timeout=4) as r:
                server_hdr = r.headers.get("Server", "").lower()
                if "microsoft" in server_hdr or "exchange" in server_hdr or r.status in (200, 401):
                    s = dict(_PROVIDER_SETTINGS["microsoft"])
                    s.update({"stage": 2, "provider": "microsoft", "confidence": "high", "reason": f"autodiscover_{url[:30]}"})
                    return s
        except Exception:
            pass

    return result


def _provider_stage3(email_addr: str, domain: str) -> dict:
    """Stufe 3: Aktiver Microsoft-Probe via OAuth-Discovery."""
    import urllib.request as _ur
    result = {"stage": 3, "is_microsoft": False}
    try:
        # Microsoft OpenID-Config für diese Domain abfragen
        url = f"https://login.microsoftonline.com/{domain}/v2.0/.well-known/openid-configuration"
        with _ur.urlopen(url, timeout=6) as r:
            data = json.loads(r.read())
        if "authorization_endpoint" in data and "microsoft" in data.get("issuer", "").lower():
            result["is_microsoft"] = True
            result["reason"] = "ms_openid_config"
            result["tenant_hint"] = data.get("issuer", "")
    except Exception:
        pass

    # Fallback: IMAP Autodiscover via outlook EWS
    if not result["is_microsoft"]:
        try:
            import socket
            sock = socket.create_connection(("outlook.office365.com", 993), timeout=3)
            sock.close()
            # Wenn EWS erreichbar: als Microsoft-Kandidat merken
            result["ews_reachable"] = True
        except Exception:
            pass

    return result


def detect_provider_advanced(email_addr: str) -> dict:
    """3-stufige Provider-Erkennung: Domain → DNS/Autodiscover → MS-Probe."""
    domain = email_addr.split("@")[-1].lower() if "@" in email_addr else ""
    base = {"email": email_addr, "domain": domain, "stages": []}

    # Stufe 1
    s1 = _provider_stage1(domain, email_addr)
    base["stages"].append(s1)
    if s1.get("confidence") == "high":
        base.update({k: v for k, v in s1.items() if k not in ("stage", "confidence", "reason", "stages")})
        base["confidence"] = "high"
        base["detection_stage"] = 1
        return base

    # Stufe 2: DNS + Autodiscover
    s2 = _provider_stage2(domain)
    base["stages"].append(s2)
    if s2.get("provider"):
        base.update({k: v for k, v in s2.items() if k not in ("stage", "confidence", "reason", "stages")})
        base["confidence"] = s2.get("confidence", "medium")
        base["detection_stage"] = 2
        if base.get("confidence") == "high":
            return base

    # Stufe 3: MS-Probe
    s3 = _provider_stage3(email_addr, domain)
    base["stages"].append(s3)
    if s3.get("is_microsoft"):
        s = dict(_PROVIDER_SETTINGS["microsoft"])
        base.update(s)
        base["provider"] = "microsoft"
        base["confidence"] = "high"
        base["detection_stage"] = 3
        return base

    # Fallback: IMAP
    if not base.get("provider"):
        base.update(dict(_PROVIDER_SETTINGS["imap"]))
        base["provider"] = "imap"
        base["confidence"] = "low"
        base["detection_stage"] = 0
    return base

# ── Account Health Status (in-memory) ───────────────────────────────────────
_account_health: dict = {}  # email → {status, last_check, error, inbox_count}
_health_lock = threading.Lock()

# Fallback-Listen wenn kein config.json-Eintrag vorhanden
ORDNER_AUSSCHLIESSEN = [
    "spam", "junk", "trash", "papierkorb", "outbox",
    "archive", "archiv", "unerwünscht", "unerwuenscht",
    "kalender", "kontakte", "notizen", "aufgaben", "journal",
    "snoozed", "postausgang", "verlauf",
]
ORDNER_EINSCHLIESSEN = [
    "inbox", "posteingang", "eingang",
    "sent", "gesendete", "gesendet",
    "entwürfe", "entwurfe", "drafts",
    "gelöschte", "geloeschte", "deleted", "papierkorb", "trash",
]


def _get_sync_ordner(email_addr: str) -> list:
    """Liefert konfigurierte Sync-Ordner für ein Konto aus config.json.
    Gibt eine Liste von Ordnernamen zurück (case-insensitive Substring-Match).
    Fallback: ORDNER_EINSCHLIESSEN wenn keine Config vorhanden."""
    try:
        cfg = json.loads(CONFIG_FILE.read_text('utf-8'))
        sync = cfg.get('mail_archiv', {}).get('sync_ordner', {})
        if email_addr in sync and sync[email_addr]:
            return [o.lower().strip() for o in sync[email_addr]]
    except Exception:
        pass
    return ORDNER_EINSCHLIESSEN

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


def _msal_app_kira(email_addr: str):
    """MSAL App mit der zentralen KIRA Entra App (kein per-Konto client_id nötig)."""
    if not MSAL_OK:
        raise RuntimeError("msal nicht installiert: pip install msal")
    cache = msal.SerializableTokenCache()
    cache_path = _token_cache_path(email_addr)
    if cache_path.exists():
        cache.deserialize(cache_path.read_text(encoding="utf-8"))
    app = msal.PublicClientApplication(
        KIRA_MS_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{KIRA_MS_TENANT_ID}",
        token_cache=cache,
    )
    return app, cache, cache_path


def _save_token_cache(cache, path):
    if cache.has_state_changed:
        path.write_text(cache.serialize(), encoding="utf-8")


def get_oauth2_token(konto):
    """Holt OAuth2 Access Token aus dem KIRA-App-Cache (silent).
    Retry-Logik: bei Netzwerk-/Timeout-Fehlern bis zu 2 Wiederholungen.
    Cache wird auch nach Refresh-Token-Nutzung gespeichert."""
    email_addr = konto["email"]
    # Immer zentrale KIRA-App nutzen — per-konto oauth2_client_id ist veraltet.
    # start_oauth_browser_flow() speichert immer unter KIRA-App-Client-ID.
    app, cache, cache_path = _msal_app_kira(email_addr)

    # Scope-Version prüfen — bei Änderung Cache leeren und neu mit KIRA-App aufbauen
    version_path = cache_path.parent / (cache_path.stem + "_version.txt")
    if version_path.exists() and version_path.read_text().strip() != OAUTH_SCOPE_VERSION:
        log.info(f"Scope geändert, Token-Reset für {email_addr}")
        if cache_path.exists():
            cache_path.unlink()
        if version_path.exists():
            version_path.unlink()
        app, cache, cache_path = _msal_app_kira(email_addr)  # neu initialisieren

    # Silent aus Cache — mit Retry bei Netzwerk-Fehlern
    MAX_RETRIES = 2
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        accounts = app.get_accounts(username=email_addr)
        if accounts:
            try:
                result = app.acquire_token_silent(OAUTH_SCOPES, account=accounts[0])
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    import time
                    time.sleep(2 * (attempt + 1))
                    log.warning(f"OAuth2 silent retry {attempt+1} für {email_addr}: {e}")
                    # Cache neu laden (evtl. wurde er extern aktualisiert)
                    app, cache, cache_path = _msal_app_kira(email_addr)
                    continue
                else:
                    log.error(f"OAuth2 silent fehlgeschlagen nach {MAX_RETRIES+1} Versuchen für {email_addr}: {e}")
                    break
            if result and "access_token" in result:
                _save_token_cache(cache, cache_path)
                version_path.write_text(OAUTH_SCOPE_VERSION)
                return result["access_token"]
            elif result and "error" in result:
                err_desc = result.get("error_description", result.get("error", ""))
                log.warning(f"OAuth2 silent Fehler für {email_addr}: {err_desc}")
                # Bei interaction_required: Token abgelaufen, kein Retry sinnvoll
                if "interaction_required" in str(result.get("error", "")):
                    break
                if attempt < MAX_RETRIES:
                    import time
                    time.sleep(2 * (attempt + 1))
                    continue
            else:
                break  # Kein result oder kein Token — kein Retry
        else:
            break  # Kein Account im Cache

    # Cache trotzdem speichern (MSAL könnte Refresh-Token intern aktualisiert haben)
    _save_token_cache(cache, cache_path)

    # Kein Token → Reconnect über UI-Wizard erforderlich (kein Device-Flow)
    log.warning(f"OAuth2 Token fehlt für {email_addr} — Reconnect über Einstellungen nötig")
    raise RuntimeError(f"TOKEN_ABGELAUFEN:{email_addr}")


# ── OAuth2 Jobs (für Browser-Flow aus UI) ───────────────────────────────────
_oauth_jobs: dict = {}  # job_id → {status, email, error, token}
_oauth_jobs_lock = threading.Lock()


def start_oauth_browser_flow(email_addr: str, job_id: str):
    """Startet Browser-OAuth in Thread. Status via get_oauth_job_status()."""
    def _run():
        try:
            app, cache, cache_path = _msal_app_kira(email_addr)
            # Silent zuerst
            accounts = app.get_accounts(username=email_addr)
            if accounts:
                result = app.acquire_token_silent(OAUTH_SCOPES, account=accounts[0])
                if result and "access_token" in result:
                    _save_token_cache(cache, cache_path)
                    with _oauth_jobs_lock:
                        _oauth_jobs[job_id] = {"status": "done", "email": email_addr, "error": None}
                    log.info(f"OAuth silent OK für {email_addr}")
                    return
            # Interaktiver Browser-Flow
            log.info(f"Browser-OAuth gestartet für {email_addr}")
            result = app.acquire_token_interactive(
                scopes=OAUTH_SCOPES,
                login_hint=email_addr,
                # redirect_uri wird von MSAL automatisch auf http://localhost:PORT gesetzt.
                # http://localhost muss in Azure App (a0591b2d) unter
                # Mobile and desktop applications eingetragen sein (ist es).
            )
            if "access_token" in result:
                _save_token_cache(cache, cache_path)
                with _oauth_jobs_lock:
                    _oauth_jobs[job_id] = {"status": "done", "email": email_addr, "error": None}
                log.info(f"Browser-OAuth OK für {email_addr}")
            else:
                err = result.get("error_description") or result.get("error") or "Unbekannter Fehler"
                with _oauth_jobs_lock:
                    _oauth_jobs[job_id] = {"status": "error", "email": email_addr, "error": err}
                log.error(f"Browser-OAuth Fehler für {email_addr}: {err}")
        except Exception as e:
            with _oauth_jobs_lock:
                _oauth_jobs[job_id] = {"status": "error", "email": email_addr, "error": str(e)}
            log.error(f"Browser-OAuth Exception für {email_addr}: {e}")

    with _oauth_jobs_lock:
        _oauth_jobs[job_id] = {"status": "pending", "email": email_addr, "error": None}
    t = threading.Thread(target=_run, daemon=True)
    t.start()


def get_oauth_job_status(job_id: str) -> dict:
    with _oauth_jobs_lock:
        return dict(_oauth_jobs.get(job_id, {"status": "unbekannt"}))


def test_microsoft_app() -> dict:
    """Testet ob die zentrale KIRA Entra App erreichbar und gültig ist."""
    if not MSAL_OK:
        return {"ok": False, "error": "msal nicht installiert"}
    try:
        import urllib.request as _ur
        # Einfacher Discovery-Request gegen den OIDC-Endpoint der App
        url = f"https://login.microsoftonline.com/{KIRA_MS_TENANT_ID}/v2.0/.well-known/openid-configuration"
        with _ur.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
        # MSAL App instanziieren (kein Token-Request — nur Erreichbarkeit)
        app = msal.PublicClientApplication(
            KIRA_MS_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{KIRA_MS_TENANT_ID}",
        )
        return {
            "ok": True,
            "client_id": KIRA_MS_CLIENT_ID,
            "tenant": KIRA_MS_TENANT_ID,
            "issuer": data.get("issuer", ""),
            "token_endpoint": data.get("token_endpoint", "")[:60],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ── Account Health Check ─────────────────────────────────────────────────────
def check_account_health(email_addr: str) -> dict:
    """Echte IMAP-Verbindungsprüfung für ein Konto."""
    konten = _load_accounts()
    konto = next((k for k in konten if k["email"].lower() == email_addr.lower()), None)
    if not konto:
        result = {"status": "unbekannt", "error": "Konto nicht gefunden", "inbox_count": 0}
    else:
        try:
            imap = imap_connect(konto)
            typ, data = imap.select("INBOX", readonly=True)
            try:
                v = data[0]
                inbox_count = int(v.decode('ascii', errors='ignore').strip() if isinstance(v, bytes) else v)
            except Exception:
                inbox_count = 0
            imap.logout()
            result = {"status": "ok", "error": None, "inbox_count": inbox_count}
        except Exception as e:
            err = str(e)
            if "authentication" in err.lower() or "login" in err.lower() or "token" in err.lower():
                status = "auth_fehler"
            else:
                status = "fehler"
            result = {"status": status, "error": err[:200], "inbox_count": 0}
    result["email"] = email_addr
    result["last_check"] = datetime.utcnow().isoformat()
    with _health_lock:
        _account_health[email_addr] = result
    return result


def get_all_health_status() -> dict:
    """Gibt gecachten Health-Status aller Konten zurück."""
    with _health_lock:
        return dict(_account_health)


def get_smtp_settings(konto: dict) -> dict:
    """Gibt SMTP-Einstellungen für ein Konto zurück (basierend auf Provider/IMAP-Server)."""
    imap_server = konto.get("imap_server", "")
    if "outlook.office365" in imap_server or konto.get("auth_methode") == "oauth2":
        return {"server": "smtp.office365.com", "port": 587, "starttls": True, "auth": "oauth2"}
    if "gmail" in imap_server:
        return {"server": "smtp.gmail.com", "port": 587, "starttls": True, "auth": "password"}
    if "gmx" in imap_server:
        return {"server": "mail.gmx.net", "port": 587, "starttls": True, "auth": "password"}
    if "web.de" in imap_server:
        return {"server": "smtp.web.de", "port": 587, "starttls": True, "auth": "password"}
    # Generic SMTP guess
    domain = konto.get("email", "").split("@")[-1]
    return {"server": f"smtp.{domain}", "port": 587, "starttls": True, "auth": "password"}


def run_full_connection_test(email_addr: str) -> dict:
    """Voller Verbindungstest: IMAP read + SMTP send an sich selbst + Empfangscheck."""
    import smtplib, imaplib, email as _email
    from email.mime.text import MIMEText
    result = {"email": email_addr, "imap_ok": False, "smtp_ok": False, "roundtrip_ok": False,
              "imap_error": None, "smtp_error": None, "roundtrip_error": None,
              "inbox_count": 0, "timestamp": datetime.utcnow().isoformat()}

    konten = _load_accounts()
    konto = next((k for k in konten if k["email"].lower() == email_addr.lower()), None)
    if not konto:
        result["imap_error"] = "Konto nicht gefunden"
        return result

    # 1. IMAP-Test
    try:
        imap = imap_connect(konto)
        typ, data = imap.select("INBOX", readonly=True)
        try:
            v = data[0]
            result["inbox_count"] = int(v.decode('ascii', errors='ignore').strip() if isinstance(v, bytes) else v)
        except Exception:
            result["inbox_count"] = 0
        imap.logout()
        result["imap_ok"] = True
    except Exception as e:
        result["imap_error"] = str(e)[:200]

    # 2. SMTP-Sendetest (nur wenn IMAP ok)
    if result["imap_ok"]:
        smtp_cfg = get_smtp_settings(konto)
        test_subject = f"KIRA Verbindungstest {datetime.utcnow().strftime('%H:%M:%S')}"
        auth_methode = konto.get("auth_methode", "oauth2")
        use_password_smtp = auth_methode in ("imap_password", "imap", "password") or \
                            "password" in auth_methode or smtp_cfg.get("auth") == "password"
        try:
            msg = MIMEText(f"Dies ist ein automatischer KIRA-Verbindungstest.\nZeitpunkt: {datetime.utcnow().isoformat()}", "plain", "utf-8")
            msg["Subject"] = test_subject
            msg["From"] = email_addr
            msg["To"] = email_addr

            smtp = smtplib.SMTP(smtp_cfg["server"], smtp_cfg["port"], timeout=15)
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()

            if use_password_smtp:
                # Passwort-Auth fuer SMTP (IMAP-Passwort-Konten: GMX, web.de, custom IMAP etc.)
                import base64 as _b64
                passwort = konto.get("passwort", "") or konto.get("password", "")
                if passwort.startswith("enc:"):
                    passwort = _b64.b64decode(passwort[4:]).decode("utf-8", errors="ignore")
                login = konto.get("login", email_addr)
                smtp.login(login, passwort)
            else:
                # XOAUTH2 fuer Microsoft OAuth2 / Google OAuth2
                token = get_oauth2_token(konto)
                auth_string = f"user={email_addr}\x01auth=Bearer {token}\x01\x01"
                import base64 as _b64
                auth_b64 = _b64.b64encode(auth_string.encode()).decode()
                smtp.docmd("AUTH", f"XOAUTH2 {auth_b64}")

            smtp.sendmail(email_addr, [email_addr], msg.as_string())
            smtp.quit()
            result["smtp_ok"] = True
            result["test_subject"] = test_subject

            # 3. Empfangs-Check: 30s warten, dann INBOX nach Testmail suchen
            import time as _time
            _time.sleep(30)
            try:
                imap2 = imap_connect(konto)
                imap2.select("INBOX")
                _, ids = imap2.search(None, f'SUBJECT "{test_subject}"')
                imap2.logout()
                result["roundtrip_ok"] = bool(ids and ids[0])
                if not result["roundtrip_ok"]:
                    result["roundtrip_error"] = "Testmail nicht in INBOX gefunden (ggf. noch nicht angekommen)"
            except Exception as e:
                result["roundtrip_error"] = str(e)[:200]
        except Exception as e:
            result["smtp_error"] = str(e)[:200]

    with _health_lock:
        _account_health[email_addr] = {
            "status": "ok" if result["imap_ok"] else "fehler",
            "error": result["imap_error"],
            "inbox_count": result["inbox_count"],
            "last_check": result["timestamp"],
            "volltest": result,
        }

    return result


# Job-System für async Volltest
_volltest_jobs: dict = {}
_volltest_lock = threading.Lock()

def start_volltest(email_addr: str, job_id: str):
    """Startet Volltest (IMAP + SMTP + Roundtrip) in Thread."""
    def _run():
        try:
            r = run_full_connection_test(email_addr)
            with _volltest_lock:
                _volltest_jobs[job_id] = {"status": "done", "result": r}
        except Exception as e:
            with _volltest_lock:
                _volltest_jobs[job_id] = {"status": "error", "error": str(e)}
    with _volltest_lock:
        _volltest_jobs[job_id] = {"status": "pending", "email": email_addr}
    threading.Thread(target=_run, daemon=True).start()

def get_volltest_status(job_id: str) -> dict:
    with _volltest_lock:
        return dict(_volltest_jobs.get(job_id, {"status": "unbekannt"}))


def imap_connect(konto, _retry=0):
    """IMAP-Verbindung via OAuth2 (Microsoft/Google) oder IMAP-Passwort.
    Bei Verbindungs-/Auth-Fehlern: 1 Retry mit frischem Token."""
    server = konto.get("imap_server", "outlook.office365.com")
    port = int(konto.get("imap_port", 993))
    use_ssl = konto.get("imap_ssl", True)
    email_addr = konto["email"]
    auth_methode = konto.get("auth_methode", "oauth2_microsoft")

    try:
        if use_ssl:
            imap = imaplib.IMAP4_SSL(server, port)
        else:
            imap = imaplib.IMAP4(server, port)
            try:
                imap.starttls()
            except:
                pass
    except (OSError, TimeoutError, ConnectionError) as e:
        if _retry < 1:
            import time
            log.warning(f"IMAP-Verbindung fehlgeschlagen ({email_addr}), Retry in 5s: {e}")
            time.sleep(5)
            return imap_connect(konto, _retry=_retry + 1)
        raise

    try:
        imap.sock.settimeout(IMAP_TIMEOUT)
    except:
        pass

    # Passwort-Auth wenn auth_methode imap/imap_password/password enthält
    use_password = auth_methode in ("imap_password", "imap", "password") or \
                   "password" in auth_methode or auth_methode == ""
    if use_password:
        passwort = konto.get("passwort", "") or konto.get("password", "")
        login = konto.get("login", email_addr)
        if not passwort:
            raise RuntimeError(f"Kein Passwort für {email_addr} hinterlegt")
        imap.login(login, passwort)
    else:
        # OAuth2 (Microsoft XOAUTH2 / Google) — auth_methode: oauth2, oauth2_microsoft, oauth2_google
        try:
            token = get_oauth2_token(konto)
            auth_string = f"user={email_addr}\x01auth=Bearer {token}\x01\x01".encode("utf-8")
            imap.authenticate("XOAUTH2", lambda x: auth_string)
        except imaplib.IMAP4.error as e:
            # XOAUTH2-Auth abgelehnt — bei erstem Versuch Token-Cache leeren und Retry
            if _retry < 1 and "AUTHENTICATE" in str(e).upper():
                log.warning(f"XOAUTH2 Auth fehlgeschlagen ({email_addr}), Token-Cache leeren + Retry: {e}")
                try:
                    imap.logout()
                except:
                    pass
                # Token-Cache-Datei nicht loeschen — MSAL Refresh soll erneut versucht werden
                import time
                time.sleep(3)
                return imap_connect(konto, _retry=_retry + 1)
            raise

    return imap


def _imap_connect_konto(email_addr: str):
    """Lädt Konto-Config und baut IMAP-Verbindung auf. Gibt IMAP-Objekt oder None zurück."""
    try:
        archiver_cfg = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\raumkult_config.json")
        konten = []
        if archiver_cfg.exists():
            cfg = json.loads(archiver_cfg.read_text('utf-8'))
            konten = cfg.get('konten', [])
        # Zusätzlich aus Kira config.json
        kira_cfg_path = CONFIG_FILE
        if kira_cfg_path.exists():
            kira_cfg = json.loads(kira_cfg_path.read_text('utf-8'))
            konten += kira_cfg.get('mail_konten', {}).get('konten', [])
        konto = next((k for k in konten if k.get('email') == email_addr), None)
        if not konto:
            return None
        return imap_connect(konto)
    except Exception:
        return None


def _ordner_erlaubt(name, sync_ordner_liste=None):
    """Prüft ob ein IMAP-Ordner vom mail_monitor verarbeitet werden soll.
    sync_ordner_liste: config-basierte Liste (aus _get_sync_ordner()), None = Fallback-Heuristik."""
    n = name.lower().strip()
    if sync_ordner_liste is not None:
        # Config-basiert: Ordner erlaubt wenn einer der konfigurierten Namen enthalten ist
        return any(s in n or n in s for s in sync_ordner_liste)
    # Fallback: Hardcoded-Heuristik
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


# ── Anthropic Billing Push (session-oo) ──────────────────────────────────────
def _check_anthropic_billing(absender: str, betreff: str, text: str):
    """Erkennt Anthropic-Zahlungsmails und sendet Pushover-Benachrichtigung."""
    try:
        absender_lower = absender.lower()
        if 'anthropic.com' not in absender_lower:
            return
        betreff_lower = betreff.lower()
        text_lower    = (text or '').lower()
        billing_keywords = ('invoice', 'payment', 'receipt', 'charged', 'subscription',
                            'rechnung', 'zahlung', 'abrechnung', 'abbuchung')
        if not any(kw in betreff_lower or kw in text_lower for kw in billing_keywords):
            return
        # Betrag extrahieren
        betrag_str = ""
        betrag_m = re.search(r'(?:USD|EUR|CHF|[\$€£])\s*([\d,]+\.?\d{0,2})'
                             r'|(\d{1,6}[.,]\d{2})\s*(?:USD|EUR|CHF|[\$€£])',
                             text or betreff)
        if betrag_m:
            betrag_str = " | Betrag: " + (betrag_m.group(1) or betrag_m.group(2))
        push_msg = "Anthropic Zahlung ausgefuehrt" + betrag_str
        # Pushover via PowerShell
        ps_script = r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\notivy.ps1"
        import subprocess
        subprocess.Popen(
            ['powershell', '-NonInteractive', '-File', ps_script,
             '-Message', push_msg, '-Priority', '1'],
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        _elog('system', 'anthropic_billing_push',
              f'Anthropic Zahlung erkannt: {betreff[:80]}{betrag_str}',
              source='mail_monitor', modul='billing', actor_type='system', status='ok')
    except Exception as _e:
        _elog('system', 'anthropic_billing_fehler', f'Billing-Check Fehler: {_e}',
              source='mail_monitor', modul='billing', actor_type='system', status='fehler')


# ── Eingangsrechnungs-Auto-Scan (session-bbb) ─────────────────────────────────
def _auto_scan_eingangsrechnung(mail_data: dict, konto_label: str, kategorie: str,
                                 msg_id: str, absender: str, betreff: str, text: str):
    """
    Wenn kategorie 'Rechnung / Beleg': betrag extrahieren + Eintrag in geschaeft-Tabelle.
    Idempotent (ON CONFLICT IGNORE via mail_ref).
    """
    if kategorie not in ('Rechnung / Beleg',):
        return
    try:
        # Betrag per Regex aus Text extrahieren (EUR-Betrag)
        betrag = 0.0
        _betrag_patterns = [
            r'(?:Gesamtbetrag|Betrag|Total|Summe|Rechnungsbetrag|Amount|Charged)[^\d]*?([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})',
            r'(?:Gesamtbetrag|Betrag|Total|Summe|Rechnungsbetrag|Amount|Charged)[^\d]*?([\d]+[.,]\d{2})',
            r'([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*(?:EUR|€|\$|USD)',
            r'(?:EUR|€|\$|USD)\s*([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})',
            r'([\d]+[.,]\d{2})\s*(?:EUR|€|\$|USD)',
        ]
        _combined = betreff + '\n' + text[:3000]
        for _pat in _betrag_patterns:
            _m = re.search(_pat, _combined, re.IGNORECASE)
            if _m:
                betrag = _parse_amount(_m.group(1))
                if betrag > 0:
                    break

        # Absender-E-Mail
        _se_m = re.search(r'<([^>]+@[^>]+)>', absender)
        absender_email = _se_m.group(1).lower() if _se_m else absender.strip().lower()
        absender_name  = absender.split('<')[0].strip() if '<' in absender else absender_email

        db = sqlite3.connect(str(TASKS_DB))
        db.execute("""INSERT OR IGNORE INTO geschaeft
            (typ, datum, betrag, gegenpartei, gegenpartei_email, betreff, konto, mail_ref, quelle)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            ('eingangsrechnung',
             mail_data.get('datum', '')[:10],
             betrag if betrag > 0 else None,
             absender_name[:200],
             absender_email[:200],
             betreff[:500],
             konto_label,
             msg_id,
             'mail_monitor'))
        db.commit()
        db.close()
        _elog('system', 'eingangsrechnung_erkannt',
              f'Eingangsrechnung: {absender_email} | {betrag:.2f} EUR | {betreff[:60]}',
              source='mail_monitor', modul='eingangsrechnungen', actor_type='system',
              status='ok', context_id=msg_id)
    except Exception as _e:
        _elog('system', 'eingangsrechnung_fehler', f'Auto-Scan fehlgeschlagen: {_e}',
              source='mail_monitor', modul='eingangsrechnungen', actor_type='system',
              status='fehler', context_id=msg_id)


# ── Lexware Eingangsbeleg-Pruefqueue-Scan (session-eee) ──────────────────────
# Erkennt Eingangsrechnungen intelligenter: PayPal-Ausnahme, Body-only-Rechnungen,
# Lieferantenrechnungen vs. Zahlungsbestaetigung.
_LEX_INVOICE_SIGNALS = [
    r'rechnung', r'invoice', r'faktura', r'rechnungs?nummer', r'invoice\s*number',
    r'lieferschein', r'bestellung', r'abonnement', r'abo\b', r'subscription',
    r'umsatzsteuer', r'mehrwertsteuer', r'mwst', r'vat', r'ust\b',
    r'zahlungsziel', r'faellig', r'bitte.*(?:bezahlen|ueberweisen)',
]
_LEX_PAYPAL_DOMAINS = {'paypal.com', 'paypal.de', 'e.paypal.com'}
_LEX_PAYPAL_CONFIRM = [
    r'zahlung\s*best', r'payment\s*confirm', r'zahlung\s*eingegangen',
    r'wir haben.*zahlung', r'payment\s*received', r'you\s*sent\s*a\s*payment',
]

def _is_paypal_mail(absender_email: str, betreff: str, text: str) -> bool:
    """Erkennt ob eine Mail eine PayPal-Zahlungsbestaetigung ist (kein Beleg)."""
    domain = absender_email.split('@')[-1].lower() if '@' in absender_email else ''
    if domain not in _LEX_PAYPAL_DOMAINS:
        return False
    combined = (betreff + ' ' + text[:500]).lower()
    return any(re.search(pat, combined, re.IGNORECASE) for pat in _LEX_PAYPAL_CONFIRM)


def _scan_eingangsbeleg_lexware(mail_data: dict, konto_label: str, kategorie: str,
                                 msg_id: str, absender: str, betreff: str, text: str):
    """
    Erweiterter Eingangsbeleg-Scan fuer Lexware Buchhaltungs-Pruefqueue (session-eee).
    Wird nur aufgerufen wenn lexware.status == 'freigeschaltet' und
    lexware.buchalt_pruefregel_aktiv == True.
    Schreibt in eingangsbelege_pruefqueue (idempotent via mail_id).
    """
    # Nur fuer eingehende Belege
    if kategorie not in ('Rechnung / Beleg', 'Abonnement / Kosten', 'Sonstiges'):
        return

    try:
        cfg_path = SCRIPTS_DIR / 'config.json'
        cfg = {}
        try:
            import json as _json
            cfg = _json.loads(cfg_path.read_text('utf-8'))
        except Exception:
            pass
        lex_cfg = cfg.get('lexware', {})
        if lex_cfg.get('status') != 'freigeschaltet':
            return
        if not lex_cfg.get('buchalt_pruefregel_aktiv', True):
            return

        # E-Mail-Adresse aus absender
        _se_m = re.search(r'<([^>]+@[^>]+)>', absender)
        absender_email = _se_m.group(1).lower() if _se_m else absender.strip().lower()
        absender_domain = absender_email.split('@')[-1] if '@' in absender_email else ''

        # PayPal-Ausnahme prüfen
        is_paypal = False
        if lex_cfg.get('paypal_ausnahme_aktiv', True):
            is_paypal = _is_paypal_mail(absender_email, betreff, text)
            if is_paypal and kategorie not in ('Rechnung / Beleg',):
                return  # PayPal-Zahlungsbestaetigung nicht in Queue

        # Rechnungs-Signale suchen
        combined = (betreff + ' ' + text[:2000]).lower()
        has_invoice_signal = any(re.search(pat, combined, re.IGNORECASE) for pat in _LEX_INVOICE_SIGNALS)
        if not has_invoice_signal and kategorie not in ('Rechnung / Beleg',):
            return  # Kein klares Rechnungs-Signal

        # Betrag extrahieren
        betrag = None
        _betrag_patterns = [
            r'(?:Gesamtbetrag|Total|Summe|Rechnungsbetrag|Betrag|Amount|Charged)[^\d]*?([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})',
            r'(?:Gesamtbetrag|Total|Summe|Rechnungsbetrag|Betrag|Amount|Charged)[^\d]*?([\d]+[.,]\d{2})',
            r'([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*(?:EUR|€|\$|USD)',
            r'(?:EUR|€|\$|USD)\s*([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})',
            r'([\d]+[.,]\d{2})\s*(?:EUR|€|\$|USD)',
        ]
        for _pat in _betrag_patterns:
            _m = re.search(_pat, combined, re.IGNORECASE)
            if _m:
                _b = _parse_amount(_m.group(1))
                if 0.5 < _b < 999999:
                    betrag = _b
                    break

        # Body-Excerpt (fuer Pruefqueue-Ansicht)
        body_excerpt = text[:500].strip() if text else ''

        # Ist es eine Body-only-Rechnung (kein Anhang angekuendigt)?
        is_body_only = betrag is not None and not mail_data.get('hat_anhaenge', False)

        db = sqlite3.connect(str(TASKS_DB))
        try:
            # Idempotent — kein Doppeleintrag fuer gleiche mail_id
            existing = db.execute(
                'SELECT id FROM eingangsbelege_pruefqueue WHERE mail_id=?', (msg_id,)
            ).fetchone()
            if not existing:
                db.execute("""
                    INSERT INTO eingangsbelege_pruefqueue
                        (mail_id, source, absender, absender_domain, betreff, betrag, waehrung,
                         datum_beleg, body_excerpt, is_paypal, is_body_only, status)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,'zu_pruefen')
                """, (
                    msg_id, 'mail_monitor', absender_email, absender_domain,
                    betreff[:500], betrag, 'EUR',
                    (mail_data.get('datum', '') or '')[:10],
                    body_excerpt, 1 if is_paypal else 0, 1 if is_body_only else 0,
                ))
                db.commit()
                _elog('system', 'eingangsbeleg_pruefqueue',
                      f'Eingangsbeleg Queue: {absender_email} | {betrag} EUR | {betreff[:60]}',
                      source='mail_monitor', modul='lexware', actor_type='system',
                      status='ok', context_id=msg_id)
        finally:
            db.close()
    except Exception as _e:
        _elog('system', 'eingangsbeleg_scan_fehler',
              f'Lexware-Scan fehlgeschlagen: {_e}',
              source='mail_monitor', modul='lexware', actor_type='system',
              status='fehler', context_id=msg_id)


# ── Routing-Helfer ───────────────────────────────────────────────────────────
def _load_firma_signatur():
    """Lädt Firmenname + Inhaber für Signatur aus config.json."""
    try:
        cfg = json.loads((Path(__file__).parent / "config.json").read_text("utf-8", errors="replace"))
        return cfg.get("firma_name", ""), cfg.get("firma_inhaber", "")
    except Exception:
        return "", ""


def _route_kira_vorschlag(result, kunden_email, betreff, text, msg_id, konto):
    """Bei kira_vorschlag: Auto-Entwurf / Wiedervorlage / Signal je nach Kategorie."""
    try:
        kat = result.get("kategorie", "")
        aktion = result.get("angebot_aktion", "")
        zusammenfassung = result.get("zusammenfassung", "")
        firma, inhaber = _load_firma_signatur()
        signatur = f"\n\nMit freundlichen Grüßen\n{inhaber or 'Team'}\n{firma}" if firma else ""

        body_plain = ""
        notiz = f"Routing: kira_vorschlag | Kategorie: {kat} | Aktion: {aktion}"
        vorschlag_typ = "entwurf"  # entwurf | wiedervorlage | signal

        # ── Angebotsabsage → Danke-Mail-Entwurf ──
        if kat == "Angebotsrueckmeldung" and aktion == "abgelehnt":
            body_plain = (
                "Sehr geehrte Damen und Herren,\n\n"
                "vielen Dank für Ihre Rückmeldung zu unserem Angebot.\n\n"
                "Wir bedanken uns für die ehrliche Rückmeldung und das entgegengebrachte Vertrauen. "
                "Sollte sich in Zukunft ein neues Projekt ergeben, stehen wir Ihnen "
                "jederzeit gerne zur Verfügung."
                + signatur
            )

        # ── Schulungs-/Workshop-Interesse → Wiedervorlage 4 Wochen ──
        elif _kw_in_text(["schulung", "workshop", "seminar", "weiterbildung", "kurs",
                          "training", "fortbildung"], (betreff + " " + (text or "")[:500]).lower()):
            wiedervorlage = (datetime.now() + timedelta(days=28)).strftime("%Y-%m-%d")
            vorschlag_typ = "wiedervorlage"
            body_plain = f"Kira: Schulungs-/Workshop-Interesse erkannt — Wiedervorlage am {wiedervorlage}"
            notiz = f"Routing: kira_vorschlag | Wiedervorlage: {wiedervorlage} | {zusammenfassung[:100]}"
            # Wiedervorlage als Task mit Datum
            db = sqlite3.connect(str(TASKS_DB))
            db.execute("""INSERT OR IGNORE INTO tasks
                (message_id, kunden_email, betreff, kategorie, task_typ, prioritaet,
                 status, erstellt_am, konto, routing, routing_grund, faellig)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (msg_id, kunden_email, f"Wiedervorlage: {betreff[:150]}",
                 "Zur Kenntnis", "wiedervorlage", "normal",
                 "offen", datetime.now().isoformat(), konto,
                 "kira_vorschlag", "Schulungs-Interesse → Wiedervorlage 4 Wochen",
                 wiedervorlage))
            db.commit()
            db.close()
            _elog('kira', 'kira_vorschlag_wiedervorlage',
                  f"Kira-Vorschlag: Wiedervorlage {wiedervorlage} | {betreff[:60]}",
                  source='mail_monitor', modul='routing', actor_type='kira', status='ok',
                  context_type='mail', context_id=msg_id)
            return

        # ── Zahlungsproblem (Kreditkarte abgelehnt, Zahlung fehlgeschlagen) → Signal ──
        elif _kw_in_text(["kreditkarte abgelehnt", "zahlung fehlgeschlagen", "payment failed",
                          "card declined", "zahlungsfehler", "payment error"],
                         (betreff + " " + (text or "")[:500]).lower()):
            vorschlag_typ = "signal"
            try:
                from case_engine import add_signal
                add_signal(None, "zahlungsproblem",
                           f"Zahlungsproblem: {betreff[:120]} — {zusammenfassung[:200]}",
                           stufe="B", quelle="kira_routing", kontext={"msg_id": msg_id})
            except Exception:
                pass
            _elog('kira', 'kira_vorschlag_signal',
                  f"Kira-Signal: Zahlungsproblem | {betreff[:60]}",
                  source='mail_monitor', modul='routing', actor_type='kira', status='ok',
                  context_type='mail', context_id=msg_id)
            return

        # ── Zur Kenntnis ──
        elif kat == "Zur Kenntnis":
            body_plain = f"Kira-Vorschlag: Mail zur Kenntnis genommen — {zusammenfassung}"

        # ── Fallback ──
        else:
            body_plain = f"Kira-Vorschlag: {result.get('empfohlene_aktion', 'Prüfen')}"

        if not body_plain:
            return

        # Entwurf in Freigabe-Queue
        db = sqlite3.connect(str(TASKS_DB))
        db.execute("""INSERT INTO mail_approve_queue
            (an, betreff, body_plain, konto, in_reply_to, erstellt_von, status, erstellt_am, notiz_intern)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (kunden_email, f"Re: {betreff[:180]}", body_plain, konto, msg_id,
             "kira_routing", "entwurf", datetime.now().isoformat(), notiz))
        db.commit()
        db.close()
        _elog('kira', 'kira_vorschlag_entwurf',
              f"Kira-Vorschlag: {kat} → Entwurf erstellt | {betreff[:60]}",
              source='mail_monitor', modul='routing', actor_type='kira', status='ok',
              context_type='mail', context_id=msg_id)
    except Exception as e:
        log.error(f"Kira-Vorschlag fehlgeschlagen: {e}")


def _kw_in_text(keywords, text):
    """Prüft ob mindestens ein Keyword im Text vorkommt."""
    return any(kw in text for kw in keywords)


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

    # Kunden-E-Mail: Bei Formular-Benachrichtigungen (noreply@raumkult.eu)
    # die echte Kunden-E-Mail aus dem Body extrahieren
    _absender_email_m = re.search(r'<([^>]+@[^>]+)>', absender)
    _absender_email = _absender_email_m.group(1).lower() if _absender_email_m else absender.strip().lower()
    _kunden_email_resolved = _absender_email
    from mail_classifier import load_eigene_config as _lec
    _eigene_emails_mm, _eigene_domains_mm = _lec()
    _abs_dom = _absender_email.split('@')[-1] if '@' in _absender_email else ''
    if _abs_dom in _eigene_domains_mm:
        # Formular-Muster? E-Mail aus Body extrahieren
        _form_pat = re.compile(r'(Anfrage\s*\(Landing\)|Kontaktformular|neue\s+Anfrage)', re.IGNORECASE)
        if _form_pat.search(betreff or ""):
            _clean_text = re.sub(r'<[^>]+>', ' ', text or '')
            _em_m = re.search(r'E-Mail\s+([\w.+-]+@[\w.-]+\.\w+)', _clean_text)
            if _em_m:
                _form_em = _em_m.group(1).lower()
                _form_dom = _form_em.split('@')[-1]
                if _form_dom not in _eigene_domains_mm:
                    _kunden_email_resolved = _form_em

    # Kopie-Erkennung: Absender ist konfigurierte eigene E-Mail UND keine Formular-Mail → interne Kopie
    if _absender_email in _eigene_emails_mm and _kunden_email_resolved == _absender_email:
        # Absender ist eigene Domain UND keine Formular-Email extrahiert → interne Kopie
        _index_mail(mail_data, konto_label, folder_name)
        return {"kategorie": "Abgeschlossen", "routing": "archivieren",
                "erfordert_handlung": False, "kategorie_grund": "Eigene Domain, interne Kopie"}

    # Duplikat-Check
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    existing = db.execute("SELECT id FROM tasks WHERE message_id=?", (msg_id,)).fetchone()
    if existing:
        db.close()
        return None

    # Thread-Check: gehört diese Mail zu einem bestehenden Thread mit offenem Task?
    thread_id = mail_data.get("thread_id", "")
    _thread_task = None
    if thread_id and thread_id != msg_id:
        _thread_task = db.execute(
            "SELECT id, status, kategorie FROM tasks WHERE thread_id=? AND status='offen' ORDER BY id DESC LIMIT 1",
            (thread_id,)
        ).fetchone()

    # Klassifizierung
    t0 = time.monotonic()
    result = classify_mail(konto_label, absender, betreff, text,
                          anhaenge=mail_data.get("anhaenge", []),
                          folder=folder_name, is_sent=is_sent,
                          mail_datum=mail_data.get("datum", ""),
                          kanal="email")
    kat_ms = int((time.monotonic() - t0) * 1000)

    # Bei LLM-Ausfall: Mail nur indexieren, keinen Task erstellen
    if result.get("_llm_fallback") and result.get("_all_providers_failed"):
        log.warning(f"LLM nicht verfügbar, Mail nur indexiert (kein Task): {betreff[:60]}")
        _elog('system', 'llm_unavailable_queued',
              f"LLM nicht verfügbar, Mail nur indexiert: {betreff[:60]}",
              source='mail_monitor', modul='mail_monitor', status='warnung',
              context_type='mail', context_id=msg_id)
        return result

    kategorie = result.get("kategorie", "Zur Kenntnis")
    konfidenz = result.get("konfidenz", "?")

    # Automatische Angebot-Aktion (Annahme/Ablehnung automatisch buchen)
    if kategorie == "Angebotsrueckmeldung" and result.get("angebot_aktion"):
        auto_result = _auto_angebot_aktion(result, _kunden_email_resolved, betreff, msg_id)
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

    # ── Routing-Dispatch: Nicht jede Klassifizierung erzeugt einen Task ──
    routing = result.get("routing", "task")
    erfordert_handlung = result.get("erfordert_handlung", True)

    # In mail_index.db speichern — IMMER, unabhängig von Kategorie
    _index_mail(mail_data, konto_label, folder_name)

    # Klassifizierung + Routing in mail_index.db speichern
    try:
        from datetime import datetime as _dt
        _mi = sqlite3.connect(str(MAIL_INDEX_DB))
        _mi.execute(
            "UPDATE mails SET kategorie=?, konfidenz=?, antwort_noetig=?, klassifiziert_am=? WHERE message_id=?",
            (kategorie, konfidenz,
             1 if result.get("antwort_noetig") else 0,
             _dt.now().isoformat(), msg_id))
        _mi.commit()
        _mi.close()
    except Exception:
        pass

    # Archivieren: kein Task
    if routing == "archivieren" or kategorie in ("Ignorieren", "Newsletter / Werbung", "Abgeschlossen"):
        db.close()
        return result

    # Buchhaltung: Rechnung/Beleg ohne Frage → kein Task
    if routing == "buchhaltung":
        db.close()
        return result

    # Feed: Info-Mails → kein Task
    if routing == "feed":
        db.close()
        return result

    # Kira-Vorschlag: Kira bereitet Aktion vor → kein manueller Task
    if routing == "kira_vorschlag":
        _route_kira_vorschlag(result, _kunden_email_resolved, betreff, text, msg_id, konto_label)
        db.close()
        return result

    # Sicherheits-Check: nur Tasks erstellen wenn Handlung erforderlich
    if not erfordert_handlung and routing != "task":
        db.close()
        return result

    # Antwort-Entwurf generieren
    entwurf = None
    if result.get("antwort_noetig"):
        try:
            entwurf = generate_draft(betreff, absender, text, _kunden_email_resolved)
        except:
            pass

    # Thread-Zusammenführung: bestehenden Task updaten statt neuen erstellen
    if _thread_task and _thread_task["status"] == "offen":
        try:
            from datetime import datetime as _dt_thread
            db.execute("""UPDATE tasks SET
                aktualisiert_am=?, notiz=COALESCE(notiz,'') || ?
                WHERE id=?""",
                (_dt_thread.now().isoformat(),
                 f"\n[{mail_data.get('datum','')}] Folgemail: {betreff[:80]}",
                 _thread_task["id"]))
            db.commit()
            _alog("Mail", "Folgemail → Task aktualisiert",
                  f"Task #{_thread_task['id']} | {betreff[:80]}", "ok",
                  task_id=_thread_task["id"])
            _elog('system', 'task_thread_update',
                  f"Folgemail in Thread: Task #{_thread_task['id']} | {betreff[:80]}",
                  source='mail_monitor', modul='mail_monitor', submodul='thread',
                  actor_type='system', status='ok', context_type='mail', context_id=msg_id)
        except Exception as e:
            log.error(f"Thread-Update fehlgeschlagen: {e}")
        finally:
            db.close()
        return result

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
             mit_termin, manuelle_pruefung, beantwortet,
             thread_id, konfidenz)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (typ, kategorie, betreff[:200],
             result.get("zusammenfassung", ""),
             text[:2000],
             _kunden_email_resolved,
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
             result.get("beantwortet", 0),
             mail_data.get("thread_id", ""),
             konfidenz))
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

    # ── Case Engine: Vorgang-Routing (session-nn) ─────────────────────────────
    try:
        _tid = task_id_new  # NameError wenn Task-Insert fehlschlug → Router überspringen
        from vorgang_router import route_classified_mail as _vr_route
        _kunden_name_vr  = (absender.split("<")[0].strip() if "<" in absender else "") or ""
        _route_result = _vr_route(
            task_id=_tid,
            classification_result=result,
            mail_message_id=msg_id,
            kunden_email=_kunden_email_resolved,
            kunden_name=_kunden_name_vr,
            konto=konto_label,
            betreff=betreff,
        )
        if _route_result.get("stufe") in ("B", "C") and _route_result.get("vorgang_id"):
            _elog('system', 'vorgang_signal',
                  f"Vorgang-Signal Stufe {_route_result['stufe']}: {_route_result.get('vorgang_typ','')} | {betreff[:60]}",
                  source='mail_monitor', modul='vorgang_router', actor_type='system',
                  status='ok', context_id=msg_id)
    except NameError:
        pass  # task_id_new nicht gesetzt = Task-Insert fehlgeschlagen
    except Exception as _ve:
        _elog('system', 'vorgang_router_fehler', f"Router-Fehler: {_ve}",
              source='mail_monitor', modul='vorgang_router', actor_type='system', status='fehler')

    # ── Eingangsrechnungs-Auto-Scan ───────────────────────────────────────────
    _auto_scan_eingangsrechnung(mail_data, konto_label, kategorie, msg_id, absender, betreff, text)

    # ── Lexware Buchhaltungs-Pruefqueue (session-eee) ─────────────────────────
    _scan_eingangsbeleg_lexware(mail_data, konto_label, kategorie, msg_id, absender, betreff, text)

    # ── Anthropic Billing Push ────────────────────────────────────────────────
    _check_anthropic_billing(absender, betreff, text)

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

    # ── Urlaubsmodus Auto-Antwort (session-bbb) ──────────────────────────────
    if not is_sent and kategorie not in ("Ignorieren", "Newsletter / Werbung"):
        try:
            _urlaub_cfg = json.loads(CONFIG_FILE.read_text('utf-8')).get('ntfy', {})
            if _urlaub_cfg.get('urlaub_modus') and _urlaub_cfg.get('urlaub_autoreply_aktiv'):
                _ar_log_path = KNOWLEDGE_DIR / 'urlaub_autoreply_log.json'
                _ar_log = {}
                if _ar_log_path.exists():
                    try: _ar_log = json.loads(_ar_log_path.read_text('utf-8'))
                    except: pass
                _sender_email_m = re.search(r'<([^>]+@[^>]+)>', absender)
                _se = _sender_email_m.group(1).lower() if _sender_email_m else absender.strip().lower()
                # Max 1 Auto-Reply pro Absender pro Urlaubsperiode (basierend auf urlaub_von)
                _urlaub_von_key = _urlaub_cfg.get('urlaub_von', '')[:10]
                _ar_key = f"{_se}_{_urlaub_von_key}"
                if _ar_key not in _ar_log:
                    from mail_sender import send_mail as _sm_send
                    _ar_betreff = _urlaub_cfg.get('urlaub_autoreply_betreff',
                        'Abwesenheitsnotiz: Ich bin derzeit im Urlaub')
                    _ar_text = _urlaub_cfg.get('urlaub_autoreply_text',
                        'Vielen Dank fuer Ihre Nachricht. Ich befinde mich derzeit im Urlaub '
                        'und werde mich nach meiner Rueckkehr bei Ihnen melden.')
                    _ar_bis = _urlaub_cfg.get('urlaub_bis', '')
                    if _ar_bis:
                        try:
                            _bis_dt = datetime.fromisoformat(_ar_bis[:16])
                            _ar_text += f'\n\nIch bin voraussichtlich wieder ab {_bis_dt.strftime("%d.%m.%Y")} erreichbar.'
                        except: pass
                    # Absender-Konto bestimmen
                    _all_konten = json.loads(CONFIG_FILE.read_text('utf-8')).get('konten', [])
                    _from_email = next(
                        (k.get('email','') for k in _all_konten if k.get('label','') == konto_label),
                        ''
                    )
                    if _from_email:
                        _ar_result = _sm_send(
                            from_email=_from_email,
                            to=_se,
                            subject='AW: ' + betreff if not betreff.startswith('AW:') else betreff,
                            body_plain=_ar_text,
                            in_reply_to=msg_id,
                            references=msg_id,
                            save_to_db=False,
                        )
                        if _ar_result.get('ok'):
                            _ar_log[_ar_key] = datetime.now().isoformat()
                            _ar_log_path.write_text(json.dumps(_ar_log, ensure_ascii=False, indent=2), 'utf-8')
                            _elog('system', 'urlaub_autoreply_sent',
                                  f'Auto-Antwort gesendet an {_se} | {betreff[:60]}',
                                  source='mail_monitor', modul='urlaub', actor_type='system',
                                  status='ok', context_id=msg_id)
        except Exception as _ur_e:
            _elog('system', 'urlaub_autoreply_fehler', f'Auto-Antwort fehlgeschlagen: {_ur_e}',
                  source='mail_monitor', modul='urlaub', actor_type='system', status='fehler')

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
             eml_path, mail_folder_pfad, gelesen)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
            1 if any(s in (folder_name or '').lower() for s in ('sent', 'gesendet', 'ausgang', 'gesendete')) else 0,  # gelesen: Gesendete Elemente sind immer gelesen
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
        ang_nr = ang["a_nummer"] or ""
        kunde  = (ang["kunde_name"] or "").strip() or kunden_email or "Unbekannt"
        safe_msg_id = (msg_id or "")[:40]
        safe_betreff = (betreff or "")

        if angebot_aktion == "angenommen":
            db.execute(
                "UPDATE angebote SET status='angenommen', grund_angenommen=? WHERE id=?",
                (f"Mail: {safe_betreff[:200]}", ang_id)
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
                safe_betreff[:200], "auto",
                "offen", "hoch", 0,
                f"auto-annahme-{safe_msg_id}"
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
def _migrate_konto_smtp(konto: dict) -> dict:
    """Ergaenzt fehlende smtp_server/smtp_port/smtp_ssl aus Provider-Defaults (Migration)."""
    if konto.get("smtp_server"):
        return konto  # bereits gesetzt
    smtp = get_smtp_settings(konto)
    konto["smtp_server"] = smtp.get("server", "")
    konto["smtp_port"] = smtp.get("port", 587)
    konto["smtp_ssl"] = not smtp.get("starttls", True)
    return konto


def migrate_all_smtp_settings():
    """Schreibt fehlende SMTP-Einstellungen in raumkult_config.json (einmalige Migration)."""
    if not ARCHIVER_CFG.exists():
        return
    try:
        cfg = json.loads(ARCHIVER_CFG.read_text("utf-8"))
        changed = False
        for k in cfg.get("konten", []):
            if not k.get("smtp_server"):
                _migrate_konto_smtp(k)
                changed = True
        if changed:
            ARCHIVER_CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
            log.info("SMTP-Migration: fehlende smtp_server-Felder ergaenzt")
    except Exception as e:
        log.warning(f"SMTP-Migration fehlgeschlagen: {e}")


def _load_accounts():
    """Lädt Konten aus dem Archiver-Config."""
    if not ARCHIVER_CFG.exists():
        log.error(f"Archiver-Config nicht gefunden: {ARCHIVER_CFG}")
        return []

    try:
        cfg = json.loads(ARCHIVER_CFG.read_text('utf-8'))
        konten = cfg.get("konten", [])
        aktive = [k for k in konten if k.get("aktiv", True)]
        # Fehlende SMTP-Felder on-the-fly ergaenzen (kein Disk-Write)
        for k in aktive:
            if not k.get("smtp_server"):
                _migrate_konto_smtp(k)
        return aktive
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
            err_str = str(e).lower()
            is_token_expired = "token_abgelaufen" in err_str
            is_transient = any(k in err_str for k in ("timeout", "timed out", "connection", "reset", "broken pipe", "eof"))
            # Bei transienten Fehlern: einmal Retry nach 10s
            if is_transient and not is_token_expired:
                log.warning(f"IMAP transient error für {email_addr}, Retry in 10s: {e}")
                import time
                time.sleep(10)
                try:
                    imap = imap_connect(konto)
                except Exception as e2:
                    log.error(f"IMAP-Verbindung fehlgeschlagen (Retry) für {email_addr}: {e2}")
                    e = e2
                    err_str = str(e2).lower()
                else:
                    # Retry erfolgreich — weiter zum normalen Flow
                    e = None
            if e is not None:
                log.error(f"IMAP-Verbindung fehlgeschlagen für {email_addr}: {e}")
                _update_status(last_error=f"{email_addr}: {e}")
                with _health_lock:
                    _account_health[email_addr] = {
                        "status": "auth_fehler" if any(k in err_str for k in ("auth", "login", "token")) else "fehler",
                        "error": str(e)[:200], "inbox_count": 0,
                        "last_check": datetime.now().isoformat(),
                    }
                continue

        # IMAP verbunden → Health auf ok setzen
        with _health_lock:
            _account_health[email_addr] = {
                "status": "ok", "error": None, "inbox_count": 0,
                "last_check": datetime.now().isoformat(),
            }

        try:
            # Ordner auflisten
            status_ok, folder_list = imap.list()
            folders = []
            for entry in (folder_list or []):
                if isinstance(entry, bytes):
                    parts = entry.decode(errors='replace').split('"/"')
                    if parts:
                        folders.append(parts[-1].strip().strip('"'))

            # Config-basierte Ordner-Whitelist laden (einmal pro Konto)
            sync_liste = _get_sync_ordner(email_addr)
            log.info(f"  {label}: Sync-Ordner aus config: {sync_liste}")

            for folder_name in folders:
                if _stop_event.is_set():
                    break
                if not _ordner_erlaubt(folder_name, sync_ordner_liste=sync_liste):
                    continue

                folder_key = f"{email_addr}:{folder_name}"
                last_uid = konto_state.get(folder_name, {}).get("last_uid", 0)

                try:
                    s, d = imap.select(f'"{folder_name}"', readonly=True)
                    if s != "OK":
                        continue

                    # Neue UIDs suchen
                    # Hinweis: imaplib gibt UIDs als bytes zurück (b'7703') — immer decoden vor int()
                    def _uid2int(u):
                        return int(u.decode('ascii', errors='ignore').strip() if isinstance(u, bytes) else u)

                    if last_uid > 0:
                        sr, ud = imap.uid("SEARCH", f"UID {last_uid + 1}:*")
                        if sr == "OK" and ud[0]:
                            new_uids = [u for u in ud[0].split() if u and _uid2int(u) > last_uid]
                        else:
                            new_uids = []
                    else:
                        # Erster Lauf: letzte 50 Mails für vollständige Ersterfassung
                        sr, ud = imap.uid("SEARCH", "ALL")
                        if sr == "OK" and ud[0]:
                            all_uids = ud[0].split()
                            new_uids = all_uids[-50:] if len(all_uids) > 50 else all_uids
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
                            # Volle E-Mail-Adresse setzen (für korrekte mail_index.db Zuordnung)
                            mail_data['konto'] = email_addr
                            # Ins Archiv speichern (JSON+EML+Anhänge)
                            # email_addr (z.B. anfrage@raumkult.eu) statt label (anfrage)
                            # → Ordnername anfrage_raumkult_eu, passend zum alten Archiver
                            pfad = _save_to_archive(mail_data, raw, email_addr, folder_name)
                            if pfad:
                                mail_data['mail_folder_pfad'] = pfad
                                mail_data['eml_path'] = str(Path(pfad) / 'mail.eml')
                            result = _process_mail(mail_data, label, folder_name)
                            if result and result.get("kategorie") not in ("Ignorieren", "Newsletter / Werbung", "Abgeschlossen"):
                                all_new_tasks.append(result)

                        # Max UID tracken
                        batch_max = max(_uid2int(u) for u in batch)
                        if batch_max > max_uid:
                            max_uid = batch_max

                    # State updaten
                    if max_uid > last_uid:
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

    _poll_count = 0
    # Proaktiver Scan alle 15 Min — bei 300s-Intervall jeder 3. Poll, sonst jeder Poll
    _proaktiv_every = max(1, 900 // interval_sec)

    while not _stop_event.is_set():
        try:
            new_tasks = poll_all_accounts()
            if new_tasks:
                log.info(f"Monitor: {len(new_tasks)} neue Aufgaben erstellt")
        except Exception as e:
            log.error(f"Monitor-Fehler: {e}")
            _update_status(last_error=str(e))

        # Proaktiver Business-Scan alle ~15 Min
        _poll_count += 1
        if PROAKTIV_OK and _poll_count % _proaktiv_every == 0:
            try:
                result = _proaktiv.run_proaktiver_scan()
                if result.get("ergebnisse"):
                    log.info(f"Proaktiver Scan: {list(result['ergebnisse'].keys())}")
            except Exception as e:
                log.error(f"Proaktiver Scan Fehler: {e}")

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
