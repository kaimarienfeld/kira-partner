# Session-Log — Crash-Backup & Auftrags-Protokoll

> Append-only. Wird automatisch ohne Nachfrage geschrieben.
> Zweck: Crash-Recovery. Beim Start immer letzten Eintrag prüfen!

---

## 2026-03-29 22:15 — Session-Start (session-y)

**Auftrag:** Continuation Session: Mail-Bug beheben (keine neuen Mails kommen an), WhatsApp Einstellungen fehlen in Integrationen, Kira System tot → beheben. + Mail & Konten Einstellungen Komplett-Overhaul mit Konto-Karten, Stats, Buttons, Archiv-Panel, IMAP-Ordner.
**Status:** erledigt

---

**Erledigt:**

- \_process_mail() Bug behoben: \_index_mail() wird jetzt immer aufgerufen (auch Newsletter/Ignorieren)
- State-Rollback: alle Konten last_uid -50 für Re-Fetch
- WhatsApp Business Cloud API vollständig implementiert (GET Hub-Verifizierung, POST HMAC-SHA256)
- Mail & Konten UI Komplettumbau: Konto-Karten mit echten Stats, Abrufen/Testen/Token-Buttons, Archiv-Panel
- Integrationen-Sektion: WhatsApp-Konfigurationsformular
- ISS-015: GET /api/einstellungen 404 behoben
- Alle Tracking-Dateien aktualisiert (session_handoff, known_issues, feature_registry, server_map, AGENT.md)
  **Offen geblieben:** Konto-Löschen im UI nur Toast (nicht vollständig verdrahtet). WhatsApp-Token muss Kai noch eintragen.
  **Status:** erledigt

---

## 2026-03-29 22:35 — Session-Start (session-z)

**Auftrag:** AGENT.md Regeln erweitern: 5 neue Regeln (session_log Crash-Backup, Feature-Listen-Sync, Partner View Ende-Pflicht mit Mail-Fehler-Meldung, Todo_checkliste Pflicht).
**Status:** offen

### 2026-03-29 22:40 — Neue Teilaufgabe

**Auftrag:** Korrekturen an den 5 Regeln: (1) Alle Dateien immer mit Datum+Uhrzeit. (2) session_log.md auch mid-session befüllen nach Schema. (3) Crash-Recovery ohne Nachfragen — selbst rekonstruieren. (4) Partner-View Regel 3 automatisch (kein Nachfragen).
**Status:** erledigt

## 2026-03-29 22:42 — Session-Ende (session-z)

**Erledigt:** AGENT.md vollständig aktualisiert mit 5 neuen Regeln + 4 Korrekturen. session_log.md Datei erstellt. MEMORY.md aktualisiert. Alle committed.
**Offen geblieben:** —
**Status:** erledigt

---

## 2026-03-29 05:30 — Session-Start (session-aa)

**Auftrag:** Regeln aus AGENT.md ausführen als wäre es ein neuer Auftrag — alle Session-Start-Schritte durchführen und Kai zeigen was gemacht wurde.
**Status:** erledigt

## 2026-03-29 05:35 — Session-Ende (session-aa)

**Erledigt:** Alle 6 Session-Start-Schritte ausgeführt. session_log.md gelesen (kein Crash). Auftrag eingetragen. feature_registry abgeglichen (42 Features, done=26). Todo_checkliste.md Abschnitt 7+8 aktualisiert (session-y Änderungen eingetragen). Partner-View lokal generiert — kein Push (keine leni_visible Features geändert diese Session).
**Offen geblieben:** —
**Status:** erledigt

---

## 2026-03-29 23:05 — Session-Start (session-bb)

**Auftrag:** (1) Neue AGENT.md Regel: change_log.jsonl vor jeder neuen Aufgabe aufgabenbezogen prüfen. (2) Mail-Login Umbau laut Arbeitsanweisung `_archiv/arbeitsanweisung_Mail-Micration-login.md`: Microsoft-Login produktgerecht umbauen (zentrale Kira-App a0591b2d), neuer Konto-Assistent im Mailbird-Stil, Bestehende Konten erhalten + Reconnect-Funktion, echte Verbindungsampel (grün/gelb/rot) in Einstellungen+Postfach+Sidebar. Zusatz von Kai: Verbindung zur registrierten Microsoft-App testen.
**Status:** erledigt

---

**Erledigt:**

- AGENT.md: Session-Start Step 7 — change_log.jsonl aufgabenbezogen prüfen (neues Kapitel 1e)
- MSAL OAuth mit zentraler KIRA Entra App (a0591b2d): \_msal_app_kira(), start_oauth_browser_flow(), get_oauth_job_status()
- 3-stufige Provider-Erkennung: Stage1 (Domain-Heuristik) → Stage2 (DNS-MX/Autodiscover) → Stage3 (MS OpenID-Probe) — detect_provider_advanced()
- Mailbird-Stil 6-Schritt-Konto-Assistent: Overlay-Wizard, Anbietererkennung mit Stufen-Fortschritt, Expert-Mode (IMAP/Exchange/EWS/POP3), OAuth-Browser-Flow
- Exchange/EWS-Protokoll im Expert-Schritt: \_wizProtoChange() zeigt EWS-Server-Feld dynamisch
- Echte Verbindungsampel (grün/gelb/rot): run_full_connection_test() IMAP+SMTP+30s Roundtrip, check_account_health() Background-IMAP, Ampel in Einstellungen/Postfach/Sidebar
- Reconnect-Funktion für bestehende Konten (start_oauth_browser_flow mit existierendem Konto)
- Microsoft App Test: /api/mail/microsoft-app/test → OIDC-Endpoint Prüfung
- Health-Check: 30-Minuten-Intervall (war 8s), 15s initiales Refresh nach Page-Load
- Wizard Hintergrund fest/opak (kein transparent, kein backdrop-filter)
- info@raumkult.eu korrekt als Microsoft erkannt via DNS-MX-Prüfung (Stage 2)
- Token/Client-ID-Prinzip aus UI entfernt — nur noch zentrale KIRA App
- Neue API-Endpunkte: /api/mail/provider-detect, /api/mail/konto/oauth-start, /api/mail/konto/oauth-status, /api/mail/konto/health, /api/mail/konto/health-check, /api/mail/konto/volltest, /api/mail/konto/volltest-status, /api/mail/konto/reconnect, /api/mail/microsoft-app/test
  **Offen geblieben:** Google OAuth noch nicht verdrahtet. Provider nach OAuth-Login nicht persistiert. Import aus anderem Mail-Client: UI-Karte vorbereitet, Logik fehlt. SMTP-Test für IMAP-Password-Konten (Volltest nutzt aktuell nur OAuth/XOAUTH2).

## 2026-03-29 — Session-Ende (session-bb)

**Status:** erledigt

---

## 2026-03-29 — Session-Start (session-cc)

**Auftrag:** (1) AGENT.md: Neue Regel — bei großen Aufträgen Plan-Agent nutzen für beste Umsetzungsstruktur. (2) Toast-Kopierbutton funktioniert nicht + zu klein beheben. (3) Archiv-Mails "weg" — nach Update nicht mehr zugänglich. (4) Doppelte Archiv-Ordner klären (anfrage vs anfrage_raumkult_eu). (5) Offene Punkte für nächste Session festhalten: Google OAuth, SMTP-Passwort-Auth, Provider-Persistierung, Mail-Archiv-Plan.
**Status:** erledigt

**Erledigt:**

- AGENT.md: Neue Regel in "Session-Start: Größerer Auftrag" — Plan-Agent Pflicht vor Implementierung
- config.json Bug: mail_archiv.pfad war leer ("") → wiederhergestellt auf korrekten Archiv-Pfad. Ursache: war in Arbeitskopie gelöscht, nie committed.
- mail_monitor.py Bug: \_save_to_archive() erhielt label=`anfrage` statt email_addr=`anfrage@raumkult.eu` → Ordner `anfrage/` statt `anfrage_raumkult_eu/` → Fix: email_addr übergeben. Die 12.507 Mails im alten Archiv (anfrage_raumkult_eu etc.) sind vollständig erhalten und intakt.
- Erklärung Doppelordner: Neue Ordner (anfrage/ info/ invoice/ kaimrf/ shop/) entstanden durch falsches Label im mail_monitor — können gelöscht werden.
- Toast-Kopierbutton: größer (16px, Rahmen, Padding), JS-Fallback via execCommand wenn clipboard API nicht verfügbar
- session_handoff.json aktualisiert mit offenen Punkten
  **Offen geblieben:** Neue (falsch benannte) Ordner `anfrage/`, `info/`, `invoice/`, `kaimrf/`, `shop/` können vom User manuell gelöscht werden.

## 2026-03-29 — Session-Ende (session-cc)

**Status:** erledigt

---

## 2026-03-29 21:00 — Session-Start (session-ff)

**Auftrag:** Kira indexiert hereingekommene E-Mails nicht mehr. Angebote, Eingangs- und Ausgangsrechnungen werden nicht mehr zugeordnet. Die Kacheln (Geschäft, Nächste Termine, Geschäft aktuell) sind seit mehreren Tagen unverändert. Im Aktivitätsprotokoll nach 16:10 Uhr nichts mehr über Klassifizierung. Die migrierten Archiv-Mails wurden nicht in die Klassifizierung genommen. Bitte Problem identifizieren, beheben, alle Mails der letzten 3-4 Tage nachklassifizieren und eine "Nachklassifizieren ab Datum"-Funktion einbauen.

**Diagnose:** Mail-Monitor läuft korrekt (Speedify 17:48, Ecwid 17:38 in Aktivitätslog). Root-Cause: daily_check.py's scan_new_mails() überspringt Mails älter als letzter_lauf. 511 Kandidaten in mail_index.db ohne Task, davon 5 echte Business-Mails (übrige: Newsletter, System, bereits beantwortet).

**Umsetzung:** (1) daily_check.py: recheck_mails(seit, bis, dry_run) + get_recheck_progress() + --seit/--bis/--trocken CLI. (2) server.py: POST /api/mail/nachklassifizieren + GET /api/mail/nachklassifizieren/status + UI-Button in Einstellungen > Mail-Klassifizierung. (3) Nachklassifizierung durchgeführt: 5 neue Tasks (Angebotsrückmeldung Kaufmann A-SB260093, Betonkosmetik Horsting, Amir Sad Lead, Calumex Lead, Handwerker).

**Status:** erledigt

---

## 2026-03-29 — Session-Start (session-gg)

**Auftrag:** (Continuation session-ff) Folgefragen: (1) Klassifiziert Kira neue Mails wieder automatisch? (2) Dashboard "Geschäft aktuell" zeigt unleserliche Rohdaten ("sonstiger_vorgang: Timon...") — übersichtlicher machen. Nächste Termine zeigt alte Daten mit falschem Badge "heute".

**Diagnose:** mail_monitor war immer korrekt. Dashboard-Problem: geschaeft.typ = Raw-DB-Werte ohne Label-Mapping + organisation-Badge "heute" für vergangene Termine.

**Umsetzung:** build_dashboard() server.py: (1) \_TYP_LABELS dict: sonstiger_vorgang→"Vorgang", zahlungserinnerung→"Zahlungserinnerung" etc. (2) Farbprüfung auf raw_typ (zuverlässig). (3) \_ORG_TYP dict: termin/frist/rueckruf→Deutsch. (4) Badge "⚠ überfällig" statt "heute" wenn diff < 0. Commit 1e4ca49.

## 2026-03-29 — Session-Ende (session-gg)

**Status:** erledigt

---

## 2026-03-30 07:00 — Session-Start (session-hh)

**Auftrag:** Vollwertiges IMAP-Postfach + Ordner-System Komplett-Umbau.
(1) Screenshot 1 Chips "IMAP-Ordner / KIRA-Zugang" → umbenennen in "Zusätzliche Postfach-Ordner". Chips funktional machen: speichern, zeigt nur Ordner die NICHT in Screenshot 2 (Kira-Kernordner) gecheckt sind. Markierung = nur Postfach-Anzeige, kein Kira-Archiv.
(2) Screenshot 2 (Sync-Ordner & KIRA-Zugang): Nur gecheckte Ordner = Kira-Kernordner. Kein Auto-Spam. Erweiterbar aus Postfach. Deaktivieren nur mit Admin + Dreifach-Absicherung. Jeder gecheckte Ordner bekommt Archiv-Unterordner.
(3) mail_monitor.py: ORDNER_EINSCHLIESSEN/AUSSCHLIESSEN hardcoded → config-basiert aus sync_ordner. Entwürfe + Gelöschte wirklich verdrahten.
(4) /api/mail/folders → IMAP-live (nicht nur mail_index.db). Postfach zeigt alle sichtbaren Ordner.
(5) Mail verschieben per IMAP (POST /api/mail/verschieben).
(6) Gelöschte-Protokoll-System: Archiv-Ordner "Gelöschte" nach einstellbarer Zeit auto-bereinigen. Anhänge/grosse Dateien löschen, Kurzprotokoll (Datum/Absender/Betreff/200 Zeichen) bleibt für immer. Kira LLM kann Protokoll lesen.
(7) Tatsächlich testen mit echten Mails.
**Status:** erledigt

---

**Erledigt:**

- Phase 0: `_ensure_geloeschte_protokoll_table()` + `geloeschte_protokoll`-Tabelle in tasks.db (mit Indizes)
- Phase 1: `mail_monitor.py` — `_get_sync_ordner()` + `_ordner_erlaubt()` config-basiert. `ORDNER_EINSCHLIESSEN`/`AUSSCHLIESSEN` hardcoded durch config-Logik ersetzt. Entwürfe+Gelöschte Elemente verdrahtet.
- Phase 2: 3 neue API-Endpunkte: POST `/api/mail/konto/postfach-ordner`, POST `/api/mail/verschieben`, GET `/api/mail/protokoll`
- Phase 3: `/api/mail/folders` komplett neu — Live-IMAP mit `_decode_imap_utf7()` (RFC 3501 Modified UTF-7), 60s Cache, DB-Fallback, Kira-/Zusatz-Ordner-Split pro Konto
- Phase 4: JS-Frontend — zwei Panels, `_pfCurrentMsgId`, `pfOpenVerschiebenMenu()`/`pfVerschiebenNach()`, `showKritischModal()` bei Kira-Ordner deaktivieren
- Phase 5: `archiv_cleanup.py` neu, tägl. Background-Thread in `run_server()`, Integration in `daily_check.py`
- Phase 6: `kira_llm.py _build_data_context()` — GELÖSCHTE MAILS PROTOKOLL Sektion (letzte 20)
- Phase 7: Tests — UTF-7-Decoding-Bug gefunden+gefixt, ordner-als-Liste-Handling, `_ensure_geloeschte_protokoll_table()` on-demand in Protokoll-Endpoint
- Bugs: (1) IMAP Modified UTF-7 nicht decodiert → Entwürfe/Gelöschte nicht erkannt. (2) ordner als Array statt String im Handler. (3) Protokoll-Tabelle nur on-demand erstellt.
  **Offen geblieben:** Einstellungen-UI für `bereinigung_frist_tage`. Mail-Verschieben mit echten Mails testen.

## 2026-03-30 — Session-Ende (session-hh)

**Status:** erledigt

---

## 2026-03-30 — Session-Start (session-ll)

**Auftrag:** Automatisches Model-Validierungs-System implementieren: Erkennt wenn LLM-Modelle unavailable werden (Anthropic/OpenAI/OpenRouter/Ollama), korrigiert automatisch auf bestes verfügbares Modell, sendet ntfy-Push + Dashboard-Meldung, updated config.json persistent. Danach KIRA_SYSTEM_ANALYSE.md aktualisieren.
**Status:** erledigt

## 2026-03-30 — Session-Ende (session-ll)

**Erledigt:**

- kira_llm.py: `ModelNotFoundError` Klasse, `_MODEL_CACHE`/TTL, `_send_ntfy_push()`, `_fetch_provider_models()` (24h-Cache, alle 4 Provider-Typen), `_model_in_list()`, `_validate_model()`, `_auto_update_model()` (config.json + ntfy), `validate_all_providers()` (schreibt state-file)
- kira_llm.py: `_call_anthropic()` + `_call_openai_compat()` fangen Modell-404/NotFoundError → Auto-Update + `ModelNotFoundError` → Fallback auf nächsten Provider
- server.py: Import erweitert, `POST /api/kira/provider/check-models` Endpoint, 🟡 Status-Icon für veraltete Modelle, 🔍 Modell-Button pro Provider-Karte, Stale-Model-Warnung (gelb), `checkProviderModel()` JS-Funktion, `_model_validation_loop` Hintergrund-Thread (20s + 24h)
- KIRA_SYSTEM_ANALYSE.md: Aktualisiert (session-kk + session-ll Änderungen, alle behobenen Fehler markiert, neue Sektion 3.5 Modell-Validierung, neue Endpunkte, aktualisierte Prioritäts-Matrix)
- Beide Dateien syntaktisch korrekt (py_compile OK)
  **Offen geblieben:** FEHLER-05 (NULL-Check mail_monitor), FEHLER-07 (State-File Race Condition) — weiterhin offen.
  **Status:** erledigt

---

## 2026-03-30 — Session-Start (session-ii)

**Auftrag:** Postfach-Rebuild: (1) pfBulkDelete IIFE-Scope-Bug beheben. (2) Unread-Badge INBOX prominent/fett. (3) Favoriten-Klick filtert korrekt + Active State. (4) Gemeinsames Postfach: "Ungelesene" + "Erinnert mich" Sub-Ordner. (5) Aktionsleiste auch bei Einzel-Auswahl (Single-Mode vs Bulk-Mode). (6) Snooze/Erneut erinnern: Dropdown (Presets + Freitext), IMAP-Ordner auto-anlegen, Kira LLM-Kontext ohne Limit.
**Status:** erledigt

**Erledigt:**

- Bug: pfBulkDelete/pfBulkMarkRead/pfClearSelection als window.\* exponiert (IIFE-Scope-Problem)
- Favoriten: pfSelectFolder bereinigt active von .pf-fav-item + data-konto/data-folder Attribute für Highlight
- Badge: INBOX=fetter blauer Badge, Entwürfe=grauer Italic-Total-Badge, Snooze-Ordner=gelb, andere=wie gehabt
- Combined Postfach: "Ungelesene" (folder_type=unread, nur gelesen=0 INBOX-Mails) + "Erinnert mich" (folder_type=snoozed) Sub-Items
- Aktionsleiste: pf-bulk-bar mit Single-Modus (Antworten/Allen/Weiterleiten/Löschen/Kennzeichnen/Heften/Erinnern/Verschieben) + Bulk-Modus getrennt; pfOpenMail ruft pfUpdateBulkBar auf
- Snooze: snooze_until Spalte in mails, POST /api/mail/snooze + GET /api/mail/snooze/count, IMAP-Ordner auto-CREATE + in sync_ordner eintragen, Dropdown mit 7 Presets + Freitext-Parser (2h30m / YYYY-MM-DD HH:MM), Snooze-Badge auf Mail-Item, Snooze-Wecker-Thread alle 60s, Inbox filtert snoozed-Mails aus
- kira_llm.py: SCHLAFENDE MAILS-Sektion ohne Limit (alle aktiven Snooze-Mails)
  **Offen geblieben:** Google OAuth, SMTP-Passwort-Auth, Stats-Zeile klickbar, Wissens-DB auto-pflege

## 2026-03-30 — Session-Ende (session-ii)

**Status:** erledigt

---

## 2026-03-30 — Session-Start (session-jj)

**Auftrag:** Vollständige System-Analyse erstellen (\_analyse/KIRA_SYSTEM_ANALYSE.md) + alle gefundenen Fehler direkt beheben: Modell-ID veraltet, hardcoded Pfade, stummes Logging im Daemon-Modus, DB-Verbindungs-Leaks, SyntaxWarnings in server.py.
**Status:** erledigt

## 2026-03-30 — Session-Ende (session-jj)

**Erledigt:** System-Analyse + 10 Bugfixes (ISS-003/018/019/020/021). Commit 9103bd6.
**Offen geblieben:** Keine.
**Status:** erledigt

---

## 2026-03-30 10:00 — Session-Start (session-kk)

**Auftrag:** Postfach: (1) Mail-Inhalt Rendering kaputt — bei EML nur kleines Stück sichtbar (iframe height), Text-Mails zeigen JSON/Formatierungs-Elemente. (2) Kira-Button: extrem präsent machen, klick führt ins leere beheben — Kira soll Chatfenster öffnen mit kompletten Mail-Kontext, Auto-Send, lädt Kundenverlauf vor, "stelle gerade Informationen zusammen" Meldung.
**Status:** erledigt

## 2026-03-30 10:45 — Session-Ende (session-kk)

**Erledigt:**

- A1: iframe height fix — min-height:0 + iframe-mode CSS-Klasse, overflow:hidden
- A2: Text-Rendering — HTML-Entities dekodieren, HTML-in-Text als iframe
- B4: GET /api/mail/kira-kontext — volltext EML + letzte 5 Absender-Mails + offene Tasks
- B1: Kira-Button — prominent lila, Glow, Kira-Icon mit Augen+Lächeln
- B2: pfKiraMailContext() — openKiraWorkspace (kein showPanel), Lade-Spinner, Auto-Send, 5000 Zeichen + Verlauf + Tasks
- B3: kiraSetQuickActions 'mail'-Typ
  Commit: 66241b0
  **Offen geblieben:** Keine.
  **Status:** erledigt

---

## 2026-03-30 — Session-Start (session-mm)

**Auftrag:** Postfach / Mail-Arbeitsfläche Komplett-Umbau nach neuen HTML-Vorlagen (02_postfach_action_ribbon_v4.html, 02_postfach_attachment_bar_v1.html, 02_postfach_mail_viewer_states_v1.html, 02_postfach_mail_detail_header_v1.html, 02_postfach_mail_detail_focus_v1.html, 02_postfach_thread_hints_v1.html, 02_postfach_image_gallery_viewer_v1.html). Ziele: (1) Feste Hauptleiste/Ribbon über Postfach (Outlook-Style, Vollmodus/Kompaktmodus mit Pfeil, keine Scrollbalken). (2) Alle Ribbon-Aktionen funktional anbinden. (3) Mail-Kopfbereich neu nach Vorlage (Betreff dekodiert, Avatar, Name/E-Mail, Datum rechts, Aktionen). (4) Mail-Viewer-Zustände (HTML/Text/Blockiert mit State-Chips + Trust-Banner). (5) Thread-Hinweise als Chips (geantwortet/weitergeleitet/Wiedervorlage/Kira/erledigt). (6) Anhang-Leiste: eingeklappt by default, aufklappbar mit Vorschau/Aktionen. (7) Bild-Galerie-Viewer. (8) Kira- und Logging-Anbindung für alle Mail-Aktionen.
**Status:** erledigt (siehe Commits 4010271, 3571077 — Fluent UI Ribbon + Mail & Konten Tabs + E-Mail-Signaturen)

---

## 2026-03-30 18:00 — Session-Start (session-nn)

**Auftrag:** Großer Architektur-Umbau: KIRA Case Engine + Multi-Agent-System. Arbeitsanweisung: `_archiv/arbeitsanweisung_claude_case_engine_multiagent.md`. Kernziel: Weg von Einzelmail-Verarbeitung, hin zu vorgangs- und entscheidungsbasierter Arbeitslogik. Neue Vorgangslogik (cases), Verknüpfungsschicht (Mail+Rechnung+Angebot+Kunde+Task), Statusmaschinen pro Vorgangstyp, 3 Entscheidungsstufen (A/B/C), Aktivfenster/Aktive-Assistenz, Präsenz-Logik, Kira-Workspace korrekt verdrahten.
**Status:** erledigt

**Erledigt:**

- Paket 1: rebuild_all.py — 4 neue Tabellen (vorgaenge, vorgang_links, vorgang_status_history, vorgang_signals), vorgang_id + snooze_until in tasks
- Paket 2: case_engine.py — dict-basierte Statusmaschinen für 10 Vorgangstypen, vollständige CRUD-API, Signal-Queue, transitions-kompatible Signaturen
- Paket 3: vorgang_router.py — Routing-Layer zwischen Mail-Klassifizierung und Case Engine (Stufe A/B/C)
- Paket 4+5: mail_monitor.py + daily_check.py — beide Task-INSERT-Stellen mit Router-Integration verdrahtet (commit + route call)
- Paket 6: server.py — 7 neue Vorgang-API Endpoints (GET /api/vorgaenge, /api/vorgang/{id}, /api/vorgang/kunde/{email}, /api/vorgang/signals, POST /api/vorgang/neu, /{id}/status, /{id}/link, /signal/gelesen)
- Paket 7: kira_llm.py — 2 neue Tools (vorgang_kontext_laden, vorgang_status_setzen), System-Prompt um offene Vorgänge erweitert
- Paket 8: server.py — Signal-Polling-JS (10s), Toast für Stufe-B, Modal für Stufe-C, CSS-Injection im Dashboard
- Paket 9: presence_detector.py (Windows ctypes GetLastInputInfo), activity_window.py (tkinter -topmost Desktop-Overlay), Signal-Watcher-Thread + /api/presence Endpoint
- Paket 10: case_engine_backfill.py — Backfill für Rechnungen/Angebote/Tasks mit --dry-run Option, idempotent
  **Offen geblieben:** Backfill noch nicht ausgeführt (muss manuell als `python case_engine_backfill.py --dry-run` getestet werden).

---

## 2026-03-31 07:00 — Session-Start (session-oo)

**Auftrag:** Kira 2.0 Umbau-Plan: (1) Browser-Screenshots aller UI-Panels erstellen. (2) UX-Recherche durchführen. (3) Vollständigen UI/UX-Umbauplan als `_analyse/KIRA_2_0_UI_UMBAU_PLAN.md` erstellen. (4) Phase 2 Einstellungen erweitert (Kira/LLM neue Gruppen: Memory, Proaktiv, ReAct, Feedback, Sicherheit; Automationen aktiviert; Sicherheit & Audit neu). (5) Plan-Freigabe durch Kai. (6) Phase 3 (Kira-Postfach) + Phase 4 (Live-Chip + Activity-Drawer) implementieren. Zusatz: Farben für Hell+Dunkel-Modus, Einstellungen als 3-Pane-Ansicht (Outlook-Referenz).
**Status:** erledigt

**Erledigt:**

- Kira-Live-Chip im Header (idle/scanning/pending/error-States), 15s Polling via \_pollKiraStatus()
- Activity-Drawer (Slide-In von rechts, 400px): zeigt Freigabe-Queue + Proaktiv-Status, non-modal
- Einstellungen 3-Pane-Layout (Outlook-Style): Mail & Konten, Kira/LLM, Protokoll als Sub-Pane
- Kira-Ausgang im Postfach: Ordnergruppe mit Entwürfe/Gesendet/Abgelehnt/Abgelaufen
- /api/mail/approve/pending?status=X unterstützt alle 4 Queue-Ansichten
- pfKiraMailFreigeben/Bearbeiten/Sendenbearbeitet/Ablehnen korrekt als window.\* exponiert
- Fix: JS SyntaxError durch `'div[style]'` in single-quoted string (parentElement-Traversal als Fix)
- Fix: pf-load-more korrekt versteckt bei leerer Kira-Liste
- Commit: fb879cd

**Offen geblieben:** Microsoft Graph Calendar-UI, Ribbon-Kira-Gruppe für Kira-Mails, Partner-View generieren.

## 2026-03-31 — Session-Ende (session-oo)

**Status:** erledigt

---

## 2026-03-31 — Session-Start (session-rr)

**Auftrag:** Continuation nach session-qq. Selbst priorisiert: verbleibende KIRA-LLM-Verbindungen schließen + praktische UX-Features.
**Status:** erledigt

**Erledigt:**

- Antwort-Länge (build_system_prompt Wiring): kurz/normal/ausführlich beeinflusst jetzt tatsächlich Kiras Stil
- Kira-Sprache: Deutsch/Englisch/gemischt als Select + Prompt-Override (session-rr)
- LLM-Temperatur: Range-Slider 0.0–1.0 in Einstellungen + Wiring in \_call_anthropic() + \_call_openai_compat()
- Provider Verbindungstest: ⚡ Test-Button pro Provider-Karte + POST /api/kira/provider/test
- Einstellungen-Suche: Suchfeld über der Navigation filtert Sektionen + Panel-Volltext, ESC zum Reset
- DB-VACUUM: POST /api/db/vacuum + Button in Protokoll > Konfigurationsbackup
- Toast-Anzeigedauer: Sekunden-Inputs in Benachrichtigungen-Sektion (Normal/Fehler)
- Logo-Größe: Select Klein/Mittel/Groß + applyLogoSize() + restoreDesign() Wiring
- KIRA_SYSTEM_ANALYSE.md: session-qq und session-rr Changelog ergänzt
- Todo_checkliste.md: alle session-rr Features auf ✅

**Commits:** 5ccb873, c2acf94, ffb1057, 729ff65, c07648d
**Offen geblieben:** Ribbon-Kira-Gruppe für Kira-Mails, Google OAuth, WhatsApp-Token (Kai-Aktion).
**Status:** erledigt

---

## 2026-03-31 — Session-Start (session-ss)

**Auftrag:** Continuation nach session-rr. Selbst priorisiert: praktische Settings/UX-Features + Sicherheitsfix.
**Status:** erledigt

**Erledigt:**

- User-Präsenz-Erkennung: visibilitychange API — Kira-Status-Polling pausiert wenn Tab versteckt
- Kira-Position: Select (unten-rechts/links, oben-rechts/links) + applyKiraPosition() + localStorage-Restore
- Kira-Chitchat-Toggle: "Smalltalk erlaubt" in Einstellungen → beeinflusst System-Prompt (kira_llm.py build_system_prompt)
- ntfy Push-Priorität: Select low/default/high/urgent in Einstellungen → kira_proaktiv.py \_push() liest config
- Dashboard-Refresh-Intervall: Select 1/5/15/30/60min oder Deaktiviert → silentRefreshDashboard dynamisch
- Morgen-Briefing konfigurierbar: Toggle + Uhrzeit-Input → scan_tagesstart_briefing() liest config (3h Fenster ab Startzeit)
- Sicherheitsfix: hardcoded `bcc:'info@raumkult.eu'` in pfSend() entfernt → BCC-Eingabefeld im Compose-Formular

**Commits:** 9dc60f1, 1632065, b20985e
**Offen geblieben:** Google OAuth, WhatsApp-Token (Kai-Aktion), Auto-Backup config.json.
**Status:** erledigt

---

## 2026-03-31 — Session-Start (session-tt)

**Auftrag:** Continuation nach session-ss. Selbst priorisiert: Auto-Backup fertigstellen + Dashboard-Features.
**Status:** erledigt

**Erledigt:**

- Dashboard "Heute gesendet"-Karte (Zone C0): zeigt Kira-gesendete Mails (mail_approve_queue) + User-gesendete Mails (runtime_events.db mail_gesendet)
- Tagesbriefing Timestamp: "Stand HH:MM" im Briefing-Titel, erstellt_am in kira_briefings gespeichert
- Sent-Items Ungelesen-Badge Fix: \_index_mail() setzt gelesen=1 für Gesendet-Ordner (Ordnernamens-Check)
- Auto-Backup (server.py): POST /api/backup/jetzt Endpoint, Einstellungen-UI (Toggle/Pfad/Keep-N/Button)
- Auto-Backup (kira_proaktiv.py): scan_auto_backup() als Scan 11, 23h TTL, SQLite .backup() API
- backupNow() JS: Button ruft /api/backup/jetzt → Toast mit Ergebnis
- saveSettings() Backup-Wiring: backup.aktiv/pfad/keep_n in config.json gespeichert
- Mail-Senden Logging: rlog('user', 'mail_gesendet', ...) in \_api_mail_send()

**Commits:** (folgt)
**Offen geblieben:** Google OAuth, WhatsApp-Token (Kai-Aktion), Mail-Ignorieren-Lernfrage.
**Status:** erledigt

---

## 2026-03-31 14:00 — Session-Start (session-uu)

**Auftrag:** Continuation nach session-tt. Server-Neustart + F-01/F-02 testen + Tracking aktualisieren.
**Status:** erledigt

**Erledigt:**

- Server-Neustart: 2 Bugs gefunden+gefixt (NameError eingang_offen, f-string backtick-Template in Verbindungstest)
- F-01 Mail-Ignorieren Lernmodal: ignorierModal mit 5 Preset-Gruenden + Freitextfeld, speichert Wissensregel via /api/wissen/neu. Playwright-getestet (Modal oeffnet, im-tid/im-kat korrekt).
- F-02 filterKomm-Fix: jumpToSeg() verdrahtet, Playwright-test bestaetigt Segment-Tab "Neue Leads" aktiv.
- Kais Checkliste: 3 Items als erledigt markiert (Stats-Filter, Ignorieren-Lernfrage, Wissensregeln-Zeitstempel).

**Commits:** 708e37a
**Offen geblieben:** "Spaeter"-Klick Lernfrage (Reminder-Datum), Google OAuth, WhatsApp-Token (Kai).
**Status:** erledigt

---

## 2026-03-31 15:00 — Session-Start (session-vv)

**Auftrag:** Selbst priorisiert nach Scan aller offenen Items.
**Status:** erledigt

**Verifiziert als bereits fertig:**

- Fenster-Split Position (localStorage pf_pane_w) — in Checkliste markiert

**Erledigt:**

- Ungelesene Badge Postfach: \_pfGlobalBadgeUpdate() sofort + alle 2min (alle Panels). Playwright: Badge=3 auf Start-Panel.
- Spaeter-Klick Lernfrage: datetime-local Picker + 4 Schnellbuttons + Warum-Frage mit Presets + Wissensregel-Speicherung
- Sidebar-Logo: K-Text → Kira-Launcher SVG (lila Orb, Augen, applyLogo/applyLogoSize angepasst)

**Commits:** ac0c057 + c845669
**Offen geblieben:** Plan Paket 1-A (Tool-Idempotenz kira_llm.py), Kalender-Eintrag für Spaeter (wartet auf Graph API), App-Icon-Verknüpfung.
**Status:** erledigt

### 2026-03-31 15:35 — Ergänzung session-vv

**Auftrag:** Klärung was die "offen gebliebenen" Items blockiert + Favicon sofort umsetzen.
**Erledigt:**

- Favicon: Kira-Launcher SVG als data-URI im <head> — Tab-Icon und gepinntes App-Icon
- Kalender-Blocker identifiziert: Azure App braucht Calendars.ReadWrite Permission (Kai-Aktion im Entra Portal)
  **Commit:** c4f68bb
