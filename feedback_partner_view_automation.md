---
name: Partner-View Automation — stehende Regel nach jedem Commit
description: Nach jedem Commit generate_partner_view.py ausführen. Push nur nach Kais Freigabe. Leni-Feedback-Prozess.
type: feedback
---

Nach jedem git commit im KIRA-Projekt: `python scripts/generate_partner_view.py` ausführen.

**Why:** Die Partner-View (Lenis Seite) muss immer den aktuellen Stand der feature_registry.json widerspiegeln. Ohne Automatisierung würde die Seite veralten und Leni falsche Informationen sehen.

**How to apply:**
- Immer nach Session-Ende + Commit ausführen (steht auch in AGENT.md Schritt 8)
- Push zu GitHub Pages (`--push`) nur nach expliziter Freigabe durch Kai — nie automatisch ohne Bestätigung
- Wenn feature_registry.json geändert wurde (neues Feature, Status-Änderung, leni_* Felder): Script MUSS laufen
- Bei reinen Code-Änderungen (server.py etc.) ohne Registry-Änderung: Script optional aber empfohlen

**Leni-Feedback-Prozess (Pflicht):**
1. Kai gibt Export-Text aus Admin-Panel → Claude prüft jeden Punkt
2. Claude formuliert verständliches Update: was macht Sinn, was nicht, warum
3. Kai gibt Freigabe → dann erst in Registry eintragen (Status `leni_idea`, niedrige Prio)
4. Umgesetzt → Status `leni_done` → generate_partner_view.py → push mit Kais OK

**Status-Werte in feature_registry.json:**
- `done` = fertig eingebaut
- `partial` = halb fertig
- `planned` = geplant
- `leni_idea` = Lenis Vorschlag, wartet auf Umsetzung
- `leni_done` = Lenis Idee wurde umgesetzt → goldenes Banner auf ihrer Seite

**Passwörter ändern:** In `scripts/config.json` unter `partner_view.partner_pw_kai` und `partner_pw_leni`. Das Script liest sie aus und injiziert sie ins HTML (noch nicht implementiert — aktuell noch hardcoded in HTML, TODO für nächste Session).
