04 - Wissen - Plan für UI

Claude soll „Wissen“ nicht als Sammlung langer Blöcke bauen, sondern als echtes Wissenszentrum. Und die Funktionen dazu müssen richtig gesetzt werden.

So sollte „Wissen“ aufgebaut sein:

Ganz oben eine klare Modul-Kopfzeile.
Links Titel „Wissen“ plus kurze Statuszeile:
z. B. 42 feste Regeln, 11 Vorschläge offen, 7 Korrekturen, 3 Freigaben ausstehend.
Rechts:
Suche
Filter
neuer Eintrag
Import
Freigaben prüfen

Wichtig:
Diese Zahlen müssen aus echten Wissensdatensätzen kommen.
Nicht hart codiert.
Nicht nur dekorativ.

Darunter eine klare Zweiteilung auf Navigationsebene:

Bibliothek
Regelsteuerung

Das ist wichtig.
Sonst vermischt Claude wieder alles in einer einzigen Fläche.

Bereich 1: Bibliothek

Hier geht es um Wissenszugang, nicht um Administrationslogik.

Die Bibliothek soll nicht mit riesigen Textblöcken starten, sondern mit kleineren, gut lesbaren Wissenskarten oder Clustern.

Hauptkategorien:
Stil & Ton
Preise & Kalkulation
Technik
Prozess
Geschäftsregeln
FAQ
Projektwissen

Jede Kategorie als gut sichtbare Karte oder Kachel.
Nicht mini, nicht blass, sondern klar lesbar.

Jede Wissenskarte zeigt:
Titel
kurze Beschreibung
Anzahl Einträge
letzte Änderung
Typ oder Status
Button „Öffnen“

Beim Klick auf eine Kategorie öffnet sich nicht einfach mehr Wandtext, sondern eine größere Inhaltsansicht.
Also:
links Unterkategorien oder Einträge
mitte Hauptinhalt
rechts optional Metadaten, Verknüpfungen, Bearbeitungsaktionen

Wichtig:
Claude soll hier echte Funktionen setzen.
„Öffnen“ lädt die Inhalte dieser Wissenskategorie.
Die Untereinträge müssen anklickbar sein.
Bearbeiten muss wirklich editieren.
Speichern muss die Änderungen wirklich in der Wissensbasis sichern.

Bereich 2: Regelsteuerung

Hier wird klar getrennt zwischen dem, was verbindlich ist, und dem, was gelernt oder vorgeschlagen wurde.

Tabs oder Segmente:
Feste Regeln
Gelernt
Vorschläge
Korrekturen
Freigaben

Diese Trennung ist zentral. Sie ist im bisherigen Konzept schon mehrfach festgelegt und genau das fehlt UX-seitig noch.

Die Funktionslogik dazu muss so aussehen:

Feste Regeln
Zeigt verbindliche Regeln.
Aktionen:
öffnen
bearbeiten
verknüpfen
historie ansehen

Gelernt
Zeigt Dinge, die aus Systemnutzung, Korrekturen oder Mustern übernommen wurden, aber noch nicht automatisch verbindlich sind.
Aktionen:
prüfen
in Vorschlag umwandeln
verwerfen
zuordnen

Vorschläge
Zeigt neue potenzielle Regeln oder Formulierungen.
Aktionen:
annehmen
bearbeiten
ablehnen
mit bestehender Regel zusammenführen

Korrekturen
Zeigt Korrekturen aus Dashboard, Kommunikation oder Kira-Feedback.
Aktionen:
prüfen
Regelbezug setzen
als Einzelfall markieren
lernen zulassen / nicht zulassen

Freigaben
Zeigt alles, was auf Bestätigung wartet.
Aktionen:
freigeben
zurückstellen
ablehnen
bearbeiten

Wichtig:
Diese Buttons müssen echte Zustandsänderungen auslösen.
Nicht wieder nur statische UI.

Zusätzlich braucht Wissen eine gute Detailansicht.

Wenn ein Eintrag geöffnet wird, soll nicht wieder ein schmaler Kasten erscheinen, sondern eine breite Bearbeitungsfläche.

Diese Detailansicht zeigt:
Titel
Kategorie
Typ
Status
Inhalt
verknüpfte Regeln oder Bereiche
Quelle
letzte Änderung
Historie
Kommentare oder Hinweise

Aktionen:
bearbeiten
speichern
als Vorschlag markieren
in feste Regel übernehmen
archivieren
mit Kira besprechen

Auch hier wieder:
Diese Aktionen müssen funktional korrekt gesetzt werden.

Was ich für Wissen ausdrücklich will:
kleinere schöne Einstiegskarten
klare Cluster
große lesbare Detailansicht
klare Trennung zwischen Bibliothek und Steuerung
echte Bearbeitung
echte Statuslogik
echte Freigabelogik

Was ich ausdrücklich nicht mehr will:
lange Seiten mit riesigen Textblöcken
20 ähnliche Kacheln untereinander
winzige Karten mit kaum lesbarer Schrift
unklare Trennung zwischen fest und vorgeschlagen
Bearbeiten ohne klaren Status
Wissenswand statt Wissenssystem

Zusätzliche sinnvolle Funktionen, die Claude mitdenken soll:

Suche über alles Wissen
Die Suche muss Kategorien, Titel und Inhalte durchsuchen.

Filter:
nur feste Regeln
nur Vorschläge
nur Preislogik
nur Stil
nur Technik
nur zuletzt geändert
nur mit Freigabebedarf

Verknüpfung zu Kira
Jeder Wissenseintrag soll in Kira referenzierbar sein.
Also:
„mit Kira besprechen“ öffnet den Eintrag im Kira-Kontext.
Nicht generischer Chat, sondern echter Wissenskontext.

Verknüpfung zu Modulen
Wissen soll später mit Kommunikation, Geschäft, Technik, Kunden, Marketing verknüpfbar sein.
Wenn noch nicht komplett umsetzbar, dann strukturell vorbereiten.

Wenn ich das als schlichtes Text-Wireframe zusammenfasse:

Kopfzeile
Titel | Statuszahlen | Suche | Filter | neuer Eintrag | Freigaben prüfen

Ebene 1
Bibliothek | Regelsteuerung

Bibliothek
Kachelraster der Hauptkategorien
Klick öffnet größere Inhaltsansicht mit Einträgen und Editor

Regelsteuerung
Tabs:
Feste Regeln | Gelernt | Vorschläge | Korrekturen | Freigaben

Detailansicht
großer Editor / Viewer mit Metadaten, Historie und Aktionen

Und wieder ausdrücklich für Claude:
Nicht nur anders gruppieren. Die Kategorien, Statuswechsel, Freigaben, Korrekturen, Suche, Filter, Bearbeiten, Speichern und Kira-Verknüpfung müssen auch funktional korrekt gesetzt werden.