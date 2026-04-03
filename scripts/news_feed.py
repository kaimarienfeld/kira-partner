#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KIRA News-Feed Widget-Backend (session-cccc)
Wetter, RSS-News, Newsletter-Digest für das Dashboard.
Nur stdlib-Abhängigkeiten (urllib, xml.etree, sqlite3, json).

Öffentliche API:
  get_dashboard_widgets() -> dict   — Alle Widget-Daten als JSON
  start_feed_refresh_thread()       — Hintergrund-Cache-Refresh (15 Min)
"""
import json
import hashlib
import logging
import re
import sqlite3
import threading
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("news_feed")

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
CONFIG_FILE   = SCRIPTS_DIR / "config.json"
MAIL_INDEX_DB = KNOWLEDGE_DIR / "mail_index.db"
FEED_CACHE_DB = KNOWLEDGE_DIR / "feed_cache.db"

# ── wttr.in weatherCode → Emoji ──────────────────────────────────────────────
_WEATHER_EMOJI = {
    "113": "\u2600\ufe0f", "116": "\u26c5", "119": "\u2601\ufe0f",
    "122": "\u2601\ufe0f", "143": "\U0001f32b\ufe0f", "176": "\U0001f326\ufe0f",
    "179": "\U0001f328\ufe0f", "182": "\U0001f328\ufe0f", "185": "\U0001f328\ufe0f",
    "200": "\u26c8\ufe0f", "227": "\U0001f328\ufe0f", "230": "\u2744\ufe0f",
    "248": "\U0001f32b\ufe0f", "260": "\U0001f32b\ufe0f", "263": "\U0001f327\ufe0f",
    "266": "\U0001f327\ufe0f", "281": "\U0001f327\ufe0f", "284": "\U0001f327\ufe0f",
    "293": "\U0001f327\ufe0f", "296": "\U0001f327\ufe0f", "299": "\U0001f327\ufe0f",
    "302": "\U0001f327\ufe0f", "305": "\U0001f327\ufe0f", "308": "\U0001f327\ufe0f",
    "311": "\U0001f327\ufe0f", "314": "\U0001f327\ufe0f", "317": "\U0001f327\ufe0f",
    "320": "\U0001f328\ufe0f", "323": "\U0001f328\ufe0f", "326": "\U0001f328\ufe0f",
    "329": "\U0001f328\ufe0f", "332": "\U0001f328\ufe0f", "335": "\U0001f328\ufe0f",
    "338": "\U0001f328\ufe0f", "350": "\U0001f327\ufe0f", "353": "\U0001f327\ufe0f",
    "356": "\U0001f327\ufe0f", "359": "\U0001f327\ufe0f", "386": "\u26c8\ufe0f",
    "389": "\u26c8\ufe0f", "392": "\u26c8\ufe0f", "395": "\U0001f328\ufe0f",
}

# wttr.in weatherDesc Deutsch-Mapping (häufigste)
_CONDITION_DE = {
    "sunny": "Sonnig", "clear": "Klar", "partly cloudy": "Teilweise bewölkt",
    "cloudy": "Bewölkt", "overcast": "Bedeckt", "mist": "Nebelig",
    "fog": "Nebel", "light rain": "Leichter Regen", "moderate rain": "Mäßiger Regen",
    "heavy rain": "Starker Regen", "light snow": "Leichter Schnee",
    "moderate snow": "Mäßiger Schnee", "heavy snow": "Starker Schnee",
    "thunderstorm": "Gewitter", "patchy rain possible": "Vereinzelt Regen möglich",
    "patchy rain nearby": "Vereinzelt Regen möglich",
    "light drizzle": "Leichter Nieselregen", "freezing fog": "Gefrierender Nebel",
    "light rain shower": "Leichter Regenschauer",
    "moderate or heavy rain shower": "Mäßiger bis starker Regenschauer",
}

_db_initialized = False


# ── SQLite Cache ─────────────────────────────────────────────────────────────

def _ensure_db():
    global _db_initialized
    if _db_initialized:
        return
    db = sqlite3.connect(str(FEED_CACHE_DB))
    db.execute("""
        CREATE TABLE IF NOT EXISTS feed_cache (
            key TEXT PRIMARY KEY,
            data_json TEXT,
            fetched_at TEXT,
            expires_at REAL
        )
    """)
    db.commit()
    db.close()
    _db_initialized = True


def _cache_get(key: str) -> dict | None:
    _ensure_db()
    try:
        db = sqlite3.connect(str(FEED_CACHE_DB))
        row = db.execute(
            "SELECT data_json FROM feed_cache WHERE key=? AND expires_at > ?",
            (key, time.time())
        ).fetchone()
        db.close()
        return json.loads(row[0]) if row else None
    except Exception:
        return None


def _cache_get_stale(key: str) -> dict | None:
    """Gibt auch abgelaufene Cache-Daten zurück (Offline-Fallback)."""
    _ensure_db()
    try:
        db = sqlite3.connect(str(FEED_CACHE_DB))
        row = db.execute("SELECT data_json FROM feed_cache WHERE key=?", (key,)).fetchone()
        db.close()
        return json.loads(row[0]) if row else None
    except Exception:
        return None


def _cache_set(key: str, data, ttl_seconds: int):
    _ensure_db()
    try:
        db = sqlite3.connect(str(FEED_CACHE_DB))
        db.execute(
            "INSERT OR REPLACE INTO feed_cache (key, data_json, fetched_at, expires_at) VALUES (?,?,?,?)",
            (key, json.dumps(data, ensure_ascii=False), datetime.now().isoformat(), time.time() + ttl_seconds)
        )
        db.commit()
        db.close()
    except Exception as e:
        log.debug(f"cache_set Fehler: {e}")


def _get_config() -> dict:
    try:
        cfg = json.loads(CONFIG_FILE.read_text("utf-8"))
        return cfg.get("news_feed", {})
    except Exception:
        return {}


# ── Wetter (wttr.in) ────────────────────────────────────────────────────────

def fetch_weather() -> dict | None:
    """Holt Wetterdaten von wttr.in. Cache: 30 Min."""
    cfg = _get_config().get("wetter", {})
    if not cfg.get("aktiv", True):
        return None

    standort = cfg.get("standort", "Düsseldorf")
    cache_key = f"weather:{standort}"

    cached = _cache_get(cache_key)
    if cached:
        return cached

    try:
        url = f"https://wttr.in/{urllib.request.quote(standort)}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "KIRA-Dashboard/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode("utf-8"))

        cur = raw.get("current_condition", [{}])[0]
        code = cur.get("weatherCode", "116")
        desc_en = (cur.get("weatherDesc", [{}])[0].get("value", "")).strip().lower()

        # 3-Tage Forecast
        forecast = []
        for day in raw.get("weather", [])[:3]:
            d = day.get("date", "")
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                day_name = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][dt.weekday()]
            except Exception:
                day_name = d
            fc_code = "116"
            hourly = day.get("hourly", [])
            if hourly:
                # Nimm Mittags-Wert (12:00) wenn verfügbar
                noon = next((h for h in hourly if h.get("time") in ("1200", "1100", "1300")), hourly[len(hourly)//2])
                fc_code = noon.get("weatherCode", "116")
            forecast.append({
                "day": day_name,
                "high": int(day.get("maxtempC", 0)),
                "low": int(day.get("mintempC", 0)),
                "icon_code": fc_code,
            })

        result = {
            "typ": "weather",
            "temp_c": int(cur.get("temp_C", 0)),
            "condition": desc_en.title(),
            "condition_de": _CONDITION_DE.get(desc_en, desc_en.title()),
            "icon_code": code,
            "humidity": cur.get("humidity", "?") + "%",
            "wind_kmh": int(cur.get("windspeedKmph", 0)),
            "location": standort,
            "forecast": forecast,
            "stale": False,
            "cached_at": datetime.now().isoformat()[:16],
        }

        _cache_set(cache_key, result, 1800)  # 30 Min
        return result

    except Exception as e:
        log.warning(f"Wetter-Fetch fehlgeschlagen: {e}")
        # Fallback: abgelaufener Cache
        stale = _cache_get_stale(cache_key)
        if stale:
            stale["stale"] = True
            return stale
        return None


# ── RSS Feeds ────────────────────────────────────────────────────────────────

def _parse_rss(raw_bytes: bytes) -> list[dict]:
    """Parst RSS 2.0 / Atom Feed. Extrahiert Bilder aus media:content, enclosure, img-Tags."""
    try:
        root = ET.fromstring(raw_bytes)
    except ET.ParseError:
        return []

    items = []
    ns = {"media": "http://search.yahoo.com/mrss/", "atom": "http://www.w3.org/2005/Atom"}

    # RSS 2.0
    for item in root.findall(".//item"):
        entry = _extract_rss_item(item, ns)
        if entry:
            items.append(entry)

    # Atom Fallback
    if not items:
        for entry_el in root.findall(".//atom:entry", ns):
            entry = _extract_atom_entry(entry_el, ns)
            if entry:
                items.append(entry)

    return items[:15]


def _extract_rss_item(item, ns) -> dict | None:
    title = (item.findtext("title") or "").strip()
    if not title:
        return None

    link = (item.findtext("link") or "").strip()
    pub_date = (item.findtext("pubDate") or "").strip()
    desc_raw = item.findtext("description") or ""
    snippet = re.sub(r"<[^>]+>", "", desc_raw).strip()[:200]

    image_url = _extract_image(item, ns, desc_raw)

    return {
        "title": title,
        "link": link,
        "snippet": snippet,
        "image_url": image_url,
        "published": pub_date,
    }


def _extract_atom_entry(entry, ns) -> dict | None:
    title = (entry.findtext("atom:title", namespaces=ns) or entry.findtext("title") or "").strip()
    if not title:
        return None

    link_el = entry.find("atom:link[@href]", ns) or entry.find("link[@href]")
    link = link_el.get("href", "") if link_el is not None else ""

    pub_date = (entry.findtext("atom:updated", namespaces=ns)
                or entry.findtext("atom:published", namespaces=ns)
                or entry.findtext("updated") or "").strip()

    summary = entry.findtext("atom:summary", namespaces=ns) or entry.findtext("summary") or ""
    snippet = re.sub(r"<[^>]+>", "", summary).strip()[:200]

    image_url = _extract_image(entry, ns, summary)

    return {
        "title": title,
        "link": link,
        "snippet": snippet,
        "image_url": image_url,
        "published": pub_date,
    }


def _extract_image(el, ns, desc_html: str) -> str | None:
    """Extrahiert Bild-URL: media:content → enclosure → img in description."""
    # 1. media:content
    media = el.find("media:content", ns)
    if media is not None and media.get("url"):
        return media.get("url")

    # 2. media:thumbnail
    thumb = el.find("media:thumbnail", ns)
    if thumb is not None and thumb.get("url"):
        return thumb.get("url")

    # 3. enclosure (type=image/*)
    enc = el.find("enclosure")
    if enc is not None and enc.get("type", "").startswith("image"):
        return enc.get("url")

    # 4. Erstes <img src="..."> im Description-HTML
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc_html)
    if m:
        return m.group(1)

    return None


def fetch_rss_feeds() -> list[dict]:
    """Holt alle konfigurierten RSS-Feeds. Cache: 15 Min pro Feed."""
    cfg = _get_config()
    feeds = cfg.get("rss_feeds", [])
    if not feeds:
        return []

    all_items = []
    for feed_cfg in feeds:
        url = feed_cfg.get("url", "")
        label = feed_cfg.get("label", url)
        if not url:
            continue

        cache_key = f"rss:{hashlib.md5(url.encode()).hexdigest()}"
        cached = _cache_get(cache_key)
        if cached:
            for item in cached:
                item["source"] = label
            all_items.extend(cached)
            continue

        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "KIRA-Dashboard/1.0",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
            })
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = resp.read()

            items = _parse_rss(raw)
            _cache_set(cache_key, items, 900)  # 15 Min

            for item in items:
                item["source"] = label
            all_items.extend(items)

        except Exception as e:
            log.debug(f"RSS-Fetch fehlgeschlagen für {label}: {e}")
            # Stale-Fallback
            stale = _cache_get_stale(cache_key)
            if stale:
                for item in stale:
                    item["source"] = label
                all_items.extend(stale)

    # Nach Datum sortieren (neueste zuerst), max 30
    all_items.sort(key=lambda x: x.get("published", ""), reverse=True)
    return all_items[:30]


# ── Newsletter-Digest (LLM) ─────────────────────────────────────────────────

def generate_newsletter_digest() -> dict | None:
    """Fasst Newsletter der letzten 7 Tage via Kira-LLM zusammen. Cache: 24h."""
    cfg = _get_config().get("newsletter_digest", {})
    if not cfg.get("aktiv", True):
        return None

    cache_key = "newsletter_digest"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    max_items = cfg.get("max_items", 5)

    # Newsletter aus mail_index.db laden
    newsletters = _load_recent_newsletters()
    if not newsletters:
        return None

    # LLM-Zusammenfassung versuchen
    digest = _llm_digest(newsletters, max_items)
    if digest:
        _cache_set(cache_key, digest, 86400)  # 24h
        return digest

    # Fallback ohne LLM
    fallback = _fallback_digest(newsletters, max_items)
    _cache_set(cache_key, fallback, 43200)  # 12h
    return fallback


def _load_recent_newsletters() -> list[dict]:
    """Lädt letzte 7 Tage Newsletter aus mail_index.db."""
    if not MAIL_INDEX_DB.exists():
        return []
    try:
        db = sqlite3.connect(str(MAIL_INDEX_DB))
        db.row_factory = sqlite3.Row
        seit = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        rows = db.execute("""
            SELECT betreff, absender, text_plain, datum
            FROM mails
            WHERE kategorie = 'Newsletter / Werbung'
              AND text_plain IS NOT NULL
              AND length(text_plain) > 100
              AND datum >= ?
            ORDER BY datum DESC
            LIMIT 10
        """, (seit,)).fetchall()
        db.close()
        return [dict(r) for r in rows]
    except Exception as e:
        log.debug(f"Newsletter-Load fehlgeschlagen: {e}")
        return []


def _llm_digest(newsletters: list[dict], max_items: int) -> dict | None:
    """LLM-basierte Newsletter-Zusammenfassung."""
    try:
        from kira_llm import chat

        # Kontext bauen
        parts = []
        for nl in newsletters[:10]:
            absender = nl.get("absender", "?")
            betreff = nl.get("betreff", "?")
            text = (nl.get("text_plain") or "")[:500]
            parts.append(f"--- Newsletter von {absender} ---\nBetreff: {betreff}\n{text}\n")

        kontext = "\n".join(parts)

        prompt = (
            f"Fasse die folgenden Newsletter zusammen. "
            f"Extrahiere {max_items} interessante Highlights als kurze Karten-Texte. "
            f"Für jedes Highlight: ein kurzer Titel (max 60 Zeichen), eine Zusammenfassung "
            f"(max 120 Zeichen), und die Quelle (Absender-Name). "
            f"Antworte NUR mit einem JSON-Array:\n"
            f'[{{"titel": "...", "text": "...", "quelle": "..."}}]\n\n'
            f"Newsletter-Inhalte:\n{kontext}"
        )

        result = chat(prompt, session_id="newsletter_digest_auto")
        text = result.get("text", "")

        # JSON aus Antwort extrahieren
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            highlights = json.loads(m.group())
            return {
                "typ": "newsletter_digest",
                "highlights": highlights[:max_items],
                "erstellt_am": datetime.now().isoformat()[:16],
                "via": "llm",
            }
    except Exception as e:
        log.debug(f"LLM-Digest fehlgeschlagen: {e}")

    return None


def _fallback_digest(newsletters: list[dict], max_items: int) -> dict:
    """Fallback ohne LLM: Betreff + gekürzte Texte."""
    highlights = []
    for nl in newsletters[:max_items]:
        highlights.append({
            "titel": (nl.get("betreff") or "Newsletter")[:60],
            "text": re.sub(r'\s+', ' ', (nl.get("text_plain") or "")[:120]).strip(),
            "quelle": (nl.get("absender") or "").split("<")[0].strip() or "Newsletter",
        })
    return {
        "typ": "newsletter_digest",
        "highlights": highlights,
        "erstellt_am": datetime.now().isoformat()[:16],
        "via": "fallback",
    }


# ── Hauptfunktion ────────────────────────────────────────────────────────────

def get_dashboard_widgets() -> dict:
    """Liefert alle Widget-Daten für das Dashboard."""
    _ensure_db()

    weather = None
    news = []
    newsletter = None

    try:
        weather = fetch_weather()
    except Exception as e:
        log.debug(f"Widget weather Fehler: {e}")

    try:
        news = fetch_rss_feeds()
    except Exception as e:
        log.debug(f"Widget news Fehler: {e}")

    try:
        newsletter = generate_newsletter_digest()
    except Exception as e:
        log.debug(f"Widget newsletter Fehler: {e}")

    return {
        "weather": weather,
        "news": news,
        "newsletter": newsletter,
        "ts": datetime.now().isoformat()[:16],
    }


# ── Hintergrund-Refresh ─────────────────────────────────────────────────────

_refresh_started = False


def start_feed_refresh_thread():
    """Startet Hintergrund-Thread für Cache-Vorwärmung (alle 15 Min)."""
    global _refresh_started
    if _refresh_started:
        return
    _refresh_started = True

    def _loop():
        time.sleep(30)  # 30s nach Server-Start warten
        while True:
            try:
                get_dashboard_widgets()
                log.debug("Feed-Cache vorgewärmt")
            except Exception as e:
                log.debug(f"Feed-Refresh Fehler: {e}")
            time.sleep(900)  # 15 Min

    t = threading.Thread(target=_loop, name="NewsFeedRefresh", daemon=True)
    t.start()
    log.info("News-Feed Refresh-Thread gestartet (15 Min Intervall)")
