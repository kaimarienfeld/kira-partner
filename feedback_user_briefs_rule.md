---
name: Regel – Größere Aufträge als User Brief festhalten
description: Bei jedem größeren Auftrag von Kai den Original-Wortlaut in user_briefs.md festhalten, bevor mit der Arbeit begonnen wird
type: feedback
---

Bei jedem größeren Auftrag den Original-Wortlaut (oder eine sinngemäß treue Rekonstruktion) in `user_briefs.md` festhalten — als append-only Eintrag, bevor oder direkt nachdem die Arbeit beginnt.

**Why:** Kai hat explizit angeordnet, Aufträge mitzuloggen (2026-03-27). Ohne Original-Brief ist in späteren Sessions nicht mehr nachvollziehbar, warum etwas so gebaut wurde — nur das Ergebnis, nicht die Anforderung.

**How to apply:**
- Format: `## YYYY-MM-DD | session-X | Kurztitel`
- Inhalt: Kais Wortlaut oder sinngemäß treue Rekonstruktion, bei Rekonstruktion als solche markieren
- Pflichtfelder: Datum, Session-ID, Auftrag-Text, Ergebnis (was wurde umgesetzt, was offen)
- Schwelle: Alles was mehr als eine kleine Einzelkorrektur ist — neue Features, UI-Rebuilds, System-Neubauten, Architektur-Entscheidungen
- Nicht nötig für: "ändere Zeile X", "füge einen Button hinzu", kleine Bugfixes
- Datei: `user_briefs.md` — nie überschreiben, immer unten anfügen

**Zusammen mit:** Nach dem Brief in `session_handoff.json` (next_step), `feature_registry.json` (neues Feature → planned) und `known_issues.json` (falls bekannte Einschränkungen) aktualisieren.
