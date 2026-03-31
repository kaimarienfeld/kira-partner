#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KIRA Case Engine Backfill (session-nn)
Migriert bestehende Datensätze (Ausgangsrechnungen, Angebote, Tasks) in Vorgänge.

Aufruf:
  python case_engine_backfill.py --dry-run     # nur anzeigen, nichts schreiben
  python case_engine_backfill.py               # tatsächlich migrieren

Idempotent: bereits migrierte Datensätze (vorgang_id gesetzt) werden übersprungen.
"""
import sys
import argparse
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("backfill")


def _get_db():
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    return db


def _safe_email(raw: str) -> str:
    """Extrahiert E-Mail-Adresse aus 'Name <email>' oder gibt raw zurück."""
    import re
    m = re.search(r'<([^>]+@[^>]+)>', raw or "")
    return m.group(1).lower() if m else (raw or "").strip().lower()


def backfill_ausgangsrechnungen(dry_run: bool = True) -> dict:
    """Erstellt Vorgänge für Ausgangsrechnungen ohne vorgang_id."""
    from case_engine import create_vorgang, link_entity

    db  = _get_db()
    stats = {"geprüft": 0, "erstellt": 0, "übersprungen": 0, "fehler": 0}

    try:
        rows = db.execute("""
            SELECT id, re_nummer, kunde_name, kunde_email, datum,
                   betrag_brutto, status
            FROM ausgangsrechnungen
            WHERE vorgang_id IS NULL OR vorgang_id = 0
            ORDER BY datum ASC
        """).fetchall()
    except Exception as e:
        log.error(f"ausgangsrechnungen Abfrage: {e}")
        db.close()
        return stats

    for r in rows:
        stats["geprüft"] += 1
        email      = _safe_email(r["kunde_email"] or "")
        kunde_name = (r["kunde_name"] or "").strip()
        re_status  = r["status"] or "offen"

        # Vorgang-Status ableiten
        if re_status in ("bezahlt", "storniert"):
            v_status = "abgeschlossen"
        elif re_status == "überfällig":
            v_status = "mahnung_versendet"
        else:
            v_status = "rechnung_gestellt"

        titel = f"RE {r['re_nummer']} – {kunde_name or email or '?'}"
        log.info(f"  {'[DRY]' if dry_run else '[OK]'} Rechnung {r['re_nummer']} → Vorgang ({v_status})")

        if dry_run:
            stats["erstellt"] += 1
            continue

        try:
            vid = create_vorgang(
                typ="rechnung",
                kunden_email=email,
                kunden_name=kunde_name,
                titel=titel[:120],
                quelle="backfill",
                konfidenz=1.0,
                konto=None,
                entscheidungsstufe="A",
            )
            # Status direkt setzen (force, da Backfill)
            from case_engine import update_status
            if v_status != "entwurf":
                update_status(vid, v_status, grund="backfill", actor="system", force=True)

            link_entity(vid, "ausgangsrechnung", str(r["id"]), rolle="zugehoerig")

            # vorgang_id in ausgangsrechnungen setzen
            try:
                db.execute("UPDATE ausgangsrechnungen SET vorgang_id=? WHERE id=?", (vid, r["id"]))
                db.commit()
            except Exception:
                pass

            stats["erstellt"] += 1
        except Exception as e:
            log.error(f"Fehler bei Rechnung {r['re_nummer']}: {e}")
            stats["fehler"] += 1

    db.close()
    return stats


def backfill_angebote(dry_run: bool = True) -> dict:
    """Erstellt Vorgänge für Angebote ohne vorgang_id."""
    from case_engine import create_vorgang, link_entity

    db    = _get_db()
    stats = {"geprüft": 0, "erstellt": 0, "übersprungen": 0, "fehler": 0}

    try:
        rows = db.execute("""
            SELECT id, a_nummer, kunde_name, kunde_email, datum, status
            FROM angebote
            WHERE vorgang_id IS NULL OR vorgang_id = 0
            ORDER BY datum ASC
        """).fetchall()
    except Exception as e:
        log.error(f"angebote Abfrage: {e}")
        db.close()
        return stats

    for r in rows:
        stats["geprüft"] += 1
        email      = _safe_email(r["kunde_email"] or "")
        kunde_name = (r["kunde_name"] or "").strip()
        a_status   = r["status"] or "offen"

        # Vorgang-Status ableiten
        status_map = {
            "offen":         "angebot_versendet",
            "angenommen":    "angenommen",
            "abgelehnt":     "abgelehnt",
            "keine_antwort": "angebot_versendet",
            "abgeschlossen": "abgeschlossen",
        }
        v_status = status_map.get(a_status, "angebot_versendet")

        titel = f"Angebot {r['a_nummer']} – {kunde_name or email or '?'}"
        log.info(f"  {'[DRY]' if dry_run else '[OK]'} Angebot {r['a_nummer']} → Vorgang ({v_status})")

        if dry_run:
            stats["erstellt"] += 1
            continue

        try:
            vid = create_vorgang(
                typ="angebot",
                kunden_email=email,
                kunden_name=kunde_name,
                titel=titel[:120],
                quelle="backfill",
                konfidenz=1.0,
                konto=None,
                entscheidungsstufe="A",
            )
            from case_engine import update_status
            if v_status != "neu_eingang":
                update_status(vid, v_status, grund="backfill", actor="system", force=True)

            link_entity(vid, "angebot", str(r["id"]), rolle="zugehoerig")

            try:
                db.execute("UPDATE angebote SET vorgang_id=? WHERE id=?", (vid, r["id"]))
                db.commit()
            except Exception:
                pass

            stats["erstellt"] += 1
        except Exception as e:
            log.error(f"Fehler bei Angebot {r['a_nummer']}: {e}")
            stats["fehler"] += 1

    db.close()
    return stats


def backfill_tasks(dry_run: bool = True, nur_kategorie: str = None) -> dict:
    """
    Erstellt Vorgänge für offene Tasks ohne vorgang_id.
    Nur Kategorien die einen Vorgang-Typ haben (kein Newsletter etc.).
    """
    from case_engine import create_vorgang, link_entity
    from vorgang_router import KATEGORIE_ZU_VORGANG_TYP

    db    = _get_db()
    stats = {"geprüft": 0, "erstellt": 0, "übersprungen": 0, "fehler": 0}

    try:
        rows = db.execute("""
            SELECT id, kategorie, titel, kunden_email, kunden_name,
                   konto, message_id, betreff, konfidenz
            FROM tasks
            WHERE (vorgang_id IS NULL OR vorgang_id = 0)
              AND status = 'offen'
            ORDER BY id ASC
        """).fetchall()
    except Exception as e:
        log.error(f"tasks Abfrage: {e}")
        db.close()
        return stats

    for r in rows:
        stats["geprüft"] += 1
        kat = r["kategorie"] or ""
        if nur_kategorie and kat != nur_kategorie:
            stats["übersprungen"] += 1
            continue

        vorgang_typ = KATEGORIE_ZU_VORGANG_TYP.get(kat)
        if vorgang_typ is None:
            stats["übersprungen"] += 1
            continue

        email      = _safe_email(r["kunden_email"] or "")
        kunde_name = (r["kunden_name"] or "").strip()
        titel      = (r["titel"] or r["betreff"] or f"Task {r['id']}")[:120]

        log.info(f"  {'[DRY]' if dry_run else '[OK]'} Task {r['id']} ({kat}) → Vorgang {vorgang_typ}")

        if dry_run:
            stats["erstellt"] += 1
            continue

        try:
            # konfidenz normalisieren
            k_raw = r["konfidenz"]
            if isinstance(k_raw, str):
                k = {"hoch": 0.9, "mittel": 0.65, "niedrig": 0.35}.get(k_raw.lower(), 0.65)
            else:
                k = float(k_raw) if k_raw else 0.65

            vid = create_vorgang(
                typ=vorgang_typ,
                kunden_email=email,
                kunden_name=kunde_name,
                titel=titel,
                quelle="backfill",
                konfidenz=k,
                konto=r["konto"],
                entscheidungsstufe="A",
            )
            link_entity(vid, "task", str(r["id"]), rolle="ausloesend")
            if r["message_id"]:
                link_entity(vid, "mail", r["message_id"], rolle="ausloesend")

            # vorgang_id im Task setzen
            from case_engine import update_task_vorgang_id
            update_task_vorgang_id(r["id"], vid)

            stats["erstellt"] += 1
        except Exception as e:
            log.error(f"Fehler bei Task {r['id']}: {e}")
            stats["fehler"] += 1

    db.close()
    return stats


def run_backfill(dry_run: bool = True):
    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"\n{'='*60}")
    print(f"  KIRA Case Engine Backfill — {mode}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    print("1/3 Ausgangsrechnungen ...")
    s1 = backfill_ausgangsrechnungen(dry_run)
    print(f"    -> geprueft={s1['geprüft']}, erstellt={s1['erstellt']}, fehler={s1['fehler']}\n")

    print("2/3 Angebote ...")
    s2 = backfill_angebote(dry_run)
    print(f"    -> geprueft={s2['geprüft']}, erstellt={s2['erstellt']}, fehler={s2['fehler']}\n")

    print("3/3 Tasks (nur vorgangsrelevante Kategorien) ...")
    s3 = backfill_tasks(dry_run)
    print(f"    -> geprueft={s3['geprüft']}, erstellt={s3['erstellt']}, "
          f"uebersprungen={s3['übersprungen']}, fehler={s3['fehler']}\n")

    total = s1['erstellt'] + s2['erstellt'] + s3['erstellt']
    fehler = s1['fehler'] + s2['fehler'] + s3['fehler']
    print(f"{'='*60}")
    print(f"  GESAMT: {total} Vorgaenge {'wuerden erstellt' if dry_run else 'erstellt'}, {fehler} Fehler")
    if dry_run:
        print(f"\n  DRY-RUN -- keine Aenderungen gespeichert.")
        print(f"  Fuer Live-Migration: python case_engine_backfill.py")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KIRA Case Engine Backfill")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Nur anzeigen, nichts schreiben (Standard: False)")
    args = parser.parse_args()
    run_backfill(dry_run=args.dry_run)
