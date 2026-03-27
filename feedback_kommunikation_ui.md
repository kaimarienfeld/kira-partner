---
name: feedback_kommunikation_ui
description: Visuelle Richtlinien für das Kommunikation-Panel (Karten-Design, Buttons, Typografie)
type: feedback
---

Karten im Kommunikation-Panel müssen visuell hochwertig sein — analog zur Dashboard-Qualität.

**Regel: Karten-Optik**
- Großer, fetter Titel: `font-size:15px; font-weight:700` (kein schmaler Text)
- Badges/Tags oben in der Karte (Priorität, Kategorie, Konto-Badge)
- Meta-Zeile: "Rolle: X · email@…" in gedämpfter Farbe
- Zusammenfassung: 13px, sekundäre Textfarbe
- Empfehlung (empfohlene_aktion): Akzentfarbe, fett (`color:var(--accent); font-weight:600`)
- Einordnungsgrund: kursiv, gedämpft (`font-style:italic; color:var(--muted)`)
- Karten-Schatten: `box-shadow:0 1px 6px rgba(0,0,0,.14)`
- Hover-Glow: `box-shadow:0 3px 16px rgba(79,125,249,.18)` + `border-color:var(--accent-border)`

**Why:** Ohne diese Styles sehen die Karten flach und textlich zu dünn aus — nicht passend zum hochwertigen Dashboard-Design.

**Regel: Buttons auf Karten vs. Kontextpanel**
- Auf der Karte (Liste): NUR ein Schnellbutton "Zur Kenntnis" (klein, `wi-quick-btn`)
- Im rechten Kontextpanel: Alle Aktionen mit vollem Farbset aus `.btn` Klassen:
  - Mit Kira besprechen → `btn-kira`
  - Outlook → `btn-primary` (als `<a href="mailto:...">`)
  - Mail lesen → `btn-sec` (nur wenn message_id vorhanden)
  - Erledigt → `btn-done`
  - Zur Kenntnis → `btn-kenntnis`
  - Später → `btn-later`
  - Ignorieren → `btn-ignore`
  - Korrektur → `btn-korr`
  - Löschen → `btn-loeschen`

**Why:** User-Feedback: "die button aber nicht präsent auf der mitte, sondern in das rechte feld". Karten ohne Buttonwand wirken aufgeräumt, im Kontextpanel sind alle Aktionen trotzdem vollständig erreichbar.

**How to apply:** Beim nächsten Kommunikation-UI-Rebuild oder -Update diese Aufteilung strikt einhalten. Nie die komplette Buttonleiste auf die Karten bringen.

**Regel: Typografie Kommunikation-Panel**
- Kontext-Panel-Titel: `font-size:18px; font-weight:700` (war 17px/500 — zu dünn)
- Zeitstempel auf Karten: `font-size:11px; font-weight:500`
- `.km-tg` Badges: Pill-Form, kleine Schrift (9px), Kategorie-spezifische Farben behalten

**How to apply:** Schriften großzügig und edel halten wie das Dashboard — kein "System-Look" mit dünnen, grauen Texten überall.
