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
import json, logging, re, sqlite3, hashlib, time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("kunden_classifier")

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
KUNDEN_DB     = KNOWLEDGE_DIR / "kunden.db"

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
    Returns Zuordnungsergebnis oder None wenn LLM nötig.
    """
    try:
        db = _get_kunden_db()
        row = db.execute("""
            SELECT ki.kunden_id, ki.confidence, k.name, k.firmenname
            FROM kunden_identitaeten ki
            JOIN kunden k ON k.id = ki.kunden_id
            WHERE LOWER(ki.wert) = ? AND ki.typ = 'mail'
            ORDER BY CASE ki.confidence
                WHEN 'eindeutig' THEN 1
                WHEN 'wahrscheinlich' THEN 2
                WHEN 'pruefen' THEN 3
                ELSE 4
            END
            LIMIT 1
        """, (absender_email.lower(),)).fetchone()

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
    """Baut kompakten Kunden-Kontext für den Super-Prompt."""
    try:
        db = _get_kunden_db()
        kunden = db.execute("""
            SELECT k.id, k.name, k.firmenname, k.email, k.kundentyp, k.status,
                   k.letztkontakt
            FROM kunden k
            WHERE k.status != 'archiv'
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


def _build_llm_prompt(absender: str, betreff: str, text_auszug: str,
                      datum: str, kunden_kontext: str) -> str:
    """Baut den Super-Prompt für den Kunden-Classifier."""
    return f"""Du bist ein Geschäftsprozess-Klassifizierer für ein Handwerksunternehmen (Sichtbeton/Betonkosmetik).

Analysiere diese neue Nachricht und beantworte NUR als JSON:

{{
  "kunden_id": null oder ID (z.B. 42),
  "kunden_confidence": "eindeutig|wahrscheinlich|pruefen|unklar",
  "projekt_id": null oder ID,
  "projekt_confidence": "eindeutig|wahrscheinlich|pruefen|unklar",
  "fall_typ": "anfrage|angebot|nachfass|rechnung|reklamation|maengel|streitfall|intern|freigabe|kein_geschaeftsfall",
  "ist_geschaeftsfall": true oder false,
  "reasoning": "max 2 Sätze warum"
}}

Bekannte Kunden und Projekte:
{kunden_kontext}

Neue Nachricht:
Absender: {absender}
Betreff: {betreff}
Datum: {datum}
Inhalt (Auszug):
{text_auszug[:2000]}

Wichtige Regeln:
- Mängelanzeigen gehören zum ABGESCHLOSSENEN Projekt, nicht zu einem neuen
- Newsletter, Automails, Marketing → ist_geschaeftsfall = false
- Wenn Absender eine bekannte Kunden-E-Mail ist → kunden_confidence = "eindeutig"
- Zeitlicher Abstand beachten: Mail 2 Jahre nach Projektabschluss = Nachprojekt-Fall
- Nie zwei verschiedene Projekte zusammenmischen
- Bei komplett unbekanntem Absender → kunden_id = null, kunden_confidence = "unklar"
- Antworte NUR mit dem JSON-Objekt, kein anderer Text"""


def _parse_llm_response(antwort: str) -> dict | None:
    """Parst die LLM-JSON-Antwort."""
    try:
        # JSON aus der Antwort extrahieren
        text = antwort.strip()
        # Markdown Code-Block entfernen
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)
        # Erstes { ... } finden
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        result = json.loads(text)

        # Validierung
        valid_confidence = {"eindeutig", "wahrscheinlich", "pruefen", "unklar"}
        valid_fall_typen = {
            "anfrage", "angebot", "nachfass", "rechnung", "reklamation",
            "maengel", "streitfall", "intern", "freigabe", "kein_geschaeftsfall",
        }

        if result.get("kunden_confidence") not in valid_confidence:
            result["kunden_confidence"] = "unklar"
        if result.get("projekt_confidence") not in valid_confidence:
            result["projekt_confidence"] = "unklar"
        if result.get("fall_typ") not in valid_fall_typen:
            result["fall_typ"] = "anfrage"

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

    # 2. Fast-Path
    fp = _fast_path(email)
    if fp:
        _log_classification(eingabe_typ, eingabe_id, fp, llm_modell="fast_path")
        return fp

    # 3. Cache prüfen
    cache_key = hashlib.md5(f"{email}:{betreff}".encode()).hexdigest()
    cached = _CLASSIFY_CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]

    # 4. LLM-Klassifizierung
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

        kunden_kontext = _build_kunden_kontext(max_kunden=50)
        prompt = _build_llm_prompt(absender, betreff, text[:2000], datum, kunden_kontext)

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
        _log_classification(eingabe_typ, eingabe_id, result, llm_modell=modell)

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

def _log_classification(eingabe_typ: str, eingabe_id: str, result: dict, llm_modell: str = ""):
    """Speichert Klassifizierungsergebnis in kunden_classifier_log."""
    try:
        from case_engine import _ensure_crm_tables
        _ensure_crm_tables()

        db = _get_kunden_db()
        db.execute("""
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
        db.commit()
        db.close()
    except Exception as e:
        logger.warning("Classifier-Log Fehler: %s", e)


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
