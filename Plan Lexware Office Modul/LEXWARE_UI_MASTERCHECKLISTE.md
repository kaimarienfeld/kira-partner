# Lexware Office UI Komplettausbau — Mastercheckliste

Stand: 2026-04-01
Session: session-fff — Autonome Nacht-Session

## Legende
[x] Erledigt | [ ] Offen | [!] Kai-Aktion | [~] In Planung / Vorbereitet

---

## Phase 0 — Session-Start
- [x] Pflichtdateien gelesen (AGENT.md, session_handoff, session_log, Arbeitsanweisungen)
- [x] session_log.md Eintrag 2026-04-01 08:00
- [x] change_log.jsonl Suche (lexware / sidebar / lx- / cockpit)
- [x] Planungsordner geprueft
- [x] Ist-Zustand aus build_lexware() analysiert

## Phase 1 — Plan-Agent
- [x] LEXWARE_UI_SESSION_PLAN.md erstellt
- [x] Ist-Zustand dokumentiert
- [x] Soll-Zustand und Scope definiert

## Phase 2 — Repo-Audit
- [x] Alle build_lexware-Funktionen kartiert
- [x] Alle /api/lexware/* Endpunkte kartiert
- [x] CSS lx-* Klassen identifiziert
- [x] JS-Funktionen inventarisiert
- [x] Sidebar-Eintrag analysiert
- [x] Einstellungs-Sektion analysiert

## Phase 3 — Gap-Analyse
- [x] LEXWARE_UI_GAP_ANALYSE.md erstellt
- [x] Alle 9 Unterbereiche bewertet
- [x] Einstellungen-Luecken kartiert

## Phase 4 — Pflicht-Plandateien
- [x] LEXWARE_UI_SESSION_PLAN.md
- [x] LEXWARE_UI_GAP_ANALYSE.md
- [x] LEXWARE_UI_MASTERCHECKLISTE.md (diese Datei)
- [x] LEXWARE_UI_KOMPONENTEN.md
- [x] LEXWARE_UI_ENDPUNKTE.md
- [x] LEXWARE_UI_ENTSCHEIDUNGEN.md
- [x] KAI_TODO_LEXWARE_UI.md

## Phase 5 — Implementierung

### Paket A — Sidebar & Modul-Shell
- [ ] Sidebar nav-lexware Badge-Logik (n_pruef + Verbindungsstatus)
- [ ] Modul-Kopfbereich links: Titel + Statuszeile (verbunden/sync/offene)
- [ ] Modul-Kopfbereich rechts: Suche + Datum + Sync + Pruefung + Diagnose + Kira
- [ ] 3-Zustand Sidebar (nicht_gebucht=unsichtbar / gesperrt=Info / freigeschaltet=voll)
- [ ] CSS lx-header, lx-header-left, lx-header-right, lx-nav-sec

### Paket B — Sekundaere Navigation + Cockpit
- [ ] Sekundaere Navigation (lx-nav-sec): 9 Pflicht + 4 In-Planung Tabs
- [ ] Cockpit: Hero-KPIs gross + Warnungen-Panel rechts + Signale
- [ ] Cockpit: Schnellaktionen (Sync, Kira, manuelle Pruefung)
- [ ] Belege: Tabelle erweitert (Faelligkeit, Kira-Spalte) + echte Detailflaeche (kein JSON-Modal)
- [ ] Kontakte: Detailflaeche + Vorgaenge + Kira-Einstieg
- [ ] Artikel: Herkunft + letzte Nutzung + Aktionen

### Paket C — Buchhaltung & Regeln
- [ ] Buchhaltung: 6 Unterbereich-Tabs (Zu pruefen / Vorbereitet / Abgelegt / Unklar / Vollautomatik / Historie)
- [ ] Buchhaltung: Kira-Rueckfrage-Badge + Kontierungsvorschlag sichtbar
- [ ] Buchhaltung: Pruef-Modal mit Kontierungs-Confirm
- [ ] Regeln & Muster: Vollstaendige Ansicht (9 Typen, Aktionen, Kira)
- [ ] Diagnose & Mapping: 3-Bereiche-Layout

### Paket D — Einstellungen 3-Spalten
- [ ] es-sec-lexware: 9 Unterbereiche als Sub-Navigation
- [ ] Unterbereich Verbindung (bestehend erweitern)
- [ ] Unterbereich Sync + Kategorien
- [ ] Unterbereich Eingangsbelege + Vollautomatik
- [ ] Unterbereich Regeln & Muster + Dataverse
- [ ] Unterbereich Diagnose + Freischaltung

### Paket E — Kira-Verzahnung
- [ ] Kira-Einstieg aus Belege (echten Kontext uebergeben)
- [ ] Kira-Einstieg aus Kontakte
- [ ] Kira-Einstieg aus Eingangsbeleg-Detail
- [ ] Kira-Einstieg aus Regeln
- [ ] Kira-Einstieg aus Diagnose
- [ ] openKiraWorkspace() mit Lexware-Kontext korrekt aufrufen

### Paket F — In-Planung-Komponenten
- [ ] Zahlungen Tab: Statushinweis + geplante Struktur sichtbar
- [ ] Dateien Tab: Statushinweis + lokale Eingangsbeleg-Dateiliste
- [ ] Auswertung / Kunden-360 / Cashflow / Kalkulation: "In Planung" Badges

## Phase 6 — Abschluss
- [ ] KIRA_SYSTEM_ANALYSE.md aktualisieren
- [ ] LEXWARE_UI_MASTERCHECKLISTE.md finalisieren
- [ ] server_map.md aktualisieren
- [ ] feature_registry.json aktualisieren
- [ ] KAI_TODO_LEXWARE_UI.md finalisieren
- [ ] session_handoff.json finalisieren
- [ ] session_log.md Abschlusseintrag
- [ ] Git Commits pro Paket
- [ ] Abschlusstabelle im Chat
