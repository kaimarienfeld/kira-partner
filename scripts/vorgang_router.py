#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KIRA Vorgang-Router (session-nn)
Routing-Layer zwischen Mail-Klassifizierung und Case Engine.

route_classified_mail():
  1. Klassifiziertes Mail → Vorgang-Typ ableiten
  2. Offenen Vorgang suchen (find_open_vorgang) oder neuen anlegen
  3. Task + Mail verknüpfen
  4. Entscheidungsstufe A/B/C bestimmen
  5. Signal erzeugen (bei B/C)
  6. Routing-Ergebnis zurückgeben

Der Router ändert nie die Task-Erstellung selbst — er arbeitet
nach dem Task-Insert als additive Schicht.
"""
import sqlite3, logging
from pathlib import Path
from datetime import datetime

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"

log = logging.getLogger("vorgang_router")

try:
    from case_engine import (
        create_vorgang, find_open_vorgang, link_entity,
        classify_decision_level, create_signal, update_task_vorgang_id,
        get_valid_transitions, INITIAL_STATUS,
    )
    _CE_AVAILABLE = True
except ImportError as _e:
    _CE_AVAILABLE = False
    log.error(f"case_engine nicht verfügbar: {_e}")

# ── Kategorie → Vorgang-Typ Mapping ──────────────────────────────────────────
# None = kein Vorgang anlegen (Stufe A, still verarbeiten)
KATEGORIE_ZU_VORGANG_TYP: dict[str, str | None] = {
    "Neue Lead-Anfrage":     "lead",
    "Angebotsrueckmeldung":  "angebot",
    "Antwort erforderlich":  "anfrage",
    "Angebotsrückmeldung":   "angebot",      # beide Schreibweisen abdecken
    "Rechnung / Beleg":      "rechnung",
    "Eingangsrechnung":      "eingangsrechnung",
    "Termin / Frist":        "termin",
    "Mahnung":               "mahnung",
    "Zahlung":               "zahlung",
    "Zur Kenntnis":          None,   # kein Vorgang
    "Newsletter / Werbung":  None,   # kein Vorgang
    "Shop / System":         None,   # kein Vorgang
    "Abgeschlossen":         None,   # kein Vorgang
    "Ignorieren":            None,   # kein Vorgang
}

def _kategorie_zu_vorgang_typ(kategorie: str) -> str | None:
    """Gibt den Vorgang-Typ für eine Kategorie zurück, oder None."""
    return KATEGORIE_ZU_VORGANG_TYP.get(kategorie)

def _konfidenz_float(konfidenz_raw) -> float:
    """Normalisiert Konfidenz-Wert auf 0.0–1.0."""
    if isinstance(konfidenz_raw, float):
        return max(0.0, min(1.0, konfidenz_raw))
    if isinstance(konfidenz_raw, str):
        mapping = {"hoch": 0.9, "mittel": 0.65, "niedrig": 0.35}
        return mapping.get(konfidenz_raw.lower(), 0.65)
    if isinstance(konfidenz_raw, int):
        return max(0.0, min(1.0, konfidenz_raw / 100.0))
    return 0.65


def route_classified_mail(
    task_id: int,
    classification_result: dict,
    mail_message_id: str = None,
    kunden_email: str = None,
    kunden_name: str = None,
    konto: str = None,
    betreff: str = None,
) -> dict:
    """
    Hauptfunktion: Ordnet eine klassifizierte Mail einem Vorgang zu.

    Args:
        task_id: ID des gerade erstellten Tasks in tasks.db
        classification_result: Rückgabe von classify_mail()
        mail_message_id: Message-ID der Mail (für Verknüpfung)
        kunden_email: E-Mail-Adresse des Absenders
        kunden_name: Name des Absenders
        konto: KIRA-Konto (z.B. "anfrage")
        betreff: Betreff der Mail

    Returns:
        {
          "vorgang_id": int | None,
          "vorgang_neu": bool,
          "stufe": "A" | "B" | "C",
          "signal_id": int,
          "vorgang_typ": str | None,
          "aktion": str,   # "vorgang_erstellt" | "vorgang_verknuepft" | "uebersprungen"
        }
    """
    result = {
        "vorgang_id": None,
        "vorgang_neu": False,
        "stufe": "A",
        "signal_id": 0,
        "vorgang_typ": None,
        "aktion": "uebersprungen",
    }

    if not _CE_AVAILABLE:
        return result

    try:
        kategorie     = classification_result.get("kategorie", "")
        konfidenz_raw = classification_result.get("konfidenz", "mittel")
        zusammenfassung = classification_result.get("zusammenfassung", betreff or "")
        konfidenz     = _konfidenz_float(konfidenz_raw)

        vorgang_typ = _kategorie_zu_vorgang_typ(kategorie)

        if vorgang_typ is None:
            # Kein Vorgang nötig (Newsletter, Zur Kenntnis etc.) → Stufe A
            result["stufe"] = "A"
            result["aktion"] = "uebersprungen"
            return result

        result["vorgang_typ"] = vorgang_typ

        # Ist-Bekannter-Kunde prüfen (hat schon Tasks oder Vorgänge)
        ist_bekannter_kunde = False
        if kunden_email:
            try:
                db = sqlite3.connect(str(TASKS_DB))
                row = db.execute(
                    "SELECT COUNT(*) as cnt FROM vorgaenge WHERE LOWER(kunden_email)=?",
                    (kunden_email.lower(),)
                ).fetchone()
                ist_bekannter_kunde = (row[0] > 0) if row else False
                db.close()
            except Exception:
                pass

        # Offenen Vorgang suchen
        offener_vorgang_id = find_open_vorgang(kunden_email, vorgang_typ)
        hat_offenen_vorgang = offener_vorgang_id is not None

        # Entscheidungsstufe bestimmen
        stufe = classify_decision_level(
            konfidenz=konfidenz,
            kategorie=kategorie,
            vorgang_typ=vorgang_typ,
            ist_bekannter_kunde=ist_bekannter_kunde,
            hat_offenen_vorgang=hat_offenen_vorgang,
        )

        # Vorgang anlegen oder bestehenden verwenden
        if offener_vorgang_id:
            vorgang_id = offener_vorgang_id
            result["vorgang_neu"] = False
            result["aktion"] = "vorgang_verknuepft"
        else:
            titel = (betreff or zusammenfassung or f"{vorgang_typ.capitalize()}")[:120]
            vorgang_id = create_vorgang(
                typ=vorgang_typ,
                kunden_email=kunden_email,
                kunden_name=kunden_name,
                titel=titel,
                quelle="mail",
                konfidenz=konfidenz,
                konto=konto,
                entscheidungsstufe=stufe,
            )
            result["vorgang_neu"] = True
            result["aktion"] = "vorgang_erstellt"

        result["vorgang_id"] = vorgang_id
        result["stufe"] = stufe

        # Task verknüpfen
        if task_id:
            link_entity(vorgang_id, "task", str(task_id), rolle="ausloesend" if result["vorgang_neu"] else "folgend")
            update_task_vorgang_id(task_id, vorgang_id)

        # Mail verknüpfen
        if mail_message_id:
            link_entity(vorgang_id, "mail", mail_message_id, rolle="ausloesend" if result["vorgang_neu"] else "folgend")

        # Signal für Stufe B oder C erzeugen
        if stufe in ("B", "C"):
            aktion_text = "Neuer Vorgang angelegt" if result["vorgang_neu"] else "Bestehender Vorgang aktualisiert"
            signal_titel = f"{vorgang_typ.upper()} — {kategorie}"
            signal_nachricht = (
                f"{aktion_text}: {titel if result['vorgang_neu'] else ''}\n"
                f"Absender: {kunden_name or kunden_email or '?'}\n"
                f"Konfidenz: {int(konfidenz * 100)}%"
            )
            payload = {
                "vorgang_id": vorgang_id,
                "vorgang_typ": vorgang_typ,
                "task_id": task_id,
                "kategorie": kategorie,
                "konfidenz": konfidenz,
                "ist_neu": result["vorgang_neu"],
            }
            signal_id = create_signal(
                stufe=stufe,
                titel=signal_titel,
                nachricht=signal_nachricht,
                vorgang_id=vorgang_id,
                typ=vorgang_typ,
                payload=payload,
            )
            result["signal_id"] = signal_id

        return result

    except Exception as e:
        log.error(f"route_classified_mail Fehler: {e}", exc_info=True)
        result["aktion"] = f"fehler: {e}"
        return result


def route_status_update(
    vorgang_id: int,
    neuer_status: str,
    actor: str = "kai",
    grund: str = "",
) -> bool:
    """
    Leitet einen Statusübergang an die Case Engine weiter.
    Gibt True zurück wenn erfolgreich.
    """
    if not _CE_AVAILABLE:
        return False
    try:
        from case_engine import update_status
        return update_status(vorgang_id, neuer_status, grund=grund, actor=actor)
    except Exception as e:
        log.error(f"route_status_update Fehler: {e}")
        return False
