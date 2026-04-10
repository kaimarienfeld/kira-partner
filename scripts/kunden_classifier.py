#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kunden_classifier.py — LLM-basierte Kunden-/Projekt-Zuordnung für KIRA CRM.

Pipeline:
  1. Geschäftskontakt-Vorfilter (Newsletter/noreply → kein Geschäftsfall)
  2. Fast-Path: Absender in kunden_identitaeten mit confidence='eindeutig'
  3. LLM-Path: Super-Prompt mit Kunden-Kontext → JSON-Response
  4. Confidence-Auswertung → Auto-Zuordnung oder Prüfliste

Läuft NACH vorgang_router.py in der Mail-Verarbeitungspipeline.
"""
import json, logging, re, sqlite3, hashlib, time, threading, datetime as _dt, uuid
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("kunden_classifier")

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
KUNDEN_DB     = KNOWLEDGE_DIR / "kunden.db"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"
MAIL_INDEX_DB = KNOWLEDGE_DIR / "mail_index.db"
CONFIG_FILE   = SCRIPTS_DIR / "config.json"

# ── Lead-Signal-Erkennung ──────────────────────────────────────────────────
_ANFRAGE_SIGNALE = re.compile(
    r"(anfrage|angebot|interesse|projekt|termin|beratung|kosten|preis|"
    r"möchte|moechte|würden sie|wuerden sie|auftrag|besichtigung|bestellung)",
    re.IGNORECASE,
)
_FREEMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "gmx.de", "gmx.net", "web.de",
    "yahoo.com", "yahoo.de", "outlook.com", "hotmail.com", "hotmail.de",
    "t-online.de", "freenet.de", "posteo.de", "mailbox.org", "icloud.com",
    "aol.com", "live.de", "live.com", "msn.com",
}
_MASSEN_DOMAINS = {
    "mailchimp.com", "sendgrid.net", "constantcontact.com",
    "hubspot.com", "mailjet.com", "sendinblue.com", "brevo.com",
    "klicktipp.com", "cleverreach.com", "mailerlite.com",
    "amazonses.com", "bounce.google.com",
}

# ── Cache für gleiche Absender+Betreff-Kombination (1h) ─────────────────────
_CLASSIFY_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 3600  # 1 Stunde

# ── Newsletter-/Noreply-Signale ──────────────────────────────────────────────
_NOREPLY_PATTERNS = re.compile(
    r"^(noreply|no-reply|mailer|bounce|newsletter|notifications?|info|support|marketing|sales|postmaster)@",
    re.IGNORECASE,
)
_NEWSLETTER_BETREFF = re.compile(
    r"(newsletter|unsubscribe|abbestellen|nur heute|exklusiv f[uü]r sie|jetzt sichern|angebot des tages)",
    re.IGNORECASE,
)
_NEWSLETTER_DOMAINS = {
    "mailchimp.com", "sendgrid.net", "constantcontact.com",
    "hubspot.com", "mailjet.com", "sendinblue.com", "brevo.com",
    "klicktipp.com", "cleverreach.com", "mailerlite.com",
}


def _get_kunden_db():
    """Öffnet kunden.db mit Row-Factory."""
    db = sqlite3.connect(str(KUNDEN_DB))
    db.row_factory = sqlite3.Row
    return db


def _extract_email(absender: str) -> str:
    """Extrahiert E-Mail aus 'Name <email>' oder plain email."""
    m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", absender or "")
    return m.group(0).lower() if m else (absender or "").lower().strip()


def _extract_domain(email: str) -> str:
    """Extrahiert Domain aus E-Mail."""
    parts = email.split("@")
    return parts[1] if len(parts) == 2 else ""


# ── Geschäftskontakt-Filter ─────────────────────────────────────────────────

def ist_geschaeftskontakt(absender: str, betreff: str = "", headers: dict = None) -> bool:
    """
    Prüft ob eine Mail von einem echten Geschäftskontakt stammt.
    Returns True wenn es ein Geschäftskontakt ist, False wenn Newsletter/Spam.
    """
    email = _extract_email(absender)
    domain = _extract_domain(email)

    # 1. Bekannte Newsletter-Domains
    if domain in _NEWSLETTER_DOMAINS:
        return False

    # 2. Noreply-Muster
    if _NOREPLY_PATTERNS.match(email):
        return False

    # 3. Newsletter-Betreff
    if _NEWSLETTER_BETREFF.search(betreff or ""):
        return False

    # 4. Mail-Header-Check (List-Unsubscribe, Precedence: bulk)
    if headers:
        if headers.get("List-Unsubscribe") or headers.get("list-unsubscribe"):
            return False
        prec = headers.get("Precedence", "").lower()
        if prec in ("bulk", "list", "junk"):
            return False

    # 5. Bekannt in kunden_identitaeten → definitiv Geschäftskontakt
    try:
        db = _get_kunden_db()
        row = db.execute(
            "SELECT COUNT(*) as c FROM kunden_identitaeten WHERE LOWER(wert) = ?",
            (email,)
        ).fetchone()
        db.close()
        if row and row["c"] > 0:
            return True
    except Exception:
        pass

    # Default: als Geschäftskontakt behandeln (besser zu viel als zu wenig)
    return True


# ── Fast-Path ────────────────────────────────────────────────────────────────

def _fast_path(absender_email: str) -> dict | None:
    """
    Prüft ob Absender eindeutig einem Kunden zugeordnet ist.
    Stufe 1: Exakter Email-Match in kunden_identitaeten
    Stufe 2: Domain-Match (nur für Geschäfts-Domains, nicht Freemail)
    Returns Zuordnungsergebnis oder None wenn LLM nötig.
    """
    try:
        db = _get_kunden_db()
        # Stufe 1: Exakter Email-Match
        row = db.execute("""
            SELECT ki.kunden_id, ki.confidence, k.name, k.firmenname
            FROM kunden_identitaeten ki
            JOIN kunden k ON k.id = ki.kunden_id
            WHERE LOWER(ki.wert) = ? AND ki.typ = 'mail'
              AND k.lexware_id IS NOT NULL
            ORDER BY CASE ki.confidence
                WHEN 'eindeutig' THEN 1
                WHEN 'wahrscheinlich' THEN 2
                WHEN 'pruefen' THEN 3
                ELSE 4
            END
            LIMIT 1
        """, (absender_email.lower(),)).fetchone()

        if not row:
            # Stufe 2: Domain-Match
            domain = _extract_domain(absender_email)
            if domain:
                row = db.execute("""
                    SELECT ki.kunden_id, 'wahrscheinlich' as confidence,
                           k.name, k.firmenname
                    FROM kunden_identitaeten ki
                    JOIN kunden k ON k.id = ki.kunden_id
                    WHERE LOWER(ki.wert) = ? AND ki.typ = 'domain'
                      AND k.lexware_id IS NOT NULL
                    LIMIT 1
                """, (domain.lower(),)).fetchone()

        if not row:
            db.close()
            return None

        if row["confidence"] not in ("eindeutig", "wahrscheinlich"):
            db.close()
            return None

        # Aktives Projekt finden
        projekt = db.execute("""
            SELECT id, projektname, status FROM kunden_projekte
            WHERE kunden_id = ? AND status IN ('aktiv', 'planung')
            ORDER BY aktualisiert_am DESC LIMIT 1
        """, (row["kunden_id"],)).fetchone()

        db.close()

        return {
            "kunden_id": row["kunden_id"],
            "kunden_name": row["name"] or row["firmenname"] or "?",
            "kunden_confidence": row["confidence"],
            "projekt_id": projekt["id"] if projekt else None,
            "projekt_name": projekt["projektname"] if projekt else None,
            "projekt_confidence": "wahrscheinlich" if projekt else "unklar",
            "fall_typ": None,  # Fast-Path bestimmt keinen Fall-Typ
            "ist_geschaeftsfall": True,
            "fast_path": True,
            "reasoning": f"Absender {absender_email} ist als {row['confidence']} zugeordnet",
        }
    except Exception as e:
        logger.warning("Fast-Path Fehler: %s", e)
        return None


# ── LLM-Kontext laden ────────────────────────────────────────────────────────

def _build_kunden_kontext(max_kunden: int = 50) -> str:
    """Baut kompakten Kunden-Kontext für den Super-Prompt.

    NUR Lexware-verifizierte Kunden werden einbezogen (REGEL-09).
    """
    try:
        db = _get_kunden_db()
        kunden = db.execute("""
            SELECT k.id, k.name, k.firmenname, k.email, k.kundentyp, k.status,
                   k.letztkontakt
            FROM kunden k
            WHERE k.status != 'archiv'
              AND k.lexware_id IS NOT NULL AND k.lexware_id != ''
            ORDER BY k.letztkontakt DESC NULLS LAST
            LIMIT ?
        """, (max_kunden,)).fetchall()

        lines = []
        for k in kunden:
            kid = k["id"]
            name = k["firmenname"] or k["name"] or "?"
            email = k["email"] or ""

            # Identitäten
            idents = db.execute(
                "SELECT typ, wert FROM kunden_identitaeten WHERE kunden_id = ? LIMIT 5",
                (kid,)
            ).fetchall()
            ident_str = ", ".join(f"{i['typ']}:{i['wert']}" for i in idents) if idents else email

            # Projekte
            projekte = db.execute("""
                SELECT id, projektname, status, beginn_am, abschluss_am
                FROM kunden_projekte WHERE kunden_id = ?
                ORDER BY aktualisiert_am DESC LIMIT 5
            """, (kid,)).fetchall()
            proj_str = ""
            if projekte:
                proj_parts = []
                for p in projekte:
                    pname = p["projektname"]
                    pstat = p["status"]
                    pdate = p["beginn_am"] or ""
                    pend = p["abschluss_am"] or ""
                    proj_parts.append(f"P{p['id']}:{pname}({pstat},{pdate[:7]}-{pend[:7] if pend else 'laufend'})")
                proj_str = " | Projekte: " + ", ".join(proj_parts)

            lines.append(f"K{kid}: {name} [{ident_str}] Status:{k['status'] or 'aktiv'}{proj_str}")

        db.close()
        return "\n".join(lines) if lines else "(Keine Kunden in Datenbank)"
    except Exception as e:
        logger.warning("Kunden-Kontext Fehler: %s", e)
        return "(Fehler beim Laden des Kunden-Kontexts)"


def _tabelle_existiert(conn, name: str) -> bool:
    """Prüft ob Tabelle existiert."""
    r = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return r is not None


def _build_kunden_kontext_erweitert(conn=None) -> str:
    """
    Token-effizienter Kunden-Kontext mit Identitäten, Projekten,
    letzten Aktivitäten und Lernregeln für den erweiterten Super-Prompt.
    """
    close_db = False
    try:
        if conn is None:
            conn = _get_kunden_db()
            close_db = True

        kunden = conn.execute('''
            SELECT k.id, k.name, k.firmenname, k.status,
                   GROUP_CONCAT(DISTINCT ki.typ || ':' || ki.wert) AS identitaeten
            FROM kunden k
            LEFT JOIN kunden_identitaeten ki
                ON ki.kunden_id = k.id
                AND ki.confidence IN ('eindeutig','wahrscheinlich')
            WHERE k.lexware_id IS NOT NULL
              AND k.status != 'archiv'
            GROUP BY k.id
            ORDER BY k.kundenwert DESC, k.name ASC
            LIMIT 100
        ''').fetchall()

        projekte = conn.execute('''
            SELECT kp.kunden_id, kp.id, kp.projektname, kp.status,
                   kp.beginn_am, kp.abschluss_am
            FROM kunden_projekte kp
            JOIN kunden k ON k.id = kp.kunden_id
            WHERE k.lexware_id IS NOT NULL
            ORDER BY kp.kunden_id, kp.beginn_am DESC
        ''').fetchall()

        aktivitaeten = conn.execute('''
            SELECT ka.kunden_id, ka.ereignis_typ, ka.zusammenfassung, ka.erstellt_am
            FROM kunden_aktivitaeten ka
            JOIN kunden k ON k.id = ka.kunden_id
            WHERE k.lexware_id IS NOT NULL
              AND ka.sichtbar_in_verlauf = 1
            ORDER BY ka.kunden_id, ka.erstellt_am DESC
        ''').fetchall()

        lernregeln = []
        if _tabelle_existiert(conn, 'kunden_lernregeln'):
            lernregeln = conn.execute('''
                SELECT kunden_id, regel_typ, bedingung_json, aktion_json,
                       confidence, anwendungen
                FROM kunden_lernregeln
                WHERE aktiv = 1
                ORDER BY anwendungen DESC
                LIMIT 20
            ''').fetchall()

        # Indizes aufbauen
        proj_by_kunde = {}
        for p in projekte:
            proj_by_kunde.setdefault(p['kunden_id'], []).append(p)

        akt_by_kunde = {}
        for a in aktivitaeten:
            lst = akt_by_kunde.setdefault(a['kunden_id'], [])
            if len(lst) < 5:
                lst.append(a)

        regel_by_kunde = {}
        globale_regeln = []
        for r in lernregeln:
            if r['kunden_id']:
                regel_by_kunde.setdefault(r['kunden_id'], []).append(r)
            else:
                globale_regeln.append(r)

        zeilen = []
        for k in kunden:
            kid = k['id']
            name = k['name'] or k['firmenname'] or f"Kunde #{kid}"
            zeilen.append(f"\n#{kid}: {name} [{k['status']}]")

            if k['identitaeten']:
                zeilen.append(f"  Kontakte: {k['identitaeten']}")

            for p in proj_by_kunde.get(kid, [])[:4]:
                zeitraum = ""
                if p['beginn_am']:
                    zeitraum = f" {p['beginn_am'][:7]}"
                    if p['abschluss_am']:
                        zeitraum += f"—{p['abschluss_am'][:7]}"
                zeilen.append(f"  Projekt #{p['id']}: {p['projektname']} [{p['status']}]{zeitraum}")

            for a in akt_by_kunde.get(kid, [])[:3]:
                zeilen.append(f"  [{a['erstellt_am'][:10]}] {a['ereignis_typ']}: {(a['zusammenfassung'] or '')[:60]}")

            for r in regel_by_kunde.get(kid, []):
                try:
                    bed = json.loads(r['bedingung_json'])
                    desc = bed.get('beschreibung', r['regel_typ'])
                except Exception:
                    desc = r['regel_typ']
                zeilen.append(f"  Lernregel: {desc}")

            # B-2: Schreibstil-Fingerprinting (lazy, 7d-Cache)
            try:
                schreibstil = _build_schreibstil_profil(kid, conn)
                if schreibstil:
                    zeilen.append(f"  Schreibstil: {schreibstil}")
            except Exception:
                pass

        if close_db:
            conn.close()
        return '\n'.join(zeilen) if zeilen else "Noch keine Kunden vorhanden."
    except Exception as e:
        logger.warning("Erweiterter Kunden-Kontext Fehler: %s", e)
        if close_db and conn:
            try:
                conn.close()
            except Exception:
                pass
        return "(Fehler beim Laden des erweiterten Kunden-Kontexts)"


def _build_lernregeln_kontext(conn=None) -> str:
    """Baut Lernregeln-Kontext für den Super-Prompt."""
    close_db = False
    try:
        if conn is None:
            conn = _get_kunden_db()
            close_db = True
        if not _tabelle_existiert(conn, 'kunden_lernregeln'):
            return "(Noch keine Lernregeln)"
        regeln = conn.execute('''
            SELECT kl.id, kl.kunden_id, kl.regel_typ, kl.bedingung_json,
                   kl.aktion_json, kl.anwendungen, k.name as kunden_name
            FROM kunden_lernregeln kl
            LEFT JOIN kunden k ON k.id = kl.kunden_id
            WHERE kl.aktiv = 1
            ORDER BY kl.anwendungen DESC
            LIMIT 20
        ''').fetchall()
        if close_db:
            conn.close()
        if not regeln:
            return "(Noch keine Lernregeln)"
        lines = []
        for r in regeln:
            kunde = r['kunden_name'] or "global"
            try:
                bed = json.loads(r['bedingung_json'])
                desc = bed.get('beschreibung', r['regel_typ'])
            except Exception:
                desc = r['regel_typ']
            lines.append(f"- [{r['regel_typ']}] {desc} (Kunde: {kunde}, {r['anwendungen']}x angewendet)")
        return '\n'.join(lines)
    except Exception as e:
        logger.debug("Lernregeln-Kontext Fehler: %s", e)
        return "(Fehler beim Laden der Lernregeln)"


# ── B-2: Schreibstil-Fingerprinting ──────────────────────────────────────────
_SCHREIBSTIL_CACHE = {}  # {kunden_id: (timestamp, profil_text)}
_SCHREIBSTIL_TTL = 7 * 86400  # 7 Tage Cache


def _build_schreibstil_profil(kunden_id: int, conn) -> str:
    """
    Extrahiert charakteristische Schreibmerkmale aus den letzten Mails
    eines Kunden für den LLM-Kontext.
    Max. 5 repräsentative Sätze — kein vollständiger Text.
    Lazy gebaut, 7-Tage-Cache.
    """
    # Cache prüfen
    cached = _SCHREIBSTIL_CACHE.get(kunden_id)
    if cached and (time.time() - cached[0]) < _SCHREIBSTIL_TTL:
        return cached[1]

    aktivitaeten = conn.execute('''
        SELECT quelle_id, volltext_auszug
        FROM kunden_aktivitaeten
        WHERE kunden_id = ?
          AND ereignis_typ = 'mail'
          AND volltext_auszug IS NOT NULL
        ORDER BY erstellt_am DESC
        LIMIT 10
    ''', (kunden_id,)).fetchall()

    if not aktivitaeten:
        return ""

    auszuege = '\n---\n'.join([a['volltext_auszug'][:200] for a in aktivitaeten[:5]])

    prompt = f"""Analysiere den Schreibstil dieser Mails und beschreibe ihn in maximal 2 Sätzen.
Fokus auf: Anrede (formell/informell?), Satzlänge, typische Formulierungen, Abschlussformel.
NICHT den Inhalt beschreiben — nur den Stil.

Mails:
{auszuege}

Antwort (max 2 Sätze, kein JSON):"""

    try:
        from kira_llm import _call_llm_simple
        profil = _call_llm_simple(prompt, max_tokens=100)
        _SCHREIBSTIL_CACHE[kunden_id] = (time.time(), profil)
        return profil
    except Exception:
        return ""


# ── B-3: Sentiment-Analyse ──────────────────────────────────────────────────


def _sentiment_analysieren(mail_auszug: str) -> float:
    """
    Schnelle Sentiment-Einschätzung via LLM.
    Gibt Score zwischen -1.0 und 1.0 zurück.
    Verwendet das günstigste verfügbare Modell.
    """
    if not mail_auszug or len(mail_auszug) < 20:
        return 0.0

    prompt = f"""Bewerte den Ton dieser Nachricht auf einer Skala von -1.0 bis 1.0.
-1.0 = sehr negativ/unzufrieden/fordernd
 0.0 = neutral/sachlich
+1.0 = sehr positiv/freundlich/zufrieden

Nachricht: {mail_auszug[:300]}

Antworte NUR mit einer Zahl zwischen -1.0 und 1.0, z.B.: 0.3"""

    try:
        from kira_llm import _call_llm_simple
        antwort = _call_llm_simple(prompt, max_tokens=5)
        return max(-1.0, min(1.0, float(antwort.strip())))
    except Exception:
        return 0.0


def _sentiment_trend_berechnen(kunden_id: int, conn) -> float:
    """
    Berechnet den Sentiment-Trend eines Kunden über die letzten 30 Tage.
    Vergleicht mit den 30 Tagen davor. Negatives Ergebnis = Verschlechterung.
    """
    letzte_30 = conn.execute('''
        SELECT AVG(sentiment_score) FROM kunden_aktivitaeten
        WHERE kunden_id = ? AND ereignis_typ = 'mail'
          AND sentiment_score IS NOT NULL
          AND erstellt_am >= ?
    ''', (kunden_id, (datetime.now() - timedelta(days=30)).isoformat())
    ).fetchone()[0] or 0.0

    davor_30 = conn.execute('''
        SELECT AVG(sentiment_score) FROM kunden_aktivitaeten
        WHERE kunden_id = ? AND ereignis_typ = 'mail'
          AND sentiment_score IS NOT NULL
          AND erstellt_am BETWEEN ? AND ?
    ''', (
        kunden_id,
        (datetime.now() - timedelta(days=60)).isoformat(),
        (datetime.now() - timedelta(days=30)).isoformat()
    )).fetchone()[0] or 0.0

    trend = letzte_30 - davor_30

    if trend < -0.3 and letzte_30 < 0.0:
        _sentiment_warnung(kunden_id, trend, letzte_30, conn)

    conn.execute('''
        UPDATE kunden SET sentiment_trend = ?, sentiment_warnung = ?
        WHERE id = ?
    ''', (round(trend, 3), 1 if trend < -0.3 else 0, kunden_id))

    return trend


def _sentiment_warnung(kunden_id, trend, aktuell, conn):
    """Aufgabe für Kai wenn Sentiment sich stark verschlechtert."""
    kunde = conn.execute(
        'SELECT name, firmenname FROM kunden WHERE id = ?', (kunden_id,)
    ).fetchone()
    if not kunde:
        return
    name = kunde['firmenname'] or kunde['name'] or f"Kunde #{kunden_id}"

    try:
        tdb = sqlite3.connect(str(TASKS_DB))
        tdb.row_factory = sqlite3.Row
        # Prüfen ob bereits kürzlich gewarnt (14 Tage)
        recent = tdb.execute("""
            SELECT MAX(created_at) FROM tasks
            WHERE title LIKE ? AND created_at > ?
        """, (
            f"%Ton-Veränderung%{kunden_id}%",
            (datetime.now() - timedelta(days=14)).isoformat()
        )).fetchone()[0]
        if recent:
            tdb.close()
            return

        tdb.execute('''
            INSERT INTO tasks (title, body, status, priority, created_at)
            VALUES (?, ?, 'offen', 'normal', ?)
        ''', (
            f"Ton-Veränderung bei {name} (Kunde #{kunden_id})",
            f"Kira hat bemerkt: Der Ton bei {name} hat sich in letzter Zeit "
            f"messbar verschlechtert.\n\n"
            f"Aktueller Durchschnitt: {aktuell:+.1f} | Veränderung: {trend:+.1f}\n\n"
            f"Empfehlung: Proaktiv Kontakt aufnehmen bevor eine Reklamation entsteht.",
            datetime.now().isoformat()
        ))
        tdb.commit()
        tdb.close()
        _elog_safe("sentiment_warnung", f"Kunde {kunden_id} ({name}): Trend {trend:+.2f}")
    except Exception as e:
        logger.warning("Sentiment-Warnung Fehler: %s", e)


# ── B-4: Cross-Channel Thread-Linking ────────────────────────────────────────


def _thread_link_erkennen(neue_aktivitaet: dict,
                          kunden_id: int, conn) -> str | None:
    """
    Prüft ob eine neue Aktivität zu einem bestehenden Thread gehört.
    Nutzt: zeitliche Nähe (72h), gleicher Fall, Inhaltsbezug.
    Gibt thread_id zurück oder None wenn neuer Thread.
    """
    letzte = conn.execute('''
        SELECT id, thread_id, zusammenfassung, erstellt_am, ereignis_typ
        FROM kunden_aktivitaeten
        WHERE kunden_id = ?
          AND erstellt_am >= ?
          AND sichtbar_in_verlauf = 1
        ORDER BY erstellt_am DESC
        LIMIT 10
    ''', (
        kunden_id,
        (datetime.now() - timedelta(hours=72)).isoformat()
    )).fetchall()

    if not letzte:
        return None

    letzte_text = '\n'.join([
        f"[{a['ereignis_typ'].upper()}] {a['erstellt_am'][:16]}: {(a['zusammenfassung'] or '')[:80]}"
        for a in letzte
    ])

    prompt = f"""Prüfe ob diese neue Aktivität zu einer der letzten gehört.

NEUE AKTIVITÄT:
[{neue_aktivitaet.get('typ', '').upper()}] {(neue_aktivitaet.get('zusammenfassung', '') or '')[:200]}

LETZTE AKTIVITÄTEN (letzte 72h):
{letzte_text}

Gehört die neue Aktivität zu einer der letzten? (gleiche Konversation / Folge-Aktion)

Antworte NUR als JSON:
{{"ist_folge": true/false, "gehoert_zu_index": null, "begruendung": "max 1 Satz"}}"""

    try:
        from kira_llm import _call_llm_simple
        raw = _call_llm_simple(prompt, max_tokens=80)
        # JSON aus Antwort extrahieren
        json_match = re.search(r'\{[^}]+\}', raw)
        if not json_match:
            return None
        antwort = json.loads(json_match.group())
        if antwort.get('ist_folge') and antwort.get('gehoert_zu_index') is not None:
            idx = int(antwort['gehoert_zu_index'])
            if 0 <= idx < len(letzte):
                thread_id = letzte[idx]['thread_id']
                if not thread_id:
                    thread_id = str(uuid.uuid4())[:8]
                    conn.execute('''
                        UPDATE kunden_aktivitaeten
                        SET thread_id = ?, thread_typ = 'haupt'
                        WHERE id = ?
                    ''', (thread_id, letzte[idx]['id']))
                return thread_id
    except Exception:
        pass
    return None


# ── B-5: Next-Best-Action ────────────────────────────────────────────────────
_NBA_CACHE = {}  # {fall_id: (timestamp, result)}
_NBA_TTL = 900  # 15 Minuten Cache


def next_best_action_fuer_fall(fall_id: int, conn=None) -> dict:
    """
    Analysiert einen Fall und schlägt die sinnvollste nächste Aktion vor.
    Ergebnis wird gecacht (15 Minuten).
    """
    cached = _NBA_CACHE.get(fall_id)
    if cached and (time.time() - cached[0]) < _NBA_TTL:
        return cached[1]

    close_db = False
    if conn is None:
        conn = _get_kunden_db()
        close_db = True
    try:
        fall = conn.execute('SELECT * FROM kunden_faelle WHERE id = ?', (fall_id,)).fetchone()
        if not fall:
            return {"aktion": "Prüfen", "begruendung": "Fall nicht gefunden", "dringlichkeit": "keine_eile"}
        kunde = conn.execute('SELECT * FROM kunden WHERE id = ?', (fall['kunden_id'],)).fetchone()
        letzte_aktivitaeten = conn.execute('''
            SELECT ereignis_typ, zusammenfassung, erstellt_am
            FROM kunden_aktivitaeten
            WHERE fall_id = ?
            ORDER BY erstellt_am DESC
            LIMIT 10
        ''', (fall_id,)).fetchall()

        tage_seit_update = 99
        if fall['aktualisiert_am']:
            try:
                tage_seit_update = (datetime.now() - datetime.fromisoformat(
                    fall['aktualisiert_am'].split('+')[0]
                )).days
            except Exception:
                pass

        kunden_name = (kunde['firmenname'] or kunde['name']) if kunde else f"Kunde #{fall['kunden_id']}"

        prompt = f"""Du bist der Geschäftsstratege für ein Handwerksunternehmen.

FALL:
Typ: {fall['fall_typ']}
Status: {fall['status']}
Priorität: {fall['prioritaet']}
Fällig: {fall['faellig_am'] or 'kein Datum'}
Zuletzt aktualisiert: vor {tage_seit_update} Tagen

KUNDE:
Name: {kunden_name}
Health-Score: {(kunde.get('health_score') or 0.5) if kunde else 0.5:.0%}
Zahlungsverhalten: {(kunde.get('zahlungsverhalten_score') or 0.5) if kunde else 0.5:.0%}

LETZTE AKTIVITÄTEN:
{chr(10).join([f"[{a['erstellt_am'][:10]}] {a['ereignis_typ']}: {(a['zusammenfassung'] or '')[:80]}" for a in letzte_aktivitaeten]) or '(keine)'}

Was ist die sinnvollste nächste Aktion? Sei konkret und handlungsorientiert.
Antworte NUR als JSON:
{{"aktion": "Mail senden|Anrufen|Angebot erstellen|Status ändern|Warten|Prüfen", "begruendung": "max 1 Satz warum", "dringlichkeit": "sofort|diese_woche|naechste_woche|keine_eile", "vorschlagstext": "Optional: konkreter Vorschlagstext (max 2 Sätze)"}}"""

        from kira_llm import _call_llm_simple
        raw = _call_llm_simple(prompt, max_tokens=200)
        json_match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            _NBA_CACHE[fall_id] = (time.time(), result)
            return result
        return {"aktion": "Prüfen", "begruendung": "Keine Empfehlung möglich", "dringlichkeit": "keine_eile"}
    except Exception as e:
        logger.warning("NBA Fehler für Fall %s: %s", fall_id, e)
        return {"aktion": "Prüfen", "begruendung": str(e), "dringlichkeit": "keine_eile"}
    finally:
        if close_db:
            conn.close()


def _build_llm_prompt(absender: str, betreff: str, text_auszug: str,
                      datum: str, kunden_kontext: str,
                      lernregeln_kontext: str = "") -> str:
    """Baut den erweiterten Super-Prompt für den Kunden-Classifier (v2).
    Beantwortet drei Fragen gleichzeitig: Wer? Welches Projekt? Neue Identität?"""
    return f"""Du bist der CRM-Analyst von KIRA für ein Handwerksunternehmen
(Sichtbeton / Betonkosmetik / Oberflächenveredelung).

Analysiere die neue Aktivität und beantworte alle drei Fragen.

## NEUE AKTIVITÄT
Typ: mail
Von: {absender}
Betreff: {betreff}
Datum: {datum}
Inhalt:
{text_auszug[:2000]}

## BEKANNTE KUNDEN MIT HISTORIA
{kunden_kontext}

## GELERNTE REGELN (aus Kai-Korrekturen)
{lernregeln_kontext or '(Noch keine Lernregeln)'}

---

## FRAGE 1: WER IST DAS?

Prüfe NICHT nur die E-Mail-Adresse. Prüfe auch:
- Wird ein bekannter Firmenname erwähnt?
- Schreibstil — passt er zum bekannten Stil eines Kunden?
  (Formell/informell, typische Formulierungen, Anrede)
- Passt der Inhalt / die Wortwahl zu einem bekannten Kunden?
- Gibt es zeitliche Nähe zu bekannten Aktivitäten dieses Kunden?
- Gibt es gelernte Regeln die hier greifen?
- Ist die Absender-Domain zu einem bekannten Kunden ähnlich?

Wenn der Absender nicht bekannt ist, aber sehr wahrscheinlich
ein bekannter Kunde von einer anderen Adresse ist: erkenne das.

## FRAGE 2: WELCHES PROJEKT?

Wenn ein Kunde gefunden: zu welchem Projekt passt der Inhalt?

WICHTIGE REGELN:
- Prüfe den INHALT, nicht nur den Zeitraum
- Mängelanzeige / Reklamation zu abgeschlossenem Projekt = ALTES Projekt
- Zahlung / Rechnung = gehört zum Projekt das sie ausgelöst hat
- Neue Leistung / anderer Raum / anderes Material = NEUES Projekt
- "Wie besprochen" / "damals" / "vor X Jahren" = Bezug auf altes Projekt

## FRAGE 3: NEUE IDENTITÄT?

Wenn der Absender nicht in den bekannten Identitäten steht,
aber mit hoher Wahrscheinlichkeit ein bekannter Kunde ist:
schlage die neue Identität vor.

---

## ANTWORT — NUR JSON, kein Text

{{
  "kunden_id": null oder integer,
  "kunden_confidence": 0.0 bis 1.0,
  "kunden_confidence_stufe": "eindeutig|wahrscheinlich|pruefen|unklar",
  "kunden_reasoning": "max 2 Sätze warum dieser Kunde",

  "projekt_id": null oder integer,
  "projekt_ist_neu": true oder false,
  "projekt_neuer_name_vorschlag": null oder "Vorgeschlagener Projektname",
  "projekt_confidence": 0.0 bis 1.0,
  "projekt_confidence_stufe": "eindeutig|wahrscheinlich|pruefen|unklar",
  "projekt_reasoning": "max 2 Sätze warum dieses oder neues Projekt",

  "neue_identitaet": {{
    "vorschlagen": true oder false,
    "typ": "mail|telefon|firma|domain",
    "wert": "die neue Identität",
    "confidence": 0.0 bis 1.0,
    "reasoning": "warum diese Identität zu diesem Kunden gehört"
  }},

  "ist_geschaeftsfall": true oder false,
  "fall_typ": "anfrage|angebot|nachfass|rechnung|reklamation|maengel|streitfall|intern|freigabe|allgemein|kein_geschaeftsfall",

  "neue_lernregel": {{
    "erstellen": true oder false,
    "regel_typ": "identitaet|projekt_signal|kanal_muster|ausschluss|projekt_typ",
    "beschreibung": "Was Kira gelernt hat (max 1 Satz)",
    "bedingung_json": {{}},
    "aktion_json": {{}}
  }}
}}"""


def _parse_llm_response(antwort: str) -> dict | None:
    """Parst die LLM-JSON-Antwort (v2 — mit Identitäts- + Projekt-Feldern)."""
    try:
        text = antwort.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        result = json.loads(text)

        valid_stufen = {"eindeutig", "wahrscheinlich", "pruefen", "unklar"}
        valid_fall_typen = {
            "anfrage", "angebot", "nachfass", "rechnung", "reklamation",
            "maengel", "streitfall", "intern", "freigabe", "allgemein",
            "kein_geschaeftsfall",
        }

        # v2: numerische confidence → stufe ableiten (abwärtskompatibel)
        for prefix in ("kunden", "projekt"):
            score_key = f"{prefix}_confidence"
            stufe_key = f"{prefix}_confidence_stufe"
            score = result.get(score_key)
            if isinstance(score, (int, float)):
                # Numerischer Score → Stufe ableiten
                if score >= 0.85:
                    result[stufe_key] = "eindeutig"
                elif score >= 0.60:
                    result[stufe_key] = "wahrscheinlich"
                elif score >= 0.40:
                    result[stufe_key] = "pruefen"
                else:
                    result[stufe_key] = "unklar"
            elif isinstance(score, str) and score in valid_stufen:
                # Alt-Format: String direkt als Stufe
                result[stufe_key] = score
                result[score_key] = _confidence_to_score(score)

            if result.get(stufe_key) not in valid_stufen:
                result[stufe_key] = "unklar"

        # Abwärtskompatibel: kunden_confidence als Stufe-String
        if isinstance(result.get("kunden_confidence"), (int, float)):
            result["kunden_confidence"] = result.get("kunden_confidence_stufe", "unklar")
        if isinstance(result.get("projekt_confidence"), (int, float)):
            result["projekt_confidence"] = result.get("projekt_confidence_stufe", "unklar")

        if result.get("fall_typ") not in valid_fall_typen:
            result["fall_typ"] = "anfrage"

        # Reasoning aus v2-Feldern zusammenbauen
        if not result.get("reasoning"):
            parts = []
            if result.get("kunden_reasoning"):
                parts.append(result["kunden_reasoning"])
            if result.get("projekt_reasoning"):
                parts.append(result["projekt_reasoning"])
            result["reasoning"] = " | ".join(parts) if parts else ""

        return result
    except Exception as e:
        logger.warning("LLM-Response Parse-Fehler: %s — Antwort: %s", e, antwort[:200])
        return None


# ── Haupt-Funktion ───────────────────────────────────────────────────────────

def classify_kunde_projekt(
    absender: str,
    betreff: str = "",
    text: str = "",
    datum: str = None,
    eingabe_typ: str = "mail",
    eingabe_id: str = None,
    headers: dict = None,
) -> dict:
    """
    Klassifiziert eine Aktivität → Kunde + Projekt + Fall-Typ.

    Returns dict mit:
      kunden_id, kunden_confidence, projekt_id, projekt_confidence,
      fall_typ, ist_geschaeftsfall, reasoning, fast_path
    """
    email = _extract_email(absender)
    datum = datum or datetime.now().isoformat(sep=" ", timespec="seconds")

    # 1. Geschäftskontakt-Filter
    if not ist_geschaeftskontakt(absender, betreff, headers):
        result = {
            "kunden_id": None,
            "kunden_confidence": "unklar",
            "projekt_id": None,
            "projekt_confidence": "unklar",
            "fall_typ": "kein_geschaeftsfall",
            "ist_geschaeftsfall": False,
            "fast_path": True,
            "reasoning": "Newsletter/Noreply/Marketing-Absender erkannt",
        }
        _log_classification(eingabe_typ, eingabe_id, result, llm_modell="regel")
        try:
            from runtime_log import elog
            elog("kein_geschaeftsfall", f"Kein Geschäftsfall: {absender[:60]} | {betreff[:40]}")
        except Exception:
            pass
        return result

    # 2. Ignoriert-Check
    if _ist_absender_ignoriert(email):
        result = {
            "kunden_id": None,
            "kunden_confidence": "unklar",
            "projekt_id": None,
            "projekt_confidence": "unklar",
            "fall_typ": "kein_geschaeftsfall",
            "ist_geschaeftsfall": False,
            "fast_path": True,
            "reasoning": "Absender dauerhaft ignoriert",
        }
        _log_classification(eingabe_typ, eingabe_id, result, llm_modell="ignoriert")
        return result

    # 3. Fast-Path
    fp = _fast_path(email)
    if fp:
        _log_classification(eingabe_typ, eingabe_id, fp, llm_modell="fast_path")
        return fp

    # 4. Cache prüfen
    cache_key = hashlib.md5(f"{email}:{betreff}".encode()).hexdigest()
    cached = _CLASSIFY_CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]

    # 5. LLM-Klassifizierung
    try:
        from runtime_log import elog as _elog_cls
        _elog_cls("classifier_aufgerufen", f"LLM-Classifier für {absender[:50]} | {betreff[:40]}")
    except Exception:
        pass
    try:
        from kira_llm import classify_direct, get_providers

        providers = get_providers()
        if not providers:
            logger.warning("Kein LLM-Provider für Kunden-Classifier verfügbar")
            result = _fallback_result(email, "Kein LLM-Provider verfügbar")
            _log_classification(eingabe_typ, eingabe_id, result, llm_modell="fallback")
            return result

        kunden_kontext = _build_kunden_kontext_erweitert()
        lernregeln_kontext = _build_lernregeln_kontext()
        prompt = _build_llm_prompt(absender, betreff, text[:2000], datum,
                                   kunden_kontext, lernregeln_kontext)

        llm_result = classify_direct(prompt, max_tokens=512)

        if llm_result.get("error"):
            logger.warning("LLM-Classifier Fehler: %s", llm_result["error"])
            result = _fallback_result(email, f"LLM-Fehler: {llm_result['error']}")
            _log_classification(eingabe_typ, eingabe_id, result, llm_modell="fallback")
            return result

        antwort = llm_result.get("antwort", "")
        parsed = _parse_llm_response(antwort)

        if not parsed:
            result = _fallback_result(email, "LLM-Response nicht parsbar")
            _log_classification(eingabe_typ, eingabe_id, result, llm_modell="fallback")
            return result

        # IDs als int sicherstellen
        kid = parsed.get("kunden_id")
        pid = parsed.get("projekt_id")
        if isinstance(kid, str) and kid.isdigit():
            kid = int(kid)
        if isinstance(pid, str) and pid.isdigit():
            pid = int(pid)

        result = {
            "kunden_id": kid if isinstance(kid, int) else None,
            "kunden_confidence": parsed.get("kunden_confidence", "unklar"),
            "projekt_id": pid if isinstance(pid, int) else None,
            "projekt_confidence": parsed.get("projekt_confidence", "unklar"),
            "fall_typ": parsed.get("fall_typ", "anfrage"),
            "ist_geschaeftsfall": parsed.get("ist_geschaeftsfall", True),
            "fast_path": False,
            "reasoning": parsed.get("reasoning", ""),
        }

        # Cache speichern
        _CLASSIFY_CACHE[cache_key] = (time.time(), result)

        # Modell-Info
        modell = llm_result.get("provider", "unbekannt")
        if llm_result.get("model"):
            modell = f"{modell}/{llm_result['model']}"
        log_id = _log_classification(eingabe_typ, eingabe_id, result, llm_modell=modell)

        # 6a. v2: Neue Identität vorschlagen
        _process_neue_identitaet(parsed, result, email)

        # 6b. v2: Neues Projekt auto-anlegen (wenn confident genug)
        _process_neues_projekt(parsed, result)

        # 6c. v2: Lernregel aus LLM-Vorschlag speichern
        _process_lernregel(parsed, result)

        # 7. Lead-Flow: unbekannter Absender + Geschäftsfall
        if result.get("kunden_id") is None and result.get("ist_geschaeftsfall"):
            mail_daten = {
                "absender_email": email,
                "absender_name": _extract_name(absender),
                "absender_firma": "",
                "betreff": betreff,
                "mail_id": eingabe_id,
            }
            classifier_ergebnis = {
                "confidence_score": _confidence_to_score(result.get("kunden_confidence", "unklar")),
                "reasoning_kurz": result.get("reasoning", ""),
                "log_id": log_id,
            }
            result = _lead_flow(mail_daten, classifier_ergebnis, result, absender, betreff)

        return result

    except Exception as e:
        logger.error("Kunden-Classifier Ausnahme: %s", e, exc_info=True)
        result = _fallback_result(email, str(e))
        _log_classification(eingabe_typ, eingabe_id, result, llm_modell="error")
        return result


def _fallback_result(email: str, reason: str) -> dict:
    """Erstellt ein Fallback-Ergebnis wenn LLM nicht verfügbar."""
    return {
        "kunden_id": None,
        "kunden_confidence": "unklar",
        "projekt_id": None,
        "projekt_confidence": "unklar",
        "fall_typ": "anfrage",
        "ist_geschaeftsfall": True,
        "fast_path": False,
        "reasoning": f"Fallback: {reason}",
    }


# ── Logging ──────────────────────────────────────────────────────────────────

def _log_classification(eingabe_typ: str, eingabe_id: str, result: dict, llm_modell: str = "") -> int | None:
    """Speichert Klassifizierungsergebnis in kunden_classifier_log. Gibt log_id zurück."""
    try:
        from case_engine import _ensure_crm_tables
        _ensure_crm_tables()

        db = _get_kunden_db()
        cur = db.execute("""
            INSERT INTO kunden_classifier_log
            (eingabe_typ, eingabe_id, kunden_id_vorschlag, projekt_id_vorschlag,
             fall_typ_vorschlag, confidence, reasoning_kurz, llm_modell)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            eingabe_typ,
            eingabe_id,
            result.get("kunden_id"),
            result.get("projekt_id"),
            result.get("fall_typ"),
            result.get("kunden_confidence", "unklar"),
            (result.get("reasoning", "") or "")[:500],
            llm_modell,
        ))
        log_id = cur.lastrowid
        db.commit()
        db.close()
        return log_id
    except Exception as e:
        logger.warning("Classifier-Log Fehler: %s", e)
        return None


# ── Zuordnung ausführen ──────────────────────────────────────────────────────

def apply_classification(eingabe_typ: str, eingabe_id: str, result: dict) -> bool:
    """
    Wendet das Klassifizierungsergebnis an:
    - Erstellt/aktualisiert kunden_aktivitaeten Eintrag
    - Bei 'eindeutig': automatisch zuordnen
    - Bei 'wahrscheinlich': zuordnen + Hinweis
    Returns True wenn auto-zugeordnet.
    """
    if not result.get("ist_geschaeftsfall"):
        return False
    if not result.get("kunden_id"):
        return False

    try:
        from case_engine import _ensure_crm_tables
        _ensure_crm_tables()

        db = _get_kunden_db()
        confidence = result.get("kunden_confidence", "unklar")
        auto = confidence in ("eindeutig", "wahrscheinlich")

        # Aktivitäts-Eintrag erstellen
        db.execute("""
            INSERT INTO kunden_aktivitaeten
            (kunden_id, projekt_id, ereignis_typ, quelle_id, quelle_tabelle,
             zusammenfassung)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            result["kunden_id"],
            result.get("projekt_id"),
            eingabe_typ,
            eingabe_id,
            eingabe_typ,
            result.get("reasoning", "Automatisch zugeordnet"),
        ))

        # Kunden-Kontakt aktualisieren
        db.execute("""
            UPDATE kunden SET letztkontakt = datetime('now'),
                              aktualisiert_am = datetime('now')
            WHERE id = ?
        """, (result["kunden_id"],))

        db.commit()
        db.close()

        # Runtime-Log
        try:
            from runtime_log import elog
            event = "kunde_zugeordnet_auto" if auto else "kunde_zugeordnet_manuell"
            elog(event, f"Kunde {result['kunden_id']} ({confidence}), "
                 f"Projekt {result.get('projekt_id')}, Typ {result.get('fall_typ')}")
        except Exception:
            pass

        return auto
    except Exception as e:
        logger.error("Apply-Classification Fehler: %s", e)
        return False


# ── Manuelle Korrektur ───────────────────────────────────────────────────────

def korrektur_speichern(log_id: int, korrektur_kunden_id: int = None,
                        korrektur_projekt_id: int = None) -> bool:
    """
    Speichert eine manuelle Korrektur und lernt daraus.
    Aktualisiert kunden_classifier_log + ggf. kunden_identitaeten.
    """
    try:
        db = _get_kunden_db()
        db.execute("""
            UPDATE kunden_classifier_log
            SET user_bestaetigt = 1,
                user_korrektur_kunden_id = ?,
                user_korrektur_projekt_id = ?
            WHERE id = ?
        """, (korrektur_kunden_id, korrektur_projekt_id, log_id))

        # Lerneffekt: Absender-Confidence hochstufen
        if korrektur_kunden_id:
            log_row = db.execute(
                "SELECT eingabe_typ, eingabe_id FROM kunden_classifier_log WHERE id = ?",
                (log_id,)
            ).fetchone()

            # Zähle Korrekturen für diesen Kunden
            count = db.execute("""
                SELECT COUNT(*) as c FROM kunden_classifier_log
                WHERE user_korrektur_kunden_id = ? AND user_bestaetigt = 1
            """, (korrektur_kunden_id,)).fetchone()

            if count and count["c"] >= 3:
                # 3+ Korrekturen → Confidence auf 'eindeutig' hochstufen
                db.execute("""
                    UPDATE kunden_identitaeten
                    SET confidence = 'eindeutig'
                    WHERE kunden_id = ? AND confidence != 'eindeutig'
                """, (korrektur_kunden_id,))

        db.commit()
        db.close()

        try:
            from runtime_log import elog
            elog("classifier_korrigiert", f"Log {log_id} → Kunde {korrektur_kunden_id}, Projekt {korrektur_projekt_id}")
        except Exception:
            pass

        return True
    except Exception as e:
        logger.error("Korrektur-Speicherung Fehler: %s", e)
        return False


# ── Prüfliste ────────────────────────────────────────────────────────────────

def get_unzugeordnete(limit: int = 50) -> list[dict]:
    """
    Gibt unzugeordnete/unsichere Klassifizierungen zurück.
    Für die Prüfliste im Aktivitäten-Panel.
    """
    try:
        from case_engine import _ensure_crm_tables
        _ensure_crm_tables()

        db = _get_kunden_db()
        rows = db.execute("""
            SELECT cl.id, cl.eingabe_typ, cl.eingabe_id,
                   cl.kunden_id_vorschlag, cl.projekt_id_vorschlag,
                   cl.fall_typ_vorschlag, cl.confidence,
                   cl.reasoning_kurz, cl.erstellt_am,
                   k.name as kunden_name
            FROM kunden_classifier_log cl
            LEFT JOIN kunden k ON k.id = cl.kunden_id_vorschlag
            WHERE cl.user_bestaetigt = 0
              AND cl.confidence IN ('pruefen', 'unklar')
            ORDER BY cl.erstellt_am DESC
            LIMIT ?
        """, (limit,)).fetchall()
        db.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("Unzugeordnete-Abfrage Fehler: %s", e)
        return []


# ── Hilfsfunktionen ────────────────────────────────────────────────────────

def _extract_name(absender: str) -> str:
    """Extrahiert Name aus 'Vorname Nachname <email>' Format."""
    if "<" in absender:
        name = absender.split("<")[0].strip().strip('"').strip("'")
        if name:
            return name
    return ""


def _confidence_to_score(confidence: str) -> float:
    """Wandelt String-Confidence in numerischen Score."""
    return {"eindeutig": 0.95, "wahrscheinlich": 0.75, "pruefen": 0.50, "unklar": 0.25}.get(confidence, 0.25)


def _get_config() -> dict:
    """Liest config.json."""
    try:
        return json.loads(CONFIG_FILE.read_text("utf-8"))
    except Exception:
        return {}


def _ntfy_push(titel: str, nachricht: str, prioritaet: str = "default"):
    """Sendet ntfy Push-Notification."""
    try:
        from kira_llm import _send_ntfy_push
        _send_ntfy_push(titel, nachricht, prioritaet)
    except Exception as e:
        logger.debug("ntfy Push fehlgeschlagen: %s", e)


# ── Ignoriert-Check ────────────────────────────────────────────────────────

def _ist_absender_ignoriert(email: str) -> bool:
    """Prüft ob Absender oder dessen Domain in kunden_ignoriert steht."""
    try:
        email_lower = email.lower().strip()
        domain = email_lower.split('@')[1] if '@' in email_lower else ''
        db = _get_kunden_db()
        row = db.execute(
            """SELECT id FROM kunden_ignoriert
               WHERE LOWER(absender_email) = ?
                  OR (absender_domain = ? AND absender_domain != '')
               LIMIT 1""",
            (email_lower, domain)
        ).fetchone()
        db.close()
        return row is not None
    except Exception:
        return False


def absender_ignorieren(email: str, grund: str = "manuell") -> bool:
    """Fügt Absender zur Ignoriert-Liste hinzu."""
    try:
        db = _get_kunden_db()
        domain = _extract_domain(email)
        db.execute("""
            INSERT OR IGNORE INTO kunden_ignoriert
                (absender_email, absender_domain, grund, erstellt_am)
            VALUES (?, ?, ?, datetime('now'))
        """, (email.lower(), domain, grund))
        db.commit()
        db.close()
        try:
            from runtime_log import elog
            elog("absender_ignoriert", f"Absender ignoriert: {email} (Grund: {grund})")
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error("Absender-Ignorieren Fehler: %s", e)
        return False


def get_ignorierte(limit: int = 100) -> list[dict]:
    """Gibt Liste der ignorierten Absender zurück."""
    try:
        db = _get_kunden_db()
        rows = db.execute(
            "SELECT id, absender_email, absender_domain, grund, erstellt_am "
            "FROM kunden_ignoriert ORDER BY erstellt_am DESC LIMIT ?",
            (limit,)
        ).fetchall()
        db.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def absender_reaktivieren(email: str) -> bool:
    """Entfernt Absender aus der Ignoriert-Liste."""
    try:
        db = _get_kunden_db()
        db.execute("DELETE FROM kunden_ignoriert WHERE LOWER(absender_email) = ?", (email.lower(),))
        db.commit()
        db.close()
        return True
    except Exception:
        return False


# ── 3-Stufen Lead-Flow ─────────────────────────────────────────────────────

def _lead_flow(mail_daten: dict, classifier_ergebnis: dict,
               original_result: dict, absender: str, betreff: str) -> dict:
    """
    3-Stufen Lead-Flow für unbekannte Absender die ein Geschäftsfall sein könnten.
    Stufe 1: confidence >= Schwelle → automatisch Lead anlegen
    Stufe 2: confidence 0.50-Schwelle → Kai fragen (Aufgabe)
    Stufe 3: kein Geschäftsfall → ignorieren
    """
    cfg = _get_config()
    crm_cfg = cfg.get("crm", {})
    auto_lead_aktiv = crm_cfg.get("auto_lead", True)
    fragen_aktiv = crm_cfg.get("fragen_bei_unsicherheit", True)
    schwelle = crm_cfg.get("lead_schwelle", 0.85)

    score = classifier_ergebnis.get("confidence_score", 0)
    email = mail_daten.get("absender_email", "")
    domain = _extract_domain(email)

    # Zusätzliche Signal-Prüfung
    hat_anfrage_signal = bool(_ANFRAGE_SIGNALE.search(betreff or ""))
    hat_echten_namen = bool(mail_daten.get("absender_name", "").strip())
    ist_individuelle_domain = domain and domain not in _FREEMAIL_DOMAINS and domain not in _MASSEN_DOMAINS

    # Stufe 1: Automatisch Lead anlegen
    if auto_lead_aktiv and score >= schwelle:
        signale_ok = hat_anfrage_signal or (hat_echten_namen and ist_individuelle_domain)
        if signale_ok:
            try:
                kunden_id = _lead_aus_mail_anlegen(mail_daten, classifier_ergebnis)
                original_result["kunden_id"] = kunden_id
                original_result["lead_flow"] = "auto_lead"
                original_result["reasoning"] += " → Automatisch als Lead angelegt"
                try:
                    from runtime_log import elog
                    elog("lead_automatisch_angelegt",
                         f"Auto-Lead: {email} | {betreff[:50]} | Score: {score:.0%}")
                except Exception:
                    pass
                return original_result
            except Exception as e:
                logger.error("Auto-Lead Fehler: %s", e)

    # Stufe 2: Kai fragen
    if fragen_aktiv and score >= 0.50:
        try:
            _lead_bestaetigung_aufgabe(mail_daten, classifier_ergebnis)
            original_result["lead_flow"] = "kai_fragen"
            original_result["reasoning"] += " → Aufgabe für Kai erstellt (Lead-Bestätigung)"
            try:
                from runtime_log import elog
                elog("lead_bestaetigung_aufgabe",
                     f"Kai gefragt: {email} | {betreff[:50]} | Score: {score:.0%}")
            except Exception:
                pass
        except Exception as e:
            logger.error("Lead-Bestätigung Fehler: %s", e)

    return original_result


def _lead_aus_mail_anlegen(mail_daten: dict, classifier_ergebnis: dict) -> int:
    """Legt einen neuen Lead aus einer eingehenden Mail an. Gibt kunden_id zurück."""
    jetzt = datetime.now().isoformat(sep=" ", timespec="seconds")
    email = mail_daten.get("absender_email", "")

    db = _get_kunden_db()
    try:
        # Prüfen ob Absender bereits als Kunde existiert
        existing = db.execute(
            "SELECT id FROM kunden WHERE LOWER(email) = ?", (email.lower(),)
        ).fetchone()
        if existing:
            db.close()
            return existing["id"]

        # 1. Neuen Kunden mit status='lead' anlegen
        cur = db.execute('''
            INSERT INTO kunden
                (name, firmenname, email, kundentyp, status,
                 erstkontakt, letztkontakt, aktualisiert_am, metadata_json)
            VALUES (?, ?, ?, 'unbekannt', 'lead', ?, ?, ?, ?)
        ''', (
            mail_daten.get("absender_name", ""),
            mail_daten.get("absender_firma", ""),
            email,
            jetzt, jetzt, jetzt,
            json.dumps({"quelle": "mail_eingang", "auto_lead": True})
        ))
        kunden_id = cur.lastrowid

        # 2. Mail-Adresse als Identität
        db.execute('''
            INSERT OR IGNORE INTO kunden_identitaeten
                (kunden_id, typ, wert, confidence, verifiziert, quelle, erstellt_am)
            VALUES (?, 'mail', ?, 'wahrscheinlich', 0, 'auto_lead', ?)
        ''', (kunden_id, email.lower(), jetzt))

        # 3. Domain als Identität (wenn keine Freemail)
        domain = _extract_domain(email)
        if domain and domain not in _FREEMAIL_DOMAINS:
            db.execute('''
                INSERT OR IGNORE INTO kunden_identitaeten
                    (kunden_id, typ, wert, confidence, verifiziert, quelle, erstellt_am)
                VALUES (?, 'domain', ?, 'wahrscheinlich', 0, 'auto_lead', ?)
            ''', (kunden_id, domain.lower(), jetzt))

        # 4. Erste Aktivität eintragen (die auslösende Mail)
        db.execute('''
            INSERT INTO kunden_aktivitaeten
                (kunden_id, ereignis_typ, quelle_id, quelle_tabelle,
                 zusammenfassung, erstellt_am, sichtbar_in_verlauf)
            VALUES (?, 'mail', ?, 'mail_index', ?, ?, 1)
        ''', (kunden_id, str(mail_daten.get("mail_id", "")),
              f"Erste Anfrage: {mail_daten.get('betreff', '')[:100]}", jetzt))

        # 5. Aufgabe für Kai
        tasks_db = sqlite3.connect(str(TASKS_DB))
        tasks_db.execute('''
            INSERT INTO tasks (title, body, status, priority, created_at, metadata_json)
            VALUES (?, ?, 'offen', 'hoch', ?, ?)
        ''', (
            f"Neuer Lead: {mail_daten.get('absender_name') or email}",
            f"Kira hat automatisch einen Lead angelegt.\n"
            f"Absender: {email}\n"
            f"Betreff: {mail_daten.get('betreff', '')}\n"
            f"Confidence: {classifier_ergebnis.get('confidence_score', 0):.0%}\n"
            f"Kira-Begründung: {classifier_ergebnis.get('reasoning_kurz', '')}\n\n"
            f"Bitte prüfen und bestätigen:\n"
            f"→ Im CRM unter 'Leads' findest du diesen Kontakt.\n"
            f"→ Du kannst ihn zu 'Kunde' hochstufen oder als 'Kein Geschäftsfall' markieren.",
            jetzt,
            json.dumps({
                "typ": "lead_info",
                "kunden_id": kunden_id,
                "absender_email": email,
            })
        ))
        tasks_db.commit()
        tasks_db.close()

        db.commit()

        # 6. ntfy-Push
        _ntfy_push(
            titel=f"Neuer Lead: {mail_daten.get('absender_name', email)}",
            nachricht=f"Anfrage von {email} — bitte im CRM prüfen",
            prioritaet="default"
        )

        # 7. Nachqualifizierung starten
        cfg = _get_config()
        if cfg.get("crm", {}).get("auto_nachqualifizierung", True):
            _nachqualifizierung_starten(kunden_id)

        return kunden_id
    finally:
        db.close()


def _lead_bestaetigung_aufgabe(mail_daten: dict, classifier_ergebnis: dict):
    """Erstellt eine Aufgabe mit Ja/Nein für Kai (Stufe 2)."""
    jetzt = datetime.now().isoformat(sep=" ", timespec="seconds")
    email = mail_daten.get("absender_email", "")

    tasks_db = sqlite3.connect(str(TASKS_DB))
    tasks_db.execute('''
        INSERT INTO tasks (title, body, status, priority, created_at, metadata_json)
        VALUES (?, ?, 'offen', 'normal', ?, ?)
    ''', (
        f"Ist das ein Geschäftskontakt? {email}",
        f"Kira ist nicht sicher ob diese Mail ein Geschäftsfall ist.\n\n"
        f"Absender: {mail_daten.get('absender_name', '')} <{email}>\n"
        f"Betreff: {mail_daten.get('betreff', '')}\n"
        f"Kira meint: {classifier_ergebnis.get('reasoning_kurz', '')}\n\n"
        f"Was möchtest du tun?\n"
        f"[Ja — Als Lead anlegen] [Nein — Kein Geschäftsfall] [Nie wieder fragen]",
        jetzt,
        json.dumps({
            "typ": "lead_bestaetigung",
            "absender_email": email,
            "absender_name": mail_daten.get("absender_name", ""),
            "mail_id": mail_daten.get("mail_id"),
            "classifier_log_id": classifier_ergebnis.get("log_id"),
        })
    ))
    tasks_db.commit()
    tasks_db.close()

    _ntfy_push(
        titel=f"Lead prüfen: {mail_daten.get('absender_name', email)}",
        nachricht=f"Bitte entscheide: {email} — Geschäftskontakt?",
        prioritaet="low"
    )


def lead_bestaetigen(absender_email: str, mail_id: str = None,
                     ist_lead: bool = True, nie_wieder: bool = False,
                     name: str = "", firma: str = "") -> dict:
    """
    Kai bestätigt oder lehnt einen Lead ab.
    Aufgerufen von POST /api/crm/lead-bestaetigen.
    """
    if nie_wieder:
        absender_ignorieren(absender_email, grund="nie_wieder")
        try:
            from runtime_log import elog
            elog("absender_ignoriert", f"Nie-wieder-fragen: {absender_email}")
        except Exception:
            pass
        return {"ok": True, "aktion": "ignoriert", "message": "Absender wird dauerhaft ignoriert."}

    if not ist_lead:
        try:
            from runtime_log import elog
            elog("lead_bestaetigt_nein", f"Kein Lead: {absender_email}")
        except Exception:
            pass
        return {"ok": True, "aktion": "abgelehnt", "message": "Kein Geschäftsfall — kein Lead angelegt."}

    # Lead anlegen
    mail_daten = {
        "absender_email": absender_email,
        "absender_name": name,
        "absender_firma": firma,
        "betreff": "",
        "mail_id": mail_id or "",
    }
    try:
        kunden_id = _lead_aus_mail_anlegen(mail_daten, {"confidence_score": 0.75, "reasoning_kurz": "Manuell bestätigt"})
        try:
            from runtime_log import elog
            elog("lead_bestaetigt_ja", f"Lead bestätigt: {absender_email} → Kunde {kunden_id}")
        except Exception:
            pass
        return {"ok": True, "aktion": "angelegt", "kunden_id": kunden_id,
                "message": f"Lead angelegt (ID: {kunden_id}). Nachqualifizierung läuft."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def lead_manuell_anlegen(absender_email: str, mail_id: str = None,
                         name: str = "", firma: str = "",
                         status: str = "lead",
                         nachqualifizieren: bool = True) -> dict:
    """
    Legt manuell einen Lead/Kunden aus dem Postfach an.
    Aufgerufen von POST /api/crm/lead-manuell.
    """
    jetzt = datetime.now().isoformat(sep=" ", timespec="seconds")
    email = absender_email.lower().strip()

    db = _get_kunden_db()
    try:
        # Prüfen ob bereits vorhanden
        existing = db.execute(
            "SELECT id FROM kunden WHERE LOWER(email) = ?", (email,)
        ).fetchone()
        if existing:
            db.close()
            return {"ok": False, "error": f"Kontakt mit {email} existiert bereits (ID: {existing['id']})"}

        cur = db.execute('''
            INSERT INTO kunden
                (name, firmenname, email, kundentyp, status,
                 erstkontakt, letztkontakt, aktualisiert_am, metadata_json)
            VALUES (?, ?, ?, 'unbekannt', ?, ?, ?, ?, ?)
        ''', (name, firma, email, status, jetzt, jetzt, jetzt,
              json.dumps({"quelle": "manuell", "mail_id": mail_id})))
        kunden_id = cur.lastrowid

        # Identität
        db.execute('''
            INSERT OR IGNORE INTO kunden_identitaeten
                (kunden_id, typ, wert, confidence, verifiziert, quelle, erstellt_am)
            VALUES (?, 'mail', ?, 'wahrscheinlich', 0, 'manuell', ?)
        ''', (kunden_id, email, jetzt))

        domain = _extract_domain(email)
        if domain and domain not in _FREEMAIL_DOMAINS:
            db.execute('''
                INSERT OR IGNORE INTO kunden_identitaeten
                    (kunden_id, typ, wert, confidence, verifiziert, quelle, erstellt_am)
                VALUES (?, 'domain', ?, 'wahrscheinlich', 0, 'manuell', ?)
            ''', (kunden_id, domain.lower(), jetzt))

        # Mail als erste Aktivität verknüpfen
        if mail_id:
            db.execute('''
                INSERT INTO kunden_aktivitaeten
                    (kunden_id, ereignis_typ, quelle_id, quelle_tabelle,
                     zusammenfassung, erstellt_am, sichtbar_in_verlauf)
                VALUES (?, 'mail', ?, 'mail_index', ?, ?, 1)
            ''', (kunden_id, str(mail_id),
                  f"Manuell zugeordnet", jetzt))

        db.commit()
    finally:
        db.close()

    try:
        from runtime_log import elog
        elog("kunde_erstellt", f"Manuell angelegt: {name or email} (Status: {status})")
    except Exception:
        pass

    # Nachqualifizierung
    if nachqualifizieren:
        _nachqualifizierung_starten(kunden_id)

    return {"ok": True, "kunden_id": kunden_id,
            "message": f"Kontakt angelegt (ID: {kunden_id}).{' Nachqualifizierung läuft.' if nachqualifizieren else ''}"}


# ── Retroaktive Nachqualifizierung ─────────────────────────────────────────

def _nachqualifizierung_starten(kunden_id: int):
    """Startet retroaktive Nachqualifizierung asynchron im Hintergrund."""
    try:
        from runtime_log import elog
        elog("nachqualifizierung_gestartet", f"Kunde {kunden_id}: Hintergrund-Scan startet")
    except Exception:
        pass
    t = threading.Thread(
        target=_nachqualifizierung_ausfuehren,
        args=(kunden_id,),
        daemon=True,
    )
    t.start()
    return t


def nachqualifizierung_manuell(kunden_id: int) -> dict:
    """Startet Nachqualifizierung manuell (API-Aufruf)."""
    db = _get_kunden_db()
    kunde = db.execute("SELECT id, name, firmenname FROM kunden WHERE id = ?", (kunden_id,)).fetchone()
    db.close()
    if not kunde:
        return {"ok": False, "error": f"Kunde {kunden_id} nicht gefunden"}
    _nachqualifizierung_starten(kunden_id)
    return {"ok": True, "message": f"Nachqualifizierung für {kunde['name'] or kunde['firmenname']} gestartet."}


def _nachqualifizierung_ausfuehren(kunden_id: int):
    """Durchsucht alle Quellen nach Aktivitäten des Kunden."""
    try:
        conn = sqlite3.connect(str(KUNDEN_DB))
        conn.row_factory = sqlite3.Row

        kunde = conn.execute("SELECT * FROM kunden WHERE id = ?", (kunden_id,)).fetchone()
        if not kunde:
            conn.close()
            return

        identitaeten = conn.execute(
            "SELECT typ, wert FROM kunden_identitaeten WHERE kunden_id = ?",
            (kunden_id,)
        ).fetchall()

        mail_adressen = [i["wert"].lower() for i in identitaeten if i["typ"] == "mail"]
        domains = [i["wert"].lower() for i in identitaeten if i["typ"] == "domain"]
        firmennamen = []

        if kunde["email"]:
            mail_adressen.append(kunde["email"].lower())
        if kunde["firmenname"]:
            firmennamen.append(kunde["firmenname"].lower())

        mail_adressen = list(set(mail_adressen))
        firmennamen = list(set(filter(None, firmennamen)))

        gefunden_gesamt = 0

        # Quelle 1: Mail-Archiv
        gefunden_gesamt += _scan_mail_archiv(kunden_id, mail_adressen, conn)

        # Quelle 2: Vorgänge / Tasks
        gefunden_gesamt += _scan_tasks(kunden_id, mail_adressen, firmennamen, conn)

        # Quelle 3: Lexware-Belege (wenn lexware_id)
        if kunde["lexware_id"]:
            gefunden_gesamt += _scan_lexware_belege(kunden_id, kunde["lexware_id"], conn)

        # Kunden-Statistiken aktualisieren
        if gefunden_gesamt > 0:
            _update_kunden_stats(kunden_id, conn)

        conn.commit()
        conn.close()

        # Kira-Hinweis
        if gefunden_gesamt > 0:
            try:
                from runtime_log import elog
                elog("nachqualifizierung_abgeschlossen", json.dumps({
                    "kunden_id": kunden_id,
                    "kunden_name": kunde["name"] or kunde["firmenname"],
                    "gefunden": gefunden_gesamt
                }))
            except Exception:
                pass
            if gefunden_gesamt >= 5:
                _ntfy_push(
                    titel=f"Nachqualifizierung: {kunde['name'] or kunde['firmenname']}",
                    nachricht=f"{gefunden_gesamt} historische Aktivitäten gefunden und in Kundenakte eingebaut.",
                    prioritaet="low"
                )
        else:
            try:
                from runtime_log import elog
                elog("nachqualifizierung_abgeschlossen", json.dumps({
                    "kunden_id": kunden_id,
                    "kunden_name": kunde["name"] or kunde["firmenname"],
                    "gefunden": 0
                }))
            except Exception:
                pass

    except Exception as e:
        logger.error("Nachqualifizierung Fehler für Kunde %s: %s", kunden_id, e, exc_info=True)


def _scan_mail_archiv(kunden_id: int, mail_adressen: list, conn) -> int:
    """Sucht im Mail-Archiv nach Mails von/an bekannte Mailadressen."""
    if not mail_adressen:
        return 0
    try:
        mail_conn = sqlite3.connect(str(MAIL_INDEX_DB))
        mail_conn.row_factory = sqlite3.Row

        platzhalter = ",".join(["?" for _ in mail_adressen])
        mails = mail_conn.execute(f'''
            SELECT rowid, von, an, betreff, datum
            FROM mail_index
            WHERE LOWER(von) IN ({platzhalter})
               OR LOWER(an) IN ({platzhalter})
            ORDER BY datum ASC
        ''', mail_adressen + mail_adressen).fetchall()

        mail_conn.close()

        geschrieben = 0
        for mail in mails:
            existiert = conn.execute(
                "SELECT id FROM kunden_aktivitaeten WHERE kunden_id = ? AND quelle_id = ? AND quelle_tabelle = 'mail_index'",
                (kunden_id, str(mail["rowid"]))
            ).fetchone()
            if existiert:
                continue

            conn.execute('''
                INSERT INTO kunden_aktivitaeten
                    (kunden_id, ereignis_typ, quelle_id, quelle_tabelle,
                     zusammenfassung, erstellt_am, sichtbar_in_verlauf)
                VALUES (?, 'mail', ?, 'mail_index', ?, ?, 1)
            ''', (
                kunden_id,
                str(mail["rowid"]),
                f"Mail: {(mail['betreff'] or '')[:100]}",
                mail["datum"] or datetime.now().isoformat(sep=" ", timespec="seconds"),
            ))
            geschrieben += 1

        return geschrieben
    except Exception as e:
        logger.debug("Mail-Archiv-Scan Fehler: %s", e)
        return 0


def _scan_tasks(kunden_id: int, mail_adressen: list, firmennamen: list, conn) -> int:
    """Sucht in Tasks nach Bezug zum Kunden (Absender-Email in title/body)."""
    if not mail_adressen and not firmennamen:
        return 0
    try:
        tasks_conn = sqlite3.connect(str(TASKS_DB))
        tasks_conn.row_factory = sqlite3.Row

        geschrieben = 0
        for addr in mail_adressen[:5]:
            tasks = tasks_conn.execute(
                "SELECT id, title, created_at FROM tasks WHERE LOWER(body) LIKE ? OR LOWER(title) LIKE ? LIMIT 20",
                (f"%{addr}%", f"%{addr}%")
            ).fetchall()
            for t in tasks:
                existiert = conn.execute(
                    "SELECT id FROM kunden_aktivitaeten WHERE kunden_id = ? AND quelle_id = ? AND quelle_tabelle = 'tasks'",
                    (kunden_id, str(t["id"]))
                ).fetchone()
                if existiert:
                    continue
                conn.execute('''
                    INSERT INTO kunden_aktivitaeten
                        (kunden_id, ereignis_typ, quelle_id, quelle_tabelle,
                         zusammenfassung, erstellt_am, sichtbar_in_verlauf)
                    VALUES (?, 'geschaeft', ?, 'tasks', ?, ?, 1)
                ''', (kunden_id, str(t["id"]),
                      f"Aufgabe: {(t['title'] or '')[:100]}",
                      t["created_at"] or datetime.now().isoformat(sep=" ", timespec="seconds")))
                geschrieben += 1

        tasks_conn.close()
        return geschrieben
    except Exception as e:
        logger.debug("Tasks-Scan Fehler: %s", e)
        return 0


def _scan_lexware_belege(kunden_id: int, lexware_id: str, conn) -> int:
    """Sucht Lexware-Belege (Rechnungen, Angebote) in tasks.db/lexware_*."""
    try:
        tasks_conn = sqlite3.connect(str(TASKS_DB))
        tasks_conn.row_factory = sqlite3.Row
        geschrieben = 0

        # Angebote
        for tabelle, typ_name in [("angebote", "Angebot"), ("ausgangsrechnungen", "Rechnung")]:
            try:
                rows = tasks_conn.execute(f"""
                    SELECT id, kontakt_id, titel, datum, betrag
                    FROM {tabelle}
                    WHERE kontakt_id = ?
                    LIMIT 50
                """, (lexware_id,)).fetchall()
            except Exception:
                continue

            for r in rows:
                quelle_id = f"{tabelle}:{r['id']}"
                existiert = conn.execute(
                    "SELECT id FROM kunden_aktivitaeten WHERE kunden_id = ? AND quelle_id = ? AND quelle_tabelle = ?",
                    (kunden_id, quelle_id, tabelle)
                ).fetchone()
                if existiert:
                    continue
                betrag_str = f" — {r['betrag']:.2f}€" if r.get("betrag") else ""
                conn.execute('''
                    INSERT INTO kunden_aktivitaeten
                        (kunden_id, ereignis_typ, quelle_id, quelle_tabelle,
                         zusammenfassung, erstellt_am, sichtbar_in_verlauf)
                    VALUES (?, 'lexware', ?, ?, ?, ?, 1)
                ''', (kunden_id, quelle_id, tabelle,
                      f"{typ_name}: {(r.get('titel') or '')[:80]}{betrag_str}",
                      r.get("datum") or datetime.now().isoformat(sep=" ", timespec="seconds")))
                geschrieben += 1

        tasks_conn.close()
        return geschrieben
    except Exception as e:
        logger.debug("Lexware-Belege-Scan Fehler: %s", e)
        return 0


def _update_kunden_stats(kunden_id: int, conn):
    """Aktualisiert Kunden-Statistiken nach Nachqualifizierung."""
    try:
        stats = conn.execute("""
            SELECT COUNT(*) as anzahl,
                   MIN(erstellt_am) as erstes,
                   MAX(erstellt_am) as letztes
            FROM kunden_aktivitaeten
            WHERE kunden_id = ? AND ereignis_typ = 'mail'
        """, (kunden_id,)).fetchone()
        if stats and stats["anzahl"]:
            conn.execute("""
                UPDATE kunden
                SET anzahl_mails = ?, erstkontakt = ?, letztkontakt = ?,
                    aktualisiert_am = datetime('now')
                WHERE id = ?
            """, (stats["anzahl"], stats["erstes"], stats["letztes"], kunden_id))
    except Exception as e:
        logger.debug("Kunden-Stats Update Fehler: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# v2 — Intelligente Identitäts- und Projektauflösung (session-uu)
# ══════════════════════════════════════════════════════════════════════════════

def _process_neue_identitaet(parsed: dict, result: dict, absender_email: str):
    """Verarbeitet LLM-Vorschlag für neue Identität → kunden_identitaeten + Graph."""
    try:
        ni = parsed.get("neue_identitaet")
        if not ni or not ni.get("vorschlagen"):
            return
        kid = result.get("kunden_id")
        if not kid:
            return
        wert = ni.get("wert", "").strip().lower()
        typ = ni.get("typ", "mail")
        if not wert:
            return
        conf = ni.get("confidence", 0.5)
        stufe = "wahrscheinlich" if conf >= 0.7 else "pruefen"

        db = _get_kunden_db()
        # Duplikat-Check
        exists = db.execute(
            "SELECT id FROM kunden_identitaeten WHERE kunden_id = ? AND LOWER(wert) = ? AND typ = ?",
            (kid, wert, typ)
        ).fetchone()
        if exists:
            db.close()
            return

        # Auto-anlegen wenn Confidence hoch genug (>= 0.85)
        auto = conf >= 0.85
        quelle = "llm" if not auto else "llm"
        db.execute("""
            INSERT INTO kunden_identitaeten (kunden_id, typ, wert, confidence, verifiziert, quelle, erstellt_am)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (kid, typ, wert, "eindeutig" if auto else stufe, 1 if auto else 0, quelle))

        # Graph-Eintrag: Beziehung zwischen Absender-Identität und neuer Identität
        absender_ident = db.execute(
            "SELECT id FROM kunden_identitaeten WHERE kunden_id = ? AND LOWER(wert) = ? LIMIT 1",
            (kid, absender_email.lower())
        ).fetchone()
        neue_ident = db.execute(
            "SELECT id FROM kunden_identitaeten WHERE kunden_id = ? AND LOWER(wert) = ? AND typ = ? LIMIT 1",
            (kid, wert, typ)
        ).fetchone()
        if absender_ident and neue_ident:
            a_id = min(absender_ident["id"], neue_ident["id"])
            b_id = max(absender_ident["id"], neue_ident["id"])
            db.execute("""
                INSERT OR IGNORE INTO kunden_identitaeten_graph
                (identitaet_a_id, identitaet_b_id, confidence, confidence_stufe,
                 reasoning, entschieden_durch, erstellt_am)
                VALUES (?, ?, ?, ?, ?, 'llm', datetime('now'))
            """, (a_id, b_id, conf, stufe, ni.get("reasoning", "")[:200]))

        db.commit()
        db.close()

        event = "identitaet_auto_angelegt" if auto else "identitaet_vorgeschlagen"
        try:
            from runtime_log import elog
            elog(event, f"Identität {typ}:{wert} für Kunde {kid} (Confidence {conf:.2f})")
        except Exception:
            pass
    except Exception as e:
        logger.debug("Neue Identität Verarbeitung: %s", e)


def _process_neues_projekt(parsed: dict, result: dict):
    """Legt neues Projekt an wenn LLM es vorschlägt und Confidence hoch."""
    try:
        if not parsed.get("projekt_ist_neu"):
            return
        kid = result.get("kunden_id")
        if not kid:
            return
        pname = parsed.get("projekt_neuer_name_vorschlag")
        if not pname:
            return
        pconf = parsed.get("projekt_confidence", 0)
        if isinstance(pconf, str):
            pconf = _confidence_to_score(pconf)
        if pconf < 0.70:
            return  # Nur ab wahrscheinlich

        db = _get_kunden_db()
        jetzt = datetime.now().isoformat(sep=" ", timespec="seconds")
        cur = db.execute("""
            INSERT INTO kunden_projekte
            (kunden_id, projektname, projekttyp, status, beginn_am, erstellt_am, aktualisiert_am)
            VALUES (?, ?, 'standard', 'planung', ?, ?, ?)
        """, (kid, pname[:200], jetzt[:10], jetzt, jetzt))
        pid = cur.lastrowid
        result["projekt_id"] = pid
        result["projekt_name"] = pname
        db.commit()
        db.close()

        try:
            from runtime_log import elog
            elog("projekt_auto_angelegt", f"Projekt '{pname}' für Kunde {kid} angelegt (ID {pid})")
        except Exception:
            pass
    except Exception as e:
        logger.debug("Neues Projekt Verarbeitung: %s", e)


def _process_lernregel(parsed: dict, result: dict):
    """Speichert Lernregel wenn LLM eine vorschlägt und Confidence >= 0.90."""
    try:
        lr = parsed.get("neue_lernregel")
        if not lr or not lr.get("erstellen"):
            return
        kid = result.get("kunden_id")
        regel_typ = lr.get("regel_typ", "identitaet")
        valid_typen = {"identitaet", "projekt_signal", "kanal_muster", "ausschluss", "projekt_typ"}
        if regel_typ not in valid_typen:
            return

        bedingung = lr.get("bedingung_json") or {}
        if isinstance(bedingung, str):
            bedingung = json.loads(bedingung)
        bedingung["beschreibung"] = lr.get("beschreibung", "")[:200]

        aktion = lr.get("aktion_json") or {}
        if isinstance(aktion, str):
            aktion = json.loads(aktion)

        db = _get_kunden_db()
        jetzt = datetime.now().isoformat(sep=" ", timespec="seconds")
        db.execute("""
            INSERT INTO kunden_lernregeln
            (kunden_id, regel_typ, bedingung_json, aktion_json, confidence, quelle, erstellt_am)
            VALUES (?, ?, ?, ?, ?, 'llm_schluss', ?)
        """, (kid, regel_typ, json.dumps(bedingung, ensure_ascii=False),
              json.dumps(aktion, ensure_ascii=False), 0.9, jetzt))
        db.commit()
        db.close()

        try:
            from runtime_log import elog
            elog("lernregel_angelegt", f"Lernregel '{regel_typ}' für Kunde {kid}: {lr.get('beschreibung', '')[:80]}")
        except Exception:
            pass
    except Exception as e:
        logger.debug("Lernregel Verarbeitung: %s", e)


# ── apply_classification_v2 — Confidence-basierte Handlungsmatrix ──────────

def apply_classification_v2(eingabe_typ: str, eingabe_id: str, result: dict) -> dict:
    """
    Erweiterte Zuordnung mit Handlungsmatrix:
      >= 0.90: Auto-Zuordnung + Info-Aufgabe (niedrig)
      0.70–0.89: Zuordnung + Kai wird gefragt (Ja/Nein)
      0.50–0.69: Vorschlag in Prüf-Inbox + Aufgabe
      < 0.50: Prüf-Inbox, Kai entscheidet komplett
    """
    if not result.get("ist_geschaeftsfall"):
        return {"aktion": "ignoriert", "auto": False}
    kid = result.get("kunden_id")
    if not kid:
        return {"aktion": "pruef_inbox", "auto": False}

    conf_stufe = result.get("kunden_confidence", "unklar")
    conf_score = _confidence_to_score(conf_stufe)
    # v2-Felder bevorzugen
    if isinstance(result.get("kunden_confidence"), (int, float)):
        conf_score = result["kunden_confidence"]

    try:
        from case_engine import _ensure_crm_tables
        _ensure_crm_tables()
        db = _get_kunden_db()

        # Aktivitäts-Eintrag erstellen
        auto = conf_score >= 0.70
        zusammenfassung = (result.get("reasoning", "") or "")[:300]
        text_auszug = result.get("text_auszug", "")

        # B-3: Sentiment-Analyse
        sent_score = None
        cfg = _get_config()
        try:
            if cfg.get("crm", {}).get("sentiment", True) and text_auszug:
                sent_score = _sentiment_analysieren(text_auszug)
        except Exception:
            pass

        # B-4: Cross-Channel Thread-Linking
        thread_id = None
        try:
            if cfg.get("crm", {}).get("thread_link", True):
                thread_id = _thread_link_erkennen(
                    {"typ": eingabe_typ, "zusammenfassung": zusammenfassung},
                    kid, db)
        except Exception:
            pass

        db.execute("""
            INSERT INTO kunden_aktivitaeten
            (kunden_id, projekt_id, ereignis_typ, quelle_id, quelle_tabelle,
             zusammenfassung, sichtbar_in_verlauf, sentiment_score, thread_id, thread_typ)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """, (kid, result.get("projekt_id"), eingabe_typ, eingabe_id,
              eingabe_typ, zusammenfassung,
              sent_score, thread_id, 'folge' if thread_id else None))

        # B-3: Sentiment-Trend aktualisieren
        if sent_score is not None:
            try:
                _sentiment_trend_berechnen(kid, db)
            except Exception:
                pass

        # Projekt-Zuordnung loggen
        if result.get("projekt_id"):
            _elog_safe("projekt_zugeordnet_auto",
                       f"Aktivität {eingabe_id} → Projekt {result['projekt_id']} (Kunde {kid}, Score {conf_score:.2f})")

        # Kunden-Kontakt aktualisieren
        db.execute("""
            UPDATE kunden SET letztkontakt = datetime('now'),
                              aktualisiert_am = datetime('now')
            WHERE id = ?
        """, (kid,))
        db.commit()
        db.close()

        # Handlungsmatrix
        if conf_score >= 0.90:
            aktion = "auto_zugeordnet"
            _elog_safe("kunde_zugeordnet_auto",
                       f"Kunde {kid} auto-zugeordnet (Score {conf_score:.2f})")
        elif conf_score >= 0.70:
            aktion = "zugeordnet_frage"
            _elog_safe("kunde_zugeordnet_auto",
                       f"Kunde {kid} zugeordnet, Kai wird gefragt (Score {conf_score:.2f})")
        elif conf_score >= 0.50:
            aktion = "vorschlag_pruef_inbox"
            _elog_safe("unzugeordnet_markiert",
                       f"Vorschlag: Kunde {kid} (Score {conf_score:.2f}) → Prüf-Inbox")
        else:
            aktion = "pruef_inbox"
            _elog_safe("unzugeordnet_markiert",
                       f"Unsicher: Kunde {kid} (Score {conf_score:.2f}) → Prüf-Inbox")

        return {"aktion": aktion, "auto": auto, "confidence_score": conf_score}
    except Exception as e:
        logger.error("apply_classification_v2 Fehler: %s", e)
        return {"aktion": "fehler", "auto": False}


def _elog_safe(event: str, summary: str):
    """Wrapper für elog — ignoriert Fehler."""
    try:
        from runtime_log import elog
        elog(event, summary)
    except Exception:
        pass


# ── Projekt-Clustering ─────────────────────────────────────────────────────

PROJEKT_CLUSTERING_PROMPT = """Analysiere diese Aktivitäten eines Handwerksunternehmens
und schlage sinnvolle Projektgruppierungen vor.

BESTEHENDE PROJEKTE:
{bestehende_projekte}

AKTIVITÄTEN OHNE PROJEKTZUORDNUNG (chronologisch):
{aktivitaeten_liste}

CLUSTERING-REGELN:
- Zeitraum allein ist KEIN Kriterium — Inhalt und Kontext zählen
- Mängelanzeige / Reklamation zu altem Projekt = gehört zum ALTEN Projekt
- Neue Leistungsart / anderer Raum / anderes Objekt = neues Projekt
- Zahlungen / Rechnungen gehören zum Projekt das sie ausgelöst hat
- Planungs-Mails vor Projektbeginn gehören zum Projekt das daraus entstand

ANTWORT NUR ALS JSON:
{{
  "projektvorschlaege": [
    {{
      "ist_bestehendes_projekt": true oder false,
      "projekt_id": null oder integer,
      "projektname_neu": null oder "Name für neues Projekt",
      "aktivitaet_ids": [list der zugehörigen Aktivität-IDs],
      "confidence": 0.0 bis 1.0,
      "begruendung": "max 2 Sätze"
    }}
  ]
}}"""


def projekt_clustering(kunden_id: int) -> dict:
    """
    Startet LLM-basiertes Clustering für unzugeordnete Aktivitäten eines Kunden.
    Gibt Vorschläge zurück — Kai muss bestätigen.
    """
    try:
        db = _get_kunden_db()
        # Bestehende Projekte laden
        projekte = db.execute("""
            SELECT id, projektname, status, beginn_am, abschluss_am
            FROM kunden_projekte WHERE kunden_id = ?
            ORDER BY beginn_am DESC
        """, (kunden_id,)).fetchall()

        proj_text = "\n".join(
            f"Projekt #{p['id']}: {p['projektname']} [{p['status']}] "
            f"{(p['beginn_am'] or '')[:10]}–{(p['abschluss_am'] or 'laufend')[:10]}"
            for p in projekte
        ) if projekte else "(Noch keine Projekte)"

        # Unzugeordnete Aktivitäten
        aktivitaeten = db.execute("""
            SELECT id, ereignis_typ, zusammenfassung, erstellt_am
            FROM kunden_aktivitaeten
            WHERE kunden_id = ? AND projekt_id IS NULL
              AND sichtbar_in_verlauf = 1
            ORDER BY erstellt_am ASC
            LIMIT 100
        """, (kunden_id,)).fetchall()
        db.close()

        if not aktivitaeten:
            return {"status": "ok", "vorschlaege": [],
                    "hinweis": "Keine unzugeordneten Aktivitäten"}

        akt_text = "\n".join(
            f"ID {a['id']}: [{a['erstellt_am'][:10]}] {a['ereignis_typ']}: {(a['zusammenfassung'] or '')[:100]}"
            for a in aktivitaeten
        )

        prompt = PROJEKT_CLUSTERING_PROMPT.format(
            bestehende_projekte=proj_text,
            aktivitaeten_liste=akt_text,
        )

        from kira_llm import classify_direct
        llm_result = classify_direct(prompt, max_tokens=1024)
        if llm_result.get("error"):
            return {"status": "fehler", "fehler": llm_result["error"]}

        parsed = _parse_llm_response(llm_result.get("antwort", ""))
        if not parsed:
            return {"status": "fehler", "fehler": "LLM-Antwort nicht parsbar"}

        vorschlaege = parsed.get("projektvorschlaege", [])

        _elog_safe("clustering_gestartet",
                   f"Clustering für Kunde {kunden_id}: {len(vorschlaege)} Vorschläge, "
                   f"{len(aktivitaeten)} Aktivitäten")

        return {"status": "ok", "vorschlaege": vorschlaege}
    except Exception as e:
        logger.error("Projekt-Clustering Fehler: %s", e)
        return {"status": "fehler", "fehler": str(e)}


def clustering_anwenden(kunden_id: int, vorschlag: dict) -> dict:
    """Wendet einen bestätigten Clustering-Vorschlag an."""
    try:
        db = _get_kunden_db()
        jetzt = datetime.now().isoformat(sep=" ", timespec="seconds")

        if vorschlag.get("ist_bestehendes_projekt") and vorschlag.get("projekt_id"):
            pid = vorschlag["projekt_id"]
        elif vorschlag.get("projektname_neu"):
            cur = db.execute("""
                INSERT INTO kunden_projekte
                (kunden_id, projektname, projekttyp, status, beginn_am, erstellt_am, aktualisiert_am)
                VALUES (?, ?, 'standard', 'planung', ?, ?, ?)
            """, (kunden_id, vorschlag["projektname_neu"][:200], jetzt[:10], jetzt, jetzt))
            pid = cur.lastrowid
        else:
            db.close()
            return {"status": "fehler", "fehler": "Kein Projekt angegeben"}

        akt_ids = vorschlag.get("aktivitaet_ids", [])
        updated = 0
        for aid in akt_ids:
            db.execute("""
                UPDATE kunden_aktivitaeten SET projekt_id = ?
                WHERE id = ? AND kunden_id = ?
            """, (pid, aid, kunden_id))
            updated += 1

        db.commit()
        db.close()

        _elog_safe("clustering_vorschlag_bestaetigt",
                   f"Clustering: {updated} Aktivitäten → Projekt {pid} (Kunde {kunden_id})")

        return {"status": "ok", "projekt_id": pid, "zugeordnet": updated}
    except Exception as e:
        logger.error("Clustering-Anwenden Fehler: %s", e)
        return {"status": "fehler", "fehler": str(e)}


# ── Korrektur + Lernschleife ───────────────────────────────────────────────

def korrektur_verarbeiten(aktivitaet_id: int, richtige_kunden_id: int,
                          richtige_projekt_id: int = None,
                          kai_notiz: str = "") -> dict:
    """
    Verarbeitet eine Kai-Korrektur:
    1. Zuordnung in kunden_aktivitaeten korrigieren
    2. Identität auf 'eindeutig' hochstufen
    3. LLM leitet Lernregel ab
    4. Lernregel in kunden_lernregeln speichern
    """
    try:
        db = _get_kunden_db()
        jetzt = datetime.now().isoformat(sep=" ", timespec="seconds")

        # 1. Zuordnung korrigieren
        akt = db.execute(
            "SELECT * FROM kunden_aktivitaeten WHERE id = ?",
            (aktivitaet_id,)
        ).fetchone()
        if not akt:
            db.close()
            return {"status": "fehler", "fehler": "Aktivität nicht gefunden"}

        alter_kunde = akt["kunden_id"]
        altes_projekt = akt["projekt_id"]

        db.execute("""
            UPDATE kunden_aktivitaeten
            SET kunden_id = ?, projekt_id = ?
            WHERE id = ?
        """, (richtige_kunden_id, richtige_projekt_id, aktivitaet_id))

        # 2. Identitäten hochstufen
        db.execute("""
            UPDATE kunden_identitaeten
            SET confidence = 'eindeutig', verifiziert = 1
            WHERE kunden_id = ? AND confidence != 'eindeutig'
        """, (richtige_kunden_id,))

        # 3. Classifier-Log aktualisieren
        if akt["quelle_id"]:
            db.execute("""
                UPDATE kunden_classifier_log
                SET user_bestaetigt = 1,
                    user_korrektur_kunden_id = ?,
                    user_korrektur_projekt_id = ?
                WHERE eingabe_id = ? AND user_bestaetigt = 0
            """, (richtige_kunden_id, richtige_projekt_id, akt["quelle_id"]))

        db.commit()

        # 4. LLM-Lernregel ableiten
        lernregel_result = _lernregel_ableiten(
            db, akt, richtige_kunden_id, richtige_projekt_id, kai_notiz
        )

        db.close()

        _elog_safe("korrektur_gespeichert",
                   f"Korrektur: Akt {aktivitaet_id} → Kunde {richtige_kunden_id} "
                   f"(vorher {alter_kunde}), Projekt {richtige_projekt_id}")
        if richtige_projekt_id:
            _elog_safe("projekt_zugeordnet_manuell",
                       f"Manuelle Zuordnung: Akt {aktivitaet_id} → Projekt {richtige_projekt_id} (durch Kai)")

        return {
            "status": "ok",
            "alter_kunde": alter_kunde,
            "altes_projekt": altes_projekt,
            "lernregel": lernregel_result,
        }
    except Exception as e:
        logger.error("Korrektur Fehler: %s", e)
        return {"status": "fehler", "fehler": str(e)}


def _lernregel_ableiten(conn, aktivitaet: sqlite3.Row, kunden_id: int,
                         projekt_id: int, kai_notiz: str) -> dict | None:
    """Leitet via LLM eine generalisierbare Lernregel aus der Korrektur ab."""
    try:
        # Kunden-Info laden
        kunde = conn.execute("SELECT name, firmenname FROM kunden WHERE id = ?",
                             (kunden_id,)).fetchone()
        kname = (kunde["firmenname"] or kunde["name"] or f"#{kunden_id}") if kunde else f"#{kunden_id}"

        pname = ""
        if projekt_id:
            proj = conn.execute("SELECT projektname FROM kunden_projekte WHERE id = ?",
                                (projekt_id,)).fetchone()
            pname = proj["projektname"] if proj else ""

        prompt = f"""Eine Zuordnung wurde korrigiert.
Aktivität: [{aktivitaet['ereignis_typ']}] {(aktivitaet['zusammenfassung'] or '')[:200]}
Richtige Zuordnung: Kunde {kname}, Projekt {pname or 'keins'}
Kais Notiz: {kai_notiz or '(keine)'}

Was ist das generalisierbare Muster?
Welche Lernregel sollte Kira ableiten?

Antwort als JSON: {{ "regel_typ": "identitaet|projekt_signal|kanal_muster|ausschluss|projekt_typ", "beschreibung": "max 1 Satz", "bedingung_json": {{}}, "aktion_json": {{}} }}"""

        from kira_llm import classify_direct
        llm_result = classify_direct(prompt, max_tokens=300)
        if llm_result.get("error"):
            return None

        parsed = _parse_llm_response(llm_result.get("antwort", ""))
        if not parsed:
            return None

        regel_typ = parsed.get("regel_typ", "identitaet")
        valid_typen = {"identitaet", "projekt_signal", "kanal_muster", "ausschluss", "projekt_typ"}
        if regel_typ not in valid_typen:
            regel_typ = "identitaet"

        bedingung = parsed.get("bedingung_json") or {}
        if isinstance(bedingung, str):
            bedingung = json.loads(bedingung)
        bedingung["beschreibung"] = parsed.get("beschreibung", "")[:200]

        aktion = parsed.get("aktion_json") or {}
        if isinstance(aktion, str):
            aktion = json.loads(aktion)

        jetzt = datetime.now().isoformat(sep=" ", timespec="seconds")
        conn.execute("""
            INSERT INTO kunden_lernregeln
            (kunden_id, regel_typ, bedingung_json, aktion_json, confidence, quelle, erstellt_am)
            VALUES (?, ?, ?, ?, 1.0, 'kai_korrektur', ?)
        """, (kunden_id, regel_typ, json.dumps(bedingung, ensure_ascii=False),
              json.dumps(aktion, ensure_ascii=False), jetzt))
        conn.commit()

        _elog_safe("lernregel_angelegt",
                   f"Lernregel '{regel_typ}' aus Korrektur: {parsed.get('beschreibung', '')[:80]}")

        return {"regel_typ": regel_typ, "beschreibung": parsed.get("beschreibung", "")}
    except Exception as e:
        logger.debug("Lernregel-Ableitung: %s", e)
        return None


# ── Lernregeln-Verwaltung ──────────────────────────────────────────────────

def get_lernregeln(kunden_id: int = None, nur_aktive: bool = True) -> list[dict]:
    """Gibt Lernregeln zurück (optional gefiltert nach Kunde)."""
    try:
        db = _get_kunden_db()
        if not _tabelle_existiert(db, 'kunden_lernregeln'):
            db.close()
            return []
        query = """
            SELECT kl.*, k.name as kunden_name, k.firmenname as kunden_firma
            FROM kunden_lernregeln kl
            LEFT JOIN kunden k ON k.id = kl.kunden_id
            WHERE 1=1
        """
        params = []
        if nur_aktive:
            query += " AND kl.aktiv = 1"
        if kunden_id is not None:
            query += " AND (kl.kunden_id = ? OR kl.kunden_id IS NULL)"
            params.append(kunden_id)
        query += " ORDER BY kl.anwendungen DESC, kl.erstellt_am DESC LIMIT 50"
        rows = db.execute(query, params).fetchall()
        db.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.debug("Lernregeln abrufen: %s", e)
        return []


def lernregel_deaktivieren(regel_id: int) -> bool:
    """Deaktiviert eine Lernregel."""
    try:
        db = _get_kunden_db()
        db.execute("UPDATE kunden_lernregeln SET aktiv = 0 WHERE id = ?", (regel_id,))
        db.commit()
        db.close()
        _elog_safe("lernregel_deaktiviert", f"Lernregel {regel_id} deaktiviert")
        return True
    except Exception as e:
        logger.debug("Lernregel deaktivieren: %s", e)
        return False


# ── Identitäten-Verwaltung ──────────────────────────────────────────────────

def get_identitaeten(kunden_id: int) -> list[dict]:
    """Gibt alle Identitäten eines Kunden zurück inkl. Graph-Info."""
    try:
        db = _get_kunden_db()
        idents = db.execute("""
            SELECT ki.*, k.name as kunden_name
            FROM kunden_identitaeten ki
            JOIN kunden k ON k.id = ki.kunden_id
            WHERE ki.kunden_id = ?
            ORDER BY ki.confidence DESC, ki.erstellt_am ASC
        """, (kunden_id,)).fetchall()

        result = []
        for i in idents:
            d = dict(i)
            # Graph-Verbindungen laden
            graph = db.execute("""
                SELECT g.*, ki2.wert as verbunden_mit, ki2.typ as verbunden_typ
                FROM kunden_identitaeten_graph g
                JOIN kunden_identitaeten ki2 ON
                    (g.identitaet_a_id = ki2.id AND g.identitaet_b_id = ?)
                    OR (g.identitaet_b_id = ki2.id AND g.identitaet_a_id = ?)
                WHERE g.identitaet_a_id = ? OR g.identitaet_b_id = ?
            """, (i["id"], i["id"], i["id"], i["id"])).fetchall()
            d["graph_verbindungen"] = [dict(g) for g in graph]
            result.append(d)

        db.close()
        return result
    except Exception as e:
        logger.debug("Identitäten abrufen: %s", e)
        return []


def identitaet_bestaetigen(graph_id: int, bestaetigt: bool) -> bool:
    """Kai bestätigt oder lehnt eine Identitäts-Verbindung ab."""
    try:
        db = _get_kunden_db()
        jetzt = datetime.now().isoformat(sep=" ", timespec="seconds")
        if bestaetigt:
            db.execute("""
                UPDATE kunden_identitaeten_graph
                SET kai_bestaetigt = 1, kai_abgelehnt = 0,
                    confidence_stufe = 'eindeutig', confidence = 1.0,
                    entschieden_durch = 'kai_manuell', bestaetigt_am = ?
                WHERE id = ?
            """, (jetzt, graph_id))
            _elog_safe("identitaet_bestaetigt", f"Identitäts-Verbindung {graph_id} bestätigt")
        else:
            db.execute("""
                UPDATE kunden_identitaeten_graph
                SET kai_abgelehnt = 1, kai_bestaetigt = 0,
                    entschieden_durch = 'kai_manuell'
                WHERE id = ?
            """, (graph_id,))
            _elog_safe("identitaet_abgelehnt", f"Identitäts-Verbindung {graph_id} abgelehnt")
        db.commit()
        db.close()
        return True
    except Exception as e:
        logger.debug("Identität bestätigen: %s", e)
        return False
