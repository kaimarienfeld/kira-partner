---
name: Regel – Feature-System vor/nach Arbeitssession prüfen
description: Vor jeder Arbeitssession AGENT.md + feature_registry.json + session_handoff.json lesen, nach Abschluss alle drei JSON-Dateien aktualisieren
type: feedback
---

Vor dem Start einer Arbeitssession immer `AGENT.md`, `memory/feature_registry.json` und `memory/session_handoff.json` lesen. Nach Abschluss alle drei Tracking-Dateien aktualisieren.

**Why:** Kai hat explizit verlangt, dass eine akribische Feature-Liste geführt wird, die immer aktuell ist. Das System wurde auf maschinenlesbare JSON-Dateien + AGENT.md umgestellt (2026-03-27). `feature_list.md` ist archiviert.

**How to apply:**
- Session-Start: AGENT.md lesen (Regeln) + session_handoff.json (letzter Stand) + feature_registry.json (Feature-Status)
- Neue Features: in feature_registry.json eintragen (Schema v2, alle Pflichtfelder)
- Geänderte Features: status + last_updated in feature_registry.json aktualisieren
- Session-Ende: session_handoff.json (what_was_done, next step), progress_log.json (Eintrag), feature_registry.json (Status) aktualisieren
