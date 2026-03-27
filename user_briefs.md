# User Briefs — Original-Aufträge von Kai

> Append-only. Nie überschreiben, nie umsortieren.
> Bei jedem größeren Auftrag den Original-Wortlaut festhalten.
> Dient als Referenz: "Warum wurde das so gebaut?" → hier steht die Original-Anforderung.

---

## 2026-03-27 | session-g | Kira Workspace UI Rebuild

**Auftrag (sinngemäß rekonstruiert aus Session-Verlauf):**

> "Bitte beginne jetzt ausschließlich mit der UI-Anpassung der Seite Kira-Workspace.
>
> Binding reference:
> - 05-Kira-Workspace Plan für UI.md
> - 05_kira_workspace_modul_v1.html
> - 05.1 kira_quick_panel_v1.html
> - 05.2_kira_launcher_v2_elegant.html
>
> Alte Kira UI: gestalterisch vollständig verwerfen — nicht recyceln.
> Bestehende Backend-Funktionen: dürfen nicht gelöscht werden.
>
> Architektur: 3 Ebenen
> - Ebene 1: Launcher (FAB, lila, schwebend)
> - Ebene 2: Quick Panel (kq-*) — 7 Items mit farbigen Icon-Boxen, Pfeilen, Footer-Input
> - Ebene 3: Workspace (kw-*) — 3-Spalten-Layout
>
> Workspace 3 Spalten:
> - Links: kw-ctx-panel (240px) — Navigation + History-Sidebar
> - Mitte: kw-center — Kontext-Bar (kw-cbar, default hidden), Tabs, Quick-Actions-Bar, Input
> - Rechts: kw-tools (240px, collapsible) — Anhänge, Regeln, Aktionen
>
> Quick Panel 7 Items (mit Farb-Icons):
> - Neue Frage (purple), Aufgaben (amber), Rechnungen (green), Angebote (blue),
>   Kunden (coral), Letzte Verläufe (gray), Suche (teal)
> - Jedes Item: farbige Icon-Box + Title + Sub + Pfeil-Arrow
> - Footer: Input + Senden-Button (kqDirectSend)
>
> Nach Kira fertig: stoppen."

**Ergebnis:** Vollständig umgesetzt. CSS kq-*/kw-*, 15 neue JS-Funktionen, HTML komplett neu.

---

## 2026-03-27 | session-h | Runtime- und Kontext-Logging-System

**Auftrag (sinngemäß rekonstruiert aus Session-Verlauf):**

> "Bitte erweitere das bestehende Logging-System in Kira jetzt zu einem vollständigen,
> lückenlosen Runtime- und Kontext-Logging-System für das gesamte Programm.
>
> NICHT ein drittes System bauen — zuerst den aktuellen Stand prüfen,
> dann sinnvoll erweitern oder migrieren.
>
> Ziel: lückenlose Nachvollziehbarkeit für drei Akteure:
> - Kai (was hat Kira wann getan?)
> - Claude Code (was wurde in welcher Session gebaut?)
> - Kira selbst (was habe ich getan, welche Fehler gab es?)
>
> Was muss geloggt werden:
> - UI-Klicks und Ereignisse (Panel öffnen, Status setzen, Navigation)
> - Kira Chat / Tool-Aufrufe / Kontext-Übergaben
> - LLM Provider / Modell / Tokens / Dauer / Fallback / Fehler
> - Hintergrundjobs (Mail-Monitor, daily_check)
> - Einstellungsänderungen (mit Vor- und Nachwert)
>
> Für relevante Ereignisse: vollständiger Kontext-Payload speichern:
> - Volle Nutzerfrage, volle Kira-Antwort, vollständiger Kontext-Snapshot
>
> Architektur-Anforderungen:
> - SQLite Event-Store bevorzugt (nicht JSONL)
> - Zwei Tabellen: Metadaten-Tabelle + Payload-Tabelle
> - 5 Event-Typen: ui / kira / llm / system / settings
> - Performance: buffered/async, WAL-Modus, keine blockierenden Schreibvorgänge,
>   keine hochfrequenten Events loggen
>
> Pflichtfelder (Metadaten):
> id, timestamp, session_id, event_type, source, modul, submodul,
> actor_type, context_type, context_id, action, status, result, summary,
> provider, model, token_in, token_out, duration_ms,
> error_code, error_message, follow_up_required, related_event_id
>
> Payload-Felder:
> user_input_full, assistant_output_full, context_snapshot_json,
> entity_snapshot_json, settings_before_json, settings_after_json,
> mail_body_full, thread_excerpt_full
>
> Kira muss Logs lesen können:
> - Tool 'runtime_log_suchen' in kira_llm.py
> - Nur aktiv wenn kira_darf_lesen=True in Config
>
> Einstellungen-Section im Dashboard:
> - Granularitäts-Steuerung per Toggle pro Event-Typ
> - Stats-Anzeige (total, heute, fehler, db-größe)
> - Filter + Viewer"

**Ergebnis:** runtime_log.py erstellt (280 Zeilen), kira_llm.py + server.py vollständig integriert.
Offen: mail_monitor.py + daily_check.py Integration ausstehend (ISS-004, ISS-005).

---

## 2026-03-27 | session-i | Memory-System + Cross-Session-Continuity

**Auftrag:**

> "Ist es sinnvoll die Anweisungen in irgendeiner Form mit zu loggen?
> Ja bitte unbedingt und in den Regeln dann mit aufnehmen."

> (Vorher): "Was benötigst du noch um session-übergreifend besser arbeiten zu können,
> damit nichts — aber auch wirklich nichts — verloren geht und die nächste Session
> bis ins kleinste Detail sieht was vorher gemacht wurde?"

**Ergebnis:**
- server_map.md (alle Funktionen + Zeilen)
- architecture_decisions.md (7 ADRs)
- known_issues.json (5 offene Issues)
- user_briefs.md (diese Datei)
- KIRA_KOMPLETT_UEBERSICHT.md auf Stand 27.03. gebracht
- Feedback-Regel für Briefs aufgenommen
