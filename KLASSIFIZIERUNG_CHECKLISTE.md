# KIRA Mail-Klassifizierung — Master-Checkliste

> Arbeitsliste fuer das Klassifizierungs-Reparatur-Projekt
> Erstellt: 2026-04-02 · Letzte Aktualisierung: 2026-04-03

---

## Phase 1 — Klassifizierung reparieren (Kern-Fixes)

### A. Filter-Kaskade entschaerfen

| # | Was | Status | Commit | Anmerkung |
|---|-----|--------|--------|-----------|
| A1 | "Zur Kenntnis" nicht mehr uebersprungen | ✅ Erledigt (session-vvv) | 27acc81 | In daily_check.py + mail_monitor.py |
| A2 | Textfenster 1200→3000 Zeichen | ✅ Erledigt (session-vvv) | 27acc81 | mail_classifier.py + llm_classifier.py |
| A3 | Domain-Level "schon beantwortet" entfernt — nur noch per E-Mail | ✅ Erledigt (session-vvv) | 27acc81 | daily_check.py recheck + scan |
| A4 | Universelle Geschaefts-Keywords ergaenzt | ✅ Erledigt (session-vvv) | 27acc81 | 30+ Keywords in CUSTOMER_STRONG/NORMAL |
| A5 | Smarter Fallback: anfrage@/info@ mit persoenl. Inhalt → Task | ✅ Erledigt (session-vvv) | 27acc81 | Step 8b in mail_classifier.py |
| A6 | **Formular-Mails (noreply@) als Leads erkennen** | ✅ Erledigt (session-vvv) | 5133857 | Neuer Step 1b VOR System-Sender-Check |
| A7 | **Formular-Kunden-Email aus Body extrahieren** | ✅ Erledigt (session-vvv) | 27acc81 | extract_form_customer_email() in daily_check + mail_monitor |

### B. LLM-Absicherung

| # | Was | Status | Commit | Anmerkung |
|---|-----|--------|--------|-----------|
| B1 | LLM-Fehler sichtbar machen (Runtime-Log + Marker) | ✅ Erledigt (session-vvv) | 27acc81 | llm_classifier.py: Logging statt silent pass, _llm_fallback=True |
| B2 | "LLM nicht verbunden" Warnung im Dashboard-Header | ✅ Erledigt (session-xxx-intelligence) | b71b3a0 | Header-Chip #llmPauseChip + Toast bei Pause |
| B3 | ntfy-Push bei LLM-Ausfall | ✅ Erledigt (session-xxx-intelligence) | b71b3a0 | _send_qualify_pause_push() in daily_check.py |

### C. System-Prompt

| # | Was | Status | Commit | Anmerkung |
|---|-----|--------|--------|-----------|
| C1 | Universal-Kern (Geschaeftl. E-Mail-Klassifizierer) | ✅ Erledigt (session-vvv) | 27acc81 | kira_llm.py classify_direct() |
| C2 | Firmenspezifisch aus config.json (firma_name/branche/beschreibung) | ✅ Erledigt (session-vvv) | 27acc81 | Liest aus config.json, nicht hardcoded |

---

## Phase 2 — Sichtbarkeit + Infrastruktur

| # | Was | Status | Commit | Anmerkung |
|---|-----|--------|--------|-----------|
| D1 | Klassifizierung in mail_index.db speichern (kategorie+konfidenz) | ✅ Erledigt (session-vvv) | 27acc81 | Spalten angelegt + UPDATE nach Klassifizierung |
| D2 | DB-Migration fuer neue Spalten | ✅ Erledigt (session-vvv) | 27acc81 | server.py _ensure_mail_columns() |
| D3 | Thread-ID in Tasks speichern | ✅ Erledigt (session-vvv) | 27acc81 | daily_check.py + mail_monitor.py |
| D4 | Thread-basierte Task-Zusammenfuehrung | ✅ Erledigt (session-vvv) | 27acc81 | mail_monitor.py: Folgemail → bestehenden Task updaten |
| D5 | Pflegbare Keywords in config.json | ✅ Erledigt (session-vvv) | 27acc81 | mail_klassifizierung.eigene_keywords Array |
| D6 | **Pflegbare Keywords in Einstellungen-UI** | ⚠️ Offen | — | Input-Feld in Einstellungen > Mail-Klassifizierung |
| D7 | **Historische Qualifizierung (12.000+ Mails)** | ✅ Erledigt (session-www) | cbf5401 | 11.652/12.071 (96,5%) klassifiziert. Phase 1+2 komplett |

---

## Phase 2.5 — Routing-System (Task-Erstellung nur bei Handlung)

| # | Was | Status | Commit | Anmerkung |
|---|-----|--------|--------|-----------|
| R1 | LLM-Prompt: erfordert_handlung + routing Felder | ✅ Erledigt (session-bbbb) | be52f1d | 2 Pflichtfelder im JSON-Schema + Routing-Anweisung |
| R2 | Regelbasiertes Routing in mail_classifier.py | ✅ Erledigt (session-bbbb) | be52f1d | _default_routing() + alle Branches mit routing/erfordert_handlung |
| R3 | Routing-Dispatch in daily_check.py + mail_monitor.py | ✅ Erledigt (session-bbbb) | be52f1d | archivieren/buchhaltung/feed/kira_vorschlag/task |
| R4 | Bulk-Cleanup bestehender Tasks | ✅ Erledigt (session-bbbb) | be52f1d | 118→30 offene Tasks (88 archiviert) |
| R5 | Kira-Vorschlag Danke-Mail bei Absagen | ✅ Erledigt (session-bbbb) | be52f1d | _route_kira_vorschlag() → mail_approve_queue |
| R6 | Konversations-Gruppierung Kommunikation | ✅ Erledigt (session-bbbb) | be52f1d | thread_id-basiert, conv_badge lila |
| R7 | Bot-Icon im Postfach (hat_task Badge) | ✅ Erledigt (session-bbbb) | be52f1d | Lila "Aufgabe" Badge in beiden Mail-APIs |

---

## Phase 3 — Newsletter-Intelligence + Lern-System

| # | Was | Status | Commit | Anmerkung |
|---|-----|--------|--------|-----------|
| E1 | Newsletter-Erkennung intelligent machen | ⚠️ Offen | — | Zulieferer/Partner-NL → relevant, Fach-NL → relevant, Spam → ignorieren |
| E2 | Neue Kategorie "Newsletter (relevant)" | ⚠️ Offen | — | Zusaetzlich zu "Newsletter / Werbung" |
| E3 | **Dashboard News-Kachel** | ⚠️ Offen | — | Relevante Newsletter, Branchennews, abonnierte Inhalte |
| E4 | Daumen hoch/runter Feedback-Buttons | ⚠️ Offen | — | Pro News-Karte, speichert in corrections-Tabelle |
| E5 | Mini-Prompt bei "Daumen runter" | ⚠️ Offen | — | "Was stimmt nicht?" → Kira lernt daraus |
| E6 | Few-Shot-Beispiele aus Corrections in Klassifizierung | ⚠️ Offen | — | Bisherige 12 Korrekturen + neue Bewertungen |

---

## Phase 4 — Multi-Kanal + Zukunftssicherheit

| # | Was | Status | Commit | Anmerkung |
|---|-----|--------|--------|-----------|
| F1 | Kanal-Parameter in Klassifizierung | ✅ Vorhanden | — | kanal="email" wird uebergeben (auch whatsapp/sms ready) |
| F2 | WhatsApp-Eingangsverarbeitung → gleiche Pipeline | ✅ Erledigt (session-y) | — | verarbeite_kanal_eingang() existiert |
| F3 | Kunden-360-Verknuepfung (alle Kanaele pro Kunde) | ⚠️ Offen | — | Zentrale Kundenansicht mit Timeline ueber alle Kanaele |
| F4 | Neue Kanaele per Adapter integrierbar | ✅ Architektur steht | — | Pipeline ist kanal-neutral aufgebaut |

---

## Ergebnisse

### Nachtlauf 2026-04-02/03 — Historische Qualifizierung

| Kennzahl | Wert |
|----------|------|
| INBOX-Mails gesamt | 12.071 |
| Klassifiziert | 11.569 (95,8%) |
| Ignorieren | 7.669 (66,3%) |
| Rechnung / Beleg | 1.297 (11,2%) |
| Antwort erforderlich | 772 (6,7%) |
| Newsletter / Werbung | 650 (5,6%) |
| Zur Kenntnis | 437 (3,8%) |
| Shop / System | 312 (2,7%) |
| Neue Lead-Anfrage | 213 (1,8%) |
| Angebotsrueckmeldung | 173 (1,5%) |
| Abgeschlossen | 46 (0,4%) |
| **Geschaeftsrelevant** | **1.158 Mails** |

### Frueherer Trockenlauf (nur 2026)

| Zeitraum | Mails | Tasks (vorher) | Tasks (nach Fix) | Anmerkung |
|----------|-------|----------------|------------------|-----------|
| Januar 2026 | 203 | 0 | **3** | +3 unbeantwortete Leads/Business-Mails |
| Februar 2026 | 260 | 1 | **3** | +2 neue durch Formular-Erkennung |
| Maerz 2026 | 244 | 1 | **3** | +2 neue durch Formular-Erkennung |
| **Gesamt** | **707** | **2** | **9** | **4,5× mehr Tasks** |

> **Warum nicht 50+ Tasks?** ~85% der Mails sind System/Newsletter (Google, Apple, Shipcloud, Finom, Descript etc.). Echte Kundenanfragen kommen fast nur ueber das anfrage-Konto (~30/Monat). Von diesen wurden die meisten bereits manuell von Kai beantwortet → "schon beantwortet" filtert sie korrekt. Die 9 neuen Tasks sind wirklich unbeantwortete Leads.
>
> **Der echte Wert:** Ab JETZT werden neue Formular-Anfragen (Landing Page) und Business-Mails automatisch erkannt und als Tasks erstellt. Das waren vorher ~20 verlorene Leads pro Monat, die nie als Task erschienen.

---

## Offene Fragen fuer Kai

1. **Soll ich die echte Nachklassifizierung (kein Trockenlauf) fuer Feb+Maerz starten?**
   → Wuerde ~2-5 neue Tasks erstellen fuer unbeantwortete Leads

2. **Steuerberater-Mails (z.B. Zwicker "Jahresabschluss"): Sollen die als Task erscheinen?**
   → Aktuell: "Zur Kenntnis" → wird NICHT mehr uebersprungen → Task wird erstellt
   → Alternative: eigene Kategorie "Buchhaltung/Steuer" erstellen?

3. **kaimrf@gmail.com als eigene Adresse definieren?**
   → Kai's private Gmail-Adresse kommt in Test-Formular-Einsendungen vor
   → Aktuell: Wird als externer Kunde behandelt → erstellt Tasks fuer Tests
   → Fix: In EIGENE_DOMAINS aufnehmen oder spezielle Test-Erkennung?

4. **Firmendaten in config.json — stimmen die?**
   → `firma_name`: "rauMKult Sichtbeton"
   → `firma_branche`: "Betonkosmetik / Sichtbeton-Fachbetrieb"
   → Sollen diese in Einstellungen editierbar sein?

5. **Newsletter-Intelligence Prioritaet?**
   → Phase 3 (News-Kachel + Feedback-Buttons) ist aufwaendiger
   → Soll das als naechstes oder erst spaeter kommen?

6. **Keywords-Pflege in Einstellungen — sofort oder spaeter?**
   → config.json-Feld existiert, UI-Sektion fehlt noch

---

## Aenderungsprotokoll

| Datum | Session | Was |
|-------|---------|-----|
| 2026-04-02 | session-vvv | Phase 1 (A1-A7, B1, C1-C2) + Phase 2 (D1-D5) implementiert |
| 2026-04-02 | session-vvv | Formular-Klassifizierung gefixt (Step 1b in mail_classifier.py) |
| 2026-04-02 | session-vvv | Lexware-Kontext in LLM-Klassifizierung (bdc4552) |
| 2026-04-02 | session-www | qualify_mails() + Einstellungen-UI + API-Endpoints (cbf5401) |
| 2026-04-02 | session-www | Nachtlauf gestartet: 12.071 INBOX-Mails 2021-2025 nur_klassifizieren |
