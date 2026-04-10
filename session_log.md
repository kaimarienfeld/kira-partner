# Session Log

## 2026-04-10 18:16 — Session-Start: CRM Datenbank-Reparatur (session-tt)
**Auftrag:** CRM Kunden-Datenbank Reparatur — Lexware als einzige Stammdaten-Quelle herstellen. 10 Schritte: Bestandsaufnahme, Backup, falsche Kunden löschen, Lexware-Import, Classifier umstellen, retroaktiver Mail-Scan, Settings UI, Doku, Tests, Commit. Autonomer Durchlauf ohne Rückfragen.
**Status:** erledigt

### 2026-04-10 18:45 — Session-Ende
**Erledigt:**
- Schritt 1: Bestandsaufnahme — 1433 falsche Kunden (ALLE aus Mail-Archiv), 0 Lexware-verknüpft
- Schritt 2: Backup kunden.db.backup_vor_reparatur_20260410 (14.9 MB)
- Schritt 3: Alle 1433 falschen Einträge gelöscht (Sicherheitschecks bestanden: 0 Lexware-IDs)
- Schritt 4: kunden_lexware_sync.py NEU — 273 Lexware-Kontakte importiert (128 Firmen, 145 Personen), 285 Identitäten (186 mail, 84 domain, 15 telefon)
- Schritt 5: Classifier auf Lexware-Only umgestellt (_build_kunden_kontext + _fast_path mit WHERE lexware_id IS NOT NULL, Domain-Match Stufe 2), alte Migration in case_engine.py entfernt
- Schritt 6: kunden_mail_retroaktiv.py NEU — 12654 Mails gescannt, 1718 zugeordnet (13.6%), 96 Kunden mit Statistiken aktualisiert
- Schritt 7: CRM-Einstellungen erweitert (Sync-Status, Lexware-Sync-Button, Retro-Scan-Button, 3 neue API-Endpoints)
- Schritt 8: KUNDEN_CLASSIFIER_KONZEPT.md + CRM_TECHNIK_REFERENZ.md + CRM_REPARATUR_ANALYSE.md aktualisiert
- Schritt 9: Alle Tests bestanden (DB-Integrität, Fast-Path, Domain-Match, Newsletter-Filter, Syntax-Check)
- Schritt 10: Git Commit + Tracking
**Offen geblieben:** —

---

## 2026-04-10 13:30 — Session-Start (session-rr)
**Auftrag:** Konsolidierte KIRA_MASTERLISTE.md erstellen — alle Features, Pläne, Bugs, Wünsche und Programmier-Regeln aus 10+ Einzellisten zusammenführen. Sync-Regeln und AGENT.md-Integration.
**Status:** erledigt

### 2026-04-10 14:00 — Session-Ende
**Erledigt:**
- KIRA_MASTERLISTE.md erstellt mit 9 Kapiteln: Sync-Regeln, 13 Programmier-Regeln, 94 fertige Features, 5 teilweise fertige, 9 geplante Module (detailliert mit CRM/Social/Dokumente/Vertrag), ~25 offene Wünsche, aktive Bugs, Kai-Aktionen
- AGENT.md erweitert: Session-Start liest Masterliste, Session-Ende aktualisiert sie (Punkt 9a)
- Geplante Module besonders detailliert: Kunden/CRM mit Projekttrennung, Fallansicht, Akkordeon-Logik; Social/DMs mit Kanal-Strategie; Dokumente mit Studio-Konzept; Vertragsprüfung
**Offen geblieben:** —

---

## 2026-04-09 05:30 — Session-Start (session-qq)
**Auftrag:** Postfach Compose vollwertig machen: Rich-Text-Editor, Modal-Fenstermodus (wie Outlook), Signatur-Integration, Entwurf-Speicherung, Formatierung
**Status:** erledigt

### 2026-04-09 06:00 — Session-Ende
**Erledigt:**
- Quill.js Rich-Text-Editor mit voller Toolbar in Compose eingebaut (Inline + Modal)
- Modal-Fenstermodus mit abgedunkeltem Backdrop (820px, blur)
- Signatur-Auto-Einfügung: Standard-Signatur wird beim Öffnen geladen, Konto-Wechsel ersetzt korrekt
- Zero-Width-Space Marker für Quill-kompatible Signatur-Position (Quill filtert HTML-Kommentare und display:none)
- Entwurf-System: mail_drafts DB-Tabelle + /api/mail/draft/save Endpoint
- Kira-Draft-Button: Mail per /api/kira/chat formulieren lassen
- Inline↔Modal Sync (Felder + Quill-Inhalt)
- body_html wird beim Senden als MIME text/html mitgeschickt
- 0 JS-Fehler, Playwright-verifiziert
**Commit:** 27cc408

### 2026-04-09 06:30 — Dateianhänge + Autovervollständigung
**Erledigt:**
- POST /api/mail/upload-attachments: Multipart-Upload mit UUID-Temp-Speicherung
- _pfDoSend() lädt Anhänge hoch → sendet mit attachment_ids → mail_sender.py bindet als MIME ein
- GET /api/mail/kontakte: 500 bekannte Adressen aus mail_index.db
- HTML datalist auf An/CC/BCC-Feldern (Inline + Modal)
- Playwright-verifiziert: Anhang-Chips sichtbar, Upload-Endpoint funktioniert, 0 JS-Fehler
**Commit:** eb31dca

### 2026-04-09 07:00 — Autocomplete-Fixes + Validierung + Kontakte speichern
**Erledigt:**
- Autovervollständigung: datalist durch eigenes Dropdown ersetzt (erst ab 2 Zeichen, max 12, Pfeiltasten+Escape)
- Gesendete Empfänger: mail_kontakte DB-Tabelle, beim Senden automatisch gespeichert, priorisiert in Suche
- Betreff-Warnung: confirm() statt stummem Abbruch
- Anhang-Vergessen-Check: Textscan auf dt.+engl. Keywords, Warnung wenn Anhang erwähnt aber keiner da
**Commit:** 061ba05
**Offen geblieben:** —

---

## 2026-04-08 23:15 — Session-Ende (session-pp-cont4)
**Auftrag:** Artikel-UI fertigstellen: Beschreibungs-Spalte, Sync-UI, Änderungshistorie, Netto-Preis-Fix, Playwright reparieren.
**Status:** erledigt

### Änderungen:
- `upArtikelLaden()` von 7 auf 8 Spalten erweitert (Beschreibung sichtbar, Last-Sync-Anzeige, Info-Banner)
- 4 neue JS-Funktionen: `upSaveArtikelSync()`, `upArtikelSyncJetzt()`, `upShowHistorie()`, `upExportHistorie()`
- 3 neue API-Endpoints: `GET /api/artikel/historie`, `GET /api/artikel/historie/export`, `POST /api/lexware/sync-artikel`
- `POST /api/config/patch` — universeller Config-Patch-Endpoint (dot-notation Pfade)
- Routing-Bug: `/api/config/patch` aus `_handle_lexware_post()` in `do_POST()` verschoben
- Lexware `netto_preis`-Extraktion gefixt (`price.netPrice` statt `netPrice`)
- `artikel_preishistorie` API liefert jetzt `beschreibung` + `aenderung_typ`
- Playwright repariert (browser_close + navigate)
- Alle Tests bestanden: 0 JS-Fehler, alle Endpoints funktional

### Commits:
- `79db99b` — fix(artikel): Beschreibungs-Spalte + Sync-UI + Änderungshistorie + Netto-Preis-Fix
- `98f7a19` — fix(routing): /api/config/patch aus _handle_lexware_post in do_POST verschoben

---

## 2026-04-08 22:15 — Session-Start (session-oo)
**Auftrag:** Universelle Verknüpfung + Projekt-System — Thread-Awareness im Classifier, Projekt-Vorgänge (typ='projekt'), automatische Zuordnung, 4 Kira Projekt-Tools, CRM-Vorbereitung.
**Status:** erledigt

### Änderungen:
- Phase 1: Thread-Awareness — `_get_mail_verlauf_kontext()` erweitert (thread_id, THREAD-STATUS), `classify_mail_llm()` + `classify_mail()` Signatur erweitert, mail_monitor + daily_check thread_id durchgereicht
- Phase 2: Projekt-Vorgänge — `case_engine.py` erweitert (12 neue Funktionen), `llm_classifier.py` projekt_zuordnung im Classifier-Output, `mail_monitor.py` automatische Projekt-Zuordnung
- Phase 3: Kira-Tools — 4 neue Tools + Handler + Dispatch + System-Prompt in `kira_llm.py`
- Phase 4: CRM-Vorbereitung — AGENT.md §5c aktualisiert, CRM-Kompatibilität dokumentiert
- CRM-Arbeitsanweisung v2 gelesen und Kompatibilität geprüft: Keine separate projekte-Tabelle, stattdessen vorgaenge typ='projekt'

---

## 2026-04-08 17:30 — Session-Start (session-ffff-universal)
**Auftrag:** Universelle Kira-Handlungsfähigkeit — mail_korrektur → korrektur (universal), neue CRUD-Tools, kiraOpenWithContext() für alle Module, Architektur-Regel.
**Status:** erledigt

### 2026-04-08 17:35 — Schritt 1: mail_korrektur → korrektur (universell)
**Was:** Tool umbenannt, Handler universell für task/capture/vorgang/beleg, corrections-Tabelle +entitaet_typ +kanal, Legacy-Alias
**Status:** erledigt

### 2026-04-08 17:40 — Schritt 2: Neue CRUD-Tools
**Was:** task_erstellen, task_bearbeiten, wissen_verwalten (ersetzt wissen_speichern mit erstellen/bearbeiten/deaktivieren)
**Status:** erledigt

### 2026-04-08 17:45 — Schritt 3: kiraOpenWithContext() + alle Buttons
**Was:** Neue universelle JS-Funktion, POST /api/kira/kontext Python-Endpoint (7 Module), 25+ Kira-Buttons migriert (geschKira, lxOpenKiraWithContext, capKiraOpen, lxBelegKira, lxKontaktKira, lxBuchKira, Quick Panel 6×, Geschäft 2×)
**Status:** erledigt

### 2026-04-08 17:50 — Schritt 4: System-Prompt + Klassifizierungs-Regeln
**Was:** STRUKTURELLE FÄHIGKEITEN Sektion im Prompt, Klassifizierungs-Korrekturen in _build_data_context()
**Status:** erledigt

### 2026-04-08 17:55 — Schritt 5: Architektur-Regel
**Was:** AGENT.md §5b Kira-CRUD-Pflicht, wissen_regeln DB-Eintrag (fest/aktiv)
**Status:** erledigt

---
## 2026-04-08 14:00 — Session-Start (session-ffff-intelligenz)
**Auftrag:** Kira Intelligenz-Upgrade — Plan "gleaming-sauteeing-sun" (6 Schritte). Mails wirklich lesen, Aktionen vorschlagen, Follow-ups tracken. Universelle Benutzerprofile statt hardcoded.
**Status:** erledigt

### 2026-04-08 14:05 — Schritt 1: Benutzerprofile
**Was:** get_active_profile() in task_manager.py, Legacy-Fallback, Einstellungen-UI (Firma/Team/Domains)
**Status:** erledigt

### 2026-04-08 14:10 — Schritt 2: Klassifizierer profil-basiert + tiefer lesen
**Was:** llm_classifier.py: Profil-Prompt, Text-Limit 3000→6000, 3 neue LLM-Felder (vorgeschlagene_aktionen, erkannte_termine, mail_zusammenhang), Tiefer-Lesen + Gesendete-Mail-Analyse
**Status:** erledigt

### 2026-04-08 14:15 — Schritt 3: Aktionen bei ALLEN Mails verarbeiten
**Was:** mail_monitor.py: mail_commitments DB-Tabelle, _process_vorgeschlagene_aktionen() + _process_erkannte_termine() VOR Early-Returns
**Status:** erledigt

### 2026-04-08 14:20 — Schritt 4: scan_offene_zusagen() Proaktiv-Scan
**Was:** kira_proaktiv.py: Scan 13, überfällige + bald fällige Commitments, Stufe-B Signale via kira_notify()
**Status:** erledigt

### 2026-04-08 14:25 — Schritt 5+6: UI + kira_llm.py profil-basiert
**Was:** server.py: Benutzerprofile-Sektion, Offene Zusagen Tab, Activity-Feed Kacheln, /api/zusagen. kira_llm.py: System-Prompt + Kontext aus Profil, OFFENE ZUSAGEN Sektion. daily_check.py: Profil-basiert.
**Status:** erledigt

### 2026-04-08 14:30 — Commit
**Commit:** 08fcf7a — feat(kira): Intelligenz-Upgrade — Mails tiefer lesen, Aktionen vorschlagen, Zusagen tracken
**Status:** erledigt

---
## 2026-04-08 14:30 — Session-Ende (session-ffff-intelligenz)
**Erledigt:** Kira Intelligenz-Upgrade ALLE 6 Schritte komplett. 7 Dateien, 758 Insertions, 54 Deletions.
**Offen geblieben:** Playwright-Test der neuen UI-Elemente. Nachklassifizierung mit neuen LLM-Feldern testen.
**Status:** erledigt

---
## 2026-04-03 14:00 — Session-Start (session-cccc-dashboard)
**Auftrag:** Dashboard Live-Redesign implementieren — Plan "whimsical-frolicking-dawn" (6 Phasen). Statisches Server-Side-HTML durch dynamisches Client-Side-JS ersetzen. 3 wählbare Layouts (A: Bento Grid, B: Command Center, C: Smart Cards). JSON-API /api/dashboard/live. Animationen (Count-Up, Stagger, Bounce, Shimmer, Pulse). Auto-Refresh. Einstellungen UI.
**Status:** erledigt (Phasen 1-4 + 6)

### 2026-04-03 14:15 — Phase 1: /api/dashboard/live Endpoint
**Was:** _dashboard_data() Funktion (~200 Zeilen) + GET /api/dashboard/live Handler
**Status:** erledigt

### 2026-04-03 14:30 — Phase 2+3: JS Renderer + Animationen
**Was:** build_dashboard() komplett neu: ~340 Zeilen JS (Animation-Engine + 3 Layout-Renderer + Card-Builder). ~200 Zeilen CSS (.dlive-* Klassen, alle auf CSS-Variablen).
**Status:** erledigt

### 2026-04-03 14:45 — Phase 4: Live Feed
**Was:** Feed aus runtime_events.db + mail_approve_queue + ausgangsrechnungen in _dashboard_data() integriert
**Status:** erledigt

### 2026-04-03 15:00 — Phase 6: Einstellungen UI
**Was:** Layout-Dropdown (A/B/C), Refresh-Intervall (15s-5m/aus), Konfetti-Toggle, Reduzierte Animationen in saveSettings()
**Status:** erledigt

### 2026-04-03 15:15 — Dead Code Entfernung + Playwright-Test
**Was:** 437 Zeilen alter build_dashboard() Body entfernt. Server gestartet, Playwright: 0 JS-Fehler, alle 3 Layouts + beide Themes verifiziert.
**Status:** erledigt

### 2026-04-03 15:30 — Commit
**Commit:** cd25025 — feat(dashboard): Dynamisches Live-Dashboard mit 3 wählbaren Layouts
**Status:** erledigt

### 2026-04-03 15:50 — Phase 5: Activity Window erweitern
**Was:** 3 neue Trigger in activity_window.py: (1) _scan_ueberfaellige_rechnungen() — >14d Stufe B, >30d Stufe C, (2) _scan_kira_freigaben() — pending >2h Stufe B, (3) _scan_neue_leads() — Typ anfrage/lead letzte 2h Stufe B. Cooldown 1h pro Trigger-Typ. _emit_signal() schreibt auch in Case-Engine-DB für Browser-Polling.
**Commit:** 3488d46 — feat(activity): 3 neue Trigger für Activity Window — Phase 5
**Status:** erledigt

### 2026-04-03 16:00 — Listen aktualisiert
**Was:** feature_registry.json: dashboard-ui → "Dashboard Live-Redesign" (aktualisiert), activity-window-multi-trigger (neu). session_handoff.json: session-cccc Eintrag + Phase 5 Features.
**Status:** erledigt

---
## 2026-04-03 16:05 — Session-Ende (session-cccc-dashboard)
**Erledigt:** Dashboard Live-Redesign ALLE 6 Phasen komplett. Activity Window mit 3 neuen Triggern. Listen aktualisiert.
**Offen geblieben:** —
**Status:** erledigt (6/6 Phasen)

---
## 2026-04-03 13:25 — Session-Start (session-dddd-widgets)
**Auftrag:** Dashboard Feed-Widgets implementieren — Windows-Widget-Stil: Live-Wetter, News-Karussell mit Bildern (RSS), Newsletter-Digest von Kira zusammengestellt. Konfigurierbar in Einstellungen. Plan "whimsical-frolicking-dawn" (5 Phasen).
**Status:** erledigt

### 2026-04-03 13:25 — Phase 1: news_feed.py Backend
**Was:** Neues Modul ~350 Zeilen: fetch_weather() (wttr.in), fetch_rss_feeds() (xml.etree), generate_newsletter_digest() (LLM), SQLite TTL-Cache (feed_cache.db), Background-Refresh-Thread
**Commit:** e3d0efc (zusammen mit Phasen 2-5)
**Status:** erledigt

### 2026-04-03 13:25 — Phase 2: server.py API + Import
**Was:** Import news_feed (defensiv), GET /api/dashboard/widgets Endpoint, start_feed_refresh_thread() in run_server()
**Status:** erledigt

### 2026-04-03 13:25 — Phase 3: CSS Widget-Styles
**Was:** ~60 Zeilen .dlive-widget-* CSS: 3-Col Grid (280px 1fr 320px), responsive Breakpoints, Crossfade-Karussell, Gradient-Overlay, Dot-Navigation, Newsletter Shimmer-Border
**Status:** erledigt

### 2026-04-03 13:25 — Phase 4: JS Widget-Renderer
**Was:** weatherWidget(), newsCarousel() (auto-rotate 8s, Crossfade, Dots+Pfeile), newsletterWidget() (Kira-Branding, auto-rotate 10s), renderWidgetStrip(), fetchWidgets() + 5min Refresh
**Status:** erledigt

### 2026-04-03 13:25 — Phase 5: config.json + Einstellungen UI
**Was:** news_feed Sektion in config.json (Wetter/RSS/Newsletter), Einstellungen > Feed-Widgets Sidebar-Sektion (Wetter-Toggle/Standort, RSS-Feed-Liste add/remove, Newsletter-Digest-Toggle/Max), saveSettings() erweitert
**Status:** erledigt

### 2026-04-03 13:25 — Bugfix: Widget-Strip Race-Condition
**Was:** Widget-Strip erschien nicht im DOM — fetchAndRender() überschrieb renderWidgetStrip() bei async Race. Fix: renderWidgetStrip() in renderDashboard() nach Layout-Rebuild integriert.
**Commit:** f1407e0
**Status:** erledigt

### 2026-04-03 13:26 — Playwright-Verifizierung
**Was:** 0 JS-Fehler, alle 3 Widgets sichtbar: Wetter 8°C Düsseldorf, News-Karussell 8 Slides (Spiegel mit Bildern + tagesschau), Newsletter-Digest 3 Kira-Highlights
**Status:** erledigt

### 2026-04-03 13:35 — Kai-Feedback: Signal-Modals
**Auftrag:** Vorgang-Signale (Stufe-C) kamen als hässliches eigenes Modal (5x einzeln). Sollen stattdessen gruppiert im bestehenden Activity-Drawer (Slide-In von rechts) erscheinen.
**Was:** Signal-Polling IIFE komplett umgebaut: (1) Stufe-C → Activity-Drawer mit rot markierter "Aktion erforderlich" Sektion, alle Signale gruppiert. (2) Stufe-B → ein gruppierter Toast statt mehrere einzelne. (3) Altes _vg-modal-overlay + _vg-toast-container komplett entfernt.
**Commit:** 1866d07
**Status:** erledigt

### 2026-04-03 13:38 — To-Do: Feed-Widget Design-Tuning auf nächste Woche
**Was:** 3 Aufgaben (Design-Tuning, weitere RSS-Feeds, Newsletter-Digest Qualität) in Todo_checkliste.md Sektion "NÄCHSTE WOCHE (ab 2026-04-07)" eingetragen
**Status:** erledigt

---
## 2026-04-07 22:00 — Session-Start (session-ffff-kira-reparatur)
**Auftrag:** KIRA Komplett-Reparatur nach Kai's Urlaub — 6 Phasen Nacht-Plan. Alle 26 offenen Tasks zeigten nur "Zur Kenntnis" Button. Keine Konversations-Verknüpfung. "Schon beantwortet" greift nicht. Lernsystem hat Bugs (auto_gelernt ignoriert, harte Limits).
**Status:** erledigt (6/6 Phasen)

### 2026-04-07 22:15 — Phase 0: Daten-Cleanup
**Was:** Python-Script: 7 Tasks als beantwortet markiert (gesendete Mail nach Eingang), 8 Tasks älter 60 Tage erledigt, 5 Thread-IDs nachträglich gesetzt
**Commit:** c15eef6
**Status:** erledigt

### 2026-04-07 22:30 — Phase 1: UI-Buttons
**Was:** _wi_item() in server.py:1702-1724 — kategorie-basierte Buttons (Kira fragen/Erledigt/Später/Ignorieren/Zur Kenntnis) statt nur kenntnis_btn. CSS für .wi-btn-done/.wi-btn-kira/.wi-btn-later/.wi-btn-ign + Dark-Mode
**Commit:** c15eef6
**Status:** erledigt

### 2026-04-07 22:45 — Phase 4: Lernsystem Sofort-Fixes
**Was:** llm_classifier.py: auto_gelernt+stil zu SQL-Filter hinzugefügt (waren komplett ignoriert!), Limits 10→50/12→30, Snippet 120→200 Zeichen
**Commit:** f675be5
**Status:** erledigt

### 2026-04-07 23:00 — Phase 2: Thread-Zuweisung
**Was:** daily_check.py:445-457 — 60-Tage-Fenster statt 30, Betreff-Normalisierung als Fallback (_norm_betreff_dc)
**Commit:** 902024d
**Status:** erledigt

### 2026-04-07 23:10 — Phase 3: Auto-Cleanup
**Was:** _cleanup_answered_tasks() in server.py beim Server-Start + POST /api/tasks/cleanup Endpoint für manuellen Trigger
**Commit:** 546fd99
**Status:** erledigt

### 2026-04-07 23:15 — Phase 5: Relevanz-basierte Auswahl
**Was:** Neue Funktionen _get_kira_wissen_relevant() und _get_correction_beispiele_relevant() in llm_classifier.py. Scoring: Keyword-Overlap 35%, Domain-Match 25%, Absender 15%, Aktualität 10%, Kategorie-Bonus 15%. ALLE Regeln geladen (kein Limit), nach Relevanz sortiert, Zeichenbudget 12k/6k
**Commit:** 546fd99
**Status:** erledigt

### 2026-04-07 23:25 — Phase 6: Korrektur-Konsolidierung
**Was:** Schema-Migration (_ensure_correction_columns): konsolidiert_am in corrections, gewicht+quell_anzahl in wissen_regeln. _consolidate_corrections() in daily_check.py (>=3 gleiche → permanente Regel). Sofort-Konsolidierung im Korrektur-Endpoint (server.py)
**Commit:** 81ef2cd
**Status:** erledigt

---
## 2026-04-07 23:30 — Session-Ende (session-ffff-kira-reparatur, Teil 1)
**Erledigt:** KIRA Komplett-Reparatur ALLE 6 Phasen.
**Status:** erledigt (6/6 Phasen)

---
## 2026-04-07 23:45 — Session-Fortsetzung (session-ffff Teil 2: Bereinigung + Nachklassifizierung)
**Auftrag:** App komplett sauber machen — alle veralteten Tasks/Entwürfe/Angebote/Vorgänge bereinigen. 945 Mails (544 unklassifiziert + 401 regelbasiert) per LLM nachklassifizieren. mail_monitor bei LLM-Ausfall absichern.
**Status:** läuft (Nachklassifizierung im Hintergrund)

### 2026-04-08 00:00 — Phase A: Daten-Cleanup
**Was:** 8 Tasks erledigt (3 bleiben offen: #10, #50, #237), 14 Kira-Entwürfe abgelaufen, 16 alte Angebote archiviert, 16+2 Vorgänge abgeschlossen, RE-SB240038 bezahlt
**Status:** erledigt

### 2026-04-08 00:05 — Phase B: Server-Start Ablauf-Logik
**Was:** _expire_stale_drafts() — 7-Tage-Ablauf für pending Entwürfe beim Server-Start. ablauf_am in Kira-Vorschlag (daily_check.py)
**Status:** erledigt

### 2026-04-08 00:10 — Phase C: Nachklassifizierung
**Was:** reclassify_low_confidence() in daily_check.py (Pause-Logik wie qualify_mails). POST /api/mail/reclassify + GET /api/mail/reclassify/status in server.py. Nachtlauf gestartet für 945 Mails.
**Commit:** 155cdf5
**Status:** läuft (Hintergrund)

### 2026-04-08 00:15 — Phase D: mail_monitor LLM-Ausfall
**Was:** _all_providers_failed Check in _process_mail() — Mail nur indexieren bei LLM-Budget=0, keinen regelbasierten Task erstellen
**Commit:** f1e5e7f
**Status:** erledigt

### 2026-04-08 01:00 — Anhang-Text-Extraktion für Mail-Klassifizierung
**Auftrag:** Mail-Anhänge (PDF, DOCX, ZIP, Bilder) vor LLM-Klassifizierung auslesen. OCR für Bilder, Vision-Fallback wenn OCR keinen Text findet.
**Was:** 5 Phasen implementiert:
- Phase 1: config.json `anhang_extraktion` Sektion (10 Config-Keys) + `anhang_text_cache` SQLite-Tabelle in mail_index.db
- Phase 2: `_extract_attachment_texts()` in llm_classifier.py (~160 Zeilen) — nutzt dokument_pipeline.py (extract_text/extract_text_image), ZIP-Entpackung, base64 Vision-Fallback, DB-Cache. `_build_classification_prompt()` + `classify_mail()` + `classify_mail_llm()` um anhang_texte/anhaenge_pfad erweitert.
- Phase 3: `classify_direct()` in kira_llm.py — `vision_images` Parameter, Anthropic Content-Block-Liste, OpenAI image_url Format-Konvertierung in `_call_openai_compat()`
- Phase 4: mail_monitor.py, daily_check.py (4 Stellen) — anhaenge_pfad ableiten und an classify_mail() übergeben. reclassify_low_confidence() jetzt mit echten Anhängen + Pfad.
- Phase 5: Einstellungen-UI (server.py) — 5 Toggles/Inputs in "Anhang-Extraktion bei Klassifizierung" Gruppe + saveSettings() erweitert
**Verifiziert:** Syntax-Check alle 4 .py-Dateien OK, config.json valide, Server 0 JS-Fehler, alle UI-Elemente im DOM, saveSettings() sendet anhang_extraktion korrekt
**Status:** erledigt

---
## 2026-04-08 10:30 — Session-Start (session-gggg)
**Auftrag:** Crash-Recovery nach Windows-Update-Neustart. Status prüfen + Reklassifizierung (letzte 3 Monate, 195 unklassifizierte Mails mit Anhang-Kontext) vorbereiten zum späteren Starten.
**Status:** erledigt

### 2026-04-08 10:45 — Reklassifizierung mit Zeitfilter vorbereitet
**Was:** (1) daily_check.py: `reclassify_low_confidence(seit="")` — optionaler `seit`-Parameter für Datum-Filter in SQL-Query. (2) server.py POST /api/mail/reclassify: liest `seit` aus Body, übergibt an Thread. (3) Einstellungen-UI: Neuer Button "Unklassifizierte mit Anhängen nachqualifizieren" mit Datum-Input (Default: 3 Monate zurück), Progress-Anzeige, Polling alle 3s. JS-Funktion `esMailReklassifizieren()`.
**Status:** erledigt

### 2026-04-08 11:00 — Kira Background-Status-Chip in Header-Leiste
**Was:** (1) GET /api/kira/background-status — kombinierter Endpoint: prüft Reklassifizierung, Nachklassifizierung, Qualifizierung, Mail-Monitor. Gibt `jobs[]` Array zurück. (2) HTML: `kiraBgChip` im Header nach Kira-Live-Chip. Spinner + Text, nur sichtbar wenn Jobs aktiv. (3) CSS: Lila Gradient-Background, Shimmer-Animation, Mini-Spinner (12px), `kira-bg-pct` für Prozent-Anzeige. (4) JS: `_pollBgStatus()` alle 5s, läuft durchgehend (auch bei minimiertem Tab).
**Status:** erledigt

### 2026-04-08 11:30 — tkinter Popup deaktiviert + Signal-Scanner im Server
**Was:** (1) `start_signal_watcher()` (tkinter Desktop-Overlay) deaktiviert — das war die Ursache für das hässliche "KIRA — Aktion erforderlich"-Fenster das alle ~1h mit gleichen Daten kam. (2) Neuer `_signal_scanner_loop` Thread im Server: nutzt die bestehenden Scan-Funktionen (Rechnungen, Leads, Freigaben) aus activity_window.py, schreibt Signale in Case-Engine-DB → Browser Activity-Drawer zeigt sie. (3) **4h Cooldown** statt 1h, im Server-Thread-RAM (überlebt Scan-Zyklen, reset bei Server-Neustart — was OK ist da neue Infos kommen könnten). (4) Scan-Funktionen in activity_window.py: eigener _cooldown_ok()-Check entfernt (Server-Thread macht das jetzt zentral). (5) Scan alle 5 Minuten, aber dank Cooldown maximal 1 Signal pro Thema alle 4h.
**Status:** erledigt

### 2026-04-08 12:30 — Activity-Drawer Komplett-Redesign (Windows 11 Widget-Style)
**Was:** Kompletter Umbau des Activity-Drawers:
- **Backend:** `_ensure_activity_dismissed_table()` in tasks.db (item_key UNIQUE, dismissed_at, revived_at). GET /api/kira/activity-feed — sammelt individuelle Items aus 4 Quellen (Rechnungen, Leads, Freigaben, Signale), filtert dismissed, Begrüßung nach Tageszeit. POST /api/kira/activity-feed/dismiss — markiert Items als dismissed.
- **HTML:** Neuer Drawer mit Kira-Avatar, Begrüßungszeile, Grid-Container. Header-Button `#kdHeaderBtn` mit Badge neben Neustart.
- **CSS:** Glass-Effekt (backdrop-blur 24px, semi-transparent BG), 14px border-radius Kacheln in 2-Spalten-Grid, Priority-Farben (rot/gelb/neutral), Hover-Lift, Dismiss-Animation (scale+translateX+opacity), Einsaug-Animation (kd-sucking: scale(.2)+translateX(80%)+border-radius:50%), Loading-Dots, Header-Button mit Pulse.
- **JS:** `kiraActivityDrawerOpen()` mit Ausblas-Effekt, `kiraActivityDrawerClose()` mit Einsaug-in-Header-Button + Pulse. `_kiraDrawerLoad()` fetcht activity-feed API. `_kdRenderTiles()` baut individuelle Kacheln mit X-Dismiss, Kira-says, Action-Links. `_kdDismiss()` animiert + POST. Auto-Minimize nach 60s. Badge-Polling alle 30s.
- **Kira-says:** Template-basiert pro Item-Typ (kein LLM nötig).
- **Revival:** Rechnungen kommen nach config.activity_feed.revival_tage (Default 7) wieder wenn noch offen. Einstellbar.
**Status:** erledigt

---

## 2026-04-09 08:30 — Session-qq-cont4: Universal Learning + CRM-Notizen
**Auftrag:** Kais Anforderung: "Kein Button ohne Hinterlegen — jede Aktion muss für CRM/Kundenhistorie erfasst werden, damit Kira lernt und später im CRM steht was gemacht wurde, nicht nur Erledigt+Datum."

### Fixes (3 Commits: 014f6fa, aab9f3d, 20cc368):
1. **Task-Persistence-Bug** (014f6fa): kira_proaktiv.py _task_exists() Status-Filter entfernt + Kaskaden-Status-Änderung für Lead-Erinnerungen
2. **Korrektur-Aktionsvorschlag** (aab9f3d): LLM generiert Aktionsvorschlag + Antwort-Entwurf statt nur "Korrektur gespeichert". In-Place Preview statt location.reload()
3. **Universal Notiz/Learning** (20cc368):
   - _doStatusChange: sendet notiz+einstufung → Task-Datensatz
   - saveIgnorieren: Grund als notiz
   - multiAction: prompt()-Dialog für Sammelkommentar
   - capMarkErledigt/capArchivieren: prompt()-Dialog + payload_json
   - _zusageErledigt/_zusageVerschieben: prompt()-Dialog + ALTER TABLE notiz
   - quickErledigt/quickKenntnis: Default-Notiz statt leer
   - mailApproveAction reject: prompt() für reject_reason
**Status:** erledigt

## 2026-04-09 09:10 — session-qq-cont5: Preview-Persistenz behoben
**Auftrag:** Vorschaufenster bleibt nach Entfernung/Ordnerwechsel stehen — muss geleert werden + Einstellung next/none
**Änderungen:**
1. `_pfClearPreview()` bei jedem Ordnerwechsel (4 Funktionen)
2. `_pfAfterItemRemoved()` zeigt nächste Mail oder leere Vorschau
3. `pfBulkDelete` + `pfVerschiebenNach` nutzen `_pfAfterItemRemoved`
4. Neue Einstellung "Nach Entfernung aus Liste" (next/none) unter Mail > Postfach
5. Config `mail_postfach.after_remove` wird geladen + gespeichert
**Git:** 8064d32
**Status:** erledigt

## 2026-04-09 09:30 — session-qq-cont6: Kira Chat-Kontext Fix
**Auftrag:** Kira verliert nach jeder Antwort den Kontext — bei Folgefragen ("Ja, plane das bitte so ein") antwortet sie "Du musst mir schon etwas mehr Kontext geben"
**Root-Cause:** `_call_anthropic()` + `_call_openai_compat()` starteten immer mit nur 1 Nachricht (aktuelle User-Message). Die in `kira_konversationen` gespeicherte History wurde nie an die LLM-API übergeben.
**Fix:**
1. `chat()` lädt bisherige Session-Messages aus DB nach `_save_message()`
2. Max 20 Nachrichten (konfigurierbar via `llm.kontext_nachrichten`)
3. Letzte User-Msg abgeschnitten (wird von `_call_*` selbst hinzugefügt)
4. Anthropic: History vor aktuelle Nachricht im messages-Array
5. OpenAI: History nach System-Prompt, vor aktuelle Nachricht
**Git:** b026baf
**Status:** erledigt

### 2026-04-09 09:50 — Chat-Gedächtnis Einstellungen-UI + Checklisten
**Auftrag:** Einstellung für kontext_nachrichten in Einstellungen-UI + auf Checklisten aufnehmen (Chat-Projekte wie OpenAI)
**Änderungen:**
1. Neue Gruppe "🧠 Chat-Gedächtnis" in Einstellungen > Kira/LLM mit:
   - Verlauf speichern Toggle (dimmt Details wenn deaktiviert)
   - Slider 2–50 Nachrichten mit Live-Token-Kosten-Anzeige (farbcodiert grün/gelb/rot)
   - Gradient-Leiste + Erklärungs-Karte (2–10 kurz / 20 Standard / 30–50 lang)
2. saveSettings() speichert `llm.kontext_nachrichten`
3. feature_registry: `kira-chat-kontext` (done) + `kira-chat-projekte` (planned)
4. Todo_checkliste §6b-2: 3× ✅ done, 3× 📋 planned (Projekte, Suche, Export)
5. Weitere Todos: Chat-Projekte vorgemerkt
**Git:** 2aee293
**Status:** erledigt

## 2026-04-09 10:30 — session-qq-cont7: E-Mail-Darstellung wie Outlook
**Auftrag:** Mails sehen in KIRA komplett anders aus als in Outlook — fehlende Bilder, kaputtes Layout, nur Text statt HTML
**Root-Cause:** `_parse_eml_content()` entfernte `<style>`, `<meta>`, `<link>` Tags bei der Sanitierung → gesamtes CSS-Layout ging verloren. Inline-Bilder (`cid:`) wurden nicht aufgelöst.
**Fixes:**
1. Sanitierung: `<style>`/`<meta>`/`<link>` beibehalten (iframe sandbox isoliert bereits)
2. `cid:` Inline-Bilder → `data:` base64 URLs eingebettet (max 2MB/Bild)
3. iframe: responsive CSS injiziert (`img max-width:100%`, `table max-width`)
4. Links öffnen in neuem Tab (`<base target="_blank">`)
5. `mail.json` HTML-Fallback wenn EML kein HTML hat
6. Kommunikations-Modul `readMail()`: iframe statt `textContent` für HTML-Mails
**Git:** d74de77
**Status:** ⚠️ NICHT AUSREICHEND — EML-Fix allein reicht nicht (s. cont8)

## 2026-04-09 17:20 — session-qq-cont8: IMAP-Direktabruf für E-Mail-Rendering
**Auftrag:** E-Mails sehen immer noch falsch aus (cont7-Fix hat nichts geändert). Kai: "was ist mit der direkt anzeige über die smtp verbindung.. ich denke das eigene zusammenstellen oder nachbilden der mails bringt auf dauer immer probleme"
**Diagnose:**
- Letzte 50 Mails haben KEIN `mail_folder_pfad` (leer) → keine EML-Dateien vorhanden
- `mail_archiv.pfad` in config.json war leer → _save_to_archive() speicherte nichts
- `_extract_text()` speichert nur text/plain in DB (HTML wird verworfen via `strip_html()`)
- 12.500+ Mails nur mit text_plain, kein HTML → cont7-Fix griff nie
**Fix: IMAP-Direktabruf**
1. `_fetch_mail_html_from_imap()` — neue statische Methode in server.py
   - IMAP-Verbindung per `imap_connect()` aus mail_monitor (OAuth2/Password)
   - SEARCH HEADER Message-ID → FETCH RFC822
   - Parse mit cid:-Inline-Bilder-Auflösung + HTML-Sanitierung
   - Probiert bis zu 7 IMAP-Ordner (INBOX, Sent Items, etc.)
2. `_read_mail()` erweitert: IMAP als 3. Fallback nach EML und kunden.db
3. Ladeindikator mit Spinner statt nur "Lade..."
**Playwright-Test:** LinkedIn (Logo+rote Badges ✓), Finom (Logo+Layout ✓), business-wissen.de (Logo+Formatierung ✓), rauMKult Formulare/Akademie/Betonkosmetik (Dark-Theme ✓)
**Git:** 76c0fb0
**Status:** ✅ erledigt — alle Mails rendern jetzt wie in Outlook

### 2026-04-09 16:00 — Postfach Preview-Height + Vollbild-Modal Bugfixes (session-qq-cont9)
**Auftrag:** 3 Bugs aus cont8 fixen: (1) Preview bleibt weiß, (2) Maximize-Button im Modal fehlt, (3) JS-Fehler bei Antworten aus Modal
**Root-Cause Preview-Bug:** display:none auf hint-section + attachment-section entfernt diese aus dem Grid-Flow → pf-content-section rutscht von Row 4 (1fr) auf Row 2 (auto=38px) → 0px Höhe für pf-prev-body
**Fix:**
1. grid-row:4 auf .pf-content-section — erzwingt korrekte Grid-Zeile unabhängig von display:none-Geschwistern
2. Maximize/Restore Button im Modal-Titlebar — pfReadModalToggleMax() toggled .maximized CSS-Klasse (100vw/100vh)
3. Reply aus Modal: pfReply()/pfReplyAll()/pfForward() direkt aufrufen statt Panel-Button-Click
**Playwright-Test:** LinkedIn-Mail Preview ✓ (HTML mit Bildern), Vollbild-Modal ✓, Maximize/Restore ✓, Antworten ohne JS-Fehler ✓, 0 Console-Errors
**Git:** 8cb7234
**Status:** ✅ erledigt

### 2026-04-09 22:00 — Partner-View --auto Modus (session-qq-cont13)
**Auftrag:** generate_partner_view.py --auto Modus einbauen: vollautomatisch HTML regenerieren, GitHub API Push, Feature-Erkennung, Mail+ntfy an Leni (max 1x/Tag), technische Pushes ohne Mail
**Änderungen:**
1. `generate_partner_view.py`: --auto Modus komplett implementiert
   - GitHub API Push via REST (GET SHA → PUT Content) — kein lokaler Clone nötig
   - Feature-Change-Erkennung (Snapshot vs. aktuell, neue Features + Status-Wechsel)
   - HTML-Template-Versand (benachrichtigung.html) via mail_monitor.send_system_mail()
   - ntfy Push an Kai + Leni (wenn konfiguriert)
   - 1x/Tag-Limit (persistent in partner_auto_state.json)
   - Technische Pushes (ohne Feature-Änderungen) → kein Mail/ntfy
2. `knowledge/partner_auto_state.json`: neuer persistenter State (Feature-Snapshot + last_mail_date)
**End-to-End Test:**
- Lauf 1: GitHub Push ✓ (Commit 52aef7f), 68 Features erkannt (erster Snapshot), Mail ✓ (info@raumkult.eu → marlenabraham@gmail.com, BCC info@), ntfy ✓
- Lauf 2: HTML identisch → kein Push, keine Änderungen → keine Mail (korrekt)
**Status:** ✅ erledigt

### 2026-04-10 09:00 — Postfach Kaskaden-Bug + Einstellungen-Schutz (session-qq-cont14)
**Auftrag:** (B) Favoriten-Ungelesen: Klick auf 1 Mail markiert ALLE als gelesen. (C) Einstellungen werden bei Systemarbeit zurückgesetzt (mail_monitor inaktiv, lese_markierung wechselt zu sofort etc.)
**Änderungen:**
1. **Kaskaden-Bug behoben** (Commit 411f250): `_pfAutoSelected` Flag verhindert dass auto-selektierte Mails in Ungelesen-Ansicht als gelesen markiert werden. Kette: pfOpenMail→pfDoMarkRead→_pfAfterItemRemoved→pfOpenMail wird unterbrochen.
2. **Einstellungen-Schutz** (Commit 5a8c8a8): `saveSettings()` komplett auf null-sichere Helfer umgebaut (`_v/_c/_i/_f`). Fehlende DOM-Elemente → null → `_stripNulls()` entfernt sie → Backend `_deep_merge()` überspringt null → bestehende Config-Werte bleiben erhalten. ~80 `getElementById`-Muster ersetzt.
**Verifiziert:** Config intakt — mail_monitor.aktiv=true, lese_markierung=manuell, after_remove=none, intervall=900
**Offen:** mail_favorites=[] (leer durch Kaskaden-Bug, muss Kai neu setzen), Ungelesen-Zähler erholen sich bei neuen Mails
**Status:** ✅ erledigt

### 2026-04-10 10:15 — Kira-Entwürfe: Voller Compose-Editor (session-qq-cont14)
**Auftrag:** Kira-Entwürfe "Bearbeiten" soll identisch aussehen wie "Neue Mail" — Quill-Editor, Kontoauswahl, Signatur, Formatierung
**Änderungen:**
1. `pfKiraMailBearbeiten()`: Öffnet jetzt den Compose-Modal (pf-compose-modal-overlay) statt simples Textarea-Modal. Vorbefüllt mit Draft-Daten (Von, An, Betreff, Body als HTML/Plain), Signatur wird automatisch eingefügt.
2. `_pfKiraEditId` globale Variable: Steuert ob `pfSendModal()` über approve-API sendet statt normale send-API.
3. `pfSendModal()`: Erkennt Kira-Drafts und sendet über `/api/mail/approve/{id}` mit `action:'edit'` + `body_html`.
4. Backend: `body_html` wird aus Request gelesen und an `send_mail()` weitergereicht.
5. `pfComposeModalMinimize/Close`: Reset von `_pfKiraEditId`.
**Commit:** ed4c325
**Status:** ✅ erledigt

### 2026-04-10 10:45 — Kira-Entwürfe: 3 UI-Fixes (session-qq-cont14)
**Auftrag:** (1) Preview-Panel reißt rechts aus. (2) HTML-Formatierung geht im Editor verloren. (3) Kira-Entwürfe-Liste sieht anders aus als normales Postfach.
**Änderungen:**
1. **Preview-Overflow behoben**: Kira-Vorschau nutzt jetzt scrollbaren Body statt `iframe-mode` mit `position:absolute`. iframe.onload passt Höhe automatisch an.
2. **HTML-Formatierung erhalten**: `body_plain` wird pro Zeile als eigenes `<p>`-Element in Quill geladen statt als ein Fließtext-Block.
3. **Kira-Listen-Optik identisch mit Postfach**: `pfRenderKiraMailItem` nutzt jetzt `pf-item-avatar` + `pf-item-body` + `pf-item-row1/betreff/row3`-Struktur. Datums-Gruppen (Heute/Gestern/Diese Woche/Älter), `pfFormatDatum` (Di 14:03 / 02.04.), Kira+Status-Badges.
**Commit:** 5b73053
**Status:** ✅ erledigt

---

## 2026-04-10 12:00 — Session-Start (session-ss)
**Auftrag:** Kunden/CRM/Kundencenter Vollausbau — 8 Pakete gemäß PROMPT_Kunden_CRM_v2_FINAL.md implementieren. Plan erstellen, bestätigen, dann ohne Stopp alles implementieren.
**Status:** erledigt

### 2026-04-10 12:30 — Paket 1 ✅ Plandateien + Gap-Analyse
7 Plandateien in Plan Kundenmonitor/ erstellt.

### 2026-04-10 12:45 — Paket 2 ✅ Datenmodell + LLM-Projekt-Classifier
6 DB-Tabellen, kunden_classifier.py (~400 LOC), Geschäftskontakt-Filter, Classifier-Integration. Commit 9bc5594.

### 2026-04-10 13:30 — Paket 3-7 ✅ Navigation + UI + API + Funktionspflicht
build_kunden() mit 2-Spalten-Layout, 5 Sub-Panels, ~150Z CSS, ~500Z JS, 20+ API-Endpoints. Akkordeon-Übersicht, Kundenakte mit Projekt-Zeitstrahl, Fallansicht mit Timeline, alle Aktionen verdrahtet.

### 2026-04-10 14:15 — Paket 8 ✅ Kira + Einstellungen + Tour
7 neue Kira-Tools + Handler, CRM-Kontext im System-Prompt, 5 Quick-Actions, CRM-Einstellungssektion (10 Optionen) in Einstellungen, 13+ elog-Events, Guided Tour (6 Schritte). Fix: _read_json_body → body-Parameter.

### 2026-04-10 14:30 — Fortsetzung (Kontext-Recovery)
do_PUT-Bug behoben (Alias do_PUT=do_POST in DashboardHandler). Export-API GET /api/crm/faelle/{id}/export implementiert (Streitfall-Dossier mit Kunde/Projekt/Aktivitäten/Classifier-Log). crmFallExport() JS mit Modal (JSON-Export + Streitfall-Markierung + Kopieren + Herunterladen). feature_registry.json +4 CRM-Einträge (106 total). KIRA_SYSTEM_ANALYSE.md Sektion 8.5 + Modul-Inventar + Changelog. KUNDEN_MASTERCHECKLISTE.md alle Punkte abgehakt.

### 2026-04-10 15:00 — Session-Ende
**Erledigt:** Kunden/CRM Modul vollständig implementiert (Paket 1-8 + Abschluss). ~3400 LOC total. do_PUT-Bug, Export-API, Streitfall-Dossier. Alle Tracking-Dateien aktualisiert.
**Offen geblieben:** —
**Status:** ✅ erledigt

---

## 2026-04-10 19:30 — Session-Start: CRM Lead-Flow + Nachqualifizierung (session-tt2)
**Auftrag:** 000_PROMPT_CRM_LeadFlow_Nachqualifizierung.md ausführen — 3-Stufen Lead-Flow für neue Kontakte + retroaktive Kundenakte-Befüllung + nachträgliche Zuordnung. Autonomer Durchlauf.
**Status:** erledigt

### Paket 1 — DB: kunden_ignoriert + tasks.metadata_json
- kunden_ignoriert Tabelle in kunden.db erstellt (mit Indexes)
- tasks.metadata_json Spalte hinzugefügt (ALTER TABLE)
- case_engine.py _ensure_crm_tables() um kunden_ignoriert erweitert

### Paket 2 — 3-Stufen Lead-Flow in kunden_classifier.py
- Ignoriert-Check vor LLM-Aufruf (absender in kunden_ignoriert → STOP)
- Stufe 1: Auto-Lead (confidence >= Schwelle, Anfrage-Signale erkannt)
- Stufe 2: Kai fragen (confidence 0.50-Schwelle, Aufgabe mit Ja/Nein/Nie-wieder)
- Stufe 3: Still ignorieren (kein Geschäftsfall)
- _lead_aus_mail_anlegen() + _lead_bestaetigung_aufgabe()
- lead_bestaetigen(), lead_manuell_anlegen(), absender_ignorieren()
- get_ignorierte(), absender_reaktivieren()

### Paket 3 — Retroaktive Nachqualifizierung
- _nachqualifizierung_starten() — asynchroner Thread
- _nachqualifizierung_ausfuehren() — durchsucht alle Quellen
- _scan_mail_archiv() — Mail-Index nach E-Mail-Match
- _scan_tasks() — Tasks nach Absender-Bezug
- _scan_lexware_belege() — Angebote/Rechnungen aus Lexware
- _update_kunden_stats() — Kunden-Statistiken aktualisieren
- Integration in kunden_lexware_sync.py (bei neuen Kunden)

### Paket 4 — 5 neue API-Endpunkte
- POST /api/crm/lead-bestaetigen
- POST /api/crm/lead-manuell
- POST /api/crm/absender-ignorieren
- POST /api/crm/kunden/{id}/nachqualifizieren
- POST /api/crm/kunden/{id}/lexware-anlegen (Rücksync)
- _api_crm_kunden_create erweitert (Nachqualifizierung)

### Paket 5 — UI
- Lead-Bestätigungs-Buttons in task_card (metadata_json.typ=lead_bestaetigung)
- "Als Kunden anlegen" Button im Postfach Preview-Toolbar (pf-tb-lead)
- pfAlsLeadAnlegen() + postfachAlsLeadMarkieren() + crmLeadManuellSpeichern()
- Nachqualifizierung-Checkbox im CRM Neuer-Kunde-Formular
- Lexware-Hint in Kundenakte (wenn keine lexware_id)
- Nachqualifizieren-Button in Kundenakte-Header

### Paket 6 — Einstellungen + Kira-Tools + Runtime-Log
- Lead-Erkennung Sektion (5 Optionen: Auto-Lead, Kai-fragen, Schwelle, Auto-NQ, Ignorierte)
- saveSettings() erweitert (4 neue CRM-Keys)
- 4 neue Kira-Tools: crm_lead_anlegen, crm_nachqualifizierung_starten, crm_absender_ignorieren, crm_ignorierte_anzeigen
- elog-Events: lead_automatisch_angelegt, lead_bestaetigung_aufgabe, lead_bestaetigt_ja/nein, absender_ignoriert, nachqualifizierung_gestartet/abgeschlossen, lexware_ruecksync_ok/fehler

### Paket 7 — Tests
- DB-Integrität: kunden_ignoriert ✓, metadata_json ✓, Lexware-Check (273/273) ✓
- Classifier-Funktionen: Import ✓, _extract_name ✓, _confidence_to_score ✓, ist_geschaeftskontakt ✓
- Ignorieren/Reaktivieren: Round-Trip ✓
- Kira-Tools: Alle 4 OK ✓
- Lead-Anlegen: Erstellen ✓, Duplikat-Check ✓, Identitäten (mail+domain) ✓
- Syntax: kunden_classifier.py ✓, server.py ✓, kira_llm.py ✓, case_engine.py ✓

### 2026-04-10 20:00 — Session-Ende
**Erledigt:** CRM Lead-Flow + Nachqualifizierung vollständig implementiert (7 Pakete).
**Offen geblieben:** —
**Status:** ✅ erledigt

---

## 2026-04-10 22:00 — Session-Start (session-uu)
**Auftrag:** CRM Vollausbau v3 — `000_PROMPT_CRM_Vollausbau_v3_FINAL.md` prüfen, Fehlendes einbauen/ergänzen. Danach CRM_TECHNIK_REFERENZ.md + alle Checklisten/Featurelisten/Partnerlisten aktualisieren. GitHub Push mit Benachrichtigung.
**Status:** offen

### 2026-04-10 22:10 — Gap-Analyse
7-Paket-Prompt gegen bestehenden Code geprüft. Fehlend: 2 DB-Tabellen, erweiterter Super-Prompt, Handlungsmatrix, Clustering, Lernschleife, 8 API-Endpunkte, 6 Kira-Tools, UI-Erweiterungen, Tour-Upgrade.

### 2026-04-10 22:30 — Paket 1: DB (kunden_identitaeten_graph + kunden_lernregeln)
2 neue Tabellen in `_ensure_crm_tables()` (case_engine.py). 11 Spalten je Tabelle. DB verifiziert: 11 Tabellen.

### 2026-04-10 22:50 — Paket 2-4: Classifier v3
kunden_classifier.py: ~600 neue LOC. 3-Fragen-Super-Prompt, numerische Confidence, Handlungsmatrix, Clustering, Lernschleife, 16 neue Funktionen.

### 2026-04-10 23:10 — Paket 5: UI-Erweiterungen
server.py: Identitäten-Tab, Projekt-Zeitstrahl visuell, Korrektur-Dialog, 10 JS-Funktionen, 5 CSS-Klassen, Identitäts-Konfidenz-Indikator in Kundenliste.

### 2026-04-10 23:20 — Paket 6: API-Endpunkte (8 neue)
Clustering-Vorschlag/-Anwenden, Korrektur, Identitäts-Bestätigung, Lernregeln CRUD.

### 2026-04-10 23:30 — Paket 7: Kira-Tools + Einstellungen + Tour
6 neue Kira-Tools, Einstellungen (Identitätsauflösung + Lexware-Sync), saveSettings() erweitert, Tour 6→9 Schritte.

### 2026-04-10 23:45 — Tests + Tracking
Syntax-Checks: 4/4 OK. DB: 11 Tabellen OK. CRM_TECHNIK_REFERENZ.md vollständig aktualisiert. session_handoff.json + session_log.md aktualisiert.

### 2026-04-10 23:50 — Session-Ende
**Erledigt:** CRM Vollausbau v3 komplett — 2 DB-Tabellen, 600 LOC Classifier, 8 API-Endpunkte, 6 Kira-Tools, UI (Identitäten/Zeitstrahl/Korrektur), Tour 9 Schritte, Technik-Referenz aktualisiert.
**Offen geblieben:** Browser-Live-Test, feature_registry.json, partner_view.
**Status:** ✅ erledigt

---

## 2026-04-11 00:15 — Session-Start (session-uu2)
**Auftrag:** CRM Nachbesserung + Innovationen v4 — 5 fehlende Punkte nachholen + 5 Innovationen einbauen
**Status:** erledigt

### 2026-04-11 14:25 — Session-Ende
**Erledigt:**
- Block A (5 fehlende Punkte): A-1 kunden_ignoriert Domain-Check, A-2 Runtime-Log Events, A-3 Retroaktiv-Scan UI, A-4 PDF-Export, A-5 Quick-Actions + Handlungsregeln
- Block B (5 Innovationen): B-1 Health Score (kunden_health.py + API + UI + Kira-Tool), B-2 Schreibstil-Fingerprinting (LLM, 7d-Cache), B-3 Sentiment-Trend (Score + 30/30-Tage-Vergleich), B-4 Cross-Channel Thread-Linking (72h LLM), B-5 Next-Best-Action (15min-Cache + NBA-Banner)
- 10 neue DB-Spalten (6 kunden + 4 kunden_aktivitaeten)
- 3 neue API-Endpunkte, 2 neue Kira-Tools, 5 neue Einstellungen
- feature_registry.json: 5 neue Features (114 total)
- CRM_TECHNIK_REFERENZ.md v4-Sektion
- Alle 5 Python-Dateien syntax-clean
**Offen geblieben:** —
**Status:** erledigt
