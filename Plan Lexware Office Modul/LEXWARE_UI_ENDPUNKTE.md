# Lexware UI — API-Endpunkte (bestehend + neu)

Stand: 2026-04-01
Session: session-fff

---

## Bestehende Endpunkte (session-eee)

| Methode | Pfad | Funktion | Status |
|---------|------|----------|--------|
| GET | /api/lexware/status | Verbindungsstatus, letzte Sync | OK |
| GET | /api/lexware/belege | Liste aller Belege | OK |
| GET | /api/lexware/beleg/{id} | Einzelbeleg | OK |
| GET | /api/lexware/kontakte | Liste aller Kontakte | OK |
| GET | /api/lexware/kontakt/{id} | Einzelkontakt | OK |
| GET | /api/lexware/eingangsbelege | Pruefqueue-Liste | OK |
| GET | /api/lexware/eingangsbeleg/{id} | Einzelbeleg Pruefqueue | OK |
| POST | /api/lexware/test | Verbindung testen | OK |
| POST | /api/lexware/sync | Synchronisierung starten | OK |
| POST | /api/lexware/config/save | Config speichern | OK |
| POST | /api/lexware/eingangsbeleg/{id}/status | Status setzen | OK |
| POST | /api/lexware/eingangsbeleg/neu | Manuell anlegen | OK |

---

## Neue Endpunkte (session-fff)

| Methode | Pfad | Zweck |
|---------|------|-------|
| GET | /api/lexware/cockpit | Cockpit-Daten (KPIs + Signale zusammengefasst) |
| GET | /api/lexware/regeln | Regeln & Muster aus eingangsbelege_pruefqueue lernen |
| GET | /api/lexware/zahlungen | Zahlungsliste (lokale eingangsbelege mit is_paypal=False und Betrag) |
| GET | /api/lexware/dateien | Dateiliste aus eingangsbelege + tasks.db Anhaenge |
| GET | /api/lexware/diagnose | Strukturierter Diagnosebericht (Sync-History, Fehler, Mapping) |
| POST | /api/lexware/kira-kontext | Kira-Kontext fuer einen Datensatz aufbauen |
| POST | /api/lexware/eingangsbeleg/{id}/kira-klassifizieren | Kira klassifiziert direkt aus Pruefbeleg |

---

## Routing

Alle neuen GET-Endpunkte in do_GET() eintragen (nach bestehenden lexware-Abschnitten).
Alle neuen POST-Endpunkte in _handle_lexware_post() eintragen.
