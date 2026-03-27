# Architecture Decisions

> Warum wurde was wie gebaut. Niemals rückgängig machen ohne diesen Eintrag zu lesen.

---

## ADR-001: runtime_log.py als separates Modul statt Erweiterung von activity_log.py

**Datum:** 2026-03-27 (session-h)
**Entscheidung:** Neues Modul `runtime_log.py`, `activity_log.py` unverändert belassen.

**Warum:**
- activity_log.py hat nur 8 Spalten, Details auf 600 Zeichen gekappt — kein Vollkontext möglich
- Bestehende Aufrufer von alog() (5 Stellen in server.py, mail_monitor.py) würden brechen
- Neues Schema brauchte 24 Metadaten-Spalten + separate Payload-Tabelle
- activity_log.py bleibt als Backward-Compat und für simple Diagnose-Logs

**Nicht rückgängig machen weil:** activity_log.py ist stabil, hat Aufrufer, Schema-Änderung würde Migration aller bestehenden Daten erfordern.

---

## ADR-002: SQLite WAL-Modus für runtime_events.db

**Datum:** 2026-03-27 (session-h)
**Entscheidung:** `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=NORMAL`

**Warum:**
- Kira liest Logs während server.py schreibt (gleichzeitiger Zugriff)
- WAL erlaubt mehrere Leser gleichzeitig ohne Schreiber zu blockieren
- NORMAL statt FULL: ausreichende Sicherheit bei besserer Performance
- Threading-Lock (`_lock`) serialisiert Schreibvorgänge

**Nicht ändern weil:** Ohne WAL würden Lesezugriffe von Kira Schreibvorgänge blockieren.

---

## ADR-003: kq-*/kw-* CSS-Prefix statt alte kira-quick-*/kira-ws-*

**Datum:** 2026-03-27 (session-g)
**Entscheidung:** Vollständiger CSS-Neuaufbau mit neuen Prefixen.

**Warum:**
- Alte Klassen (kira-quick-*, kira-ws-*) hatten inkonsistente Benennung
- Referenzvorlagen (05-Kira-Workspace, 05.1-Kira-Quick) verwenden kq-*/kw-*
- Sauberer Schnitt ermöglicht zuverlässiges Debugging (kein Klassen-Mix)

**CSS-Namespace:**
- `kq-*` = Quick Panel (Overlay, 7 Items, Footer-Input)
- `kw-*` = Workspace (3-Spalten: ctx-panel/center/tools)
- `kira-*` = allgemein (kiraWorkspace ID etc. beibehalten für JS-Refs)

---

## ADR-004: kiraSendBtn als `<button>` nicht `<div>`

**Datum:** 2026-03-27 (session-g, Bugfix)
**Entscheidung:** `<button class="kw-ia send" id="kiraSendBtn">` statt `<div>`

**Warum:** `element.disabled = true` funktioniert nur auf Form-Elementen (button, input, select). Bei einem `<div>` hat `.disabled` keinen Effekt — der Button bleibt klickbar während Kira lädt und erzeugt Doppel-Anfragen.

**Nicht rückgängig machen weil:** Bug war reproduzierbar: bei schnellem Doppelklick wurden 2 Chat-Anfragen gesendet.

---

## ADR-005: showKTab() mit data-tab Attribut statt textContent-Matching

**Datum:** 2026-03-27 (session-g)
**Entscheidung:** `querySelector('.kw-ctx-item[data-tab="name"]')` statt textContent-Vergleich.

**Warum:** textContent-Matching ist fragil (ändert sich wenn UI-Text geändert wird, Whitespace-Probleme). data-tab ist semantisch, stabil, unabhängig vom Anzeigetext.

---

## ADR-006: generate_html() baut Seite einmalig pro Request

**Datum:** (original Design)
**Entscheidung:** Kein SPA-Framework, kein React. Komplette HTML-Seite wird bei jedem `GET /` neu generiert.

**Warum:** Einfache Architektur, kein Build-Step, keine Dependencies. Python f-string HTML ist direkt debuggbar. Für 1-User-Dashboard ausreichend.

**Konsequenz:** JS-Code in Python f-strings braucht `{{}}` für geschweifte Klammern.

---

## ADR-007: Getrennte DB für Runtime-Events

**Datum:** 2026-03-27 (session-h)
**Entscheidung:** `knowledge/runtime_events.db` statt Tabellen in `tasks.db`

**Warum:**
- tasks.db enthält Geschäftsdaten — Trennung vermeidet Schema-Konflikte
- Runtime-Events können sehr viele Zeilen haben (100k+) — separate DB verhindert tasks.db-Bloat
- Kann unabhängig gelöscht/archiviert werden ohne Geschäftsdaten zu verlieren
