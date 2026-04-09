# KIRA — Laufende Mastercheckliste
# Grundlage fuer alle weiteren Tests, Fehler und Anpassungen
# Erstellt: 2026-04-01 | Immer aktuell halten — nach jeder Session aktualisieren

> Diese Liste ist die einzige Wahrheitsquelle fuer alle offenen, laufenden und erledigten
> Aufgaben aus der Testphase. Sie ersetzt keine KIRA_SYSTEM_ANALYSE, sondern ergaenzt sie
> um den laufenden Tagesbetrieb. Claude Code aktualisiert sie nach jeder Aufgabe.

---

## Legende

| Symbol | Bedeutung |
|--------|-----------|
| ✅ | Erledigt und getestet |
| 🔄 | In Bearbeitung |
| ⏳ | Offen — noch nicht angefangen |
| ⚠️ | Kai-Aktion erforderlich |
| ❌ | Blockiert (Grund eingetragen) |
| 🔜 | In Planung — spaetere Session |
| 🐛 | Bug — aktiv |
| 🐛✅ | Bug — behoben |

---

## BLOCK A — UI-Verbesserungen & Bug-Fixes (2026-04-01)

### A-00 — KRITISCH / PRIO 1: Mail-Archiv leer — Pfad-Verbindung durch Admin-Sender-Einbau gebrochen
**Status:** ✅ Behoben (session-ooo, commit 693d0d9)
**Gefunden am:** 2026-04-01
**Betrifft:** Mail-Archiv-Anzeige, Einstellungen → Archiv-Pfad, Admin-Sender-Konfiguration
**Ursache:**
  Beim Einbau des Admin-Senders wurde der Archiv-Pfad in den Admin verlegt,
  aber nicht korrekt mit der bestehenden Mail-Lade-Funktion verbunden.
  Ergebnis: Zwei verschiedene config.json-Keys fuer denselben Pfad,
  Mail-Lade-Funktion liest noch den alten (jetzt leeren) Key.
**Symptome:**
  - Archivierte Mails nicht mehr sichtbar (Archiv erscheint leer)
  - Einstellungen-Bereich zeigt "Pfad angeben" obwohl Pfad im Admin hinterlegt
  - Deaktiviertes Pfad-Feld in Einstellungen ist nicht mit Admin-Pfad verbunden
**Physische Mails:** wahrscheinlich unveraendert auf Festplatte vorhanden — nur Referenz kaputt
**Fix:**
  1. config.json-Key vereinheitlichen (ein Key fuer beide Bereiche)
  2. Mail-Lade-Funktion auf korrekten Key zeigen
  3. Einstellungsfeld zeigt Admin-Pfad (schreibgeschuetzt + Link zum Admin)
  4. Button "Pfad pruefen" prueft den Admin-Pfad, nicht ein leeres Feld
  5. mail_archiv_reindex.py ausfuehren um Index neu aufzubauen
**Abhaengigkeit:** Keine — sofort loesbar
**Erledigt am:** 2026-04-01

---

### A-01 — Sync-Richtung bei allen Sync-Buttons klar beschriften
**Status:** ✅ Erledigt (session-ooo, commit b8f2981)
**Betrifft:** Lexware-Modul, Einstellungen Lexware, Einstellungen Dataverse, gesamte App
**Kern:** Pfeil-Symbol + Klartext direkt am Button ("Von Lexware abrufen" / "An Lexware senden")
**Aufwand:** Mittel — alle Sync-Buttons in server.py finden und erweitern
**Abhaengigkeit:** Keine
**Erledigt am:** 2026-04-01

---

### A-02 — Lexware Office: Vollbreite nutzen
**Status:** ✅ Erledigt (session-ooo, commit 35f434d)
**Betrifft:** Lexware-Office-Modul
**Kern:** Gesamte Inhaltsbreite nutzen, keine unnoetige Zentrierung
**Aufwand:** Klein
**Erledigt am:** 2026-04-01

---

### A-03 — Lexware Office: 2-3-spaltige Registernavigation statt oberer Leistennavigation
**Status:** ✅ Erledigt (session-ooo, commit 35f434d)
**Betrifft:** Lexware-Office-Modul, Sekundaer-Navigation
**Kern:** Linke schmalere Spalte (Navigation) + rechte grosse Spalte (Inhalt), wie Einstellungen
**Aufwand:** Mittel
**Erledigt am:** 2026-04-01

---

### A-04 — Sync-Abbrueche: Fehlermeldung anzeigen + kopierbares Detaillog
**Status:** ✅ Erledigt (session-ooo, commit 9b78765)
**Betrifft:** Alle Sync-Vorgaenge, besonders Lexware
**Kern:** Kein stilles Umleiten zum Cockpit. Modal mit Fehlertext + "Fehlerdetails kopieren"-Button
**Log muss enthalten:** Zeitstempel, Funktion, Parameter, Lexware-API-Antwort, Kompatibilitaetsproblem
**Aufwand:** Mittel
**Erledigt am:** 2026-04-01

---

### A-05 — Lexware Kontakte: Alle verfuegbaren Felder abrufen
**Status:** ✅ Erledigt (session-ooo, commit 36f402f)
**Betrifft:** Lexware-Modul → Kontakte
**Kern:** API-Abfrage erweitern, alle Felder (Name/Firma/Adresse/Telefon/Email/USt/Bank/etc.)
**Aufwand:** Mittel — API-Recherche + DB-Migration
**Erledigt am:** 2026-04-01

---

### A-06 — Lexware Kontakte: Vollwertige Kontakt-UI mit 2-spaltiger Detailansicht
**Status:** ✅ Erledigt (session-ooo, commit 36f402f)
**Betrifft:** Lexware-Modul → Kontakte
**Kern:** Liste + Detailansicht (2 Spalten: Kategorien-Nav links, Felder rechts) + Bearbeitungsmodus
**Fenstergrösse:** Gross — kein kleines Popup
**Aufwand:** Gross
**Erledigt am:** 2026-04-01

---

### A-07 — Mikro-Logging: Alle UI-Klicks und Aktionen vollstaendig aufzeichnen
**Status:** ✅ Erledigt (session-ooo, commit f052320)
**Betrifft:** Protokoll-Bereich, runtime_log.py
**Kern:** Alle Button-Klicks, Einstellungsaenderungen, API-Calls, Syncs, Fehler aufzeichnen
**Format:** Zeitstempel + Typ + Modul + Aktion + Ergebnis (ok / Fehlertext)
**Im Protokoll:** Filter nach Typ/Modul/Zeitraum + "Alles kopieren"-Button
**Aufwand:** Mittel — erst Recherche was damals implementiert war
**Erledigt am:** 2026-04-01

---

### A-08 — SMTP-Test: Eingang und Ausgang testen + Log
**Status:** ✅ Erledigt (session-ooo, commit 9b78765)
**Betrifft:** Einstellungen → Mail & Konten
**Kern:** Pro Konto: "Testmail senden" (SMTP) + "Posteingang pruefen" (IMAP), je mit Ergebnisanzeige
**Bei Fehler:** Fehlercode + Beschreibung + "Fehlerdetails kopieren"
**Aufwand:** Klein bis Mittel
**Erledigt am:** 2026-04-01

---

### A-09 — Cloudflare Tunnel: Installation vereinfachen (1-Klick wo moeglich)
**Status:** ✅ Erledigt (session-ooo, commit 9e899a1)
**Betrifft:** Einstellungen → Mobil / Oeffentlicher Zugang
**Kern:** Automatischer Download + Tunnel-Erstellung + Dienst-Installation per Knopfdruck
**Was Kai machen muss:** Cloudflare-Account + einloggen → Link dazu
**Recherche noetig:** Cloudflare-API fuer programmatische Tunnel-Erstellung
**Aufwand:** Gross — erfordert Plan-Agent + Recherche
**Kai-Aktion:** ⚠️ Cloudflare-Account erstellen/einloggen
**Erledigt am:** 2026-04-01

---

### A-10 — Diagnose/Test: Fehler-Bericht-Button ueberall einbauen
**Status:** ✅ Erledigt (session-ppp, commit folgt)
**Betrifft:** Lexware Diagnose-Panel (Haupttest)
**Kern:** Nach jedem Test: Erfolg (Haekchen) oder Fehler (X + "Fehlerdetails kopieren"-Button)
**Umgesetzt:** _lxShowTestResult(ok, errText) + lx-test-result-api Span + lx-test-copy-err Div in lexTestConnection()
**Erledigt am:** 2026-04-01

---

### A-11 — Button-Design: Einheitlich schwarz/weiss — alle blauen Buttons korrigieren
**Status:** ✅ Erledigt (session-ooo, commit 4107399)
**Betrifft:** Gesamte App — alle Buttons pruefen
**Kern:** Blaue Buttons → schwarz mit weisser Schrift (Standard). Keine Emoji auf Buttons.
**Ausnahmen erlaubt:** Rot fuer destruktive Aktionen, Ampel-Status-Chips (nicht klickbar)
**Als Regel speichern:** KIRA_DESIGN_REGELN.md + Hinweis in AGENT.md
**Aufwand:** Klein bis Mittel
**Erledigt am:** 2026-04-01

---

### A-12 — Dataverse-Einstellungen: Erklaerungen, Tooltips, Einrichtungsassistent
**Status:** ✅ Erledigt (session-ooo, commit e0e5841)
**Betrifft:** Einstellungen → Dataverse
**Kern:** ? Symbol hinter jedem Feld → Modal mit Erklaerung + Azure-Links + Beispielwert
**Feld "Duplikatpruefung":** Komplett ueberarbeiten — nicht nutzbar als simples Textfeld
**Einrichtungsassistent:** Schrittweiser Flow durch alle noetigen Felder
**Recherche noetig:** Microsoft Dataverse Doku — welche Felder, wo in Azure zu finden
**Aufwand:** Gross — erfordert Plan-Agent + Recherche
**Erledigt am:** 2026-04-01

---

### A-13a — Tour-Engine: Wiederverwendbare Grundkomponente bauen
**Status:** ✅ Erledigt (session-ooo, commit 012e683)
**Betrifft:** Neue Komponente kira_tour.js / Tour-Grundlogik in server.py
**Kern:**
  Spotlight-Overlay-System das jedes beliebige Element hervorheben kann.
  Erklaerungsbox mit Weiter/Zurueck/Beenden.
  Schritt-Steuerung: nur manuell, kein Autoplay.
  Fortschrittsanzeige "Schritt 4 von 18 — Bereich: Belege".
  Tastatur-Unterstuetzung (Pfeiltasten, Escape).
  Registerkarten-Wechsel automatisch beim naechsten Tour-Schritt.
  Bereichs-Auswahl: Gesamttour oder nur aktuelle Registerkarte.
  Tour-Button: immer sichtbar im Modulkopf + Sekundaer-Navigation.
  Testdaten-Modus: Dry-Run-Flag, Demo-Datensaetze, orangefarbener Banner.
  Erklaer-Modus: Schreib-Buttons gesperrt, nur Erklaerungen.
  Runtime-Log: tour_gestartet / tour_schritt_N / tour_beendet / tour_abgebrochen.
  Technisch gekapselt: naechste Module uebergeben nur ihre Schrittliste.
**Aufwand:** Gross
**Erledigt am:** 2026-04-01

---

### A-13b — Lexware Office: Vollstaendige Tour-Inhalte (alle Bereiche)
**Status:** ✅ Erledigt (session-ooo, commit 012e683 — 21 Schritte, alle Bereiche)
**Betrifft:** Alle Bereiche des Lexware-Office-Moduls + Einstellungen Lexware
**Kern:**
  Claude Code formuliert alle Texte selbst aus den Planungsdokumenten.
  Einfaches Deutsch, kein Jargon, verstaendlich fuer Nicht-Techniker.
  Pro Schritt: Was sehe ich? Was kann ich tun? Was passiert dabei?
  Loest das etwas in Lexware aus? Ist das umkehrbar?
  Anzeige-Elemente erklaeren (nicht nur Buttons).
  Warnungen bei Schreib-Zugriffen auf Lexware einbauen.
  Alle Bereiche vollstaendig:
  Cockpit | Belege | Zahlungen | Kontakte & Kunden | Artikel & Preispositionen |
  Dateien | Buchhaltung | Regeln & Muster | Diagnose & Mapping |
  Einstellungen Lexware (komplett)
  Pro Bereich: zuerst Ueberblick, dann jede Funktion und jede Anzeige einzeln.
**Quelldokumente fuer Texte:**
  Arbeitsanweisung_Lexware_ClaudeCode_AKTUALISIERT_V5.md +
  Arbeitsanweisung_Lexware_UI_Komplettausbau_ClaudeCode.md
**Aufwand:** Sehr gross
**Erledigt am:** 2026-04-01

---

### A-13c — Tour-Vorlage dokumentieren + Modul-Liste fuer alle offenen Tours
**Status:** ✅ Erledigt (session-ooo — KIRA_TOUR_SYSTEM_VORLAGE.md erstellt)
**Betrifft:** Plan KIRA Laufend/KIRA_TOUR_SYSTEM_VORLAGE.md
**Kern:**
  Dokument wie Tour-Engine technisch aufgebaut ist.
  Anleitung fuer Claude Code wie eine neue Modul-Tour angelegt wird.
  Pflicht-Schritte jeder Tour definieren.
  Folgende Module als offene Tour-Aufgaben in diese Checkliste eintragen:
**Offene Tours (spaetere Sessions):**
  A-14: Kommunikation / Postfach — Tour offen
  A-15: Geschaeft — Tour offen
  A-16: Wissen — Tour offen
  A-17: Capture / Mobile Memo — Tour offen
  A-18: Kira-Workspace — Tour offen
  A-19: Dashboard — Tour offen
  A-20: Einstellungen komplett (alle Sektionen) — Tour offen
  A-21: Partner-View / Leni — Tour offen
**Aufwand:** Mittel
**Erledigt am:** 2026-04-01

---

## BLOCK B — Kai-Aktionen (koennen nicht automatisiert werden)

### B-01 — Cloudflare Account
**Status:** ⚠️ Kai-Aktion
**Was:** Cloudflare-Account erstellen oder einloggen
**Wo:** https://dash.cloudflare.com
**Warum:** Benoetigt fuer Tunnel-Erstellung (AUFGABE-7)
**Erledigt am:** —

### B-02 — Azure Entra: Calendars.ReadWrite
**Status:** ⚠️ Kai-Aktion (bereits bekannt aus KIRA_SYSTEM_ANALYSE)
**Was:** Im Azure Portal die Berechtigung Calendars.ReadWrite hinzufuegen
**Wo:** Azure Portal → App-Registrierungen → KIRA-App → API-Berechtigungen
**Erledigt am:** —

### B-03 — WhatsApp Business Token
**Status:** ⚠️ Kai-Aktion (bereits bekannt)
**Was:** WhatsApp Business API Token in KIRA eintragen
**Erledigt am:** —

### B-04 — Leni Gmail-Draft Passwort
**Status:** ✅ Erledigt (session-uuu, 2026-04-02)
**Was:** Passwort-Platzhalter im Gmail-Draft ersetzen
**Erledigt am:** 2026-04-02

---

## BLOCK C — Laufende Fehler aus Testphase

*(Wird laufend ergaenzt — Claude Code traegt hier neue Bugs ein die beim Testen auffallen)*

### C-01 — ERR_EMPTY_RESPONSE: f-string Braces-Bug in Tour-Buttons
**Status:** 🐛✅ Behoben (session-rrr, commit a479341)
**Gefunden am:** 2026-04-01
**Beschreibung:** Tour-Buttons in `build_lexware()`, `build_capture()` und `generate_html()` (kw-header-right)
  verwendeten `{erklaermodus:true}` (einfache Klammern) innerhalb von Python f-Strings.
  Resultat: `NameError: name 'erklaermodus' is not defined` → Server sendete leere HTTP-Antwort.
  py_compile erkennt diese Art von Fehler NICHT — nur erkennbar durch direkten generate_html()-Aufruf.
**Fix:** Alle 3 Stellen auf `{{erklaermodus:true}}` (doppelte Klammern in f-string) korrigiert.
**Behoben am:** 2026-04-01

### C-02 — Lexware: Panel nicht full-width + Sync springt zur Cockpit-Ansicht
**Status:** 🐛✅ Behoben (session-sss, commit 4e5784e)
**Gefunden am:** 2026-04-02
**Beschreibung:** `#panel-lexware` hatte `max-width:1200px;margin:0 auto` durch globale `.panel`-Klasse.
  Sync-Funktion `lexSync()` rief `location.reload()` nach Abschluss auf → sprang immer zur Start-Ansicht.
**Fix:** CSS-Override `max-width:none` fuer `#panel-lexware`, `location.reload()` entfernt, stattdessen
  Toast-Benachrichtigung + Statuszeile mit Kategorien-Counts.
**Behoben am:** 2026-04-02

### C-03 — Lexware: Verbindungsstatus-Chip zeigt "Nicht verbunden" nach erfolgreichem Test
**Status:** 🐛✅ Behoben (session-sss, commit 4e5784e)
**Gefunden am:** 2026-04-02
**Beschreibung:** `lexTestConnection()` aktualisierte den Chip `lx-status-dot` nicht nach dem API-Call.
  Chip blieb statisch auf "Nicht verbunden" auch wenn Test erfolgreich.
**Fix:** JS-Code in `lexTestConnection()` ergaenzt: `dot.className = 'lx-chip ' + (ok ? 'lx-chip-ok' : 'lx-chip-err')`
  + `dot.innerHTML` aktualisiert.
**Behoben am:** 2026-04-02

### C-04 — Lexware: Sync holt nur 200/273 Kontakte (Pagination-Bug)
**Status:** 🐛✅ Behoben (session-sss, commit 4e5784e)
**Gefunden am:** 2026-04-02
**Beschreibung:** `get_all_contacts()` in `lexware_client.py` pruefte nur `totalPages - 1` als Abbruch-Bedingung,
  ignorierte das `last`-Flag der Lexware-API. Resultat: Loop brach zu frueh ab.
  Gleiches Problem in `get_all_vouchers()` und `get_all_articles()`.
**Fix:** Alle drei Pagination-Loops pruefen jetzt `result.get("last", False)` ODER `page >= totalPages - 1`
  + leere Items als zusaetzlicher Abbruch-Guard. Test: 273 Kontakte, 52 Artikel.
**Behoben am:** 2026-04-02

### C-05 — Admin: SMTP-Test fehlte, falsche Buttons in Einstellungen > Mail
**Status:** 🐛✅ Behoben (session-sss, commit 4e5784e)
**Gefunden am:** 2026-04-02
**Beschreibung:** SMTP/IMAP-Test-Buttons standen in Einstellungen > Mail-Konten (falscher Ort).
  Im Admin-Panel fehlte ein SMTP-Test komplett.
**Fix:** Buttons aus Einstellungen entfernt. Im Admin > E-Mail SMTP neuer Button `adm-smtp-test-btn`
  + `admSmtpTest()` JS + `/api/ntfy/test` Backend-Extension fuer SMTP-Test via smtplib.
**Behoben am:** 2026-04-02

### C-06 — GitHub-Token in Partner-View nach Push nicht gespeichert
**Status:** 🐛✅ Behoben (session-sss, commit 4e5784e)
**Gefunden am:** 2026-04-02
**Beschreibung:** `pushToGitHub()` verwendete `ghToken` aber setzte `s.gh_token` nicht vor dem
  `localStorage.setItem()`-Aufruf. Token ging nach Session-Ende verloren.
  Admin-Panel zeigte keinen Token-Status.
**Fix:** `s.gh_token = ghToken` vor localStorage-Save. Nach erfolgreichem Push: KIRA-API
  `/api/partner/save-token` aufgerufen (Token in secrets.json persistiert).
  Admin zeigt jetzt `adm-gh-status` mit `ghp_ViANv8sU****`.
  Neue Endpoints: GET `/api/partner/get-token`, POST `/api/partner/save-token`.
**Behoben am:** 2026-04-02

### C-07 — `esNavTo` ReferenceError (Kalender-Fehler-Link)
**Status:** 🐛✅ Behoben (session-sss, commit 4e5784e)
**Gefunden am:** 2026-04-02
**Beschreibung:** Zwei onclick-Handler in der Kalender-Fehleranzeige (Dashboard) riefen `esNavTo('mail')` auf —
  Funktion existiert nicht. Korrekte Funktion ist `esShowSec()`.
**Fix:** Beide Stellen (Zeile 17567 + 17594) auf `esShowSec('mail')` korrigiert.
**Behoben am:** 2026-04-02

### C-08 — ARCHIVER_DIR falscher Pfad: OAuth-Tokens nicht gefunden nach Server-Neustart
**Status:** 🐛✅ Behoben (session-ttt, commit f0cb6a4)
**Gefunden am:** 2026-04-02
**Beschreibung:** `config.json → mail_archiv.pfad` zeigte auf `.../Mail Archiv/Archiv` (Unterordner).
  `mail_monitor.py` leitete daraus `ARCHIVER_DIR`, `TOKEN_DIR` und `ARCHIVER_CFG` ab.
  Tatsaechlicher Speicherort: `raumkult_config.json` und `tokens/` liegen im Elternordner
  `.../Mail Archiv/`. Folge: Alle Tokens wurden beim Start nicht gefunden → scheinbar verloren.
**Fix:** `mail_monitor.py` prueft jetzt ob `raumkult_config.json` im Parent-Ordner liegt und
  korrigiert `ARCHIVER_DIR` automatisch. 5/6 Konten zeigen nach Neustart `status=ok`.
**Behoben am:** 2026-04-02

### C-09 — Microsoft OAuth: Konto erscheint nach Login nicht in der Liste
**Status:** 🐛✅ Behoben (session-ttt, commit f0cb6a4)
**Gefunden am:** 2026-04-02
**Beschreibung:** `_wizPollOAuth()` done-Branch rief `esLoadMailKonten()` nicht auf nach Abschluss.
  Liste blieb veraltet bis manuelles Neu-Laden.
**Fix:** `setTimeout(()=>{{if(typeof esLoadMailKonten==='function')esLoadMailKonten();}},3000);`
  im done-Branch von `_wizPollOAuth()` ergaenzt (analog zu Google-OAuth-Flow).
**Behoben am:** 2026-04-02

### C-10 — Microsoft OAuth: "Konto bereits vorhanden" blockiert Reconnect-Flow
**Status:** 🐛✅ Behoben (session-ttt, commit f0cb6a4)
**Gefunden am:** 2026-04-02
**Beschreibung:** Wizard zeigte Fehler "Konto bereits vorhanden" und blieb stehen wenn das
  Konto bereits in `raumkult_config.json` eingetragen war (Reconnect-Szenario).
**Fix:** Wenn `saved.error` den String "bereits vorhanden" enthaelt und `!_wiz.isReconnect`,
  wird `_wiz.isReconnect=true` automatisch gesetzt und der Flow weitergemacht.
**Behoben am:** 2026-04-02

### C-11 — Bestehende Mail-Konten ohne smtp_server: SMTP-Test schlug fehl
**Status:** 🐛✅ Behoben (session-ttt, commit f0cb6a4)
**Gefunden am:** 2026-04-02
**Beschreibung:** Aeltere Konten in `raumkult_config.json` hatten kein `smtp_server`-Feld.
  SMTP-Test meldete "Konto nicht gefunden" oder verwendete leeren Server-String.
**Fix:** `_migrate_konto_smtp()` + `migrate_all_smtp_settings()` in `mail_monitor.py` ergaenzt.
  Wird beim Server-Start automatisch aufgerufen (run_server()). Alle 5 aktiven Konten
  erhalten jetzt `smtp.office365.com:587` als Default.
**Behoben am:** 2026-04-02

### C-12 — Health-Check Konto-Suche case-sensitive (Email-Gross-/Kleinschreibung)
**Status:** 🐛✅ Behoben (session-ttt, commit f0cb6a4)
**Gefunden am:** 2026-04-02
**Beschreibung:** `check_account_health()` und `run_full_connection_test()` suchten Konto
  per `k["email"] == email_addr` (exakter Vergleich). Kleinschreibung-Unterschied → Konto nicht gefunden.
  Duplikat-Check in `neues_konto`-Handler ebenfalls case-sensitive.
**Fix:** Alle drei Stellen auf `.lower()`-Vergleich umgestellt.
**Behoben am:** 2026-04-02

### C-13 — Admin SMTP: Kein persistenter Verbindungsstatus-Indikator
**Status:** 🐛✅ Behoben (session-ttt, commit f0cb6a4)
**Gefunden am:** 2026-04-02
**Beschreibung:** Admin > E-Mail SMTP zeigte keinen Status ob SMTP getestet/verbunden war.
  Nach Server-Neustart kein Hinweis ob Test zuletzt erfolgreich war.
**Fix:** Badge `adm-smtp-status-badge` im Admin-Header. `admLoadData()` liest `letzter_test_ok`
  aus `config.json → email_notification`. Drei Zustaende: gruenes "Verbunden" / gelbes "Ungetestet"
  / graues "Nicht konfiguriert". Nach erfolgreichem Test: Badge sofort aktualisiert + Timestamp
  via POST `/api/admin/save` mit `section='smtp_test_ok'` in `config.json` gespeichert.
**Behoben am:** 2026-04-02

### C-14 — Quill CDN-Ladung loest Browser-Sicherheitswarnung aus
**Status:** 🐛✅ Behoben (session-ttt, commit f0cb6a4)
**Gefunden am:** 2026-04-02
**Beschreibung:** Quill.js v1.3.7 wurde von `cdn.quilljs.com` geladen. Browser-Extension
  zeigte Warnung "nicht autorisiertes Bibliotheken-Flag" (externe CDN-Anfrage von localhost-App).
**Fix:** Quill `quill.min.js` (216 KB) und `quill.snow.css` (24 KB) nach `scripts/static/`
  kopiert. Neuer `/static/` Route-Handler in `do_GET`. HTML-Loader aendert `src`/`href`
  auf `/static/quill.min.js` bzw. `/static/quill.snow.css`.
**Behoben am:** 2026-04-02

### C-15 — Lexware Belege-Sync: 3 Fehler (HTTP 400 voucherStatus fehlt)
**Status:** 🐛✅ Behoben (session-uuu, commit abeddd5)
**Gefunden am:** 2026-04-02
**Beschreibung:** `sync_belege_to_db()` rief `get_all_vouchers(typ)` ohne `voucherStatus` auf.
  Lexware `/voucherlist` erfordert `voucherStatus` als Pflichtparameter → HTTP 400 fuer alle 3 Typen
  (invoice, creditnote, quotation). Fehler-Body `"Missing required request parameters: [voucherStatus]"`
  war bisher nicht sichtbar da `e.body` leer.
**Fix:** (1) `_TYP_STATUSES` dict in `sync_belege_to_db()` definiert: invoice=6 Statuses,
  creditnote=5, quotation=4. Pro Typ alle relevanten Statuses abrufen (Deduplizierung via `seen_ids`).
  (2) `fehler_details[]` Array in allen 3 sync-Methoden — Fehlertext + API-Body werden zurueckgegeben.
  (3) JS `lexSync()` zeigt Modal mit Fehler-Details wenn `fehler > 0`.
**Ergebnis:** 141 Belege + 273 Kontakte + 52 Artikel — 0 Fehler.
**Behoben am:** 2026-04-02 10:46 MEZ

### C-16 — JS-Syntaxfehler: `closest()` in onclick + `{{}}` in regulaerer Python-String
**Status:** 🐛✅ Behoben (session-vvv, 2026-04-02)
**Gefunden am:** 2026-04-02 09:32 MEZ
**Beschreibung:** 2 JavaScript-Syntaxfehler nach session-uuu-Aenderungen:
  (1) `this.closest(\'#kira-approve-modal\')` und `this.closest(\'div[style*=fixed]\')` in
  `onclick`-Attributen — die `\'` wurden zu `'` in der regulaeren Python-String und terminierten
  den umgebenden JS-String-Delimiter, sodass `#kira` bzw. `div` als nackte Identifier gesehen wurden.
  (2) `pfAlleKontenAbrufen` mit `{{...}}` (f-string-Stil) in `build_postfach()` regulaerer `"""..."""`-String
  → `{{method:'POST',...}}` wurde als `{{method:...}}` ausgegeben → `Unexpected token '{'`.
**Fix:**
  (1) `closest(\'...\')` in onclick → `closest(&apos;...&apos;)` (HTML-Entity, wird vom Browser zu `'` vor JS-Ausfuehrung)
  bzw. `document.getElementById(&apos;kira-approve-modal&apos;).remove()` fuer die spezifische Modal-ID.
  (2) `pfAlleKontenAbrufen`: alle `{{` → `{` und `}}` → `}` korrigiert.
**Behoben am:** 2026-04-02 09:36 MEZ

---

## BLOCK D — Zukunft / Spaetere Sessions

*(Features die bewusst zurueckgestellt wurden)*

### D-01 — Kira Live-Chip im Header
**Status:** ✅ Erledigt (session-zz) — kiraLiveChip im Header, 4 Status-CSS-Klassen (idle/scanning/pending/error), onclick oeffnet Activity-Drawer
**Behoben am:** 2026-03-31

### D-02 — Activity-Drawer Slide-In
**Status:** ✅ Erledigt (session-zz) — kiraActivityDrawer mit Overlay, kiraActivityDrawerOpen/Close(), Aktivitaeten-Liste
**Behoben am:** 2026-03-31

### D-03 — Multi-Agent-Architektur
**Status:** 🔜 Langfristig

### D-04 — Tour: Kommunikation / Postfach
**Status:** ✅ Erledigt (session-qqq) — KIRA_TOUR_POSTFACH, 8 Schritte, Tour-Button in pf-left-hdr

### D-05 — Tour: Geschaeft
**Status:** ✅ Erledigt (session-qqq) — KIRA_TOUR_GESCHAEFT, 10 Schritte, Tour-Button in gh-mod-acts

### D-06 — Tour: Wissen
**Status:** ✅ Erledigt (session-qqq) — KIRA_TOUR_WISSEN, 7 Schritte, Tour-Button in wissen-level-tabs

### D-07 — Tour: Capture / Mobile Memo
**Status:** ✅ Erledigt (session-qqq) — KIRA_TOUR_CAPTURE, 7 Schritte, Tour-Button in cap-nav

### D-08 — Tour: Kira-Workspace
**Status:** ✅ Erledigt (session-qqq) — KIRA_TOUR_KIRA, 7 Schritte, Tour-Button in kw-header-right

### D-09 — Tour: Dashboard
**Status:** ✅ Erledigt (session-qqq) — KIRA_TOUR_DASHBOARD, 7 Schritte, Tour-Button in dash-briefing-head

### D-10 — Tour: Einstellungen komplett (alle Sektionen)
**Status:** ✅ Erledigt (session-qqq) — KIRA_TOUR_EINSTELLUNGEN, 8 Schritte, Tour-Button in es-macts

### D-11 — Tour: Partner-View / Leni
**Status:** ✅ Erledigt — partner_view.html hat eigene Tour-Engine (TOUR_KAI/TOUR_LENI, tour-overlay, tour-card, Dots, Skip/Next)
**Behoben am:** 2026-03-31

---

## STATISTIK (wird von Claude Code aktualisiert)

| Bereich | Gesamt | Erledigt | Offen | Blockiert | Kai-Aktion |
|---------|--------|----------|-------|-----------|------------|
| Block A (UI/Bugs + Tours) | 16 | 16 | 0 | 0 | 0 |
| Block B (Kai) | 4 | 1 | 0 | 0 | 3 |
| Block C (Laufend) | 16 | 16 | 0 | 0 | 0 |
| Block D (Zukunft + Tours) | 11 | 10 | 0 | 0 | 0 |
| **Gesamt** | **47** | **43** | **0** | **0** | **3** |

> Block-A 16/16 komplett. Block-C 16/16 komplett. Block-D 10/11 (nur D-03 langfristig offen).
> Block-B 1/4: B-04 erledigt. B-01..B-03 = Kai-Aktionen (Cloudflare, Azure, WhatsApp).
> session-zzz: D-01/D-02/D-11 als erledigt verifiziert + alle open_tasks aus session_handoff geprueft und bereinigt.

---

## CHANGELOG DIESER DATEI

| Datum | Was geaendert |
|-------|---------------|
| 2026-04-01 | Erstellt aus Kai-Feedback-Session |
| 2026-04-01 | A-00 Mail-Archiv-Bug als kritisch ergaenzt |
| 2026-04-01 | A-13 Lexware-Tour als Prio 2 ergaenzt |
| 2026-04-01 | A-13 aufgeteilt in 13a/b/c + Tour-Vorlage + Modul-Liste D-04 bis D-11 |
| 2026-04-01 | session-ooo: A-00/01/04/07/08/11/13a/b/c als erledigt markiert |
| 2026-04-01 | session-ppp: A-10 Diagnose Test-Ergebnis-Buttons erledigt — Block-A 16/16 komplett |
| 2026-04-01 | session-qqq: D-04..D-10 Modul-Tours alle erledigt (7 Tours, 59 Schritte gesamt) |
| 2026-04-01 | session-ooo (Fortsetzung): A-02/03/05/06/09/12 erledigt — alle AUFGABEN abgeschlossen |
| 2026-04-01 | session-rrr: C-01 f-string ERR_EMPTY_RESPONSE Crash behoben (3 Tour-Button-Stellen) |
| 2026-04-02 | session-sss: C-02..C-07 eingetragen + behoben (Lexware Full-Width/Chip/Sync, SMTP-Admin, GitHub-Token, esNavTo) |
| 2026-04-02 | session-ttt: C-08..C-14 eingetragen + behoben (ARCHIVER_DIR-Pfad, OAuth-Liste, Reconnect, SMTP-Migration, Case-Insensitive, Admin-Badge, Quill-CDN) |
| 2026-04-02 | session-uuu: C-15 eingetragen + behoben (Lexware Belege-Sync HTTP-400 + fehler_details-Array) |
| 2026-04-02 | session-zzz: D-01/D-02/D-11 als erledigt verifiziert. Alle open_tasks geprueft: 9 von 13 waren bereits implementiert. Statistik 43/47 (3 Kai-Aktionen, 1 langfristig) |
| 2026-04-09 | session-qq-cont4: Universal Learning (jeder Button erfasst Kontext), Postfach Ungelesen-Filter, Badge-Sofort-Update, Auto-Refresh ohne Flackern (ISS-040/041/042) |
| 2026-04-09 | session-qq-cont5: Postfach Preview-Reset bei Ordnerwechsel/Löschen/Verschieben + Einstellung next/none (ISS-043) |
| 2026-04-09 | session-qq-cont6: KRITISCH — Kira Chat-Kontext Fix (History an LLM übergeben, ISS-044) + Chat-Gedächtnis Einstellungen-UI (Slider 2–50 Nachrichten, Token-Kosten) |

---

*Erstellt: 2026-04-01*
*Speicherort: Plan KIRA Laufend/KIRA_MASTERCHECKLISTE_LAUFEND.md*
*Aktualisierung: nach jeder Claude-Code-Session zwingend*
