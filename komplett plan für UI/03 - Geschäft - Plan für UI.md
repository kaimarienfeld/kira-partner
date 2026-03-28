03 - Geschäft - Plan für UI





Claude soll „Geschäft“ nicht nur anders anordnen, sondern die Funktionen dazu auch wirklich richtig setzen.



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

Nicht nur schöner machen. Die Datenlogik, Filter, Datensatzöffnungen, Verknüpfungen, Warnungen und Kira-Aktionen müssen auch funktional korrekt gesetzt werden.ungen, Verknüpfungen, Warnungen und Kira-Aktionen müssen auch funktional korrekt gesetzt werden.

