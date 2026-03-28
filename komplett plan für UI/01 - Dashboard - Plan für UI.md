Plan für UI

Step 1: Zielstruktur nur für das Dashboard.

Das Dashboard bekommt volle Breite und wird als Cockpit gebaut. Nicht als mittige Kartenwand. Nicht als Mailstartseite. Nicht als Verlängerung von Kommunikation. Es soll beim Öffnen in 5 Sekunden sagen: Was ist heute wichtig, was brennt, was bringt Geld, was kippt, was braucht Entscheidung.

Die Zielstruktur für das Dashboard ist aus meiner Sicht so:

Oben eine schmale Utility-Zeile.
Links globale Suche.
Mitte leer oder kontextabhängig.
Rechts Systemstatus, offene Aufgaben, schnelle Aktion, Profil.

Darunter das Tagesbriefing als horizontale Management-Zeile.
Keine große Karte, sondern ein kompakter Überblick:
heute wichtig,
kritische Fristen,
Nachfass,
Geschäftssignale,
auffällige Dinge.
Das passt auch zur Projektübersicht, weil dort das Briefing bereits als eigener Bestandteil und als proaktiver Tagesstart vorgesehen ist.

Darunter die KPI-Zone in voller Breite.
Nicht 4 kleine Kästen in der Mitte, sondern ein sauberes Raster über die nutzbare Fläche.
Die Karten:
Antworten nötig
Neue Leads
Angebotsrückmeldungen
Termine / Fristen
Offenes Rechnungsvolumen
Eingangsrechnungen offen
Nachfass fällig
Gesamt offen

Wichtig:
jede Karte klickbar,
führt direkt in die passende gefilterte Modulansicht,
keine reine Deko.
Das ist auch exakt die fachliche Soll-Struktur, die im Projekt für das Dashboard beschrieben ist.

Darunter der eigentliche Arbeitsbereich des Dashboards in drei Spalten oder zwei flexible Zonen, je nach Breite:

Zone 1 links, breit:
Heute priorisiert
Maximal 5 Einträge.
Jeder Eintrag mit:
Titel
kurzer Grund
nächste Aktion
Kategorie-Badge
Dringlichkeit
Button „öffnen“ oder „mit Kira besprechen“

Zone 2 rechts oben:
Nächste Termine & Fristen
Kompakt als Liste oder Mini-Timeline
Datum, Typ, Kontext, Kunde, Aktion

Zone 2 rechts unten:
Geschäft aktuell
letzte Zahlungen
kritische Rechnungen
Nachfass
offene Eingangsrechnungen
Skonto-Hinweise

Darunter über volle Breite:
Signale / Auffälligkeiten
Das sind keine normalen Aufgaben, sondern Dinge wie:
unklare Zahlung
alte offene Rechnung
Angebot seit X Tagen ohne Reaktion
widersprüchige Daten
manuelle Prüfung nötig

Wichtig:
Mailkarten gehören nicht als Hauptmasse auf die Startseite.
Höchstens einzelne priorisierte Einträge aus Kommunikation, aber kuratiert, nicht roh. Genau das ist auch in Prompt 05 und der Memory festgelegt.

Mein konkreter Dashboard-Grundsatz für Claude wäre:
Das Dashboard ist eine Führungsansicht, kein Arbeitsdump.
Es zeigt Priorität, Signale und Einstiege.
Die eigentliche Detailarbeit passiert in Kommunikation, Organisation, Geschäft und Kira.

Was ich im Dashboard ausdrücklich nicht mehr sehen will:
lange Maillisten
viele kleine gleichartige Karten
schmale Mittelspalte
blasse Mini-Infos
zu kleine Schrift
Text ohne klare Aktion
Kira nur als kleines angeheftetes Element

Was ich dort stattdessen sehen will:
klare Hierarchie
viel bessere Lesbarkeit
wenige, starke Bereiche
volle Breite sinnvoll genutzt
echte Klick-Logik
sichtbare Priorisierung
deutliche Trennung zwischen:
Kommunikation,
Organisation,
Geschäft,
Auffälligkeiten


=====================================================================================================================================================================

So sollte Claude das Dashboard jetzt visuell bauen:

AIWorkspace Pro

Tools & GPTs




Teammitglieder einladen
ja, nächster step wieder mit verbindung zu den funktionen

Nachgedacht für 6s
Step 5: Zielbild für „Geschäft“ — mit echter Funktionslogik, nicht nur schönerer Darstellung.

Hier ist die größte Gefahr wieder dieselbe: Claude baut hübschere Karten, aber lässt die Seite im Kern wie eine Mailsammlung. Genau das darf nicht passieren. Laut Projektstand ist „Geschäft“ fachlich längst mehr als Mail: offene Rechnungssicht, Angebote, Eingangsrechnungen, Mahnungen, Geschäftsstatistik, Zahlungs-Matching, Rechnungsdetails und spätere Erweiterungen wie Kalkulation, Preispositionen, Cashflow und Kunden-360 sind bereits vorgesehen. Das muss jetzt auch wie ein kaufmännisches Modul aussehen und sich so verhalten. 

 

 


Also: Claude soll „Geschäft“ nicht nur anders anordnen, sondern die Funktionen dazu auch wirklich richtig setzen.

So sollte die Seite aufgebaut sein:

Ganz oben eine breite Modul-Kopfzeile.
Links Titel „Geschäft“ plus kompakte Live-Zahlen, zum Beispiel:
offenes Rechnungsvolumen,
offene Eingangsrechnungen,
Angebote offen,
Nachfass fällig,
ungeklärte Zahlungen.
Rechts:
Suche,
Datumsfilter,
Export,
manuelle Prüfung,
Neubewertung / Sync.

Wichtig:
Diese Zahlen müssen aus den echten Geschäftsdaten kommen, nicht aus Betreff-Suchen.
Wenn Daten unvollständig oder unsicher sind, muss das sichtbar markiert werden.
Keine falsche Sicherheit.

Darunter eine sekundäre Navigation, klar und groß genug:
Übersicht
Ausgangsrechnungen
Angebote
Eingangsrechnungen
Zahlungen
Mahnungen
Auswertung

Zusätzlich mit Badge „In Planung“:
Kalkulation
Preispositionen
Cashflow
Kunden-360

Wichtig:
Diese Tabs müssen funktional sein.
Jeder Tab zeigt einen anderen echten Datenscope.
Nicht nur dieselbe Liste in anderer Verpackung.

Jetzt zur Struktur der einzelnen Bereiche.

Übersicht:
Das ist die kaufmännische Cockpit-Seite innerhalb von Geschäft.

Oben eine Hero-Zone mit 4 bis 6 großen Zahlen:
offenes Rechnungsvolumen
fällige Ausgangsrechnungen
offene Eingangsrechnungen
Angebote ohne Rückmeldung
ungeklärte Zahlungen
Mahnfälle

Diese Kacheln müssen klickbar sein.
Klick auf „offene Eingangsrechnungen“ öffnet den passenden Untertab mit Filter.
Klick auf „Angebote ohne Rückmeldung“ springt zu Angebote mit aktivem Nachfass-Filter.

Darunter zwei Zonen.

Links, breit:
Aktuelle geschäftliche Vorgänge
also:
kritische Rechnungen
fällige Zahlungen
Angebote mit Handlungsbedarf
ungeklärte Belege

Rechts:
Signale / Warnungen
zum Beispiel:
Rechnung aus altem Thread erkannt
Dokumentdatum weicht vom Maildatum ab
Doppelzuordnung möglich
Skonto läuft bald ab
Zahlung ohne klare Rechnung
manuelle Prüfung nötig

Wichtig:
Diese Warnungen müssen funktional mit den Datensätzen verknüpft sein.
Beim Klick muss der jeweilige Fall geöffnet werden.

Ausgangsrechnungen:
Nicht als Mailliste, sondern als echte Tabelle oder hybride Arbeitsliste.

Spalten:
Rechnungsnummer
Kunde
Rechnungsdatum
Fälligkeit
Betrag
Zahlungsstatus
Leistungsart
Quelle
Aktion

Filter:
offen
überfällig
bezahlt
teilbezahlt
ungeklärt
letzter Monat
dieses Jahr

Aktionen:
Details öffnen
mit Kira besprechen
Status prüfen
zu Zahlung springen
Dokument öffnen

Wichtig:
Claude soll die Funktionen wirklich richtig setzen.
„Details öffnen“ lädt den Geschäftsdatensatz, nicht nur die Mail.
„Dokument öffnen“ öffnet das erkannte Rechnungsdokument oder den Beleg.
„zu Zahlung springen“ zeigt verknüpfte Zahlungseinträge.
„mit Kira besprechen“ öffnet den Geschäftskontext in Kira, nicht einen generischen Chat.

Angebote:
Diese Seite ist keine Rechnungsliste.
Sie muss wie eine Pipeline funktionieren.

Oben Filter:
neu
gesendet
Rückmeldung offen
Nachfass fällig
gewonnen
verloren
unklar

Darstellung:
als saubere Liste oder Board-artige Abschnitte, aber nicht verspielt.
Jeder Eintrag zeigt:
Kunde
Projekt
Angebotsdatum
Volumen
Status
nächste Aktion
Nachfass-Datum

Aktionen:
öffnen
mit Kira besprechen
Nachfass vorbereiten
Status ändern
Notiz

Wichtig:
„Nachfass vorbereiten“ muss eine echte Aktion auslösen, nicht nur eine Deko-Schaltfläche.
Wenn vorhanden, soll der bisherige Verlauf oder die Angebots-Historie einbezogen werden.

Eingangsrechnungen:
Diese Seite braucht eine klare Trennung zu Ausgangsrechnungen.
Keine Vermischung.

Spalten:
Gegenpartei
Dokumenttyp
Rechnungsdatum
Eingangsdatum
Betrag
Status
Zahlziel
Prüfbedarf
Quelle

Filter:
neu erkannt
offen
bezahlt
ungeklärt
Abo
mit Alt-Anhang
manuelle Prüfung

Wichtig:
Hier muss Claude die Logik wirklich funktional richtig setzen:
Maildatum, Dokumentdatum und Thread-Kontext dürfen nicht stumpf vermischt werden.
Wenn eine alte Rechnung in einem neuen Thread hängt, muss der Datensatz das erkennen und markieren, statt sie als „aktuell“ zu zählen.
Genau dieser Fehler wurde von dir schon beschrieben und muss hier fachlich behoben werden.

Zahlungen:
Diese Seite muss eigenständig sein, nicht nur Rechnungsstatus wiederholen.

Bereiche:
Zahlungseingänge
Abbuchungen
Rückzahlungen
Teilzahlungen
nicht zuordenbare Zahlungen

Jeder Eintrag zeigt:
Datum
Betrag
Typ
Gegenpartei
zugeordnet ja/nein
bezogene Rechnung ja/nein
Klärstatus

Aktionen:
zuordnen
Fall öffnen
mit Kira besprechen
manuelle Prüfung
als erledigt markieren

Wichtig:
„zuordnen“ und „manuelle Prüfung“ müssen echte Funktionen sein oder sauber als noch nicht umgesetzt markiert sein.
Keine Fake-Knöpfe.

Mahnungen:
Keine große Standardliste, sondern klare Arbeitsansicht.

Zeigt:
mahnbare Fälle
bereits gemahnt
Mahnstufe
nächster Schritt
Kommunikationsverlauf
Risiko

Aktionen:
Mahnung öffnen
mit Kira besprechen
Frist setzen
Status ändern

Auswertung:
Hier sollte Claude bewusst eine ruhigere Analysefläche bauen.
Nicht zu viele Charts.
Lieber wenige, gute Auswertungen.

Sinnvoll:
Monatsentwicklung
offen vs. bezahlt
Angebotsquote
durchschnittliche Zahlungsdauer
Anzahl manuelle Prüfungen
offene Volumina nach Status

Wichtig:
Nur zeigen, was belastbar ist.
Wenn Datenlage unklar, dann klar markieren:
unvollständig
noch im Aufbau
nicht valide genug

Das ist wichtig, damit das Modul nicht wieder „Senf präsentiert“, wie du es genannt hast.

Jetzt die übergreifenden Funktionsregeln für „Geschäft“:

Erstens:
Geschäft arbeitet primär datensatzbasiert, nicht mailbasiert.
Mails sind nur Quelle oder Kontext, nicht die Hauptdarstellung.

Zweitens:
Jede Hauptansicht braucht echte Filterlogik.
Nicht nur optische Dropdowns.

Drittens:
Jede Hauptaktion muss technisch wirklich etwas tun:
öffnen,
filtern,
zuordnen,
Status ändern,
mit Kira besprechen,
Dokument laden,
Prüfung markieren.

Viertens:
Warnungen und Auffälligkeiten müssen anklickbar und nachvollziehbar sein.

Fünftens:
Wenn Daten unklar sind, muss die UI das zeigen statt saubere Zahlen vorzutäuschen.

Was ich hier ausdrücklich nicht mehr will:
Mails mit dem Wort „Rechnung“
alte Thread-Anhänge als aktuelle Geschäftsfälle
gleichförmige Kartenwände
Mini-Tabellen mit zu kleiner Schrift
rein dekorative Finanz-KPIs
nicht anklickbare Warnungen

Was ich stattdessen will:
echtes kaufmännisches Modul
lesbare Tabellen
große klare Kennzahlen
echte Datensatzlogik
brauchbare Warnungen
echte Aktionen
gute Verknüpfung zu Kira

Wenn ich das als kompaktes Text-Wireframe zusammenfasse:

Kopfzeile
Titel | Live-Zahlen | Datumsfilter | Suche | Export | Sync/Prüfung

Sekundäre Navigation
Übersicht | Ausgangsrechnungen | Angebote | Eingangsrechnungen | Zahlungen | Mahnungen | Auswertung

Übersicht
oben große KPI-Zahlen
links aktuelle Geschäftsvorgänge
rechts Warnungen / Auffälligkeiten

Unterseiten
tabellarische oder hybride Arbeitsansichten
mit echten Filtern und echter Aktionsebene

Kira-Anbindung
jeder Datensatz kann mit Kira besprochen werden
Kira übernimmt dabei Rechnungs-/Angebots-/Zahlungskontext sauber

Und wieder ausdrücklich für Claude:
Nicht nur schöner machen. Die Datenlogik, Filter, Datensatzöffnungen, Verknüpfungen, Warnungen und Kira-Aktionen müssen auch funktional korrekt gesetzt werden.

Der nächste sinnvolle Step wäre:
„Wissen“ als Wireframe + Funktionslogik, damit das endlich wie eine echte Wissensbibliothek mit Bearbeitung wirkt und nicht wie eine lange Regelwand.

Anpassen oder nächster Step?


klingt gut, nächster step

Nachgedacht für 5s
Step 6: Zielbild für „Wissen“ — wieder mit echter Funktionslogik, nicht nur hübscheren Kacheln.

Genau hier ist der aktuelle Stand noch am deutlichsten „technisch vorhanden, aber UX-seitig schwach“. Laut Projekt gibt es Wissen, editierbare Regeln, Vorschläge, Freigaben, Stil/Ton, Preislogik, Technik, Prozesse und Projektwissen bereits als fachliche Grundlage. In Prompt 04 und Prompt 05 ist außerdem klar festgelegt, dass Wissen nicht mehr als Regelwand enden darf, sondern als Bibliothek plus Regelsteuerung funktionieren soll. 

 

 


Also: Claude soll „Wissen“ nicht als Sammlung langer Blöcke bauen, sondern als echtes Wissenszentrum. Und die Funktionen dazu müssen richtig gesetzt werden.

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

Der nächste sinnvolle Step wäre:
„Kira Workspace“ als Wireframe + Funktionslogik, weil genau dort der größte Erlebnisbruch aktuell noch sitzt.

Anpassen oder nächster Step?


nächster step

Nachgedacht für 9s
Step 7: Zielbild für den Kira-Workspace — mit echter Arbeitslogik, nicht nur Chatfläche.

Hier sitzt aktuell der größte Bruch. Kira ist zwar sichtbar, aber noch nicht als echtes Assistenzsystem gebaut. Für dich muss Kira wie ein Arbeitsraum wirken, nicht wie ein kleines Seitenmodul oder ein größer gezogener Chatkasten. Darum ist der nächste Schritt entscheidend: Claude muss Kira als eigenen Workspace denken und die Funktionen dazu auch wirklich korrekt setzen.

So sollte Kira aufgebaut sein:

Kira hat drei Ebenen.

Erstens der Launcher.
Unten rechts ein kleiner, hochwertiger Einstieg. Ruhig, präzise, nicht verspielt. Er darf sichtbar sein, aber nicht wie ein Gimmick. Hover, Statuspunkt, evtl. kleine Aktivitätsanzeige reichen.

Zweitens das Quick Panel.
Beim Klick auf Kira öffnet sich kein halber Chat, sondern ein kompaktes Aktionspanel mit klaren Einstiegen:
Frage stellen
Aufgabe besprechen
Rechnung prüfen
Angebot prüfen
Kunde öffnen
Suche
Letzte Verläufe

Wichtig:
Diese Punkte müssen funktional sein.
„Rechnung prüfen“ öffnet nicht einfach den allgemeinen Chat, sondern startet Kira mit Rechnungskontext.
„Aufgabe besprechen“ übernimmt die aktuelle Aufgabe.
„Kunde öffnen“ sucht im Kundentext oder CRM-Kontext.
„Letzte Verläufe“ zeigt echte Historie.

Drittens der volle Kira-Workspace.
Das ist die eigentliche Hauptfläche für Zusammenarbeit mit Kira. Nicht als Sidebar, nicht als kleine Leiste, sondern als großer Arbeitsraum. Entweder als eigener Modulbereich oder als großes Overlay. Aber immer so, dass man dort wirklich arbeiten kann.

Der Aufbau des Kira-Workspace sollte dreigeteilt sein:

Links:
Kontexte / Threads / Verläufe
Hier stehen:
offene Aufgaben
letzte Gespräche
aktive Vorgänge
fixierte Kontexte
Suchergebnisse

Diese Liste muss anklickbar sein und den mittleren Arbeitsraum wirklich wechseln.

Mitte:
der eigentliche Gesprächs- und Arbeitsbereich
Dort passiert die Zusammenarbeit mit Kira:
Fragen
Entwürfe
Zusammenfassungen
Rückfragen
Strategien
Prüfungen
Dokumentvorschläge

Der Chatbereich muss groß, ruhig und sehr gut lesbar sein. Keine schmale Spalte, keine Mini-Typografie, keine zu dünnen Farben.

Rechts:
optionale Werkzeug- und Kontextspalte
Dort stehen je nach Vorgang:
Anhänge
Kundendaten
Mail-Zusammenfassung
Rechnungsdaten
Angebotsdaten
Wissensregeln
nächste Aktionen
Tools

Wichtig:
Diese rechte Spalte darf einklappbar sein. Sie soll helfen, aber nicht dauernd Platz wegnehmen.

Jetzt zur Funktionslogik. Das ist der entscheidende Teil.

Kira muss kontextbasiert starten können.
Das heißt: Wenn du aus Kommunikation „Mit Kira besprechen“ klickst, muss Kira nicht leer aufgehen, sondern mit:
Mail-/Thread-Kontext
Zusammenfassung
Anhängen
Status
bisheriger Einordnung
nächster Empfehlung

Wenn du aus Geschäft kommst, dann mit:
Rechnungs- oder Angebotsdatensatz
Status
Warnung
relevanten Belegen
passender Fragestellung

Wenn du aus Wissen kommst, dann mit:
Regel oder Wissenseintrag
Kategorie
Historie
Bearbeitungsoptionen

Also:
Claude soll nicht einfach nur einen allgemeinen Chat bauen, sondern echte Einstiegskontexte funktional verdrahten.

Der mittlere Bereich des Kira-Workspace braucht oberhalb des Chats eine Kontextleiste.
Dort sichtbar:
aktueller Modus
z. B. Aufgabe, Mail, Rechnung, Angebot, Wissen, Suche
Kontexttitel
verknüpfte Objekte
Provider
evtl. letzte Aktualisierung

Daneben schnelle Aktionen:
Kontext lösen
weiteren Kontext anhängen
Anhänge hinzufügen
mit anderem Tool prüfen
an Verlauf anheften

Diese Aktionen müssen wirklich funktionieren.
Nicht nur schöne Chips.

Jetzt der Chatbereich selbst.

Der Chat darf nicht bloß Nachrichten zeigen.
Er muss als Arbeitskonsole funktionieren.

Elemente, die dort sinnvoll sind:
große Eingabezeile
Anhang-Button
Kontext anhängen
Modus wählen
Senden
Antwort stoppen
Verlauf umbenennen
als Aufgabe speichern
als Entwurf übernehmen

Über dem Eingabefeld können je nach Kontext Quick Actions auftauchen, etwa:
Antworte auf diese Mail
fasse zusammen
erstelle Rückfrage
bewerte Risiko
prüfe Rechnung
vergleiche mit Wissensregeln
erstelle Nachfass-Vorschlag

Wichtig:
Diese Quick Actions müssen kontextabhängig sein.
Mail-Kontext zeigt andere Aktionen als Rechnungs-Kontext.

Wenn Kira antwortet, dann nicht nur Text.
Sondern je nach Fall auch strukturierte Karten:
Zusammenfassung
Entwurf
offene Fragen
nächste Schritte
Warnhinweis
Dokumentvorschlag

Diese Karten müssen weiter nutzbar sein:
als Entwurf übernehmen
in Aufgabe umwandeln
in Wissensvorschlag speichern
zurück in Kommunikation senden
bearbeiten

Das ist wichtig:
Der Chat muss nicht nur „reden“, sondern Arbeit weitergeben können.

Jetzt zu „Aufgabe besprechen“, weil das aktuell besonders schwach wirkt.

Wenn du auf „Aufgabe besprechen“ klickst, soll nicht einfach die Aufgabenbeschreibung in den Chat kopiert werden. Stattdessen braucht es eine strukturierte Aufgabenstartkarte im Chat:
Worum geht es
Warum ist es offen
welche Daten sind vorhanden
welche Anhänge gibt es
welche Entscheidung ist jetzt nötig
welche Vorschläge sind sinnvoll

Darunter ein Eingabefeld von dir und dann erst Kiras Reaktion.

Also:
nicht stumpf Inhalte reinschieben,
sondern Arbeitskontext aufbauen.

Historie braucht einen eigenen Bereich.
Nicht nur irgendwo mitlaufen.

Im Kira-Workspace oder in der Navigation muss es einen Bereich „Verläufe“ geben.
Dort:
Titel
letzte Aktivität
Kontexttyp
fixiert ja/nein
wieder öffnen
umbenennen
archivieren

Wichtig:
Verläufe müssen wirklich gespeichert und wieder aufrufbar sein.

Kira sollte außerdem verschiedene Modustypen beherrschen:
Fragen
Bearbeiten
Prüfen
Entscheiden
Erstellen

Das kann als Modusleiste oder Kontextschnellwahl umgesetzt werden.
Der Punkt ist:
Kira soll nicht immer denselben Chatmodus zeigen.
Ein Rechnungsprüf-Flow fühlt sich anders an als eine Mailantwort oder Wissensbearbeitung.

Was ich hier ausdrücklich nicht mehr will:
schmalen Chat
blasse Minischrift
einfach nur Daten in den Chat kippen
keine klare Kontextleiste
keine echte Historie
rechte Leiste als Pflicht
Kira als bloßes Zusatzfenster

Was ich stattdessen will:
eigenen Arbeitsraum
große Lesbarkeit
kontextgesteuerte Zusammenarbeit
echte Folgeaktionen
echte Historie
echte Werkzeuglogik
echte Übergänge aus Kommunikation, Geschäft und Wissen

Wenn ich das als kurzes Text-Wireframe zusammenfasse:

Launcher
unten rechts, klein, hochwertig

Quick Panel
Frage stellen | Aufgabe besprechen | Rechnung prüfen | Angebot prüfen | Kunde öffnen | Suche | Verläufe

Kira-Workspace
links: Kontexte / Verläufe
mitte: Chat / Arbeitsbereich
rechts: Werkzeuge / Daten / Anhänge / Vorschläge

Kontextleiste oben
Typ | Titel | Datenobjekte | Provider | Schnellaktionen

Chat unten
große Eingabe | Anhang | Kontext anhängen | Modus | Senden

Antworten
nicht nur Text, sondern nutzbare Arbeitskarten mit Folgeaktionen

Und wieder ausdrücklich für Claude:
Nicht nur UI bauen. Kontextübergaben, Verlauf, Anhänge, Quick Actions, Kira-Modi, Folgeaktionen und Bereichswechsel müssen auch funktional korrekt gesetzt werden.

Der nächste sinnvolle Step wäre:
„Einstellungen“ als Wireframe plus Funktionslogik, damit Design, Lesbarkeit, Branding später und Kira-Verhalten wirklich steuerbar werden.

Anpassen oder nächster Step?


perfekt, nächster step

Ich mache jetzt den nächsten Bereich genauso konkret: Einstellungen, aber nicht nur optisch, sondern mit echter Steuerlogik für Design, Kira, Provider und Verhalten. Danach fehlt uns nur noch die saubere Gesamtzusammenführung.

Nachgedacht für 17s
Step 8: Zielbild für „Einstellungen“ — wieder mit echter Steuerlogik, nicht nur Formulare hübscher machen.

Das ist wichtiger, als es erstmal wirkt. Laut Projekt gibt es in den Einstellungen heute schon Push-Benachrichtigungen, Aufgaben-Parameter, Nachfass-Intervalle, Server-Port, Auto-Browser und vor allem die Multi-LLM-Provider-Verwaltung mit Prioritäten, API-Keys, Modellwahl und Statusanzeige. Gleichzeitig ist im Rebuild klar festgelegt, dass Einstellungen künftig auch Design, Lesbarkeit, Dashboard, Kira-Verhalten, Integrationen und spätere Automationen steuern sollen. 

 


Also: Claude soll „Einstellungen“ nicht als lange Seite mit Inputs bauen, sondern als echtes Steuerzentrum. Und die Funktionen dazu müssen auch wirklich korrekt gesetzt werden.

So sollte „Einstellungen“ aufgebaut sein:

Ganz oben eine klare Modul-Kopfzeile.
Links Titel „Einstellungen“ plus kurze Statuszeile:
zum Beispiel aktiver Provider, Theme-Modus, Benachrichtigungen aktiv, letzte Änderung.
Rechts:
Suche
zurücksetzen
exportieren
importieren
Änderungen speichern

Wichtig:
Diese Statuszeile muss aus echten Zuständen kommen.
Nicht nur Deko.
Wenn aktuell Anthropic aktiv ist oder OpenAI als Fallback gesetzt ist, soll das dort sichtbar sein. Das passt auch zur Projektübersicht mit Provider-Verwaltung und Fallback-Reihenfolge. 

 


Darunter eine linke Sekundärnavigation oder große Segmentliste.
Nicht alles untereinander.

Bereiche:
Design
Benachrichtigungen
Aufgabenlogik
Nachfass-Intervalle
Dashboard
Kira / LLM / Provider
Integrationen
Automationen — In Planung

Wichtig:
Diese Bereiche müssen wirklich trennen.
Nicht nur Überschriften auf einer langen Scrollseite.

Bereich 1: Design

Das ist für dich besonders wichtig, weil die jetzige Oberfläche zu klein, zu blass und zu anstrengend ist. Genau das ist auch im Rebuild und in der Memory festgehalten: größere Standardschrift, bessere Kontraste, Dichte-Modi, Logo, Theme und Design als steuerbare Ebene. 

 

 


Unter „Design“ sollen direkt diese Einsteller liegen:
Farbschema
Akzentfarbe
Light / Dark / Auto
Schriftgröße
Dichte
Firmenname
Logo
Kartenradius
Schattenstärke
Animationen reduzieren
hoher Kontrast

Wichtig:
Claude soll diese Dinge nicht nur optisch zeigen, sondern funktional wirklich umschaltbar machen.
Wenn du Schriftgröße auf groß stellst, muss sich die App sichtbar anpassen.
Wenn du Dichte auf entspannt stellst, müssen Listen, Karten und Tabellen mehr Luft bekommen.
Wenn du hohem Kontrast aktivierst, müssen Farben und Trennungen wirklich lesbarer werden.
Wenn Logo/Firmenname geändert werden, muss die App-Shell das übernehmen.

Bereich 2: Benachrichtigungen

Hier greifen die schon vorhandenen technischen Grundlagen wie ntfy.sh und Windows Toast. Das ist bereits dokumentiert. 

 


Sinnvolle Einstellungen:
Push aktiv / aus
Windows-Benachrichtigung aktiv / aus
nur hohe Priorität
Zusammenfassungsmodus
Zeitfenster für Stille
Testbenachrichtigung senden

Wichtig:
„Testbenachrichtigung“ muss eine echte Testaktion auslösen.
Nicht nur ein Placebo-Button.

Bereich 3: Aufgabenlogik

Hier sollen die vorhandenen Aufgaben-Parameter steuerbar werden.
Laut Projekt gibt es Erinnerungsintervall und Prüfzeitraum bereits. 


Sinnvolle Felder:
Erinnerungsintervall
Prüfzeitraum
wann Aufgaben als dringend gelten
wie lange etwas offen sein darf
ob automatisch Wiedervorlagen vorgeschlagen werden
manuelle Prüfungen bevorzugen ja/nein

Wichtig:
Diese Werte müssen in die Aufgaben- und Task-Logik zurückschreiben.
Nicht nur UI.

Bereich 4: Nachfass-Intervalle

Das ist fachlich schon im Projekt verankert: 10/21/45 Tage, anpassbar. Außerdem sind Nachfass-Mails und Angebotsstatus Teil des Systems. 

 


Diese Seite sollte nicht nur drei Zahlen zeigen, sondern:
Intervall 1, 2, 3
Tonalitätsstufe
nur für Angebote / auch für Rechnungen / auch für Leads
automatisch erinnern ja/nein
manuell bestätigen vor Entwurf ja/nein

Wichtig:
Wenn du die Intervalle änderst, muss die Nachfass-Logik und die Anzeige in Geschäft / Kommunikation das wirklich berücksichtigen.

Bereich 5: Dashboard

Hier steuerst du, wie das Cockpit aussieht und priorisiert.

Sinnvolle Einstellungen:
welche KPI-Karten oben gezeigt werden
wie viele Prioritäten angezeigt werden
welche Blöcke eingeblendet sind
ob Geschäftssignale sichtbar sind
Startansicht beim Öffnen
kompakt / standard / entspannt

Wichtig:
Diese Optionen müssen die Dashboard-Oberfläche wirklich verändern.
Nicht nur ein Einstellungsformular ohne Wirkung.

Bereich 6: Kira / LLM / Provider

Das ist ein Kernbereich, weil laut Projekt hier bereits Provider hinzugefügt, entfernt, sortiert, priorisiert und mit API-Key/Modell versehen werden können. Außerdem gibt es Multi-LLM-Fallback und sichtbare Provider-Info im Chat. 

 


Diese Seite muss wie eine kleine Provider-Konsole wirken, nicht wie ein nacktes JSON-Formular.

Bereiche:
aktive Providerliste
Fallback-Reihenfolge
Provider hinzufügen
Provider testen
Modellwahl
API-Status
Kontextverhalten

Wichtige Aktionen:
hinzufügen
deaktivieren
sortieren
testen
als Standard setzen
Fallback-Reihenfolge speichern

Wichtig:
Diese Aktionen müssen wirklich die Konfiguration ändern.
Nicht bloß lokal die UI umsortieren.

Zusätzlich sinnvoll:
Kira-Verhalten einstellen:
standardmäßiger Kontextmodus
wie viel Historie geladen wird
ob Antworten eher knapp / standard / ausführlich sein sollen
ob Vorschläge aggressiv / neutral / zurückhaltend erscheinen
ob Kira automatisch Folgeaktionen anbietet

Auch das soll funktional wirken, nicht nur textlich da sein.

Bereich 7: Integrationen

Hier kann Claude jetzt schon eine saubere Shell für spätere Anbindungen aufbauen:
Mail
Kalender — In Planung
OneDrive / Dokumente
Push
Web-Recherche
weitere Quellen

Wichtig:
Nicht tot.
Aber klar als aktuelle vs. geplante Integration markieren.

Bereich 8: Automationen — In Planung

Hier reicht jetzt eine gute Shell, aber nicht leer.
Zeigen:
was später kommt
z. B. Regeln, Trigger, Eskalationen, Follow-ups, automatische Aufgaben.
Das passt direkt zu den in Planung genannten Workflow-Bausteinen, Triggern und Eskalationen im Rebuild. 


Jetzt zur Detailansicht innerhalb der Einstellungen:

Claude soll dort nicht einfach Rohformulare mit 20 Inputs übereinander bauen.
Sondern:
links Bereichsnavigation,
mitte die Hauptkonfiguration,
rechts optional Hilfe / Status / Vorschau.

Vor allem bei Design ist eine Live-Vorschau sinnvoll.
Wenn du Schriftgröße, Dichte, Kontrast oder Theme änderst, sollte man das direkt sehen.
Das ist wichtig, damit das Modul nicht wieder technisch korrekt, aber UX-seitig unerquicklich wird.

Was ich hier ausdrücklich nicht mehr will:
lange Forms ohne Gliederung
blasse kleine Inputs
Mini-Schrift
keine Rückmeldung nach Änderung
Speichern ohne sichtbare Wirkung
Provider nur als technische Zeilen
Designoptionen ohne Vorschau

Was ich stattdessen will:
echtes Steuerzentrum
klare Kategorien
größere lesbare Einstellungen
live wirksame Optionen
gute Provider-Konsole
Dashboard- und Kira-Steuerung
klare Trennung von aktiv, geplant, technisch, visuell

Wenn ich das als kompaktes Text-Wireframe zusammenfasse:

Kopfzeile
Titel | Status | Suche | Import | Export | Speichern

Linke Bereichsnavigation
Design | Benachrichtigungen | Aufgabenlogik | Nachfass | Dashboard | Kira/LLM/Provider | Integrationen | Automationen

Hauptbereich
große, klar gruppierte Einstellungen
je Bereich mit echten Schaltern, Auswahlfeldern und Speichern

Rechte Hilfsspalte optional
Status
Vorschau
Kontext
Testaktionen

Und wieder ausdrücklich für Claude:
Nicht nur Formulare schöner machen. Die Designoptionen, Provider-Reihenfolge, Fallbacks, Benachrichtigungen, Dashboard-Einstellungen, Nachfass-Werte und Kira-Verhaltensparameter müssen auch funktional korrekt gesetzt werden.

Damit haben wir die sechs Kernbereiche jetzt inhaltlich sauber aufgespannt:
Dashboard,
Kommunikation,
Geschäft,
Wissen,
Kira Workspace,
Einstellungen.

Der nächste sinnvolle Schritt ist jetzt nicht sofort noch mehr Text, sondern die visuelle Ebene:
Wir sollten daraus jetzt Wireframe-/Mockup-Vorlagen für die wichtigsten Screens bauen, damit Claude nicht wieder frei interpretiert.

Anpassen oder nächster Step?


bevor wir damit beginnen, noch einmal zurüch zum Daschboard, hier das wireframe noch mal mit funktionslogic ausgeben, das hatten wir da noch nicht..


hier noch mal der context

Plan für UI

Step 1: Zielstruktur nur für das Dashboard.

Das Dashboard bekommt volle Breite und wird als Cockpit gebaut. Nicht als mittige Kartenwand. Nicht als Mailstartseite. Nicht als Verlängerung von Kommunikation. Es soll beim Öffnen in 5 Sekunden sagen: Was ist heute wichtig, was brennt, was bringt Geld, was kippt, was braucht Entscheidung.

Die Zielstruktur für das Dashboard ist aus meiner Sicht so:

Oben eine schmale Utility-Zeile.
Links globale Suche.
Mitte leer oder kontextabhängig.
Rechts Systemstatus, offene Aufgaben, schnelle Aktion, Profil.

Darunter das Tagesbriefing als horizontale Management-Zeile.
Keine große Karte, sondern ein kompakter Überblick:
heute wichtig,
kritische Fristen,
Nachfass,
Geschäftssignale,
auffällige Dinge.
Das passt auch zur Projektübersicht, weil dort das Briefing bereits als eigener Bestandteil und als proaktiver Tagesstart vorgesehen ist.

Darunter die KPI-Zone in voller Breite.
Nicht 4 kleine Kästen in der Mitte, sondern ein sauberes Raster über die nutzbare Fläche.
Die Karten:
Antworten nötig
Neue Leads
Angebotsrückmeldungen
Termine / Fristen
Offenes Rechnungsvolumen
Eingangsrechnungen offen
Nachfass fällig
Gesamt offen

Wichtig:
jede Karte klickbar,
führt direkt in die passende gefilterte Modulansicht,
keine reine Deko.
Das ist auch exakt die fachliche Soll-Struktur, die im Projekt für das Dashboard beschrieben ist.

Darunter der eigentliche Arbeitsbereich des Dashboards in drei Spalten oder zwei flexible Zonen, je nach Breite:

Zone 1 links, breit:
Heute priorisiert
Maximal 5 Einträge.
Jeder Eintrag mit:
Titel
kurzer Grund
nächste Aktion
Kategorie-Badge
Dringlichkeit
Button „öffnen“ oder „mit Kira besprechen“

Zone 2 rechts oben:
Nächste Termine & Fristen
Kompakt als Liste oder Mini-Timeline
Datum, Typ, Kontext, Kunde, Aktion

Zone 2 rechts unten:
Geschäft aktuell
letzte Zahlungen
kritische Rechnungen
Nachfass
offene Eingangsrechnungen
Skonto-Hinweise

Darunter über volle Breite:
Signale / Auffälligkeiten
Das sind keine normalen Aufgaben, sondern Dinge wie:
unklare Zahlung
alte offene Rechnung
Angebot seit X Tagen ohne Reaktion
widersprüchige Daten
manuelle Prüfung nötig

Wichtig:
Mailkarten gehören nicht als Hauptmasse auf die Startseite.
Höchstens einzelne priorisierte Einträge aus Kommunikation, aber kuratiert, nicht roh. Genau das ist auch in Prompt 05 und der Memory festgelegt.

Mein konkreter Dashboard-Grundsatz für Claude wäre:
Das Dashboard ist eine Führungsansicht, kein Arbeitsdump.
Es zeigt Priorität, Signale und Einstiege.
Die eigentliche Detailarbeit passiert in Kommunikation, Organisation, Geschäft und Kira.

Was ich im Dashboard ausdrücklich nicht mehr sehen will:
lange Maillisten
viele kleine gleichartige Karten
schmale Mittelspalte
blasse Mini-Infos
zu kleine Schrift
Text ohne klare Aktion
Kira nur als kleines angeheftetes Element

Was ich dort stattdessen sehen will:
klare Hierarchie
viel bessere Lesbarkeit
wenige, starke Bereiche
volle Breite sinnvoll genutzt
echte Klick-Logik
sichtbare Priorisierung
deutliche Trennung zwischen:
Kommunikation,
Organisation,
Geschäft,
Auffälligkeiten


=====================================================================================================================================================================

So sollte Claude das Dashboard jetzt visuell bauen:

Ganz oben eine breite Utility-Zeile über die volle Seite. Links globale Suche. In der Mitte optional leer oder kontextabhängig. Rechts offene Aufgaben, Provider-/Systemstatus, schnelle Aktionen. Die App-Shell soll laut Prompt bewusst die Breite nutzen und eben nicht wieder in eine enge Zentralspalte zurückfallen.

Darunter ein kompaktes Tagesbriefing über fast die ganze Nutzbreite. Kein dicker Kasten mit viel Luft, sondern eine klare Management-Zeile mit drei bis fünf Signalen:
Heute wichtig
kritischste Punkte
Nachfass fällig
Fristen
Geschäftssignale
Das passt direkt zu dem, was in der Projektübersicht als „Kira proaktiver Tagesstart“ schon vorgesehen ist.

Darunter eine volle KPI-Zone in zwei Reihen oder einem adaptiven Grid. Nicht vier kleine Kästchen in der Mitte, sondern ein sauberes Raster über die verfügbare Fläche. Die Karten:
Antworten nötig
Neue Leads
Angebotsrückmeldungen
Termine / Fristen
Offenes Rechnungsvolumen
Eingangsrechnungen offen
Nachfass fällig
Gesamt offen
Diese Karten müssen laut Prompt klickbar sein und direkt in gefilterte Modulansichten führen.

Darunter der eigentliche Arbeitsbereich. Nicht eine einzige Spalte, sondern ein breites Zweizonen-Layout.

Links, die Hauptarbeitszone mit etwa 65 bis 70 Prozent Breite:
Heute priorisiert
Maximal fünf Einträge. Jeder Eintrag nur mit:
Titel
kurzer Grund
nächste Aktion
Badge
Dringlichkeit
Button „Öffnen“ oder „Mit Kira besprechen“

Rechts, die Nebenarbeitszone mit etwa 30 bis 35 Prozent Breite:
oben „Nächste Termine & Fristen“
darunter „Geschäft aktuell“
also zwei kompakte Panels mit hoher Informationsdichte. Das entspricht auch dem fachlichen Soll aus der Projektübersicht mit Top-5-Aufgaben, nächsten Terminen und letzten Geschäftsvorgängen.

Unter diesen beiden Zonen über volle Breite:
Signale / Auffälligkeiten
Das ist kein Mailblock, sondern eine kurze Liste von Ausreißern:
unklare Zahlung
alte offene Rechnung
Skonto läuft bald ab
Angebot seit X Tagen ohne Rückmeldung
manuelle Prüfung nötig
Diese Art von Frühwarn- und Managementsignal ist in der KIRA-Komplettübersicht bereits als Zielbild beschrieben, etwa bei Cashflow, Eskalationen, Nachfass und Anomalien.

Wichtig für Claude:
Auf dem Dashboard dürfen Mails nur noch in kuratierter Form vorkommen, nicht als Hauptmasse. Die Startseite ist eine Führungsansicht, keine Kommunikationsliste. Genau das steht sowohl in Prompt 05 als auch in der Memory.

Konkrete visuelle Regeln für das Dashboard:

Die Inhalte sollen fast die gesamte Browserbreite nutzen, aber in einem kontrollierten Grid. Keine schmale Mittelspalte.
Die Standard-Schrift muss größer und kräftiger werden. Zu blass und zu klein ist laut Rebuild-Prompt ausdrücklich zu vermeiden.
KPI-Karten sollen klarer, größer und klickbar sein.
Panels rechts sollen kompakt, aber gut lesbar sein.
„Heute priorisiert“ soll wie eine Task-/Decision-Liste wirken, nicht wie eine Mini-Mail-Ansicht.
Jeder Bereich muss eine sichtbare Überschrift und klare Hierarchie haben.
Kein leerer Raum ohne Funktion. Lieber Luft mit Struktur als Leere mit Unsicherheit.

Wenn ich das in ein schlichtes Text-Wireframe packe, dann so:

Obere Leiste
Suche | Schnellaktionen | Status | Profil

Tagesbriefing
kurze Zeile mit 3–5 Managementsignalen

KPI-Raster
8 klickbare Kennzahlen in voller Breite

Arbeitsbereich
links: Heute priorisiert
rechts oben: Nächste Termine & Fristen
rechts unten: Geschäft aktuell

Unterer Bereich
Signale / Auffälligkeiten

Nachgedacht für 5s
Ja. Hier ist das Dashboard jetzt noch einmal sauber zusammengezogen — diesmal ausdrücklich mit Funktionslogik, damit Claude nicht wieder nur die Optik baut und der Rest stumpf bleibt.

Dashboard – Wireframe plus Funktionslogik
Das Dashboard ist die Führungsansicht des Systems.
Es ist kein Posteingang, keine Mailliste und keine abgespeckte Kommunikationsseite.

Sein Zweck ist:
in wenigen Sekunden zeigen,
was heute wichtig ist,
wo Handlungsbedarf besteht,
welche Fristen oder Risiken anstehen,
was geschäftlich relevant ist,
und von dort gezielt in die passenden Module zu führen.

Die Detailarbeit passiert nicht auf dem Dashboard selbst, sondern in:
Kommunikation,
Organisation,
Geschäft
und Kira.

1. Grundregel für Claude
Das Dashboard muss komplett über die nutzbare Breite aufgebaut werden.
Keine schmale Mittelspalte.
Keine alte Kartenwand mit ein paar Kennzahlen oben.
Keine Mail-Hauptansicht als Startseite.

Das Dashboard ist ein Cockpit.
Es zeigt:
Priorität,
Signale,
Einstiege,
und konkrete nächste Wege.

Nicht:
Rohlisten,
Mailmassen,
Mini-Infos ohne Aktion.

2. Wireframe-Struktur
A. Obere Utility-Leiste
Über die volle Breite.

Links:
globale Suche

Mitte:
kontextabhängig leer oder Systemhinweis

Rechts:
offene Aufgaben
Systemstatus
Providerstatus
Schnellaktionen
Profil

Funktionslogik
Die globale Suche muss wirklich suchen, nicht nur UI sein.
Sie soll mindestens durchsuchen:
Aufgaben
Mails / Threads
Kundenbezüge
Geschäftsfälle
Wissenseinträge

Offene Aufgaben oben rechts muss anklickbar sein und in die passende Ansicht führen.

Systemstatus / Providerstatus muss echte Zustände anzeigen:
Server aktiv
Provider aktiv
Fallback verfügbar
Fehler / Warnung, falls vorhanden

Schnellaktionen müssen echte Einstiege sein, zum Beispiel:
Mit Kira sprechen
Neue Notiz
manuelle Aufgabe
Geschäft prüfen
Suche öffnen

3. Tagesbriefing
Direkt unter der Utility-Leiste eine kompakte horizontale Management-Zeile.

Inhalt:
Heute wichtig
kritischste Punkte
Nachfass fällig
Fristen
Geschäftssignale
auffällige Dinge

Nicht als riesige Karte.
Nicht mit viel leerem Raum.
Sondern kompakt, klar, hoch priorisiert.

Funktionslogik
Jeder Briefing-Punkt muss anklickbar sein und in den passenden Kontext führen.

Beispiele:
„3 kritische Fristen“ öffnet Organisation mit aktivem Fristenfilter
„2 Nachfass fällig“ öffnet Geschäft oder Kommunikation mit Nachfass-Filter
„1 unklare Zahlung“ öffnet Geschäft direkt auf den betroffenen Fall

Das Briefing darf nicht statisch oder händisch sein.
Es muss aus den vorhandenen Daten live befüllt werden.

Wenn für einen Bereich keine Daten vorhanden sind, soll das sauber dargestellt werden.
Nicht künstlich Platzhalter vortäuschen.

4. KPI-Zone
Darunter ein volles KPI-Raster über die Breite.

Karten:
Antworten nötig
Neue Leads
Angebotsrückmeldungen
Termine / Fristen
Offenes Rechnungsvolumen
Eingangsrechnungen offen
Nachfass fällig
Gesamt offen

Anordnung:
in zwei Reihen oder adaptiv im Grid, je nach Breite.

Nicht:
vier Minikarten in der Mitte.

Funktionslogik
Jede KPI-Karte ist eine aktive Navigationskarte.

Klick auf:
Antworten nötig → Kommunikation mit Filter „Antwort erforderlich“
Neue Leads → Kommunikation mit Filter „Neue Leads“
Angebotsrückmeldungen → Kommunikation oder Geschäft, je nach interner Zuordnung
Termine / Fristen → Organisation
Offenes Rechnungsvolumen → Geschäft / Übersicht oder Ausgangsrechnungen
Eingangsrechnungen offen → Geschäft / Eingangsrechnungen
Nachfass fällig → Geschäft oder Kommunikation mit Nachfassfilter
Gesamt offen → kombinierte offene Fälle oder Dashboard-Fokusansicht

Wichtig:
Diese Karten dürfen nicht nur Zahlen zeigen.
Sie müssen wirklich filtern und springen.

Wenn Daten unsicher oder unvollständig sind, muss die Karte das sichtbar markieren, z. B.:
„teilweise unvollständig“
statt einfach eine scheinpräzise Zahl zu zeigen.

5. Hauptarbeitsbereich
Darunter ein breites Zweizonen-Layout.

Linke Hauptzone, ca. 65–70 Prozent Breite
Bereich:
Heute priorisiert

Maximal fünf Einträge.

Jeder Eintrag zeigt:
Titel
kurzer Grund
nächste Aktion
Kategorie-Badge
Dringlichkeit
Button „Öffnen“
Button „Mit Kira besprechen“

Funktionslogik
Diese Liste ist keine Mailliste.
Sie ist eine priorisierte Entscheidungs-/Arbeitsliste.

Die Einträge müssen kuratiert aus mehreren Modulen kommen können:
Kommunikation
Organisation
Geschäft

Nicht einfach die letzten fünf Mails.

„Öffnen“ muss in den passenden Bereich springen:
Kommunikation, Organisation oder Geschäft

„Mit Kira besprechen“ muss den Vorgang mit richtigem Kontext an Kira übergeben:
Zusammenfassung
Status
relevante Daten
Anhänge, falls vorhanden
nächste Empfehlung

Die Priorisierung darf nicht zufällig wirken.
Claude soll sichtbar machen, warum ein Eintrag dort steht:
Dringlichkeit
Frist
Geldbezug
offene Entscheidung
manuelle Prüfung

6. Rechte Nebenarbeitszone
Ca. 30–35 Prozent Breite, vertikal in zwei Panels.

Rechts oben:
Nächste Termine & Fristen

Als kompakte Liste oder Mini-Timeline.

Jeder Eintrag:
Datum
Typ
Kontext
Kunde oder Bezug
Aktion

Funktionslogik
Klick auf einen Eintrag öffnet Organisation direkt am passenden Datensatz.

Aktionen dort:
Öffnen
Mit Kira besprechen
Frist bestätigen
Wiedervorlage setzen

Wenn Termine oder Fristen aus Mails erkannt wurden, soll das markiert sein:
aus Mail erkannt
manuell ergänzt

Rechts unten:
Geschäft aktuell

Inhalt:
letzte Zahlungen
kritische Rechnungen
Nachfass
offene Eingangsrechnungen
Skonto-Hinweise

Funktionslogik
Jeder Eintrag muss direkt in Geschäft zum passenden Unterbereich springen.

Beispiele:
kritische Rechnung → Ausgangsrechnungen / Detail
Skonto-Hinweis → Eingangsrechnungen / relevanter Datensatz
Nachfass → Angebote oder Kommunikation mit Nachfasskontext
ungeklärte Zahlung → Zahlungen / Prüfbedarf

Auch hier:
Nicht nur Text.
Echte Verknüpfung.

7. Unterer Bereich – Signale / Auffälligkeiten
Unter dem Hauptarbeitsbereich über volle Breite.

Das ist kein Aufgabenblock und keine Mailliste.

Hier stehen nur Ausreißer, Risiken und manuelle Prüfungen:
unklare Zahlung
alte offene Rechnung
Skonto läuft bald ab
Angebot seit X Tagen ohne Rückmeldung
widersprüchige Daten
manuelle Prüfung nötig

Funktionslogik
Jeder Eintrag ist anklickbar und öffnet den betroffenen Fall direkt.

Zusätzlich sinnvolle Aktionen:
Fall öffnen
Mit Kira besprechen
als geprüft markieren
zurückstellen
zur passenden Modulansicht springen

Wichtig:
Diese Auffälligkeiten müssen aus echten Regeln / Daten kommen.
Nicht aus bloßer Keyword-Suche.
Und sie dürfen sich nicht doppelt in allen Bereichen wiederholen.

8. Was auf dem Dashboard ausdrücklich nicht mehr erscheinen darf
Keine langen Maillisten
Keine Massenansicht von Kommunikation
Keine winzigen Karten ohne Hierarchie
Keine schmale Mittelspalte
Keine blassen Mini-Texte
Keine unklaren Deko-Zahlen
Keine Bereiche ohne Aktion
Keine Kira-Deko ohne funktionale Übergabe

9. Was auf dem Dashboard ausdrücklich sichtbar sein muss
Klare Hierarchie
große, gut lesbare Typografie
volle Breite sinnvoll genutzt
wenige, starke Bereiche
klickbare KPI-Karten
klare Trennung zwischen:
Kommunikation
Organisation
Geschäft
Auffälligkeiten

Sichtbare nächste Schritte
echte Sprunglogik
echte Kira-Übergaben

10. Kurzform als Text-Wireframe
Obere Leiste
Suche | Schnellaktionen | Status | Profil

Tagesbriefing
heute wichtig | kritische Punkte | Nachfass | Fristen | Geschäftssignale

KPI-Raster
Antworten nötig | Neue Leads | Angebotsrückmeldungen | Termine / Fristen | Offenes Rechnungsvolumen | Eingangsrechnungen offen | Nachfass fällig | Gesamt offen

Arbeitsbereich
links: Heute priorisiert
rechts oben: Nächste Termine & Fristen
rechts unten: Geschäft aktuell

Unterer Bereich
Signale / Auffälligkeiten

11. Verbindliche Funktionsregel für Claude
Beim Dashboard reicht es nicht, die Struktur zu zeichnen.

Claude muss die Funktionen dazu korrekt setzen:

Suche funktioniert
KPI-Karten filtern und springen wirklich
Briefing-Punkte öffnen echte Kontexte
„Heute priorisiert“ ist kuratiert und nicht nur Maildump
„Öffnen“ führt in das richtige Modul
„Mit Kira besprechen“ übergibt echten Kontext
Termine / Fristen sind echte Datensätze
Geschäft aktuell greift auf echte Geschäftsdaten
Signale / Auffälligkeiten öffnen echte Fälle
keine Deko-Interaktion
keine Fake-Buttons

