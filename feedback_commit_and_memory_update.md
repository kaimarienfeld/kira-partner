---
name: Regel – Nach jeder Änderung committen + Memory aktualisieren
description: Nach jeder abgeschlossenen Änderung sofort Git-Commit erstellen und AGENT.md / MEMORY.md / session_handoff.json / feature_registry.json aktualisieren
type: feedback
---

Nach jeder abgeschlossenen Änderung sofort einen Git-Commit erstellen und alle relevanten Memory/Tracking-Dateien aktualisieren.

**Why:** Kai hat explizit diese Regel eingefordert (2026-03-27). Ohne Commits und aktuelle Tracking-Dateien geht Arbeitsstand verloren und zukünftige Sessions starten ohne Kontext.

**How to apply:**
1. **Git Commit** — direkt nach jeder abgeschlossenen Änderungseinheit, nicht erst am Session-Ende
2. **session_handoff.json** — `what_was_done`, `open_tasks`, `next_step`, `critical_notes` aktualisieren
3. **feature_registry.json** — Status geänderter Features auf `done`/`partial`/`planned` setzen, `last_updated` anpassen
4. **AGENT.md** — Session-Protokoll-Tabelle ergänzen, `Open Feature-Wünsche` bei Bedarf aktualisieren
5. **MEMORY.md** — Neue Dateien/Einträge hinzufügen wenn neue Memory-Dateien erstellt wurden
6. **KIRA_KOMPLETT_UEBERSICHT.md** — Bei größeren Architekturänderungen aktualisieren (nicht bei Kleinigkeiten)

Reihenfolge: Commit → dann Memory-Updates (oder beides in einem Commit).
