# KIRA Tour-System — Technische Vorlage & Anleitung

> Erstellt: 2026-04-01 (session-ooo, A-13a/b/c)
> Gilt fuer: alle Modul-Tours in KIRA

---

## 1. Architektur

### CSS
- Klassen in `CSS`-Konstante (`server.py` ab ca. Zeile 19039):
  `.kt-overlay`, `.kt-spotlight`, `.kt-box`, `.kt-progress`, `.kt-box-title`, `.kt-box-text`, `.kt-box-warn`, `.kt-box-nav`, `.kt-test-banner`, `.kt-tour-btn`

### JavaScript
- Variable `TOUR_JS` (Python-String, kein f-string) direkt nach `CSS`-Konstante
- Wird als `<script>{TOUR_JS}</script>` vor `</body>` in `generate_html()` injiziert
- Globales Objekt: `window.kira_tour` mit Methoden: `start()`, `next()`, `prev()`, `end()`, `goTo()`

### Tour-Schritte-Variablen
- Werden am Ende von `TOUR_JS` als globale JS-Variablen definiert:
  - `window.KIRA_TOUR_LEXWARE` = Lexware-Tour (21 Schritte, bereits implementiert)
- Jede neue Modul-Tour als eigene Variable: `window.KIRA_TOUR_[MODUL]`

### Tour-Button
- Im Modul-Kopfbereich: `<button class="kt-tour-btn" onclick="kira_tour.start(window.KIRA_TOUR_X,{erklaermodus:true})">Tour</button>`
- Button-Klasse: `kt-tour-btn` (dunkel, kein Blau — KIRA Design-Regeln)

---

## 2. Schrittformat

Jeder Tour-Schritt ist ein JS-Objekt mit diesen Feldern:

| Feld | Pflicht | Beschreibung |
|------|---------|--------------|
| `area` | nein | Bereichsname fuer Fortschrittsanzeige (z.B. `'Cockpit'`) |
| `title` | nein | Ueberschrift der Erklaerungsbox |
| `text` | nein | Erklaerungstext (HTML erlaubt: `<b>`, `<br>`, `&rarr;`) |
| `warn` | nein | Warnhinweis (orange) — fuer destruktive Aktionen |
| `target` | nein | CSS-Selektor des hervorzuhebenden Elements (`'#element-id'` oder `'.klasse'`) |
| `tab` | nein | Sektions-ID — wird automatisch per Klick aktiviert vor Schritt-Anzeige |

### Beispiel:
```javascript
{area: 'Cockpit', title: 'Beleg-Uebersicht',
 target: '#lx-sec-cockpit',
 tab: 'cockpit',
 text: 'Das Cockpit zeigt alle offenen Vorgaenge. Klicke einen Beleg an um Details zu sehen.',
 warn: 'Das Buchen schreibt Daten in Lexware — nicht umkehrbar.'}
```

---

## 3. Start-Optionen

`kira_tour.start(steps, opts)` akzeptiert:

| Option | Typ | Beschreibung |
|--------|-----|--------------|
| `erklaermodus` | bool | Write-Buttons sperren (`.btn-primary`, `.lx-sync-btn`) |
| `testdaten` | bool | Oranger Banner + Write-Buttons sperren |

---

## 4. Tastaturkuerzel

| Taste | Aktion |
|-------|--------|
| Pfeil rechts / unten | Naechster Schritt |
| Pfeil links / oben | Vorheriger Schritt |
| Escape | Tour beenden |

---

## 5. Runtime-Logging

Folgende Events werden automatisch in `runtime_events.db` geloggt:
- `tour_gestartet` — mit Anzahl Schritte
- `tour_schritt_N` — mit Schritttitel
- `tour_beendet` — mit Schrittnummer

---

## 6. Offene Tours (noch nicht implementiert)

| Aufgaben-ID | Modul | Variable | Status |
|-------------|-------|----------|--------|
| A-14 | Kommunikation / Postfach | `KIRA_TOUR_POSTFACH` | offen |
| A-15 | Geschaeft | `KIRA_TOUR_GESCHAEFT` | offen |
| A-16 | Wissen | `KIRA_TOUR_WISSEN` | offen |
| A-17 | Capture / Mobile Memo | `KIRA_TOUR_CAPTURE` | offen |
| A-18 | Kira-Workspace | `KIRA_TOUR_KIRA` | offen |
| A-19 | Dashboard | `KIRA_TOUR_DASHBOARD` | offen |
| A-20 | Einstellungen (alle Sektionen) | `KIRA_TOUR_EINSTELLUNGEN` | offen |
| A-21 | Partner-View / Leni | `KIRA_TOUR_PARTNER` | offen |

---

## 7. Neue Tour anlegen — Schritt fuer Schritt

1. **Modul analysieren:** Welche Bereiche gibt es? Welche Sektions-IDs (`data-lxsec`, `data-tab`, Element-IDs)?
2. **Schritte schreiben:**
   - Einfaches Deutsch, kein Jargon
   - Pro Schritt: Was sehe ich? Was kann ich tun? Was passiert dabei?
   - Loest etwas einen Lexware-/Datenbank-Schreibvorgang aus? → `warn`-Feld setzen
   - Erst Ueberblick, dann Einzelfunktionen
3. **Variable eintragen:** Am Ende von `TOUR_JS` in `server.py`:
   ```javascript
   window.KIRA_TOUR_MEINMODUL = [...];
   ```
4. **Tour-Button einbauen:** Im Modul-Kopfbereich (Python-Funktion `build_meinmodul()`):
   ```python
   <button class="kt-tour-btn" onclick="kira_tour.start(window.KIRA_TOUR_MEINMODUL,{{erklaermodus:true}})">Tour</button>
   ```
   Hinweis: Da `build_*`-Funktionen im f-string-Kontext aufgerufen werden, gilt das normale Python-Escaping.
5. **Tabelle oben aktualisieren** (Status auf "implementiert" setzen)

---

*Letzte Aenderung: 2026-04-01*
