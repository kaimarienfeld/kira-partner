# Dokumente-Modul — Masterplan

> Stand: 2026-04-03 · Session: eeee-dokumente
> Status: Planungsphase — keine Implementierung vor Freigabe

---

## 1. Zielbild

KIRA bekommt ein vollwertiges **Dokumente**-Modul als zweite zentrale Quelle neben Mail.

**Zwei Betriebsarten:**
- **A. Eingang/Verarbeitung** — überwachter Ordner, Uploads, Mail-Anhänge, Scans, OCR, Klassifizierung, Routing
- **B. Dokument-Studio** — Erstellen, Vorlagen, Editor, Export (PDF/DOCX), Druck, Teilen, Anhängen, Versionierung

**Kernprinzip:** Dokumente = gleichwertige Quelle neben Mail → Vorgang = Arbeitsobjekt.

---

## 2. Scope

### In Scope (v1)
- Sidebar-Eintrag "Dokumente" mit Sub-Navigation
- Watched-Folder-Überwachung (watchdog)
- Datei-Upload / Drag & Drop
- OCR für gescannte PDFs/Bilder (pytesseract)
- LLM-Klassifizierung + Routing-Schicht (erfordert_handlung, routing-ziel)
- Dokument-Metadaten in DB (nicht Dateien selbst)
- Externe strukturierte Ablage (konfigurierbar in Einstellungen)
- Dokument-Studio mit Quill-Editor
- PDF-Erzeugung (weasyprint)
- DOCX-Erzeugung (docxtpl/Jinja2)
- Preview (iframe PDF, mammoth.js DOCX)
- Vorlagen-System (Jinja2-Platzhalter)
- Vorgangsbezug (case_engine Integration)
- Kira-Kontext-Erweiterung (Dokumente als Datenquelle)
- Runtime-Log-Integration (Dokument-Events)
- Einstellungen-Sektion "Dokumente"
- Feature-Flag / Lizenz-Vorbereitung

### In Scope (v2 — vorbereitet, nicht gebaut)
- TinyMCE als Editor-Upgrade
- EasyOCR für Handschrift
- OneDrive/Cloud-Integration
- WhatsApp/Instagram-Dokument-Eingang
- Freigabe-Workflows
- Versionierung mit Diff
- Premium/Abo-Splitting
- Multi-User-Rechte

### Out of Scope
- Mobile App
- Cloud-Hosting
- E-Signatur
- Volltextsuche über alle Dokumente (v3)

---

## 3. Architekturübersicht

```
┌─────────────────────────────────────────────────────┐
│                    QUELLEN                           │
│  Watched Folder │ Upload │ Mail-Anhang │ Kira │ Scan │
└────────┬────────┴────┬───┴──────┬──────┴──┬───┴─────┘
         │             │          │         │
         ▼             ▼          ▼         ▼
┌─────────────────────────────────────────────────────┐
│              DOKUMENT-PIPELINE                       │
│  1. Import → 2. OCR/Text → 3. LLM-Klassifizierung  │
│  4. Routing-Entscheidung → 5. Vorgangszuordnung     │
└────────────────────┬────────────────────────────────┘
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
    ┌─────────┐ ┌─────────┐ ┌──────────┐
    │  task   │ │  feed   │ │ archiv   │
    │ buchh.  │ │ kira_v. │ │ man.prüf │
    └─────────┘ └─────────┘ └──────────┘
         │           │           │
         ▼           ▼           ▼
┌─────────────────────────────────────────────────────┐
│              ZIELMODULE                              │
│  Kommunikation │ Geschäft │ Organisation │ Wissen   │
│  Kira-Workspace │ Dashboard │ Dokumente-Archiv      │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│              DOKUMENT-STUDIO                         │
│  Quill-Editor │ Vorlagen │ Platzhalter │ Preview    │
│  PDF-Export │ DOCX-Export │ Druck │ Teilen │ Anhang  │
└─────────────────────────────────────────────────────┘
```

### Dateispeicherung

```
Externe Ablage (konfigurierbar):
  {dokumente_pfad}/
    ├── {jahr}/
    │   ├── {kunde_oder_vorgang}/
    │   │   ├── eingang/
    │   │   ├── ausgang/
    │   │   └── intern/
    │   └── sonstige/
    └── vorlagen/

Kira-DB speichert nur:
  - Metadaten, Hash, Pfad, OCR-Text, Klassifizierung
  - Vorgangsbezug, Tags, Status, Routing-Entscheidung
```

---

## 4. Umsetzungsphasen

### Phase A — Fundament (Backend)
1. DB-Schema: `dokumente` Tabelle in tasks.db
2. `dokument_pipeline.py` — Import, OCR, Klassifizierung, Routing
3. `dokument_storage.py` — Externe Ablage, Ordnerstruktur, Hash/Dedup
4. watchdog-Integration für überwachten Ordner
5. Vorgang-Router um Dokument-Routing erweitern
6. Runtime-Log Event-Typen für Dokumente
7. Config-Schema erweitern (dokumente.* Sektion)

### Phase B — Kira-Integration
1. Kira-Kontext: `_build_data_context()` um Dokumente erweitern
2. Kira-Tools: `dokument_erstellen()`, `dokument_suchen()`, `dokument_zuordnen()`
3. Mail-Anhänge als Dokumente registrieren

### Phase C — Dokument-Studio
1. Quill-Editor einbinden (CDN)
2. Vorlagen-System (DB + Jinja2)
3. PDF-Export (weasyprint)
4. DOCX-Export (docxtpl)
5. Preview (iframe + mammoth.js)
6. Briefkopf/Signatur-Verwaltung

### Phase D — UI + Frontend
1. Sidebar-Eintrag "Dokumente"
2. Dokumenten-Liste mit Filter/Suche
3. Dokument-Detail-Ansicht
4. Upload/Drag&Drop
5. Studio-UI (3-Spalten)
6. Einstellungen-Sektion

### Phase E — Integration + Polish
1. Dashboard-Widget "Neue Dokumente"
2. Geschäft: Rechnungen/Angebote als Dokumente verknüpfen
3. Postfach: Anhang → Dokument-Button
4. Feature-Flag vorbereiten
5. Tests via Playwright

---

## 5. Risiken

| Risiko | Schwere | Mitigation |
|--------|---------|------------|
| weasyprint Windows-Install | Mittel | Fallback: pdfkit + wkhtmltopdf |
| Tesseract Windows-Install | Mittel | MSI-Installer, Pfad in config.json |
| watchdog Doppel-Events | Niedrig | Debounce-Wrapper (0.5s) |
| DB-Größe durch OCR-Texte | Mittel | TEXT-Spalte, kein BLOB |
| Mail-Anhang-Verknüpfung | Mittel | Schrittweise: erst neue, dann Backfill |
| Editor-Kompatibilität | Niedrig | Quill ist breit getestet |

---

## 6. Offene Punkte

- [ ] Tesseract-OCR Installationspfad für Windows klären
- [ ] weasyprint Windows-Wheel Kompatibilität verifizieren
- [ ] Kai: Gewünschte Ordnerstruktur für externe Ablage bestätigen
- [ ] Kai: Soll Dokumente sofort als eigener Sidebar-Punkt oder unter Geschäft?
- [ ] Feature-Flag-Konzept: Einfaches `config.json` Flag oder separates Lizenz-System?
- [ ] Vorlagen-Design: Soll Kai DOCX-Vorlagen in Word erstellen oder im Editor?

---

*Erstellt: 2026-04-03 22:30 · Session eeee-dokumente*
