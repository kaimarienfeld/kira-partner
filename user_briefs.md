# User Briefs — Original-Aufträge von Kai

> Append-only. Nie überschreiben, nie umsortieren.
> Bei jedem größeren Auftrag den Original-Wortlaut festhalten.

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
>
> Nach Kira fertig: stoppen."

**Ergebnis:** Vollständig umgesetzt. CSS kq-*/kw-*, 15 neue JS-Funktionen, HTML komplett neu.

---

## 2026-03-27 | session-h | Runtime- und Kontext-Logging-System

**Auftrag (sinngemäß rekonstruiert aus Session-Verlauf):**

> "Bitte erweitere das bestehende Logging-System in Kira jetzt zu einem vollständigen,
> lückenlosen Runtime- und Kontext-Logging-System für das gesamte Programm.
>
> NICHT ein drittes System bauen — zuerst den aktuellen Stand prüfen, dann erweitern.
>
> Ziel: lückenlose Nachvollziehbarkeit für Kai, Claude Code und Kira selbst.
>
> Was muss geloggt werden:
> - UI-Klicks und Ereignisse, Kira Chat/Tools/Kontext,
>   LLM Provider/Modell/Tokens, Hintergrundjobs, Einstellungsänderungen
>
> Architektur: SQLite, 2 Tabellen (Metadaten + Payload), 5 Typen: ui/kira/llm/system/settings
> Performance: WAL-Modus, keine blockierenden Writes
> Kira muss Logs lesen können. Einstellungen-Section für Granularitäts-Steuerung."

**Ergebnis:** runtime_log.py erstellt, kira_llm.py + server.py integriert.
Offen: mail_monitor + daily_check Integration, vollständige JS-Coverage.

---

## 2026-03-27 | session-i | Memory-System + Cross-Session-Continuity

**Auftrag:** "Was benötigst du noch um session-übergreifend besser arbeiten zu können,
damit nichts verloren geht? Anweisungen auch mitloggen."

**Ergebnis:** server_map.md, architecture_decisions.md, known_issues.json, user_briefs.md,
KIRA_KOMPLETT_UEBERSICHT.md aktualisiert, Regeln ergänzt.

---

## 2026-03-27 | session-j | Runtime-Log vollständig + Kira Log-Zugriff + Einstellungen-Karte

**Auftrag (Originalwortlaut):**

> "Das Programm-Logging ist aber auch aktiv, also dass alles aufgezeichnet wird was
> im Programm geklickt, eingegeben, verändert, gesprochen, von KI benutzt etc. wird?
>
> Ja bitte vollständig ergänzen und Kira + LLM Zugriff geben und nötigen
> skill/prompt/skript dafür geben dass sie es mit nutzen soll in jeder Situation.
> In den Einstellungen eine neue Karte anlegen, wo man alle relevanten Logs schalten kann,
> man sieht ob aktiv, wieviel Logs enthalten, Größe, LLM dazu an oder aus..
> und was sonst noch sinnvoll ist für das Kira Projekt."

**Anforderungen:**
1. Alle fehlenden JS _rtlog() Aufrufe ergänzen (showPanel, setStatus, arSetStatus, angSetStatus, geschKira, readMail, loadThread, newKiraChat, kqDirectSend, loadKiraConv, wissenAction, etc.)
2. mail_monitor.py: elog() für Mail-Klassifizierung, Task-Erstellung, Monitor-Start/Stop
3. daily_check.py: elog() für Job-Start/-Ende mit Ergebnissen
4. Kira aktiv mit Logs versorgen: get_recent_for_kira() in System-Kontext einbauen
5. Kira-Instruktion: wann und wie sie die Logs nutzen soll (Systemprompt-Erweiterung)
6. Neue Einstellungen-Karte "Runtime-Log & Telemetrie" mit:
   - Alle Typ-Toggles mit Live-Status (aktiv + Anzahl Einträge + letzte Aktivität)
   - DB-Größe, Gesamt-Stats
   - LLM-Zugriff an/aus mit Erklärung
   - Vollkontext an/aus
   - Letzte Einträge Viewer (inline)
   - Export + Bereinigen
