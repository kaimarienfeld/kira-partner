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

## Paket 3 — Navigation + 2-Spalten-Menü ✅
- [x] Sidebar-Eintrag "Kunden" mit Badge
- [x] build_kunden() Hauptfunktion in server.py
- [x] _build_crm_subnav() — 5 Untermenüpunkte
- [x] Panel-Wechsel-JS (crmShowPanel)
- [x] CSS crm-* Grundgerüst
- [x] showPanel('kunden') Verdrahtung

## Paket 4 — Kundenübersicht + Akkordeon ✅
- [x] _build_crm_kundenuebersicht() — HTML aus Mockup
- [x] Suchfeld + Filter (Typ, Status, Segment)
- [x] Akkordeon-Gruppen (Aktive/Leads/Inaktive/Archiv)
- [x] Kunden-Zeilen (Name, Typ, Projekt, Aktivität, Fälle, Status)
- [x] "Neuer Kunde"-Button → Formular
- [x] Contacts-Ansicht (Absender ohne Kundenstatus)
- [x] GET /api/crm/kunden (Filter/Suche/Gruppierung)
- [x] GET /api/crm/contacts
- [x] POST /api/crm/kunden (Neuen Kunden anlegen)
- [x] GET /api/crm/kunden/{id}
- [x] PUT /api/crm/kunden/{id}
- [x] GET /api/crm/stats (KPI-Zahlen)
- [x] JS: crmLoadKunden(), crmFilterKunden(), crmToggleAccordion()

## Paket 5 — Kundenakte + Projekt-Zeitstrahl ✅
- [x] _build_crm_kundenakte() — HTML aus Mockup
- [x] Kundenkopf (Firma, Typ, Status, Wert, Warnsignale)
- [x] Projekt-Zeitstrahl (horizontal/vertikal)
- [x] Projektumschalter-Dropdown
- [x] Zentrale Verlaufsfläche (projektgefiltert)
- [x] Rechte Kontextspalte (Stammdaten, Lexware)
- [x] Tabs: Verlauf | Fälle | Dokumente | Finanzen | Kira | Einstellungen
- [x] GET /api/crm/kunden/{id}/projekte
- [x] POST /api/crm/kunden/{id}/projekte
- [x] PUT /api/crm/projekte/{id}
- [x] GET /api/crm/kunden/{id}/aktivitaeten?projekt_id=X
- [x] GET /api/crm/kunden/{id}/stammdaten
- [x] JS: crmLoadKundenakte(), crmSwitchProject(), crmLoadTimeline()

## Paket 6 — Fallansicht (Ticket-Layer) ✅
- [x] _build_crm_fallansicht() — HTML aus Mockup
- [x] Ticket-Kopf (Nummer, Titel, Typ, Status, Priorität)
- [x] Timeline alle Quellen (Mail, Kira, Memo, Dokument, Lexware, manuell)
- [x] Aktionen (E-Mail, Notiz, Dokument, Status, Kira, Export)
- [x] Streitfall-Ansicht (_build_crm_streitfall)
- [x] GET /api/crm/kunden/{id}/faelle?projekt_id=X
- [x] POST /api/crm/faelle
- [x] GET /api/crm/faelle/{id}
- [x] PUT /api/crm/faelle/{id}
- [x] POST /api/crm/faelle/{id}/aktivitaeten
- [x] GET /api/crm/faelle/{id}/export
- [x] JS: crmLoadFall(), crmUpdateFallStatus(), crmAddAktivitaet()

## Paket 7 — Funktionspflicht ✅
- [x] Kontakt bearbeiten → Formular
- [x] Neuer Kunde → Formular
- [x] Verlaufseintrag klicken → Detail
- [x] Neue E-Mail → Compose-Fenster
- [x] Neue Rechnung/Angebot → Lexware-Modul
- [x] Neuer Fall → Erstell-Dialog
- [x] Export/Streitfall → Streitfall-Dossier-Modal mit JSON-Export + Herunterladen + Kopieren
- [x] Kira fragen → Workspace mit Kontext
- [x] Projekt wechseln → Dropdown + Filter
- [x] Fall-Status ändern → In-place

## Paket 8 — Kira + Einstellungen + Runtime-Log + Tour ✅
- [x] Kira-Tool: kunden_suchen
- [x] Kira-Tool: kundenakte_laden
- [x] Kira-Tool: crm_projekt_zuordnen
- [x] Kira-Tool: crm_fall_erstellen
- [x] Kira-Tool: crm_fall_oeffnen
- [x] Kira-Tool: crm_kunden_klassifizieren
- [x] Kira-Tool: crm_aktivitaeten_pruefliste
- [x] System-Prompt-Erweiterung (Top 5, offene Fälle, unzugeordnete)
- [x] 5 Quick-Actions im Kira-Workspace
- [x] Einstellungen-Sektion "Kunden / CRM" (10 Optionen)
- [x] Runtime-Log-Events via elog() (13 implementiert)
- [x] Guided Tour (6 Schritte)

## Paket-Abschluss
- [x] Git Commit
- [x] session_handoff.json aktualisiert
- [x] feature_registry.json aktualisiert (4 neue CRM-Einträge, kunden-360 + crm-pipeline aktualisiert)
- [x] KIRA_SYSTEM_ANALYSE.md aktualisiert (Sektion 8.5, Modul-Inventar, Changelog)
- [x] KUNDEN_MASTERCHECKLISTE.md Punkte abgehakt
- [x] session_log.md Zwischeneintrag
