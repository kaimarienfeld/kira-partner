# Dokumente-Modul — Vorlagen-Plan

> Stand: 2026-04-03 · Session: eeee-dokumente

## DB-Schema: dokument_vorlagen

```sql
CREATE TABLE IF NOT EXISTS dokument_vorlagen (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    kategorie     TEXT,           -- brief, rechnung, angebot, mahnung, memo, protokoll, frei
    dokumenttyp   TEXT DEFAULT 'html',  -- html, docx
    inhalt        TEXT,           -- HTML (Quill) oder DOCX-Pfad
    briefkopf_id  INTEGER,
    signatur_id   INTEGER,
    platzhalter   TEXT,           -- JSON: [{key, label, typ, default}]
    kira_aktiv    INTEGER DEFAULT 0,
    aktiv         INTEGER DEFAULT 1,
    version       INTEGER DEFAULT 1,
    erstellt      TEXT,
    geaendert     TEXT
);
```

## Platzhalter-System

Jinja2-Variablen: `{{ kunde.name }}`, `{{ vorgang.betreff }}`, `{{ datum }}`, `{{ firma.name }}`

Verfügbare Kontexte:
- `kunde.*` — Name, Firma, Adresse, E-Mail
- `vorgang.*` — Betreff, Typ, Status, Datum
- `firma.*` — rauMKult-Stammdaten
- `datum`, `datum_lang`, `jahr`, `monat`
- `rechnung.*` — Nummer, Betrag, Fällig
- `angebot.*` — Nummer, Betrag, Gültig bis

## Dokumenttypen die erzeugt werden können

Mahnung, Zahlungserinnerung, Rechnung, Angebot, Brief, Anschreiben, Begleitschreiben, internes Memo, Auswertung, Protokoll, freie Vorlage

## Briefkopf

Wiederverwendbar aus mail_signaturen oder eigene `dokument_briefkoepfe` Tabelle. Enthält: Logo, Firmenname, Adresse, Kontakt, Bankverbindung, Steuernummer.

*Erstellt: 2026-04-03 22:35 · Session eeee-dokumente*
