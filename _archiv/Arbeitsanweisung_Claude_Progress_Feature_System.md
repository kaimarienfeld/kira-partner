# Arbeitsanweisung für Claude Code – Fortschritt, Handoff und Feature-System

Bitte setze sofort ein verbindliches Fortschritts-, Handoff- und Feature-System im Projekt auf.

## Ziel

Claude soll künftig nicht mehr versuchen, große UI- oder Feature-Umbauten in einem Schritt zu erledigen, dabei Kontext zu verlieren und halb fertige Ergebnisse zu hinterlassen.

Stattdessen soll ab jetzt jede Aufgabe über drei feste Ebenen laufen:

1. AGENT.md als dauerhafte Arbeitsregel, bestehende Regeln in anderen dateien dort migrieren und alte auslagern
2. JSON-basierte Feature-Listen für kleine abgeschlossene Arbeitseinheiten, bestehende andere listen in anderen dateien dort migrieren und alte auslagern
3. JSON-basierte Fortschritts- und Handoff-Dateien als Brücke zwischen Sessions in Kombination mit der git Historie

Dieses System gilt ab sofort für jede weitere Aufgabe im Projekt.

## Bestehende Lage im Projekt

Im Projekt ist bereits dokumentiert, dass Kira viel mehr als ein Mail-Dashboard ist: lokaler Server, Mail-Überwachung, Aufgabenverwaltung, Geschäftsmodul, Wissensspeicher, Einstellungen, Dokumentenscan, Kira-Chat, Historie, Tools, Provider-Verwaltung und mehrere Datenbanken. Außerdem gibt es bereits eine definierte Zielstruktur als Unternehmens-Cockpit mit Start, Kommunikation, Organisation, Geschäft, Wissen, Einstellungen sowie geplanten Modulen wie Kunden, Marketing, Social / DMs, Automationen und Analysen. Das bestehende System soll also nicht neu erfunden, sondern strukturiert weitergebaut werden. Siehe dazu auch die bestehende Memory-Datei im Projekt. \[CITATIONS]

Zusätzlich ist in UI-Plänen wie Kommunikation und Einstellungen bereits festgelegt, dass sichtbare Hauptaktionen, Filter, Provider-/Fallback-Logik, Design-Einstellungen und Verknüpfungen funktional korrekt gesetzt werden müssen und nicht nur optisch existieren dürfen. \[CITATIONS]

## 1\. Bestehendes prüfen, bevor neu angelegt wird

Bevor du neue Dateien anlegst, prüfe im Projektordner und insbesondere im Memory-Bereich, ob bereits ähnliche Dateien existieren. Sollten die angelegten Formate der Dateien/Inhalt, z.B. .json dateien für dich nicht korrekt sein, dann passe diese bitte so an, dass du uneingeschrängt damit arbeiten kannst und die datei seinen zweck erfüllt. vorhandenen inhalt übernimmst du dann in das neue format.

Suche mindestens nach:

* AGENT.md
* agent.md
* progress
* handoff
* session
* feature
* todo
* backlog
* roadmap
* implementation status
* ui status

Wenn bereits passende Dateien existieren:

* nicht blind überschreiben
* sinnvoll umstrukturieren
* in das neue System überführen
* alte Inhalte übernehmen, wenn noch relevant
* veraltete Inhalte klar als archiviert markieren

Wenn du keine passenden Dateien findest:

* lege die neuen Dateien nach den Vorgaben unten an

## 2\. Verbindliche neue Dateien

Lege – sofern noch nicht in sinnvoller Form vorhanden – diese Dateien an:

### A. AGENT.md

Ort:
Projektwurzel oder dort, wo Claude Code sie für das Projekt sicher berücksichtigt

Zweck:
Dauerhafte Arbeitsregel für Claude Code im gesamten Projekt

Inhalt:

* niemals alles auf einmal umbauen
* immer in kleine abgeschlossene Einheiten arbeiten
* zuerst vorhandene Referenzen, HTML-Vorschauen, Screenshots und UI-Pläne lesen
* bestehende Funktionen nicht löschen
* neue reale Funktionen nicht übersehen oder verwerfen
* UI-Referenzen haben Vorrang vor der alten UI
* wenn Funktion fehlt: UI vorbereiten + „In Planung“ oder Status markieren + Todo anlegen
* nach jedem Schritt Fortschritt in JSON-Dateien aktualisieren
* vor neuer Session zuerst Handoff und Progress lesen
* immer nur an der angeforderten Seite oder Einheit arbeiten, dann stoppen

### B. feature\_registry.json

Zweck:
Gesamtliste aller Features und Teilfeatures in sauberer, maschinenlesbarer Struktur

Wichtig:
Nicht als Markdown speichern.
JSON verwenden.

### C. session\_handoff.json

Zweck:
Brücke zwischen Sessions
Enthält aktuellen Arbeitsstand, offenen Punkt, nächste empfohlene Einheit, Blocker, Referenzen

### D. progress\_log.json

Zweck:
Fortschrittsverlauf
Welche Einheiten wurden wann abgeschlossen, geändert, verschoben oder vorbereitet

## 3\. JSON-Dateien sicher behandeln

JSON-Dateien dürfen nicht aus Versehen überschrieben werden.

Regeln:

* vor Änderungen einlesen
* strukturiert aktualisieren
* vorhandene Einträge erhalten
* keine Total-Neuschreibung ohne Migration
* wenn Struktur geändert werden muss, alte Inhalte migrieren
* bei Konflikten lieber erweitern statt zerstören
* nur Felder ändern, die wirklich angepasst werden müssen

Wenn bereits bestehende JSON- oder Statusdateien ähnlich genutzt werden:

* diese in das neue Schema überführen
* nicht einfach daneben ein zweites System aufmachen

## 4\. Feature-System – Pflichtlogik

Jede neue Arbeit wird künftig in kleine abgeschlossene Einheiten zerlegt.

Beispiel:
Nicht „Geschäft komplett umbauen“,
sondern:

* shell übernehmen
* Kopfzeile umsetzen
* Untertabs umsetzen
* KPI-Zone umsetzen
* Warnungsbereich umsetzen
* Datensatzansicht anschließen
* Kira-Aktionen anschließen
* Test und Review

Jede Einheit im feature\_registry.json braucht mindestens:

* id
* modul
* titel
* beschreibung
* status
* prioritaet
* depends\_on
* ui\_reference\_files
* current\_system\_files
* todo\_notes
* implementation\_scope
* acceptance\_criteria
* last\_updated

Statuswerte:

* planned
* in\_progress
* blocked
* ready\_for\_review
* done
* archived

## 5\. Session-Handoff – Pflichtlogik

Vor jeder neuen Aufgabe:

* session\_handoff.json lesen
* feature\_registry.json lesen
* relevante Referenzdateien lesen
* erst dann arbeiten

Nach jeder Aufgabe:

* session\_handoff.json aktualisieren
* progress\_log.json ergänzen
* betroffene Feature-Status im feature\_registry.json aktualisieren

session\_handoff.json soll mindestens enthalten:

* current\_focus
* current\_feature\_id
* what\_was\_done
* what\_is\_not\_done
* blockers
* required\_references
* next\_recommended\_step
* warnings
* updated\_at

## 6\. Bezug auf UI-Referenzen und bestehende Funktionen

Bei allen zukünftigen UI-Aufgaben gilt:

* die Dateien im Ordner „komplett plan für UI“ sind bindend
* pro Seite nur die jeweilige Nummern-Datei fachlich verwenden
* bereits umgesetzte neuere visuelle Entscheidungen aus vorherigen Seiten übernehmen
* neue reale Funktionen aus dem Systemstand dürfen nicht verloren gehen
* wenn Referenz-UI etwas zeigt, was funktional noch fehlt:

  * UI trotzdem anlegen
  * als „In Planung“ oder vorbereitet markieren
  * Feature-Eintrag dazu anlegen

## 7\. Sofort umzusetzende Schritte

Bitte jetzt in genau dieser Reihenfolge arbeiten:

1. Im Projekt und im Memory-Bereich nach bestehenden AGENT-, Progress-, Feature- und Handoff-Dateien suchen
2. Prüfen, welche davon übernommen oder umstrukturiert werden müssen
3. Falls keine passende AGENT-Datei existiert, AGENT.md anlegen
4. feature\_registry.json anlegen oder vorhandene Feature-Datei sauber migrieren
5. session\_handoff.json anlegen oder vorhandene Handoff-Datei sauber migrieren
6. progress\_log.json anlegen oder vorhandene Fortschrittsdatei sauber migrieren
7. Bereits bekannte große Aufgaben in kleine abgeschlossene Features zerlegen
8. Bestehende UI- und Umbauarbeiten für Dashboard, Kommunikation, Geschäft, Wissen, Kira Workspace, Einstellungen als erste strukturierte Feature-Gruppen eintragen
9. Danach kurz dokumentieren:

   * welche Dateien neu angelegt wurden
   * welche Dateien umstrukturiert wurden
   * welche alten Dateien übernommen wurden
   * welches Schema jetzt verbindlich gilt

## 8\. Wichtige Arbeitsregel ab jetzt

Dieses System gilt ab sofort für jede Aufgabe.

Das heißt:

* keine großen Umbauten ohne Feature-Zerlegung
* keine neue Session ohne Handoff-Lesen
* keine halben Zwischenstände ohne Progress-Update
* keine UI-Änderung ohne Referenzbezug
* keine bestehenden Funktionen verlieren
* keine neuen echten Funktionen weglassen, nur weil sie in einer älteren UI-Referenz noch nicht standen

