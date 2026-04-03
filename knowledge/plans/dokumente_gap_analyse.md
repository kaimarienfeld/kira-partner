# Dokumente-Modul — Gap-Analyse Ist/Soll

> Stand: 2026-04-03 · Session: eeee-dokumente

---

## Legende

| Symbol | Bedeutung |
|--------|-----------|
| ✅ | Vorhanden und korrekt |
| 🔧 | Vorhanden, aber anpassen/erweitern |
| ⚠️ | Vorhanden, aber falsch gedacht/verdrahtet |
| 🆕 | Vollständig fehlend — neu bauen |

---

## 1. Dokument-Eingang & Verarbeitung

| Funktion | Ist-Zustand | Soll | Status |
|----------|------------|------|--------|
| PDF-Textextraktion | `scan_dokumente.py` mit pdfplumber | Beibehalten + erweitern | ✅ |
| OCR für Bild-Scans | Nicht vorhanden | pytesseract + Tesseract-OCR | 🆕 |
| DOCX-Parsing | Nicht vorhanden | python-docx zum Lesen | 🆕 |
| Watched Folder | Nicht vorhanden | watchdog-basiert, konfigurierbar | 🆕 |
| Datei-Upload | `capture`-Modul in server.py (Zeile 28796) | Erweitern auf Dokumente-Kontext | 🔧 |
| Drag & Drop | Nicht vorhanden | JS im Dokumente-Panel | 🆕 |
| Mail-Anhang → Dokument | Anhänge indiziert (hat_anhaenge, anhaenge JSON) aber nicht als Dokumente registriert | Automatisch als Dokument anlegen + verknüpfen | 🔧 |
| Dedup/Hash | `scan_dokumente.py` hat Suffix-Dedup | SHA256-Hash + DB-Prüfung | 🔧 |

---

## 2. Klassifizierung & Routing

| Funktion | Ist-Zustand | Soll | Status |
|----------|------------|------|--------|
| LLM-Klassifizierung | `llm_classifier.py` für Mails | Erweitern auf Dokumente | 🔧 |
| Routing-Schicht | `vorgang_router.py` (KATEGORIE_ZU_VORGANG_TYP) | Erweitern: erfordert_handlung + routing-ziel | 🔧 |
| Routing-Ziele | task/vorgang nur | task, buchhaltung, feed, kira_vorschlag, archivieren, manuelle_pruefung | 🔧 |
| Case Engine Anbindung | `case_engine.py` voll funktional für Mails | Dokumente als weitere Entity einbinden | 🔧 |
| Dokumentrolle/-typ | Nicht vorhanden | Quelltyp + Dokumentrolle + Tags | 🆕 |

---

## 3. Datenbank

| Funktion | Ist-Zustand | Soll | Status |
|----------|------------|------|--------|
| Dokumente-Tabelle | Nicht vorhanden | `dokumente` in tasks.db | 🆕 |
| Dokument-Vorgang-Link | `vorgang_links` existiert für tasks/angebote/rechnungen | Link-Typ "dokument" hinzufügen | 🔧 |
| Dokument-Metadaten | Nur für Mails (mail_index.db) | Eigene Tabelle mit Hash, Pfad, OCR, Klassifizierung | 🆕 |
| Vorlagen-Tabelle | `mail_vorlagen` existiert (server.py:248) | Separate `dokument_vorlagen` oder erweitern | 🔧 |
| Signaturen | `mail_signaturen` vorhanden (server.py:227) | Beibehalten, für Dokumente mitnutzen | ✅ |

---

## 4. Dokument-Studio (Erstellen & Bearbeiten)

| Funktion | Ist-Zustand | Soll | Status |
|----------|------------|------|--------|
| Rich-Text-Editor | Nicht vorhanden | Quill (CDN, WYSIWYG) | 🆕 |
| PDF-Export | Nicht vorhanden | weasyprint | 🆕 |
| DOCX-Export | `ausgabe/gen_docx.py` (Basis-Demo) | docxtpl + Jinja2-Vorlagen | 🔧 |
| Preview PDF | Nicht vorhanden | iframe/embed | 🆕 |
| Preview DOCX | Nicht vorhanden | mammoth.js | 🆕 |
| Briefkopf-Verwaltung | Nicht vorhanden | Einstellungen + Vorlage | 🆕 |
| Platzhalter-System | Nicht explizit | Jinja2 {{ }} durchgängig | 🆕 |
| Druck | Nur Browser-CSS-Print | weasyprint-PDF → Druck-Dialog | 🆕 |
| An Mail anhängen | Nicht vorhanden | Dokument → Mail-Compose als Anhang | 🆕 |
| Versionierung | Nicht vorhanden | Version-Counter + Archiv-Pfad | 🆕 |

---

## 5. Kira-Integration

| Funktion | Ist-Zustand | Soll | Status |
|----------|------------|------|--------|
| Kira-Kontext Dokumente | Nicht vorhanden (nur Mail/Task/Rechnung/Angebot) | Dokument-Metadaten + Preview in _build_data_context | 🆕 |
| Tool: dokument_erstellen | Nicht vorhanden | Kira erzeugt Dokument aus Vorlage | 🆕 |
| Tool: dokument_suchen | Nicht vorhanden | Kira sucht Dokumente nach Kriterien | 🆕 |
| Tool: dokument_zuordnen | Nicht vorhanden | Kira ordnet Dokument einem Vorgang zu | 🆕 |
| Kira darf Vorlagen nutzen | `kira_aktiv` Flag in mail_vorlagen | Für Dokument-Vorlagen übernehmen | 🔧 |

---

## 6. UI & Frontend

| Funktion | Ist-Zustand | Soll | Status |
|----------|------------|------|--------|
| Sidebar "Dokumente" | Nicht vorhanden | Eigener Hauptpunkt mit Icon | 🆕 |
| Dokumenten-Liste | Nicht vorhanden | Filter, Suche, Vorgangsbezug, Status | 🆕 |
| Dokument-Detail | Nicht vorhanden | Preview + Metadaten + Aktionen | 🆕 |
| Studio-UI | Nicht vorhanden | 3-Spalten: Vorlagen/Editor/Aktionen | 🆕 |
| Dashboard-Widget | Nicht vorhanden | "Neue Dokumente" Karte | 🆕 |
| Postfach Anhang→Dokument | Nur Anhang-Flag sichtbar | Button "Als Dokument speichern" | 🆕 |
| Geschäft Dokument-Link | Nicht vorhanden | Rechnung/Angebot → zugehörige Dokumente | 🆕 |

---

## 7. Einstellungen

| Funktion | Ist-Zustand | Soll | Status |
|----------|------------|------|--------|
| Überwachte Ordner | Nicht vorhanden | Pfad + Unterordner + Intervall | 🆕 |
| Dateitypen-Filter | Nicht vorhanden | PDF, DOCX, JPG, PNG etc. | 🆕 |
| OCR-Einstellungen | Nicht vorhanden | Aktiv/Inaktiv, Sprache, Qualität | 🆕 |
| Externe Ablage-Pfad | Nicht vorhanden | Hauptspeicherort konfigurierbar | 🆕 |
| Ordnerstruktur-Regel | Nicht vorhanden | Jahr/Kunde/Vorgang/Quelle | 🆕 |
| Dublettenerkennung | Nicht vorhanden | Hash-basiert, Ein/Aus | 🆕 |
| Vorlagen-Verwaltung | mail_vorlagen vorhanden | Eigene Sektion für Dokument-Vorlagen | 🔧 |
| Briefkopf/Signatur | mail_signaturen vorhanden | Erweitern auf Dokument-Briefköpfe | 🔧 |
| Kira-Regeln | kira.kontext_* vorhanden | + kontext_dokumente, darf_erstellen | 🔧 |
| Feature-Flag | Nicht vorhanden | module.dokumente.aktiv | 🆕 |

---

## 8. Runtime-Log

| Funktion | Ist-Zustand | Soll | Status |
|----------|------------|------|--------|
| Event-Typ "dokument" | Nicht vorhanden | Neuer Typ in runtime_log.py | 🆕 |
| Import-Events | Nicht vorhanden | doc_import, doc_scan, doc_ocr | 🆕 |
| Klassifizierungs-Events | Nur für Mail (llm_classifier) | doc_classify, doc_route | 🆕 |
| Studio-Events | Nicht vorhanden | doc_create, doc_edit, doc_export | 🆕 |
| Routing-Events | Nicht vorhanden | routing_decision, zielmodul | 🆕 |
| Freigabe-Events | Nicht vorhanden | doc_approve, doc_reject | 🆕 |

---

## 9. Feature-Flag / Lizenz

| Funktion | Ist-Zustand | Soll | Status |
|----------|------------|------|--------|
| Feature-Flag System | feature_registry.json (nur Tracking) | config.json Flag + Backend-Gate + UI-Gate | 🆕 |
| 3 Zustände | Nicht vorhanden | nicht_gebucht, sichtbar_gesperrt, freigeschaltet | 🆕 |
| API-Gate | Nicht vorhanden | Check vor jedem /api/dokument/* Endpoint | 🆕 |
| UI-Gate | Nicht vorhanden | Sidebar ausblenden/sperren je nach Status | 🆕 |
| Hintergrund-Gate | Nicht vorhanden | Watcher/Scanner nur wenn freigeschaltet | 🆕 |

---

## Zusammenfassung

| Kategorie | ✅ | 🔧 | ⚠️ | 🆕 | Gesamt |
|-----------|----|----|----|----|--------|
| Eingang/Verarbeitung | 1 | 3 | 0 | 4 | 8 |
| Klassifizierung/Routing | 0 | 4 | 0 | 1 | 5 |
| Datenbank | 1 | 2 | 0 | 2 | 5 |
| Dokument-Studio | 0 | 1 | 0 | 9 | 10 |
| Kira-Integration | 0 | 1 | 0 | 4 | 5 |
| UI/Frontend | 0 | 0 | 0 | 7 | 7 |
| Einstellungen | 0 | 3 | 0 | 7 | 10 |
| Runtime-Log | 0 | 0 | 0 | 6 | 6 |
| Feature-Flag | 0 | 0 | 0 | 5 | 5 |
| **Gesamt** | **2** | **14** | **0** | **45** | **61** |

**Fazit:** 2 Bausteine direkt nutzbar, 14 müssen erweitert werden, 45 neu zu bauen. Kein falsch Verdrahtetes gefunden (⚠️=0) — gute Ausgangslage.

---

*Erstellt: 2026-04-03 22:30 · Session eeee-dokumente*
