# Memory Index – rauMKult® Assistenz für Kai Marienfeld

## Pflicht vor jeder Session
- [AGENT.md](AGENT.md) — Verbindliche Arbeitsregeln, Projektstruktur, kritische technische Regeln
- [session_handoff.json](session_handoff.json) — Letzter Arbeitsstand, offene Punkte, nächster Schritt
- [feature_registry.json](feature_registry.json) — Alle Features mit Status (Schema v2, 21 Einträge)
- [known_issues.json](known_issues.json) — Bekannte offene Probleme (immer prüfen!)

## Grundprinzip
- [feedback_commit_and_memory_update.md](feedback_commit_and_memory_update.md) — PFLICHT: Nach jeder Änderung committen + alle Tracking-Dateien aktualisieren
- [feedback_user_briefs_rule.md](feedback_user_briefs_rule.md) — PFLICHT: Größere Aufträge als Original-Brief in user_briefs.md festhalten
- [feedback_llm_first.md](feedback_llm_first.md) — LLM-First: Alle Features mit KI-Integration, nie offline-only
- [feedback_dashboard_ui_rebuild.md](feedback_dashboard_ui_rebuild.md) — Dashboard UI aus Referenzvorlagen bauen, alte UI vollständig ersetzen
- [feedback_feature_list_rule.md](feedback_feature_list_rule.md) — PFLICHT: feature_registry.json VOR und NACH jeder Session prüfen+aktualisieren
- [feedback_activity_log_rule.md](feedback_activity_log_rule.md) — Neue Module/Funktionen immer mit activity_log integrieren
- [feedback_integration_check.md](feedback_integration_check.md) — PFLICHT: Nach jedem neuen Feature App-weit auf Integrationspunkte prüfen (Einstellungen/LLM/Log/Notifs/Backup/Dashboard/Mail/Kunden/Marketing) + in feature_registry+open_tasks eintragen

## Navigation & Architektur
- [server_map.md](server_map.md) — Alle Funktionen in server.py mit Zeilennummern (7200 Zeilen!)
- [architecture_decisions.md](architecture_decisions.md) — Warum wurde was wie gebaut (ADR-001..007)
- [KIRA_KOMPLETT_UEBERSICHT.md](KIRA_KOMPLETT_UEBERSICHT.md) — Vollständige Systemübersicht inkl. Runtime-Log (Stand 27.03.2026)

## Partner & Universalversion
- [project_partner_feedback_system.md](project_partner_feedback_system.md) — Beta-Testerin Leni, partner_view.html live auf kaimarienfeld.github.io/kira-partner
- [project_leni_mail_pending.md](project_leni_mail_pending.md) — Willkommens- und Passwort-Mail AUSSTEHEND — erst nach nächstem KIRA-App-Commit senden!
- [feedback_partner_view_automation.md](feedback_partner_view_automation.md) — PFLICHT: Nach jedem Commit generate_partner_view.py + Leni-Feedback-Prozess

## Nutzer & Projekt
- [user_profile.md](user_profile.md) — Kai Marienfeld, rauMKult® Inhaber, Betonkosmetik-Spezialist
- [project_kontext.md](project_kontext.md) — Geschäftskontext, Leistungen, Preisstruktur, Mail-Archiv-Pfad

## Dashboard & UI
- [feedback_kommunikation_ui.md](feedback_kommunikation_ui.md) — Visuelle Regeln: Karten-Design, Buttons Karte vs. Kontextpanel, Typografie Kommunikation-Panel

## Kommunikation & Stil
- [feedback_gmail.md](feedback_gmail.md) — Gmail-Tool nie verwenden, stattdessen Mail-Archiv-Ordner
- [feedback_kommunikation.md](feedback_kommunikation.md) — Kommunikationsregeln und verbotene Formulierungen
- [knowledge/stil_guide.md](knowledge/stil_guide.md) — Kais Schreibstil, Phrasen, Dos & Don'ts (aus 522 gesendeten Mails gelernt)

## Preise & Kalkulation
- [knowledge/preisliste_referenz.md](knowledge/preisliste_referenz.md) — Preistabellen, Kalkulationsregeln, Reisekosten

## Datenbanken (SQLite)
- `knowledge/tasks.db` — Aufgaben, Wissen, Geschäft, Kira-Konversationen
- `knowledge/runtime_events.db` — Runtime-Event-Store (NEU session-h)
- `knowledge/mail_index.db` — Index aller 12.642 Mails (nicht anfassen — groß!)
- `knowledge/kunden.db` — 7.321 Kundeninteraktionen + Kundenstamm
- `knowledge/sent_mails.db` — 525 gesendete Mails (Stil-Lernbasis)
- `knowledge/newsletter.db` — 4.646 Newsletter (auto-klassifiziert)
- `knowledge/rechnungen_detail.db` — Rechnungsdetails via PDF-Extraktion

## Fortschritt & Logs
- [user_briefs.md](user_briefs.md) — Original-Aufträge von Kai (append-only, warum wurde was gebaut?)
- [change_log.jsonl](change_log.jsonl) — Append-only Code-Änderungs-Log (feingranular, nie überschreiben)

## Cowork-Ausgaben (automatisch generiert)
- `cowork/AKTUELL.md` — Immer aktueller Tagesbericht (wird überschrieben)
- `cowork/HEUTE_YYYY-MM-DD.md` — Archiv-Tagesberichte

## Scripts
- `scripts/server.py` — Dashboard-Server (localhost:8765, ~7200 Zeilen → server_map.md!)
- `scripts/kira_llm.py` — Kira LLM-Modul (Multi-LLM, 9 Tools, runtime_log)
- `scripts/runtime_log.py` — Runtime-Event-Store (NEU session-h)
- `scripts/activity_log.py` — Einfaches Aktivitätslog (Legacy, nicht ändern!)
- `scripts/mail_monitor.py` — IMAP-Polling Echtzeit-Monitor
- `scripts/daily_check.py` — Täglicher Mail-Scan + Bericht
- `scripts/secrets.json` — API Keys (NIEMALS committen!)

## Archiv
- `_archiv/` — Veraltete/superseded Dateien (feature_list.md, alte Prompts)
