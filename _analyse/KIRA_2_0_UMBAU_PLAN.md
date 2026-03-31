# KIRA 2.0 — Umbau-Plan: Einstellungen, UI/UX & Neue Features
**Erstellt:** 2026-03-31
**Basis:** KIRA_SYSTEM_ANALYSE.md + Kais Anmerkungen (Zusatz v Kai zu Kira 2.0 umbau.md)
**Status:** PLAN — noch nicht umgesetzt

---

## PRIORITÄTEN (Reihenfolge)

1. **App läuft stabil** (JS-Fehler behoben ✅)
2. **Einstellungen an Kira 2.0 anpassen** — neue Tabs, fehlende Sektionen
3. **Kira-Postfach** — eigenes Postfach für Kira-Mails im Dashboard
4. **Aktiv-Fenster / Live-Status** — dynamische Anzeige was Kira gerade tut
5. **UI-Gesamtüberarbeitung** — bestehende Panels an neue Funktionen anpassen
6. **Kalender-Integration** — eigene Kalenderansicht im Dashboard
7. **Belegvorlagen-Modul** — neues Modul wie Lexware

---

## TEIL 1 — EINSTELLUNGEN: IST vs. SOLL

### Vorhandene Einstellungs-Sektionen

| Sektion | Vorhanden | Anpassung nötig |
|---|---|---|
| Design | ✅ | nein |
| Benachrichtigungen | ✅ | ntfy ergänzen um Kira-Stufen A/B/C |
| Aufgabenlogik | ✅ | leicht anpassen |
| Nachfass-Intervalle | ✅ | Kira-Automatisierung verknüpfen |
| Dashboard | ✅ | Kira-Live-Status Einstellungen |
| Kira / LLM / Provider | ✅ | **stark erweitern** (Memory, ReAct, Feedback) |
| Mail & Konten | ✅ | **Kira-Postfach + Vorlagen ergänzen** |
| Integrationen | ✅ | Graph Calendar Einstellungen |
| Automationen | ⚠️ (als "Geplant" markiert) | **jetzt aktivieren** |
| Protokoll & Logs | ✅ | Kira-Aktivitäten-Einstellungen |

### Neue Einstellungs-Sektionen (zu erstellen)

| Neue Sektion | Zweck |
|---|---|
| **Kira — Gedächtnis** | 3-Tier Memory: episodisch, tägl. Summary, Regeln |
| **Kira — Automatisierung** | Proaktiv-Scans konfigurieren (TTL, Konfidenz-Schwellen) |
| **Kira — Sicherheit & Audit** | Circuit Breaker, Rate Limits, actor_type-Einstellungen |
| **Mail-Vorlagen** | Vorlagen für Kira-Mails, Signaturen-Zuordnung |
| **Kalender** | Graph Calendar Konto, Sync-Einstellungen |
| **Belegvorlagen** | Rechnungs-/Angebots-Layouts (zukünftig) |

---

## TEIL 2 — DETAILPLAN: EINSTELLUNGS-ERWEITERUNGEN

### 2-A: Sektion "Kira / LLM / Provider" erweitern

**Bestehende Gruppen:**
- Kira Assistent (Name, Modus, Sprache)
- KI-Provider (API-Keys)
- LLM-Kontext
- Mail-Klassifizierung

**Hinzufügen:**

```
Gruppe: Konversations-Gedächtnis
  [ ] Gedächtnis aktiviert                          (default: an)
  [ ] Episodische Erinnerungen (letzte N Sessions)  (default: 3, Bereich: 1-10)
  [ ] Tägliche Zusammenfassung                       (default: an)
      ℹ️ Kira fasst täglich alle Gespräche zusammen und speichert Schlüsselentscheidungen.
         Einstellung wirkt ab nächstem Scan-Zyklus.
  [ ] Max. Token für Gedächtnis im Kontext           (default: 3200)

Gruppe: Proaktive Automatisierung
  [ ] Proaktive Scans aktiviert                      (default: an)
  [Slider] Scan-Intervall: alle __ Min               (default: 15, Bereich: 5-60)
  [Slider] Angebot-Followup nach __ Tagen            (default: 7)
  [Slider] Mahnung-Eskalation nach __ Tagen          (default: 14)
  [Slider] Konfidenz-Schwelle Stufe A (autonom)      (default: 85%)
  [Slider] Konfidenz-Schwelle Stufe B (bestätigen)   (default: 60%)
      ℹ️ Unterhalb Stufe-B: Kira fragt immer nach. Stufe A: Kira handelt ohne Rückfrage.

Gruppe: ReAct & Multi-Step
  [ ] Mehrstufige Aufgaben erlauben                  (default: an)
  [Zahl] Max. Schritte pro Aufgabe                   (default: 5, Bereich: 2-10)
      ℹ️ ReAct-Modus: Kira kann komplexe Aufgaben in mehreren Schritten durchführen.

Gruppe: Feedback & Lernen
  [ ] Feedback-Buttons anzeigen (👍/👎)             (default: an)
  [ ] Auto-Lernregeln aus Feedback erstellen         (default: an)
  [ ] Stil-Lernen aus Mail-Bearbeitungen             (default: an)
      ℹ️ Wenn du Kiras Mail-Entwürfe stark änderst, lernt Kira deinen Schreibstil.

Gruppe: Sicherheit & Limits
  [Zahl] Max. LLM-Anfragen pro Minute               (default: 20)
  [Zahl] Circuit Breaker: Fehler bis Sperre         (default: 3)
  [Zahl] Sperre-Dauer nach Fehler (Sekunden)        (default: 300)
```

### 2-B: Sektion "Mail & Konten" erweitern

**Kira-Postfach-Bereich hinzufügen:**
```
Gruppe: Kira-Postfach
  [ ] Kira-Ausgangsbereich im Postfach anzeigen
      Zeigt: Entwürfe | Genehmigt | Gesendet | Abgelehnt
  [Auswahl] Kira sendet von: [Konto auswählen ▼]
      ℹ️ Kira nutzt dieses Konto für alle ausgehenden Mails.

Gruppe: Mail-Vorlagen
  [Liste] Vorlage  |  Typ  |  Aktiv  |  Bearbeiten
  [+ Neue Vorlage]
      ℹ️ Kira wählt automatisch die passende Vorlage je nach Mailtyp (Angebot, Rechnung, Nachfass...).

Gruppe: Signatur-Zuordnung
  Zu jeder Vorlage: [Vorlage X → Signatur Y ▼]
```

### 2-C: Neue Sektion "Automationen" (aus "Geplant" → "Aktiv")

```
Gruppe: Aktive Automatisierungsregeln
  Liste mit Status:
  ✅ Angebot-Followup (nach {N} Tagen)
  ✅ Mahnung-Eskalation (nach {N} Tagen)
  ✅ Autonomy-Decision-Scan (alle {N} Min)
  ✅ Tägliche Memory-Summary
  ❌ Termin-Erkennung in Mails (geplant)

Gruppe: Manuelle Aktionen
  [▶ Scan jetzt ausführen]  — löst run_proaktiver_scan() aus
  [🔄 Rückwirkend analysieren] — analysiert historische Konversationen (erst auf Knopfdruck!)
  [🗑️ Memory zurücksetzen] — löscht tages_summary Einträge
```

### 2-D: Sektion "Sicherheit & Audit" (neu)

```
Gruppe: API-Sicherheit
  Circuit Breaker Status je Provider: [Anthropic ✅ | Ollama ✅]
  [Reset Circuit Breaker]

Gruppe: Kira-Aktivitäten-Einstellungen
  [Zahl] Aktivitäten-Log speichern: __ Tage        (default: 90)
  [ ] Nur bestätigte Aktionen zeigen im Log

Gruppe: Audit-Export
  [Export CSV: Kira-Aktionen letzte 30 Tage]
```

---

## TEIL 3 — KIRA-POSTFACH

### Konzept

Im vorhandenen Postfach-Bereich: eigener **"Kira"**-Ordner/Tab in der Sidebar.

**Ansichten:**
- `📥 Entwürfe` — mail_approve_queue WHERE status='pending'
- `✅ Gesendet` — mail_approve_queue WHERE status='sent'
- `❌ Abgelehnt` — mail_approve_queue WHERE status='rejected'
- `⏰ Abgelaufen` — mail_approve_queue WHERE status='expired'

**Aktionen pro Mail:**
- Genehmigen → sendet sofort
- Ablehnen → status='rejected'
- Bearbeiten → opens edit modal
- Weiterleiten an Kira-Chat → kontextuell weiterverarbeiten

**Integration in vorhandenes Postfach:**
- Neue Ordnergruppe "Kira-Ausgang" in der Ordnerliste links
- Gleiche Ansicht wie normales Postfach, aber READ-ONLY für reguläre Mails

---

## TEIL 4 — KIRA LIVE-STATUS (dynamisches Aktiv-Fenster)

### Konzept: "Kira-Live-Chip" + "Activity-Drawer"

**Kira-Live-Chip** (Header-Bereich, dauerhaft sichtbar):
```
[🔄 Kira analysiert...] ← bei aktivem Scan
[✅ Kira wartet]        ← idle
[⚡ 2 Aktionen offen]   ← bei pending signals
```

**Activity-Drawer** (Slide-In von rechts, nicht-modal):
- Öffnet bei Klick auf Chip
- Zeigt: "Was macht Kira gerade?"
  - Laufende Scans mit Fortschritt
  - Letzte 5 Aktionen (aus runtime_events.db WHERE actor_type IN kira_autonom, kira_vorschlag)
  - Ausstehende Genehmigungen (mail_approve_queue + signals)
- Live-Update via setInterval (15s) oder SSE
- **Kein Technik-Jargon** — verständliche Sprache:
  - ❌ "scan_angebot_followup_vorgang läuft mit TTL=48h"
  - ✅ "Kira prüft 3 Angebote auf Nachfass-Bedarf"

**Kira kommt in Vordergrund wenn User am PC:**
- Nutzt document.visibilityState oder window focus
- Wenn Kira Stufe-B-Signal hat + User ist aktiv → sanfter Toast statt still
- Einstellbar: "Kira darf aktiv auffordern" (default: an)

---

## TEIL 5 — UI-GESAMTANALYSE (To-do für Browser-Analyse)

**Noch zu tun:** Browser öffnen, Screenshots aller Panels, dann konkrete Umbau-Liste.

### Bekannte Umbau-Punkte (ohne Browser-Check)

| Panel | Problem | Lösung |
|---|---|---|
| Dashboard | Kira-Briefing statisch, keine Live-Aktionen | Live-Status-Chip + Activity-Drawer |
| Postfach | Kein Kira-Ausgang | Neuer Kira-Ordner |
| Geschäft | Buttons wie "Kira fragen" wirken lost | An Kira 2.0 Workflow andocken |
| Kira-Chat | Nur Chatfenster, kein Kontext-Panel | Kontext-Sidebar zeigen (Vorgang, Kunde) |
| Einstellungen > Automationen | Zeigt "Geplant" | Aktivieren (Scans laufen schon!) |
| Wissen | Wissensregeln zeigen, aber kein Feedback-Loop-UI | 👍/👎 auch in Wissens-Panel |

### Panels komplett neu (To-do)

- **Kalender-Panel** — Outlook-Kalender-View oder eigene Mini-Kalenderansicht
- **Kira-Aktivitäten** (P9, schon im Code) — Timeline-View ist gebaut, aber verbesserbar
- **Belegvorlagen** (Zukunft) — ähnlich wie Einstellungen, eigenes Panel

---

## TEIL 6 — KALENDER-INTEGRATION (Plan)

### Option A: Mini-Kalender im Dashboard (einfach)
- Widget auf Dashboard-Seite: Monatsansicht + Liste nächste 7 Tage
- Daten von `/api/kira/termine` (Graph API)
- Kira kann Termine direkt hinzufügen

### Option B: Outlook-Kalender embed (komplex)
- Outlook Web App kann via iframe eingebettet werden
- Erfordert Microsoft Authentication + CORS-Freigabe
- Komplexität: hoch

**Empfehlung:** Option A zuerst, Option B optional als Einstellung.

---

## NÄCHSTE SCHRITTE (Reihenfolge)

```
Phase 1 (sofort): App stabil halten
  [x] JS SyntaxError gut/reject behoben
  [ ] Browser-Test nach Server-Neustart

Phase 2 (nächste Session): Einstellungen erweitern
  [ ] Kira/LLM-Sektion: Memory, Proaktiv, ReAct, Feedback, Sicherheit
  [ ] Mail & Konten: Kira-Postfach + Vorlagen-Bereich
  [ ] Automationen-Sektion: aus "Geplant" → aktiv, mit Scan-Status
  [ ] Sicherheit & Audit: neue Sektion

Phase 3: Kira-Postfach
  [ ] Ordner-Gruppe "Kira-Ausgang" im Postfach
  [ ] Approval-Queue als Postfach-Ansicht
  [ ] Aktionen: Genehmigen/Ablehnen/Bearbeiten inline

Phase 4: Kira-Live-Status
  [ ] Live-Chip im Header
  [ ] Activity-Drawer (Slide-In)
  [ ] Verständliche Sprache statt Technik-Jargon
  [ ] "Kira kommt in Vordergrund wenn User aktiv"

Phase 5: Browser-Analyse & UI-Überarbeitung
  [ ] Screenshots aller Panels (Playwright)
  [ ] Konkrete Änderungsliste pro Panel
  [ ] Umsetzen Priorität nach Liste

Phase 6: Kalender-Panel
  [ ] Mini-Kalender Widget auf Dashboard
  [ ] Graph-API-Daten

Phase 7: Belegvorlagen-Modul (Zukunft)
  [ ] Eigene Panel-Seite
  [ ] Vorlagen-Editor
```

---

## ANMERKUNG: Rückwirkende Analyse

**Status: Zurückgestellt auf Wunsch.**
Erst wenn App + UI stabil und Einstellungen angepasst. Dann als Knopf in Einstellungen > Automationen > "Rückwirkend analysieren".
