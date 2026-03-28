02 - Kommunikation - Plan für UI

Claude soll „Kommunikation“ nicht nur neu anordnen, sondern die Funktionen dazu auch wirklich richtig setzen.

So sollte die Seite aufgebaut sein:

Ganz oben eine Modul-Kopfzeile über volle Breite.
Links Titel „Kommunikation“ plus kurze Statuszeile, zum Beispiel:
26 offen, 5 neue Leads, 3 Angebotsrückmeldungen, 2 manuelle Prüfungen.
Rechts die wichtigsten Aktionen:
Suche
Filter öffnen
Ansicht wechseln
Sammelaktion
Neue Notiz / manuelle Aufgabe

Darunter eine echte Segmentnavigation, nicht nur lose Buttons:
Antwort erforderlich
Neue Leads
Angebotsrückmeldungen
Zur Kenntnis
Newsletter / System
Abgeschlossen

Wichtig:
Diese Tabs müssen funktional sein.
Nicht nur optisch aktiv.
Jeder Tab filtert die Datenbasis wirklich neu.
Die Zahlen an den Tabs müssen live mitlaufen.

Darunter eine starke Filterleiste.
Nicht versteckt und nicht mini.
Sichtbar, lesbar, mehr wie in guter Software.

Filter:
offene Frage
mit Termin
mit Fotos
mit Anhängen
Kunde
Projektart
Quelle
Dringlichkeit
bereits beantwortet
manuelle Prüfung
nur mit Kira-Kontext

Wichtig:
Diese Filter müssen kombinierbar funktionieren.
Also nicht nur optisch anklickbar.
Wenn „mit Fotos“ und „Neue Leads“ aktiv ist, müssen wirklich nur diese Fälle erscheinen.
Wenn „bereits beantwortet“ aktiv ist, muss der Threadstatus berücksichtigt werden.

Darunter die Hauptfläche in zwei Zonen.

Links die Arbeitsliste mit ca. 55 bis 60 Prozent Breite.
Rechts die Kontext-/Vorschaufläche mit ca. 40 bis 45 Prozent Breite.

Links in der Arbeitsliste:
Keine winzigen Karten.
Keine stumpfe Mailansicht.
Sondern klare, gut lesbare Listeneinträge oder breite Kartenzeilen.

Jeder Eintrag zeigt:
Titel
Ein-Satz-Zusammenfassung
Grund der Einordnung
Absenderrolle
Zeitstempel
wichtige Marker wie:
Frage
Termin
Foto
Anhang
Rechnung
System
Dringlichkeit
und die empfohlene nächste Aktion

Unten oder rechts am Eintrag nur wenige starke Aktionen:
Öffnen
Mit Kira besprechen
Status ändern
Korrektur

Nicht mehr.

Wichtig:
Claude soll hier die Funktionen richtig setzen.
Das heißt konkret:
„Öffnen“ lädt wirklich die Detailansicht des Threads.
„Mit Kira besprechen“ öffnet wirklich den Kira-Vorgangskontext.
„Status ändern“ schreibt wirklich in die Daten.
„Korrektur“ öffnet wirklich Kategorie-/Hinweisfunktion.
Keine Fake-Buttons.

Rechts die Kontextfläche.
Diese Fläche darf nicht wieder ein schmaler schlechter Mailkasten sein.
Sie ist die Vorschau- und Arbeitsfläche für den aktuell ausgewählten Vorgang.

Standardmäßig zeigt sie:
große Kurz-Zusammenfassung
aktuellen Status
warum eingeordnet
was offen ist
was schon beantwortet wurde
empfohlene nächste Aktion
Anhänge
Threadverlauf kurz

Und darunter direkte Aktionen:
Mit Kira besprechen
Mail vollständig lesen
Anhänge öffnen
Wiedervorlage setzen
als erledigt markieren
Kategorie korrigieren

Wichtig:
Auch hier müssen die Funktionen wirklich arbeiten.
Also:
„Mail vollständig lesen“ muss ein echtes, gut lesbares Detailfenster öffnen.
„Anhänge öffnen“ muss Anhänge laden.
„Wiedervorlage“ muss speichern.
„Kategorie korrigieren“ muss die Einordnung neu setzen und Lernsignal ablegen, wenn vorgesehen.

Für die Mail-/Thread-Detailansicht selbst:
Claude soll sie bewusst neu bauen.
Nicht wieder schmal, blass und mini.

Sie muss:
deutlich breiter sein
große Typografie haben
gute Zeilenhöhe
klare Struktur zwischen Mailkopf, Inhalt, Anhängen, Threadverlauf
und direkte Folgeaktionen

Dort müssen Funktionen direkt möglich sein:
Mit Kira besprechen
Kontext an Kira anhängen
Anhänge an Kira übergeben
Status ändern
Notiz hinzufügen
Wiedervorlage setzen
Korrektur senden

Das ist wichtig:
Kommunikation ist nicht nur Lesen, sondern Bearbeiten.

Zusätzlich sollte Kommunikation zwei Ansichtsmodi bekommen:

Listenmodus
für viele Vorgänge, klar und dicht

Fokusmodus
für tieferes Bearbeiten eines Vorgangs mit größerem Detailbereich

Auch diese Umschaltung muss funktional sein.
Nicht nur UI-Spielerei.

Was ich auf dieser Seite ausdrücklich nicht mehr will:
Mailkarten ohne Handlung
zu kleine Schrift
zu schmale Lesebereiche
optische Filter ohne echte Funktion
Buttons, die nichts tun
Kira nur als Deko-Abkürzung
gleichförmige Kachelwüste

Was ich stattdessen will:
echte Arbeitsliste
starke Filter
breites Lesefenster
klare nächste Schritte
echte Kira-Anbindung
echte Statuslogik
echte Korrektur

Der Grundsatz für Claude sollte hier sein:

Kommunikation ist ein Entscheidungs- und Bearbeitungsmodul.
Es soll nicht nur zeigen, welche Mails da sind.
Es soll lesbar machen, worum es geht, warum es wichtig ist und was als nächstes getan werden kann.
Und jede sichtbare Hauptaktion muss technisch wirklich funktionieren.

Wenn ich das als kurzes Text-Wireframe zusammenfasse:

Kopfzeile
Titel | offene Zahlen | Suche | Filter | Aktionen

Segmentnavigation
Antwort erforderlich | Neue Leads | Angebotsrückmeldungen | Zur Kenntnis | Newsletter/System | Abgeschlossen

Filterleiste
offene Frage | Termin | Fotos | Anhänge | Quelle | Kunde | Projektart | Dringlichkeit | beantwortet | manuelle Prüfung

Hauptbereich
links: Arbeitsliste
rechts: Kontext-/Vorschaufläche

Detailansicht bei Öffnen
großes Lesefenster mit Thread, Anhängen und Aktionen

Kira-Anbindung
„Mit Kira besprechen“ öffnet echten Vorgangskontext und übernimmt Mail + Thread + Marker

Und nochmal ausdrücklich für Claude:
Nicht nur Layout umbauen. Die Filter, Tabs, Statuswechsel, Korrekturen, Mail-Öffnung, Anhänge und Kira-Verknüpfung müssen auch funktional korrekt gesetzt werden.