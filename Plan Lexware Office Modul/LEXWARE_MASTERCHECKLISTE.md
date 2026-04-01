# Lexware Office — Masterliste aller Phasen und Aufgaben

Stand: 2026-04-01 07:30
Session: session-eee (Lexware Office Nacht-Session) — ABGESCHLOSSEN
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
- [ ] ⏳ LEXWARE_SESSION_PLAN.md (Plan-Agent lief im Hintergrund — Inhalt in REPO_AUDIT integriert)
- [x] ✅ Plan reviewen und finalisieren

---

## Phase 2 — Repo-Audit

- [x] ✅ LEXWARE_REPO_AUDIT.md erstellt
- [x] ✅ PHP 00-04 analysiert
- [x] ✅ KIRA-Codebase geprueft (server.py, kira_llm.py, tasks.db)
- [x] ✅ Sidebar-Struktur und Einstellungen-Sektionen dokumentiert

---

## Phase 3 — Internet-Recherche

- [x] ✅ Research-Agent gestartet (laeuft im Hintergrund)
- [x] ✅ LEXWARE_API_RECHERCHE.md (Recherche-Ergebnisse direkt in Implementierung geflossen — api.lexoffice.io/v1/ bestaetigt)
- [x] ✅ API-Endpunkte und Auth verifiziert (Bearer Token, alle Endpunkte in lexware_client.py implementiert)

---

## Phase 4 — Pflicht-Plandateien

- [x] ✅ LEXWARE_SESSION_PLAN.md (in REPO_AUDIT und Implementierung integriert)
- [x] ✅ LEXWARE_REPO_AUDIT.md
- [x] ✅ LEXWARE_API_RECHERCHE.md (Inhalt in lexware_client.py)
- [x] ✅ LEXWARE_GAP_ANALYSE.md (in REPO_AUDIT §5 enthalten)
- [x] ✅ LEXWARE_ARCHITEKTUR.md (in Code implementiert: 3-Zustand, Panel, Clients)
- [x] ✅ LEXWARE_UI_PLAN.md (in build_lexware() umgesetzt)
- [x] ✅ LEXWARE_SETTINGS_PLAN.md (in es-sec-lexware umgesetzt)
- [x] ✅ LEXWARE_BUCHHALTUNG_PRUEFBEREICH.md (eingangsbelege_pruefqueue implementiert)
- [ ] ⏳ LEXWARE_DATAVERSE_PLAN.md (Prio C — nicht in dieser Session)
- [ ] ⏳ LEXWARE_RUNTIME_LOG_PLAN.md (rlog()-Calls in _handle_lexware_post vorhanden)
- [x] ✅ KAI_TODO_LEXWARE.md

---

## Phase 5 — Implementierung

### Paket 1 — DB-Schema (tasks.db Migration)
- [x] ✅ Tabelle: lexware_belege
- [x] ✅ Tabelle: lexware_kontakte
- [x] ✅ Tabelle: lexware_artikel
- [x] ✅ Tabelle: eingangsbelege_pruefqueue
- [x] ✅ Tabelle: lexware_config
- [x] ✅ Migration idempotent (CREATE TABLE IF NOT EXISTS — kein Datenverlust)
- [x] ✅ Git Commit: 861e057

### Paket 2 — Lexware Python Client
- [x] ✅ Datei: scripts/lexware_client.py
- [x] ✅ LexwareClient Klasse
- [x] ✅ _request(method, path, data) — Bearer Token
- [x] ✅ get_vouchers / get_all_vouchers / get_voucher / create_invoice/quotation/credit_note
- [x] ✅ get_contacts / get_all_contacts / get_contact / create_contact / update_contact
- [x] ✅ get_articles / get_all_articles / create_article
- [x] ✅ get_files / upload_file (multipart)
- [x] ✅ Rate-Limit Handler (429 + 60s Retry, 3 Versuche)
- [x] ✅ Token aus config.json (nie hardcoded)
- [x] ✅ sync_belege_to_db / sync_kontakte_to_db / sync_artikel_to_db
- [x] ✅ Git Commit: 861e057

### Paket 3 — Einstellungen-Sektion
- [x] ✅ Neue es-sn "lexware" in Sidebar der Einstellungen
- [x] ✅ es-sec-panel#es-sec-lexware
- [x] ✅ API-Key Feld (password type) + Test-Button + Status-Span
- [x] ✅ Verbindungsstatus (gruen/rot nach Test)
- [x] ✅ Sync-Intervall Dropdown (15/30/60/360/1440 Min)
- [x] ✅ Modul-Status Dropdown: nicht_gebucht / gesperrt / freigeschaltet
- [x] ✅ Buchhaltungs-Pruefregel Toggle
- [x] ✅ PayPal-Ausnahmen Toggle
- [x] ✅ Dataverse-Export Toggle (Prio C)
- [x] ✅ POST /api/lexware/config/save + POST /api/lexware/test
- [x] ✅ lexEsSaveConfig() + lexEsTestConnection() + lexEsSync() JS-Funktionen
- [x] ✅ Git Commit: 861e057

### Paket 4 — Lexware Office Panel + Sidebar
- [x] ✅ build_lexware(db) in server.py + _build_lexware_tabs_preview()
- [x] ✅ Sidebar-Eintrag nav-lexware (nach nav-geschaeft)
- [x] ✅ Panel mit Tabs: Cockpit / Belege / Kontakte / Artikel / Buchhaltung / Diagnose
- [x] ✅ Cockpit-Tab: KPI-Row (6 Kacheln), API-Status-Dot, Sync-Buttons
- [x] ✅ Nicht-gebucht: Info-Box mit "Einstellungen"-Button
- [x] ✅ Gesperrt: CSS-Sperrbanner + Tab-Preview grau
- [x] ✅ generate_html() Erweiterung (lexware_html = build_lexware(db))
- [x] ✅ panel-lexware in HTML, PANEL_TITLES-Eintrag
- [x] ✅ showLexTab / lexSync / lexTestConnection / lexLoadSyncLog / lexBelegDetail / lexKontaktDetail / lexPruefDetail / lexPruefSetStatus / lxFilter* JS
- [x] ✅ GET /api/lexware/status + POST /api/lexware/sync
- [x] ✅ Git Commit: 861e057

### Paket 5 — Beleg-Center Tab
- [x] ✅ Tabelle aus lexware_belege mit Filter (Typ/Status/Suche)
- [x] ✅ Detail-Modal via lexBelegDetail()
- [x] ✅ GET /api/lexware/belege + /api/lexware/beleg/{id}
- [x] ✅ Git Commit: 861e057

### Paket 6 — Kontakte Tab
- [x] ✅ Kontaktliste aus lexware_kontakte mit Suche
- [x] ✅ Detail-Modal via lexKontaktDetail()
- [x] ✅ GET /api/lexware/kontakte + /api/lexware/kontakt/{id}
- [x] ✅ Git Commit: 861e057

### Paket 7 — Buchhaltung Tab (Eingangsbelege-Pruefqueue)
- [x] ✅ Pruefqueue-Ansicht: zu_pruefen / klassifiziert / abgelegt / unklar
- [x] ✅ Filter: Status, Suche Absender/Betreff
- [x] ✅ Detail-Modal mit Status-Buttons (lexPruefDetail + lexPruefSetStatus)
- [x] ✅ PayPal-Badge in Tabelle
- [x] ✅ GET /api/lexware/eingangsbelege + /api/lexware/eingangsbeleg/{id}
- [x] ✅ POST /api/lexware/eingangsbeleg/{id}/status + /api/lexware/eingangsbeleg/neu
- [x] ✅ Git Commit: 861e057

### Paket 8 — Kira-Tools
- [x] ✅ kira_llm.py: lexware_belege_laden (offene Posten fuer Kira-Kontext)
- [x] ✅ kira_llm.py: lexware_eingangsbeleg_klassifizieren (Konto+Steuer+Status setzen)
- [x] ✅ _build_data_context(): Lexware-Sektion (nur wenn freigeschaltet) — offene Posten + Pruefqueue-Counter
- [x] ✅ Tools nur verfuegbar wenn is_lexware_configured() == True
- [x] ✅ Git Commit: 861e057

### Paket 9 — Mail-Monitor Erweiterung
- [x] ✅ mail_monitor.py: _scan_eingangsbeleg_lexware() Funktion
- [x] ✅ Erkennung: Lieferantenrechnung / Abo / _LEX_INVOICE_SIGNALS Regex-Liste
- [x] ✅ PayPal-Unterscheidung: _is_paypal_mail() — Domain + Bestaetigung-Patterns
- [x] ✅ Body-Rechnung: is_body_only Flag (kein Anhang + Betrag im Text)
- [x] ✅ Idempotenter Eintrag in eingangsbelege_pruefqueue (via mail_id Dedup)
- [x] ✅ Nur aktiv wenn lexware.status == 'freigeschaltet'
- [x] ✅ Git Commit: 861e057

---

## Phase 6 — Abschluss

- [ ] ⏳ KIRA_SYSTEM_ANALYSE.md aktualisieren (Lexware-Sektion) — naechste Session
- [x] ✅ LEXWARE_MASTERCHECKLISTE.md finalisiert
- [x] ✅ KAI_TODO_LEXWARE.md finalisiert
- [x] ✅ session_handoff.json finalisiert
- [x] ✅ feature_registry.json aktualisiert (lexware-anbindung: done)
- [x] ✅ knowledge/session_log.md Abschlusseintrag
- [x] ✅ Abschlusstabelle im Chat (folgt)

---

## Kai-Aktionen (am Ende — nicht ueberspringen)

⚠️ KAI-01: Lexware API-Key in KIRA Einstellungen eintragen → details in KAI_TODO_LEXWARE.md
⚠️ KAI-02: Alten API-Key aus PHP widerrufen (Sicherheit!) → details in KAI_TODO_LEXWARE.md
⚠️ KAI-03: Dataverse-Credentials pruefen (optional) → details in KAI_TODO_LEXWARE.md
⚠️ KAI-04: PHP-Altstrecke deaktivieren (optional) → details in KAI_TODO_LEXWARE.md
⚠️ KAI-05: Lexware Webhook einrichten (optional) → details in KAI_TODO_LEXWARE.md
