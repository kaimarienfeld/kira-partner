# Architektur-Entscheidungen — Kunden CRM

Stand: 2026-04-10

---

## E-01: Alle CRM-Tabellen in kunden.db

**Entscheidung:** Alle 6 neuen Tabellen kommen in `knowledge/kunden.db`.  
**Begründung:** kunden.db existiert bereits mit `kunden` + `interaktionen`. Logische Zusammengehörigkeit. Kein neues DB-File nötig. tasks.db bleibt für Tasks/Vorgänge.  
**Risiko:** kunden.db wächst — aber WAL-Modus + Autocheckpoint (ISS-009 Fix) deckt das ab.

## E-02: ALTER TABLE statt neue Tabelle

**Entscheidung:** Bestehende `kunden`-Tabelle um 11 Spalten erweitern.  
**Begründung:** 1.432 bestehende Kunden-Einträge bleiben erhalten. Kein Datenverlust, kein Mapping nötig. SQLite ALTER TABLE ADD COLUMN ist sicher (immer am Ende).  
**Alternative verworfen:** `kunden_v2` neu → Datenmigration + Umbenennungschaos.

## E-03: Classifier NACH Vorgang-Router

**Entscheidung:** kunden_classifier.py läuft nach vorgang_router.py in der Pipeline.  
**Begründung:** Vorgang-Router erstellt den Vorgang (Typ, Entscheidungsstufe). Classifier ordnet danach Kunde+Projekt zu. Beide ergänzen sich, keiner ersetzt den anderen.  
**Reihenfolge:** mail_classifier → vorgang_router → kunden_classifier

## E-04: Fast-Path vor LLM

**Entscheidung:** Bekannte E-Mail-Adressen (confidence='eindeutig') → sofort zuordnen, kein LLM.  
**Begründung:** ~80% der Geschäftsmails kommen von bekannten Kunden. LLM-Aufruf pro Mail = unnötige Kosten + Latenz. Fast-Path macht das System effizient.

## E-05: Lexware als führende Quelle

**Entscheidung:** Lexware-Kontakte sind Stammdaten-Quelle. kunden.lexware_id verknüpft.  
**Begründung:** REGEL-09 (Masterliste). Keine parallele Stammdatenwelt. Background-Sync alle 6h.  
**Konsequenz:** Neue Kunden über Lexware → automatisch in KIRA sichtbar.

## E-06: CSS-Prefix crm-*

**Entscheidung:** Alle neuen CSS-Klassen mit `crm-` Prefix.  
**Begründung:** server.py hat >35.000 Zeilen mit vielen CSS-Klassen. Prefix verhindert Kollisionen.

## E-07: 2-Spalten-Muster wie Lexware

**Entscheidung:** build_kunden() folgt exakt dem Muster von build_lexware().  
**Begründung:** Bewährtes Pattern. Sub-Navigation links, Hauptbereich rechts. Konsistente UX.
