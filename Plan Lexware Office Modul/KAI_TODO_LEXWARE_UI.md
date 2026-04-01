# Kai-Aktionen: Lexware Office UI

Stand: 2026-04-01
Session: session-fff

---

## Pflicht-Aktionen (ohne diese laeuft nichts)

### KAI-01: Lexware API-Key in KIRA eintragen

**Wann:** Sobald KIRA laeuft
**Wo:** KIRA > Einstellungen > Lexware Office > Verbindung > API-Key
**Was tun:**
1. Lexware Office App oeffnen (office.lexware.de)
2. Einstellungen > Schnittstellen > API > Neuen Schluessel erstellen
3. Key kopieren
4. In KIRA einfuegen und "Verbindung testen" klicken
5. Wenn gruener Haken: Modul-Status auf "Freigeschaltet" setzen

---

### KAI-02: Modul-Status in Einstellungen setzen

**Wann:** Direkt nach KAI-01
**Wo:** KIRA > Einstellungen > Lexware Office > Freischaltung
**Was tun:**
1. Dropdown "Modul-Status" auf "Freigeschaltet" setzen
2. Speichern
3. Lexware Office in der Sidebar klicken → Vollzugang sollte erscheinen

---

## Optional (kein Blocker)

### KAI-03: Ersten Sync starten

**Wann:** Nach KAI-02
**Wo:** KIRA > Lexware Office > Cockpit > "Jetzt synchronisieren"
**Was tun:**
1. "Vollsync" klicken → alle Belege, Kontakte, Artikel werden geladen
2. Nach Sync: KPI-Zahlen im Cockpit pruefe ob plausibel
3. Belege-Tab oeffnen → Rechnungsliste sollte erscheinen

---

### KAI-04: Alten Lexware-Key aus PHP-Strecke widerrufen

**Wann:** Sobald KIRA-Strecke laeuft
**Wo:** Lexware Office > Einstellungen > Schnittstellen > API > Alter Key
**Was tun:** Key widerrufen (Sicherheit)

---

### KAI-05: Auto-Sync Intervall einstellen

**Wann:** Nach erstem Sync
**Wo:** KIRA > Einstellungen > Lexware Office > Sync
**Was tun:**
1. Intervall waehlen (Empfehlung: 60 Minuten)
2. Speichern

---

### KAI-06: Eingangsbeleg-Pruefqueue testen

**Wann:** Sobald naechste Lieferantenrechnung per Mail ankommt
**Wo:** KIRA > Lexware Office > Buchhaltung > Zu pruefen
**Erwartung:** Eingangsrechnung erscheint automatisch in Pruefqueue
**Was wenn nicht:** Einstellungen > Lexware > Eingangsbelege > Pruefqueue aktiv = An

---

### KAI-07: PayPal-Ausnahme testen

**Wann:** Sobald PayPal-Mail ankommt
**Wo:** KIRA > Lexware Office > Buchhaltung
**Erwartung:** PayPal-Bestaetigung NICHT in Pruefqueue (orange PayPal-Badge)
**Was wenn doch:** Einstellungen > Lexware > Eingangsbelege > PayPal-Ausnahme = An

---

## BLOCKIERT (warte auf externe Freigabe)

### KAI-B1: Webhooks einrichten (optional)

**Status:** Warte auf Lexware Webhook-Support
**Was noetig waere:** POST-URL in Lexware: http://[KIRA-IP]:8765/api/lexware/webhook
**Hinweis:** Lexware Office hat aktuell eingeschraenkten Webhook-Support
