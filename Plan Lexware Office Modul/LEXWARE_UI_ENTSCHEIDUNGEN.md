# Lexware UI — Architektur- und Design-Entscheidungen

Stand: 2026-04-01
Session: session-fff

---

## Entscheidung 1: Sekundaere Navigation als Buttons (nicht Tabs)

**Problem:** Bisherige Tab-Leiste ist zu eng fuer 9+ Eintraege.
**Entscheidung:** lx-nav-sec als breite Button-Leiste unterhalb des Modul-Kopfbereichs.
Scrollbar horizontal bei kleinen Screens (overflow-x: auto).
Aktiver Bereich: data-lxsec Attribut.
**Grund:** Konsistent mit Einstellungen-Sub-Navigation (esShowSec Pattern).

---

## Entscheidung 2: Split-View vs. Modal fuer Details

**Problem:** JSON-Modal ist unbrauchbar (rohe Daten, nicht produktiv).
**Entscheidung:** Bei Beleg/Kontakt-Klick: Detailbereich rechts aufklappen (Split-View).
Bei kleinen Screens: Detailbereich ueberlagernd (Overlay, nicht Modal).
**Grund:** Ermoeglicht paralleles Arbeiten (Liste links, Detail rechts).

---

## Entscheidung 3: Zahlungen als "In Planung"

**Problem:** Lexware API hat keinen dedizierten Zahlungsexport-Endpunkt in der kostenlosen API-Variante.
**Entscheidung:** Zahlungen-Tab zeigt strukturierte Ansicht mit "In Planung"-Hinweis PLUS lokale Zahlungserfassung aus eingangsbelege_pruefqueue (Felder: betrag, is_paypal, status).
**Grund:** Kai muss nicht blockiert werden — Vorstruktur sichtbar machen.

---

## Entscheidung 4: Regeln & Muster aus DB konstruiert

**Problem:** Keine eigene "Regeln"-Tabelle vorhanden.
**Entscheidung:** Regeln werden aus eingangsbelege_pruefqueue abgeleitet (GROUP BY absender + konto_vorschlag) und als dynamische Ansicht dargestellt.
Echte Regeltabelle ist Prio C (naechste Session).
**Grund:** Echten Mehrwert zeigen ohne neue DB-Migration.

---

## Entscheidung 5: Kira-Kontext-Uebergabe

**Problem:** openKiraWorkspace() erwartet bestimmte Parameter.
**Entscheidung:** Alle lxOpenKiraWithContext()-Aufrufe bauen einen Prompt-String auf der Basis des Datensatzes und rufen openKiraWorkspace('lexware', prompt) auf.
**Grund:** Konsistent mit bestehendem Kira-Einstieg aus Buchhaltung-Modal.

---

## Entscheidung 6: Einstellungen Sub-Navigation

**Problem:** 9 Unterbereiche in einer langen rechten Spalte ist unuebersichtlich.
**Entscheidung:** Mittlere Spalte der Einstellungen bekommt fuer Lexware eine eigene Sub-Nav-Liste (lx-es-subnav) mit 9 Eintraegen. Klick wechselt lx-es-subpanel.
**Grund:** Konsistent mit dem 3-Spalten-Konzept der Arbeitsanweisung.

---

## Entscheidung 7: Sidebar Badge-Farbe

**Problem:** Welche Farbe fuer welchen Badge-Typ?
**Entscheidung:**
- Pruefbedarf (n_pruef > 0): orange Badge (rgba(200,100,0,.12) / #c86400)
- Fehler (kein API-Key): rotes Badge
- Neues (sync_count > 0): blaues Badge wie andere Module
**Grund:** Konsistent mit bestehender Badge-Logik in KIRA (Kommunikation, Protokoll).

---

## Entscheidung 8: Buchhaltungs-Unterbereich-Tabs

**Problem:** Buchhaltung hat 6 Unteransichten.
**Entscheidung:** lx-buch-nav mit 6 Buttons, showLexBuchTab() wechselt lx-buch-content-Divs.
Aktive Unteransicht wird per data-buch-tab Attribut gesteuert.
**Grund:** Gleiche Struktur wie showKTab() im Kira-Workspace — bewaeHRt.

---

## Entscheidung 9: Dokumente-Bezug in Belegdetail

**Problem:** Dokumente-Modul ist noch nicht fertig implementiert.
**Entscheidung:** In der Belegdetail-Flaeche wird ein "Dokumente-Bezug"-Block vorbereitet:
Status: "Dokument vorhanden: [Ja/Nein]" aus Anhang-Daten der eingangsbelege_pruefqueue.
Echter Dokumente-Link kommt wenn Dokumente-Modul fertig ist.
**Grund:** Vorbereitung ohne Abhaengigkeit.
