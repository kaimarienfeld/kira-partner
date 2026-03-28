---
name: Kira Dashboard – Vollständige Feature-Liste
description: Akribische Liste aller Features nach Bereich, Status, Datei und Verknüpfungen. VOR und NACH jeder Arbeitssession prüfen und aktualisieren.
type: project
---

> **REGEL:** Diese Datei VOR dem Start einer Arbeitssession lesen und NACH der Session mit allen Änderungen aktualisieren.
> Letzte Prüfung: 2026-03-27

---

# KIRA DASHBOARD v4 — FEATURE-LISTE

**Server:** server.py (HTTP, Port 8765) | **DB:** tasks.db, kunden.db, rechnungen_detail.db
**Konfiguration:** config.json, secrets.json

Status-Legende: ✅ AKTIV | ⚠️ TEILWEISE | 🕐 GEPLANT | ❌ FEHLT/DEFEKT

---

## 1. DASHBOARD / ÜBERSICHT

| Feature | Status | Datei:Zeile | Verknüpfung |
|---|---|---|---|
| Tagesbriefing (KI-generiert) | ✅ | server.py:224, kira_llm.py:1432 | LLM → tasks.db → Cache täglich |
| Tagesbriefing (Statistik-Fallback) | ✅ | kira_llm.py:1521 | tasks.db Stats wenn kein LLM |
| 8 KPI-Karten | ✅ | server.py:267–301 | Klick → Panel/Filter |
| Priorisierte Aufgaben (Top 5) | ✅ | server.py:303–344 | tasks.db → Kategorie-Farben |
| Nächste Termine & Fristen | ✅ | server.py:349–374 | organisation-Tabelle, Urgency-Badges |
| Geschäft aktuell (letzte 5 Events) | ✅ | server.py:376–399 | geschaeft-Tabelle, Typ-Farben |
| Signale / Auffälligkeiten (Alerts) | ✅ | server.py:421–495 | AR, Angebote, Korrektionen, Skonto |
| Sparkline (6-Monate AR-Volumen) | ✅ | server.py:~270 | ausgangsrechnungen-Tabelle |
| Briefing manuell aktualisieren | ✅ | server.py:~3624 | POST /api/kira/briefing/regenerate |

---

## 2. KOMMUNIKATION / TASK-MANAGEMENT

| Feature | Status | Datei:Zeile | Verknüpfung |
|---|---|---|---|
| Task-Karten (Rich Card UI) | ✅ | server.py:647–720 | tasks.db → HTML-Karten |
| Großtitel (15px/700) + Badges-Reihe | ✅ | server.py:647, CSS:4350+ | – |
| Empfehlung in Akzentfarbe | ✅ | server.py:701, CSS:4370 | empfohlene_aktion-Spalte |
| Grund kursiv-gedämpft | ✅ | server.py:~703, CSS:~4372 | kategorie_grund-Spalte |
| Hover-Glow (Karten-Schatten) | ✅ | CSS:~4355 | – |
| Schnellbutton „Zur Kenntnis" auf Karte | ✅ | server.py:~710 | setStatusLernen() |
| Kontextpanel rechts (9 Buttons) | ✅ | server.py:~2644 | Mit Kira, Outlook, Mail lesen, Erledigt, Zur Kenntnis, Später, Ignorieren, Korrektur, Löschen |
| Segment-Navigation (Kategorie-Tabs) | ✅ | server.py:~520 | kommSegFilter() |
| Filter-Chips | ✅ | server.py:~530 | applyKommFilters2() |
| → Filter: Antwort nötig | ✅ | server.py:~530 | data-antwort Attribut |
| → Filter: Mit Anhang | ✅ | server.py:~530 | data-anhang Attribut |
| → Filter: Mit Fotos | ✅ | server.py:~530 | data-fotos Attribut |
| → Filter: Mit Termin | ✅ | server.py:~668, ~530 | data-termin, mit_termin-Spalte |
| → Filter: Beantwortet | ✅ | server.py:~670, ~530 | data-beantwortet, beantwortet-Spalte |
| → Filter: Manuelle Prüfung | ✅ | server.py:~669, ~530 | data-pruefung, manuelle_pruefung-Spalte |
| → Filter: Nur mit Kira | ✅ | server.py:~671, ~530 | data-kira Attribut |
| Prioritäts-Dropdown-Filter | ✅ | server.py:~535 | km-filter-prio |
| Suchfeld (Freitext) | ✅ | server.py:~540 | applyKommFilters2() |
| Stats-Zeile (n offen / Leads / Angebote) | ✅ | server.py:553–556 | km-stat-link → jumpToSeg() |
| jumpToSeg() — Stats-Links | ✅ | server.py:~2830 | aktiviert Segment-Tab |
| Thread-Verlauf (live geladen) | ✅ | server.py:~4930 | GET /api/task/{id}/thread |
| Thread: aktuell hervorgehoben | ✅ | server.py:~540 | km-thread-current CSS |
| Konfidenz-Badge (niedrig) | ✅ | server.py:~685 | konfidenz-Spalte |
| Erinnerungs-Badge (1./2./3.) | ✅ | server.py:~688 | erinnerungen-Spalte |
| Korrekturen (Klassifizierungs-Feedback) | ✅ | server.py:5665+ | corrections-Tabelle → Few-Shot |
| Lösch-History & Duplikat-Block | ✅ | server.py:~4810 | loeschhistorie-Tabelle |
| Anhang-Browser (Datei-Viewer) | ✅ | server.py:~4855 | GET /api/attachments |
| Mail lesen (RFC822-Raw) | ✅ | server.py:~4870 | GET /api/mail/read |

---

## 3. KIRA (KI-ASSISTENT)

| Feature | Status | Datei:Zeile | Verknüpfung |
|---|---|---|---|
| Chat-Interface | ✅ | server.py:5228+, kira_llm.py:1281 | POST /api/kira/chat |
| Multi-Provider (Anthropic, OpenAI, OpenRouter, Ollama, Custom) | ✅ | kira_llm.py:21–230 | Provider-Fallback-Chain |
| Provider-Verwaltung (UI) | ✅ | server.py:5261–5362 | secrets.json |
| Kira System-Prompt (Geschäftsdaten) | ✅ | kira_llm.py:263–376 | tasks.db → AR, Angebote, Wissen |
| Tages-Briefing (KI) | ✅ | kira_llm.py:1432–1521 | kira_briefings-Tabelle, Cache |
| Konversationen speichern | ✅ | kira_llm.py:234–259 | kira_konversationen-Tabelle |
| Token-Tracking | ✅ | kira_llm.py:~1350 | token_input, token_output Spalten |
| Budget-Modell (Klassifizierung) | ✅ | kira_llm.py:~100 | Haiku / gpt-4o-mini, max_tokens=512 |
| classify_direct() | ✅ | kira_llm.py:~90 | kein System-Prompt, keine Tools |
| **Tool: rechnung_bezahlt** | ✅ | kira_llm.py:600 | ausgangsrechnungen UPDATE + Statistik |
| **Tool: angebot_status** | ✅ | kira_llm.py:~650 | angebote UPDATE |
| **Tool: eingangsrechnung_erledigt** | ✅ | kira_llm.py:~680 | geschaeft UPDATE |
| **Tool: kunde_nachschlagen** | ✅ | kira_llm.py:~700 | tasks.db + kunden.db |
| **Tool: nachfass_email_entwerfen** | ✅ | kira_llm.py:~730 | 3 Tonfall-Varianten |
| **Tool: wissen_speichern** | ✅ | kira_llm.py:~760 | wissen_regeln INSERT |
| **Tool: rechnungsdetails_abrufen** | ✅ | kira_llm.py:772 | rechnungen_detail.db |
| **Tool: angebot_pruefen** | ✅ | kira_llm.py:~800 | Antwort-Intent-Klassifizierung |
| **Tool: web_recherche** | ✅ | kira_llm.py:~850 | DuckDuckGo, config: internet_recherche |
| **Tool: duplikate_suchen** | ✅ | kira_llm.py:844–933 | Betreff-Ähnlichkeit, Cluster-Erkennung |
| **Tool: task_erledigen** | ✅ | kira_llm.py:~960 | tasks UPDATE (erledigt/zur_kenntnis/ignorieren) |
| **Tool: tasks_loeschen** | ✅ | kira_llm.py:~1000 | tasks DELETE + loeschhistorie INSERT |
| Task-Kontext in Kira (KIRA_CTX) | ✅ | server.py:~2620 | Per-Task-Kontext als JS-Constant |

---

## 4. MAIL-MONITOR / KLASSIFIZIERUNG

| Feature | Status | Datei:Zeile | Verknüpfung |
|---|---|---|---|
| IMAP-Polling (5 Konten) | ✅ | mail_monitor.py | OAuth2 → UID-State → Tasks |
| OAuth2 Device-Flow + Token-Cache | ✅ | mail_monitor.py | raumkult_mail_archiver_config.json |
| Polling-Intervall (default 15 min) | ✅ | mail_monitor.py, config.json | mail_monitor.intervall_sekunden=900 |
| Fast-Path (regelbasiert, kein LLM) | ✅ | llm_classifier.py | Gesendete, System-Sender, Newsletter |
| LLM-Klassifizierung | ✅ | llm_classifier.py | classify_direct() + Kontext |
| Angebots-Kontext (3-Ebenen-Match) | ✅ | llm_classifier.py:~180 | Mail-Domain → Kundenname-Match |
| Few-Shot-Beispiele (Korrektionen) | ✅ | llm_classifier.py:341–371 | corrections-Tabelle, letzte 12 |
| Kira-Wissen im Prompt | ✅ | llm_classifier.py:~350 | wissen_regeln WHERE status='aktiv' |
| Kundenprofil-Kontext | ✅ | llm_classifier.py:~380 | tasks.db + kunden.db |
| JSON-Felder: mit_termin | ✅ | llm_classifier.py, mail_monitor.py | tasks.mit_termin-Spalte |
| JSON-Felder: manuelle_pruefung | ✅ | llm_classifier.py, mail_monitor.py | tasks.manuelle_pruefung-Spalte |
| JSON-Felder: beantwortet | ✅ | llm_classifier.py, mail_monitor.py | tasks.beantwortet-Spalte |
| ntfy Push-Benachrichtigungen | ✅ | mail_monitor.py:424–456 | config: ntfy.aktiv, ntfy.topic_name |
| Multi-Kanal (WhatsApp, Instagram, SMS) | 🕐 | llm_classifier.py (kanal-Param), server.py (Webhooks) | Infrastruktur bereit |
| Auto-Reply generieren | 🕐 | llm_response_gen.py | generate_draft() vorhanden |

---

## 5. ORGANISATION

| Feature | Status | Datei:Zeile | Verknüpfung |
|---|---|---|---|
| Termine & Fristen Panel | ✅ | server.py:730–789 | organisation-Tabelle |
| Typen: termin, frist, rueckruf | ✅ | rebuild_all.py:101 | LLM extrahiert aus Mail |
| Urgency-Farben (heute/bald/normal) | ✅ | server.py:~770 | datum_erkannt vs. today |

---

## 6. GESCHÄFT / FINANZEN

| Feature | Status | Datei:Zeile | Verknüpfung |
|---|---|---|---|
| Ausgangsrechnungen (AR) | ✅ | server.py:805–892 | ausgangsrechnungen-Tabelle |
| AR: Bezahlt-Tracking + Zahlungsdauer | ✅ | kira_llm.py:600 | Tool: rechnung_bezahlt |
| AR: Mahnung-Tracking (Stufe 1/2/3) | ✅ | rebuild_all.py:162 | mahnung_count-Spalte |
| AR: Skonto-Erkennung | ✅ | rechnungen_detail.db | skonto_datum, skonto_betrag |
| Angebote / Sales Pipeline | ✅ | server.py:805–892 | angebote-Tabelle |
| Angebote: Nachfass-Tracking | ✅ | kira_llm.py:~650 | nachfass_count, naechster_nachfass |
| Angebote: Nachfass-Intervalle | ✅ | config.json | 10, 21, 45 Tage |
| Geschäftsdaten-Events | ✅ | server.py:~805 | geschaeft-Tabelle |
| Geschäft-Statistik (Muster) | ✅ | kira_llm.py:~645 | geschaeft_statistik-Tabelle |
| Rechnungsdetails (Positionen, Skonto) | ✅ | kira_llm.py:772 | rechnungen_detail.db |
| Eingangsrechnungen | ✅ | kira_llm.py:~680 | geschaeft WHERE typ='Eingangsrechnung' |
| Angebots-Tracker (angebote_tracker.py) | ⚠️ | angebote_tracker.py | Anbindung unklar |

---

## 7. WISSEN / REGELN

| Feature | Status | Datei:Zeile | Verknüpfung |
|---|---|---|---|
| Knowledge Base (wissen_regeln) | ✅ | server.py:1627–1788 | wissen_regeln-Tabelle |
| 9 Fest-Regeln beim Init | ✅ | rebuild_all.py:410–438 | status='fest', dauerhaft aktiv |
| Dynamisches Lernen (Tools) | ✅ | kira_llm.py:654–1049 | quelle='Kira-Chat' |
| Wissen in System-Prompt | ✅ | kira_llm.py:~320 | max 20 gelernte Regeln |
| Wissen in Klassifizierungs-Prompt | ✅ | llm_classifier.py:~350 | max 10 aktive Regeln |
| Wissen-UI (Edit/Delete/Review) | ✅ | server.py:1627 | – |
| Korrektionen als Few-Shot | ✅ | llm_classifier.py:341 | letzte 12 Korrektionen |

---

## 8. SERVER / INFRASTRUKTUR

| Feature | Status | Datei:Zeile | Verknüpfung |
|---|---|---|---|
| Auto-Kill alter Instanzen (Start) | ✅ | server.py:6030 | netstat → taskkill → Port-Check |
| Port-Verfügbarkeits-Check (bind-Test) | ✅ | server.py:6047 | socket.bind → max 3s warten |
| Neustart-Button (permanent sichtbar) | ✅ | server.py:1926 | kill-all + restart + page reload |
| Neustart-Countdown (Sekunden) | ✅ | server.py:~3588 | „↻ 3s", „↻ 4s" während Warten |
| Cache-Control: no-store (alle Responses) | ✅ | server.py:6023 | kein Browser-Cache |
| Thread-Safe HTTP-Server | ✅ | server.py:43 | ThreadingMixIn |
| DB-Safe-Migration (ALTER TABLE) | ✅ | server.py:35–41, rebuild_all.py | alle neuen Spalten migriert |
| restart_kira.bat (harter Neustart) | ✅ | scripts/restart_kira.bat | taskkill + VBS + Browser-Open |
| start_dashboard.bat / start_kira_silent.vbs | ✅ | scripts/ | Vollpfad via WScript.ScriptFullName |

---

## 9. DATENBANK-TABELLEN

| Tabelle | DB | Status | Wichtige Spalten |
|---|---|---|---|
| tasks | tasks.db | ✅ | id, kategorie, status, prioritaet, mit_termin, manuelle_pruefung, beantwortet, thread_id, konfidenz |
| ausgangsrechnungen | tasks.db | ✅ | re_nummer, status, mahnung_count, bezahlt_am |
| angebote | tasks.db | ✅ | a_nummer, status, nachfass_count, naechster_nachfass |
| kunden_aliases | tasks.db | ✅ | haupt_email, alias_email |
| geschaeft | tasks.db | ✅ | typ, betrag, status, quelle |
| geschaeft_statistik | tasks.db | ✅ | typ, ereignis, daten_json |
| organisation | tasks.db | ✅ | typ (termin/frist/rueckruf), datum_erkannt |
| wissen_regeln | tasks.db | ✅ | kategorie, titel, inhalt, status, quelle |
| corrections | tasks.db | ✅ | alter_typ, neuer_typ, notiz |
| task_kira_context | tasks.db | ✅ | task_id, kai_input, kira_antwort |
| loeschhistorie | tasks.db | ✅ | absender, betreff, grund, message_id |
| kira_konversationen | tasks.db | ✅ | session_id, rolle, provider_used, token_input, token_output |
| kira_briefings | tasks.db | ✅ | datum (UNIQUE), inhalt_json |
| interaktionen | kunden.db | ✅ | konto_label, absender, datum, text_plain |
| rechnungen_detail | rechnungen_detail.db | ✅ | positionen_json, skonto_datum, zahlungsziel_datum |
| mahnungen_detail | rechnungen_detail.db | ✅ | re_nummer, stufe, datum |

---

## OFFENE PUNKTE / TODO

| Aufgabe | Priorität | Notiz |
|---|---|---|
| Multi-Kanal (WhatsApp/Instagram) | 🕐 mittel | Webhook-Gerüst da, Anbindung fehlt |
| Auto-Reply aus Entwurf senden | 🕐 mittel | llm_response_gen.py vorhanden |
| angebote_tracker.py Anbindung prüfen | ⚠️ offen | Unklar ob aktiv genutzt |
| Duplikat-Erkennung verbessern | ⚠️ mittel | Nur Betreff-Match, kein semantisches Matching |
| Kira: Task-Kontext automatisch in Chat | ⚠️ teilweise | KIRA_CTX vorhanden aber nicht immer gefüllt |
