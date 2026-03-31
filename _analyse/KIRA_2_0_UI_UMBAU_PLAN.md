# KIRA 2.0 — UI/UX Umbau-Plan

**Erstellt:** 2026-03-31
**Basis:** Browser-Analyse (18 Screenshots), Code-Scan server.py, KIRA_2_0_UMBAU_PLAN.md, "Zusatz v Kai zu Kira 2.0 umbau.md", UX-Research (Smashing Magazine, NNGroup, Cursor 2.0, Microsoft Copilot Patterns)
**Status:** PLAN — zur Freigabe durch Kai

---

## Screenshot-Referenz

Alle Screenshots gespeichert in `_analyse/ui_screenshots_2026-03-31/`

| Datei                         | Panel                                             |
| ----------------------------- | ------------------------------------------------- |
| 01_dashboard.jpg              | Dashboard — Tagesbriefing, KPI-Karten             |
| 02_kommunikation.jpg          | Kommunikation — Tab-Filter, Task-Liste            |
| 03_postfach.jpg               | Postfach — Fluent Ribbon, Ordnerbaum, Mail-Liste  |
| 04_organisation.jpg           | Organisation — Timeline/Fristen/Rückrufe/Kalender |
| 05_geschaeft.jpg              | Geschäft — KPI-Übersicht, Vorgänge, Signale       |
| 06_wissen.jpg                 | Wissen — Bibliothek/Regelsteuerung, Regelkarten   |
| 07_kira_log.jpg               | Kira-Aktivitäten — leer, noch keine Aktionen      |
| 08_protokoll.jpg              | Aktivitätsprotokoll — Log-Tabelle                 |
| 09_kira_chat_launcher.jpg     | Kira Quick-Actions Overlay                        |
| 10_kira_chat_vollbild.jpg     | Kira Chat-Modal — Sidebar + Chat                  |
| 11_einst_design.jpg           | Einstellungen — Design + neue Nav-Items           |
| 12_einst_kira_llm.jpg         | Einstellungen — Kira/LLM (alle 5 neuen Gruppen)   |
| 13_einst_mail_konten.jpg      | Einstellungen — Mail & Konten / Mailkonten        |
| 13b_einst_mail_signaturen.jpg | Einstellungen — Mail & Konten / Signaturen        |
| 14_einst_integrationen.jpg    | Einstellungen — Integrationen                     |
| 15_einst_automationen.jpg     | Einstellungen — Automationen (aktiv)              |
| 16_einst_sicherheit_audit.jpg | Einstellungen — Sicherheit & Audit (neu)          |
| 17_einst_protokoll_logs.jpg   | Einstellungen — Protokoll & Logs                  |

---

## RESEARCH-VALIDIERUNG (Internet-Recherche 2026-03-31)

### Activity-Drawer / Live-Status (✅ Plan bestätigt + Verfeinerungen)

- **Cursor 2.0** nutzt exakt das geplante Muster: Header-Chip + Slide-In-Sidebar mit Named-Agent-Liste
- **Konsens:** Kein Chat-UI für Hintergrundaktionen — stattdessen **async "Inbox"-Metapher** (wie Task-Manager, nicht Terminal)
- **"Needs You"**-Sektion (ausstehende Genehmigungen) muss **visuell getrennt** von der Aktivitätsliste sein
- **Empty State** der Genehmigungsqueue ist genauso wichtig wie gefüllter State → "Keine Aktionen offen" gibt Ruhe

### AI-Ausgang / Approval (✅ Plan bestätigt + Ergänzungen)

- **"Intent Preview Card"**: Zeige immer eine kurze Begründung — "Warum hat Kira das erstellt?" (z.B. "Angebot seit 7 Tagen ohne Rückmeldung")
- **Inline-Editing** vor Freigabe ist Standard — kein Wechsel in neues Fenster, sondern direkt in der Vorschaukarte bearbeiten
- **Kein Bulk-Approve in Phase 1** — erst wenn Muster eingefahren sind

### Kalender (✅ Option A = Graph API bestätigt)

- Microsoft iframe-Embed = schlechte UX, kein Styling
- **Richtig:** Graph API `/me/calendarView` mit eigenem Mini-Widget ("Today's schedule"-Strip mit 3–5 Events)
- ICS als Fallback möglich wenn OAuth noch nicht erteilt

### Modal/Popup (✅ Plan bestätigt, Konkretisierung)

- Overlay: `rgba(0,0,0,0.5)` Minimum — opaker ist besser für modale Entscheidungen
- **3-Schritte-Regel** für Wizard-Modals: max. 3 Screens, Back-Button behält Daten
- **Nicht-destruktive** Modals (Settings) → Klick auf Overlay schließt; **Destruktive** (Senden, Löschen) → nur expliziter Button
- Modaltitel immer als **"Was passiert hier?" in ≤5 Wörtern** formulieren

### Einstellungen UI — 3-Pane-Layout (Outlook-Referenz)

- **NEU: 3-Pane-Ansicht** (wie Outlook-Einstellungen, Referenz-Screenshot):
  - **Pane 1** (links, ~200px): Haupt-Kategorien (Design, Benachrichtigungen, Kira/LLM, Mail & Konten …)
  - **Pane 2** (Mitte, ~220px): Sub-Items der gewählten Kategorie (z.B. bei Mail & Konten: Mailkonten / Signaturen / Vorlagen / …)
  - **Pane 3** (rechts, flex:1): Inhalt des gewählten Sub-Items — kein Tabs-Scrollen mehr nötig
- Das 3-Pane-Prinzip **überall wo sinnvoll anwenden** — insbesondere Mail & Konten, Kira/LLM, Protokoll & Logs
- Inline-Tooltips (ℹ-Button) auf **jedem** nicht-offensichtlichen Parameter (bereits umgesetzt in Phase 2)
- **Progressive Disclosure:** "Erweiterte Einstellungen anzeigen" für Power-User

---

## DESIGN-LEITLINIEN (gilt für alle neuen UI-Komponenten)

### Farben & Stil (Dark + Light Mode)

- **Immer nur CSS-Variablen verwenden** — niemals Farben hardcoden. Die Variablen wechseln automatisch mit dem Theme.
- **Dunkel:** `var(--bg)` ≈ `#18181b`, `var(--bg-raised)` ≈ `#232328`, `var(--bg-overlay)` ≈ `#2a2a30`
- **Hell:** `var(--bg)` ≈ `#f5f5f7`, `var(--bg-raised)` ≈ `#ffffff`, `var(--bg-overlay)` ≈ `#ffffff`
- **Akzent:** `var(--accent, #4f7df9)` — Blau für aktive Elemente (beide Themes)
- **Status:** `var(--success, #1D9E75)`, `var(--warning, #EF9F27)`, `var(--error, #E24B4A)`
- **Borders:** `1px solid var(--border)` / `var(--border-strong)` für betonte Trennlinien
- **Schatten:** `0 4px 24px rgba(0,0,0,.4)` dunkel, `0 4px 24px rgba(0,0,0,.15)` hell — via `var(--shadow-modal)`
- **Overlay-Dimmer:** immer `rgba(0,0,0,.72)` — auch im Hell-Modus schafft das die nötige visuelle Trennung

### Fenster & Modals (OAuth-Assistenten-Stil)

- **NICHT transparent** — vollständig opaker Hintergrund: `var(--bg-overlay)` oder `var(--bg-raised)`
- **Overlay-Dimmer:** `rgba(0,0,0,.72)` (wie `.kira-wiz-overlay` in server.py:5265) — nicht `.45`
- **Rahmen:** `border-radius: 16px`, `border: 1px solid var(--border-strong)`
- **Breite:** Modal max. 620px (wie OAuth-Assistent), Drawer max. 420px
- **Header:** dunkler Streifen mit Icon + Titel + Schliessen-Button
- **Inhalt:** Klare Abschnitte mit `<hr>` oder `padding: 20px`
- **Aktionen:** Primary-Button rechts, Secondary/Cancel links — immer sichtbar unten

### Kira-Sprechweise in der UI

- **KEIN Technik-Jargon:** Keine Begriffe wie `scan_angebot_followup_vorgang`, `actor_type`, `TTL`
- **Stattdessen:** "Kira prüft Angebote auf Nachfass-Bedarf", "Kira wartet auf Bestätigung"
- **Status-Chips:** Kurze, aktive Formulierungen — max. 30 Zeichen

---

## STATUS: WAS BEREITS UMGESETZT IST

### Phase 1 — Implementierungs-Pakete (aus Hauptplan, Backend)

| Paket | Feature                                                      | Status  |
| ----- | ------------------------------------------------------------ | ------- |
| P2    | `mail_approve_queue` Tabelle (HITL-Gate)                     | ✅ done |
| P2    | `_api_mail_approve_pending` + `_api_mail_approve_action`     | ✅ done |
| P8    | `graph_calendar.py` — `erstelle_termin()`, `liste_termine()` | ✅ done |
| P9    | `_api_kira_aktivitaeten()` mit CSV-Export                    | ✅ done |

### Phase 2 — Einstellungen erweitert (session-oo)

| Sektion                    | Was wurde hinzugefügt                                                                  | Status  |
| -------------------------- | -------------------------------------------------------------------------------------- | ------- |
| Kira/LLM/Provider          | Gruppe: Konversations-Gedächtnis (4 Settings)                                          | ✅ done |
| Kira/LLM/Provider          | Gruppe: Proaktive Automatisierung (6 Settings)                                         | ✅ done |
| Kira/LLM/Provider          | Gruppe: ReAct & Multi-Step (2 Settings)                                                | ✅ done |
| Kira/LLM/Provider          | Gruppe: Feedback & Lernen (3 Settings)                                                 | ✅ done |
| Kira/LLM/Provider          | Gruppe: Sicherheit & Limits (3 Settings)                                               | ✅ done |
| Nav-Leiste                 | "Automationen" (ohne "Geplant"-Badge)                                                  | ✅ done |
| Nav-Leiste                 | "Sicherheit & Audit" (neuer Eintrag)                                                   | ✅ done |
| Automationen               | 6 Scan-Status-Zeilen + Manuelle Aktionen                                               | ✅ done |
| Sicherheit & Audit         | Circuit Breaker Status, Log-Settings, CSV-Export                                       | ✅ done |
| Mail & Konten              | Tabs (Mailkonten / Mail-Monitor / Klassifizierung / Signaturen / Archiv / Sync)        | ✅ done |
| Mail & Konten > Signaturen | Signatur-Editor, Konto-Zuordnung, Standard-Flag                                        | ✅ done |
| `saveSettings()` JS        | kira.memory, kira.react, kira.feedback, kira.sicherheit, kira_proaktiv                 | ✅ done |
| API GET                    | `/api/kira/circuit_breaker`                                                            | ✅ done |
| API POST                   | `/api/kira/proaktiv/scan`, `/api/kira/circuit_breaker/reset`, `/api/kira/memory/reset` | ✅ done |

### Noch NICHT umgesetzt (Einstellungen)

| Sektion       | Was fehlt                                                                       |
| ------------- | ------------------------------------------------------------------------------- |
| Mail & Konten | Gruppe "Kira-Postfach" (Kira sendet von: Konto-Auswahl + Kira-Ausgang anzeigen) |
| Mail & Konten | Gruppe "Mail-Vorlagen" (Vorlagen-Liste + Editor + Kira-Anbindung)               |
| Mail & Konten | Gruppe "Signatur-Zuordnung" (Vorlage → Signatur)                                |
| Integrationen | Microsoft Graph Kalender Scope + Einstellungen                                  |

---

## PHASE 3 — KIRA-POSTFACH (Approval-Queue im Postfach)

### Ist-Zustand (03_postfach.jpg) — **✅ PHASE 3 VOLLSTÄNDIG IMPLEMENTIERT (2026-03-31)**

- Postfach hat 3-Pane-Ansicht: Ordnerleiste links, Mail-Liste Mitte, Mail-Viewer rechts
- Fluent-Ribbon mit vollständigen Aktions-Buttons
- Aktive Ordnermarkierung ✅
- **Kira-Ausgang-Gruppe** in Ordnerleiste: Entwürfe, Gesendet, Abgelehnt, Abgelaufen ✅
- Badge "2" bei offenen Entwürfen ✅
- Kira-Mail-Viewer: gelber Banner, Betreff/Empfänger, Body-Text, Aktionsbuttons ✅
- Ribbon-Gruppe "Kira-Entwurf": Freigeben/Bearbeiten/Ablehnen — erscheint NUR bei Kira-Mail ✅
- Bearbeiten-Modal mit editierbarer Textarea ✅
- Header-Badges "2 Freigaben" + "X Freigabe" ✅
- Leer-Zustand zeigt "Keine Einträge vorhanden" statt "Kein Ordner ausgewählt" ✅
- API-Endpunkte `/api/mail/approve/pending` + `/api/mail/approve/{id}` aktiv ✅
- Getestet 2026-03-31 mit Playwright (2 Entwürfe + 1 Gesendet, danach gelöscht) ✅

### Soll-Zustand

**Neue Ordnergruppe "Kira-Ausgang"** in der Ordnerleiste (unter regulären Ordnern):

```
── Kira-Ausgang ──────────
  📝 Entwürfe        (3)   ← pending
  ✅ Gesendet              ← sent
  ❌ Abgelehnt             ← rejected
  ⏰ Abgelaufen            ← expired
```

**Klick auf einen Kira-Ordner** → zeigt mail_approve_queue-Einträge in der Mail-Liste:

- Gleiche Liste-Optik wie reguläres Postfach (Von, Betreff, Datum, Vorschau)
- "Von" = "Kira" mit Kira-Icon
- Status-Badge statt Gelesen/Ungelesen

**Kira-Entwurf im Viewer** (READ-ONLY-Stil):

- Header: "Kira-Entwurf — wartet auf Freigabe" (gelber Balken)
- Mail-Inhalt anzeigen (body_plain / body_html)
- Aktionsleiste am unteren Rand des Viewers:
  - **[✅ Senden]** — öffnet Bestätigungs-Modal (OAuth-Stil, opak)
  - **[✎ Bearbeiten]** — öffnet Edit-Modal (OAuth-Stil, opak, Textarea vorausgefüllt, Ausgangskonto zuweisung bearbeiten, signatur zuweisen bearbeiten etc)
  - **[❌ Ablehnen]** — mit optionalem Kommentar-Feld

**Approve-Modal (OAuth-Assistent-Stil):**

```
┌─────────────────────────────────┐
│  ✅ Mail freigeben               │
│─────────────────────────────────│
│  An: kunde@beispiel.de          │
│  Betreff: Nachfass Angebot 2026  │
│                                 │
│  [Vorschau des Mail-Textes]     │
│  …                              │
│                                 │
│  [Abbrechen]    [Jetzt senden ▶]│
└─────────────────────────────────┘
```

- Hintergrund: `var(--bg-overlay)`, Overlay: `rgba(0,0,0,.72)`
- Keine Transparenz im Modal-Body

**Ribbon-Integration:**

- Wenn Kira-Entwurf ausgewählt: Ribbon-Gruppe "Kira" einblenden mit [✅ Freigeben] [❌ Ablehnen] [✎ Bearbeiten]
- Wenn reguläre Mail: Ribbon-Gruppe "Kira" ausblenden

**Einstellungen (Mail & Konten — noch zu ergänzen):**

```
Gruppe: Kira-Postfach
  [ ] Kira-Ausgangsbereich im Postfach anzeigen  (default: ein)
  [Auswahl] Kira sendet von: [Konto auswählen ▼]
```

### Betroffene Code-Stellen

- `build_postfach()` (server.py:1025) — Ordnerleiste um Kira-Gruppe erweitern
- `pfLoadFolderList()` JS — Kira-Ordner-Gruppe rendern
- `pfLoadMailList()` JS — bei Kira-Ordner-Auswahl: `/api/mail/approve/pending?status=X` laden
- `pfShowMail()` JS — Kira-Viewer-Modus mit Aktionsleiste
- `build_einstellungen()` — Mail & Konten: Gruppe "Kira-Postfach" ergänzen

---

## PHASE 4 — KIRA LIVE-STATUS (Activity-Chip + Drawer)

### Ist-Zustand (10_kira_chat_vollbild.jpg)

- Kira ist als Launcher-Button (128px, Charakter-Stil B) sichtbar
- Chat-Modal öffnet sich bei Klick — halbdurchsichtiger Overlay (`rgba(28,28,26,.45)`)
- Kein Status-Chip im Header
- Kein "Kira arbeitet..."-Anzeige
- Kein Activity-Drawer
- Mail-Badge (`approve_pending`) ist nicht im Header sichtbar

### Soll-Zustand

#### 4-A: Kira-Live-Chip im Header

Rechts vom Suchfeld, links von den Badges:

```html
<div
  id="kira-live-chip"
  class="kira-chip kira-chip--idle"
  onclick="kiraDrawerOpen()"
>
  <!-- Zustand wechselt dynamisch: -->
  idle: ✅ Kira bereit scanning: 🔄 Kira analysiert… pending: ⚡ 2 Aktionen
  offen error: ⚠ Kira nicht erreichbar
</div>
```

- Polling: `setInterval(loadKiraStatus, 15000)` — GET `/api/kira/proaktiv/status`
- Animierter Spin-Icon bei `scanning`-Zustand (CSS `@keyframes spin`)

#### 4-B: Mail-Approve-Badge im Header

- Badge neben dem vorhandenen Glocken-Badge: "📬 3" bei pending > 0
- Klick → öffnet direkt Postfach > Kira-Ausgang > Entwürfe
- Polling: `setInterval(loadApproveBadge, 30000)` — GET `/api/mail/approve/pending`

#### 4-C: Activity-Drawer (Slide-In von rechts, NICHT modal)

Öffnet bei Klick auf Live-Chip — schiebt Inhalt NICHT weg, liegt drüber.
**Wichtig (Research):** Async "Inbox"-Metapher, kein Chat-UI. "Needs You"-Sektion klar visuell getrennt.

```
┌──────────────────────────────┐  ← Slide-In von rechts, 400px breit
│  🤖 Kira — Was läuft gerade?  [×]│
│──────────────────────────────│
│  ⚡ DEINE BESTÄTIGUNG NÖTIG (2)   │  ← hervorgehoben, oben
│  ─────────────────────────────   │
│  📬 Nachfass-Mail – Müller         │
│     Angebot seit 8 Tagen ohne     │  ← Begründung = Intent Preview
│     Rückmeldung                   │
│     [Anzeigen & freigeben ▶]      │
│                                   │
│  📬 Mahnung – Bauer GmbH          │
│     Rechnung 14 Tage überfällig   │
│     [Anzeigen & freigeben ▶]      │
│  ─────────────────────────────   │
│  Laufend                          │
│  🔄 Angebote prüfen  [stoppen]    │
│                                   │
│  Letzte Aktionen                  │
│  ✓ Mail klassifiziert  10:32      │
│  ✓ Aufgabe erstellt    10:28      │
│  ✓ Scan abgeschlossen  10:15      │
│                                   │
│              [Alle Aktivitäten ▶] │
└──────────────────────────────┘
```

- Wenn keine offenen Aktionen: "✅ Keine Aktionen offen" (Empty-State = beruhigend)
- Hintergrund: `var(--bg-overlay)` — OPAK, nicht transparent
- Schließen: Klick auf "×" oder außerhalb
- Animiert: `transform: translateX(0)` ↔ `translateX(100%)`
- Daten von: `/api/kira/aktivitaeten?seit=1h` + `/api/mail/approve/pending`
- Sprache: KEIN Technik-Jargon — menschliche Formulierungen

#### 4-D: "Kira kommt in Vordergrund" (User-Präsenz)

- `document.addEventListener('visibilitychange', ...)` — wenn Tab aktiv wird
- Wenn pending Stufe-B-Signale vorhanden + User ist aktiv: Toast einblenden
  - Toast-Text: "Kira hat 2 Aktionen, die deine Bestätigung brauchen" [Anzeigen]
- Einstellbar: Kira / LLM / Provider > Proaktive Automatisierung > "Kira darf aktiv auffordern"

#### Chat-Modal: Overlay-Stil anpassen (OAuth-Assistent)

- Aktuell: `rgba(28,28,26,.45)` → Ändern auf: `rgba(0,0,0,.72)`
- Chat-Panel selbst bleibt gleich, nur Overlay-Dimmer wird opaker

### Betroffene Code-Stellen

- `build_dashboard()` oder globaler Header-HTML-Bereich — Live-Chip + Mail-Badge
- Globaler JS-Bereich — `loadKiraStatus()`, `loadApproveBadge()`, `kiraDrawerOpen()`
- CSS — `.kira-chip`, `.kira-drawer`, `@keyframes spin`
- `.kira-workspace-overlay` (server.py:11616) — Overlay-Alpha von `.45` auf `.72`

---

## PHASE 5 — UI-GESAMTÜBERARBEITUNG (Panel für Panel)

### 5-A: Dashboard (01_dashboard.jpg)

**Ist:** Tagesbriefing-Leiste, KPI-Karten, priorisierte Liste
**Problem:** Kira-Status fehlt, statisch, kein Live-Element
**Soll:**

- Live-Chip im Header (Phase 4-A)
- Kira-Briefing-Karte: statt "Aktualisieren"-Button → kleines Live-Indikator-Dot wenn scan läuft
- KPI-Karten: "Kira-Postfach"-Karte hinzufügen wenn pending > 0 (zeigt Anzahl Entwürfe)
- Kalender-Widget-Kachel (Phase 6) unten rechts

### 5-B: Kommunikation (02_kommunikation.jpg)

**Ist:** Tab-Filter, Tasks mit Kategorie-Badges, Kira-Button pro Item
**Problem:** "Kira fragen"-Buttons wirken isoliert
**Soll:**

- "Kira fragen"-Buttons bleiben, werden aber mit Live-Kontext verknüpft
- Beim Klick: Chat-Modal öffnet sich mit vorausgefülltem Task-Kontext (existiert bereits in Code:10364)
- Kleines Status-Badge wenn Kira gerade an einem Task arbeitet

### 5-C: Postfach (03_postfach.jpg)

**Ist:** Vollständiges 3-Pane-Postfach, Fluent-Ribbon, Ordnergruppen
**Problem:** Kein Kira-Ausgang
**Soll:** → Phase 3

### 5-D: Organisation (04_organisation.jpg)

**Ist:** Timeline / Fristen / Rückrufe / Kalender-Tabs
**Problem:** Kalender-Tab ist leer / Platzhalter
**Soll:**

- Kalender-Tab: Echte Daten von Graph-API (Phase 6) Hier eine vollständige Anleitung als datei ausgeben wenn einrichting notwendig!
- "Termin erstellen" Button → öffnet Termin-Modal (OAuth-Assistent-Stil)
- Kira kann Terminvorschläge direkt in diesen Tab einblenden

### 5-E: Geschäft (05_geschaeft.jpg)

**Ist:** KPI-Übersicht, Vorgänge-Liste, Signale-Panel
**Problem:** Signale-Panel zeigt "Geplant"-Platzhalter für Autonomy-Vorschläge
**Soll:**

- Signale-Panel: Echte Kira-Vorschläge aus `vorgaenge.signals`-Tabelle
- Klick auf Signal → öffnet Vorgang-Detail (existiert: `_api_vorgang_detail`)
- Kira-Vorschlag-Karte: zeigt Konfidenz, Aktion, [Bestätigen] / [Ablehnen]

### 5-F: Wissen (06_wissen.jpg)

**Ist:** Bibliothek, Regelkarten mit Ein/Aus-Toggle
**Problem:** Kein Feedback-Loop-UI (👍/👎) auf Regelkarten
**Soll:**

- 👍/👎-Buttons unter jeder Kira-Antwort im Chat
- Im Wissen-Panel: Regelkarten zeigen "Von Kira gelernt am..." Badge
- Suchfeld für Regeln (existiert als Kira-Tool, aber kein UI)

### 5-G: Kira-Chat (09/10)

**Ist:** Quick-Actions Overlay + Chat-Modal (Sidebar + Chat)
**Problem:**

- Kein Kontext-Panel zeigt aktuellen Vorgang/Kunden
- Chat-Overlay-Dimmer ist halbdurchsichtig (`.45`)
- Keine 👍/👎-Feedback-Buttons unter Antworten
  **Soll:**
- Kontext-Sidebar: "Aktueller Kontext" — Vorgang-Karte wenn relevant, Kunden-Infos
- Overlay-Alpha: `.72` (opaker = professionalerer Look)
- 👍/👎 nach jeder Kira-Antwort (klein, dezent)
- Bei laufendem ReAct-Loop: Fortschrittsbalken in der Sidebar

### 5-H: Kira-Aktivitäten (07_kira_log.jpg)

**Ist:** Leere Timeline-Ansicht (keine Kira-autonomen Aktionen bisher)
**Problem:** Wird erst leben wenn P4/P8/P9 implementiert
**Soll (für jetzt):** Bleibt, wird nach Paket 4 befüllt — Design ist OK

---

## PHASE 6 — KALENDER-INTEGRATION

### Optionen-Abwägung

| Option                                      | Komplexität       | UX-Qualität | Empfehlung                                                                                                                                                                                                                                                                                                                                        |
| ------------------------------------------- | ----------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A: Mini-Widget im Dashboard**             | Niedrig           | Gut         | ✅ Zuerst umsetzen                                                                                                                                                                                                                                                                                                                                |
| **B: Eigener Kalender-Tab in Organisation** | Mittel            | Sehr gut    | ✅ danach umsetzen                                                                                                                                                                                                                                                                                                                                |
| **C: Outlook iframe embed**                 | Hoch (CORS, Auth) | Exzellent   | ✅ danach umsetzen , nur wenn dann ohne einrichtung bei einer Verkaufsversion möglich ist.. klar zugangsdaten oth schon, aber nicht grapf/entra/azur erforderlich bei endkunde --- -- kunde soll im Menü wählen können welche art kalender, für den fall er sit nicht bei microsoft -- Was meinst du, bitte feadback und recherche ob umsetzbar!! |

### Option A: Dashboard-Kachel (Priorität 1)

- Neue KPI-Kachel rechts unten: "Nächste Termine"
- Daten von `/api/kira/termine` → `graph_calendar.liste_termine()` (graph_calendar.py:118 ✅ bereits vorhanden)
- Zeigt max. 5 Termine als Liste: Datum | Uhrzeit | Betreff
- "+ Termin erstellen" → öffnet Termin-Modal (OAuth-Assistent-Stil)
- Graceful Fallback wenn Graph-Token fehlt: "Verbinde Microsoft-Konto unter Einstellungen > Integrationen"

### Option B: Kalender-Tab in Organisation (Priorität 2)

- Tab "Kalender" (existiert in 04_organisation.jpg aber ohne Inhalt)
- Monatsansicht: einfaches CSS-Grid mit Tagen, Termine als Dots
- Tages-Details per Klick (Slide-In)
- Kira kann Termine via `termin_erstellen`-Tool eintragen

### Termin-Modal (OAuth-Assistent-Stil)

```
┌────────────────────────────────────┐
│  📅 Termin erstellen                │
│────────────────────────────────────│
│  Betreff: [___________________]    │
│  Datum:   [__.__.__]  Uhrzeit: [__]│
│  Bis:     [__:__] (optional)       │
│  Ort:     [___________________]    │
│  Notiz:   [___________________]    │
│                                    │
│  Konto:   [info@raumkult.eu ▼]     │
│                                    │
│  [Abbrechen]   [In Outlook eintragen ▶]│
└────────────────────────────────────┘
```

- Opak: `var(--bg-overlay)`, Dimmer: `rgba(0,0,0,.72)`
- Nach Erfolg: Toast "Termin erstellt — in Outlook eingetragen"

### Einstellungen (Integrationen — zu ergänzen)

```
Gruppe: Microsoft Graph — Kalender
  [ ] Kalender-Integration aktiv
  [Status] Berechtigung Calendars.ReadWrite: [Prüfen ▶]
  ℹ️ Kira kann Termine in deinen Outlook-Kalender eintragen.
     Verbindung wird beim nächsten Konto-Login erteilt.
```

---

## PHASE 7 — MAIL-VORLAGEN & KIRA-ANBINDUNG

### Konzept

Kira nutzt Vorlagen für ausgehende Mails — je nach Typ automatisch die passende Vorlage.

### Vorlagen-Typen (vordefiniert, anpassbar)

| Vorlagen-Typ        | Automatische Nutzung durch Kira    |
| ------------------- | ---------------------------------- |
| Angebots-Nachfass   | Scan 6: Angebot-Followup           |
| Mahnung             | Scan 7: Mahnung-Eskalation         |
| Allgemein           | Standard wenn kein Typ passt       |
| Auftragsbestätigung | Wenn Vorgang-Status → "beauftragt" |

### Einstellungen Mail & Konten — neue Gruppe

```
Tab: Vorlagen  [neu]
─────────────────────────────────────────
Gruppe: Kira-Postfach
  [ ] Kira-Ausgangsbereich im Postfach anzeigen
  [Auswahl] Kira sendet von: [Konto auswählen ▼]

Gruppe: Mail-Vorlagen
  [Vorlagen-Liste]
  ID | Typ | Name | Aktiv | Signatur | Aktionen
  1  | Nachfass | Standard-Nachfass | ✅ | Standard rauMKult | [Bearbeiten] [Kopieren] [Löschen]

  [+ Neue Vorlage]

Gruppe: Vorlage bearbeiten (Modal, OAuth-Assistent-Stil)
```

### Vorlagen-Editor Modal

- Betreff-Feld mit Platzhaltern: `{{kunde_name}}`, `{{vorgang_nr}}`, `{{datum}}`
- Rich-Text oder Plain-Text-Editor (Textarea)
- Signatur-Zuordnung: Dropdown
- Kira-Freigabe: [ ] Kira darf diese Vorlage autonom verwenden
- Vorschau-Button

---

## PHASE 8 — BELEGVORLAGEN (Zukunft)

**Status:** Zurückgestellt — nach Phase 3-7
**Konzept:** Eigene Panel-Seite (ähnlich Einstellungen) mit Vorlagen-Editor für Angebote, Rechnungen, etc. (ähnlich wie Lexware Office)
**Einstellungen:** Neuer Tab in Einstellungen

---

## FENSTER & POPUP-STANDARD (Design-Referenz)

Alle neuen Fenster/Modals in KIRA 2.0 folgen diesem Standard:

### Kira-Standard-Modal (opak, OAuth-Stil)

```css
.kira-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.72); /* NICHT .45 — opak */
  display: flex;
  align-items: center;
  justify-content: center;
}
.kira-modal {
  background: var(--bg-overlay);
  border: 1px solid var(--border-strong);
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.6);
  width: min(620px, 92vw);
  max-height: 80vh;
  overflow-y: auto;
}
.kira-modal-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  font-size: 15px;
}
.kira-modal-body {
  padding: 20px;
}
.kira-modal-footer {
  padding: 14px 20px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
```

### Kira-Standard-Drawer (Slide-In, nicht modal)

```css
.kira-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(420px, 90vw);
  z-index: 400;
  background: var(--bg-overlay);
  border-left: 1px solid var(--border-strong);
  box-shadow: -8px 0 32px rgba(0, 0, 0, 0.4);
  transform: translateX(100%);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.kira-drawer.open {
  transform: translateX(0);
}
```

---

## ZUSAMMENFASSUNG: PRIORISIERTE REIHENFOLGE

| Phase               | Was                                 | Aufwand        | Priorität  |
| ------------------- | ----------------------------------- | -------------- | ---------- |
| **Phase 3**         | Kira-Postfach im Postfach-Panel     | 1 Session      | 🔴 Hoch    |
| **Phase 4**         | Kira Live-Chip + Activity-Drawer    | 1 Session      | 🔴 Hoch    |
| **Phase 5-C/G**     | Postfach + Chat-Modal-Fix (Overlay) | Teil von P3/P4 | 🔴 Hoch    |
| **Phase 5-A/E**     | Dashboard + Geschäft (Signale)      | 0.5 Sessions   | 🟡 Mittel  |
| **Phase 7**         | Mail-Vorlagen + Einstellungen       | 1 Session      | 🟡 Mittel  |
| **Phase 6-A**       | Kalender-Kachel Dashboard           | 0.5 Sessions   | 🟡 Mittel  |
| **Phase 6-B**       | Kalender-Tab Organisation           | 0.5 Sessions   | 🟡 Mittel  |
| **Phase 5-B/D/F/H** | Übrige Panel-Verbesserungen         | 1 Session      | 🟢 Niedrig |
| **Phase 8**         | Belegvorlagen                       | Zukunft        | ⬜ Später  |

---

## NÄCHSTE SCHRITTE (zur Bestätigung durch Kai)

```
Nach Freigabe dieses Plans:

Phase 3 + 4 (zusammen, da eng verknüpft):
  [ ] Kira-Ausgang in Postfach-Ordnerleiste
  [ ] Kira-Entwurf-Viewer mit Aktionsleiste
  [ ] Approve-Modal (OAuth-Stil, opak)
  [ ] Live-Chip im Header
  [ ] Activity-Drawer (opaker Slide-In)
  [ ] Mail-Approve-Badge im Header
  [ ] Chat-Modal Overlay-Alpha .45 → .72
  [ ] Einstellungen Mail & Konten: Kira-Postfach-Gruppe + Vorlagen-Tab

Phase 5 (UI-Overhaul pro Panel):
  [ ] Dashboard Kira-Kachel
  [ ] Geschäft: Signale-Panel mit echten Kira-Vorschlägen
  [ ] Chat: 👍/👎 Feedback-Buttons
  [ ] Organisation/Kalender: Vorbereitung für Phase 6

Phase 6:
  [ ] API-Endpunkt /api/kira/termine → graph_calendar.liste_termine()
  [ ] Kalender-Kachel im Dashboard
  [ ] Kalender-Tab im Organisation-Panel
  [ ] Termin-Modal (OAuth-Stil)
  [ ] Einstellungen Integrationen: Graph-Kalender-Gruppe

Phase 7:
  [ ] Mail-Vorlagen Datenstruktur (config.json oder neue DB-Tabelle)
  [ ] Einstellungen: Mail & Konten Tab "Vorlagen" + Editor-Modal
  [ ] Kira-Anbindung: _tool_mail_senden() nutzt passende Vorlage
```

---

_Dieser Plan ist zur Bestätigung durch Kai. Keine weitere Implementierung ohne Freigabe._
