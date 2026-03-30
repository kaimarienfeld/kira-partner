# Session-Log — Crash-Backup & Auftrags-Protokoll

> Append-only. Niemals Einträge löschen oder überschreiben.
> Zweck: Crash-Recovery. Beim Start immer letzten Eintrag prüfen!

---

## 2026-03-29 22:15 — Session-Start (session-y)

**Auftrag:** Continuation Session: Mail-Bug beheben (keine neuen Mails kommen an), WhatsApp Einstellungen fehlen in Integrationen, Kira System tot → beheben. + Mail & Konten Einstellungen Komplett-Overhaul mit Konto-Karten, Stats, Buttons, Archiv-Panel, IMAP-Ordner.
**Status:** erledigt

---
**Erledigt:**
- _process_mail() Bug behoben: _index_mail() wird jetzt immer aufgerufen (auch Newsletter/Ignorieren)
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
- MSAL OAuth mit zentraler KIRA Entra App (a0591b2d): _msal_app_kira(), start_oauth_browser_flow(), get_oauth_job_status()
- 3-stufige Provider-Erkennung: Stage1 (Domain-Heuristik) → Stage2 (DNS-MX/Autodiscover) → Stage3 (MS OpenID-Probe) — detect_provider_advanced()
- Mailbird-Stil 6-Schritt-Konto-Assistent: Overlay-Wizard, Anbietererkennung mit Stufen-Fortschritt, Expert-Mode (IMAP/Exchange/EWS/POP3), OAuth-Browser-Flow
- Exchange/EWS-Protokoll im Expert-Schritt: _wizProtoChange() zeigt EWS-Server-Feld dynamisch
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
- mail_monitor.py Bug: _save_to_archive() erhielt label=`anfrage` statt email_addr=`anfrage@raumkult.eu` → Ordner `anfrage/` statt `anfrage_raumkult_eu/` → Fix: email_addr übergeben. Die 12.507 Mails im alten Archiv (anfrage_raumkult_eu etc.) sind vollständig erhalten und intakt.
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

**Umsetzung:** build_dashboard() server.py: (1) _TYP_LABELS dict: sonstiger_vorgang→"Vorgang", zahlungserinnerung→"Zahlungserinnerung" etc. (2) Farbprüfung auf raw_typ (zuverlässig). (3) _ORG_TYP dict: termin/frist/rueckruf→Deutsch. (4) Badge "⚠ überfällig" statt "heute" wenn diff < 0. Commit 1e4ca49.

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

## 2026-03-30 — Session-Start (session-ii)

**Auftrag:** Postfach-Rebuild: (1) pfBulkDelete IIFE-Scope-Bug beheben. (2) Unread-Badge INBOX prominent/fett. (3) Favoriten-Klick filtert korrekt + Active State. (4) Gemeinsames Postfach: "Ungelesene" + "Erinnert mich" Sub-Ordner. (5) Aktionsleiste auch bei Einzel-Auswahl (Single-Mode vs Bulk-Mode). (6) Snooze/Erneut erinnern: Dropdown (Presets + Freitext), IMAP-Ordner auto-anlegen, Kira LLM-Kontext ohne Limit.
**Status:** erledigt

**Erledigt:**
- Bug: pfBulkDelete/pfBulkMarkRead/pfClearSelection als window.* exponiert (IIFE-Scope-Problem)
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
