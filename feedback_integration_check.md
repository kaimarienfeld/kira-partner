---
name: App-weiter Integrations-Check nach jedem neuen Feature
description: Nach jedem neuen Feature/Modul die gesamte App auf Integrationspunkte prüfen und alles in feature_registry + open_tasks festhalten
type: feedback
---

Nach jedem neuen Feature oder Modul MUSS ein systematischer App-weiter Integrations-Check durchgeführt werden.

**Why:** Die App soll als kohärentes Ganzes wachsen, nicht als Sammlung isolierter Inseln. Neue Module die nicht in bestehende Strukturen eingebunden werden, verursachen später teure Nacharbeiten und inkonsistente UX.

**How to apply:**

Nach jeder neuen Funktion / jedem neuen Modul aktiv in alle relevanten Bereiche schauen:

1. **Einstellungen** — Muss das Feature konfigurierbar sein? → Eintrag in `build_einstellungen()` + `config.json`
2. **LLM / Kira** — Soll Kira das Feature kennen, nutzen oder darüber Auskunft geben können? → System-Prompt, Tool, Kontext
3. **Runtime-Log** — Loggt das Modul seine wichtigsten Events via `elog()`? → Typ registrieren
4. **Benachrichtigungen** — Soll das Feature ntfy-Push oder In-App-Toast auslösen? → `benachrichtigungen.*` Config + SSE
5. **Backup / Export / Config-Reset** — Muss der neue State gesichert / beim Reset berücksichtigt werden?
6. **Dashboard-Karten** — Soll das Feature im Dashboard sichtbar / zählbar sein?
7. **Mail / Kommunikation** — Gibt es einen Mail-Trigger oder eine Mail-Reaktion?
8. **Kunden-Modul** — Betrifft das Feature Kundendaten oder Kundeninteraktionen?
9. **Nachfass / Marketing** — Newsletter, Nachfass-Logik, Automationen betroffen?
10. **Activity-Log** — Soll das Feature im Aktivitätslog erscheinen? (Legacy, nur wenn sinnvoll)

**Ergebnis festhalten:**

- Was sofort integriert wurde → in `feature_registry.json` mit Status `done` + Verweis
- Was sinnvoll aber noch nicht gebaut ist → in `feature_registry.json` mit Status `planned` oder `partial`
- Was offen bleibt → als konkreter Eintrag in `session_handoff.json` → `open_tasks`

Nichts darf "still vergessen" werden. Wenn etwas bewusst zurückgestellt wird, muss es explizit dokumentiert sein.
