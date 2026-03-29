# AGENT.md — Verbindliche Arbeitsregeln für Claude Code

> Immer lesen vor Arbeitsbeginn. Stand: 2026-03-29

---

## 1. Pflicht-Ablauf jeder Session

### Session-Start
1. Diese Datei lesen (Regeln)
2. `session_handoff.json` lesen (letzter Arbeitsstand, offene Punkte, nächster Schritt)
3. `feature_registry.json` lesen (Feature-Status aller Module)
4. **`knowledge/session_log.md` lesen** — prüfen ob offene Punkte aus vorheriger Session (Crash-Recovery!)
5. **Kai's Arbeitsanweisung/Prompt sofort in `knowledge/session_log.md` eintragen** mit Datum+Uhrzeit-Stempel (Pflicht, auch bei kleinen Aufträgen — Crash-Backup)
6. **Feature-Listen scannen und abgleichen** (PFLICHT, auch bei kleinen Änderungen):
   - `_archiv/feature_list.md` lesen
   - `_archiv/only_kais checkliste.md` lesen
   - `knowledge/Todo_checkliste.md` lesen
   → Mit `feature_registry.json` abgleichen, alle drei Dateien bei Bedarf aktualisieren

### Session-Start: Größerer Auftrag kommt rein
1. **Sofort** in `user_briefs.md` festhalten — Original-Wortlaut oder treue Rekonstruktion
2. Dann mit der Arbeit beginnen

### Session-Ende / Nach jeder Änderung
1. **Git Commit** erstellen (immer nach jeder abgeschlossenen Änderung)
   → **pre-commit Hook läuft automatisch** und schreibt atomare Mikro-Einträge in change_log.jsonl
   → Kein manuelles Schreiben nötig — Hook übernimmt das
2. `session_handoff.json` aktualisieren (was wurde getan, nächster Schritt)
3. `feature_registry.json` aktualisieren (Status geänderter Features)
4. `known_issues.json` aktualisieren (neue Issues rein, behobene auf "fixed")
5. `MEMORY.md` prüfen und bei Bedarf ergänzen
6. `KIRA_KOMPLETT_UEBERSICHT.md` bei größeren Änderungen aktualisieren
7. `server_map.md` aktualisieren wenn neue Funktionen in server.py hinzukamen
8. **`knowledge/session_log.md` abschließen** — Status der Session eintragen (erledigt / was offen blieb)
9. **Feature-Listen abgleichen** (PFLICHT, auch bei kleinen Änderungen):
   - `_archiv/feature_list.md` aktualisieren
   - `_archiv/only_kais checkliste.md` aktualisieren
   - `knowledge/Todo_checkliste.md` aktualisieren (auch kleine Aufgaben!)
   → Alle drei mit `feature_registry.json` abgleichen
10. **Partner-View generieren** (PFLICHT nach Änderungen an feature_registry.json):
    ```
    python scripts/generate_partner_view.py
    ```
    → prüft ob HTML aktuell ist, aktualisiert falls nötig
    → Push zu GitHub NUR nach expliziter Freigabe durch Kai: `--push` Flag
    → Kai sieht diff und sagt "ja, push" → dann: `python scripts/generate_partner_view.py --push`
    → **Mail an Leni + BCC Kai**: Wenn Versand fehlschlägt → sofort explizite Fehlermeldung im Chat ausgeben: "⚠️ Mail an Leni konnte nicht gesendet werden: [Fehlerdetail]. Bitte manuell prüfen."

### Nach Leni-Feedback (Workflow)
1. Kai gibt Leni-Feedback mit "Alles für Claude kopieren" (Admin-Panel) → fügt in Chat ein
2. Claude prüft jedes Feedback-Item:
   - Sinnvoll & machbar? → formuliert Update-Vorschlag für Kai
   - Kai gibt Freigabe? → Claude trägt in `feature_registry.json` ein (Status `leni_idea`)
   - Nicht sinnvoll / außerhalb Scope? → Claude erklärt warum, kein Eintrag
3. **Priorität:** Leni-Ideen bekommen KEINE hohe Priorität — außer Claude sieht klaren Mehrwert
4. Wenn Leni-Idee umgesetzt: Status → `leni_done`, `generate_partner_view.py` ausführen, pushen

> **Atomares Mikro-Logging (automatisch via pre-commit Hook):**
> `scripts/diff_to_changelog.py --staged` — ein Eintrag pro CSS-Property, Funktion, HTML-Attribut, Farbe, Schriftart
> Manuell ausführen: `python scripts/diff_to_changelog.py --since HEAD~1 --dry-run`
> Bei Bedarf nachträglich: `python scripts/diff_to_changelog.py --since COMMIT_HASH`

---

## 1b. Crash-Backup: session_log.md

**Datei:** `knowledge/session_log.md` (append-only, niemals überschreiben)

**Format für jeden Eintrag:**
```
## [DATUM] [UHRZEIT] — Session-Start
**Auftrag:** [Kai's vollständiger Prompt / Arbeitsanweisung — Original-Wortlaut]
**Status:** offen

---
[Session-Ende-Nachtrag:]
**Erledigt:** [Was wurde fertig]
**Offen geblieben:** [Was nicht fertig wurde oder beim nächsten Start weitergehen muss]
**Status:** erledigt / teilweise / crash
```

**Zweck:** Wenn Claude oder der Server crasht und der Kontext verloren geht, kann die nächste Session anhand dieser Datei sofort weitermachen — ohne dass Kai alles neu erklären muss.

**Regel beim Start:** Letzten Eintrag prüfen — wenn Status = "offen" oder "crash" → Kai sofort informieren: "Ich sehe eine offene Aufgabe vom [Datum]: [Auftrag]. Weiterführen?"

---

## 1c. Todo_checkliste.md — Pflicht-Aktualisierung

**Datei:** `knowledge/Todo_checkliste.md`

- Enthält ALLE Features und Aufgaben mit Status (✅/🔧/❌/💡/📋)
- **Pflicht: nach jeder Session aktualisieren** — auch bei kleinen Änderungen
- Neue Features sofort eintragen, erledigte auf ✅ setzen
- Ist die **Grundlage unserer Arbeit** — immer aktuell halten
- Dient zusammen mit `feature_registry.json` als Single Source of Truth

**Die 3 Listen immer synchron halten:**

| Datei | Zweck |
|---|---|
| `knowledge/Todo_checkliste.md` | Detaillierte Status-Checkliste pro Feature-Element |
| `feature_registry.json` | Maschinenlesbare Feature-Liste (für Partner-View) |
| `_archiv/feature_list.md` | Technische Übersicht mit Datei:Zeile Referenzen |
| `_archiv/only_kais checkliste.md` | Kais persönliche Wunschliste + Prioritäten |

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
| session-i | 2026-03-27 | Memory-System ausgebaut (server_map, ADRs, known_issues, user_briefs, UEBERSICHT aktuell) |
| session-j | 2026-03-27 | Vollständiges Runtime-Logging: mail_monitor+daily_check+13 JS _rtlog-Calls, Kira nutzt Logs aktiv, reichhaltige Einstellungen-Karte |
| session-y | 2026-03-29 | Mail-Bug-Fix (_index_mail immer) + WhatsApp Business Cloud API + Mail & Konten Overhaul + Integrationen UI + ISS-015 behoben |
