# Lexware UI — Gap-Analyse (Ist vs. Soll)

Stand: 2026-04-01
Session: session-fff

---

## 1. Cockpit

| | Ist | Soll | Aufwand | Prio |
|-|-----|------|---------|------|
| KPIs | 5 Kacheln (Zahlen) | 7+ Kacheln + Hero-Zone | M | A |
| Warnungen-Panel | fehlt | Warnungen/Signale rechts | M | A |
| Schnellaktionen | fehlt | Kira-Einstieg, manuelle Pruefung | S | A |
| Kira-Einstieg | fehlt | "Mit Kira besprechen" Button | S | A |
| Letzte Vorgaenge | fehlt | Liste aktuelle Vorgaenge links | M | B |
| Sync-Status | einfach | Letzte Sync + Ampel | S | B |

---

## 2. Belege

| | Ist | Soll | Aufwand | Prio |
|-|-----|------|---------|------|
| Tabelle | vorhanden (6 Spalten) | + Fälligkeit + Quelle + Kira-Spalte | S | A |
| Filter | Typ/Status/Suche | + Datum + Betrag + Quelle + "Mit Dok" | M | B |
| Detail | JSON-Modal | Detailflaeche (Absender, Dok, Status-History) | L | A |
| Kira-Einstieg | fehlt | Button "Mit Kira besprechen" | S | A |
| Dok-Bezug | fehlt | "Dokument vorhanden: Ja/Nein" in Detail | M | B |
| Aktionen | fehlt | Sync, zu Zahlungen, Verlauf | S | B |

---

## 3. Zahlungen

| | Ist | Soll | Aufwand | Prio |
|-|-----|------|---------|------|
| Alles | fehlt | Zahlungsliste, Filter, Detail, Kira | L | A |
| Backend | kein Lexware-Zahlungs-API | "In Planung"-Hinweis + lokale Zahlungserfassung | M | B |

---

## 4. Kontakte & Kunden

| | Ist | Soll | Aufwand | Prio |
|-|-----|------|---------|------|
| Tabelle | Name/Email/Sync | + offenes Volumen + letzter Vorgang + Lex-Status | M | A |
| Detail | JSON-Modal | Detailflaeche mit Vorgaengen und Belegen | L | A |
| Kira-Einstieg | fehlt | Button "Mit Kira besprechen" | S | A |
| Suche | vorhanden | behalten | - | - |

---

## 5. Artikel & Preispositionen

| | Ist | Soll | Aufwand | Prio |
|-|-----|------|---------|------|
| Tabelle | Name/Typ/Netto/Einheit/Steuer | + Herkunft + letzte Nutzung + aktiv/inaktiv | S | A |
| Aktionen | fehlt | "In Angebot", "In Rechnung", Kira | S | B |
| Detail | fehlt | Kurzdetail auf Klick | M | B |

---

## 6. Dateien

| | Ist | Soll | Aufwand | Prio |
|-|-----|------|---------|------|
| Alles | fehlt | Dateiliste + Vorschau + Metadaten + Dok-Bezug | L | A |
| Backend | nicht noetig | lokale Abbildung aus eingangsbelege + tasks.db | M | B |

---

## 7. Buchhaltung

| | Ist | Soll | Aufwand | Prio |
|-|-----|------|---------|------|
| Unterbereich-Tabs | fehlt (1 Ansicht) | Zu pruefen / Vorbereitet / Abgelegt / Unklar / Vollautomatik / Historie | L | A |
| Kira-Rueckfrage | fehlt | kira_frage-Feld sichtbar in Zeile | S | A |
| Kontierungsvorschlag | fehlt | konto_vorschlag sichtbar mit Ampel | S | A |
| Bestaetigungsflow | nur Modal | Pruef-Modal mit Kontierungs-Confirm + Kira | M | A |
| Vollautomatik | fehlt | eigene Unteransicht mit blockierten Faellen | M | B |
| Historie | fehlt | Verlauf-Tab | M | C |

---

## 8. Regeln & Muster

| | Ist | Soll | Aufwand | Prio |
|-|-----|------|---------|------|
| Alles | fehlt | Regelliste mit 9 Typen, Aktionen, Kira | L | A |
| Backend | in kira_llm.py verwaltet | Regeltypen aus eingangsbelege-Lernen lesen | M | B |

---

## 9. Diagnose & Mapping

| | Ist | Soll | Aufwand | Prio |
|-|-----|------|---------|------|
| Layout | Log-Dump monospace | Strukturiertes 3-Bereiche Layout | M | A |
| Mapping-Tabelle | fehlt | KIRA<>Lexware Feldmapping | M | B |
| Event-Status | fehlt | Webhook-Status, letzte Events | S | B |

---

## Einstellungen (9 Unterbereiche)

| Unterbereich | Ist | Aufwand |
|---|---|---|
| Verbindung | vorhanden (basis) | S ergaenzen |
| Sync | teilweise | M ausbauen |
| Kategorien | fehlt | M neu |
| Eingangsbelege | Toggles da | S ergaenzen |
| Vollautomatik | fehlt | M neu |
| Regeln & Muster | fehlt | M neu |
| Dataverse | Toggle da | S ergaenzen |
| Diagnose | fehlt | S neu |
| Freischaltung | Modul-Status da | S ergaenzen |
