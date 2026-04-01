# Lexware UI — Neue lx-* Komponenten und JS-Funktionen

Stand: 2026-04-01
Session: session-fff

---

## CSS-Klassen (Prefix lx-*)

### Modul-Shell
- lx-module — Hauptcontainer des Lexware-Panels
- lx-header — Modul-Kopfbereich (flex, space-between)
- lx-header-left — Titel + Statuszeile
- lx-header-right — Aktionsleiste (Suche, Sync, Kira)
- lx-title — Modultitel "Lexware Office"
- lx-status-row — Statuszeile unter Titel (Chips)
- lx-nav-sec — Sekundaere Navigationsleiste
- lx-nav-btn — Button in lx-nav-sec (active-State)

### Inhaltsflaeche
- lx-content — Tab-Content-Container
- lx-detail-panel — Detailflaeche rechts (Split-View)
- lx-split — Flex-Container fuer Liste+Detail

### Cockpit
- lx-kpi-row — KPI-Kachel-Reihe (bestehend)
- lx-kpi — einzelne KPI-Kachel (bestehend)
- lx-kpi-n — Zahl in KPI-Kachel (bestehend)
- lx-kpi-lbl — Label in KPI-Kachel (bestehend)
- lx-kpi-warn — Warn-Farbe (bestehend)
- lx-signals-panel — Warnungen/Signale rechts
- lx-signal-item — einzelnes Signal/Warning

### Tabellen und Listen
- lx-table — Datentabelle (bestehend)
- lx-tr — Tabellenzeile klickbar (bestehend)
- lx-kira-badge — lila "Kira" Badge
- lx-doc-badge — "Dok" Badge

### Buchhaltung
- lx-buch-nav — Unterbereich-Tabs Buchhaltung
- lx-buch-tab — Tab-Button (Zu pruefen / Vorbereitet etc.)
- lx-buch-content — Inhalt je Unterbereich
- lx-kira-frage — Kira-Rueckfrage-Chip in Zeile
- lx-konto-chip — Kontierungsvorschlag-Chip

### Regeln & Muster
- lx-regel-row — Regelzeile
- lx-regel-typ — Typ-Badge (feste Regel / Muster / Ausnahme)
- lx-regel-conf — Confidence-Anzeige

### Einstellungen (neue Sub-Navigation)
- lx-es-subnav — Unterbereich-Navigation in Einstellungen
- lx-es-subbtn — Sub-Navigation-Button
- lx-es-subpanel — Inhalt je Unterbereich

---

## JS-Funktionen

### Navigation
- showLexSec(id) — Unterbereich im Modul wechseln (ersetzt showLexTab fuer Hauptnavi)
- showLexBuchTab(id) — Unterbereich-Tab in Buchhaltung wechseln
- showLexEsSec(id) — Unterbereich in Einstellungen wechseln
- lxUpdateHeader() — Modul-Kopfbereich aktualisieren (Status, Badges)

### Cockpit
- lxLoadCockpit() — Cockpit-Daten laden (async, ohne Reload)
- lxCockpitSignale() — Warnungen/Signale laden

### Belege
- lxBelegDetail(id) — Detailflaeche aufmachen (nicht JSON-Modal)
- lxBelegKira(id) — "Mit Kira besprechen" fuer Beleg
- lxBeleg2Zahlung(id) — Zu Zahlungen springen

### Kontakte
- lxKontaktDetail(id) — Detailflaeche aufmachen
- lxKontaktKira(id) — Kira-Einstieg fuer Kontakt

### Artikel
- lxArtikelDetail(id) — Detailflaeche
- lxArtikelNutzen(id, typ) — "In Angebot/Rechnung nutzen"

### Buchhaltung
- lxBuchDetailFull(id) — Vollstaendige Pruef-Detailflaeche
- lxBuchKira(id) — Kira-Einstieg mit Buchaltungs-Kontext
- lxBuchBestaetigen(id, konto) — Kontierung bestaetigen
- lxLoadBuchTab(tab) — Inhalte je Buchhaltungs-Tab laden

### Regeln
- lxRegelDetail(id) — Regeldetail oeffnen
- lxRegelKira(id) — Kira-Einstieg fuer Regel
- lxRegelToggle(id, aktiv) — Regel aktivieren/deaktivieren

### Diagnose
- lxDiagRefresh() — Diagnose-Daten neu laden
- lxDiagMappingView() — Mapping-Tabelle einblenden

### Kira-Kontext
- lxOpenKiraWithContext(typ, id) — Kira oeffnen mit Lexware-Kontext
  typ: 'beleg' | 'zahlung' | 'kontakt' | 'eingangsbeleg' | 'regel' | 'diagnose'

### Filter
- lxFilterBelege() — bestehend
- lxFilterKontakte() — bestehend
- lxFilterArtikel() — bestehend
- lxFilterPruef() — bestehend
- lxFilterRegeln() — neu

---

## Neue Backend-Endpunkte (Phase 5)

Dokumentiert in LEXWARE_UI_ENDPUNKTE.md
