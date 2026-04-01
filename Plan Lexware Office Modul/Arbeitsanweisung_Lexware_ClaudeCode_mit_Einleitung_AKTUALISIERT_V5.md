# Arbeitsanweisung für Claude Code — Modul „Lexware Office“ inkl. Multi-Agent-Planung, KIRA-Integration, Buchhaltungs-Prüfbereich, Dokumente-Vorbereitung, Abo-Modus und Dataverse-Fortführung

Stand: 2026-04-01

## Bitte bringe dich vor der Arbeit an „Lexware Office“ zuerst auf den aktuellen Stand im Ordner:

`C:\Users\kaimr\.claude\projects\C--Users-kaimr-OneDrive---rauMKult-Sichtbeton-00-rauMKult-Auftr-ge-Anfragen\memory`

Wichtig:
Alle dort liegenden Dateien sind als aufgabenbezogener Zusatzkontext für dieses Modul zu prüfen.
Nichts davon stillschweigend ignorieren.

## Reihenfolge, mit der du beginnen sollst

1. **`AGENT.md`**
   Das ist global bindend. Pflicht-Start, Session-Regeln, Handoff-, Registry-, Log- und Commit-Regeln gelten zuerst.

2. **`memory\_archiv\arbeitsanweisung_claude_case_engine_multiagent.md`**
   Diese Arbeitsanweisung ist die bindende Grundlogik für große Umbauten:
   erst Plan-Agent, dann Repo-Audit, dann Gap-Analyse, dann kleine kontrollierte Pakete.
   Nicht direkt bauen.
   Nicht mit UI beginnen.

3. **Diese Datei hier**
   „Arbeitsanweisung für Claude Code — Modul Lexware Office inkl. Multi-Agent-Planung, KIRA-Integration, Buchhaltungs-Prüfbereich, Dokumente-Vorbereitung, Abo-Modus und Dataverse-Fortführung“

4. **Zusätzlich zwingend lesen und für Architekturkompatibilität berücksichtigen:**
   `Arbeitsanweisung_Dokumente_ClaudeCode_mit_Einleitung.md`

   Wichtig:
   Das neue Modul **Lexware Office** darf nicht isoliert gedacht werden.
   Die spätere Dokumente-Architektur und die zentrale Dokumentablage müssen schon jetzt mit vorbereitet werden.

5. **Danach die bestehenden Lexware-/Billbee-/Dataverse-Dateien vollständig prüfen**

   Mindestens:
   - `00_lex_billb_master.php`
   - `01_lex_billb_fetch_invoices.php`
   - `02_lex_billb_fetch_invoice_details.php`
   - `03_lex_billb_fetch_contact.php`
   - `04_lex_billb_convert_to_billbee.php`
   - `admin_lex_billb.php`
   - `cron_lex_billb_control.php`
   - `CLAUDE.md`
   - `requirements.txt`

   Wichtig:
   Diese Altstrecke ist **nicht Priorität des Ganzen**.
   Sie ist nur Zusatznutzen für den weiter benötigten Dataverse-Export und als Feldmapping-/Payload-Vorlage relevant.
   Sie darf also nicht die Zielarchitektur diktieren.

6. **Danach zusätzlich den aktuellen Projektstand gegenprüfen**

   Vor allem:
   - `Kira Assistenz -- Komplettübersicht`
   - relevante UI-/Memory-Dateien
   - `03 - Geschäft - Plan für UI.md`
   - `05 - Kira-Workspace - Plan für UI.md`
   - `06 - Einstellungen - Plan für UI.md`
   - bestehende Geschäfts-, Kunden-, Kira-, Logging-, Dokument- und Mail-Logik im Code

## Wichtige Regel

Das Modul **Lexware Office** ist kein kleines Zusatzmodul.
Es ist ein größerer Architektur-, Datenfluss- und Workflow-Umbau.

Darum gilt:

- erst planen
- dann Bestand prüfen
- dann Internet-Recherche für sinnvollen Stack und die echte Lexware-Umsetzung
- dann Plan-Dateien + Checklisten anlegen
- erst danach Implementierung

## Erste Arbeitsausgabe vor jeder Implementierung

Bevor du etwas baust, liefere zuerst:

- Ergebnis des Plan-Agenten
- Gap-Analyse Ist/Soll
- betroffene Dateien, APIs, Datenbanken, Logs und Module
- welche vorhandenen Teile übernommen, ersetzt oder migriert werden
- welche Plan-Dateien und Checklisten angelegt wurden
- Architektur-Empfehlung für v1 und vorbereitete v2
- sichere Umsetzungsreihenfolge in kleinen Paketen

---

# Arbeitsanweisung für Claude Code — Modul „Lexware Office“

## Zweck dieser Arbeitsanweisung

Diese Arbeitsanweisung konkretisiert den nächsten großen Auftrag für KIRA.

Sie ist verbindlich.

Du sollst nicht direkt losbauen, nichts Wichtiges stillschweigend weglassen, keine Teilbereiche eigenmächtig streichen und den Auftrag nicht auf reine UI reduzieren.

Der Schwerpunkt liegt jetzt auf dem neuen zentralen Integrations- und Arbeitsmodul **„Lexware Office“**.

Wichtig:
„Lexware Office“ ist **nicht** nur eine technische API-Anbindung.
„Lexware Office“ ist ab jetzt:

- eine produktive Geschäftsintegration,
- ein eigenes freischaltbares Zusatzmodul,
- eine Datenquelle für Geschäft, Kunden, Kira und später Analysen,
- die Grundlage dafür, dass KIRA selbst Angebote, Rechnungen, Mahnungen, Kontakte und weitere Belege sauber im Lexware-Schema erzeugen und an Lexware übergeben kann,
- und zusätzlich eine fachliche Arbeitsoberfläche für Buchhaltungsvorbereitung, Belegprüfung und spätere Zuordnung.

Ganz wichtig:
**Alle Einstellungen, Anbindungen, API-Konfigurationen, Provider-/Webhook-/Sync-Optionen, Freischaltlogik und sonstige Steuerlogik gehören in den normalen Bereich „Einstellungen“ im bekannten 3-Spalten-Aufbau.**
Die sichtbare Oberfläche von **Lexware Office** selbst soll **frei von Einstellungsformularen** bleiben und nur Arbeitsflächen, Status, Datenansichten, Diagnose und produktive Aktionen zeigen.

---

## Verbindliche Vorrang-Regeln

1. `AGENT.md` ist bindend und vor Arbeitsbeginn vollständig zu beachten.
2. Bei diesem Auftrag ist der **Plan-Agent Pflicht**, bevor irgendeine Implementierung beginnt.
3. Nutze zusätzlich passende Agenten/Subagents für Planung, Repo-Audit, Architektur, Recherche, UI-Auswirkungen, Validierung und Tracking.
4. Bereits vorhandene Architektur, Datenbanken, APIs, Logs, Geschäftslogik, Kundenlogik, Dokumentenlogik, Kira-Kontexte und Runtime-Logs sind zuerst zu prüfen, bevor neu gebaut wird.
5. Wenn etwas bereits vorhanden ist, aber falsch gedacht oder falsch verdrahtet ist, dann korrigieren oder migrieren, nicht blind neu daneben bauen.
6. Nicht UI zuerst. Zuerst Gap-Analyse, Architektur, Datenfluss, Nummernlogik, Kundenlogik, Beleglogik, Sync-Strategie und Verdrahtung.
7. Wenn etwas noch nicht fertig ist, darf es sichtbar vorbereitet werden, aber nur mit sauberem Statushinweis und Todo.
8. Nach jeder abgeschlossenen Arbeitseinheit sind Tracking, Session-Log, Handoff, Registry, Checklisten, Known Issues, Partner-View-Regeln und Commit-Pflichten aus `AGENT.md` vollständig einzuhalten.
9. Für Verbesserungen, Erweiterungen und die echte Lexware-Architektur ist **Internet-Recherche Pflicht**.
10. Für Dataverse ist zusätzlich **Recherche in der offiziellen Microsoft-Dokumentation Pflicht**, inklusive Abgleich mit dem vorhandenen PHP-Code.
11. Wenn du an einer Stelle unsicher bist, dokumentiere es offen, begründe den Vorschlag und arbeite strukturiert weiter.

---

## Harte Priorisierung

Die Priorität dieses Auftrags ist klar und darf nicht verwässert werden.

### Priorität A — Kernziel

KIRA + Lexware Office als echte produktive Geschäftsintegration:

- Rechnungen erstellen
- Angebote erstellen
- Mahnungen erstellen
- Kontakte / Kunden anlegen und pflegen
- Artikel / Preispositionen nutzbar machen
- Zahlungsstatus / offene Posten / Belege / Dateien / Kontextdaten nutzbar machen
- Lexware-Daten als Arbeitsgrundlage für Geschäft, Kunden, Kira und Dokumente einbinden
- sinnvolle Lexware-Arbeitsoberfläche bauen

### Priorität B — Buchhaltungs-Prüfbereich für Eingangsbelege

Zusätzlich soll KIRA geschäftliche Eingangsbelege intelligenter erkennen, prüfen, vorbereiten und in einen eigenen prüfbaren Arbeitsfluss für Lexware-Buchhaltung überführen.

### Priorität C — Dataverse-Fortführung

Der Dataverse-Export aus der alten 00–04-Strecke bleibt gewünscht.
Aber:
Er ist **nicht** das Hauptziel dieses Auftrags.
Er ist ein Zusatzpfad und soll nachgelagert sauber weitergeführt werden.

---

## Phase 0 — Pflicht-Start nach AGENT.md

Arbeite den Session-Start aus `AGENT.md` vollständig ab:

- `AGENT.md` lesen
- `session_handoff.json` lesen
- `feature_registry.json` lesen
- `knowledge/session_log.md` lesen
- diesen Auftrag sofort in `knowledge/session_log.md` eintragen
- `_archiv/feature_list.md`, `_archiv/only_kais checkliste.md`, `knowledge/Todo_checkliste.md` prüfen und mit `feature_registry.json` abgleichen
- `change_log.jsonl` aufgabenbezogen prüfen
- prüfen, ob weitere bindende Projektdateien für diesen Auftrag relevant sind
- bei diesem großen Auftrag zwingend Plan-Agent starten

Ohne diesen Ablauf nicht mit der Umsetzung beginnen.

---

## Phase 1 — Multi-Agent-Ablauf ist Pflicht

Starte nicht direkt mit der Implementierung.

Nutze für diesen Auftrag mehrere Agenten oder klar getrennte Arbeitsphasen.

### Pflicht-Agenten / Pflicht-Rollen

#### 1. `plan-agent`

Zweck:

- Gesamtstruktur planen
- Reihenfolge festlegen
- Umfang absichern
- nichts vergessen

Pflicht:

- immer zuerst bei diesem Auftrag

Aufgaben:

- Sollbild und Ist-Zustand abgleichen
- betroffene Dateien, APIs, Module, Datenbanken, Logs, Belegarten, Nummernlogik und Kundenlogik benennen
- Risiken, Seiteneffekte und Migrationsbedarf benennen
- Umsetzungsreihenfolge in kleinen Paketen festlegen
- Plan-Dateien und Checklisten anlegen

#### 2. `repo-audit-agent`

Zweck:

- aktuelle Implementierung prüfen
- bestehende Lexware-/Billbee-/Dataverse-Strecke dokumentieren
- Doppelbau vermeiden

Prüfen:

- 00–04 Altstrecke vollständig
- Adminpanel, Cron, Flags, Dry-Run, Logs
- bestehende Geschäftslogik
- bestehende Kunden-/Kontaktdatenlogik
- bestehende Kira-Kontexte
- bestehende Dokument-/Mail-/Anhangslogik
- bestehende Runtime-Logs
- vorhandene APIs und DB-Strukturen

Wichtig:
Diese Altstrecke ist **nicht der Hauptpfad**, sondern nur Vorlage für Mapping, Datenfelder und Dataverse-Fortführung.

#### 3. `research-agent`

Zweck:

- belastbare Recherche im Internet
- technisch umsetzbare und projektpassende Lexware-Lösungen finden
- v1/v2-Empfehlungen ableiten

Recherchiere:

- aktuelle Lexware-API-Endpunkte
- produktive Gateway-URL
- Event-Subscriptions / Webhooks
- Rate-Limits
- Zahlungsverhalten / Payments / Voucherlist
- Files / PDF-Download / Upload
- Belegarten: Rechnungen, Angebote, Mahnungen, Kontakte, Artikel, Auftragsbestätigungen, Lieferscheine, Credit Notes, Vouchers, Posting Categories
- ob und wie Buchhaltungsbelege / Eingangsbelege in Lexware per API angelegt, aktualisiert, mit Dateien versehen und mit Posting-Kategorien vorbereitet werden können
- praktische Umsetzungen über Make / Pipedream / ähnliche Tools als Architekturhinweis, nicht als Hauptlösung
- sinnvolle Sync-Modelle: push-first, event-driven, delta-sync, reconciliation
- offizielle Microsoft-Dataverse-Dokumentation für Create/Update/Upsert, Alternate Keys, Batch/Mehrfachoperationen und Beziehungspflege
- Abgleich der vorhandenen Dataverse-Variante aus 00–04 mit der Microsoft-Doku
- ob es eine **einfachere und robustere** Methode gibt als die bisherige PHP-Variante

Wichtig:

- nutze bevorzugt offizielle Doku, Primärquellen und belastbare technische Referenzen
- nur projektpassende Lösungen aufnehmen
- keine Theorie sammeln, sondern realistisch umsetzbare Optionen
- bei Dataverse nicht nur auf „läuft irgendwie“ prüfen, sondern auf Wartbarkeit, Einfachheit, Stabilität und künftige Skalierbarkeit

#### 4. `lexware-architecture-agent`

Zweck:

- Architektur für das Modul „Lexware Office“ definieren
- Lexware sauber in KIRA einbinden
- Source-of-Truth-Regeln und Nummern-/Kontaktlogik modellieren

#### 5. `workflow-impact-agent`

Zweck:

- prüfen, welche bestehenden Module durch Lexware angepasst werden müssen
- sicherstellen, dass Lexware nicht isoliert endet, sondern Geschäft, Kunden, Dokumente und Kira wirklich speist

#### 6. `bookkeeping-agent`

Zweck:

- den zusätzlichen Prüf- und Vorbereitungsfluss für **geschäftliche Eingangsbelege** definieren
- Erkennung, Body-Parsing, Prüfqueue, Nutzer-Rückfrage, Kontierungsvorschlag und Lexware-Zielmodell sauber planen

#### 7. `ui-impact-agent`

Zweck:

- UI-Auswirkungen auf Sidebar, Geschäft, Kunden, Kira-Workspace, Dokumente und Einstellungen prüfen
- aber erst nach Architekturfreigabe

Wichtig:
Für **Einstellungen** gilt ausdrücklich:
Die komplette Lexware-Konfiguration, Anbindungslogik und Freischaltlogik ist im 3-Spalten-Menü der globalen Einstellungen unterzubringen.
Nicht im Modul Lexware Office.

#### 8. `validation-agent`

Zweck:

- prüfen, ob die sichtbaren Hauptfunktionen tatsächlich funktionieren
- Regressionen, Seiteneffekte und fehlende Verdrahtungen benennen

#### 9. `memory-tracking-agent`

Zweck:

- Session-Log, Handoff, Registry, Todo-Checkliste, Known Issues und offene Punkte sauber nachziehen

---

## Phase 2 — Verbindliche Plan-Dateien anlegen

Lege vor der eigentlichen Implementierung neue Plan-Dateien an, die die Grundlage der Arbeit bilden.

Diese Dateien sind Pflicht und sollen sauber benannt, befüllt und aktuell gehalten werden.

### Empfohlene Plan-Dateien

1. `knowledge/plans/lexware_masterplan.md`
   - Zielbild
   - Scope
   - verbindliche Regeln
   - Architekturübersicht
   - Umsetzungsphasen
   - Risiken
   - offene Punkte

2. `knowledge/plans/lexware_gap_analyse.md`
   - Ist/Soll-Matrix
   - bereits vorhanden
   - vorhanden aber falsch gedacht
   - vorhanden aber falsch verdrahtet
   - teilweise vorhanden
   - vollständig fehlend

3. `knowledge/plans/lexware_api_recherche.md`
   - offizielle Lexware-Recherche
   - Endpunkte
   - Limits
   - Events
   - Belegarten
   - offene Einschränkungen
   - Empfehlung v1 / vorbereitete v2

4. `knowledge/plans/lexware_buchhaltung_pruefbereich.md`
   - Erkennung geschäftlicher Eingangsbelege
   - Body-Parsing
   - Ausnahmen wie PayPal
   - Nutzer-Rückfrage
   - Kontierungslogik
   - Prüfstatus
   - Lexware-Übergabe

5. `knowledge/plans/lexware_dataverse_recherche.md`
   - aktueller PHP-Weg
   - Microsoft-Doku-Abgleich
   - Alternate Keys
   - Upsert / ggf. Batch-Strategie
   - Empfehlung für robustere Umsetzung

6. `knowledge/plans/lexware_ui_plan.md`
   - Modulstruktur
   - Teilbereiche
   - Untermenüs
   - Arbeitsansichten
   - Kira-Anbindung
   - In-Planung-Bereiche

7. `knowledge/plans/lexware_settings_plan.md`
   - Bereich in Einstellungen
   - 3-Spalten-Struktur
   - Verbindungsstatus
   - Sync-Steuerung
   - Webhooks
   - Lizenz-/Abo-Freischaltung
   - Telemetrie / Diagnose

8. `knowledge/plans/lexware_runtime_log_plan.md`
   - Event-Typen
   - Payloads
   - Sync
   - Belegerstellung
   - Kundenanlage
   - Klassifizierung
   - Buchhaltungsvorschlag
   - Fehler / Retry

Wenn im Projekt bereits passendere Ordner/Dateistrukturen existieren, darfst du die Benennung sinnvoll anpassen.
Aber:
Plan-Dateien + Checklisten sind Pflicht und müssen als echte Arbeitsgrundlage genutzt werden.

---

## Grundsatz der Zielarchitektur

Die alte 00–04-Strecke darf **nicht** das neue Zielmodell bestimmen.

Die neue Zielrichtung ist:

- KIRA arbeitet produktiv mit Lexware Office,
- KIRA kann eigene Belege im Lexware-Schema erzeugen und an Lexware übergeben,
- Lexware bleibt die maßgebliche Beleg- und Statusinstanz für die dort geführten Geschäftsvorfälle,
- KIRA hält einen normalisierten Cache und einen kontextreichen Arbeitslayer,
- KIRA zieht Daten nicht nur ab, sondern arbeitet aktiv mit ihnen,
- Nummern, IDs, Kontakte und Belegzustände werden sauber abgeglichen,
- Dataverse bleibt optionaler Zusatzexport,
- die Altstrecke 00–04 ist nur noch Vorlage und Zusatzpfad.

Ganz wichtig:
Nicht nur Abruflogik bauen.
Sondern eine **echte produktive Geschäfts- und Buchhaltungsintegration**.

---

## Verbindliche Produktregeln

### 1. Modulname

Das Modul heißt **„Lexware Office“**.

### 2. Keine Einstellungen im Lexware-Modul

Alle Anbindungen, Token, Verbindungsprüfungen, Sync-Optionen, Webhooks, Freischaltung und Integrationsparameter gehören in **Einstellungen**.
Das Modul **Lexware Office** selbst bleibt eine Arbeitsfläche.

### 3. Abo-/Freischaltfähigkeit von Anfang an vorbereiten

Dieses Modul wird ein **separat freischaltbares Zusatzmodul**.
Darum muss die Architektur von Anfang an feature-flag- bzw. lizenzfähig aufgebaut werden.

Es müssen mindestens vorbereitet werden:

1. **nicht gebucht**
   - Modul in Sidebar nicht sichtbar
   - keine unnötigen Hintergrundprozesse

2. **sichtbar, aber gesperrt**
   - Modul als Zusatzmodul erkennbar
   - keine Scheinfunktionen
   - klare Sperrkennzeichnung

3. **gebucht / freigeschaltet**
   - vollständige Nutzung
   - aktive Hintergrundprozesse
   - aktive Kira- und Geschäftsintegration

Wichtig:
Nicht nur UI-seitig sperren.
Navigation, UI, Backend, Hintergrundprozesse und Kira-Aktionen müssen dieselbe Freischaltlogik respektieren.

### 4. Lexware Office ist ein Arbeitsmodul, kein reines Technikmodul

Die Oberfläche muss echte Arbeitsbereiche haben und nicht nur Diagnose oder Sync-Buttons zeigen.

### 5. Kundenbereich integrierbar vorbereiten

Der Lexware-Kontakte-/Kundenbereich ist so zu bauen, dass er später sauber mit dem geplanten **Kundenverwaltungssystem** und Kunden-360 verbunden werden kann.

### 6. Artikel- und Preispositionsbereich ausdrücklich mit einplanen

Der Bereich **Artikel & Preispositionen** ist nicht optional.
Er ist Grundlage für:

- Angebote
- Rechnungen
- KIRA-LLM-Unterstützung bei Belegerstellung
- spätere Kalkulation
- spätere Preispositionsanalyse
- strukturierte Wiederverwendung von Leistungen

### 7. Dokumente-/Belegdatei-Bereich ausdrücklich mit einplanen

Der Bereich **Dateien / Belegdokumente** ist Pflicht.
Er soll mittelfristig bisherige umständliche Rechnungs-Mail-Weiterleitungen und externe Regelstrecken ersetzen, sobald die Lexware-Integration sauber funktioniert.

### 8. Dataverse bleibt erhalten, aber nachgeordnet

Die Dataverse-Exportstrecke bleibt gewünscht.
Die bestehende 00–04-Konfiguration kann als Vorlage genutzt werden.
Aber:
Sie ist nicht das Produktzentrum.

---

## Kernziel des Auftrags

KIRA soll künftig:

- Kunden, Kontakte, Angebote, Rechnungen, Mahnungen und weitere Belege sauber im Lexware-Schema erzeugen oder synchronisieren,
- Lexware-Daten in Geschäft, Kunden, Kira und Dokumente bereitstellen,
- geschäftliche Eingangsbelege intelligent erkennen und für Buchhaltung vorbereiten,
- offene Posten, Zahlungen, Dateien und Kontextdaten nutzbar machen,
- Dataverse bei Bedarf weiter befüllen,
- und das Ganze in einer hochwertigen, klaren Arbeitsoberfläche nutzbar machen.

---

## Was „Lexware Office“ fachlich sein soll

Das Modul **Lexware Office** ist ein zentrales Arbeitsmodul mit mehreren klaren Teilbereichen.

### A. Lexware-Cockpit

- Verbindungsstatus
- letzte erfolgreiche Synchronisation
- Fehler / Warnungen
- Webhook-/Event-Status
- Queue-/Job-Status
- letzte API-Aktivität
- manuelle Aktionen wie Sync / Delta-Sync / Rebuild / Retry

### B. Beleg-Center

Mindestens vorbereiten oder umsetzen:

- Ausgangsrechnungen
- Angebote
- Mahnungen
- Gutschriften
- Auftragsbestätigungen
- Lieferscheine
- Eingangsrechnungen / purchase vouchers
- weitere relevante Voucher / Buchhaltungsbelege

### C. Zahlungen & Offene Posten

- offene Forderungen
- offene Verbindlichkeiten
- überfällige Fälle
- Teilzahlungen
- unklare Zahlungen
- Zahlungsstatus
- Fälligkeiten

### D. Kontakte & Kunden

- Kontakte
- Ansprechpartner
- Firmen
- Kundenhistorie
- offene Posten
- letzter Vorgang
- Lexware-Referenzdaten
- KIRA- und Kundenmodul-Verknüpfung

### E. Artikel & Preispositionen

- Artikel
- Standardpositionen
- Leistungspositionen
- Preislogiken
- spätere Kalkulations- und Angebotsverwendung

### F. Dateien / Belegdokumente

- PDF / Bild / XML / e-Rechnung
- Originaldokumente
- herunterladbare Dateien
- hochladbare Belegdateien
- Verknüpfung mit Vorgang, Kunde und Lexware-Datensatz

### G. Buchhaltung / Eingangsbelege prüfen

Das ist ein zusätzlicher eigener Bereich innerhalb von Lexware Office.
Nicht nur Dokumente.
Nicht nur Geschäft.
Sondern eine gezielte Arbeitsfläche für die Prüfung und Vorbereitung geschäftlicher Eingangsbelege.

### H. Diagnose / Mapping / Dataverse

- Mapping Lexware ↔ KIRA ↔ Dataverse
- Sync-Protokolle
- Fehler / Retry
- Payload-Vorschau
- Status des Zusatzexports

---

## Zusätzlicher Pflichtbereich: geschäftliche Eingangsbelege intelligent erkennen und vorbereiten

Dieser Zusatz ist **verbindlich** und zusätzlich zu allen bisherigen Anforderungen zu berücksichtigen.

### Ziel

Wenn KIRA erkennt, dass es sich um einen **echten geschäftlichen Eingangsbeleg** handelt, soll dieser nicht nur irgendwo klassifiziert werden, sondern in einen eigenen vorbereitenden Arbeitsfluss für die spätere Lexware-Buchhaltung überführt werden.

Wichtig:
Das ist **nicht** dieselbe allgemeine Belegklassifizierung wie in anderen Modulen.
Es ist ein **eigenständiger Zusatzbereich**, der aber integriert mit Dokumente, Kommunikation, Geschäft und Lexware Office zusammenarbeiten muss.

### Was erkannt werden soll

KIRA soll prüfen, ob es sich um einen **geschäftlichen Eingangsbeleg** handelt, also zum Beispiel:

- Lieferantenrechnung
- Onlinekauf-Rechnung
- Abo-Rechnung
- Dienstleisterrechnung
- Buchungs- / Reise- / Software- / Materialrechnung
- Rechnung nur im Mail-Body ohne PDF-Anhang
- Rechnung mit PDF-, Bild- oder XML-Anhang

### Was ausdrücklich sauber unterschieden werden muss

- **kein Ausgangsbeleg von uns**
- **keine bloße Zahlungsmitteilung**
- **keine reine Versand-/Bestellinfo ohne Rechnung**
- **keine PayPal-Zahlungsmitteilung als Rechnung**

### Sonderregeln

#### PayPal

PayPal ist im Regelfall **nicht** die Rechnung, sondern nur die Zahlungsmitteilung.
Darum:

- PayPal-Nachrichten nicht blind als Rechnung behandeln
- PayPal eher als Zahlungsereignis / Hinweis behandeln
- wenn die eigentliche Rechnung später vom Anbieter kommt, diesen Beleg bevorzugen
- KIRA soll lernen, welche Absender typischerweise **keine echte Rechnung**, sondern nur eine Zahlungsbestätigung senden

#### Apple und ähnliche Fälle

Es gibt Anbieter, bei denen die Rechnung oder die wesentlichen Rechnungsdaten **im Body der E-Mail** stehen.
Darum:

- KIRA soll nicht nur Anhänge prüfen, sondern auch den Mail-Body aktiv analysieren
- wenn im Body ein echter Rechnungsinhalt steckt, soll KIRA diesen extrahieren und als Beleggrundlage nutzbar machen
- falls nötig, daraus eine strukturierte Dokumentansicht oder einen ablegbaren Belegdatensatz erzeugen

### Zielarbeitsfluss

1. KIRA erkennt einen potenziellen geschäftlichen Eingangsbeleg.
2. KIRA prüft Quelle, Absender, Anhang, Body, Dokumentmerkmale und Kontext.
3. KIRA legt den Fall in einen Bereich wie **„Zu prüfen für Lexware Buchhaltung“**.
4. Dort kann der Nutzer den Fall ansehen, klassifizieren, ergänzen und mit KIRA besprechen.
5. KIRA fragt bei Bedarf aktiv nach dem wirtschaftlichen Zweck, zum Beispiel:
   - „Für was hast du das gekauft?“
   - „Für welchen Bereich war das?“
6. Der Nutzer gibt einen kurzen Text ein oder spricht mit KIRA.
7. KIRA erstellt daraus einen **nachvollziehbaren Buchhaltungsvorschlag** und speichert ihn beim Beleg.
8. Später kann dieser Beleg wiedergefunden, durchsucht, gefiltert und nachvollzogen werden.
9. Wenn API-seitig möglich, wird dieser Beleg zusätzlich in Lexware vorklassifiziert oder vorbereitet.

### Pflichtinformationen pro geprüftem Eingangsbeleg

Für jeden Beleg sollen mindestens ausgegeben oder speicherbar sein:

- Konto **(Lexware Office Bezeichnung + Nummer)**
- Abschreibung **ja/nein**
- Steuer **inkl. Besonderheiten wie Reverse Charge**
- Belegnummer
- kurzer Text für Steuerberater **(max. 255 Zeichen)**
- Quelle
- Absender / Gegenpartei
- Rechnungsdatum
- Eingangsdatum
- Betrag
- KIRA-Rückfrage / Nutzerantwort
- gespeicherte Begründung / Zweck
- Prüfstatus

### Kontierungslogik — verbindliche Regeln

Nutze **keine DATEV-, SKR03- oder SKR04-Standardkonten aus anderen Systemen**, wenn diese nicht tatsächlich in der aktuellen Lexware-Office-Umgebung vorhanden sind.

Stattdessen gilt:

- Prüfe bei jeder Zuordnung, ob das Konto oder die Posting Category tatsächlich **im aktuellen Lexware Office vorhanden** ist.
- Wenn unklar: **nicht raten**, sondern markieren.
- Praxisnah entscheiden, also nach wirtschaftlichem Zweck, nicht nach theoretischer Lehrbuchromantik.
- Keine unnötige Aufsplittung, wenn Lexware das nicht sinnvoll abbildet.
- Einheitliche, nachvollziehbare Linie für Steuerberater und Finanzamt.

### Sonderregel „camper“

Standard:

- **4540 – Reparaturen und Instandhaltung Kfz**

Gilt für:

- fest verbaute oder funktionsrelevante Teile
- Ausbau
- Technik
- Heizung
- Möbel

Ausnahmen:

- lose Teile → **4985 Werkzeuge/Betriebsbedarf**
- Verbrauchsmaterial → **3200 Material**

Wichtig:
Diese Regel ist als **projektbezogene fachliche Vorgabe** zu behandeln, aber nur dann direkt zu verwenden, wenn die betreffenden Konten bzw. Kategorien im aktuellen Lexware-Kontext wirklich vorhanden und passend sind.
Wenn die aktuelle Lexware-Konfiguration anders lautet oder die API-seitige Kategorie anders abbildet, muss das sauber markiert und nicht blind erzwungen werden.

### Ziel der Buchhaltungsvorbereitung

Die Buchung bzw. der Vorschlag soll:

- für Steuerberater sofort verständlich sein
- für das Finanzamt plausibel und belastbar sein
- keine Vermischung mit fremden Kontenrahmen produzieren
- später schnell wiedergefunden werden können

---

## Verpflichtende UI-Struktur für Lexware Office

### Grundsatz

Lexware Office soll in der Sidebar als eigenes Modul erscheinen, aber **nicht** als Einstellungsseite.

### Empfohlene Modulstruktur / Untermenüs

- Cockpit
- Belege
- Zahlungen
- Kontakte & Kunden
- Artikel & Preispositionen
- Dateien
- Buchhaltung
- Diagnose & Mapping

### Bereich „Buchhaltung“ oder „Lexware Buchhaltung“

Dieser Bereich ist ausdrücklich mit vorzusehen.
Dort sollen später sauber getrennt sichtbar sein:

- neue Eingangsbelege / zu prüfen
- bereits klassifizierte Belege
- abgelegte Belege
- unklare Fälle
- Such- und Filterfunktionen nach Zeitraum, Gegenpartei, Status, Betrag, Konto, Steuer, Abschreibung, Quelle
- Auswertungen / Übersichten, soweit belastbar

Wichtig:
Das soll eine **übersichtliche Arbeitsfläche** sein.
Nicht nur eine einfache Liste.

### Zusätzliche UI-Regeln

- klare Arbeitsoberfläche
- schnelle Wiederauffindbarkeit
- Suchfunktion
- Filter nach Zeitraum / Status / Quelle / Prüffall
- Detailsicht mit gespeichertem Kontext und Nutzerantwort
- KIRA-Frage und KIRA-Antwort nachvollziehbar sichtbar
- Beleghistorie sichtbar
- sauberer Status: neu, geprüft, vorbereitet, unklar, abgelegt, an Lexware übergeben

---

## Verbindliche Regeln für KIRA-Nutzung in diesem Modul

KIRA soll in Lexware Office nicht nur ein Chat-Button sein.

Sondern:

- KIRA kann Belege erklären
- KIRA kann Rechnungen / Angebote / Mahnungen prüfen
- KIRA kann Eingangsbelege vorbereiten
- KIRA kann Rückfragen stellen
- KIRA kann den vom Nutzer genannten Zweck in einen strukturierten Vorschlag übersetzen
- KIRA kann Buchhaltungstexte / Steuerberater-Notizen formulieren
- KIRA kann gespeicherte Prüfkontexte später wieder aufrufen

Wichtig:
Wenn ein Beleg später erneut geöffnet wird, muss der frühere KIRA-Kontext wieder sichtbar oder abrufbar sein.

---

## Verbindliche Regeln für Einstellungen

Alle Lexware-bezogenen Einstellungen gehören in **Einstellungen** im 3-Spalten-Menü.

### Dort unterzubringen oder vorzubereiten:

- API-Key / Verbindung
- Status / Verbindungstest
- Organisation / Profil
- Webhooks / Event-Subscriptions
- Sync-Verhalten
- Delta-Sync / Vollsync / Retry-Regeln
- Buchhaltungs-Prüfregeln
- Body-Analyse / Anhangsanalyse
- PayPal-Ausnahmen / Anbieterregeln / lernfähige Absenderregeln
- Detailgrad der Diagnose / Logs
- Dataverse-Zusatzexport
- Modulfreischaltung / Abo-Status
- Sichtbar aber gesperrt / aktiv / inaktiv

Wichtig:
Das Modul Lexware Office selbst zeigt diese Einstellungen **nicht** als Primärinhalt.

---

## Dataverse — verbindliche Zusatzregel

Dataverse bleibt gewünscht.
Die alte 00–04-Strecke ist dafür eine funktionierende Vorlage.

Aber:
Claude soll **nicht einfach nur diese PHP-Variante nachbauen**, sondern die offizielle Microsoft-Dokumentation prüfen und gegen den bestehenden Code abgleichen.

### Verbindliche Recherchefragen für Dataverse

- Funktioniert der bestehende Weg fachlich und technisch sauber?
- Ist die aktuelle Create-/Check-/Post-Variante robust genug?
- Ist **Upsert** mit **Alternate Keys** eine einfachere und wartbarere Lösung?
- Gibt es eine bessere Methode für Rechnungen und Positionsdaten?
- Wie werden Beziehungen / Fremdschlüssel sauber gepflegt?
- Ist eine einfachere Batch-/Mehrfachstrategie sinnvoll?

### Verbindliches Ziel

Wenn Claude eine **einfachere, robustere und klar wartbarere** Dataverse-Variante findet, soll er diese bevorzugen.
Der vorhandene PHP-Code ist Vorlage, nicht Dogma.

---

## Nummern-, Kunden- und Beleglogik

Dieser Bereich ist kritisch und darf nicht oberflächlich behandelt werden.

### Verbindliche Regeln

- Rechnungsnummern, Angebotsnummern und weitere Belegnummern müssen mit Lexware sauber übereinstimmen.
- Kundendaten und Kundennummern müssen abgeglichen werden.
- KIRA darf keine wilde Parallel-Nummerierung einführen.
- Wenn Lexware die finalen Belegnummern vergibt, muss KIRA damit sauber umgehen.
- KIRA muss Unterschiede zwischen Entwurf, KIRA-internem Datensatz, Lexware-Objekt und finaler Belegnummer nachvollziehbar speichern.
- Gleiches gilt für Kontakte / Kunden / Ansprechpartner.

---

## Technische Leitlinien

### 1. Nicht die alte Datei-Altstrecke einfach in neuem Gewand weiterziehen

Die aktuelle 00–04-Strecke arbeitet dateibasiert und teilweise nur mit der jeweils neuesten Datei.
Diese Logik darf nicht das neue KIRA-Produktzentrum bleiben.

### 2. Saubere Integrationsschicht bauen

Bevorzugt mit:

- eigenem Lexware-Client
- Throttling / Queue
- Delta-Sync
- Event-Subscriptions / Webhooks
- Fehler- / Retry-Strategie
- Mapping-Schicht
- normalisiertem KIRA-Cache

### 3. Runtime-Logging mitdenken

Alle wichtigen Aktionen in Lexware Office und dem Buchhaltungs-Prüfbereich sollen ins Runtime-Log eingebunden werden:

- Sync
- Belegerkennung
- Body-Extraktion
- Nutzer-Rückfrage
- Klassifizierung
- Kontierungsvorschlag
- Lexware-Übergabe
- Dataverse-Export
- Fehler / Teilfehler

### 4. KIRA-Kontextfähigkeit mitdenken

KIRA soll diese Datensätze später sinnvoll lesen und verwenden können.

---

## Recherchepflicht: offene technische Realität sauber prüfen

Nicht raten.
Nicht nur hoffen.

Sondern sauber prüfen und dokumentieren:

- welche Lexware-Endpunkte in v1 wirklich nutzbar sind
- ob Eingangsbelege direkt API-seitig erstellt / aktualisiert / vorklassifiziert werden können
- wie Posting Categories und Voucher-Kategorien konkret funktionieren
- was bei Dateien / PDF / XML / E-Rechnungen geht
- wo Grenzen der API liegen
- was nur vorbereitet werden kann

Wenn etwas API-seitig heute **nicht** sauber möglich ist:

- offen sagen
- sichtbar vorbereiten
- nicht so tun, als sei es live

---

## Verbindliche erste Arbeitsausgabe vor Implementierung

Bevor du etwas implementierst, liefere zuerst genau diese Punkte:

1. Ergebnis des Plan-Agenten
2. Gap-Analyse Ist/Soll
3. Liste aller betroffenen Dateien, Datenbanken, APIs, Module und Logs
4. Liste aller bereits vorhandenen Lexware-, Dataverse-, Dokument-, Geschäfts-, Kunden- und KIRA-Bausteine
5. Plan-Dateien und Checklisten angelegt
6. Recherche-Ergebnis Lexware + Dataverse
7. Architektur-Empfehlung:
   - empfohlene v1
   - vorbereitete v2
8. sichere Umsetzungsreihenfolge in kleinen Paketen

Erst danach implementieren.

---

## Verbindliche Reihenfolge der Umsetzung

1. Session-Start nach AGENT.md
2. Plan-Agent laufen lassen
3. Repo-Audit durchführen
4. Plan-Dateien anlegen
5. Gap-Analyse schreiben
6. Internet-Recherche Lexware + Microsoft durchführen
7. Architektur definieren
8. Buchhaltungs-Prüfbereich definieren
9. Auswirkungen auf Geschäft, Kunden, Dokumente, Kira und Einstellungen prüfen
10. erst dann Implementierung in kleinen Paketen
11. nach jedem Paket testen
12. nach jedem Paket committen
13. Tracking-Dateien aktualisieren
14. offene Punkte explizit dokumentieren

---

## Abschlussformat nach jeder abgeschlossenen Arbeitseinheit

Nach jeder Phase oder abgeschlossenen Arbeitseinheit klare Rückmeldung mit:

- was wurde geprüft
- was wurde recherchiert
- was wurde entschieden
- welche Dateien sind betroffen
- was war schon da
- was wurde erweitert statt neu gebaut
- was ist funktionsfähig
- was ist nur vorbereitet
- was ist offen
- was ist der nächste sinnvolle Schritt

Zusätzlich die Abschluss-Tabelle aus `AGENT.md` ausgeben.

---

## Letzte Klarstellung

Dieser Auftrag ist kein kleiner Zusatz.
Er ist ein Architektur-, Geschäfts-, Buchhaltungs- und Workflow-Umbau mit eigenem Zusatzmodul.

Die wichtigste Regel lautet:

Nicht schneller bauen.
Richtiger denken.
Strukturiert prüfen.
Internet sinnvoll nutzen.
Plan-Dateien anlegen.
Checklisten aktuell halten.
Nichts stillschweigend weglassen.

Und ganz besonders:

- Priorität ist **KIRA ↔ Lexware als echte Arbeitsintegration**
- Einstellungen bleiben in **Einstellungen**
- Dataverse bleibt **Zusatzpfad**
- Eingangsbelege / Buchhaltungsvorbereitung sind **zusätzlicher Pflichtbereich**
- Abo-/Freischaltlogik ist **von Anfang an vorzubereiten**

---

## Ergänzung — Lernfähige Regeln für Eingangsbelege, wiederkehrende Rechnungen und automatische Vorbefüllung

Diese Ergänzung ist verbindlich zusätzlich zu allen bisherigen Anforderungen umzusetzen und darf nicht weggelassen werden.

### Ziel

KIRA soll im Bereich **geschäftliche Eingangsbelege / Buchhaltung prüfen** nicht nur einmalige Belege erkennen, sondern aus bestätigten Benutzerentscheidungen lernen.

Das Ziel ist:

- wiederkehrende Eingangsbelege intelligenter behandeln
- bekannte Belegmuster automatisch wiedererkennen
- bereits bestätigte Klassifizierungen und Zusatzangaben erneut verwenden
- nur dann erneut nachfragen, wenn der aktuelle Fall vom bekannten Muster abweicht oder die Sicherheit nicht ausreicht
- den Benutzer bei Routinebelegen spürbar entlasten, ohne blind zu raten

### Wichtige Grundregel

Automatisierung ist hier ausdrücklich erwünscht, aber nur kontrolliert.

Das bedeutet:

- bei hoher Übereinstimmung mit bereits bestätigten Fällen darf KIRA Felder automatisch vorbefüllen oder – wenn die Freigabelogik es erlaubt – automatisch einordnen
- bei mittlerer oder niedriger Sicherheit darf KIRA nicht raten, sondern muss sichtbar markieren: **Bitte prüfen**
- jede automatische Übernahme muss nachvollziehbar dokumentiert werden
- der Benutzer muss sehen können, auf welcher früheren Entscheidung oder Regel die Vorbefüllung basiert

### Lernfähige Regelbasis für Eingangsbelege

Bitte zusätzlich eine lernfähige Regel- und Musterlogik für geschäftliche Eingangsbelege einführen oder vorbereiten.

Diese Logik soll mindestens drei Ebenen unterstützen:

#### 1. feste Regeln

Vom Benutzer oder System bewusst angelegte Regeln, z. B.:

- PayPal grundsätzlich nicht als Rechnung behandeln
- Apple-Mail nur dann als Eingangsbeleg behandeln, wenn der Rechnungsinhalt im Body erkannt wird
- bestimmte Versender immer als Prüf-Fall behandeln
- bestimmte Belegquellen immer in einen definierten Prüfstatus setzen

#### 2. gelernte Muster

Aus bereits bestätigten Belegen abgeleitete Wiedererkennungen, z. B.:

- gleicher Absender
- gleicher Lieferant
- gleicher Betrefftyp
- ähnliche Body-Struktur
- ähnliche Positions- oder Abo-Bezeichnung
- ähnliche Steuerlogik
- gleiches wirtschaftliches Einsatzgebiet
- wiederkehrender Monats- oder Jahresbezug

#### 3. wiederkehrende Belegvorlagen / Abomuster

Spezielle Logik für wiederkehrende Belege, z. B.:

- Apple-Abos
- SaaS-Abos
- Hosting
- Tools
- Cloud-Dienste
- Softwarelizenzen
- Versicherungen
- Telefon / Internet
- wiederkehrende Material- oder Servicekosten

Wird ein solches Muster nach mehreren bestätigten Fällen stabil erkannt, soll KIRA den nächsten Beleg derselben Art bereits mit den bekannten Zusatzinformationen vorbelegen können.

### Konkrete gewünschte Arbeitslogik

Wenn ein neuer Eingangsbeleg erkannt wird, soll KIRA künftig in dieser Reihenfolge arbeiten:

1. prüfen, ob es sich überhaupt um einen geschäftlichen Eingangsbeleg handeln könnte
2. PayPal und ähnliche reine Zahlungsmitteilungen ausfiltern
3. Anhänge und Body-Inhalt prüfen
4. bei Body-only-Fällen wie Apple gezielt den Textinhalt als mögliche Rechnungsquelle auswerten
5. Lieferant / Absender / Muster / bekannte Regelbasis prüfen
6. nachsehen, ob es bereits bestätigte ähnliche Fälle gibt
7. wenn ja:
   - bekannte Angaben übernehmen oder vorbefüllen
   - Herkunft dieser Übernahme dokumentieren
8. wenn nein oder wenn etwas abweicht:
   - Benutzer gezielt fragen
   - neue Erkenntnis als lernbare Regel oder Muster speichern

### Beispiel Apple / Abo-Fälle

Wenn Apple-Rechnungen oder ähnliche Body-basierte Abo-Belege mehrfach bestätigt wurden, soll KIRA nicht jeden Monat dieselbe Rückfrage stellen.

Sondern:

- Apple als bekannte Quelle erkennen
- Body auswerten
- prüfen, ob Abo / Produkt / Betrag / Beschreibung zu einem bekannten Muster passen
- wenn ausreichend ähnlich:
  - bekannte Zuordnung automatisch vorbefüllen
  - z. B. Zweck, Bereich, Belegtyp, Buchungshinweis, Steuerberatertext
- wenn Abweichung erkannt wird:
  - nicht blind übernehmen
  - stattdessen markieren: **Apple erkannt, aber Inhalt weicht vom bekannten Muster ab – bitte prüfen**

Diese Logik gilt sinngemäß auch für andere wiederkehrende Lieferanten und Abo-Modelle.

### KIRA soll Regeln später direkt erweitern können

Bitte zusätzlich vorsehen oder umsetzen, dass neue Regeln und Filter nicht nur manuell in starren Einstellungsformularen entstehen.

Sondern möglichst auch über KIRA selbst.

Beispiel:

Der Benutzer erklärt im Gespräch mit KIRA:

- dieser Absender ist keine Rechnung
- diese Apple-Mail ist immer ein Abo für X
- diese wiederkehrende Rechnung gehört immer zu Bereich Y
- diese Art Beleg bitte künftig automatisch so vorbelegen

Dann soll KIRA diese Information – nach Bestätigung – als neue nutzbare Regel oder als lernbares Muster speichern können.

Wichtig:

- KIRA darf solche Regeln nicht heimlich ohne Kontrolle scharf schalten
- neue Regeln müssen nachvollziehbar sein
- neue Regeln müssen bearbeitbar, deaktivierbar und löschbar sein
- es muss sichtbar sein, ob etwas eine feste Regel, ein gelernter Vorschlag oder ein bestätigtes Abomuster ist

### Eigener Verwaltungsbereich für diese Lernlogik

Bitte dafür in der UI einen passenden Bereich vorsehen.

Das kann entweder:

- im Modul Lexware Office unter einem Unterbereich wie **Buchhaltung prüfen / Regeln & Muster**
- oder im Dokumente-/Eingangsbelegbereich mit Lexware-Bezug
- oder zusätzlich zentral in Wissen / Regelsteuerung

sichtbar werden.

Dort sollen mindestens verwaltbar sein:

- feste Filterregeln
- Ausnahmen wie PayPal
- Body-only-Regeln
- Lieferantenmuster
- Abo-Muster
- wiederkehrende Vorbelegungen
- Sicherheitsstufe
- Auto-Vorbelegung ja/nein
- Auto-Ablage ja/nein
- nur Vorschlag / vollautomatisch / immer prüfen
- letzte Verwendung
- Herkunft der Regel

### Sicherheitslogik für automatische Übernahme

Ganz wichtig:

Nicht alles, was ähnlich aussieht, darf blind übernommen werden.

Darum soll Claude eine saubere Sicherheitslogik bauen oder vorbereiten:

#### automatische Übernahme nur wenn:

- Quelle passt
- Inhalt ausreichend ähnlich
- Betrag / Turnus / Kategorie plausibel
- bekannte Zuordnung vorhanden
- keine widersprüchlichen Signale erkannt werden

#### Prüfpflicht wenn:

- Betreff oder Body deutlich abweicht
- Betrag stark abweicht
- Steuerlogik nicht passt
- neues Produkt / neues Abo / neuer Leistungsumfang erkannt wird
- Lieferant zwar gleich ist, aber der Inhalt anders wirkt
- bisher keine ausreichend belastbare Regel vorhanden ist

Dann soll KIRA dem Benutzer klar sagen, warum geprüft werden muss.

Nicht nur: **unsicher**

Sondern z. B.:

- bekannter Lieferant, aber anderer Leistungsinhalt
- gleiches Apple-Konto, aber neues Abo erkannt
- Betrag weicht deutlich vom bisherigen Muster ab
- Body passt nicht zur bekannten Rechnungsstruktur

### Auto-Vorbefüllung statt blindem Vollautomatismus

Standardmäßig soll nicht alles vollautomatisch final verbucht werden.

Bevorzugt wird:

- automatische Erkennung
- automatische Vorbefüllung
- sichtbarer Herkunftshinweis
- schnelle Bestätigung durch den Benutzer

Vollautomatische Ablage oder Vorklassifizierung ohne Prüfung soll nur dann möglich sein, wenn:

- genügend bestätigte Vergleichsfälle existieren
- die Sicherheitslogik hoch genug ist
- diese Automatik ausdrücklich erlaubt wurde
- der Fall in einen dafür freigegebenen Regeltyp fällt

### Pflicht für Protokollierung und Nachvollziehbarkeit

Jede lernbasierte Übernahme, Vorbefüllung oder automatische Zuordnung muss sauber im Runtime-/Kontext-Log festgehalten werden.

Mindestens:

- welcher Beleg erkannt wurde
- welche Regel oder welches Muster gegriffen hat
- welche früheren Fälle als Grundlage dienten
- welche Felder automatisch gesetzt wurden
- ob nur vorgeschlagen oder automatisch übernommen wurde
- ob der Benutzer bestätigt oder korrigiert hat
- ob daraus eine neue Regel entstanden ist

### Bezug zu der bestehenden Buchhaltungs-Prüflogik

Diese neue Lernlogik ist ein Zusatz auf die bereits definierte Logik für:

- geschäftliche Eingangsbelege / Buchhaltung prüfen
- Konto-Vorschlag in Lexware Office
- Abschreibung ja/nein
- Steuerlogik
- Belegnummer
- kurzer Steuerberatertext
- wirtschaftlicher Zweck statt theoretischer Musterbuchung

Wichtig:

Die Lernlogik ersetzt diese fachliche Prüfung nicht.
Sie soll sie nur beschleunigen und intelligenter machen.

### Verbindliche Arbeitsanweisung an Claude

Bitte ergänze den Auftrag so, dass KIRA im Bereich geschäftliche Eingangsbelege zusätzlich eine lernfähige Regel- und Musterlogik für wiederkehrende Belege erhält.

Wichtig:

- PayPal-Ausnahme beibehalten
- Body-Analyse für Apple- und ähnliche Fälle beibehalten
- neue Regeln möglichst auch über KIRA-Gespräche anlegbar machen
- wiederkehrende Rechnungen nicht jeden Monat neu vollständig abfragen
- bekannte bestätigte Zusatzinformationen automatisch wiederverwenden
- bei Abweichungen Prüfpflicht setzen
- alles nachvollziehbar loggen
- Regeln und Muster sichtbar verwaltbar machen
- automatische Übernahme nur mit Sicherheitslogik und Freigabemodell

Wenn Claude im Projekt eine technisch sauberere Struktur findet, darf er sie wählen.
Aber das Ziel muss vollständig erhalten bleiben:

**KIRA soll aus bestätigten Eingangsbelegen lernen, wiederkehrende Fälle intelligent vorbefüllen oder teilweise automatisch behandeln und nur dann erneut fragen, wenn der neue Fall nicht sauber zum bekannten Muster passt.**

---

## Zusatzergänzung — Standardmodus für Eingangsbelege + vorbereitete Vollautomatik

Diese Ergänzung ist verbindlich und kommt zusätzlich zu allen bisherigen Punkten hinzu.
Sie ersetzt nichts aus den bisherigen Anforderungen, sondern schärft den Zielmodus für den Umgang mit geschäftlichen Eingangsbelegen in Verbindung mit Lexware Office.

### 1. Standardmodus als Pflicht für v1

Der Standardmodus für geschäftliche Eingangsbelege soll so aufgebaut werden:

1. Beleg wird von KIRA erkannt und fachlich geprüft.
2. KIRA analysiert Anhang, Body, Absender, Betreff, bekannte Muster, frühere Fälle und Benutzerhinweise.
3. KIRA schlägt die nötigen Felder vor:
   - Lexware-Konto bzw. passende Lexware-Posting-Category
   - Abschreibung ja/nein
   - Steuerlogik inkl. Besonderheiten
   - Belegnummer
   - Steuerberater-Kurztext
   - wirtschaftlicher Zweck / Bereich
4. Benutzer prüft den Fall in KIRA und bestätigt, ergänzt oder korrigiert.
5. Danach wird der Beleg **inklusive der in KIRA ausgefüllten und bestätigten Informationen** an Lexware Office übergeben.
6. In Lexware soll der Beleg dabei standardmäßig als **normaler Prüfbeleg** bzw. **zu prüfender Buchhaltungsbeleg** hinterlegt werden, aber mit möglichst vielen bereits vorbereiteten Informationen.

Wichtig:
Der Standardmodus ist **nicht** „blind fertig buchen“.
Er ist:

- intelligent erkennen
- sauber vorprüfen
- in KIRA bestätigen
- mit Zusatzinformationen an Lexware übergeben
- dort regulär im Buchhaltungsfluss verfügbar machen

Das Ziel ist:
Der Benutzer soll die eigentliche Denk- und Vorarbeit in KIRA machen oder durch KIRA vorbereiten lassen, damit der Beleg in Lexware nicht mehr roh und leer auftaucht.

### 2. Zweite Variante verbindlich mit einbauen: „komplett automatisch fertig buchen“

Zusätzlich zum Standardmodus muss eine zweite, echte Betriebsart **vollständig mit eingebaut** werden:

**„komplett automatisch fertig buchen“**

Wichtig:

- diese Variante ist **nicht** nur vorzubereiten
- sie ist **komplett mit umzusetzen**
- sie bleibt **sauber getrennt** vom Standardmodus „in KIRA prüfen und dann als Prüfbeleg an Lexware übergeben“
- sie ist **nicht Default**, aber technisch real funktionsfähig
- bis Rollen-/Rechte-/Freigabelogik später sauber fertig ist, darf sie vorerst allgemein verfügbar oder über einfachen Modul-/Abo-Status steuerbar sein
- die Architektur muss trotzdem schon so gebaut werden, dass später Freigaben, Rollen und Einschränkungen ohne Neubau ergänzt werden können

Diese Vollautomatik bedeutet:

1. KIRA erkennt einen geschäftlichen Eingangsbeleg.
2. KIRA prüft Anhang, Body, Absender, Betreff, bekannte Lieferantenmuster, bekannte Abo-Fälle, frühere Benutzerentscheidungen und vorhandene Lexware-Kategorien.
3. KIRA entscheidet **nur bei hoher Sicherheit**, dass der Fall automatisch fertig verarbeitet werden darf.
4. KIRA erzeugt oder vervollständigt den passenden Buchhaltungsbeleg in Lexware mit den nötigen Voucher-Daten, den nötigen Voucher-Positionen und den zugehörigen Zusatzinformationen.
5. KIRA finalisiert den Beleg so weit API-seitig sinnvoll, damit er in Lexware **nicht** nur roh unter „zu prüfen“ liegt, sondern möglichst bereits fertig im vorgesehenen Buchhaltungsfluss landet.
6. Jede automatische Fertigbuchung muss vollständig protokolliert, nachvollziehbar und später auffindbar sein.

Wichtig:

- diese Vollautomatik darf **niemals blind raten**
- sie darf nur greifen, wenn der Fall durch Regeln, Muster, Historie und aktuelle Lexware-Datenlage ausreichend sicher ist
- bei Unsicherheit, Abweichung, neuem Sachverhalt oder fehlender Kategorie muss automatisch in den Standard-Prüfmodus zurückgefallen werden

### 3. Lernlogik für wiederkehrende Belege ist Pflicht

Für die Vollautomatik und den Standardmodus gilt gemeinsam:

KIRA soll aus bestätigten Eingangsbelegen lernen und wiederkehrende Fälle intelligent erkennen.

Das betrifft insbesondere:

- wiederkehrende Lieferanten
- Abo-Modelle
- Apple-Body-only-Rechnungen
- typische wiederkehrende Leistungen
- immer gleiche wirtschaftliche Zwecke
- bekannte Kontierungsregeln
- bekannte Steuerlogiken
- bekannte Kurztexte für den Steuerberater

Wenn zum Beispiel ein wiederkehrender Beleg vom selben Anbieter inhaltlich und fachlich zum bekannten Muster passt, dann soll KIRA:

- den Fall automatisch erkennen
- die früher bestätigten Angaben übernehmen
- Konto / Kategorie nur aus den **aktuell vorhandenen Lexware-Kategorien** wählen
- Steuerlogik übernehmen, wenn der Fall dazu passt
- Kurztext und Zweckbeschreibung vorbefüllen
- den Fall je nach Modus entweder
  - automatisch in den Prüfmodus vorbereiten oder
  - bei hoher Sicherheit direkt vollständig fertig buchen

Wenn sich dagegen relevante Dinge ändern, zum Beispiel:

- anderer Leistungsinhalt
- anderer wirtschaftlicher Zweck
- neuer Abo-Typ
- abweichender Bodytext
- ungewohnter Betrag
- andere Steuerlogik
- fehlende oder geänderte Lexware-Kategorie

dann darf KIRA **nicht automatisch durchbuchen**, sondern muss den Fall als Prüffall markieren und den Benutzer gezielt um Einordnung bitten.

Zusätzlich soll Claude vorsehen, dass solche Regeln und Muster nicht nur technisch intern entstehen, sondern auch aktiv verwaltbar sind:

- neue Regel aus bestätigtem Fall lernen
- bestehende Regel anpassen
- Auto-Regel deaktivieren
- Sicherheit / Confidence festlegen
- Quelle der Regel anzeigen
- über KIRA-Gespräch neue Filter- und Erkennungsregeln anlegen oder erweitern, wenn sinnvoll

### 3. Nur tatsächlich vorhandene Lexware-Kategorien verwenden

Ganz wichtig:
Wenn KIRA bei Eingangsbelegen prüft, wohin ein Beleg gehört, darf sie **ausschließlich** Kategorien/Konten/Posting Categories verwenden, die in der aktuell angebundenen Lexware-Umgebung tatsächlich vorhanden und gültig sind.

Das bedeutet:

- keine fremden DATEV-, SKR03- oder SKR04-Listen aus anderen Systemen verwenden
- keine hart codierten Fremdkontenraster als Wahrheit behandeln
- keine Kategorien raten, die in Lexware Office aktuell nicht verfügbar sind
- keine statischen Annahmen treffen, wenn Lexware sich ändert

Stattdessen verpflichtend:

- aktuelle Lexware-Posting-Categories und relevante Buchhaltungsoptionen regelmäßig per API abrufen
- lokal gecacht halten, aber kontrolliert aktualisieren
- Änderungen erkennen und im System nachziehen
- wenn neue Kategorien hinzukommen oder alte sich ändern, muss KIRA das merken und künftig mit dem aktualisierten Stand arbeiten
- wenn eine Kategorie unklar oder nicht mehr vorhanden ist, darf KIRA nicht raten, sondern muss den Fall kennzeichnen

### 4. Synchronisations- und Aktualisierungslogik für Lexware-Kategorien

Bitte dafür eine saubere Aktualisierungslogik vorsehen:

- regelmäßiger Sync der relevanten Lexware-Kategorien / Posting Categories
- zusätzlicher Refresh bei wichtigen Integrationsereignissen
- manueller Aktualisieren-Button im Einstellungsbereich
- sichtbarer Zeitstempel „zuletzt mit Lexware-Kategorien abgeglichen“
- Warnstatus, wenn Kategorie-Cache veraltet oder fehlerhaft ist

Wichtig:
KIRA soll die Kategorien nicht „durch Nachfragen in der Doku“ aktuell halten, sondern primär **über die echte Lexware-API / den echten Lexware-Datenstand**.
Offizielle Dokumentation dient nur als technische Referenz, nicht als laufende Live-Datenquelle für konkrete Buchungskategorien der Benutzerumgebung.

### 5. UI- und Einstellungslogik dazu

Bitte im Bereich Einstellungen und im Lexware-Modul vorbereiten bzw. einbauen:

#### In Einstellungen:

- Standardmodus für Eingangsbelege
- vorbereitete Vollautomatik als gesonderter Modus / Zusatzfunktion
- Auto-Refresh für Lexware-Kategorien
- manueller Kategorie-Refresh
- letzte erfolgreiche Kategorie-Synchronisation
- Sicherheitsstufe für automatische Vorbefüllung
- Sicherheitsstufe für spätere Vollautomatik
- Verhalten bei unbekannter Kategorie
- Verhalten bei Kategorie-Konflikt
- Logging-Detailgrad für Buchhaltungsentscheidungen

#### Im Arbeitsbereich für Eingangsbelege:

- sichtbar, ob der Fall nur intern geprüft wurde
- sichtbar, ob der Beleg nur als Prüfbeleg an Lexware übergeben wurde
- sichtbar, ob bereits strukturierte Zusatzinfos mitgesendet wurden
- sichtbar, ob der Fall nur vorbefüllt oder vollständig finalisiert wurde
- sichtbar, welche Lexware-Kategorie gewählt wurde und woher sie stammt
- sichtbar, wann der Kategoriestand zuletzt mit Lexware abgeglichen wurde

### 6. Verbindliche Arbeitsanweisung an Claude

Bitte ergänze den Auftrag so, dass für geschäftliche Eingangsbelege zwei Modi sauber vorgesehen werden:

#### Modus A — Standardmodus (Pflicht für v1)

- Beleg in KIRA erkennen und prüfen
- Benutzer bestätigt oder ergänzt die Zuordnung
- ausgefüllte Informationen werden am Beleg mitgeführt
- Beleg wird mit diesen Informationen an Lexware Office übergeben
- Standardziel: normaler Prüf-/Buchhaltungsfluss in Lexware, nicht rohe Datei ohne Kontext

#### Modus B — Vollautomatik (nur vorbereiten)

- „komplett automatisch fertig buchen“ als gesonderte Zusatzfunktion vorbereiten
- aktuell nicht als Standard behandeln
- technisch kapseln
- für spätere Freischaltung / Rollenlogik / Abo-Modell vorbereiten

Außerdem verbindlich:

- KIRA darf nur aktuell vorhandene Lexware-Kategorien verwenden
- diese Kategorien müssen regelmäßig per Lexware-API synchronisiert werden
- bei Änderungen muss KIRA den Kategoriestand aktualisieren
- bei Unsicherheit oder veralteten Kategorien nicht raten
- jede Kategorieentscheidung und jede automatische Vorbelegung sauber loggen

### 7. Zielbild in einem Satz

**Der Standardweg soll sein: Eingangsbeleg in KIRA prüfen, Informationen ergänzen, dann mit vorbereiteten Daten als sauberer Prüfbeleg an Lexware übergeben. Die Vollautomatik „komplett automatisch fertig buchen“ wird als spätere Zusatzfunktion vorbereitet, aber nicht als aktueller Default behandelt.**
