# Dokumente-Modul — Umsetzungs-Checkliste

> Stand: 2026-04-03 23:45 · Session: eeee-dokumente

## Phase A — Backend-Fundament

- [x] ✅ DB-Schema: `dokumente` Tabelle (26 Spalten) · 2026-04-03 22:50
- [x] ✅ DB-Schema: `dokument_vorlagen` Tabelle (13 Spalten) + `dokument_briefkoepfe` (13 Spalten) · 2026-04-03 22:50
- [x] ✅ `dokument_pipeline.py` — Import, OCR, Klassifizierung, Routing (~400 Zeilen) · 2026-04-03 23:00
- [x] ✅ `dokument_storage.py` — Externe Ablage, Ordnerstruktur, Hash/Dedup (~350 Zeilen) · 2026-04-03 22:50
- [x] ✅ watchdog-Integration: Überwachter Ordner (start_folder_watcher + debounce) · 2026-04-03 23:00
- [ ] ⚠️ vorgang_router.py erweitern: Dokument-Routing-Ziele — offen (Phase E)
- [ ] ⚠️ Runtime-Log: Event-Typ "dokument" + Event-Typen — Plan erstellt, noch nicht verdrahtet
- [x] ✅ config.json: `dokumente.*` Sektion (16 Einstellungen) · 2026-04-03 22:45
- [x] ✅ Feature-Flag: `dokumente.feature_status` (3 Zustände) · 2026-04-03 22:45
- [x] ✅ API-Endpoints: 20 Endpoints (10 GET + 10 POST) · 2026-04-03 23:30

## Phase B — Kira-Integration

- [x] ✅ `_build_data_context()` um Dokumente erweitern (letzte 15 Docs) · 2026-04-03 23:05
- [x] ✅ Tool: `dokument_erstellen()` · 2026-04-03 23:05
- [x] ✅ Tool: `dokument_suchen()` · 2026-04-03 23:05
- [x] ✅ Tool: `dokument_zuordnen()` · 2026-04-03 23:05
- [ ] ⚠️ Mail-Anhänge als Dokumente registrieren — offen (Phase E)

## Phase C — Dokument-Studio

- [x] ✅ Quill-Editor einbinden (CDN) · 2026-04-03 23:15
- [x] ✅ Vorlagen-CRUD (DB + API) · 2026-04-03 23:15
- [x] ✅ Platzhalter-System (Variablen-Insert + Vorlagen-Load) · 2026-04-03 23:15
- [x] ✅ PDF-Export (weasyprint) · 2026-04-03 23:20
- [x] ✅ DOCX-Export (docxtpl + python-docx) · 2026-04-03 23:20
- [x] ✅ Preview (iframe) · 2026-04-03 23:25
- [x] ✅ Briefkopf/Signatur-CRUD (DB + API) · 2026-04-03 22:50
- [x] ✅ Druck-Flow (window.print via Studio) · 2026-04-03 23:25

## Phase D — UI + Frontend

- [x] ✅ Sidebar-Eintrag "Dokumente" mit Badge · 2026-04-03 23:30
- [x] ✅ Dokumenten-Liste (Filter nach Status, Suche) · 2026-04-03 23:30
- [x] ✅ Dokument-Detail-Ansicht (Preview-Overlay) · 2026-04-03 23:30
- [x] ✅ Upload + Drag & Drop · 2026-04-03 23:30
- [x] ✅ Studio-UI (Overlay mit Quill + Toolbar) · 2026-04-03 23:25
- [x] ✅ Einstellungen-Sektion "Dokumente" + saveSettings() · 2026-04-03 23:40
- [x] ✅ CSS-Klassen (.dok-nav-item/.dok-status-card/.dok-list-item/.dok-drop-zone) · 2026-04-03 23:40

## Phase E — Integration + Polish (offen)

- [ ] Dashboard-Widget "Neue Dokumente"
- [ ] Geschäft: Dokument-Verknüpfung mit Vorgängen
- [ ] Postfach: "Als Dokument speichern" Button
- [ ] vorgang_router.py: Dokument-Routing-Ziele
- [ ] Runtime-Log: Event-Typ "dokument" verdrahten
- [ ] Mail-Anhänge automatisch als Dokumente registrieren
- [ ] Playwright-Tests
- [ ] pip install weasyprint docxtpl python-docx mammoth pytesseract watchdog

**Commit:** 49fa685
*Aktualisiert: 2026-04-03 23:45 · Session eeee-dokumente*
