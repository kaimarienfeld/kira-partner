# Prompt 02 – Kira Dashboard, Kommunikationsfenster & UI-Logik

DU BIST:
Der UI- und Ablauf-Controller für das rauMKult-Dashboard mit Kira – der rauMKult Assistenz.

Deine Aufgabe ist es, das bestehende Dashboard über die vorhandene Localhost-Struktur weiterzuentwickeln, ohne das Projekt unnötig umzubauen oder parallel neue Oberflächen zu erfinden.
Du arbeitest auf dem vorhandenen Grundgerüst und baust die HTML-/Localhost-Lösung so aus, dass sie benutzerfreundlich, übersichtlich, schnell und für den Alltag von Kai wirklich nutzbar ist.

## 1. Technische Grundregel

Nutze das bestehende Localhost-Dashboard als Basis.
Behandle den aktuellen Startweg als vorhandenes Grundgerüst.
Ersetze nichts blind durch eine neue Desktop-App, solange die Web-/Localhost-Lösung sauber und flüssig umgesetzt werden kann.

Bevor du UI oder Logik änderst, prüfe:
- wie das Dashboard aktuell gestartet wird
- welche Struktur bereits vorhanden ist
- welche HTML-, CSS-, JS- oder sonstigen Komponenten schon existieren
- wo Kira, Kommunikationsfenster und neue Statuslogik sauber integriert werden können
- welche Interaktionen bereits gespeichert werden
- wie bestehende Aktionen aktuell verarbeitet werden

Wenn eine Funktion innerhalb der bestehenden Localhost-Lösung sauber umsetzbar ist, bevorzuge diese Variante.

## 2. Bezug zum bestehenden Projekt

Das bestehende Dashboard läuft aktuell lokal über den vorhandenen Startweg.
Behandle diese Struktur als bestehendes Grundgerüst, das weiterentwickelt werden soll.

Berücksichtige dabei, dass die bisherige Nutzung über den lokalen Dashboard-Start läuft, damit Eingaben, Statusänderungen, Korrekturen und die Interaktion mit Kira direkt im Projekt gespeichert und weiterverarbeitet werden können.

Wenn Bot, Chat, Kommunikationsfenster und Vorgangskontexte innerhalb dieser Struktur stabil und flüssig laufen, ist diese Lösung zu bevorzugen.

Erst wenn sich die HTML-/Localhost-Variante technisch als zu unsauber, zu instabil oder zu begrenzt herausstellt, darf eine Desktop-Web-App als zweite Option vorgeschlagen werden.

## 3. Ziel der Oberfläche

Das Dashboard soll nicht wie eine einfache Mailliste wirken.
Es soll eine klare Arbeitsoberfläche für Kai sein.

Wichtig:
- schnelle Übersicht
- wenig visuelles Chaos
- klare Prioritäten
- kein unnötiges Springen
- kein Seitenreload bei jeder Kleinigkeit
- Kontext bleibt offen
- Vorgänge direkt bearbeitbar
- Korrekturen sofort speicherbar
- Kommunikation mit Kira direkt in der Oberfläche

## 4. Aufbau der Oberfläche

Die Hauptnavigation soll logisch und übersichtlich aufgebaut sein:

- Dashboard
- Kommunikation
- Organisation
- Geschäft
- Wissen

Dashboard ist die Startseite.
Dort nur das Wichtigste:
- Heute wichtig
- Antworten nötig
- neue Leads
- Termine / Fristen
- Wiedervorlagen
- Rechnungen / Belege
- Hinweise / Auffälligkeiten

Kommunikation enthält:
- Antwort erforderlich
- neue Leads
- Wiedervorlagen
- zur Kenntnis
- ignoriert / abgeschlossen

Organisation enthält:
- Termine
- Rückrufe
- Fristen
- Follow-ups
- Besprechungsvorbereitung

Geschäft enthält:
- Rechnungen
- Belege
- Zahlungsstatus
- Umsatzsicht
- kaufmännische Hinweise

Wissen enthält:
- feste Regeln
- gelernte Muster
- Formulierungen
- Vorschläge
- gespeicherte Notizen / Erfahrungswerte

## 5. Kira als schwebende Assistenz

Kira sitzt unten rechts als schwebender Assistenz-Einstieg.
Nicht als starre Kachel im Raster.

Klick auf Kira öffnet rechts ein Panel oder Drawer.
Dieses Panel bleibt in der Oberfläche und darf möglichst ohne Unterbrechung nutzbar sein.

Kira-Bereiche:
- Home
- Nachrichten
- Aufgaben
- Wissen
- Vorschläge

Home zeigt:
- Heute wichtig
- offene Rückfragen
- neue Leads
- Rechnungen / Belege
- Wiedervorlagen
- Lernvorschläge

Nachrichten:
- direkter Chat mit Kira
- laufender Kontext je Vorgang
- keine neue Seite
- kein Kontextverlust

Aufgaben:
- aktuelle Aufgaben
- Fehlzuordnungen
- Follow-ups
- Wiedervorlagen

Wissen:
- feste Regeln
- gelernte Muster
- Formulierungen
- Preislogiken
- Projektwissen

Vorschläge:
- neue Regeln
- neue Textbausteine
- Optimierungen
- erkannte Muster

## 6. Kommunikationsfenster pro Vorgang

Bei antwortwürdigen Vorgängen darf der Hauptbutton nicht „Entwurf ansehen“ heißen.
Stattdessen:
- Mit Kira besprechen

Dieser Button öffnet direkt das Kommunikationsfenster für genau diesen Vorgang.

Das Kommunikationsfenster zeigt zuerst:
- Kurz-Zusammenfassung
- Einschätzung
- fehlende Infos
- Risiken / Hinweise
- empfohlene nächste Richtung

Darunter Eingabefeld für Kai:
- Gedanken
- Notizen
- gewünschte Richtung
- was betont werden soll
- was vermieden werden soll
- Rückfrage / Termin / Absage / Einordnung / Entwurf

Erst nach Kais Input erzeugt Kira:
- Antwortentwurf
- Rückfrage
- Zusammenfassung
- Protokoll
- Angebotsskizze
- interne Notiz

Das Kommunikationsfenster muss kontextbezogen bleiben.
Wenn Kai denselben Vorgang erneut öffnet, soll der bisherige Verlauf sichtbar sein.

## 7. Kartenlogik

Jede Mail- oder Aufgabenkarte zeigt mindestens:

- Status
- Ein-Satz-Zusammenfassung
- bereinigten Titel
- Absenderrolle
- Begründung der Einordnung
- empfohlene nächste Aktion
- erkannte Inhalte:
  - Termin
  - Frist
  - Ort
  - Leistung
  - Anhänge
  - Budgethinweise
  - offene Frage ja/nein

Nicht nur Betreff anzeigen.
Nicht nur eine knappe Zeile ohne Kontext.
Kai muss auf einen Blick verstehen:
- worum es geht
- warum es relevant ist
- was jetzt zu tun ist

## 8. Statusfelder

Verbindliche Statuswerte:
- Antwort erforderlich
- Neue Lead-Anfrage
- Angebotsrückmeldung
- Termin / Frist
- Wiedervorlage
- Rechnung / Beleg
- Shop / System
- Newsletter / Werbung
- Zur Kenntnis
- Abgeschlossen
- Ignorieren

Zusätzlich:
- Priorität
- letzte Aktivität
- nächster Schritt
- Antwort nötig ja/nein

## 9. Aktionen auf jeder Karte

Jede Karte soll direkt bedienbar sein mit:
- Mit Kira besprechen
- Erledigt
- Später
- Ignorieren
- Falsch zugeordnet
- Kategorie ändern
- Als Regel merken
- Notiz an Assistenz

Wenn Kai etwas ändert:
- sofort im Projekt speichern
- aktuelle Karte direkt neu einsortieren
- Grund optional mitloggen
- als Lernsignal speichern, wenn passend

## 10. Benutzerfreundlichkeit

Die Oberfläche soll ruhig und klar wirken.
Vermeide:
- überladene Listen
- zu viele gleich starke Farben
- zu viele Buttons ohne Hierarchie
- mehrfache Navigation für dieselbe Sache
- neue Fenster oder Tabs für Standardaktionen
- harte Reloads bei jeder Aktion

Bevorzuge:
- klare visuelle Hierarchie
- kompakte Karten
- ausklappbare Details
- rechtsseitige Panel-Logik
- saubere Statusfarben
- persistente Kontexte
- flüssige Bedienung

## 11. Localhost-taugliche Umsetzung

Baue die Lösung so, dass sie innerhalb des bestehenden Localhost-Setups sauber läuft.
Nicht auf eine externe SaaS-Oberfläche ausweichen.
Nicht auf einen unnötig schweren Umbau springen.

Wenn Bot, Chat, Kartenaktionen und Kommunikationsfenster innerhalb der bestehenden HTML-/JS-/Localhost-Struktur sauber funktionieren, ist diese Variante zu bevorzugen.

Wenn für flüssige Interaktion nötig:
- zustandsbasierte UI verwenden
- Panel-/Drawer-System statt Seitenwechsel
- lokale API oder Prozessbrücke sauber anbinden
- Verlauf pro Vorgang speichern
- UI-Aktionen asynchron verarbeiten

Wenn eine automatische Hintergrundanbindung an den Agenten sinnvoll ist, zuerst prüfen:
- ob das bestehende Projekt bereits dafür eine saubere Startlogik hat
- ob der Agent beim Dashboard-Start robust mitgestartet werden kann
- ob Eingaben und Antworten stabil ohne Unterbrechung verarbeitet werden

Nur wenn das mit der bestehenden Localhost-Lösung nicht sauber stabil umsetzbar ist, darf eine Desktop-Web-App als zweite Option vorgeschlagen werden.

## 12. Prüflogik vor Umsetzung

Vor jeder Änderung prüfen:
- was ist schon da
- was fehlt
- was ist doppelt
- was kann erweitert statt neu gebaut werden
- was muss erhalten bleiben
- wie wird gespeichert
- wo gehört Kira logisch hin
- wie bleibt die Oberfläche übersichtlich

Nach jedem größeren Schritt:
- speichern
- testen
- offene Punkte notieren
- erst dann nächsten Schritt angehen

Vor Commit:
- UI logisch
- keine Doppelwege
- Kommunikation mit Kira flüssig
- Karten verständlich
- Status korrekt
- Localhost-Ablauf stabil
- keine unnötigen Brüche im Bedienfluss

## 13. Ziel

Ziel ist eine HTML-/Localhost-Lösung, die Kai gern benutzt.
Nicht technisch irgendwie funktionierend.
Sondern:
- klar
- ruhig
- verständlich
- schnell
- direkt korrigierbar
- mit flüssiger Kommunikation zu Kira
- ohne unnötige Unterbrechungen
- sauber im bestehenden Projekt integriert
