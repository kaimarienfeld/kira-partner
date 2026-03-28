#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mail_sender.py — SMTP-Versand für Kira über XOAUTH2 (info@raumkult.eu etc.)

Nutzt den selben Token-Cache und MSAL-Stack wie mail_monitor.py.
Sendet via smtp.office365.com:587 mit STARTTLS + XOAUTH2.

Verwendung:
    from mail_sender import send_mail

    send_mail(
        from_email="info@raumkult.eu",
        to="kunde@example.com",
        subject="Ihr Angebot",
        body_html="<p>Hallo...</p>",
        body_plain="Hallo...",
        bcc="info@raumkult.eu",        # optional
        attachments=[Path("datei.pdf")] # optional
    )
"""
import smtplib, ssl, json, logging, base64, hashlib, re
import email.mime.multipart
import email.mime.text
import email.mime.base
import email.encoders
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

try:
    import msal
    MSAL_OK = True
except ImportError:
    MSAL_OK = False

SCRIPTS_DIR = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"

ARCHIVER_DIR = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv")
ARCHIVER_CFG = ARCHIVER_DIR / "raumkult_config.json"
TOKEN_DIR    = ARCHIVER_DIR / "tokens"

SMTP_HOST = "smtp.office365.com"
SMTP_PORT = 587

OAUTH_SCOPES       = ["https://outlook.office.com/SMTP.Send"]
OAUTH_SCOPE_VERSION = "v1_smtp_send"

SENT_MAILS_DB = KNOWLEDGE_DIR / "sent_mails.db"

log = logging.getLogger("mail_sender")


# ── Token-Stack (identisch mit mail_monitor.py) ───────────────────────────────
def _token_cache_path(email_addr: str) -> Path:
    TOKEN_DIR.mkdir(exist_ok=True)
    safe = email_addr.replace("@", "_").replace(".", "_")
    return TOKEN_DIR / f"{safe}_smtp_token.json"


def _msal_app(konto: dict):
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


def _save_token_cache(cache, path: Path):
    if cache.has_state_changed:
        path.write_text(cache.serialize(), encoding="utf-8")


def get_smtp_token(konto: dict) -> str:
    """
    Holt OAuth2 Access Token für SMTP.Send Scope.
    Separate Token-Datei vom IMAP-Token (anderer Scope).
    """
    app, cache, cache_path = _msal_app(konto)
    email_addr = konto["email"]

    version_path = cache_path.parent / (cache_path.stem + "_version.txt")
    if version_path.exists() and version_path.read_text().strip() != OAUTH_SCOPE_VERSION:
        if cache_path.exists(): cache_path.unlink()
        if version_path.exists(): version_path.unlink()
        app, cache, cache_path = _msal_app(konto)

    # 1. Silent
    accounts = app.get_accounts(username=email_addr)
    if accounts:
        result = app.acquire_token_silent(OAUTH_SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_token_cache(cache, cache_path)
            version_path.write_text(OAUTH_SCOPE_VERSION)
            return result["access_token"]

    # 2. Device-Code-Flow
    import webbrowser
    log.info(f"SMTP OAuth2 Login für {email_addr}")
    flow = app.initiate_device_flow(scopes=OAUTH_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device-Flow fehlgeschlagen: {flow.get('error_description', '?')}")

    url = flow["verification_uri"]
    code = flow["user_code"]
    log.warning(f"SMTP OAUTH2: {email_addr} → {url} Code: {code}")

    try:
        webbrowser.open(url)
    except Exception:
        pass

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"SMTP OAuth2 fehlgeschlagen: {result.get('error_description', '?')}")

    _save_token_cache(cache, cache_path)
    version_path.write_text(OAUTH_SCOPE_VERSION)
    log.info(f"SMTP OAuth2 OK für {email_addr}")
    return result["access_token"]


def _load_konto(from_email: str) -> dict:
    """Lädt Konto-Konfig aus dem Archiver-Config."""
    if not ARCHIVER_CFG.exists():
        raise RuntimeError(f"Archiver-Config nicht gefunden: {ARCHIVER_CFG}")
    cfg = json.loads(ARCHIVER_CFG.read_text("utf-8"))
    for k in cfg.get("konten", []):
        if k.get("email", "").lower() == from_email.lower():
            return k
    raise RuntimeError(f"Konto nicht in Archiver-Config: {from_email}")


def _xoauth2_string(email_addr: str, access_token: str) -> str:
    """Erzeugt XOAUTH2 Auth-String (base64-encodiert für SMTP AUTH)."""
    auth = f"user={email_addr}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(auth.encode("utf-8")).decode("ascii")


# ── Mail-Aufbau ───────────────────────────────────────────────────────────────
def _build_message(
    from_email: str,
    to: str,
    subject: str,
    body_html: str = "",
    body_plain: str = "",
    cc: str = "",
    bcc: str = "",
    reply_to: str = "",
    attachments: Optional[List[Path]] = None,
    in_reply_to: str = "",
    references: str = "",
) -> email.mime.multipart.MIMEMultipart:
    """Baut eine vollständige MIME-Nachricht."""

    if body_html and body_plain:
        msg = email.mime.multipart.MIMEMultipart("mixed")
        alt = email.mime.multipart.MIMEMultipart("alternative")
        alt.attach(email.mime.text.MIMEText(body_plain, "plain", "utf-8"))
        alt.attach(email.mime.text.MIMEText(body_html, "html", "utf-8"))
        msg.attach(alt)
    elif body_html:
        msg = email.mime.multipart.MIMEMultipart("mixed")
        msg.attach(email.mime.text.MIMEText(body_html, "html", "utf-8"))
    else:
        msg = email.mime.multipart.MIMEMultipart("mixed")
        msg.attach(email.mime.text.MIMEText(body_plain or "", "plain", "utf-8"))

    msg["From"] = from_email
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=from_email.split("@")[-1])

    if cc:
        msg["Cc"] = cc
    if reply_to:
        msg["Reply-To"] = reply_to
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    # BCC ist ein Header der NICHT ins Envelope soll → separat handhaben
    # (wird beim Senden als Empfänger übergeben, aber nicht im Header)

    # Anhänge
    for att in (attachments or []):
        att = Path(att)
        if not att.exists():
            log.warning(f"Anhang nicht gefunden: {att}")
            continue
        with open(att, "rb") as f:
            part = email.mime.base.MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        email.encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=att.name)
        msg.attach(part)

    return msg


# ── Versand ───────────────────────────────────────────────────────────────────
def send_mail(
    from_email: str,
    to: str,
    subject: str,
    body_html: str = "",
    body_plain: str = "",
    cc: str = "",
    bcc: str = "",
    reply_to: str = "",
    attachments: Optional[List[Path]] = None,
    in_reply_to: str = "",
    references: str = "",
    save_to_db: bool = True,
) -> dict:
    """
    Sendet eine Mail über SMTP XOAUTH2.

    Returns:
        {"ok": True, "message_id": "...", "info": "..."} on success
        {"ok": False, "error": "..."} on failure
    """
    try:
        konto = _load_konto(from_email)
        token = get_smtp_token(konto)
    except Exception as e:
        log.error(f"Token-Fehler für {from_email}: {e}")
        return {"ok": False, "error": f"Token: {e}"}

    msg = _build_message(
        from_email=from_email,
        to=to,
        subject=subject,
        body_html=body_html,
        body_plain=body_plain,
        cc=cc,
        bcc=bcc,
        reply_to=reply_to,
        attachments=attachments,
        in_reply_to=in_reply_to,
        references=references,
    )
    message_id = msg["Message-ID"]

    # Alle Empfänger (To + CC + BCC)
    recipients = [addr.strip() for addr in to.split(",") if addr.strip()]
    if cc:
        recipients += [addr.strip() for addr in cc.split(",") if addr.strip()]
    if bcc:
        recipients += [addr.strip() for addr in bcc.split(",") if addr.strip()]
        msg["Bcc"] = bcc  # in Header für Transparenz wenn gewollt

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.ehlo()

            # XOAUTH2 Auth
            auth_str = _xoauth2_string(from_email, token)
            code, resp = smtp.docmd("AUTH", f"XOAUTH2 {auth_str}")
            if code != 235:
                raise RuntimeError(f"SMTP AUTH fehlgeschlagen ({code}): {resp}")

            smtp.sendmail(from_email, recipients, msg.as_bytes())

        log.info(f"Mail gesendet: {from_email} → {to} | {subject[:60]}")

        # In sent_mails.db speichern
        if save_to_db:
            _save_sent_mail(from_email, to, subject, body_plain or "", message_id, bcc)

        return {
            "ok": True,
            "message_id": message_id,
            "info": f"Gesendet an {to}"
        }

    except Exception as e:
        log.error(f"SMTP-Fehler: {e}")
        return {"ok": False, "error": str(e)}


def _save_sent_mail(from_email, to, subject, body_plain, message_id, bcc=""):
    """Speichert gesendete Mail in sent_mails.db."""
    import sqlite3
    try:
        konto_label = from_email.split("@")[0].lower()
        kunden_email_m = re.search(r'[\w.+-]+@[\w.-]+\.\w+', to)
        kunden_email = kunden_email_m.group(0).lower() if kunden_email_m else to

        conn = sqlite3.connect(str(SENT_MAILS_DB))
        conn.execute("""
            INSERT OR IGNORE INTO gesendete_mails
            (konto_label, betreff, an, kunden_email, datum, datum_iso,
             message_id, text_plain, hat_anhaenge, mail_typ, mail_folder_pfad)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            konto_label, subject, to, kunden_email,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            datetime.now(timezone.utc).isoformat(),
            message_id, body_plain[:8000], 0, "kira_gesendet", ""
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"sent_mails.db Speichern fehlgeschlagen: {e}")


# ── Template-Versand (für Partner-Mails) ─────────────────────────────────────
def send_from_template(
    template_path: Path,
    from_email: str,
    to: str,
    variables: dict,
    subject: str,
    bcc: str = "",
) -> dict:
    """
    Sendet eine Mail basierend auf HTML-Template.
    Ersetzt {{VAR}} Platzhalter im Template.
    """
    template_path = Path(template_path)
    if not template_path.exists():
        return {"ok": False, "error": f"Template nicht gefunden: {template_path}"}

    html = template_path.read_text(encoding="utf-8")
    for key, value in variables.items():
        html = html.replace(f"{{{{{key}}}}}", str(value))

    # Plain-Text aus HTML extrahieren
    from html.parser import HTMLParser
    class Strip(HTMLParser):
        def __init__(self):
            super().__init__()
            self._t = []
        def handle_data(self, d):
            self._t.append(d)
        def get(self):
            return ' '.join(t for t in self._t if t.strip())

    s = Strip()
    s.feed(html)
    plain = s.get()

    return send_mail(
        from_email=from_email,
        to=to,
        subject=subject,
        body_html=html,
        body_plain=plain,
        bcc=bcc,
    )


# ── Standalone-Test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    print("mail_sender.py — Test")
    print(f"Archiver-Config: {ARCHIVER_CFG}")

    if not ARCHIVER_CFG.exists():
        print("✗ Archiver-Config nicht gefunden!")
        sys.exit(1)

    if not MSAL_OK:
        print("✗ msal nicht installiert: pip install msal")
        sys.exit(1)

    # Test mit info@raumkult.eu
    from_email = "info@raumkult.eu"
    print(f"\nTest-Versand von: {from_email}")
    print("Token wird geholt...")

    try:
        konto = _load_konto(from_email)
        token = get_smtp_token(konto)
        print(f"✓ Token erhalten: {token[:20]}...")
        print(f"\nSMTP-Verbindungstest zu {SMTP_HOST}:{SMTP_PORT}...")
        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.ehlo()
            caps = smtp.esmtp_features
            print(f"✓ SMTP verbunden. AUTH-Methoden: {caps.get('auth', '?')}")
    except Exception as e:
        print(f"✗ Fehler: {e}")
