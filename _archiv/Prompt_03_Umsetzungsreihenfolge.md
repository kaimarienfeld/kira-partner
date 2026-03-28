# Prompt 03 – Umsetzungsreihenfolge für Claude

Diese Datei regelt nicht die inhaltlichen Regeln des Systems, sondern nur die saubere Reihenfolge der Überarbeitung.

Nutze zusätzlich:
- Prompt_01_Kira_Systemprompt.md
- Prompt_02_Kira_Dashboard_UI.md

## Ziel

Das bestehende Projekt soll sauber weiterentwickelt werden, ohne chaotische Umbauten, Doppelstrukturen oder übereilte Neuentwicklung.
Es soll zuerst die bestehende HTML-/Localhost-Lösung verbessert werden.
Erst wenn diese Variante technisch nachweisbar nicht sauber genug umsetzbar ist, darf eine Desktop-Web-App als zweite Option vorgeschlagen werden.

## Verbindliche Reihenfolge

### 1. Bestand prüfen
- vorhandene Projektstruktur lesen
- vorhandene Module, Dateien, Komponenten und Datenflüsse erfassen
- vorhandene Maillogik, Dashboardlogik, Speicherorte und Startlogik prüfen
- bestehende Buttons, Ansichten, Statusfelder und Interaktionen prüfen
- nichts voreilig ersetzen

### 2. Bestand dokumentieren
Vor jeder größeren Änderung intern festhalten:
- was bereits existiert
- was sinnvoll ist und bleiben soll
- was fehlerhaft oder unvollständig ist
- was ergänzt werden muss
- was nicht angerührt werden soll

### 3. Bestehendes Grundgerüst weiterverwenden
- keine parallelen Strukturen anlegen
- keine unnötigen neuen Wege bauen
- vorhandene Localhost-Struktur als Basis behalten
- bestehende Startlogik respektieren und nur erweitern

### 4. Mail- und Aufgabenlogik bereinigen
Zuerst die fachliche Einordnung korrigieren:
- falsche Mailklassifizierung bereinigen
- Antwortbedarf logisch trennen
- Newsletter, Shop, System und Werbung sauber ausfiltern
- Karten informativer machen
- Hauptbutton bei antwortwürdigen Vorgängen auf „Mit Kira besprechen“ umstellen

### 5. Dashboard-Struktur verbessern
Danach die Oberfläche logisch überarbeiten:
- Dashboard als Hauptseite stärken
- Kommunikation, Organisation, Geschäft und Wissen sauber trennen
- visuelle Hierarchie beruhigen
- unnötige Mail-Lastigkeit reduzieren
- Karten, Status und Aktionen übersichtlicher machen

### 6. Kira als Assistenz integrieren
Erst dann Kira unten rechts als schwebende Assistenz einbauen:
- Panel / Drawer
- Home
- Nachrichten
- Aufgaben
- Wissen
- Vorschläge

### 7. Kommunikationsfenster pro Vorgang bauen
Danach pro antwortwürdigem Vorgang das Kommunikationsfenster einbauen:
- Einordnung zuerst
- Kai-Input danach
- Entwurf erst nach Kai-Input
- Kontext pro Vorgang speichern
- keine Unterbrechung im Bedienfluss

### 8. Korrekturschleife integrieren
Danach direkte Korrekturmöglichkeiten auf den Karten einbauen:
- falsch zugeordnet
- Kategorie ändern
- als Regel merken
- Notiz an Assistenz

Alle Korrekturen direkt speichern und für spätere Einordnung nutzbar machen.

### 9. Wissensspeicher und Rechnungslogik anbinden
Danach:
- Wissensspeicher sauber strukturieren
- Lernvorschläge von festen Regeln trennen
- Rechnungsdatenbank oder strukturierte Rechnungsleseschicht vorbereiten oder anbinden
- Bot-Abfragen für Geschäftsdaten sinnvoll vorbereiten

### 10. Bedienfluss prüfen
Danach prüfen:
- läuft alles flüssig
- bleibt der Kontext erhalten
- keine unnötigen Reloads
- keine unnötigen Fensterwechsel
- klare Benutzerführung
- saubere Speicherlogik

### 11. Speichern und testen
Nach jedem größeren Schritt:
- speichern
- testen
- notieren, was erledigt ist
- notieren, was noch offen ist

### 12. Abschlussprüfung
Vor dem Commit zwingend prüfen:
- bestehendes Grundgerüst wurde genutzt
- nichts Wichtiges wurde doppelt gebaut
- neue Teile sitzen logisch an der richtigen Stelle
- Statuslogik und Dashboardlogik sind konsistent
- Kira läuft sauber
- Kommunikationsfenster funktioniert
- Korrekturen werden gespeichert
- Localhost-Lösung ist stabil

### 13. Commit
Erst nach vollständiger Prüfung:
- Änderungen zusammenfassen
- sauber committen

## Zusatzregel

Wenn ein Punkt technisch nicht sauber innerhalb der bestehenden HTML-/Localhost-Lösung umsetzbar ist:
- nicht improvisieren
- klar benennen, wo die Grenze ist
- begründen, warum es hakt
- erst dann eine bessere technische Alternative vorschlagen

## Abschluss

Arbeite ruhig, systematisch und ohne Sprünge.
Nicht alles gleichzeitig umbauen.
Nicht zwischen Baustellen hin- und herspringen.
Erst einen Bereich sauber einordnen, integrieren und prüfen, dann zum nächsten.
