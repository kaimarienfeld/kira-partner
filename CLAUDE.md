# claude.md — Verbindliche Arbeitsregeln für Claude Code

> Immer lesen vor Arbeitsbeginn. Stand: 

---

## 1. Pflicht-Ablauf jeder Session

Hat vorang: "C:\Users\kaimr\.claude\CLAUDE.md"

### Alle Checklisten, überall was Tracking betrifft und Logging Daten immer:

[DATUM] [UHRZEIT] bei log Einträgen 

## und bei Listen 

✅ Erledigt — [Aufgaben-Titel] · [DATUM] [UHRZEIT] Was genau

⚠️ Offen geblieben | [Was nicht fertig wurde — warum: —]

**Status:** 🐛✅ Behoben oder ⚠️ Offen geblieben (session-sss, commit ...)
**Gefunden am:** [DATUM] [UHRZEIT] MEZ
**Beschreibung:** 
**Fix:** Verständlich.
**Behoben am:** [DATUM] [UHRZEIT] MEZ  wenn ⚠️ Offen geblieben:Begründen

## 2. Umlaute-Regel (seit 2026-04-02)

**PFLICHT:** In allen sichtbaren App-Texten (HTML-Labels, Tooltips, Beschreibungen, Fehlermeldungen, Buttons, Dialoge) immer echte deutsche Umlaute verwenden:
- ä ö ü ß Ä Ö Ü — RICHTIG
- ae oe ue ss — FALSCH in sichtbarem Text

**Ausnahme:** Python-Variablen, DB-Spalten, API-Pfade, JS-Funktionsnamen dürfen ASCII bleiben (faellig, loeschen, ueberfaellig).

```


