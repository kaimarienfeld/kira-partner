#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KIRA Microsoft Graph — Kalender-Integration (Paket 8, session-oo)
Erstellt und verwaltet Termine via Microsoft Graph API.

Nutzt die bestehende MSAL-App-Konfiguration aus mail_monitor.py.
Erfordert Calendars.ReadWrite Scope — falls Token fehlt: hilfreiche Fehlermeldung.
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

log = logging.getLogger("graph_calendar")

SCRIPTS_DIR  = Path(__file__).parent
_GRAPH_SCOPE = ["https://graph.microsoft.com/Calendars.ReadWrite"]
_GRAPH_BASE  = "https://graph.microsoft.com/v1.0/me"


def _get_graph_token(email: str) -> str:
    """
    Versucht einen Microsoft Graph Token (Calendars.ReadWrite) zu holen.
    Wirft RuntimeError wenn keine Berechtigung vorhanden.
    """
    try:
        from mail_monitor import _msal_app_kira, _save_token_cache
    except ImportError:
        raise RuntimeError("mail_monitor nicht verfuegbar")

    app, cache, cache_path = _msal_app_kira(email)
    accounts = app.get_accounts(username=email)
    if not accounts:
        raise RuntimeError(f"Kein MSAL-Account fuer {email} — bitte neu verbinden")

    result = app.acquire_token_silent(_GRAPH_SCOPE, account=accounts[0])
    if result and "access_token" in result:
        _save_token_cache(cache, cache_path)
        return result["access_token"]

    # Kein silent Token vorhanden
    raise RuntimeError(
        f"Graph-Berechtigung (Calendars.ReadWrite) fehlt fuer {email}.\n"
        f"Bitte in Einstellungen > E-Mail-Konten das Konto neu verbinden, "
        f"um die Kalender-Berechtigung zu erteilen."
    )


def _graph_request(token: str, method: str, path: str, body: dict = None) -> dict:
    """Einfacher Graph-API-Request."""
    import urllib.request
    url = f"{_GRAPH_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Graph API Fehler {e.code}: {err_body[:200]}")


def erstelle_termin(
    email: str,
    betreff: str,
    start: str,           # ISO-8601: "2026-04-01T10:00:00"
    end: str = None,      # ISO-8601, default: start + 1h
    ort: str = "",
    notiz: str = "",
    zeitzone: str = "Europe/Berlin",
) -> dict:
    """
    Erstellt einen Kalender-Termin via Microsoft Graph.
    Gibt dict zurueck: {ok, event_id, link, error}
    """
    try:
        token = _get_graph_token(email)
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}

    if not end:
        try:
            dt_start = datetime.fromisoformat(start)
            end = (dt_start + timedelta(hours=1)).isoformat()
        except Exception:
            end = start

    event_body = {
        "subject": betreff,
        "start": {"dateTime": start, "timeZone": zeitzone},
        "end":   {"dateTime": end,   "timeZone": zeitzone},
        "body":  {"contentType": "text", "content": notiz},
    }
    if ort:
        event_body["location"] = {"displayName": ort}

    try:
        result = _graph_request(token, "POST", "/events", event_body)
        return {
            "ok": True,
            "event_id": result.get("id", ""),
            "betreff": result.get("subject", betreff),
            "start": start,
            "end": end,
            "link": result.get("webLink", ""),
            "message": f"Termin '{betreff}' erstellt ({start[:16].replace('T', ' ')} Uhr)",
        }
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}


def liste_termine(email: str, tage: int = 7) -> dict:
    """Listet Termine der naechsten N Tage."""
    try:
        token = _get_graph_token(email)
    except RuntimeError as e:
        return {"ok": False, "error": str(e), "termine": []}

    jetzt = datetime.now(timezone.utc)
    bis   = jetzt + timedelta(days=tage)
    start_str = jetzt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str   = bis.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        path = (f"/calendarview?startDateTime={start_str}&endDateTime={end_str}"
                f"&$top=20&$orderby=start/dateTime")
        result = _graph_request(token, "GET", path)
        termine = []
        for ev in result.get("value", []):
            termine.append({
                "betreff": ev.get("subject", ""),
                "start":   (ev.get("start") or {}).get("dateTime", "")[:16],
                "end":     (ev.get("end")   or {}).get("dateTime", "")[:16],
                "ort":     (ev.get("location") or {}).get("displayName", ""),
            })
        return {"ok": True, "termine": termine}
    except RuntimeError as e:
        return {"ok": False, "error": str(e), "termine": []}
