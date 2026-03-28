# Assistenzplan – Was ich für Kai erledige
*Übersicht aller Aufgaben, Automatisierungen und Workflows*

---

## SOFORT VERFÜGBAR (kann ich jetzt)

### Kundenanfragen bearbeiten
- Neue Leads aus `anfrage_raumkult_eu/INBOX/` lesen
- Fotos aus `attachments/` ansehen
- Antwortmail schreiben (Stil gelernt aus 522 gesendeten Mails)
- Intern: Einschätzung + fehlende Infos + nächste Aktion
- Befehl: „schau was neu reingekommen ist" / „bearbeite Anfrage von [Name]"

### Angebote & Texte
- Angebotstext erstellen (nach Preisliste)
- Ausschreibungsantworten formulieren
- Ablehnungsmails schreiben
- Follow-up Mails bei Schweigen

### Mail-Suche & -Analyse
- Alle 12.642 Mails durchsuchbar via mail_index.db
- Gesendete Mails nach Typ/Datum suchen
- Threads nachverfolgen (was wurde wann geantwortet?)

### Kalkulationen
- Projektpreise aus Preisliste berechnen
- Reisekosten-Kalkulation
- Tagessatz vs. m²-Empfehlung

---

## MANUELL ANSTOSSEN (ich mache es wenn du sagst)

### Newsletter abmelden
- 409 Newsletter-Absender identifiziert
- Ich zeige dir die Liste, du entscheidest welche abzumelden
- Ich schreibe die Abmelde-Anfragen / suche Abmelde-Links

### Leads-Status pflegen
- leads.db aktualisieren: Status setzen (beantwortet, Angebot erstellt, abgelehnt, Auftrag)
- Offene Leads zeigen: wer hat noch keine Antwort?
- Befehl: „zeig mir alle offenen Anfragen"

### Datenbanken aktualisieren
- `scripts/build_databases.py` neu ausführen → nimmt neue Mails auf
- Befehl: „aktualisiere die Datenbanken"

---

## GEPLANT / NOCH EINZURICHTEN

### Kalender-Integration (Google Calendar verfügbar)
- Projekttermine eintragen
- Freie Zeitfenster für Angebots-Calls finden
- Folge-Erinnerungen für offene Anfragen
- → Benötigt: Deine Freigabe pro Nutzung (GCal ist verknüpft)

### Rechnungen & Zahlungserinnerungen
- Offene Rechnungen tracken (aus invoice@sichtbeton-cire.de)
- Mahnstufen erkennen und Erinnerungen schreiben
- → Nächster Schritt: invoice-Mails analysieren + Struktur klären

### Wichtige Mails herausfiltern
- Täglich / bei Bedarf: Posteingänge scannen auf Dringendes
- Kategorien: Neue Anfragen / Zahlungseingänge / Angebots-Rückmeldungen / Dringendes
- Befehl: „zeig mir was heute wichtig ist"

### Newsletter-Automatik
- Regelmäßig neue Newsletter erkennen
- Relevante Branchen-Infos (Baustoffe, Betonkosmetik, Handwerk) behalten
- Rest: Abmelde-Liste vorschlagen

---

## BEFEHLE / SHORTCUTS (wie du mich am besten nutzt)

| Was du sagst | Was ich mache |
|---|---|
| „neue Anfragen" | Zeige unbearbeitete Leads aus dem Archiv |
| „bearbeite [Name]" | Lese Mail + Fotos, schreibe Antwort-Entwurf |
| „was ist offen" | Leads ohne Status / ohne Antwort |
| „kalkulation [Projekt]" | Preisberechnung nach Preisliste |
| „newsletter zeigen" | Liste der 409 erkannten Absender |
| „aktualisiere DB" | build_databases.py neu ausführen |
| „wichtige Mails heute" | Posteingänge nach Relevanz scannen |

---

## DATENBANKEN PFLEGEN

Die Datenbanken werden **nicht automatisch** aktualisiert – du musst sagen „aktualisiere die Datenbanken" oder ich mache es zu Beginn einer längeren Sitzung.

Letzter Build: Wird in `knowledge/db_status.json` gespeichert.
