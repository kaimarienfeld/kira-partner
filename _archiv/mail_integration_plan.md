# Mail-Modul Integration: Technischer Plan & Status

**Stand:** 2026-03-28
**Session:** session-x

---

## Ausgangslage (was analysiert wurde)

### Mail Archiv App (Quelle)
- `raumkult_mail_archiver_v3.81.py` (2432 Zeilen, tkinter)
- 35.686 Mails in Filesystem: `Archiv/{email}/{folder}/{date}_{subject}_{hash}/mail.json + mail.eml`
- 5 OAuth2-Konten (alle via MSAL Device-Code-Flow, Scope: `IMAP.AccessAsUser.All`)
- Token-Cache: `Mail Archiv/tokens/{email}_token.json`
- Client-ID: `0c6f47fc-2daa-475f-a7b0-f1c03743dbae`, Tenant: `common`
- IMAP, **receive-only** (kein SMTP-Versand)
- Incremental Sync via IMAP UID + UIDVALIDITY
- Nur INBOX + Gesendete Elemente
- Dedup: MD5(Message-ID + Date) als Directory-Suffix

### Kira bestehende Mail-Infrastruktur
- `mail_monitor.py`: Aktiver IMAP-Poller, nutzt selben Token-Cache
- `build_databases.py`: Liest Mail Archiv Filesystem → mail_index.db
- **mail_index.db**: 12.442 Mails, `message_id UNIQUE`
- **sent_mails.db**: 546 gesendete Mails (Stil-Lernbasis)
- **kunden.db**: Kunden-Interaktionen
- **tasks.db**: 51 Tasks mit message_id FK + loeschhistorie
- `mail_monitor_state.json`: UID-Stand pro Konto/Ordner

---

## Erkannte Lücken (Schritt 0 — Analyse)

| Lücke | Problem | Fix |
|-------|---------|-----|
| mail_monitor.py schreibt NICHT in mail_index.db | Live-Mails landen nur in tasks.db | _index_mail() hinzugefügt ✅ |
| Keine Thread-Header (In-Reply-To, References) | Kein Threading möglich | In parse_raw_mail() extrahiert ✅ |
| Kein SMTP-Versand | Kira kann keine Mails senden | mail_sender.py gebaut ✅ |
| mail_index.db Schema fehlen Felder | thread_id, sync_source, text_plain fehlen | mail_schema_migrate.py + build_databases.py ✅ |
| Mails ohne message_id → Duplikate möglich | Fallback fehlte | Fallback-Hash implementiert ✅ |
| 35.686 Mail Archiv ≠ 12.442 mail_index.db | Lücke im Index | build_databases.py neu laufen lassen |

---

## Architektur: Primärpfad vs. Fallback

### Primärpfad (Kira-eigener Mail-Abruf)
```
IMAP-Server (outlook.office365.com:993)
    ↓ OAuth2 XOAUTH2 (MSAL, token aus Mail Archiv cache)
    ↓ Incremental Sync (UID > last_uid)
mail_monitor.py
    ↓ parse_raw_mail() → extrahiert Threading-Header
    ↓ _process_mail() → klassifiziert, erstellt Task
    ↓ _index_mail() NEU → schreibt in mail_index.db (sync_source='live_sync')
    ↓ kunden.db → Kunden-Interaktionen
tasks.db + mail_index.db
```

### Fallback (Mail Archiv als historische Basis)
```
Mail Archiv Filesystem (35.686 Mails)
    ↓ build_databases.py (Batch-Import, INSERT OR IGNORE)
    ↓ sync_source = 'archiv_import'
mail_index.db (Bestandsmails)
```

### Wenn IMAP-Verbindung ausfällt
```
mail_monitor.py IMAP fehlgeschlagen
    → letzter UID-Stand bleibt in mail_monitor_state.json
    → mail_index.db enthält alle bisher importierten Mails
    → UI zeigt Bestand aus mail_index.db
    → Beim nächsten erfolgreichen Poll: Lücke wird nachgeholt (UID-basiert)
```

---

## Duplikat-Prävention (Strategie)

### Stufe A — Harte Identität (primär)
- `message_id` RFC822 Message-ID Header
- `UNIQUE`-Constraint in mail_index.db → INSERT OR IGNORE
- Gleiche Mail zweimal → zweiter Insert wird still ignoriert

### Stufe B — Fallback-Hash (wenn message_id fehlt)
- `FALLBACK-{SHA256(konto|absender|an|datum_iso|betreff[:60])[:20]}`
- Wird als message_id UND fallback_hash gespeichert
- Schützt auch ältere Mails ohne Message-ID Header

### Stufe C — loeschhistorie-Sperre (user-deleted)
- Gelöschte Mails in tasks.db.loeschhistorie mit message_id
- mail_monitor prüft tasks.db auf Duplikate → wenn message_id dort bekannt → skip

### Thread-Rekonstruktion
- `thread_id` = älteste Message-ID im References-Header (RFC 2822 Standard)
- Falls keine References → In-Reply-To als Thread-Anker
- Falls beides fehlt → message_id selbst (neue Konversation)

---

## Erstimport-Strategie

**Ziel:** Mail Archiv Filesystem (35.686) → mail_index.db vollständig importieren ohne Duplikate

**Vorgehen:**
1. `build_databases.py` neu ausführen → INSERT OR IGNORE auf message_id UNIQUE
2. Neue Felder (thread_id, sync_source='archiv_import', text_plain, eml_path) werden mitgespeichert
3. Danach `mail_schema_migrate.py` für Backfill-Checks
4. Ergebnis: mail_index.db enthält BEIDE Quellen (Archiv + Live)

**Keine Dublettenexplosion möglich weil:**
- message_id UNIQUE Constraint
- INSERT OR IGNORE → stilles Überspringen
- loeschhistorie verhindert Re-Import gelöschter Tasks

---

## Laufende Synchronisation (Konfikte-Behandlung)

| Szenario | Behandlung |
|----------|-----------|
| Gleiche Mail: Archiv UND live_sync | message_id UNIQUE → zweiter Insert ignoriert. Erster Treffer (meist Archiv) gilt. |
| Mail in Inbox UND Gesendete | Verschiedene folder-Werte → beide Einträge vorhanden (legitim) |
| mail_monitor crash mid-batch | UID-Stand nicht aktualisiert → nächster Poll holt dieselben UIDs nochmal → INSERT OR IGNORE schützt |
| Archivierte Mail hat unvollst. Metadaten | eml_path speichert Pfad zur .eml → Volltext abrufbar |
| Bereits als Task bearbeitet, Mail kommt erneut | message_id in tasks.db → _process_mail() skip via Duplikat-Check Zeile 350 |
| Manuell gelöschter Task, Mail re-importiert | loeschhistorie-Sperre → wird nicht neu klassifiziert |

**Führende Version:** Bei Konflikten gilt der ERSTE Import (zuerst gespeicherte Zeile). Spätere Imports werden durch IGNORE verworfen. KIRA-Kontexte (Kategorie, Notizen, Tasks) können daher nie durch Re-Import überschrieben werden.

---

## Status aller gebauten Komponenten

### ✅ Fertig (diese Session)

| Datei | Was wurde geändert |
|-------|------------------|
| `scripts/mail_schema_migrate.py` | NEU: Sicheres Schema-Upgrade, Backfill thread_id, Duplikat-Check |
| `scripts/mail_sender.py` | NEU: SMTP XOAUTH2 Versand, Template-Versand, saved in sent_mails.db |
| `scripts/mail_monitor.py` | Erweitert: Threading-Header (In-Reply-To/References), _index_mail(), Fallback-Hash |
| `scripts/build_databases.py` | Erweitert: Schema mit neuen Feldern, in_reply_to/thread_id/sync_source/text_plain/eml_path im Insert |

### 🔲 Nächste Session — Mail-UI

- **server.py**: Mail-Modul Endpoints (GET /api/mail/list, GET /api/mail/thread, POST /api/mail/send)
- **UI**: Outlook-Style 3-Pane (Kontoliste links, Mailliste Mitte, Preview rechts)
- **Thread-View**: Mails nach thread_id gruppiert anzeigen
- **Versand-Dialog**: Aus Kira heraus schreiben + senden via mail_sender.py
- **Ordner-Navigation**: Inbox, Gesendete, Entwürfe, Archiv

### 🔲 Später

- Entwürfe speichern (drafts.db oder tasks.db mit status='entwurf')
- KI-Antwortvorschlag direkt im Mail-UI
- Anhang-Viewer
- Multi-Account-Filterung
- Gmail/IMAP-Generic Account Support

---

## Nächste sofortige Schritte (vor UI-Bau)

1. **Schema-Migration ausführen**: `python scripts/mail_schema_migrate.py`
2. **Archiv-Import neu laufen**: `python scripts/build_databases.py` (befüllt neue Felder)
3. **SMTP-Token testen**: `python scripts/mail_sender.py` (prüft OAuth2 für SMTP)
4. **mail_monitor.py testen**: `python scripts/mail_monitor.py` (prüft _index_mail())

---

## Geprüfte Dateien (Analyse)

- `raumkult_mail_archiver_v3.81.py` (2432 Zeilen) — vollständig analysiert
- `scripts/mail_monitor.py` — vollständig gelesen + erweitert
- `scripts/build_databases.py` — vollständig gelesen + erweitert
- `knowledge/mail_index.db` — Schema + Statistik (12.442 Mails)
- `knowledge/sent_mails.db` — Schema (546 Mails)
- `knowledge/mail_monitor_state.json` — UID-Stände 5 Konten
- `scripts/server.py` — Mail-Endpoints lokalisiert (Zeilen 7524-7591)
