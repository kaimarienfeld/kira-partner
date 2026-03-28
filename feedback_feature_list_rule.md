---
name: Regel – Feature-System vor/nach Arbeitssession prüfen
description: Vor jeder Arbeitssession AGENT.md + feature_registry.json + session_handoff.json lesen, nach Abschluss alle drei JSON-Dateien aktualisieren
type: feedback
---

Vor dem Start einer Arbeitssession immer `AGENT.md`, `memory/feature_registry.json` und `memory/session_handoff.json` lesen. Nach Abschluss alle drei Tracking-Dateien aktualisieren.

**Why:** Kai hat explizit verlangt, dass eine akribische Feature-Liste geführt wird, die immer aktuell ist. Das System wurde auf maschinenlesbare JSON-Dateien + AGENT.md umgestellt (2026-03-27). `feature_registry.json` ist die Schnittstelle — alle anderen Listen werden damit abgeglichen.

**Referenz-Quellen die bei jeder Feature-Discovery abzugleichen sind:**
1. `feature_registry.json` — Haupt-Schnittstelle (immer zuerst)
2. `_archiv/feature_list.md` — Kai arbeitet aktiv damit im Editor (detaillierte Tabellen mit Datei:Zeile)
3. `_archiv/only_kais checkliste.md` — Kais laufende Wunschliste, Bugs und Ideen (rohe Notizen)
4. `KIRA_KOMPLETT_UEBERSICHT.md` §7.x — Roadmap/Entwicklungsstand
5. `kira_llm.py` Tools, `server.py` Funktionen, git-Log — für Abgleich was tatsächlich implementiert ist

**How to apply:**
- Session-Start: AGENT.md lesen (Regeln) + session_handoff.json (letzter Stand) + feature_registry.json (Feature-Status)
- Discovery: Alle 5 Referenz-Quellen abgleichen → Abweichungen in feature_registry.json eintragen
- Neue Features: in feature_registry.json eintragen (Schema v3, alle Pflichtfelder), dann generate_partner_view.py laufen lassen
- Geänderte Features: status + last_updated in feature_registry.json aktualisieren
- Session-Ende: session_handoff.json (what_was_done, next step), change_log.jsonl (Eintrag), feature_registry.json (Status) aktualisieren
