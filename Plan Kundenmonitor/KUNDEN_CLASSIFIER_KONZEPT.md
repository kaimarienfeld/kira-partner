# Kunden-Classifier — Konzept

Stand: 2026-04-10 (aktualisiert session-tt: Lexware-Only-Basis)

---

## Zweck

Jede neue Aktivität (Mail, Memo, Dokument) wird analysiert und einem Kunden + Projekt + Fall-Typ zugeordnet. Kein reines Regel-Matching — kontextbewusstes Verständnis durch LLM.

**REGEL-09: Lexware ist die einzige Kunden-Stammdatenquelle.** Kunden kommen ausschließlich aus Lexware Office — NICHT aus dem Mail-Archiv.

---

## Datenfluss

```
Lexware Office (273 Kontakte)
    │
    └── kunden_lexware_sync.py
          │
          ├── kunden.db/kunden (lexware_id gesetzt)
          └── kunden.db/kunden_identitaeten
                ├── E-Mails (confidence='eindeutig', quelle='lexware')
                ├── Domains (confidence='wahrscheinlich', quelle='lexware')
                └── Telefon  (confidence='eindeutig', quelle='lexware')
```

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
    └── 3. Kunden-Classifier (kunden_classifier.py)
          │
          ├── Fast-Path Stufe 1: Exakter Email-Match
          │   Absender in kunden_identitaeten (typ='mail')
          │   WHERE k.lexware_id IS NOT NULL
          │   → Sofort zuordnen, kein LLM
          │
          ├── Fast-Path Stufe 2: Domain-Match
          │   Absender-Domain in kunden_identitaeten (typ='domain')
          │   → Zuordnen mit confidence='wahrscheinlich'
          │
          └── LLM-Path: Super-Prompt
              → NUR Lexware-Kunden als Kontext
              → JSON-Response auswerten
              → Nach Confidence handeln
```

---

## Fast-Path (kein LLM nötig)

Stufe 1 — Exakter Email-Match:
```python
row = db.execute("""
    SELECT ki.kunden_id, ki.confidence, k.name, k.firmenname
    FROM kunden_identitaeten ki
    JOIN kunden k ON k.id = ki.kunden_id
    WHERE LOWER(ki.wert) = ? AND ki.typ = 'mail'
      AND k.lexware_id IS NOT NULL  -- NUR Lexware-Kunden
    LIMIT 1
""", (absender_email.lower(),)).fetchone()
```

Stufe 2 — Domain-Match (Fallback):
```python
row = db.execute("""
    SELECT ki.kunden_id, 'wahrscheinlich' as confidence, k.name, k.firmenname
    FROM kunden_identitaeten ki
    JOIN kunden k ON k.id = ki.kunden_id
    WHERE LOWER(ki.wert) = ? AND ki.typ = 'domain'
      AND k.lexware_id IS NOT NULL
    LIMIT 1
""", (domain.lower(),)).fetchone()
```

---

## LLM-Kontext (nur Lexware-Kunden)

```python
kunden = db.execute("""
    SELECT k.id, k.name, k.firmenname, k.email, k.kundentyp, k.status, k.letztkontakt
    FROM kunden k
    WHERE k.status != 'archiv'
      AND k.lexware_id IS NOT NULL AND k.lexware_id != ''
    ORDER BY k.letztkontakt DESC NULLS LAST
    LIMIT 50
""", ()).fetchall()
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

## Lexware-Sync

| Script | Zweck |
|---|---|
| `kunden_lexware_sync.py` | Lexware Office → kunden.db (Import/Update) |
| `kunden_mail_retroaktiv.py` | Mail-Archiv gegen Kundenliste scannen |

Sync-Ablauf:
1. Liest `tasks.db/lexware_kontakte` (bereits via `lexware_client.py` synchronisiert)
2. INSERT/UPDATE in `kunden.db/kunden` (alle mit `lexware_id`)
3. Alle E-Mails + Domains + Telefon → `kunden_identitaeten`

Trigger:
- Manuell: POST /api/crm/lexware-sync
- Automatisch: kira_proaktiv.py (6h-Intervall, wenn `crm.lexware_sync=true`)

---

## Performance-Regeln

1. **Fast-Path zuerst** — bekannte E-Mail = kein LLM
2. **Domain-Match als Stufe 2** — Geschäfts-Domains (nicht Freemail)
3. **Cache** — gleiche Absender+Betreff-Kombi → 1h Cache
4. **Kunden-Kontext kompakt** — max 50 Kunden, nur Lexware-verifizierte
5. **Günstigstes Modell** — Haiku/kleine Modelle bevorzugen (REGEL: kein Prio-Provider)

---

## Kira lernt aus Korrekturen

Wenn Kai eine Zuordnung manuell korrigiert:
1. `kunden_classifier_log.user_bestaetigt = 1` + `user_korrektur_*` setzen
2. Wenn Absender bisher `confidence='unklar'` → auf `wahrscheinlich` hochstufen
3. Wenn 3+ Korrekturen zum gleichen Kunden → `confidence='eindeutig'` in kunden_identitaeten
