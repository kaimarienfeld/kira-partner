# KAI_TODO_MOBIL — Offene Aktionen nach session-hhh

> Erstellt: 2026-04-01 11:00

## Pflicht-Aktionen (ohne diese funktioniert die Mobile-App nicht)

### 1. Mobil-Passwort setzen
- **Datei:** `scripts/secrets.json`
- **Schluessel:** `mobil_password`
- **Aktion:** Beliebiges Passwort eintragen, z.B. `"mobil_password": "kira2026"`
- **Warum:** Login-Screen auf /mobil prueft gegen dieses Passwort. Ohne Eintrag: Login schlaegt fehl.

### 2. Capture-Modul aktivieren
- **Weg:** Einstellungen → Mobil → "Capture-Modul aktiv" einschalten → Speichern
- **Optional:** Auto-Analyse + Auto-Zuordnung aktivieren

---

## Optionale Einrichtung

### 3. Schwellwert fuer LLM-Matching
- Default: `confidence_threshold: 0.6` in config.json (capture-Sektion)
- Wenn viele False-Positives → erhoehen auf 0.75
- Wenn zu wenig Auto-Zuordnungen → senken auf 0.5

### 4. Upload-Limit anpassen
- Default: max 5 Dateien, max 10 MB pro Datei
- Konfigurierbar in Einstellungen → Mobil

---

## Technische Hinweise

- Mobile-Login ist HMAC-basiert, Session-Token laeuft nach `session_duration_hours` ab (Default: 24h)
- Upload-Verzeichnis: `knowledge/capture_files/`
- Alle Capture-Items in SQLite: `knowledge/tasks.db` (Tabellen capture_*)
- Kira-Tools `capture_suchen` und `capture_zuordnen` sind aktiv sobald Modul aktiviert

---

## Getestete Funktionen (session-hhh)

- [x] /api/capture/stats → `{heute:1, pruefung:1, ...}`
- [x] /api/capture/create → Item erstellt, ID=1
- [x] Desktop-Panel: KPI-Karten, Quick-Form, Nav-Badge
- [x] /mobil → Seite laedt mit 0 JS-Fehlern
- [x] Dashboard: 0 JS-Fehler
