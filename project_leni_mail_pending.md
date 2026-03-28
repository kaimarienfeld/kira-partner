---
name: Leni Willkommens-Mail ausstehend
description: Erste Mail an Leni (Link) + zweite Mail (Passwort) noch nicht versendet — wartet auf nächsten KIRA-App-Commit
type: project
---

Zwei Mails an Leni sind vorbereitet aber noch NICHT versendet.

**Trigger**: Erste Mail geht ERST raus nach dem nächsten Commit der direkt die KIRA-App betrifft (server.py, kira_llm.py, o.ä.). Nicht für Partner-View-only Änderungen.

**Gmail-Entwürfe vorhanden (kaimrf@gmail.com):**
- Draft 1 (Einladung): ID `r251255831736144918` — "Dein persönlicher Einblick in KIRA wartet ✨"
- Draft 2 (Passwort): ID `r1565559517660587330` — "Dein KIRA-Passwort 🔑"
- Empfänger: marlenabraham@gmail.com — BCC: info@raumkult.eu
- Beide HTML-formatiert, Kira-Branding (dunkel/lila)
- Draft 2: Passwort-Platzhalter `[PASSWORT]` muss vor dem Senden ersetzt werden!

**Mail 1 — Willkommen + Link (kein Passwort!):**
- Gmail Draft direkt versenden ODER Button im Admin-Panel > Einstellungen > "📧 Willkommens-Mail senden"
- Enthält: Link https://kaimarienfeld.github.io/kira-partner
- Info: Benachrichtigungseinstellungen direkt auf der Seite anpassbar
- Kein Passwort in dieser Mail

**Mail 2 — Passwort (separat):**
- Gmail Draft: [PASSWORT] durch echtes Passwort ersetzen, dann senden
- Nur: Passwort + Link
- Separat für Sicherheit

**HTML-Templates gespeichert unter:**
- `knowledge/mail_templates/einladung.html` (Var: {{LINK}})
- `knowledge/mail_templates/passwort.html` (Var: {{PASSWORT}}, {{LINK}})
- `knowledge/mail_templates/benachrichtigung.html` (Var: {{TITEL}}, {{DATUM}}, {{INTRO_TEXT}}, {{FEATURES_BLOCK}}, {{LINK}})

**Voraussetzung für SMTP-Versand via server.py:**
1. SMTP in config.json konfiguriert (email_notification.smtp_server + absender_email + absender_passwort)
2. Lenis E-Mail im Admin-Panel: marlenabraham@gmail.com
3. Kira-App läuft (localhost:8765)

**Why:** Kai will Leni erst nach echtem KIRA-App-Fortschritt einladen — nicht für reine Partner-View-Änderungen.

**How to apply:** Bei jedem Commit prüfen: Betrifft es server.py / kira_llm.py / andere App-Logik? Wenn ja: daran erinnern dass Leni-Mail jetzt versendet werden kann.
