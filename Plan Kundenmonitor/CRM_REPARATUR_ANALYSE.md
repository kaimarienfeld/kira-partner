# CRM Datenbank-Reparatur — Analyse & Protokoll

Stand: 2026-04-10 18:40, Session: session-tt

---

## Bestandsaufnahme (Schritt 1)

### kunden.db — Tabellen
- `kunden` (vorher: 1.433 Einträge, ALLE aus Mail-Archiv-Migration)
- `kunden_identitaeten` (vorher: 1.433, ALLE typ='mail', quelle='migration')
- `kunden_projekte` (1 Test-Eintrag)
- `kunden_faelle` (1 Test-Eintrag)
- `kunden_aktivitaeten` (0)
- `kunden_classifier_log` (0)
- `interaktionen` (7.361 — alt, vor CRM)

### Kernproblem
- **1.433 Kunden — ALLE aus Mail-Archiv-Migration**
- **0 Kunden mit lexware_id** (kein einziger Lexware-verknüpft)
- Ursache: `_ensure_crm_tables()` in case_engine.py kopierte `kunden.email` → `kunden_identitaeten`
- Das war die ursprüngliche `interaktionen`-Tabelle, die ALLE Mail-Absender enthielt (Newsletter, eBay, Amazon, etc.)

### Lexware-Kontakte (korrekte Quelle)
- **273 Kontakte** in `tasks.db/lexware_kontakte`
- 166 mit E-Mail, 107 ohne
- 128 Firmen (geschaeft), 145 Personen (privat)

---

## Schritt 2 — Backup ✅
- `kunden.db.backup_vor_reparatur_20260410` erstellt (14.9 MB)

## Schritt 3 — Löschung ✅
- Sicherheitschecks bestanden: 0 Kunden mit lexware_id
- Gelöscht: 1.433 kunden, 1.433 identitaeten, 1 projekt, 1 fall
- VACUUM durchgeführt
- Autoincrement zurückgesetzt

## Schritt 4 — Lexware-Import ✅
- `kunden_lexware_sync.py` erstellt (~280 LOC)
- 273 Kunden importiert (128 geschaeft, 145 privat)
- 285 Identitäten erstellt (186 mail, 84 domain, 15 telefon)
- 2 Email-Duplikate korrekt behandelt (m.muenz@ib-muenz.de, christian.rabe@rewa.li)
- Alle mit lexware_id, quelle='lexware', confidence='eindeutig'

## Schritt 5 — Classifier umgestellt ✅
- `_build_kunden_kontext()`: WHERE lexware_id IS NOT NULL hinzugefügt
- `_fast_path()`: Stufe 2 Domain-Match ergänzt, k.lexware_id IS NOT NULL Filter
- `_ensure_crm_tables()`: Alte Migration entfernt (Zeile 761-768)

## Schritt 6 — Retroaktiver Mail-Scan ✅
- `kunden_mail_retroaktiv.py` erstellt (~200 LOC)
- 12.654 Mails gescannt, 1.718 zugeordnet (13.6%)
- 1.718 Aktivitäten erstellt
- 96 Kunden mit Mail-Statistiken aktualisiert
- Top: GOLDBECK Ost GmbH (603), Marius Felber (446), shipcloud GmbH (132)

## Schritt 7 — CRM-Einstellungen UI ✅
- Lexware-Sync-Status-Anzeige
- "Lexware-Sync starten" Button
- "Mail-Archiv scannen" Button (Retro-Scan)
- 3 neue API-Endpoints: POST /api/crm/lexware-sync, /api/crm/retro-scan, /api/crm/sync-status
- JS: crmLexwareSyncJetzt(), crmRetroScanJetzt(), crmLoadSyncStatus()

## Schritt 8 — Dokumentation ✅
- KUNDEN_CLASSIFIER_KONZEPT.md aktualisiert (Lexware-Only-Pipeline)
- CRM_REPARATUR_ANALYSE.md erstellt (dieses Dokument)

---

## Dateien geändert

| Datei | Aktion |
|---|---|
| `scripts/kunden_lexware_sync.py` | **NEU** — Lexware → kunden.db Sync |
| `scripts/kunden_mail_retroaktiv.py` | **NEU** — Retroaktiver Mail-Scan |
| `scripts/case_engine.py` | Migration entfernt (Zeile 761-768) |
| `scripts/kunden_classifier.py` | Lexware-Only Filter + Domain-Match |
| `scripts/server.py` | 3 neue Endpoints + Einstellungen UI + JS |
| `Plan Kundenmonitor/KUNDEN_CLASSIFIER_KONZEPT.md` | Aktualisiert |
| `Plan Kundenmonitor/CRM_REPARATUR_ANALYSE.md` | **NEU** |

---

## Ergebnis

| Vorher | Nachher |
|---|---|
| 1.433 Kunden aus Mail-Archiv | 273 Kunden aus Lexware Office |
| 0 mit lexware_id | 273 mit lexware_id (100%) |
| 1.433 Identitäten (nur mail) | 285 Identitäten (mail + domain + telefon) |
| 0 Aktivitäten | 1.718 zugeordnete Mail-Aktivitäten |
| Classifier ohne Lexware-Filter | Classifier NUR Lexware-Kunden |
| Kein Sync-Mechanismus | Lexware-Sync + Retro-Scan Scripts |
