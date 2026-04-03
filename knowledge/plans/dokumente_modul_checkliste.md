# Dokumente-Modul — Umsetzungs-Checkliste

> Stand: 2026-04-03 · Session: eeee-dokumente

## Phase A — Backend-Fundament

- [ ] DB-Schema: `dokumente` Tabelle in tasks.db
- [ ] DB-Schema: `dokument_vorlagen` Tabelle
- [ ] `dokument_pipeline.py` — Import, OCR, Klassifizierung, Routing
- [ ] `dokument_storage.py` — Externe Ablage, Ordnerstruktur, Hash/Dedup
- [ ] watchdog-Integration: Überwachter Ordner
- [ ] vorgang_router.py erweitern: Dokument-Routing-Ziele
- [ ] Runtime-Log: Event-Typ "dokument" + Event-Typen
- [ ] config.json: `dokumente.*` Sektion
- [ ] Feature-Flag: `module.dokumente.aktiv`
- [ ] API-Endpoints: CRUD für Dokumente

## Phase B — Kira-Integration

- [ ] `_build_data_context()` um Dokumente erweitern
- [ ] Tool: `dokument_erstellen()`
- [ ] Tool: `dokument_suchen()`
- [ ] Tool: `dokument_zuordnen()`
- [ ] Mail-Anhänge als Dokumente registrieren

## Phase C — Dokument-Studio

- [ ] Quill-Editor einbinden (CDN)
- [ ] Vorlagen-CRUD (DB + API)
- [ ] Platzhalter-System (Jinja2)
- [ ] PDF-Export (weasyprint)
- [ ] DOCX-Export (docxtpl)
- [ ] Preview (iframe + mammoth.js)
- [ ] Briefkopf/Signatur-Auswahl
- [ ] Druck-Flow (PDF → window.print)

## Phase D — UI + Frontend

- [ ] Sidebar-Eintrag "Dokumente" mit Icon
- [ ] Dokumenten-Liste (Filter, Suche, Vorgangsbezug)
- [ ] Dokument-Detail-Ansicht
- [ ] Upload + Drag & Drop
- [ ] Studio-UI (3-Spalten)
- [ ] Einstellungen-Sektion "Dokumente"

## Phase E — Integration + Polish

- [ ] Dashboard-Widget "Neue Dokumente"
- [ ] Geschäft: Dokument-Verknüpfung
- [ ] Postfach: "Als Dokument speichern" Button
- [ ] Feature-Flag 3 Zustände (nicht gebucht / gesperrt / aktiv)
- [ ] Playwright-Tests

*Erstellt: 2026-04-03 22:35 · Session eeee-dokumente*
