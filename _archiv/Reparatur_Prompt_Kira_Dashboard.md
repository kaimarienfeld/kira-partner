# Reparatur-Prompt – Kira Dashboard / Localhost

Bitte repariere das bestehende Projekt jetzt gezielt auf Basis meines Feedbacks.  
Wichtig: Nicht noch einmal oberflächlich umbauen. Nicht nur optisch etwas verschieben.  
Die jetzige Überarbeitung ist nur teilweise erledigt. Mehrere Kernpunkte wurden ignoriert oder falsch umgesetzt.

Du sollst **explizit auf dem bereits Gebauten aufbauen**, aber fehlerhafte Eigeninterpretationen zurückbauen und die Logik sauber neu aufsetzen.

## 1. Arbeitsweise ab jetzt

Arbeite strikt in dieser Reihenfolge:

1. Bestehendes Projekt und bisherige Änderungen prüfen  
2. Eigene angelegte Datenbanken, Klassifizierungen und gecachten Ergebnisse prüfen  
3. Alles, was auf alter oder falscher Logik basiert, bereinigen oder neu aufbauen  
4. Danach **mit den Regeln aus meinen drei Prompt-Dateien neu klassifizieren und neu aufbauen**  
5. Erst dann UI, Filter, Karten, Kira-Funktionen und Geschäftsbereich fertigstellen  
6. Danach testen  
7. Danach speichern  
8. Danach committen

Wichtig:
- Nichts überspringen
- Nicht wieder zuerst an der Oberfläche arbeiten und die Logik ignorieren
- Nicht nur grafisch „fertig aussehen lassen“
- Wenn bisher falsch aufgebaute Datenbanken oder Klassifizierungen die neue Logik blockieren, dann diese **zurücksetzen, leeren oder neu erzeugen**
- Lieber einmal sauber neu aufbauen als den alten Fehlerbestand weiterzuschleppen

## 2. Wichtigster Fehler: Das schlaue Lesen funktioniert nicht

Der größte Fehler ist aktuell, dass die Mail-Einordnung weiterhin fast so falsch ist wie vorher.

Beispiele aus „Antwort ausstehend 26“ zeigen klar:
- Anthropic-Receipt wurde als antwortwürdig eingestuft
- Figma-Newsletter wurde als antwortwürdig eingestuft
- Stripo Account Deletion wurde als Bestandskunde / Interessent behandelt
- Nordic Fire Händlernewsletter wurde als antwortwürdig behandelt
- Ecwid Login-Link / Warenkorb / Business-Tarif wurde als antwortwürdig behandelt
- AVG / OBSBOT / Descript / Microsoft / Vevor / AnswerThePublic wurden falsch einsortiert
- Rechnungen / Belege / Reminder / Shop-Systemmails / Newsletter werden nicht sauber getrennt

Das ist fachlich falsch.

Du sollst deshalb die Mail-Einordnung **nicht nur anhand von Betreff oder grober Rolle** machen, sondern sauber anhand von:
- Absender-Typ
- Inhalt
- Thread-Verlauf
- Anhängen
- Rechnung/Beleg/Shop/System-Kontext
- offener Frage ja/nein
- echter Handlungsbedarf ja/nein

Wenn die bestehende Einordnung auf alter Logik beruht, dann:
- bestehende abgeleitete Mail-Klassifizierungen neu aufbauen
- eigene Index-/Klassifizierungs-DBs prüfen
- falsche Klassifizierungsdaten leeren oder neu erzeugen
- danach komplette Mailbewertung neu rechnen

## 3. Dashboard ist noch kein echtes Dashboard

Das jetzige Dashboard ist im Kern weiter nur Mail.
Genau das war nicht das Ziel.

So soll es repariert werden:

### Dashboard
Dashboard ist die Hauptseite mit echter Übersicht.
Dort keine endlosen Maillisten als Hauptinhalt.

Dashboard soll enthalten:
- Antworten nötig
- neue Leads
- Termine / Fristen
- Wiedervorlagen
- Rechnungen / Belege
- Zahlungen
- wichtige Hinweise
- auffällige Dinge
- grafische / informative Übersichten, wo sinnvoll

Mail-Listen gehören primär in Kommunikation, nicht auf die Dashboard-Hauptseite.

### Filter-Kopf / Kennzahlen
Die Kennzahlen oben sind aktuell nur grafisch dargestellt.
Das reicht nicht.

Sie müssen klickbar sein.
Beispiel:
- Klick auf „5 neue Leads“ → filtert direkt nur diese
- Klick auf „26 Antworten nötig“ → zeigt nur diese
- Klick auf Zahlungen / Rechnungen → springt in passende gefilterte Ansicht

## 4. Kommunikation muss wirklich neu gelesen werden

Der Reiter Kommunikation zeigt aktuell weiterhin viele falsche Ergebnisse.

Das muss repariert werden durch:
- komplette Neubewertung der vorhandenen Maildaten
- neue Trennung zwischen:
  - Antwort erforderlich
  - neue Leads
  - Kundenantworten
  - Shop / System
  - Newsletter / Werbung
  - Rechnung / Beleg
  - zur Kenntnis
  - ignorieren
  - abgeschlossen

Zusätzlich:
- Thread-Verlauf besser auswerten
- prüfen, ob schon beantwortet
- prüfen, ob Kunde nur bedankt / bestätigt / absagt / verschiebt
- prüfen, ob überhaupt noch eine neue Frage offen ist

## 5. Organisation darf nicht leer sein

Der Reiter Organisation ist aktuell leer.
Das ist nicht plausibel und deutet darauf hin, dass Termine / Rückrufe / Fristen nicht sauber gelesen wurden.

Du sollst Organisation gezielt aufbauen mit:
- erkannte Termine aus Mails
- Rückrufbitten
- Fristen
- Wiedervorlagen
- Besprechungsvorbereitung

Dafür müssen Mails nicht nur grob klassifiziert, sondern auf:
- Datum
- Uhrzeit
- Rückrufbitte
- „bitte melden“
- „Termin verschieben“
- „rufen Sie mich an“
- Frist / Deadline
- Kalenderbezug
geprüft werden.

Wenn dafür neue Tabellen / Datenbanken nötig sind, baue sie.

## 6. Geschäft muss sinnvoll werden, nicht stumpf aus Mail-Betreff

Der Reiter Geschäft ist aktuell nicht brauchbar.
Dort wurden nur stumpf Mails gezogen, in denen irgendwo „Rechnung“ vorkommt.
Das ist keine sinnvolle geschäftliche Übersicht.

Geschäft soll stattdessen sauber aufgebaut werden als eigener Bereich mit echter Auswertung.

### Geschäft soll enthalten:
- Ausgangsrechnungen
- Eingangsrechnungen
- Zahlungen
- offene / aktuelle Belege
- aktuelle Geschäftsvorgänge
- grafische und informative Übersicht, wo sinnvoll
- aktuelle Monats- / Jahreswerte, wenn aus Daten ableitbar
- keine Vermischung alter Threads nur wegen alter Anhänge

### Ganz wichtig:
Wenn in einem März-Thread im Anhang eine Rechnung aus dem Vorjahr hängt, dann zählt nicht stumpf der Mail-Zeitstempel.
Es müssen geprüft werden:
- Zeitstempel der Mail
- Dokumenttyp
- Rechnungsdatum im Anhang
- ob es wirklich eine aktuelle Rechnung ist oder nur Alt-Anhang in altem Thread

Wenn möglich, sollst du beim ersten sauberen Lauf Verknüpfungen / strukturierte Geschäftsdatenbanken aufbauen, damit spätere Auswertungen belastbar werden.

Lieber zuerst saubere Datenbasis bauen als mir später wieder unbrauchbare Listen zu zeigen.

## 7. Sinnvolle Maße / Struktur für „Geschäft“

Bitte baue „Geschäft“ nicht als Mailsammlung, sondern als geschäftliche Übersicht mit sinnvollen Bereichen, z. B.:

- Übersicht
  - Eingangsrechnungen aktuell
  - Ausgangsrechnungen aktuell
  - Zahlungen
  - offene / ungeprüfte Belege
  - letzte Auffälligkeiten

- Rechnungen
  - strukturierte Liste mit Rechnungsdatum, Betrag, Typ, Status, Gegenpartei
  - Filter: Eingang / Ausgang / offen / bezahlt / unklar

- Zahlungen
  - Zahlungen, Rückzahlungen, Abbuchungen, Abo-Zahlungen
  - sinnvoll getrennt von Rechnungen

- Auswertung
  - Summen pro Monat / Jahr
  - Entwicklung, sofern Daten sauber genug
  - nur wenn belastbar, sonst klar als unvollständig markieren

- Prüfbedarf
  - unklare Belege
  - doppelte oder widersprüchliche Zuordnungen
  - alte Anhänge in neuen Threads
  - Rechnungsdatum unklar

## 8. Wissen ist zu passiv und nicht steuerbar

Im Reiter Wissen steht aktuell einfach nur Inhalt.
Ich habe dort kaum Einfluss.

Das soll verbessert werden.

Wissen soll gegliedert und steuerbar sein:
- Stil & Tonalität
- Preislogik
- Assistenzplan
- Lernvorschläge
- neue Regeln in Prüfung
- manuell bestätigte Regeln

Ich möchte dort nicht nur Text sehen, sondern nachvollziehen können:
- was feste Regel ist
- was gelernt wurde
- was vorgeschlagen wurde
- was ich freigeben oder korrigieren kann

## 9. Kira ist aktuell fast ohne Funktion

Die Kira-Sidebar ist zwar sichtbar, aber funktional nur teilweise umgesetzt.

Aktuelle Probleme:
- tote Links / Buttons
- Chat nicht integriert
- Aufgaben wiederholen nur Mail-Inhalte
- Wissen in Kira wiederholt nur vorhandenen Inhalt
- keine echte Interaktion
- Kommunikationsfenster nicht sinnvoll

Das muss repariert werden.

### Kira soll funktional werden:
- Home: echte Übersicht
- Chat: echter eingebauter Chat / Kommunikationsbereich
- Aufgaben: nicht nur Wiederholung der Mail-Liste
- Wissen: sinnvoller Zugriff, nicht bloß Dublette
- Ideen / Vorschläge: echte Lern- und Verbesserungsvorschläge

### Kommunikationsfenster
Bei „Mit Kira besprechen“ muss wirklich ein Vorgangsfenster aufgehen, in dem:
- Vorgangszusammenfassung steht
- meine Gedanken eingetragen werden können
- darauf basierend Entwurf / Antwort / Rückfrage / Notiz erzeugt werden kann

Kein toter Platzhalter. Kein halbfertiger Reiter.

## 10. Explizite Reparatur der Datenbasis

Prüfe ausdrücklich, ob die aktuell verwendeten internen Datenbanken oder abgeleiteten Datenspeicher bereits mit falscher Logik befüllt wurden.

Wenn ja:
- dokumentieren, was davon falsch ist
- entscheiden, was geleert / neu aufgebaut werden muss
- danach mit den aktuellen Prompt-Regeln sauber neu aufbauen

Besonders prüfen:
- eigene Klassifizierungs-DBs
- Leads-Daten
- Aufgabenlisten
- Rechnungs-/Geschäfts-DBs
- Wiedervorlagen / Organisationsdaten
- Kira-Kontextdaten

Wenn nötig:
- neu indizieren
- neu klassifizieren
- neu verknüpfen

## 11. HTML-/Localhost-Lösung zuerst sauber reparieren

Bleibe zuerst in der bestehenden HTML-/Localhost-Lösung.
Nicht sofort auf eine andere App springen.

Aber:
Wenn etwas innerhalb der bestehenden Struktur nicht sauber und flüssig umsetzbar ist, dann:
- klar benennen, wo die Grenze ist
- begründen, warum es technisch hakt
- erst dann eine bessere technische Lösung vorschlagen

Keine halbgaren Fake-Funktionen mehr bauen.

## 12. Konkrete Reparatur-Reihenfolge

Arbeite jetzt in genau dieser Reihenfolge:

1. Bestand und bisherige Änderungen lesen  
2. Prüfen, welche DBs / gespeicherten Klassifizierungen bereits falsch aufgebaut wurden  
3. Falsche oder alte Einordnungsdaten bereinigen / leeren / neu aufsetzen  
4. Mailklassifizierung neu und strikt nach den aktuellen Regeln aufbauen  
5. Dashboard-Hauptseite wirklich als Dashboard umbauen  
6. Kommunikation neu filtern und korrekt aufbauen  
7. Organisation aus Mails / Threads / Fristen / Rückrufen sauber extrahieren  
8. Geschäft mit sinnvoller Datenbasis und echter Übersicht neu aufbauen  
9. Wissen steuerbar und nachvollziehbar machen  
10. Kira-Sidebar wirklich funktional machen  
11. Kommunikationsfenster und Chat integrieren  
12. Filter, Kennzahlen und Klicklogik funktionsfähig machen  
13. Alles testen  
14. Speichern  
15. Committen

## 13. Zusätzliche Regel

Wenn du an einem Punkt merkst, dass du meine Anweisung nicht umgesetzt hast oder etwas nur halb gebaut wurde:
- nicht drüber hinweggehen
- nicht kosmetisch kaschieren
- explizit reparieren

## 14. Ziel

Ziel ist nicht, dass es „ungefähr anders aussieht“.

Ziel ist:
- wirklich bessere Einordnung
- wirklich funktionales Dashboard
- wirklich funktionierende Kira
- wirklich sinnvolle Geschäftsübersicht
- wirklich nutzbare Kommunikation
- wirklich belastbare Datenbasis

Wenn du dafür Teile neu berechnen oder Datenbanken neu aufbauen musst, dann tu das.
Lieber einmal richtig als weiter halbfertig.
