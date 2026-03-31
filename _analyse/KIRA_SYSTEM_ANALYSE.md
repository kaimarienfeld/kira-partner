# KIRA — Vollständige System-Analyse
**Erstellt:** 2026-03-30 | **Zuletzt aktualisiert:** 2026-03-31 (session-rr)
**Analysiert:** 35+ Python-Module, 8 SQLite-Datenbanken, 70+ API-Endpunkte
**Projektpfad:** `memory/` (Git-Repo)

> **Changelog dieser Datei:**
> - session-jj: Erstellt. 10 Bugs identifiziert, 7 sofort behoben.
> - session-kk: Postfach Mail-Rendering + Kira-Button Redesign (commit 66241b0).
> - session-ll: Automatisches Modell-Validierungssystem implementiert.
> - session-nn: Case Engine (Vorgänge), 5 neue Tools (17 total), Desktop-Overlay, Presence-Detection, Backfill-Skript, GAP-Analyse + Roadmap ergänzt.
> - session-oo: **VOLLSTÄNDIGE AKTIVE ASSISTENZ** — Alle 10 Pakete implementiert: Idempotenz, Circuit Breaker, Rate-Limiting, Mail-Senden HITL, Konversations-Gedächtnis, Vorgang-Scans, Autonomy-Loop, ReAct, Feedback-Lernen, FTS5-Suche, MS-Graph-Kalender, Audit-Trail, Live-Migration (83 Vorgänge).
> - session-pp: Bug-Fixes B-04 (NULL-Check mail_monitor), B-05 (Race Condition proaktiv_state.json), Task-Löschen Server-Blockade. Alle GAPs geschlossen.
> - session-qq: kira_cfg Bug-Fix (Top-Level statt llm-Sub-Dict), Kontext-Steuerung (3 Selects), Auto-Wissen-Extraktion verdrahtet, Eingangsrechnungen Tabellen-View + Proaktiv-Scan, Kira-Proaktiv aktiv-Check.
> - session-rr: Antwort-Länge/Sprache/Temperatur vollständig verdrahtet, Provider Verbindungstest, Einstellungen-Suche, DB-VACUUM, Toast-Anzeigedauer. Alle KIRA-LLM-Verbindungen abgeschlossen.

---

## INHALTSVERZEICHNIS

1. [Überblick & Architektur](#1-überblick--architektur)
2. [Was KIRA alles tut — Feature-Vollbild](#2-was-kira-alles-tut--feature-vollbild)
3. [LLM-Integration — wie KI angebunden ist](#3-llm-integration--wie-ki-angebunden-ist)
4. [Datenbanken — Struktur & Verknüpfungen](#4-datenbanken--struktur--verknüpfungen)
5. [Mail-System — Eingang bis Task](#5-mail-system--eingang-bis-task)
6. [Proaktive Automatisierung](#6-proaktive-automatisierung)
7. [Dashboard & Server](#7-dashboard--server)
8. [Konfiguration & Secrets](#8-konfiguration--secrets)
9. [Partner-View (Leni)](#9-partner-view-leni)
10. [Fehler & Irregularitäten — mit Behebungsvorschlägen](#10-fehler--irregularitäten--mit-behebungsvorschlägen)
11. [Case Engine — Vorgang-Layer (session-nn)](#11-case-engine--vorgang-layer-session-nn)
12. [GAP-Analyse: Vollständige Aktive Assistenz](#12-gap-analyse-vollständige-aktive-assistenz)
13. [Verbesserungs-Roadmap](#13-verbesserungs-roadmap)

---

## 1. Überblick & Architektur

**KIRA** ist ein Python-basiertes Geschäftsassistenz-System für rauMKult® Sichtbeton (Kai Marienfeld, Betonkosmetik-Spezialist). Es läuft lokal auf `http://127.0.0.1:8765` und verbindet folgende Hauptkomponenten:

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser (Dashboard + Kira-Workspace)                            │
│  http://127.0.0.1:8765                                           │
└────────────────────┬─────────────────────────────────────────────┘
                     │ HTTP (50+ Endpunkte)
┌────────────────────▼─────────────────────────────────────────────┐
│  server.py  (9.250 Zeilen)                                       │
│  ThreadedHTTPServer — HTML + API                                 │
└──┬──────────┬──────────┬──────────┬──────────────────────────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
kira_llm  mail_monitor  daily_check  kira_proaktiv
(LLM-     (IMAP-       (Nacht-     (Business-
 Gehirn)   Polling)     Check)      Scanner)
   │          │              │
   ▼          ▼              ▼
┌─────────────────────────────────────────────────────┐
│  SQLite-Datenbanken (knowledge/)                    │
│  tasks.db · mail_index.db · kunden.db               │
│  runtime_events.db · sent_mails.db · ...            │
└─────────────────────────────────────────────────────┘
```

### Dateistruktur (Kern)
| Datei | Zeilen | Zweck |
|---|---|---|
| `scripts/server.py` | 9.450+ | Haupt-Dashboard, alle API-Endpunkte, HTML-Generierung |
| `scripts/kira_llm.py` | 2.950+ | LLM-Multi-Provider, Kira-Chat, 12 Tools, Modell-Validierung |
| `scripts/mail_monitor.py` | 2.000 | IMAP-Polling, Mail-Klassifizierung, Task-Erstellung |
| `scripts/daily_check.py` | 1.450 | Täglicher Mail-Scan, Erinnerungen, Nachklassifizierung |
| `scripts/kira_proaktiv.py` | 613 | Autonomer Business-Scanner (alle 15 Min) |
| `scripts/llm_classifier.py` | 500+ | LLM-basierte Mail-Klassifizierung |
| `scripts/mail_classifier.py` | 600+ | Regelbasierte Mail-Klassifizierung (Fast-Path) |
| `scripts/runtime_log.py` | 483 | Event-Store (SQLite, Thread-safe) |
| `scripts/task_manager.py` | 102 | Task-CRUD für tasks.db |
| `scripts/llm_response_gen.py` | 200+ | Auto-Antwort-Entwürfe (LLM) |

---

## 2. Was KIRA alles tut — Feature-Vollbild

### 2.1 Dashboard-Panels (sichtbar im Browser)

**Panel: Dashboard (Startseite)**
- KPI-Karten: offene Aufgaben, Rechnungen, Angebote, Kunden
- Sparklines (Trend-Verlauf)
- Top-5-Aufgaben nach Priorität
- Überfällig-Badge für kritische Items

**Panel: Kommunikation**
- Alle klassifizierten Mails nach Kategorie (9 Kategorien)
- Filter: alle / unanswered / beantwortet / usw.
- Kira-Buttons pro Mail: Zusammenfassung, Antwort-Entwurf, Kategorie-Korrektur
- Status-Aktionen: erledigt, ignorieren, zur Kenntnis
- **Kira-Button (session-kk):** Prominent lila mit Glow; öffnet Kira-Workspace mit vollständigem Mail-Kontext (EML-Volltext + letzte 5 Absender-Mails + offene Tasks), Auto-Send
- **Volltext-Postfach (session-hh/ii):** Live-IMAP-Ordner, Mail verschieben, Snooze (7 Presets + Freitext), Aktionsleiste Single/Bulk, Gelöschte-Protokoll-System

**Panel: Geschäft (5 Sub-Tabs)**
1. Ausgangsrechnungen — Status, Betrag, Überfällig-Warnung
2. Angebote — Nachfass-Datum, Betrag geschätzt
3. Mahnungen — Stufe 1/2/3
4. Eingangsrechnungen — Lieferanten, Fälligkeiten
5. Statistik — Zahlungsdauern, Muster

**Panel: Wissen**
- 7 Kategorien gelernter Regeln: Preisregeln, Kundenwünsche, Prozessregeln, Ausschlussregeln, Auto-gelernt, Korrektionen, Freitextnotizen
- CRUD: neue Regel anlegen, bearbeiten, löschen
- Direkt in Kira-Kontext injiziert (System-Prompt)

**Panel: Organisation**
- Termine und Fristen aus Mails erkannt
- Rückruf-Erinnerungen

**Panel: Einstellungen (55 KB HTML)**
- Design, Benachrichtigungen, Aufgabenlogik, Nachfass-Intervalle
- Mail-Konten (OAuth2-Flow, Ordner-Sync)
- LLM-Provider (Anthropic / OpenAI / OpenRouter / Ollama / Custom)
- Automationen (Mail-Monitor, Daily-Check, Proaktiv-Scanner)
- Protokoll (Runtime-Log Anzeige, Vollkontext, Löschen)

### 2.2 Kira-Workspace (Chat + Tools)
3-Spalten-Layout:
- **Links**: Kontext-Tabs (Aufgaben, Mails, Geschäft, Wissen)
- **Mitte**: Chat-Verlauf + Eingabefeld
- **Rechts**: Tool-Aufrufe, Aktionshistorie

Kira kann über Chat:
- Rechnungen als bezahlt markieren
- Angebote bestätigen / ablehnen
- Kunden-Daten nachschlagen (inkl. kompletter Mail-Historie)
- Nachfass-Mails entwerfen
- Wissen speichern
- Tasks erledigen oder löschen
- Im Internet recherchieren
- Runtime-Log durchsuchen (wenn aktiviert)
- Angebote prüfen + Vergleiche ziehen

### 2.3 Hintergrundprozesse
- **Mail-Monitor** — IMAP-Polling alle ~60 Sekunden (5 Konten)
- **Proaktiver Scanner** — alle 15 Minuten via Mail-Monitor
- **Daily Check** — 1x täglich (nachts), Nachklassifizierung + Erinnerungen
- **Archiv-Cleanup** — täglich, bereinigt Anhänge aus gelöschten Mails
- **Snooze-Wecker** — alle 60 Sekunden, weckt abgelaufene Snooze-Mails auf
- **Modell-Validierung** — 20s nach Start + alle 24h, prüft alle Provider-Modelle automatisch (session-ll)
- **Tagesstart-Briefing** — morgens 6–10 Uhr, generiert von LLM
- **Signal-Watcher** — alle 15 Sekunden, zeigt Desktop-Overlay für Stufe-C-Signale (session-nn, activity_window.py)
- **Signal-Polling-JS** — Browser-seitig alle 10 Sekunden, zeigt Toast (Stufe B) oder Modal (Stufe C) (session-nn)

### 2.4 Case Engine — Vorgang-Tracking (session-nn)
- **Vorgänge**: Strukturierte Geschäftsprozesse oberhalb der Task-/Mail-Ebene
- **10 Vorgang-Typen**: lead, angebot, rechnung, mahnung, support, projekt, partner, lieferant, intern, sonstige
- **Entscheidungsstufen**: A (automatisch, stumm), B (SSE-Toast im Browser), C (Modal + Desktop-Overlay)
- **State Machines**: Typ-spezifische Übergänge, ungültige Transitionen werden abgelehnt
- **Verknüpfungen**: Jeder Vorgang kann mit Tasks, Mails, Rechnungen, Angeboten verlinkt sein
- **Browser-API**: 8 neue Endpunkte (`/api/vorgaenge`, `/api/vorgang/{id}`, `/api/vorgang/signals` u.a.)
- **Presence-Detection**: `presence_detector.py` — Windows `GetLastInputInfo()`, kein Popup wenn >5 Min inaktiv

---

## 3. LLM-Integration — wie KI angebunden ist

### 3.1 Multi-Provider-System (`kira_llm.py`)

KIRA unterstützt 4 Provider mit automatischem Fallback:

```
Priorität 1: Anthropic   → claude-sonnet-4-6 (Standard)
Priorität 2: OpenAI      → gpt-4o
Priorität 3: OpenRouter  → anthropic/claude-sonnet-4
Priorität 4: Ollama      → llama3.1 (lokal, offline)
Priorität X: Custom      → beliebige OpenAI-kompatible API
```

**Fallback-Logik:** Wenn Provider fehlschlägt (Timeout, API-Fehler, kein Guthaben) → automatisch nächster in der Prioritäts-Liste.

**Modell-nicht-gefunden (session-ll):** Wenn ein Modell mit HTTP 404 / `not_found_error` antwortet → `ModelNotFoundError` wird ausgelöst → `_auto_update_model()` wird sofort aufgerufen → Fallback auf nächsten Provider in derselben Anfrage.

**Konfiguration in `config.json`:**
```json
"llm_providers": [
  {"name": "anthropic", "type": "anthropic",
   "model": "claude-sonnet-4-20250514", "active": true, "priority": 1}
]
```

**API-Key aus `secrets.json`:**
```json
{"anthropic_api_key": "sk-ant-..."}
```

### 3.2 Kira-Chat-Pipeline

```
User-Eingabe
    → POST /api/kira/chat
    → kira_llm.chat()
        → build_system_prompt()
            → Kira-Rolle + rauMKult-Kontext
            → _build_data_context() [offene RE, Angebote, Tasks]
            → get_recent_for_kira(limit=30) [letzte 30 Runtime-Events]
            → _get_wissen_by_kategorie() [gelernte Regeln → System-Prompt]
            → letzte 15 Eingangs-Mails (Kurzvorschau)
            → Proaktive Findings des Tages
            → Gelöschte-Protokoll (letzten 20)
        → LLM-Provider-Aufruf (mit Tools)
        → Tool-Aufruf erkannt? → Tool ausführen → DB-Aktion
        → Antwort
    → elog() in runtime_events.db
```

### 3.3 Die 17 Kira-Tools (kira_llm.py)

Alle Tools sind im Anthropic-Format definiert und werden automatisch in OpenAI-Format konvertiert für nicht-Anthropic-Provider:

| Tool | Aktion | Datenbank | Seit |
|---|---|---|---|
| `rechnung_bezahlt` | Ausgangsrechnung → status='bezahlt' | tasks.db / ausgangsrechnungen | session-jj |
| `angebot_status` | Angebot → angenommen/abgelehnt/keine_antwort | tasks.db / angebote | session-jj |
| `eingangsrechnung_erledigt` | Eingangsrechnung → erledigt | tasks.db | session-jj |
| `kunde_nachschlagen` | Kunden-Infos + Mail-Historie | kunden.db + mail_index.db | session-jj |
| `nachfass_email_entwerfen` | LLM-Entwurf generieren | kein DB-Schreiben | session-jj |
| `wissen_speichern` | Neue Regel → wissen_regeln | tasks.db | session-jj |
| `rechnungsdetails_abrufen` | PDF-extrahierte Details | rechnungen_detail.db | session-jj |
| `web_recherche` | Google-Suche via urllib | extern | session-jj |
| `runtime_log_suchen` | Events suchen | runtime_events.db | session-jj |
| `angebot_pruefen` | Angebot-Details + ähnliche Anfragen | tasks.db + mail_index.db | session-jj |
| `task_erledigen` | Task → status='erledigt' | tasks.db | session-jj |
| `tasks_loeschen` | Mehrere Tasks löschen | tasks.db | session-jj |
| `duplikate_suchen` | Doppelte Tasks/Mails finden | tasks.db + mail_index.db | session-mm |
| `mail_suchen` | Mail-Index durchsuchen | mail_index.db | session-mm |
| `mail_lesen` | Mail-Volltext aus Archiv laden | mail_index.db + Archiv | session-mm |
| `vorgang_kontext_laden` | Vorgang-Details + History laden | tasks.db (vorgaenge) | **session-nn** |
| `vorgang_status_setzen` | Vorgang-Status via State-Machine ändern | tasks.db (vorgaenge) | **session-nn** |

### 3.4 Mail-Klassifizierung — 3-stufig

**Stufe 1 — Fast-Path (mail_classifier.py, ~80% der Mails):**
- System-Absender-Check (100+ Domains, 50+ Patterns)
- Newsletter-Keywords
- Kunden-Keywords direkt erkannt
- → Ergebnis ohne LLM-Aufruf

**Stufe 2 — LLM-Klassifizierung (llm_classifier.py, ~20% der Mails):**
- Lädt Kontext: offene Angebote zum Absender, Kundenprofil, Mail-Verlauf
- Nutzt gelernte Korrektionen als Beispiele
- Gibt strukturiertes JSON zurück:
  ```json
  {
    "kategorie": "Neue Lead-Anfrage",
    "absender_rolle": "Lead",
    "zusammenfassung": "...",
    "antwort_noetig": true,
    "empfohlene_aktion": "...",
    "prioritaet": "hoch|mittel|niedrig",
    "konfidenz": "hoch|mittel|niedrig",
    "mit_termin": false,
    "beantwortet": false,
    "angebot_aktion": "angenommen|abgelehnt|rueckfrage|null",
    "angebot_nummer": "ANF-2026-001"
  }
  ```

**Stufe 3 — Regelbasierter Fallback (wenn LLM fehlschlägt):**
- Aus mail_classifier.py
- ~95% Accuracy ohne LLM

### 3.5 Automatische Modell-Validierung (session-ll, kira_llm.py)

**Zweck:** Erkennt automatisch wenn LLM-Modell-IDs von einem Provider zurückgezogen werden und wechselt auf das beste verfügbare Modell — ohne manuelle Intervention.

**Komponenten:**
```
_fetch_provider_models(provider)       → GET /v1/models (Anthropic/OpenAI/OpenRouter)
                                          GET /api/tags (Ollama)
                                          Ergebnis 24h gecacht in _MODEL_CACHE
_model_in_list(model_id, available)   → Exakter + Prefix-Match (dated snapshots)
_validate_model(provider)             → Prüft konfiguriertes Modell gegen API-Liste
_auto_update_model(provider)          → Wechselt Modell + speichert config.json + ntfy Push
validate_all_providers()              → Alle aktiven Provider prüfen + state-file schreiben
```

**Fallback-Ranking (bevorzugte Modelle wenn aktives deprecated):**
| Provider | Ranking |
|---|---|
| anthropic | claude-opus-4-6 → claude-sonnet-4-6 → claude-haiku-4-5-20251001 |
| openai | gpt-4o → gpt-4o-mini → gpt-4.1-2025-04-14 → o3-mini |
| openrouter | anthropic/claude-sonnet-4 → openai/gpt-4o → google/gemini-2.5-pro-preview |
| ollama | dynamisch (erstes verfügbares) |

**Auslöser:**
1. **Laufzeitfehler** — `_call_anthropic()` fängt `APIStatusError` (404 + `not_found_error`) → sofortiger Auto-Update
2. **OpenAI-Fehler** — `_call_openai_compat()` fängt `NotFoundError` und `BadRequestError` mit Modell-Keywords
3. **Hintergrund-Thread** — Täglich 20s nach Server-Start → `validate_all_providers()` für alle Provider
4. **Manuell** — 🔍 Modell-Button in Einstellungen → `POST /api/kira/provider/check-models`

**Persistenz:**
- `knowledge/model_validation_state.json` — Ergebnis des letzten Checks (timestamp + pro Provider)
- `config.json` — Modell wird direkt aktualisiert bei Auto-Update

**Dashboard-Integration:**
- Einstellungen/LLM-Provider: 🟡 Status-Icon wenn Modell veraltet (statt 🟢)
- Gelb hinterlegter Warn-Text mit Grund + empfohlenem Ersatzmodell
- 🔍 Modell-Button per Provider für manuellen Check

### 3.6 Case Engine Context im System-Prompt (session-nn)

`build_system_prompt()` injiziert jetzt zusätzlich offene Vorgänge:
```python
from case_engine import get_vorgang_summary_for_kira
vs = get_vorgang_summary_for_kira(limit=8)
if vs:
    prompt += f"\n\nOFFENE VORGÄNGE (Case Engine):\n{vs}\n"
```

Die Summary enthält die 8 aktuellsten offenen Vorgänge mit Status, Typ und Titel.
Kira kann dann direkt die Tools `vorgang_kontext_laden` und `vorgang_status_setzen` nutzen.

### 3.7 Antwort-Entwürfe (llm_response_gen.py)
5 Situationstypen mit LLM-generierten Entwürfen:
1. Erstanfrage (Begrüßung, Leistungsüberblick)
2. Fotos eingegangen (Dank, Analyse-Offer)
3. Preisanfrage (Kostenvoranschlag, Bedingungen)
4. Termin gewünscht (Verfügbarkeit, Bestätigung)
5. Folgemail (Weiterführung)

**Stil gelernt aus:** 525 versendeten Mails in `sent_mails.db`

---

## 4. Datenbanken — Struktur & Verknüpfungen

### 4.1 tasks.db (17 MB) — Kern-Datenbank

**Tabelle: tasks**
```
id, typ, kategorie, titel, zusammenfassung, beschreibung,
kunden_email, kunden_name, absender_rolle, empfohlene_aktion,
kategorie_grund, message_id, mail_folder_pfad, anhaenge_pfad,
antwort_entwurf, claude_prompt, betreff, konto, datum_mail,
status, prioritaet, antwort_noetig, mit_termin, manuelle_pruefung,
beantwortet, erinnerungen, naechste_erinnerung, notiz,
erstellt_am, aktualisiert_am, erledigt_am
```

Verknüpfungen:
- `message_id` → `mail_index.db.mails.message_id` (Mail-Volltext)
- `kunden_email` → `kunden.db` (Kundenprofil)
- `mail_folder_pfad` → OneDrive-Archiv (mail.json mit Volltext)

**Tabelle: ausgangsrechnungen**
```
id, re_nummer, datum, faellig_am, kunde_name, kunde_email,
betrag_netto, betrag_brutto, mwst_satz, status, bezahlt_am,
zahlungseingang, skonto_prozent, message_id, notiz
```

**Tabelle: angebote**
```
id, a_nummer, datum, kunde_name, kunde_email, beschreibung,
betrag_geschaetzt, status, nachfass_count, naechster_nachfass,
message_id, notiz
```

**Tabelle: eingangsrechnungen**
```
id, re_nummer, datum, anbieter, betrag, status, erledigt_am, notiz
```

**Tabelle: wissen_regeln**
```
id, kategorie, titel, inhalt, erstellt_am
```
→ Direkt in Kira-System-Prompt injiziert bei jedem Chat

**Tabelle: kira_konversationen**
```
id, kira_id, session_id, benutzer_input, kira_antwort,
tools_genutzt, tokens_in, tokens_out, model, provider, erstellt_am
```

**Tabelle: geloeschte_protokoll**
```
id, konto, datum_mail, absender, betreff, kurzinhalt, datum_geloescht
```
→ Kira hat Zugriff (im System-Prompt: "Gelöschte Mails Protokoll")

**Tabelle: geschaeft_statistik**
```
id, ereignis, daten_json, ts
```
→ Für Zahlungsdauer-Berechnung (Ø Tage bis Zahlung)

### 4.2 runtime_events.db (24 MB) — Event-Store

**Tabelle: events** (25 Spalten)
```
id, ts, session_id, event_type, source, modul, submodul,
actor_type, context_type, context_id, action, status, result,
error_code, error_message, provider, model, token_in, token_out,
duration_ms, follow_up, related_event_id, has_payload,
created_at, summary
```

**Tabelle: event_payloads**
```
event_id, payload_type, content
```
Payload-Typen: `user_input`, `assistant_output`, `context_snapshot`, `entity_snapshot`, `settings_before`, `settings_after`, `mail_body`, `thread_excerpt`, `raw_request`, `raw_response`

5 Event-Typen:
- `ui` — Panel-Wechsel, Button-Klick, Workspace öffnen
- `kira` — Chat, Tool-Aufruf, Antwort-Entwurf
- `llm` — Provider, Modell, Tokens, Dauer, Fallback
- `system` — Server-Start, Mail-Monitor, Daily-Check, Proaktiv
- `settings` — Einstellungs-Änderung mit Vor/Nach-Wert

**Schreib-Funktion `elog()`:**
```python
elog(event_type, action, summary, *, session_id, modul, source,
     actor_type, context_type, context_id, status, result,
     provider, model, token_in, token_out, duration_ms,
     user_input, assistant_output, ...) → event_id (str)
```

**Lese-Funktionen:**
- `eget(limit, event_type, modul, search)` → Liste von Events
- `eget_payload(event_id)` → Vollkontext-Dict
- `estats()` → Statistiken (total, fehler, heute, by_type, ...)
- `get_recent_for_kira(limit)` → Formatierter Text für System-Prompt

### 4.3 mail_index.db (14 MB) — Mail-Index

**Tabelle: mails** (12.642 Einträge)
```
id, message_id, datum, datum_iso, absender, absender_short, an,
betreff, folder, text_plain, text_html, hat_anhaenge, anhaenge,
konto, konto_label, klassifiziert
```

Indizes: `(datum_iso DESC)`, `(absender, datum_iso DESC)`, `(message_id)`, `(folder)`

5 Mail-Konten:
- `anfrage@raumkult.eu`
- `info@raumkult.eu`
- `invoice@sichtbeton-cire.de`
- `kaimrf@rauMKultSichtbeton.onmicrosoft.com`
- `shop@sichtbeton-cire.de`

### 4.4 kunden.db (14 MB) — Kundenstamm

**Tabelle: kunden** (7.321 Interaktionen)
```
kunden_email, kontakte, erstkontakt, letzter_kontakt, notizen
```

Verknüpft über `kunden_email` mit `tasks.kunden_email`.

### 4.5 Weitere Datenbanken

| DB | Größe | Zweck |
|---|---|---|
| `sent_mails.db` | 2,3 MB | 525 versendete Mails — Stil-Lernbasis für LLM |
| `newsletter.db` | 120 KB | Auto-klassifizierte Newsletter |
| `rechnungen_detail.db` | 360 KB | PDF-extrahierte Rechnungsdetails (OCR) |

### 4.6 Datenbankverbindungen — wer greift wo zu

```
server.py        → tasks.db, kunden.db, mail_index.db, runtime_events.db,
                   sent_mails.db, rechnungen_detail.db
kira_llm.py      → tasks.db, kunden.db, mail_index.db, rechnungen_detail.db
mail_monitor.py  → tasks.db, mail_index.db, kunden.db, runtime_events.db
daily_check.py   → tasks.db, mail_index.db, kunden.db, sent_mails.db
kira_proaktiv.py → tasks.db, kunden.db, mail_index.db
runtime_log.py   → runtime_events.db (WAL-Modus, Thread-safe mit Lock)
task_manager.py  → tasks.db
```

---

## 5. Mail-System — Eingang bis Task

### 5.1 IMAP-Architektur (mail_monitor.py)

**Haupt-Loop (~60 Sekunden):**
```
Für jedes der 5 Konten:
  1. IMAP-Verbindung via OAuth2 (Microsoft Entra KIRA-App)
  2. Neue Mails via IMAP UID (inkrementell, nicht alles)
  3. Mail in Archiv schreiben (OneDrive/Mail Archiv/{konto}/{folder}/{datum}/)
  4. mail_index.db aktualisieren
  5. Mail klassifizieren (Fast-Path oder LLM)
  6. Task erstellen wenn antwort_noetig=true
  7. Push-Notification via ntfy.sh
Alle 15 Minuten:
  → kira_proaktiv.run_all_scans()
```

**OAuth2-Token-Flow:**
```
Einstellungen → "Mit Microsoft anmelden" Button
    → POST /api/mail/konto/oauth-start (job_id, email)
    → MSAL PublicClientApplication.acquire_token_interactive()
    → Browser öffnet Microsoft-Login
    → Token in TOKEN_DIR/{email}_token.json gespeichert
    → JS pollt GET /api/mail/konto/oauth-status (job_id)
    → Formular aktualisiert
```

**3-stufige Provider-Erkennung (neue Konten):**
1. Domain-Heuristik (100+ hardcodierte Domains)
2. DNS MX-Record + Autodiscover-URL
3. Microsoft OpenID-Config-Probe

### 5.2 Mail-Archiv-Struktur (OneDrive)
```
Mail Archiv/
  Archiv/
    {konto_label}/          z.B. "anfrage"
      {folder}/             z.B. "INBOX"
        {YYYY-MM-DD}/
          {message-id}/
            mail.json       ← Metadaten + Volltext
            [Anhänge]       ← Nur wenn vorhanden
```

`mail.json` enthält: message_id, datum, absender, an, betreff, text_html, text_plain, hat_anhaenge, anhaenge, konto, folder, klassifizierung

### 5.3 Mail → Task-Erstellung

Automatisch wenn `antwort_noetig=true` aus Klassifizierung:
```python
tasks.insert(
    typ=kategorie_to_task_typ(kategorie),
    kategorie=kategorie,
    titel=betreff[:200],
    kunden_email=absender,
    status='offen',
    prioritaet=prio,
    antwort_noetig=1,
    beantwortet=0,
    message_id=msg_id
)
```

### 5.4 Mail-Nachklassifizierung (recheck_mails)
Manuell auslösbar über UI-Button oder:
```bash
python daily_check.py --seit 2026-01-01 --bis 2026-03-30
```
→ Durchsucht mail_index.db für Zeitraum → klassifiziert neu → erstellt fehlende Tasks

---

## 6. Proaktive Automatisierung

### 6.1 kira_proaktiv.py — 5 Scan-Module

Läuft alle 15 Minuten via `mail_monitor.py`. State in `knowledge/proaktiv_state.json` (verhindert Spam per TTL).

**Scan 1: Überfällige Rechnungen**
- Query: `ausgangsrechnungen WHERE status='offen'`
- Stufen: ≥14 Tage → Zahlungserinnerung, ≥30 Tage → 2. Mahnung, ≥45 Tage → 3. Mahnung
- Aktion: Task erstellen (Typ "Mahnung") + ntfy-Push
- TTL: 72 Stunden (kein Spam)

**Scan 2: Angebote Nachfass**
- Query: `angebote WHERE status='offen'`
- Intervalle aus `config.json`: 7/14/30 Tage (3x max)
- Aktion: Task (Typ "Nachfass") + ntfy-Push
- TTL: 48 Stunden

**Scan 3: Leads ohne Antwort**
- Query: `tasks WHERE kategorie IN ('Neue Lead-Anfrage','Antwort erforderlich') AND antwort_noetig=1 AND beantwortet=0`
- Grenze aus `config.json`: `unanswered_check_days` (Standard: 2 Tage)
- Aktion: Reminder-Task

**Scan 4: Tagesstart-Briefing**
- Nur zwischen 06:00–10:00 Uhr
- LLM generiert Zusammenfassung: offene RE + Nachfass + Tasks + neue Mails
- ntfy-Push + elog() als `system`-Event
- TTL: 24 Stunden (1x täglich)

**Scan 5: Neue Kunden erkennen**
- Query: kunden mit ≥2 Kontakten aber nicht in tasks.db als Kunden bekannt
- Aktion: Notiz-Task "Neuer Lead erkannt"

### 6.2 daily_check.py — Nacht-Routine

1. Archiv-Ordner nach neuen Mails scannen (inkrementell seit letztem Lauf)
2. Klassifizierung nachholen (über llm_classifier.py)
3. Tasks für unklassifizierte/unbeantwortete Mails erstellen
4. Erinnerungen für offene Tasks (via task_manager.get_due_reminders())
5. Tagesstart-Briefing (wenn 6–10 Uhr)

Status in `knowledge/daily_check_status.json` gespeichert.

### 6.3 Push-Notifications (ntfy.sh)
- Topic: `raumkult_kira` (aus config.json)
- Arbeitszeit-Filter: nur 06:00–20:00 Uhr (konfigurierbar)
- Urlaub-Modus: alle Pushes stumm
- Prioritäten: `default`, `high`, `urgent`

---

## 7. Dashboard & Server

### 7.1 server.py — Architektur

`ThreadedHTTPServer` auf `127.0.0.1:8765`, ein Thread pro Request.

**HTML-Generierung:**
- `GET /` → komplette Seite (alle 6 Panels inline)
- Kein Template-System — reiner Python f-string
- CSS-Namespaces: `kq-*` (Quick Panel), `kw-*` (Workspace), `es-*` (Einstellungen), `kd-*` (Dashboard), `kk-*` (Kommunikation), `kg-*` (Geschäft)

**GET-Endpunkte (wichtigste):**
- `GET /` — Haupt-Dashboard
- `GET /api/runtime/events` — Event-Liste
- `GET /api/runtime/stats` — Statistiken
- `GET /api/runtime/payload` — Vollkontext eines Events
- `GET /api/einstellungen` — Aktuelle Einstellungen
- `GET /api/mail/konten/stats` — Konto-Status + Ordner
- `GET /api/kira/conversations` — Chat-Verlauf
- `GET /api/kira/briefing` — Tagesstart-Briefing
- `GET /api/mail/nachklassifizieren/status` — Fortschritt Nachklassifizierung

**POST-Endpunkte (wichtigste):**
- `POST /api/kira/chat` — Kira-LLM-Aufruf
- `POST /api/runtime/event` — UI-Event loggen
- `POST /api/einstellungen` — Einstellungen speichern
- `POST /api/mail/konto/oauth-start` — OAuth2-Flow starten
- `POST /api/mail/verschieben` — IMAP-Ordner verschieben
- `POST /api/mail/snooze` — Mail snoozen (7 Presets + Freitext)
- `POST /api/task/{id}/status` — Task-Status ändern
- `POST /api/wissen/neu` — Wissens-Regel speichern
- `POST /api/mail/nachklassifizieren` — Nachklassifizierung starten
- `POST /api/kira/provider/check-models` — Modell-Verfügbarkeit prüfen + Auto-Update (session-ll)
- `POST /api/kira/provider/save-key` — API-Key speichern
- `POST /api/kira/provider/add` / `toggle` / `move` / `delete` — Provider-CRUD

**GET-Endpunkte (Ergänzungen seit session-hh/ii/kk):**
- `GET /api/mail/folders` — Live-IMAP-Ordner (60s Cache, UTF-7 decoded)
- `GET /api/mail/snooze/count` — Anzahl aktiver Snooze-Mails
- `GET /api/mail/protokoll` — Gelöschte-Protokoll-Einträge
- `GET /api/mail/kira-kontext` — Volltext EML + Absender-Verlauf + Tasks (für Kira-Button, session-kk)

### 7.2 Einstellungen — Speicherung
Einstellungen werden in `config.json` gespeichert:
```python
config = load_config()
config.update(request_data)
config_file.write_text(json.dumps(config, indent=2))
# Änderung → elog('settings', ...)
```
Secrets (API-Keys) gehen NUR in `secrets.json`, NIEMALS in `config.json`.

---

## 8. Konfiguration & Secrets

### 8.1 config.json (versioniert)
```json
{
  "server": {"host": "127.0.0.1", "port": 8765},
  "mail_archiv": {
    "pfad": "C:\\Users\\kaimr\\OneDrive - rauMKult Sichtbeton\\...",
    "konten": [{...}],
    "sync_ordner": {...}
  },
  "aufgaben": {"unanswered_check_days": 2, ...},
  "nachfass": {"aktiv": true, "intervall_1_tage": 7, ...},
  "ntfy": {"aktiv": true, "topic_name": "raumkult_kira", ...},
  "runtime_log": {"aktiv": true, "kira_darf_lesen": true, ...},
  "llm_providers": [{...}]
}
```

### 8.2 secrets.json (NIEMALS committen, .gitignore)
```json
{
  "anthropic_api_key": "sk-ant-...",
  "openai_api_key": "sk-...",
  "openrouter_api_key": "sk-...",
  "github_pat": "ghp_..."
}
```

### 8.3 Microsoft OAuth2
- Zentrale KIRA Entra App: Client-ID `a0591b2d-86c3-...`
- Token-Cache: lokal in `TOKEN_DIR/{email}_token.json`
- Scope-Version `v5_imap_smtp` erzwingt Token-Reset bei Upgrade
- Unterstützt: IMAP XOAUTH2 (Microsoft Exchange Online)

---

## 9. Partner-View (Leni)

- URL: `https://kaimarienfeld.github.io/kira-partner/`
- Statisches HTML (generiert von `generate_partner_view.py`)
- Passwortgeschützt (Frontend-only)
- 24 Features sichtbar (aus 38 gesamt)
- Filter: Alle / Eingebaut / Geplant / Leni-Ideen / Neu
- Feedback-System: Leni hinterlässt Ideen → ntfy an Kai
- Admin-Panel: Nur für Kai (separater Login)
- Generierung: `python scripts/generate_partner_view.py --push` → GitHub Pages

---

## 10. Fehler & Irregularitäten — mit Behebungsvorschlägen

### KRITISCH (verhindert/beeinträchtigt aktive Arbeit)

---

#### FEHLER-01: Falsches Standard-Modell in kira_llm.py — ✅ BEHOBEN (session-jj)
**Datei:** `scripts/kira_llm.py`, Zeile 40
**Problem:** Der Standard-Modell-ID lautet `claude-sonnet-4-20250514`. Das aktuell korrekte Modell laut Anthropic-Dokumentation ist `claude-sonnet-4-6`. Bei API-Anfragen an einen ungültigen Snapshot schlägt der Aufruf mit HTTP 404 fehl — Kira antwortet nicht.
**Fix (session-ll):** Zusätzlich automatische Modell-Validierung implementiert — solche Fehler werden künftig auto-korrigiert.

```python
# Aktuell (möglicherweise deprecated Snapshot):
"default_model": "claude-sonnet-4-20250514"

# Korrekt (aktuelles Modell):
"default_model": "claude-sonnet-4-6"
```

**Behebung:** In `kira_llm.py` Zeile 36 und 40 ändern:
```python
("claude-sonnet-4-6", "Claude Sonnet 4.6"),  # Zeile 36
"default_model": "claude-sonnet-4-6",          # Zeile 40
```
Danach in `config.json` unter `llm_providers[0].model` ebenfalls aktualisieren — oder in den Einstellungen im Browser neu setzen.

---

#### FEHLER-02: ARCHIV_ROOT hardcoded in mehreren Dateien — ✅ BEHOBEN (session-jj)
**Dateien:** `scripts/daily_check.py` (Zeile 32), `scripts/build_databases.py` (Zeile 20)
**Problem:** Der OneDrive-Archiv-Pfad ist absolut und statisch codiert. Wenn OneDrive den Pfad ändert (Synchronisierung, Umbenennung, anderer User), bricht der gesamte Mail-Scan ab. `daily_check.py` findet dann keine Mails mehr, Tasks werden nicht erstellt.

```python
# Hardcoded — bricht wenn OneDrive-Pfad sich ändert:
ARCHIV_ROOT = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\Archiv")
```

**Behebung:** Beide Dateien sollen den Pfad aus `config.json` lesen (wo er bereits korrekt gespeichert ist):
```python
# Stattdessen: aus config.json lesen
import json
_cfg = json.loads((Path(__file__).parent / "config.json").read_text('utf-8'))
ARCHIV_ROOT = Path(_cfg.get("mail_archiv", {}).get("pfad", "")) / "Archiv"
```

---

#### FEHLER-03: KNOWLEDGE_DIR absolutpfad in build_databases.py — ✅ BEHOBEN (session-jj)
**Datei:** `scripts/build_databases.py`, Zeile 21
**Problem:** Der Pfad zur knowledge-Datenbank ist als absoluter Claude-Projektpfad codiert. Wenn das Projekt jemals von einem anderen Ort gestartet wird (z.B. nach Neuinstallation), schreibt build_databases.py in den falschen Ordner oder schlägt fehl.

```python
# Hardcoded absolut (bricht bei anderem Pfad):
KNOWLEDGE_DIR = Path(r"C:\Users\kaimr\.claude\projects\C--Users-kaimr-...\memory\knowledge")
```

**Behebung:** Relativ zum Skript berechnen (wie alle anderen Module es tun):
```python
KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
```

---

#### FEHLER-04: kira_proaktiv.py — Logging im Daemon-Modus stumm — ✅ BEHOBEN (session-jj)
**Datei:** `scripts/kira_proaktiv.py`, Zeile 45
**Problem:** `log = logging.getLogger("kira_proaktiv")` erstellt einen Logger. `logging.basicConfig()` wird aber nur in `if __name__ == "__main__"` (Zeile 596+) aufgerufen. Wenn `kira_proaktiv` via `mail_monitor.py` als Modul importiert und ausgeführt wird, haben alle `log.error()` und `log.debug()` Aufrufe keinen Handler — Fehler werden vollständig verschluckt.

**Konkrete Auswirkung:** Wenn ein Proaktiv-Scan intern fehlschlägt (DB gesperrt, JSON-Fehler, fehlende Spalte), gibt es keinerlei Log-Eintrag. Der Scan schlägt lautlos fehl, Tasks werden nicht erstellt.

**Behebung:** Logging auch im Modul-Kontext einrichten:
```python
# Direkt nach Zeile 45, außerhalb des if __name__ == "__main__"-Blocks:
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter('%(asctime)s [kira_proaktiv] %(levelname)s: %(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.INFO)
```

---

#### FEHLER-05: _auto_angebot_aktion() ohne NULL-Check für angebot_nummer
**Datei:** `scripts/mail_monitor.py` (Funktion `_auto_angebot_aktion`, ca. Zeile 1141)
**Problem:** Die Funktion prüft zwar ob `angebot_aktion` vorhanden ist, aber `angebot_nummer` kann `None` oder `""` sein. Der anschließende SQL-Query `WHERE a_nummer=?` mit `None` liefert kein Ergebnis (statt Fehler) — die Angebots-Verknüpfung schlägt dann lautlos fehl.

**Behebung:**
```python
def _auto_angebot_aktion(result, kunden_email, betreff, msg_id):
    angebot_aktion = result.get("angebot_aktion")
    angebot_nummer = result.get("angebot_nummer")
    if not angebot_aktion or not angebot_nummer:  # ← angebot_nummer ergänzen
        return {}
    ...
```

---

### WICHTIG (beeinträchtigt Zuverlässigkeit)

---

#### FEHLER-06: task_manager.py — DB-Verbindungen nicht mit Context Manager — ✅ BEHOBEN (session-jj, try/finally)
**Datei:** `scripts/task_manager.py`, alle Funktionen (z.B. Zeile 34–49)
**Problem:** Datenbankverbindungen werden mit `db = get_tasks_db()` geöffnet und manuell mit `db.close()` geschlossen. Wenn zwischen open und close eine Exception auftritt, bleibt die Verbindung offen (Leak). Bei vielen parallelen Anfragen (mehrere Browser-Tabs, Hintergrundprozesse) können SQLite-Locks entstehen.

```python
# Aktuell (fragil):
db = get_tasks_db()
db.execute(...)
db.commit()
db.close()  # ← wird übersprungen bei Exception
```

**Behebung:** `with`-Statement verwenden:
```python
with get_tasks_db() as db:
    db.execute(...)
    db.commit()
# Verbindung automatisch geschlossen, auch bei Exception
```

Alternativ: `get_tasks_db()` als Context Manager implementieren (`__enter__`/`__exit__`).

---

#### FEHLER-07: proaktiv_state.json — kein File-Locking
**Datei:** `scripts/kira_proaktiv.py`, Zeilen 61–65
**Problem:** `_save_state()` schreibt direkt auf Datei ohne Locking. Wenn mail_monitor.py nach einem Absturz doppelt läuft (alter Prozess + neuer), können beide gleichzeitig schreiben. Der zuletzt Schreibende überschreibt die Änderungen des anderen — State-Einträge gehen verloren, gleiche Tasks werden mehrfach erstellt.

**Behebung (Windows-kompatibel):**
```python
import msvcrt, os

def _save_state(state: dict):
    try:
        path = str(SCAN_STATE_FILE)
        with open(path, 'w', encoding='utf-8') as f:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            f.write(json.dumps(state, ensure_ascii=False, indent=2))
    except Exception:
        pass
```
Oder pragmatisch: `proaktiv_state.json` in eine SQLite-Tabelle migrieren (atomic writes).

---

#### FEHLER-08: SyntaxWarnings in server.py (ISS-003) — ✅ BEHOBEN (session-jj, 7 Stellen)
**Datei:** `scripts/server.py`, ca. Zeilen 4789–4791
**Problem:** Ungültige Escape-Sequences in Regex-Strings ohne `r`-Prefix. Python gibt SyntaxWarnings aus — bei künftigen Python-Versionen werden diese zu SyntaxErrors und crashen den Server beim Start.

```python
# Problematisch:
re.sub("\d+", ...)  # \d ist kein gültiges Python-Escape → SyntaxWarning

# Korrekt:
re.sub(r"\d+", ...)
```

**Behebung:** Alle betroffenen Regex-Strings auf Raw-Strings umstellen (`r"..."` statt `"..."`).

---

### NIEDRIG (Sauberkeit & Wartbarkeit)

---

#### FEHLER-09: MAILBOXEN und KONTO_LABEL hardcoded in daily_check.py — ✅ BEHOBEN (session-jj)
**Datei:** `scripts/daily_check.py`, Zeilen 33–38
**Problem:** Konto-Liste und Label-Mapping sind als Konstanten im Code fest. Wenn ein neues Mail-Konto in `config.json` angelegt wird, muss `daily_check.py` manuell angepasst werden — sonst ignoriert der Daily-Check das neue Konto.

**Behebung:** Konten aus `config.json` lesen:
```python
_cfg = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
_konten = _cfg.get("mail_archiv", {}).get("konten", [])
KONTO_LABEL = {k["email"]: k.get("konto_label", k["email"]) for k in _konten if k.get("aktiv")}
```

---

#### FEHLER-10: gpt-4.1-2025-04-14 als wählbares Modell — 🔄 ENTSCHÄRFT (session-ll)
**Datei:** `scripts/kira_llm.py`, Zeile 50
**Problem:** `gpt-4.1-2025-04-14` ist als OpenAI-Modell-Option in der Dropdown-Liste. Es ist unklar ob diese Modell-ID in der OpenAI-API existiert. Wählt der Nutzer es aus, schlagen alle Kira-Anfragen mit HTTP 404 fehl.

**Behebung:** Entweder entfernen oder auf bekannte IDs wie `gpt-4o`, `gpt-4o-mini`, `o3-mini` beschränken.
**Status session-ll:** Das neue Modell-Validierungssystem erkennt ungültige Modelle automatisch beim ersten Aufruf und wechselt auf das nächste in der Fallback-Ranking-Liste — das Risiko ist damit systemisch entschärft.

---

### BEKANNTE ISSUES (aus known_issues.json, ALLE BEHOBEN)

Die 15 bekannten Issues ISS-001 bis ISS-015 sind laut Projektdokumentation alle behoben. Letzte offene war ISS-003 (SyntaxWarnings) — hier als FEHLER-08 weitergeführt.

---

## Zusammenfassung: Prioritäts-Matrix

| # | Fehler | Datei | Auswirkung | Schwere | Status |
|---|---|---|---|---|---|
| 01 | Standard-Modell-ID veraltet | kira_llm.py:40 | Kira antwortet nicht | KRITISCH | ✅ jj |
| 02 | ARCHIV_ROOT hardcoded | daily_check.py:32 | Mail-Scan bricht ab | KRITISCH | ✅ jj |
| 03 | KNOWLEDGE_DIR absolut | build_databases.py:21 | Rebuild schlägt fehl | KRITISCH | ✅ jj |
| 04 | Logging stumm im Daemon | kira_proaktiv.py:45 | Fehler unsichtbar | KRITISCH | ✅ jj |
| 05 | NULL-Check fehlt (_auto_angebot_aktion) | mail_monitor.py | TypeError wenn msg_id/kunde_name None | WICHTIG | ✅ pp |
| 06 | DB-Verbindungs-Leak | task_manager.py | SQLite-Locks möglich | WICHTIG | ✅ jj |
| 07 | State-File Race Condition | kira_proaktiv.py:61 | Doppelte Tasks möglich | WICHTIG | ✅ pp |
| 08 | SyntaxWarnings | server.py | Zukünftiger Server-Crash | WICHTIG | ✅ jj |
| 09 | Konten hardcoded | daily_check.py:33 | Neue Konten ignoriert | NIEDRIG | ✅ jj |
| 10 | Ungültige Modell-Option | kira_llm.py:50 | Fehler wenn gewählt | NIEDRIG | ✅ ll |
| 11 | rechnung_bezahlt: blindes UPDATE | kira_llm.py | Duplikat-Statistik-Einträge | HOCH | ✅ oo |
| 12 | Kein Exponential Backoff bei API-Fehlern | kira_llm.py | Endloser Fehler-Loop | MITTEL | ✅ oo |
| 13 | kira_konversationen nicht im System-Prompt | kira_llm.py | Kein Gedächtnis | MITTEL | ✅ oo |
| 14 | System-Prompt wächst unbegrenzt | kira_llm.py:570 | Context-Degradierung | NIEDRIG | ✅ oo |
| 15 | Task-Löschen blockiert Server (sync kira_chat) | server.py | Server 10-30s eingefroren | HOCH | ✅ pp |

### Neu implementiert (session-ll)
| Feature | Datei | Beschreibung |
|---|---|---|
| `ModelNotFoundError` | kira_llm.py | Spezifische Exception für Modell-404 |
| `_fetch_provider_models()` | kira_llm.py | API-Modell-Liste, 24h-Cache |
| `_validate_model()` | kira_llm.py | Modell gegen API-Liste prüfen |
| `_auto_update_model()` | kira_llm.py | config.json aktualisieren + ntfy Push |
| `validate_all_providers()` | kira_llm.py | Alle Provider, schreibt state-file |
| `POST /api/kira/provider/check-models` | server.py | Manueller UI-Trigger |
| 🟡 Status-Icon | server.py | Warnt bei veraltetem Modell in Einstellungen |
| 🔍 Modell-Button | server.py | Pro Provider-Karte in Einstellungen |
| `_model_validation_loop` | server.py | Täglicher Hintergrund-Thread |

---

### Neu implementiert (session-nn)
| Feature | Datei | Beschreibung |
|---|---|---|
| `case_engine.py` | scripts/ | Kern-Modul: create_vorgang, update_status, link_entity, get_pending_signals, mark_signal_shown, get_vorgang_summary_for_kira |
| `vorgang_router.py` | scripts/ | Routing: Mail-Klassifizierung → Vorgang-Typ, Konfidenz-basierte Entscheidungsstufe |
| `presence_detector.py` | scripts/ | Windows-Idle-Detection via ctypes.windll.user32.GetLastInputInfo() |
| `activity_window.py` | scripts/ | Desktop-Overlay (tkinter -topmost), Signal-Watcher-Thread 15s |
| `case_engine_backfill.py` | scripts/ | Einmalige Migration: Bestandsdaten → Vorgänge |
| Vorgang-Router-Integration | mail_monitor.py + daily_check.py | Nach jedem Task-INSERT: route_classified_mail() aufrufen |
| 8 neue API-Endpunkte | server.py | GET/POST /api/vorgaenge, /api/vorgang/{id}, /api/vorgang/signals, /api/vorgang/neu, /api/vorgang/{id}/status, /api/vorgang/{id}/link, /api/vorgang/signal/gelesen, /api/presence |
| Signal-Polling-JS | server.py | Browser-seitig: Toast (Stufe B), Modal (Stufe C), 10s Intervall |
| Desktop-Signal-Watcher | server.py + activity_window.py | Startet beim Server-Start |
| 2 neue LLM-Tools | kira_llm.py | `vorgang_kontext_laden`, `vorgang_status_setzen` |
| System-Prompt Vorgänge | kira_llm.py | Offene Vorgänge (limit=8) im Kira-Kontext |
| State-Machine-Validierung | case_engine.py | Ungültige Übergänge werden abgelehnt (HTTP 400 mit erlaubten Übergängen) |
| Query-String Routing-Fix | server.py | `/api/vorgang/signals?limit=5` → `startswith()` statt `==` |
| f-String Escaping-Fix | server.py | Alle `{}`/`{{}}` in eingebetteten JS-Blöcken korrekt gedoppelt |

---

### Neu implementiert (session-oo) — Vollständige Aktive Assistenz
| Feature | Datei | Beschreibung |
|---|---|---|
| Tool-Idempotenz | kira_llm.py | rechnung_bezahlt, angebot_status, eingangsrechnung_erledigt, task_erledigen: Pre-Check + Early Return |
| Circuit Breaker + Backoff | kira_llm.py | `_CIRCUIT_BREAKER`: 3 Fehler/60s → Provider-Circuit 300s offen, Exponential Backoff 2^attempt |
| Rate-Limiting | kira_llm.py | `_rate_check_and_record()`: max 20 LLM-Calls/Min (rolling window) |
| `mail_approve_queue` | tasks.db | HITL-Gate-Tabelle: pending/approved/rejected/sent/expired |
| Tool: `mail_senden` | kira_llm.py | Erstellt Entwurf in Approval-Queue, Signal Stufe B, sendet NIE direkt |
| Mail-Approve API | server.py | `GET /api/mail/approve/pending`, `POST /api/mail/approve/{id}` |
| Mail-Approve Dashboard | server.py | Header-Badge "N Freigabe", Preview-Modal, Approve/Reject/Edit |
| Konversations-Gedächtnis | kira_llm.py | letzte 3 Sessions pro Kunde in system_prompt, Token-Budget 800 |
| Tool: `konversation_suchen` | kira_llm.py | Sucht in kira_konversationen nach Suchbegriff, max 5 Sessions |
| Tägliche Memory-Summary | kira_proaktiv.py | Scan 6: fasst Kira-Konversationen via LLM, speichert in wissen_regeln |
| Context-Window-Budgets | kira_llm.py | Runtime-Log max 30, Wissen max 20, Memory max 3200 Zeichen |
| Scan: Angebot-Followup | kira_proaktiv.py | Scan 7: angebot_versendet > 7 Tage → Nachfass-Entwurf in approval queue |
| Scan: Mahnung-Eskalation | kira_proaktiv.py | Scan 8: mahnung > 14 Tage → Signal Stufe B |
| Scan: Autonomy-Decision | kira_proaktiv.py | Scan 9: LLM analysiert alle Vorgänge → Konfidenz-Stufen A/B/C |
| Tool: `vorgang_naechste_aktion_vorschlagen` | kira_llm.py | valid_transitions → LLM wählt optimalen nächsten Schritt |
| ReAct-Schleife | kira_llm.py | `start_react_task()`: max 5 Runden, [WEITER]-Signal, Background-Thread |
| API: `/api/kira/task` | server.py | Komplexe Aufgabe → task_id + SSE-Stream-Polling |
| User-Interrupt | server.py | `DELETE /api/kira/task/{id}` |
| 👍/👎 Feedback | server.py | Pro Kira-Antwort im Workspace, `POST /api/kira/feedback` |
| Auto-Wissensregel aus 👎 | server.py | LLM extrahiert Lernregel, INSERT wissen_regeln Kategorie auto_gelernt |
| Stil-Lernen aus Mail-Edits | server.py | Diff > 40% → LLM extrahiert Stil-Regel |
| FTS5 Mail-Index | mail_index.db | Virtual Table mail_fts, BM25-Ranking, Auto-Trigger |
| Tool: `semantisch_suchen` | kira_llm.py | FTS5 MATCH statt LIKE, Top-10 BM25-sortiert |
| MS Graph Kalender | graph_calendar.py | MSAL silent acquire, Calendars.ReadWrite Scope |
| Tool: `termin_erstellen` | kira_llm.py | POST Graph /me/events, Stufe B Signal, UTC→Europe/Berlin |
| Tool: `termine_anzeigen` | kira_llm.py | GET Graph /me/calendarView, nächste 7 Tage |
| actor_type-Standard | runtime_log.py | kira_autonom / kira_vorschlag / user / system |
| Dashboard-Tab: Kira-Aktivitäten | server.py | Timeline: letzte 30 Tage, 🤖/👤 Icons, Filter nach actor_type |
| API: `/api/kira/aktivitaeten` | server.py | Events nach actor_type kira_autonom/kira_vorschlag |
| Live-Migration | case_engine_backfill.py | 83 Vorgänge aus Bestandsdaten (2026-03-31 06:38) |

### Neu implementiert (session-pp) — Bug-Fixes
| Feature | Datei | Beschreibung |
|---|---|---|
| B-04 NULL-Check | mail_monitor.py | _auto_angebot_aktion: msg_id/kunde_name/a_nummer abgesichert |
| B-05 Race Condition | kira_proaktiv.py | threading.Lock + atomischer os.replace()-Schreibvorgang |
| Task-Löschen entblockt | server.py | Synchrones kira_chat() entfernt; Lernregel direkt ohne LLM gespeichert |

---

## 11. Case Engine — Vorgang-Layer (session-nn)

### 11.1 Konzept

Die **Case Engine** ist ein Vorgang-Layer (engl. "Case") oberhalb von Tasks und Mails. Ein Vorgang repräsentiert einen vollständigen Geschäftsprozess — von der ersten Anfrage bis zum Abschluss. Er verknüpft mehrere Tasks, Mails, Rechnungen und Angebote unter einem gemeinsamen Kontext.

```
Mail eingeht
  → Klassifizierung (FastPath oder LLM)
  → Task erstellt (tasks.db)
  → Vorgang-Router (vorgang_router.py)
      → Existiert Vorgang für diesen Kunden? → Link
      → Neuer Vorgang? → create_vorgang() → Entscheidungsstufe bestimmen
          → Stufe A: stumm gespeichert
          → Stufe B: Signal in vorgang_signals → Browser-Toast
          → Stufe C: Signal + Desktop-Overlay (tkinter)
```

### 11.2 Datenbank-Tabellen (tasks.db)

**vorgaenge**
```
id, typ, kunden_email, kunden_name, titel, status, konto,
quelle, konfidenz, entscheidungsstufe,
erstellt_am, aktualisiert_am, abgeschlossen_am
```

**vorgang_history**
```
id, vorgang_id, von_status, nach_status, grund, actor, ts
```

**vorgang_entities**
```
id, vorgang_id, entity_typ, entity_id, rolle, erstellt_am
```
Entity-Typen: `task`, `mail`, `ausgangsrechnung`, `angebot`, `eingangsrechnung`

**vorgang_signals**
```
id, vorgang_id, stufe, titel, nachricht, angezeigt, angezeigt_am,
angezeigt_wie, erstellt_am
```

### 11.3 Vorgang-Typen und State Machines

10 Typen mit jeweils eigener Zustands-Maschine:

| Typ | Wichtige Status | Endstatus |
|---|---|---|
| `lead` | neu_eingang → qualifiziert → angebot_gesendet → ... | angenommen, abgelehnt, archiviert |
| `angebot` | neu_eingang → angebot_versendet → angenommen / abgelehnt | abgeschlossen |
| `rechnung` | rechnung_gestellt → bezahlt / überfällig → mahnung | abgeschlossen |
| `mahnung` | mahnung_versandt → mahnung_2 → mahnung_3 → inkasso | abgeschlossen |
| `support` | offen → in_bearbeitung → wartend_auf_kunde → gelöst | abgeschlossen |
| `projekt` | planung → in_umsetzung → abnahme_ausstehend | abgeschlossen |
| `partner` | kontaktiert → in_verhandlung → aktiv | beendet |
| `lieferant` | anfrage → angebot_erhalten → bestellt | abgeschlossen |
| `intern` | offen → in_bearbeitung | erledigt |
| `sonstige` | offen → in_bearbeitung | erledigt |

Ungültige Übergänge werden von `update_status()` abgelehnt → HTTP 400 mit `erlaubte_uebergaenge`.

### 11.4 Vorgang-Router (vorgang_router.py)

**KATEGORIE_ZU_VORGANG_TYP** — Mapping:
```python
"Neue Lead-Anfrage"         → "lead"
"Angebotsrueckmeldung"      → "angebot"
"Zahlungseingang"           → "rechnung"
"Beschwerden/Reklamationen" → "support"
"Projektanfrage"            → "projekt"
"Partner-Anfrage"           → "partner"
"Lieferanten-Kommunikation" → "lieferant"
"Interne Kommunikation"     → "intern"
# Newsletter, Spam, System → kein Vorgang
```

**Konfidenz → Entscheidungsstufe:**
- ≥ 0.85 (hoch) → Stufe A (automatisch, stumm)
- 0.60–0.84 (mittel) → Stufe B (SSE-Toast im Browser)
- < 0.60 (niedrig) → Stufe C (Modal + Desktop-Overlay)

### 11.5 Entscheidungsstufen im Detail

**Stufe A — Automatisch:**
- Vorgang wird angelegt, kein User-Feedback nötig
- kira_proaktiv.py und mail_monitor.py laufen durch ohne Interrupt

**Stufe B — Browser-Toast:**
- Signal in `vorgang_signals` gespeichert
- JavaScript-Polling alle 10s: `GET /api/vorgang/signals?limit=5`
- Gelber/lila Toast erscheint oben rechts im Dashboard
- Nutzer klickt "OK" → `POST /api/vorgang/signal/gelesen`

**Stufe C — Desktop-Modal + Overlay:**
- Signal-Polling erkennt `stufe == "C"` → Fullscreen-Modal im Browser
- Parallel: `activity_window.py` Signal-Watcher (15s) → tkinter -topmost Fenster
- Desktop-Overlay erscheint auch wenn Browser-Tab nicht aktiv ist
- Presence-Check: kein Popup wenn Nutzer > 5 Min inaktiv

### 11.6 Backfill (case_engine_backfill.py)

Migration bestehender Daten in das Vorgang-System:
```bash
python scripts/case_engine_backfill.py --dry-run  # Vorschau
python scripts/case_engine_backfill.py            # Live
```
Idempotent: bereits migrierte Datensätze (vorgang_id ≠ NULL) werden übersprungen.

---

## 12. GAP-Analyse: Vollständige Aktive Assistenz

### 12.1 Was KIRA heute ist (Code-Realität) — Stand: 2026-03-31

KIRA ist eine **vollständige aktive Assistenz** mit Autonomy Loop, HITL-Gate und Multi-Step-Planung:

| Dimension | Aktueller Stand | Bewertung |
|---|---|---|
| Mail-Verarbeitung | Automatisch, ohne Eingriff | ✅ Vollständig |
| Klassifizierung | 3-stufig, ~95% Accuracy | ✅ Sehr gut |
| Task-Erstellung | Automatisch bei antwort_noetig=1 | ✅ Vollständig |
| Vorgang-Tracking | State Machine, 10 Typen (session-nn) | ✅ Implementiert |
| Kira-Chat | Reaktiv + proaktiv mit Gedächtnis | ✅ Vollständig |
| LLM-Aufruf | Anthropic primary, 3 Fallbacks + Circuit Breaker + Backoff | ✅ Robust |
| Proaktive Scans | 9 Scans inkl. Autonomy-Decision-Loop (session-oo) | ✅ Vollständig |
| Autonomes Handeln | Autonomy-Loop: Stufe A (still) / B (Toast) / C (Modal) | ✅ Implementiert |
| Email-Senden | HITL-Gate: mail_approve_queue, Dashboard-Badge + Modal | ✅ Implementiert |
| Lernen aus Feedback | 👍/👎 → Auto-Wissensregel + Stil-Lernen aus Mail-Edits | ✅ Implementiert |
| Kalender-Integration | MS Graph Calendars.ReadWrite, Tool: termin_erstellen | ✅ Implementiert |
| Multi-Step-Planung | ReAct-Schleife: chat_react(), max 5 Runden, User-Interrupt | ✅ Implementiert |
| Konversations-Gedächtnis | Tier-2 Episodic Memory, tägliche Summary, Tool: konversation_suchen | ✅ Implementiert |
| Semantische Suche | FTS5 BM25-Ranking, Tool: semantisch_suchen | ✅ Implementiert |
| Audit-Trail | Dashboard-Tab "Kira-Aktivitäten", actor_type kira_autonom/kira_vorschlag | ✅ Implementiert |
| Live-Migration | 83 Vorgänge aus Bestandsdaten (2026-03-31) | ✅ Abgeschlossen |

### 12.2 Der entscheidende Unterschied: Reaktiv vs. Proaktiv

**Kira heute (reaktiv):**
```
Nutzer fragt → Kira antwortet → Nutzer handelt → fertig
```

**Vollständige Aktive Assistenz (proaktiv):**
```
Ereignis tritt auf → Kira erkennt → Kira plant → Kira handelt (mit/ohne Bestätigung)
→ Kira beobachtet Ergebnis → Kira lernt
```

Der einzige wirklich proaktive Baustein ist `kira_proaktiv.py` — aber auch der erstellt nur Tasks/Notifications, handelt nie direkt.

### 12.3 Kritische Lücken (priorisiert)

**GAP-1: Kein Autonomy Loop / Agentic Loop**
- Kira kann nicht mehrstufig planen: "Überprüfe RE-Status, wenn überfällig → erstelle Mahnung, wenn keine Antwort in 3 Tagen → eskaliere"
- Fehlt: ReAct-Schleife (Reason → Act → Observe → Repeat) und der grundlegende **Autonomy Loop**:
  ```
  background-timer → context collect → LLM invoke → decide action → execute (mit HITL gate) → log → sleep → repeat
  ```
- kira_proaktiv.py hat einen Timer, aber keinen LLM-Entscheidungsschritt darin — nur feste Regellogik

**GAP-2: Kein Mail-Senden**
- Alle Antwort-Entwürfe müssen manuell kopiert und versendet werden
- Nutzer muss Mail-Client öffnen, einfügen, absenden
- Wichtigstes fehlendes Feature für echte Assistenz

**GAP-3: Keine Kalender-Integration**
- Termine werden aus Mails erkannt aber nicht in Kalender eingetragen
- Keine Erinnerungen aus Kalender → Kira
- Microsoft Graph API wäre der Weg (MSAL bereits vorhanden)

**GAP-4: Kein strukturiertes Feedback-Lernen**
- Wissen_regeln können gespeichert werden, aber nur wenn Nutzer explizit sagt "merke dir das"
- Kein automatisches Lernen aus: "Kira hat einen Entwurf erstellt → Nutzer hat ihn stark verändert → Kira lernt den Stil"

**GAP-5: Vorgang-Automatisierung fehlt (Case Engine ist Struktur ohne Automation)**
- Case Engine hat State Machines, aber kein automatisches Fortschreiten
- Beispiel: Angebot versendet → Kira könnte nach 7 Tagen automatisch Nachfass-Draft erstellen + Nutzer bestätigen lassen
- Derzeit: kira_proaktiv.py erstellt nur einen Task, Nutzer muss selbst handeln

**GAP-6: Kein strukturiertes Kontext-Gedächtnis**
- Kira-Konversationen werden gespeichert, aber nicht in den nächsten Chat-Kontext geladen
- Nutzer muss Kira immer wieder denselben Kontext geben
- kira_konversationen-Tabelle existiert aber wird nicht als "Memory" verwendet
- Forschungsstand 2025: Drei Gedächtnis-Ebenen gelten als Best Practice:
  1. **Working Memory** — aktueller LLM-Context (existiert)
  2. **Episodic Memory** — SQLite: was lief heute (runtime_events.db, teilweise genutzt)
  3. **Semantic Memory** — Wissensbasis: Kunden, Regeln, Muster (wissen_regeln, teilweise)

**GAP-7: Context-Window-Degradierung**
- Kira injiziert immer mehr Kontext (Vorgänge, Runtime-Log, Mails, Wissen) in den System-Prompt
- Arxiv 2025: Recall-Qualität sinkt bei Modellen ab ca. 16–32k Token — auch wenn technisches Maximum größer ist
- Risiko: Kira "übersieht" wichtige Information die tief im System-Prompt steckt
- Lösung: Dynamischen Kontext kürzen + SQLite FTS5 als lokales RAG

---

## 13. Verbesserungs-Roadmap

*Basiert auf Code-Analyse + Internet-Recherche zu Agentic AI Patterns 2025*

### Tier 1 — Sofort umsetzbar (hoher Impact, wenig Aufwand)

#### T1-A: Mail-Versand via SMTP mit HITL-Gate
- SMTP ist bereits konfiguriert (mail_monitor hat IMAP-Auth)
- Industrie-Standard-Pattern: **Human-in-the-Loop (HITL) Approval Gate**
  ```
  Kira erstellt Entwurf → speichert in DB (status="pending_review")
  → benachrichtigt Nutzer ("Mail fertig, bitte prüfen")
  → Nutzer genehmigt/lehnt ab/bearbeitet → Kira sendet
  ```
- Neues Tool `mail_senden(an, betreff, text, task_id)` mit `needs_approval=True`
- Sicherheitsprinzip: Kira sendet **nie ohne Bestätigung** (Stufe A niemals für Senden)
- Wann autonomes Senden ggf. akzeptabel: rein informationell + templatisiert + mit 30s Cancel-Fenster
- Protokollierung in sent_mails.db + elog()

#### T1-B: Vorgang-Automatisierung (Trigger-basiert)
- Erweitere kira_proaktiv.py um vorgang-basierte Scans:
  - Angebot in Status `angebot_versendet` seit > 7 Tagen → automatisch Nachfass-Draft erstellen
  - Vorgang in Status `mahnung_versendet` seit > 14 Tagen → Stufe-2-Mahnung vorschlagen
- Kira-Tool `vorgang_naechste_aktion_vorschlagen` → LLM schlägt nächsten Schritt vor

#### T1-C: Kira-Konversations-Gedächtnis
- Beim Chat-Start: letzte 3 relevante Konversationen zum Kunden laden (`kira_konversationen WHERE kunden_email = ?`)
- Tool `konversation_suchen` → Kira kann explizit in vergangenen Gesprächen suchen
- Memory-Summary: täglich 1 LLM-Aufruf der Konversationen des Tages zu 3 Kernpunkten zusammenfasst

#### T1-D: Tool-Reliability + Circuit Breaker
- **Tool-Fehler-Klassifikation** (wichtiger als die Retry-Logik selbst):
  - `TransientError` — Timeout, Rate Limit → exponentieller Backoff mit Jitter (`base * 2^attempt + random(0,1)`) und nochmal versuchen
  - `PermanentError` — Auth-Fehler, ungültige Parameter → nicht retrien, eskalieren
  - `LogicError` — LLM halluziniert Tool-Parameter → JSON-Schema-Validierung vor Aufruf
- Exponentieller Backoff: `wait = 2**attempt + random.random()` (Jitter verhindert Thundering Herd)
- Circuit Breaker: nach 3 TransientErrors in 60s → Provider für 5 Minuten sperren
- State in `knowledge/llm_circuit_state.json`
- Jeden Tool-Call mit Input/Output/Fehler in runtime_events.db loggen (bereits möglich via elog())

### Tier 2 — Mittelfristig (höherer Aufwand, hoher strategischer Wert)

#### T2-A: Microsoft Graph Calendar Integration
- MSAL (`msal` library) ist bereits für IMAP-Auth vorhanden
- Scope: `Calendars.ReadWrite`
- Neues Tool: `termin_erstellen(titel, datum, dauer_min, teilnehmer)`
- Aus Mails erkannte Termine → Kira fragt "Soll ich das in den Kalender eintragen?"
- Erinnerungen rückwärts: Kalender-Events → ntfy-Push 24h vorher

#### T2-B: ReAct-Schleife für Kira
- Aktuell: 1 LLM-Aufruf → optional 1 Tool → Antwort (flach)
- Verbesserung: `while tool_calls_pending: aufruf → tools → neuer aufruf` (bis zu 5 Runden)
- Aktiviert echte Mehrschritt-Aktionen: "Schaue nach ob RE offen → wenn ja, was ist das Datum → erstelle Erinnerung"
- Sicherheit: Max-Iterations-Limit + User-Interrupt-Möglichkeit

#### T2-C: Strukturiertes Feedback-Lernen (RLHF-light)
- Nach jedem Kira-Tool-Aufruf: Nutzer kann 👍/👎 geben
- 👎 → automatisch "Korrektur"-Wissensregel erstellen, die beim nächsten ähnlichen Fall injiziert wird
- Mails die Kira als "Entwurf" erstellt + Nutzer stark verändert hat → Diff-Analyse → Stil-Anpassung

#### T2-D: Semantische Suche mit SQLite FTS5 (lokales RAG)
- Aktuell: nur SQLite LIKE-Suche, keine Ähnlichkeits-Suche
- Empfehlung Forschung 2025: SQLite FTS5 ist für < 100k Datensätze absolut ausreichend als Vektor-Datenbank-Ersatz — kein ChromaDB/Qdrant nötig
- Implementierung: `CREATE VIRTUAL TABLE mail_fts USING fts5(betreff, text_plain, content=mails)`
- Tool `semantisch_suchen` → findet ähnliche Anfragen/Mails via FTS5-Ranking, nicht nur LIKE
- **Context-Strategie**: Statt alles in System-Prompt zu laden, bei Bedarf gezielt abfragen:
  ```python
  def get_relevant_context(query, db):
      customers = db.execute("SELECT * FROM mails WHERE mails MATCH ?", [query])
      return format_context(customers)  # < 2000 Token, nicht 10000
  ```
- Arxiv 2025: Effektive Recall-Qualität sinkt ab ~16-32k Token — System-Prompt klein halten gewinnt

### Tier 3 — Langfristig (Architektur-Änderungen)

#### T3-A: Multi-Agent-Architektur
- Aktuell: Kira ist ein einzelner Agent
- Ziel: Spezialisierte Sub-Agenten:
  - **Mail-Agent**: Klassifizierung, Entwurf, Versand
  - **Rechnungs-Agent**: RE-Tracking, Mahnwesen, Zahlungsabgleich
  - **Kunden-Agent**: CRM, Kommunikationshistorie, Potenzial-Bewertung
  - **Orchestrator-Agent** (Kira): koordiniert die Spezialisten
- Vorteil: Kleinere Kontextfenster, weniger Token-Kosten, spezialisiertes Wissen

#### T3-B: Persistente Agent-Planung
- Kira kann komplexe Tasks planen: "Bereite die Jahresabschluss-Kommunikation vor"
  1. Alle offenen REs prüfen
  2. Danke-Mails an Stammkunden entwerfen
  3. Angebote mit Status "keine_antwort" archivieren
  4. Reporting für Kai generieren
- Plan wird gespeichert, stückweise ausgeführt, Fortschritt getrackt

#### T3-C: Lokales LLM für Datenschutz-kritische Operationen
- Kundendaten (RE, persönliche Infos) nur zu lokalem Ollama senden
- Anthropic/OpenAI nur für nicht-personenbezogene Anfragen
- Routing-Logik: `kira_llm.py` → prüft ob Prompt personenbezogene Daten enthält

### ROI-Ranking: Was lohnt sich wirklich (aus Internet-Recherche 2025)

| Automatisierung | Aufwand | Nutzen | Lokal realisierbar |
|---|---|---|---|
| Follow-up-Erinnerungen (kein Feedback seit X Tagen) | sehr niedrig | sehr hoch | ✅ ja (kira_proaktiv.py) |
| Mail-Klassifikation + Priorität | niedrig | hoch | ✅ ja (vorhanden) |
| Eingangsrechnung-Extraktion (PDF → SQLite) | niedrig | hoch | ✅ ja (LLM + pdfplumber) |
| Angebots-Entwurf aus CRM-Daten | mittel | sehr hoch | ✅ ja (kira_llm.py) |
| Wöchentlicher Reporting-Summary | niedrig | mittel | ✅ ja (kira_proaktiv.py) |
| Automatische Rechnungsstellung | hoch | mittel | ⚠️ nur mit HITL |
| Autonomes Mail-Senden | hoch | hoch | ⚠️ nur mit HITL-Gate |

**Fazit der Recherche:** Der größte Hebel ist der **Autonomy Loop mit Event-Driven Triggers + HITL-Gate**, nicht die KI-Intelligenz selbst. KIRA hat bereits alle Rohdaten — was fehlt ist der Loop der sie zu Entscheidungen verdichtet.

### Tier 4 — Sicherheit & Compliance   /////////////  Hierzu sinvoll Einstellungen in den einstellungen als zusätzlichen Tap mit einstellmöglichkeiten und diagnose daten -z.b. wenn möglich kosten aktuel filter nach zeiten

#### T4-A: Tool-Idempotenz sicherstellen
- Jedes schreibende Tool (rechnung_bezahlt, etc.) prüft vor Aktion ob bereits ausgeführt
- Idempotenz-Key: `tool_name + entity_id + hash(params)` in runtime_events.db
- Verhindert Doppel-Buchungen bei LLM-Retry

#### T4-B: Audit-Trail für alle autonomen Aktionen
- Jede Aktion die Kira ohne explizite User-Bestätigung ausführt → elog() mit `actor_type='kira_autonom'`
- Dashboard-Ansicht: "Was hat Kira heute autonom getan?" (filtert actor_type='kira_autonom')

#### T4-C: Rate-Limiting für API-Calls
- Schutz vor LLM-Kosten-Explosion wenn Feedback-Schleife hängt
- Max N API-Aufrufe pro Minute, danach Queue

---

### Changelog session-ss (2026-03-31)

| Feature | Datei | Details |
|---|---|---|
| User-Präsenz-Erkennung | server.py | visibilitychange API — _pollKiraStatus stoppt/startet je nach Tab-Sichtbarkeit |
| Kira-Position | server.py | 4 Ecken via Select + applyKiraPosition() + localStorage |
| Chitchat-Toggle | server.py + kira_llm.py | "Smalltalk erlaubt" Toggle → build_system_prompt() injiziert Fokus-Anweisung |
| ntfy Push-Priorität | server.py + kira_proaktiv.py | Select low/default/high/urgent → _push() liest config.kira_proaktiv.ntfy.prioritaet |
| Dashboard-Refresh-Intervall | server.py | Select 1–60min oder deaktiviert → silentRefreshDashboard configgesteuert |
| Morgen-Briefing konfigurierbar | server.py + kira_proaktiv.py | Toggle + Uhrzeit-Input → 3h-Fenster ab konfigurierter Startzeit |
| **Sicherheitsfix BCC** | server.py | hardcoded `bcc:'info@raumkult.eu'` aus pfSend() entfernt → opt. BCC-Feld im Compose |

**Commits:** 9dc60f1, 1632065, b20985e

---

*Analyse erstellt 2026-03-30 (session-jj) | Aktualisiert 2026-03-31 (session-ss) | 35+ Module, 8 DBs, 70+ Endpunkte*
