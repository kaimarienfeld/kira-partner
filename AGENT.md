# AGENT.md — Verbindliche Arbeitsregeln für Claude Code

> Immer lesen vor Arbeitsbeginn. Stand: 2026-03-27

---

## 1. Pflicht-Ablauf jeder Session

### Session-Start
1. Diese Datei lesen (Regeln)
2. `session_handoff.json` lesen (letzter Arbeitsstand, offene Punkte, nächster Schritt)
3. `feature_registry.json` lesen (Feature-Status aller Module)

### Session-Ende / Nach jeder Änderung
1. **Git Commit** erstellen (immer nach jeder abgeschlossenen Änderung)
2. `session_handoff.json` aktualisieren (was wurde getan, nächster Schritt)
3. `feature_registry.json` aktualisieren (Status geänderter Features)
4. `MEMORY.md` prüfen und bei Bedarf ergänzen
5. `KIRA_KOMPLETT_UEBERSICHT.md` bei größeren Änderungen aktualisieren

---

## 2. Git-Regeln

- **Nach jeder abgeschlossenen Änderung sofort committen** — nie mehrere Sessions ohne Commit
- Neue Dateien staged hinzufügen (nie `git add -A` mit sensiblen Dateien)
- `scripts/secrets.json` NIEMALS committen
- `knowledge/*.db` nur committen wenn explizit gewünscht
- Commit-Nachrichten: kurz, auf Deutsch oder Englisch, beschreibt das Warum

---

## 3. Projektstruktur

```
memory/                     ← Dieses Verzeichnis (Git-Repo)
├── scripts/                ← Python-Backend + server.py
│   ├── server.py           ← Haupt-Dashboard (localhost:8765)
│   ├── kira_llm.py         ← Multi-LLM Chat-Modul
│   ├── runtime_log.py      ← Runtime-Event-Store (NEU session-h)
│   ├── activity_log.py     ← Einfaches Aktivitätslog (Legacy)
│   ├── change_log.py       ← Entwicklungs-Mikro-Log
│   ├── mail_monitor.py     ← IMAP-Polling (Echtzeit)
│   ├── daily_check.py      ← Täglicher Mail-Scan
│   └── config.json         ← Konfiguration (kein secrets.json!)
├── knowledge/              ← SQLite-Datenbanken
│   ├── tasks.db            ← Aufgaben, Wissen, Kira-Konversationen
│   ├── runtime_events.db   ← Runtime-Event-Store (NEU)
│   └── ...
├── AGENT.md                ← Diese Datei
├── MEMORY.md               ← Memory-Index
├── session_handoff.json    ← Letzter Arbeitsstand
├── feature_registry.json   ← Feature-Status-Tracking
└── change_log.jsonl        ← Append-only Entwicklungs-Log
```

---

## 4. Kritische technische Regeln

### Kira-Workspace UI (kq-* / kw-*)
- CSS-Prefix `kq-*` = Quick Panel, `kw-*` = Workspace
- Workspace: 3 Spalten (kw-ctx-panel 240px | kw-center flex:1 | kw-tools 240px)
- `kiraSendBtn` muss `<button>` sein (nicht `<div>`) damit `.disabled` funktioniert
- `showKTab()` verwendet `data-tab` Attribut, nie textContent-Matching
- Alte CSS-Klassen `kira-quick-*` und `kira-ws-*` sind vollständig entfernt

### Runtime-Log (session-h)
- Neues Modul: `scripts/runtime_log.py` + DB: `knowledge/runtime_events.db`
- 5 Event-Typen: `ui`, `kira`, `llm`, `system`, `settings`
- `elog()` wirft NIE Exceptions, gibt event_id zurück
- Activity_log.py bleibt für Backward-Compat erhalten
- Kira kann Logs via `runtime_log_suchen` Tool lesen (wenn `kira_darf_lesen=True`)

### Server-Architektur
- ThreadedHTTPServer auf 127.0.0.1:8765
- `do_GET` / `do_POST` in `DashboardHandler`
- Alle f-strings in HTML-Strings: JS-Code mit `{{}}` escapen

### Datenbanken
- `tasks.db`: Aufgaben, corrections, wissen_regeln, kira_konversationen, etc.
- Niemals DB-Schema ohne Migration ändern
- `get_db()` gibt Row-Factory-Connection zurück

---

## 5. Verbote

- `scripts/secrets.json` NIEMALS lesen, anzeigen, committen
- `knowledge/mail_index.db` nicht ohne Reason anfassen (groß, langsam)
- Keine Änderungen an `activity_log.py` (Backward-Compat)
- Gmail-Tool NIEMALS verwenden — immer Mail-Archiv-Ordner nutzen
- Keine Preise im Erstkontakt mit Kunden (Kiras Wissensregel)

---

## 6. Offene Feature-Wünsche (Future List)

Detaillierte Übersicht in `KIRA_KOMPLETT_UEBERSICHT.md` → Kapitel 7.

**Kurzliste prioritär:**
- [ ] Direkte E-Mail-Antwort aus Dashboard (SMTP)
- [ ] Kira Tagesstart-Briefing (Morgen-Zusammenfassung)
- [ ] Kunden-360-Ansicht (Timeline pro Kunde)
- [ ] Angebots-Kalkulations-Assistent
- [ ] mail_monitor.py: runtime_log Integration
- [ ] daily_check.py: runtime_log Integration
- [ ] Cashflow-Prognose

---

## 7. Session-Protokoll (laufend)

| Session | Datum | Was |
|---------|-------|-----|
| session-g | 2026-03-27 | Kira-Workspace UI Rebuild (kq-*/kw-*, 3-Spalten, Quick Panel) |
| session-h | 2026-03-27 | Runtime-Log-System (runtime_log.py, server.py Integration, Einstellungen-UI) |
