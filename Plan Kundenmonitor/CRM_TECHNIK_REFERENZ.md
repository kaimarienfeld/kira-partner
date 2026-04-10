# CRM / Kundencenter — Vollständige Technik-Referenz

**Stand:** 2026-04-10 | **Sessions:** session-ss, session-tt | **Commits:** `9bc5594`, `438371a`, `350bd96`

---

## 1. Beteiligte Dateien

| Datei | Aktion | Umfang |
|---|---|---|
| `scripts/server.py` | Erweitert | ~2.900 neue Zeilen (UI + API + JS + CSS) |
| `scripts/kunden_classifier.py` | **NEU** | ~620 Zeilen (Lexware-Only-Basis seit session-tt) |
| `scripts/kunden_lexware_sync.py` | **NEU** (session-tt) | ~280 Zeilen — Lexware → kunden.db Sync |
| `scripts/kunden_mail_retroaktiv.py` | **NEU** (session-tt) | ~200 Zeilen — Retroaktiver Mail-Scan |
| `scripts/kira_llm.py` | Erweitert | ~280 neue Zeilen (7 Tools + Handler + Kontext) |
| `scripts/case_engine.py` | Erweitert | `_ensure_crm_tables()` — 6 Tabellen (Migration entfernt session-tt) |
| `scripts/mail_classifier.py` | Erweitert | Geschäftskontakt-Filter (~30 Zeilen) |
| `scripts/mail_monitor.py` | Erweitert | Classifier-Aufruf nach vorgang_router (~20 Zeilen) |
| `scripts/daily_check.py` | Erweitert | Classifier-Aufruf bei Nachklassifizierung (~20 Zeilen) |
| `knowledge/kunden.db` | Repariert (session-tt) | 273 Lexware-Kunden, 285 Identitäten, 1.718 Aktivitäten |

---

## 2. Datenbank — `knowledge/kunden.db`

### 2.1 Bestehende Tabelle `kunden` — ALTER TABLE (11 neue Spalten)

| Spalte | Typ | Default | Zweck |
|---|---|---|---|
| `firmenname` | TEXT | — | Firmenname (separat von `name`) |
| `ansprechpartner` | TEXT | — | Ansprechpartner bei Firma |
| `kundentyp` | TEXT | `'unbekannt'` | `geschaeft` / `privat` / `intern` / `unbekannt` |
| `status` | TEXT | `'aktiv'` | `aktiv` / `inaktiv` / `lead` / `archiv` |
| `lexware_id` | TEXT | — | Verknüpfung zu Lexware Office Kontakt |
| `kundenwert` | REAL | `0` | Geschätzter Kundenwert (EUR) |
| `fit_score` | REAL | `0` | Wie gut passt der Kunde (0-1) |
| `zahlungsverhalten_score` | REAL | `0` | Zahlungsmoral (0-1) |
| `risiko_score` | REAL | `0` | Risiko-Einschätzung (0-1) |
| `metadata_json` | TEXT | `'{}'` | Freiform-JSON für Zusatzdaten |
| `aktualisiert_am` | TEXT | — | Letztes Update-Datum |

### 2.2 Neue Tabelle `kunden_identitaeten`

Speichert alle bekannten Kontaktdaten eines Kunden (E-Mails, Telefon, Domain, etc.).

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | INTEGER PK | Auto-Increment |
| `kunden_id` | INTEGER FK → kunden.id | Zugehöriger Kunde |
| `typ` | TEXT | `mail` / `telefon` / `firma` / `domain` / `lexware` / `social` |
| `wert` | TEXT | Der eigentliche Wert (z.B. `kunde@firma.de`) |
| `confidence` | TEXT | `eindeutig` / `wahrscheinlich` / `prüfen` / `unklar` |
| `verifiziert` | INTEGER | 0 = nicht verifiziert, 1 = manuell bestätigt |
| `quelle` | TEXT | `auto` / `manuell` / `migration` / `llm` |
| `erstellt_am` | TEXT | Zeitstempel |

**Indizes:** `idx_ki_wert` (LOWER(wert)), `idx_ki_kunden` (kunden_id)
**UNIQUE:** `(kunden_id, typ, wert)`

**Initiale Migration:** Bestehende `kunden.email` → automatisch in `kunden_identitaeten` kopiert (confidence=`wahrscheinlich`, quelle=`migration`).

### 2.3 Neue Tabelle `kunden_projekte`

Projekttrennung: Ein Kunde hat mehrere Projekte (z.B. "Küche 2023", "Bad 2026").

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | INTEGER PK | Auto-Increment |
| `kunden_id` | INTEGER FK → kunden.id | Zugehöriger Kunde |
| `projektname` | TEXT NOT NULL | Name des Projekts |
| `projekttyp` | TEXT | `standard` / `reklamation` / `wartung` / etc. |
| `status` | TEXT | `planung` / `aktiv` / `abgeschlossen` / `archiv` |
| `beginn_am` | TEXT | Projektstart |
| `abschluss_am` | TEXT | Projektende |
| `beschreibung` | TEXT | Freitext-Beschreibung |
| `auftragswert` | REAL | Geplanter/tatsächlicher Auftragswert (EUR) |
| `naechste_aktion` | TEXT | Was steht als nächstes an |
| `erstellt_am` | TEXT | Zeitstempel |
| `aktualisiert_am` | TEXT | Letztes Update |

**Indizes:** `idx_kp_kunden`, `idx_kp_status`

### 2.4 Neue Tabelle `kunden_faelle`

Ticket-Layer: Ein Fall = ein konkreter Geschäftsvorfall (Anfrage, Reklamation, Streitfall).

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | INTEGER PK | Auto-Increment |
| `kunden_id` | INTEGER FK → kunden.id | Zugehöriger Kunde |
| `projekt_id` | INTEGER FK → kunden_projekte.id | Optionales Projekt (nullable) |
| `fall_typ` | TEXT | `anfrage` / `angebot` / `reklamation` / `maengel` / `streitfall` / `allgemein` / `intern` / `freigabe` / `nachfass` / `rechnung` |
| `titel` | TEXT NOT NULL | Kurztitel des Falls |
| `status` | TEXT | `offen` / `in_bearbeitung` / `wartend` / `geloest` / `geschlossen` / `streitfall` |
| `prioritaet` | TEXT | `niedrig` / `normal` / `hoch` / `dringend` |
| `naechste_aktion` | TEXT | Was steht als nächstes an |
| `faellig_am` | TEXT | Fälligkeitsdatum |
| `erstellt_am` | TEXT | Zeitstempel |
| `aktualisiert_am` | TEXT | Letztes Update |
| `confidence_score` | REAL | Confidence des Classifiers bei Auto-Zuordnung |
| `auto_zugeordnet` | INTEGER | 1 = vom Classifier automatisch angelegt |
| `manuell_geprueft` | INTEGER | 1 = manuell bestätigt/korrigiert |

**Indizes:** `idx_kf_kunden`, `idx_kf_projekt`, `idx_kf_status`

### 2.5 Neue Tabelle `kunden_aktivitaeten`

Zentrale Timeline: Alle Ereignisse aus allen Quellen chronologisch verknüpft.

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | INTEGER PK | Auto-Increment |
| `kunden_id` | INTEGER FK → kunden.id | Zugehöriger Kunde |
| `projekt_id` | INTEGER FK (nullable) | Optionales Projekt |
| `fall_id` | INTEGER FK (nullable) | Optionaler Fall |
| `ereignis_typ` | TEXT | `mail` / `kira` / `memo` / `dokument` / `geschaeft` / `lexware` / `manuell` / `routing` |
| `quelle_id` | TEXT | ID in der Quell-Tabelle (z.B. mail_index rowid) |
| `quelle_tabelle` | TEXT | Name der Quell-Tabelle |
| `zusammenfassung` | TEXT | Kurztext für Timeline-Anzeige |
| `volltext_auszug` | TEXT | Längerer Textauszug |
| `erstellt_am` | TEXT | Zeitstempel |
| `sichtbar_in_verlauf` | INTEGER | 1 = wird im Verlauf angezeigt |

**Indizes:** `idx_ka_kunden`, `idx_ka_projekt`, `idx_ka_fall`, `idx_ka_zeit`

### 2.6 Neue Tabelle `kunden_classifier_log`

LLM-Entscheidungsprotokoll: Jede Klassifizierung wird protokolliert.

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | INTEGER PK | Auto-Increment |
| `eingabe_typ` | TEXT NOT NULL | `mail` / `task` / `manuell` |
| `eingabe_id` | TEXT | ID des Quell-Eintrags |
| `kunden_id_vorschlag` | INTEGER | Vorgeschlagener Kunde |
| `projekt_id_vorschlag` | INTEGER | Vorgeschlagenes Projekt |
| `fall_typ_vorschlag` | TEXT | Vorgeschlagener Fall-Typ |
| `confidence` | TEXT | `eindeutig` / `wahrscheinlich` / `prüfen` / `unklar` |
| `reasoning_kurz` | TEXT | Begründung des LLM (Kurztext) |
| `llm_modell` | TEXT | Welches LLM verwendet wurde |
| `erstellt_am` | TEXT | Zeitstempel |
| `user_bestaetigt` | INTEGER | 1 = manuell bestätigt |
| `user_korrektur_kunden_id` | INTEGER | Manuell korrigierter Kunde |
| `user_korrektur_projekt_id` | INTEGER | Manuell korrigiertes Projekt |

**Indizes:** `idx_cl_eingabe`, `idx_cl_zeit`

### 2.7 Tabellenbeziehungen (ER-Diagramm)

```
kunden (id)
  │
  ├─→ kunden_identitaeten (kunden_id FK)      1:n   Kontaktdaten
  ├─→ kunden_projekte (kunden_id FK)           1:n   Projekte
  │     │
  │     ├─→ kunden_faelle (projekt_id FK)      1:n   Fälle pro Projekt
  │     │     │
  │     │     └─→ kunden_aktivitaeten (fall_id FK)  1:n   Aktivitäten pro Fall
  │     │
  │     └─→ kunden_aktivitaeten (projekt_id FK) 1:n   Aktivitäten pro Projekt
  │
  ├─→ kunden_faelle (kunden_id FK)             1:n   Fälle direkt am Kunden
  ├─→ kunden_aktivitaeten (kunden_id FK)       1:n   Alle Aktivitäten
  └─→ kunden_classifier_log (kunden_id_vorschlag) 1:n   Klassifizierungsprotokoll
```

---

## 3. LLM-Kunden-Classifier (`scripts/kunden_classifier.py`)

### 3.1 Pipeline

```
Mail eingehend
  → mail_classifier.py (Kategorie: anfrage/newsletter/etc.)
  → vorgang_router.py (Vorgang: anfrage/angebot/etc.)
  → kunden_classifier.py:
      ┌─ 1. Geschäftskontakt-Vorfilter
      │     noreply@, newsletter-domains, marketing-Keywords
      │     → "kein_geschaeftsfall" → STOP
      │
      ├─ 2. Fast-Path
      │     Absender-E-Mail → kunden_identitaeten WHERE confidence='eindeutig'
      │     → Treffer → sofort zuordnen (kein LLM nötig)
      │
      ├─ 3. LLM-Path
      │     Super-Prompt mit:
      │       - Absender, Betreff, Text-Auszug
      │       - Alle Kunden mit Identitäten, Projekten, letzte Aktivitäten
      │     → JSON-Response mit kunden_id, projekt_id, confidence, reasoning
      │
      └─ 4. Confidence-Auswertung
            eindeutig (≥0.85) → auto-zuordnen
            wahrscheinlich (0.65-0.84) → zuordnen + Kira-Hinweis
            prüfen (0.40-0.64) → Prüfliste
            unklar (<0.40) → Prüfliste
```

### 3.2 Funktionen in `kunden_classifier.py`

| Funktion | Zeile | Beschreibung |
|---|---|---|
| `ist_geschaeftskontakt()` | 65 | Newsletter/noreply-Filter (Regex + Domain-Check) |
| `_fast_path()` | 112 | Lookup in kunden_identitaeten (confidence=eindeutig) |
| `_build_kunden_kontext()` | 169 | Baut Kontextblock aller Kunden für LLM |
| `_build_llm_prompt()` | 221 | Generiert vollständigen LLM-Prompt |
| `_parse_llm_response()` | 258 | Parst JSON-Response des LLM |
| `classify_kunde_projekt()` | 296 | **Hauptfunktion** — orchestriert die 4-Stufen-Pipeline |
| `_log_classification()` | 435 | Schreibt in `kunden_classifier_log` |
| `apply_classification()` | 465 | Wendet Ergebnis an (Identität + Aktivität + Fall anlegen) |
| `korrektur_speichern()` | 528 | Manuelle Korrektur speichern (Update log + Identität hochstufen) |
| `get_unzugeordnete()` | 582 | Prüfliste: Alle nicht bestätigten Einträge |

### 3.3 Integration

- **mail_monitor.py**: Nach `vorgang_router()` wird `classify_kunde_projekt()` + `apply_classification()` aufgerufen
- **daily_check.py**: Bei Nachklassifizierung wird der Classifier ebenfalls aufgerufen
- **Cache**: `_CLASSIFY_CACHE` — gleiche Absender+Betreff-Kombination wird 1h gecacht (kein doppelter LLM-Aufruf)

---

## 4. API-Endpunkte (22 Stück)

### 4.1 GET-Endpunkte (13)

| Pfad | Handler | Beschreibung |
|---|---|---|
| `/api/crm/kunden` | `_api_crm_kunden_list()` | Kundenliste mit Identitäten, Projektanzahl, Fall-Statistik |
| `/api/crm/kunden/{id}` | `_api_crm_kunden_get(kid)` | Einzelner Kunde mit allen Details |
| `/api/crm/kunden/{id}/projekte` | `_api_crm_projekte_list(kid)` | Projekte eines Kunden |
| `/api/crm/kunden/{id}/aktivitaeten` | `_api_crm_aktivitaeten(kid)` | Aktivitäten (optional: `?projekt_id=X`) |
| `/api/crm/kunden/{id}/faelle` | `_api_crm_faelle_list(kid)` | Fälle eines Kunden (optional: `?projekt_id=X`) |
| `/api/crm/kunden/{id}/stammdaten` | (im Kundenakte-Panel) | Lexware-basierte Stammdaten |
| `/api/crm/contacts` | `_api_crm_contacts()` | Alle Absender ohne Kundenstatus |
| `/api/crm/stats` | `_api_crm_stats()` | KPI-Zahlen (Kunden, Projekte, Fälle, Leads) |
| `/api/crm/projekte` | `_api_crm_projekte_list()` | Alle Projekte (ohne Kunden-Filter) |
| `/api/crm/faelle/{id}` | `_api_crm_faelle_get(fid)` | Fall-Details + Aktivitäten-Timeline |
| `/api/crm/faelle/{id}/export` | `_api_crm_faelle_export(fid)` | Streitfall-Dossier (Kunde+Projekt+Timeline+Log) |
| `/api/crm/aktivitaeten/{id}` | `_api_crm_aktivitaet_get(aid)` | Einzelne Aktivität mit Detail |
| `/api/crm/unzugeordnete` | `_api_crm_unzugeordnete()` | Classifier-Prüfliste (unbestätigte Zuordnungen) |

### 4.2 POST-Endpunkte (4)

| Pfad | Handler | Beschreibung |
|---|---|---|
| `/api/crm/kunden` | `_api_crm_kunden_create(data)` | Neuen Kunden anlegen |
| `/api/crm/kunden/{id}/projekte` | `_api_crm_projekte_create(kid, data)` | Neues Projekt für Kunden |
| `/api/crm/faelle` | `_api_crm_faelle_create(data)` | Neuen Fall anlegen |
| `/api/crm/faelle/{id}/aktivitaeten` | `_api_crm_faelle_add_aktivitaet(fid, data)` | Aktivität zu Fall hinzufügen |

### 4.3 PUT-Endpunkte (3) — via `do_PUT = do_POST` Alias

| Pfad | Handler | Beschreibung |
|---|---|---|
| `/api/crm/kunden/{id}` | `_api_crm_kunden_update(kid, data)` | Kunde bearbeiten |
| `/api/crm/faelle/{id}` | `_api_crm_faelle_update(fid, data)` | Fall bearbeiten (Status, Priorität, Titel) |
| `/api/crm/projekte/{id}` | (Update via POST-Route) | Projekt bearbeiten |

### 4.4 DashboardHandler — PUT-Unterstützung

```python
def do_PUT(self):
    """PUT-Requests werden wie POST behandelt (CRM-Update-Endpoints)."""
    return self.do_POST()
```

Ohne diesen Alias würden alle JS-Aufrufe mit `method:'PUT'` ins Leere laufen (DashboardHandler hatte nur `do_GET` und `do_POST`).

---

## 5. UI-Funktionen (`server.py`)

### 5.1 Python-Funktionen (HTML-Generierung)

| Funktion | Zeile | Beschreibung |
|---|---|---|
| `build_kunden()` | 14454 | Hauptfunktion — gibt komplettes CRM-HTML zurück |
| `_build_crm_subnav()` | (inline) | 5 Untermenüpunkte (Contacts, Kunden, Projekte, Aktivitäten, Pipeline) |
| `_build_crm_kundenuebersicht()` | (inline) | Akkordeon mit 4 Gruppen (Aktive/Leads/Inaktive/Archiv) |
| `_build_crm_kundenakte()` | (inline) | Kundenkopf + Projekt-Zeitstrahl + Verlauf + Stammdaten |
| `_build_crm_fallansicht()` | (inline) | Ticket-Kopf + Timeline + Aktionen |

### 5.2 JavaScript-Funktionen (47 Stück)

#### Navigation & State
| Funktion | Beschreibung |
|---|---|
| `crmInit()` | Initialisierung beim Panel-Wechsel |
| `crmShowPanel(name)` | Panel-Wechsel (uebersicht/akte/fall/projekte/aktivitaeten/pipeline) |
| `crmBack()` | Zurück-Navigation |
| `crmToggleAccordion(group)` | Akkordeon auf-/zuklappen |
| `crmFilterList()` | Suche + Filter in Kundenübersicht |

#### Daten laden
| Funktion | Beschreibung |
|---|---|
| `crmLoadKunden()` | Kundenliste laden → `_crmRenderKunden()` |
| `crmOpenKunde(id)` | Kundenakte öffnen |
| `crmLoadProjektSwitch(kundenId)` | Projekt-Dropdown befüllen |
| `crmSwitchProject(projektId)` | Projektfilter wechseln |
| `crmLoadTimeline(kundenId, projektId)` | Verlauf laden (projektgefiltert) |
| `crmLoadFaelle(kundenId)` | Fälle laden |
| `crmOpenFall(fallId)` | Fallansicht öffnen |
| `crmLoadProjekte()` | Projekte-Übersicht laden |
| `crmLoadUnzugeordnete()` | Prüfliste laden |
| `crmLoadPipeline()` | Pipeline-Ansicht laden |
| `crmOpenAktivitaet(id)` | Einzelne Aktivität öffnen |

#### CRUD-Aktionen
| Funktion | Beschreibung |
|---|---|
| `crmNeuerKunde()` | "Neuer Kunde"-Modal öffnen |
| `crmSaveNeuerKunde()` | POST /api/crm/kunden |
| `crmKontaktBearbeiten()` | "Kontakt bearbeiten"-Modal |
| `crmSaveKontakt()` | PUT /api/crm/kunden/{id} |
| `crmNeuerFall()` | "Neuer Fall"-Modal |
| `crmSaveNeuerFall()` | POST /api/crm/faelle |
| `crmNeuesProjektFuerKunde()` | "Neues Projekt"-Modal |
| `crmSaveNeuesProjekt()` | POST /api/crm/kunden/{id}/projekte |
| `crmUpdateFallStatus(fallId, status)` | PUT /api/crm/faelle/{id} |
| `crmFallNeueNotiz()` | Notiz-Modal im Fall |
| `crmSaveNotiz()` | POST /api/crm/faelle/{id}/aktivitaeten |

#### Aktionen aus Kundenakte/Fallansicht
| Funktion | Beschreibung |
|---|---|
| `crmNeueEmail()` | Compose-Fenster öffnen (Empfänger vorausgefüllt) |
| `crmFallNeueEmail()` | Compose aus Fallansicht |
| `crmFallDokument()` | Dokument-Upload (Stub) |
| `crmFallKira()` | Kira mit CRM-Kontext öffnen |
| `crmNeuesAngebot()` | Weiterleitung zu Lexware-Modul |
| `crmKiraFragen()` | Kira-Workspace mit vollem Kundenkontext |

#### Export / Streitfall
| Funktion | Beschreibung |
|---|---|
| `crmFallExport()` | Export/Streitfall-Modal öffnen |
| `crmDoExport(fid, typ)` | Export API aufrufen + Streitfall-Markierung |
| `crmCopyExport()` | Export in Zwischenablage |
| `crmDownloadExport()` | JSON als Datei herunterladen |

#### Rendering-Helfer
| Funktion | Beschreibung |
|---|---|
| `_crmRenderKunden(kunden)` | Kundenliste als Akkordeon rendern |
| `_crmRenderAkteHeader(k)` | Kundenkopf rendern |
| `_crmRenderStammdaten(k)` | Stammdaten-Seitenleiste rendern |
| `_crmEsc(s)` | HTML-Escape-Helfer |
| `crmShowAkteTab(tab)` | Tab-Wechsel in Kundenakte (verlauf/faelle/dokumente/finanzen/kira/settings) |

#### Modals
| Funktion | Beschreibung |
|---|---|
| `crmShowModal(title, body, footer)` | Generisches Modal öffnen |
| `crmCloseModal()` | Modal schließen |
| `crmZuordnen(logId)` | Zuordnungs-Dialog (Stub für Prüfliste) |

---

## 6. CSS-System

### Prefix: `crm-*`

Alle CRM-spezifischen CSS-Klassen verwenden den Prefix `crm-` um Kollisionen zu vermeiden.

| Klasse | Verwendung |
|---|---|
| `.crm-container` | Haupt-Container (2-Spalten-Layout) |
| `.crm-subnav` | Linke Sub-Navigation (5 Einträge) |
| `.crm-sn-item` | Einzelner Nav-Eintrag |
| `.crm-sn-item.active` | Aktiver Nav-Eintrag |
| `.crm-main` | Rechter Hauptbereich |
| `.crm-panel` | Panel (sichtbar/unsichtbar per display) |
| `.crm-filter-bar` | Suchfeld + Filter-Leiste |
| `.crm-accordion-header` | Akkordeon-Kopf (klickbar) |
| `.crm-accordion-content` | Akkordeon-Inhalt |
| `.crm-kunde-row` | Einzelne Kundenzeile in Übersicht |
| `.crm-akte-header` | Kundenkopf in Akte |
| `.crm-chip` | Status-Chip (aktiv/lead/inaktiv/archiv) |
| `.crm-chip-*` | Farb-Varianten der Chips |
| `.crm-timeline-item` | Timeline-Eintrag |
| `.crm-projekt-zeitstrahl` | Projekt-Zeitstrahl-Container |
| `.crm-fall-kopf` | Ticket-Kopf in Fallansicht |
| `.crm-action-bar` | Aktions-Leiste |
| `.crm-action-btn` | Aktions-Button |
| `.crm-btn-warn` | Warn-Button (orange) |
| `.crm-stammdaten` | Rechte Kontextspalte |
| `.crm-tab-bar` | Tab-Leiste (Verlauf/Fälle/Dokumente/etc.) |
| `.crm-tab-bar span.active` | Aktiver Tab |

### CSS-Variablen (aus Mockups)

Verwendet die globalen KIRA-Design-Variablen: `--bg`, `--bg-raised`, `--text`, `--text-muted`, `--border`, sowie Farbvariablen für Chips.

---

## 7. Kira-Tools (7 neue in `kira_llm.py`)

### 7.1 Tool-Definitionen

| Tool-Name | Parameter | Beschreibung |
|---|---|---|
| `kunden_suchen` | `suchbegriff` (string) | Sucht in kunden + kunden_identitaeten (LEFT JOIN) |
| `kundenakte_laden` | `kunden_id` (integer) | Lädt vollständige Akte: Identitäten, Projekte, Fälle, letzte 20 Aktivitäten |
| `crm_projekt_zuordnen` | `aktivitaet_id`, `projekt_id` | Aktivität einem Projekt zuordnen (UPDATE) |
| `crm_fall_erstellen` | `kunden_id`, `fall_typ`, `titel`, optional: `projekt_id`, `prioritaet` | INSERT in kunden_faelle |
| `crm_fall_oeffnen` | `fall_id` (integer) | Lädt Fall + zugehörige Aktivitäten |
| `crm_kunden_klassifizieren` | `eingabe_typ`, `eingabe_id` | Ruft `classify_kunde_projekt()` + `apply_classification()` |
| `crm_aktivitaeten_pruefliste` | (keine) | Ruft `get_unzugeordnete()` — Liste nicht bestätigter Zuordnungen |

### 7.2 Handler-Funktionen

| Funktion | Zeile | Beschreibung |
|---|---|---|
| `_tool_kunden_suchen(p)` | 5377 | SELECT mit LIKE + LEFT JOIN kunden_identitaeten |
| `_tool_kundenakte_laden(p)` | 5417 | 4 Queries: Kunde + Identitäten + Projekte + Fälle + Aktivitäten |
| `_tool_crm_projekt_zuordnen(p)` | 5468 | UPDATE kunden_aktivitaeten SET projekt_id + elog |
| `_tool_crm_fall_erstellen(p)` | 5487 | INSERT kunden_faelle + elog |
| `_tool_crm_fall_oeffnen(p)` | 5512 | SELECT Fall + Aktivitäten |
| `_tool_crm_kunden_klassifizieren(p)` | 5547 | `from kunden_classifier import ...` → classify + apply |
| `_tool_crm_aktivitaeten_pruefliste(p)` | 5572 | `from kunden_classifier import get_unzugeordnete` |

### 7.3 System-Prompt-Erweiterung

In `_build_data_context()` wird nach den bestehenden Kontextblöcken ergänzt:

```
🏢 CRM — TOP-KUNDEN (5 aktivste)
  - Firmenname (ID #X) — N Projekte, M offene Fälle

📋 CRM — OFFENE FÄLLE (max 10)
  - Fall #X: Titel (Typ) — Status — Kunde

⚠ N unzugeordnete Aktivitäten warten auf Prüfung (Tool: crm_aktivitaeten_pruefliste)

🏗️ CRM — AKTIVE PROJEKTE (max 10)
  - Projektname (Kunde) — Status — Auftragswert
```

### 7.4 Quick-Actions

Im Kira-Workspace für CRM-Kontext:

```javascript
crm: ['Kundenakte zeigen', 'Offene Fälle diese Woche', 'Mail zuordnen',
      'Unzugeordnete prüfen', 'Neuen Fall erstellen']
```

Aktiviert via `kiraSetQuickActions('crm')` in `crmKiraFragen()`.

---

## 8. CRM-Einstellungen (`server.py` — Einstellungen-Panel)

### 8.1 Einstellungen-Sektion `es-sec-crm`

Nav-Eintrag: `esShowSec('crm')` → zeigt CRM-Einstellungssektion.

### 8.2 Konfigurationsoptionen (10 Stück)

| Config-Key | Typ | Default | Beschreibung |
|---|---|---|---|
| `crm.auto_zuordnung` | Boolean | `true` | Automatische Kunden-Zuordnung bei Mails |
| `crm.llm_classifier` | Boolean | `true` | LLM-Classifier aktiv |
| `crm.confidence_schwelle` | Text | `wahrscheinlich` | Mindest-Confidence für Auto-Zuordnung |
| `crm.geschaeftskontakt_filter` | Boolean | `true` | Newsletter/noreply ausfiltern |
| `crm.auto_fall_erstellung` | Boolean | `false` | Automatisch Fälle bei neuen Mails erstellen |
| `crm.fall_typen` | Text | `anfrage,angebot,...,allgemein` | Komma-getrennte Fall-Typen |
| `crm.export_format` | Select | `json` | Export-Format (json/csv) |
| `crm.log_detail` | Select | `normal` | Log-Detailgrad (minimal/normal/verbose) |
| `crm.lexware_sync` | Boolean | `true` | Lexware-Kontakte als Kunden synchronisieren |
| `crm.max_timeline` | Number | `50` | Max. Aktivitäten in Timeline |

### 8.3 Speicherung

In `saveSettings()` JS-Funktion wird der `crm`-Block gesammelt:

```javascript
crm: {
    auto_zuordnung: _chk('cfg-crm-auto-zuordnung'),
    llm_classifier: _chk('cfg-crm-llm-classifier'),
    confidence_schwelle: _v('cfg-crm-confidence', 'wahrscheinlich'),
    geschaeftskontakt_filter: _chk('cfg-crm-geschaeftskontakt-filter'),
    auto_fall_erstellung: _chk('cfg-crm-auto-fall'),
    fall_typen: _v('cfg-crm-fall-typen', 'anfrage,...'),
    export_format: _v('cfg-crm-export-format', 'json'),
    log_detail: _v('cfg-crm-log-detail', 'normal'),
    lexware_sync: _chk('cfg-crm-lexware-sync'),
    max_timeline: parseInt(_v('cfg-crm-max-timeline', '50'))
}
```

---

## 9. Runtime-Log Events (via `elog()`)

| Event-Typ | Modul | Wann |
|---|---|---|
| `kunde_erstellt` | server.py | POST /api/crm/kunden |
| `kunde_aktualisiert` | server.py | PUT /api/crm/kunden/{id} |
| `projekt_erstellt` | server.py, kira_llm.py | POST /api/crm/kunden/{id}/projekte, Kira-Tool |
| `fall_erstellt` | server.py, kira_llm.py | POST /api/crm/faelle, Kira-Tool |
| `fall_status_geaendert` | server.py | PUT /api/crm/faelle/{id} |
| `export_gestartet` | server.py | GET /api/crm/faelle/{id}/export |
| `aktivitaet_zugeordnet` | kira_llm.py | Tool crm_projekt_zuordnen |
| `classifier_aufgerufen` | kunden_classifier.py | LLM-Path vor Klassifizierung |
| `classifier_korrigiert` | kunden_classifier.py | Manuelle Korrektur |
| `kein_geschaeftsfall` | kunden_classifier.py | Newsletter/noreply erkannt |
| `unzugeordnet_markiert` | mail_monitor.py | Classifier-Ergebnis confidence < Schwelle |
| `crm_classifier_fehler` | mail_monitor.py | Exception im Classifier |
| `projekt_gewechselt` | server.py (JS _rtlog) | User wechselt Projekt in Akte |
| `kira_kontext_gestartet` | server.py (JS _rtlog) | "Kira fragen" aus CRM |

---

## 10. Guided Tour (6 Schritte)

Definiert als `window.KIRA_TOUR_CRM` im `<script>`-Block:

| Schritt | Highlight-Element | Beschreibung |
|---|---|---|
| 1 | `.crm-subnav` | "Navigation — hier findest du alle Bereiche des Kundencenters" |
| 2 | `#crm-panel-uebersicht` | "Kundenübersicht mit Akkordeon-Gruppen" |
| 3 | `.crm-filter-bar` | "Suche und Filter — finde Kunden schnell" |
| 4 | `.crm-projekt-zeitstrahl` | "Projekt-Zeitstrahl — alle Projekte auf einer Timeline" |
| 5 | `.crm-fall-kopf` | "Fallansicht — jeder Geschäftsvorfall als Ticket" |
| 6 | `.crm-action-bar` | "Aktionen — E-Mail, Notiz, Kira fragen, Export" |

Gestartet via Tour-Button in der CRM-Toolbar:
```html
<button onclick="kira_tour.start(window.KIRA_TOUR_CRM,{erklaermodus:true})">Tour</button>
```

---

## 11. Verarbeitungspipeline (Mail → CRM)

```
    ┌──────────────────────────────────────────────────────────────────────────┐
    │  Neue Mail (IMAP-Polling, mail_monitor.py)                             │
    └────────────────────────┬─────────────────────────────────────────────────┘
                             │
                             ▼
    ┌──────────────────────────────────────────────────────────────────────────┐
    │  1. mail_classifier.py — Kategorie bestimmen                           │
    │     (anfrage / newsletter / privat / eingangsrechnung / etc.)          │
    │     + Geschäftskontakt-Filter (noreply → STOP)                        │
    └────────────────────────┬─────────────────────────────────────────────────┘
                             │
                             ▼
    ┌──────────────────────────────────────────────────────────────────────────┐
    │  2. vorgang_router.py — Vorgang-Typ bestimmen                          │
    │     (anfrage / angebot / reklamation / etc.)                           │
    │     → Vorgang in case_engine.py anlegen                                │
    └────────────────────────┬─────────────────────────────────────────────────┘
                             │
                             ▼
    ┌──────────────────────────────────────────────────────────────────────────┐
    │  3. kunden_classifier.py — Kunde + Projekt zuordnen                    │
    │                                                                        │
    │  3a. Fast-Path: E-Mail in kunden_identitaeten?                         │
    │      JA (confidence=eindeutig) → Sofort zuordnen                       │
    │                                                                        │
    │  3b. LLM-Path: Super-Prompt mit Kundenliste                            │
    │      → JSON: {kunden_id, projekt_id, fall_typ, confidence, reasoning}  │
    │                                                                        │
    │  3c. Confidence-Auswertung:                                            │
    │      eindeutig → auto-zuordnen + Aktivität + ggf. Fall                 │
    │      wahrscheinlich → zuordnen + Kira-Hinweis                          │
    │      prüfen/unklar → in Prüfliste                                      │
    └────────────────────────┬─────────────────────────────────────────────────┘
                             │
                             ▼
    ┌──────────────────────────────────────────────────────────────────────────┐
    │  4. Ergebnis in DB:                                                    │
    │     - kunden_classifier_log (Protokoll)                                │
    │     - kunden_identitaeten (neue Identität bei eindeutig)               │
    │     - kunden_aktivitaeten (Verlaufseintrag)                            │
    │     - kunden_faelle (neuer Fall wenn auto_fall_erstellung=true)         │
    └──────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Export / Streitfall-Dossier

### API-Response: `GET /api/crm/faelle/{id}/export`

```json
{
    "ok": true,
    "export": {
        "export_typ": "streitfall_dossier",
        "export_datum": "2026-04-10T15:00:00",
        "fall": { /* alle Spalten aus kunden_faelle */ },
        "kunde": { /* alle Spalten aus kunden */ },
        "projekt": { /* alle Spalten aus kunden_projekte */ },
        "identitaeten": [ /* alle kunden_identitaeten des Kunden */ ],
        "aktivitaeten": [ /* alle kunden_aktivitaeten des Falls, chronologisch */ ],
        "classifier_log": [ /* letzte 20 Classifier-Einträge des Kunden */ ],
        "zusammenfassung": {
            "fall_titel": "...",
            "fall_typ": "streitfall",
            "status": "streitfall",
            "kunde_name": "...",
            "projekt_name": "...",
            "anzahl_aktivitaeten": 15,
            "zeitraum_von": "2026-01-15T...",
            "zeitraum_bis": "2026-04-10T..."
        }
    }
}
```

### JS-Aktionen im Export-Modal

1. **JSON-Export** — Lädt Dossier, zeigt im Modal, Kopieren/Herunterladen
2. **Streitfall-Dossier** — Zusätzlich: Fall-Status auf `streitfall` setzen (PUT)

---

## 13. Abhängigkeiten zu bestehenden Modulen

| Bestehendes Modul | Wie genutzt |
|---|---|
| `case_engine.py` | `_ensure_crm_tables()` dort hinzugefügt (Schema-Migration) |
| `mail_classifier.py` | Geschäftskontakt-Filter als neue Stufe ergänzt |
| `mail_monitor.py` | Classifier-Aufruf nach vorgang_router (20 LOC) |
| `daily_check.py` | Classifier-Aufruf bei Nachklassifizierung (20 LOC) |
| `runtime_log.py` | `elog()` für alle CRM-Events |
| `kira_llm.py` | 7 Tools + System-Prompt-Erweiterung |
| `lexware_client.py` | Stammdaten-Abfrage für Kundenakte (via `lexware_id`) |
| Postfach Compose | `crmNeueEmail()` öffnet bestehendes Compose-Fenster |
| Guided Tours Engine | Tour-Schritte für CRM-Modul |
| Einstellungen (3-Spalten) | CRM-Sektion als `es-sec-crm` eingefügt |
