# Einstellungen – Vollständige Checkliste & Erweiterungsvorschläge
_Stand: 2026-03-27 · session-s · Analyse-Basis: config.json, server.py (~8000 Z.), kira_llm.py, mail_monitor.py, llm_classifier.py_

---

## LEGENDE

- ✅ Fertig & verbunden
- 🔧 UI vorhanden, Backend-Verbindung unvollständig
- ❌ Fehlt komplett (noch keine UI)
- 💡 Erweiterungsvorschlag (neu, noch nicht geplant)
- 🔗 Kira-LLM-Verbindung benötigt
- 📋 In Planung (laut Architektur, noch nicht implementiert)

---

## 1. DESIGN

| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Farbschema (Hell/Dunkel) | `cfg-theme` / localStorage | applyTheme() verbunden |
| ✅ | Akzentfarbe | `cfg-accent` / localStorage | applyAccent() verbunden |
| ✅ | Schriftgröße | `cfg-fontsize` / localStorage | applyFontSize() verbunden |
| ✅ | Dichte (compact/comfortable) | `cfg-density` / localStorage | applyDensity() verbunden |
| ✅ | Firmenname | `cfg-company-name` / localStorage | applyCompanyName() verbunden |
| ✅ | Logo (URL oder Emoji) | `cfg-logo` / localStorage | applyLogo() verbunden |
| ✅ | Kartenradius | `cfg-card-radius` / localStorage | applyCardRadius() verbunden |
| ✅ | Schatten | `cfg-shadow` / localStorage | applyShadow() verbunden |
| ✅ | Animationen reduzieren | `cfg-reduce-motion` / localStorage | applyReduceMotion() verbunden |
| ✅ | Hoher Kontrast | `cfg-high-contrast` / localStorage | applyHighContrast() verbunden |
| ✅ | Sidebar-Breite (px) | `cfg-sidebar-width` / localStorage | applySidebarWidth() + restoreDesign() verbunden, session-s |
| ✅ | Schriftfamilie | `cfg-font-family` / localStorage | applyFontFamily() + CSS [data-font-family] verbunden, session-s |
| ✅ | Tabellen-Zeilenhöhe | `cfg-row-height` / localStorage | applyRowHeight() + CSS [data-row-height] verbunden, session-s |
| ✅ | Toast-Position | `cfg-toast-pos` / localStorage | applyToastPos() + CSS [data-toast-pos] verbunden, session-s |
| ✅ | Tabellen Zebrastreifen | `cfg-table-zebra` / localStorage | applyTableZebra() + CSS [data-table-zebra] verbunden, session-s |

---

## 2. BENACHRICHTIGUNGEN

### 2a. Push (ntfy.sh)
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Push aktiv | `cfg-ntfy-aktiv` / `ntfy.aktiv` | saveSettings verbunden |
| ✅ | Kanal (Topic) | `cfg-ntfy-topic` / `ntfy.topic_name` | saveSettings verbunden |
| ✅ | Server-URL | `cfg-ntfy-server` / `ntfy.server` | saveSettings verbunden |
| 🔧 | Test-Push Button | `testPush()` | Funktion vorhanden, ntfy-Server muss erreichbar sein |
| 💡 | Notification-Priorität | `ntfy.prioritaet` | low/default/high/urgent |
| 💡 | Welche Events → Push | `ntfy.events[]` | Mail / Aufgabe fällig / Fehler / Daily-Check |
| 💡 | Push-Stille-Zeiten | `ntfy.stille_von`, `ntfy.stille_bis` | z.B. 22:00–07:00 kein Push |

### 2b. E-Mail-Benachrichtigungen
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ❌ | E-Mail-Benachrichtigung aktiv | `cfg-email-aktiv` / `email_notification.aktiv` | In config.json vorhanden, **keine UI** |
| ❌ | SMTP-Server | `cfg-smtp-server` / `email_notification.smtp_server` | **keine UI** |
| ❌ | SMTP-Port | `cfg-smtp-port` / `email_notification.smtp_port` | **keine UI** |
| ❌ | Absender-E-Mail | `cfg-smtp-from` / `email_notification.absender_email` | **keine UI** |
| ❌ | Absender-Passwort | `cfg-smtp-pw` / `email_notification.absender_passwort` | Sensitiv → secrets.json |
| ❌ | Empfänger-E-Mail | `cfg-smtp-to` / `email_notification.empfaenger_email` | **keine UI** |
| ❌ | Test-E-Mail senden | Button | Backend-Funktion noch nicht vorhanden |
| 💡 | E-Mail-Templates | `email_notification.templates` | Betreff-Vorlagen für Benachrichtigungen |

---

## 3. AUFGABENLOGIK

| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Erinnerungs-Vorlauf (Stunden) | `cfg-erinnerung-h` / `aufgaben.erinnerung_intervall_stunden` | saveSettings verbunden |
| ✅ | Unbeantwortete Mails (Tage) | `cfg-unanswered-days` / `aufgaben.unanswered_check_days` | saveSettings verbunden |
| ✅ | Port | `cfg-server-port` / `server.port` | saveSettings verbunden |
| ✅ | Browser auto-öffnen | `cfg-auto-browser` / `server.auto_open_browser` | saveSettings verbunden |
| 💡 | Aufgaben-Standardpriorität | `aufgaben.default_prioritaet` | normal/hoch/kritisch bei Neu-Erstellung |
| 💡 | Aufgaben-Standarddeadline | `aufgaben.default_deadline_tage` | X Tage nach Erstellung |
| 💡 | Automatisch erledigt archivieren | `aufgaben.auto_archiv_tage` | Erledigte nach X Tagen verstecken |
| 💡 | Aufgaben aus Kira-Chat | `aufgaben.kira_erstellt_aufgaben` 🔗 | Soll Kira Aufgaben anlegen können? |
| 💡 | Deadline-Warnung bei Fälligkeit | `aufgaben.warnung_bei_faelligkeit` | Push / Toast / beides |

---

## 4. NACHFASS-INTERVALLE

| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Stufe 1 (Tage) | `cfg-nf-1` / `nachfass.intervall_1_tage` | saveSettings verbunden |
| ✅ | Stufe 2 (Tage) | `cfg-nf-2` / `nachfass.intervall_2_tage` | saveSettings verbunden |
| ✅ | Stufe 3 (Tage) | `cfg-nf-3` / `nachfass.intervall_3_tage` | saveSettings verbunden |
| 💡 | Nachfass-Typ | `nachfass.typ` | Manuell / Push-Erinnerung / Auto-Mail |
| 💡 | Nachfass für Rechnungen | `nachfass.rechnung_tage` | Separate Intervalle für offene Rechnungen |
| 💡 | Nachfass deaktivieren für | `nachfass.ausnahme_kategorien[]` | Bestimmte Kontakttypen ausschließen |

---

## 5. DASHBOARD

| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Max. Protokoll-Einträge | `cfg-proto-max` / `protokoll.max_eintraege` | saveSettings verbunden |
| ✅ | Protokoll aufbewahren (Tage) | `cfg-proto-tage` / `protokoll.tage` | saveSettings verbunden |
| ✅ | Internet-Kontext | `cfg-llm-internet` / `llm.internet_recherche` | saveSettings verbunden |
| ✅ | Geschäfts-Kontext | `cfg-llm-geschaeft` / `llm.geschaeftsdaten_teilen` | saveSettings verbunden |
| ✅ | Konversations-Kontext | `cfg-llm-konv` / `llm.konversationen_speichern` | saveSettings verbunden |
| ❌ | Max. Kontext-Items | `cfg-llm-max-items` / `llm.max_kontext_items` | In config.json (50), **keine UI** |
| ❌ | Auto-Wissen extrahieren | `cfg-llm-auto-wissen` / `llm.auto_wissen_extrahieren` | In config.json, **keine UI** |
| 💡 | Dashboard-Kacheln konfigurieren | `dashboard.kacheln[]` | Welche Statistiken auf Start-Seite |
| 💡 | Refresh-Intervall Dashboard | `dashboard.refresh_intervall` | Auto-Reload alle X Minuten |
| 💡 | Aufgaben-Ansicht Standard | `dashboard.aufgaben_view` | Liste / Kanban / Kalender |
| 💡 | KPIs auf Dashboard | `dashboard.kpis[]` | Welche Metriken angezeigt werden |

---

## 6. KIRA / LLM / PROVIDER

### 6a. Kira-Assistent (vollständig)
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Launcher-Stil (A/B/C) | `cfg-kira-variant` / `kira.launcher_variant` | switchKiraVariant() verbunden |
| ✅ | Größe (px) | `cfg-kira-size` / `kira.size` | saveSettings verbunden |
| ✅ | Proximity-Radius | `cfg-kira-prox` / `kira.prox_radius` | saveSettings verbunden |
| ✅ | Bounce-Distanz | `cfg-kira-bounce` / `kira.bounce_dist` | saveSettings verbunden |
| ✅ | Bored-Modus | `cfg-kira-idle` / `kira.idle_mode` | saveSettings verbunden |
| ✅ | Bored-Wartezeit | `cfg-kira-idle-delay` / `kira.idle_delay` | saveSettings verbunden |
| 💡 | Kira-Position | `kira.position` | Unten rechts / links / oben |
| 💡 | Kira-Name anpassen | `kira.name` 🔗 | Eigener Name statt "Kira" (auch in System-Prompt) |
| 💡 | Kira-Persönlichkeit | `kira.persoenlichkeit` 🔗 | Professionell / Freundlich / Direkt → System-Prompt-Variante |
| 💡 | Kira-Sprache | `kira.sprache` 🔗 | Deutsch / Englisch / gemischt → System-Prompt |
| 💡 | Kira Quick-Actions editieren | `kira.quick_actions[]` | Welche 7 Items im Quick Panel |
| 💡 | Kira im Hintergrund aktiv | `kira.background_hints` | Push wenn Kira Idee hat |

### 6b. LLM-Verhalten
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ❌ | Max. Kontext-Items (Zeilen) | `cfg-llm-max-items` / `llm.max_kontext_items` | Kira liest bis 50 Items aus DB |
| ❌ | Auto-Wissen extrahieren | `cfg-llm-auto-wissen` / `llm.auto_wissen_extrahieren` | Automatisch Wissensregeln aus Kira-Chats |
| 💡 | System-Prompt anzeigen/editieren | `kira.system_prompt_custom` 🔗 | Eigenen Prompt-Anteil hinzufügen |
| 💡 | Antwort-Länge | `llm.antwort_laenge` 🔗 | Kurz / Normal / Ausführlich |
| 💡 | LLM-Temperatur | `llm.temperatur` | 0.0–1.0 (Kreativität vs. Präzision) |
| 💡 | Kira merkt sich Präferenzen | `kira.lernmodus` 🔗 | Aus Feedback Wissensregeln erstellen |
| 💡 | Kira proaktive Vorschläge | `kira.proaktiv` 🔗 | Kira schlägt Aktionen vor (z.B. Nachfass) |
| 💡 | Kira als Gesprächspartner | `kira.chitchat_erlaubt` | On/Off für Smalltalk |
| 💡 | Kira-Context: Offene Aufgaben | `kira.kontext_aufgaben` 🔗 | Immer / Nur wenn relevant / Nie |
| 💡 | Kira-Context: Aktuelle Mails | `kira.kontext_mails` 🔗 | Immer / Nur wenn relevant / Nie |
| 💡 | Kira-Context: Rechnungen | `kira.kontext_rechnungen` 🔗 | Immer / Nur wenn relevant / Nie |

### 6c. Provider-Verwaltung
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Provider-Liste | `provider-list` / `llm.providers[]` | Karten mit Feldern |
| ✅ | Provider-Typ | `ptype-{id}` | anthropic/openai/ollama/openrouter/custom |
| ✅ | Provider-Modell | `pmodel-{id}` | Dropdown je nach Typ |
| ✅ | Provider-Base-URL | `purl-{id}` | Für custom/ollama |
| ✅ | Provider aktiv/inaktiv | paktiv-{id} | Toggle |
| ✅ | Provider hinzufügen/löschen | addProvider() | Verbunden |
| ✅ | API-Key speichern | saveProviderKey() | Speichert in secrets.json |
| 💡 | Provider Verbindungstest | Button pro Provider | Test-API-Call mit Ergebnis-Anzeige |
| 💡 | Provider-Timeout | `llm.provider_timeout` | Sekunden bis Timeout (aktuell hardcoded) |
| 💡 | Fallback-Provider | `llm.fallback_provider_id` | Bei Fehler auf Backup-Provider |
| 💡 | Provider-Kosten-Tracking | `llm.kosten_tracking` | Token-Verbrauch anzeigen |

---

## 7. MAIL & KONTEN

| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ❌ | Mail-Monitor aktiv | `cfg-mail-monitor-aktiv` / `mail_monitor.aktiv` | Wird in server.py gelesen, **keine UI** |
| ❌ | Polling-Intervall (Sekunden) | `cfg-mail-intervall` / `mail_monitor.intervall_sekunden` | Aktuell 300 Sek., **keine UI** |
| 📋 | IMAP-Server | `mail.imap_server` | Geplant |
| 📋 | IMAP-Port | `mail.imap_port` | Geplant |
| 📋 | IMAP-Konto / User | `mail.user` | In secrets.json |
| 📋 | IMAP-Passwort | `mail.passwort` | In secrets.json |
| 📋 | Überwachter Ordner | `mail.ordner` | z.B. INBOX |
| 📋 | Unterordner ebenfalls | `mail.unterordner` | on/off |
| 💡 | Mail-Filter (Absender ignorieren) | `mail.ignore_sender[]` | Newsletter, Spam ausschließen |
| 💡 | Mail als gelesen markieren | `mail.mark_as_read` | Nach Verarbeitung |
| 💡 | Mail-Archiv-Ordner | `mail.archiv_ordner` | Nach Verarbeitung verschieben |
| 💡 | Maximale Mails pro Durchlauf | `mail.max_per_run` | Throttle für große Postfächer |
| 💡 | Mehrere Konten | `mail.konten[]` | Privat + Geschäft |

### 7a. Mail-Klassifizierung
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| 📋 | Auto-Klassifizierung aktiv | `mail.klassifizierung_aktiv` | Geplant |
| 💡 | Klassifizierungs-Kategorien | `mail.kategorien[]` | Angebot / Anfrage / Rechnung etc. editierbar |
| 💡 | Mindest-Konfidenz | `mail.min_konfidenz` | Unter X% → Manuell |
| 💡 | Aufgaben-Erstellung bei Kategorie | `mail.aufgabe_bei[]` | Nur für bestimmte Kategorien |
| 💡 | LLM für Klassifizierung | `mail.klassifizierung_provider` | Eigener Provider oder Standard |

---

## 8. INTEGRATIONEN

| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| 📋 | Google Calendar | – | Geplant (OAuth) |
| 📋 | CRM-Export | – | Geplant |
| 📋 | Webhook | – | Geplant |
| 📋 | Buchhaltungs-Export (DATEV/CSV) | – | Geplant |
| 💡 | Lexoffice / sevDesk | `integrationen.lexoffice` | Rechnungen aus Kira heraus anlegen |
| 💡 | Zapier / Make (Webhook-Empfang) | `integrationen.webhook_empfang` | Trigger von extern |
| 💡 | Slack / Teams | `integrationen.slack` | Benachrichtigungen senden |
| 💡 | Notion / Obsidian Export | `integrationen.notes_export` | Wissensregeln exportieren |

---

## 9. AUTOMATIONEN

| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| 📋 | Regelbasierte Aufgaben | – | Geplant |
| 📋 | Auto-Nachfass-Mails | – | Geplant |
| 📋 | Wöchentliche Berichte | – | Geplant |
| 💡 | Daily-Check-Zeitplan | `automationen.daily_check_uhrzeit` | Wann läuft der Check? |
| 💡 | Wochenbericht an E-Mail | `automationen.wochenbericht_email` | Freitags Zusammenfassung |
| 💡 | Kira Morgen-Briefing | `automationen.morgen_briefing` 🔗 | Push mit Tages-Zusammenfassung |
| 💡 | Backup-Automatisierung | `automationen.backup_intervall` | DB täglich sichern |
| 💡 | Kira-Erinnerung bei Inaktivität | `automationen.inaktivitaet_push` | Nach X Tagen Push |

---

## 10. PROTOKOLL & LOGS

### 10a. Runtime-Log (vollständig)
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Aktiv/Inaktiv | `cfg-rl-aktiv` | saveSettings verbunden |
| ✅ | UI-Events | `cfg-rl-ui` | saveSettings verbunden |
| ✅ | Kira-Interaktionen | `cfg-rl-kira` | saveSettings verbunden |
| ✅ | LLM-Aufrufe | `cfg-rl-llm` | saveSettings verbunden |
| ✅ | Hintergrund-Jobs | `cfg-rl-bg` | saveSettings verbunden |
| ✅ | Einstellungen-Änderungen | `cfg-rl-settings` | saveSettings verbunden |
| ✅ | Fehler immer | `cfg-rl-fehler` | saveSettings verbunden |
| ✅ | Vollkontext speichern | `cfg-rl-vollkontext` | saveSettings verbunden |
| ✅ | Kira liest Log | `cfg-rl-kira-lesen` | saveSettings verbunden |
| ✅ | DB leeren | clearRtLog() | Button verbunden |
| ✅ | CSV Export | exportRtLog() | Button verbunden |
| ✅ | Statistiken | refreshRtLogStats() | Button verbunden |
| ✅ | Log-Viewer mit Filtern | runtimelog-entries | API verbunden |
| 💡 | Max. Log-Einträge | `runtime_log.max_eintraege` | Aktuell 5000 hardcoded |
| 💡 | Log-Aufbewahrung (Tage) | `runtime_log.aufbewahrung_tage` | Automatisch löschen |
| 💡 | Log-Level | `runtime_log.level` | DEBUG / INFO / WARN / ERROR |

### 10b. Änderungsverlauf
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Viewer mit 4 Filtern | changelog-entries | Modul/Resultat/Feature/Aktion |
| ✅ | Statistiken (Einträge/Datum/Module) | — | Angezeigt |
| 💡 | Export als JSON | — | Aktuell nur Ansicht |
| 💡 | Max. Export-Einträge | `changelog.export_limit` | Aktuell 9999 hardcoded |

### 10c. Konfigurationsbackup
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | DB-Größe anzeigen | — | Statische Info |
| ✅ | Runtime-Log-DB-Größe | — | Statische Info |
| ❌ | Config exportieren | — | Button vorhanden, **Funktion fehlt** (showToast Platzhalter) |
| ❌ | Config importieren | — | Button vorhanden, **Funktion fehlt** (showToast Platzhalter) |
| ❌ | Zurücksetzen | — | Button vorhanden, **Funktion fehlt** (showToast Platzhalter) |
| 💡 | Auto-Backup aktivieren | `backup.aktiv` | Täglich config.json sichern |
| 💡 | Backup-Pfad | `backup.pfad` | Wohin gesichert wird |

---

## KIRA-LLM ZUSAMMENARBEIT – FEHLENDE VERBINDUNGEN

_Diese Punkte betreffen die direkte Kopplung zwischen Einstellungen und Kira's Verhalten_

| Prio | Funktion | Config-Key | Was passiert |
|------|---------|-----------|-------------|
| 🔴 Hoch | Kira-Name | `kira.name` | Kira nennt sich dann anders im Chat + System-Prompt |
| 🔴 Hoch | Kira-Persönlichkeit | `kira.persoenlichkeit` | Wählt System-Prompt-Variante in kira_llm.py |
| 🔴 Hoch | Kontext-Steuerung | `kira.kontext_*` | Was Kira immer / situativ / nie im Kontext hat |
| 🟡 Mittel | System-Prompt-Ergänzung | `kira.system_prompt_custom` | User-definierter Zusatz-Prompt (Freitext) |
| 🟡 Mittel | Kira proaktive Vorschläge | `kira.proaktiv` | Kira meldet sich bei offenen Aufgaben |
| 🟡 Mittel | Auto-Wissen | `llm.auto_wissen_extrahieren` | Nach Kira-Gesprächen Wissensregeln vorschlagen |
| 🟡 Mittel | Antwort-Länge | `llm.antwort_laenge` | Beeinflusst Prompt-Instruktion |
| 🟢 Niedrig | Kira-Sprache | `kira.sprache` | Deutsch / Englisch / gemischt |
| 🟢 Niedrig | LLM-Temperatur | `llm.temperatur` | Kreativität vs. Faktentreue |
| 🟢 Niedrig | Kira-Chitchat | `kira.chitchat_erlaubt` | Darf Kira Smalltalk machen? |

---

## SESSION-s FIXES (2026-03-27)

### Visuelle Korrekturen (Hell/Dunkel-Konflikt behoben)
| Status | Fix | Details |
|--------|-----|---------|
| ✅ | Globale Form-Element-Theming-Regel | `input,select,textarea{background:var(--bg-raised);color:var(--text);}` — alle Eingaben reagieren auf Theme |
| ✅ | Provider-Karten: Hardcoded `#0b0b0b` / `#111` → CSS-Variablen | API-Key, Base-URL, Modell-Select, Card-Hintergrund |
| ✅ | Log-Viewer: Hardcoded `#080808` → `var(--bg)` | Runtime-Log + Änderungsverlauf Scroll-Boxen |
| ✅ | Modal-Inputs: Hardcoded `#0b0b0b` → `var(--bg-raised)` | loeschModal, spaeterModal, editRegelModal, Korrespondenz-Alias |
| ✅ | Dynamische Form-Felder: Hardcoded `#0b0b0b` → `var(--bg-raised)` | Kira-Interakt-Modal (JS-generiert) |
| ✅ | Sidebar Dunkel-Modus | `[data-theme="dark"] .sidebar{background:#101012}` + alle Text/Border-Farben auf CSS-Variablen |

### 3-Schritt Kritisch-Bestätigung (showKritischModal)
| Status | Funktion | Details |
|--------|---------|---------|
| ✅ | `showKritischModal(title, msg, word, fn)` | Modal mit Bestätigungswort-Eingabe. Button enabled erst wenn exaktes Wort getippt. |
| ✅ | `clearRtLog()` → kritisch | Bestätigungswort: LEEREN |
| ✅ | `deleteProvider()` → kritisch | Bestätigungswort: ENTFERNEN |
| ✅ | `wissenAction('loeschen')` → kritisch | Bestätigungswort: LÖSCHEN |

---

## PRIORISIERTE ARBEITSREIHENFOLGE

### Phase 1 – Lücken schließen (bestehende config.json-Keys ohne UI)
1. ❌ E-Mail-Benachrichtigungen (SMTP) → Sektion Benachrichtigungen erweitern
2. ❌ Mail-Monitor-Intervall → Sektion Mail & Konten
3. ❌ Mail-Monitor aktiv/inaktiv → Sektion Mail & Konten
4. ❌ `llm.max_kontext_items` → Sektion Dashboard/LLM
5. ❌ `llm.auto_wissen_extrahieren` → Sektion LLM
6. ❌ Config-Export/Import echte Implementierung → Sektion Konfiguration

### Phase 2 – Kira-LLM-Verbindungen herstellen
7. 🔗 Kira-Persönlichkeit → kira_llm.py System-Prompt-Varianten
8. 🔗 Kira-Name anpassen → kira_llm.py + System-Prompt
9. 🔗 System-Prompt-Ergänzung (Freitext-Feld)
10. 🔗 Kontext-Steuerung (Aufgaben/Mails/Rechnungen)
11. 🔗 Kira proaktive Vorschläge (Push bei offenen Aufgaben)

### Phase 3 – Mail & Konten vollständig
12. 📋 IMAP-Zugangsdaten (mit Verbindungstest)
13. 💡 Mail-Filter-Regeln
14. 💡 Kategorien-Verwaltung für Klassifizierung
15. 💡 Mehrere Mail-Konten

### Phase 4 – LLM & Provider erweitern
16. 💡 Provider-Verbindungstest
17. 💡 Fallback-Provider konfigurieren
18. 💡 LLM-Temperatur
19. 💡 Antwort-Länge

### Phase 5 – Automationen
20. 💡 Daily-Check-Zeitplan
21. 💡 Morgen-Briefing (Kira Push)
22. 💡 Auto-Backup

### Phase 6 – UX-Verbesserungen
23. 💡 Einstellungen-Suche (Suchfeld filtert Sektionen/Felder)
24. ✅ Toast-Position konfigurierbar — session-s
25. 💡 Dashboard-Kacheln konfigurieren
26. ✅ Schriftfamilie wählen — session-s
27. ✅ Tabellen-Zeilenhöhe + Zebrastreifen — session-s
28. ✅ Sidebar-Breite als Einstellung — session-s

---

## TECHNISCHE NOTIZEN

- **saveSettings()** liest Element-IDs aus dem DOM → neue Felder brauchen neue IDs + Eintrag in saveSettings()
- **config.json** wird per `POST /api/settings` gespeichert → neue Keys müssen im Handler verarbeitet werden
- **secrets.json** für sensible Daten (Passwörter, API-Keys) → eigener Handler `POST /api/secrets`
- **kira_llm.py** muss bei Persönlichkeits-/Name-Änderungen den System-Prompt neu laden → Server-Neustart oder Hot-Reload nötig
- **CSS-Klassen**: `es-*` Prefix für alle neuen Einstellungs-Elemente beibehalten
- **ISS-003**: SyntaxWarnings in server.py → raw-strings wenn Zeilen angefasst werden

---
_Erstellt: session-r · 2026-03-27_
