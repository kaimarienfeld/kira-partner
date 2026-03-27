# Memory Index – rauMKult® Assistenz für Kai Marienfeld

## Pflicht vor jeder Session (AGENT.md lesen!)
- [AGENT.md](AGENT.md) — Verbindliche Arbeitsregeln, Projektstruktur, kritische technische Regeln
- [session_handoff.json](session_handoff.json) — Letzter Arbeitsstand, offene Punkte, nächster Schritt
- [feature_registry.json](feature_registry.json) — Alle Features mit Status (Schema v2, 20+ Einträge)

## Grundprinzip
- [feedback_commit_and_memory_update.md](feedback_commit_and_memory_update.md) — PFLICHT: Nach jeder Änderung committen + AGENT.md/session_handoff/feature_registry aktualisieren
- [feedback_llm_first.md](feedback_llm_first.md) — LLM-First: Alle Features mit KI-Integration, nie offline-only
- [feedback_dashboard_ui_rebuild.md](feedback_dashboard_ui_rebuild.md) — Dashboard UI aus Referenzvorlagen bauen, alte UI vollständig ersetzen
- [feedback_feature_list_rule.md](feedback_feature_list_rule.md) — PFLICHT: feature_registry.json VOR und NACH jeder Session prüfen+aktualisieren
- [feedback_activity_log_rule.md](feedback_activity_log_rule.md) — Neue Module/Funktionen immer mit activity_log integrieren

## Nutzer & Projekt
- [user_profile.md](user_profile.md) — Kai Marienfeld, rauMKult® Inhaber, Betonkosmetik-Spezialist
- [project_kontext.md](project_kontext.md) — Geschäftskontext, Leistungen, Preisstruktur, Mail-Archiv-Pfad
- [KIRA_KOMPLETT_UEBERSICHT.md](KIRA_KOMPLETT_UEBERSICHT.md) — Vollständige Systemübersicht: Architektur, Tools, Verbesserungsideen (Stand 25.03.2026)

## Dashboard & UI
- [feedback_kommunikation_ui.md](feedback_kommunikation_ui.md) — Visuelle Regeln: Karten-Design, Buttons Karte vs. Kontextpanel, Typografie Kommunikation-Panel

## Kommunikation & Stil
- [feedback_gmail.md](feedback_gmail.md) — Gmail-Tool nie verwenden, stattdessen Mail-Archiv-Ordner
- [feedback_kommunikation.md](feedback_kommunikation.md) — Kommunikationsregeln und verbotene Formulierungen
- [knowledge/stil_guide.md](knowledge/stil_guide.md) — Kais Schreibstil, Phrasen, Dos & Don'ts (aus 522 gesendeten Mails gelernt)

## Preise & Kalkulation
- [knowledge/preisliste_referenz.md](knowledge/preisliste_referenz.md) — Preistabellen, Kalkulationsregeln, Reisekosten

## Datenbanken (SQLite, alle Postfächer kanalübergreifend)
- `knowledge/mail_index.db` — Index aller 12.642 Mails (Metadaten)
- `knowledge/kunden.db` — 7.321 Kundeninteraktionen aus ALLEN Postfächern + Kundenstamm
- `knowledge/sent_mails.db` — 525 gesendete Mails mit bereinigtem Text (Stil-Lernbasis)
- `knowledge/newsletter.db` — 4.646 Newsletter, auto-klassifiziert (relevant/irrelevant/unklar)
- `knowledge/rechnungen_detail.db` — Rechnungsdetails (Positionen, Skonto, Zahlungsziel) via PDF-Extraktion
- `knowledge/db_status.json` — Letzter Build-Zeitpunkt

## Fortschritt & Logs
- [progress_log.json](progress_log.json) — Verlauf abgeschlossener Arbeitseinheiten (grob, Meilensteine)
- [change_log.jsonl](change_log.jsonl) — Append-only Entwicklungs-Log (feingranular, jede Änderung, nie überschreiben)

## Cowork-Ausgaben (automatisch generiert)
- `cowork/AKTUELL.md` — Immer aktueller Tagesbericht (wird überschrieben)
- `cowork/HEUTE_YYYY-MM-DD.md` — Archiv-Tagesberichte

## Scripts
- `scripts/build_databases.py` — Vollständiger DB-Rebuild (einmalig / bei Bedarf)
- `scripts/daily_check.py` — Täglicher Check: neue Mails, Newsletter, Bericht → AKTUELL.md
- `scripts/daily_check.bat` — Wrapper für Windows Task Scheduler
- `scripts/setup_task_scheduler.bat` — **EINMALIG als Admin ausführen** für Automatisierung
- `scripts/scan_rechnungen_detail.py` — PDF-Extraktion für Rechnungsdetails
- `scripts/kira_llm.py` — Kira LLM-Modul (Claude API, Tools, Chat)
- `scripts/server.py` — Dashboard-Server (localhost:8765) mit Kira Chat-UI
- `scripts/secrets.json` — API Keys (NICHT committen!)

## Archiv
- `_archiv/` — Veraltete/superseded Dateien (feature_list.md, alte Prompts, Reparatur-Anweisung)
