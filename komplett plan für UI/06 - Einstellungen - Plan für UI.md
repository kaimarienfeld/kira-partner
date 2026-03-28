06 - Einstellungen - Plan für UI


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

Hier greifen die schon vorhandenen technischen Grundlagen wie ntfy.sh (+ Dokumentations BTN wie richte ich das ein) und Windows Toast. Das ist bereits dokumentiert.

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