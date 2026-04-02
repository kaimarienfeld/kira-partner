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
**Status:** ⚠️ Kai-Aktion (bereits bekannt)
**Was:** Passwort-Platzhalter im Gmail-Draft ersetzen
**Erledigt am:** —

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

---

## BLOCK D — Zukunft / Spaetere Sessions

*(Features die bewusst zurueckgestellt wurden)*

### D-01 — Kira Live-Chip im Header
**Status:** 🔜 In Planung
**Aus:** KIRA_SYSTEM_ANALYSE offene Posten

### D-02 — Activity-Drawer Slide-In
**Status:** 🔜 In Planung

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
**Status:** 🔜 Offen — partner_view.html ist separate Datei (kein TOUR_JS). Bei Bedarf dort integrieren.

---

## STATISTIK (wird von Claude Code aktualisiert)

| Bereich | Gesamt | Erledigt | Offen | Blockiert | Kai-Aktion |
|---------|--------|----------|-------|-----------|------------|
| Block A (UI/Bugs + Tours) | 16 | 16 | 0 | 0 | 0 |
| Block B (Kai) | 4 | 0 | 0 | 0 | 4 |
| Block C (Laufend) | 1 | 1 | 0 | 0 | 0 |
| Block D (Zukunft + offene Tours) | 11 | 7 | 1 | 0 | 0 |
| **Gesamt** | **32** | **24** | **1** | **0** | **4** |

> Block-A 16/16 komplett. Block-C 1/1 (C-01 f-string Crash behoben session-rrr).
> session-qqq: D-04..D-10 (7 Modul-Tours) erledigt. D-11 (Partner-View) noch offen (separate HTML).
> Block-B 0/4 (Kai-Aktionen: Cloudflare, Azure, WhatsApp, Leni-Draft).

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

---

*Erstellt: 2026-04-01*
*Speicherort: Plan KIRA Laufend/KIRA_MASTERCHECKLISTE_LAUFEND.md*
*Aktualisierung: nach jeder Claude-Code-Session zwingend*
