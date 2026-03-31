# AGENT.md — Verbindliche Arbeitsregeln für Claude Code

> Immer lesen vor Arbeitsbeginn. Stand: 2026-03-29

---

## 1. Pflicht-Ablauf jeder Session

### Session-Start
1. Diese Datei lesen (Regeln)
2. `session_handoff.json` lesen (letzter Arbeitsstand, offene Punkte, nächster Schritt)
3. `feature_registry.json` lesen (Feature-Status aller Module)
4. **`knowledge/session_log.md` lesen** — letzten Eintrag prüfen (Crash-Recovery). Bei Status "offen" oder "crash": session_log.md + App-Zustand prüfen → was war fertig, was offen → direkt weiterführen (kein Nachfragen nötig, Kai fragt selbst wenn er Kontext braucht)
5. **Kai's Arbeitsanweisung/Prompt sofort in `knowledge/session_log.md` eintragen** mit Datum+Uhrzeit-Stempel (Pflicht, auch bei kleinen Aufträgen — Crash-Backup). Während der Session: neue Teilaufgaben ebenfalls nach Schema der Datei eintragen.
6. **Feature-Listen scannen und abgleichen** (PFLICHT, auch bei kleinen Änderungen):
   - `_archiv/feature_list.md` lesen
   - `_archiv/only_kais checkliste.md` lesen
   - `knowledge/Todo_checkliste.md` lesen
   → Mit `feature_registry.json` abgleichen, alle drei Dateien bei Bedarf aktualisieren

7. **`change_log.jsonl` aufgabenbezogen prüfen** (PFLICHT bei jeder neuen Aufgabe):
   → Relevante Einträge zum Auftrag sammeln: Was ist bereits eingebaut? Was ist noch offen? Was fehlt ganz?
   → Konflikte, Doppelarbeit und überflüssige Eingriffe vermeiden
   → Siehe Abschnitt 1e für Details

### Session-Start: Größerer Auftrag kommt rein
1. **Sofort** in `user_briefs.md` festhalten — Original-Wortlaut oder treue Rekonstruktion
2. **Plan-Agent nutzen** (PFLICHT bei größeren Aufträgen): Vor der Implementierung immer `Plan`-Agenten starten, um die beste Umsetzung zu strukturieren — Schritte, betroffene Dateien, Reihenfolge. Direkt danach implementieren. Verhindert vergessene Arbeitsanweisungen und Fehler durch fehlende Planung.
3. Dann mit der Arbeit beginnen

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
10a. **KIRA 2.0 UI-Umbau-Plan aktuell halten** (PFLICHT bei allen UI/UX-Änderungen):
   - `_analyse/KIRA_2_0_UI_UMBAU_PLAN.md` — Status-Tabellen aktualisieren (✅ done, 📋 offen, 🔧 in Arbeit)
   - Neue To-dos die beim Bauen auffallen direkt eintragen
   - Ist-Zustand-Beschreibungen nach Umbau aktualisieren
   → Gilt als Referenz für alle KIRA-Umbau-Sessions — immer lesen bevor neue KIRA-UI-Arbeit beginnt
10. **Partner-View generieren + automatisch pushen** (PFLICHT):
    ```
    python scripts/generate_partner_view.py        # immer: lokal aktualisieren
    python scripts/generate_partner_view.py --push # wenn Push-Kriterien erfüllt
    ```
    → Lokal generieren: immer, kein Nachfragen
    → **Auto-Push zu GitHub**: wenn die Änderung für Leni relevant ist (siehe Abschnitt 1d)
    → **KEIN Push**: wenn Änderung auf der KEIN-PUSH-Liste steht (siehe Abschnitt 1d)
    → **Mail an Leni + BCC Kai**: Wenn Versand fehlschlägt → sofort im Chat: "⚠️ Mail an Leni konnte nicht gesendet werden: [Fehlerdetail]. Bitte manuell prüfen."

### Abschluss-Tabelle (PFLICHT nach jeder erledigten Aufgabe)

Nach jeder abgeschlossenen Aufgabe IMMER diese Tabelle im Chat ausgeben — gibt Kai Kontrolle und Gewissheit:

```
## ✅ Erledigt — [Aufgaben-Titel] · [DATUM] [UHRZEIT]

| Was | Details |
|-----|---------|
| 🔧 Geänderte Dateien | [Datei 1, Datei 2, ...] |
| 📝 Git Commit | [Commit-Hash] — [Commit-Message] |
| 📋 Tracking aktualisiert | session_handoff ✓ / known_issues ✓ / feature_registry ✓ / Todo_checkliste ✓ |
| 🤝 Partner-View | generiert ✓ / Push ✓ oder: kein Push (Grund) |
| ⚠️ Offen geblieben | [Was nicht fertig wurde — oder: —] |
| 🔜 Empfohlener nächster Schritt | [Was als nächstes sinnvoll wäre] |
```

Regel: Tabelle kommt IMMER — auch bei kleinen Aufgaben (1 Zeile reicht dann). Kai soll nicht nachfragen müssen ob alles gemacht wurde.

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

**WICHTIG: Alle Einträge IMMER mit Datum UND Uhrzeit** — gilt auch für alle anderen Tracking-Dateien (session_handoff.json, known_issues.json, AGENT.md Protokoll, etc.)

**Format für jeden Eintrag:**
```
## 2026-MM-DD HH:MM — Session-Start
**Auftrag:** [Kai's vollständiger Prompt / Arbeitsanweisung — Original-Wortlaut]
**Status:** offen

### 2026-MM-DD HH:MM — Neue Teilaufgabe
**Auftrag:** [Neue Anweisung von Kai mid-session]
**Status:** offen / erledigt

---
## 2026-MM-DD HH:MM — Session-Ende
**Erledigt:** [Was wurde fertig — mit Datum+Uhrzeit]
**Offen geblieben:** [Was nicht fertig wurde]
**Status:** erledigt / teilweise / crash
```

**Wann eintragen:**
- Session-Start: Kai's erster Prompt → sofort als Eintrag
- Mid-Session: Jede neue Teilaufgabe von Kai → Eintrag nach Schema
- Session-Ende: Abschluss-Eintrag mit Status

**Crash-Recovery (kein Nachfragen):**
Bei Status "offen" oder "crash": session_log.md + App/Git-Zustand prüfen → selbst rekonstruieren was fertig war und was offen → direkt weiterführen. Kai fragt aktiv wenn er Kontext braucht ("Was war die letzte Aufgabe?") — dann: Datei lesen, App prüfen, Bericht + sofort weiterführen.

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

## 1d. Partner-View Push-Entscheidung

**Faustregel:** Würde Leni etwas Neues oder Geändertes sehen? → Push. Sonst nicht.

### KEIN Push — technische/interne Änderungen

| Kategorie | Beispiele |
|---|---|
| Regeländerungen | AGENT.md, MEMORY.md, session_log.md, feedback_*.md |
| Tracking-Dateien | session_handoff.json, known_issues.json, server_map.md, change_log.jsonl |
| Reparaturen / Bugfixes | Mail-Monitor-Bug, Server-Crashes, Encoding-Fixes, API-404-Fixes |
| Konfiguration | config.json, secrets.json Änderungen |
| Interne Infra | runtime_log.py, activity_log.py, diff_to_changelog.py |
| feature_registry ohne leni-Effekt | Nur `notes`-Feld oder interne Status-Tags geändert, keine neuen sichtbaren Features |
| Session-Bookkeeping | Nur Tracking-Commits (chore/fix/docs ohne App-Änderung) |

### PUSH — Leni-relevante Änderungen

| Kategorie | Beispiele |
|---|---|
| Neues Feature eingebaut | Status `planned` → `done` bei leni_visible=true Feature |
| Neues Feature in Registry | Neues Feature mit `leni_visible=true` hinzugefügt |
| Leni-Idee umgesetzt | Status `leni_idea` → `leni_done` |
| Sichtbare UI-Verbesserung | Dashboard-Redesign, neue Ansicht, neue Funktion die Leni kennt |
| Wichtige Funktion repariert | Wenn die Funktion Leni-sichtbar ist (z.B. Mail-Eingang, Kira-Chat) |

### Entscheidungs-Check (2 Sekunden)
```
Hat sich feature_registry.json geändert UND
  ist mindestens 1 Feature mit leni_visible=true betroffen UND
  ist es kein reiner Tracking/Bookkeeping-Commit?
→ JA: python scripts/generate_partner_view.py --push
→ NEIN: python scripts/generate_partner_view.py  (nur lokal)
```

### Einrichtung (2026-03-29 — einmalig erledigt, NICHT nochmal ausführen)

| Was | Wert |
|-----|------|
| Lokales Repo-Verzeichnis | `C:/Users/kaimr/kira-partner/` |
| Geklont von | `https://github.com/kaimarienfeld/kira-partner` |
| config.json Key | `partner_github_repo_dir` = `C:/Users/kaimr/kira-partner` (Top-Level!) |
| git user (im Repo) | `Kai Marienfeld` / `kaimrf@rauMKultSichtbeton.onmicrosoft.com` |
| PAT | in `scripts/secrets.json` → `github_pat` |
| Leni-URL | **https://kaimarienfeld.github.io/kira-partner/** |

> Wenn das Repo-Verzeichnis fehlt oder beschädigt ist:
> `git clone https://[PAT]@github.com/kaimarienfeld/kira-partner.git C:/Users/kaimr/kira-partner`
> dann `git config user.email` + `user.name` im Repo setzen.

---

## 1e. change_log.jsonl — Aufgabenbezogene Vorprüfung

**Zweck:** Bevor eine neue Aufgabe umgesetzt wird, change_log.jsonl nach relevanten Einträgen durchsuchen — um zu wissen was bereits eingebaut ist, was noch offen ist, und was noch nie angefasst wurde. Verhindert Konflikte, Doppelarbeit und sinnlose Eingriffe.

**Wann:** Pflicht bei jeder neuen Aufgabe — besonders bei Features, Bugfixes oder Umbauten.

**Wie:**
```
API-Aufruf: GET /api/changelog?limit=200&search=[Stichwort]
oder: python scripts/change_log.py --search "[Stichwort]"
```

**Auswertung — 3 Kategorien:**

| Kategorie | Bedeutung | Konsequenz |
|---|---|---|
| ✅ Bereits eingebaut | Eintrag zeigt Feature/Fix existiert | Nur prüfen ob noch aktuell, nicht neu bauen |
| 🔧 Teilweise / WIP | Mehrere Einträge aber kein abschließender | Fortführen, nicht von Null beginnen |
| ❌ Nicht enthalten | Kein passender Eintrag | Neu implementieren ohne Rücksicht auf Altlasten |

**Suchstrategie:** Auftragsbezogene Schlüsselwörter (Dateiname, Funktion, Feature-ID, Modul) → Ergebnis kurz zusammenfassen → dann erst umsetzen.

**Beispiel:**
> Auftrag: "Mail-Archiv einbauen"
> → Search: "archiv", "mail_monitor", "eml", "sync_source"
> → Findet: 12 Einträge für mail_monitor.py, letzter 2026-03-29 — archiv_import sync_source bereits vorhanden
> → Konsequenz: Nicht neu erfinden, vorhandene Struktur erweitern

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
- `scripts/config.json` NIEMALS direkt editieren — enthält Kais persönliche Einstellungen. Alle Config-Änderungen müssen über Code-Defaults (Python) oder die API/UI laufen. Neue Config-Keys werden im Python-Code mit Defaults eingeführt, NICHT durch Editieren der config.json.
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
