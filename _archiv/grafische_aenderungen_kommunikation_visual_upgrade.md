# Grafische Änderungen – Kommunikation Visual Upgrade
**Stand: 2026-03-26 | Commit: d96467c**

---

## Übersicht

Nach dem Kommunikation UI-Rebuild (Commit 596c4da) wurde das visuelle Niveau
der Karten und des Kontextpanels auf Dashboard-Standard angehoben.

---

## 1. Karten (Work Items) – Visuelles Upgrade

### Vorher
- Flacher Titel: 13px, Gewicht 500 (dünn)
- Tags und Sender unten in einer Zeile
- Komplette Buttonleiste direkt auf der Karte (Öffnen, Kira, Erledigt, Löschen)
- Kein Schatten, kein Hover-Glow
- Keine Empfehlung oder Einordnungsgrund in der Karte sichtbar

### Nachher
- **Titel**: 15px, `font-weight:700`, `letter-spacing:-.01em` — klar und dominant
- **Badge-Reihe oben**: Kategorie-Badges + Konto-Badge (links), Zeitstempel (rechts, 11px/500)
- **Meta-Zeile**: "Rolle: X · email@…" in gedämpfter Farbe (`--muted`)
- **Zusammenfassung**: 13px, sekundäre Textfarbe, `line-height:1.5`
- **Empfehlung** (→ Icon): Akzentfarbe (`--accent`), `font-weight:600` — direkt auf Karte sichtbar
- **Einordnungsgrund**: kursiv, gedämpft (`--muted`, `font-style:italic`)
- **Karten-Schatten**: `box-shadow: 0 1px 6px rgba(0,0,0,.14)` — Tiefe in Ruheposition
- **Hover-Glow**: `box-shadow: 0 3px 16px rgba(79,125,249,.18)` + Akzent-Rahmen
- **Auswahl-State** (`.wi.sel`): Akzent-Hintergrund + doppelter Glow-Ring

---

## 2. Buttons – Umverteilung

### Vorher
Buttonleiste direkt in der Karte (Öffnen, Kira, Erledigt, Löschen — 4 Buttons pro Karte).

### Nachher
- **Auf der Karte**: Nur 1 Schnellbutton — **"✔ Zur Kenntnis"** (klein, `wi-quick-btn`, Akzent-Stil)
- **Im rechten Kontextpanel**: Vollständige Aktionen mit Farb-Semantik aus dem `.btn`-System:

| Button | Klasse | Farbe |
|--------|--------|-------|
| Mit Kira besprechen | `btn-kira` | Akzent-Blau (transparent bg) |
| Outlook ✉ | `btn-primary` (Link) | Solides Blau |
| Mail lesen | `btn-sec` | Neutral grau |
| Erledigt | `btn-done` | Grün |
| Zur Kenntnis | `btn-kenntnis` | Blau (heller) |
| Später | `btn-later` | Amber |
| Ignorieren | `btn-ignore` | Gedämpft grau |
| Korrektur | `btn-korr` | Muted grau |
| Löschen | `btn-loeschen` | Rot |

---

## 3. Kontextpanel – Upgrades

### Vorher
- Titel: 17px, `font-weight:500`
- Buttons: Generische `.km-ctx-btn`-Klasse, alle gleich grau

### Nachher
- **Titel**: 18px, `font-weight:700`, `letter-spacing:-.01em`
- **Buttons**: Alle mit semantischen Farbklassen (gleiche `.btn`-Klassen wie restliches Dashboard)
- **Outlook-Link**: Als `<a href="mailto:...">` mit `btn-primary`-Stil, öffnet E-Mail-Client

---

## 4. CSS-Klassen (neu / geändert)

| Klasse | Beschreibung |
|--------|-------------|
| `.wi-tags-row` | Flex-Container für Badges oben in der Karte |
| `.wi-title` | Aufgewertet: 15px/700 statt 13px/500 |
| `.wi-meta` | Meta-Zeile Rolle·E-Mail |
| `.wi-empfehlung` | Empfehlung in Akzentfarbe, fett |
| `.wi-grund` | Einordnungsgrund kursiv gedämpft |
| `.wi-quick-btn` | Basis für Schnellbutton auf Karte |
| `.wi-btn-k` | Akzent-Stil für Quick-Buttons |
| `.km-ctx-title` | 18px/700 (war 17px/500) |
| `.km-ctx-actions` | Padding optimiert für `.btn`-Größen |

---

## 5. Betroffene Code-Stellen in server.py

| Bereich | Zeilen (ca.) | Beschreibung |
|---------|-------------|-------------|
| `_wi_item()` | ~647–700 | Karten-HTML komplett überarbeitet |
| CSS `.wi` Block | ~4294–4316 | Shadows, Hover, Typography upgrades |
| `selectKommItem()` JS | ~2644–2653 | Button-Set mit `.btn` Farbklassen |
| CSS `.km-ctx-title` | ~4327 | 18px/700 |
| CSS `.km-ctx-actions` | ~4353 | Kompatibilität mit `.btn` |

---

*Generiert mit Claude Code · Commit d96467c*
