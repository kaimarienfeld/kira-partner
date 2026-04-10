# Kunden-Classifier — Konzept

Stand: 2026-04-10

---

## Zweck

Jede neue Aktivität (Mail, Memo, Dokument) wird analysiert und einem Kunden + Projekt + Fall-Typ zugeordnet. Kein reines Regel-Matching — kontextbewusstes Verständnis durch LLM.

---

## Pipeline

```
Neue Mail/Memo/Dokument
    │
    ├── 1. Geschäftskontakt-Filter (mail_classifier.py)
    │     Newsletter/noreply/Marketing → kein_geschaeftsfall → STOP
    │
    ├── 2. Vorgang-Router (vorgang_router.py) — unverändert
    │
    └── 3. Kunden-Classifier (kunden_classifier.py) — NEU
          │
          ├── Fast-Path: Absender in kunden_identitaeten
          │   mit confidence='eindeutig'
          │   → Sofort zuordnen, kein LLM
          │
          └── LLM-Path: Super-Prompt
              → JSON-Response auswerten
              → Nach Confidence handeln
```

---

## Fast-Path (kein LLM nötig)

```python
def _fast_path(absender_email: str) -> dict | None:
    """Prüft ob Absender eindeutig einem Kunden zugeordnet ist."""
    row = db.execute("""
        SELECT ki.kunden_id, ki.confidence, k.name, k.firmenname
        FROM kunden_identitaeten ki
        JOIN kunden k ON k.id = ki.kunden_id
        WHERE LOWER(ki.wert) = ? AND ki.typ = 'mail'
        ORDER BY ki.confidence ASC LIMIT 1
    """, (absender_email.lower(),)).fetchone()
    
    if row and row['confidence'] == 'eindeutig':
        # Aktives Projekt finden
        projekt = db.execute("""
            SELECT id, projektname FROM kunden_projekte
            WHERE kunden_id = ? AND status = 'aktiv'
            ORDER BY aktualisiert_am DESC LIMIT 1
        """, (row['kunden_id'],)).fetchone()
        
        return {
            'kunden_id': row['kunden_id'],
            'kunden_confidence': 'eindeutig',
            'projekt_id': projekt['id'] if projekt else None,
            'projekt_confidence': 'wahrscheinlich' if projekt else 'unklar',
            'fast_path': True
        }
    return None
```

---

## LLM Super-Prompt

```
Du bist ein Geschäftsprozess-Klassifizierer für ein Handwerksunternehmen.

Analysiere diese neue Nachricht und beantworte NUR als JSON:

{
  "kunden_id": null oder ID,
  "kunden_confidence": "eindeutig|wahrscheinlich|pruefen|unklar",
  "projekt_id": null oder ID,
  "projekt_confidence": "eindeutig|wahrscheinlich|pruefen|unklar",
  "fall_typ": "anfrage|angebot|nachfass|rechnung|reklamation|maengel|streitfall|intern|freigabe|kein_geschaeftsfall",
  "ist_geschaeftsfall": true|false,
  "reasoning": "max 2 Sätze warum"
}

Bekannte Kunden und Projekte:
[KUNDEN_KONTEXT — Top 50 Kunden mit Identitäten + Projekten]

Neue Nachricht:
Absender: [ABSENDER]
Betreff: [BETREFF]
Inhalt: [INHALT_AUSZUG — max 2000 Zeichen]
Datum: [DATUM]

Wichtige Regeln:
- Mängelanzeigen gehören zum ABGESCHLOSSENEN Projekt, nicht zu einem neuen
- Newsletter, Automails, Marketing → ist_geschaeftsfall = false
- Wenn Absender bekannte Lexware-ID hat → kunden_confidence = "eindeutig"
- Zeitlicher Abstand beachten: Mail 2 Jahre nach Projektabschluss = Nachprojekt-Fall
- Nie zwei verschiedene Projekte zusammenmischen
- Bei komplett unbekanntem Absender → kunden_id = null, kunden_confidence = "unklar"
```

---

## Confidence-Auswertung

| Confidence | Aktion |
|---|---|
| `eindeutig` + `ist_geschaeftsfall=true` | Automatisch zuordnen, Aktivität in kunden_aktivitaeten |
| `wahrscheinlich` | Zuordnen + Kira-Hinweis für Kai (Toast Stufe B) |
| `pruefen` | In Prüfliste (Aktivitäten-Panel), manuelle Zuordnung nötig |
| `unklar` | In Prüfliste, kein Auto-Zuordnen |

---

## Performance-Regeln

1. **Nicht synchron bei jeder Mail** — asynchron im Hintergrund
2. **Fast-Path zuerst** — bekannte E-Mail = kein LLM
3. **Cache** — gleiche Absender+Betreff-Kombi → 1h Cache
4. **Kunden-Kontext kompakt** — max 50 Kunden, nur Name+E-Mail+Projekte
5. **Günstigstes Modell** — Haiku/kleine Modelle bevorzugen (REGEL: kein Prio-Provider)

---

## Kira lernt aus Korrekturen

Wenn Kai eine Zuordnung manuell korrigiert:
1. `kunden_classifier_log.user_bestaetigt = 1` + `user_korrektur_*` setzen
2. Wenn Absender bisher `confidence='unklar'` → auf `wahrscheinlich` hochstufen
3. Wenn 3+ Korrekturen zum gleichen Kunden → `confidence='eindeutig'` in kunden_identitaeten
