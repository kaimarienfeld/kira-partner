#!/usr/bin/env python3
"""
archiv_cleanup.py — Bereinigt altes Archiv-Material nach konfigurierbarer Frist.

Logik:
- Liest config.json: mail_archiv.bereinigung_frist_tage (default: 90)
- Liest config.json: mail_archiv.geloeschte_bereinigung_aktiv (default: True)
- Durchsucht alle "Gelöschte"-artigen Ordner im Archiv-Dateisystem
- Mails älter als Frist: Kurzprotokoll in tasks.db > geloeschte_protokoll schreiben
- Dann: mail.eml + attachments-Ordner löschen (mail.json bleibt als Metadaten-Rest)
- Dry-Run-Modus: --dry-run zeigt was gelöscht würde, ohne zu löschen

Aufruf:
  python scripts/archiv_cleanup.py
  python scripts/archiv_cleanup.py --dry-run
  python scripts/archiv_cleanup.py --frist 30
"""

import argparse
import json
import logging
import re
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

SCRIPTS_DIR  = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
CONFIG_FILE  = SCRIPTS_DIR / "config.json"
TASKS_DB     = KNOWLEDGE_DIR / "tasks.db"

log = logging.getLogger("archiv_cleanup")

# Ordner-Namen die als "Gelöschte Elemente"-artig gelten
GELOESCHTE_MARKER = [
    "gelöscht", "geloescht", "deleted", "trash", "papierkorb",
    "gelöschte elemente", "deleted messages", "deleted items",
]

def _is_geloeschte_ordner(ordner_name: str) -> bool:
    n = ordner_name.lower()
    return any(m in n for m in GELOESCHTE_MARKER)


def _kurzinhalt(mail_json: dict) -> str:
    """Extrahiert ersten 300 Zeichen des Mail-Textes."""
    text = mail_json.get("text_plain") or mail_json.get("body") or ""
    if not text and mail_json.get("zusammenfassung"):
        text = mail_json["zusammenfassung"]
    return str(text).strip()[:300]


def _protokoll_eintragen(db: sqlite3.Connection, mail_json: dict, konto: str,
                          folder: str, datum_geloescht: str, n_anhaenge: int):
    """Schreibt einen Protokoll-Eintrag für eine bereinigte Mail."""
    db.execute("""
        INSERT INTO geloeschte_protokoll
            (konto, folder, datum_mail, absender, empfaenger, betreff,
             kurzinhalt, datum_geloescht, anhaenge_entfernt, message_id)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        konto,
        folder,
        mail_json.get("datum_iso") or mail_json.get("datum", ""),
        mail_json.get("absender") or mail_json.get("von", ""),
        mail_json.get("empfaenger") or mail_json.get("an", ""),
        mail_json.get("betreff") or mail_json.get("subject", ""),
        _kurzinhalt(mail_json),
        datum_geloescht,
        n_anhaenge,
        mail_json.get("message_id", ""),
    ))


def run_cleanup(frist_tage_override: int = None, dry_run: bool = False) -> dict:
    """Führt die Archiv-Bereinigung durch.

    Returns: dict mit stats (bereinigt, protokoll, fehler, uebersprungen)
    """
    stats = {"bereinigt": 0, "protokoll": 0, "fehler": 0, "uebersprungen": 0,
             "dry_run": dry_run}

    # Config laden
    try:
        cfg = json.loads(CONFIG_FILE.read_text("utf-8"))
    except Exception as e:
        log.error(f"Config nicht lesbar: {e}")
        return stats

    ma = cfg.get("mail_archiv", {})
    if not ma.get("geloeschte_bereinigung_aktiv", True):
        log.info("Archiv-Bereinigung deaktiviert (geloeschte_bereinigung_aktiv=false)")
        return stats

    frist_tage = frist_tage_override or ma.get("bereinigung_frist_tage", 90)
    archiv_pfad = ma.get("pfad", "").strip()
    if not archiv_pfad:
        log.warning("Kein Archiv-Pfad konfiguriert — Bereinigung übersprungen")
        return stats

    archiv_root = Path(archiv_pfad)
    if not archiv_root.exists():
        log.warning(f"Archiv-Pfad nicht gefunden: {archiv_root}")
        return stats

    grenzwert = datetime.now() - timedelta(days=frist_tage)
    datum_geloescht = datetime.now().isoformat()

    log.info(f"Archiv-Bereinigung: Frist={frist_tage}d, Grenzwert={grenzwert.date()}, "
             f"Archiv={archiv_root}, dry_run={dry_run}")

    # DB öffnen
    db = None
    if not dry_run:
        try:
            db = sqlite3.connect(str(TASKS_DB))
            db.execute("""
                CREATE TABLE IF NOT EXISTS geloeschte_protokoll (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    konto TEXT NOT NULL, folder TEXT NOT NULL,
                    datum_mail TEXT, absender TEXT, empfaenger TEXT,
                    betreff TEXT, kurzinhalt TEXT,
                    datum_geloescht TEXT NOT NULL,
                    anhaenge_entfernt INTEGER DEFAULT 0,
                    message_id TEXT
                )
            """)
        except Exception as e:
            log.error(f"DB-Fehler: {e}")
            return stats

    # Archiv-Verzeichnis durchsuchen
    # Struktur: archiv_root / konto_folder / imap_folder / YYYY-MM-DD_betreff_hash8 / mail.json
    for konto_dir in archiv_root.iterdir():
        if not konto_dir.is_dir():
            continue
        konto_name = konto_dir.name

        for ordner_dir in konto_dir.iterdir():
            if not ordner_dir.is_dir():
                continue
            ordner_name = ordner_dir.name

            # Nur Gelöschte-Ordner bereinigen
            if not _is_geloeschte_ordner(ordner_name):
                stats["uebersprungen"] += 1
                continue

            log.info(f"  Prüfe: {konto_name}/{ordner_name}")

            for mail_dir in ordner_dir.iterdir():
                if not mail_dir.is_dir():
                    continue

                json_path = mail_dir / "mail.json"
                eml_path  = mail_dir / "mail.eml"
                att_dir   = mail_dir / "attachments"

                if not json_path.exists():
                    continue

                # Datum aus Ordnername (YYYY-MM-DD_...)
                datum_match = re.match(r"(\d{4}-\d{2}-\d{2})", mail_dir.name)
                if datum_match:
                    try:
                        mail_datum = datetime.strptime(datum_match.group(1), "%Y-%m-%d")
                    except ValueError:
                        mail_datum = datetime.fromtimestamp(json_path.stat().st_mtime)
                else:
                    mail_datum = datetime.fromtimestamp(json_path.stat().st_mtime)

                if mail_datum >= grenzwert:
                    continue  # Noch nicht fällig

                # Mail-Metadaten laden
                try:
                    mail_json = json.loads(json_path.read_text("utf-8", errors="replace"))
                except Exception:
                    mail_json = {}

                # Anhänge zählen
                n_anhaenge = 0
                if att_dir.exists():
                    n_anhaenge = sum(1 for f in att_dir.iterdir() if f.is_file())

                log.info(f"    Bereinige: {mail_dir.name} (Datum: {mail_datum.date()}, "
                         f"Anhänge: {n_anhaenge})")

                if dry_run:
                    stats["bereinigt"] += 1
                    stats["protokoll"] += 1
                    continue

                # Protokoll-Eintrag schreiben
                try:
                    _protokoll_eintragen(
                        db, mail_json,
                        konto=konto_name,
                        folder=ordner_name,
                        datum_geloescht=datum_geloescht,
                        n_anhaenge=n_anhaenge,
                    )
                    db.commit()
                    stats["protokoll"] += 1
                except Exception as e:
                    log.error(f"    Protokoll-Fehler: {e}")
                    stats["fehler"] += 1
                    continue

                # Dateien löschen
                try:
                    if eml_path.exists():
                        eml_path.unlink()
                    if att_dir.exists():
                        shutil.rmtree(att_dir, ignore_errors=True)
                    # mail.json bleibt als Metadaten-Stub
                    stats["bereinigt"] += 1
                except Exception as e:
                    log.error(f"    Lösch-Fehler: {e}")
                    stats["fehler"] += 1

    if db:
        db.close()

    log.info(f"Bereinigung abgeschlossen: {stats}")
    return stats


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Kira Archiv-Bereinigung")
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur anzeigen was gelöscht würde — keine Änderungen")
    parser.add_argument("--frist", type=int, default=None,
                        help="Frist in Tagen (überschreibt config.json)")
    args = parser.parse_args()

    stats = run_cleanup(frist_tage_override=args.frist, dry_run=args.dry_run)

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Ergebnis:")
    print(f"  Mails bereinigt: {stats['bereinigt']}")
    print(f"  Protokoll-Eintraege: {stats['protokoll']}")
    print(f"  Fehler: {stats['fehler']}")
    print(f"  Ordner uebersprungen (kein Geloeschte-Ordner): {stats['uebersprungen']}")


if __name__ == "__main__":
    main()
