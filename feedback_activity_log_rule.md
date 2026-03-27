---
name: Regel – Neue Module und Funktionen im Aktivitätsprotokoll aufzeichnen
description: Jedes neue Modul und jede neue wichtige Funktion muss activity_log integrieren
type: feedback
---

Bei jedem neuen Modul oder jeder neuen wichtigen Funktion immer das Aktivitätsprotokoll einbinden.

**Why:** Kai möchte jederzeit nachvollziehen können was in der App passiert ist, wo etwas fehlgeschlagen ist und warum — das Protokoll ist das zentrale Diagnosewerkzeug.

**How to apply:**
- Neues Python-Modul: Import am Anfang einfügen:
  ```python
  try:
      from activity_log import log as _alog
  except Exception:
      def _alog(*a, **k): pass
  ```
- Neue wichtige Funktion: `_alog(bereich, aktion, details, status, fehler, task_id, dauer_ms)` aufrufen
  - bereich: Kurzname des Moduls ("Mail", "Kira", "LLM", "Task", "Server", ...)
  - status: "ok" | "warnung" | "fehler"
  - Bei Fehlern: fehler=str(e) übergeben
  - Bei Zeitkritischem: dauer_ms messen mit time.monotonic()
- Vorhandene Integrationspunkte als Vorlage: execute_tool() in kira_llm.py, _process_mail() in mail_monitor.py
- Faustregel: Was für die Diagnose eines Problems nützlich wäre, soll geloggt werden
- Faustregel: Was trivial/häufig ist (z.B. jede DB-Query), NICHT loggen — nur Aktionen auf Benutzer/System-Ebene
