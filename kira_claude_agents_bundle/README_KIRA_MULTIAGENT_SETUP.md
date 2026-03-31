# KIRA Multi-Agent Setup für Claude Code

Diese Dateien sind für den Projektordner gedacht.

Zielstruktur im Projekt:

```text
.claude/
  README_KIRA_MULTIAGENT_SETUP.md
  agents/
    kira-repo-auditor.md
    kira-memory-compliance-guard.md
    kira-case-engine-architect.md
    kira-workflow-integrator.md
    kira-db-migration-guard.md
    kira-validation-guard.md
  optional/
    settings.agent-guards.example.json
    (entfernt — konsolidiert in _analyse/KIRA_SYSTEM_ANALYSE.md)
```

## Wichtige Regel

Diese Agenten sollen **projektbezogen** unter `.claude/agents/` liegen. Projekt-Agenten haben in Claude Code höhere Priorität als persönliche Agenten unter `~/.claude/agents/`.

## So einsetzen

1. Alle Dateien aus diesem Bundle in den Projektordner kopieren.
2. Claude Code neu starten oder `/agents` verwenden.
3. Bei mittleren oder großen Aufträgen zuerst **Plan Mode** bzw. den eingebauten **Plan**-Agenten nutzen.
4. Danach **kira-repo-auditor** laufen lassen.
5. Erst wenn Gap-Analyse und Umsetzungsplan vorliegen, dürfen schreibende Agents eingesetzt werden.

## Verbindliche Projektquellen

Alle Agents müssen sich zuerst an diese Quellen halten:

- `AGENT.md`
- `memory/_analyse/KIRA_SYSTEM_ANALYSE.md`
- `memory/_analyse/KIRA_SYSTEM_ANALYSE.md` (konsolidierte Systemdokumentation)
- `memory/session_log.md`
- `memory/change_log.jsonl`
- relevante Dateien unter `memory/komplett plan für UI/`
- Feature-Registry, Issues, Handovers und To-do-Listen, falls vorhanden

## Arbeitsreihenfolge für größere Aufträge

1. Plan Mode / Plan-Agent
2. Repo-Audit gegen Soll und Ist
3. Architektur- und Migrationsplan
4. Teilumsetzung in kleinen, dokumentierten Schritten
5. Validierung gegen Memory, AGENT.md und reale Funktion
6. Session-Log, Handover, Registry und Change-Log aktualisieren

## Wichtige Schutzregel

UI gilt nicht als Beweis für Funktion.
Alles muss gegen echte Verdrahtung, echte Datenflüsse und reale Zustandsänderungen geprüft werden.
