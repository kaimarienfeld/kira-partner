# Lexware Office — Masterliste aller Phasen und Aufgaben

Stand: 2026-04-01 05:45
Session: session-eee (Lexware Office Nacht-Session)
Ziel: Vollstaendige strukturierte Abarbeitung bis Modul-Abschluss

## Legende
✅ Erledigt | 🔄 In Bearbeitung | ⏳ Offen | ⚠️ Kai-Aktion | ❌ Blockiert | 🔍 Zu pruefen

---

## Phase 0 — Session-Start

- [x] ✅ Pflichtdateien gelesen (AGENT.md, Arbeitsanweisung V5)
- [x] ✅ session_log.md Eintrag 2026-04-01 05:30
- [x] ✅ change_log.jsonl geprueft (lexware: bisher nur planned, keine Implementation)
- [x] ✅ PHP-Altstrecke gelesen und dokumentiert
- [x] ✅ feature_registry.json Eintrag lexware-anbindung: status=planned
- [x] ✅ Planungsordner geprueft (leer, jetzt befuellt)
- [x] ✅ Repo-Audit durchgefuehrt

---

## Phase 1 — Plan-Agent

- [x] ✅ Plan-Agent gestartet (laeuft im Hintergrund)
- [ ] ⏳ LEXWARE_SESSION_PLAN.md (aus Plan-Agent)
- [ ] ⏳ Plan reviewen und finalisieren

---

## Phase 2 — Repo-Audit

- [x] ✅ LEXWARE_REPO_AUDIT.md erstellt
- [x] ✅ PHP 00-04 analysiert
- [x] ✅ KIRA-Codebase geprueft (server.py, kira_llm.py, tasks.db)
- [x] ✅ Sidebar-Struktur und Einstellungen-Sektionen dokumentiert

---

## Phase 3 — Internet-Recherche

- [x] ✅ Research-Agent gestartet (laeuft im Hintergrund)
- [ ] ⏳ LEXWARE_API_RECHERCHE.md (aus Research-Agent)
- [ ] ⏳ API-Endpunkte und Auth verifiziert

---

## Phase 4 — Pflicht-Plandateien

- [ ] ⏳ LEXWARE_SESSION_PLAN.md
- [x] ✅ LEXWARE_REPO_AUDIT.md
- [ ] ⏳ LEXWARE_API_RECHERCHE.md
- [ ] ⏳ LEXWARE_GAP_ANALYSE.md
- [ ] ⏳ LEXWARE_ARCHITEKTUR.md
- [ ] ⏳ LEXWARE_UI_PLAN.md
- [ ] ⏳ LEXWARE_SETTINGS_PLAN.md
- [ ] ⏳ LEXWARE_BUCHHALTUNG_PRUEFBEREICH.md
- [ ] ⏳ LEXWARE_DATAVERSE_PLAN.md
- [ ] ⏳ LEXWARE_RUNTIME_LOG_PLAN.md
- [x] ✅ KAI_TODO_LEXWARE.md

---

## Phase 5 — Implementierung

### Paket 1 — DB-Schema (tasks.db Migration)
- [ ] ⏳ Tabelle: lexware_belege
- [ ] ⏳ Tabelle: lexware_kontakte
- [ ] ⏳ Tabelle: lexware_artikel
- [ ] ⏳ Tabelle: eingangsbelege_pruefqueue
- [ ] ⏳ Tabelle: lexware_config
- [ ] ⏳ Migration testen (keine bestehenden Daten beschaedigen)
- [ ] ⏳ Git Commit: feat(db): Lexware DB-Schema

### Paket 2 — Lexware Python Client
- [ ] ⏳ Datei: scripts/lexware_client.py anlegen
- [ ] ⏳ LexwareClient Klasse
- [ ] ⏳ _request(method, path, data) — Bearer Token
- [ ] ⏳ get_vouchers(typ, status, seite)
- [ ] ⏳ get_voucher(id)
- [ ] ⏳ create_voucher(typ, payload)
- [ ] ⏳ get_contacts()
- [ ] ⏳ get_contact(id)
- [ ] ⏳ create_contact(payload)
- [ ] ⏳ get_articles()
- [ ] ⏳ get_files(voucher_id)
- [ ] ⏳ upload_file(voucher_id, pfad)
- [ ] ⏳ Rate-Limit Handler (429 + Retry)
- [ ] ⏳ Token aus config (nie hardcoded)
- [ ] ⏳ Sync-Methoden: _sync_belege_to_db(), _sync_kontakte_to_db()
- [ ] ⏳ Git Commit: feat(lexware): Python Client

### Paket 3 — Einstellungen-Sektion
- [ ] ⏳ Neue es-sn "lexware" in Sidebar der Einstellungen
- [ ] ⏳ es-sec-panel#es-sec-lexware
- [ ] ⏳ API-Key Feld + Test-Button
- [ ] ⏳ Verbindungsstatus (gruener/roter Chip)
- [ ] ⏳ Sync-Verhalten: Intervall, Auto/Manuell
- [ ] ⏳ Modul-Freischaltung: nicht_gebucht / gesperrt / freigeschaltet Toggle
- [ ] ⏳ Buchhaltungs-Pruefregel Toggles
- [ ] ⏳ PayPal-Ausnahmen-Regeln
- [ ] ⏳ Dataverse-Zusatzexport Toggle + Credentials
- [ ] ⏳ API-Endpunkte: POST /api/lexware/config/save, POST /api/lexware/test
- [ ] ⏳ saveSettings() Erweiterung fuer lexware.*
- [ ] ⏳ Git Commit: feat(einstellungen): Lexware Office Sektion

### Paket 4 — Lexware Office Panel + Sidebar
- [ ] ⏳ def build_lexware(db) in server.py
- [ ] ⏳ Sidebar-Eintrag nav-lexware
- [ ] ⏳ Panel mit Tabs: Cockpit / Belege / Zahlungen / Kontakte / Artikel / Buchhaltung / Diagnose
- [ ] ⏳ Cockpit-Tab: Status, letzte Sync, Fehler, manuelle Aktionen
- [ ] ⏳ Sperrverhalten: CSS-Sperrbanner wenn nicht freigeschaltet
- [ ] ⏳ showPanel('lexware') verdrahten
- [ ] ⏳ generate_html() Erweiterung
- [ ] ⏳ JS: showLexTab(), loadLexCockpit(), lexSync()
- [ ] ⏳ API-Endpunkte: GET /api/lexware/status, POST /api/lexware/sync
- [ ] ⏳ Git Commit: feat(lexware): Panel + Sidebar + Cockpit-Tab

### Paket 5 — Beleg-Center Tab
- [ ] ⏳ Tabelle: Rechnungen, Angebote, Mahnungen aus lexware_belege
- [ ] ⏳ Filter: Typ, Status, Zeitraum, Kontakt
- [ ] ⏳ Detail-Ansicht: Belegdaten, Positionen, Zahlungsstatus
- [ ] ⏳ PDF-Link (falls URL in API vorhanden)
- [ ] ⏳ Kira-Button pro Beleg
- [ ] ⏳ API: GET /api/lexware/belege
- [ ] ⏳ Git Commit: feat(lexware): Beleg-Center Tab

### Paket 6 — Kontakte Tab
- [ ] ⏳ Kontaktliste aus lexware_kontakte
- [ ] ⏳ Suche/Filter
- [ ] ⏳ Detail: offene Posten, letzter Vorgang
- [ ] ⏳ API: GET /api/lexware/kontakte
- [ ] ⏳ Git Commit: feat(lexware): Kontakte Tab

### Paket 7 — Buchhaltung Tab (Eingangsbelege-Pruefqueue)
- [ ] ⏳ Pruefqueue-Ansicht: zu pruefen / klassifiziert / abgelegt / unklar
- [ ] ⏳ Filter: Status, Zeitraum, Absender, Betrag
- [ ] ⏳ Detail: Absender, Betrag, Datum, Body-Excerpt, Anhang-Info
- [ ] ⏳ Kira-Frage/Antwort sichtbar und editierbar
- [ ] ⏳ Kontenvorschlag (Lexware Office Konto + Nummer)
- [ ] ⏳ Status-Buttons: pruefen / klassifizieren / ablegen
- [ ] ⏳ API: GET/POST /api/lexware/eingangsbelege
- [ ] ⏳ Git Commit: feat(lexware): Buchhaltung-Tab Eingangsbelege

### Paket 8 — Kira-Tools
- [ ] ⏳ kira_llm.py: Tool lexware_belege_laden (Kontext fuer Kira)
- [ ] ⏳ kira_llm.py: Tool lexware_eingangsbeleg_klassifizieren(beleg_id)
- [ ] ⏳ System-Prompt Erweiterung: Lexware-Kontext wenn Modul aktiv
- [ ] ⏳ Git Commit: feat(kira): Lexware Tools

### Paket 9 — Mail-Monitor Erweiterung
- [ ] ⏳ mail_monitor.py: _scan_eingangsbelege() Funktion
- [ ] ⏳ Erkennung: Lieferantenrechnung / Abo / Dienstleister (Body + Anhang)
- [ ] ⏳ PayPal-Unterscheidung: Zahlungsbestaetigung ≠ Rechnung
- [ ] ⏳ Apple/Body-Rechnung: Body-Parsing fuer rechnung-im-body
- [ ] ⏳ Eintrag in eingangsbelege_pruefqueue
- [ ] ⏳ Git Commit: feat(mail): Eingangsbeleg-Scan fuer Buchhaltungs-Pruefqueue

---

## Phase 6 — Abschluss

- [ ] ⏳ KIRA_SYSTEM_ANALYSE.md aktualisieren (Lexware-Sektion)
- [ ] ⏳ LEXWARE_MASTERCHECKLISTE.md finalisieren
- [ ] ⏳ KAI_TODO_LEXWARE.md finalisieren
- [ ] ⏳ session_handoff.json finalisieren
- [ ] ⏳ feature_registry.json aktualisieren (lexware-anbindung: done)
- [ ] ⏳ knowledge/session_log.md Abschlusseintrag
- [ ] ⏳ Abschlusstabelle im Chat

---

## Kai-Aktionen (am Ende — nicht ueberspringen)

⚠️ KAI-01: Lexware API-Key in KIRA Einstellungen eintragen → details in KAI_TODO_LEXWARE.md
⚠️ KAI-02: Alten API-Key aus PHP widerrufen (Sicherheit!) → details in KAI_TODO_LEXWARE.md
⚠️ KAI-03: Dataverse-Credentials pruefen (optional) → details in KAI_TODO_LEXWARE.md
⚠️ KAI-04: PHP-Altstrecke deaktivieren (optional) → details in KAI_TODO_LEXWARE.md
⚠️ KAI-05: Lexware Webhook einrichten (optional) → details in KAI_TODO_LEXWARE.md
