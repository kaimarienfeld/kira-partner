# KAI_TODO_LEXWARE.md — Alle Aktionen die nur Kai ausfuehren kann

Stand: 2026-04-01 05:45
Session: session-eee (Lexware Office Nacht-Session)

> Diese Datei wird von Claude Code automatisch befuellt.
> Kai muss NICHTS davon waehrend der Nacht erledigen — alles ist gesammelt fuer den naechsten Arbeitstag.
> Reihenfolge: erst 1, dann 2, dann 3 — sonst funktioniert das Modul nicht vollstaendig.

---

## PRIORITAET 1 — OHNE DAS FUNKTIONIERT NICHTS

### KAI-01: Lexware Office API-Key in KIRA hinterlegen

**Was:** Den persoenlichen Lexware Office API-Key in KIRA Einstellungen > Lexware Office eintragen.

**Wo den Key finden:**
1. Einloggen auf https://app.lexoffice.de
2. Oben rechts: Profil / Einstellungen
3. "Apps & Schnittstellen" → "LexOffice API"
4. Bestehenden Key kopieren ODER neuen Key erstellen

**Wichtig:**
- Der alte Key aus den PHP-Dateien (01_lex_billb_fetch_invoices.php) sollte NICHT mehr verwendet werden
  da er auf dem Webserver liegt und oeffentlich einsehbar war
- Besser: Neuen Key erstellen und den alten deaktivieren
- Der neue Key gehort NUR in KIRA Einstellungen (nicht auf den Webserver!)

**Wo in KIRA eintragen:**
→ Einstellungen > Lexware Office > API-Verbindung > API-Key Feld

**Sicherheitshinweis:**
Der alte Key M_DdX... aus den PHP-Dateien sollte in Lexware widerrufen werden.

---

### KAI-02: Neuen Lexware API-Key erstellen und alten widerrufen

**Was:** Sicherheitsmassnahme — der alte Key war im Klartext auf dem Webserver.

**Schritte:**
1. https://app.lexoffice.de aufrufen
2. Einstellungen > Apps & Schnittstellen > LexOffice API
3. Alten Key "Widerrufen" oder "Loeschen"
4. "Neuen API-Key erstellen"
5. Key sofort kopieren (wird nur einmal angezeigt!)
6. In KIRA Einstellungen > Lexware Office einfuegen (KAI-01)

---

## PRIORITAET 2 — FUER VOLLE FUNKTIONALITAET

### KAI-03: Dataverse-Verbindung pruefen (optional, fuer Dataverse-Export)

**Was:** Falls der Dataverse-Export weiter genutzt werden soll, muss gecheckt werden ob die
Azure-Credentials noch gueltig sind.

**Hintergrund:**
- Tenant-ID: 2d79d7b6-... (aus PHP-Dateien bekannt)
- Org-URL: https://orge14a61e1.crm16.dynamics.com
- Die App-Credentials (Client-ID + Secret) aus den PHP-Dateien sind veraltet

**Schritte:**
1. Azure Portal oeffnen: https://portal.azure.com
2. Azure Active Directory > App-Registrierungen
3. App `42b5e93e-...` suchen — existiert sie noch?
4. Falls ja: Client Secret pruefen (ablaufdatum)
5. Falls Secret abgelaufen: Neues Secret erstellen
6. Neue Credentials in KIRA Einstellungen > Lexware Office > Dataverse eintragen

**Entscheidung noetig:** Soll der Dataverse-Export ueberhaupt weiter genutzt werden?
Wenn nein → KAI-03 und KAI-04 ueberspringen.

---

### KAI-04: PHP-Altstrecke auf Webserver deaktivieren (optional)

**Was:** Die 5 PHP-Dateien (00-04) auf dem Webserver k8bykk7yun24/public_html laufen noch.
Wenn KIRA die Lexware-Anbindung uebernimmt, ist die PHP-Strecke redundant.

**Entscheidung:** Soll die alte PHP-Strecke:
- [ ] Weiter laufen (Cron-Job bleibt aktiv)
- [ ] Deaktiviert werden (Cron-Job anhalten)
- [ ] Geloescht werden

**Falls deaktivieren:**
1. Auf Hosting-Panel einloggen (k8bykk7yun24)
2. Cron-Jobs > Cron fuer 00_lex_billb_master.php deaktivieren
3. PHP-Dateien ggf. in Unterordner _archiv/ verschieben

---

### KAI-05: Lexware Webhook-URL einrichten (wenn Echtzeit-Updates gewuenscht)

**Was:** Fuer sofortige Benachrichtigung wenn Belege in Lexware erstellt/geaendert werden.

**Voraussetzung:** KIRA muss oeffentlich erreichbar sein (localhost ist nicht genug).
Optionen:
- ngrok-Tunnel (fuer Test: `ngrok http 8765`)
- Feste externe URL (falls Kai einen Server/VPS hat)

**In Lexware einrichten:**
1. https://app.lexoffice.de > Einstellungen > Apps & Schnittstellen > Webhooks
2. URL: https://[deine-domain]/api/webhook/lexware
3. Events: Alle oder nur: voucher.created, voucher.updated, contact.created

**In KIRA eintragen:**
→ Einstellungen > Lexware Office > Webhooks > URL + Secret

---

## PRIORITAET 3 — SPAETER / OPTIONAL

### KAI-06: Billbee-Integration pruefe (falls weiter benoetigt)

**Was:** Die PHP-Strecke schickte Rechnungen auch an Billbee.
Wenn Billbee weiter genutzt wird, muss geklart werden ob das weiter ueber PHP oder ueber KIRA laufen soll.

---

### KAI-07: Azure Entra App fuer Kalender-Zugriff (Outlook-Kalender)

**Was:** Bereits dokumentiert in frueheren Sessions.
Azure App a0591b2d braucht Calendars.ReadWrite Delegated Permission.
(Nicht Lexware-spezifisch, aber zusammen erledigen.)

---

## ZUSAMMENFASSUNG

| Prioritaet | Task | Beschreibung | Zeit |
|-----------|------|-------------|------|
| ⚡ 1 | KAI-01 | Lexware API-Key in KIRA eintragen | 5 Min |
| ⚡ 1 | KAI-02 | Alten API-Key widerrufen + neuen erstellen | 5 Min |
| 📋 2 | KAI-03 | Dataverse pruefen (optional) | 15 Min |
| 📋 2 | KAI-04 | PHP-Altstrecke deaktivieren (optional) | 10 Min |
| 📋 2 | KAI-05 | Lexware Webhook einrichten (optional) | 10 Min |
| 🕐 3 | KAI-06 | Billbee-Entscheidung | nach Bedarf |
| 🕐 3 | KAI-07 | Azure Entra Kalender | bekannt |

**Empfehlung fuer Kai morgen frueh:**
1. Schritt KAI-02 zuerst (Sicherheit!)
2. Schritt KAI-01 (KIRA aktivieren)
3. KIRA Einstellungen > Lexware Office > Verbindung testen
4. Dann alles andere nach Bedarf
