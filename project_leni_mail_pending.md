---
name: Leni Willkommens-Mail ausstehend
description: Erste Mail an Leni (Link) + zweite Mail (Passwort) noch nicht versendet — wartet auf nächsten KIRA-App-Commit
type: project
---

Zwei Mails an Leni sind vorbereitet aber noch NICHT versendet.

**Trigger**: Erste Mail geht ERST raus nach dem nächsten Commit der direkt die KIRA-App betrifft (server.py, kira_llm.py, o.ä.). Nicht für Partner-View-only Änderungen.

**Mail 1 — Willkommen + Link (kein Passwort!):**
- Button im Admin-Panel > Einstellungen > "📧 Willkommens-Mail senden"
- Enthält: Link https://kaimarienfeld.github.io/kira-partner
- Info: Benachrichtigungseinstellungen direkt auf der Seite anpassbar
- Kein Passwort in dieser Mail

**Mail 2 — Passwort (separat):**
- Button im Admin-Panel > Einstellungen > "🔑 Passwort-Mail senden"
- Nur: Passwort + Link
- Separat für Sicherheit

**Voraussetzung für den Versand:**
1. SMTP muss in config.json konfiguriert sein (email_notification.smtp_server + absender_email + absender_passwort)
2. Lenis E-Mail-Adresse im Admin-Panel eintragen
3. Kira-App muss laufen (localhost:8765)

**Why:** Kai will Leni erst nach echtem KIRA-App-Fortschritt einladen — nicht für reine Partner-View-Änderungen.

**How to apply:** Bei jedem Commit prüfen: Betrifft es server.py / kira_llm.py / andere App-Logik? Wenn ja: daran erinnern dass Leni-Mail jetzt versendet werden kann.
