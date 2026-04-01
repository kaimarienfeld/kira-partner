# LEXWARE_REPO_AUDIT.md — Repo-Audit Ist-Zustand

Stand: 2026-04-01 05:45
Session: session-eee

---

## 1. PHP-Altstrecke (00-04)

**Speicherort:** `C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\07_Webseiten\VS\sonstige Webseiten\Sichtbeton-cire.de\`

| Datei | Zweck | Status |
|-------|-------|--------|
| 00_lex_billb_master.php | Orchestrierung: ruft 01-04 sequenziell auf | aktiv auf Webserver |
| 01_lex_billb_fetch_invoices.php | GET /v1/voucherlist?voucherType=invoice&voucherStatus=open | aktiv |
| 02_lex_billb_fetch_invoice_details.php | GET /v1/vouchers/{id} fuer jeden Beleg | aktiv |
| 03_lex_billb_fetch_contact.php | GET /v1/contacts/{id} | aktiv |
| 04_lex_billb_convert_to_billbee.php | POST nach Billbee + POST nach Dataverse | aktiv |
| admin_lex_billb.php | Admin-Panel fuer die Strecke | unklar |
| cron_lex_billb_control.php | Cron-Steuerung | unklar |

### API-Endpunkt alt
```
https://api.lexoffice.io/v1/voucherlist?voucherType=invoice&voucherStatus=open
Authorization: Bearer [KEY]
Accept: application/json
```

### Dataverse-Konfiguration (aus PHP-Code)
- Tenant: 2d79d7b6-d1c0-47c1-971e-66ee3173b8c8
- Org-URL: https://orge14a61e1.crm16.dynamics.com
- API-Version: /api/data/v9.2/
- Entity Rechnungen: cr812_rechnungenraumkultleistungs
- Entity Positionen: cr812_posrechnungenraumkultleistungs
- Client-App: 42b5e93e-a8fa-4479-9869-e8642c40b7a1
- Methode: client_credentials (App-only, kein User-Login)

### Duplikat-Handling (alt)
- GET mit $filter=cr812_dokumenttypundnummer eq '{nummer}'
- Falls vorhanden: UUID zurueckgeben, kein erneuter POST
- Falls nicht: POST + Location-Header auswerten fuer neue UUID

### Payload-Struktur Rechnung (aus PHP)
Felder: cr812_dokumenttypundnummer, weitere Felder aus Lexware-Response gemappt

### Ergebnis des Audits
- Strecke NICHT in KIRA-Codebase — laeuft als PHP auf externem Webserver
- Keine Integration in server.py, kira_llm.py, tasks.db
- Kein Runtime-Logging
- Kein UI in KIRA-Dashboard
- Altstrecke ist Vorlage fuer Mapping-Felder und Dataverse-Struktur
- **Wird NICHT in KIRA migriert als PHP** — stattdessen Python-Native-Implementation

---

## 2. KIRA-Codebase (aktuell)

### 2a. server.py — Bestehende Lexware-Referenzen
- Keine direkte Lexware-API-Integration
- `_build_gesch_aktiv()` (Zeile ~1282): zeigt manuelle Eingangsrechnungen aus tasks.db
- `geschaeft WHERE typ='eingangsrechnung'`: einfache manuelle Erfassung, NICHT auto-erkannt
- Keine `lexware_*` Tabellen in DB
- Keine `/api/lexware/*` Endpunkte

### 2b. kira_llm.py — Bestehende Tools
- 23 Tools definiert
- Keine Lexware-spezifischen Tools
- Kein Zugriff auf Lexware-Daten

### 2c. mail_monitor.py — Bestehende Mail-Logik
- Erkennt Mails und klassifiziert sie (eingangsrechnung, anfrage, etc.)
- Erstellt Tasks fuer erkannte Eingangsrechnungen
- KEIN intelligenter Parsing/Prueflauf fuer Buchhaltungs-Vorbereitung
- KEIN PayPal-Unterscheidung auf Rechnungs-Ebene (nur grobe Klassifizierung)

### 2d. tasks.db — Bestehende Tabellen
```sql
-- Relevante bestehende Tabellen
geschaeft (id, typ, partner, datum, betrag, faellig, status, beschreibung, referenz, notizen, quelle, erledigt_ts)
-- typ: 'ausgangsrechnung', 'angebot', 'eingangsrechnung', 'zahlungserinnerung', 'mahnung'
```
Keine Lexware-spezifischen Tabellen.

### 2e. feature_registry.json — Lexware-Eintrag
```json
{
  "id": "lexware-anbindung",
  "status": "planned",
  "leni_visible": false
}
```
Status: planned → wird in dieser Session auf "in_progress" / "done" gesetzt.

---

## 3. Sidebar-Struktur (aktuell)

Aktive Module:
- dashboard, kommunikation, postfach, organisation, geschaeft, wissen
- kira-aktivitaeten, protokoll, einstellungen

Geplante Module (CSS-Klasse "planned"):
- kunden, marketing, social, automationen, analysen

**Lexware Office** wird als neues Modul nach "geschaeft" eingefuegt.

---

## 4. Einstellungen-Sektionen (aktuell)

Vorhandene Sektionen in esShowSec():
design, benachrichtigungen, aufgaben, nachfass, dashboard, provider, mail, integrationen, automationen, sicherheit-audit, verbrauch, protokoll

**Neue Sektion:** `lexware` (nach "integrationen" einzufuegen)

---

## 5. Bewertung: Was ist zu bauen

| Bereich | Ist-Zustand | Massnahme |
|---------|-------------|-----------|
| Lexware Python Client | fehlt | NEU: scripts/lexware_client.py |
| DB-Schema Lexware | fehlt | NEU: 5 Tabellen in tasks.db (Migration) |
| Eingangsbeleg-Pruefqueue | fehlt | NEU: Tabelle + UI |
| Einstellungen Lexware-Sektion | fehlt | NEU in build_einstellungen() |
| Lexware Office Panel | fehlt | NEU: build_lexware() in server.py |
| Sidebar-Eintrag Lexware | fehlt | NEU: sidebar-item |
| Kira-Tools Lexware | fehlt | NEU: 2-3 Tools in kira_llm.py |
| Mail-Monitor Eingangsbeleg-Scan | teilweise | ERWEITERN: intelligenteres Parsing |
| Dataverse-Export | alt (PHP) | Optional: Python-Port oder belassen |
| Billbee-Export | alt (PHP) | Ausserhalb Scope dieser Session |

---

## 6. Risiken und Seiteneffekte

| Risiko | Bereich | Massnahme |
|--------|---------|-----------|
| server.py ist bereits ~20.000+ Zeilen | Performance | Neue build_lexware() Funktion analog build_geschaeft() |
| DB-Migrationen koennen vorhandene Daten korrumpieren | DB | Nur ALTER TABLE ADD COLUMN oder neue Tabellen — niemals DROP |
| Doppelerfassung Eingangsrechnungen | Daten | Dedup via mail_id oder beleg_hash |
| API-Rate-Limits Lexware | API | 429-Handler + Retry mit Backoff |
| Lexware API-Endpunkt Migration | API | Pruefe ob api.lexoffice.io oder api.lexware.io |
| Kira-Kontext zu gross | LLM | Lexware-Daten nur on-demand, nicht in jedem Prompt |

---

*Erstellt: 2026-04-01 05:45 | session-eee*
