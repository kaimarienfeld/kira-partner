05 - Kira-Workspace - Plan für UI

Claude muss Kira als eigenen Workspace denken und die Funktionen dazu auch wirklich korrekt setzen.

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
Voiceover
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