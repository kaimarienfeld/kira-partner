# Dokumente-Modul — Runtime-Log-Plan

> Stand: 2026-04-03 · Session: eeee-dokumente

## Neuer Event-Typ: "dokument"

Ergänzt die bestehenden Typen (ui, kira, llm, system, settings).

## Event-Aktionen

| Aktion | Beschreibung | Payload |
|--------|-------------|---------|
| doc_import | Dokument importiert (Ordner/Upload/Mail) | quelle, dateityp, größe, pfad |
| doc_ocr | OCR durchgeführt | seiten, sprache, dauer_ms, textlänge |
| doc_classify | LLM-Klassifizierung | kategorie, konfidenz, dokumentrolle |
| doc_route | Routing-Entscheidung | erfordert_handlung, routing_ziel, zielmodul |
| doc_assign | Vorgang zugeordnet | vorgang_id, vorgang_typ, methode (auto/manuell) |
| doc_create | Dokument erstellt (Studio) | vorlage_id, dokumenttyp, platzhalter |
| doc_edit | Dokument bearbeitet | version_vorher, version_nachher |
| doc_export | Export erzeugt | format (pdf/docx), größe, briefkopf |
| doc_print | Druck ausgelöst | format, seiten |
| doc_share | Dokument geteilt | methode (mail/link), empfänger |
| doc_attach | An Mail angehängt | mail_id, dateiname |
| doc_approve | Freigabe erteilt | freigeber, stufe |
| doc_reject | Freigabe abgelehnt | freigeber, grund |
| doc_delete | Dokument gelöscht | grund, archiviert |
| doc_correct | Klassifizierung korrigiert | alt, neu, grund |
| doc_dedup | Dublette erkannt | original_id, hash |

## Logging-Aufruf

```python
elog("dokument", "doc_import", f"Dokument importiert: {dateiname}",
     modul="dokumente", context_type="dokument", context_id=dok_id,
     vollkontext={"quelle": "watched_folder", "dateityp": "pdf", ...})
```

*Erstellt: 2026-04-03 22:35 · Session eeee-dokumente*
