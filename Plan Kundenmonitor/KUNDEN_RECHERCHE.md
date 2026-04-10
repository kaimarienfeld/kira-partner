# Internet-Recherche — Kunden CRM

Stand: 2026-04-10

---

## 1. CRM-Ticket-Aggregations-Muster

**Prinzipien aus modernen CRM-Systemen (Zendesk, Linear, Intercom):**
- Jeder Geschäftsvorfall ist ein "Ticket" / "Issue" / "Conversation"
- Tickets aggregieren alle zugehörigen Kommunikation (E-Mail-Threads, Chat, Notizen)
- Timeline-Darstellung: chronologisch, mit Quellen-Icons zur Unterscheidung
- Status-Workflows: konfigurierbar, aber mit sinnvollen Defaults
- Automatisches Zusammenführen: gleicher Absender + ähnlicher Betreff = gleicher Fall
- SLA-Tracking: Fälligkeit + Warnung wenn überschritten

**Übertragung auf KIRA:**
- kunden_faelle = Ticket-Äquivalent
- kunden_aktivitaeten = Timeline-Einträge
- fall_typ + status = konfigurierbarer Workflow
- Quellen-Icons (Mail/Kira/Memo/Dokument/Lexware/manuell) für visuelle Unterscheidung

---

## 2. LLM-basierte Kontext-Klassifizierung

**Best Practices für robusten Super-Prompt:**
- Kontext kompakt halten: nur relevante Kunden + Projekte (nicht die ganze DB)
- Klare JSON-Struktur erzwingen (Schema vorgeben)
- Explizite Negativ-Beispiele: "Mängelanzeige = altes Projekt, NICHT neues"
- Confidence-Stufen definieren (nicht nur ja/nein)
- Reasoning verlangen (max 2 Sätze) für Nachvollziehbarkeit
- Temperatur niedrig (0.0-0.1) für konsistente Klassifizierung

**Übertragung auf KIRA:**
- Super-Prompt mit Kunden-Kontext (Top 50 + Projekte + Identitäten)
- JSON-only Response mit Confidence + Reasoning
- 4 Stufen: eindeutig / wahrscheinlich / prüfen / unklar

---

## 3. Projekt-Zeitachsen in SQLite

**Effiziente Abfrage-Muster:**
- Index auf (kunden_id, erstellt_am) für schnelle chronologische Abfragen
- Projekt-Filter via WHERE projekt_id = ? — nicht Client-seitig filtern
- Aggregations-Queries für KPIs: COUNT + GROUP BY status
- Pagination: LIMIT + OFFSET für große Verläufe
- Composite Index: (kunden_id, projekt_id, erstellt_am) für gefilterte Timelines

**Übertragung auf KIRA:**
- Indizes auf allen kunden_id + projekt_id + erstellt_am Kombinationen
- API liefert projektgefilterte Daten, nicht alles + Client-Filter

---

## 4. Geschäftskontakt vs. Newsletter Filter

**Signale für kein Geschäftsfall:**
- Absender-Domain: newsletter.*, noreply@, no-reply@, mailer@, bounce@, info@großer-anbieter
- Betreff-Muster: "Newsletter", "Angebot exklusiv", "Nur heute", "Unsubscribe", "Abbestellen"
- Header: List-Unsubscribe, Precedence: bulk, X-Mailer: Newsletter
- Häufigkeit: >5 Mails/Woche vom gleichen Absender = wahrscheinlich Newsletter
- Kein Name in Kunden-Identitäten bekannt

**Übertragung auf KIRA:**
- Neue Stufe in mail_classifier.py (vor Schritt 7)
- Regelbasiert (kein LLM nötig für offensichtliche Newsletter)
- LLM-Fallback: Classifier sagt ist_geschaeftsfall=false

---

## 5. Confidence-Score-Modelle

**Automatische vs. manuelle Zuordnung:**
- Threshold-basiert: Score > 0.9 = auto, 0.6-0.9 = Vorschlag, < 0.6 = manuell
- In CRM-Systemen: "High confidence" = direkt routen, "Low confidence" = Queue für Review
- Lerneffekt: manuelle Korrekturen verbessern zukünftige Zuordnung
- Wichtig: Alle Entscheidungen loggen (auch automatische) für Audit-Trail

**Übertragung auf KIRA:**
- 4 Stufen statt numerisch (eindeutig/wahrscheinlich/prüfen/unklar) — lesbarer
- Konfigurierbare Schwelle in Einstellungen (Auto-Zuordnung ab welcher Confidence)
- kunden_classifier_log für vollständiges Audit-Trail
- Manuelle Korrektur → Confidence in kunden_identitaeten hochstufen
