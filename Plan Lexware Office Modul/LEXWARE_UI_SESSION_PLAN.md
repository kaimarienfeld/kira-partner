# Lexware UI Komplettausbau — Session-Plan (session-fff)

Stand: 2026-04-01
Session: session-fff — Autonome Nacht-Session

---

## Ist-Zustand (nach session-eee)

### Was bereits implementiert ist

- build_lexware(db) in server.py (~290 Zeilen) mit 3 Zustaenden (nicht_gebucht / gesperrt / freigeschaltet)
- 6 Tabs: Cockpit, Belege, Kontakte, Artikel, Buchhaltung, Diagnose (einfache Tabellen)
- Sidebar-Eintrag nav-lexware ohne Badge-Logik
- Einstellungen es-sec-lexware mit API-Key, Sync, Toggle-Switches
- 7 GET-Endpunkte + 5 POST-Endpunkte (lexware_client.py, eingangsbelege)
- JS: showLexTab, lexSync, lexBelegDetail, lexKontaktDetail, lexPruefDetail, lxFilter*

### Was fehlt oder unzureichend ist

1. Sidebar: kein Badge fuer neue Belege / Pruefbedarf / Fehler
2. Modul-Kopfbereich: fehlt komplett (Titel + Statuszeile links, Aktionsleiste rechts)
3. Sekundaere Navigation: nur als simple Tab-Leiste — fehlen: Zahlungen, Dateien, Regeln & Muster, Diagnose & Mapping als volle Unterseiten
4. Cockpit: zu einfach — fehlen: Warnungen-Panel, Signale, Schnellaktionen, Kira-Einstieg
5. Belege: Detail fehlt (nur JSON-Modal), keine Detailflaeche, kein Kira-Einstieg
6. Zahlungen: komplett fehlend
7. Kontakte: zu simpel — keine offenen Volumen, keine Kira-Einstiege, kein Detailbereich
8. Artikel: fehlende "In Angebot nutzen", Herkunft-Spalte, Kira-Einstieg
9. Dateien: komplett fehlend
10. Buchhaltung: nur Pruefqueue-Tabelle — fehlen: Unterbereich-Tabs (Zu pruefen / Vorbereitet / Abgelegt / Unklar / Vollautomatik / Historie), Kira-Rueckfrage-Anzeige, Kontierungsvorschlag
11. Regeln & Muster: komplett fehlend
12. Diagnose & Mapping: nur Log-Dump (monospace) — kein strukturiertes Layout
13. Einstellungen: nur Basis-Sektion — fehlen: Sync, Kategorien, Eingangsbelege, Vollautomatik, Regeln & Muster, Dataverse, Diagnose, Freischaltung als separate Unterbereiche
14. Kira-Einstiege: nur in Buchhaltung-Detail-Modal — fehlen: aus Belegen, Zahlungen, Kontakten, Regeln, Diagnose

---

## Soll-Zustand laut Arbeitsanweisung

Siehe Arbeitsanweisung_Lexware_UI_Komplettausbau_ClaudeCode.md (vollstaendig).

Kurzfassung:
- Hochwertiges Unternehmens-Software-Modul
- 9 Pflicht-Unterbereiche als eigene echte Arbeitsansichten
- Modul-Kopfbereich mit echten Zustaenden
- Sidebar mit Badge-Logik und Freischaltlogik
- Einstellungen im 3-Spalten-System mit 9 Lexware-Unterbereichen
- Kira-Einstiege aus allen Hauptbereichen mit echtem Kontext
- Dokumente-Bezug in Belegansicht sichtbar

---

## Scope dieser Session

### In Scope (session-fff)

- Paket A: Sidebar Badge + Modul-Kopfbereich
- Paket B: Sekundaere Navigation + alle 9 Unterseiten vollstaendig ausgebaut
- Paket C: Buchhaltung Unterbereich-Tabs + Regeln & Muster
- Paket D: Einstellungen 9 Unterbereiche
- Paket E: Kira-Einstiege aus allen Bereichen
- Paket F: In-Planung Statushinweise (Zahlungen, Dateien, Auswertung etc.)

### Nicht in Scope (Kai-Aktionen)

- API-Key eintragen (KAI-01)
- Live-Verdrahtung der Zahlungs-API (kein Lexware-Zahlungsexport-Endpunkt verfuegbar)
- Dataverse-Vollintegration (Prio C)

---

## Arbeitsreihenfolge

1. Plan-Dateien schreiben (diese + GAP, Komponenten, Endpunkte, Entscheidungen, KAI_TODO)
2. Paket A: Sidebar Badge-Logik + Modul-Kopfbereich in build_lexware()
3. Paket B: Alle 9 Unterseiten (neue Tabs + Inhalte)
4. Paket C: Buchhaltung Unterbereich-Tabs + Regeln & Muster vollstaendig
5. Paket D: Einstellungen erweitern (9 Unterbereiche)
6. Paket E: Kira-Einstiege mit Kontext-Uebergabe
7. Paket F: In-Planung-Komponenten
8. Abschluss: Tracking, Commits, Abschlusstabelle

---

## Betroffene Bereiche in server.py

| Zeile | Bereich |
|-------|---------|
| 9587-9874 | build_lexware() — vollstaendiger Umbau |
| 9877-9892 | _build_lexware_tabs_preview() — Erweiterung |
| 10038-10040 | Sidebar nav-lexware — Badge hinzufuegen |
| 8548-8704 | es-sec-lexware — Erweiterung um 9 Unterbereiche |
| 10729-10860 | JS Lexware-Funktionen — neue hinzufuegen |

---

## Risiken und Seiteneffekte

- server.py ist 21835 Zeilen — gezieltes Ersetzen nur der Lexware-Abschnitte
- CSS lx-* Prefix beibehalten — keine Konflikte mit anderen Modulen
- Neue Tabs erfordern showLexSecTab() (Unterbereich-Navigation innerhalb Buchhaltung)
- Keine DB-Schema-Aenderungen noetig — alle Tabellen aus session-eee vorhanden
- Einstellungen: neue Unterbereich-IDs muessen mit esShowLexSec() navigierbar sein

---

## Was Kai selbst tun muss

Siehe KAI_TODO_LEXWARE_UI.md (wird in Phase 4 geschrieben).
