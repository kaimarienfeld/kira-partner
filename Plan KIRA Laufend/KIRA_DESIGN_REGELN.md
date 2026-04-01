# KIRA Design-Regeln — verbindlich fuer alle Sessions

> Erstellt: 2026-04-01 (session-ooo)
> Claude Code beachtet diese Regeln bei jeder Aenderung an server.py

---

## 1. Button-Design

### Pflicht-Standard

**Alle klickbaren Buttons:**
- Hintergrund: `#1e1e24` (Dark Mode) / `#18181c` (Light Mode)
- Text: `#f0f0f2` (Dark Mode) / `#ffffff` (Light Mode)
- Border: `1px solid rgba(255,255,255,.1)` (Dark) / `transparent` (Light)
- Hover: `#28282e` (Dark) / `#2e2e34` (Light)

**CSS-Muster:**
```css
.mein-button {
  background: #1e1e24;
  color: #f0f0f2;
  border: 1px solid rgba(255,255,255,.1);
  border-radius: 6px;
  padding: 5px 12px;
  cursor: pointer;
}
.mein-button:hover { background: #28282e; }
[data-theme="light"] .mein-button { background: #18181c; color: #fff; border-color: transparent; }
```

### Betroffene CSS-Klassen (bereits umgestellt, 2026-04-01)

| Klasse | Aenderung |
|--------|-----------|
| `.btn-primary` | War var(--accent) blau → jetzt dunkel |
| `.es-mk-btn` | War var(--accent) blau → jetzt dunkel |
| `.kira-wiz-btn-primary` | War var(--accent) blau → jetzt dunkel |
| `.pf-compose-btn` | War #3b82f6 blau → jetzt dunkel |
| `.pf-snooze-custom-btn` | War #3b82f6 blau → jetzt dunkel |

### Erlaubte Ausnahmen

| Was | Erlaubt warum |
|-----|---------------|
| `.btn-loeschen` / rot | Semantisch: destruktive Aktion |
| `.btn-done` / gruen | Semantisch: Erfolgsstatus-Aktion |
| Status-Chips (nicht klickbar) | Semantisch: zeigen Status an |
| Ampel-Anzeigen (Verbindungsstatus) | Semantisch: Farbe ist Information |
| `.btn-kira` / Kira-Tint | Kira-Branding, kein Aktionsbutton |
| Active-State-Indikatoren (Sidebar, Ordner) | Semantisch: zeigen aktiven Zustand |
| Avatar-Farben | Design-Element |
| Links mit `color:var(--accent)` | Kein Button — nur Text-Link |

### Verbote

- **NIEMALS** blaue Hintergr\u00fcnde fuer Buttons (kein #3b82f6, #2563eb, #4f7df9, var(--accent) als background)
- **NIEMALS** Emoji auf Buttons (`&#x1F4BE;`, `&#x1F916;`, etc.) — nur SVG-Icons oder Text
- **NIEMALS** hardcoded Farben ausserhalb dieser Regeln

---

## 2. Farb-Variablen (verbindlich)

Alle Farben MUESSEN CSS-Variablen nutzen (keine hardcoded Hex-Codes ausser bei Button-Dark-Standard):

| Variable | Verwendung |
|----------|-----------|
| `var(--text)` | Fliesstext, Labels |
| `var(--text-muted)` / `var(--muted)` | Hinweistexte, sekundaere Infos |
| `var(--bg)` | Seiten-Hintergrund |
| `var(--bg-raised)` | Panel-/Sidebar-Hintergrund |
| `var(--bg-card)` | Karten-Hintergrund |
| `var(--bg-modal)` | Modal-Hintergrund |
| `var(--border)` | Standard-Trenner |
| `var(--border-strong)` | Betonter Trenner |
| `var(--success)` | Erfolgs-Farbe |
| `var(--danger)` | Fehler/Loeschen-Farbe |
| `var(--warn)` | Warnungs-Farbe |
| `var(--accent)` | NUR: Links, aktive Zust\u00e4nde, Kira-Elemente |
| `var(--fs-xs/sm/base/md/lg/xl)` | Schriftgroessen |

---

## 3. Schriftgroessen

Alle Schriftgroessen in CSS-Klassen MUESSEN `var(--fs-*)` nutzen:
- `var(--fs-xs)` = 12px
- `var(--fs-sm)` = 13px  
- `var(--fs-base)` = 15px
- `var(--fs-md)` = 16px
- `var(--fs-lg)` = 18px
- `var(--fs-xl)` = 24px

**NIEMALS** hardcoded `px` in CSS-Klassen (nur inline-Styles ausnahmsweise).

---

## 4. Input-Felder (form inputs)

Alle `input`, `select`, `textarea` in KIRA-Formularen:
- Hintergrund: `var(--bg-raised)` oder `var(--bg-input, var(--bg-raised))`
- Border: `var(--border)`
- Text: `var(--text)`
- **NIEMALS** hardcoded `#0b0b0b`, `#111`, `#080808`

---

*Letzte Aenderung: 2026-04-01*
*Gilt fuer: alle Aenderungen an scripts/server.py*
