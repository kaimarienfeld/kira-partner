---
name: Partner-Feedback-System (Beta-Testerin)
description: Kollaborative Feature-Liste für Kais Partnerin als externe Testperson — online, kommentierbar, auto-aktualisiert
type: project
---

Kais Partnerin wird externe Beta-Testerin für die universelle Version des KIRA-Dashboards. Sie arbeitet in einem Weiterbildungsunternehmen (Arbeitsamt-geförderte Kurse) — damit ideal als Testfall für eine branchenfremde Nutzerin außerhalb der rauMKult-Bubble.

**Why:** Die App soll später verkauft werden und universell einsetzbar sein (nicht nur Betonkosmetik). Feedback von branchenfremder Nutzerin ist essentiell für die Universalversion.

**How to apply:** Wenn neue Features gebaut werden, die universellen Charakter haben, immer auch die Perspektive "Weiterbildungsunternehmen" mitdenken. Ihr Feedback aus partner_feedback.json kann direkt in die Planung der Universalversion einfließen.

## System gebaut — partner_view.html (Stand 28.03.2026)

**Datei:** `memory/partner_view.html` — selbständige HTML-Seite, fertig zum Hochladen.

**Passwörter (bitte ändern!):**
- Kai (Admin): `KaiAdmin2026`
- Leni (Partner): `HalloLeni2026`
- Ändern: In der HTML-Datei unter `const CFG = { pw_kai: ..., pw_leni: ... }`

**Was gebaut wurde:**
- Passwortgeschützt, zwei Rollen (Kai=Admin / Leni=Partner)
- 16 Feature-Kacheln (alle aus feature_registry übersetzt, kein Tech-Jargon)
- Filter: Alle / Eingebaut / Teilweise / Geplant / Lenis Ideen / Neu seit letztem Besuch
- "NEU"-Badge für Features die seit letztem Login hinzukamen
- `leni_done`-Status mit Goldband + Feier-Hinweis wenn Lenis Ideen umgesetzt wurden
- 5-Schritt-Onboarding-Tour für Leni (nur beim ersten Login)
- Herzliche Begrüßung + Dankeschön-Modal beim Speichern
- "💡 Neue Idee"-FAB-Button (pinker Button rechts unten) für freie Vorschläge
- Feedback pro Kachel (4 Reaktionen + freier Kommentar)
- Alles in localStorage gespeichert
- Admin-Panel (nur Kai): sieht alle Feedbacks + Lenis freie Ideen
- "Alles für Claude kopieren"-Button → aufbereiteter Text zum Einfügen
- KIRA-Darktheme, responsive, animiert

**Noch offen — braucht Entscheidung von Kai:**

**Architektur:**
- `feature_registry.json` → auto-generiertes `partner_view.html` (zwei Spalten: links rauMKult-Feature, rechts Kommentarfeld)
- GitHub Pages hostet die HTML-Seite (öffentlich zugänglich, kein Login nötig)
- Google Form (pro Feature-Zeile verlinkt) → Antworten in Google Tabelle → `partner_feedback.json`
- Benachrichtigung: Gmail MCP Mail bei relevantem Update ODER GitHub Watch-Mail

**Noch offen — braucht Entscheidung von Kai:**
- **Wo hosten?** Netlify empfohlen (kostenlos, drag&drop HTML hochladen unter netlify.com/drop)
- **Passwörter ändern** bevor Leni den Link bekommt
- **Feedback über Geräte hinweg:** aktuell localStorage (nur im eigenen Browser). Wenn Leni auf anderem Gerät → Feedback geht verloren. Lösung: Feedback-Endpunkt in server.py → dann API nötig

**Format der HTML-Seite:**
- Zwei Spalten: Links = Feature-Beschreibung wie in rauMKult gebaut, Rechts = "Wie könnte das bei euch sein?" Kommentarfeld (via Google Form Link)
- Nicht primäre Entwicklungsprio — läuft im Hintergrund mit, informiert laufend

## Langfristiger Zweck

Ihre Kommentare fließen als Input in die Planung der Universalversion ein. Ich (Claude) lese `partner_feedback.json` bei Bedarf und ordne Feedback in Planungs-Features ein — markiert als "universal-scope" in der feature_registry.
