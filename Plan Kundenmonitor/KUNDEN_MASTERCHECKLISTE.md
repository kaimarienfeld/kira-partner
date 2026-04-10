# Kunden / CRM / Kundencenter — Mastercheckliste

Stand: 2026-04-10

---

## Paket 1 — Plandateien + Gap-Analyse ✅
- [x] KUNDEN_MASTERCHECKLISTE.md
- [x] KUNDEN_SESSION_PLAN.md
- [x] KUNDEN_RECHERCHE.md
- [x] KUNDEN_DATENMODELL.md
- [x] KUNDEN_CLASSIFIER_KONZEPT.md
- [x] KUNDEN_ENTSCHEIDUNGEN.md
- [x] KAI_TODO_KUNDEN.md

## Paket 2 — Datenmodell + LLM-Projekt-Classifier ✅
- [x] ALTER TABLE kunden — 11 neue Spalten
- [x] CREATE TABLE kunden_identitaeten
- [x] CREATE TABLE kunden_projekte
- [x] CREATE TABLE kunden_faelle
- [x] CREATE TABLE kunden_aktivitaeten
- [x] CREATE TABLE kunden_classifier_log
- [x] _ensure_crm_tables() in case_engine.py
- [x] kunden_classifier.py — neues Modul (~400 LOC)
  - [x] Fast-Path (bekannte E-Mail → sofort zuordnen)
  - [x] LLM-Path (Super-Prompt + JSON-Response)
  - [x] Confidence-Auswertung (eindeutig/wahrscheinlich/prüfen/unklar)
  - [x] Logging in kunden_classifier_log
- [x] Geschäftskontakt-Filter in mail_classifier.py
- [x] Classifier-Aufruf in mail_monitor.py (nach vorgang_router)
- [x] Classifier-Aufruf in daily_check.py

## Paket 3 — Navigation + 2-Spalten-Menü
- [ ] Sidebar-Eintrag "Kunden" mit Badge
- [ ] build_kunden() Hauptfunktion in server.py
- [ ] _build_crm_subnav() — 5 Untermenüpunkte
- [ ] Panel-Wechsel-JS (crmShowPanel)
- [ ] CSS crm-* Grundgerüst
- [ ] showPanel('kunden') Verdrahtung

## Paket 4 — Kundenübersicht + Akkordeon
- [ ] _build_crm_kundenuebersicht() — HTML aus Mockup
- [ ] Suchfeld + Filter (Typ, Status, Segment)
- [ ] Akkordeon-Gruppen (Aktive/Leads/Inaktive/Archiv)
- [ ] Kunden-Zeilen (Name, Typ, Projekt, Aktivität, Fälle, Status)
- [ ] "Neuer Kunde"-Button → Formular
- [ ] Contacts-Ansicht (Absender ohne Kundenstatus)
- [ ] GET /api/crm/kunden (Filter/Suche/Gruppierung)
- [ ] GET /api/crm/contacts
- [ ] POST /api/crm/kunden (Neuen Kunden anlegen)
- [ ] GET /api/crm/kunden/{id}
- [ ] PUT /api/crm/kunden/{id}
- [ ] GET /api/crm/stats (KPI-Zahlen)
- [ ] JS: crmLoadKunden(), crmFilterKunden(), crmToggleAccordion()

## Paket 5 — Kundenakte + Projekt-Zeitstrahl
- [ ] _build_crm_kundenakte() — HTML aus Mockup
- [ ] Kundenkopf (Firma, Typ, Status, Wert, Warnsignale)
- [ ] Projekt-Zeitstrahl (horizontal/vertikal)
- [ ] Projektumschalter-Dropdown
- [ ] Zentrale Verlaufsfläche (projektgefiltert)
- [ ] Rechte Kontextspalte (Stammdaten, Lexware)
- [ ] Tabs: Verlauf | Fälle | Dokumente | Finanzen | Kira | Einstellungen
- [ ] GET /api/crm/kunden/{id}/projekte
- [ ] POST /api/crm/kunden/{id}/projekte
- [ ] PUT /api/crm/projekte/{id}
- [ ] GET /api/crm/kunden/{id}/aktivitaeten?projekt_id=X
- [ ] GET /api/crm/kunden/{id}/stammdaten
- [ ] JS: crmLoadKundenakte(), crmSwitchProject(), crmLoadTimeline()

## Paket 6 — Fallansicht (Ticket-Layer)
- [ ] _build_crm_fallansicht() — HTML aus Mockup
- [ ] Ticket-Kopf (Nummer, Titel, Typ, Status, Priorität)
- [ ] Timeline alle Quellen (Mail, Kira, Memo, Dokument, Lexware, manuell)
- [ ] Aktionen (E-Mail, Notiz, Dokument, Status, Kira, Export)
- [ ] Streitfall-Ansicht (_build_crm_streitfall)
- [ ] GET /api/crm/kunden/{id}/faelle?projekt_id=X
- [ ] POST /api/crm/faelle
- [ ] GET /api/crm/faelle/{id}
- [ ] PUT /api/crm/faelle/{id}
- [ ] POST /api/crm/faelle/{id}/aktivitaeten
- [ ] GET /api/crm/faelle/{id}/export
- [ ] JS: crmLoadFall(), crmUpdateFallStatus(), crmAddAktivitaet()

## Paket 7 — Funktionspflicht
- [ ] Kontakt bearbeiten → Formular
- [ ] Neuer Kunde → Formular
- [ ] Verlaufseintrag klicken → Detail
- [ ] Neue E-Mail → Compose-Fenster
- [ ] Neue Rechnung/Angebot → Lexware-Modul
- [ ] Neuer Fall → Erstell-Dialog
- [ ] Export/Streitfall → Streitfall-Ansicht
- [ ] Kira fragen → Workspace mit Kontext
- [ ] Projekt wechseln → Dropdown + Filter
- [ ] Fall-Status ändern → In-place

## Paket 8 — Kira + Einstellungen + Runtime-Log + Tour
- [ ] Kira-Tool: kunden_suchen
- [ ] Kira-Tool: kundenakte_laden
- [ ] Kira-Tool: projekt_zuordnen
- [ ] Kira-Tool: fall_erstellen
- [ ] Kira-Tool: fall_oeffnen
- [ ] Kira-Tool: kunden_klassifizieren
- [ ] Kira-Tool: aktivitaeten_pruefliste
- [ ] System-Prompt-Erweiterung (Top 5, offene Fälle, unzugeordnete)
- [ ] 5 Quick-Actions im Kira-Workspace
- [ ] Einstellungen-Sektion "Kunden / CRM" (11 Optionen)
- [ ] 16 Runtime-Log-Events via elog()
- [ ] Guided Tour (5 Schritte)

## Paket-Abschluss (nach jedem Paket)
- [ ] Git Commit
- [ ] session_handoff.json aktualisiert
- [ ] feature_registry.json aktualisiert
- [ ] KIRA_SYSTEM_ANALYSE.md aktualisiert
- [ ] KUNDEN_MASTERCHECKLISTE.md Punkte abgehakt
- [ ] session_log.md Zwischeneintrag
