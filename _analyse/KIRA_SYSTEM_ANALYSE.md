# KIRA — Vollstaendige System-Analyse & Masterdatei

**Erstellt:** 2026-03-30 | **Konsolidiert:** 2026-03-31 (session-xx)
**Analysiert:** 34 Python-Module (35.439 Zeilen), 7 SQLite-Datenbanken (46 Tabellen), 96 API-Endpunkte
**Projektpfad:** `memory/` (Git-Repo)

> **Diese Datei ist die einzige Wahrheitsquelle fuer KIRA-Architektur, Status und Planung.**
> Alle frueheren Planungsdokumente (KIRA_2_0_UMBAU_PLAN.md, KIRA_2_0_UI_UMBAU_PLAN.md, etc.) wurden hierin konsolidiert.
>
> **Changelog:**
> - session-jj (2026-03-30): Erstellt. 10 Bugs identifiziert, 7 sofort behoben.
> - session-kk: Postfach Mail-Rendering + Kira-Button Redesign.
> - session-ll: Automatisches Modell-Validierungssystem.
> - session-nn: Case Engine, 5 neue Tools (17→22), Desktop-Overlay, Presence-Detection, Backfill, GAP-Analyse.
> - session-oo: Vollstaendige Aktive Assistenz — Pakete 1-9 implementiert.
> - session-pp: Bug-Fixes B-04, B-05, Task-Loeschen.
> - session-qq: kira_cfg Fix, Kontext-Steuerung, Eingangsrechnungen-View, Proaktiv-Scan.
> - session-rr: Antwort-Laenge/Sprache/Temperatur, Provider-Test, Settings-Suche, DB-VACUUM.
> - session-ss: User-Praesenz, Kira-Position, Chitchat, ntfy-Prioritaet, Dashboard-Refresh, BCC-Fix.
> - session-tt: Heute-gesendet-Karte, Auto-Backup-System, Briefing-Timestamp.
> - session-uu: Stats-Filter, Ignorieren-Lernfrage mit Presets, Wissensregeln-Timestamps.
> - session-vv: Global-Badge-Polling, Spaeter-Dialog, Sidebar-Logo Kira-Orb, Favicon, Modal-BG-Fix.
> - session-ww: Vorgaenge-Uebersicht Panel, Launcher Drag-to-Move, Geloeschte-Protokoll-UI.
> - **session-xx (2026-03-31): KONSOLIDIERUNG — alle Planungsdokumente integriert, Status-Tabelle, offene Posten.**

---

## INHALTSVERZEICHNIS

1. [Ueberblick & Architektur](#1-ueberblick--architektur)
2. [Modul-Inventar](#2-modul-inventar)
3. [Feature-Vollbild](#3-feature-vollbild)
4. [LLM-Integration](#4-llm-integration)
5. [Datenbanken](#5-datenbanken)
6. [Mail-System](#6-mail-system)
7. [Proaktive Automatisierung](#7-proaktive-automatisierung)
8. [Case Engine — Vorgang-Layer](#8-case-engine--vorgang-layer)
9. [Dashboard & Server](#9-dashboard--server)
10. [Konfiguration & Secrets](#10-konfiguration--secrets)
11. [Partner-View (Leni)](#11-partner-view-leni)
12. [Behobene Fehler](#12-behobene-fehler)
13. [Konsolidierte Status-Tabelle (alle Plaene)](#13-konsolidierte-status-tabelle)
14. [Offene Posten & Roadmap](#14-offene-posten--roadmap)
15. [Design-Leitlinien](#15-design-leitlinien)

---

## 1. Ueberblick & Architektur

**KIRA** ist ein Python-basiertes Geschaeftsassistenz-System fuer rauMKult Sichtbeton (Kai Marienfeld, Betonkosmetik-Spezialist). Es laeuft lokal auf `http://127.0.0.1:8765`.

```
+------------------------------------------------------------------+
|  Browser (Dashboard + Kira-Workspace)                            |
|  http://127.0.0.1:8765                                           |
+--------------------+---------------------------------------------+
                     | HTTP (96 Endpunkte)
+--------------------v---------------------------------------------+
|  server.py  (17.941 Zeilen)                                      |
|  ThreadedHTTPServer — HTML + API                                 |
+--+----------+----------+----------+------------------------------+
   |          |          |          |
   v          v          v          v
kira_llm  mail_monitor  daily_check  kira_proaktiv
(3.341Z)  (1.576Z)      (1.058Z)    (1.107Z)
23 Tools  IMAP-Poll     Nacht-Scan  11 Scans
   |          |              |           |
   v          v              v           v
+-----------------------------------------------------+
|  SQLite-Datenbanken (knowledge/)                    |
|  7 DBs, 46 Tabellen, ~72 MB                        |
|  tasks.db | mail_index.db | kunden.db               |
|  runtime_events.db | sent_mails.db | ...            |
+-----------------------------------------------------+
```

### Tech-Stack
- **Backend:** Python 3.x (stdlib + msal, anthropic, openai)
- **Server:** ThreadedHTTPServer auf 127.0.0.1:8765
- **Frontend:** Inline HTML/CSS/JS (Python f-strings, kein Template-System)
- **Datenbank:** SQLite3 (WAL-Modus, Row-Factory)
- **Mail:** IMAP XOAUTH2 (Microsoft Entra), SMTP
- **LLM:** Multi-Provider (Anthropic, OpenAI, OpenRouter, Ollama, Custom)
- **Push:** ntfy.sh
- **Kalender:** Microsoft Graph API (MSAL)
- **Partner-View:** GitHub Pages (statisches HTML)

---

## 2. Modul-Inventar

### Python-Module (34 Dateien, 35.439 Zeilen)

| Datei | Zeilen | Zweck |
|---|---|---|
| `server.py` | 17.941 | Haupt-Dashboard, 96 API-Endpunkte, 8 build_*-Funktionen, 133 Funktionen total |
| `kira_llm.py` | 3.341 | Multi-LLM Chat, 23 Tools, Modell-Validierung, ReAct-Schleife, Circuit Breaker |
| `mail_monitor.py` | 1.576 | IMAP-Polling (5 Konten), Mail-Klassifizierung, Task-Erstellung, OAuth2 |
| `kira_proaktiv.py` | 1.107 | Autonomer Business-Scanner (11 Scans, alle 15 Min) |
| `daily_check.py` | 1.058 | Taeglicher Mail-Scan, Erinnerungen, Nachklassifizierung |
| `scan_dokumente.py` | 983 | Dokumenten-Scanner |
| `diff_to_changelog.py` | 815 | Pre-commit-Hook: atomares Mikro-Logging |
| `llm_classifier.py` | 595 | LLM-basierte Mail-Klassifizierung |
| `rebuild_all.py` | 590 | Komplett-Rebuild aller Datenbanken |
| `case_engine.py` | 549 | Vorgang-Layer: State Machines, CRUD, Signal-Queue |
| `scan_rechnungen_detail.py` | 549 | PDF-Rechnungsextraktion |
| `build_databases.py` | 513 | DB-Initialisierung und -Migration |
| `mail_classifier.py` | 504 | Regelbasierte Mail-Klassifizierung (Fast-Path) |
| `runtime_log.py` | 481 | Event-Store (SQLite, Thread-safe, elog()) |
| `seed_wissen_komplett.py` | 408 | Wissens-Seed-Daten |
| `mail_archiv_reindex.py` | 384 | Mail-Archiv Re-Indexierung |
| `mail_sender.py` | 379 | SMTP-Mailversand |
| `scan_geschaeft.py` | 351 | Geschaeftsdaten-Scanner |
| `generate_partner_view.py` | 338 | Partner-View HTML-Generierung + GitHub Push |
| `angebote_tracker.py` | 321 | Angebots-Tracking |
| `case_engine_backfill.py` | 307 | Einmalige Migration: Bestandsdaten → Vorgaenge |
| `response_gen.py` | 302 | Antwort-Generierung |
| `archiv_cleanup.py` | 254 | Taegliche Bereinigung geloeschter Mails |
| `vorgang_router.py` | 244 | Routing: Mail-Klassifizierung → Vorgang-Typ |
| `upgrade_geschaeft.py` | 231 | Geschaefts-DB-Upgrade |
| `change_log.py` | 229 | Changelog-API + Suche |
| `mail_schema_migrate.py` | 203 | Mail-DB-Schema-Migration |
| `llm_response_gen.py` | 201 | Auto-Antwort-Entwuerfe (5 Situationstypen) |
| `activity_window.py` | 163 | Desktop-Overlay (tkinter -topmost) + Signal-Watcher |
| `graph_calendar.py` | 144 | Microsoft Graph Kalender-API |
| `activity_log.py` | 131 | Legacy Aktivitaetslog (nicht anfassen — Backward-Compat) |
| `reclassify_existing.py` | 107 | Re-Klassifizierung bestehender Mails |
| `task_manager.py` | 105 | Task-CRUD fuer tasks.db |
| `presence_detector.py` | 35 | Windows-Idle-Detection (GetLastInputInfo) |

### Konfigurationsdateien

| Datei | Zweck |
|---|---|
| `scripts/config.json` | Hauptkonfiguration (nie direkt editieren!) |
| `scripts/secrets.json` | API-Keys (nie committen!) |
| `feature_registry.json` | Feature-Status (38 Features, 24 Leni-sichtbar) |
| `known_issues.json` | Bekannte Probleme (ISS-001 bis ISS-021) |
| `session_handoff.json` | Letzter Arbeitsstand |
| `knowledge/daily_check_status.json` | Daily-Check State |
| `knowledge/mail_monitor_state.json` | Mail-Monitor State |
| `knowledge/model_validation_state.json` | Modell-Validierung State |
| `knowledge/proaktiv_state.json` | Proaktiv-Scanner State |
| `knowledge/db_status.json` | DB-Status |

### Verzeichnisstruktur

```
memory/                          <- Git-Repo Root
+-- scripts/                     <- Python-Backend (34 Module)
+-- knowledge/                   <- SQLite-DBs + State + Templates
|   +-- mail_templates/          <- 3 HTML-Templates (Einladung/Passwort/Benachrichtigung)
+-- _analyse/                    <- KIRA_SYSTEM_ANALYSE.md (diese Datei)
+-- _archiv/                     <- Alte Arbeitsanweisungen + Checklisten
+-- kira_claude_agents_bundle/   <- Agent-Konfigurationen
+-- komplett plan fuer UI/       <- UI-Design-Referenzen (Firefly-Prompts + HTML-Previews)
+-- cowork/                      <- Berichte + Aktuell-Status
+-- Plan Dokumente Modul/        <- Dokumente-Modul Planung
+-- AGENT.md                     <- Arbeitsregeln fuer Claude Code
+-- MEMORY.md                    <- Memory-Index
+-- partner_view.html            <- Lenis Feature-Uebersicht
+-- feature_registry.json        <- Feature-Tracking
+-- session_handoff.json         <- Session-Uebergabe
```

---

## 3. Feature-Vollbild

### 3.1 Dashboard-Panels (6 + Einstellungen)

**Dashboard (Startseite)**
- KPI-Karten: offene Aufgaben, Rechnungen, Angebote, Kunden (Sparklines)
- Top-5-Aufgaben nach Prioritaet, Ueberfaellig-Badge
- Tagesstart-Briefing (LLM-generiert, 06-10 Uhr)
- "Heute gesendet"-Karte (Zone C0): Kira-gesendete + User-gesendete Mails
- Vorgaenge-Uebersicht Panel: 82 Vorgaenge nach Typ
- Stats-Zeile springt via filterKomm()+jumpToSeg() zu korrektem Tab

**Kommunikation**
- 9 Kategorien klassifizierter Mails mit Filter
- Kira-Buttons pro Mail: Zusammenfassung, Antwort-Entwurf, Kategorie-Korrektur
- Status-Aktionen: erledigt, ignorieren (mit Lernfrage + 5 Presets), zur Kenntnis, spaeter (datetime-Picker + 4 Schnellbuttons + Warum-Lernfrage)

**Postfach (Outlook-Style)**
- 3-Pane-Ansicht: Ordnerleiste | Mail-Liste | Mail-Viewer
- Fluent-Ribbon mit Aktions-Buttons
- Live-IMAP-Ordner (UTF-7 decoded, 60s Cache)
- Hover-Aktionen: Gelesen/Flag/Pin/Trash
- Bulk-Bar: Mehrfachauswahl mit Aktionen
- Kira-Button: oeffnet Workspace mit vollstaendigem Mail-Kontext
- Favoriten-Sterne, Kombiniertes Postfach
- Mail verschieben (IMAP), Snooze (7 Presets + Freitext)
- **Kira-Ausgang**: Entwuerfe/Gesendet/Abgelehnt/Abgelaufen (mail_approve_queue)
- Ribbon-Gruppe "Kira-Entwurf": Freigeben/Bearbeiten/Ablehnen

**Geschaeft (5 Sub-Tabs)**
1. Ausgangsrechnungen — Status, Betrag, Ueberfaellig-Warnung
2. Angebote — Nachfass-Datum, Betrag
3. Mahnungen — Stufe 1/2/3
4. Eingangsrechnungen — Lieferanten, Faelligkeiten, Tabellen-View
5. Statistik — Zahlungsdauern, Muster

**Organisation**
- Termine und Fristen aus Mails erkannt
- Rueckruf-Erinnerungen
- Kalender-Tab (vorbereitet fuer Graph-API)

**Wissen**
- 7 Kategorien: Preisregeln, Kundenwuensche, Prozessregeln, Ausschlussregeln, Auto-gelernt, Korrektionen, Freitextnotizen
- CRUD + Timestamps
- Direkt in Kira-Kontext injiziert

**Einstellungen (55+ KB HTML, 3-Spalten-Architektur)**
- 12 Sektionen: Design, Benachrichtigungen, Aufgabenlogik, Nachfass, Dashboard, Provider/LLM, Mail & Konten, Integrationen, Automationen, Sicherheit & Audit, Protokoll
- 5 Provider-Gruppen: Konversations-Gedaechtnis, Proaktive Automatisierung, ReAct & Multi-Step, Feedback & Lernen, Sicherheit & Limits
- Signatur-Editor, Mail-Klassifizierung, Archiv-Panel
- 5 Design-Einstellungen: Schriftfamilie, Sidebar-Breite, Toast-Position (6 Optionen), Tabellen-Zeilenhoehe, Zebrastreifen
- Kira-Position (4 Ecken), Launcher-Varianten (A/B/C), Chitchat-Toggle
- Dashboard-Refresh-Intervall, Morgen-Briefing konfigurierbar
- Config-Reset mit Backup, Config-Export/Import, DB-VACUUM
- Logo-Upload (max 512KB), Logo-Groesse
- Geloeschte-Mails-Protokoll in Mail & Konten

### 3.2 Kira-Workspace (Chat + Tools)

3-Spalten-Layout:
- **Links**: Kontext-Tabs (Aufgaben, Mails, Geschaeft, Wissen)
- **Mitte**: Chat-Verlauf + Eingabefeld
- **Rechts**: Tool-Aufrufe, Aktionshistorie

Kira kann ueber Chat: Rechnungen bezahlen, Angebote bestaetigen, Kunden nachschlagen, Nachfass-Mails entwerfen, Wissen speichern, Tasks erledigen/loeschen, Internet recherchieren, Runtime-Log durchsuchen, Vorgaenge laden/Status setzen, Termine erstellen/anzeigen, Mails semantisch suchen, Konversationen durchsuchen, Mails senden (HITL-Gate), naechste Aktion vorschlagen.

### 3.3 Kira-Launcher

- 3 Varianten: A (Minimal), B (Charakter/Default), C (Orb/Tech)
- SVG mit radialGradient + 3D-Tiefe + kira-float CSS-Animation
- Globales Augen-Tracking via rAF-Loop, Excited-Bounce bei Naehe
- Bored-Mode: Sequenz blink→drowsy→yawn→eye-roll→sleep
- Drag-to-Move mit Ecken-Snap + QP-Positionierung
- Sidebar-Logo: Kira-Orb-SVG, Favicon: Kira-SVG im head

### 3.4 Hintergrundprozesse

| Prozess | Intervall | Beschreibung |
|---|---|---|
| Mail-Monitor | ~60s | IMAP-Polling (5 Konten), Klassifizierung, Task-Erstellung |
| Proaktiv-Scanner | 15 Min | 11 Scans (via mail_monitor) |
| Daily-Check | 1x taeglich | Nachklassifizierung, Erinnerungen |
| Archiv-Cleanup | taeglich | Bereinigt Anhaenge geloeschter Mails |
| Snooze-Wecker | 60s | Weckt abgelaufene Snooze-Mails |
| Modell-Validierung | 20s + 24h | Prueft alle Provider-Modelle |
| Tagesstart-Briefing | 06-10 Uhr | LLM-generierte Zusammenfassung |
| Signal-Watcher Desktop | 15s | tkinter -topmost fuer Stufe-C-Signale |
| Signal-Polling Browser | 10s | Toast (Stufe B) / Modal (Stufe C) |
| Auto-Backup | 23h TTL | SQLite .backup() API |
| Badge-Polling | 2 Min | _pfGlobalBadgeUpdate() |

---

## 4. LLM-Integration

### 4.1 Multi-Provider-System (kira_llm.py)

```
Prioritaet 1: Anthropic   → claude-sonnet-4-6 (Standard)
Prioritaet 2: OpenAI      → gpt-4o
Prioritaet 3: OpenRouter   → anthropic/claude-sonnet-4
Prioritaet 4: Ollama      → llama3.1 (lokal, offline)
Prioritaet X: Custom      → beliebige OpenAI-kompatible API
```

**Fallback:** Automatisch naechster Provider bei Fehler. Circuit Breaker: 3 Fehler/60s → Provider 300s gesperrt. Rate-Limiting: max 20 LLM-Calls/Min.

**Modell-Validierung (session-ll):** Erkennt automatisch wenn Modelle deprecated werden → Auto-Update auf bestes verfuegbares Modell → ntfy Push + config.json Update.

### 4.2 Die 23 Kira-Tools

| # | Tool | Aktion | Seit |
|---|---|---|---|
| 1 | `rechnung_bezahlt` | RE → status='bezahlt' (idempotent) | jj |
| 2 | `angebot_status` | Angebot → angenommen/abgelehnt (idempotent) | jj |
| 3 | `eingangsrechnung_erledigt` | ER → erledigt (idempotent) | jj |
| 4 | `kunde_nachschlagen` | Kunden-Infos + Mail-Historie | jj |
| 5 | `nachfass_email_entwerfen` | LLM-Entwurf generieren | jj |
| 6 | `wissen_speichern` | Neue Regel → wissen_regeln | jj |
| 7 | `rechnungsdetails_abrufen` | PDF-extrahierte Details | jj |
| 8 | `angebot_pruefen` | Angebot-Details + aehnliche Anfragen | jj |
| 9 | `duplikate_suchen` | Doppelte Tasks/Mails | mm |
| 10 | `task_erledigen` | Task → status='erledigt' (idempotent) | jj |
| 11 | `tasks_loeschen` | Mehrere Tasks loeschen | jj |
| 12 | `runtime_log_suchen` | Events suchen (wenn aktiviert) | jj |
| 13 | `mail_suchen` | Mail-Index durchsuchen | mm |
| 14 | `mail_lesen` | Mail-Volltext aus Archiv | mm |
| 15 | `web_recherche` | Google-Suche via urllib | jj |
| 16 | `vorgang_kontext_laden` | Vorgang-Details + History | nn |
| 17 | `vorgang_status_setzen` | Status via State-Machine aendern | nn |
| 18 | `termin_erstellen` | MS Graph POST /me/events | oo |
| 19 | `termine_anzeigen` | MS Graph GET /me/calendarView | oo |
| 20 | `semantisch_suchen` | FTS5 BM25-Ranking | oo |
| 21 | `vorgang_naechste_aktion_vorschlagen` | LLM waehlt naechsten Schritt | oo |
| 22 | `konversation_suchen` | Sucht in kira_konversationen | oo |
| 23 | `mail_senden` | HITL-Gate: Entwurf in Approval-Queue | oo |

### 4.3 Mail-Klassifizierung — 3-stufig

1. **Fast-Path** (mail_classifier.py, ~80%): System-Absender, Newsletter-Keywords, Kunden direkt
2. **LLM** (llm_classifier.py, ~20%): Kontext-basiert mit gelernten Korrektionen
3. **Fallback** (wenn LLM fehlt): Regelbasiert, ~95% Accuracy

### 4.4 Kira-Chat-Pipeline

```
User-Eingabe → POST /api/kira/chat → kira_llm.chat()
  → build_system_prompt():
    - Kira-Rolle + rauMKult-Kontext
    - Antwort-Laenge (kurz/normal/ausfuehrlich), Sprache, Temperatur
    - _build_data_context() [offene RE, Angebote, Tasks]
    - get_recent_for_kira(limit=30) [Runtime-Events]
    - _get_wissen_by_kategorie() [max 20 Regeln]
    - Letzte 15 Eingangs-Mails
    - Proaktive Findings, Geloeschte-Protokoll (letzte 20)
    - Offene Vorgaenge (limit=8, Case Engine)
    - Konversations-Gedaechtnis (letzte 3 Sessions, max 3200 Token)
    - Chitchat-Steuerung
  → LLM-Provider-Aufruf (mit Tools)
  → ReAct-Schleife: max 5 Runden bei chat_react()
  → elog() in runtime_events.db
```

### 4.5 Konversations-Gedaechtnis (3-Tier Memory)

1. **Working Memory** — aktueller LLM-Context
2. **Episodic Memory** — letzte 3 Sessions pro Kunde in System-Prompt (Token-Budget 800)
3. **Semantic Memory** — Wissensbasis (wissen_regeln), taegliche Summary via Scan 9

---

## 5. Datenbanken

### 5.1 tasks.db (17 MB, 23 Tabellen)

| Tabelle | Zweck |
|---|---|
| `tasks` | Kern: Aufgaben mit Klassifizierung, Status, Prioritaet |
| `ausgangsrechnungen` | Ausgangsrechnungen mit Status, Betrag, Faelligkeit |
| `angebote` | Angebote mit Nachfass-Count, Status |
| `eingangsrechnungen` | Eingangsrechnungen (Lieferanten) |
| `wissen_regeln` | Gelernte Regeln (7 Kategorien) → System-Prompt |
| `kira_konversationen` | Chat-Verlauf (Session-basiert) |
| `kira_feedback` | Thumbs up/down pro Antwort |
| `kira_briefings` | Tagesstart-Briefings |
| `vorgaenge` | Case Engine: Vorgangs-Haupttabelle |
| `vorgang_links` | Verknuepfungen (Task/Mail/RE/Angebot → Vorgang) |
| `vorgang_status_history` | Status-Uebergaenge mit Actor |
| `vorgang_signals` | Stufe A/B/C Signale |
| `mail_approve_queue` | HITL-Gate: pending/approved/rejected/sent/expired |
| `mail_signaturen` | E-Mail-Signaturen |
| `corrections` | Kira-Klassifizierungs-Korrekturen |
| `geschaeft` | Geschaeftsdaten |
| `geschaeft_statistik` | Zahlungsdauer-Statistik |
| `organisation` | Termine, Fristen |
| `kunden_aliases` | Kunden-Email-Aliases |
| `loeschhistorie` | Geloeschte Tasks |
| `aktivitaeten` | Aktivitaeten-Log |
| `task_kira_context` | Kira-Kontext pro Task |
| `geloeschte_protokoll` | Geloeschte-Mails-Protokoll |

### 5.2 runtime_events.db (25 MB, 3 Tabellen)

- `events`: 25 Spalten (ts, event_type, source, modul, actor_type, action, status, provider, model, tokens, duration, summary...)
- `event_payloads`: Volltext-Payloads (user_input, assistant_output, etc.)
- 5 Event-Typen: ui, kira, llm, system, settings
- actor_type: kira_autonom, kira_vorschlag, user, system

### 5.3 mail_index.db (14 MB, 7 Tabellen)

- `mails`: 12.642+ Eintraege (message_id, datum, absender, betreff, folder, text, flagged, pinned, kira_verwendet)
- `mail_fts`: FTS5 Virtual Table mit BM25-Ranking
- 5 Mail-Konten: anfrage@, info@, invoice@, kaimrf@, shop@

### 5.4 Weitere Datenbanken

| DB | Groesse | Tabellen | Zweck |
|---|---|---|---|
| `kunden.db` | 14 MB | kunden, interaktionen | 7.321+ Interaktionen |
| `sent_mails.db` | 2,3 MB | gesendete_mails | 525 gesendete Mails (Stil-Lernbasis) |
| `rechnungen_detail.db` | 360 KB | rechnungen_detail, angebote_detail, mahnungen_detail, rechnungs_positionen, zahlungseingaenge | PDF-extrahierte Details |
| `newsletter.db` | 120 KB | newsletter | Auto-klassifizierte Newsletter |

### 5.5 Datenbankverbindungen

```
server.py        → tasks.db, kunden.db, mail_index.db, runtime_events.db, sent_mails.db, rechnungen_detail.db
kira_llm.py      → tasks.db, kunden.db, mail_index.db, rechnungen_detail.db
mail_monitor.py  → tasks.db, mail_index.db, kunden.db, runtime_events.db
daily_check.py   → tasks.db, mail_index.db, kunden.db, sent_mails.db
kira_proaktiv.py → tasks.db, kunden.db, mail_index.db
runtime_log.py   → runtime_events.db (WAL-Modus, Thread-safe mit Lock)
case_engine.py   → tasks.db (vorgaenge, vorgang_links, vorgang_status_history, vorgang_signals)
task_manager.py  → tasks.db
```

---

## 6. Mail-System

### 6.1 IMAP-Architektur (mail_monitor.py)

Haupt-Loop (~60s): Fuer jedes der 5 Konten → IMAP via OAuth2 → Neue Mails (UID-inkrementell) → Archiv schreiben → mail_index.db aktualisieren → Klassifizieren → Task erstellen → Push-Notification. Alle 15 Min: kira_proaktiv.run_all_scans().

### 6.2 OAuth2 (Microsoft Entra KIRA-App a0591b2d)

- MSAL PublicClientApplication.acquire_token_interactive()
- Token-Cache: TOKEN_DIR/{email}_token.json
- 3-stufige Provider-Erkennung: Domain-Heuristik → DNS MX+Autodiscover → OpenID-Config-Probe
- 6-Schritt-Wizard (Mailbird-Stil) mit Expert-Mode

### 6.3 Mail-Archiv-Struktur (OneDrive)

```
Mail Archiv/Archiv/{konto_label}/{folder}/{YYYY-MM-DD}/{message-id}/
  mail.json       <- Metadaten + Volltext
  [Anhaenge]      <- Nur wenn vorhanden
```

### 6.4 Mail → Task-Erstellung

Automatisch wenn `antwort_noetig=true` → Task INSERT + vorgang_router.route_classified_mail()

### 6.5 Mail-Nachklassifizierung

```bash
python daily_check.py --seit 2026-01-01 --bis 2026-03-30
```
Oder UI-Button in Einstellungen > Mail-Klassifizierung.

---

## 7. Proaktive Automatisierung

### 7.1 kira_proaktiv.py — 11 Scan-Module

| # | Scan | TTL | Beschreibung |
|---|---|---|---|
| 1 | `scan_ueberfaellige_rechnungen` | 72h | RE offen > 14/30/45 Tage → Mahnung-Task + Push |
| 2 | `scan_angebot_nachfass` | 48h | Angebote offen > 7/14/30 Tage → Nachfass-Task |
| 3 | `scan_leads_ohne_antwort` | — | Unbeantwortete Leads > 2 Tage → Reminder |
| 4 | `scan_tagesstart_briefing` | 24h | 06-10 Uhr → LLM-Summary |
| 5 | `scan_neue_kunden_erkennen` | — | Kunden mit >=2 Kontakten → Notiz-Task |
| 6 | `scan_angebot_followup_vorgang` | — | Angebot > 7 Tage → Nachfass-Draft in Queue |
| 7 | `scan_mahnung_eskalation` | — | Mahnung > 14 Tage → Signal Stufe B |
| 8 | `scan_autonomy_decision` | — | LLM analysiert alle Vorgaenge → Stufen A/B/C |
| 9 | `scan_tages_memory_summary` | — | Taegl. Konversations-Summary via LLM |
| 10 | `scan_offene_eingangsrechnungen` | — | ER-Proaktiv-Scan |
| 11 | `scan_auto_backup` | 23h | SQLite .backup() API |

### 7.2 Push-Notifications (ntfy.sh)

- Topic: `raumkult_kira`
- Arbeitszeit-Filter: konfigurierbar (Standard 06-20 Uhr)
- Urlaub-Modus: alle Pushes stumm + Header-Chip
- Prioritaeten: low/default/high/urgent (konfigurierbar)

---

## 8. Case Engine — Vorgang-Layer

### 8.1 Konzept

Die Case Engine ist ein Vorgang-Layer oberhalb von Tasks und Mails. Ein Vorgang repraesentiert einen vollstaendigen Geschaeftsprozess mit State Machine.

```
Mail → Klassifizierung → Task → vorgang_router.py
  → Existiert Vorgang fuer Kunden? → Link
  → Neuer Vorgang? → create_vorgang() → Entscheidungsstufe
    → Stufe A: stumm     → Stufe B: Browser-Toast     → Stufe C: Desktop-Overlay
```

### 8.2 10 Vorgang-Typen mit State Machines

| Typ | Wichtige Status | Endstatus |
|---|---|---|
| `lead` | neu_eingang → qualifiziert → angebot_gesendet | angenommen, abgelehnt, archiviert |
| `angebot` | neu_eingang → angebot_versendet → angenommen/abgelehnt | abgeschlossen |
| `rechnung` | rechnung_gestellt → bezahlt/ueberfaellig → mahnung | abgeschlossen |
| `mahnung` | mahnung_versandt → mahnung_2 → mahnung_3 → inkasso | abgeschlossen |
| `support` | offen → in_bearbeitung → wartend_auf_kunde → geloest | abgeschlossen |
| `projekt` | planung → in_umsetzung → abnahme_ausstehend | abgeschlossen |
| `partner` | kontaktiert → in_verhandlung → aktiv | beendet |
| `lieferant` | anfrage → angebot_erhalten → bestellt | abgeschlossen |
| `intern` | offen → in_bearbeitung | erledigt |
| `sonstige` | offen → in_bearbeitung | erledigt |

### 8.3 Entscheidungsstufen

- **Stufe A** (Konfidenz >= 0.85): Automatisch, stumm
- **Stufe B** (0.60-0.84): Browser-Toast, 10s Polling
- **Stufe C** (< 0.60): Modal + Desktop-Overlay (tkinter), Presence-Check

---

## 9. Dashboard & Server

### 9.1 server.py — 96 API-Endpunkte

**GET-Endpunkte (~32):** `/`, `/partner`, `/api/tasks/open`, `/api/tasks/closed`, `/api/corrections`, `/api/geschaeft`, `/api/organisation`, `/api/wissen`, `/api/mail/folders`, `/api/mail/konten`, `/api/mail/snooze/count`, `/api/mail/archiv/status`, `/api/kira/insights`, `/api/kira/proaktiv/status`, `/api/kira/circuit_breaker`, `/api/config/export`, `/api/monitor/status`, `/api/runtime/stats`, `/api/server/version`, `/api/kira/briefing`, `/api/kira/conversations`, `/api/einstellungen`, `/api/mail/signaturen`, `/api/browse/folder`, `/api/presence`, `/api/vorgaenge`, `/api/vorgang/signals`, u.a.

**POST-Endpunkte (~64):** `/api/kira/chat`, `/api/mail/send`, `/api/mail/gelesen`, `/api/mail/flag`, `/api/mail/pin`, `/api/mail/loeschen`, `/api/mail/snooze`, `/api/mail/verschieben`, `/api/mail/konto/oauth-start`, `/api/mail/nachklassifizieren`, `/api/einstellungen`, `/api/kira/feedback`, `/api/kira/task`, `/api/kira/provider/*`, `/api/wissen/neu`, `/api/vorgang/neu`, `/api/vorgang/signal/gelesen`, `/api/backup/jetzt`, `/api/db/vacuum`, `/api/config/reset`, `/api/config/import`, u.v.m.

### 9.2 HTML-Generierung (8 build_*-Funktionen)

| Funktion | Zeile | Beschreibung |
|---|---|---|
| `build_dashboard()` | 455 | KPI-Karten, Briefing, Stats, Vorgaenge |
| `build_kommunikation()` | 907 | Tab-Filter, Tasks, Kira-Buttons |
| `build_postfach()` | 1104 | 3-Pane Outlook-Style + Kira-Ausgang |
| `build_organisation()` | 3570 | Timeline, Fristen, Rueckrufe |
| `build_geschaeft()` | 3645 | 5 Sub-Tabs (RE/Angebote/Mahnungen/ER/Statistik) |
| `build_einstellungen()` | 4350 | 55+ KB, 12 Sektionen, 3-Spalten |
| `build_wissen()` | 7823 | 7 Kategorien, CRUD |
| `build_section()` | 448 | Hilfs-Funktion fuer zusammenklappbare Sektionen |

### 9.3 CSS-Namespaces

| Prefix | Bereich |
|---|---|
| `kq-*` | Quick Panel |
| `kw-*` | Kira Workspace |
| `es-*` | Einstellungen |
| `kd-*` | Dashboard |
| `kk-*` | Kommunikation |
| `kg-*` | Geschaeft |
| `pf-*` | Postfach |

---

## 10. Konfiguration & Secrets

### 10.1 config.json (versioniert, nie direkt editieren)

Wichtigste Abschnitte: server, mail_archiv (konten, sync_ordner), aufgaben, nachfass, ntfy, runtime_log, llm_providers, kira (memory, react, feedback, sicherheit), kira_proaktiv, benachrichtigungen, backup.

### 10.2 secrets.json (NIEMALS committen)

API-Keys: anthropic_api_key, openai_api_key, openrouter_api_key, github_pat.

### 10.3 Microsoft OAuth2

- Zentrale KIRA Entra App: Client-ID `a0591b2d-86c3-...`
- Token-Cache: TOKEN_DIR/{email}_token.json
- Scope-Version `v5_imap_smtp` erzwingt Token-Reset bei Upgrade

---

## 11. Partner-View (Leni)

- URL: `https://kaimarienfeld.github.io/kira-partner/`
- 38 Features total, 24 Leni-sichtbar (13 done, 1 partial, 10 planned)
- Passwortgeschuetzt, Premium-Design (Playfair Display + Inter)
- Filter: Alle/Eingebaut/Geplant/Leni-Ideen/Neu
- Feedback-System: ntfy Push, Admin-Panel nur fuer Kai
- Auto-Generierung: `python scripts/generate_partner_view.py --push`

---

## 12. Behobene Fehler

| # | Fehler | Datei | Status |
|---|---|---|---|
| 01 | Standard-Modell-ID veraltet | kira_llm.py | ✅ jj + ll (Auto-Validierung) |
| 02 | ARCHIV_ROOT hardcoded | daily_check.py, build_databases.py | ✅ jj |
| 03 | KNOWLEDGE_DIR absolut | build_databases.py | ✅ jj |
| 04 | Logging stumm im Daemon | kira_proaktiv.py | ✅ jj |
| 05 | NULL-Check _auto_angebot_aktion | mail_monitor.py | ✅ pp |
| 06 | DB-Verbindungs-Leak | task_manager.py | ✅ jj (try/finally) |
| 07 | State-File Race Condition | kira_proaktiv.py | ✅ pp (threading.Lock) |
| 08 | SyntaxWarnings (7 Stellen) | server.py | ✅ jj |
| 09 | Konten hardcoded | daily_check.py | ✅ jj |
| 10 | Ungueltige Modell-Option | kira_llm.py | ✅ ll (entschaerft) |
| 11 | rechnung_bezahlt blindes UPDATE | kira_llm.py | ✅ oo (Idempotenz) |
| 12 | Kein Exponential Backoff | kira_llm.py | ✅ oo (Circuit Breaker) |
| 13 | kira_konversationen nicht im Prompt | kira_llm.py | ✅ oo (3 Sessions) |
| 14 | System-Prompt waechst unbegrenzt | kira_llm.py | ✅ oo (Budgets) |
| 15 | Task-Loeschen blockiert Server | server.py | ✅ pp |
| ISS-015 | GET /api/einstellungen 404 | server.py | ✅ y |
| ISS-020 | ARCHIV_ROOT nicht aus config | mehrere | ✅ jj |
| ISS-021 | Falsches Standard-Modell | kira_llm.py | ✅ jj |

---

## 13. Konsolidierte Status-Tabelle

> **Quellen:** KIRA_2_0_UMBAU_PLAN.md, KIRA_2_0_UI_UMBAU_PLAN.md, Implementierungsplan, Zusatz v Kai, arbeitsanweisung_case_engine_multiagent.md, Kontext_engen_GPT_KIRA_Struktur.txt

### Backend / Kernlogik

| Feature / Komponente | Status | Session | Hinweis |
|---|---|---|---|
| Vorgangslogik (Case Engine) | ✅ Erledigt | nn | 10 Typen, State Machines, Verknuepfungen |
| Vorgang-Router (Mail → Vorgang) | ✅ Erledigt | nn | vorgang_router.py, in mail_monitor + daily_check |
| Entscheidungsstufen A/B/C | ✅ Erledigt | nn | Konfidenz-basiert |
| Signal-Queue + Polling | ✅ Erledigt | nn | Browser + Desktop |
| Presence-Detection (Windows) | ✅ Erledigt | nn | GetLastInputInfo |
| Desktop-Overlay (tkinter) | ✅ Erledigt | nn | activity_window.py |
| Case Engine Backfill | ✅ Erledigt | nn/ww | 83 Vorgaenge migriert |
| Tool-Idempotenz | ✅ Erledigt | oo | Pre-Check + Early Return |
| Circuit Breaker + Backoff | ✅ Erledigt | oo | 3 Fehler/60s → 300s Sperre |
| Rate-Limiting | ✅ Erledigt | oo | max 20 Calls/Min |
| Mail-Senden HITL-Gate | ✅ Erledigt | oo | mail_approve_queue |
| Konversations-Gedaechtnis | ✅ Erledigt | oo | 3-Tier Memory |
| Vorgang-Automatisierung (3 Scans) | ✅ Erledigt | oo | Followup/Mahnung/Autonomy |
| ReAct-Schleife (Multi-Step) | ✅ Erledigt | oo | max 5 Runden, User-Interrupt |
| Feedback-Lernen (Thumbs) | ✅ Erledigt | oo | Auto-Wissensregel + Stil-Lernen |
| FTS5 Semantische Suche | ✅ Erledigt | oo | mail_fts, BM25-Ranking |
| MS Graph Kalender-Tools | ✅ Erledigt | oo | termin_erstellen, termine_anzeigen |
| Audit-Trail (actor_type) | ✅ Erledigt | oo | kira_autonom/kira_vorschlag |
| Modell-Validierung Auto-Update | ✅ Erledigt | ll | 24h-Cache + Laufzeit-Catch |
| Automatisches Backup | ✅ Erledigt | tt | SQLite .backup(), 23h TTL |
| Tagesstart-Briefing | ✅ Erledigt | ss/tt | Konfigurierbar, 3h-Fenster |
| Mail-Nachklassifizierung | ✅ Erledigt | ff | recheck_mails() + UI |
| IMAP Ordner-System | ✅ Erledigt | hh | Live-IMAP, UTF-7, Sync-Config |
| Archiv-Cleanup | ✅ Erledigt | hh | Taeglich, geloeschte_protokoll |
| Ignorieren-Lernfrage | ✅ Erledigt | uu | 5 Presets + Wissensregel |
| Spaeter-Dialog | ✅ Erledigt | vv | datetime-Picker + 4 Schnellbuttons |

### UI / Frontend

| Feature / Komponente | Status | Session | Hinweis |
|---|---|---|---|
| Kira-Workspace 3-Spalten | ✅ Erledigt | g | kq-*/kw-* CSS |
| Kira-Launcher 3 Varianten | ✅ Erledigt | p/q | SVG, Augen-Tracking, Drag |
| Einstellungen 3-Spalten-Redesign | ✅ Erledigt | r | 12 Sektionen, es-* CSS |
| Hell/Dunkel-Theme komplett | ✅ Erledigt | s | Alle hardcoded Farben ersetzt |
| 5 Design-Einstellungen | ✅ Erledigt | s | Schrift/Sidebar/Toast/Zeile/Zebra |
| Postfach Outlook-Style | ✅ Erledigt | dd/ee | 3-Pane, Hover, Bulk, Toolbar |
| Kira-Ausgang im Postfach | ✅ Erledigt | qq | Entwuerfe/Gesendet/Abgelehnt/Abgelaufen |
| Mail-Approve Dashboard | ✅ Erledigt | oo | Header-Badge + Preview-Modal |
| Kira-Aktivitaeten Timeline | ✅ Erledigt | oo | Panel mit kira_autonom/kira_vorschlag |
| Vorgaenge-Uebersicht Dashboard | ✅ Erledigt | ww | 82 Vorgaenge nach Typ |
| Provider Verbindungstest | ✅ Erledigt | rr | Test-Button pro Provider |
| Einstellungen-Suche | ✅ Erledigt | rr | Suchfeld filtert Sektionen |
| DB-VACUUM UI | ✅ Erledigt | rr | Button in Protokoll |
| Automationen-Sektion aktiv | ✅ Erledigt | oo | 6 Scan-Status + Manuelle Aktionen |
| Sicherheit & Audit Sektion | ✅ Erledigt | oo | Circuit Breaker, Log-Settings |
| 5 Provider-Gruppen (LLM) | ✅ Erledigt | oo | Memory, Proaktiv, ReAct, Feedback, Sicherheit |
| Signatur-Editor | ✅ Erledigt | qq | Mail & Konten Tab |
| Geloeschte-Protokoll-UI | ✅ Erledigt | ww | Einstellungen > Mail & Konten |
| Global-Badge-Polling | ✅ Erledigt | vv | Unabhaengig von aktivem Panel |
| Sidebar-Logo Kira-Orb | ✅ Erledigt | vv | SVG |
| Favicon Kira-SVG | ✅ Erledigt | vv | data-URI im head |
| Modal-Transparenz Fix | ✅ Erledigt | vv | --bg-card Variable |
| Partner-View Premium | ✅ Erledigt | w | Light Mode, Playfair Display |

### Erledigt (session-zz, 2026-03-31)

| Feature / Komponente | Status | Session | Hinweis |
|---|---|---|---|
| Kira Live-Chip im Header | ✅ Erledigt | zz | Status-Chip: idle/scanning/pending/error |
| Activity-Drawer (Slide-In) | ✅ Erledigt | zz | 400px, nicht-modal, Kira-Aktivitaeten |
| Mail-Vorlagen + Editor | ✅ Erledigt | zz | Vorlagen-Typen, Kira-Anbindung, Signatur-Zuordnung |
| Kalender-Widget Dashboard | ⚠️ Partial | zz | Graph-API verdrahtet, braucht Azure Calendars.ReadWrite |
| Kalender-Tab Organisation | ✅ Erledigt | zz | Live-Terminliste, Toolbar |
| Direkte E-Mail-Antwort aus Postfach | ✅ Erledigt | bb | Compose + Reply + pfSend + /api/mail/send + mail_sender.py |
| Kunden-360-Ansicht | ✅ Erledigt | bb | k360-drawer, 5 Tabs, /api/kunden/360 Backend |
| Geschaeft: Signale-Panel live | ✅ Erledigt | zz | loadGeschKiraSignale, /api/vorgang/signals?alle=1 |
| Chat: Kontext-Sidebar (Vorgang/Kunde) | ✅ Erledigt | zz | kiraKontextMenuToggle, 3 Aktionen |
| Wissen: Feedback-Loop-UI | ✅ Erledigt | oo | Thumbs up/down, auto Lernregeln, "Von Kira gelernt" Badge |
| Einstellungen: Kira-Postfach Gruppe | ✅ Erledigt | zz | Kira sendet von: Konto, Graph-Pruef-Button |
| Einstellungen: Graph Kalender | ✅ Erledigt | zz | Scope-Status + Pruef-Button |
| Google OAuth | ✅ Erledigt | aaa | google_oauth.py, Browser-Flow, Wizard, Einstellungen > Integrationen |

### Erledigt (session-bbb + session-ccc, 2026-03-31/04-01)

| Feature / Komponente | Status |
|---|---|
| Belegvorlagen-Modul | ✅ Erledigt (session-bbb) — HTML-Editor + JS + Backend + GET/POST/DELETE /api/belegvorlagen, Storage knowledge/belegvorlagen/*.json |
| Sprachmodul | ✅ Erledigt (session-bbb) — Web Speech API Mikrofon-Button im Kira-Chat |
| Dokument-Export | ✅ Erledigt (session-bbb) — CSV/JSON Export fuer Tasks/Kunden/Vorgaenge/Mails |
| Cloud-Backup | ✅ Erledigt (session-bbb) — daily_check.py Step 7, manuell via /api/backup/jetzt |
| Urlaubsmodus-Smart | ✅ Erledigt (session-bbb) — Auto-Reply in mail_monitor.py, Tracking-Log urlaub_autoreply_log.json |
| Zeiterfassung | ✅ Erledigt (session-bbb) — Neuer Geschaeft-Tab: Timer, manuelle Eintraege, SQLite zeiterfassung in tasks.db, GET/POST/DELETE /api/zeiterfassung |
| Cashflow-Prognose | ✅ Erledigt (session-bbb) — Neuer Geschaeft-Tab: Monats-KPI-Karten + CSS-Balkendiagramm aus ausgangsrechnungen (bezahlt/offen), letzten 12 Monate |
| CRM Pipeline | ✅ Erledigt (session-bbb) — Neuer Geschaeft-Tab: Kanban-Board 5 Spalten (neu/angebot_gesendet/verhandlung/gewonnen/verloren) aus vorgaenge WHERE typ IN ('lead','angebot','anfrage') |
| Angebots-Kalkulation | ✅ Erledigt (session-bbb) — Neuer Geschaeft-Tab: Material/Arbeit/Fremd-Zeilen, GK/Marge/MwSt-Berechnung, _kalLastNetto global, kalKiraAngebot() uebergibt Netto an Kira |
| Eingangsrechnungen-Auto-Scan | ✅ Erledigt (session-bbb) — mail_monitor.py _auto_scan_eingangsrechnung(): Regex-Betrag-Extraktion, INSERT OR IGNORE INTO geschaeft bei Kategorie 'Rechnung / Beleg' |
| DB-Autopflege | ✅ Erledigt (session-bbb) — daily_check.py Step 8: alte Tasks loeschen, wissen_regeln dedup, VACUUM tasks.db + mail_index.db |
| Foto-Analyse | ✅ Erledigt (session-bbb+ccc) — Frontend: FileReader-Upload, _kiraAttachment global, sendKiraMsg schickt bild-Payload. Backend: kira_llm.chat(bild=) Parameter, Anthropic vision content-list (image+text Block) |

### Offen / Kai-Aktionen erforderlich

| Feature / Komponente | Status | Prioritaet | Hinweis |
|---|---|---|---|
| Azure Calendars.ReadWrite | ⏳ Offen (Kai) | Mittel | Entra Portal: Permission hinzufuegen (Kalender-Widget dann voll aktiv) |
| Lexware-Anbindung | ⏳ Offen | — | Eigene Arbeitsanweisung kommt von Kai |
| WhatsApp-Token | ⏳ Offen (Kai) | Niedrig | Kai muss Token eintragen |
| Leni Draft-2 Passwort | ⏳ Offen (Kai) | Niedrig | Gmail-Draft Platzhalter ersetzen |
| Multi-Agent-Architektur | ⏳ Langfristig | — | Spezialisierte Sub-Agenten |
| Persistente Agent-Planung | ⏳ Langfristig | — | Komplexe Tasks planen + stueckweise ausfuehren |
| Lokales LLM fuer Datenschutz | ⏳ Langfristig | — | Personenbezogene Daten nur zu Ollama |

---

## 14. Offene Posten & Roadmap

### Implementiert (session-yy, 2026-03-31)

#### F-LLM-01 — Provider-Guthaben-Anzeige
**Status:** 🟢 Implementiert
**Dateien:** `scripts/server.py` (`_api_provider_balance`, `_balance_cache`, balance_row in provider cards)
**Beschreibung:** Balance-Abfrage per Provider-API (OpenAI: `/v1/dashboard/billing/credit_grants`, OpenRouter: `/api/v1/credits`), Fallback-Link fuer Anthropic, "Kostenlos" fuer Ollama. Badge + Refresh-Button in jeder Provider-Karte. 60 Min In-Memory-Cache.

#### F-LLM-02 — Token-Verbrauchshistorie
**Status:** 🟢 Implementiert
**Dateien:** `scripts/server.py` (`_api_kosten_uebersicht`, neue Einstellungen-Sektion "Verbrauch & Kosten")
**Beschreibung:** Tages-/Wochenansicht Tokenverbrauch aus `runtime_events.db`. Zeitraum-Filter: 7d/30d/Gesamt. Summary-Cards, CSS-only Balkendiagramm, Provider-Aufschluss-Tabelle.

#### F-LLM-03 — Kostenanalyse Detailtabelle
**Status:** 🟢 Implementiert
**Dateien:** `scripts/server.py` (`_api_kosten_detail`, `_cost_for_row`, `MODEL_PRICING_USD_PER_1M`)
**Beschreibung:** Gefilterte Rohdaten-Tabelle (Provider/Datum/Summary-Filter, Paginierung 50/Seite). Preisberechnung mit `MODEL_PRICING_USD_PER_1M` Dict (Exakt- + Prefix-Match). CSV-Export. Neue Einstellungen-Sektion mit 2 Sub-Tabs.

**Neue API-Endpunkte:**
- `GET /api/kira/provider/{id}/balance`
- `GET /api/kira/kosten/uebersicht?zeitraum=7d|30d|gesamt`
- `GET /api/kira/kosten/detail?seite=&pro_seite=&provider=&von=&bis=&q=&format=csv`

---

### Implementiert (session-zz + session-aaa, 2026-03-31)

#### F-UI-01 — Kira Live-Chip + Activity-Drawer
**Status:** 🟢 Implementiert (session-zz)
**Dateien:** `scripts/server.py` (`#kiraLiveChip`, `kira-activity-drawer`, `kiraActivityDrawerOpen()`, `kiraLiveUpdate()`)
**Beschreibung:** Header-Status-Chip (idle/scanning/pending/error), 400px Slide-In-Drawer mit letzten Kira-Aktivitaeten aus runtime_events.db.

#### F-UI-02 — Direkte E-Mail-Antwort aus Postfach
**Status:** 🟢 Implementiert (session-bb)
**Dateien:** `scripts/server.py` (`#pf-compose`, `pfReply()`, `pfForward()`, `pfSend()`), `scripts/mail_sender.py`, `/api/mail/send`
**Beschreibung:** Compose-Modal mit Von/An/CC/BCC/Betreff/Body, pfReply() befuellt Antwortformular mit Zitatblock, SMTP XOAUTH2 Versand via mail_sender.py, sofortige Indexierung in mail_index.db.

#### F-UI-03 — Mail-Vorlagen Editor
**Status:** 🟢 Implementiert (session-zz)
**Beschreibung:** Vorlagen-Typen, Kira-Anbindung, Signatur-Zuordnung.

#### F-UI-04 — Kalender-Widget Dashboard
**Status:** ⚠️ Partial (session-zz)
**Beschreibung:** loadDashKalender() + /api/kira/termine verdrahtet. Braucht Azure Calendars.ReadWrite Permission (Kai-Aktion).

#### F-UI-05 — Kunden-360-Ansicht
**Status:** 🟢 Implementiert (session-bb)
**Dateien:** `scripts/server.py` (`#k360-drawer`, `pfOpenKunden360()`, `pfShowKunden360()`, `/api/kunden/360`)
**Beschreibung:** Slide-In-Drawer im Postfach, 5 Tabs (Mails/Tasks/Vorgaenge/Rechnungen/Angebote), Kunden-Avatar + Chips.

#### F-INT-01 — Google OAuth 2.0 fuer Gmail
**Status:** 🟢 Implementiert (session-aaa)
**Dateien:** `scripts/google_oauth.py` (neu), `scripts/server.py` (Wizard-Schritt 5 dynamisch, GET /oauth/google/callback, POST /api/mail/konto/google-oauth-start, Einstellungen > Integrationen)
**Beschreibung:** Vollstaendiger Google OAuth2-Flow (Authorization Code, Token Exchange, Refresh). Browser-Flow identisch mit Microsoft MSAL. Gmail IMAP XOAUTH2 Support. Callback-Handler mit HTML-Bestaetigung. Einstellungen-Gruppe fuer Client ID/Secret.

**Neue API-Endpunkte (session-aaa):**
- `GET /oauth/google/callback` — OAuth2 Redirect-URI Handler
- `POST /api/mail/konto/google-oauth-start` — Browser-Flow starten
- `GET /api/mail/konto/google-oauth-status?job_id=` — Status abfragen
- `GET /api/google-oauth/test` — Credentials-Validierung

### Erledigt (session-ddd, 2026-04-01)

| Feature / Komponente | Status |
|---|---|
| Google OAuth health-check nach Login | ✅ Erledigt — `_wizPollGoogleOAuth()` ruft health-check + esLoadMailKonten() nach status=done |
| "Zu Kira hinzufuegen"-Button im Postfach | ✅ Erledigt — `pfAddFolderToKira()` + "+" Button auf Ordner die noch nicht in sync_ordner |
| SMTP-Passwort-Auth im Volltest | ✅ Erledigt — `run_full_connection_test()` brancht jetzt zwischen XOAUTH2 + Passwort-Auth |

### Kai-Aktionen erforderlich

- **Azure Entra:** Calendars.ReadWrite Permission hinzufuegen (dann ist Kalender-Widget voll funktional)
- **WhatsApp Business:** Token eintragen (Einstellungen > Integrationen)
- **Google OAuth App:** Cloud Console Project erstellen, Client ID/Secret in Einstellungen eintragen
- **Leni Gmail-Draft:** Draft-2 Passwort-Platzhalter ersetzen

### Bekannte technische Schulden

- `server.py` hat jetzt **19.600+ Zeilen** → server_map.md vor groesserer Arbeit lesen
- Zeilen-Angaben in server_map.md sind veraltete ca.-Werte
- Gmail-IMAP via google_oauth.py: braucht Gmail API aktiviert in Google Cloud Console
- Outlook-Kalender iframe-Embed: nur sinnvoll ohne Entra-Setup

---

## 15. Design-Leitlinien

### Farben & Stil (Dark + Light Mode)

- **Immer nur CSS-Variablen** — niemals Farben hardcoden
- Dunkel: `var(--bg)` ~ `#18181b`, `var(--bg-raised)` ~ `#232328`
- Hell: `var(--bg)` ~ `#f5f5f7`, `var(--bg-raised)` ~ `#ffffff`
- Akzent: `var(--accent, #4f7df9)`, Status: `var(--success/warning/error)`
- Schatten: `var(--shadow-modal)`

### Fenster & Modals (OAuth-Assistent-Stil)

- **NICHT transparent** — vollstaendig opaker Hintergrund
- Overlay-Dimmer: `rgba(0,0,0,.72)` (nicht .45)
- `border-radius: 16px`, `max-width: 620px` (Modal), `420px` (Drawer)
- Destruktive Modals: nur expliziter Button schliesst
- `showKritischModal(title, msg, word, fn, note)` fuer kritische Aktionen

### CSS-Regeln fuer neue Elemente

- `es-*` CSS-Klassen MUESSEN `var(--fs-*)` nutzen (nie hardcoded px)
- Alle form inputs: `var(--bg-raised)/var(--bg)/var(--text)`
- JS in Python-f-string: `\\\\'` fuer einfache Anfuehrungszeichen

### Kira-Sprechweise in der UI

- KEIN Technik-Jargon — verstaendliche Formulierungen
- Status-Chips: max. 30 Zeichen, aktive Formulierungen

---

*Analyse erstellt 2026-03-30 (session-jj) | Konsolidiert 2026-03-31 (session-xx) | Aktualisiert 2026-04-01 (session-ddd) | 35 Module, 7 DBs, 103 Endpunkte, 23 Tools, 11 Scans*
