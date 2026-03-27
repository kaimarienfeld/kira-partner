---
name: LLM-First Prinzip
description: Alle Dashboard-Features müssen mit vollständiger LLM-Integration gebaut werden, nie offline-only
type: feedback
---

Alle Änderungen und zusätzliche Funktionen im Kira Dashboard IMMER in Verbindung mit LLM bauen, um beste Ergebnisse zu erzielen.

**Why:** Kai will keinen "offline DB-basierten 0815-Assistenten", sondern ein vollständig integriertes LLM, das wie ein echter Assistent arbeitet — wie eine Claude-Konversation, aber mit allen Geschäftsdaten als Kontext. Daten die verarbeitet werden dürfen nie verworfen werden; Datenbanken/Wissenspeicher immer weiter ausbauen und protokollieren.

**How to apply:**
- Kira Chat (kira_llm.py) ist die zentrale Schnittstelle — nicht statische HTML-Ausgaben
- Jede neue Funktion prüfen: "Kann das LLM das besser/interaktiver machen?"
- Konversationen sinnvoll speichern (kira_konversationen Tabelle)
- Bei Statusänderungen (bezahlt, abgelehnt etc.) immer in wissen_regeln + geschaeft_statistik speichern
- Internet-Recherche optional zuschaltbar (DuckDuckGo via web_recherche Tool)
- Geschäftsdaten bleiben vertraulich (geschaeftsdaten_teilen Schalter)
- API Key separat in secrets.json (nicht in config.json, nicht committen)
