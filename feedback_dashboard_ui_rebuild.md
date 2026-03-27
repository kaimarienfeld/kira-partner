---
name: Dashboard UI Rebuild – Referenzvorlagen und Vorgehensweise
description: Verbindliche Designregel: Dashboard UI wird aus komplett plan für UI Referenzvorlagen gebaut, nicht aus bestehender UI recycelt
type: feedback
---

Dashboard-UI vollständig aus Referenzvorlagen neu gebaut (nicht auf bestehender UI aufgebaut).

**Why:** Kai hat explizit gewünscht: alte UI vollständig ignorieren und gestalterisch entfernen. Referenz: `memory/komplett plan für UI/` mit HTML-Vorschau-Dateien und Screenshots.

**How to apply:**
- Referenz-HTML-Dateien in `UI als HTML Vorschau/` sind die verbindliche Quelle für CSS-Klassen, Layout-Werte und Farbcodes
- Screenshots in `Scrrenshots zur UI/` sind das visuelle Ziel
- Jede Seite hat eine eigene Referenzdatei (01_Dashboard, 02_Kommunikation, 03_Geschäft, 04_Wissen, 05_Kira-Workspace, etc.)
- Neue CSS-Klassen immer mit Modul-Prefix (z.B. `dash-` für Dashboard, `komm-` für Kommunikation)
- Alte CSS-Klassen nicht entfernen (legacy compat), aber neue Klassen für neue Elemente verwenden

**Umgesetztes Dashboard-Design (Stand 2026-03-26):**
- Light-Theme als Default (data-theme="light")
- Sidebar immer dunkel (#1C1C1A), unabhängig vom Theme
- Topbar: Globalsuche + Quick-Actions-Chip + Verbunden-Chip + Aufgaben-Chip + Avatar
- Zone A: Horizontale Briefing-Leiste mit Farb-Dots
- Zone B: 4x2 KPI-Grid mit Sparklines + Change-Badges
- Zone C: 63fr/37fr Split — Heute priorisiert | Termine + Geschäft aktuell
- Zone D: 3-Spalten Signale-Grid mit Farbvarianten (s-red/s-amber/s-blue/s-coral/s-teal)
- Kira-FAB: Lila #534AB7, K-Label + "Kira" Subtext + grüner Status-Punkt
