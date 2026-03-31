#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
google_oauth.py -- Google OAuth2 + Gmail IMAP XOAUTH2 fuer KIRA

Ermoeglicht das Hinzufuegen von Gmail-/Google-Workspace-Konten zu KIRA.

Setup (einmalig):
  1. Google Cloud Console -> APIs & Services -> Credentials
  2. "Create Credentials" -> OAuth 2.0 Client ID -> Web application
  3. Authorized redirect URIs -> http://localhost:8765/oauth/google/callback
  4. Client ID + Client Secret in KIRA-Einstellungen > Integrationen eintragen

Benoetigt:
  - Gmail API aktiviert in Google Cloud Console
  - Scope: https://mail.google.com/ (IMAP + SMTP Zugriff)
"""

import base64
import json
import logging
import secrets
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import webbrowser
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"

# Token-Dir: gleicher Ordner wie mail_monitor.py
try:
    _archiver_cfg_path = SCRIPTS_DIR.parent / "scripts" / "config.json"
    _base_cfg = json.loads(_archiver_cfg_path.read_text("utf-8")) if _archiver_cfg_path.exists() else {}
    _archiv_root_str = _base_cfg.get("mail_archiv", {}).get("pfad", "")
    ARCHIVER_DIR = Path(_archiv_root_str) if _archiv_root_str else Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv")
except Exception:
    ARCHIVER_DIR = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv")

TOKEN_DIR = ARCHIVER_DIR / "tokens"

GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SCOPE      = "https://mail.google.com/"
REDIRECT_URI     = "http://localhost:8765/oauth/google/callback"

CONFIG_PATH = SCRIPTS_DIR / "config.json"

log = logging.getLogger("google_oauth")

# ── In-Memory Job-Tracking ────────────────────────────────────────────────────
_oauth_jobs: dict = {}
_jobs_lock  = threading.Lock()


# ── Config-Laden ──────────────────────────────────────────────────────────────

def get_google_credentials() -> tuple:
    """
    Laedt Client ID + Secret aus config.json > google_oauth.
    Gibt (client_id, client_secret) zurueck oder ('', '') wenn nicht gesetzt.
    """
    try:
        cfg = json.loads(CONFIG_PATH.read_text("utf-8"))
        g   = cfg.get("google_oauth", {})
        return g.get("client_id", ""), g.get("client_secret", "")
    except Exception:
        return "", ""


def credentials_configured() -> bool:
    """True wenn Client ID + Secret in config.json eingetragen sind."""
    cid, csec = get_google_credentials()
    return bool(cid and csec)


# ── OAuth URL ─────────────────────────────────────────────────────────────────

def build_auth_url(email: str, state: str) -> str:
    """
    Baut die Google OAuth2-Authorization-URL.
    email: Hinweis fuer Google welches Konto gewaehlt werden soll (login_hint).
    """
    client_id, _ = get_google_credentials()
    if not client_id:
        raise RuntimeError("Google OAuth Client ID nicht konfiguriert")

    params = {
        "client_id":     client_id,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         GMAIL_SCOPE,
        "access_type":   "offline",    # erhalten wir refresh_token
        "prompt":        "consent",    # erzwinge refresh_token-Ausgabe
        "state":         state,
    }
    if email:
        params["login_hint"] = email

    return GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)


# ── Token-Exchange ─────────────────────────────────────────────────────────────

def exchange_code(code: str) -> dict:
    """
    Tauscht Authorization Code gegen Access + Refresh Token.
    Gibt {'access_token','refresh_token','expires_in',...} zurueck.
    """
    client_id, client_secret = get_google_credentials()
    if not client_id:
        raise RuntimeError("Google OAuth Credentials nicht konfiguriert")

    data = urllib.parse.urlencode({
        "code":          code,
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def refresh_access_token(email: str) -> str:
    """
    Erneuert Access Token mit gespeichertem Refresh Token.
    Gibt frischen access_token zurueck.
    """
    client_id, client_secret = get_google_credentials()
    token_data = _load_token(email)
    refresh_token = token_data.get("refresh_token", "")
    if not refresh_token:
        raise RuntimeError(f"Kein Refresh Token fuer {email}")

    data = urllib.parse.urlencode({
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }).encode("utf-8")

    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        new_data = json.loads(resp.read().decode("utf-8"))

    # Token-Cache aktualisieren (refresh_token bleibt erhalten)
    token_data["access_token"]  = new_data["access_token"]
    token_data["expires_in"]    = new_data.get("expires_in", 3600)
    token_data["obtained_at"]   = datetime.now(timezone.utc).isoformat()
    _save_token(email, token_data)
    return new_data["access_token"]


# ── Token-Storage ─────────────────────────────────────────────────────────────

def _token_file(email: str) -> Path:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    safe = email.lower().replace("@", "_at_").replace(".", "_")
    return TOKEN_DIR / f"google_{safe}.json"


def _save_token(email: str, token_data: dict):
    token_data["_email"]      = email
    token_data["obtained_at"] = token_data.get("obtained_at", datetime.now(timezone.utc).isoformat())
    _token_file(email).write_text(json.dumps(token_data, indent=2), encoding="utf-8")
    log.info(f"Google Token gespeichert fuer {email}")


def _load_token(email: str) -> dict:
    p = _token_file(email)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return {}


def _token_valid(token_data: dict, margin_sec: int = 120) -> bool:
    """True wenn Access Token noch mind. margin_sec gueltig."""
    obtained_str = token_data.get("obtained_at", "")
    expires_in   = int(token_data.get("expires_in", 0))
    if not obtained_str or not expires_in:
        return False
    try:
        obtained = datetime.fromisoformat(obtained_str)
        expires  = obtained + timedelta(seconds=expires_in - margin_sec)
        return datetime.now(timezone.utc) < expires
    except Exception:
        return False


# ── Oeffentliche Token-API ─────────────────────────────────────────────────────

def get_gmail_token(email: str) -> str:
    """
    Gibt einen gueltigen Google Access Token zurueck.
    Erneuert automatisch wenn abgelaufen.
    Wirft RuntimeError wenn kein Token vorhanden.
    """
    token_data = _load_token(email)
    if not token_data.get("access_token"):
        raise RuntimeError(f"Kein Google Token fuer {email} -- OAuth-Login erforderlich")

    if _token_valid(token_data):
        return token_data["access_token"]

    log.info(f"Google Token abgelaufen fuer {email} -- erneuere...")
    return refresh_access_token(email)


def build_xoauth2_string(email: str, access_token: str) -> str:
    """Baut XOAUTH2 Auth-String fuer IMAP (base64-encodiert)."""
    auth = f"user={email}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(auth.encode("utf-8")).decode("ascii")


def has_token(email: str) -> bool:
    """True wenn ein gespeicherter Google Token vorhanden ist."""
    return bool(_load_token(email).get("refresh_token", ""))


# ── OAuth-Flow (Browser) ──────────────────────────────────────────────────────

def start_oauth_browser_flow(email: str, job_id: str):
    """
    Startet den Google OAuth2-Browser-Flow in einem Background-Thread.
    Status kann via get_oauth_job_status(job_id) abgefragt werden.
    """
    if not credentials_configured():
        with _jobs_lock:
            _oauth_jobs[job_id] = {
                "status": "error",
                "error": "Google OAuth Credentials nicht konfiguriert. Bitte in Einstellungen > Integrationen eintragen."
            }
        return

    state = f"{job_id}:{secrets.token_urlsafe(16)}"
    auth_url = build_auth_url(email, state)

    with _jobs_lock:
        _oauth_jobs[job_id] = {
            "status":   "pending",
            "email":    email,
            "state":    state,
            "auth_url": auth_url,
        }

    def _open_browser():
        try:
            log.info(f"Google OAuth Browser-Flow gestartet fuer {email}")
            webbrowser.open(auth_url)
        except Exception as e:
            with _jobs_lock:
                _oauth_jobs[job_id]["status"] = "error"
                _oauth_jobs[job_id]["error"]  = f"Browser konnte nicht geoeffnet werden: {e}"

    t = threading.Thread(target=_open_browser, daemon=True)
    t.start()


def handle_oauth_callback(code: str, state: str) -> dict:
    """
    Verarbeitet den OAuth-Callback nach dem Browser-Login.
    Wird von server.py GET /oauth/google/callback aufgerufen.
    Gibt {'ok': True/False, 'email': ...} zurueck.
    """
    # Job aus State ermitteln
    job_id = state.split(":")[0] if ":" in state else state

    with _jobs_lock:
        job = _oauth_jobs.get(job_id, {})

    if not job:
        log.warning(f"Google OAuth Callback: unbekannter Job-State {state!r}")
        return {"ok": False, "error": "Unbekannter OAuth-State"}

    email = job.get("email", "")

    try:
        token_data = exchange_code(code)
        token_data["obtained_at"] = datetime.now(timezone.utc).isoformat()
        _save_token(email, token_data)

        with _jobs_lock:
            _oauth_jobs[job_id]["status"] = "done"
            _oauth_jobs[job_id]["email"]  = email

        log.info(f"Google OAuth erfolgreich fuer {email}")
        return {"ok": True, "email": email}

    except Exception as e:
        err = str(e)
        log.error(f"Google OAuth Token-Exchange fehlgeschlagen: {err}")
        with _jobs_lock:
            _oauth_jobs[job_id]["status"] = "error"
            _oauth_jobs[job_id]["error"]  = err
        return {"ok": False, "error": err}


def get_oauth_job_status(job_id: str) -> dict:
    """Gibt Status eines laufenden OAuth-Jobs zurueck."""
    with _jobs_lock:
        job = _oauth_jobs.get(job_id, {})
    if not job:
        return {"status": "unknown"}
    return {
        "status": job.get("status", "unknown"),
        "email":  job.get("email", ""),
        "error":  job.get("error", ""),
    }


# ── Gmail IMAP-Verbindungstest ────────────────────────────────────────────────

def test_gmail_imap(email: str) -> dict:
    """
    Testet die IMAP-Verbindung zu Gmail mit XOAUTH2.
    Gibt {'ok': True/False, 'info': '...', 'error': '...'} zurueck.
    """
    try:
        import imaplib
        token = get_gmail_token(email)
        xoauth2 = build_xoauth2_string(email, token)

        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=15)
        result = imap.authenticate("XOAUTH2", lambda _: xoauth2.encode("ascii"))
        imap.logout()

        if result[0] == "OK":
            return {"ok": True, "info": f"IMAP-Verbindung fuer {email} erfolgreich"}
        else:
            return {"ok": False, "error": f"IMAP AUTH fehlgeschlagen: {result}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
