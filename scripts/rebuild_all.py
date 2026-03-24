#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rauMKult / Kira – Vollstaendiger Neuaufbau der Aufgaben-Datenbasis.
Loescht alte Tasks, liest alle Mails aus kunden.db + sent_mails.db,
klassifiziert mit neuer Logik, baut tasks.db sauber neu auf.
"""
import sqlite3, json, sys
from pathlib import Path
from datetime import datetime, timedelta

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
sys.path.insert(0, str(SCRIPTS_DIR))

from mail_classifier import (classify_mail, extract_email, is_system_sender,
                              kategorie_to_task_typ)
from response_gen import generate_draft

TASKS_DB  = KNOWLEDGE_DIR / "tasks.db"
KUNDEN_DB = KNOWLEDGE_DIR / "kunden.db"
SENT_DB   = KNOWLEDGE_DIR / "sent_mails.db"

DAYS_TASKS  = 30   # Tasks fuer die letzten N Tage
DAYS_GESCH  = 180  # Geschaeftsdaten fuer die letzten N Tage

EIGENE_DOMAINS = {"raumkult.eu","sichtbeton-cire.de","raumkultsichtbeton.onmicrosoft.com"}

# ======================================================================
# 1. DATENBANK-SCHEMA
# ======================================================================
def rebuild_schema(db):
    """Loescht alte Daten und erstellt saubere Tabellen."""
    db.executescript("""
        DROP TABLE IF EXISTS tasks;
        DROP TABLE IF EXISTS task_kira_context;
        DROP TABLE IF EXISTS corrections;
        DROP TABLE IF EXISTS organisation;
        DROP TABLE IF EXISTS geschaeft;
        DROP TABLE IF EXISTS wissen_regeln;

        CREATE TABLE tasks (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            typ               TEXT NOT NULL,
            kategorie         TEXT NOT NULL,
            titel             TEXT NOT NULL,
            zusammenfassung   TEXT,
            beschreibung      TEXT,
            kunden_email      TEXT,
            kunden_name       TEXT,
            absender_rolle    TEXT,
            empfohlene_aktion TEXT,
            kategorie_grund   TEXT,
            message_id        TEXT,
            mail_folder_pfad  TEXT,
            anhaenge_pfad     TEXT,
            antwort_entwurf   TEXT,
            claude_prompt     TEXT,
            betreff           TEXT,
            konto             TEXT,
            datum_mail        TEXT,
            status            TEXT DEFAULT 'offen',
            prioritaet        TEXT DEFAULT 'mittel',
            antwort_noetig    INTEGER DEFAULT 0,
            erstellt_am       TEXT DEFAULT CURRENT_TIMESTAMP,
            aktualisiert_am   TEXT DEFAULT CURRENT_TIMESTAMP,
            erledigt_am       TEXT,
            naechste_erinnerung TEXT,
            erinnerungen      INTEGER DEFAULT 0,
            notiz             TEXT
        );
        CREATE INDEX idx_tasks_status ON tasks(status);
        CREATE INDEX idx_tasks_typ    ON tasks(typ);
        CREATE INDEX idx_tasks_kat    ON tasks(kategorie);
        CREATE INDEX idx_tasks_email  ON tasks(kunden_email);
        CREATE INDEX idx_tasks_msgid  ON tasks(message_id);

        CREATE TABLE task_kira_context (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id      INTEGER NOT NULL,
            kai_input    TEXT,
            kira_antwort TEXT,
            erstellt_am  TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE corrections (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id     INTEGER NOT NULL,
            alter_typ   TEXT,
            neuer_typ   TEXT,
            notiz       TEXT,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE organisation (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id     INTEGER,
            typ         TEXT,
            datum_erkannt TEXT,
            beschreibung TEXT,
            kunden_email TEXT,
            betreff     TEXT,
            konto       TEXT,
            mail_ref    TEXT,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE geschaeft (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            typ              TEXT,
            rechnungsnummer  TEXT,
            datum            TEXT,
            betrag           REAL,
            gegenpartei      TEXT,
            gegenpartei_email TEXT,
            status           TEXT DEFAULT 'offen',
            quelle           TEXT DEFAULT 'mail',
            betreff          TEXT,
            konto            TEXT,
            mail_ref         TEXT,
            notiz            TEXT,
            erstellt_am      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_gesc_typ    ON geschaeft(typ);
        CREATE INDEX idx_gesc_datum  ON geschaeft(datum);

        CREATE TABLE wissen_regeln (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            kategorie      TEXT,
            titel          TEXT,
            inhalt         TEXT,
            status         TEXT DEFAULT 'aktiv',
            erstellt_am    TEXT DEFAULT CURRENT_TIMESTAMP,
            bestaetigt_am  TEXT
        );
    """)
    # Zusätzliche Tabellen (IF NOT EXISTS - überleben Rebuilds)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS ausgangsrechnungen (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            re_nummer       TEXT UNIQUE,
            datum           TEXT,
            kunde_email     TEXT,
            kunde_name      TEXT,
            betrag_netto    REAL,
            betrag_brutto   REAL,
            betreff         TEXT,
            mail_ref        TEXT,
            anhaenge_pfad   TEXT,
            status          TEXT DEFAULT 'offen',
            bezahlt_am      TEXT,
            mahnung_count   INTEGER DEFAULT 0,
            letzte_mahnung  TEXT,
            notiz           TEXT,
            erstellt_am     TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ar_status ON ausgangsrechnungen(status);

        CREATE TABLE IF NOT EXISTS angebote (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            a_nummer         TEXT UNIQUE,
            datum            TEXT,
            kunde_email      TEXT,
            kunde_name       TEXT,
            betrag_geschaetzt REAL,
            betreff          TEXT,
            mail_ref         TEXT,
            anhaenge_pfad    TEXT,
            status           TEXT DEFAULT 'offen',
            nachfass_count   INTEGER DEFAULT 0,
            letzter_nachfass TEXT,
            naechster_nachfass TEXT,
            notiz            TEXT,
            grund_abgelehnt  TEXT,
            grund_angenommen TEXT,
            erstellt_am      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ang_status ON angebote(status);

        CREATE TABLE IF NOT EXISTS geschaeft_statistik (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            typ         TEXT,
            referenz_id INTEGER,
            ereignis    TEXT,
            daten_json  TEXT,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.commit()


# ======================================================================
# 2. GESENDETE MAILS LADEN  (fuer Antwort-Check)
# ======================================================================
def load_sent_index(since: str) -> dict:
    """Gibt {email: [datum, ...]} zurueck fuer gesendete Mails."""
    sent = {}
    try:
        sdb = sqlite3.connect(str(SENT_DB))
        sdb.row_factory = sqlite3.Row
        rows = sdb.execute("""SELECT kunden_email, datum FROM gesendete_mails
            WHERE datum >= ? ORDER BY datum""", (since,)).fetchall()
        sdb.close()
        for r in rows:
            em = (r["kunden_email"] or "").lower()
            if em:
                sent.setdefault(em, []).append(r["datum"])
    except Exception as e:
        print(f"  Warnung: sent_mails.db nicht lesbar: {e}")
    return sent


def was_answered(email: str, datum: str, sent_index: dict) -> bool:
    """Prüft ob an diese email NACH datum eine Mail gesendet wurde."""
    dates = sent_index.get(email.lower(), [])
    return any(d > datum for d in dates)


# ======================================================================
# 3. INTERAKTIONEN LESEN + KLASSIFIZIEREN
# ======================================================================
def classify_and_build(db, since_tasks: str, since_gesch: str, sent_index: dict):
    """Liest interaktionen aus kunden.db, klassifiziert, baut Tasks + Geschaeft."""
    kdb = sqlite3.connect(str(KUNDEN_DB))
    kdb.row_factory = sqlite3.Row

    rows = kdb.execute("""SELECT * FROM interaktionen
        WHERE datum >= ? ORDER BY datum DESC""", (since_gesch,)).fetchall()
    kdb.close()

    stats = {"gesamt": len(rows), "tasks": 0, "ignoriert": 0,
             "geschaeft": 0, "organisation": 0, "zur_kenntnis": 0}
    seen_msgids = set()

    for r in rows:
        folder = r["folder"] or ""
        is_sent = "Gesendete" in folder or "Sent" in folder
        konto  = r["konto_label"] or ""
        absnd  = r["absender"] or ""
        betr   = r["betreff"] or ""
        text   = r["text_plain"] or ""
        k_email= (r["kunden_email"] or "").lower()
        datum  = r["datum"] or ""
        msgid  = r["message_id"] or ""

        # Duplikat-Check
        if msgid and msgid in seen_msgids:
            continue
        if msgid:
            seen_msgids.add(msgid)

        # Eigene-Domain-Mails ignorieren
        if k_email:
            dom = k_email.split('@')[-1] if '@' in k_email else ''
            if dom in EIGENE_DOMAINS:
                continue

        # Klassifizieren
        cl = classify_mail(konto, absnd, betr, text, folder=folder, is_sent=is_sent)
        kat = cl["kategorie"]
        task_typ = kategorie_to_task_typ(kat)

        # ── Geschaeftsdaten immer extrahieren ──
        if cl.get("geschaeft") and datum >= since_gesch:
            g = cl["geschaeft"]
            db.execute("""INSERT INTO geschaeft
                (typ, rechnungsnummer, datum, betrag, gegenpartei, gegenpartei_email,
                 betreff, konto, mail_ref)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (g.get("typ",""), g.get("rechnungsnummer",""), datum,
                 g.get("betrag"), r["kunden_name"] or k_email, k_email,
                 betr[:120], konto, msgid))
            stats["geschaeft"] += 1

        # ── Organisationsdaten extrahieren ──
        if cl.get("organisation") and datum >= since_tasks:
            org = cl["organisation"]
            for org_typ in ("termin","frist","rueckruf"):
                if org.get(org_typ):
                    val = org[org_typ] if isinstance(org[org_typ], str) else ""
                    db.execute("""INSERT INTO organisation
                        (typ, datum_erkannt, beschreibung, kunden_email, betreff, konto, mail_ref)
                        VALUES (?,?,?,?,?,?,?)""",
                        (org_typ, val, betr[:120], k_email, betr[:120], konto, msgid))
                    stats["organisation"] += 1

        # ── Tasks nur fuer letzte N Tage, nur wenn Handlungsbedarf ──
        if datum < since_tasks:
            continue

        if kat in ("Ignorieren","Newsletter / Werbung","Abgeschlossen"):
            stats["ignoriert"] += 1
            continue

        if kat == "Zur Kenntnis":
            stats["zur_kenntnis"] += 1
            continue

        if kat in ("Shop / System","Rechnung / Beleg") and not cl["antwort_noetig"]:
            # Nur als geschaeft/zur kenntnis, kein aktiver Task
            stats["zur_kenntnis"] += 1
            continue

        # Wenn schon beantwortet -> kein Task
        if k_email and was_answered(k_email, datum, sent_index):
            continue

        # Entwurf nur fuer antwortwuerdige Mails
        entwurf = ""
        claude_prompt = ""
        if cl["antwort_noetig"] and k_email:
            try:
                draft = generate_draft(betr, absnd, text, k_email)
                entwurf = draft.get("entwurf","")
                claude_prompt = draft.get("claude_prompt","")
            except:
                pass

        # Kundenname extrahieren
        kunden_name = r["kunden_name"] or ""

        db.execute("""INSERT INTO tasks
            (typ, kategorie, titel, zusammenfassung, beschreibung,
             kunden_email, kunden_name, absender_rolle, empfohlene_aktion,
             kategorie_grund, message_id, mail_folder_pfad, anhaenge_pfad,
             antwort_entwurf, claude_prompt, betreff, konto, datum_mail,
             prioritaet, antwort_noetig)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (task_typ, kat, betr[:120] or f"Mail von {k_email}",
             cl["zusammenfassung"], text[:1000],
             k_email, kunden_name, cl["absender_rolle"],
             cl["empfohlene_aktion"], cl["kategorie_grund"],
             msgid, r["mail_folder_pfad"] or "", r["anhaenge_pfad"] or "",
             entwurf[:4000], claude_prompt[:2000],
             betr[:120], konto, datum,
             cl["prioritaet"], 1 if cl["antwort_noetig"] else 0))
        stats["tasks"] += 1

    db.commit()
    return stats


# ======================================================================
# 4. WISSEN-GRUNDREGELN ANLEGEN
# ======================================================================
def seed_wissen(db):
    regeln = [
        ("fest","Keine Preise in der Erstantwort",
         "Auf neue Anfragen niemals Preise, m2-Preise oder Preisranges nennen. "
         "Stattdessen: Einordnung, Moeglichkeiten, Aufwandseinfluss, naechster Schritt."),
        ("fest","Anrede nach Kundensprache",
         "Kunde duzt -> wir duzen. Kunde siezt -> wir siezen. Unklar -> professionell, freundlich."),
        ("fest","Kein KI-Sound",
         "Keine Floskeln, keine uebertriebenen Fachbegriffe, keine belehrende Sprache. "
         "Natuerlich, klar, direkt, handwerklich-praktisch formulieren."),
        ("fest","Verbotene Formulierungen",
         "Nie: 'fundierte Einschaetzung', 'Wir schauen uns das fachlich an', "
         "'gerne koennen wir Ihnen ein unverbindliches Angebot erstellen'"),
        ("fest","Erst Einordnung, dann Entwurf",
         "Kommunikationsfenster: Zuerst Zusammenfassung + Einschaetzung zeigen, "
         "dann Kai-Input abwarten, erst danach Entwurf erstellen."),
        ("fest","Fotos immer anfordern",
         "Bei Anfragen ohne Fotos: Fotos aktiv anfordern (Gesamtansicht + Nahaufnahmen)."),
        ("fest","Max 3-7 Rueckfragen",
         "Bei Erstanfragen: nur Massangaben, keine Plaene. Max 3-7 kurze, priorisierte Rueckfragen."),
        ("fest","Reinigung materialschonend",
         "Reinigung immer materialschonend einordnen. Hydrophobierung nur als abschliessenden Schutzschritt."),
        ("fest","Ehrliche Grenzen",
         "Ehrliche Grenzen klar benennen. Keine erfundenen Fakten, keine erfundenen Termine."),
    ]
    for kat, titel, inhalt in regeln:
        db.execute("""INSERT INTO wissen_regeln (kategorie, titel, inhalt, status)
            VALUES (?,?,?,'aktiv')""", (kat, titel, inhalt))
    db.commit()


# ======================================================================
# 5. HAUPTPROGRAMM
# ======================================================================
def main():
    print("=" * 60)
    print("rauMKult / Kira – Datenbank-Neuaufbau")
    print("=" * 60)

    since_tasks = (datetime.now() - timedelta(days=DAYS_TASKS)).strftime("%Y-%m-%d")
    since_gesch = (datetime.now() - timedelta(days=DAYS_GESCH)).strftime("%Y-%m-%d")

    print(f"\n1. Tasks-Zeitraum:    letzte {DAYS_TASKS} Tage (ab {since_tasks})")
    print(f"   Geschaeft-Zeitraum: letzte {DAYS_GESCH} Tage (ab {since_gesch})")

    # Schema neu aufbauen
    print("\n2. Loesche alte tasks.db und baue Schema neu auf...")
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    rebuild_schema(db)
    print("   Schema erstellt: tasks, organisation, geschaeft, wissen_regeln, corrections, task_kira_context")

    # Gesendete Mails laden
    print("\n3. Lade gesendete Mails fuer Antwort-Check...")
    sent_index = load_sent_index(since_gesch)
    total_sent = sum(len(v) for v in sent_index.values())
    print(f"   {total_sent} gesendete Mails an {len(sent_index)} Empfaenger geladen")

    # Klassifizieren und aufbauen
    print("\n4. Lese + klassifiziere Interaktionen aus kunden.db...")
    stats = classify_and_build(db, since_tasks, since_gesch, sent_index)
    print(f"   Gesamt gelesen:   {stats['gesamt']}")
    print(f"   Tasks erstellt:   {stats['tasks']}")
    print(f"   Ignoriert:        {stats['ignoriert']}")
    print(f"   Zur Kenntnis:     {stats['zur_kenntnis']}")
    print(f"   Geschaeftsdaten:  {stats['geschaeft']}")
    print(f"   Organisationsdaten: {stats['organisation']}")

    # Wissen-Grundregeln
    print("\n5. Wissen-Grundregeln anlegen...")
    seed_wissen(db)
    print("   9 feste Regeln angelegt")

    # Statistik ausgeben
    print("\n6. Ergebnis-Uebersicht:")
    for row in db.execute("SELECT typ, kategorie, COUNT(*) c FROM tasks WHERE status='offen' GROUP BY typ, kategorie ORDER BY c DESC"):
        print(f"   {row['kategorie']:30s} ({row['typ']:15s}) = {row['c']}")

    n_org = db.execute("SELECT COUNT(*) FROM organisation").fetchone()[0]
    n_ges = db.execute("SELECT COUNT(*) FROM geschaeft").fetchone()[0]
    n_wis = db.execute("SELECT COUNT(*) FROM wissen_regeln").fetchone()[0]
    print(f"\n   Organisation: {n_org} Eintraege")
    print(f"   Geschaeft:    {n_ges} Eintraege")
    print(f"   Wissen:       {n_wis} Regeln")

    db.close()
    print("\n" + "=" * 60)
    print("Fertig. Dashboard neu laden: http://localhost:8765")
    print("=" * 60)


if __name__ == "__main__":
    main()
