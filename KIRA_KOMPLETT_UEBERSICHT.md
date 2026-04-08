# Kira Assistenz -- Komplettübersicht

> Stand: 27.03.2026 | Dashboard v4 | localhost:8765
>
> **Änderungen seit 25.03.:** session-g (Kira-Workspace UI Rebuild kq-*/kw-*) + session-h (Runtime-Log-System)

---

## 1. Was Kira ist

Kira ist die KI-gestützte Geschäftsassistenz für rauMKult Sichtbeton. Sie läuft als lokaler Server (localhost:8765) und verbindet automatisierte E-Mail-Überwachung, Aufgabenverwaltung, Finanz-Tracking, Wissensspeicher und Multi-LLM-Chat in einem Dashboard.

**Technologie:** Python 3.13, SQLite, eigener HTTP-Server, JavaScript-Frontend
**Datenquellen:** 5 Mail-Postfächer, 12.642 Mails, 7.321 Kundeninteraktionen, 525 gesendete Mails

---

## 2. Was Kira automatisch im Hintergrund tut

### 2.1 Tägliche E-Mail-Überwachung (`daily_check.py`)
- Scannt alle 5 Postfächer (anfrage@, info@, invoice@, shop@, intern@) auf neue Mails
- Klassifiziert jede Mail automatisch in 9 Kategorien (Lead, Antwort nötig, Rechnung, Newsletter etc.) sollte bei direkt mail einbindung automatisch nutzlose newletter abbestellen!
- Erstellt Aufgaben für alle handlungsrelevanten Mails
- Generiert Antwort-Entwürfe basierend auf Situation und Kais Schreibstil
- Ignoriert automatisch: System-Mails, Newsletter, bereits beantwortete Mails
- Läuft als Windows Scheduled Task (konfigurierbar)

### 2.2 Push-Benachrichtigungen
- **ntfy.sh:** Sofort-Push auf iPhone wenn neue Aufgaben erkannt werden
- **Windows Toast:** Native Desktop-Benachrichtigung mit Link zum Dashboard
- Priorisierung: Hohe Priorität bei unbeantworteten Kundenanfragen
- Zusammenfassung: "3 Antworten nötig, 1 neuer Lead, 2 Rechnungen"

### 2.3 Datenbank-Aufbau (`build_databases.py`)
- Indiziert alle 12.642+ Mails mit Metadaten
- Baut Kundenstamm automatisch aus allen Interaktionen
- Klassifiziert 4.646 Newsletter (relevant/irrelevant/unklar)
- Extrahiert und bereinigt 525 gesendete Mails als Stil-Lernbasis

### 2.4 Rechnungs-PDF-Extraktion (`scan_rechnungen_detail.py`)
- Liest alle Rechnungs-PDFs automatisch aus
- Extrahiert: RE-Nummer, Datum, Kunde, Positionen, Beträge, MwSt
- Erkennt Zahlungsziel und Skonto-Fristen automatisch
- Erkennt Mahnungen und ordnet sie der richtigen Rechnung zu
- Korrigiert Tippfehler in RE-Nummern automatisch

### 2.5 Automatisches Lernen
- Jede Statusänderung (bezahlt, angenommen, abgelehnt) erzeugt einen Wissenseintrag
- Zahlungsdauer pro Kunde wird getrackt und gemittelt
- Angebots-Erfolgsquote wird berechnet
- Ablehnungsgründe werden kategorisiert und gespeichert
- Korrekturen an der Mail-Klassifizierung fließen in zukünftige Einordnung ein

---

## 3. Was Kira aktiv im Dashboard zeigt

### 3.1 Dashboard (Startseite)
| KPI | Beschreibung |
|-----|-------------|
| Antworten nötig | Unbeantwortete Kundenanfragen (rot wenn > 0) |
| Neue Leads | Erstanfragen von Interessenten |
| Angebotsrückmeldungen | Reaktionen auf gesendete Angebote |
| Termine/Fristen | Anstehende Deadlines und Rückrufbitten |
| Geschäft (30 Tage) | Rechnungen und Zahlungen im letzten Monat |
| Rechnungen/Belege | Eingangsrechnungen zur Bearbeitung |
| Gesamt offen | Alle offenen Aufgaben |

Plus: Top-5 dringendste Aufgaben, nächste Termine, letzte Geschäftsvorgänge

### 3.2 Kommunikation
- Aufgabenkarten gruppiert nach Kategorie
- Pro Karte: Priorität, Zusammenfassung, empfohlene Aktion, Absender-Rolle
- Erinnerungs-Badge (1./2./3. Erinnerung, farblich eskalierend)
- Buttons: Kira fragen, In Outlook öffnen, Anhänge, Mail lesen, Erledigt, Später, Ignorieren, Korrektur

### 3.3 Organisation
- Erkannte Termine mit Datum
- Fristen und Deadlines
- Rückrufbitten von Kunden
- Jeweils mit Kunde, Konto, Kontext

### 3.4 Geschäft (5 Sub-Tabs)

**Übersicht:**
- Offenes Rechnungsvolumen als Hero-Zahl (EUR)
- KPI-Karten: Offene Rechnungen, Angebote, fällige Nachfass, Mahnungen
- Skonto-Alerts: Welche Rechnungen haben Skonto-Frist, wie viel spart man, wie viele Tage noch
- Dringendste Punkte quer über alle Kategorien
- Statistik: Erfolgsquote Angebote, durchschnittl. Zahlungsdauer, Gesamtvolumen

**Ausgangsrechnungen:**
- Vollständige Tabelle aller gesendeten Rechnungen
- Filter nach Jahr
- Status: offen / bezahlt / Streitfall
- Aktion "Bezahlt markieren" mit Datum, Betrag, Grund-Abfrage
- Mahnung-Count pro Rechnung

**Angebote:**
- Alle Angebote mit Nachfass-Countdown (1/3, 2/3, 3/3)
- Nächster Nachfass-Termin (gelb = heute fällig)
- Status: offen / angenommen / abgelehnt / keine Antwort / bearbeitet
- Aktion: Status setzen, Nachfass-Mail generieren

**Eingangsrechnungen:**
- Offene Lieferantenrechnungen als Karten
- Status-Tracking: offen / bezahlt / Streitfall

**Mahnungen:**
- Cross-Referenz mit Ausgangsrechnungen
- Mahnhistorie: Stufe 1/2/3 mit Datum und Beträgen
- Mahngebühren und Zinsen

### 3.5 Wissen
- 7 Kategorien: Feste Regeln, Stil, Preise, Technik, Prozess, Gelernt, Vorschläge
- 9 fest hinterlegte Grundregeln (z.B. "Keine Preise im ersten Kontakt")
- Automatisch gelernte Regeln aus jeder Interaktion
- Vorschläge von Kira zum Freigeben/Ablehnen
- Jede Regel editierbar, löschbar, verschiebbar

### 3.6 Einstellungen
- Push-Benachrichtigungen (ntfy.sh Konfiguration)
- Aufgaben-Parameter (Erinnerungsintervall, Prüfzeitraum)
- Nachfass-Intervalle (10/21/45 Tage, anpassbar)
- Server-Port und Auto-Browser
- **Multi-LLM Provider-Verwaltung:**
  - Provider hinzufügen/entfernen/sortieren
  - API Key pro Provider
  - Modell-Auswahl pro Provider
  - Prioritäts-Reihenfolge für automatischen Fallback
  - Status-Anzeige (bereit / kein Key / Paket fehlt)

---

## 4. Was man mit Kira im Chat machen kann

### 4.1 Direkte Gespräche
- Chat-Interface im Kira-Panel (rechte Seite)
- Session-basiert mit Historie
- Kira kennt bei jedem Gespräch: alle offenen Rechnungen, Angebote, Aufgaben, Kunden, Wissensregeln

### 4.2 Verfügbare Tools (9 Stück)

| Tool | Was es tut |
|------|-----------|
| `rechnung_bezahlt` | Rechnung als bezahlt markieren (Datum, Betrag, Methode erfassen) |
| `angebot_status` | Angebotsstatus ändern (angenommen/abgelehnt + Grund) |
| `eingangsrechnung_erledigt` | Eingangsrechnung als erledigt markieren |
| `kunde_nachschlagen` | Kundendatenbank durchsuchen (alle Interaktionen) |
| `nachfass_email_entwerfen` | Nachfass-Mail generieren (3 Stufen: freundlich/bestimmt/letzte Chance) |
| `wissen_speichern` | Erkenntnis im Wissenspeicher ablegen |
| `rechnungsdetails_abrufen` | Rechnungspositionen, Skonto, Zahlungsziel abrufen |
| `web_recherche` | Internet-Suche (DuckDuckGo, optional zuschaltbar) |
| `runtime_log_suchen` | **NEU (session-h)** — Kira durchsucht eigenes Ereignisprotokoll (nur wenn `kira_darf_lesen=True`) |

### 4.3 Kira Workspace UI — 3-Ebenen-Architektur (session-g)

**Ebene 1: Kira Launcher (FAB)**
- Lila Schwebeschaltfläche unten rechts
- Klick → öffnet Quick Panel

**Ebene 2: Quick Panel (kq-*)**
- Overlay mit 7 farbigen Icon-Items + Pfeilen
- Header: K-Logo, "Kira", Status-Dot, X-Button
- Footer: Direkt-Input (`kqInput`) + Senden-Button (`kqDirectSend()`)
- Items: Neue Frage (purple), Aufgaben (amber), Rechnungen (green), Angebote (blue), Kunden (coral), Letzte Verläufe (gray), Suche (teal)

**Ebene 3: Workspace (kw-*)**
- Vollbild-Overlay: `kw-shell` (96vw, max-1260px, 87vh)
- **3 Spalten:**
  - Links: `kw-ctx-panel` (240px) — Navigation (Chat/Aufgaben/Muster/Wissen) + History-Sidebar
  - Mitte: `kw-center` — Kontext-Bar (`kw-cbar`, default hidden), Tabs, Quick-Actions-Bar, Input-Bereich
  - Rechts: `kw-tools` (240px, collapsible) — Anhänge, Regeln, Aktionen
- **Kontext-Bar** (`kw-cbar`): zeigt aktiven Kontext (z.B. "Rechnung RE-2026-001 | Kunde X")
- **Quick-Actions-Bar**: 4 kontextspezifische Buttons je nach `kiraSetQuickActions(typ)`
- **7 Kontext-Typen**: frage / aufgabe / rechnung / angebot / kunde / suche / dokument

**Navigation**: `showKTab(name)` — verwendet `data-tab="name"` Attribut (nicht textContent)

### 4.4 Aufgaben-Kontext
- Klick auf "Mit Kira besprechen" bei jeder Aufgabe
- Kira bekommt automatisch: Betreff, Kunde, Zusammenfassung, Entwurf, Anhänge
- Kann gezielt zu einer Aufgabe beraten, Antwort verfeinern, Strategie vorschlagen

### 4.5 Konversations-Historie
- Alle Gespräche gespeichert und abrufbar
- Token-Verbrauch getrackt
- Welcher Provider genutzt wurde

### 4.6 Multi-LLM Fallback
- Wenn Anthropic ausfällt → automatisch OpenAI, OpenRouter, Ollama oder Custom
- Prioritätsreihenfolge einstellbar
- Fallback-Info wird im Chat angezeigt ("via OpenAI (GPT-4o) -- Fallback")
- Jeder Provider bekommt denselben rauMKult-Kontext

---

## 5. Antwort-Generierung (`response_gen.py`)

### 5.1 Automatische Erkennung
- Anrede (du vs. Sie) aus Mail-Text
- Projekttyp (Treppe, Fassade, Wand, Boden, Decke)
- Situation (Erstanfrage, mit Fotos, Preisanfrage, Terminwunsch, Folgemail)
- Vorname des Absenders

### 5.2 Vorlagen (5 Situationen)
1. **Erstanfrage:** Infos anfragen + SharePoint-Upload-Link
2. **Mit Fotos:** Direkte Einschätzung + Rückfragen
3. **Preisanfrage:** Aufklärung (keine Zahlen im Erstkontakt)
4. **Terminwunsch:** Telefonlink + direkter Anruf
5. **Folgemail:** Kontextbezogene Antwort

### 5.3 Nachfass-Sequenz (3 Stufen)
| Stufe | Timing | Tonalität |
|-------|--------|-----------|
| 1 | 10 Tage | Freundlich: "Gibt es noch Fragen?" |
| 2 | 21 Tage | Bestimmt: Zeitplan ansprechen, Anpassungen anbieten |
| 3 | 45 Tage | Letzte Chance: Tür bleibt offen, Angebot aktualisieren |

---

## 6. Datenbanken im Detail

| Datenbank | Einträge | Zweck |
|-----------|----------|-------|
| `mail_index.db` | 12.642 Mails | Suchindex aller E-Mails |
| `kunden.db` | 7.321 Interaktionen | Kundenstamm + alle Kontakte |
| `sent_mails.db` | 525 Mails | Kais Schreibstil lernen |
| `newsletter.db` | 4.646 Newsletter | Auto-Klassifizierung |
| `rechnungen_detail.db` | alle PDFs | Rechnungspositionen, Skonto |
| `tasks.db` | dynamisch | Aufgaben, Wissen, Geschäft, Konversationen |
| `runtime_events.db` | **NEU (session-h)** | Runtime-Event-Store: 5 Typen, Vollkontext-Payloads, WAL-Modus |

---

## 6b. Runtime-Log-System (session-h, NEU)

### Was es ist
Lückenlose Nachvollziehbarkeit aller Ereignisse im Kira-System. Kein Ereignis geht verloren.

### 5 Event-Typen
| Typ | Was wird geloggt |
|-----|-----------------|
| `ui` | Browser-Klicks: Workspace öffnen, Nachricht senden, Panel-Wechsel |
| `kira` | Tool-Aufrufe, Kontext-Übergaben, Antwort-Generierung |
| `llm` | Provider, Modell, Tokens, Dauer, Fallback, Fehler |
| `system` | Server-Start, Mail-Monitor, daily_check, Task-Status-Änderungen |
| `settings` | Einstellungs-Änderungen mit Vor-/Nachwert |

### Architektur
- **`scripts/runtime_log.py`** — zentrales Modul
- **`knowledge/runtime_events.db`** — SQLite, WAL-Modus, 2 Tabellen
  - `events` — 24-Spalten Metadaten
  - `event_payloads` — Vollkontext (user_input_full, assistant_output_full, context_snapshot etc.)
- **Performance**: threading.Lock, WAL-Modus, PRAGMA synchronous=NORMAL, `_is_enabled()` per Typ

### Hauptfunktionen
- `elog(event_type, action, summary, **kwargs)` — schreibt Event, wirft NIE Exception
- `eget(...)` — gefilterte Abfrage (limit/offset/type/modul/status/search)
- `eget_payload(event_id)` — lädt Vollkontext eines Events
- `estats()` — Statistiken (total/heute/fehler/sessions/by_type/db_size)
- `get_recent_for_kira(limit=30)` — lesbare Zusammenfassung für Kiras Kontext
- `ensure_config_defaults()` — initialisiert Config beim Server-Start

### Integrationen (Stand 27.03.)
| Modul | Status | Was |
|-------|--------|-----|
| `kira_llm.py` | ✅ done | elog in execute_tool() + chat() + chat_failed |
| `server.py` | ✅ done | Server-Start, Task-Status, Einstellungen-Save, API-Endpunkte |
| `server.py` (JS) | ✅ done | `_rtlog()` fire-and-forget, openKiraWorkspace, sendKiraMsg |
| `mail_monitor.py` | 📋 geplant | Mail-Klassifizierung, Task-Erstellung |
| `daily_check.py` | 📋 geplant | Job-Start/-Ende |

### Kira liest eigene Logs
Tool `runtime_log_suchen` (wenn `kira_darf_lesen=True`):
- Kira kann sich selbst fragen: "Was habe ich gestern getan?" oder "Welche Fehler gab es?"
- Filter: event_type, action, modul, context_type, status, search

### Einstellungen (UI-Section)
9 Toggles: aktiv / ui_events / kira_events / llm_events / hintergrund_events / settings_events / fehler_immer_loggen / vollkontext_speichern / kira_darf_lesen
Stats-Anzeige: total, heute, fehler, sessions, db-größe
Viewer: gefiltert nach Typ/Status/Suche, paginiert

---

## 7. Entwicklungsstand & Roadmap

### 7.0 Zuletzt abgeschlossen

| Session | Was | Status |
|---------|-----|--------|
| session-g (27.03.) | Kira-Workspace UI vollständig neu (kq-*/kw-*, 3-Spalten, Quick Panel 7 Items, Kontext-Bar, Quick-Actions-Bar, History-Sidebar, 15 neue JS-Funktionen) | ✅ done |
| session-h (27.03.) | Runtime-Log-System (runtime_log.py, kira_llm.py + server.py Integration, Einstellungen-UI, API-Endpunkte, JS _rtlog()) | ✅ done |

### 7.1 Offen / In Arbeit

| Feature | Modul | Priorität | Notes |
|---------|-------|-----------|-------|
| mail_monitor.py runtime_log Integration | mail_monitor.py | hoch | elog bei Mail-Klassifizierung, Task-Erstellung |
| daily_check.py runtime_log Integration | daily_check.py | mittel | elog für Job-Start/-Ende |
| Server-Test nach Rebuild | server.py | **kritisch** | session-g/h noch nicht getestet |
| Direkte E-Mail-Antwort aus Dashboard | server.py | mittel | SMTP vorbereitet in config.json |
| Kira Tagesstart-Briefing (Morning-UI) | server.py | mittel | API vorhanden, Morning-Anzeige fehlt |
| Kunden-360-Ansicht | server.py | mittel | Timeline aller Interaktionen pro Kunde |
| Angebots-Kalkulations-Assistent | kira_llm.py | mittel | Preisliste im Wissenspeicher vorhanden |
| Cashflow-Prognose | server.py | niedrig | Offene Rechnungen + Zahlungsverhalten |

### 7.2 Geplante Erweiterungen (Mittelfristig)

**Direkte E-Mail-Antwort aus Dashboard**
- "Antworten" Button der fertigen Entwurf direkt als Mail sendet
- SMTP-Integration (schon in config.json vorbereitet)
- Kein Wechsel zu Outlook nötig

**Kalender-Integration**
- Google Calendar / Outlook Sync für erkannte Termine
- Automatisch Blocker setzen wenn Frist naht
- Erinnerung: "Morgen Rückruf bei Firma Y fällig"

### 7.3 Mittelfristig (Nächste Wochen)

**Kira proaktiver Tagesstart**
- Morgens beim Öffnen: automatische Zusammenfassung
- "Heute wichtig: 2 unbeantwortete Leads (einer seit 3 Tagen), Skonto-Frist für RE-2567 läuft morgen ab, Nachfass bei A-SB089 fällig"
- Priorisierte To-Do-Liste für den Tag

**Angebots-Kalkulation**
- Preisliste ist bereits im Wissenspeicher
- Kira könnte aus Projektbeschreibung + Fotos eine Schätzung generieren
- Vergleich mit ähnlichen abgeschlossenen Projekten
- "Projekt X ähnelt Projekt Y (2024) -- dort waren es 4.200 EUR"
- Kira scannt alle Leistungsrechnungen nach positionen und erstellt eine datenbank für vergleiche und optimale angebote
- Kann daraus übersichten und analyse daten erstellen und zeigen und ständig updaten, z.B. wie entwickelt sich der preis einer position

**Kunden-360-Ansicht**
- Eigene Seite pro Kunde mit Timeline aller Interaktionen
- Alle Mails, Angebote, Rechnungen, Mahnungen, Notizen
- Kira-Einschätzung: Zahlungsverhalten, Reaktionszeit, Potenzial

**Dokument-Vorlagen**
- Angebots-PDF direkt aus Dashboard generieren
- Rechnungs-PDF mit rauMKult-Layout
- Mahnschreiben nach Template (3 Stufen, rechtssicher)

### 7.4 Langfristig (Nächste Monate)

**Foto-Video Analyse für Angebote**
- Multimodales LLM (Claude/GPT-4o) analysiert hochgeladene Fotos und Videos
- Automatische Erkennung: Betonart, Schadenstyp, Fläche (geschätzt)
- Vorschlag: passende Leistung + ungefährer Aufwand
- "Sieht nach Sichtbetonkosmetik Klasse SB3 aus, ca. 15m2, Richtwert 2.800-3.500 EUR"

**Finanz-Prognose**
- Cashflow-Vorschau basierend auf offenen Rechnungen + durchschnittl. Zahlungsdauer
- "Erwarteter Eingang nächste 30 Tage: ca. 12.500 EUR"
- Warnung bei Liquiditätslücke
- Saisonale Muster erkennen (wann kommen die meisten Anfragen) Top!

**CRM-Funktionalität**
- Lead-Pipeline: Anfrage -> Angebot -> Auftrag -> Abrechnung
- Conversion-Rate pro Kanal (Website, Empfehlung, Messe)
- Automatische Wiedervorlage bei "kalten" Kontakten
- Tags und Notizen pro Kunde

**Wettbewerber-Monitoring**
- Regelmäßige Web-Recherche nach Markt-Trends
- Neue Wettbewerber, Preisänderungen, Branchennews
- Kira fasst wöchentlich zusammen: "In der Branche ist diese Woche passiert..."

**WhatsApp/Telegram-Integration**
- Viele Handwerks-Kunden kommunizieren per Messenger
- Kira könnte Nachrichten entgegennehmen und im Dashboard anzeigen
- Schnellantworten direkt aus dem Dashboard

**Zeiterfassung pro Projekt**
- Start/Stop Timer im Dashboard
- Automatische Zuordnung zu Rechnung
- Auswertung: Stundensatz effektiv vs. kalkuliert
- Integration mit ProjektZeit App (bereits vorhanden unter `com.raumkult.projektzeit`)

**Mobile App / PWA**
- Dashboard als Progressive Web App
- Offline-fähig für Baustelle
- Push-Benachrichtigungen nativ
- Foto-Upload direkt vom Handy

### 7.5 Kira-Intelligenz verbessern

**Stil-Coaching**
- Kira lernt aus den 525 gesendeten Mails Kais exakten Ton
- Bei Entwürfen: Abgleich mit gelerntem Stil, Warnung bei Abweichung
- Phrasen-Datenbank: Was Kai sagt vs. was er nie sagen würde

**Mustererkennung**
- Welche Angebote werden angenommen? (Branche, Größe, Preis, Jahreszeit)
- Welche Kunden zahlen pünktlich/spät?
- Welche Anfragen führen zu Aufträgen?
- Daraus: Scoring für neue Leads ("Hohe Abschlusswahrscheinlichkeit")

**Automatische Eskalation**
- Wenn Rechnung 16+ Tage offen: automatisch Zahlungserinnerung-Entwurf erstellen
- Wenn Rechnung 24+ Tage offen: automatisch Mahnung-Entwurf erstellen --> Inkasso
- Wenn Lead 48h unbeantwortet: Push mit Warnung
- Wenn Nachfass fällig: Entwurf vorbereiten und zur Freigabe vorlegen

**Kontext über Sessions hinweg**
- Kira merkt sich Gesprächsergebnisse dauerhaft
- "Letzte Woche hast du gesagt, du willst bei Kunde X nachfassen -- soll ich?"
- Projektnotizen die sich über Wochen aufbauen

**Datenanalyse & Entscheidungsunterstützung
Durch den Zugriff auf interne Datenbanken (ERP, CRM, DMS) liefert der Bot fundierte Einblicke: 

**On-Demand Business Intelligence: Beantwortung komplexer Fragen wie „Welcher Kunde hat im letzten Quartal am wenigsten bestellt?“ oder „Wie hoch ist die aktuelle Marge bei Produkt X?“ ohne manuelle Tabellensuche.
Frühwarnsystem: Proaktive Meldung von Anomalien, wie z.B. sinkende Liquidität oder Verzögerungen in der Lieferkette.
Vorbereitung von Meetings: Automatisches Erstellen von Dossiers über Gesprächspartner durch Verknüpfung von Mail-Historie und CRM-Daten. 

**Administrative & operative Automatisierung
Routineaufgaben werden fast vollständig übernommen: 

Komplexe Terminplanung: Koordination von Meetings über Zeitzonen hinweg unter Berücksichtigung von Prioritäten und optimalen Fokuszeiten.
Dokumentenerstellung: Umwandlung von Notizen oder Daten aus E-Mails in strukturierte Dokumente wie Angebote, Projektpläne oder Protokolle.
Finanz-Vorsortierung: Extraktion von Daten aus Rechnungen oder Belegen direkt aus dem Posteingang zur Vorbereitung für die Buchhaltung. 

wenn nicht schon Umgesetzt:

**Zentrales E-Mail- & Kommunikationsmanagement
Der Assistent fungiert als Schutzschild vor der Informationsflut: 
Virtualworkforce.ai
Virtualworkforce.ai
Inbox-Triage & Priorisierung: Automatische Kategorisierung von E-Mails nach Dringlichkeit (z.B. "Kundenbeschwerde", "Rechnung", "Newsletter") und Markierung geschäftskritischer Nachrichten.
Intelligente Antwortentwürfe: Erstellung kontextbezogener Entwürfe basierend auf dem bisherigen Mailverlauf und internen Daten (z.B. Lieferstatus aus dem ERP), sodass der Inhaber nur noch freigeben muss.
Zusammenfassungen: Komprimierung langer E-Mail-Threads oder komplexer Berichte in kurze Briefings mit den wichtigsten Aktionspunkten.
Automatisches Follow-up: Überwachung von Fristen und automatisches Nachfassen bei unbeantworteten Anfragen. 

**3. Automatisierung von Arbeitsabläufen 
Onboarding & Workflows: Routineprozesse, wie das Onboarding neuer Kunden oder Mitarbeiter, können teilweise oder vollständig automatisiert werden.
Rechnungsmanagement: Der Bot kann Eingangsrechnungen aus E-Mails erkennen, auslesen, kategorisieren und zur Freigabe bereitstellen.
CRM-Pflege: Nach einem Meeting oder E-Mail-Kontakt aktualisiert der Bot automatisch die Kundendaten im CRM. 
Theams..

**2. Datenanalyse und Recherche (Geschäftsdaten)
Information Retrieval: Auf Fragen wie "Wie hoch war der Umsatz mit Kunde X im letzten Quartal?" antwortet der Bot sofort, indem er Daten aus CRM-Systemen, Rechnungen und Dokumenten zusammenführt.
Vorrecherche & Zusammenfassungen: Bei längeren E-Mail-Verläufen oder umfangreichen Projektunterlagen erstellt der Bot prägnante Zusammenfassungen (Summaries).
Risikoerkennung: Der Assistent kann in Verträgen oder Dokumenten auf potenzielle finanzielle Risiken oder Klauseln hinweisen

MARKETING UND SOZIAL MEDIA 
Ein vollwertiger KI-Assistent mit Zugriff auf Ihre Geschäftsdaten und E-Mails kann im Bereich Marketing und Social Media (insbesondere Instagram) als strategisches "Gehirn" fungieren, das weit über einfaches Posten hinausgeht. Durch die Verknüpfung interner Daten mit externen Kanälen entstehen folgende Entlastungsmöglichkeiten: 
1. Intelligente Content-Erstellung aus Geschäftsdaten
Statt mühsam Themen zu suchen, generiert der Bot Inhalte direkt aus Ihrem Arbeitsalltag: 
Benchmark Email
Benchmark Email
 +1
Produkt-Highlights: Der Bot erkennt über E-Mails oder Warenwirtschaft neue Lieferungen oder Bestseller und entwirft dazu passende Instagram-Captions oder Reels-Skripte.
Erfolgsstorys: Er analysiert abgeschlossene Projekte in Ihren Mails und formuliert daraus "Behind-the-Scenes"-Posts oder Fallstudien.
Stimmige Markenstimme: Durch den Zugriff auf Ihre bisherige Korrespondenz lernt die KI Ihren persönlichen Schreibstil und sorgt für eine konsistente Brand Voice auf allen Kanälen. 
Marketer Milk
Marketer Milk
 +2
2. Automatisierung des Kunden-Interaktions-Zyklus
Der Bot schließt die Lücke zwischen Social-Media-Anfrage und Geschäftsabschluss: 
Smart DM-Management: Er beantwortet Instagram-Direktnachrichten basierend auf Informationen aus Ihren Geschäftsdaten (z. B. Lieferzeiten, Preise, FAQ).
Lead-Nurturing: Wenn ein Interessent auf Instagram kommentiert, kann der Bot ihn (bei Vorliegen der Daten) direkt einer passenden E-Mail-Sequenz zuordnen oder den Kontakt in Ihr CRM einpflegen.
Terminkoordination: Er erkennt in DMs oder Mails Terminwünsche und gleicht diese mit Ihrem Kalender ab, um direkt Buchungslinks zu versenden. 
Gmelius
Gmelius
 +3
3. Datengestützte Strategie & Analyse
Der Assistent fungiert als Analyst, der Ihre Zahlen in Taten übersetzt: 
Medium
Medium
 +2
Versandoptimierung: Er analysiert, wann Ihre Kunden E-Mails öffnen oder auf Instagram aktiv sind, und plant Posts sowie Newsletter für diese optimalen Zeitfenster.
Trend-Frühwarnsystem: Durch den Abgleich von Markttrends mit Ihren Verkaufsdaten (aus Mails/Rechnungen) schlägt er Themen vor, die gerade für Ihre Zielgruppe relevant sind.
Performance-Reporting: Statt Tabellen zu wälzen, fragen Sie den Bot einfach: „Welcher Post hat letzten Monat die meisten Verkäufe generiert?“. 
First-Rate Tech Corp.
First-Rate Tech Corp.
 +4
4. Effizienz im E-Mail-Marketing
Personalisierung: Die KI nutzt Kaufhistorien aus Ihren Daten, um hochgradig personalisierte Newsletter zu erstellen, die genau die Produkte enthalten, die den jeweiligen Kunden interessieren könnten.
Automatisierte Follow-ups: Der Bot erkennt in Ihrem Postfach, wenn ein potenzieller Kunde nicht auf ein Angebot reagiert hat, und entwirft eine freundliche Nachfassmail. 
National Institutes of Health (.gov)
National Institutes of Health (.gov)
 +3


Der Assistent sollte idealerweise in einer gesicherten Unternehmensumgebung betrieben werden, um Datenschutz und DSGVO-Konformität zu gewährleisten

---

## 8. Architektur-Übersicht

```
 Postfächer (5x)                    OneDrive-Ordner
       |                            (Rechnungen, Angebote,
       v                             Mahnungen, Zahlungen)
 [daily_check.py] ──> tasks.db           |
       |                                  v
       v                         [scan_dokumente.py] ──> rechnungen_detail.db
 [mail_classifier.py]                     |               (+ rechnungs_positionen
 [response_gen.py]                        |                + zahlungseingaenge
       |                                  |                + angebote_detail)
       v                                  v
 kunden.db                    ┌──> [server.py :8765] <──┐
 sent_mails.db                |     Dashboard (Browser)  |
 newsletter.db                |           |              |
                              |           v              |
                              |    [kira_llm.py]         |
                              |    Multi-LLM Chat        |
                              |    (Anthropic/OpenAI/    |
                              |     OpenRouter/Ollama)   |
                              |           |              |
                              |           v              |
                              |    wissen_regeln         |
                              |    geschaeft_statistik   |
                              |    kira_konversationen   |
                              |                          |
 [rebuild_all.py] ────────────┘                          |
                                                         |
 ntfy.sh ──> iPhone Push                                 |
 PowerShell ──> Windows Toast ───────────────────────────┘
```

---

## 9. Dateien und Scripts

| Datei | Zweck | Zeilen | Status |
|-------|-------|--------|--------|
| `server.py` | Dashboard-Server, UI, API, Multi-LLM Provider UI | ~3.550 | Fertig |
| `kira_llm.py` | Multi-LLM Brain, Tools, Chat, Provider-Fallback | ~1.030 | Fertig |
| `scan_dokumente.py` | **NEU** Ordner-Scanner: Rechnungen, Angebote, Mahnungen, Zahlungen | ~960 | Fertig |
| `mail_classifier.py` | Regelbasierte Mail-Klassifizierung (Backup) | ~505 | Wird durch LLM ersetzt |
| `response_gen.py` | Antwort-Entwürfe + Nachfass-Vorlagen (Backup) | ~303 | Wird durch LLM ersetzt |
| `daily_check.py` | Täglicher Mail-Scan + Alerts | ~356 | Aktiv |
| `build_databases.py` | DB-Aufbau aus Mail-Archiv | ~467 | Aktiv |
| `rebuild_all.py` | Komplett-Rebuild aller Aufgaben | ~439 | Aktiv |
| `scan_rechnungen_detail.py` | PDF-Extraktion aus Mail-Archiv (ALT) | ~550 | Ersetzt durch scan_dokumente.py |
| `task_manager.py` | Status- und Erinnerungsverwaltung | ~101 | Aktiv |
| `config.json` | Konfiguration (Intervalle, Server, LLM, Provider) | - | Aktiv |
| `secrets.json` | API Keys (nicht im Git) | - | Aktiv |

---

## 10. Umbau-Status: LLM-First + Ordner-basiert

### Fertig (alle 5 Phasen implementiert + getestet)

| Phase | Komponente | Was |
|-------|-----------|-----|
| -- | Multi-LLM Provider | 5 Provider-Typen (Anthropic/OpenAI/OpenRouter/Ollama/Custom), automatischer Fallback, Provider-Verwaltung in Einstellungen |
| 0 | `scan_dokumente.py` | **29 Rechnungen** (117.822 EUR), **19 Angebote** (184.801 EUR), **82 Positionen**, **5 Zahlungen**, **1 Mahnung** aus OneDrive-Ordnern. Dedup, Hybrid-Extraktion, Zahlungs-Matching, Positions-DB |
| 1 | `llm_classifier.py` | LLM-Klassifizierung. Fast-Path fuer System/Newsletter/Gesendete (kein LLM noetig). Fallback auf regelbasiert wenn LLM offline. Imports geswappt in daily_check + rebuild_all |
| 2 | `llm_response_gen.py` | LLM-Antworten in Kais Stil. 5 Stil-Referenzen aus sent_mails.db + 8.212 Zeichen Wissensregeln. Fallback auf Templates. Imports geswappt in daily_check + server + rebuild_all |
| 3 | `mail_monitor.py` | Echtzeit-IMAP-Polling alle 5 Min. OAuth2/MSAL aus Mail-Archiver (geteilter Token-Cache). 5 Konten. Auto-Start als Daemon-Thread in server.py. API: /api/monitor/status |
| 4 | `angebote_tracker.py` | Auto-Status-Erkennung: A-SB260094 als angenommen erkannt. 2 Nachfass DRINGEND (A-SB260092 + A-SB260093, je 38 Tage offen). ntfy Push bei Faelligkeit |
| 5 | Tagesbriefing + angebot_pruefen Tool | `generate_daily_briefing()` mit LLM + Statistik-Fallback. Briefing: "6 Mails warten, 28 Rechnungen offen (114.249 EUR), 3 Angebote offen, 2 Nachfass faellig". API: /api/kira/briefing + /regenerate. Neues Kira-Tool angebot_pruefen (9 Tools total) |

### Offene Alerts (aus Phase 0)

- Zahlung 03.12.2024: Keine RE-Nummer im JSON -- manuell prüfen
- Zahlung RE-SB2568: Rechnung nicht in DB (liegt vor dem Scan-Zeitraum)
- Zahlung RE-SB260098: 2.982,87 EUR erhalten vs. 1.791,46 EUR Rechnung -- Differenz 1.191,41 EUR
- Zahlung RE-SB260102: 2.708,33 EUR erhalten vs. 2.792,09 EUR Rechnung -- Differenz 83,76 EUR (Skonto?)

---

---

## ERGÄNZUNGEN SEIT 25.03.2026 (session-r bis session-pp-cont4)

_Stand: 2026-04-08 · Kurzform — vollständige Details in feature_registry.json_

### Neue DB-Tabellen

| Tabelle | DB | Zweck |
|---------|-----|-------|
| `artikel_preishistorie` | kunden.db | Preis-/Name-/Beschreibungsänderungen mit diff_pct + aenderung_typ |
| `manuelle_artikel` | kunden.db | Lexware-kompatibles Schema für Artikel ohne Lexware-Anbindung |
| `vorgaenge` | tasks.db | Case Engine Vorgänge (10 Typen, Status-Maschinen) |
| `vorgang_links` | tasks.db | Verknüpfungen zwischen Vorgängen und Tasks/Angeboten/Rechnungen |
| `vorgang_status_history` | tasks.db | Statusübergänge mit Timestamps |
| `vorgang_signals` | tasks.db | Signal-Queue für Activity-Drawer (Stufe A/B/C) |
| `geloeschte_protokoll` | tasks.db | Protokoll gelöschter Mails |
| `dokumente` | kunden.db | Dokumente-Modul (Eingang, Studio, Vorlagen) |

### Neue Kira-Tools (15+ seit session-r)

| Tool | Modul | Zweck |
|------|-------|-------|
| `artikel_preise_abfragen` | kira_llm.py | LIKE-Suche in lexware_artikel + manuelle_artikel |
| `angebot_positionen_vorschlagen` | kira_llm.py | LLM wählt passende Artikel + Mengen |
| `preisentwicklung_abfragen` | kira_llm.py | Chronologische Preis-Snapshots + Trend |
| `vorgang_kontext_laden` | kira_llm.py | Vorgang-Details mit Status-History |
| `vorgang_status_setzen` | kira_llm.py | Statusübergang in Case Engine |
| `projekt_erstellen` | kira_llm.py | Neues Projekt als Vorgang anlegen |
| `projekt_mails_zuordnen` | kira_llm.py | Mails zu Projekt verknüpfen |
| `mail_korrektur` | kira_llm.py | Klassifizierung korrigieren + neu zuordnen |

### Neue API-Endpoints (Auswahl der wichtigsten)

| Method | Pfad | Zweck |
|--------|------|-------|
| GET | /api/artikel | Vereinheitlichte Artikelliste (Lexware + Manuell) |
| GET | /api/artikel/historie | Gesamt-Änderungshistorie |
| GET | /api/artikel/historie/export | CSV-Export der Historie |
| GET | /api/artikel/statistik | Aggregierte Preis-Statistiken |
| POST | /api/artikel | Manuellen Artikel anlegen |
| POST | /api/artikel/import | CSV-Import |
| POST | /api/artikel/transfer-lexware | Manuelle Artikel zu Lexware übertragen |
| POST | /api/lexware/sync-artikel | Nur Artikel synchronisieren |
| POST | /api/config/patch | Einzelnen Config-Wert setzen (dot-notation) |
| GET | /api/vorgang/* | 8 Vorgang-API-Endpoints |
| GET | /api/presence | Präsenz-Erkennung (idle detection) |
| POST | /api/dokumente/* | Dokumente CRUD + Export |

### Architektur-Änderungen

- **5-Stufen Routing**: Vorfilter → Klassifizierung → Routing → Vorgang → Task
- **Case Engine**: dict-basierte Statusmaschinen für 10 Vorgangstypen
- **Thread-Awareness**: Mails im Kontext des Verlaufs klassifizieren
- **Unternehmensprofile**: Neue Pane-2 Sub-Navigation mit 6 Tabs
- **Universelle Handlungsfähigkeit**: Kira kann in allen Modulen CRUD ausführen
- **Activity-Drawer**: Windows 11 Widget-Style mit Signal-System
- **Anhang-Extraktion**: PDF/DOCX/ZIP/OCR + Vision-Fallback bei Klassifizierung

*Erstellt am 25.03.2026. Letzte Aktualisierung: 2026-04-08 (session-pp-cont4).*
