#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rauMKult® Reklassifizierung bestehender Tasks
Wendet den aktuellen Classifier (inkl. aller Punkte 6-18) auf vorhandene Tasks an.
"""
import sqlite3, sys
from pathlib import Path
from datetime import datetime

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"

sys.path.insert(0, str(SCRIPTS_DIR))
from llm_classifier import classify_mail_llm, kategorie_to_task_typ

def reclassify_all(dry_run: bool = False, limit: int = 0):
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row

    query = """
        SELECT id, kunden_email, betreff, beschreibung, datum_mail, konto
        FROM tasks
        WHERE beschreibung IS NOT NULL AND beschreibung != ''
        ORDER BY id DESC
    """
    if limit:
        query += f" LIMIT {limit}"

    rows = db.execute(query).fetchall()
    print(f"[reclassify] {len(rows)} Tasks gefunden")

    updated = 0
    skipped = 0

    for row in rows:
        task_id   = row["id"]
        k_email   = row["kunden_email"] or ""
        betreff   = row["betreff"] or ""
        text      = row["beschreibung"] or ""
        datum     = row["datum_mail"] or ""
        konto     = row["konto"] or ""

        if len(text.strip()) < 20:
            skipped += 1
            continue

        try:
            cl = classify_mail_llm(
                konto=konto,
                absender=k_email,
                betreff=betreff,
                text=text,
                mail_datum=datum,
                kanal="email",
            )

            kat       = cl.get("kategorie", "")
            konfidenz = cl.get("konfidenz", "mittel")
            task_typ  = kategorie_to_task_typ(kat)
            prio      = cl.get("prioritaet", 2)
            zusammen  = cl.get("zusammenfassung", "")
            aktion    = cl.get("empfohlene_aktion", "")
            antwort   = cl.get("antwort_noetig", False)
            rolle     = cl.get("absender_rolle", "")
            grund     = cl.get("kategorie_grund", "")

            print(f"  Task {task_id}: {betreff[:50]!r} -> {kat} [{konfidenz}]")

            if not dry_run:
                db.execute("""
                    UPDATE tasks SET
                        typ               = ?,
                        kategorie         = ?,
                        konfidenz         = ?,
                        prioritaet        = ?,
                        zusammenfassung   = ?,
                        empfohlene_aktion = ?,
                        antwort_noetig    = ?,
                        absender_rolle    = ?,
                        kategorie_grund   = ?
                    WHERE id = ?
                """, (task_typ, kat, konfidenz, prio,
                      zusammen, aktion, 1 if antwort else 0,
                      rolle, grund, task_id))
            updated += 1

        except Exception as e:
            print(f"  Task {task_id}: Fehler – {e}")
            skipped += 1

    if not dry_run:
        db.commit()
    db.close()

    print(f"\n[reclassify] Fertig: {updated} aktualisiert, {skipped} übersprungen"
          + (" (DRY RUN – nichts gespeichert)" if dry_run else ""))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nicht speichern")
    p.add_argument("--limit", type=int, default=0, help="Nur N Tasks verarbeiten")
    args = p.parse_args()
    reclassify_all(dry_run=args.dry_run, limit=args.limit)
