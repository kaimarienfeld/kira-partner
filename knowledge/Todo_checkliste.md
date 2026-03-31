# Einstellungen – Vollständige Checkliste & Erweiterungsvorschläge
_Stand: 2026-03-29 · session-bb · Analyse-Basis: config.json, server.py (~9250 Z.), kira_llm.py, mail_monitor.py, llm_classifier.py_

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
| ✅ | Logo Datei-Upload | `cfg-logo-file` / localStorage | handleLogoUpload() → FileReader → base64 data URL, max 512KB, session-u |
| ✅ | Tabellen Trennlinien | `cfg-table-lines` / localStorage | applyTableLines() + CSS [data-table-lines], session-u |
| ✅ | Kartenradius | `cfg-card-radius` / localStorage | applyCardRadius() verbunden |
| ✅ | Schatten | `cfg-shadow` / localStorage | applyShadow() verbunden |
| ✅ | Animationen reduzieren | `cfg-reduce-motion` / localStorage | applyReduceMotion() verbunden |
| ✅ | Hoher Kontrast | `cfg-high-contrast` / localStorage | applyHighContrast() verbunden |
| ✅ | Sidebar-Breite (px) | `cfg-sidebar-width` / localStorage | applySidebarWidth() + restoreDesign() verbunden, session-s |
| ✅ | Schriftfamilie | `cfg-font-family` / localStorage | applyFontFamily() + CSS [data-font-family] verbunden, session-s |
| ✅ | Tabellen-Zeilenhöhe | `cfg-row-height` / localStorage | applyRowHeight() + CSS [data-row-height] verbunden, session-s |
| ✅ | Toast-Position | `cfg-toast-pos` / localStorage | applyToastPos() + CSS [data-toast-pos], 6 Optionen (unten/oben × rechts/mitte/links), session-s+u |
| ✅ | Tabellen Zebrastreifen | `cfg-table-zebra` / localStorage | applyTableZebra() + CSS [data-table-zebra] verbunden, session-s |

---

## 2. BENACHRICHTIGUNGEN

### 2a. Push (ntfy.sh)
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Push aktiv | `cfg-ntfy-aktiv` / `ntfy.aktiv` | saveSettings verbunden |
| ✅ | Kanal (Topic) | `cfg-ntfy-topic` / `ntfy.topic_name` | saveSettings verbunden |
| ✅ | Server-URL | `cfg-ntfy-server` / `ntfy.server` | saveSettings verbunden |
| ✅ | ntfy.sh Docs-Link | — | Link zu ntfy.sh + Einrichtungs-Hinweis, session-t |
| ✅ | Arbeitszeiten-Filter aktiv | `cfg-ntfy-arbeitszeit-aktiv` / `ntfy.arbeitszeit_aktiv` | saveSettings verbunden, session-t |
| ✅ | Arbeitszeit von | `cfg-ntfy-az-von` / `ntfy.arbeitszeit_von` | time-Input, session-t |
| ✅ | Arbeitszeit bis | `cfg-ntfy-az-bis` / `ntfy.arbeitszeit_bis` | time-Input, session-t |
| ✅ | Urlaubsmodus | `cfg-ntfy-urlaub` / `ntfy.urlaub_modus` | Toggle + Badge, session-t |
| ✅ | Urlaubsmodus planen (von) | `cfg-urlaub-von` / `ntfy.urlaub_von` | datetime-local, saveSettings(), session-u |
| ✅ | Urlaubsmodus planen (bis) | `cfg-urlaub-bis` / `ntfy.urlaub_bis` | datetime-local, saveSettings(), session-u |
| ✅ | Urlaub-Header-Chip | — | Roter Chip im Header wenn `ntfy.urlaub_modus=true`, session-u |
| ✅ | Test-Push Button | `testPush()` / `POST /api/ntfy/test` | JS-Funktion + Backend-Endpoint (urllib.request, timeout 8s), session-u |
| 💡 | Notification-Priorität | `ntfy.prioritaet` | low/default/high/urgent |
| 💡 | Welche Events → Push | `ntfy.events[]` | Mail / Aufgabe fällig / Fehler / Daily-Check |

### 2b. In-App Benachrichtigungen (neu session-t)
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Mail-Eingang Toast | `cfg-inapp-mail` / `benachrichtigungen.inapp_mail` | saveSettings verbunden |
| ✅ | Kira-Antwort Toast | `cfg-inapp-kira` / `benachrichtigungen.inapp_kira` | saveSettings verbunden |
| ✅ | Aufgaben-Erinnerungen Toast | `cfg-inapp-aufgaben` / `benachrichtigungen.inapp_aufgaben` | saveSettings verbunden |
| ✅ | Hintergrund-Jobs Toast | `cfg-inapp-bg` / `benachrichtigungen.inapp_bg` | default: aus, session-t |
| ✅ | Fehler-Meldungen Toast | `cfg-inapp-fehler` / `benachrichtigungen.inapp_fehler` | default: an, session-t |
| 🔧 | Toast-Auslösung im Backend | — | Einstellungen werden gespeichert; Backend-Auslösung (showToast via SSE) noch nicht verdrahtet |

### 2b. E-Mail-Benachrichtigungen
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | E-Mail-Benachrichtigung aktiv | `cfg-email-aktiv` / `email_notification.aktiv` | Toggle, session-pp |
| ✅ | SMTP-Server | `cfg-smtp-server` / `email_notification.smtp_server` | Text-Input, session-pp |
| ✅ | SMTP-Port | `cfg-smtp-port` / `email_notification.smtp_port` | Number-Input, session-pp |
| ✅ | Absender-E-Mail | `cfg-smtp-from` / `email_notification.absender_email` | Email-Input, session-pp |
| ✅ | Absender-Passwort | `cfg-smtp-pw` / `email_notification.absender_passwort` | Password-Input, session-pp |
| ✅ | Empfänger-E-Mail | `cfg-smtp-to` / `email_notification.empfaenger_email` | Email-Input, session-pp |
| ✅ | Test-E-Mail senden | `POST /api/email-notification/test` | smtplib STARTTLS/SSL, session-pp |
| 💡 | E-Mail-Templates | `email_notification.templates` | Betreff-Vorlagen für Benachrichtigungen |

---

## 3. AUFGABENLOGIK

| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Erinnerungs-Vorlauf (Stunden) | `cfg-erinnerung-h` / `aufgaben.erinnerung_intervall_stunden` | saveSettings verbunden |
| ✅ | Unbeantwortete Mails (Tage) | `cfg-unanswered-days` / `aufgaben.unanswered_check_days` | saveSettings verbunden |
| ✅ | Deadline-Warnung (Tage vorher) | `cfg-deadline-warnung-tage` / `aufgaben.deadline_warnung_tage` | saveSettings verbunden, session-t |
| ✅ | Erinnerungs-Typ | `cfg-erinnerung-typ` / `aufgaben.erinnerung_typ` | push/toast/beide, session-t |
| ✅ | Standard-Priorität | `cfg-default-prioritaet` / `aufgaben.default_prioritaet` | normal/hoch/kritisch, session-t |
| ✅ | Auto-Archiv (Tage) | `cfg-auto-archiv-tage` / `aufgaben.auto_archiv_tage` | 0=nie, session-t |
| 💡 | Aufgaben-Standarddeadline | `aufgaben.default_deadline_tage` | X Tage nach Erstellung |
| 💡 | Aufgaben aus Kira-Chat | `aufgaben.kira_erstellt_aufgaben` 🔗 | Soll Kira Aufgaben anlegen können? |

---

## 4. NACHFASS-INTERVALLE

| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Nachfass aktiv | `cfg-nf-aktiv` / `nachfass.aktiv` | Toggle, session-t |
| ✅ | Benachrichtigung via | `cfg-nf-typ` / `nachfass.benachrichtigung` | push/toast/beide/aufgabe(Kira LLM)/alle, session-t+u |
| ✅ | Kira schreibt Nachfass-Text | `cfg-nf-kira-text` / `nachfass.kira_nachfass_text` | LLM-Vorschlag, session-t |
| ✅ | Stufe 1 (Tage) | `cfg-nf-1` / `nachfass.intervall_1_tage` | saveSettings verbunden |
| ✅ | Stufe 2 (Tage) | `cfg-nf-2` / `nachfass.intervall_2_tage` | saveSettings verbunden |
| ✅ | Stufe 3 (Tage) | `cfg-nf-3` / `nachfass.intervall_3_tage` | saveSettings verbunden |
| ✅ | Rechnungs-Nachfass (Tage) | `cfg-nf-rechnung` / `nachfass.rechnung_tage` | session-t |
| 💡 | Nachfass deaktivieren für | `nachfass.ausnahme_kategorien[]` | Bestimmte Kontakttypen ausschließen |

---

## 5. DASHBOARD

_session-t: Server-Einstellungen hierher verschoben (war: Aufgabenlogik). LLM-Kontext nach §6 verschoben._

| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Max. Protokoll-Einträge | `cfg-proto-max` / `protokoll.max_eintraege` | saveSettings verbunden |
| ✅ | Protokoll aufbewahren (Tage) | `cfg-proto-tage` / `protokoll.tage` | saveSettings verbunden |
| ✅ | Server-Port | `cfg-server-port` / `server.port` | hierher verschoben (war Aufgabenlogik), session-t |
| ✅ | Browser auto-öffnen | `cfg-auto-browser` / `server.auto_open_browser` | hierher verschoben, session-t |
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
| ✅ | Kira-Name anpassen | `kira.name` | Eigener Name statt "Kira" (auch in System-Prompt), session-pp + Bug fix session-qq |
| ✅ | Kira-Persönlichkeit | `kira.persoenlichkeit` | Professionell / Freundlich / Direkt → System-Prompt-Variante, session-pp + Bug fix session-qq |
| 💡 | Kira-Sprache | `kira.sprache` 🔗 | Deutsch / Englisch / gemischt → System-Prompt |
| 💡 | Kira Quick-Actions editieren | `kira.quick_actions[]` | Welche 7 Items im Quick Panel |
| 💡 | Kira im Hintergrund aktiv | `kira.background_hints` | Push wenn Kira Idee hat |

### 6b. LLM-Kontext (neu in §6, session-t verschoben von Dashboard)
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Internet-Kontext | `cfg-llm-internet` / `llm.internet_recherche` | korrekte Key-Namen, session-t |
| ✅ | Geschäfts-Kontext | `cfg-llm-geschaeft` / `llm.geschaeftsdaten_teilen` | session-t |
| ✅ | Konversations-Kontext | `cfg-llm-konv` / `llm.konversationen_speichern` | session-t |

### 6c. Mail-Klassifizierung / Budget-Modell (neu session-t)
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Erklärungs-Tabelle (Haiku vs Sonnet) | — | Info-Tabelle mit Kostenvergleich, session-t |
| ✅ | Auto-Budget Hinweis | — | Anthropic→Haiku, OpenAI→gpt-4o-mini, session-t |
| ✅ | Aktives Klassifizierungs-Modell | `active_budget_model` (Python) | Zeigt aktuell aktives Budget-Modell mit grünem Haken, session-u |
| 💡 | Manuelles Klassifizierungs-Modell | `llm.classifier_model` | Eigenes Modell festlegen statt Auto (nach Rollen-System) |

### 6d. LLM-Verhalten
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Max. Kontext-Items (Zeilen) | `cfg-llm-max-items` / `llm.max_kontext_items` | Number-Input, default 50, session-pp |
| ✅ | Auto-Wissen extrahieren | `cfg-llm-auto-wissen` / `llm.auto_wissen_extrahieren` | Toggle, default an, session-pp |
| ✅ | System-Prompt anzeigen/editieren | `kira.system_prompt_custom` | Freitext-Textarea in Einstellungen, session-pp + Bug fix session-qq |
| 💡 | Antwort-Länge | `llm.antwort_laenge` 🔗 | Kurz / Normal / Ausführlich |
| 💡 | LLM-Temperatur | `llm.temperatur` | 0.0–1.0 (Kreativität vs. Präzision) |
| 💡 | Kira merkt sich Präferenzen | `kira.lernmodus` 🔗 | Aus Feedback Wissensregeln erstellen |
| 💡 | Kira proaktive Vorschläge | `kira.proaktiv` 🔗 | Kira schlägt Aktionen vor (z.B. Nachfass) |
| 💡 | Kira als Gesprächspartner | `kira.chitchat_erlaubt` | On/Off für Smalltalk |
| ✅ | Kira-Context: Offene Aufgaben | `kira.kontext_aufgaben` | Immer / Nur wenn vorhanden / Nie, session-qq |
| ✅ | Kira-Context: Aktuelle Mails | `kira.kontext_mails` | Immer / Nur wenn vorhanden / Nie, session-qq |
| ✅ | Kira-Context: Rechnungen | `kira.kontext_rechnungen` | Immer / Nur wenn offen / Nie, session-qq |

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
_Komplett überarbeitet session-y + session-bb (2026-03-29)_

### 7a. Konto-Übersicht & Verwaltung
| Status | Element | Anmerkung |
|--------|---------|-----------|
| ✅ | Konto-Karten mit Index+Archiv-Stats | Echte Zahlen aus mail_index.db + Archiv-Ordner, session-y |
| ✅ | Verbindungsampel pro Konto (grün/gelb/rot) | Echtzeit via `check_account_health()`, session-bb |
| ✅ | Standard-Konto auswählen | Radio-Button pro Karte, session-y |
| ✅ | Abrufen (pro Konto) | `POST /api/mail/konto/abrufen` — startet sofort, session-y |
| ✅ | Alle abrufen | `POST /api/mail/konto/alle-abrufen`, session-y |
| ✅ | Volltest (IMAP+SMTP+Roundtrip) | `POST /api/mail/konto/volltest` + Polling Status, session-bb |
| ✅ | Verbindung wiederherstellen (Reconnect) | `POST /api/mail/konto/reconnect` — neue OAuth-Token für bestehendes Konto, session-bb |
| ✅ | Konto löschen | `POST /api/mail/konto/loeschen` — entfernt aus raumkult_config.json + config.json, session-pp |
| ✅ | Konto hinzufügen (Mailbird-Wizard) | 6-Schritt-Assistent mit 3-stufiger Provider-Erkennung + OAuth-Browser, session-bb |
| ✅ | IMAP-Ordner Accordion | Ordner laden via `GET /api/mail/konten/ordner`, session-y |

### 7a-2. Konto-Assistent (Mailbird-Stil, session-bb)
| Status | Element | Anmerkung |
|--------|---------|-----------|
| ✅ | Schritt 1: Name + E-Mail | Eingabe + Import-Karte (Zukunft) |
| ✅ | Schritt 2: Provider-Erkennung | 3-stufig: Domain → DNS-MX+Autodiscover → MS OpenID-Probe |
| ✅ | Schritt 3: Provider gefunden | Zeigt Anbieter-Logo/Name, Weiter-Button |
| ✅ | Schritt 4: Expert-Mode | IMAP / Exchange/EWS / POP3 — EWS zeigt Server-Feld dynamisch |
| ✅ | Schritt 5: OAuth-Browser | MSAL acquire_token_interactive() in eigenem Fenster |
| ✅ | Schritt 6: Ergebnis | Erfolg/Fehler, Konto-Karte erscheint |
| ❌ | Google OAuth | Noch nicht verdrahtet (geplant) |
| ❌ | Provider nach OAuth persistieren | Nach Login: erkannter Provider in konto-config speichern |

### 7b. Mail-Monitor
| Status | Element | ID / Schlüssel | Anmerkung |
|--------|---------|---------------|-----------|
| ✅ | Mail-Monitor aktiv Toggle | `cfg-mail-monitor-aktiv` / `mail_monitor.aktiv` | session-y |
| ✅ | Polling-Intervall (Sekunden) | `cfg-mail-intervall` / `mail_monitor.intervall_sekunden` | Spinner, session-y |
| ✅ | Mails vorladen im Postfach | `cfg-mail-vorladen` | Spinner, session-y |
| ✅ | Monitor-Status-Anzeige | Zuletzt + Aktiv/Inaktiv, session-y |

### 7c. Mail-Klassifizierung
| Status | Element | Anmerkung |
|--------|---------|-----------|
| ✅ | Klassifizierung (LLM) Toggle | session-y |
| ✅ | Aufgaben automatisch erstellen Toggle | session-y |
| ✅ | Newsletter ignorieren Toggle | session-y |
| 🐛 | _index_mail() Bug behoben | Newsletter wurden nicht indexiert — jetzt immer indexiert, nur kein Task, session-y |

### 7d. Mail-Archiv (Pflicht-Panel)
| Status | Element | Anmerkung |
|--------|---------|-----------|
| ✅ | Archiv-Ordner Pfad-Eingabe | Vorausgefüllt aus raumkult_config.json, session-y |
| ✅ | Archiv-Pfad prüfen | `GET /api/mail/archiv/pruefen` → "Pfad vorhanden ✓", session-y |
| ✅ | Neue Mails archivieren Toggle | session-y |
| ✅ | Re-Index starten | `POST /api/mail/archiv/reindex`, Fortschrittsanzeige, session-y |
| ✅ | Archiv-Status Anzeige | Mails im Index + Pfad, session-y |

### 7e. Sync-Ordner & KIRA-Zugang
| Status | Element | Anmerkung |
|--------|---------|-----------|
| ✅ | Sync-Ordner Checkboxen pro Konto | INBOX+Gesendete = Pflicht (disabled), weitere optional, session-y |
| 💡 | KIRA LLM-Zugang pro Ordner | Geplant — welche Ordner KIRA aktiv lesen darf |
| 💡 | Mail-Filter (Absender ignorieren) | `mail.ignore_sender[]` |
| 💡 | Maximale Mails pro Durchlauf | Throttle für große Postfächer |

---

## 8. INTEGRATIONEN

| Status | Element | Anmerkung |
|--------|---------|-----------|
| ✅ | WhatsApp Business Cloud API — Webhook GET | Hub-Verifizierung (hub.challenge), session-y |
| ✅ | WhatsApp Business Cloud API — Webhook POST | HMAC-SHA256, Meta entry[].changes[].value.messages[] Parsing, session-y |
| ✅ | WhatsApp Einstellungen UI | Verify Token, App Secret, Phone Number ID in Integrationen-Sektion, session-y |
| ✅ | GET /api/einstellungen | Lädt WhatsApp-Tokens aus secrets.json (ISS-015 fix), session-y |
| 🔧 | WhatsApp Token eingetragen | Kai muss Verify-Token + App-Secret noch in Einstellungen > Integrationen eintragen |
| 📋 | Google Calendar | Geplant (OAuth) |
| 📋 | CRM-Export | Geplant |
| 📋 | Webhook (ausgehend) | Geplant |
| 📋 | Buchhaltungs-Export (DATEV/CSV) | Geplant |
| 💡 | Lexoffice / sevDesk | Rechnungen aus Kira heraus anlegen |
| 💡 | Zapier / Make (Webhook-Empfang) | Trigger von extern |
| 💡 | Slack / Teams | Benachrichtigungen senden |

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
| ✅ | Config exportieren | `GET /api/config/export` | JSON-Download als kira_config.json, session-pp |
| ✅ | Config importieren | `POST /api/config/import` | File-Upload + Backup + Reload, session-pp |
| ✅ | Zurücksetzen | `resetConfig()` / `POST /api/config/reset` | showKritischModal(ZURÜCKSETZEN) + Backup als config.json.bak + factory defaults, session-t |
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

## OFFENE BUGS (Pflicht vor neuen Features!)

| Prio | Bug | ID | Details |
|------|-----|-----|---------|
| 🔴 KRITISCH | Task-Löschen funktioniert nicht | `task-loeschen-bug` | Einzeln + Multi: Kira fragt Grund, nach Bestätigung passiert nichts — Einträge werden nicht gelöscht. Kira arbeitet danach nicht mehr. |

---

## KAIS WUNSCHLISTE (aus only_kais checkliste.md, 2026-03-29)

| Prio | Feature | ID | Status |
|------|---------|-----|--------|
| ✅ Hoch | Stats-Zeile Dashboard: Klick → Tab + Filter | `stats-zeile-filter-klick` | filterKomm() implementiert, KPI-onclick verbunden |
| ✅ Hoch | Wissen-Bibliothek: Zeitstempel erstellt/geändert | `wissen-zeitstempel` | geaendert_am-Spalte + UI-Anzeige, session-pp |
| ✅ Hoch | Eingangsrechnungen auto-scan + Offene-Posten-DB | `eingangsrechnungen-auto-scan` | Tabellen-View mit Filter/Neu/Betrag/Bezahlt, faelligkeit_datum-Spalte, Proaktiv-Scan, session-qq |
| 🟡 Mittel | Kira LLM: Datenbanken + Wissen automatisch pflegen | `kira-llm-datenbanken-autopflege` | 📋 Geplant |
| ✅ Mittel | Konto löschen vollständig verdrahten | `mail-konten-settings-overhaul` | POST /api/mail/konto/loeschen, session-pp |
| 🟡 Mittel | WhatsApp-Token eintragen (Kai-Aktion) | — | ⏳ Wartet auf Kai |

---

## PRIORISIERTE ARBEITSREIHENFOLGE

### Phase 0 – Bugs (sofort)
0. ✅ Task-Löschen reparieren (einzeln + multi) → server.py: sync kira_chat() entfernt, session-pp

### Phase 1 – Lücken schließen (bestehende config.json-Keys ohne UI)
1. ✅ E-Mail-Benachrichtigungen (SMTP) → implementiert session-pp
2. ✅ Mail-Monitor-Intervall → erledigt session-y
3. ✅ Mail-Monitor aktiv/inaktiv → erledigt session-y
4. ✅ `llm.max_kontext_items` → Number-Input, session-pp
5. ✅ `llm.auto_wissen_extrahieren` → Toggle, session-pp
6. ✅ Config-Export/Import → GET /api/config/export + POST /api/config/import, session-pp

### Phase 2 – Kira-LLM-Verbindungen herstellen
7. ✅ Kira-Persönlichkeit → kira_llm.py: direkt/professionell/freundlich, session-pp
8. ✅ Kira-Name anpassen → kira_llm.py + System-Prompt, session-pp
9. ✅ System-Prompt-Ergänzung (Freitext-Feld) → kira.system_prompt_custom, session-pp
10. ✅ Kontext-Steuerung (Aufgaben/Mails/Rechnungen) → kira.kontext_*, 3 Selects im LLM-Kontext-Panel, session-qq + Bug fix: kira_cfg aus config.json["kira"] statt llm-Sub-Dict
11. ✅ Kira proaktive Vorschläge → Automatisierung-Panel hat aktiv-Toggle (cfg-proaktiv-aktiv), run_proaktiver_scan() prüft jetzt kira_proaktiv.aktiv, session-qq

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

---

## SESSION-oo KIRA 2.0 UMBAU (2026-03-31)

### Kira Live-Chip & Activity-Drawer
| Status | Element | Anmerkung |
|--------|---------|-----------|
| ✅ | Kira-Live-Chip im Header | idle/scanning/pending/error-States, session-oo |
| ✅ | 15s Polling via _pollKiraStatus() | fetcht /api/kira/proaktiv/status + /api/mail/approve/pending |
| ✅ | Activity-Drawer (Slide-In rechts 400px) | kiraActivityDrawerOpen/Close(), nicht-modal, session-oo |
| ✅ | Drawer: Freigabe-Queue Sektion | zeigt pending Kira-Mails mit Freigabe/Ablehnen-Buttons |
| ✅ | Drawer: Proaktiv-Status Sektion | zeigt aktive Scan-Infos |
| ✅ | CSS: .kira-live-chip alle 4 States | @keyframes kira-spin, session-oo |
| 📋 | Drawer: Laufende Scans mit Fortschritt | Noch nicht implementiert |
| 📋 | User-Präsenz-Erkennung für Drawer | document.visibilityState / window focus |

### Einstellungen 3-Pane Layout
| Status | Element | Anmerkung |
|--------|---------|-----------|
| ✅ | 3-Pane: Mail & Konten | Mailkonten/Monitor/Klassifizierung/Signaturen/Archiv/Sync, session-oo |
| ✅ | 3-Pane: Kira/LLM/Provider | Assistent/Provider/Kontext/Gedächtnis/Proaktiv/ReAct/Feedback/Sicherheit, session-oo |
| ✅ | 3-Pane: Protokoll & Logs | Runtime/Changelog/Konfiguration, session-oo |
| ✅ | esP2Select() Scroll-Ankerfunktion | scrollt zu Untergruppen-ID, session-oo |
| ✅ | CSS .es-pane2, .es-ct.p2vis | Pane 2 erscheint bei p2vis-Klasse, session-oo |
| ✅ | Neue Einstellungs-Gruppen Kira/LLM | Gedächtnis, Proaktiv, ReAct, Feedback, Sicherheit (IDs für Scroll-Anker), session-oo |
| ✅ | Sicherheit & Audit — neue Sektion | Circuit Breaker Status, Audit-Export, Aktivitäten-Einstellungen, session-oo |

### Kira-Ausgang im Postfach
| Status | Element | Anmerkung |
|--------|---------|-----------|
| ✅ | Ordnergruppe "KIRA-AUSGANG" in Postfach-Sidebar | am Ende der Folder-Tree, session-oo |
| ✅ | 4 Ordner: Entwürfe/Gesendet/Abgelehnt/Abgelaufen | pfSelectKiraFolder(status), session-oo |
| ✅ | pfLoadKiraList() mit Status-Filter | fetcht /api/mail/approve/pending?status=X, session-oo |
| ✅ | pfRenderKiraMailItem() Kira-Mail-Item | Kira-Avatar (🤖), Status-Badge, Betreff, session-oo |
| ✅ | pfShowKiraMail() Mail-Viewer | Header-Banner je Status, Body, Aktions-Buttons, session-oo |
| ✅ | pfKiraMailFreigeben/Bearbeiten/Ablehnen | als window.* exponiert (IIFE-Scope), session-oo |
| ✅ | Bearbeiten-Modal | Textarea + Senden, parentElement-Traversal statt closest(), session-oo |
| ✅ | Badge pf-kira-pending-badge | gelb, zeigt Anzahl Entwürfe, session-oo |
| ✅ | pfKiraAusgangOpen() | öffnet Postfach + navigiert zu Entwürfe (aus Header-Badge), session-oo |
| 📋 | Ribbon-Kira-Gruppe für Kira-Mails | [✅ Freigeben][❌ Ablehnen][✎ Bearbeiten] bei Kira-Mail-Auswahl |

### API-Erweiterungen (session-oo)
| Status | Endpoint | Anmerkung |
|--------|---------|-----------|
| ✅ | GET /api/mail/approve/pending?status=X | pending/sent/rejected/expired, session-oo |
| ✅ | GET /api/kira/proaktiv/status | für Drawer + Chip-Polling, session-oo |

---

## TECHNISCHE NOTIZEN

- **saveSettings()** liest Element-IDs aus dem DOM → neue Felder brauchen neue IDs + Eintrag in saveSettings()
- **config.json** wird per `POST /api/settings` gespeichert → neue Keys müssen im Handler verarbeitet werden
- **secrets.json** für sensible Daten (Passwörter, API-Keys) → eigener Handler `POST /api/secrets`
- **kira_llm.py** muss bei Persönlichkeits-/Name-Änderungen den System-Prompt neu laden → Server-Neustart oder Hot-Reload nötig
- **CSS-Klassen**: `es-*` Prefix für alle neuen Einstellungs-Elemente beibehalten
- **ISS-003**: SyntaxWarnings in server.py → raw-strings wenn Zeilen angefasst werden

---

## SESSION-u FIXES (2026-03-28)

### Schriftgröße-Bug behoben
| Status | Fix | Details |
|--------|-----|---------|
| ✅ | es-* CSS: hardcoded px → CSS-Variablen | `.es-sec-h{font-size:var(--fs-lg)}`, `.es-grp-h{font-size:var(--fs-sm)}`, `.es-badge{font-size:var(--fs-xs)}` etc. — Einstellungen-Panel reagiert jetzt auf Schriftgröße-Einstellung |
| ✅ | Playwright-Verifikation | `computed fontSize` von `.es-sec-h` = 20px bei Einstellung "Groß" ✓ |

### Neue Design-Features
| Status | Feature | Details |
|--------|---------|---------|
| ✅ | Toast: 6 Positionsoptionen | Unten rechts(Standard)/Mitte/links + Oben rechts/Mitte/links; CSS transforms für Zentrierung |
| ✅ | Tabellen Trennlinien | `applyTableLines()` + CSS `[data-table-lines] .proto-table tbody tr td{border-bottom:0.5px solid var(--border)}` |
| ✅ | Tabellen Live-Vorschau | proto-table in Design-Sektion reagiert auf alle 3 Tabellen-Einstellungen in Echtzeit |
| ✅ | Logo File-Upload | `<input type="file" id="cfg-logo-file">` + `handleLogoUpload()` via FileReader, max 512KB, base64 in localStorage |

### Benachrichtigungen-Fixes
| Status | Feature | Details |
|--------|---------|---------|
| ✅ | testPush() ReferenceError behoben | Funktion war nie definiert (Zeile 3481). Jetzt: fetch POST /api/ntfy/test → urllib.request → ntfy.sh |
| ✅ | POST /api/ntfy/test Backend | urllib.request, timeout=8s, headers: Title/Priority, gibt `{ok, error}` zurück |
| ✅ | Urlaubsmodus planen | datetime-local Inputs (von/bis) → ntfy.urlaub_von/urlaub_bis in config.json |
| ✅ | Urlaub-Header-Chip | Roter Chip erscheint in Header wenn ntfy.urlaub_modus=true (Python page-render-time check) |

### Nachfass-Erweiterung
| Status | Feature | Details |
|--------|---------|---------|
| ✅ | Benachrichtigung 'alle' | cfg-nf-typ: push/toast/beide/aufgabe(Kira LLM)/alle (Push+Toast+Aufgabe kombiniert) |

---
_Erstellt: session-r · 2026-03-27 · Zuletzt: session-u · 2026-03-28_
