#!/usr/bin/env python3
"""Nacharchivierung: Holt Mails ohne lokales Archiv per IMAP und speichert sie.

Nutzung:
    python scripts/backfill_archive.py              # Alle fehlenden
    python scripts/backfill_archive.py --dry-run    # Nur zeigen, nicht speichern
"""
import sys, os, json, sqlite3, email
from pathlib import Path
from datetime import datetime

# Windows cp1252 fix
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Pfade relativ zum Script
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / 'config.json'
MAIL_INDEX_DB = SCRIPT_DIR.parent / 'knowledge' / 'mail_index.db'

# mail_monitor importieren
sys.path.insert(0, str(SCRIPT_DIR))
import mail_monitor
from mail_monitor import imap_connect, _imap_connect_konto, _decode_hdr

def _save_to_archive_forced(mail_data, raw_bytes, konto_label, folder_name):
    """Wrapper: setzt neue_mails_archivieren temporär auf True damit _save_to_archive() nicht abbricht."""
    import mail_monitor as _mm
    # Config temporär patchen
    cfg = json.loads(CONFIG_FILE.read_text('utf-8'))
    changed = False
    if not cfg.get('mail_archiv', {}).get('neue_mails_archivieren', True):
        cfg.setdefault('mail_archiv', {})['neue_mails_archivieren'] = True
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
        changed = True
    result = _mm._save_to_archive(mail_data, raw_bytes, konto_label, folder_name)
    return result

def main():
    dry_run = '--dry-run' in sys.argv

    config = json.loads(CONFIG_FILE.read_text('utf-8'))
    konten_cfg = config.get('mail_konten', {}).get('konten', [])

    # Alle Mails ohne Archiv-Pfad finden
    db = sqlite3.connect(str(MAIL_INDEX_DB))
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT message_id, konto, folder, absender, betreff, datum, an, text_plain "
        "FROM mails WHERE (mail_folder_pfad IS NULL OR mail_folder_pfad='') "
        "ORDER BY konto, datum"
    ).fetchall()
    db.close()

    if not rows:
        print("Keine Mails ohne Archiv gefunden.")
        return

    print(f"{'[DRY-RUN] ' if dry_run else ''}Nacharchivierung: {len(rows)} Mails")

    # Pro Konto gruppieren
    by_konto = {}
    for r in rows:
        k = r['konto'] or ''
        by_konto.setdefault(k, []).append(r)

    total_ok = 0
    total_fail = 0

    for konto_email, mails in by_konto.items():
        print(f"\n--- Konto: {konto_email} ({len(mails)} Mails) ---")

        if dry_run:
            for m in mails:
                print(f"  [DRY] {m['datum']} | {m['absender'][:35]} | {m['betreff'][:45]}")
            total_ok += len(mails)
            continue

        # IMAP-Verbindung via _imap_connect_konto (löst Config aus archiver + kira auf)
        try:
            imap = _imap_connect_konto(konto_email)
            if not imap:
                raise ConnectionError("Kein Konto gefunden")
        except Exception as e:
            print(f"  FEHLER: IMAP-Verbindung fehlgeschlagen: {e}")
            total_fail += len(mails)
            continue

        for m in mails:
            msg_id = m['message_id']
            folder = m['folder'] or 'INBOX'

            # Message-ID für SEARCH formatieren
            search_id = msg_id.strip()
            if not search_id.startswith('<'):
                search_id = '<' + search_id
            if not search_id.endswith('>'):
                search_id = search_id + '>'

            # In mehreren Ordnern suchen
            folders_to_try = [folder, 'INBOX', 'Sent Items', 'Gesendete Elemente', 'Sent', 'Junk-E-Mail']
            seen = set()
            folders_to_try = [f for f in folders_to_try if not (f in seen or seen.add(f))]

            raw_bytes = None
            found_folder = ''
            for fld in folders_to_try:
                try:
                    status, _ = imap.select(f'"{fld}"', readonly=True)
                    if status != 'OK':
                        continue
                    status, data = imap.uid('SEARCH', None, f'HEADER Message-ID "{search_id}"')
                    if status == 'OK' and data and data[0]:
                        uids = data[0].split()
                        if uids:
                            status, msg_data = imap.uid('FETCH', uids[0], '(RFC822)')
                            if status == 'OK' and msg_data:
                                for item in msg_data:
                                    if isinstance(item, tuple) and len(item) >= 2:
                                        raw_bytes = item[1]
                                        break
                            if raw_bytes:
                                found_folder = fld
                                break
                except Exception:
                    continue

            if not raw_bytes:
                betr = m['betreff'][:40] if m['betreff'] else '?'
                print(f"  NICHT GEFUNDEN: {m['datum']} | {betr}")
                total_fail += 1
                continue

            # Archivieren via _save_to_archive()
            mail_data = {
                'message_id': msg_id,
                'konto': konto_email,
                'betreff': m['betreff'] or '',
                'absender': m['absender'] or '',
                'an': m['an'] or '',
                'datum': m['datum'] or '',
                'datum_iso': (m['datum'] or '')[:19],
                'text': m['text_plain'] or '',
            }

            pfad = _save_to_archive_forced(mail_data, raw_bytes, konto_email, found_folder)
            if pfad:
                # mail_index.db aktualisieren
                try:
                    udb = sqlite3.connect(str(MAIL_INDEX_DB))
                    eml_path = str(Path(pfad) / 'mail.eml')
                    udb.execute(
                        "UPDATE mails SET mail_folder_pfad=?, eml_path=? WHERE message_id=?",
                        (pfad, eml_path, msg_id)
                    )
                    udb.commit()
                    udb.close()
                except Exception as e:
                    print(f"  DB-UPDATE FEHLER: {e}")

                betr = m['betreff'][:40] if m['betreff'] else '?'
                print(f"  OK: {m['datum']} | {betr}")
                total_ok += 1
            else:
                betr = m['betreff'][:40] if m['betreff'] else '?'
                print(f"  ARCHIV-FEHLER: {m['datum']} | {betr}")
                total_fail += 1

        try:
            imap.logout()
        except:
            pass

    print(f"\n=== Ergebnis: {total_ok} archiviert, {total_fail} fehlgeschlagen ===")


if __name__ == '__main__':
    main()
