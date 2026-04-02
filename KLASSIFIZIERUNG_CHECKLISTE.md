# KIRA Mail-Klassifizierung — Master-Checkliste

> Arbeitsliste fuer das Klassifizierungs-Reparatur-Projekt
> Erstellt: 2026-04-02 · Letzte Aktualisierung: 2026-04-02

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
| B2 | "LLM nicht verbunden" Warnung im Dashboard-Header | ⚠️ Offen | — | Toast + roter Header-Chip wenn kein Provider aktiv |
| B3 | ntfy-Push bei LLM-Ausfall | ⚠️ Offen | — | Wenn Provider komplett fehlt/fehlschlaegt |

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
| D7 | **Nachklassifizierung mit neuen Fixes ausfuehren** | ⚠️ Offen | — | Feb+Maerz Mails echt nachklassifizieren (kein dry_run) |

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

## Trockenlauf-Ergebnisse

| Zeitraum | Mails | Tasks (vorher) | Tasks (nach Fix) | Anmerkung |
|----------|-------|----------------|------------------|-----------|
| Januar 2026 | 203 | 0 | 2 | Meiste Leads schon beantwortet, Tests gefiltert |
| Februar 2026 | 260 | — | ⏳ Laeuft | — |
| Maerz 2026 | 244 | — | ⏳ Laeuft | — |

> **Warum nicht 50+ Tasks?** Die meisten Mails auf dem info-Konto sind System-Mails (Google, Apple, Shipcloud, Newsletter). Echte Kundenanfragen kommen fast nur ueber das anfrage-Konto (26/Monat). Von diesen wurden die meisten bereits manuell von Kai beantwortet → "schon beantwortet" filtert sie korrekt.
>
> **Der echte Wert:** Ab JETZT werden neue Formular-Anfragen und Business-Mails automatisch erkannt und als Tasks erstellt. Die historischen Mails waren groesstenteils schon manuell bearbeitet.

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
