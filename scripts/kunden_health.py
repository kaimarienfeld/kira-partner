"""
kunden_health.py — Customer Health Score für KIRA CRM
Berechnet täglich einen zusammengesetzten Score pro Kunde (0.0–1.0).
Unter 0.35 = Warnung → Kira-Aufgabe.

Stand: 2026-04-11 (session-vv)
"""
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).resolve().parent
KUNDEN_DB = SCRIPTS_DIR.parent / "knowledge" / "kunden.db"
TASKS_DB = SCRIPTS_DIR.parent / "knowledge" / "tasks.db"


def _get_kunden_db():
    db = sqlite3.connect(str(KUNDEN_DB))
    db.row_factory = sqlite3.Row
    return db


def berechne_health_score(kunden_id: int, conn=None) -> dict:
    """
    Zusammengesetzter Score aus 5 Faktoren (je 0.0 bis 1.0).
    Höher = gesunder Kunde. Unter 0.35 = Warnung.
    """
    close_conn = False
    if conn is None:
        conn = _get_kunden_db()
        close_conn = True

    try:
        heute = datetime.now()
        kunde = conn.execute("SELECT * FROM kunden WHERE id = ?", (kunden_id,)).fetchone()
        if not kunde:
            return {"score": 0.0, "detail": {"fehler": "Kunde nicht gefunden"}}

        # Faktor 1: Letzter Kontakt (je älter desto schlechter)
        letzte_akt = conn.execute("""
            SELECT MAX(erstellt_am) FROM kunden_aktivitaeten
            WHERE kunden_id = ? AND sichtbar_in_verlauf = 1
        """, (kunden_id,)).fetchone()[0]

        tage_seit_kontakt = 999
        if letzte_akt:
            try:
                tage_seit_kontakt = (heute - datetime.fromisoformat(
                    letzte_akt.replace("Z", "+00:00").split("+")[0]
                )).days
            except Exception:
                pass
            f_kontakt = max(0.0, 1.0 - (tage_seit_kontakt / 180))
        else:
            f_kontakt = 0.0

        # Faktor 2: Zahlungsverhalten (aus Lexware-Sync)
        f_zahlung = float(kunde["zahlungsverhalten_score"] or 0.5)

        # Faktor 3: Offene Reklamationen / Streitfälle
        offene_probleme = conn.execute("""
            SELECT COUNT(*) FROM kunden_faelle
            WHERE kunden_id = ?
              AND fall_typ IN ('reklamation', 'maengel', 'streitfall')
              AND status NOT IN ('geloest', 'geschlossen', 'archiv')
        """, (kunden_id,)).fetchone()[0]
        f_probleme = max(0.0, 1.0 - (offene_probleme * 0.3))

        # Faktor 4: Projektaktivität (laufende Projekte = positiv)
        aktive_projekte = conn.execute("""
            SELECT COUNT(*) FROM kunden_projekte
            WHERE kunden_id = ? AND status = 'aktiv'
        """, (kunden_id,)).fetchone()[0]
        f_projekte = min(1.0, aktive_projekte * 0.5)

        # Faktor 5: Risiko-Score (invertiert)
        f_risiko = 1.0 - float(kunde["risiko_score"] or 0.3)

        # Gewichteter Gesamtscore
        health_score = (
            f_kontakt * 0.35 +
            f_zahlung * 0.25 +
            f_probleme * 0.20 +
            f_projekte * 0.10 +
            f_risiko * 0.10
        )

        detail = {
            "letzter_kontakt_tage": tage_seit_kontakt,
            "f_kontakt": round(f_kontakt, 2),
            "f_zahlung": round(f_zahlung, 2),
            "f_probleme": round(f_probleme, 2),
            "f_projekte": round(f_projekte, 2),
            "f_risiko": round(f_risiko, 2),
            "offene_probleme": offene_probleme,
            "aktive_projekte": aktive_projekte,
        }

        # Warnung erzeugen wenn Score kritisch
        if health_score < 0.35:
            _health_warnung_erzeugen(kunden_id, health_score, detail, conn)

        conn.execute("""
            UPDATE kunden SET
                health_score = ?,
                health_score_detail_json = ?,
                health_score_berechnet_am = ?,
                letzte_aktivitaet_am = ?
            WHERE id = ?
        """, (round(health_score, 3), json.dumps(detail),
              heute.isoformat(), letzte_akt, kunden_id))
        conn.commit()

        return {"score": round(health_score, 3), "detail": detail}
    except Exception as e:
        logger.error("Health-Score Berechnung Fehler (Kunde %s): %s", kunden_id, e)
        return {"score": 0.0, "detail": {"fehler": str(e)}}
    finally:
        if close_conn:
            conn.close()


def _health_warnung_erzeugen(kunden_id: int, score: float, detail: dict, conn):
    """Erstellt Kira-Aufgabe wenn Health-Score kritisch."""
    kunde = conn.execute(
        "SELECT name, firmenname FROM kunden WHERE id = ?", (kunden_id,)
    ).fetchone()
    kunden_name = (kunde["firmenname"] or kunde["name"] or f"Kunde #{kunden_id}") if kunde else f"Kunde #{kunden_id}"

    # Prüfen ob bereits kürzlich gewarnt (nicht jeden Tag)
    try:
        tdb = sqlite3.connect(str(TASKS_DB))
        tdb.row_factory = sqlite3.Row
        letzte_warnung = tdb.execute("""
            SELECT MAX(created_at) FROM tasks
            WHERE title LIKE ? AND created_at > ?
        """, (
            f"%Health-Warnung%{kunden_id}%",
            (datetime.now() - timedelta(days=14)).isoformat()
        )).fetchone()[0]

        if letzte_warnung:
            tdb.close()
            return  # Nicht doppelt warnen

        grund = []
        if detail.get("letzter_kontakt_tage", 0) > 60:
            grund.append(f"Kein Kontakt seit {detail['letzter_kontakt_tage']} Tagen")
        if detail.get("offene_probleme", 0) > 0:
            grund.append(f"{detail['offene_probleme']} offene Reklamationen/Streitfälle")
        if detail.get("f_zahlung", 1) < 0.4:
            grund.append("Schlechtes Zahlungsverhalten")

        tdb.execute("""
            INSERT INTO tasks (title, body, status, priority, created_at)
            VALUES (?, ?, 'offen', 'normal', ?)
        """, (
            f"Health-Warnung Kunde #{kunden_id}: {kunden_name}",
            f"Kira hat einen niedrigen Health-Score ({score:.0%}) festgestellt.\n\n"
            f"Gründe:\n" + "\n".join([f"• {g}" for g in grund]) + "\n\n"
            f"Empfehlung: Kontakt aufnehmen oder offene Probleme klären.",
            datetime.now().isoformat()
        ))
        tdb.commit()
        tdb.close()

        try:
            from runtime_log import elog
            elog("health_warnung_erzeugt", f"Kunde {kunden_id} ({kunden_name}): Score {score:.0%}")
        except Exception:
            pass
    except Exception as e:
        logger.error("Health-Warnung Fehler: %s", e)


def berechne_alle_health_scores() -> dict:
    """Berechnet Health-Score für alle aktiven Kunden. Für täglichen Batch."""
    conn = _get_kunden_db()
    try:
        kunden_ids = [r[0] for r in conn.execute(
            "SELECT id FROM kunden WHERE status = 'aktiv'"
        ).fetchall()]
        ergebnisse = {"berechnet": 0, "warnungen": 0, "fehler": 0}
        for kid in kunden_ids:
            result = berechne_health_score(kid, conn)
            if result.get("score", 0) < 0.35:
                ergebnisse["warnungen"] += 1
            if "fehler" in result.get("detail", {}):
                ergebnisse["fehler"] += 1
            else:
                ergebnisse["berechnet"] += 1
        return ergebnisse
    except Exception as e:
        logger.error("Batch Health-Score Fehler: %s", e)
        return {"berechnet": 0, "fehler": 1}
    finally:
        conn.close()
