# Session-Plan — Kunden CRM Vollausbau

Stand: 2026-04-10

---

## 1. Ist-Zustand

### Was existiert
| Komponente | Datei | Status |
|---|---|---|
| kunden-Tabelle | kunden.db | 1.432 Einträge, 8 Spalten (email, name, erstkontakt, letztkontakt, anzahl_mails, hauptkanal, notiz) |
| interaktionen-Tabelle | kunden.db | 7.361 Einträge (Mail-Verlauf) |
| kunden-360 API | server.py:33374 | GET /api/kunden/360?email= — liest kunden + interaktionen + tasks + vorgaenge + rechnungen + angebote |
| Case Engine | case_engine.py | 10 Vorgangstypen, State Machines, CRUD-API |
| Vorgang-Router | vorgang_router.py | Mail → Vorgang Routing |
| Mail-Classifier | mail_classifier.py | 5-Stufen-Pipeline |
| LLM-Classifier | llm_classifier.py | 4-Stufen, JSON-Response |
| Lexware-Client | lexware_client.py | get_all_contacts(), create/update |
| Sidebar "Kunden"-Eintrag | server.py:16907 | Vorhanden, aber Panel leer |
| CRM-Pipeline (build_crm_pipeline) | server.py:6638 | Dashboard-Widget, kein echtes CRM |
| Runtime-Log | runtime_log.py | elog() + SQLite |
| Tour-Engine | server.py | 8 Module, 59 Schritte |
| Kira-Tools | kira_llm.py | 52 Tools |

### Was fehlt (Gap-Analyse)
| Was | Beschreibung |
|---|---|
| Projekttrennung | Kein Projekt-Konzept — alles pro Kunde ungefiltert |
| Ticket-Layer | Kein Fall/Ticket-Konzept für einzelne Geschäftsvorfälle |
| Kunden-Classifier | Keine automatische Zuordnung Mail → Kunde → Projekt |
| 2-Spalten-Menü | Sidebar zeigt "Kunden" aber kein Sub-Menü |
| Kundenübersicht | Kein breites Listen-Layout, kein Akkordeon |
| Kundenakte | Keine echte Arbeitsakte mit Verlauf + Tabs |
| Fallansicht | Keine Einzelfall-Ansicht mit Timeline |
| Geschäftskontakt-Filter | Kein Filter für Newsletter vs. echte Geschäftspartner |
| CRM-Einstellungen | Keine Sektion in Einstellungen |
| CRM Kira-Tools | Keine kundenspezifischen Tools |

---

## 2. Soll-Zustand

Vollständiges Kundenmodul mit:
- 6 neuen DB-Tabellen (ALTER TABLE kunden + 5 neue)
- LLM-basierter Kunden-Classifier (kunden_classifier.py)
- 2-Spalten-Navigation (5 Unterpunkte)
- Kundenübersicht mit Akkordeon-Gruppen
- Kundenakte mit Projekt-Zeitstrahl und Projektumschalter
- Fallansicht (Ticket-Layer) mit Timeline aller Quellen
- Alle Mockup-Aktionen funktional
- 7 neue Kira-Tools
- CRM-Einstellungen
- 16 Runtime-Log-Events
- Guided Tour

---

## 3. Umsetzungsreihenfolge

P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8

Jedes Paket baut auf dem vorherigen auf. Kein Paket kann übersprungen werden. Git-Commit nach jedem Paket.

---

## 4. Betroffene Dateien

| Datei | Änderungsart | Geschätzte LOC |
|---|---|---|
| scripts/server.py | Erweitern | ~4.350 |
| scripts/kunden_classifier.py | NEU | ~400 |
| scripts/case_engine.py | Erweitern | ~100 |
| scripts/kira_llm.py | Erweitern | ~250 |
| scripts/mail_classifier.py | Erweitern | ~50 |
| scripts/mail_monitor.py | Erweitern | ~20 |
| scripts/daily_check.py | Erweitern | ~20 |
| scripts/kira_proaktiv.py | Erweitern | ~30 |
| knowledge/kunden.db | Migration | — |
| **Total** | | **~5.220** |
