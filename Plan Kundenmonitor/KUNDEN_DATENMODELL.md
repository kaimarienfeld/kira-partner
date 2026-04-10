# Kunden CRM — Datenmodell

Stand: 2026-04-10  
Datenbank: `knowledge/kunden.db` (existiert bereits)

---

## Bestehende Tabellen (Ist-Zustand)

### kunden (1.432 Zeilen)
| Spalte | Typ | Beschreibung |
|---|---|---|
| id | INTEGER PK | Auto-Increment |
| email | TEXT | Haupt-E-Mail |
| name | TEXT | Anzeigename |
| erstkontakt | TEXT | Datum Erstkontakt |
| letztkontakt | TEXT | Datum letzter Kontakt |
| anzahl_mails | INTEGER | Zähler |
| hauptkanal | TEXT | Hauptkommunikationskanal |
| notiz | TEXT | Freitext |

### interaktionen (7.361 Zeilen)
Bleibt unverändert — wird weiterhin für Mail-Verlauf genutzt.

---

## Migration — ALTER TABLE kunden

Neue Spalten (via ALTER TABLE ADD COLUMN, try/except für Idempotenz):

| Spalte | Typ | Default | Beschreibung |
|---|---|---|---|
| firmenname | TEXT | NULL | Firmenname (Lexware-Quelle) |
| ansprechpartner | TEXT | NULL | Ansprechpartner-Name |
| kundentyp | TEXT | 'unbekannt' | geschaeft / privat / intern / unbekannt |
| status | TEXT | 'aktiv' | aktiv / inaktiv / lead / archiv |
| lexware_id | TEXT | NULL | Verknüpfung zu Lexware-Kontakt |
| kundenwert | REAL | 0 | Berechneter Kundenwert (EUR) |
| fit_score | REAL | 0 | Fit-Score 0-100 |
| zahlungsverhalten_score | REAL | 0 | Zahlungsverhalten 0-100 |
| risiko_score | REAL | 0 | Risiko-Score 0-100 |
| metadata_json | TEXT | '{}' | Erweiterbare Metadaten |
| aktualisiert_am | TEXT | NULL | ISO-Timestamp letzte Änderung |

---

## Neue Tabellen

### kunden_identitaeten
Alle bekannten Kontaktdaten eines Kunden. Ein Kunde kann mehrere E-Mails, Telefonnummern etc. haben.

```sql
CREATE TABLE IF NOT EXISTS kunden_identitaeten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kunden_id INTEGER NOT NULL,
    typ TEXT NOT NULL DEFAULT 'mail',
    -- typ: mail, telefon, firma, domain, lexware, social
    wert TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'wahrscheinlich',
    -- confidence: eindeutig, wahrscheinlich, pruefen, unklar
    verifiziert INTEGER NOT NULL DEFAULT 0,
    quelle TEXT DEFAULT 'auto',
    -- quelle: auto, manuell, lexware, mail_header, kira
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (kunden_id) REFERENCES kunden(id),
    UNIQUE(kunden_id, typ, wert)
);
CREATE INDEX IF NOT EXISTS idx_ki_wert ON kunden_identitaeten(LOWER(wert));
CREATE INDEX IF NOT EXISTS idx_ki_kunden ON kunden_identitaeten(kunden_id);
```

### kunden_projekte
Projekttrennung — ein Kunde hat mehrere Projekte über Jahre.

```sql
CREATE TABLE IF NOT EXISTS kunden_projekte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kunden_id INTEGER NOT NULL,
    projektname TEXT NOT NULL,
    projekttyp TEXT DEFAULT 'standard',
    status TEXT NOT NULL DEFAULT 'planung',
    -- status: planung, aktiv, abgeschlossen, archiv
    beginn_am TEXT,
    abschluss_am TEXT,
    beschreibung TEXT,
    auftragswert REAL DEFAULT 0,
    naechste_aktion TEXT,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
    aktualisiert_am TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (kunden_id) REFERENCES kunden(id)
);
CREATE INDEX IF NOT EXISTS idx_kp_kunden ON kunden_projekte(kunden_id);
CREATE INDEX IF NOT EXISTS idx_kp_status ON kunden_projekte(status);
```

### kunden_faelle
Ticket-ähnliche Geschäftsvorfälle — Erweiterung der Case Engine.

```sql
CREATE TABLE IF NOT EXISTS kunden_faelle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kunden_id INTEGER NOT NULL,
    projekt_id INTEGER,
    fall_typ TEXT NOT NULL DEFAULT 'anfrage',
    -- fall_typ: anfrage, angebot, nachfass, rechnung, reklamation,
    --           maengel, streitfall, intern, freigabe
    titel TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'offen',
    -- status: entwurf, offen, aktiv, warten_kunde, intern_blockiert,
    --         erledigt, eskalation, archiv
    prioritaet TEXT DEFAULT 'normal',
    -- prioritaet: niedrig, normal, hoch, kritisch
    naechste_aktion TEXT,
    faellig_am TEXT,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
    aktualisiert_am TEXT NOT NULL DEFAULT (datetime('now')),
    confidence_score REAL DEFAULT 0,
    auto_zugeordnet INTEGER DEFAULT 0,
    manuell_geprueft INTEGER DEFAULT 0,
    FOREIGN KEY (kunden_id) REFERENCES kunden(id),
    FOREIGN KEY (projekt_id) REFERENCES kunden_projekte(id)
);
CREATE INDEX IF NOT EXISTS idx_kf_kunden ON kunden_faelle(kunden_id);
CREATE INDEX IF NOT EXISTS idx_kf_projekt ON kunden_faelle(projekt_id);
CREATE INDEX IF NOT EXISTS idx_kf_status ON kunden_faelle(status);
```

### kunden_aktivitaeten
Timeline — alle Ereignisse aller Quellen für einen Kunden.

```sql
CREATE TABLE IF NOT EXISTS kunden_aktivitaeten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kunden_id INTEGER NOT NULL,
    projekt_id INTEGER,
    fall_id INTEGER,
    ereignis_typ TEXT NOT NULL DEFAULT 'manuell',
    -- ereignis_typ: mail, kira, memo, dokument, geschaeft, lexware, manuell, routing
    quelle_id TEXT,
    quelle_tabelle TEXT,
    zusammenfassung TEXT,
    volltext_auszug TEXT,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
    sichtbar_in_verlauf INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (kunden_id) REFERENCES kunden(id),
    FOREIGN KEY (projekt_id) REFERENCES kunden_projekte(id),
    FOREIGN KEY (fall_id) REFERENCES kunden_faelle(id)
);
CREATE INDEX IF NOT EXISTS idx_ka_kunden ON kunden_aktivitaeten(kunden_id);
CREATE INDEX IF NOT EXISTS idx_ka_projekt ON kunden_aktivitaeten(projekt_id);
CREATE INDEX IF NOT EXISTS idx_ka_fall ON kunden_aktivitaeten(fall_id);
CREATE INDEX IF NOT EXISTS idx_ka_zeit ON kunden_aktivitaeten(erstellt_am);
```

### kunden_classifier_log
Protokolliert jede LLM-Klassifizierungsentscheidung — für Nachvollziehbarkeit und Lerneffekt.

```sql
CREATE TABLE IF NOT EXISTS kunden_classifier_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    eingabe_typ TEXT NOT NULL,
    -- eingabe_typ: mail, memo, dokument
    eingabe_id TEXT,
    kunden_id_vorschlag INTEGER,
    projekt_id_vorschlag INTEGER,
    fall_typ_vorschlag TEXT,
    confidence TEXT NOT NULL DEFAULT 'unklar',
    reasoning_kurz TEXT,
    llm_modell TEXT,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
    user_bestaetigt INTEGER DEFAULT 0,
    user_korrektur_kunden_id INTEGER,
    user_korrektur_projekt_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_cl_eingabe ON kunden_classifier_log(eingabe_typ, eingabe_id);
CREATE INDEX IF NOT EXISTS idx_cl_zeit ON kunden_classifier_log(erstellt_am);
```

---

## Initiale Datenmigration

Nach Tabellenerstellung:
1. Bestehende `kunden.email` → je 1 Eintrag in `kunden_identitaeten` (typ='mail', confidence='wahrscheinlich', quelle='migration')
2. Lexware-Sync: Wenn Lexware verfügbar → `lexware_id` füllen, `firmenname` + `ansprechpartner` aus Lexware
3. Bestehende Interaktionen analysieren: Domain-Extraktion → `kunden_identitaeten` (typ='domain')
