# Prompt 04 – Neue Informationsarchitektur, UX- und UI-Konzept für Kira

Bitte überarbeite das bestehende Projekt jetzt nicht nur optisch, sondern auf Ebene der Produktstruktur, UX und Informationsarchitektur.

Wichtig:
- Baue auf dem aktuellen Projektstand auf.
- Zerstöre keine bestehenden Funktionen.
- Verwerfe nicht die vorhandene technische Architektur.
- Organisiere die Oberfläche, Navigation, Komponenten und Benutzerführung neu.
- Führe keinen festen rauMKult-Brand-Look ein.
- Keine festen rauMKult-Farben, keine harten Marken-Styles, keine finale Brand-Optik.
- Alles Design muss später über Einstellungen steuerbar sein.
- Ziel ist eine hochwertige, neutrale Software-Oberfläche, die später gebrandet werden kann.

## 1. Projektstand, auf dem du aufbauen sollst

Das aktuelle System ist bereits deutlich weiter als ein einfaches Mail-Dashboard.

Es gibt bereits:
- lokalen Server auf `localhost:8765`
- Python + SQLite + eigener HTTP-Server + JavaScript-Frontend
- Multi-LLM-Chat mit Provider-Fallback
- Mail-Überwachung
- Aufgabenverwaltung
- Geschäftsmodul
- Wissensmodul
- Einstellungen
- Dokumenten-Scanner für Rechnungen, Angebote, Mahnungen, Zahlungen
- Kira-Chat und Kira-Tools
- strukturierte Datenbanken für Mail, Kunden, Stil-Lernen, Newsletter, Rechnungsdetails, Aufgaben

Diese Basis bleibt erhalten und soll nicht unnötig ersetzt werden.

## 2. Zielbild

Kira soll sich wie eine echte Unternehmens-Software anfühlen.
Nicht wie eine Mailseite mit ein paar Zusatzreiter.
Nicht wie ein Retro-Dashboard.
Nicht wie eine dunkle Testoberfläche.
Nicht wie eine angeklebte Sidebar.

Ziel ist ein modernes Unternehmens-Cockpit mit Kira als zentraler Assistenz.

Die Oberfläche soll:
- ruhig
- hochwertig
- klar lesbar
- modern
- softwareartig
- modular
- zukunftsfähig
- responsiv
- angenehm im Alltag
sein

## 3. Wichtigste Grundregel für das Design

Vorläufig KEIN festes rauMKult-Branding einbauen.

Stattdessen:
- neutrales Premium-Design
- neutrale Grundfarben
- gut lesbare Typografie
- hochwertige Abstände
- klare Hierarchie
- Theme-Engine / Design-Optionen in Einstellungen vorbereiten

Später einstellbar:
- Logo-Upload
- App-Name
- Light / Dark / Auto
- Akzentfarbe
- Schriftgröße
- Dichte / Kompaktheit
- Kartenradius
- Schattenstärke
- Animationen reduzieren
- Kontrastmodus

## 4. Neue Hauptnavigation

Die Informationsarchitektur soll jetzt schon die aktuelle Funktionalität und die geplanten Ausbaustufen berücksichtigen.

Neue Hauptnavigation:

- Start
- Kommunikation
- Organisation
- Geschäft
- Kunden
- Marketing
- Social / DMs
- Wissen
- Automationen
- Analysen
- Einstellungen

Wichtig:
- Kunden, Marketing, Social / DMs, Automationen und Analysen dürfen zunächst als Modul-Shells mit Badge „In Planung“ angelegt werden
- sie sollen aber jetzt schon strukturell sauber vorgesehen werden
- keine toten Links ohne Kontext
- jede In-Planung-Seite soll eine ruhige Platzhalterfläche mit Zielbild und geplanter Funktion bekommen

## 5. Startseite als echtes Cockpit

Die Startseite darf nicht mehr wie eine verlängerte Mailseite aussehen.

Die neue Startseite soll vier Bereiche haben:

### A. Tagesbriefing
Kompakte Management-Zeile mit:
- heute wichtig
- kritischste Punkte
- Nachfass fällig
- Fristen
- Geschäftssignale

### B. Klickbare KPI-Karten
Mindestens:
- Antworten nötig
- Neue Leads
- Angebotsrückmeldungen
- Termine / Fristen
- Offenes Rechnungsvolumen
- Eingangsrechnungen offen
- Nachfass fällig
- Gesamt offen

Diese Karten müssen klickbar und filternd sein.

### C. Kuratierte Arbeitsblöcke
- Heute priorisiert
- Nächste Termine & Fristen
- Geschäft aktuell

### D. Signale / Auffälligkeiten
- unklare Zahlungen
- manuelle Prüfungen
- Warnungen
- neu erkannte Auffälligkeiten

Wichtig:
- keine endlosen Listen auf der Startseite
- keine Mail-Hauptansicht auf der Dashboard-Startseite

## 6. Kommunikation als Arbeitsmodul

Kommunikation ist das Mail-/Kontaktmodul.
Aber nicht als Dump.

Ansichten:
- Antwort erforderlich
- Neue Leads
- Angebotsrückmeldungen
- Zur Kenntnis
- Newsletter / System
- Abgeschlossen

Zusätzliche Filter:
- offene Frage
- mit Termin
- mit Fotos
- mit Anhängen
- Quelle
- Kunde
- Projektart
- Dringlichkeit

Kartenlogik:
- klarer Titel
- Ein-Satz-Zusammenfassung
- Grund der Einordnung
- nächste Empfehlung
- Marker: Frage, Fotos, Termin, Rechnung, Systemmail usw.

Buttons reduziert:
- Mit Kira besprechen
- Mail lesen
- Anhänge
- Status ändern
- Korrektur

Kein Button-Friedhof.

## 7. Organisation als echtes Zeit- und Fristenmodul

Organisation soll nicht nur eine Liste erkannter Mails sein.

Neue Ansichten:
- Timeline
- Kalender
- Fristenliste
- Rückrufliste

Vorbereiten:
- Badge „aus Mail erkannt“
- Badge „manuell ergänzt“
- Badge „In Planung: Kalender-Sync“

Ziel:
- Termine
- Rückrufe
- Deadlines
- Wiedervorlagen
- Besprechungsvorbereitung

## 8. Geschäft als echtes Finanz- und Angebotsmodul

Das bestehende Geschäftsmodul ist fachlich bereits wertvoll.
Es muss jetzt visuell und strukturell wie eine hochwertige Softwarefläche aussehen.

Sekundäre Navigation in Geschäft:
- Übersicht
- Ausgangsrechnungen
- Angebote
- Eingangsrechnungen
- Zahlungen
- Mahnungen
- Auswertung

Zusätzlich vorbereiten mit Badge „In Planung“:
- Kalkulation
- Preispositionen
- Cashflow
- Kunden-360

Geschäft soll nicht wie Mail aussehen, sondern wie ein eigenständiges kaufmännisches Modul.

## 9. Wissen neu strukturieren

Wissen soll aus der jetzigen Regelwand zu einem steuerbaren Wissenszentrum werden.

Zwei Ebenen:

### A. Bibliothek
- Stil & Ton
- Preise & Kalkulation
- Technik
- Prozess
- Geschäftsregeln
- FAQ
- Projektwissen

### B. Regelsteuerung
- Feste Regeln
- Gelernt
- Vorschläge
- Korrekturen
- Freigaben

Wichtig:
- sichtbar trennen, was verbindlich ist und was nur Vorschlag / Lernmaterial ist
- editierbar, aber mit klarer Struktur

## 10. Kira komplett neu denken

Kira darf nicht bloß eine seitlich angeklebte Chatleiste bleiben.

Kira bekommt drei Modi:

### A. Launcher
- kleiner, hochwertiger Assistenz-Button unten rechts
- ruhig, präzise, unaufdringlich
- kein spielerischer Gimmick-Look

### B. Quick Panel
Beim Klick:
- Frage stellen
- Aufgabe besprechen
- Rechnung prüfen
- Angebot prüfen
- Kunde öffnen
- Suche

### C. Voller Assistenz-Workspace
Wenn man wirklich mit Kira arbeitet:
- keine schmale Sidebar
- keine halbe Leiste
- eigener großer Arbeitsbereich / Overlay / Workspace

Layout des Kira-Workspaces:
- links: Kontexte / Threads / Vorgänge
- mitte: Chatverlauf
- rechts optional: Aktionen, Kundendaten, Dokumente, Wissensregeln, Vorschläge

Historie bekommt einen eigenen Bereich / Menüpunkt „Verläufe“ oder „Historie“.

## 11. Kira auf Zukunft vorbereiten

Kira soll jetzt schon auf folgende Kontexttypen vorbereitet werden:
- Aufgabe
- Kunde
- Angebot
- Rechnung
- Dokument
- Recherche
- Marketing-Idee
- Social-Nachricht

Das ist Vorbereitung.
Nicht alles sofort voll bauen.
Aber die Struktur jetzt anlegen.

## 12. Neue Module als vorbereitete Shells

Die folgenden Module jetzt als ruhige Shells mit „In Planung“-Badge vorbereiten:

### Kunden
- Timeline
- Pipeline
- Potenzial
- Zahlungsverhalten
- offene Themen

### Marketing
- Content-Pipeline
- Themenideen aus Projekten
- Kampagnen
- Newsletter
- Redaktionsplanung

### Social / DMs
- DM-Eingang
- Schnellantworten
- Lead-Zuordnung
- Terminbezug
- Plattformbezug

### Automationen
- Mail-Follow-up
- Erinnerungsregeln
- Eskalationen
- Workflow-Bausteine
- Trigger / Bedingungen

### Analysen
- Umsatzfragen
- Angebotsquote
- Lead-Scoring
- Kanalwirkung
- Preisentwicklung
- Performance-Reporting

Diese Shells sollen:
- nicht leer und tot wirken
- aber auch nicht funktional vorgetäuscht werden
- den Platz für spätere Erweiterung sauber reservieren

## 13. Designstil

Bitte das UI in einem neutralen, hochwertigen Software-Stil überarbeiten.

Vermeiden:
- Retro-Look
- Atari-Gefühl
- schwammige Farben
- Mini-Schrift
- enge Zeilen
- starre, schwere Kartenwüsten
- laute, billige Effekte
- zu viele gleich starke Farben
- zu viele Buttons
- Chat als angeklebte Sidebar

Bevorzugen:
- klare Typografie
- großzügige Lesbarkeit
- ruhige Flächen
- starke Informationshierarchie
- gute Leerräume
- dezente Micro-Animationen
- hochwertiges Card-/Table-/List-System
- Dashboard wie echte Business-Software
- Chat wie Assistenz-Workspace
- gute Hover- und Fokuszustände
- sehr gut lesbare Standard-Schriftgrößen

## 14. Accessibility / Lesbarkeit

Das jetzige System ist teilweise zu klein und anstrengend zu lesen.
Darum bitte direkt mitdenken:

- Standardschrift größer und besser lesbar
- klare Zeilenabstände
- gute Kontraste
- Klickflächen nicht zu klein
- kompakt / standard / entspannt als Dichte-Modi vorbereiten
- Schriftgrößen über Einstellungen anpassbar

## 15. Umsetzung mit minimalem Umbau

Wichtig:
- Bestehende Architektur beibehalten
- Bestehende Funktionen beibehalten
- Keine unnötige technische Neuentwicklung
- Bestehende APIs, Datenbanken, Tools und Provider-Struktur weiterverwenden
- Nur Informationsarchitektur, Komponentenstruktur, App-Shell und UX neu organisieren

Das Ziel ist:
- minimal-invasive strukturelle UX-Erneuerung
- kein Zerstören des funktionierenden Unterbaus

## 16. Umsetzungsreihenfolge

Arbeite in dieser Reihenfolge:

1. Neue App-Shell und neue Hauptnavigation entwerfen
2. Dashboard-Startseite in ein echtes Cockpit umbauen
3. Kommunikation als Arbeitsmodul neu organisieren
4. Kira in Launcher + Quick Panel + Workspace aufteilen
5. Geschäft als hochwertiges kaufmännisches Modul schärfen
6. Wissen als steuerbares Wissenszentrum umsetzen
7. Einstellungen um Design-/Theme-Konfiguration erweitern
8. In-Planung-Module als Shells vorbereiten
9. Alles testen
10. Speichern
11. Committen

## 17. Ziel

Ziel ist eine Oberfläche, in der man gern arbeitet.

Nicht:
- irgendwie anders
- nur neuer Look
- nur dunkle Farben tauschen

Sondern:
- klare Unternehmenssoftware
- hochwertige Assistenz-Erfahrung
- skalierbare Produktstruktur
- Kira als echter Arbeitsraum
- Module für heute nutzbar
- Module für morgen vorbereitet
