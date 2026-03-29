# server.py — Funktionskarte

> server.py: ~9250 Zeilen | Stand: 2026-03-29 | Zuletzt aktualisiert: session-y

## Python-Funktionen (Top-Level)

| Zeile | Funktion | Beschreibung |
|-------|----------|-------------|
| 46 | `ThreadedHTTPServer` | HTTP-Server Klasse (ThreadingMixIn + HTTPServer) |
| 50 | `get_db()` | SQLite-Verbindung mit Row-Factory |
| 55 | `esc()` | HTML-Entity-Escaping |
| 58 | `js_esc()` | JS-String-Escaping |
| 61 | `format_datum()` | Datumsformatierung DE |
| 83 | `prio_class()` | CSS-Klasse nach Priorität |
| 87 | `task_card()` | HTML-Karte für eine Aufgabe |
| 184 | `build_section()` | Aufgaben-Section mit Karten |
| 191 | `build_dashboard()` | Dashboard-HTML generieren |
| 545 | `build_kommunikation()` | Kommunikation-Panel-HTML |
| 742 | `build_organisation()` | Organisation-Panel-HTML |
| 802 | `_load_rechnungen_detail()` | Rechnungsdetails aus DB laden |
| 817 | `build_geschaeft()` | Geschäft-Panel-HTML (5 Tabs) |
| 937 | `_build_gesch_auswertung()` | Geschäft-Statistik-Section |
| 958 | `_build_gesch_uebersicht()` | Geschäft-Übersicht-Section |
| 1132 | `_build_ar_table()` | Ausgangsrechnungen-Tabelle |
| 1215 | `_build_ang_table()` | Angebote-Tabelle |
| 1282 | `_gesch_aktiv_cards()` | Eingangsrechnungen-Karten |
| 1335 | `_build_mahnung_section()` | Mahnungen-Section |
| 1473 | `build_einstellungen()` | Einstellungen-Panel-HTML (inkl. runtime_log Section session-h) |
| 1930 | `build_wissen()` | Wissen-Panel-HTML |
| 2092 | `generate_html()` | Haupt-HTML-Seite zusammensetzen |
| 5751 | `DashboardHandler` | HTTP-Request-Handler (do_GET + do_POST) |
| 7109 | `_kill_old_instances()` | Alte Server-Prozesse beenden |
| 7147 | `run_server()` | Server starten |

## DashboardHandler — Methoden

| Zeile | Methode | Beschreibung |
|-------|---------|-------------|
| 5751 | `DashboardHandler` | Klasse |
| ~5760 | `do_GET()` | GET-Routing |
| ~6064 | `do_POST()` | POST-Routing |
| ~6720 | `_handle_task_action()` | Task-Aktionen (status/korrektur/loeschen) |

## GET-Endpunkte (do_GET)

| Zeile | Pfad | Beschreibung |
|-------|------|-------------|
| ~5760 | `/` | Haupt-Dashboard HTML |
| ~5800 | `/api/kira/chat` (GET) | - |
| ~5820 | `/api/kira/conversations` | Konversations-Liste |
| ~5840 | `/api/kira/conversation/{id}` | Konversations-Nachrichten |
| ~5850 | `/api/aktivitaeten` | Aktivitätslog (legacy) |
| ~5860 | `/api/runtime/events` | Runtime-Events gefiltert (NEU session-h) |
| ~5880 | `/api/runtime/stats` | Runtime-Statistiken (NEU session-h) |
| ~5888 | `/api/runtime/event/{id}/payload` | Vollkontext laden (NEU session-h) |
| ~5895 | `/api/changelog` | Änderungsverlauf |
| ~5930 | `/api/server/version` | Server-Versions-Hash |
| ~5940 | `/api/kira/briefing` | Tages-Briefing |
| ~5950 | `/api/kira/briefing/regenerate` | Briefing neu generieren |
| ~5960 | `/api/kira/provider/status` | Provider-Status prüfen |
| ~5970 | `/api/monitor/status` | Mail-Monitor Status |
| ~8268 | `/api/einstellungen` (GET) | WhatsApp-Tokens aus secrets.json laden (NEU session-y) |
| ~8271 | `/api/mail/konten/stats` | Index+Archiv-Stats pro Konto (NEU session-y) |
| ~8273 | `/api/mail/konten/ordner` | IMAP-Ordnerliste eines Kontos (NEU session-y) |
| ~8277 | `/api/mail/archiv/pruefen` | Archiv-Pfad-Existenz prüfen (NEU session-y) |
| ~8265 | `/api/webhook/whatsapp` (GET) | Meta Hub-Verifizierung (NEU session-x) |

## POST-Endpunkte (do_POST)

| Zeile | Pfad | Beschreibung |
|-------|------|-------------|
| ~6070 | `/api/server/restart` | Server-Neustart |
| ~6283 | `/api/runtime/event` | UI-Event empfangen (NEU session-h) |
| ~6305 | `/api/kira/chat` | Kira Chat (LLM) |
| ~6314 | `/api/kira/api-key` | API-Key speichern (Legacy) |
| ~6333 | `/api/kira/provider/save-key` | Provider Key speichern |
| ~6344 | `/api/kira/provider/add` | Provider hinzufügen |
| ~6376 | `/api/kira/provider/toggle` | Provider aktiv/inaktiv |
| ~6392 | `/api/kira/provider/move` | Provider-Priorität ändern |
| ~6414 | `/api/kira/provider/delete` | Provider löschen |
| ~6430 | `/api/einstellungen` (POST) | Einstellungen speichern (mit rlog) |
| ~9281 | `/api/whatsapp/secrets-speichern` | WhatsApp-Tokens in secrets.json (NEU session-x) |
| ~9270 | `/api/webhook/whatsapp` (POST) | WhatsApp Business Cloud Webhook (NEU session-x) |
| ~9270 | `/api/mail/konto/imap-test` | IMAP-Verbindung testen (NEU session-y) |
| ~9270 | `/api/mail/konto/abrufen` | Einzelnes Konto manuell abrufen (NEU session-y) |
| ~9270 | `/api/mail/konto/alle-abrufen` | Alle Konten manuell abrufen (NEU session-y) |
| ~9270 | `/api/mail/konto/standard` | Standard-Konto setzen (NEU session-y) |
| ~9270 | `/api/mail/konto/hinzufuegen` | Neues Konto hinzufügen (NEU session-y) |
| ~6620 | `/api/task/{id}/status` | Task-Status ändern |
| ~6620 | `/api/task/{id}/korrektur` | Task-Kategorie korrigieren |
| ~6620 | `/api/task/{id}/loeschen` | Task löschen |
| ~6720 | `/api/wissen/neu` | Neue Wissensregel anlegen |
| ~6750 | `/api/wissen/{id}/edit` | Wissensregel bearbeiten |
| ~6760 | `/api/wissen/{id}/loeschen` | Wissensregel löschen |

## JS-Funktionen (nach Bereich)

### Core Navigation
| Zeile | Funktion |
|-------|----------|
| 2752 | `showPanel(name)` — Panel-Wechsel (dashboard/kommunikation/geschaeft/etc.) |
| 2766 | `togglePrioMenu()` |
| 2778 | `toggleSidebar()` |

### Kommunikation
| Zeile | Funktion |
|-------|----------|
| 2956 | `filterKomm()` |
| 2978 | `filterKommView()` |
| 2990 | `applyKommFilters()` |
| 3116 | `loadThread(msgId)` |
| 3159 | `showOrgView()` |
| 3168 | `setStatus(taskId, status)` |

### Geschäft
| Zeile | Funktion |
|-------|----------|
| 3314 | `showGeschTab(tab)` |
| 3326 | `geschKira(typ, nr, partner, betrag)` — öffnet Kira mit Kontext |
| 3348 | `geschErledigt(typ, id)` |
| 3455 | `filterAR()` |
| 3468 | `filterAng()` |
| 3481 | `arSetStatus(id, status)` |
| 3500 | `angSetStatus(id, status)` |

### Einstellungen
| Zeile | Funktion |
|-------|----------|
| 3617 | `saveSettings()` — speichert alle Settings inkl. runtime_log (session-h) |
| 3678 | `_rtlog(event_type, action, summary, data)` — fire-and-forget UI-Tracking (NEU session-h) |
| 3690 | `loadRuntimeLog(append, onlyFehler)` — Runtime-Log Viewer (NEU session-h) |
| 3732 | `loadChangeLog(append)` |
| 3842 | `saveProviderKey(pid)` |
| 3858 | `addProvider()` |

### Kira Workspace (kq-*/kw-* — session-g)
| Zeile | Funktion |
|-------|----------|
| 3981 | `toggleKiraQuick()` — Quick Panel öffnen/schließen |
| 3986 | `closeKiraQuick()` |
| 3990 | `openKiraWorkspace(context)` — Workspace öffnen (7 Kontexte) |
| 4005 | `closeKiraWorkspace()` |
| 4016 | `showKTab(name)` — Tab-Wechsel via data-tab Attribut |
| 4035 | `loadKiraInsights()` |
| 4061 | `renderKiraAufgaben()` |
| 4074 | `renderKiraMuster()` |
| 4102 | `renderKiraLernen()` |
| 4119 | `sendKiraMsg()` — Chat senden (kiraSendBtn muss <button> sein!) |
| 4165 | `appendKiraMsg(rolle, text, tools, providerInfo, fallbackInfo)` |
| 4215 | `newKiraChat()` |
| 4246 | `refreshBriefing()` |
| 4417 | `setKiraContextBar(mode, title, tags)` — Kontext-Bar setzen (NEU session-g) |
| 4432 | `clearKiraContext()` — Kontext-Bar verstecken (NEU session-g) |
| 4439 | `kiraSetQuickActions(typ)` — 7 Kontext-Typen (NEU session-g) |
| 4457 | `kiraAddPrompt(text)` — Text an Input anhängen (NEU session-g) |
| 4467 | `toggleKiraTools()` — Tools-Panel ein/ausblenden (NEU session-g) |
| 4473 | `setKiraTools(attachments, rules, actions)` — Tools-Panel befüllen (NEU session-g) |
| 4483 | `kqDirectSend()` — Quick Panel Direkt-Senden (NEU session-g) |
| 4496 | `toggleKiraModeMenu()` — Platzhalter (NEU session-g) |
| 4501 | `loadKiraHistSidebar()` — History-Sidebar laden (NEU session-g) |
| 4507 | `renderKiraHistSidebar(data)` — History rendern (NEU session-g) |
| 4528 | `kiraProaktivCheck()` |

## Kritische Abhängigkeiten

- `kiraSendBtn` **muss** `<button>` sein — `.disabled` funktioniert nicht auf `<div>`
- `showKTab()` verwendet `data-tab="name"` Attribut — **nicht** textContent-Matching
- `rlog_stats` ist importiert als `rlog_stats` aber heißt intern `estats` — Alias beachten
- `generate_html()` baut die gesamte Seite einmalig beim GET / zusammen
- JS-Code in Python f-strings: `{{}}` für literale geschweifte Klammern
