# KIRA — Vollständige System-Analyse
**Erstellt:** 2026-03-30
**Analysiert:** 28 Python-Module, 8 SQLite-Datenbanken, 50+ API-Endpunkte
**Projektpfad:** `memory/` (Git-Repo)

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
| `scripts/server.py` | 9.250 | Haupt-Dashboard, alle API-Endpunkte, HTML-Generierung |
| `scripts/kira_llm.py` | 2.700 | LLM-Multi-Provider, Kira-Chat, 12 Tools |
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
- **Tagesstart-Briefing** — morgens 6–10 Uhr, generiert von LLM

---

## 3. LLM-Integration — wie KI angebunden ist

### 3.1 Multi-Provider-System (`kira_llm.py`)

KIRA unterstützt 4 Provider mit automatischem Fallback:

```
Priorität 1: Anthropic   → claude-sonnet-4-20250514 (Standard)
Priorität 2: OpenAI      → gpt-4o
Priorität 3: OpenRouter  → anthropic/claude-sonnet-4
Priorität 4: Ollama      → llama3.1 (lokal, offline)
Priorität X: Custom      → beliebige OpenAI-kompatible API
```

**Fallback-Logik:** Wenn Provider fehlschlägt (Timeout, API-Fehler, kein Guthaben) → automatisch nächster in der Prioritäts-Liste.

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

### 3.3 Die 12 Kira-Tools (kira_llm.py, Zeile ~572)

Alle Tools sind im Anthropic-Format definiert und werden automatisch in OpenAI-Format konvertiert für nicht-Anthropic-Provider:

| Tool | Aktion | Datenbank |
|---|---|---|
| `rechnung_bezahlt` | Ausgangsrechnung → status='bezahlt' | tasks.db / ausgangsrechnungen |
| `angebot_status` | Angebot → angenommen/abgelehnt/keine_antwort | tasks.db / angebote |
| `eingangsrechnung_erledigt` | Eingangsrechnung → erledigt | tasks.db |
| `kunde_nachschlagen` | Kunden-Infos + Mail-Historie | kunden.db + mail_index.db |
| `nachfass_email_entwerfen` | LLM-Entwurf generieren | kein DB-Schreiben |
| `wissen_speichern` | Neue Regel → wissen_regeln | tasks.db |
| `rechnungsdetails_abrufen` | PDF-extrahierte Details | rechnungen_detail.db |
| `web_recherche` | Google-Suche via urllib | extern |
| `runtime_log_suchen` | Events suchen | runtime_events.db |
| `angebot_pruefen` | Angebot-Details + ähnliche Anfragen | tasks.db + mail_index.db |
| `task_erledigen` | Task → status='erledigt' | tasks.db |
| `tasks_loeschen` | Mehrere Tasks löschen | tasks.db |

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

### 3.5 Antwort-Entwürfe (llm_response_gen.py)
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
- `POST /api/task/{id}/status` — Task-Status ändern
- `POST /api/wissen/neu` — Wissens-Regel speichern
- `POST /api/mail/nachklassifizieren` — Nachklassifizierung starten

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

#### FEHLER-01: Falsches Standard-Modell in kira_llm.py
**Datei:** `scripts/kira_llm.py`, Zeile 40
**Problem:** Der Standard-Modell-ID lautet `claude-sonnet-4-20250514`. Das aktuell korrekte Modell laut Anthropic-Dokumentation ist `claude-sonnet-4-6`. Bei API-Anfragen an einen ungültigen Snapshot schlägt der Aufruf mit HTTP 404 fehl — Kira antwortet nicht.

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

#### FEHLER-02: ARCHIV_ROOT hardcoded in mehreren Dateien
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

#### FEHLER-03: KNOWLEDGE_DIR absolutpfad in build_databases.py
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

#### FEHLER-04: kira_proaktiv.py — Logging im Daemon-Modus stumm
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

#### FEHLER-06: task_manager.py — DB-Verbindungen nicht mit Context Manager
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

#### FEHLER-08: SyntaxWarnings in server.py (ISS-003, bekannt aber offen)
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

#### FEHLER-09: MAILBOXEN und KONTO_LABEL hardcoded in daily_check.py
**Datei:** `scripts/daily_check.py`, Zeilen 33–38
**Problem:** Konto-Liste und Label-Mapping sind als Konstanten im Code fest. Wenn ein neues Mail-Konto in `config.json` angelegt wird, muss `daily_check.py` manuell angepasst werden — sonst ignoriert der Daily-Check das neue Konto.

**Behebung:** Konten aus `config.json` lesen:
```python
_cfg = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
_konten = _cfg.get("mail_archiv", {}).get("konten", [])
KONTO_LABEL = {k["email"]: k.get("konto_label", k["email"]) for k in _konten if k.get("aktiv")}
```

---

#### FEHLER-10: gpt-4.1-2025-04-14 als wählbares Modell — möglicherweise nicht existent
**Datei:** `scripts/kira_llm.py`, Zeile 50
**Problem:** `gpt-4.1-2025-04-14` ist als OpenAI-Modell-Option in der Dropdown-Liste. Es ist unklar ob diese Modell-ID in der OpenAI-API existiert. Wählt der Nutzer es aus, schlagen alle Kira-Anfragen mit HTTP 404 fehl.

**Behebung:** Entweder entfernen oder auf bekannte IDs wie `gpt-4o`, `gpt-4o-mini`, `o3-mini` beschränken.

---

### BEKANNTE ISSUES (aus known_issues.json, ALLE BEHOBEN)

Die 15 bekannten Issues ISS-001 bis ISS-015 sind laut Projektdokumentation alle behoben. Letzte offene war ISS-003 (SyntaxWarnings) — hier als FEHLER-08 weitergeführt.

---

## Zusammenfassung: Prioritäts-Matrix

| # | Fehler | Datei | Auswirkung | Schwere |
|---|---|---|---|---|
| 01 | Standard-Modell-ID veraltet | kira_llm.py:40 | Kira antwortet nicht | KRITISCH |
| 02 | ARCHIV_ROOT hardcoded | daily_check.py:32 | Mail-Scan bricht ab | KRITISCH |
| 03 | KNOWLEDGE_DIR absolut | build_databases.py:21 | Rebuild schlägt fehl | KRITISCH |
| 04 | Logging stumm im Daemon | kira_proaktiv.py:45 | Fehler unsichtbar | KRITISCH |
| 05 | NULL-Check fehlt | mail_monitor.py | Angebots-Verknüpfung failts lautlos | WICHTIG |
| 06 | DB-Verbindungs-Leak | task_manager.py | SQLite-Locks möglich | WICHTIG |
| 07 | State-File Race Condition | kira_proaktiv.py:61 | Doppelte Tasks möglich | WICHTIG |
| 08 | SyntaxWarnings | server.py:~4789 | Zukünftiger Server-Crash | WICHTIG |
| 09 | Konten hardcoded | daily_check.py:33 | Neue Konten ignoriert | NIEDRIG |
| 10 | Ungültige Modell-Option | kira_llm.py:50 | Fehler wenn gewählt | NIEDRIG |

---

*Analyse erstellt am 2026-03-30 durch vollständige Codeanalyse (28 Module, 8 DBs).*
