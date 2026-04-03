# Dokumente-Modul — Stack-Recherche

> Stand: 2026-04-03 · Session: eeee-dokumente

## Empfohlener v1-Stack (sofort umsetzbar)

| Bereich | Library | Lizenz | Install |
|---------|---------|--------|---------|
| Editor | Quill 1.3.x | BSD-3 | CDN (43 KB) |
| PDF-Erzeugung | weasyprint | BSD-3 | `pip install weasyprint` |
| DOCX-Erzeugung | docxtpl | MIT | `pip install docxtpl` |
| Preview PDF | iframe/embed | — | 0 KB |
| Preview DOCX | mammoth.js | MIT | CDN (70 KB) |
| Templates | Jinja2 | BSD-3 | bereits vorhanden |
| OCR | pytesseract | Apache-2.0 | `pip install pytesseract` + Tesseract-OCR.exe |
| Watched Folder | watchdog | Apache-2.0 | `pip install watchdog` |

## v2-Upgrades (vorbereitet, nicht gebaut)

| Bereich | v2-Option | Grund für Upgrade |
|---------|-----------|-------------------|
| Editor | TinyMCE (Self-Host) | Mehr Formatierung, Tabellen, Vorlagen-Dialoge |
| OCR | EasyOCR | Bessere Handschrift-Erkennung |
| PDF | pdfkit + wkhtmltopdf | Fallback wenn weasyprint Probleme macht |
| Preview | pdf.js | Custom-Rendering, Annotationen |

## Pip-Requirements (v1)

```
weasyprint>=60.0
docxtpl>=0.16.0
pytesseract>=0.3.10
watchdog>=3.0.0
Pillow>=10.0.0
```

*Erstellt: 2026-04-03 22:35 · Session eeee-dokumente*
