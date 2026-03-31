#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kira – Assistenz Dashboard (v4)
http://localhost:8765
Komplett neu aufgebaut: neues DB-Schema, echtes Dashboard, funktionale Kira,
strukturiertes Geschäft, interaktives Wissen.
"""
import json, sys, os, webbrowser, threading, urllib.parse, sqlite3, re, mimetypes
from pathlib import Path
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"
KUNDEN_DB     = KNOWLEDGE_DIR / "kunden.db"
MAIL_INDEX_DB = KNOWLEDGE_DIR / "mail_index.db"
_MAIL_OAUTH_STATE = {}   # {email: {'status': 'connecting'|'ok'|'error', 'message': str}}
_BROWSE_RESULTS   = {}   # {job_id: path_or_None}
DETAIL_DB     = KNOWLEDGE_DIR / "rechnungen_detail.db"
ARCHIV_ROOT   = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\Archiv")
ALLOWED_ROOTS = [str(ARCHIV_ROOT), str(KNOWLEDGE_DIR)]
sys.path.insert(0, str(SCRIPTS_DIR))

from activity_log import log as alog, get_entries as alog_entries, get_stats as alog_stats
from runtime_log import (elog as rlog, eget as rlog_get, eget_payload as rlog_payload,
                          estats as rlog_stats, ensure_config_defaults as rlog_ensure_cfg)
from llm_response_gen import generate_draft
from kira_llm import (chat as kira_chat, get_conversations as kira_get_conversations,
                       get_conversation_messages as kira_get_messages,
                       get_api_key as kira_get_api_key, get_config as get_llm_config,
                       get_all_providers, save_provider_key, check_provider_status,
                       PROVIDER_TYPES, generate_daily_briefing,
                       _validate_model, _auto_update_model, validate_all_providers,
                       start_react_task, get_react_task_status, cancel_react_task)
from mail_monitor import start_monitor_thread, get_monitor_status, stop_monitor

PORT = 8765

# Safe migration: add message_id column to loeschhistorie if missing
try:
    _db = sqlite3.connect(str(TASKS_DB))
    _db.execute("ALTER TABLE loeschhistorie ADD COLUMN message_id TEXT")
    _db.commit()
    _db.close()
except Exception:
    pass

# Paket 7 (session-oo): FTS5 Virtual Table fuer Mail-Volltext-Suche
try:
    _mdb = sqlite3.connect(str(MAIL_INDEX_DB))
    _mdb.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS mail_fts USING fts5(
            betreff, text_plain, absender,
            content=mails,
            content_rowid=id
        )
    """)
    for _trg_sql in [
        """CREATE TRIGGER IF NOT EXISTS mail_fts_insert AFTER INSERT ON mails BEGIN
            INSERT INTO mail_fts(rowid, betreff, text_plain, absender)
            VALUES (new.id, new.betreff, new.text_plain, new.absender); END""",
        """CREATE TRIGGER IF NOT EXISTS mail_fts_delete AFTER DELETE ON mails BEGIN
            INSERT INTO mail_fts(mail_fts, rowid, betreff, text_plain, absender)
            VALUES ('delete', old.id, old.betreff, old.text_plain, old.absender); END""",
        """CREATE TRIGGER IF NOT EXISTS mail_fts_update AFTER UPDATE ON mails BEGIN
            INSERT INTO mail_fts(mail_fts, rowid, betreff, text_plain, absender)
            VALUES ('delete', old.id, old.betreff, old.text_plain, old.absender);
            INSERT INTO mail_fts(rowid, betreff, text_plain, absender)
            VALUES (new.id, new.betreff, new.text_plain, new.absender); END""",
    ]:
        try: _mdb.execute(_trg_sql)
        except Exception: pass
    _mdb.commit()
    _fts_count = _mdb.execute("SELECT COUNT(*) FROM mail_fts").fetchone()[0]
    _mdb.close()
    if _fts_count == 0:
        def _fts_rebuild_bg():
            import sqlite3 as _sq
            try:
                _c = _sq.connect(str(MAIL_INDEX_DB))
                _c.execute("INSERT INTO mail_fts(mail_fts) VALUES('rebuild')")
                _c.commit()
                _c.close()
            except Exception:
                pass
        import threading as _thr
        _thr.Thread(target=_fts_rebuild_bg, daemon=True, name="FtsRebuild").start()
except Exception:
    pass

# Paket 6 (session-oo): kira_feedback — Thumbs up/down Bewertungen
try:
    _db = sqlite3.connect(str(TASKS_DB))
    _db.execute("""
        CREATE TABLE IF NOT EXISTS kira_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            message_idx INTEGER NOT NULL,
            rating TEXT NOT NULL,
            kommentar TEXT,
            kira_antwort TEXT,
            auto_regel_id INTEGER,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _db.commit()
    _db.close()
except Exception:
    pass

# Paket 2 (session-oo): mail_approve_queue — HITL-Gate für Mail-Senden durch Kira
try:
    _db = sqlite3.connect(str(TASKS_DB))
    _db.execute("""
        CREATE TABLE IF NOT EXISTS mail_approve_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            an TEXT NOT NULL,
            betreff TEXT NOT NULL,
            body_plain TEXT,
            body_html TEXT,
            konto TEXT,
            in_reply_to TEXT,
            task_id INTEGER,
            vorgang_id INTEGER,
            erstellt_von TEXT DEFAULT 'kira',
            status TEXT DEFAULT 'pending',
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP,
            entschieden_am TEXT,
            gesendet_am TEXT,
            ablauf_am TEXT
        )
    """)
    _db.commit()
    _db.close()
except Exception:
    pass

# ── Mail-Index Column Guard ───────────────────────────────────────────────────
_MAIL_COLS_ENSURED = False

# ── IMAP-Folder-Cache (60s TTL) ────────────────────────────────────────────
import threading as _threading
_folder_cache: dict = {}        # email -> {'ts': float, 'ordner': list}
_folder_cache_lock = _threading.Lock()
_FOLDER_CACHE_TTL = 60          # Sekunden

def _ensure_mail_columns():
    """Idempotent: fügt fehlende Spalten zu mail_index.db > mails hinzu + erstellt geloeschte_protokoll."""
    global _MAIL_COLS_ENSURED
    if _MAIL_COLS_ENSURED:
        return
    _MAIL_COLS_ENSURED = True
    try:
        conn = sqlite3.connect(str(MAIL_INDEX_DB))
        for col, typedef in [
            ('flagged',       'INTEGER DEFAULT 0'),
            ('pinned',        'INTEGER DEFAULT 0'),
            ('kira_verwendet','INTEGER DEFAULT 0'),
            ('snooze_until',  'TEXT DEFAULT NULL'),
        ]:
            try:
                conn.execute(f"ALTER TABLE mails ADD COLUMN {col} {typedef}")
            except Exception:
                pass  # column already exists
        conn.commit()
        conn.close()
    except Exception:
        pass
    # Gelöschte-Protokoll-Tabelle in tasks.db sicherstellen
    _ensure_geloeschte_protokoll_table()
    # Signaturen-Tabelle sicherstellen
    _ensure_mail_signaturen_table()

def _ensure_mail_signaturen_table():
    """Erstellt mail_signaturen-Tabelle in tasks.db (idempotent)."""
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.execute("""
            CREATE TABLE IF NOT EXISTS mail_signaturen (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                konto       TEXT NOT NULL,
                name        TEXT NOT NULL,
                html        TEXT NOT NULL DEFAULT '',
                ist_default INTEGER NOT NULL DEFAULT 0,
                erstellt    TEXT NOT NULL DEFAULT (datetime('now')),
                geaendert   TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_sig_konto ON mail_signaturen(konto)")
        db.commit()
        db.close()
    except Exception:
        pass

def _ensure_geloeschte_protokoll_table():
    """Erstellt geloeschte_protokoll-Tabelle in tasks.db (idempotent)."""
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.execute("""
            CREATE TABLE IF NOT EXISTS geloeschte_protokoll (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                konto             TEXT NOT NULL,
                folder            TEXT NOT NULL,
                datum_mail        TEXT,
                absender          TEXT,
                empfaenger        TEXT,
                betreff           TEXT,
                kurzinhalt        TEXT,
                datum_geloescht   TEXT NOT NULL,
                anhaenge_entfernt INTEGER DEFAULT 0,
                message_id        TEXT
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_gp_konto ON geloeschte_protokoll(konto)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_gp_datum ON geloeschte_protokoll(datum_geloescht)")
        db.commit()
        db.close()
    except Exception:
        pass

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

# ── DB Helpers ────────────────────────────────────────────────────────────────
def get_db():
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    return db

def _ensure_case_engine_tables():
    """Erstellt Case-Engine-Tabellen falls noch nicht vorhanden (session-nn)."""
    db = sqlite3.connect(str(TASKS_DB))
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS vorgaenge (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                vorgang_nr          TEXT UNIQUE,
                typ                 TEXT NOT NULL,
                status              TEXT NOT NULL DEFAULT 'neu',
                titel               TEXT,
                kunden_email        TEXT,
                kunden_name         TEXT,
                konto               TEXT,
                betrag              REAL,
                betrag_waehrung     TEXT DEFAULT 'EUR',
                prioritaet          TEXT DEFAULT 'mittel',
                entscheidungsstufe  TEXT DEFAULT 'B',
                konfidenz           REAL DEFAULT 0.5,
                quelle              TEXT DEFAULT 'mail',
                erstellt_am         TEXT DEFAULT CURRENT_TIMESTAMP,
                aktualisiert_am     TEXT DEFAULT CURRENT_TIMESTAMP,
                abgeschlossen_am    TEXT,
                erwartet_bis        TEXT,
                notiz               TEXT,
                letzter_status_grund TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_vg_typ      ON vorgaenge(typ);
            CREATE INDEX IF NOT EXISTS idx_vg_status   ON vorgaenge(status);
            CREATE INDEX IF NOT EXISTS idx_vg_email    ON vorgaenge(kunden_email);
            CREATE INDEX IF NOT EXISTS idx_vg_erstellt ON vorgaenge(erstellt_am);

            CREATE TABLE IF NOT EXISTS vorgang_links (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                vorgang_id      INTEGER NOT NULL,
                entitaet_typ    TEXT NOT NULL,
                entitaet_id     TEXT NOT NULL,
                rolle           TEXT,
                erstellt_am     TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (vorgang_id) REFERENCES vorgaenge(id)
            );
            CREATE INDEX IF NOT EXISTS idx_vl_vorgang  ON vorgang_links(vorgang_id);
            CREATE INDEX IF NOT EXISTS idx_vl_entitaet ON vorgang_links(entitaet_typ, entitaet_id);

            CREATE TABLE IF NOT EXISTS vorgang_status_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                vorgang_id      INTEGER NOT NULL,
                alter_status    TEXT,
                neuer_status    TEXT,
                grund           TEXT,
                actor           TEXT DEFAULT 'system',
                erstellt_am     TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (vorgang_id) REFERENCES vorgaenge(id)
            );
            CREATE INDEX IF NOT EXISTS idx_vsh_vorgang ON vorgang_status_history(vorgang_id);

            CREATE TABLE IF NOT EXISTS vorgang_signals (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                vorgang_id      INTEGER,
                stufe           TEXT NOT NULL,
                titel           TEXT,
                nachricht       TEXT,
                typ             TEXT,
                payload_json    TEXT,
                angezeigt       INTEGER DEFAULT 0,
                aktion          TEXT,
                erstellt_am     TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (vorgang_id) REFERENCES vorgaenge(id)
            );
            CREATE INDEX IF NOT EXISTS idx_vs_angezeigt ON vorgang_signals(angezeigt);
            CREATE INDEX IF NOT EXISTS idx_vs_stufe     ON vorgang_signals(stufe);
        """)
        for migration in [
            "ALTER TABLE tasks ADD COLUMN vorgang_id INTEGER",
            "ALTER TABLE tasks ADD COLUMN snooze_until TEXT",
            "ALTER TABLE ausgangsrechnungen ADD COLUMN vorgang_id INTEGER",
            "ALTER TABLE angebote ADD COLUMN vorgang_id INTEGER",
        ]:
            try:
                db.execute(migration)
            except Exception:
                pass
        db.commit()
    finally:
        db.close()

def esc(s):
    return str(s or "").replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def js_esc(s):
    return str(s or "").replace('\\','\\\\').replace("'","\\'").replace('\n',' ').replace('\r','')

def format_datum(d):
    if not d: return ""
    try:
        dt = datetime.strptime(str(d)[:19], "%Y-%m-%d %H:%M:%S")
        diff = datetime.now() - dt
        if diff.days == 0: return f"Heute {dt.strftime('%H:%M')}"
        if diff.days == 1: return f"Gestern {dt.strftime('%H:%M')}"
        if diff.days < 7: return f"vor {diff.days} Tagen"
        return dt.strftime("%d.%m.%Y")
    except:
        return str(d)[:10]

# ── Tag-Styles per Kategorie ──────────────────────────────────────────────────
KAT_TAGS = {
    "Antwort erforderlich":  ("Antwort nötig",       "tag-alarm"),
    "Neue Lead-Anfrage":     ("Neuer Lead",          "tag-anfrage"),
    "Angebotsrückmeldung":   ("Angebotsrückmeldung", "tag-antwort"),
    "Rechnung / Beleg":      ("Rechnung / Beleg",    "tag-rechnung"),
    "Shop / System":         ("Shop / System",       "tag-shop"),
    "Zur Kenntnis":          ("Zur Kenntnis",        "tag-muted"),
}

def prio_class(p):
    return {"hoch":"prio-hoch","mittel":"prio-mittel","niedrig":"prio-niedrig"}.get(p,"prio-mittel")

# ── Task Card ─────────────────────────────────────────────────────────────────
def task_card(t: dict) -> str:
    tid   = t["id"]
    kat   = t.get("kategorie","")
    prio  = t.get("prioritaet","mittel")
    email = t.get("kunden_email","") or ""
    konto = esc(t.get("konto","") or "")
    datum = format_datum(t.get("datum_mail"))
    notiz = esc(t.get("notiz","") or "")
    naechste_er = t.get('naechste_erinnerung', '') or ''
    anh   = t.get("anhaenge_pfad","") or ""
    zusammenfassung  = esc(t.get("zusammenfassung","") or "")
    absender_rolle   = esc(t.get("absender_rolle","") or "")
    empfohlene_aktion= esc(t.get("empfohlene_aktion","") or "")
    kategorie_grund  = esc(t.get("kategorie_grund","") or "")
    antwort_noetig   = t.get("antwort_noetig", 0)

    betreff_raw = t.get("betreff","") or ""
    re_betreff  = betreff_raw if betreff_raw.lower().startswith("re:") else f"Re: {betreff_raw}"
    mailto = f"mailto:{email}?subject={urllib.parse.quote(re_betreff)}"

    tag_text, tag_class = KAT_TAGS.get(kat, (kat or "Sonstige", "tag-muted"))

    erin = t.get("erinnerungen",0) or 0
    badge = (
        f'<span class="badge badge-warn">{erin}. Erinnerung</span>' if erin == 1 else
        f'<span class="badge badge-warn2">{erin}. Erinnerung</span>' if erin == 2 else
        f'<span class="badge badge-alarm">{erin}. Erinnerung</span>' if erin > 2 else ""
    )
    thread_count = t.get("_thread_count", 1) or 1
    thread_badge = (f'<span class="badge" title="Thread: {thread_count} Nachrichten" style="background:var(--accent-bg);color:var(--accent);border:1px solid var(--accent-border);font-size:9px">'
                    f'&#x1F4AC; {thread_count}</span>') if thread_count > 1 else ""
    konfidenz = t.get("konfidenz", "mittel") or "mittel"
    konfidenz_badge = ('<span class="badge" title="Niedrige Klassifizierungs-Konfidenz — bitte prüfen" '
                       'style="background:#FFF3CD;color:#856404;border:1px solid #FFECB5;font-size:9px">'
                       '? unsicher</span>') if konfidenz == "niedrig" else ""

    erinnerung_badge = ""
    if naechste_er:
        try:
            er_dt = datetime.fromisoformat(naechste_er[:19])
            er_fmt = er_dt.strftime("%d.%m. %H:%M")
            erinnerung_badge = f'<span class="badge badge-erinnerung" title="Erinnerung geplant">&#x23F0; {er_fmt}</span>'
        except Exception:
            pass

    fotos_btn = ""
    if anh:
        enc_anh = urllib.parse.quote(anh, safe='')
        fotos_btn = f'<button class="btn btn-sec" onclick="openAttachments(\'{enc_anh}\')">Anhänge</button>'

    mail_btn = ""
    msg_id = t.get("message_id","") or ""
    if msg_id:
        enc_mid = urllib.parse.quote(msg_id, safe='')
        mail_btn = f'<button class="btn btn-sec" onclick="readMail(\'{enc_mid}\')">Mail lesen</button>'

    kira_btn = (f'<button class="btn btn-kira" onclick="openKira({tid})">Mit Kira besprechen</button>'
                if antwort_noetig else "")

    return f"""
<div class="task-card {prio_class(prio)}" id="task-{tid}" data-kat="{js_esc(kat)}">
  <label class="tc-check" title="Auswählen"><input type="checkbox" onchange="toggleSelect({tid},this)"></label>
  <div class="task-header">
    <div class="task-tags">
      <span class="tag {tag_class}">{tag_text}</span>
      {"<span class='konto-badge'>" + konto + "</span>" if konto else ""}
      {badge}
      {thread_badge}
      {konfidenz_badge}
      {erinnerung_badge}
    </div>
    <span class="task-datum">{datum}</span>
  </div>
  <div class="task-title">{esc(t.get('titel',''))}</div>
  <div class="task-meta-row">
    <span class="meta-label">Rolle:</span>
    <span class="meta-val">{absender_rolle}</span>
    {"<span class='meta-sep'>&middot;</span><span class='meta-val muted-email'>" + esc(email) + "</span>" if email else ""}
  </div>
  {"<div class='task-summary'>" + zusammenfassung + "</div>" if zusammenfassung else ""}
  {"<div class='task-naechste'>Empfehlung: " + empfohlene_aktion + "</div>" if empfohlene_aktion else ""}
  {"<div class='task-grund'>Grund: " + kategorie_grund + "</div>" if kategorie_grund else ""}
  {"<div class='task-notiz'>Notiz: " + notiz + "</div>" if notiz else ""}
  <div class="task-actions">
    {kira_btn}
    {"<a href='" + esc(mailto) + "' class='btn btn-primary' target='_blank'>Outlook</a>" if email else ""}
    {fotos_btn}
    {mail_btn}
    <button class="btn btn-done"     onclick="setStatusLernen({tid},'erledigt','{js_esc(kat)}')">Erledigt</button>
    <button class="btn btn-kenntnis" onclick="setStatusLernen({tid},'zur_kenntnis','{js_esc(kat)}')">Zur Kenntnis</button>
    <button class="btn btn-later"    onclick="openSpaeterDialog({tid})">Später</button>
    <button class="btn btn-ignore"   onclick="setStatusLernen({tid},'ignorieren','{js_esc(kat)}')">Ignorieren</button>
    <button class="btn btn-korr"     onclick="openKorrektur({tid},'{js_esc(kat)}')">Korrektur</button>
    <button class="btn btn-loeschen" onclick="confirmLoeschen({tid})">Löschen</button>
  </div>
</div>"""

def build_section(titel, tasks, collapsed=False):
    if not tasks: return ""
    cards = "\n".join(task_card(t) for t in tasks)
    coll_class = " collapsed" if collapsed else ""
    return f'<div class="section{coll_class}"><div class="section-title" onclick="this.parentElement.classList.toggle(\'collapsed\')">{titel} <span class="count-badge">{len(tasks)}</span></div><div class="section-body">{cards}</div></div>'

# ── DASHBOARD Panel ───────────────────────────────────────────────────────────
def build_dashboard(tasks, db):
    n_antwort = sum(1 for t in tasks if t.get("kategorie") == "Antwort erforderlich")
    n_leads   = sum(1 for t in tasks if t.get("kategorie") == "Neue Lead-Anfrage")
    n_angebot = sum(1 for t in tasks if t.get("kategorie") == "Angebotsrückmeldung")
    n_ges     = len(tasks)
    today     = datetime.now().strftime("%Y-%m-%d")

    # Organisation-Daten
    try: n_org = db.execute("SELECT COUNT(*) FROM organisation").fetchone()[0]
    except: n_org = 0

    # Ausgangsrechnungen offen
    try:
        ar_row = db.execute("SELECT COUNT(*) c, COALESCE(SUM(betrag_brutto),0) s FROM ausgangsrechnungen WHERE status='offen'").fetchone()
        n_ar_offen = ar_row[0]; s_ar_offen = ar_row[1]
    except: n_ar_offen = 0; s_ar_offen = 0

    # Eingangsrechnungen offen
    try: n_eingang = db.execute("SELECT COUNT(*) FROM geschaeft WHERE wichtigkeit='aktiv' AND (bewertung IS NULL OR bewertung!='erledigt')").fetchone()[0]
    except: n_eingang = 0

    # Nachfass fällig
    try: n_nachfass = db.execute("SELECT COUNT(*) FROM angebote WHERE status='offen' AND naechster_nachfass IS NOT NULL AND naechster_nachfass <= ?", (today,)).fetchone()[0]
    except: n_nachfass = 0

    # ── Zone A: Tagesbriefing (horizontale Leiste) ──
    briefing_items = []
    if n_antwort > 0:
        briefing_items.append(f'<div class="dash-b-item"><span class="dash-b-dot" style="background:#E24B4A"></span>{n_antwort} Antwort{"en" if n_antwort>1 else ""} n&ouml;tig</div>')
    if n_nachfass > 0:
        briefing_items.append(f'<div class="dash-b-item"><span class="dash-b-dot" style="background:#EF9F27"></span>{n_nachfass} Nachfass f&auml;llig</div>')
    if n_leads > 0:
        briefing_items.append(f'<div class="dash-b-item"><span class="dash-b-dot" style="background:#378ADD"></span>{n_leads} neue{"r" if n_leads==1 else ""} Lead{"s" if n_leads>1 else ""}</div>')
    if s_ar_offen > 0:
        briefing_items.append(f'<div class="dash-b-item"><span class="dash-b-dot" style="background:#1D9E75"></span>&euro;&nbsp;{s_ar_offen:,.0f} offenes Volumen</div>')

    # LLM-Briefing (falls verfügbar) — voll anzeigen
    llm_block = ""
    try:
        briefing = generate_daily_briefing()
        bz   = (briefing.get("zusammenfassung","") or "").strip()
        prios = briefing.get("prioritaeten") or []
        if bz:
            prio_html = ""
            if prios:
                typ_col = {"rechnung":"#E24B4A","angebot":"#EF9F27","aufgabe":"#378ADD"}
                items = "".join(
                    f'<div class="dash-bs-prio"><span class="dash-bs-dot" style="background:{typ_col.get(str(p.get("typ","aufgabe")).lower(),"#888")}"></span>{esc(str(p.get("text",""))[:120])}</div>'
                    for p in prios[:5]
                )
                prio_html = f'<div class="dash-bs-prios">{items}</div>'
            llm_block = f'<div class="dash-briefing-summary"><div class="dash-bs-text">{esc(bz)}</div>{prio_html}</div>'
    except: pass

    if not briefing_items:
        briefing_items = ['<div class="dash-b-item" style="color:var(--success)"><span class="dash-b-dot" style="background:var(--success)"></span>Alles im gr&uuml;nen Bereich</div>']

    briefing_html = f'''<div id="kira-briefing" class="dash-briefing">
  <div class="dash-briefing-head">
    <div class="dash-briefing-title">Tagesbriefing</div>
    <button class="dash-briefing-refresh" onclick="refreshBriefing()">&#x21BB; Aktualisieren</button>
  </div>
  <div class="dash-briefing-items">{"".join(briefing_items)}</div>
  {llm_block}
</div>'''

    # ── Zone B: KPI-Karten ──
    # Echte Monats-Sparkline für Rechnungsvolumen (letzte 6 Monate)
    rechnung_spark = ""
    try:
        months = db.execute("""
            SELECT strftime('%Y-%m', datum) as m, SUM(betrag_brutto) as total
            FROM ausgangsrechnungen WHERE datum >= date('now','-6 months')
            GROUP BY m ORDER BY m
        """).fetchall()
        if months and len(months) >= 2:
            vals = [r['total'] or 0 for r in months[-6:]]
            max_v = max(vals) or 1
            bar_w = 28; gap = 6
            bars = ""
            for i, v in enumerate(vals):
                h = max(3, int(v / max_v * 26))
                x = 8 + i * (bar_w + gap)
                op = round(0.25 + 0.55 * v / max_v, 2)
                bars += f'<rect x="{x}" y="{34-h}" width="{bar_w}" height="{h}" rx="3" fill="#EF9F27" opacity="{op}"/>'
            rechnung_spark = f'<div class="dash-kpi-spark"><svg viewBox="0 0 220 34">{bars}</svg></div>'
    except: pass

    kpi_html = f"""<div class="dash-kpi-grid" id="kpi-bar">
  <div class="dash-kpi {'kpi-danger' if n_antwort>0 else ''}" onclick="filterKomm('Antwort erforderlich')">
    <div class="dash-kpi-label">Antworten n&ouml;tig</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_antwort}</span>{'<span class="dash-kpi-change danger">dringend</span>' if n_antwort>0 else '<span class="dash-kpi-change info">kein Handlungsbedarf</span>'}</div>
  </div>
  <div class="dash-kpi {'kpi-accent' if n_leads>0 else ''}" onclick="filterKomm('Neue Lead-Anfrage')">
    <div class="dash-kpi-label">Neue Leads</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_leads}</span><span class="dash-kpi-change info">diese Woche</span></div>
  </div>
  <div class="dash-kpi {'kpi-warn' if s_ar_offen>0 else ''}" onclick="showPanel('geschaeft')">
    <div class="dash-kpi-label">Offenes Rechnungsvolumen</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">&euro;&thinsp;{s_ar_offen:,.0f}</span>{'<span class="dash-kpi-change warn">' + str(n_ar_offen) + ' Rg.</span>' if n_ar_offen>0 else ''}</div>
    {rechnung_spark}
  </div>
  <div class="dash-kpi {'kpi-warn' if n_nachfass>0 else ''}" onclick="showPanel('geschaeft');setTimeout(()=>showGeschTab('angebote'),100)">
    <div class="dash-kpi-label">Nachfass f&auml;llig</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_nachfass}</span>{'<span class="dash-kpi-change warn">Angebote</span>' if n_nachfass>0 else ''}</div>
  </div>
  <div class="dash-kpi" onclick="filterKomm('Angebotsrückmeldung')">
    <div class="dash-kpi-label">Angebots&shy;rückmeldungen</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_angebot}</span>{'<span class="dash-kpi-change up">offen</span>' if n_angebot>0 else ''}</div>
  </div>
  <div class="dash-kpi {'kpi-danger' if n_org>0 else ''}" onclick="showPanel('organisation')">
    <div class="dash-kpi-label">Termine &amp; Fristen</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_org}</span>{'<span class="dash-kpi-change danger">heute</span>' if n_org>0 else ''}</div>
  </div>
  <div class="dash-kpi" onclick="showPanel('geschaeft');setTimeout(()=>showGeschTab('eingangsre'),100)">
    <div class="dash-kpi-label">Eingangsrechnungen offen</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_eingang}</span>{'<span class="dash-kpi-change warn">prüfen</span>' if n_eingang>0 else ''}</div>
  </div>
  <div class="dash-kpi" onclick="showPanel('kommunikation')">
    <div class="dash-kpi-label">Gesamt offen</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_ges}</span></div>
  </div>
</div>"""

    # ── Zone C1: Heute priorisiert (max 5) ──
    urgent = [t for t in tasks if t.get("kategorie") in ("Antwort erforderlich","Neue Lead-Anfrage","Angebotsrückmeldung")][:5]

    def prio_color(kat):
        if kat == "Antwort erforderlich": return "prio-red"
        if kat == "Neue Lead-Anfrage": return "prio-blue"
        if kat == "Angebotsrückmeldung": return "prio-amber"
        return "prio-gray"

    def prio_tag(kat):
        if kat == "Antwort erforderlich": return '<span class="dash-tag dash-tag-red">dringend</span>'
        if kat == "Neue Lead-Anfrage": return '<span class="dash-tag dash-tag-blue">neuer Lead</span>'
        if kat == "Angebotsrückmeldung": return '<span class="dash-tag dash-tag-amber">Angebot</span>'
        return '<span class="dash-tag dash-tag-gray">offen</span>'

    prio_items_html = ""
    for t in urgent:
        kat = t.get("kategorie","")
        title = esc((t.get("titel") or t.get("betreff") or "Vorgang")[:70])
        meta_parts = []
        if kat: meta_parts.append(kat)
        if t.get("kunden_name"): meta_parts.append(esc(t["kunden_name"][:30]))
        if t.get("datum_mail"): meta_parts.append(format_datum(t["datum_mail"]))
        meta = " · ".join(meta_parts)
        aktion = esc((t.get("empfohlene_aktion","") or "")[:60])
        next_hint = f'<span class="dash-prio-next">{aktion}</span>' if aktion else ""
        tid = t.get("id","")
        prio_items_html += f'''<div class="dash-prio-item {prio_color(kat)}">
  <div class="dash-prio-body">
    <div class="dash-prio-title">{title}</div>
    <div class="dash-prio-meta">{meta}</div>
    <div class="dash-prio-tags">{prio_tag(kat)}{next_hint}</div>
  </div>
  <div class="dash-prio-menu" id="pmenu-{tid}">
    <button class="dash-prio-dots" onclick="togglePrioMenu(this)" title="Aktionen">&#x22EE;</button>
    <div class="dash-prio-dropdown">
      <button class="dash-prio-dd-btn" onclick="filterKomm('{esc(kat)}');document.querySelectorAll('.dash-prio-menu.open').forEach(m=>m.classList.remove('open'))">&#x2192; &Ouml;ffnen</button>
      <div class="dash-prio-dd-sep"></div>
      <button class="dash-prio-dd-btn dd-kira" onclick="openKiraWorkspace('aufgabe');document.querySelectorAll('.dash-prio-menu.open').forEach(m=>m.classList.remove('open'))">&#x2728; Mit Kira bearbeiten</button>
    </div>
  </div>
</div>'''

    if not prio_items_html:
        prio_items_html = '<div style="text-align:center;padding:28px 0;color:var(--muted);font-size:13px">&#x2713; Keine priorisierten Aufgaben heute</div>'

    # ── Zone C2: Nächste Termine & Fristen ──
    try:
        org_rows = db.execute("SELECT typ,datum_erkannt,beschreibung,kunden_email FROM organisation ORDER BY datum_erkannt ASC LIMIT 5").fetchall()
        term_html = ""
        _ORG_TYP = {"termin": "Termin", "frist": "Frist", "rueckruf": "Rückruf"}
        for r in org_rows:
            dat = esc(r['datum_erkannt'] or '')
            desc = esc((r['beschreibung'] or '')[:45])
            raw_org_typ = r['typ'] or ''
            typ = esc(_ORG_TYP.get(raw_org_typ, raw_org_typ.title()))
            # Urgency color based on date
            urgency = "normal"
            try:
                d = datetime.strptime(dat[:10], "%Y-%m-%d")
                diff = (d.date() - datetime.now().date()).days
                if diff <= 0: urgency = "urgent"
                elif diff <= 2: urgency = "soon"
            except: pass
            dat_display = dat[:10] if dat else "–"
            badge = ""
            if urgency == "urgent":
                if diff < 0: badge = f'<span class="dash-term-badge dash-tag-red">&#x26A0; &uuml;berf&auml;llig</span>'
                else: badge = f'<span class="dash-term-badge dash-tag-red">heute</span>'
            elif urgency == "soon": badge = f'<span class="dash-term-badge dash-tag-amber">bald</span>'
            term_html += f'''<div class="dash-term-item">
  <span class="dash-term-date {urgency}">{dat_display}</span>
  <span class="dash-term-text">{desc or typ}</span>
  {badge}
</div>'''
    except: term_html = '<div style="padding:12px;color:var(--muted);font-size:12px">Keine Termine erfasst</div>'

    # ── Zone C3: Geschäft aktuell ──
    _TYP_LABELS = {
        "sonstiger_vorgang": "Vorgang",
        "eingangsrechnung": "Eingangsrechnung",
        "zahlungserinnerung": "Zahlungserinnerung",
        "routine_zahlung": "Routinezahlung",
        "kundenvorgang": "Kundenvorgang",
        "beleg": "Beleg",
        "rechnung": "Rechnung",
        "angebot": "Angebot",
        "anfrage": "Anfrage",
        "lead": "Lead",
        "nachfass": "Nachfass",
    }
    try:
        gesch_rows = db.execute("SELECT typ,datum,betrag,gegenpartei,gegenpartei_email FROM geschaeft ORDER BY datum DESC LIMIT 5").fetchall()
        biz_html = ""
        for r in gesch_rows:
            raw_typ = r['typ'] or ''
            typ = esc(_TYP_LABELS.get(raw_typ, raw_typ.replace("_"," ").title() if raw_typ else ''))
            betrag = r['betrag'] or 0
            name = esc((r['gegenpartei'] or r['gegenpartei_email'] or '')[:30])
            # Color by type (use raw DB value for reliable matching)
            rt = raw_typ.lower()
            if rt in ("routine_zahlung", "eingangsrechnung", "beleg") or "zahlung" in rt and "erinnerung" not in rt:
                dot_color = "#1D9E75"; val_color = "#1D9E75"; prefix = "+"
            elif "mahnung" in rt or "zahlungserinnerung" in rt or "ueberfaellig" in rt:
                dot_color = "#E24B4A"; val_color = "#E24B4A"; prefix = ""
            elif rt == "nachfass":
                dot_color = "#EF9F27"; val_color = "#BA7517"; prefix = ""
            else:
                dot_color = "#888780"; val_color = "var(--text-secondary)"; prefix = ""
            betrag_str = f'{prefix}&euro;&nbsp;{betrag:,.0f}' if betrag else ""
            biz_html += f'''<div class="dash-biz-item">
  <span class="dash-biz-dot" style="background:{dot_color}"></span>
  <span class="dash-biz-text">{typ}{": " if typ and name else ""}{name}</span>
  <span class="dash-biz-val" style="color:{val_color}">{betrag_str}</span>
</div>'''
    except: biz_html = '<div style="padding:12px;color:var(--muted);font-size:12px">Keine Geschäftsbewegungen</div>'

    work_html = f"""<div class="dash-work-grid">
  <div class="dash-panel">
    <div class="dash-panel-title" style="cursor:pointer" onclick="showPanel('kommunikation')">Heute priorisiert</div>
    <div class="dash-panel-sub">Top 5 &mdash; modulübergreifend kuratiert</div>
    {prio_items_html}
  </div>
  <div class="dash-right-col">
    <div class="dash-panel">
      <div class="dash-panel-title" style="cursor:pointer" onclick="showPanel('organisation')">N&auml;chste Termine &amp; Fristen</div>
      <div class="dash-panel-sub">Kommende 7 Tage</div>
      {term_html}
    </div>
    <div class="dash-panel">
      <div class="dash-panel-title" style="cursor:pointer" onclick="showPanel('geschaeft')">Gesch&auml;ft aktuell</div>
      <div class="dash-panel-sub">Letzte Bewegungen</div>
      {biz_html}
    </div>
  </div>
</div>"""

    # ── Zone D: Signale / Auffälligkeiten ──
    signals = []

    # Überfällige Rechnungen (> 30 Tage)
    try:
        for r in db.execute("SELECT re_nummer, kunde_name, datum FROM ausgangsrechnungen WHERE status='offen'"):
            try:
                d = datetime.strptime(str(r['datum'])[:10], "%Y-%m-%d")
                tage = (datetime.now() - d).days
                if tage > 30:
                    signals.append(('s-red', '#E24B4A',
                        f'RE {esc(r["re_nummer"])} ({esc((r["kunde_name"] or "")[:20])}) seit {tage} Tagen offen',
                        "showPanel('geschaeft')"))
            except: pass
    except: pass

    # Skonto-Fristen
    try:
        ddb = sqlite3.connect(str(DETAIL_DB))
        ddb.row_factory = sqlite3.Row
        for r in ddb.execute("SELECT re_nummer, skonto_datum, skonto_prozent FROM rechnungen_detail WHERE skonto_datum >= ? AND skonto_datum IS NOT NULL", (today,)):
            try:
                tage_rest = (datetime.strptime(r['skonto_datum'], "%Y-%m-%d").date() - datetime.now().date()).days
                if tage_rest <= 3:
                    signals.append(('s-amber', '#EF9F27',
                        f'Skonto {r["skonto_prozent"]}% für {esc(r["re_nummer"])} läuft in {tage_rest} Tagen ab',
                        "showPanel('geschaeft')"))
            except: pass
        ddb.close()
    except: pass

    # Gemahnte Rechnungen
    try:
        mc = db.execute("SELECT COUNT(*) FROM ausgangsrechnungen WHERE (mahnung_count > 0) AND status='offen'").fetchone()[0]
        if mc > 0:
            signals.append(('s-red', '#E24B4A',
                f'{mc} gemahnte Rechnung{"en" if mc>1 else ""} noch offen &mdash; Mahnstufe pr&uuml;fen',
                "showPanel('geschaeft')"))
    except: pass

    # Angebote ohne Rückmeldung > 14 Tage
    try:
        for r in db.execute("SELECT angebots_nr, kunde, erstellt FROM angebote WHERE status='offen' AND erstellt IS NOT NULL"):
            try:
                d = datetime.strptime(str(r['erstellt'])[:10], "%Y-%m-%d")
                tage = (datetime.now() - d).days
                if tage > 14:
                    signals.append(('s-blue', '#378ADD',
                        f'Angebot {esc(r["angebots_nr"] or "")} ({esc((r["kunde"] or "")[:20])}): {tage} Tage ohne Rückmeldung',
                        "showPanel('geschaeft');setTimeout(()=>showGeschTab('angebote'),100)"))
            except: pass
    except: pass

    # Korrektur-Statistik: Häufig falsch klassifizierte Kategorien (letzte 90 Tage)
    try:
        cutoff90 = (datetime.now().replace(hour=0,minute=0,second=0)
                   .__class__.now() if False else datetime.now()).strftime("%Y-%m-%d")
        from datetime import timedelta as _td90
        cutoff90 = (datetime.now() - _td90(days=90)).strftime("%Y-%m-%d")
        korr_rows = db.execute("""
            SELECT alter_typ, neuer_typ, COUNT(*) c
            FROM corrections
            WHERE alter_typ != neuer_typ AND erstellt_am >= ?
            GROUP BY alter_typ, neuer_typ
            HAVING c >= 3
            ORDER BY c DESC LIMIT 3
        """, (cutoff90,)).fetchall()
        for r in korr_rows:
            c = r['c']
            von = esc(r['alter_typ'] or '')
            zu  = esc(r['neuer_typ'] or '')
            signals.append(('s-amber', '#EF9F27',
                f'{c}x &#x201E;{von}&#x201C; &#x2192; &#x201E;{zu}&#x201C; korrigiert &mdash; Lernhinweis',
                "showPanel('wissen')"))
    except: pass

    # Lösch-History: automatisch gefilterte DATEV-Duplikate (letzte 7 Tage)
    try:
        from datetime import timedelta as _td7
        cutoff7 = (datetime.now() - _td7(days=7)).strftime("%Y-%m-%d")
        lh_count = db.execute(
            "SELECT COUNT(*) FROM loeschhistorie WHERE geloescht_am >= ? AND grund NOT LIKE 'BEHALTEN%'",
            (cutoff7,)
        ).fetchone()[0]
        lh_keep  = db.execute(
            "SELECT COUNT(*) FROM loeschhistorie WHERE geloescht_am >= ? AND grund LIKE 'BEHALTEN%'",
            (cutoff7,)
        ).fetchone()[0]
        if lh_count > 0:
            keep_hint = f", {lh_keep}x abweichend behalten" if lh_keep else ""
            signals.append(('s-blue', '#6CB4F0',
                f'{lh_count} Mail{"s" if lh_count>1 else ""} automatisch als DATEV-Duplikat gefiltert{keep_hint}',
                "showLöschHistorie()"))
    except: pass

    signals_html = ""
    if signals:
        sig_items = ""
        for cls, dot_color, text, action in signals[:7]:
            sig_items += f'<div class="dash-sig {cls}" onclick="{action}"><span class="sig-dot" style="background:{dot_color}"></span><span class="sig-text">{text}</span><span class="sig-arr">&#x2192;</span></div>'
        signals_html = f"""<div class="dash-signals">
  <div class="dash-panel-title">Signale &amp; Auff&auml;lligkeiten</div>
  <div class="dash-panel-sub">Automatisch erkannte Ausrei&szlig;er und Pr&uuml;fbedarf</div>
  <div class="dash-sig-grid">{sig_items}</div>
</div>"""

    return f"""{briefing_html}
{kpi_html}
{work_html}
{signals_html}"""

# ── KOMMUNIKATION Panel ──────────────────────────────────────────────────────
def build_kommunikation(tasks):
    # Stats
    n_offen = len(tasks)
    n_leads    = sum(1 for t in tasks if t.get("kategorie") == "Neue Lead-Anfrage")
    n_angebote = sum(1 for t in tasks if t.get("kategorie") == "Angebotsrückmeldung")
    n_dringend = sum(1 for t in tasks if (t.get("prioritaet","") or "").lower() == "hoch")

    # Segment counts
    seg_counts = {
        "Antwort erforderlich": 0,
        "Neue Lead-Anfrage":    0,
        "Angebotsrückmeldung":  0,
        "Zur Kenntnis":         0,
        "Shop / System":        0,
    }
    for t in tasks:
        kat = t.get("kategorie","")
        if kat in seg_counts:
            seg_counts[kat] += 1

    stats_parts = [f'<span class="km-stat km-stat-link" onclick="jumpToSeg(\'alle\')"><b>{n_offen}</b> offen</span>']
    if n_leads:    stats_parts.append(f'<span class="km-stat km-stat-link" onclick="jumpToSeg(\'Neue Lead-Anfrage\')"><b>{n_leads}</b> neue Leads</span>')
    if n_angebote: stats_parts.append(f'<span class="km-stat km-stat-link" onclick="jumpToSeg(\'Angebotsrückmeldung\')"><b>{n_angebote}</b> Angebotsrückm.</span>')
    if n_dringend: stats_parts.append(f'<span class="km-stat km-stat-link" style="color:var(--danger)" onclick="jumpToSeg(\'dringend\')"><b>{n_dringend}</b> dringend</span>')

    mod_hdr = f"""<div class="km-hdr">
  <div class="km-hdr-left">
    <span class="km-title">Kommunikation</span>
    <div class="km-stats">{"".join(stats_parts)}</div>
  </div>
  <div class="km-hdr-acts">
    <button class="km-act-btn" onclick="document.getElementById('km-search-input').focus()">&#x2315; Suche</button>
    <button class="km-act-btn" id="km-view-toggle" onclick="toggleKommFokusModus()">&#x229E; Fokusmodus</button>
    <button class="km-act-btn" onclick="if(_selectedIds.size)multiLoeschen();else showToast('Nichts ausgewählt')">&#x2611; Sammelaktion</button>
  </div>
</div>"""

    # Segment tabs
    seg_tabs = [
        ("alle",                  "Alle",                 n_offen),
        ("Antwort erforderlich",  "Antwort erforderlich", seg_counts["Antwort erforderlich"]),
        ("Neue Lead-Anfrage",     "Neue Leads",           seg_counts["Neue Lead-Anfrage"]),
        ("Angebotsrückmeldung",   "Angebotsrückm.",       seg_counts["Angebotsrückmeldung"]),
        ("Zur Kenntnis",          "Zur Kenntnis",         seg_counts["Zur Kenntnis"]),
        ("Shop / System",         "Newsletter / System",  seg_counts["Shop / System"]),
    ]
    segs_html = '<div class="km-seg" id="km-seg-nav">'
    for key, label, cnt in seg_tabs:
        active = ' active' if key == "alle" else ""
        segs_html += f'<div class="km-seg-t{active}" onclick="kommSegFilter(this,\'{key}\')">{label}<span class="km-seg-cnt">{cnt}</span></div>'
    segs_html += '</div>'

    # Filter bar
    konten = sorted(set(t.get("konto","") or "" for t in tasks if t.get("konto")))
    konto_opts = "".join(f'<option value="{esc(k)}">{esc(k)}</option>' for k in konten)

    flt_html = f"""<div class="km-flt" id="km-flt-bar">
  <span class="km-flt-label">Filter:</span>
  <span class="km-fc" data-filter="antwort" onclick="toggleKommFc(this)">offene Frage</span>
  <span class="km-fc" data-filter="fotos" onclick="toggleKommFc(this)">mit Fotos</span>
  <span class="km-fc" data-filter="anhang" onclick="toggleKommFc(this)">mit Anh&auml;ngen</span>
  <select class="km-fc-sel" id="km-filter-quelle" onchange="applyKommFilters2()">
    <option value="">Quelle</option>{konto_opts}
  </select>
  <select class="km-fc-sel" id="km-filter-prio" onchange="applyKommFilters2()">
    <option value="">Dringlichkeit</option>
    <option value="hoch">Hoch</option>
    <option value="mittel">Mittel</option>
    <option value="niedrig">Niedrig</option>
  </select>
  <span class="km-fc" data-filter="beantwortet" onclick="toggleKommFc(this)">bereits beantwortet</span>
  <span class="km-fc" data-filter="pruefung" onclick="toggleKommFc(this)">manuelle Pr&uuml;fung</span>
  <span class="km-fc" data-filter="kira" onclick="toggleKommFc(this)">nur mit Kira</span>
  <span class="km-fc-count" id="km-filter-count">{n_offen} Vorg&auml;nge</span>
  <input type="text" class="km-search-inp" id="km-search-input" placeholder="&#x2315; Suche&hellip;" oninput="applyKommFilters2()">
</div>"""

    def _wi_accent(t):
        prio = (t.get("prioritaet","") or "").lower()
        kat  = t.get("kategorie","") or ""
        if prio == "hoch":           return "#E24B4A"
        if kat == "Angebotsrückmeldung": return "#EF9F27"
        if kat == "Neue Lead-Anfrage":   return "#378ADD"
        if kat == "Zur Kenntnis":        return "#888780"
        if kat == "Shop / System":       return "#666460"
        return "var(--accent)"

    def _wi_tags(t):
        tags = []
        kat   = t.get("kategorie","") or ""
        prio  = (t.get("prioritaet","") or "").lower()
        antwort = t.get("antwort_noetig", 0)
        anh   = t.get("anhaenge_pfad","") or ""
        er    = t.get("naechste_erinnerung","") or ""

        if prio == "hoch":   tags.append('<span class="km-tg km-tg-red">dringend</span>')
        elif prio == "mittel": tags.append('<span class="km-tg km-tg-amber">mittel</span>')
        if antwort:          tags.append('<span class="km-tg km-tg-amber">Frage</span>')
        anh_l = anh.lower()
        if any(x in anh_l for x in (".jpg",".jpeg",".png",".gif")):
            tags.append('<span class="km-tg km-tg-blue">Fotos</span>')
        elif anh:
            tags.append('<span class="km-tg km-tg-gray">Anhang</span>')
        if kat == "Neue Lead-Anfrage":  tags.append('<span class="km-tg km-tg-blue">neuer Lead</span>')
        elif kat == "Angebotsrückmeldung": tags.append('<span class="km-tg km-tg-purple">Angebotsrückm.</span>')
        elif kat == "Zur Kenntnis":     tags.append('<span class="km-tg km-tg-green">zur Kenntnis</span>')
        elif kat == "Shop / System":    tags.append('<span class="km-tg km-tg-gray">System</span>')
        if er:
            try:
                er_dt = datetime.fromisoformat(er)
                tags.append(f'<span class="km-tg km-tg-warn">&#x23F0; {er_dt.strftime("%d.%m. %H:%M")}</span>')
            except: pass
        return "".join(tags)

    def _wi_item(t):
        tid   = t["id"]
        kat   = t.get("kategorie","") or ""
        prio  = (t.get("prioritaet","") or "").lower()
        titel = esc(t.get("titel","") or t.get("betreff","") or "(Kein Betreff)")
        summ  = esc((t.get("zusammenfassung","") or "")[:140])
        grund = esc((t.get("kategorie_grund","") or "")[:100])
        empf  = esc((t.get("empfohlene_aktion","") or "")[:110])
        rolle = esc(t.get("absender_rolle","") or "")
        email = esc(t.get("kunden_email","") or "")
        konto = esc(t.get("konto","") or "")
        anh   = t.get("anhaenge_pfad","") or ""
        anh_l = anh.lower()
        has_fotos  = "1" if any(x in anh_l for x in (".jpg",".jpeg",".png",".gif")) else "0"
        antwort    = t.get("antwort_noetig", 0)
        mit_termin = 1 if t.get("mit_termin") else 0
        man_pruef  = 1 if t.get("manuelle_pruefung") else 0
        beantw     = 1 if t.get("beantwortet") else 0
        has_kira   = "1" if (t.get("zusammenfassung") or t.get("empfohlene_aktion")) else "0"
        datum_raw  = t.get("datum_eingang","") or t.get("datum_mail","") or ""
        datum_fmt = ""
        try:
            dt    = datetime.fromisoformat(str(datum_raw)[:19])
            delta = datetime.now() - dt
            if delta.days == 0:   datum_fmt = f"heute {dt.strftime('%H:%M')}"
            elif delta.days == 1: datum_fmt = "gestern"
            elif delta.days < 7:  datum_fmt = f"vor {delta.days} Tagen"
            else:                  datum_fmt = dt.strftime("%d.%m.")
        except: datum_fmt = str(datum_raw)[:10] if datum_raw else ""

        accent    = _wi_accent(t)
        tags_html = _wi_tags(t)
        meta_str  = (rolle + (" &middot; " + email[:30] if email else "")) if (rolle or email) else ""

        kenntnis_btn = f'<button class="wi-quick-btn wi-btn-k" onclick="setStatusLernen({tid},\'zur_kenntnis\',\'{js_esc(kat)}\');event.stopPropagation()" title="Zur Kenntnis nehmen">&#x2714; Zur Kenntnis</button>'
        check_html   = f'<label class="wi-check" title="Auswählen" onclick="event.stopPropagation()"><input type="checkbox" onchange="toggleSelect({tid},this)"></label>'

        return f"""<div class="wi" id="task-{tid}"
  data-tid="{tid}" data-kat="{js_esc(kat)}" data-prio="{prio}"
  data-antwort="{"1" if antwort else "0"}" data-anhang="{"1" if anh else "0"}"
  data-fotos="{has_fotos}" data-email="{esc(email)}"
  data-termin="{mit_termin}" data-pruefung="{man_pruef}"
  data-beantwortet="{beantw}" data-kira="{has_kira}"
  onclick="selectKommItem({tid},event)">
  {check_html}
  <div class="wi-accent" style="background:{accent}"></div>
  <div class="wi-body">
    <div class="wi-top">
      <div class="wi-tags-row">{tags_html}{"<span class='konto-badge'>"+konto+"</span>" if konto else ""}</div>
      <div class="wi-time">{datum_fmt}</div>
    </div>
    <div class="wi-title">{titel}</div>
    {"<div class='wi-meta'><span class='meta-label'>Rolle:</span> <span class='meta-val'>" + meta_str + "</span></div>" if meta_str else ""}
    {"<div class='wi-sum'>" + summ + "</div>" if summ else ""}
    {"<div class='wi-empfehlung'>&#x279C; " + empf + "</div>" if empf else ""}
    {"<div class='wi-grund'>" + grund + "</div>" if grund else ""}
    <div class="wi-acts">{kenntnis_btn}</div>
  </div>
</div>"""

    items_html = "".join(_wi_item(t) for t in tasks)
    if not items_html:
        items_html = '<div class="km-empty">&#x2709;<br>Keine offenen Kommunikationsaufgaben.</div>'

    ctx_placeholder = """<div class="km-ctx-inner" id="km-ctx-content">
  <div class="km-ctx-empty">
    <span style="font-size:36px;opacity:.2">&#x25B7;</span>
    <span>Vorgang aus der Liste w&auml;hlen</span>
    <span style="font-size:11px;opacity:.6">Klick &ouml;ffnet Kontext &amp; Aktionen</span>
  </div>
</div>"""

    return f"""{mod_hdr}
{segs_html}
{flt_html}
<div class="km-workspace">
  <div class="km-wl" id="km-wl">
    <div class="km-wl-inner" id="km-items">{items_html}</div>
  </div>
  <div class="km-ctx" id="km-ctx">{ctx_placeholder}</div>
</div>"""

# ── POSTFACH Panel ────────────────────────────────────────────────────────────
def build_postfach():
    """Outlook-Style 3-Pane Mail-Modul. Daten werden via AJAX geladen."""
    return """<!-- ── RIBBON ─────────────────────────────────────────────── -->
<div class="pf-ribbon-wrap" id="pf-ribbon-wrap">
  <div class="pf-ribbon" id="pf-ribbon">
    <button class="pf-rbn-edge pf-rbn-prev" id="pf-rbn-prev" onclick="pfRibbonScroll(-1)" title="Zurück" style="display:none">&#x2039;</button>
    <div class="pf-rbn-viewport" id="pf-rbn-viewport">
      <div class="pf-rbn-inner" id="pf-rbn-inner">
        <div class="pf-rbn-group">
          <div class="pf-rbn-actions">
            <button class="pf-rbn-tool" id="pf-rb-compose" onclick="pfOpenCompose()" title="Neue Mail verfassen">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M22 11.2603V7.608L12.348 12.6644C12.13 12.7785 11.87 12.7785 11.652 12.6644L2 7.608V15.75L2.00514 15.9344C2.10075 17.6435 3.51697 19 5.25 19H11.717C11.9006 18.5781 12.1624 18.1927 12.4903 17.8648L18.3927 11.9624C19.3679 10.9871 20.8037 10.7531 22 11.2603ZM18.75 3H5.25L5.06409 3.00523C3.46432 3.09545 2.17386 4.34271 2.01619 5.92355L12 11.1533L21.9838 5.92355C21.8201 4.28191 20.4347 3 18.75 3ZM19.0999 12.6695L13.1974 18.5719C12.8533 18.916 12.6092 19.3472 12.4911 19.8194L12.0334 21.6501C11.8344 22.4462 12.5556 23.1674 13.3517 22.9683L15.1824 22.5106C15.6545 22.3926 16.0857 22.1485 16.4299 21.8043L22.3323 15.9019C23.2249 15.0093 23.2249 13.5621 22.3323 12.6695C21.4397 11.7768 19.9925 11.7768 19.0999 12.6695Z"/></svg>
              <span>Neue Mail</span>
            </button>
          </div>
          <div class="pf-rbn-label">Erstellen</div>
        </div>
        <div class="pf-rbn-sep"></div>
        <div class="pf-rbn-group">
          <div class="pf-rbn-actions">
            <button class="pf-rbn-tool pf-rbn-mail-dep" id="pf-rb-reply" onclick="pfReply()" title="Antworten">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M9.707 6.707a1 1 0 1 0-1.414-1.414l-5 5a1 1 0 0 0 0 1.414l5 5a1 1 0 0 0 1.414-1.414L6.414 12H13a5 5 0 0 1 5 5 1 1 0 1 0 2 0 7 7 0 0 0-7-7H6.414l3.293-3.293Z"/></svg>
              <span>Antworten</span>
            </button>
            <button class="pf-rbn-tool pf-rbn-mail-dep" id="pf-rb-replyall" onclick="pfReplyAll()" title="Allen antworten">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M9.707 5.293a1 1 0 0 1 0 1.414L5.414 11H13a7 7 0 0 1 7 7 1 1 0 1 1-2 0 5 5 0 0 0-5-5H5.414l4.293 4.293a1 1 0 0 1-1.414 1.414l-6-6a1 1 0 0 1 0-1.414l6-6a1 1 0 0 1 1.414 0Zm5 0a1 1 0 0 1 0 1.414L11.414 10H13a7 7 0 0 1 7 7 1 1 0 1 1-2 0 5 5 0 0 0-5-5h-1.586l3.293 3.293a1 1 0 0 1-1.414 1.414l-5-5a1 1 0 0 1 0-1.414l5-5a1 1 0 0 1 1.414 0Z"/></svg>
              <span>Allen</span>
            </button>
            <button class="pf-rbn-tool pf-rbn-mail-dep" id="pf-rb-forward" onclick="pfForward()" title="Weiterleiten">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M14.293 6.707a1 1 0 0 1 1.414-1.414l5 5a1 1 0 0 1 0 1.414l-5 5a1 1 0 0 1-1.414-1.414L17.586 12H11a5 5 0 0 0-5 5 1 1 0 1 1-2 0 7 7 0 0 1 7-7h6.586l-3.293-3.293Z"/></svg>
              <span>Weiterleiten</span>
            </button>
          </div>
          <div class="pf-rbn-label">Antworten</div>
        </div>
        <div class="pf-rbn-sep"></div>
        <div class="pf-rbn-group">
          <div class="pf-rbn-actions">
            <button class="pf-rbn-tool pf-rbn-mail-dep" id="pf-rb-read" onclick="pfRibbonToggleRead()" title="Gelesen/Ungelesen umschalten">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M10.809 2.34a2 2 0 0 1 2.382 0L21.04 7.67c.06.045.118.093.171.144L12 12.15 2.79 7.814A2 2 0 0 1 2.963 7.67L10.81 2.34ZM2.049 8.615A2.01 2.01 0 0 0 2 9.082V16.75A3.25 3.25 0 0 0 5.25 20h13.5A3.25 3.25 0 0 0 22 16.75V9.082c0-.16-.017-.317-.05-.472L12.35 13.66a1 1 0 0 1-.7 0L2.05 8.615Z"/></svg>
              <span>Gelesen</span>
            </button>
            <button class="pf-rbn-tool pf-rbn-mail-dep pf-rbn-accent-orange" id="pf-rb-flag" onclick="pfRibbonToggleFlag()" title="Kennzeichnen">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 3.748a.75.75 0 0 1 .75-.75H20.25a.625.625 0 0 1 .459 1.05l-4.164 5.5 4.164 5.5a.625.625 0 0 1-.459 1.05H4.5v5.25a.75.75 0 0 1-1.5 0V3.748Z"/></svg>
              <span>Kennzeichnen</span>
            </button>
            <button class="pf-rbn-tool pf-rbn-mail-dep" id="pf-rb-pin" onclick="pfRibbonTogglePin()" title="Anheften">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M21.068 7.758 16.242 2.932c-1.327-1.327-3.565-.964-4.404 1.714L9.403 8.517a1 1 0 0 1-.427.474L4.81 10.33a1 1 0 0 0-.476 1.065l3.105 3.106L3 19.939 3 21h1.061l4.44-4.44 3.104 3.105a1 1 0 0 0 1.065-.476l2.44-4.166a1 1 0 0 1 .474-.427l4.87-2.363c2.678-.84 3.041-3.078 1.714-4.405Z"/></svg>
              <span>Anheften</span>
            </button>
            <button class="pf-rbn-tool pf-rbn-mail-dep pf-rbn-accent-red" id="pf-rb-delete" onclick="pfRibbonDelete()" title="Löschen">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M10 5h4a2 2 0 1 0-4 0ZM8.5 5a3.5 3.5 0 1 1 7 0h5.25a.75.75 0 0 1 0 1.5h-1.32l-1.17 12.111A3.75 3.75 0 0 1 14.515 22H9.485a3.75 3.75 0 0 1-3.744-3.389L4.57 6.5H3.25a.75.75 0 0 1 0-1.5H8.5Zm1.25 4.75a.75.75 0 0 0-1.5 0v7.5a.75.75 0 0 0 1.5 0v-7.5Zm4.5 0a.75.75 0 0 0-1.5 0v7.5a.75.75 0 0 0 1.5 0v-7.5Z"/></svg>
              <span>Löschen</span>
            </button>
            <button class="pf-rbn-tool pf-rbn-mail-dep" id="pf-rb-move" onclick="pfOpenVerschiebenMenu(this)" title="Verschieben">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 8V6.25A3.25 3.25 0 0 1 5.25 3h2.879a2 2 0 0 1 1.414.586L10.836 5H2Zm0 1.5v8.25A3.25 3.25 0 0 0 5.25 21h6.772A5.5 5.5 0 0 1 11 17.5c0-3.59 2.91-6.5 6.5-6.5 1.246 0 2.41.35 3.4.956V8.75A3.25 3.25 0 0 0 17.65 5.5h-4.898L11.25 9.5H2ZM23 17.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0Zm-9 0c0 .276.224.5.5.5h5.293l-1.647 1.646a.5.5 0 0 0 .708.708l2.5-2.5a.5.5 0 0 0 0-.708l-2.5-2.5a.5.5 0 0 0-.708.708L19.793 17H14.5a.5.5 0 0 0-.5.5Z"/></svg>
              <span>Verschieben</span>
            </button>
            <button class="pf-rbn-tool pf-rbn-mail-dep pf-rbn-prep" id="pf-rb-archive" onclick="pfToastVorbereitung('Archivieren')" title="Archivieren (in Vorbereitung)">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 4.5A1.5 1.5 0 0 1 4.5 3h15A1.5 1.5 0 0 1 21 4.5V6a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 6V4.5ZM4 9h16v8.25A3.75 3.75 0 0 1 16.25 21H7.75A3.75 3.75 0 0 1 4 17.25V9Zm5.5 2.75a.75.75 0 0 0 0 1.5h5a.75.75 0 0 0 0-1.5h-5Z"/></svg>
              <span>Archivieren</span>
            </button>
            <button class="pf-rbn-tool pf-rbn-prep" id="pf-rb-rules" onclick="pfToastVorbereitung('Regeln/Sweep')" title="Regeln/Sweep (in Vorbereitung)">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M10 17a1 1 0 1 0 0 2h4a1 1 0 1 0 0-2h-4ZM8 12a1 1 0 1 0 0 2h8a1 1 0 1 0 0-2H8ZM5 7a1 1 0 0 0 0 2h14a1 1 0 1 0 0-2H5Z"/></svg>
              <span>Regeln</span>
            </button>
          </div>
          <div class="pf-rbn-label">Aktionen</div>
        </div>
        <div class="pf-rbn-sep"></div>
        <div class="pf-rbn-group">
          <div class="pf-rbn-actions">
            <button class="pf-rbn-tool pf-rbn-mail-dep" id="pf-rb-snooze" onclick="pfOpenSnoozeMenu(this)" title="Erneut erinnern / Snooze">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 1 1 0 20A10 10 0 0 1 12 2Zm0 1.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17ZM12 6a.75.75 0 0 1 .75.75V12h3a.75.75 0 0 1 0 1.5h-3.75a.75.75 0 0 1-.75-.75v-6A.75.75 0 0 1 12 6Z"/></svg>
              <span>Erinnern</span>
            </button>
            <button class="pf-rbn-tool pf-rbn-prep" id="pf-rb-print" onclick="pfToastVorbereitung('Drucken')" title="Drucken (in Vorbereitung)">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M18 17.5v1.25A2.25 2.25 0 0 1 15.75 21H8.25A2.25 2.25 0 0 1 6 18.75V17.5H4.25A2.25 2.25 0 0 1 2 15.25V9.254a3.25 3.25 0 0 1 3.25-3.25H6V5.25A2.25 2.25 0 0 1 8.25 3h7.5A2.25 2.25 0 0 1 18 5.25V6h.75A3.25 3.25 0 0 1 22 9.254v5.996A2.25 2.25 0 0 1 19.75 17.5H18Zm-10.5-4v5.25c0 .414.336.75.75.75h7.5a.75.75 0 0 0 .75-.75V13.5h-9Zm9-8.25a.75.75 0 0 0-.75-.75h-7.5a.75.75 0 0 0-.75.75V6h9V5.25Z"/></svg>
              <span>Drucken</span>
            </button>
          </div>
          <div class="pf-rbn-label">Erinnern &amp; Mehr</div>
        </div>
        <div class="pf-rbn-sep"></div>
        <div class="pf-rbn-group">
          <div class="pf-rbn-actions">
            <button class="pf-rbn-tool pf-rbn-kira pf-rbn-mail-dep" id="pf-rb-kira" onclick="pfKiraMailContext()" title="Mit Kira besprechen">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 1 1 0 20A10 10 0 0 1 12 2Zm0 2a8 8 0 1 0 0 16A8 8 0 0 0 12 4Zm0 9.5c1.74 0 3.41.81 4.5 2.18a.75.75 0 1 1-1.16.94A4.48 4.48 0 0 0 12 15a4.48 4.48 0 0 0-3.34 1.62.75.75 0 1 1-1.16-.94A5.98 5.98 0 0 1 12 13.5ZM9.5 9a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Zm5 0a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Z"/></svg>
              <span>Kira fragen</span>
            </button>
          </div>
          <div class="pf-rbn-label">KI &amp; Kira</div>
        </div>
      </div>
    </div>
    <button class="pf-rbn-edge pf-rbn-next" id="pf-rbn-next" onclick="pfRibbonScroll(1)" title="Weiter" style="display:none">&#x203A;</button>
    <button class="pf-rbn-toggle" id="pf-rbn-toggle" onclick="pfRibbonCompact()" title="Kompakt/Vollmodus">&#x25BE;</button>
  </div>
</div>

<div class="pf-shell">

<!-- LEFT: Konten + Ordner -->
<div class="pf-left" id="pf-left">
  <div class="pf-left-hdr">
    <span class="pf-left-title">Postfach</span>
    <button class="pf-compose-btn" onclick="pfOpenCompose()" title="Neue Mail verfassen">&#x270F; Neu</button>
  </div>
  <div id="pf-folders-loading" style="padding:16px;color:var(--text-muted);font-size:13px">Lade Konten...</div>
  <div id="pf-folder-tree"></div>
</div>
<div class="pf-resize-h" id="pf-resize-1"></div>

<!-- MIDDLE: Mail-Liste -->
<div class="pf-mid" id="pf-mid">
  <div class="pf-mid-hdr">
    <div class="pf-mid-title" id="pf-mid-title">Posteingang</div>
    <input class="pf-search" id="pf-search" placeholder="&#x2315; Suchen..." oninput="pfSearchDebounce()" autocomplete="off">
    <div class="pf-mid-meta" id="pf-mid-meta"></div>
  </div>
  <div id="pf-bulk-bar">
    <!-- Single-Mail-Modus (eine Mail angeklickt) -->
    <div id="pf-bar-single" style="display:none;align-items:center;gap:2px;flex:1">
      <button class="pf-bar-btn" id="pf-bar-reply" onclick="pfReply()" title="Antworten"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/></svg>Antworten</button>
      <button class="pf-bar-btn" id="pf-bar-replyall" onclick="pfForward()" title="Allen antworten"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="7 17 2 12 7 7"/><polyline points="12 17 7 12 12 7"/><path d="M22 18v-2a4 4 0 0 0-4-4H7"/></svg>Allen</button>
      <button class="pf-bar-btn" id="pf-bar-forward" onclick="pfForward()" title="Weiterleiten"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 17 20 12 15 7"/><path d="M4 18v-2a4 4 0 0 1 4-4h12"/></svg>Weiterleiten</button>
      <div class="pf-bar-sep"></div>
      <button class="pf-bar-btn pf-bar-del" id="pf-bar-delete" onclick="pfBarDeleteCurrent()" title="L\u00f6schen"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>L\u00f6schen</button>
      <button class="pf-bar-btn" id="pf-bar-flag" onclick="pfBarFlagCurrent()" title="Kennzeichnen"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>Kennzeichnen</button>
      <button class="pf-bar-btn" id="pf-bar-pin" onclick="pfBarPinCurrent()" title="Anheften"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24z"/></svg>Heften</button>
      <div class="pf-bar-sep"></div>
      <button class="pf-bar-btn pf-bar-snooze" id="pf-bar-snooze" onclick="pfOpenSnoozeMenu(this)" title="Erneut erinnern"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>Erinnern</button>
      <button class="pf-bar-btn" id="pf-bar-move" onclick="pfOpenVerschiebenMenu(this)" title="Verschieben"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 9 2 12 5 15"/><polyline points="9 5 12 2 15 5"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="12" y1="2" x2="12" y2="22"/></svg>Verschieben</button>
    </div>
    <!-- Bulk-Modus (mehrere Mails gecheckt) -->
    <div id="pf-bar-bulk" style="display:none;align-items:center;gap:6px;flex:1">
      <span class="pf-bulk-cnt" id="pf-bulk-cnt">0 ausgew&#228;hlt</span>
      <button class="pf-bulk-btn" onclick="pfBulkMarkRead(true)">Als gelesen</button>
      <button class="pf-bulk-btn" onclick="pfBulkMarkRead(false)">Als ungelesen</button>
      <button class="pf-bulk-btn red" onclick="pfBulkDelete()">L&#246;schen</button>
      <button class="pf-bulk-btn" onclick="pfClearSelection()">&#x2715; Abbrechen</button>
    </div>
  </div>
  <div id="pf-list-wrap">
    <div class="pf-list-empty" id="pf-list-empty" style="display:none">
      <div style="font-size:32px;margin-bottom:8px">&#x1F4EC;</div>
      <div>Kein Ordner ausgewählt</div>
    </div>
    <div id="pf-list"></div>
    <div id="pf-load-more" style="display:none;text-align:center;padding:12px">
      <button class="btn btn-sec btn-xs" onclick="pfLoadMore()">Weitere laden</button>
    </div>
  </div>
</div>
<div class="pf-resize-h" id="pf-resize-2"></div>

<!-- RIGHT: Preview / Compose -->
<div class="pf-right" id="pf-right">
  <div id="pf-preview-empty" class="pf-preview-empty">
    <div style="font-size:64px;margin-bottom:16px;opacity:.35">&#x1F4E8;</div>
    <div style="font-size:15px;font-weight:600;margin-bottom:6px;color:var(--text)">Zu lesendes Element auswählen</div>
    <div style="font-size:13px;color:var(--text-muted)">Es wurde keine Auswahl vorgenommen.</div>
  </div>
  <div id="pf-preview" class="pf-detail-frame" style="display:none">

    <!-- ── 1. Mail-Kopf ──────────────────────────────────────── -->
    <div class="pf-mail-head" id="pf-mail-head">
      <div class="pf-subject-bar">
        <div class="pf-subject-text" id="pf-prev-betreff"></div>
        <div class="pf-date-stack" id="pf-prev-datum"></div>
      </div>
      <div class="pf-header-meta">
        <div class="pf-sender-col">
          <div class="pf-avatar" id="pf-avatar">?</div>
          <div class="pf-identity">
            <div class="pf-from-line" id="pf-prev-absender"></div>
            <div class="pf-to-line" id="pf-prev-to"></div>
          </div>
        </div>
        <div class="pf-head-actions" id="pf-prev-toolbar">
          <button class="pf-ha-btn" id="pf-tb-reply" title="Antworten"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/></svg>Antworten</button>
          <button class="pf-ha-btn" id="pf-tb-replyall" title="Allen antworten"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="7 17 2 12 7 7"/><polyline points="12 17 7 12 12 7"/><path d="M22 18v-2a4 4 0 0 0-4-4H7"/></svg>Allen</button>
          <button class="pf-ha-btn" id="pf-tb-forward" title="Weiterleiten"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 17 20 12 15 7"/><path d="M4 18v-2a4 4 0 0 1 4-4h12"/></svg>Weiterleiten</button>
          <div class="pf-ha-sep"></div>
          <button class="pf-ha-icon" id="pf-tb-read" title="Gelesen/Ungelesen"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6L16.55 5.11A2 2 0 0 0 14.76 4H9.24A2 2 0 0 0 5.45 5.11z"/></svg></button>
          <button class="pf-ha-icon" id="pf-tb-flag" title="Kennzeichnen"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg></button>
          <button class="pf-ha-icon" id="pf-tb-pin" title="Anheften"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24z"/></svg></button>
          <button class="pf-ha-icon del-btn" id="pf-tb-delete" title="L\u00f6schen"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg></button>
          <button class="pf-ha-icon" id="pf-tb-move" title="Verschieben" onclick="pfOpenVerschiebenMenu(this)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 9 2 12 5 15"/><polyline points="9 5 12 2 15 5"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="12" y1="2" x2="12" y2="22"/></svg></button>
          <div class="pf-ha-sep"></div>
          <button class="pf-ha-btn pf-kira-btn" id="pf-tb-kira" title="Mit Kira besprechen"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a10 10 0 1 1 0 20A10 10 0 0 1 12 2"/><path d="M8 12s1-2 4-2 4 2 4 2"/><circle cx="9" cy="9" r="1" fill="currentColor"/><circle cx="15" cy="9" r="1" fill="currentColor"/></svg>\u2728 Mit Kira</button>
        </div>
      </div>
    </div>

    <!-- ── 2. Thread-/Status-Hinweise ────────────────────────── -->
    <div class="pf-hint-section" id="pf-hint-section" style="display:none"></div>

    <!-- ── 3. Anh\u00e4nge (einklappbar) ─────────────────────────── -->
    <div class="pf-attachment-section" id="pf-attachment-section" style="display:none">
      <div class="pf-att-collapsed" id="pf-att-collapsed">
        <svg class="pf-att-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
        <span id="pf-att-summary" class="pf-att-summary-text"></span>
        <button class="pf-att-open-btn" onclick="pfToggleAttBar()">Öffnen ›</button>
        <div style="flex:1"></div>
        <button class="pf-att-save-sm" onclick="pfSaveAllAtts()">Alle speichern</button>
      </div>
      <div class="pf-att-expanded" id="pf-att-expanded" style="display:none">
        <div class="pf-att-bar-head">
          <span class="pf-att-title">Anh\u00e4nge</span>
          <span class="pf-att-count" id="pf-att-count"></span>
          <div style="flex:1"></div>
          <button class="pf-att-save-sm" onclick="pfSaveAllAtts()">Alle speichern</button>
          <button class="pf-att-close-btn" onclick="pfToggleAttBar()">\u2715 Schlie\u00dfen</button>
        </div>
        <div class="pf-attachment-list" id="pf-attachment-list"></div>
      </div>
    </div>

    <!-- ── 4. Viewer ──────────────────────────────────────────── -->
    <div class="pf-content-section">
      <div class="pf-viewer-toolbar" id="pf-viewer-toolbar" style="display:none">
        <div class="pf-state-row" id="pf-state-row">
          <span class="pf-state-chip pf-chip-html" id="pf-chip-html" style="display:none">HTML</span>
          <span class="pf-state-chip pf-chip-text" id="pf-chip-text" style="display:none">Nur Text</span>
          <span class="pf-state-chip pf-chip-blocked" id="pf-chip-blocked" style="display:none">Externe Bilder blockiert</span>
        </div>
      </div>
      <div class="pf-trust-banner" id="pf-trust-banner" style="display:none">
        <span>Externe Inhalte wurden blockiert, um Ihre Privatsph\u00e4re zu sch\u00fctzen.</span>
        <button class="pf-trust-btn" onclick="pfTrustSender()">Absender vertrauen</button>
      </div>
      <div class="pf-prev-body" id="pf-prev-body"></div>
      <div id="pf-thread-wrap" style="display:none">
        <div class="pf-thread-hdr" onclick="pfToggleThread()">
          <span>&#x1F4AC; Thread-Verlauf</span><span id="pf-thread-cnt"></span>
          <span id="pf-thread-toggle">&#x25BC;</span>
        </div>
        <div id="pf-thread-list"></div>
      </div>
    </div>

  </div>
  <!-- Compose -->
  <div id="pf-compose" style="display:none">
    <div class="pf-comp-hdr">
      <span id="pf-comp-title">Neue Mail</span>
      <button class="pf-act-btn" onclick="pfCloseCompose()">&#x2715;</button>
    </div>
    <div class="pf-comp-fields">
      <div class="pf-comp-row">
        <label class="pf-comp-lbl">Von</label>
        <select class="pf-comp-sel" id="pf-comp-from"></select>
      </div>
      <div class="pf-comp-row">
        <label class="pf-comp-lbl">An</label>
        <input class="pf-comp-inp" id="pf-comp-to" placeholder="empfaenger@example.com">
      </div>
      <div class="pf-comp-row">
        <label class="pf-comp-lbl">CC</label>
        <input class="pf-comp-inp" id="pf-comp-cc" placeholder="(optional)">
      </div>
      <div class="pf-comp-row">
        <label class="pf-comp-lbl">Betreff</label>
        <input class="pf-comp-inp" id="pf-comp-subj" placeholder="Betreff">
      </div>
    </div>
    <textarea class="pf-comp-body" id="pf-comp-body" placeholder="Nachricht eingeben..."></textarea>
    <div class="pf-comp-acts">
      <button class="btn btn-primary btn-sm" onclick="pfSend()" id="pf-send-btn">&#x27A4; Senden</button>
      <button class="btn btn-sec btn-sm" onclick="pfSaveDraft()">&#x1F4BE; Entwurf</button>
      <button class="btn btn-sec btn-sm" onclick="pfKiraDraft()">&#x1F916; Kira formuliert</button>
    </div>
  </div>
</div>

</div>

<!-- ── BILD-GALERIE MODAL ──────────────────────────────────── -->
<div class="pf-gallery-modal" id="pf-gallery-modal" style="display:none" onclick="if(event.target===this)pfCloseGallery()">
  <div class="pf-gallery-wrap">
    <div class="pf-gallery-topbar">
      <span class="pf-gallery-title" id="pf-gallery-title"></span>
      <div style="flex:1"></div>
      <span class="pf-gallery-counter" id="pf-gallery-counter"></span>
      <button class="pf-gallery-close" onclick="pfCloseGallery()">&#x2715;</button>
    </div>
    <div class="pf-gallery-main">
      <button class="pf-gallery-nav pf-gallery-prev" id="pf-gallery-prev" onclick="pfGalleryNav(-1)">&#x2039;</button>
      <div class="pf-gallery-imgwrap">
        <img class="pf-gallery-img" id="pf-gallery-img" src="" alt="">
      </div>
      <button class="pf-gallery-nav pf-gallery-next" id="pf-gallery-next" onclick="pfGalleryNav(1)">&#x203A;</button>
    </div>
    <div class="pf-gallery-thumbs" id="pf-gallery-thumbs"></div>
  </div>
</div>

<style>
/* ── Postfach Shell ─────────────────────────────────────── */
.pf-shell{display:flex;height:calc(100vh - 56px - var(--pf-ribbon-h,80px));overflow:hidden;gap:0;--pf-left-w:245px;--pf-mid-w:350px}
/* LEFT SIDEBAR */
.pf-left{width:var(--pf-left-w);min-width:160px;max-width:380px;background:var(--bg-raised);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow-y:auto;overflow-x:hidden;flex-shrink:0}
.pf-left-hdr{display:flex;align-items:center;justify-content:space-between;padding:12px 14px 10px;border-bottom:1px solid var(--border);flex-shrink:0}
.pf-left-title{font-weight:700;font-size:14px;color:var(--text)}
.pf-compose-btn{background:#3b82f6;color:#fff;border:none;border-radius:7px;padding:5px 11px;font-size:12px;cursor:pointer;font-weight:600}
.pf-compose-btn:hover{background:#2563eb}
/* Favoriten */
.pf-fav-section{padding:10px 14px 3px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--text-muted)}
.pf-fav-item{display:flex;align-items:center;gap:7px;padding:5px 14px 5px 18px;cursor:pointer;font-size:12px;color:var(--text);transition:background .12s;border-left:3px solid transparent}
.pf-fav-item:hover{background:var(--bg-hover)}
.pf-fav-item.active{background:rgba(59,130,246,.15);border-left-color:#3b82f6;color:#3b82f6;font-weight:600}
.pf-fav-badge{margin-left:auto;color:#0ea5e9;font-size:11px;font-weight:700}
.pf-fav-sep{height:1px;background:var(--border);margin:6px 0}
/* Account headers */
.pf-folder-konto{padding:8px 14px 3px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted);cursor:pointer;display:flex;align-items:center;gap:5px;user-select:none;margin-top:4px}
.pf-folder-konto:hover{color:var(--text)}
.pf-folder-konto .pf-konto-arrow{font-size:9px;transition:transform .15s;display:inline-block}
.pf-folder-konto.collapsed .pf-konto-arrow{transform:rotate(-90deg)}
.pf-konto-folders{overflow:hidden;transition:max-height .25s}
.pf-konto-folders.collapsed{max-height:0!important}
/* Folder items */
.pf-folder-item{display:flex;align-items:center;gap:7px;padding:5px 14px 5px 18px;cursor:pointer;font-size:13px;color:var(--text);border-left:3px solid transparent;transition:background .12s}
.pf-folder-item:hover{background:var(--bg-hover)}
.pf-folder-item.active{background:rgba(59,130,246,.15);border-left-color:#3b82f6;color:#3b82f6;font-weight:600}
.pf-folder-badge{margin-left:auto;color:#0ea5e9;font-size:11px;font-weight:700;min-width:16px;text-align:right}
/* MIDDLE LIST */
.pf-mid{width:var(--pf-mid-w);min-width:240px;max-width:600px;border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
.pf-mid-hdr{padding:10px 14px 8px;border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:5px;flex-shrink:0}
.pf-mid-title{font-weight:700;font-size:15px;color:var(--text)}
.pf-search{border:1px solid var(--border);border-radius:7px;padding:6px 10px;font-size:12px;background:var(--bg);color:var(--text);width:100%;outline:none}
.pf-search:focus{border-color:#3b82f6}
.pf-mid-meta{font-size:11px;color:var(--text-muted)}
#pf-list-wrap{overflow-y:auto;flex:1}
/* DATE GROUP HEADERS */
.pf-date-group{padding:8px 14px 3px;font-size:11px;font-weight:600;color:var(--text-muted);display:flex;align-items:center;gap:8px;user-select:none}
.pf-date-group::after{content:'';flex:1;height:1px;background:var(--border)}
/* MAIL ITEMS — Outlook-Style */
.pf-mail-item{padding:10px 12px;border-bottom:1px solid var(--border);cursor:pointer;transition:background .1s;border-left:3px solid transparent;display:flex;align-items:flex-start;gap:10px}
.pf-mail-item:hover{background:var(--bg-hover)}
.pf-mail-item.unread{border-left-color:#0ea5e9;background:rgba(14,165,233,.04)}
.pf-mail-item.unread .pf-item-absender{color:var(--text);font-weight:700}
.pf-mail-item.unread .pf-item-betreff{font-weight:600;color:#0ea5e9}
.pf-mail-item.active{background:rgba(59,130,246,.07);border-left-color:#3b82f6!important}
/* Avatar */
.pf-item-avatar{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#fff;flex-shrink:0;letter-spacing:.3px;margin-top:1px}
/* Body */
.pf-item-body{flex:1;min-width:0}
.pf-item-row1{display:flex;justify-content:space-between;align-items:baseline;gap:6px;margin-bottom:2px}
.pf-item-absender{font-size:13px;font-weight:600;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}
.pf-item-datum{font-size:11px;color:var(--text-muted);flex-shrink:0;white-space:nowrap}
.pf-item-betreff{font-size:12px;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-bottom:2px}
.pf-item-row3{display:flex;align-items:center;gap:5px;min-width:0}
.pf-item-preview{font-size:11px;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}
.pf-item-folder-badge{font-size:10px;color:var(--text-muted);background:var(--bg-raised);padding:1px 5px;border-radius:3px;border:1px solid var(--border);white-space:nowrap;flex-shrink:0}
.pf-item-att{width:16px;height:16px;flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;color:var(--text-muted);opacity:.7}
.pf-item-att svg{width:16px;height:16px}
.pf-list-empty{padding:40px 20px;text-align:center;color:var(--text-muted);font-size:13px}
/* RIGHT PREVIEW */
.pf-right{flex:1;overflow:hidden;display:flex;flex-direction:column}
.pf-preview-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--text-muted)}
.pf-prev-hdr{padding:18px 20px 12px;border-bottom:1px solid var(--border);flex-shrink:0}
.pf-prev-betreff{font-size:17px;font-weight:700;color:var(--text);margin-bottom:8px;line-height:1.3}
.pf-prev-meta{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px}
.pf-prev-absender{font-size:13px;color:var(--text-muted)}
.pf-prev-datum{font-size:12px;color:var(--text-muted)}
.pf-prev-acts{display:flex;gap:6px;flex-wrap:wrap}
.pf-act-btn{background:var(--bg-raised);border:1px solid var(--border);border-radius:6px;padding:5px 10px;font-size:12px;cursor:pointer;color:var(--text);transition:.1s}
.pf-act-btn:hover{background:#3b82f6;color:#fff;border-color:#3b82f6}
.pf-prev-anhaenge{padding:8px 20px;background:var(--bg-raised);border-bottom:1px solid var(--border);display:flex;gap:8px;flex-wrap:wrap}
.pf-att-chip{display:flex;align-items:center;gap:4px;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:4px 9px;font-size:12px;cursor:pointer;color:var(--text)}
.pf-att-chip:hover{border-color:#3b82f6;color:#3b82f6}
.pf-prev-body{flex:1;overflow-y:auto;min-height:0;padding:20px;font-size:14px;line-height:1.7;color:var(--text);white-space:pre-wrap;word-break:break-word}
.pf-prev-body.iframe-mode{overflow:hidden;padding:0;display:flex;flex-direction:column}
.pf-thread-hdr{display:flex;align-items:center;gap:8px;padding:10px 20px;background:var(--bg-raised);border-top:1px solid var(--border);cursor:pointer;font-size:12px;font-weight:600;color:var(--text-muted)}
.pf-thread-cnt{background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:1px 7px;font-size:11px}
.pf-thread-msg{padding:12px 20px;border-bottom:1px solid var(--border);font-size:13px}
.pf-thread-msg-hdr{display:flex;justify-content:space-between;margin-bottom:6px;font-size:12px}
.pf-thread-msg-sender{font-weight:600;color:var(--text)}
.pf-thread-msg-date{color:var(--text-muted)}
.pf-thread-msg-body{color:var(--text-muted);white-space:pre-wrap;max-height:120px;overflow:hidden}
/* COMPOSE */
.pf-comp-hdr{display:flex;justify-content:space-between;align-items:center;padding:14px 20px 10px;border-bottom:1px solid var(--border)}
.pf-comp-hdr span{font-weight:700;font-size:15px}
.pf-comp-fields{padding:12px 20px 0;border-bottom:1px solid var(--border)}
.pf-comp-row{display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border)}
.pf-comp-lbl{font-size:12px;color:var(--text-muted);width:45px;flex-shrink:0}
.pf-comp-inp{flex:1;border:none;background:transparent;color:var(--text);font-size:13px;outline:none;padding:2px 0}
.pf-comp-sel{flex:1;border:none;background:transparent;color:var(--text);font-size:13px;outline:none}
.pf-comp-body{flex:1;border:none;resize:none;background:transparent;color:var(--text);font-size:13px;padding:14px 20px;outline:none;min-height:200px;font-family:inherit;line-height:1.6}
.pf-comp-acts{padding:10px 20px;border-top:1px solid var(--border);display:flex;gap:8px;flex-wrap:wrap}
@media(max-width:900px){.pf-left{width:52px}.pf-left-title,.pf-folder-konto,.pf-fav-section,.pf-fav-item span:not(.pf-fav-badge),.pf-folder-item span:not(.pf-folder-badge){display:none}.pf-mid{width:260px}}
/* Resize handles */
.pf-resize-h{width:4px;flex-shrink:0;cursor:col-resize;background:transparent;transition:background .15s;position:relative;z-index:2}
.pf-resize-h::after{content:'';position:absolute;top:0;left:-3px;right:-3px;bottom:0}
.pf-resize-h:hover,.pf-resize-h.dragging{background:rgba(59,130,246,.45)}
/* SVG folder icons */
.pf-fi-icon{width:18px;height:18px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;color:var(--text-muted);opacity:.8}
.pf-fi-icon svg{width:18px;height:18px}
.pf-folder-item.active .pf-fi-icon,.pf-fav-item.active .pf-fi-icon,.pf-combined-btn.active .pf-fi-icon{color:#3b82f6;opacity:1}
/* Combined Inbox button */
.pf-combined-btn{display:flex;align-items:center;gap:9px;padding:9px 14px;cursor:pointer;font-size:13px;color:var(--text);font-weight:600;border-bottom:1px solid var(--border);transition:background .12s;border-left:3px solid transparent}
.pf-combined-btn:hover{background:var(--bg-hover)}
.pf-combined-btn.active{background:rgba(59,130,246,.15);border-left-color:#3b82f6;color:#3b82f6;font-weight:600}
.pf-combined-cfg{padding:8px 14px;border-bottom:1px solid var(--border);display:none;background:var(--bg-raised)}
.pf-combined-cfg label{display:flex;align-items:center;gap:6px;font-size:12px;padding:3px 0;cursor:pointer}
/* Light mode — white backgrounds */
[data-theme="light"] .pf-left{background:#ffffff}
[data-theme="light"] .pf-mid{background:#ffffff}
[data-theme="light"] .pf-right{background:#ffffff}
[data-theme="light"] .pf-mid-hdr{background:#ffffff}
[data-theme="light"] .pf-mail-item{background:#ffffff}
[data-theme="light"] .pf-mail-item:hover{background:#f3f4f6}
[data-theme="light"] .pf-mail-item.unread{background:rgba(14,165,233,.04)}
[data-theme="light"] .pf-mail-item.active{background:rgba(59,130,246,.07)}
[data-theme="light"] .pf-prev-hdr{background:#ffffff}
[data-theme="light"] .pf-prev-body{background:#ffffff}
[data-theme="light"] .pf-preview-empty{background:#ffffff}
[data-theme="light"] .pf-folder-item:hover{background:#f3f4f6}
[data-theme="light"] .pf-folder-item.active{background:#dbeafe;border-left-color:#2563eb;color:#1d4ed8}
[data-theme="light"] .pf-folder-item.active .pf-fi-icon{color:#2563eb}
[data-theme="light"] .pf-fav-item:hover{background:#f3f4f6}
[data-theme="light"] .pf-fav-item.active{background:#dbeafe;border-left-color:#2563eb;color:#1d4ed8}
[data-theme="light"] .pf-fav-item.active .pf-fi-icon{color:#2563eb}
[data-theme="light"] .pf-combined-btn:hover{background:#f3f4f6}
[data-theme="light"] .pf-combined-btn.active{background:#dbeafe;border-left-color:#2563eb;color:#1d4ed8}
[data-theme="light"] .pf-combined-cfg{background:#f8f9fa}
[data-theme="light"] .pf-item-folder-badge{background:#f3f4f6;border-color:rgba(0,0,0,.09)}
/* Star/Favourite toggle on folder items */
.pf-star-btn{background:none;border:none;cursor:pointer;padding:0 3px;font-size:14px;color:var(--text-muted);opacity:0;transition:opacity .15s,color .15s;flex-shrink:0;line-height:1}
.pf-folder-item:hover .pf-star-btn,.pf-star-btn.starred{opacity:1}
.pf-star-btn.starred{color:#f59e0b}
/* Combined inbox expand arrow */
.pf-combined-arrow{font-size:10px;transition:transform .2s;display:inline-block;color:var(--text-muted);flex-shrink:0;cursor:pointer;padding:0 2px}
.pf-combined-btn.expanded .pf-combined-arrow{transform:rotate(0deg)}
.pf-combined-btn:not(.expanded) .pf-combined-arrow{transform:rotate(-90deg)}
/* Combined inbox sub-folders */
.pf-combined-sub{display:none;border-bottom:1px solid var(--border)}
.pf-combined-sub.open{display:block}
.pf-combined-sub-item{display:flex;align-items:center;gap:9px;padding:7px 14px 7px 36px;cursor:pointer;font-size:13px;color:var(--text);transition:background .12s;border-left:3px solid transparent}
.pf-combined-sub-item:hover{background:var(--bg-hover)}
.pf-combined-sub-item.active{background:rgba(59,130,246,.09);border-left-color:#3b82f6;color:#3b82f6}
.pf-combined-sub-item .pf-fi-icon{width:16px;height:16px}
.pf-combined-sub-item .pf-fi-icon svg{width:16px;height:16px}
[data-theme="light"] .pf-combined-sub-item:hover{background:#f3f4f6}
/* Hover-Aktionen auf Mail-Items */
.pf-mail-item{position:relative}
.pf-item-actions{position:absolute;right:8px;top:50%;transform:translateY(-50%);display:none;align-items:center;gap:2px;background:var(--bg-raised);border:1px solid var(--border);border-radius:8px;padding:2px 4px;box-shadow:0 2px 8px rgba(0,0,0,.12)}
.pf-mail-item:hover .pf-item-actions{display:flex}
.pf-mail-item.selected .pf-item-actions{display:flex}
.pf-item-act-btn{background:none;border:none;cursor:pointer;padding:4px 5px;border-radius:5px;color:var(--text-muted);display:flex;align-items:center;transition:background .1s,color .1s;flex-shrink:0}
.pf-item-act-btn:hover{background:var(--bg-hover);color:var(--text)}
.pf-item-act-btn.active{color:#f59e0b}
.pf-item-act-btn.pin-active{color:#3b82f6}
.pf-item-act-btn.trash-btn:hover{background:rgba(200,60,60,.12);color:#c83c3c}
.pf-item-act-btn svg{width:14px;height:14px;display:block;pointer-events:none}
/* Checkbox — overlays the avatar area on hover */
.pf-item-cbx-wrap{position:absolute;left:12px;top:50%;transform:translateY(-50%);width:36px;height:36px;display:flex;align-items:center;justify-content:center;opacity:0;transition:opacity .12s,background .12s;cursor:pointer;border-radius:50%;background:var(--bg-raised)}
.pf-mail-item:hover .pf-item-cbx-wrap,.pf-mail-item.selected .pf-item-cbx-wrap{opacity:1}
.pf-item-cbx{width:15px;height:15px;cursor:pointer;accent-color:#3b82f6;flex-shrink:0}
.pf-mail-item.selected{background:rgba(59,130,246,.07)!important}
/* Pinned + Flagged badges on item */
.pf-item-flag-badge{color:#f59e0b;font-size:12px;flex-shrink:0;line-height:1}
.pf-item-pin-badge{color:#3b82f6;font-size:11px;flex-shrink:0;line-height:1;margin-left:2px}
.pf-item-kira-badge{background:rgba(139,92,246,.15);color:#8b5cf6;border:1px solid rgba(139,92,246,.3);border-radius:4px;font-size:10px;padding:1px 5px;flex-shrink:0;line-height:1.4}
/* Aktionsleiste (single + bulk) */
#pf-bulk-bar{display:none;align-items:center;gap:4px;padding:5px 10px;background:var(--bg-raised);border-bottom:1px solid var(--border);font-size:12px;flex-shrink:0}
#pf-bulk-bar.visible{display:flex}
#pf-bar-single,#pf-bar-bulk{display:none;align-items:center;gap:2px;flex:1}
.pf-bar-btn{background:none;border:none;cursor:pointer;padding:4px 7px;border-radius:6px;color:var(--text-muted);display:flex;align-items:center;gap:4px;font-size:12px;transition:background .1s,color .1s;flex-shrink:0}
.pf-bar-btn:hover{background:var(--bg-hover);color:var(--text)}
.pf-bar-btn.active{color:#f59e0b}
.pf-bar-btn.active-pin{color:#3b82f6}
.pf-bar-btn.pf-bar-del:hover{background:rgba(200,60,60,.12);color:#c83c3c}
.pf-bar-btn.pf-bar-snooze:hover{color:#f59e0b}
.pf-bar-btn svg{width:15px;height:15px;display:block;flex-shrink:0}
.pf-bar-sep{width:1px;height:18px;background:var(--border);margin:0 3px;flex-shrink:0}
/* Snooze-Dropdown */
.pf-snooze-menu{position:fixed;z-index:9999;background:var(--bg-raised);border:1px solid var(--border);border-radius:10px;box-shadow:0 8px 32px rgba(0,0,0,.18);padding:8px;min-width:220px;max-width:280px}
.pf-snooze-title{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:var(--text-muted);padding:2px 8px 6px}
.pf-snooze-opt{display:block;width:100%;text-align:left;background:none;border:none;cursor:pointer;padding:7px 10px;border-radius:7px;font-size:13px;color:var(--text);transition:background .1s}
.pf-snooze-opt:hover{background:var(--bg-hover)}
.pf-snooze-cancel{color:#ef4444;margin-top:4px;border-top:1px solid var(--border);padding-top:9px}
.pf-snooze-custom-row{display:flex;gap:5px;margin-top:6px;padding-top:6px;border-top:1px solid var(--border)}
.pf-snooze-custom-inp{flex:1;padding:5px 8px;font-size:12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text)}
.pf-snooze-custom-btn{padding:5px 10px;font-size:12px;background:#3b82f6;color:#fff;border:none;border-radius:6px;cursor:pointer}
.pf-snooze-custom-btn:hover{background:#2563eb}
.pf-bulk-cnt{font-weight:600;color:#3b82f6;flex:1}
.pf-bulk-btn{background:var(--bg-raised);border:1px solid var(--border);border-radius:6px;padding:4px 10px;font-size:12px;cursor:pointer;color:var(--text);transition:.1s}
.pf-bulk-btn:hover{background:var(--bg-hover)}
.pf-bulk-btn.red:hover{background:rgba(200,60,60,.12);color:#c83c3c;border-color:rgba(200,60,60,.3)}
/* Ordner-Badge Varianten */
.pf-folder-badge{background:rgba(59,130,246,.15);color:#3b82f6;border-radius:9px;font-size:11px;font-weight:600;padding:1px 6px;flex-shrink:0;line-height:1.5;margin-left:auto}
.pf-folder-badge-inbox{background:#3b82f6;color:#fff;border-radius:9px;font-size:12px;font-weight:700;padding:2px 7px;flex-shrink:0;line-height:1.5;margin-left:auto;min-width:20px;text-align:center}
.pf-folder-badge-draft{background:rgba(100,116,139,.15);color:#64748b;border-radius:9px;font-size:11px;padding:1px 6px;flex-shrink:0;line-height:1.5;margin-left:auto;font-style:italic}
.pf-folder-badge-snooze{background:rgba(245,158,11,.15);color:#f59e0b;border-radius:9px;font-size:11px;font-weight:600;padding:1px 6px;flex-shrink:0;line-height:1.5;margin-left:auto}
/* Snooze-Badge auf Mail-Item */
.pf-item-snooze-badge{background:rgba(245,158,11,.15);color:#f59e0b;border:1px solid rgba(245,158,11,.3);border-radius:4px;font-size:10px;padding:1px 5px;flex-shrink:0;line-height:1.4}
/* New preview toolbar */
.pf-prev-toolbar{display:flex;align-items:center;gap:4px;flex-wrap:wrap}
.pf-tb-btn{background:none;border:none;cursor:pointer;padding:5px 7px;border-radius:6px;color:var(--text-muted);display:flex;align-items:center;gap:5px;font-size:12px;transition:background .1s,color .1s}
.pf-tb-btn:hover{background:var(--bg-hover);color:var(--text)}
.pf-tb-btn.active{color:#f59e0b}
.pf-tb-btn.pin-active{color:#3b82f6}
.pf-tb-btn.del-btn:hover{background:rgba(200,60,60,.12);color:#c83c3c}
.pf-tb-btn svg{width:16px;height:16px;display:block;flex-shrink:0}
.pf-tb-sep{width:1px;height:20px;background:var(--border);margin:0 3px;flex-shrink:0}
/* Kira-Button — prominent, Kira-Lila */
.pf-kira-btn{background:linear-gradient(135deg,#7c3aed,#6d28d9)!important;color:#fff!important;border-radius:8px!important;padding:6px 14px!important;font-weight:600!important;font-size:12.5px!important;gap:6px!important;box-shadow:0 2px 8px rgba(124,58,237,.35);transition:box-shadow .15s,transform .1s,background .15s!important}
.pf-kira-btn:hover{background:linear-gradient(135deg,#8b5cf6,#7c3aed)!important;box-shadow:0 4px 16px rgba(124,58,237,.55)!important;transform:translateY(-1px);color:#fff!important}
.pf-kira-btn:active{transform:translateY(0)}
.pf-kira-btn svg{color:#fff!important;opacity:.9;width:15px!important;height:15px!important}
.pf-kira-btn.loading{opacity:.7;pointer-events:none;cursor:wait}
@keyframes spin{to{transform:rotate(360deg)}}

/* ── RIBBON ─────────────────────────────────────────────── */
:root{--pf-ribbon-h:80px}
.pf-ribbon-wrap{background:var(--bg-raised);border-bottom:1px solid var(--border);height:var(--pf-ribbon-h);flex-shrink:0;overflow:hidden}
.pf-ribbon{display:flex;align-items:stretch;height:100%;user-select:none;padding-left:6px}
.pf-rbn-viewport{flex:1;overflow:hidden;position:relative}
.pf-rbn-inner{display:flex;align-items:stretch;height:100%;transition:transform .22s ease;will-change:transform}
.pf-rbn-group{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:0 12px;flex-shrink:0}
.pf-rbn-actions{display:flex;align-items:center;gap:2px;flex:1;padding-top:4px}
.pf-rbn-label{font-size:11px;color:var(--text-muted);letter-spacing:.02px;padding:4px 0 6px;white-space:nowrap;font-weight:400}
.pf-rbn-sep{width:1px;background:var(--border);height:58%;align-self:center;flex-shrink:0;margin:0 12px}
.pf-rbn-tool{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;background:none;border:none;cursor:pointer;padding:7px 11px;border-radius:6px;color:var(--text-muted);font-size:11px;min-width:56px;transition:background .15s,color .15s;flex-shrink:0;font-weight:400;letter-spacing:.01em}
.pf-rbn-tool svg{width:24px;height:24px;display:block;flex-shrink:0;transition:color .15s;fill:currentColor}
.pf-rbn-tool span{line-height:1;white-space:nowrap}
.pf-rbn-tool:hover{background:rgba(0,120,212,.08);color:#0078d4}
.pf-rbn-tool.disabled{opacity:.38;cursor:default;pointer-events:none}
.pf-rbn-tool.pf-rbn-prep{opacity:.5}
.pf-rbn-tool.pf-rbn-prep:hover{opacity:1}
/* Accent colors for specific actions */
.pf-rbn-tool.pf-rbn-accent-orange:not(:hover){color:#ca5010}
.pf-rbn-tool.pf-rbn-accent-red:not(:hover){color:#c4314b}
.pf-rbn-kira{background:linear-gradient(135deg,#7c3aed,#4f46e5)!important;color:#fff!important;border-radius:22px!important;box-shadow:0 2px 12px rgba(79,70,229,.38)!important;padding:8px 20px!important;min-width:auto!important;gap:8px!important;letter-spacing:.02em!important;font-weight:600!important;font-size:12px!important}
.pf-rbn-kira:hover{background:linear-gradient(135deg,#8b5cf6,#7c3aed)!important;color:#fff!important;box-shadow:0 5px 20px rgba(79,70,229,.6)!important;transform:translateY(-1px)!important}
.pf-rbn-kira svg{width:20px!important;height:20px!important;color:#fff!important;fill:#fff!important;opacity:1!important}
.pf-rbn-edge{background:none;border:none;cursor:pointer;padding:0 8px;color:var(--text-muted);font-size:20px;display:flex;align-items:center;transition:color .1s;flex-shrink:0}
.pf-rbn-edge:hover{color:var(--text)}
.pf-rbn-toggle{background:none;border:none;cursor:pointer;padding:0 10px;color:var(--text-muted);font-size:12px;display:flex;align-items:center;border-left:1px solid var(--border);flex-shrink:0;transition:color .1s}
.pf-rbn-toggle:hover{color:var(--text)}
/* Compact mode: icon-only, no labels, smaller */
.pf-ribbon.compact{--pf-ribbon-h:44px}
.pf-ribbon.compact .pf-rbn-label{display:none}
.pf-ribbon.compact .pf-rbn-tool{padding:5px 7px;min-width:38px;gap:0}
.pf-ribbon.compact .pf-rbn-tool svg{width:20px;height:20px}
.pf-ribbon.compact .pf-rbn-tool span{display:none}
.pf-ribbon.compact .pf-rbn-actions{padding-top:0}
.pf-ribbon.compact .pf-rbn-group{padding:0 6px}
/* Responsive: compact auto on narrow screens */
@media(max-width:900px){.pf-ribbon:not(.compact){--pf-ribbon-h:44px}.pf-ribbon:not(.compact) .pf-rbn-label{display:none}.pf-ribbon:not(.compact) .pf-rbn-tool{padding:4px 5px;min-width:36px}.pf-ribbon:not(.compact) .pf-rbn-tool svg{width:20px;height:20px}.pf-ribbon:not(.compact) .pf-rbn-tool span{display:none}.pf-ribbon:not(.compact) .pf-rbn-actions{padding-top:0}}
/* Light mode — elegant white ribbon */
[data-theme="light"] .pf-ribbon-wrap{background:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,.08),0 0 0 1px rgba(0,0,0,.05)}
[data-theme="light"] .pf-ribbon-wrap .pf-rbn-label{color:#5f6368}
[data-theme="light"] .pf-ribbon-wrap .pf-rbn-sep{background:#e0e0e0}
[data-theme="light"] .pf-ribbon-wrap .pf-rbn-tool{color:#444746}
[data-theme="light"] .pf-ribbon-wrap .pf-rbn-tool:hover{background:#e8f0fe;color:#1a73e8}
[data-theme="light"] .pf-ribbon-wrap .pf-rbn-toggle{color:#5f6368;border-left-color:#e0e0e0}
[data-theme="light"] .pf-ribbon-wrap .pf-rbn-toggle:hover{color:#1a73e8;background:#e8f0fe}
[data-theme="light"] .pf-ribbon-wrap .pf-rbn-edge{color:#5f6368}
[data-theme="light"] .pf-ribbon-wrap .pf-rbn-edge:hover{color:#1a73e8}

/* ── DETAIL FRAME (Mail-Lesefläche) ──────────────────────── */
.pf-detail-frame{display:grid;grid-template-rows:auto auto auto minmax(0,1fr);height:100%;overflow:hidden}

/* ── MAIL-KOPF ───────────────────────────────────────────── */
.pf-mail-head{padding:14px 20px 10px;border-bottom:1px solid var(--border);background:var(--bg-raised);flex-shrink:0}
.pf-subject-bar{display:flex;align-items:flex-start;gap:10px;margin-bottom:10px}
.pf-subject-text{font-size:16px;font-weight:700;color:var(--text);flex:1;min-width:0;line-height:1.3;word-break:break-word}
.pf-date-stack{font-size:12px;color:var(--text-muted);flex-shrink:0;white-space:nowrap;padding-top:2px}
.pf-header-meta{display:flex;flex-direction:column;gap:6px}
.pf-sender-col{display:flex;align-items:center;gap:12px;min-width:0}
.pf-avatar{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#fff;flex-shrink:0;background:#3b82f6}
.pf-identity{min-width:0;flex:1}
.pf-from-line{font-size:13px;font-weight:600;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pf-to-line{font-size:11.5px;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:1px}
.pf-head-actions{display:flex;align-items:center;gap:3px;flex-wrap:wrap;flex-shrink:0}
.pf-ha-btn{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:5px 10px;font-size:12px;cursor:pointer;color:var(--text);display:flex;align-items:center;gap:5px;white-space:nowrap;transition:.12s}
.pf-ha-btn:hover{background:var(--bg-hover);border-color:var(--border)}
.pf-ha-btn svg{width:14px;height:14px;flex-shrink:0}
.pf-ha-icon{background:none;border:none;cursor:pointer;padding:5px 6px;border-radius:6px;color:var(--text-muted);display:flex;align-items:center;transition:.12s}
.pf-ha-icon:hover{background:var(--bg-hover);color:var(--text)}
.pf-ha-icon.del-btn:hover{background:rgba(200,60,60,.12);color:#c83c3c}
.pf-ha-icon.active{color:#f59e0b}
.pf-ha-icon.pin-active{color:#3b82f6}
.pf-ha-icon svg{width:16px;height:16px;display:block}
.pf-ha-sep{width:1px;height:20px;background:var(--border);margin:0 3px;flex-shrink:0}
[data-theme="light"] .pf-mail-head{background:#fff}

/* ── HINT-SECTION ────────────────────────────────────────── */
.pf-hint-section{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:6px 20px;background:var(--bg-raised);border-bottom:1px solid var(--border);flex-shrink:0}
.pf-hint{display:inline-flex;align-items:center;gap:4px;font-size:11.5px;padding:3px 9px;border-radius:20px;white-space:nowrap}
.pf-hint-reply{background:rgba(59,130,246,.1);color:#3b82f6;border:1px solid rgba(59,130,246,.25)}
.pf-hint-forwarded{background:rgba(100,116,139,.1);color:var(--text-muted);border:1px solid var(--border)}
.pf-hint-done{background:rgba(16,185,129,.1);color:#10b981;border:1px solid rgba(16,185,129,.25)}
.pf-hint-followup{background:rgba(245,158,11,.1);color:#f59e0b;border:1px solid rgba(245,158,11,.25)}
.pf-hint-kira{background:rgba(139,92,246,.1);color:#8b5cf6;border:1px solid rgba(139,92,246,.25)}
.pf-hint-unread{background:rgba(14,165,233,.1);color:#0ea5e9;border:1px solid rgba(14,165,233,.25)}
[data-theme="light"] .pf-hint-section{background:#f8f9fa}

/* ── ANHANG-SECTION ──────────────────────────────────────── */
.pf-attachment-section{border-bottom:1px solid var(--border);background:var(--bg-raised);flex-shrink:0}
.pf-att-collapsed{display:flex;align-items:center;gap:8px;padding:7px 20px;cursor:pointer}
.pf-att-icon-svg{width:14px;height:14px;flex-shrink:0;color:var(--text-muted)}
.pf-att-summary-text{font-size:12.5px;color:var(--text-muted);flex-shrink:0}
.pf-att-open-btn{background:none;border:none;cursor:pointer;font-size:12px;color:#3b82f6;padding:0 4px;white-space:nowrap}
.pf-att-open-btn:hover{text-decoration:underline}
.pf-att-save-sm{background:none;border:1px solid var(--border);border-radius:5px;cursor:pointer;font-size:11px;color:var(--text-muted);padding:3px 8px;white-space:nowrap;transition:.1s}
.pf-att-save-sm:hover{border-color:#3b82f6;color:#3b82f6}
.pf-att-expanded{background:var(--bg-raised)}
.pf-att-bar-head{display:flex;align-items:center;gap:8px;padding:8px 20px 6px;border-top:1px solid var(--border)}
.pf-att-title{font-size:12px;font-weight:600;color:var(--text)}
.pf-att-count{font-size:11px;color:var(--text-muted);background:var(--bg);border:1px solid var(--border);border-radius:9px;padding:1px 6px}
.pf-att-close-btn{background:none;border:none;cursor:pointer;font-size:11px;color:var(--text-muted);padding:3px 6px;border-radius:5px;transition:.1s}
.pf-att-close-btn:hover{background:var(--bg-hover);color:var(--text)}
.pf-attachment-list{padding:4px 20px 10px;display:flex;flex-direction:column;gap:4px;max-height:220px;overflow-y:auto}
.pf-attachment-row{display:grid;grid-template-columns:48px 1fr auto;align-items:center;gap:10px;padding:6px 8px;border-radius:7px;background:var(--bg);border:1px solid var(--border);transition:.1s}
.pf-attachment-row:hover{border-color:rgba(59,130,246,.4)}
.pf-att-preview-box{width:48px;height:48px;border-radius:5px;background:var(--bg-hover);display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:var(--text-muted);overflow:hidden;flex-shrink:0}
.pf-att-preview-box.pdf{background:rgba(239,68,68,.12);color:#ef4444}
.pf-att-preview-box.doc{background:rgba(59,130,246,.12);color:#3b82f6}
.pf-att-preview-box.zip{background:rgba(245,158,11,.12);color:#f59e0b}
.pf-att-preview-box.img{background:#000}
.pf-att-file-info{min-width:0}
.pf-att-file-name{font-size:12.5px;font-weight:500;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pf-att-file-sub{font-size:11px;color:var(--text-muted);margin-top:1px}
.pf-att-row-actions{display:flex;align-items:center;gap:2px;flex-shrink:0}
.pf-att-act-btn{background:none;border:none;cursor:pointer;padding:5px 6px;border-radius:5px;font-size:13px;color:var(--text-muted);transition:.1s}
.pf-att-act-btn:hover{background:var(--bg-hover);color:var(--text)}
[data-theme="light"] .pf-attachment-section{background:#f8f9fa}
[data-theme="light"] .pf-att-expanded{background:#f8f9fa}
[data-theme="light"] .pf-attachment-row{background:#fff}

/* ── VIEWER / CONTENT-SECTION ─────────────────────────────── */
.pf-content-section{display:flex;flex-direction:column;min-height:0;overflow:hidden}
.pf-viewer-toolbar{display:flex;align-items:center;gap:8px;padding:5px 20px;background:var(--bg-raised);border-bottom:1px solid var(--border);flex-shrink:0}
.pf-state-chip{font-size:11px;padding:2px 8px;border-radius:9px;font-weight:500;white-space:nowrap}
.pf-chip-html{background:rgba(16,185,129,.1);color:#10b981;border:1px solid rgba(16,185,129,.25)}
.pf-chip-text{background:rgba(100,116,139,.1);color:var(--text-muted);border:1px solid var(--border)}
.pf-chip-blocked{background:rgba(245,158,11,.1);color:#f59e0b;border:1px solid rgba(245,158,11,.25)}
.pf-trust-banner{display:flex;align-items:center;gap:10px;padding:6px 20px;background:rgba(245,158,11,.08);border-bottom:1px solid rgba(245,158,11,.25);font-size:12.5px;color:#b45309;flex-shrink:0}
.pf-trust-btn{background:#f59e0b;color:#fff;border:none;border-radius:5px;padding:4px 10px;font-size:11.5px;cursor:pointer}
.pf-trust-btn:hover{background:#d97706}
[data-theme="light"] .pf-viewer-toolbar{background:#f8f9fa}

/* ── GALLERY MODAL ────────────────────────────────────────── */
.pf-gallery-modal{position:fixed;inset:0;z-index:9990;background:rgba(0,0,0,.85);display:flex;align-items:center;justify-content:center}
.pf-gallery-wrap{display:flex;flex-direction:column;width:min(92vw,1100px);height:min(90vh,800px);background:#1a1a1a;border-radius:12px;overflow:hidden}
.pf-gallery-topbar{display:flex;align-items:center;gap:12px;padding:10px 16px;background:rgba(255,255,255,.06);flex-shrink:0}
.pf-gallery-title{font-size:13px;color:rgba(255,255,255,.8);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}
.pf-gallery-counter{font-size:12px;color:rgba(255,255,255,.5);flex-shrink:0}
.pf-gallery-close{background:none;border:none;cursor:pointer;color:rgba(255,255,255,.6);font-size:18px;padding:2px 6px;border-radius:5px;transition:.1s}
.pf-gallery-close:hover{color:#fff;background:rgba(255,255,255,.1)}
.pf-gallery-main{display:flex;align-items:center;justify-content:center;flex:1;min-height:0;position:relative;gap:0}
.pf-gallery-imgwrap{flex:1;display:flex;align-items:center;justify-content:center;height:100%;padding:10px;min-width:0}
.pf-gallery-img{max-width:100%;max-height:100%;object-fit:contain;border-radius:4px;display:block}
.pf-gallery-nav{position:absolute;top:50%;transform:translateY(-50%);background:rgba(255,255,255,.1);border:none;cursor:pointer;color:rgba(255,255,255,.8);font-size:32px;width:44px;height:60px;border-radius:6px;display:flex;align-items:center;justify-content:center;transition:.15s;z-index:2}
.pf-gallery-prev{left:8px}
.pf-gallery-next{right:8px}
.pf-gallery-nav:hover{background:rgba(255,255,255,.2);color:#fff}
.pf-gallery-thumbs{display:flex;gap:6px;padding:8px 16px;background:rgba(0,0,0,.4);overflow-x:auto;flex-shrink:0}
.pf-gallery-thumb{width:56px;height:56px;object-fit:cover;border-radius:4px;cursor:pointer;opacity:.55;border:2px solid transparent;transition:.15s;flex-shrink:0}
.pf-gallery-thumb:hover{opacity:.85}
.pf-gallery-thumb.active{opacity:1;border-color:#fff}
</style>

<script>
(function(){
let _pfCurrentFolder = null;
let _pfCurrentKonto  = null;
let _pfOffset = 0;
let _pfTotal  = 0;
let _pfSearch = '';
let _pfSearchTimer = null;
let _pfActiveItem = null;
let _pfThreadOpen = false;

// ── Init ─────────────────────────────────────────────────
// ── Konto-Ampel für Postfach ─────────────────────────────
let _pfHealthCache = {};
let _pfTotalUnread = 0;
let _pfHasHealthError = false;

function _pfUpdateSidebarBadge() {
  const badge = document.getElementById('nav-postfach-badge');
  if(!badge) return;
  if(_pfTotalUnread > 0) {
    badge.textContent = _pfTotalUnread > 999 ? '999+' : _pfTotalUnread;
    badge.style.display = '';
    if(_pfHasHealthError) {
      badge.style.background='rgba(200,60,60,.12)';badge.style.color='#c83c3c';badge.style.borderColor='rgba(200,60,60,.25)';
    } else {
      badge.style.background='rgba(59,130,246,.12)';badge.style.color='#3b82f6';badge.style.borderColor='rgba(59,130,246,.25)';
    }
  } else if(_pfHasHealthError) {
    badge.textContent='⚠';badge.style.display='';
    badge.style.background='rgba(200,60,60,.12)';badge.style.color='#c83c3c';badge.style.borderColor='rgba(200,60,60,.25)';
  } else {
    badge.style.display='none';
  }
}

function pfLoadHealth() {
  fetch('/api/mail/konto/health').then(r=>r.json()).then(d=>{
    _pfHealthCache = d.health || {};
    _pfHasHealthError = false;
    // Ampeln in Folder-Tree aktualisieren — nur sichtbare Konten prüfen
    Object.entries(_pfHealthCache).forEach(([email, h])=>{
      const safe=email.replace(/[@.]/g,'_');
      const dot=document.getElementById('pf-ampel-'+safe);
      if(!dot) return; // Konto nicht im Postfach sichtbar → ignorieren
      if(h.status==='ok') { dot.style.color='#28c850'; dot.title='Verbunden'; }
      else if(h.status==='auth_fehler') { dot.style.color='#c83c3c'; dot.title='Anmeldung fehlgeschlagen'; _pfHasHealthError=true; }
      else { dot.style.color='#f0a000'; dot.title='Verbindungsproblem: '+(h.error||''); _pfHasHealthError=true; }
    });
    _pfUpdateSidebarBadge();
  }).catch(()=>{});
}

let _pfRefreshTimer = null;
function pfInit() {
  pfInitResize(); // restore pane widths (DOM now exists)
  pfRibbonInit(); // init fixed ribbon
  _pfInitToolbar(); // bind preview toolbar buttons
  fetch('/api/mail/folders').then(r=>r.json()).then(data=>{
    document.getElementById('pf-folders-loading').style.display='none';
    pfLoadHealth(); // Ampeln laden
    // Auto-select: Standardkonto bevorzugen, sonst erstes Konto — NACH DOM-Aufbau in onReady-Callback
    const stdEmail = data.standard_konto || '';
    const autoKonto = (stdEmail && data.konten?.find(k=>k.email===stdEmail)) || data.konten?.[0];
    const autoIb = autoKonto && (autoKonto.ordner?.find(o=>o.name.toLowerCase().includes('inbox')||o.name.toLowerCase().includes('posteingang')) || autoKonto.ordner?.[0]);
    pfRenderFolders(data, ()=>{
      if(autoKonto && autoIb) pfSelectFolder(autoKonto.email, autoIb.name, autoIb.label||autoIb.name);
    });
    // Periodisches Refresh: Unread-Badge + Ampeln (Intervall aus Einstellungen)
    if(_pfRefreshTimer) clearInterval(_pfRefreshTimer);
    fetch('/api/einstellungen').then(r=>r.json()).then(cfg=>{
      const mins=(cfg.mail_postfach?.refresh_intervall_min)||0;
      if(mins>0) _pfRefreshTimer=setInterval(pfRefreshBadge, mins*60000);
      _pfMarkReadMode=cfg.mail_postfach?.lese_markierung||'sofort';
    }).catch(()=>{}); // Bei Fehler: kein Auto-Refresh
  }).catch(e=>{
    document.getElementById('pf-folders-loading').textContent='Konten konnten nicht geladen werden.';
  });
}

function pfRefreshBadge() {
  fetch('/api/mail/folders').then(r=>r.json()).then(data=>{
    _pfTotalUnread = 0;
    (data.konten||[]).forEach(konto=>{
      const safe=konto.email.replace(/[@.]/g,'_');
      (konto.ordner||[]).forEach(ord=>{
        const fid='pf-fi-'+safe+'_'+ord.name.replace(/[^a-z0-9]/gi,'_');
        const el=document.getElementById(fid);
        if(el) {
          const b=el.querySelector('.pf-folder-badge');
          if(ord.unread>0) {
            if(b) b.textContent=ord.unread;
            else { const s=document.createElement('span');s.className='pf-folder-badge';s.textContent=ord.unread;el.appendChild(s); }
          } else if(b) b.remove();
        }
        if(ord.name.toLowerCase().includes('inbox')||ord.name.toLowerCase().includes('posteingang')) {
          _pfTotalUnread+=(ord.unread||0);
        }
      });
    });
    _pfUpdateSidebarBadge();
  }).catch(()=>{});
  pfLoadHealth();
}

// ── Pane Resize ──────────────────────────────────────────
function pfInitResize() {
  const saved = JSON.parse(localStorage.getItem('pf_pane_w')||'{}');
  const shell = document.querySelector('.pf-shell');
  if(!shell) return;
  if(saved.left) shell.style.setProperty('--pf-left-w', saved.left+'px');
  if(saved.mid) shell.style.setProperty('--pf-mid-w', saved.mid+'px');

  function makeHandle(handleId, paneId, varName, min, max, key) {
    const handle = document.getElementById(handleId);
    if(!handle) return;
    if(handle._pfResizeInit) return; // avoid double-binding
    handle._pfResizeInit = true;
    let startX, startW;
    handle.addEventListener('mousedown', function(e) {
      const pane = document.getElementById(paneId);
      startX = e.clientX; startW = pane.offsetWidth;
      handle.classList.add('dragging');
      document.body.style.cssText += ';cursor:col-resize;user-select:none';
      const onMove = e2 => { const w=Math.max(min,Math.min(max,startW+e2.clientX-startX)); shell.style.setProperty(varName,w+'px'); };
      const onUp = () => {
        const w=parseInt(shell.style.getPropertyValue(varName))||startW;
        const s=JSON.parse(localStorage.getItem('pf_pane_w')||'{}');
        s[key]=w; localStorage.setItem('pf_pane_w',JSON.stringify(s));
        handle.classList.remove('dragging');
        document.body.style.cursor=''; document.body.style.userSelect='';
        document.removeEventListener('mousemove',onMove); document.removeEventListener('mouseup',onUp);
      };
      document.addEventListener('mousemove',onMove); document.addEventListener('mouseup',onUp);
      e.preventDefault();
    });
  }
  makeHandle('pf-resize-1','pf-left','--pf-left-w',160,380,'left');
  makeHandle('pf-resize-2','pf-mid','--pf-mid-w',240,600,'mid');
}

// ── SVG Folder Icons ─────────────────────────────────────
function pfFolderIconWrap(name) {
  const n=(name||'').toLowerCase();
  let svg;
  if(n.includes('inbox')||n.includes('posteingang')||n.includes('eingang'))
    svg='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6L16.55 5.11A2 2 0 0 0 14.76 4H9.24A2 2 0 0 0 7.45 5.11z"/></svg>';
  else if(n.includes('sent')||n.includes('gesendet'))
    svg='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
  else if(n.includes('draft')||n.includes('entwurf'))
    svg='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';
  else if(n.includes('delet')||n.includes('trash')||n.includes('gelöscht')||n.includes('papierkorb')||n.includes('papier'))
    svg='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>';
  else if(n.includes('junk')||n.includes('spam'))
    svg='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>';
  else if(n.includes('archiv')||n.includes('archive'))
    svg='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>';
  else if(n.includes('star')||n.includes('starred'))
    svg='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>';
  else if(n.includes('outbox')||n.includes('postausgang'))
    svg='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>';
  else if(n.includes('note')||n.includes('notiz'))
    svg='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>';
  else
    svg='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>';
  return '<span class="pf-fi-icon">'+svg+'</span>';
}

// ── Combined Inbox ────────────────────────────────────────
let _pfCombinedKonten = [];  // loaded from API
window.pfToggleCombinedCfg = function() {
  const cfg = document.getElementById('pf-combined-cfg');
  if(cfg) cfg.style.display = cfg.style.display==='none' ? 'block' : 'none';
};
window.pfSaveCombinedKonten = function() {
  const checks = document.querySelectorAll('#pf-combined-cfg input[type=checkbox]');
  const konten = Array.from(checks).filter(c=>c.checked).map(c=>c.value);
  fetch('/api/mail/combined/konten',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({konten})})
  .then(r=>r.json()).then(d=>{
    if(d.ok){showToast('Gemeinsames Postfach gespeichert','ok');_pfCombinedKonten=konten;document.getElementById('pf-combined-cfg').style.display='none';}
    else showToast('Fehler: '+(d.error||'?'),'fehler');
  }).catch(()=>{});
};
window.pfSelectCombined = function() {
  _pfCurrentKonto='_combined_'; _pfCurrentFolder=''; _pfCurrentFolderType='all'; _pfCurrentFolderLabel='Gemeinsames Postfach'; _pfOffset=0; _pfSearch='';
  document.getElementById('pf-mid-title').textContent='Gemeinsames Postfach';
  document.getElementById('pf-search').value='';
  document.querySelectorAll('.pf-folder-item,.pf-fav-item,.pf-combined-sub-item').forEach(el=>el.classList.remove('active'));
  const cb = document.getElementById('pf-combined-btn');
  if(cb) { document.querySelectorAll('.pf-combined-btn').forEach(e=>e.classList.remove('active')); cb.classList.add('active'); }
  pfLoadList(true);
};
window.pfToggleCombinedExpand = function(e) {
  if(e) e.stopPropagation();
  _pfCombinedExpanded = !_pfCombinedExpanded;
  const sub = document.getElementById('pf-combined-sub');
  const btn = document.getElementById('pf-combined-btn');
  if(sub) sub.classList.toggle('open', _pfCombinedExpanded);
  if(btn) btn.classList.toggle('expanded', _pfCombinedExpanded);
};
window.pfSelectCombinedSub = function(folderType, label, el, e) {
  if(e) e.stopPropagation();
  _pfCurrentKonto='_combined_'; _pfCurrentFolder=''; _pfCurrentFolderType=folderType;
  _pfCurrentFolderLabel=label; _pfOffset=0; _pfSearch='';
  document.getElementById('pf-mid-title').textContent='Gemeinsames Postfach — '+label;
  document.getElementById('pf-search').value='';
  document.querySelectorAll('.pf-folder-item,.pf-fav-item,.pf-combined-btn').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.pf-combined-sub-item').forEach(x=>x.classList.remove('active'));
  if(el) el.classList.add('active');
  pfLoadList(true);
};
window.pfToggleFavorite = function(konto, folder, label, btn, e) {
  if(e) e.stopPropagation();
  const isStarred = btn.classList.contains('starred');
  const action = isStarred ? 'remove' : 'add';
  fetch('/api/mail/favorites',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({konto,folder,label,action})})
  .then(r=>r.json()).then(d=>{
    if(d.ok) {
      _pfFavorites = d.favorites;
      btn.classList.toggle('starred', !isStarred);
      btn.innerHTML = isStarred ? '&#x2606;' : '&#x2605;';
      btn.title = isStarred ? 'Zu Favoriten hinzuf\u00fcgen' : 'Aus Favoriten entfernen';
      if(_pfFolderData) pfRenderFolders(_pfFolderData);
    }
  }).catch(()=>{});
};

// ── Folder Tree ──────────────────────────────────────────
let _pfCollapsed = {};
try { _pfCollapsed = JSON.parse(localStorage.getItem('pf_collapsed')||'{}'); } catch(e){}
let _pfLastGroup = null;
let _pfCurrentFolderLabel = '';
let _pfFavorites = [];          // saved favorites from /api/mail/favorites
let _pfCombinedExpanded = true; // combined inbox sub-folders open
let _pfCurrentFolderType = '';  // for combined sub-folder filter (inbox|sent|drafts|all)
let _pfFolderData = null;       // cached last /api/mail/folders response for re-render
let _pfSelected = new Set();    // selected message_ids for bulk actions
let _pfCurrentMail = null;      // currently open mail object
let _pfMarkReadMode = 'sofort'; // sofort|5s|30s|manuell
let _pfMarkReadTimer = null;    // pending mark-read timeout

// ── SVG Icons ────────────────────────────────────────────
const _SVG_READ='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6L16.55 5.11A2 2 0 0 0 14.76 4H9.24A2 2 0 0 0 5.45 5.11z"/></svg>';
const _SVG_FLAG='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>';
const _SVG_PIN='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24z"/></svg>';
const _SVG_TRASH='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>';
const _SVG_ENV='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>';

// ── Bulk Selection ────────────────────────────────────────
function pfToggleSelect(msgId, checked) {
  if(checked) _pfSelected.add(msgId); else _pfSelected.delete(msgId);
  const el=document.querySelector('[data-msgid="'+msgId+'"]');
  if(el) el.classList.toggle('selected',checked);
  pfUpdateBulkBar();
}
function pfUpdateBulkBar() {
  const bar    = document.getElementById('pf-bulk-bar');
  const single = document.getElementById('pf-bar-single');
  const bulk   = document.getElementById('pf-bar-bulk');
  const cnt    = document.getElementById('pf-bulk-cnt');
  if(!bar) return;
  const n = _pfSelected.size;
  if(n > 0) {
    // Bulk-Modus
    bar.classList.add('visible');
    if(single) single.style.display='none';
    if(bulk)   bulk.style.display='flex';
    if(cnt)    cnt.textContent = n + ' ausgew\u00e4hlt';
  } else if(_pfCurrentMail) {
    // Single-Modus
    bar.classList.add('visible');
    if(single) single.style.display='flex';
    if(bulk)   bulk.style.display='none';
    // Flag/Pin-Buttons aktualisieren
    const m = _pfCurrentMail;
    const bFlag = document.getElementById('pf-bar-flag');
    const bPin  = document.getElementById('pf-bar-pin');
    if(bFlag) bFlag.classList.toggle('active', !!(m.flagged));
    if(bPin)  bPin.classList.toggle('active-pin', !!(m.pinned));
  } else {
    bar.classList.remove('visible');
    if(single) single.style.display='none';
    if(bulk)   bulk.style.display='none';
  }
}
// Aktionsleiste — Single-Mail-Aktionen
function pfBarDeleteCurrent() {
  if(!_pfCurrentMail) return;
  const id = _pfCurrentMail.message_id;
  showKritischModal('Mail l\u00f6schen','Diese Mail endg\u00fcltig l\u00f6schen?','LOESCHEN',()=>{
    fetch('/api/mail/loeschen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[id]})})
    .then(r=>r.json()).then(d=>{
      if(d.ok){
        const el=document.querySelector('[data-msgid="'+id+'"]');
        if(el) el.remove();
        _pfCurrentMail=null;
        pfRibbonUpdateState(false);
        document.getElementById('pf-preview').style.display='none';
        document.getElementById('pf-preview-empty').style.display='flex';
        pfUpdateBulkBar();
      }
    }).catch(()=>{});
  },'Diese Aktion kann nicht r\u00fcckg\u00e4ngig gemacht werden.');
}
function pfBarFlagCurrent() {
  if(!_pfCurrentMail) return;
  const el = document.querySelector('[data-msgid="'+_pfCurrentMail.message_id+'"]');
  if(el) pfToggleFlag(_pfCurrentMail.message_id, el);
}
function pfBarPinCurrent() {
  if(!_pfCurrentMail) return;
  const el = document.querySelector('[data-msgid="'+_pfCurrentMail.message_id+'"]');
  if(el) pfTogglePin(_pfCurrentMail.message_id, el);
}

// ── Snooze / Erneut erinnern ─────────────────────────────
let _pfSnoozeMenu = null;
window.pfOpenSnoozeMenu = function(btn) {
  if(_pfSnoozeMenu) { _pfSnoozeMenu.remove(); _pfSnoozeMenu=null; return; }
  if(!_pfCurrentMail) return;
  const menu = document.createElement('div');
  menu.id = 'pf-snooze-menu';
  menu.className = 'pf-snooze-menu';
  const now = new Date();
  const todayEvening = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 18, 0, 0);
  const tomorrowMorning = new Date(now.getFullYear(), now.getMonth(), now.getDate()+1, 8, 0, 0);
  const nextMonday = new Date(now); nextMonday.setDate(now.getDate()+(8-now.getDay())%7||7); nextMonday.setHours(8,0,0,0);
  const _toISO = d => d.toISOString().slice(0,19).replace('T',' ');
  const presets = [
    {label:'30 Minuten', iso: _toISO(new Date(now.getTime()+30*60000))},
    {label:'1 Stunde',   iso: _toISO(new Date(now.getTime()+60*60000))},
    {label:'2 Stunden',  iso: _toISO(new Date(now.getTime()+2*3600000))},
    {label:'4 Stunden',  iso: _toISO(new Date(now.getTime()+4*3600000))},
    {label:'Heute Abend (18:00)', iso: _toISO(todayEvening)},
    {label:'Morgen fr\u00fch (08:00)', iso: _toISO(tomorrowMorning)},
    {label:'N\u00e4chste Woche', iso: _toISO(nextMonday)},
  ];
  // Titel (keine onclick-Strings — DOM-Methoden vermeiden Quote-Escaping-Probleme)
  const titleEl = document.createElement('div');
  titleEl.className = 'pf-snooze-title';
  titleEl.textContent = '\u23f0 Erneut erinnern';
  menu.appendChild(titleEl);
  presets.forEach(p=>{
    const b = document.createElement('button');
    b.className = 'pf-snooze-opt';
    b.textContent = p.label;
    b.addEventListener('click', ()=>pfSnoozeUntil(p.iso, menu));
    menu.appendChild(b);
  });
  // Freitext-Zeile
  const customRow = document.createElement('div');
  customRow.className = 'pf-snooze-custom-row';
  const inp = document.createElement('input');
  inp.className = 'pf-snooze-custom-inp';
  inp.id = 'pf-snooze-custom';
  inp.placeholder = 'z.B. 2h30m oder 2026-04-01 09:00';
  inp.addEventListener('keydown', e=>{ if(e.key==='Enter') pfSnoozeCustom(); });
  const okBtn = document.createElement('button');
  okBtn.className = 'pf-snooze-custom-btn';
  okBtn.textContent = 'OK';
  okBtn.addEventListener('click', ()=>pfSnoozeCustom());
  customRow.appendChild(inp); customRow.appendChild(okBtn);
  menu.appendChild(customRow);
  if(_pfCurrentMail.snooze_until) {
    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'pf-snooze-opt pf-snooze-cancel';
    cancelBtn.textContent = '\u274c Erinnerung aufheben';
    cancelBtn.addEventListener('click', ()=>pfSnoozeUntil(null, menu));
    menu.appendChild(cancelBtn);
  }
  const rect = btn.getBoundingClientRect();
  menu.style.top  = (rect.bottom+6+window.scrollY)+'px';
  menu.style.left = (rect.left+window.scrollX)+'px';
  document.body.appendChild(menu);
  _pfSnoozeMenu = menu;
  const _close = e=>{ if(!menu.contains(e.target)&&e.target!==btn){ menu.remove(); _pfSnoozeMenu=null; document.removeEventListener('mousedown',_close); } };
  setTimeout(()=>document.addEventListener('mousedown',_close),10);
};
window.pfSnoozeUntil = function(isoDatetime, menuEl) {
  if(!_pfCurrentMail) return;
  if(menuEl) { menuEl.remove(); _pfSnoozeMenu=null; }
  const konto = _pfCurrentMail.konto || _pfCurrentKonto || '';
  fetch('/api/mail/snooze',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({message_id:_pfCurrentMail.message_id, snooze_until:isoDatetime, konto})})
  .then(r=>r.json()).then(d=>{
    if(d.ok) {
      _pfCurrentMail.snooze_until = isoDatetime;
      const itemEl=document.querySelector('[data-msgid="'+_pfCurrentMail.message_id+'"]');
      if(isoDatetime) {
        // Mail aus aktueller Inbox-Ansicht entfernen (snooze versteckt sie)
        if(_pfCurrentFolder && /inbox|posteingang/i.test(_pfCurrentFolder)) {
          if(itemEl) itemEl.remove();
          _pfCurrentMail=null;
          pfRibbonUpdateState(false);
          document.getElementById('pf-preview').style.display='none';
          document.getElementById('pf-preview-empty').style.display='flex';
          pfUpdateBulkBar();
        }
        showToast('Erinnerung gesetzt: '+d.snooze_label,'ok');
        // Snooze-Badge auf Bar-Button
        const sb=document.getElementById('pf-bar-snooze');
        if(sb) sb.classList.add('active');
      } else {
        showToast('Erinnerung aufgehoben','info');
        const sb=document.getElementById('pf-bar-snooze');
        if(sb) sb.classList.remove('active');
      }
      if(d.imap_ordner_erstellt) showToast('IMAP-Ordner "Erneut erinnern" automatisch angelegt','info');
    } else { showToast('Fehler: '+(d.error||'?'),'fehler'); }
  }).catch(()=>{showToast('Verbindungsfehler','fehler');});
};
window.pfSnoozeCustom = function() {
  const inp = document.getElementById('pf-snooze-custom');
  if(!inp) return;
  const val = inp.value.trim();
  if(!val) return;
  // Versuche ISO-Datum zuerst
  const isoMatch = val.match(/^(\\d{4}-\\d{2}-\\d{2})\\s*(\\d{2}:\\d{2}(?::\\d{2})?)$/);
  if(isoMatch) {
    pfSnoozeUntil(isoMatch[1]+' '+(isoMatch[2].length===5?isoMatch[2]+':00':isoMatch[2]), _pfSnoozeMenu);
    return;
  }
  // Parse Zeitdauer: 2h30m, 45min, 3d, 1h, etc.
  const now = new Date();
  let ms = 0;
  val.replace(/(\\d+(?:\\.\\d+)?)\\s*([dhm](?:in)?)/gi, (_, n, u) => {
    const x = parseFloat(n);
    if(u.toLowerCase()==='d') ms += x*86400000;
    else if(u.toLowerCase()==='h') ms += x*3600000;
    else ms += x*60000;
  });
  if(ms > 0) {
    const target = new Date(now.getTime()+ms);
    pfSnoozeUntil(target.toISOString().slice(0,19).replace('T',' '), _pfSnoozeMenu);
  } else {
    showToast('Format nicht erkannt. Beispiele: 2h30m, 45min, 1d, 2026-04-01 09:00','fehler');
  }
};

function pfClearSelection() {
  _pfSelected.forEach(id=>{const el=document.querySelector('[data-msgid="'+id+'"]');if(el)el.classList.remove('selected');});
  _pfSelected.clear();
  pfUpdateBulkBar();
}
function pfBulkMarkRead(gelesen) {
  const ids=[..._pfSelected];
  if(!ids.length) return;
  fetch('/api/mail/gelesen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids,gelesen})})
  .then(r=>r.json()).then(d=>{
    if(d.ok){
      ids.forEach(id=>{
        const el=document.querySelector('[data-msgid="'+id+'"]');
        if(el){if(gelesen)el.classList.remove('unread');else el.classList.add('unread');}
      });
      pfClearSelection();
      _pfUpdateSidebarBadge();
    }
  }).catch(()=>{});
}
function pfBulkDelete() {
  const ids=[..._pfSelected];
  if(!ids.length) return;
  showKritischModal('Mails l\u00f6schen','Sollen '+ids.length+' Mails endg\u00fcltig gel\u00f6scht werden?','LOESCHEN',()=>{
    fetch('/api/mail/loeschen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})})
    .then(r=>r.json()).then(d=>{
      if(d.ok){
        ids.forEach(id=>{const el=document.querySelector('[data-msgid="'+id+'"]');if(el)el.remove();});
        pfClearSelection();
      }
    }).catch(()=>{});
  },'Diese Aktion kann nicht r\u00fcckg\u00e4ngig gemacht werden.');
}

// ── Item-Level Actions ────────────────────────────────────
function pfToggleRead(msgId, el) {
  const isUnread=el.classList.contains('unread');
  const gelesen=isUnread?1:0;
  fetch('/api/mail/gelesen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[msgId],gelesen:!!gelesen})})
  .then(r=>r.json()).then(d=>{
    if(d.ok){
      if(gelesen) el.classList.remove('unread'); else el.classList.add('unread');
      _pfTotalUnread+=(gelesen?-1:1);
      if(_pfTotalUnread<0)_pfTotalUnread=0;
      _pfUpdateSidebarBadge();
    }
  }).catch(()=>{});
}
function pfToggleFlag(msgId, el) {
  const isFlagged=el.dataset.flagged==='1';
  fetch('/api/mail/flag',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message_id:msgId,flagged:!isFlagged})})
  .then(r=>r.json()).then(d=>{
    if(d.ok){
      el.dataset.flagged=isFlagged?'0':'1';
      const badge=el.querySelector('.pf-item-flag-badge');
      if(badge) badge.style.display=isFlagged?'none':'';
      const tbFlag=document.getElementById('pf-tb-flag');
      if(_pfCurrentMail&&_pfCurrentMail.message_id===msgId&&tbFlag){
        tbFlag.classList.toggle('active',!isFlagged);
      }
    }
  }).catch(()=>{});
}
function pfTogglePin(msgId, el) {
  const isPinned=el.dataset.pinned==='1';
  fetch('/api/mail/pin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message_id:msgId,pinned:!isPinned})})
  .then(r=>r.json()).then(d=>{
    if(d.ok){
      el.dataset.pinned=isPinned?'0':'1';
      const badge=el.querySelector('.pf-item-pin-badge');
      if(badge) badge.style.display=isPinned?'none':'';
      const tbPin=document.getElementById('pf-tb-pin');
      if(_pfCurrentMail&&_pfCurrentMail.message_id===msgId&&tbPin){
        tbPin.classList.toggle('pin-active',!isPinned);
      }
    }
  }).catch(()=>{});
}
function pfDeleteMail(msgId, el) {
  showKritischModal('Mail l\u00f6schen','Soll diese Mail endg\u00fcltig gel\u00f6scht werden?','LOESCHEN',()=>{
    fetch('/api/mail/loeschen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[msgId]})})
    .then(r=>r.json()).then(d=>{
      if(d.ok){
        el.remove();
        if(_pfCurrentMail&&_pfCurrentMail.message_id===msgId){
          document.getElementById('pf-preview').style.display='none';
          document.getElementById('pf-preview-empty').style.display='';
          _pfCurrentMail=null;
          pfRibbonUpdateState(false);
        }
      }
    }).catch(()=>{});
  },'Diese Aktion kann nicht r\u00fcckg\u00e4ngig gemacht werden.');
}

// ── Preview Toolbar Binding ───────────────────────────────
function _pfInitToolbar() {
  const tb=document.getElementById('pf-prev-toolbar');
  if(!tb||tb._pfBound) return;
  tb._pfBound=true;
  document.getElementById('pf-tb-reply')?.addEventListener('click',()=>pfReply());
  document.getElementById('pf-tb-replyall')?.addEventListener('click',()=>pfReplyAll());
  document.getElementById('pf-tb-forward')?.addEventListener('click',()=>pfForward());
  document.getElementById('pf-tb-kira')?.addEventListener('click',()=>pfKiraMailContext());
  document.getElementById('pf-tb-read')?.addEventListener('click',()=>{
    if(!_pfCurrentMail) return;
    const el=document.querySelector('[data-msgid="'+_pfCurrentMail.message_id+'"]');
    if(el) pfToggleRead(_pfCurrentMail.message_id, el);
  });
  document.getElementById('pf-tb-flag')?.addEventListener('click',()=>{
    if(!_pfCurrentMail) return;
    const el=document.querySelector('[data-msgid="'+_pfCurrentMail.message_id+'"]');
    if(el) pfToggleFlag(_pfCurrentMail.message_id, el);
  });
  document.getElementById('pf-tb-pin')?.addEventListener('click',()=>{
    if(!_pfCurrentMail) return;
    const el=document.querySelector('[data-msgid="'+_pfCurrentMail.message_id+'"]');
    if(el) pfTogglePin(_pfCurrentMail.message_id, el);
  });
  document.getElementById('pf-tb-delete')?.addEventListener('click',()=>{
    if(!_pfCurrentMail) return;
    const el=document.querySelector('[data-msgid="'+_pfCurrentMail.message_id+'"]');
    if(el) pfDeleteMail(_pfCurrentMail.message_id, el);
  });
}
function pfReplyAll() {
  if(!_pfCurrentMail) return;
  pfReply(); // reuse pfReply — To: is the sender; CC from the mail can be added manually
}

function pfRenderFolders(data, onReady) {
  _pfFolderData = data; // cache for re-render after star toggle
  const tree = document.getElementById('pf-folder-tree');
  const fromSel = document.getElementById('pf-comp-from');
  if(fromSel) fromSel.innerHTML='';
  tree.innerHTML = '';
  _pfTotalUnread = 0;

  Promise.all([
    fetch('/api/mail/combined/konten').then(r=>r.json()).catch(()=>({konten:[]})),
    fetch('/api/mail/favorites').then(r=>r.json()).catch(()=>({favorites:[]}))
  ]).then(([combinedData, favData])=>{
    _pfCombinedKonten = combinedData.konten||[];
    _pfFavorites = favData.favorites||[];

    // ── Gemeinsames Postfach ─────────────────────────────────────────────────
    const cb = document.createElement('div');
    cb.className = 'pf-combined-btn'+(_pfCombinedExpanded?' expanded':'');
    cb.id = 'pf-combined-btn';
    cb.innerHTML = '<span class="pf-combined-arrow" onclick="pfToggleCombinedExpand(event)">&#x25BC;</span>'
      +pfFolderIconWrap('inbox combined')
      +'<span style="flex:1" onclick="pfSelectCombined()">Gemeinsames Postfach</span>'
      +'<button onclick="pfToggleCombinedCfg()" style="border:none;background:transparent;cursor:pointer;font-size:13px;color:var(--text-muted);padding:2px 4px" title="Konfigurieren">&#x2699;</button>';
    tree.appendChild(cb);

    // Sub-folders
    const subDiv = document.createElement('div');
    subDiv.className = 'pf-combined-sub'+(_pfCombinedExpanded?' open':'');
    subDiv.id = 'pf-combined-sub';
    [{type:'inbox',icon:'inbox',label:'Posteingang'},{type:'unread',icon:'inbox',label:'Ungelesene'},{type:'sent',icon:'sent',label:'Gesendet'},{type:'drafts',icon:'draft',label:'Entw\u00fcrfe'},{type:'snoozed',icon:'star',label:'Erinnert mich'}].forEach(sf=>{
      const si = document.createElement('div');
      si.className = 'pf-combined-sub-item';
      si.dataset.folderType = sf.type;
      si.innerHTML = pfFolderIconWrap(sf.icon)+'<span style="flex:1">'+sf.label+'</span>';
      si.onclick = e=>pfSelectCombinedSub(sf.type, sf.label, si, e);
      subDiv.appendChild(si);
    });
    tree.appendChild(subDiv);

    // Config panel
    const cfgDiv = document.createElement('div');
    cfgDiv.className = 'pf-combined-cfg'; cfgDiv.id = 'pf-combined-cfg'; cfgDiv.style.display='none';
    const allKonten=(data.konten||[]).map(k=>k.email);
    cfgDiv.innerHTML = '<div style="font-size:11px;font-weight:600;margin-bottom:6px;color:var(--text-muted)">Konten im Gemeinsamen Postfach:</div>'
      +allKonten.map(e=>`<label><input type="checkbox" value="${e}" ${_pfCombinedKonten.includes(e)?'checked':''}> ${e}</label>`).join('')
      +'<div style="margin-top:8px"><button onclick="pfSaveCombinedKonten()" style="font-size:11px;padding:3px 10px;background:#3b82f6;color:#fff;border:none;border-radius:5px;cursor:pointer">Speichern</button></div>';
    tree.appendChild(cfgDiv);

    // ── Favoriten ─────────────────────────────────────────────────────────────
    const unreadInboxes = [];
    (data.konten||[]).forEach(konto=>{
      const displayName = konto.display_name || konto.label || konto.email.split('@')[0].toUpperCase();
      (konto.ordner||[]).forEach(ord=>{
        const isInbox = /inbox|posteingang/i.test(ord.name);
        if(isInbox) {
          _pfTotalUnread += (ord.unread||0);
          if(ord.unread>0) unreadInboxes.push({konto, displayName, inbox:ord});
        }
      });
    });
    const hasFavs = _pfFavorites.length>0 || unreadInboxes.length>0;
    if(hasFavs) {
      const favHdr = document.createElement('div');
      favHdr.className='pf-fav-section'; favHdr.textContent='Favoriten';
      tree.appendChild(favHdr);
      // Saved config favorites first
      _pfFavorites.forEach(fav=>{
        const fi = document.createElement('div');
        fi.className = 'pf-fav-item';
        fi.dataset.konto = fav.konto;
        fi.dataset.folder = fav.folder;
        const domain = (fav.konto||'').split('@')[1]||fav.konto;
        fi.innerHTML = pfFolderIconWrap(fav.folder)
          +'<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+fav.label+'</span>'
          +'<span style="font-size:10px;color:var(--text-muted);flex-shrink:0;overflow:hidden;text-overflow:ellipsis;max-width:80px">'+domain+'</span>';
        fi.onclick = ()=>pfSelectFolder(fav.konto, fav.folder, fav.label, fi);
        tree.appendChild(fi);
      });
      // Unread inboxes (dedup with saved favorites)
      unreadInboxes.forEach(({konto, displayName, inbox})=>{
        if(_pfFavorites.some(f=>f.konto===konto.email && f.folder===inbox.name)) return;
        const fi = document.createElement('div');
        fi.className = 'pf-fav-item';
        fi.dataset.konto = konto.email;
        fi.dataset.folder = inbox.name;
        fi.innerHTML = pfFolderIconWrap('inbox')
          +'<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">Ungelesen '+displayName+'</span>'
          +'<span class="pf-fav-badge">'+inbox.unread+'</span>';
        fi.onclick = ()=>pfSelectFolder(konto.email, inbox.name, 'Ungelesen '+displayName, fi);
        tree.appendChild(fi);
      });
      const sep = document.createElement('div'); sep.className='pf-fav-sep'; tree.appendChild(sep);
    }

    // ── Konten mit Ordner-Baum + Stern-Buttons ───────────────────────────────
    (data.konten||[]).forEach(konto=>{
      const safe = konto.email.replace(/[@.]/g,'_');
      const displayName = konto.display_name || konto.label || konto.email.split('@')[0].toUpperCase();
      const isCollapsed = !!_pfCollapsed[konto.email];

      const lbl = document.createElement('div');
      lbl.className = 'pf-folder-konto'+(isCollapsed?' collapsed':'');
      lbl.id = 'pf-konto-hdr-'+safe;
      lbl.innerHTML = '<span class="pf-konto-arrow">&#x25BC;</span>'
        +'<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+displayName+'</span>'
        +'<span id="pf-ampel-'+safe+'" style="margin-left:6px;font-size:10px;color:#f0a000;flex-shrink:0" title="Pr\u00fcfe Verbindung\u2026">&#x25CF;</span>';
      lbl.onclick = ()=>pfToggleKonto(konto.email, safe);
      tree.appendChild(lbl);

      if(fromSel){
        const opt=document.createElement('option');
        opt.value=konto.email; opt.textContent=konto.email;
        fromSel.appendChild(opt);
      }

      const folderWrap = document.createElement('div');
      folderWrap.className = 'pf-konto-folders'+(isCollapsed?' collapsed':'');
      folderWrap.id = 'pf-konto-folders-'+safe;
      tree.appendChild(folderWrap);

      (konto.ordner||[]).forEach(ord=>{
        const isStarred = _pfFavorites.some(f=>f.konto===konto.email && f.folder===ord.name);
        const item = document.createElement('div');
        item.className = 'pf-folder-item';
        item.id = 'pf-fi-'+safe+'_'+ord.name.replace(/[^a-z0-9]/gi,'_');
        const _fn = (ord.name||'').toLowerCase();
        const _isDraft = _fn.includes('draft')||_fn.includes('entwurf');
        const _isInbox = _fn.includes('inbox')||_fn.includes('posteingang');
        const _isSnooze= _fn.includes('erinnern');
        let _badge = '';
        if(_isInbox && ord.unread>0)
          _badge = '<span class="pf-folder-badge-inbox">'+ord.unread+'</span>';
        else if(_isDraft && (ord.count||0)>0)
          _badge = '<span class="pf-folder-badge-draft">'+(ord.count)+'</span>';
        else if(_isSnooze && (ord.count||0)>0)
          _badge = '<span class="pf-folder-badge-snooze">'+(ord.count)+'</span>';
        else if(ord.unread>0)
          _badge = '<span class="pf-folder-badge">'+ord.unread+'</span>';
        item.innerHTML = pfFolderIconWrap(ord.name)
          +'<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+(ord.label||ord.name)+'</span>'
          +_badge;
        const starBtn = document.createElement('button');
        starBtn.className = 'pf-star-btn'+(isStarred?' starred':'');
        starBtn.title = isStarred ? 'Aus Favoriten entfernen' : 'Zu Favoriten hinzuf\u00fcgen';
        starBtn.innerHTML = isStarred ? '&#x2605;' : '&#x2606;';
        starBtn.onclick = e => pfToggleFavorite(konto.email, ord.name, ord.label||ord.name, starBtn, e);
        item.appendChild(starBtn);
        item.onclick = ()=>pfSelectFolder(konto.email, ord.name, ord.label||ord.name);
        folderWrap.appendChild(item);
      });
    });

    _pfUpdateSidebarBadge();
    if(onReady) onReady();
  });
}

function pfToggleKonto(email, safe) {
  _pfCollapsed[email] = !_pfCollapsed[email];
  try { localStorage.setItem('pf_collapsed', JSON.stringify(_pfCollapsed)); } catch(e){}
  const hdr=document.getElementById('pf-konto-hdr-'+safe);
  const fw=document.getElementById('pf-konto-folders-'+safe);
  if(hdr) hdr.classList.toggle('collapsed', !!_pfCollapsed[email]);
  if(fw) fw.classList.toggle('collapsed', !!_pfCollapsed[email]);
}

// ── Select Folder ────────────────────────────────────────
window.pfSelectFolder = function(email, folder, label, favEl) {
  _pfCurrentKonto=email; _pfCurrentFolder=folder; _pfOffset=0; _pfSearch='';
  _pfCurrentFolderLabel = label;
  document.getElementById('pf-mid-title').textContent=label;
  document.getElementById('pf-search').value='';
  document.querySelectorAll('.pf-folder-item,.pf-fav-item,.pf-combined-btn,.pf-combined-sub-item').forEach(el=>el.classList.remove('active'));
  const id='pf-fi-'+email.replace(/[@.]/g,'_')+'_'+folder.replace(/[^a-z0-9]/gi,'_');
  const el=document.getElementById(id);
  if(el) el.classList.add('active');
  // Wenn direkt über Favoriten-Klick → Favorit highlighten
  if(favEl) { favEl.classList.add('active'); }
  else {
    // Favorit-Item per data-Attribut finden
    const fi = document.querySelector('.pf-fav-item[data-konto="'+email+'"][data-folder="'+folder+'"]');
    if(fi) fi.classList.add('active');
  }
  pfLoadList(true);
};

// ── Load Mail List ───────────────────────────────────────
function pfLoadList(reset) {
  if(reset) { _pfOffset=0; document.getElementById('pf-list').innerHTML=''; _pfLastGroup=null; }
  if(!_pfCurrentKonto) return;
  let url;
  if(_pfCurrentKonto==='_combined_') {
    url='/api/mail/combined?offset='+_pfOffset+'&limit=50';
    if(_pfCurrentFolderType && _pfCurrentFolderType!=='all') url+='&folder_type='+encodeURIComponent(_pfCurrentFolderType);
  } else {
    url='/api/mail/list?konto='+encodeURIComponent(_pfCurrentKonto)+'&folder='+encodeURIComponent(_pfCurrentFolder)+'&offset='+_pfOffset+'&limit=50';
  }
  if(_pfSearch) url+='&q='+encodeURIComponent(_pfSearch);
  fetch(url).then(r=>r.json()).then(data=>{
    _pfTotal=data.total||0;
    document.getElementById('pf-mid-meta').textContent=_pfTotal+' Mails';
    const list=document.getElementById('pf-list');
    if(reset) list.innerHTML='';
    if(!data.mails||data.mails.length===0) {
      if(reset) document.getElementById('pf-list-empty').style.display='';
      return;
    }
    document.getElementById('pf-list-empty').style.display='none';
    data.mails.forEach(m=>pfRenderMailItem(m, list));
    _pfOffset+=data.mails.length;
    document.getElementById('pf-load-more').style.display=_pfOffset<_pfTotal?'':'none';
  });
}

// ── Avatar / Datum Hilfsfunktionen ────────────────────────
const _AVATAR_COLORS=['#3b82f6','#10b981','#f59e0b','#ef4444','#ec4899','#06b6d4','#14b8a6','#f97316','#0ea5e9','#84cc16'];
function pfGetInitials(name) {
  const s=(name||'').trim();
  if(!s) return '?';
  if(s.includes('@')) return s[0].toUpperCase();
  const parts=s.split(/\\s+/);
  if(parts.length>=2) return (parts[0][0]+(parts[1][0]||'')).toUpperCase();
  return s.slice(0,2).toUpperCase();
}
function pfAvatarColor(name) {
  let h=0; for(let i=0;i<name.length;i++) h=((h*31+name.charCodeAt(i))>>>0);
  return _AVATAR_COLORS[h%_AVATAR_COLORS.length];
}
function pfDateGroup(datum) {
  if(!datum) return 'Älter';
  const d=new Date(datum.replace(' ','T'));
  if(isNaN(d.getTime())) return 'Älter';
  const now=new Date();
  const today=new Date(now.getFullYear(),now.getMonth(),now.getDate());
  const mdate=new Date(d.getFullYear(),d.getMonth(),d.getDate());
  const diff=Math.floor((today-mdate)/86400000);
  if(diff<=0) return 'Heute';
  if(diff===1) return 'Gestern';
  if(diff<=7) return 'Diese Woche';
  return 'Älter';
}
function pfFormatDatum(datum) {
  if(!datum) return '';
  const d=new Date(datum.replace(' ','T'));
  if(isNaN(d.getTime())) return datum.slice(0,10);
  const now=new Date();
  const diffDays=Math.floor((now-d)/86400000);
  if(diffDays<1) return d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
  const days=['So','Mo','Di','Mi','Do','Fr','Sa'];
  if(diffDays<7) return days[d.getDay()]+', '+d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
  return d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit'});
}

function pfRenderMailItem(m, container) {
  // Datums-Gruppe Header einfügen wenn nötig
  const group = pfDateGroup(m.datum||'');
  if(group !== _pfLastGroup) {
    _pfLastGroup = group;
    const gh = document.createElement('div');
    gh.className = 'pf-date-group';
    gh.textContent = group;
    container.appendChild(gh);
  }

  const el = document.createElement('div');
  el.className = 'pf-mail-item'+(m.unread?' unread':'');
  el.dataset.msgid = m.message_id;
  el.dataset.threadid = m.thread_id||'';
  el.dataset.flagged = m.flagged?'1':'0';
  el.dataset.pinned = m.pinned?'1':'0';

  const absender = m.absender_short||m.absender||'?';
  const initials = pfGetInitials(absender);
  const color = pfAvatarColor(absender);
  const datum = pfFormatDatum(m.datum||'');
  const preview = (m.text_plain||'').replace(/\\s+/g,' ').slice(0,60);

  // Checkbox wrap
  const cbxWrap = document.createElement('div');
  cbxWrap.className = 'pf-item-cbx-wrap';
  const cbx = document.createElement('input');
  cbx.type='checkbox'; cbx.className='pf-item-cbx';
  cbx.checked = _pfSelected.has(m.message_id);
  cbx.addEventListener('click', e=>{ e.stopPropagation(); pfToggleSelect(m.message_id, cbx.checked); });
  cbxWrap.appendChild(cbx);
  el.appendChild(cbxWrap);

  // Avatar (same level as body, between cbxWrap and body)
  const avatarEl = document.createElement('div');
  avatarEl.className = 'pf-item-avatar';
  avatarEl.style.background = color;
  avatarEl.textContent = initials;
  el.appendChild(avatarEl);

  // Body
  const body = document.createElement('div');
  body.className = 'pf-item-body';
  body.innerHTML =
    '<div class="pf-item-row1">'
      +'<span class="pf-item-absender">'+esc(absender)+'</span>'
      +(m.flagged?'<span class="pf-item-flag-badge" title="Gekennzeichnet">&#x2691;</span>':'<span class="pf-item-flag-badge" style="display:none" title="Gekennzeichnet">&#x2691;</span>')
      +(m.pinned?'<span class="pf-item-pin-badge" title="Angeheftet">&#x1F4CD;</span>':'<span class="pf-item-pin-badge" style="display:none" title="Angeheftet">&#x1F4CD;</span>')
      +(m.kira_verwendet?'<span class="pf-item-kira-badge" title="Von Kira verwendet">Kira</span>':'')
      +(m.snooze_until?'<span class="pf-item-snooze-badge" title="Erneut erinnern: '+esc(m.snooze_until)+'">&#x23F0;</span>':'')
      +'<span class="pf-item-datum">'+esc(datum)+'</span>'
    +'</div>'
    +'<div class="pf-item-betreff">'+esc(m.betreff||'(kein Betreff)')+'</div>'
    +'<div class="pf-item-row3">'
      +'<span class="pf-item-preview">'+esc(preview)+'</span>'
      +(_pfCurrentFolderLabel?'<span class="pf-item-folder-badge">'+esc(_pfCurrentFolderLabel)+'</span>':'')
      +(m.hat_anhaenge?'<span class="pf-item-att" title="Anhang"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg></span>':'')
    +'</div>';
  el.appendChild(body);

  // Hover action buttons
  const acts = document.createElement('div');
  acts.className='pf-item-actions';

  const btnRead=document.createElement('button');
  btnRead.className='pf-item-act-btn'; btnRead.title='Gelesen/Ungelesen';
  btnRead.innerHTML=_SVG_ENV;
  btnRead.addEventListener('click',e=>{e.stopPropagation();pfToggleRead(m.message_id,el);});
  acts.appendChild(btnRead);

  const btnFlag=document.createElement('button');
  btnFlag.className='pf-item-act-btn'+(m.flagged?' active':''); btnFlag.title='Kennzeichnen';
  btnFlag.innerHTML=_SVG_FLAG;
  btnFlag.addEventListener('click',e=>{
    e.stopPropagation();
    pfToggleFlag(m.message_id,el);
    // optimistic UI — toggle will be confirmed/reverted by pfToggleFlag
    setTimeout(()=>btnFlag.classList.toggle('active',el.dataset.flagged==='1'),50);
  });
  acts.appendChild(btnFlag);

  const btnPin=document.createElement('button');
  btnPin.className='pf-item-act-btn'+(m.pinned?' pin-active':''); btnPin.title='Anheften';
  btnPin.innerHTML=_SVG_PIN;
  btnPin.addEventListener('click',e=>{
    e.stopPropagation();
    pfTogglePin(m.message_id,el);
    setTimeout(()=>btnPin.classList.toggle('pin-active',el.dataset.pinned==='1'),50);
  });
  acts.appendChild(btnPin);

  const btnTrash=document.createElement('button');
  btnTrash.className='pf-item-act-btn trash-btn'; btnTrash.title='L\u00f6schen';
  btnTrash.innerHTML=_SVG_TRASH;
  btnTrash.addEventListener('click',e=>{e.stopPropagation();pfDeleteMail(m.message_id,el);});
  acts.appendChild(btnTrash);

  el.appendChild(acts);

  el.onclick = e=>{
    if(e.target.closest('.pf-item-cbx-wrap,.pf-item-actions')) return;
    pfOpenMail(m, el);
  };
  container.appendChild(el);
}

function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

// ── RFC-2047 Header Decode ────────────────────────────────
function pfDecodeHeader(str) {
  if (!str) return str;
  return str.replace(/=\\?([^?]+)\\?([BbQq])\\?([^?]*)\\?=/g, function(_, charset, enc, data) {
    try {
      const cs = charset.toLowerCase().replace('windows-','cp');
      if (enc.toUpperCase() === 'B') {
        const bin = atob(data.replace(/-/g,'+').replace(/_/g,'/'));
        return new TextDecoder(cs).decode(new Uint8Array([...bin].map(c=>c.charCodeAt(0))));
      } else {
        const q = data.replace(/_/g,' ').replace(/=([0-9A-Fa-f]{2})/g,(_,h)=>String.fromCharCode(parseInt(h,16)));
        return new TextDecoder(cs).decode(new Uint8Array([...q].map(c=>c.charCodeAt(0))));
      }
    } catch(e) { return data; }
  }).trim();
}

// ── Ribbon ────────────────────────────────────────────────
let _pfRibbonOffset = 0;
let _pfRibbonIsCompact = false;

function pfRibbonInit() {
  _pfRibbonIsCompact = localStorage.getItem('pf_ribbon_compact') === '1';
  const ribbon = document.getElementById('pf-ribbon');
  if (!ribbon) return;
  if (_pfRibbonIsCompact) {
    ribbon.classList.add('compact');
    const tog = document.getElementById('pf-rbn-toggle');
    if (tog) tog.innerHTML = '&#x25B4;';
  }
  pfRibbonCheckEdges();
  pfRibbonUpdateState(false);
  const vp = document.getElementById('pf-rbn-viewport');
  if (vp && typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(() => pfRibbonCheckEdges()).observe(vp);
  }
}

window.pfRibbonCompact = function() {
  _pfRibbonIsCompact = !_pfRibbonIsCompact;
  const ribbon = document.getElementById('pf-ribbon');
  if (ribbon) ribbon.classList.toggle('compact', _pfRibbonIsCompact);
  const tog = document.getElementById('pf-rbn-toggle');
  if (tog) tog.innerHTML = _pfRibbonIsCompact ? '&#x25B4;' : '&#x25BE;';
  localStorage.setItem('pf_ribbon_compact', _pfRibbonIsCompact ? '1' : '0');
  setTimeout(pfRibbonCheckEdges, 60);
};

window.pfRibbonScroll = function(dir) {
  const inner = document.getElementById('pf-rbn-inner');
  const vp = document.getElementById('pf-rbn-viewport');
  if (!inner || !vp) return;
  const step = vp.offsetWidth * 0.65;
  _pfRibbonOffset = Math.max(0, Math.min(inner.scrollWidth - vp.offsetWidth + 2, _pfRibbonOffset + dir * step));
  inner.style.transform = 'translateX(-' + _pfRibbonOffset + 'px)';
  pfRibbonCheckEdges();
};

function pfRibbonCheckEdges() {
  const inner = document.getElementById('pf-rbn-inner');
  const vp = document.getElementById('pf-rbn-viewport');
  const prev = document.getElementById('pf-rbn-prev');
  const next = document.getElementById('pf-rbn-next');
  if (!inner || !vp || !prev || !next) return;
  const overflow = inner.scrollWidth > vp.offsetWidth + 4;
  prev.style.display = (overflow && _pfRibbonOffset > 2) ? '' : 'none';
  next.style.display = (overflow && _pfRibbonOffset < inner.scrollWidth - vp.offsetWidth - 2) ? '' : 'none';
}

window.pfRibbonUpdateState = function(mailSelected) {
  document.querySelectorAll('.pf-rbn-mail-dep').forEach(btn => {
    btn.classList.toggle('disabled', !mailSelected);
  });
};

window.pfToastVorbereitung = function(name) {
  showToast((name || 'Diese Funktion') + ' — in Vorbereitung', 'info');
};

// Ribbon delegates to existing action handlers
window.pfRibbonToggleRead = function() {
  if (!_pfCurrentMail) return;
  const el = document.querySelector('[data-msgid="'+_pfCurrentMail.message_id+'"]');
  if (el) pfToggleRead(_pfCurrentMail.message_id, el);
};
window.pfRibbonToggleFlag = function() {
  if (!_pfCurrentMail) return;
  const el = document.querySelector('[data-msgid="'+_pfCurrentMail.message_id+'"]');
  if (el) pfToggleFlag(_pfCurrentMail.message_id, el);
};
window.pfRibbonTogglePin = function() {
  if (!_pfCurrentMail) return;
  const el = document.querySelector('[data-msgid="'+_pfCurrentMail.message_id+'"]');
  if (el) pfTogglePin(_pfCurrentMail.message_id, el);
};
window.pfRibbonDelete = function() {
  if (!_pfCurrentMail) return;
  const el = document.querySelector('[data-msgid="'+_pfCurrentMail.message_id+'"]');
  if (el) pfDeleteMail(_pfCurrentMail.message_id, el);
};

// ── Viewer state chips ────────────────────────────────────
function pfUpdateViewerState(type) {
  const ids = ['pf-chip-html','pf-chip-text','pf-chip-blocked'];
  ids.forEach(id => { const el=document.getElementById(id); if(el) el.style.display='none'; });
  const toolbar = document.getElementById('pf-viewer-toolbar');
  if (!type) { if(toolbar) toolbar.style.display='none'; return; }
  const map = {html:'pf-chip-html', text:'pf-chip-text', blocked:'pf-chip-blocked'};
  if (map[type]) { const el=document.getElementById(map[type]); if(el) el.style.display=''; }
  if (toolbar) toolbar.style.display='';
}

window.pfTrustSender = function() {
  const banner = document.getElementById('pf-trust-banner');
  if (banner) banner.style.display = 'none';
  showToast('Absender als vertrauenswürdig markiert', 'ok');
};

// ── Hints section ─────────────────────────────────────────
function pfRenderHints(m, d) {
  const sec = document.getElementById('pf-hint-section');
  if (!sec) return;
  const hints = [];
  if (m.replied) hints.push({cls:'reply', text:'Geantwortet'+(m.replied_at?' · '+m.replied_at:'')});
  if (m.forwarded) hints.push({cls:'forwarded', text:'Weitergeleitet'+(m.forwarded_at?' · '+m.forwarded_at:'')});
  if (m.snoozed) hints.push({cls:'followup', text:'Wiedervorlage: '+(m.snooze_until||'geplant')});
  if (m.pinned) hints.push({cls:'reply', text:'Angeheftet'});
  if (d && d.kira_context) hints.push({cls:'kira', text:'Mit Kira besprochen'});
  if (!hints.length) { sec.style.display='none'; sec.innerHTML=''; return; }
  sec.style.display='';
  sec.innerHTML = hints.map(h=>'<span class="pf-hint pf-hint-'+h.cls+'">'+esc(h.text)+'</span>').join('');
}

// ── Attachments collapsible bar ───────────────────────────
let _pfAttBarOpen = false;
let _pfGalleryImages = [];

function pfRenderAttachments(anhaenge) {
  const sec = document.getElementById('pf-attachment-section');
  if (!sec) return;
  if (!anhaenge || !anhaenge.length) { sec.style.display='none'; return; }
  sec.style.display = '';
  _pfAttBarOpen = false;
  document.getElementById('pf-att-collapsed').style.display = 'flex';
  document.getElementById('pf-att-expanded').style.display = 'none';
  // Summary
  const totalBytes = anhaenge.reduce((s,a)=>s+(a.groesse||0), 0);
  const sizeStr = totalBytes > 1048576 ? (totalBytes/1048576).toFixed(1)+' MB'
    : totalBytes > 1024 ? Math.round(totalBytes/1024)+' KB' : '';
  const summary = anhaenge.length+(anhaenge.length===1?' Anhang':' Anhänge')+(sizeStr?' · '+sizeStr:'');
  document.getElementById('pf-att-summary').textContent = summary;
  document.getElementById('pf-att-count').textContent = summary;
  // Build expanded list
  const images = anhaenge.filter(a=>/^image\\//i.test(a.typ||''));
  _pfGalleryImages = images.map(a=>({name:a.name||'Bild', src:'/api/file?path='+encodeURIComponent(a.pfad)}));
  const list = document.getElementById('pf-attachment-list');
  list.innerHTML = anhaenge.map((a, idx) => {
    const isImg = /^image\\//i.test(a.typ||'');
    const isPdf = /pdf/i.test(a.typ+a.name);
    const isDoc = /word|excel|powerpoint|docx|xlsx|pptx/i.test(a.typ+(a.name||''));
    const isZip = /zip|rar|7z/i.test(a.typ+(a.name||''));
    const pcls = isImg?'img':isPdf?'pdf':isDoc?'doc':isZip?'zip':'';
    const pContent = isImg
      ? '<img src="/api/file?path='+encodeURIComponent(a.pfad)+'" style="width:100%;height:100%;object-fit:cover;border-radius:4px">'
      : '<span>'+esc((a.name||'').split('.').pop().toUpperCase().slice(0,4)||'?')+'</span>';
    const imgIdx = isImg ? images.findIndex(im=>im.name===a.name) : -1;
    return '<div class="pf-attachment-row">'
      +'<div class="pf-att-preview-box '+pcls+'">'+pContent+'</div>'
      +'<div class="pf-att-file-info">'
      +'<div class="pf-att-file-name">'+esc(a.name||'Anhang')+'</div>'
      +'<div class="pf-att-file-sub">'+esc((a.groesse?(a.groesse>1048576?(a.groesse/1048576).toFixed(1)+' MB':Math.round(a.groesse/1024)+' KB')+' · ':'')+(a.typ||''))+'</div>'
      +'</div>'
      +'<div class="pf-att-row-actions">'
      +(isImg&&imgIdx>=0?'<button class="pf-att-act-btn" onclick="pfGalleryJump('+imgIdx+')" title="Galerie öffnen">&#x1F4F7;</button>':'')
      +'<button class="pf-att-act-btn" onclick="pfOpenAtt(encodeURIComponent(this.dataset.path))" data-path="'+esc(a.pfad)+'" title="Öffnen">&#x1F441;</button>'
      +'</div>'
      +'</div>';
  }).join('');
}

window.pfToggleAttBar = function() {
  _pfAttBarOpen = !_pfAttBarOpen;
  document.getElementById('pf-att-collapsed').style.display = _pfAttBarOpen ? 'none' : 'flex';
  document.getElementById('pf-att-expanded').style.display = _pfAttBarOpen ? '' : 'none';
};

window.pfSaveAllAtts = function() { pfToastVorbereitung('Alle Anhänge speichern'); };

// ── Gallery modal ─────────────────────────────────────────
let _pfGalleryIdx = 0;

window.pfGalleryJump = function(idx) {
  _pfGalleryIdx = idx;
  document.getElementById('pf-gallery-modal').style.display = 'flex';
  pfGalleryRender();
};

window.pfGalleryNav = function(dir) {
  if (!_pfGalleryImages.length) return;
  _pfGalleryIdx = (_pfGalleryIdx + dir + _pfGalleryImages.length) % _pfGalleryImages.length;
  pfGalleryRender();
};

window.pfCloseGallery = function() {
  document.getElementById('pf-gallery-modal').style.display = 'none';
};

function pfGalleryRender() {
  const im = _pfGalleryImages[_pfGalleryIdx];
  if (!im) return;
  document.getElementById('pf-gallery-img').src = im.src;
  document.getElementById('pf-gallery-title').textContent = im.name;
  document.getElementById('pf-gallery-counter').textContent = (_pfGalleryIdx+1)+' / '+_pfGalleryImages.length;
  const thumbs = document.getElementById('pf-gallery-thumbs');
  thumbs.innerHTML = _pfGalleryImages.map((g,i)=>
    '<img class="pf-gallery-thumb'+(i===_pfGalleryIdx?' active':'')+'" src="'+g.src
    +'" onclick="pfGalleryJump('+i+')" title="'+esc(g.name)+'">'
  ).join('');
  document.getElementById('pf-gallery-prev').style.display = _pfGalleryImages.length>1?'':'none';
  document.getElementById('pf-gallery-next').style.display = _pfGalleryImages.length>1?'':'none';
}

document.addEventListener('keydown', function(e) {
  const modal = document.getElementById('pf-gallery-modal');
  if (!modal || modal.style.display==='none') return;
  if (e.key==='ArrowLeft') pfGalleryNav(-1);
  else if (e.key==='ArrowRight') pfGalleryNav(1);
  else if (e.key==='Escape') pfCloseGallery();
});

// ── Open Mail ────────────────────────────────────────────
window.pfOpenMail = function(m, el) {
  if(_pfActiveItem) _pfActiveItem.classList.remove('active');
  _pfActiveItem = el; if(el) el.classList.add('active');
  _pfCurrentMail = m;
  _pfCurrentMsgId = m.message_id || null;
  pfUpdateBulkBar();
  pfRibbonUpdateState(true);
  document.getElementById('pf-preview-empty').style.display = 'none';
  document.getElementById('pf-preview').style.display = 'grid';
  document.getElementById('pf-compose').style.display = 'none';

  // ── Decode + render header ─────────────────────────────
  const betreff = pfDecodeHeader(m.betreff) || '(kein Betreff)';
  const absenderRaw = pfDecodeHeader(m.absender) || '';
  const emailMatch = absenderRaw.match(/<([^>]+@[^>]+)>/);
  const emailAddr = emailMatch ? emailMatch[1] : absenderRaw;
  const displayName = absenderRaw.replace(/<[^>]+>/, '').trim() || emailAddr.split('@')[0];
  const initials = displayName.split(/\\s+/).map(w=>w[0]||'').join('').slice(0,2).toUpperCase() || '?';

  const subjectEl = document.getElementById('pf-prev-betreff');
  if (subjectEl) subjectEl.textContent = betreff;
  const datumEl = document.getElementById('pf-prev-datum');
  if (datumEl) datumEl.textContent = m.datum || '';
  const avatarEl = document.getElementById('pf-avatar');
  if (avatarEl) { avatarEl.textContent = initials; avatarEl.style.background = pfAvatarColor(displayName); }
  const fromEl = document.getElementById('pf-prev-absender');
  if (fromEl) fromEl.textContent = absenderRaw || emailAddr;
  const toEl = document.getElementById('pf-prev-to');
  if (toEl) toEl.textContent = m.empfaenger ? 'An: '+pfDecodeHeader(m.empfaenger) : '';

  // Toolbar icon states
  const tbFlag = document.getElementById('pf-tb-flag');
  const tbPin = document.getElementById('pf-tb-pin');
  if (tbFlag) tbFlag.classList.toggle('active', !!(m.flagged));
  if (tbPin) tbPin.classList.toggle('pin-active', !!(m.pinned));

  // ── Reset sections ─────────────────────────────────────
  pfRenderHints(m, null);
  pfRenderAttachments([]);
  pfUpdateViewerState(null);
  document.getElementById('pf-thread-wrap').style.display = 'none';
  const body = document.getElementById('pf-prev-body');
  body.className = 'pf-prev-body';
  body.innerHTML = '';
  body.textContent = 'Lade...';

  // ── Load mail content ──────────────────────────────────
  fetch('/api/mail/read?message_id='+encodeURIComponent(m.message_id)).then(r=>r.json()).then(d=>{
    const body = document.getElementById('pf-prev-body');
    body.innerHTML = '';
    const rawText = d.text || '';
    const hasHtml = !!d.html;
    const textLooksLikeHtml = !hasHtml && /^\\s*(<html|<!doctype)/i.test(rawText);
    if (hasHtml || textLooksLikeHtml) {
      pfUpdateViewerState('html');
      body.classList.add('iframe-mode');
      body.style.cssText = '';
      const iframe = document.createElement('iframe');
      iframe.setAttribute('sandbox', 'allow-same-origin allow-popups-to-escape-sandbox');
      iframe.style.cssText = 'flex:1;width:100%;height:100%;border:none;background:#fff;display:block;min-height:0';
      iframe.srcdoc = hasHtml ? d.html : rawText;
      body.appendChild(iframe);
    } else {
      pfUpdateViewerState('text');
      body.classList.remove('iframe-mode');
      body.style.padding = '20px';
      body.style.overflow = 'auto';
      body.style.whiteSpace = 'pre-wrap';
      const tmp = document.createElement('div');
      tmp.innerHTML = rawText;
      body.textContent = tmp.textContent || '(kein Inhalt)';
    }
    if (d.anhaenge && d.anhaenge.length > 0) pfRenderAttachments(d.anhaenge);
    pfRenderHints(m, d);
  }).catch(() => {
    const body = document.getElementById('pf-prev-body');
    body.textContent = 'Fehler beim Laden.';
    pfUpdateViewerState(null);
  });

  if (m.unread) pfDoMarkRead(m);

  if (m.thread_id && m.thread_id !== m.message_id) {
    fetch('/api/mail/thread?thread_id='+encodeURIComponent(m.thread_id)).then(r=>r.json()).then(d=>{
      if (d.mails && d.mails.length > 1) pfRenderThread(d.mails, m.message_id);
    });
  }
};

function pfDoMarkRead(m) {
  if(_pfMarkReadTimer) clearTimeout(_pfMarkReadTimer);
  if(_pfMarkReadMode==='manuell') return;
  let delay = 0;
  if(_pfMarkReadMode !== 'sofort') {
    const minM = _pfMarkReadMode.match(/^(\\d+)min$/);
    const secM = _pfMarkReadMode.match(/^(\\d+)s$/);
    if(minM) delay = parseInt(minM[1]) * 60000;
    else if(secM) delay = parseInt(secM[1]) * 1000;
  }
  const doMark=()=>{
    fetch('/api/mail/gelesen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[m.message_id],gelesen:true})});
    const itemEl=document.querySelector('[data-msgid="'+m.message_id+'"]');
    if(itemEl) itemEl.classList.remove('unread');
    _pfTotalUnread=Math.max(0,_pfTotalUnread-1);
    _pfUpdateSidebarBadge();
  };
  if(delay===0) doMark();
  else _pfMarkReadTimer=setTimeout(doMark, delay);
}

function pfRenderThread(mails, currentMsgId) {
  const wrap=document.getElementById('pf-thread-wrap');
  const list=document.getElementById('pf-thread-list');
  const cnt=document.getElementById('pf-thread-cnt');
  cnt.textContent=mails.length+' Nachrichten';
  wrap.style.display='block';
  list.innerHTML='';
  list.style.display=_pfThreadOpen?'block':'none';
  mails.filter(m=>m.message_id!==currentMsgId).forEach(m=>{
    const el=document.createElement('div');
    el.className='pf-thread-msg';
    el.innerHTML='<div class="pf-thread-msg-hdr"><span class="pf-thread-msg-sender">'+esc(m.absender_short||m.absender||'')+'</span><span class="pf-thread-msg-date">'+(m.datum||'')+'</span></div>'
    +'<div class="pf-thread-msg-body">'+esc((m.text_plain||'').slice(0,200))+'</div>';
    el.onclick=()=>pfOpenMail(m,null);
    list.appendChild(el);
  });
}

window.pfToggleThread=function(){
  _pfThreadOpen=!_pfThreadOpen;
  document.getElementById('pf-thread-list').style.display=_pfThreadOpen?'block':'none';
  document.getElementById('pf-thread-toggle').textContent=_pfThreadOpen?'&#x25B2;':'&#x25BC;';
};

// ── Compose ──────────────────────────────────────────────
window.pfOpenCompose=function(replyTo){
  document.getElementById('pf-preview-empty').style.display='none';
  document.getElementById('pf-preview').style.display='none';
  document.getElementById('pf-compose').style.display='flex';
  document.getElementById('pf-compose').style.flexDirection='column';
  document.getElementById('pf-comp-title').textContent=replyTo?'Antworten':'Neue Mail';
  if(!replyTo){
    document.getElementById('pf-comp-to').value='';
    document.getElementById('pf-comp-subj').value='';
    document.getElementById('pf-comp-body').value='';
    document.getElementById('pf-comp-cc').value='';
  }
};
window.pfCloseCompose=function(){
  document.getElementById('pf-compose').style.display='none';
  document.getElementById('pf-preview-empty').style.display='flex';
};

window.pfReply=function(){
  const betreff=document.getElementById('pf-prev-betreff').textContent;
  const absender=document.getElementById('pf-prev-absender').textContent.replace('Von: ','');
  const emailMatch=absender.match(/<([^>]+@[^>]+)>/);
  const replyAddr=emailMatch?emailMatch[1]:absender.trim();
  pfOpenCompose(true);
  document.getElementById('pf-comp-to').value=replyAddr;
  document.getElementById('pf-comp-subj').value=(betreff.startsWith('Re:')?betreff:'Re: '+betreff);
};
window.pfForward=function(){
  const betreff=document.getElementById('pf-prev-betreff').textContent;
  const body=document.getElementById('pf-prev-body').textContent;
  pfOpenCompose(true);
  document.getElementById('pf-comp-subj').value=(betreff.startsWith('Fwd:')?betreff:'Fwd: '+betreff);
  document.getElementById('pf-comp-body').value='\\n\\n--- Weitergeleitet ---\\n'+body.slice(0,2000);
};

window.pfSend=function(){
  const from=document.getElementById('pf-comp-from').value;
  const to=document.getElementById('pf-comp-to').value.trim();
  const cc=document.getElementById('pf-comp-cc').value.trim();
  const subj=document.getElementById('pf-comp-subj').value.trim();
  const body=document.getElementById('pf-comp-body').value;
  if(!to||!subj){showToast('Empfänger und Betreff erforderlich','warnung');return;}
  const btn=document.getElementById('pf-send-btn');
  btn.disabled=true;btn.textContent='Wird gesendet...';
  fetch('/api/mail/send',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({from_email:from,to,cc,subject:subj,body_plain:body,bcc:'info@raumkult.eu'})
  }).then(r=>r.json()).then(d=>{
    btn.disabled=false;btn.textContent='&#x27A4; Senden';
    if(d.ok){showToast('Mail gesendet ✓','ok');pfCloseCompose();}
    else showToast('Fehler: '+(d.error||'?'),'fehler');
  }).catch(()=>{btn.disabled=false;btn.textContent='&#x27A4; Senden';showToast('Netzwerkfehler','fehler');});
};
window.pfSaveDraft=function(){showToast('Entwurf gespeichert (noch nicht implementiert)','info');};
window.pfKiraDraft=function(){
  const to=document.getElementById('pf-comp-to').value;
  const subj=document.getElementById('pf-comp-subj').value;
  if(!subj){showToast('Bitte zuerst Betreff eingeben','warnung');return;}
  document.getElementById('pf-comp-body').value='Kira formuliert...';
  fetch('/api/kira/chat',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({message:'Bitte formuliere eine professionelle Mail an '+to+' zum Thema: '+subj+'. Im Stil von rauMKult Sichtbeton.'})
  }).then(r=>r.json()).then(d=>{
    document.getElementById('pf-comp-body').value=d.response||d.text||'(keine Antwort)';
  }).catch(()=>document.getElementById('pf-comp-body').value='Fehler');
};
window.pfKiraContext=function(){ pfKiraMailContext(); }; // Compat

window.pfKiraMailContext = async function() {
  if(!_pfCurrentMail) return;
  const btn = document.getElementById('pf-tb-kira');
  const origHtml = btn ? btn.innerHTML : '';
  if(btn) { btn.classList.add('loading'); btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:15px;height:15px;animation:spin 1s linear infinite"><path d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0"/></svg> Lade...'; }

  let ctx = null;
  try {
    const r = await fetch('/api/mail/kira-kontext?message_id='+encodeURIComponent(_pfCurrentMail.message_id));
    ctx = await r.json();
  } catch(e) { ctx = null; }

  if(btn) { btn.classList.remove('loading'); btn.innerHTML = origHtml; }

  // Kira Workspace öffnen (Overlay — bleibt im Postfach!)
  openKiraWorkspace('chat');
  const betreff = _pfCurrentMail.betreff || ctx?.betreff || '(kein Betreff)';
  const absender = _pfCurrentMail.absender_short || _pfCurrentMail.absender || ctx?.absender || '';
  setKiraContextBar('\U0001F4E7 Mail', betreff, absender ? [absender] : []);
  kiraSetQuickActions('mail');

  // Lade-Nachricht im Chat anzeigen
  const area = document.getElementById('kiraChatArea');
  const loadEl = document.createElement('div');
  loadEl.id = 'kira-mail-loading';
  loadEl.style.cssText = 'padding:12px 16px;color:var(--muted);font-size:13px;display:flex;align-items:center;gap:8px';
  loadEl.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;flex-shrink:0;animation:spin 1s linear infinite"><path d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0"/></svg> Stelle gerade Informationen zusammen\u2026';
  if(area) area.appendChild(loadEl);

  // Kontext-Nachricht aufbauen
  const mailText = (ctx?.text || '').trim();
  const lines = [
    '\U0001F4E7 **Mail zur Analyse:**',
    'Von: ' + (ctx?.absender || absender),
    ctx?.an ? 'An: ' + ctx.an : '',
    'Datum: ' + (ctx?.datum || _pfCurrentMail.datum || ''),
    'Betreff: ' + betreff,
    '',
    '**Inhalt:**',
    mailText.slice(0, 5000) || '(kein Textinhalt — evtl. nur HTML)',
  ].filter(Boolean);

  // Sender-Verlauf anhängen wenn vorhanden
  if(ctx?.sender_verlauf?.length) {
    lines.push('', '\U0001F4CC **Bisherige Mails von diesem Absender:**');
    ctx.sender_verlauf.forEach(v => {
      lines.push('  \u2022 ' + (v.datum||'') + ' \u2014 ' + (v.betreff||'') + (v.snippet ? ': '+v.snippet.slice(0,80) : ''));
    });
  }

  // Offene Tasks anhängen wenn vorhanden
  if(ctx?.offene_tasks?.length) {
    lines.push('', '\U0001F4CB **Offene Aufgaben zu diesem Absender:**');
    ctx.offene_tasks.forEach(t => {
      lines.push('  \u2022 ['+t.kategorie+'] ' + t.titel + (t.datum ? ' ('+t.datum+')' : ''));
    });
  }

  lines.push('', '---');
  lines.push('Bitte lies diese Mail, fasse kurz zusammen was wichtig ist, und frag mich was du brauchst um zu helfen. Welcher n\u00e4chste Schritt w\u00e4re sinnvoll?');

  const msg = lines.join('\\n');

  // Lade-Indikator entfernen, Nachricht senden
  const doSend = () => {
    if(loadEl.parentNode) loadEl.remove();
    const inp = document.getElementById('kiraInput');
    if(inp) {
      inp.value = msg;
      inp.style.height = 'auto';
      inp.style.height = Math.min(inp.scrollHeight, 120) + 'px';
      sendKiraMsg();
    }
  };

  // Kurze Pause damit Lade-Animation sichtbar ist
  setTimeout(doSend, 400);
};
window.pfOpenAtt=function(p){window.open('/api/file?path='+p,'_blank');};

// Verschieben-Menü
let _pfCurrentMsgId = null;
window.pfOpenVerschiebenMenu = function(btn) {
  // Altes Menü entfernen
  document.querySelectorAll('.pf-verschieben-menu').forEach(m=>m.remove());
  if(!_pfCurrentMsgId || !_pfCurrentKonto) { showToast('Keine Mail ausgewählt','fehler'); return; }
  if(!_pfFolderData) { showToast('Ordnerliste nicht geladen','fehler'); return; }
  const kdata = (_pfFolderData.konten||[]).find(k=>k.email===_pfCurrentKonto);
  const ordner = kdata ? kdata.ordner : [];
  if(!ordner.length) { showToast('Keine Zielordner verfügbar','fehler'); return; }
  const menu = document.createElement('div');
  menu.className = 'pf-verschieben-menu';
  menu.style.cssText = 'position:absolute;z-index:9999;background:var(--bg-raised);border:1px solid var(--border);border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.18);min-width:200px;max-height:300px;overflow-y:auto;padding:4px 0';
  ordner.forEach(o => {
    if(o.name === _pfCurrentFolder) return; // Aktueller Ordner nicht anzeigen
    const item = document.createElement('div');
    item.textContent = o.label || o.name;
    item.style.cssText = 'padding:8px 14px;cursor:pointer;font-size:13px';
    item.onmouseenter = () => item.style.background='var(--bg-hover,rgba(0,0,0,.07))';
    item.onmouseleave = () => item.style.background='';
    item.onclick = () => {
      menu.remove();
      pfVerschiebenNach(o.name);
    };
    menu.appendChild(item);
  });
  const rect = btn.getBoundingClientRect();
  menu.style.top = (rect.bottom+4+window.scrollY)+'px';
  menu.style.left = (rect.left+window.scrollX)+'px';
  document.body.appendChild(menu);
  setTimeout(()=>document.addEventListener('click',function close(){menu.remove();document.removeEventListener('click',close);},{once:true}),50);
};
window.pfVerschiebenNach = function(zielOrdner) {
  if(!_pfCurrentMsgId||!_pfCurrentKonto) return;
  fetch('/api/mail/verschieben',{
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({konto:_pfCurrentKonto, message_id:_pfCurrentMsgId, ziel_ordner:zielOrdner})
  }).then(r=>r.json()).then(d=>{
    if(d.ok) {
      showToast('Mail verschoben nach '+zielOrdner,'ok');
      pfLoadList(true); // Liste neu laden
      document.getElementById('pf-preview').style.display='none';
      document.getElementById('pf-preview-empty').style.display='flex';
    } else {
      showToast('Fehler: '+(d.error||'?'),'fehler');
    }
  }).catch(()=>showToast('Verbindungsfehler','fehler'));
};

// Suche
window.pfSearchDebounce=function(){
  clearTimeout(_pfSearchTimer);
  _pfSearchTimer=setTimeout(()=>{
    _pfSearch=document.getElementById('pf-search').value.trim();
    pfLoadList(true);
  },400);
};
window.pfLoadMore=function(){pfLoadList(false);};

// Auto-Refresh: Ordner-Counts alle 60s aktualisieren, bei neuen Mails Banner zeigen
let _pfAutoRefreshTimer = null;
function pfStartAutoRefresh() {
  if(_pfAutoRefreshTimer) clearInterval(_pfAutoRefreshTimer);
  _pfAutoRefreshTimer = setInterval(()=>{
    if(!document.getElementById('panel-postfach')?.classList.contains('active')) return;
    fetch('/api/mail/folders').then(r=>r.json()).then(data=>{
      let totalUnread=0;
      (data.konten||[]).forEach(k=>{
        (k.ordner||[]).forEach(o=>{
          totalUnread+=o.unread||0;
          // Badge aktualisieren
          const badge=document.querySelector('#pf-fi-'+k.email.replace(/[@.]/g,'_')+'_'+o.name.replace(/[^a-z0-9]/gi,'_')+' .pf-folder-badge');
          if(o.unread>0){
            if(badge) badge.textContent=o.unread;
            else{
              const fi=document.getElementById('pf-fi-'+k.email.replace(/[@.]/g,'_')+'_'+o.name.replace(/[^a-z0-9]/gi,'_'));
              if(fi){const b=document.createElement('span');b.className='pf-folder-badge';b.textContent=o.unread;fi.appendChild(b);}
            }
          } else if(badge) badge.remove();
        });
      });
      // Wenn aktiver Ordner neue Mails hat → Liste neu laden
      if(totalUnread>0 && _pfCurrentKonto && _pfCurrentFolder) pfLoadList(true);
    }).catch(()=>{});
  }, 60000);
}
pfStartAutoRefresh();

// Postfach aufrufen (bereits aktiv beim Laden)
if(document.getElementById('panel-postfach')&&document.getElementById('panel-postfach').classList.contains('active')){
  pfInit();
}
// Bulk-Bar + Item-Aktionen global exponieren (HTML onclick-Attribute brauchen window-Scope)
window.pfBulkDelete = pfBulkDelete;
window.pfBulkMarkRead = pfBulkMarkRead;
window.pfClearSelection = pfClearSelection;
window.pfUpdateBulkBar = pfUpdateBulkBar;
window.pfToggleSelect = pfToggleSelect;
window.pfToggleRead = pfToggleRead;
window.pfToggleFlag = pfToggleFlag;
window.pfTogglePin = pfTogglePin;
window.pfBarDeleteCurrent = pfBarDeleteCurrent;
window.pfBarFlagCurrent = pfBarFlagCurrent;
window.pfBarPinCurrent = pfBarPinCurrent;
// Global exposieren damit showPanel() pfInit() aufrufen kann
window.pfInit = pfInit;
})();
</script>"""


# ── ORGANISATION Panel ────────────────────────────────────────────────────────
def build_organisation(db):
    try:
        rows = db.execute("SELECT * FROM organisation ORDER BY datum_erkannt DESC").fetchall()
    except:
        rows = []

    groups = {"termin": [], "frist": [], "rueckruf": [], "sonstige": []}
    for r in rows:
        typ = (r["typ"] or "sonstige").lower()
        if typ in groups:
            groups[typ].append(dict(r))
        else:
            groups["sonstige"].append(dict(r))

    n_total = len(rows)
    badge_labels = {"termin": "Termine", "frist": "Fristen", "rueckruf": "Rückrufe"}

    # Sub-Tabs
    tabs_html = f"""<div class="org-view-tabs">
      <div class="komm-view-tab active" onclick="showOrgView(this,'timeline')">Timeline ({n_total})</div>
      <div class="komm-view-tab" onclick="showOrgView(this,'fristen')">Fristen ({len(groups['frist'])})</div>
      <div class="komm-view-tab" onclick="showOrgView(this,'rueckrufe')">R&uuml;ckrufe ({len(groups['rueckruf'])})</div>
      <div class="komm-view-tab" onclick="showOrgView(this,'kalender')">Kalender <span class="si-badge planned" style="font-size:9px;padding:1px 5px">In Planung</span></div>
    </div>"""

    def _org_row(o, show_badge=True):
        typ = o.get('typ','') or ''
        badge_cls = 'org-badge-mail' if True else ''
        return f"""<div class="org-row">
          <span class="org-typ-badge">{esc(typ)}</span>
          <span class="org-datum">{esc(o.get('datum_erkannt','') or '')}</span>
          <span class="org-betreff">{esc((o.get('beschreibung','') or o.get('betreff','') or '')[:70])}</span>
          <span class="org-email muted">{esc(o.get('kunden_email','') or '')}</span>
          <span class="badge" style="font-size:9px;background:var(--accent-bg);color:var(--accent);border:1px solid var(--accent-border)">aus Mail erkannt</span>
        </div>"""

    # Timeline view (all items chronological)
    timeline_items = "".join(_org_row(dict(r)) for r in rows) if rows else "<p class='empty'>Keine Eintr&auml;ge. Termine, Fristen und R&uuml;ckrufbitten erscheinen hier automatisch, sobald sie aus Mails erkannt werden.</p>"

    # Fristen view
    fristen_items = "".join(_org_row(o) for o in groups["frist"]) if groups["frist"] else "<p class='empty'>Keine Fristen erkannt.</p>"

    # Rückrufe view
    rueckruf_items = "".join(_org_row(o) for o in groups["rueckruf"]) if groups["rueckruf"] else "<p class='empty'>Keine R&uuml;ckrufbitten erkannt.</p>"

    # Kalender (geplant)
    kalender_html = """<div class="planned-shell" style="min-height:200px;padding:40px 20px">
      <div class="planned-shell-icon" style="font-size:32px">&#x1F4C5;</div>
      <div class="planned-shell-title" style="font-size:var(--fs-lg)">Kalender-Ansicht</div>
      <div class="planned-shell-desc" style="font-size:var(--fs-sm)">Kalender-Sync mit Outlook, Google Calendar und manuellen Eintr&auml;gen.</div>
      <div class="planned-badge" style="font-size:var(--fs-xs)">&#x1F6A7; In Planung: Kalender-Sync</div>
    </div>"""

    return f"""{tabs_html}
<div id="org-view-timeline" class="org-view active">{timeline_items}</div>
<div id="org-view-fristen" class="org-view">{fristen_items}</div>
<div id="org-view-rueckrufe" class="org-view">{rueckruf_items}</div>
<div id="org-view-kalender" class="org-view">{kalender_html}</div>"""

# ── GESCHÄFT Panel ────────────────────────────────────────────────────────────
def _load_rechnungen_detail():
    """Lädt Detail-Daten aus rechnungen_detail.db, indexiert nach RE-Nummer."""
    details = {}
    mahnungen = []
    try:
        ddb = sqlite3.connect(str(DETAIL_DB))
        ddb.row_factory = sqlite3.Row
        for r in ddb.execute("SELECT * FROM rechnungen_detail"):
            details[r["re_nummer"]] = dict(r)
        mahnungen = [dict(r) for r in ddb.execute("SELECT * FROM mahnungen_detail ORDER BY datum DESC")]
        ddb.close()
    except: pass
    return details, mahnungen


def build_geschaeft(db):
    """Geschäft Dashboard mit 5 Sub-Tabs: Übersicht, Ausgangsrechnungen, Angebote, Eingangsrechnungen, Mahnungen."""
    try: ar = [dict(r) for r in db.execute("SELECT * FROM ausgangsrechnungen ORDER BY datum DESC").fetchall()]
    except: ar = []
    try: ang = [dict(r) for r in db.execute("SELECT * FROM angebote ORDER BY datum DESC").fetchall()]
    except: ang = []
    try: eingang = [dict(r) for r in db.execute("SELECT * FROM geschaeft WHERE wichtigkeit='aktiv' AND (bewertung IS NULL OR bewertung!='erledigt') ORDER BY datum DESC").fetchall()]
    except: eingang = []

    # Detail-Daten laden und anreichern
    re_details, mahnung_details = _load_rechnungen_detail()
    for r in ar:
        re_nr = r.get("re_nummer", "")
        if re_nr in re_details:
            d = re_details[re_nr]
            # Kundennamen aus Detail-DB übernehmen wenn nicht gesetzt
            if not r.get("kunde_name") and d.get("kunde_firma"):
                r["kunde_name"] = d["kunde_firma"]
            r["_detail"] = d  # volle Details für erweiterte Anzeige

    ar_offen = [r for r in ar if r.get("status") == "offen"]
    ar_gemahnt = [r for r in ar if (r.get("mahnung_count") or 0) > 0]
    ang_offen = [r for r in ang if r.get("status") == "offen"]
    s_ar_offen = sum(r.get("betrag_brutto") or 0 for r in ar_offen)
    s_ar_gesamt = sum(r.get("betrag_brutto") or 0 for r in ar)
    s_ar_bezahlt = sum(r.get("betrag_brutto") or 0 for r in ar if r.get("status") == "bezahlt")
    today = datetime.now().strftime("%Y-%m-%d")
    n_nf = sum(1 for r in ang if r.get("status") == "offen" and (r.get("naechster_nachfass") or "") <= today)

    # Skonto-Fristen prüfen
    skonto_dringend = []
    for r in ar_offen:
        d = r.get("_detail", {})
        sd = d.get("skonto_datum", "")
        if sd and sd >= today:
            skonto_dringend.append({"re_nr": r.get("re_nummer", ""), "skonto_datum": sd,
                                    "skonto_prozent": d.get("skonto_prozent", 0),
                                    "skonto_betrag": d.get("skonto_betrag", 0)})

    # Statistik-Daten + Muster aus geschaeft_statistik
    ang_angenommen = [r for r in ang if r.get("status") == "angenommen"]
    ang_abgelehnt = [r for r in ang if r.get("status") == "abgelehnt"]
    ar_bezahlt = [r for r in ar if r.get("status") == "bezahlt"]
    # Zahlungsdauern aus geschaeft_statistik lesen
    zahlungsdauern = []
    try:
        for s in db.execute("SELECT daten_json FROM geschaeft_statistik WHERE ereignis='status_bezahlt' AND daten_json IS NOT NULL"):
            d = json.loads(s[0]) if s[0] else {}
            if d.get('zahlungsdauer_tage'):
                zahlungsdauern.append(d['zahlungsdauer_tage'])
    except: pass
    stats = {"ang_total": len(ang), "ang_angenommen": len(ang_angenommen),
             "ang_abgelehnt": len(ang_abgelehnt), "ar_bezahlt": len(ar_bezahlt), "ar_total": len(ar),
             "ar_gesamt_eur": s_ar_gesamt, "ar_bezahlt_eur": s_ar_bezahlt,
             "skonto_dringend": skonto_dringend, "zahlungsdauern": zahlungsdauern}

    n_mahnungen = len(ar_gemahnt) + len([m for m in mahnung_details if not any(r.get("re_nummer") == m.get("re_nummer") for r in ar_gemahnt)])

    # Bezahlte Rechnungen für Zahlungen-Tab
    ar_bezahlt = [r for r in ar if r.get("status") == "bezahlt"]

    alarm_vol = ' alarm' if s_ar_offen else ''
    alarm_ein = ' alarm' if eingang else ''
    alarm_nf  = ' alarm' if n_nf else ''
    alarm_mah = ' alarm' if ar_gemahnt else ''
    html = f"""
    <div class="gh-mod-header">
      <div class="gh-mod-title">Gesch&auml;ft</div>
      <div class="gh-mod-stats">
        <div class="gh-stat{alarm_vol}">
          <div class="gh-stat-num">{s_ar_offen:,.0f}&thinsp;&euro;</div>
          <div class="gh-stat-lbl">Offenes Vol.</div>
        </div>
        <div class="gh-stat{alarm_ein}">
          <div class="gh-stat-num">{len(eingang)}</div>
          <div class="gh-stat-lbl">Eingangsre.</div>
        </div>
        <div class="gh-stat">
          <div class="gh-stat-num">{len(ang_offen)}</div>
          <div class="gh-stat-lbl">Angebote</div>
        </div>
        <div class="gh-stat{alarm_nf}">
          <div class="gh-stat-num">{n_nf}</div>
          <div class="gh-stat-lbl">Nachfass</div>
        </div>
        <div class="gh-stat{alarm_mah}">
          <div class="gh-stat-num">{len(ar_gemahnt)}</div>
          <div class="gh-stat-lbl">Gemahnt</div>
        </div>
      </div>
      <div class="gh-mod-acts">
        <button class="btn btn-sm btn-muted" onclick="openKiraWorkspace('chat')">Kira fragen</button>
        <button class="btn btn-sm btn-muted" onclick="location.reload()">Sync</button>
      </div>
    </div>
    <div class="gesch-tabs">
      <div class="gesch-tab active" onclick="showGeschTab('uebersicht')">Übersicht</div>
      <div class="gesch-tab" onclick="showGeschTab('ausgangsre')">Ausgangsrechnungen ({len(ar)})</div>
      <div class="gesch-tab" onclick="showGeschTab('angebote')">Angebote ({len(ang)})</div>
      <div class="gesch-tab" onclick="showGeschTab('eingangsre')">Eingangsrechnungen ({len(eingang)})</div>
      <div class="gesch-tab" onclick="showGeschTab('zahlungen')">Zahlungen ({len(ar_bezahlt)})</div>
      <div class="gesch-tab" onclick="showGeschTab('mahnungen')">Mahnungen ({n_mahnungen})</div>
      <div class="gesch-tab" onclick="showGeschTab('auswertung')">Auswertung</div>
      <div class="gesch-tab" onclick="showGeschTab('kalkulation')" style="opacity:.5">Kalkulation <span class="si-badge planned" style="font-size:9px;padding:0 4px">Geplant</span></div>
      <div class="gesch-tab" onclick="showGeschTab('preispositionen')" style="opacity:.5">Preispositionen <span class="si-badge planned" style="font-size:9px;padding:0 4px">Geplant</span></div>
      <div class="gesch-tab" onclick="showGeschTab('cashflow')" style="opacity:.5">Cashflow <span class="si-badge planned" style="font-size:9px;padding:0 4px">Geplant</span></div>
    </div>
    <div id="gesch-uebersicht" class="gesch-panel active">{_build_gesch_uebersicht(ar_offen, ar_gemahnt, ang_offen, s_ar_offen, n_nf, eingang, today, stats)}</div>
    <div id="gesch-ausgangsre" class="gesch-panel">{_build_ar_table(ar)}</div>
    <div id="gesch-angebote" class="gesch-panel">{_build_ang_table(ang, today)}</div>
    <div id="gesch-eingangsre" class="gesch-panel">{_gesch_aktiv_cards(eingang)}</div>
    <div id="gesch-zahlungen" class="gesch-panel">{_build_ar_table(ar_bezahlt, scope="az") if ar_bezahlt else "<p class='empty'>Keine bezahlten Rechnungen.</p>"}</div>
    <div id="gesch-mahnungen" class="gesch-panel">{_build_mahnung_section(ar_gemahnt, ar_offen, mahnung_details)}</div>
    <div id="gesch-auswertung" class="gesch-panel">{_build_gesch_auswertung(stats)}</div>
    <div id="gesch-kalkulation" class="gesch-panel"><div class="planned-shell" style="min-height:200px;padding:40px"><div class="planned-shell-icon" style="font-size:32px">&#x1F4D0;</div><div class="planned-shell-title" style="font-size:var(--fs-lg)">Kalkulation</div><div class="planned-shell-desc" style="font-size:var(--fs-sm)">Projekt- und Leistungskalkulation mit Materialkosten, Arbeitszeit und Gewinnmarge.</div><div class="planned-badge" style="font-size:var(--fs-xs)">&#x1F6A7; In Planung</div></div></div>
    <div id="gesch-preispositionen" class="gesch-panel"><div class="planned-shell" style="min-height:200px;padding:40px"><div class="planned-shell-icon" style="font-size:32px">&#x1F4CB;</div><div class="planned-shell-title" style="font-size:var(--fs-lg)">Preispositionen</div><div class="planned-shell-desc" style="font-size:var(--fs-sm)">Leistungskatalog mit Einzelpreisen, Staffeln und Erfahrungswerten.</div><div class="planned-badge" style="font-size:var(--fs-xs)">&#x1F6A7; In Planung</div></div></div>
    <div id="gesch-cashflow" class="gesch-panel"><div class="planned-shell" style="min-height:200px;padding:40px"><div class="planned-shell-icon" style="font-size:32px">&#x1F4B8;</div><div class="planned-shell-title" style="font-size:var(--fs-lg)">Cashflow</div><div class="planned-shell-desc" style="font-size:var(--fs-sm)">Liquidit&auml;ts&uuml;bersicht mit Ein- und Auszahlungen, Prognose und Warnungen.</div><div class="planned-badge" style="font-size:var(--fs-xs)">&#x1F6A7; In Planung</div></div></div>"""
    return html


def _build_gesch_auswertung(stats):
    """Auswertung-Tab mit Kennzahlen und Trends."""
    if not stats:
        return "<p class='empty'>Noch keine ausreichende Datenbasis f&uuml;r Auswertungen.</p>"
    s = stats
    html = '<div class="gesch-summary-grid" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr))">'
    html += f'<div class="gesch-sum-card"><div class="gesch-sum-num">{s.get("ar_gesamt_eur",0):,.0f} &euro;</div><div class="gesch-sum-label">Fakturiert gesamt</div></div>'
    html += f'<div class="gesch-sum-card"><div class="gesch-sum-num" style="color:var(--success)">{s.get("ar_bezahlt_eur",0):,.0f} &euro;</div><div class="gesch-sum-label">Bezahlt</div></div>'
    html += f'<div class="gesch-sum-card"><div class="gesch-sum-num">{s.get("ar_bezahlt",0)}/{s.get("ar_total",0)}</div><div class="gesch-sum-label">Rechnungen bezahlt</div></div>'
    zd = s.get("zahlungsdauern", [])
    zd_avg = f'{sum(zd)/len(zd):.0f}d' if zd else "&ndash;"
    html += f'<div class="gesch-sum-card"><div class="gesch-sum-num">{zd_avg}</div><div class="gesch-sum-label">&Oslash; Zahlungsdauer</div></div>'
    ang_t = s.get("ang_total",0)
    quote = f'{s.get("ang_angenommen",0)/ang_t*100:.0f}%' if ang_t >= 3 else "&ndash;"
    html += f'<div class="gesch-sum-card"><div class="gesch-sum-num">{quote}</div><div class="gesch-sum-label">Angebotsquote</div></div>'
    html += f'<div class="gesch-sum-card"><div class="gesch-sum-num">{s.get("ang_angenommen",0)}</div><div class="gesch-sum-label">Angenommen</div></div>'
    html += f'<div class="gesch-sum-card"><div class="gesch-sum-num">{s.get("ang_abgelehnt",0)}</div><div class="gesch-sum-label">Abgelehnt</div></div>'
    html += '</div>'
    return html


def _build_gesch_uebersicht(ar_offen, ar_gemahnt, ang_offen, s_ar_offen, n_nf, eingang, today, stats=None):
    """Übersicht-Tab: 6 KPI-Hero-Cards + 60/40-Zones (Aktuelle Vorgänge / Signale & Warnungen)."""
    s = stats or {}
    n_ar_offen = len(ar_offen)
    n_ang_offen = len(ang_offen)
    n_eingang = len(eingang)
    n_gemahnt = len(ar_gemahnt)
    ar_bez_eur = s.get("ar_bezahlt_eur", 0)
    ang_ges = s.get("ang_total", 0)
    ang_ann = s.get("ang_angenommen", 0)
    ang_abl = s.get("ang_abgelehnt", 0)
    quote = f"{ang_ann/ang_ges*100:.0f}%" if ang_ges >= 3 else "–"
    skonto_dringend = s.get("skonto_dringend", [])

    # ── 6 KPI Cards ──────────────────────────────────────────────────────────
    a1 = " alarm" if n_ar_offen else ""
    a2 = " alarm" if s_ar_offen else ""
    a4 = " alarm" if n_nf else ""
    a5 = " alarm" if n_eingang else ""
    a6 = " alarm" if n_gemahnt else ""
    html = f"""<div class="gh-kpi-grid">
      <div class="gh-kpi-card{a1}" onclick="showGeschTab('ausgangsre')">
        <div class="gh-kpi-num">{n_ar_offen}</div>
        <div class="gh-kpi-lbl">Offene Rechnungen</div>
        <div class="gh-kpi-sub">{s_ar_offen:,.0f}&thinsp;&euro; ausstehend</div>
      </div>
      <div class="gh-kpi-card{a2}" onclick="showGeschTab('ausgangsre')">
        <div class="gh-kpi-num" style="font-size:18px">{s_ar_offen:,.0f}&thinsp;&euro;</div>
        <div class="gh-kpi-lbl">Offenes Volumen</div>
        <div class="gh-kpi-sub">Bezahlt: {ar_bez_eur:,.0f}&thinsp;&euro;</div>
      </div>
      <div class="gh-kpi-card" onclick="showGeschTab('angebote')">
        <div class="gh-kpi-num">{n_ang_offen}</div>
        <div class="gh-kpi-lbl">Offene Angebote</div>
        <div class="gh-kpi-sub">Quote: {quote} ({ang_ges} gesamt)</div>
      </div>
      <div class="gh-kpi-card{a4}" onclick="showGeschTab('angebote')">
        <div class="gh-kpi-num">{n_nf}</div>
        <div class="gh-kpi-lbl">Nachfass f&auml;llig</div>
        <div class="gh-kpi-sub">Offene Angebote kontaktieren</div>
      </div>
      <div class="gh-kpi-card{a5}" onclick="showGeschTab('eingangsre')">
        <div class="gh-kpi-num">{n_eingang}</div>
        <div class="gh-kpi-lbl">Eingangsrechnungen</div>
        <div class="gh-kpi-sub">Offen zur Pr&uuml;fung</div>
      </div>
      <div class="gh-kpi-card{a6}" onclick="showGeschTab('mahnungen')">
        <div class="gh-kpi-num">{n_gemahnt}</div>
        <div class="gh-kpi-lbl">Gemahnte Rechnungen</div>
        <div class="gh-kpi-sub">Mahnverfahren aktiv</div>
      </div>
    </div>"""

    # ── Left zone: Aktuelle Vorgänge ──────────────────────────────────────────
    items = []

    # Skonto-Fristen zuerst (zeitkritisch)
    for sk in sorted(skonto_dringend, key=lambda x: x["skonto_datum"]):
        tage_rest = (datetime.strptime(sk["skonto_datum"], "%Y-%m-%d").date() - datetime.now().date()).days
        color = 'style="color:var(--danger)"' if tage_rest <= 2 else ""
        betrag_s = f'{sk["skonto_betrag"]:,.2f}&thinsp;&euro;' if sk.get("skonto_betrag") else ""
        items.append(f'<div class="gh-bi-row"><span class="gh-bi-typ re">Skonto</span>'
                     f'<div class="gh-bi-info"><div class="gh-bi-name">{sk["re_nr"]} &middot; '
                     f'<span {color}>{tage_rest}d verbleibend</span></div>'
                     f'<div class="gh-bi-meta">Frist: {format_datum(sk["skonto_datum"])} &middot; '
                     f'{sk["skonto_prozent"]}% = {betrag_s}</div></div></div>')

    # Offene Ausgangsrechnungen
    for r in ar_offen[:6]:
        re_nr = esc(r.get("re_nummer", ""))
        kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:28])
        betrag = f'{r.get("betrag_brutto") or 0:,.0f}&thinsp;&euro;'
        d = r.get("_detail", {})
        ziel = d.get("zahlungsziel_datum", "")
        meta = f'Datum: {format_datum(r.get("datum"))}'
        if ziel: meta += f' &middot; F&auml;llig: {format_datum(ziel)}'
        mc = r.get("mahnung_count") or 0
        extra = f' <span style="color:var(--danger);font-weight:700">M{mc}</span>' if mc else ""
        items.append(f'<div class="gh-bi-row"><span class="gh-bi-typ re">Rechnung</span>'
                     f'<div class="gh-bi-info"><div class="gh-bi-name">{re_nr}{extra} &middot; {kunde}</div>'
                     f'<div class="gh-bi-meta">{meta}</div></div>'
                     f'<div class="gh-bi-right"><span class="gh-bi-betrag">{betrag}</span></div></div>')

    # Nachfass-fällige Angebote
    for r in ang_offen:
        if (r.get("naechster_nachfass") or "") <= today:
            a_nr = esc(r.get("a_nummer", ""))
            kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:28])
            nf_d = r.get("naechster_nachfass", "")
            nf_cnt = r.get("nachfass_count") or 0
            items.append(f'<div class="gh-bi-row"><span class="gh-bi-typ nf">Nachfass</span>'
                         f'<div class="gh-bi-info"><div class="gh-bi-name">{a_nr} &middot; {kunde}</div>'
                         f'<div class="gh-bi-meta">F&auml;llig: {format_datum(nf_d)} &middot; {nf_cnt}/3 Kontakte</div>'
                         f'</div></div>')

    # Offene Eingangsrechnungen
    for r in eingang[:3]:
        partner = esc((r.get("gegenpartei") or r.get("gegenpartei_email") or "")[:28])
        betreff = esc((r.get("betreff") or "")[:35])
        betrag_s = f'{r.get("betrag", 0) or 0:,.0f}&thinsp;&euro;' if r.get("betrag") else ""
        name_s = partner or betreff
        items.append(f'<div class="gh-bi-row">'
                     f'<span class="gh-bi-typ re" style="color:var(--text);background:rgba(128,128,128,.12)">Eingang</span>'
                     f'<div class="gh-bi-info"><div class="gh-bi-name">{name_s}</div>'
                     f'<div class="gh-bi-meta">{format_datum(r.get("datum"))}'
                     f'{(" &middot; " + betrag_s) if betrag_s else ""}</div></div></div>')

    items_html = "".join(items) if items else '<p class="empty">Keine aktiven Vorg&auml;nge.</p>'
    n_left = n_ar_offen + n_nf + n_eingang

    # ── Right zone: Signale & Warnungen ──────────────────────────────────────
    warns = []

    for r in ar_gemahnt[:4]:
        re_nr = esc(r.get("re_nummer", ""))
        kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:25])
        mc = r.get("mahnung_count") or 0
        betrag = f'{r.get("betrag_brutto") or 0:,.0f}&thinsp;&euro;'
        warns.append(f'<div class="gh-warn-item"><div class="gh-warn-dot"></div>'
                     f'<div class="gh-warn-body"><div class="gh-warn-text">{re_nr} &middot; {kunde}</div>'
                     f'<div class="gh-warn-sub">Mahnung x{mc} &middot; {betrag}</div>'
                     f'<span class="gh-warn-act" onclick="showGeschTab(\'mahnungen\')">Mahnungen &rarr;</span>'
                     f'</div></div>')

    for sk in sorted(skonto_dringend, key=lambda x: x["skonto_datum"])[:2]:
        tage_rest = (datetime.strptime(sk["skonto_datum"], "%Y-%m-%d").date() - datetime.now().date()).days
        warns.append(f'<div class="gh-warn-item info"><div class="gh-warn-dot"></div>'
                     f'<div class="gh-warn-body"><div class="gh-warn-text">Skonto-Frist: {sk["re_nr"]}</div>'
                     f'<div class="gh-warn-sub">{tage_rest}d verbleibend &middot; '
                     f'{sk["skonto_prozent"]}% = {sk.get("skonto_betrag",0):,.2f}&thinsp;&euro;</div>'
                     f'</div></div>')

    if n_nf > 0:
        warns.append(f'<div class="gh-warn-item info"><div class="gh-warn-dot"></div>'
                     f'<div class="gh-warn-body"><div class="gh-warn-text">{n_nf} Angebot(e) zum Nachfassen f&auml;llig</div>'
                     f'<div class="gh-warn-sub">Keine Reaktion &rarr; Angebot verloren</div>'
                     f'<span class="gh-warn-act" onclick="showGeschTab(\'angebote\')">Angebote &rarr;</span>'
                     f'</div></div>')

    zdauern = s.get("zahlungsdauern", [])
    zd_avg = f'{sum(zdauern)/len(zdauern):.0f}' if zdauern else "–"
    if zdauern:
        warns.append(f'<div class="gh-warn-item ok"><div class="gh-warn-dot"></div>'
                     f'<div class="gh-warn-body"><div class="gh-warn-text">&Oslash; Zahlungsdauer: {zd_avg} Tage</div>'
                     f'<div class="gh-warn-sub">{s.get("ar_bezahlt",0)}/{s.get("ar_total",0)} Rechnungen bezahlt</div>'
                     f'</div></div>')

    if ang_ges >= 3:
        warns.append(f'<div class="gh-warn-item ok"><div class="gh-warn-dot"></div>'
                     f'<div class="gh-warn-body"><div class="gh-warn-text">Angebotsquote: {quote}</div>'
                     f'<div class="gh-warn-sub">{ang_ann} angenommen &middot; {ang_abl} abgelehnt</div>'
                     f'</div></div>')

    warn_html = "".join(warns) if warns else '<p class="empty" style="font-size:var(--fs-sm)">Keine Signale.</p>'

    html += f"""<div class="gh-zones">
      <div class="gh-zone">
        <div class="gh-zone-hdr">
          <span>Aktuelle Vorg&auml;nge</span>
          <span class="count-badge">{n_left}</span>
        </div>
        <div class="gh-zone-body">{items_html}</div>
      </div>
      <div class="gh-zone">
        <div class="gh-zone-hdr">
          <span>Signale &amp; Warnungen</span>
          <button class="btn btn-xs btn-muted" onclick="openKiraWorkspace('chat')" style="font-size:10px">Kira</button>
        </div>
        <div class="gh-zone-body">{warn_html}</div>
      </div>
    </div>"""
    return html


def _build_ar_table(rows, scope="ar"):
    """Ausgangsrechnungen-Tab mit Filter, Detail-Infos und Tabelle. scope: 'ar' oder 'az'."""
    if not rows:
        return "<p class='empty'>Keine Ausgangsrechnungen vorhanden.</p>"
    years = sorted(set(r.get("datum", "")[:4] for r in rows if r.get("datum")), reverse=True)
    y_opts = "".join(f'<option value="{y}">{y}</option>' for y in years)
    # Summary-Bar
    total = sum(r.get("betrag_brutto") or 0 for r in rows)
    offen = sum(r.get("betrag_brutto") or 0 for r in rows if r.get("status") == "offen")
    bezahlt = sum(r.get("betrag_brutto") or 0 for r in rows if r.get("status") == "bezahlt")
    html = f"""<div class="gesch-ar-summary">
      <span>Gesamt: <strong>{total:,.2f} &euro;</strong></span>
      <span style="color:#e84545">Offen: <strong>{offen:,.2f} &euro;</strong></span>
      <span style="color:#50c878">Bezahlt: <strong>{bezahlt:,.2f} &euro;</strong></span>
    </div>
    <div class="gesch-filter-bar">
      <select id="{scope}-filter-year" onchange="filterAR('{scope}')"><option value="">Alle Jahre</option>{y_opts}</select>
      <select id="{scope}-filter-status" onchange="filterAR('{scope}')">
        <option value="">Alle Status</option><option value="offen">Offen</option>
        <option value="bezahlt">Bezahlt</option><option value="streitfall">Streitfall</option>
      </select>
      <span id="{scope}-count" class="gesch-filter-count">{len(rows)} Rechnungen</span>
    </div>
    <div class="gesch-table" id="{scope}-table">
      <div class="gesch-row gesch-header">
        <span class="gc-nr">RE-Nr</span><span class="gc-datum">Datum</span>
        <span class="gc-partner">Kunde</span><span class="gc-betrag">Betrag</span>
        <span class="gc-detail">Details</span>
        <span class="gc-status">Status</span><span class="gc-actions">Aktionen</span>
      </div>"""
    today = datetime.now().strftime("%Y-%m-%d")
    for r in rows:
        rid = r.get("id", "")
        re_nr = esc(r.get("re_nummer", ""))
        datum = r.get("datum", "") or ""
        yr = datum[:4]
        kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:30])
        betrag = f'{r.get("betrag_brutto") or 0:,.2f}' if r.get("betrag_brutto") else "-"
        status = r.get("status", "offen")
        s_cls = {"offen": "tag-alarm", "bezahlt": "tag-zahlung", "streitfall": "tag-rechnung"}.get(status, "tag-muted")
        mc = r.get("mahnung_count") or 0
        m_badge = f' <span class="badge badge-warn">M{mc}</span>' if mc > 0 else ""
        # Detail-Info aus rechnungen_detail
        d = r.get("_detail", {})
        detail_parts = []
        n_pos = len(json.loads(d.get("positionen_json", "[]"))) if d.get("positionen_json") else 0
        if n_pos:
            detail_parts.append(f'{n_pos} Pos.')
        if d.get("zahlungsziel_tage"):
            detail_parts.append(f'Ziel: {d["zahlungsziel_tage"]}d')
        if d.get("skonto_prozent") and status == "offen":
            sk_datum = d.get("skonto_datum", "")
            if sk_datum and sk_datum >= today:
                detail_parts.append(f'<span style="color:#50c878">{d["skonto_prozent"]}% Skonto bis {format_datum(sk_datum)}</span>')
            elif sk_datum:
                detail_parts.append(f'<span class="muted" style="text-decoration:line-through">{d["skonto_prozent"]}% Skonto</span>')
        if d.get("reverse_charge"):
            detail_parts.append('<span class="muted">RC</span>')
        if d.get("kunde_ort"):
            detail_parts.append(f'<span class="muted">{esc(d["kunde_ort"][:20])}</span>')
        detail_html = " &middot; ".join(detail_parts) if detail_parts else '<span class="muted">-</span>'
        anh = r.get("anhaenge_pfad", "") or ""
        anh_btn = f'<button class="btn btn-xs btn-gold" onclick="openAttachments(\'{urllib.parse.quote(anh, safe="")}\')">PDF</button>' if anh else ""
        mref = r.get("mail_ref", "") or ""
        mail_btn = f'<button class="btn btn-xs btn-muted" onclick="readMail(\'{urllib.parse.quote(mref, safe="")}\')">Mail</button>' if mref else ""
        kira_btn = f'<button class="btn btn-xs btn-muted" onclick="geschKira(\'re\',\'{js_esc(re_nr)}\',\'{js_esc(kunde)}\',\'{betrag}\')" title="Mit Kira besprechen">Kira</button>'
        if status == "offen":
            acts = f'<button class="btn btn-xs btn-green" onclick="arSetStatus({rid},\'bezahlt\')">Bezahlt</button> <button class="btn btn-xs btn-warn" onclick="arSetStatus({rid},\'streitfall\')">Streitfall</button>'
        elif status == "streitfall":
            acts = f'<button class="btn btn-xs btn-green" onclick="arSetStatus({rid},\'bezahlt\')">Doch bezahlt</button>'
        else:
            acts = '<span style="color:rgba(80,200,120,.6);font-size:11px">&#10003; bezahlt</span>'
        html += f"""<div class="gesch-row {scope}-row" id="{scope}-{rid}" data-year="{yr}" data-status="{status}">
          <span class="gc-nr">{re_nr}{m_badge}</span><span class="gc-datum">{format_datum(datum)}</span>
          <span class="gc-partner">{kunde}</span><span class="gc-betrag">{betrag}</span>
          <span class="gc-detail" style="font-size:11px">{detail_html}</span>
          <span class="gc-status"><span class="tag {s_cls}">{status}</span></span>
          <span class="gc-actions">{anh_btn} {mail_btn} {kira_btn} {acts}</span>
        </div>"""
    html += '</div>'
    return html


def _build_ang_table(rows, today):
    """Angebote-Tab mit Filter, Nachfass-Indikator und Status-Actions."""
    if not rows:
        return "<p class='empty'>Keine Angebote vorhanden.</p>"
    years = sorted(set(r.get("datum", "")[:4] for r in rows if r.get("datum")), reverse=True)
    y_opts = "".join(f'<option value="{y}">{y}</option>' for y in years)
    html = f"""<div class="gesch-filter-bar">
      <select id="ang-filter-year" onchange="filterAng()"><option value="">Alle Jahre</option>{y_opts}</select>
      <select id="ang-filter-status" onchange="filterAng()">
        <option value="">Alle Status</option><option value="offen">Offen</option>
        <option value="angenommen">Angenommen</option><option value="abgelehnt">Abgelehnt</option>
        <option value="keine_antwort">Keine Antwort</option><option value="bearbeitet">Bearbeitet</option>
      </select>
      <span id="ang-count" class="gesch-filter-count">{len(rows)} Angebote</span>
    </div>
    <div class="gesch-table" id="ang-table">
      <div class="gesch-row gesch-header">
        <span class="gc-nr">A-Nr</span><span class="gc-datum">Datum</span>
        <span class="gc-partner">Kunde</span><span class="gc-status">Status</span>
        <span class="gc-nf">Nachfass</span><span class="gc-actions">Aktionen</span>
      </div>"""
    for r in rows:
        rid = r.get("id", "")
        a_nr = esc(r.get("a_nummer", ""))
        datum = r.get("datum", "") or ""
        yr = datum[:4]
        kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:30])
        status = r.get("status", "offen")
        s_cls = {"offen": "tag-alarm", "angenommen": "tag-zahlung", "abgelehnt": "tag-muted",
                 "keine_antwort": "tag-rechnung", "bearbeitet": "tag-antwort"}.get(status, "tag-muted")
        nf_count = r.get("nachfass_count") or 0
        nf_next = r.get("naechster_nachfass") or ""
        if status == "offen":
            if nf_next and nf_next <= today:
                nf_html = f'<span class="gesch-nf-indicator nf-overdue">{nf_count}/3 &middot; F&Auml;LLIG</span>'
            elif nf_next:
                nf_html = f'<span class="gesch-nf-indicator nf-planned">{nf_count}/3 &middot; {nf_next}</span>'
            else:
                nf_html = f'<span class="gesch-nf-indicator">{nf_count}/3</span>'
        else:
            nf_html = f'<span class="muted">{nf_count}</span>'
        anh = r.get("anhaenge_pfad", "") or ""
        anh_btn = f'<button class="btn btn-xs btn-gold" onclick="openAttachments(\'{urllib.parse.quote(anh, safe="")}\')">PDF</button>' if anh else ""
        mref = r.get("mail_ref", "") or ""
        mail_btn = f'<button class="btn btn-xs btn-muted" onclick="readMail(\'{urllib.parse.quote(mref, safe="")}\')">Mail</button>' if mref else ""
        kira_btn = f'<button class="btn btn-xs btn-muted" onclick="geschKira(\'ang\',\'{js_esc(a_nr)}\',\'{js_esc(kunde)}\',\'\')" title="Mit Kira besprechen">Kira</button>'
        if status == "offen":
            acts = (f'<button class="btn btn-xs btn-green" onclick="angSetStatus({rid},\'angenommen\')">Angenommen</button> '
                    f'<button class="btn btn-xs btn-warn" onclick="angSetStatus({rid},\'abgelehnt\')">Abgelehnt</button> '
                    f'<button class="btn btn-xs btn-muted" onclick="angSetStatus({rid},\'keine_antwort\')">Keine Antwort</button>')
        elif status == "bearbeitet":
            acts = (f'<button class="btn btn-xs btn-green" onclick="angSetStatus({rid},\'angenommen\')">Angenommen</button> '
                    f'<button class="btn btn-xs btn-warn" onclick="angSetStatus({rid},\'abgelehnt\')">Abgelehnt</button>')
        else:
            sym = {"angenommen": "&#10003;", "abgelehnt": "&#10007;", "keine_antwort": "&ndash;"}.get(status, "")
            acts = f'<span class="muted" style="font-size:11px">{sym} {status}</span>'
        html += f"""<div class="gesch-row ang-row" id="ang-{rid}" data-year="{yr}" data-status="{status}">
          <span class="gc-nr">{a_nr}</span><span class="gc-datum">{format_datum(datum)}</span>
          <span class="gc-partner">{kunde}</span>
          <span class="gc-status"><span class="tag {s_cls}">{status}</span></span>
          <span class="gc-nf">{nf_html}</span>
          <span class="gc-actions">{anh_btn} {mail_btn} {kira_btn} {acts}</span>
        </div>"""
    html += '</div>'
    return html


def _gesch_aktiv_cards(rows):
    """Eingangsrechnungen / Aktive Geschäftsvorgänge als Karten."""
    if not rows:
        return "<p class='empty'>Keine offenen Eingangsrechnungen.</p>"
    html = ""
    for r in rows:
        gid = r.get("id", "")
        betrag = f"{r.get('betrag', 0) or 0:,.2f} EUR" if r.get("betrag") else ""
        typ = r.get("typ", "") or ""
        typ_label = "Zahlungserinnerung" if typ == "zahlungserinnerung" else "Eingangsrechnung"
        typ_cls = "gesch-typ-mahnung" if typ == "zahlungserinnerung" else "gesch-typ-eingang"
        partner = esc((r.get("gegenpartei", "") or r.get("gegenpartei_email", "") or "")[:40])
        betreff = esc((r.get("betreff", "") or "")[:60])
        datum = format_datum(r.get("datum"))
        re_nr = esc((r.get("rechnungsnummer", "") or "")[:25])
        mail_ref = r.get("mail_ref", "") or ""
        bew = r.get("bewertung", "") or ""
        korrekt_badge = '<span class="badge badge-korrekt">Korrekt</span>' if bew == "korrekt" else ""
        anh_pfad = r.get("anhaenge_pfad", "") or ""
        anh_btn = ""
        if anh_pfad:
            enc_path = urllib.parse.quote(anh_pfad, safe='')
            anh_btn = f'<button class="btn btn-tiny btn-gold" onclick="openAttachments(\'{enc_path}\')" title="Anhang öffnen">Anhang</button>'
        mail_btn = ""
        if mail_ref:
            enc_mid = urllib.parse.quote(mail_ref, safe='')
            mail_btn = f'<button class="btn btn-tiny btn-muted" onclick="readMail(\'{enc_mid}\')">Mail</button>'
        korr_btn = (f'<button class="btn btn-tiny btn-muted" disabled style="opacity:.5">Korrekt</button>'
                    if bew == "korrekt" else
                    f'<button class="btn btn-tiny btn-muted" onclick="geschBewertung({gid},\'korrekt\')">Korrekt</button>')
        html += f"""<div class="gesch-aktiv-card" id="gesch-{gid}" {'style="border-color:rgba(80,200,120,.3)"' if bew == 'korrekt' else ''}>
          <div class="gesch-aktiv-header">
            <span class="gesch-typ-badge {typ_cls}">{typ_label}</span>
            {korrekt_badge}
            <span class="gesch-aktiv-betrag">{betrag}</span>
            <span class="gesch-aktiv-datum">{datum}</span>
          </div>
          <div class="gesch-aktiv-body">
            <div class="gesch-aktiv-betreff">{betreff}</div>
            <div class="gesch-aktiv-partner">{partner}{(' &middot; Re-Nr: ' + re_nr) if re_nr else ''}</div>
          </div>
          <div class="gesch-aktiv-actions">
            <button class="btn btn-sm btn-green" onclick="geschErledigt({gid})">Erledigt</button>
            {anh_btn}
            {mail_btn}
            {korr_btn}
            <button class="btn btn-tiny btn-warn" onclick="geschBewertungDialog({gid})">Falsch</button>
            <button class="btn btn-tiny btn-muted" onclick="geschKira('eingang','{js_esc(re_nr)}','{js_esc(partner)}','{js_esc(betrag)}')" title="Mit Kira besprechen">Kira</button>
          </div>
        </div>"""
    return html


def _build_mahnung_section(gemahnt, ar_offen, mahnung_details=None):
    """Mahnungen-Tab: Echte Mahnung-Timeline aus mahnungen_detail + überfällige offene."""
    html = ""
    mahnung_details = mahnung_details or []
    today_dt = datetime.now()
    today = today_dt.strftime("%Y-%m-%d")

    # Überfällige offene ohne Mahnung
    overdue = []
    for r in ar_offen:
        if (r.get("mahnung_count") or 0) > 0:
            continue
        d = r.get("_detail", {})
        ziel = d.get("zahlungsziel_datum", "")
        try:
            if ziel:
                frist = datetime.strptime(ziel, "%Y-%m-%d")
                days = (today_dt - frist).days
                if days > 0:
                    overdue.append((r, days, "fällig"))
            else:
                dt = datetime.strptime((r.get("datum", "") or "")[:10], "%Y-%m-%d")
                days = (today_dt - dt).days
                if days > 30:
                    overdue.append((r, days, "gestellt"))
        except:
            continue
    if overdue:
        html += '<div class="section"><div class="section-title" style="color:#e84545">Überfällige Rechnungen (ohne Mahnung)</div><div class="section-body">'
        for r, days, label in sorted(overdue, key=lambda x: -x[1]):
            rid = r.get("id", "")
            re_nr = esc(r.get("re_nummer", ""))
            kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:30])
            betrag = f'{r.get("betrag_brutto") or 0:,.2f} EUR' if r.get("betrag_brutto") else ""
            html += f'<div class="gesch-urgent-item"><span class="badge badge-warn">{days}d überfällig</span> {re_nr} &middot; {kunde} &middot; {betrag} <button class="btn btn-xs btn-green" onclick="arSetStatus({rid},\'bezahlt\')" style="margin-left:auto">Bezahlt</button></div>'
        html += '</div></div>'

    # Mahnungen aus mahnungen_detail gruppiert nach RE-Nummer
    re_mahnungen = {}
    for m in mahnung_details:
        re_nr = m.get("re_nummer", "")
        if re_nr not in re_mahnungen:
            re_mahnungen[re_nr] = []
        re_mahnungen[re_nr].append(m)

    if gemahnt or re_mahnungen:
        html += '<div class="section"><div class="section-title">Mahnungen &amp; Zahlungserinnerungen</div><div class="section-body">'
        # Zuerst gemahnte Rechnungen aus tasks.db mit echten Timeline-Daten
        shown_re = set()
        for r in gemahnt:
            rid = r.get("id", "")
            re_nr = r.get("re_nummer", "")
            re_nr_esc = esc(re_nr)
            shown_re.add(re_nr)
            datum = format_datum(r.get("datum"))
            kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:30])
            status = r.get("status", "offen")
            betrag = f'{r.get("betrag_brutto") or 0:,.2f} EUR' if r.get("betrag_brutto") else ""
            s_cls = "tag-zahlung" if status == "bezahlt" else "tag-alarm"
            # Echte Timeline aus mahnungen_detail
            m_list = re_mahnungen.get(re_nr, [])
            timeline = f'<span class="muted" style="font-size:11px">Rechnung: {datum}'
            for m in sorted(m_list, key=lambda x: x.get("datum", "")):
                m_typ = m.get("typ", "")
                m_datum = format_datum(m.get("datum", ""))
                m_betrag_val = m.get("betrag", 0)
                m_betrag = f' ({m_betrag_val:,.2f} &euro;)' if m_betrag_val else ""
                if m_typ == "erinnerung":
                    timeline += f' &#8594; Erinnerung {m_datum}{m_betrag}'
                else:
                    timeline += f' &#8594; <strong>Mahnung</strong> {m_datum}{m_betrag}'
            if not m_list:
                mc = r.get("mahnung_count") or 0
                if mc >= 1: timeline += ' &#8594; 1. Erinnerung'
                if mc >= 2: timeline += ' &#8594; 2. Mahnung'
            timeline += '</span>'
            acts = ""
            if status == "offen":
                acts = f'<button class="btn btn-xs btn-green" onclick="arSetStatus({rid},\'bezahlt\')">Bezahlt</button> <button class="btn btn-xs btn-warn" onclick="arSetStatus({rid},\'streitfall\')">Streitfall</button>'
            html += f"""<div class="gesch-aktiv-card" style="border-color:rgba(232,69,69,.3)">
              <div class="gesch-aktiv-header">
                <span class="gesch-typ-badge gesch-typ-mahnung">Mahnung</span>
                <span class="tag {s_cls}">{status}</span>
                <span class="gesch-aktiv-betrag">{betrag}</span>
                <span class="gesch-aktiv-datum">{datum}</span>
              </div>
              <div class="gesch-aktiv-body">
                <div class="gesch-aktiv-betreff">{re_nr_esc} &middot; {kunde}</div>
                <div>{timeline}</div>
              </div>
              <div class="gesch-aktiv-actions">{acts}</div>
            </div>"""

        # Mahnungen die nur in mahnungen_detail existieren (z.B. alte/nicht in tasks.db)
        for re_nr, m_list in re_mahnungen.items():
            if re_nr in shown_re:
                continue
            re_nr_esc = esc(re_nr)
            m_sorted = sorted(m_list, key=lambda x: x.get("datum", ""))
            latest = m_sorted[-1]
            betrag = f'{latest.get("betrag", 0):,.2f} EUR' if latest.get("betrag") else ""
            timeline = '<span class="muted" style="font-size:11px">'
            for m in m_sorted:
                m_typ = m.get("typ", "")
                m_datum = format_datum(m.get("datum", ""))
                lbl = "Erinnerung" if m_typ == "erinnerung" else "<strong>Mahnung</strong>"
                timeline += f'{lbl} {m_datum} &middot; '
            timeline = timeline.rstrip(' &middot; ') + '</span>'
            html += f"""<div class="gesch-aktiv-card" style="border-color:rgba(232,69,69,.2);opacity:.7">
              <div class="gesch-aktiv-header">
                <span class="gesch-typ-badge gesch-typ-mahnung">Archiv</span>
                <span class="gesch-aktiv-betrag">{betrag}</span>
              </div>
              <div class="gesch-aktiv-body">
                <div class="gesch-aktiv-betreff">{re_nr_esc}</div>
                <div>{timeline}</div>
              </div>
            </div>"""

        html += '</div></div>'

    if not gemahnt and not re_mahnungen and not overdue:
        html += "<p class='empty'>Keine Mahnungen oder überfälligen Rechnungen.</p>"

    html += """<div class="section" style="margin-top:10px">
      <div class="section-title">Rechtliche Hinweise</div>
      <div class="section-body" style="font-size:12px;color:var(--muted);line-height:1.8">
        <strong>Typischer Mahnverlauf:</strong><br>
        1. Zahlungserinnerung (14 Tage nach F&auml;lligkeit)<br>
        2. Erste Mahnung (14 Tage nach Erinnerung)<br>
        3. Letzte Mahnung mit Fristsetzung (14 Tage nach 1. Mahnung)<br>
        4. Gerichtliches Mahnverfahren / Inkasso
      </div>
    </div>"""
    return html


# ── EINSTELLUNGEN Panel ──────────────────────────────────────────────────────
def _rtlog_type_row(typ, label, cfg_id, checked, count):
    dot = '#5cb85c' if checked else '#888'
    chk = 'checked' if checked else ''
    cnt = f'<span id="rl-type-cnt-{typ}" style="font-size:10px;color:var(--muted);margin-left:auto;margin-right:8px">{count} Eintr.</span>' if count else f'<span id="rl-type-cnt-{typ}" style="font-size:10px;color:var(--muted);margin-left:auto;margin-right:8px"></span>'
    return f'''<div class="settings-row" style="padding:6px 10px;border-bottom:1px solid rgba(255,255,255,.04)">
      <div style="display:flex;align-items:center;gap:6px">
        <span style="width:7px;height:7px;border-radius:50%;background:{dot};display:inline-block"></span>
        <label style="font-size:12px;font-family:monospace;color:var(--kl)">{typ}</label>
        <span style="font-size:11px;color:var(--muted)">{label}</span>
      </div>
      {cnt}
      <input type="checkbox" id="{cfg_id}" {chk}>
    </div>'''


def build_einstellungen():
    config = {}
    try:
        config = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
    except: pass

    ntfy  = config.get("ntfy", {})
    aufg  = config.get("aufgaben", {})
    srv   = config.get("server", {})
    nf    = config.get("nachfass", {})
    benachrichtigungen = config.get("benachrichtigungen", {})
    llm   = get_llm_config()
    proto = config.get("protokoll", {})
    rtlog_cfg = config.get("runtime_log", {})
    kira_cfg  = config.get("kira", {})
    launcher_variant = kira_cfg.get("launcher_variant", "B")
    kira_size        = kira_cfg.get("size", 112)
    kira_prox_radius = kira_cfg.get("prox_radius", 0.5)
    kira_bounce_dist = kira_cfg.get("bounce_dist", 130)
    kira_idle        = kira_cfg.get("idle_mode", True)
    kira_idle_delay  = kira_cfg.get("idle_delay", 10)
    # Runtime-Log Stats
    try:
        _rl_s = rlog_stats()
        rl_total    = _rl_s.get("total", 0)
        rl_today    = _rl_s.get("today", 0)
        rl_fehler   = _rl_s.get("fehler", 0)
        rl_sessions = _rl_s.get("sessions", 0)
        rl_db_size  = _rl_s.get("db_size", "unbekannt")
        rl_by_type  = _rl_s.get("by_type", {})
    except Exception:
        rl_total = rl_today = rl_fehler = rl_sessions = 0
        rl_db_size = "unbekannt"
        rl_by_type = {}
    # Change-Log Stats
    try:
        from change_log import get_stats as _cl_stats
        _cl_s = _cl_stats()
        change_log_count    = _cl_s.get("total",    0)
        change_log_last     = _cl_s.get("last",      "")
        change_log_moduls   = _cl_s.get("moduls",    [])
        change_log_results  = _cl_s.get("results",   [])
        change_log_by_res   = _cl_s.get("by_result", {})
        change_log_features = _cl_s.get("features",  [])
        change_log_actions  = _cl_s.get("actions",   [])
    except Exception:
        change_log_count    = 0
        change_log_last     = ""
        change_log_moduls   = []
        change_log_results  = []
        change_log_by_res   = {}
        change_log_features = []
        change_log_actions  = []
    # DB-Größe berechnen
    try:
        db_size_bytes = TASKS_DB.stat().st_size
        if db_size_bytes < 1024:         db_size_str = f"{db_size_bytes} B"
        elif db_size_bytes < 1024**2:    db_size_str = f"{db_size_bytes/1024:.1f} KB"
        else:                            db_size_str = f"{db_size_bytes/1024**2:.2f} MB"
    except: db_size_str = "unbekannt"

    # Mail-Archiv Konfiguration
    mail_archiv_cfg = config.get("mail_archiv", {})
    archiv_pfad = mail_archiv_cfg.get("pfad", "")
    neue_mails_archivieren = mail_archiv_cfg.get("neue_mails_archivieren", True)
    bereinigung_aktiv      = mail_archiv_cfg.get("geloeschte_bereinigung_aktiv", True)
    bereinigung_frist      = int(mail_archiv_cfg.get("bereinigung_frist_tage", 90))
    sync_ordner_cfg = mail_archiv_cfg.get("sync_ordner", {})

    # Sync-Ordner HTML pro Konto generieren
    sync_ordner_html = ""
    _pflicht_set = {"INBOX", "Gesendete Elemente"}
    _alle_ordner = ["INBOX", "Gesendete Elemente", "Entwürfe", "Gelöschte Elemente", "Spam"]
    for _ke, _aktive in sync_ordner_cfg.items():
        _chips = ""
        for _on in _alle_ordner:
            _chk = "checked" if _on in _aktive else ""
            _dis = 'disabled title="Pflicht"' if _on in _pflicht_set else ""
            _chips += f'<label class="es-ord-chip"><input type="checkbox" class="es-ord-cb" {_chk} {_dis} data-konto="{esc(_ke)}" data-ordner="{esc(_on)}" onchange="esSyncOrdnerChange(this)"><span>{esc(_on)}</span></label>'
        sync_ordner_html += f'<div class="es-ord-row"><div class="es-ord-email">{esc(_ke)}</div><div class="es-ord-chips">{_chips}</div></div>'

    # Multi-Provider Karten generieren
    providers = get_all_providers()
    # Modell-Validierungsstatus laden (von Hintergrund-Thread geschrieben)
    _mv_state = {}
    try:
        _mv_file = KNOWLEDGE_DIR / "model_validation_state.json"
        if _mv_file.exists():
            _mv_state = json.loads(_mv_file.read_text('utf-8')).get("results", {})
    except Exception:
        pass

    provider_cards = ""
    for i, prov in enumerate(providers):
        pid = prov.get("id", "")
        pname = esc(prov.get("name", prov.get("typ", "?")))
        ptyp = prov.get("typ", "")
        pmodel = prov.get("model", "")
        paktiv = prov.get("aktiv", True)
        pprio = prov.get("prioritaet", i + 1)
        ptype_info = PROVIDER_TYPES.get(ptyp, {})
        pstatus = check_provider_status(prov)
        _mv_result = _mv_state.get(pid, {})
        _model_stale = pstatus["status"] == "ok" and not _mv_result.get("valid", True) and not _mv_result.get("skipped")
        if _model_stale:
            status_icon = "🟡"
        elif pstatus["status"] == "ok":
            status_icon = "🟢"
        elif pstatus["status"] == "no_key":
            status_icon = "🔑"
        else:
            status_icon = "📦"
        status_text = esc(pstatus["message"])
        needs_key = ptype_info.get("needs_key", True)

        # Model-Options für diesen Provider-Typ
        model_options = ""
        for mid, mname in ptype_info.get("models", []):
            sel = "selected" if mid == pmodel else ""
            model_options += f'<option value="{esc(mid)}" {sel}>{esc(mname)}</option>'
        if ptyp == "custom":
            custom_sel = f'<option value="{esc(pmodel)}" selected>{esc(pmodel or "Modell-ID eingeben")}</option>'
            model_options = custom_sel

        aktiv_checked = "checked" if paktiv else ""
        opacity = "" if paktiv else "opacity:.5;"

        key_row = ""
        if needs_key:
            if pstatus.get('status') == 'ok':
                # Key already set — show status with "Ändern" toggle
                key_row = f'''<div class="settings-row" style="margin-top:4px">
              <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
                <span style="font-size:11px;color:var(--success,#3dae6a);font-weight:600">&#x2713; API Key hinterlegt &amp; aktiv</span>
                <button class="btn btn-sm" style="font-size:10px;padding:2px 8px;background:transparent;border:1px solid var(--border);border-radius:4px;color:var(--muted);cursor:pointer"
                  onclick="toggleKeyInput('{js_esc(pid)}',this)">Schl&uuml;ssel &auml;ndern</button>
              </div>
              <div id="keyinp-{esc(pid)}" style="display:none;margin-top:6px">
                <div style="display:flex;gap:4px;align-items:center">
                  <input type="password" id="pkey-{esc(pid)}" value="" placeholder="Neuen Key eingeben ..." style="width:190px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;font-size:11px;">
                  <button class="btn btn-sm" style="font-size:10px;padding:2px 8px;background:var(--kl);color:#000;border:none;border-radius:4px;cursor:pointer" onclick="saveProviderKey('{js_esc(pid)}')">Speichern</button>
                </div>
                <div style="font-size:10px;color:var(--muted);margin-top:3px">Neuer Key &uuml;berschreibt den vorhandenen.</div>
              </div>
            </div>'''
            else:
                # Key not set — show input prominently
                key_row = f'''<div class="settings-row" style="margin-top:4px">
              <label style="font-size:11px;color:var(--danger,#dc4a4a);font-weight:600">API Key fehlt &#x26a0;</label>
              <div style="display:flex;gap:4px;align-items:center">
                <input type="password" id="pkey-{esc(pid)}" value="" placeholder="Key eingeben ..." style="width:190px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;font-size:11px;">
                <button class="btn btn-sm" style="font-size:10px;padding:2px 8px;background:var(--kl);color:#000;border:none;border-radius:4px;cursor:pointer" onclick="saveProviderKey('{js_esc(pid)}')">Speichern</button>
              </div>
            </div>'''

        base_url_row = ""
        if ptyp == "custom":
            base_url_val = esc(prov.get("base_url", ""))
            base_url_row = f'''<div class="settings-row" style="margin-top:4px">
              <label style="font-size:11px">Base URL</label>
              <input type="text" id="purl-{esc(pid)}" value="{base_url_val}" placeholder="https://api.example.com/v1" style="width:220px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;font-size:11px;">
            </div>'''
        if ptyp == "custom":
            model_row = f'''<div class="settings-row" style="margin-top:4px">
              <label style="font-size:11px">Modell-ID</label>
              <input type="text" id="pmodel-{esc(pid)}" value="{esc(pmodel)}" placeholder="model-name" style="width:180px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;font-size:11px;">
            </div>'''
        else:
            model_row = f'''<div class="settings-row" style="margin-top:4px">
              <label style="font-size:11px">Modell</label>
              <select id="pmodel-{esc(pid)}" style="width:180px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;font-size:11px;">
                {model_options}
              </select>
            </div>'''

        # Stale-model-Infozeile + "Modell prüfen"-Button
        _mv_auto = _mv_result.get("auto_update", {})
        if _model_stale:
            _mv_reason = esc(_mv_result.get("reason", "Modell nicht mehr verfügbar"))
            _mv_new = esc(_mv_auto.get("new_model", ""))
            _stale_row = (
                f'<div style="font-size:11px;margin:4px 0;padding:4px 8px;background:rgba(255,200,0,.12);'
                f'border:1px solid rgba(255,200,0,.4);border-radius:4px;color:#c8a200;">'
                f'⚠ {_mv_reason}'
                + (f' → <b>{_mv_new}</b> empfohlen' if _mv_new else '')
                + '</div>'
            )
        else:
            _stale_row = ""

        _main_status_txt = (
            "⚠ Modell veraltet — Auto-Update ausgeführt" if _model_stale and _mv_auto.get("changed")
            else "⚠ Modell veraltet" if _model_stale
            else ("API Key aktiv — Chat bereit" if pstatus["status"] == "ok" else status_text)
        )
        _main_status_color = (
            "color:#c8a200;font-weight:700" if _model_stale
            else ("color:#5cb85c;font-weight:700" if pstatus["status"] == "ok" else "color:var(--muted)")
        )

        provider_cards += f'''<div class="provider-card" id="pcard-{esc(pid)}" style="{opacity}border:1px solid var(--border);border-radius:8px;padding:10px 14px;margin-bottom:8px;background:var(--bg-raised);">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <div style="display:flex;align-items:center;gap:8px">
              <span style="font-size:14px">{status_icon}</span>
              <span style="font-weight:700;font-size:13px;color:var(--kl)">{pname}</span>
              <span style="font-size:10px;color:var(--muted)">{esc(ptype_info.get("name",""))}</span>
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <span style="font-size:10px;color:var(--muted)">Prio {pprio}</span>
              <button class="btn btn-sm" style="font-size:10px;padding:1px 6px;background:transparent;color:var(--muted);border:1px solid var(--border);border-radius:4px;cursor:pointer" onclick="moveProvider('{js_esc(pid)}',-1)" title="Höhere Priorität">▲</button>
              <button class="btn btn-sm" style="font-size:10px;padding:1px 6px;background:transparent;color:var(--muted);border:1px solid var(--border);border-radius:4px;cursor:pointer" onclick="moveProvider('{js_esc(pid)}',1)" title="Niedrigere Priorität">▼</button>
              <button class="btn btn-sm" style="font-size:10px;padding:1px 6px;background:transparent;color:#8a6ff0;border:1px solid #8a6ff0;border-radius:4px;cursor:pointer" onclick="checkProviderModel('{js_esc(pid)}')" title="Modell jetzt prüfen">🔍 Modell</button>
              <label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="paktiv-{esc(pid)}" {aktiv_checked} onchange="toggleProvider('{js_esc(pid)}',this.checked)"> Aktiv</label>
              <button class="btn btn-sm" style="font-size:10px;padding:1px 6px;background:transparent;color:#e84545;border:1px solid #e84545;border-radius:4px;cursor:pointer" onclick="deleteProvider('{js_esc(pid)}')" title="Entfernen">✕</button>
            </div>
          </div>
          <div style="font-size:11px;margin-bottom:4px;{_main_status_color}">{_main_status_txt}</div>
          {_stale_row}
          {model_row}
          {key_row}
          {base_url_row}
        </div>'''

    # Active budget model for classifier display
    _BUDGET_DISPLAY = {
        "anthropic":  "claude-haiku-4-5-20251001",
        "openai":     "gpt-4o-mini",
        "openrouter": "openai/gpt-4o-mini",
    }
    active_budget_model = "–"
    for _p in providers:
        if not _p.get("aktiv", True):
            continue
        _pst = check_provider_status(_p)
        if _pst.get("status") == "ok":
            _typ = _p.get("typ", "")
            if _typ in _BUDGET_DISPLAY:
                active_budget_model = _BUDGET_DISPLAY[_typ]
            else:
                active_budget_model = _p.get("model", "?") + " (lokal/custom)"
            break

    # Provider-Typ-Optionen für "Hinzufügen"
    add_type_options = ""
    for tkey, tval in PROVIDER_TYPES.items():
        add_type_options += f'<option value="{esc(tkey)}">{esc(tval["name"])}</option>'

    # Aktiver Provider für Status-Bar
    active_provider = next((p.get("name", p.get("typ", "?")) for p in providers if p.get("aktiv", True)), "–")
    active_model    = next((p.get("model", "?") for p in providers if p.get("aktiv", True)), "–")

    html = f"""<style>
#panel-einstellungen{{padding:0!important;max-width:none!important;width:100%;overflow:hidden;}}
#panel-einstellungen.active{{display:flex!important;flex-direction:column;height:calc(100vh - 52px);}}
.es-shell{{display:flex;flex-direction:column;flex:1;overflow:hidden;}}
.es-mh{{background:var(--bg-raised);border-bottom:0.5px solid var(--border);padding:14px 24px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;flex-shrink:0;}}
.es-mt{{font-size:var(--fs-lg);font-weight:600;color:var(--text);white-space:nowrap;}}
.es-mstats{{display:flex;gap:14px;flex-wrap:wrap;}}
.es-ms{{font-size:var(--fs-xs);color:var(--text-secondary);white-space:nowrap;}}
.es-ms b{{font-weight:600;color:var(--text);}}
.es-macts{{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap;align-items:center;}}
.es-ma{{font-size:var(--fs-xs);padding:5px 12px;border-radius:6px;border:0.5px solid var(--border-strong);background:var(--bg);color:var(--text-secondary);cursor:pointer;white-space:nowrap;font-family:inherit;transition:background 0.12s;}}
.es-ma:hover{{background:var(--bg-overlay);color:var(--text);}}
.es-ma.es-pri{{background:#444441;border-color:#444441;color:#fff;}}
.es-ct{{display:flex;flex:1;overflow:hidden;min-height:0;}}
.es-snav{{width:220px;min-width:220px;background:var(--bg-raised);border-right:0.5px solid var(--border);padding:12px 0;overflow-y:auto;flex-shrink:0;}}
.es-snav-h{{font-size:var(--fs-xs);font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;padding:10px 18px 5px;}}
.es-sn{{display:flex;align-items:center;gap:8px;padding:9px 18px;font-size:var(--fs-sm);color:var(--text-secondary);cursor:pointer;border-left:2px solid transparent;transition:background 0.12s;user-select:none;}}
.es-sn:hover{{background:var(--bg-overlay);}}
.es-sn.act{{background:var(--accent-bg,rgba(68,68,65,.08));border-left-color:var(--accent,#444441);color:var(--text);font-weight:600;}}
.es-sico{{width:18px;text-align:center;font-size:var(--fs-xs);opacity:0.5;flex-shrink:0;}}
.es-sn.act .es-sico{{opacity:0.8;}}
.es-scnt{{font-size:9px;background:var(--bg-overlay);color:var(--muted);padding:1px 6px;border-radius:8px;margin-left:auto;}}
.es-sn.es-plan{{opacity:0.55;}}
.es-pb{{font-size:8px;background:var(--bg-overlay);color:var(--muted);padding:1px 5px;border-radius:3px;margin-left:auto;}}
.es-sn-sep{{height:0.5px;background:var(--border);margin:8px 18px;}}
.es-main{{flex:1;overflow-y:auto;padding:24px 28px;background:var(--bg);}}
.es-sec-panel{{display:none;}}
.es-sec-panel.es-active{{display:block;}}
.es-sec-h{{font-size:var(--fs-lg);font-weight:600;color:var(--text);margin-bottom:4px;}}
.es-sec-sub{{font-size:var(--fs-xs);color:var(--muted);margin-bottom:16px;line-height:1.5;}}
.es-grp{{background:var(--bg-raised);border:0.5px solid var(--border);border-radius:10px;padding:18px 20px;margin-bottom:12px;}}
.es-grp-h{{font-size:var(--fs-sm);font-weight:600;color:var(--text);margin-bottom:4px;}}
.es-grp-sub{{font-size:var(--fs-xs);color:var(--muted);margin-bottom:12px;line-height:1.4;}}
.es-row{{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:0.5px solid var(--border);}}
.es-row:last-child{{border-bottom:none;}}
.es-row-label{{flex:1;display:flex;flex-direction:column;gap:2px;min-width:0;}}
.es-row-label span:first-child{{font-size:13px;color:var(--text);font-weight:500;}}
.es-row-hint{{font-size:11px;color:var(--muted,var(--text-muted));line-height:1.4;}}
.es-rl{{font-size:var(--fs-sm);color:var(--text);flex:1;min-width:0;}}
.es-rd{{font-size:var(--fs-xs);color:var(--muted);margin-top:2px;line-height:1.4;}}
.es-toggle-wrap{{position:relative;display:inline-flex;align-items:center;cursor:pointer;flex-shrink:0;}}
.es-toggle-inp{{position:absolute;opacity:0;width:0;height:0;pointer-events:none;}}
.es-toggle-vis{{display:inline-block;width:38px;height:20px;background:var(--border-strong,#888);border-radius:10px;position:relative;transition:background 0.2s;flex-shrink:0;}}
.es-toggle-vis::after{{content:'';position:absolute;top:2px;left:2px;width:16px;height:16px;background:#fff;border-radius:50%;transition:transform 0.2s;}}
.es-toggle-inp:checked ~ .es-toggle-vis{{background:#1D9E75;}}
.es-toggle-inp:checked ~ .es-toggle-vis::after{{transform:translateX(18px);}}
.es-sel{{background:var(--bg);border:0.5px solid var(--border-strong);border-radius:6px;padding:6px 12px;font-size:var(--fs-xs);color:var(--text);font-family:inherit;cursor:pointer;min-width:140px;}}
.es-inp{{background:var(--bg);border:0.5px solid var(--border-strong);border-radius:6px;padding:6px 12px;font-size:var(--fs-xs);color:var(--text);font-family:inherit;width:200px;}}
.es-inp-sm{{background:var(--bg);border:0.5px solid var(--border-strong);border-radius:6px;padding:6px 12px;font-size:var(--fs-xs);color:var(--text);font-family:inherit;width:100px;}}
.es-badge{{font-size:var(--fs-xs);padding:3px 10px;border-radius:5px;font-weight:500;flex-shrink:0;white-space:nowrap;}}
.es-badge.on{{background:#EAF3DE;color:#3B6D11;}}
.es-badge.off{{background:var(--bg-overlay);color:var(--muted);}}
.es-badge.plan{{background:var(--bg-overlay);color:var(--muted);border:0.5px solid var(--border);}}
.es-btn{{font-size:var(--fs-xs);padding:5px 12px;border-radius:6px;border:0.5px solid var(--border-strong);background:var(--bg);color:var(--text-secondary);cursor:pointer;font-family:inherit;white-space:nowrap;transition:background 0.12s;}}
.es-btn:hover{{background:var(--bg-overlay);}}
.es-btn.es-btn-pri{{background:#444441;border-color:#444441;color:#fff;}}
.es-btn.es-btn-green{{background:#EAF3DE;border-color:#C0DD97;color:#3B6D11;}}
.es-btn.es-btn-red{{background:transparent;border-color:#e84545;color:#e84545;}}
.es-intg{{display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--bg);border:0.5px solid var(--border);border-radius:8px;margin-bottom:6px;}}
.es-intg-ico{{width:32px;height:32px;border-radius:8px;background:var(--bg-overlay);display:flex;align-items:center;justify-content:center;font-size:var(--fs-lg);flex-shrink:0;}}
.es-intg-body{{flex:1;min-width:0;}}
.es-intg-name{{font-size:var(--fs-sm);font-weight:600;color:var(--text);}}
.es-intg-sub{{font-size:var(--fs-xs);color:var(--muted);margin-top:1px;}}
.es-save-bar{{margin-top:16px;padding-top:16px;border-top:0.5px solid var(--border);display:flex;align-items:center;gap:10px;}}
.es-proto-tabs{{display:flex;gap:4px;margin-bottom:16px;border-bottom:0.5px solid var(--border);}}
.es-proto-tab{{padding:8px 16px;font-size:var(--fs-xs);font-weight:600;color:var(--text-secondary);cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-0.5px;transition:color 0.12s;user-select:none;}}
.es-proto-tab.act{{color:var(--accent,#444441);border-bottom-color:var(--accent,#444441);}}
.es-proto-tab-panel{{display:none;}}
.es-proto-tab-panel.act{{display:block;}}
.es-preview{{background:var(--bg-overlay);border:0.5px solid var(--border);border-radius:10px;padding:14px 18px;margin-top:10px;}}
.es-prev-cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:8px;}}
.es-prev-card{{background:var(--bg-raised);border:0.5px solid var(--border);border-radius:8px;padding:10px;}}
.es-prev-card .pc-label{{font-size:var(--fs-xs);color:var(--muted);}}
.es-prev-card .pc-val{{font-size:var(--fs-lg);font-weight:600;color:var(--text);margin-top:2px;}}
</style>
<script>
function esShowSec(id) {{
  document.querySelectorAll('.es-sec-panel').forEach(function(p){{p.classList.remove('es-active');}});
  document.querySelectorAll('.es-sn').forEach(function(n){{n.classList.remove('act');}});
  var panel = document.getElementById('es-sec-'+id);
  if(panel) panel.classList.add('es-active');
  var nav = document.querySelector('.es-sn[data-essec="'+id+'"]');
  if(nav) nav.classList.add('act');
  if(id==='mail') {{ esLoadMailKonten(); esLoadMailArchiv(); esLoadSignaturen(); }}
  if(id==='integrationen') {{ esIntegLoad(); }}
}}
function esShowProtoTab(id) {{
  document.querySelectorAll('.es-proto-tab-panel').forEach(function(p){{p.classList.remove('act');}});
  document.querySelectorAll('.es-proto-tab').forEach(function(t){{t.classList.remove('act');}});
  var panel = document.getElementById('es-ptab-'+id);
  if(panel) panel.classList.add('act');
  var tab = document.querySelector('.es-proto-tab[data-ptab="'+id+'"]');
  if(tab) tab.classList.add('act');
}}
</script>
<div class="es-shell">

<!-- MODULE HEADER -->
<div class="es-mh">
  <span class="es-mt">Einstellungen</span>
  <div class="es-mstats">
    <span class="es-ms">Provider: <b>{active_provider}</b></span>
    <span class="es-ms" title="Aktives Chat-Modell">Modell: <b>{active_model}</b></span>
    <span class="es-ms">Push: <b>{'aktiv' if ntfy.get('aktiv') else 'inaktiv'}</b></span>
    <span class="es-ms">Runtime-Log: <b>{'aktiv' if rtlog_cfg.get('aktiv', True) else 'inaktiv'}</b></span>
    <span class="es-ms">Log-Eintr.: <b>{rl_total}</b></span>
  </div>
  <div class="es-macts">
    <button class="es-ma" onclick="showToast('Export: In Vorbereitung')">&#x2197; Export</button>
    <button class="es-ma" onclick="showToast('Import: In Vorbereitung')">&#x2199; Import</button>
    <button class="es-ma es-pri" onclick="saveSettings()">Speichern</button>
    <span id="settings-status" style="font-size:11px;color:var(--muted)"></span>
  </div>
</div>

<!-- CONTENT AREA -->
<div class="es-ct">

<!-- SECONDARY NAV -->
<div class="es-snav">
  <div class="es-snav-h">Konfiguration</div>
  <div class="es-sn act" data-essec="design" onclick="esShowSec('design')"><span class="es-sico">&#x25D0;</span>Design</div>
  <div class="es-sn" data-essec="benachrichtigungen" onclick="esShowSec('benachrichtigungen')"><span class="es-sico">&#x1F514;</span>Benachrichtigungen</div>
  <div class="es-sn" data-essec="aufgaben" onclick="esShowSec('aufgaben')"><span class="es-sico">&#x2611;</span>Aufgabenlogik</div>
  <div class="es-sn" data-essec="nachfass" onclick="esShowSec('nachfass')"><span class="es-sico">&#x21BB;</span>Nachfass-Intervalle</div>
  <div class="es-sn" data-essec="dashboard" onclick="esShowSec('dashboard')"><span class="es-sico">&#x229E;</span>Dashboard</div>
  <div class="es-sn-sep"></div>
  <div class="es-snav-h">System</div>
  <div class="es-sn" data-essec="provider" onclick="esShowSec('provider')"><span class="es-sico">&#x25C8;</span>Kira / LLM / Provider<span class="es-scnt">{len(providers)}</span></div>
  <div class="es-sn" data-essec="mail" onclick="esShowSec('mail')"><span class="es-sico">&#x2709;</span>Mail &amp; Konten</div>
  <div class="es-sn" data-essec="integrationen" onclick="esShowSec('integrationen')"><span class="es-sico">&#x21C4;</span>Integrationen</div>
  <div class="es-sn es-plan" data-essec="automationen" onclick="esShowSec('automationen')"><span class="es-sico">&#x27F3;</span>Automationen<span class="es-pb">Geplant</span></div>
  <div class="es-sn-sep"></div>
  <div class="es-snav-h">Protokoll</div>
  <div class="es-sn" data-essec="protokoll" onclick="esShowSec('protokoll')"><span class="es-sico">&#x2630;</span>Protokoll &amp; Logs<span class="es-scnt">{rl_total}</span></div>
</div>

<!-- MAIN CONTENT -->
<div class="es-main">

<!-- ── SECTION: DESIGN ─────────────────────────────────────────────────── -->
<div class="es-sec-panel es-active" id="es-sec-design">
  <div class="es-sec-h">Design</div>
  <div class="es-sec-sub">Erscheinungsbild, Farben, Schrift und visuelle Darstellung der Oberfläche.</div>

  <div class="es-grp">
    <div class="es-grp-h">Farbschema &amp; Akzent</div>
    <div class="es-row">
      <div class="es-rl">Farbschema<div class="es-rd">Hell- oder Dunkel-Modus</div></div>
      <select class="es-sel" id="cfg-theme" onchange="applyTheme(this.value)">
        <option value="dark">Dunkel</option>
        <option value="light">Hell</option>
      </select>
    </div>
    <div class="es-row">
      <div class="es-rl">Akzentfarbe<div class="es-rd">Hauptfarbe für Buttons, Links und Highlights</div></div>
      <div style="display:flex;align-items:center;gap:8px">
        <input type="color" id="cfg-accent" value="#4f7df9" onchange="applyAccent(this.value)">
        <span id="cfg-accent-hex" style="font-size:11px;color:var(--muted)">#4f7df9</span>
        <button class="es-btn" onclick="resetAccent()">Zur&uuml;cksetzen</button>
      </div>
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">Typografie &amp; Dichte</div>
    <div class="es-row">
      <div class="es-rl">Schriftgr&ouml;&szlig;e<div class="es-rd">Basis-Schriftgr&ouml;&szlig;e der Oberfläche</div></div>
      <select class="es-sel" id="cfg-fontsize" onchange="applyFontSize(this.value)">
        <option value="">Normal</option>
        <option value="small">Klein</option>
        <option value="large">Gro&szlig;</option>
      </select>
    </div>
    <div class="es-row">
      <div class="es-rl">Schriftfamilie<div class="es-rd">Serifenlose, Mono oder System-Schrift</div></div>
      <select class="es-sel" id="cfg-font-family" onchange="applyFontFamily(this.value)">
        <option value="">Sans-Serif (Standard)</option>
        <option value="mono">Monospace</option>
        <option value="system">System-Font</option>
      </select>
    </div>
    <div class="es-row">
      <div class="es-rl">Dichte<div class="es-rd">Abstände zwischen Elementen</div></div>
      <select class="es-sel" id="cfg-density" onchange="applyDensity(this.value)">
        <option value="">Normal</option>
        <option value="compact">Kompakt</option>
        <option value="comfortable">Komfortabel</option>
      </select>
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">Sidebar &amp; Navigation</div>
    <div class="es-row">
      <div class="es-rl">Sidebar-Breite<div class="es-rd">Standard-Breite der linken Navigation (px). Ziehen an der Kante &uuml;berschreibt diesen Wert.</div></div>
      <div style="display:flex;align-items:center;gap:8px">
        <input class="es-inp-sm" type="number" id="cfg-sidebar-width" min="160" max="400" step="10" value="220" oninput="applySidebarWidth(this.value)">
        <span style="font-size:11px;color:var(--muted)">px</span>
      </div>
    </div>
    <div class="es-row">
      <div class="es-rl">Toast-Position<div class="es-rd">Position der Statusmeldungen auf dem Bildschirm</div></div>
      <select class="es-sel" id="cfg-toast-pos" onchange="applyToastPos(this.value)">
        <option value="">Unten rechts (Standard)</option>
        <option value="bottom-center">Unten Mitte</option>
        <option value="bottom-left">Unten links</option>
        <option value="top-right">Oben rechts</option>
        <option value="top-center">Oben Mitte</option>
        <option value="top-left">Oben links</option>
      </select>
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">Tabellen &amp; Listen</div>
    <div class="es-row">
      <div class="es-rl">Tabellen-Zeilenhöhe<div class="es-rd">Abstands-Modus in Protokoll- und Datentabellen</div></div>
      <select class="es-sel" id="cfg-row-height" onchange="applyRowHeight(this.value)">
        <option value="">Normal</option>
        <option value="compact">Kompakt</option>
        <option value="comfortable">Komfortabel</option>
      </select>
    </div>
    <div class="es-row">
      <div class="es-rl">Zebrastreifen<div class="es-rd">Abwechselnde Hintergrundfarbe in Tabellen</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-table-zebra" onchange="applyTableZebra(this.checked)">
        <div class="es-toggle-vis"></div>
      </label>
    </div>
    <div class="es-row">
      <div class="es-rl">Trennlinien zwischen Zeilen<div class="es-rd">Horizontale Linie zwischen Tabellenzeilen</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-table-lines" onchange="applyTableLines(this.checked)">
        <div class="es-toggle-vis"></div>
      </label>
    </div>
    <div style="margin-top:14px">
      <div style="font-size:var(--fs-xs);color:var(--muted);margin-bottom:8px;font-weight:600">&#x1F441; Vorschau</div>
      <table class="proto-table" style="width:100%;border-collapse:collapse;background:var(--bg)">
        <thead><tr style="background:var(--bg-overlay)">
          <th style="padding:8px 10px;text-align:left;font-size:var(--fs-xs);font-weight:600;border-bottom:1px solid var(--border)">Datum</th>
          <th style="padding:8px 10px;text-align:left;font-size:var(--fs-xs);font-weight:600;border-bottom:1px solid var(--border)">Ereignis</th>
          <th style="padding:8px 10px;text-align:center;font-size:var(--fs-xs);font-weight:600;border-bottom:1px solid var(--border)">Status</th>
        </tr></thead>
        <tbody>
          <tr><td>28.03.2026</td><td>Mail klassifiziert</td><td style="text-align:center">&#x2713;</td></tr>
          <tr><td>28.03.2026</td><td>Aufgabe erstellt</td><td style="text-align:center">&#x2713;</td></tr>
          <tr><td>27.03.2026</td><td>Kira-Chat</td><td style="text-align:center">&#x2713;</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">Branding</div>
    <div class="es-row">
      <div class="es-rl">Firmenname<div class="es-rd">Wird in der Kopfzeile angezeigt</div></div>
      <input class="es-inp" type="text" id="cfg-company-name" placeholder="z.B. Meine Firma" oninput="applyCompanyName(this.value)">
    </div>
    <div class="es-row" style="flex-wrap:wrap;gap:10px">
      <div class="es-rl" style="min-width:180px">Logo<div class="es-rd">URL, Emoji oder Datei hochladen. Wird links oben angezeigt.</div></div>
      <div style="display:flex;flex-direction:column;gap:8px">
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
          <input class="es-inp" type="text" id="cfg-logo" placeholder="https://... oder Emoji K" oninput="applyLogo(this.value)" style="width:180px">
          <label class="es-btn" style="cursor:pointer;margin:0">
            &#x2191; Datei
            <input type="file" id="cfg-logo-file" accept="image/png,image/jpeg,image/svg+xml,image/gif,image/webp" style="display:none" onchange="handleLogoUpload(this)">
          </label>
          <button class="es-btn" onclick="applyLogo('');document.getElementById('cfg-logo').value='';localStorage.removeItem('kira_logo');updateLogoPreview('')">&#x2715; Reset</button>
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          <div id="logo-upload-preview" style="width:40px;height:40px;border:1px solid var(--border);border-radius:8px;display:flex;align-items:center;justify-content:center;overflow:hidden;background:var(--bg-overlay);font-size:20px;flex-shrink:0"></div>
          <span style="font-size:var(--fs-xs);color:var(--muted)">Vorschau (max. 200KB empfohlen)</span>
        </div>
      </div>
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">Karten &amp; Schatten</div>
    <div class="es-row">
      <div class="es-rl">Kartenradius<div class="es-rd">Abrundung der Karten-Ecken</div></div>
      <select class="es-sel" id="cfg-card-radius" onchange="applyCardRadius(this.value)">
        <option value="">Normal (12px)</option>
        <option value="4px">Eckig (4px)</option>
        <option value="20px">Rund (20px)</option>
      </select>
    </div>
    <div class="es-row">
      <div class="es-rl">Schatten<div class="es-rd">Tiefenwirkung der Karten</div></div>
      <select class="es-sel" id="cfg-shadow" onchange="applyShadow(this.value)">
        <option value="">Normal</option>
        <option value="none">Kein Schatten</option>
        <option value="strong">Stark</option>
      </select>
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">Barrierefreiheit</div>
    <div class="es-row">
      <div class="es-rl">Animationen reduzieren<div class="es-rd">Weniger Bewegung f&uuml;r Personen mit Empfindlichkeit</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-reduce-motion" onchange="applyReduceMotion(this.checked)">
        <div class="es-toggle-vis"></div>
      </label>
    </div>
    <div class="es-row">
      <div class="es-rl">Hoher Kontrast<div class="es-rd">Stärkere Kontraste f&uuml;r bessere Lesbarkeit</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-high-contrast" onchange="applyHighContrast(this.checked)">
        <div class="es-toggle-vis"></div>
      </label>
    </div>
  </div>

  <div class="es-grp es-preview">
    <div class="es-grp-h">Vorschau</div>
    <span id="design-status" style="font-size:11px;color:var(--muted)"></span>
    <div class="es-prev-cards" style="margin-top:10px">
      <div class="es-prev-card"><div class="pc-label">Farbschema</div><div class="pc-val" id="prev-theme">–</div></div>
      <div class="es-prev-card"><div class="pc-label">Schrift</div><div class="pc-val" id="prev-font">Normal</div></div>
      <div class="es-prev-card"><div class="pc-label">Dichte</div><div class="pc-val" id="prev-density">Normal</div></div>
    </div>
  </div>

  <div class="es-save-bar">
    <button class="es-btn es-btn-pri" onclick="saveSettings()">Speichern</button>
    <span style="font-size:11px;color:var(--muted)">Design-Einstellungen werden lokal gespeichert</span>
  </div>
</div>

<!-- ── SECTION: BENACHRICHTIGUNGEN ────────────────────────────────────── -->
<div class="es-sec-panel" id="es-sec-benachrichtigungen">
  <div class="es-sec-h">Benachrichtigungen</div>
  <div class="es-sec-sub">Push-Benachrichtigungen via ntfy.sh und In-App Benachrichtigungen konfigurieren.</div>

  <div class="es-grp">
    <div class="es-grp-h">Push-Kanal (ntfy.sh)</div>
    <div class="es-grp-sub">Verbinde einen ntfy-Kanal um Benachrichtigungen auf Dein Ger&auml;t zu erhalten.</div>
    <div class="es-row">
      <div class="es-rl">Push aktiv<div class="es-rd">Benachrichtigungen senden</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-ntfy-aktiv" {'checked' if ntfy.get('aktiv') else ''}>
        <div class="es-toggle-vis"></div>
      </label>
      <span class="es-badge {'on' if ntfy.get('aktiv') else 'off'}">{'Aktiv' if ntfy.get('aktiv') else 'Inaktiv'}</span>
    </div>
    <div class="es-row">
      <div class="es-rl">Kanal (Topic)<div class="es-rd">Eindeutiger Name des ntfy-Kanals</div></div>
      <input class="es-inp" type="text" id="cfg-ntfy-topic" value="{esc(ntfy.get('topic_name',''))}" placeholder="mein-kanal">
    </div>
    <div class="es-row">
      <div class="es-rl">Server-URL<div class="es-rd">Standard: https://ntfy.sh</div></div>
      <input class="es-inp" type="text" id="cfg-ntfy-server" value="{esc(ntfy.get('server','https://ntfy.sh'))}" placeholder="https://ntfy.sh">
    </div>
    <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <button class="es-btn es-btn-green" onclick="testPush()">Test-Push senden</button>
      <a href="https://ntfy.sh" target="_blank" rel="noopener" class="es-btn" style="text-decoration:none">&#x1F4D6; ntfy.sh Doku</a>
    </div>
    <div style="margin-top:10px;padding:10px;background:var(--bg-overlay);border-radius:6px;font-size:11px;color:var(--muted)">
      <strong style="color:var(--text)">Einrichtung:</strong> ntfy-App installieren (iOS/Android) &rarr; + &rarr; Topic-Name eintragen &rarr; Fertig.<br>
      Topic-Name frei w&auml;hlbar, z.B. <code>mein-kira-kanal-2026</code>. Server-URL nur bei eigenem ntfy-Server &auml;ndern.
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">Arbeitszeiten &amp; Urlaubsmodus</div>
    <div class="es-grp-sub">Push-Benachrichtigungen nur zu bestimmten Zeiten senden. Au&szlig;erhalb der Arbeitszeit werden Meldungen gepuffert.</div>
    <div class="es-row">
      <div class="es-rl">Arbeitszeiten-Filter aktiv<div class="es-rd">Push nur w&auml;hrend Arbeitszeit senden</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-ntfy-arbeitszeit-aktiv" {'checked' if ntfy.get('arbeitszeit_aktiv', False) else ''}>
        <div class="es-toggle-vis"></div>
      </label>
    </div>
    <div class="es-row">
      <div class="es-rl">Arbeitszeit von<div class="es-rd">Fr&uuml;hester Push-Zeitpunkt (Uhrzeit)</div></div>
      <input class="es-inp-sm" type="time" id="cfg-ntfy-az-von" value="{esc(ntfy.get('arbeitszeit_von','08:00'))}">
    </div>
    <div class="es-row">
      <div class="es-rl">Arbeitszeit bis<div class="es-rd">Sp&auml;tester Push-Zeitpunkt (Uhrzeit)</div></div>
      <input class="es-inp-sm" type="time" id="cfg-ntfy-az-bis" value="{esc(ntfy.get('arbeitszeit_bis','18:00'))}">
    </div>
    <div class="es-row">
      <div class="es-rl">Urlaubsmodus<div class="es-rd">Alle Push-Benachrichtigungen deaktivieren</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-ntfy-urlaub" {'checked' if ntfy.get('urlaub_modus', False) else ''}>
        <div class="es-toggle-vis"></div>
      </label>
      <span class="es-badge {'off' if ntfy.get('urlaub_modus', False) else 'on'}" id="urlaub-badge" style="{'background:var(--danger,#e84545);color:#fff' if ntfy.get('urlaub_modus', False) else ''}">{'&#x1F3D6; Urlaub aktiv' if ntfy.get('urlaub_modus', False) else 'Kein Urlaub'}</span>
    </div>
    <div class="es-row">
      <div class="es-rl">Urlaub planen: von<div class="es-rd">Automatisch aktivieren ab Datum/Uhrzeit</div></div>
      <input class="es-inp-sm" type="datetime-local" id="cfg-urlaub-von" value="{esc(ntfy.get('urlaub_von',''))}" style="width:180px">
    </div>
    <div class="es-row">
      <div class="es-rl">Urlaub planen: bis<div class="es-rd">Automatisch deaktivieren am Datum/Uhrzeit</div></div>
      <input class="es-inp-sm" type="datetime-local" id="cfg-urlaub-bis" value="{esc(ntfy.get('urlaub_bis',''))}" style="width:180px">
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">In-App Benachrichtigungen</div>
    <div class="es-grp-sub">Toast-Meldungen im Browser zeigen dir, was Kira im Hintergrund macht. So wei&szlig;t du immer was passiert.</div>
    <div class="es-row">
      <div class="es-rl">Mail-Eingang<div class="es-rd">Toast bei neuer klassifizierter Mail</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-inapp-mail" {'checked' if benachrichtigungen.get('inapp_mail', True) else ''}>
        <div class="es-toggle-vis"></div>
      </label>
    </div>
    <div class="es-row">
      <div class="es-rl">Kira-Antwort<div class="es-rd">Toast wenn Kira eine Antwort generiert</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-inapp-kira" {'checked' if benachrichtigungen.get('inapp_kira', True) else ''}>
        <div class="es-toggle-vis"></div>
      </label>
    </div>
    <div class="es-row">
      <div class="es-rl">Aufgaben-Erinnerungen<div class="es-rd">Toast bei Deadline-Warnung und Nachfass</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-inapp-aufgaben" {'checked' if benachrichtigungen.get('inapp_aufgaben', True) else ''}>
        <div class="es-toggle-vis"></div>
      </label>
    </div>
    <div class="es-row">
      <div class="es-rl">Hintergrund-Jobs<div class="es-rd">Toast bei Daily-Check / Mail-Monitor Aktionen</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-inapp-bg" {'checked' if benachrichtigungen.get('inapp_bg', False) else ''}>
        <div class="es-toggle-vis"></div>
      </label>
    </div>
    <div class="es-row">
      <div class="es-rl">Fehler-Meldungen<div class="es-rd">Toast bei Systemfehlern (empfohlen aktiv)</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-inapp-fehler" {'checked' if benachrichtigungen.get('inapp_fehler', True) else ''}>
        <div class="es-toggle-vis"></div>
      </label>
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">Meldungsdauer</div>
    <div class="es-grp-sub">Wie lange werden Toast-Meldungen angezeigt (Sekunden). &Auml;nderungen gelten sofort &mdash; kein Speichern n&ouml;tig.</div>
    <div class="es-row">
      <div class="es-rl">OK-Meldungen <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#1a6e3c;vertical-align:middle;margin-left:4px"></span><div class="es-rd">Best&auml;tigungen (gr&uuml;n)</div></div>
      <input class="es-inp-sm" type="number" id="cfg-toast-dauer-ok" min="1" max="30" value="4" style="width:64px" onchange="applyToastDauer('ok',this.value)">
      <span style="color:var(--muted);font-size:12px;margin-left:4px">s</span>
    </div>
    <div class="es-row">
      <div class="es-rl">Fehler-Meldungen <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#c0392b;vertical-align:middle;margin-left:4px"></span><div class="es-rd">Fehlermeldungen (rot)</div></div>
      <input class="es-inp-sm" type="number" id="cfg-toast-dauer-fehler" min="1" max="60" value="10" style="width:64px" onchange="applyToastDauer('fehler',this.value)">
      <span style="color:var(--muted);font-size:12px;margin-left:4px">s</span>
    </div>
    <div class="es-row">
      <div class="es-rl">Warnungen <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#c87417;vertical-align:middle;margin-left:4px"></span><div class="es-rd">Warnmeldungen (orange)</div></div>
      <input class="es-inp-sm" type="number" id="cfg-toast-dauer-warnung" min="1" max="60" value="7" style="width:64px" onchange="applyToastDauer('warnung',this.value)">
      <span style="color:var(--muted);font-size:12px;margin-left:4px">s</span>
    </div>
    <div class="es-row">
      <div class="es-rl">Info-Meldungen <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--accent);vertical-align:middle;margin-left:4px"></span><div class="es-rd">Hinweise und Prozess-Meldungen (blau)</div></div>
      <input class="es-inp-sm" type="number" id="cfg-toast-dauer-info" min="1" max="60" value="5" style="width:64px" onchange="applyToastDauer('info',this.value)">
      <span style="color:var(--muted);font-size:12px;margin-left:4px">s</span>
    </div>
    <div style="margin-top:8px;padding:8px 10px;background:var(--bg-overlay);border-radius:6px;font-size:11px;color:var(--muted)">
      Vorschau: <button onclick="showToast('OK-Meldung Beispiel','ok')" style="margin:0 4px;padding:2px 8px;border-radius:4px;border:1px solid var(--border);background:var(--bg-raised);cursor:pointer;font-size:11px">&#x2713; OK</button>
      <button onclick="showToast('Fehler: Verbindung getrennt','fehler')" style="margin:0 4px;padding:2px 8px;border-radius:4px;border:1px solid var(--border);background:var(--bg-raised);cursor:pointer;font-size:11px">&#x2715; Fehler</button>
      <button onclick="showToast('Warnung: Archiv-Pfad fehlt','warnung')" style="margin:0 4px;padding:2px 8px;border-radius:4px;border:1px solid var(--border);background:var(--bg-raised);cursor:pointer;font-size:11px">&#x26a0; Warnung</button>
      <button onclick="showToast('Info: Mail-Monitor gestartet','info')" style="margin:0 4px;padding:2px 8px;border-radius:4px;border:1px solid var(--border);background:var(--bg-raised);cursor:pointer;font-size:11px">&#x2139; Info</button>
    </div>
  </div>

  <div class="es-save-bar">
    <button class="es-btn es-btn-pri" onclick="saveSettings()">Speichern</button>
  </div>
</div>

<!-- ── SECTION: AUFGABENLOGIK ──────────────────────────────────────────── -->
<div class="es-sec-panel" id="es-sec-aufgaben">
  <div class="es-sec-h">Aufgabenlogik</div>
  <div class="es-sec-sub">Steuerung der automatischen Aufgabenerstellung, Erinnerungen und Fristen.</div>

  <div class="es-grp">
    <div class="es-grp-h">Erinnerungen &amp; Fristen</div>
    <div class="es-row">
      <div class="es-rl">Erinnerungs-Vorlauf (Stunden)<div class="es-rd">Wie viele Stunden vor Deadline Kira erinnert</div></div>
      <input class="es-inp-sm" type="number" id="cfg-erinnerung-h" value="{aufg.get('erinnerung_intervall_stunden', 24)}" min="1" max="168">
    </div>
    <div class="es-row">
      <div class="es-rl">Deadline-Warnung (Tage vorher)<div class="es-rd">Ab wie vielen Tagen vor Fälligkeit Push/Toast erscheint</div></div>
      <input class="es-inp-sm" type="number" id="cfg-deadline-warnung-tage" value="{aufg.get('deadline_warnung_tage', 1)}" min="0" max="14">
    </div>
    <div class="es-row">
      <div class="es-rl">Erinnerungs-Typ<div class="es-rd">Wie wird erinnert</div></div>
      <select class="es-sel" id="cfg-erinnerung-typ">
        <option value="push" {'selected' if aufg.get('erinnerung_typ','push')=='push' else ''}>Push (ntfy)</option>
        <option value="toast" {'selected' if aufg.get('erinnerung_typ','push')=='toast' else ''}>In-App Toast</option>
        <option value="beide" {'selected' if aufg.get('erinnerung_typ','push')=='beide' else ''}>Push + Toast</option>
      </select>
    </div>
    <div class="es-row">
      <div class="es-rl">Unbeantwortete Mails (Tage)<div class="es-rd">Ab wann eine Mail als unbeantwortete gilt</div></div>
      <input class="es-inp-sm" type="number" id="cfg-unanswered-days" value="{aufg.get('unanswered_check_days', 3)}" min="1" max="30">
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">Aufgaben-Defaults</div>
    <div class="es-row">
      <div class="es-rl">Standard-Priorität<div class="es-rd">Priorität bei manuell erstellten Aufgaben</div></div>
      <select class="es-sel" id="cfg-default-prioritaet">
        <option value="normal" {'selected' if aufg.get('default_prioritaet','normal')=='normal' else ''}>Normal</option>
        <option value="hoch" {'selected' if aufg.get('default_prioritaet','normal')=='hoch' else ''}>Hoch</option>
        <option value="kritisch" {'selected' if aufg.get('default_prioritaet','normal')=='kritisch' else ''}>Kritisch</option>
      </select>
    </div>
    <div class="es-row">
      <div class="es-rl">Erledigte auto-archivieren (Tage)<div class="es-rd">Erledigte Aufgaben nach X Tagen ausblenden. 0 = nie</div></div>
      <input class="es-inp-sm" type="number" id="cfg-auto-archiv-tage" value="{aufg.get('auto_archiv_tage', 0)}" min="0" max="365">
    </div>
  </div>

  <div class="es-save-bar">
    <button class="es-btn es-btn-pri" onclick="saveSettings()">Speichern</button>
  </div>
</div>

<!-- ── SECTION: NACHFASS-INTERVALLE ───────────────────────────────────── -->
<div class="es-sec-panel" id="es-sec-nachfass">
  <div class="es-sec-h">Nachfass-Intervalle</div>
  <div class="es-sec-sub">Definiere nach wie vielen Tagen automatisch an Angebote und Anfragen erinnert wird. Kira kann Nachfass-Texte vorschlagen.</div>

  <div class="es-grp">
    <div class="es-grp-h">Nachfass-Steuerung</div>
    <div class="es-row">
      <div class="es-rl">Nachfass aktiv<div class="es-rd">Automatische Erinnerungen f&uuml;r offene Angebote</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-nf-aktiv" {'checked' if nf.get('aktiv', True) else ''}>
        <div class="es-toggle-vis"></div>
      </label>
      <span class="es-badge {'on' if nf.get('aktiv', True) else 'off'}">{'Aktiv' if nf.get('aktiv', True) else 'Inaktiv'}</span>
    </div>
    <div class="es-row">
      <div class="es-rl">Benachrichtigung via<div class="es-rd">Wie wird der Nachfass gemeldet</div></div>
      <select class="es-sel" id="cfg-nf-typ">
        <option value="push" {'selected' if nf.get('benachrichtigung','push')=='push' else ''}>Push (ntfy)</option>
        <option value="toast" {'selected' if nf.get('benachrichtigung','push')=='toast' else ''}>In-App Toast</option>
        <option value="beide" {'selected' if nf.get('benachrichtigung','push')=='beide' else ''}>Push + Toast</option>
        <option value="aufgabe" {'selected' if nf.get('benachrichtigung','push')=='aufgabe' else ''}>Aufgabe erstellen (Kira LLM)</option>
        <option value="alle" {'selected' if nf.get('benachrichtigung','push')=='alle' else ''}>Push + Toast + Aufgabe</option>
      </select>
    </div>
    <div class="es-row">
      <div class="es-rl">Kira schreibt Nachfass-Text<div class="es-rd">Kira schl&auml;gt automatisch einen Nachfass-Mailtext vor (LLM)</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-nf-kira-text" {'checked' if nf.get('kira_nachfass_text', True) else ''}>
        <div class="es-toggle-vis"></div>
      </label>
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">Erinnerungsstufen (Angebote)</div>
    <div class="es-grp-sub">Drei aufeinanderfolgende Stufen bei unbeantworteten Angeboten. Stufe 3 = letzte Erinnerung.</div>
    <div class="es-row">
      <div class="es-rl">Stufe 1 (Tage)<div class="es-rd">Erste Erinnerung nach X Tagen ohne Antwort</div></div>
      <input class="es-inp-sm" type="number" id="cfg-nf-1" value="{nf.get('intervall_1_tage', 7)}" min="1" max="90">
    </div>
    <div class="es-row">
      <div class="es-rl">Stufe 2 (Tage)<div class="es-rd">Zweite Erinnerung nach X Tagen</div></div>
      <input class="es-inp-sm" type="number" id="cfg-nf-2" value="{nf.get('intervall_2_tage', 14)}" min="1" max="90">
    </div>
    <div class="es-row">
      <div class="es-rl">Stufe 3 (Tage)<div class="es-rd">Letzte Erinnerung nach X Tagen</div></div>
      <input class="es-inp-sm" type="number" id="cfg-nf-3" value="{nf.get('intervall_3_tage', 30)}" min="1" max="90">
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">Rechnungs-Nachfass</div>
    <div class="es-row">
      <div class="es-rl">Offene Rechnungen (Tage)<div class="es-rd">Erinnerung bei &uuml;berf&auml;lligen Rechnungen nach X Tagen</div></div>
      <input class="es-inp-sm" type="number" id="cfg-nf-rechnung" value="{nf.get('rechnung_tage', 14)}" min="1" max="60">
    </div>
  </div>

  <div class="es-save-bar">
    <button class="es-btn es-btn-pri" onclick="saveSettings()">Speichern</button>
  </div>
</div>

<!-- ── SECTION: DASHBOARD ─────────────────────────────────────────────── -->
<div class="es-sec-panel" id="es-sec-dashboard">
  <div class="es-sec-h">Dashboard</div>
  <div class="es-sec-sub">Konfiguration der Dashboard-Ansicht, Protokollierung und Server-Einstellungen.</div>

  <div class="es-grp">
    <div class="es-grp-h">Aufgaben-Protokoll</div>
    <div class="es-row">
      <div class="es-rl">Maximale Eintr&auml;ge<div class="es-rd">Wie viele Protokoll-Eintr&auml;ge gespeichert werden</div></div>
      <input class="es-inp-sm" type="number" id="cfg-proto-max" value="{proto.get('max_eintraege', 500)}" min="50" max="5000">
    </div>
    <div class="es-row">
      <div class="es-rl">Eintr&auml;ge nach X Tagen l&ouml;schen<div class="es-rd">Automatisches Ausr&auml;umen alter Eintr&auml;ge</div></div>
      <input class="es-inp-sm" type="number" id="cfg-proto-tage" value="{proto.get('aufbewahrung_tage', 90)}" min="7" max="365">
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">Server-Einstellungen</div>
    <div class="es-grp-sub">Lokaler Webserver f&uuml;r die App-Oberfl&auml;che. &Auml;nderungen am Port erfordern einen Neustart.</div>
    <div class="es-row">
      <div class="es-rl">Port<div class="es-rd">TCP-Port des lokalen Servers (Standard: 8765)</div></div>
      <input class="es-inp-sm" type="number" id="cfg-server-port" value="{srv.get('port', 8765)}" min="1024" max="65535">
    </div>
    <div class="es-row">
      <div class="es-rl">Browser automatisch &ouml;ffnen<div class="es-rd">Browser beim Start der App &ouml;ffnen</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-auto-browser" {'checked' if srv.get('auto_open_browser', True) else ''}>
        <div class="es-toggle-vis"></div>
      </label>
    </div>
  </div>

  <div class="es-save-bar">
    <button class="es-btn es-btn-pri" onclick="saveSettings()">Speichern</button>
  </div>
</div>

<!-- ── SECTION: PROVIDER / KIRA / LLM ────────────────────────────────── -->
<div class="es-sec-panel" id="es-sec-provider">
  <div class="es-sec-h">Kira / LLM / Provider</div>
  <div class="es-sec-sub">KI-Provider, Modelle und Kira-Assistent konfigurieren.</div>

  <div class="es-grp">
    <div class="es-grp-h">Kira Assistent</div>
    <div class="es-grp-sub">Erscheinungsbild und Verhalten des Kira-Launchers.</div>
    <div class="es-row">
      <div class="es-rl">Launcher-Stil<div class="es-rd">A = Minimal · B = Charakter · C = Orb/Tech</div></div>
      <select class="es-sel" id="cfg-kira-variant" onchange="switchKiraVariant(this.value)">
        <option value="A" {'selected' if launcher_variant=='A' else ''}>A — Minimal</option>
        <option value="B" {'selected' if launcher_variant=='B' else ''}>B — Charakter</option>
        <option value="C" {'selected' if launcher_variant=='C' else ''}>C — Orb / Tech</option>
      </select>
    </div>
    <div class="es-row">
      <div class="es-rl">Gr&ouml;&szlig;e (px)<div class="es-rd">Durchmesser des Launcher-Buttons</div></div>
      <input class="es-inp-sm" type="number" id="cfg-kira-size" value="{kira_size}" min="48" max="200" onchange="(function(v){{var el=document.getElementById('kira-fab');if(el){{el.style.width=v+'px';el.style.height=v+'px';}}}})(this.value)">
    </div>
    <div class="es-row">
      <div class="es-rl">Proximity-Radius (0–1)<div class="es-rd">Aktionsbereich f&uuml;r Augen-Tracking (Anteil Bildschirm)</div></div>
      <input class="es-inp-sm" type="number" id="cfg-kira-prox" value="{kira_prox_radius}" min="0.1" max="1.0" step="0.05">
    </div>
    <div class="es-row">
      <div class="es-rl">Bounce-Distanz (px)<div class="es-rd">Abstand f&uuml;r Excited-Animation</div></div>
      <input class="es-inp-sm" type="number" id="cfg-kira-bounce" value="{kira_bounce_dist}" min="50" max="400">
    </div>
    <div class="es-row">
      <div class="es-rl">Bored-Modus<div class="es-rd">Kira reagiert auf lange Inaktivit&auml;t mit Animation</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-kira-idle" {'checked' if kira_idle else ''}>
        <div class="es-toggle-vis"></div>
      </label>
    </div>
    <div class="es-row">
      <div class="es-rl">Wartezeit Bored-Modus (Sek.)<div class="es-rd">Nach wie vielen Sekunden Bored-Animation startet</div></div>
      <select class="es-sel" id="cfg-kira-idle-delay">
        <option value="10" {'selected' if kira_idle_delay==10 else ''}>10 Sekunden</option>
        <option value="30" {'selected' if kira_idle_delay==30 else ''}>30 Sekunden</option>
        <option value="60" {'selected' if kira_idle_delay==60 else ''}>1 Minute</option>
        <option value="120" {'selected' if kira_idle_delay==120 else ''}>2 Minuten</option>
        <option value="300" {'selected' if kira_idle_delay==300 else ''}>5 Minuten</option>
      </select>
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">KI-Provider</div>
    <div class="es-grp-sub">Verbundene Sprachmodell-Provider. Der erste aktive Provider mit g&uuml;ltigem API-Key wird verwendet.</div>
    <div id="provider-list">
      {provider_cards}
    </div>
    <div style="margin-top:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <select class="es-sel" id="add-provider-typ" style="min-width:160px">
        {add_type_options}
      </select>
      <input class="es-inp-sm" type="text" id="add-provider-name" placeholder="Name (optional)" style="width:140px">
      <button class="es-btn es-btn-green" onclick="addProvider()">+ Provider hinzuf&uuml;gen</button>
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">LLM-Kontext</div>
    <div class="es-grp-sub">Welche Kontextdaten Kira in jede Anfrage einbettet.</div>
    <div class="es-row">
      <div class="es-rl">Internet-Kontext<div class="es-rd">Kira darf externe Informationen einbeziehen</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-llm-internet" {'checked' if llm.get('internet_recherche', False) else ''}>
        <div class="es-toggle-vis"></div>
      </label>
    </div>
    <div class="es-row">
      <div class="es-rl">Gesch&auml;fts-Kontext<div class="es-rd">Firmendaten in Kira-Prompts einbetten</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-llm-geschaeft" {'checked' if llm.get('geschaeftsdaten_teilen', True) else ''}>
        <div class="es-toggle-vis"></div>
      </label>
    </div>
    <div class="es-row">
      <div class="es-rl">Konversations-Kontext<div class="es-rd">Verlauf der letzten Nachrichten einbeziehen</div></div>
      <label class="es-toggle-wrap">
        <input class="es-toggle-inp" type="checkbox" id="cfg-llm-konv" {'checked' if llm.get('konversationen_speichern', True) else ''}>
        <div class="es-toggle-vis"></div>
      </label>
    </div>
  </div>

  <div class="es-grp">
    <div class="es-grp-h">Mail-Klassifizierung (Budget-Modell)</div>
    <div class="es-grp-sub">Eingehende Mails werden automatisch mit einem g&uuml;nstigeren Modell klassifiziert &mdash; nicht mit dem Chat-Modell. Das spart bis zu 10&times; Kosten.</div>
    <div style="overflow-x:auto;margin-bottom:12px">
      <table style="width:100%;border-collapse:collapse;font-size:11px">
        <thead>
          <tr style="background:var(--bg-overlay)">
            <th style="padding:6px 10px;text-align:left;border-bottom:1px solid var(--border)">Modell</th>
            <th style="padding:6px 10px;text-align:center;border-bottom:1px solid var(--border)">Kosten (Input)</th>
            <th style="padding:6px 10px;text-align:center;border-bottom:1px solid var(--border)">Qualit&auml;t</th>
            <th style="padding:6px 10px;text-align:center;border-bottom:1px solid var(--border)">Empfehlung</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style="padding:5px 10px;border-bottom:1px solid var(--border)"><strong>Claude Haiku 4.5</strong></td>
            <td style="padding:5px 10px;text-align:center;border-bottom:1px solid var(--border);color:var(--success,#3dae6a)">~0.80&thinsp;$/1M</td>
            <td style="padding:5px 10px;text-align:center;border-bottom:1px solid var(--border)">Sehr gut f&uuml;r Klassifizierung</td>
            <td style="padding:5px 10px;text-align:center;border-bottom:1px solid var(--border)"><span class="es-badge on">Anthropic &#x2713;</span></td>
          </tr>
          <tr>
            <td style="padding:5px 10px;border-bottom:1px solid var(--border)"><strong>Claude Sonnet 4.5</strong></td>
            <td style="padding:5px 10px;text-align:center;border-bottom:1px solid var(--border);color:var(--warning,#e6a817)">~3.00&thinsp;$/1M</td>
            <td style="padding:5px 10px;text-align:center;border-bottom:1px solid var(--border)">Exzellent</td>
            <td style="padding:5px 10px;text-align:center;border-bottom:1px solid var(--border)"><span style="font-size:10px;color:var(--muted)">5&ndash;10&times; teurer</span></td>
          </tr>
          <tr>
            <td style="padding:5px 10px;border-bottom:1px solid var(--border)"><strong>GPT-4o-mini</strong></td>
            <td style="padding:5px 10px;text-align:center;border-bottom:1px solid var(--border);color:var(--success,#3dae6a)">~0.15&thinsp;$/1M</td>
            <td style="padding:5px 10px;text-align:center;border-bottom:1px solid var(--border)">Gut f&uuml;r Klassifizierung</td>
            <td style="padding:5px 10px;text-align:center;border-bottom:1px solid var(--border)"><span class="es-badge on">OpenAI &#x2713;</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="es-row">
      <div class="es-rl">Aktives Klassifizierungs-Modell<div class="es-rd">Wird derzeit f&uuml;r Mail-Klassifizierung verwendet</div></div>
      <span style="font-size:var(--fs-xs);color:var(--success,#3dae6a);font-weight:700">&#x2713; {esc(active_budget_model)}</span>
    </div>
    <div class="es-row">
      <div class="es-rl">Modell-Auswahl<div class="es-rd">Kira w&auml;hlt automatisch das g&uuml;nstigste Modell je Provider-Typ</div></div>
      <span style="font-size:var(--fs-xs);color:var(--muted)">Auto-Budget &mdash; <span style="color:var(--text-secondary)">Admin-Konfiguration folgt mit Rollen-System</span></span>
    </div>
  </div>

  <div class="es-save-bar">
    <button class="es-btn es-btn-pri" onclick="saveSettings()">Speichern</button>
  </div>
</div>

<!-- ── SECTION: MAIL & KONTEN ─────────────────────────────────────────── -->
<div class="es-sec-panel" id="es-sec-mail">
  <div class="es-sec-h">Mail &amp; Konten</div>

  <style>
  /* ── Mail-Tab-Bar ── */
  .es-mail-tabs{{display:flex;gap:0;border-bottom:1px solid var(--border);margin-bottom:20px;overflow-x:auto;flex-shrink:0}}
  .es-mail-tab{{padding:8px 18px;font-size:12px;font-weight:600;color:var(--text-muted);cursor:pointer;border:none;background:none;border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap;transition:color .14s,border-color .14s;letter-spacing:.01em}}
  .es-mail-tab:hover{{color:var(--text)}}
  .es-mail-tab.act{{color:var(--accent,#1a73e8);border-bottom-color:var(--accent,#1a73e8)}}
  [data-theme="light"] .es-mail-tab.act{{color:#1a73e8;border-bottom-color:#1a73e8}}
  .es-mail-panel{{display:none}}
  .es-mail-panel.act{{display:block}}
  /* ── Konto-Karten ── */
  .es-mk-card{{border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin-bottom:12px;background:var(--bg-raised)}}
  .es-mk-card-head{{display:flex;align-items:center;gap:10px;margin-bottom:10px}}
  .es-mk-radio{{cursor:pointer;margin-right:4px;accent-color:var(--accent)}}
  .es-mk-ico{{font-size:20px;flex-shrink:0}}
  .es-mk-body{{flex:1;min-width:0}}
  .es-mk-email{{font-size:13px;font-weight:600;color:var(--text)}}
  .es-mk-desc{{font-size:12px;color:var(--text-muted)}}
  .es-mk-status{{font-size:11px;padding:2px 9px;border-radius:10px;font-weight:600;flex-shrink:0}}
  .es-mk-ok{{background:rgba(40,200,80,.15);color:#28c850}}
  .es-mk-expired{{background:rgba(255,160,0,.15);color:#f0a000}}
  .es-mk-missing{{background:rgba(200,60,60,.12);color:#c83c3c}}
  /* ── Stats-Zeile ── */
  .es-mk-stats{{display:flex;gap:16px;padding:8px 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin:8px 0;flex-wrap:wrap}}
  .es-mk-stat{{flex:1;min-width:100px}}
  .es-mk-stat-val{{font-size:22px;font-weight:700;color:var(--accent)}}
  .es-mk-stat-lbl{{font-size:11px;color:var(--text-muted)}}
  .es-mk-stat-sub{{font-size:11px;color:var(--text-muted);margin-top:2px}}
  /* ── Button-Gruppen ── */
  .es-mk-actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}}
  .es-mk-btn{{background:var(--accent);color:#fff;border:none;border-radius:6px;padding:5px 12px;font-size:12px;cursor:pointer;font-weight:600}}
  .es-mk-btn:hover{{opacity:.85}}
  .es-mk-btn.sec{{background:var(--bg-card);color:var(--text);border:1px solid var(--border)}}
  .es-mk-btn.danger{{background:rgba(200,60,60,.15);color:#c84444;border:1px solid rgba(200,60,60,.3)}}
  .es-mk-btn.warn{{background:rgba(255,140,0,.15);color:#e07800;border:1px solid rgba(255,140,0,.35)}}
  .es-mk-btn:disabled{{opacity:.5;cursor:default}}
  .es-mk-card-deaktiv{{opacity:.75;border-color:var(--border);border-style:dashed}}
  .es-mk-deaktiv-banner{{background:rgba(150,150,150,.12);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:11px;color:var(--text-muted);margin-bottom:10px}}
  /* ── Ampel ── */
  .es-mk-ampel{{font-size:18px;flex-shrink:0;cursor:help}}
  .es-mk-ampel-gruen{{color:#28c850}}
  .es-mk-ampel-gelb{{color:#f0a000}}
  .es-mk-ampel-rot{{color:#c83c3c}}
  /* ── Konto-Wizard ── */
  .kira-wiz-overlay{{position:fixed;inset:0;background:rgba(0,0,0,.72);z-index:9999;display:flex;align-items:center;justify-content:center}}
  .kira-wiz-box{{background:var(--bg-card,#ffffff);border-radius:20px;width:600px;max-width:96vw;box-shadow:0 20px 80px rgba(0,0,0,.45);overflow:hidden;border:1px solid var(--border);isolation:isolate;position:relative}}
  [data-theme="dark"] .kira-wiz-box{{background:#1e1e2e}}
  [data-theme="light"] .kira-wiz-box,.kira-wiz-box{{background-color:#ffffff}}
  .kira-wiz-step{{padding:52px 60px;text-align:center}}
  .kira-wiz-dots{{display:flex;justify-content:center;gap:10px;margin-bottom:40px}}
  .kira-wiz-dot{{width:9px;height:9px;border-radius:50%;background:var(--border);transition:background .3s}}
  .kira-wiz-dot.active{{background:var(--accent)}}
  .kira-wiz-title{{font-size:28px;font-weight:700;color:var(--text);margin:0 0 12px;letter-spacing:-.3px}}
  .kira-wiz-sub{{font-size:15px;color:var(--text-muted);margin:0 0 36px;line-height:1.6;max-width:400px;margin-left:auto;margin-right:auto}}
  .kira-wiz-fields{{text-align:left;margin-bottom:32px;max-width:360px;margin-left:auto;margin-right:auto}}
  .kira-wiz-field{{margin-bottom:20px}}
  .kira-wiz-field label{{display:block;font-size:11px;font-weight:700;color:var(--text-muted);margin-bottom:7px;text-transform:uppercase;letter-spacing:.08em}}
  .kira-wiz-field input,.kira-wiz-field select{{width:100%;box-sizing:border-box;padding:13px 16px;border:1.5px solid var(--border);border-radius:10px;background:var(--bg);color:var(--text);font-size:15px;transition:border-color .2s}}
  .kira-wiz-field input[readonly]{{opacity:.65;cursor:default}}
  .kira-wiz-field input:focus,.kira-wiz-field select:focus{{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(99,102,241,.12)}}
  .kira-wiz-btns{{display:flex;align-items:center;justify-content:space-between;margin-top:12px;padding-top:24px;border-top:1px solid var(--border)}}
  .kira-wiz-btns-right{{display:flex;gap:10px}}
  .kira-wiz-link{{font-size:13px;color:var(--accent);text-decoration:none;display:inline-block;margin-top:10px}}
  .kira-wiz-link:hover{{text-decoration:underline}}
  .kira-wiz-import-link{{font-size:13px;color:var(--accent);cursor:pointer;border:none;background:none;padding:0;margin-top:6px;text-align:center;width:100%}}
  .kira-wiz-found-box{{display:flex;align-items:center;gap:18px;background:var(--bg-raised);border-radius:14px;padding:20px 24px;margin:0 auto 8px;max-width:380px;text-align:left;border:1px solid var(--border)}}
  .kira-wiz-found-ico{{font-size:32px;flex-shrink:0}}
  .kira-wiz-found-name{{font-size:16px;font-weight:700;color:var(--text)}}
  .kira-wiz-found-detail{{font-size:13px;color:var(--text-muted);margin-top:4px}}
  .kira-wiz-loading-area{{padding:20px 0 8px}}
  .kira-wiz-spinner{{width:56px;height:56px;border:4px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:kira-spin .85s linear infinite;margin:0 auto 20px}}
  .kira-wiz-success-icon{{font-size:56px;margin-bottom:16px}}
  @keyframes kira-spin{{to{{transform:rotate(360deg)}}}}
  .kira-wiz-btn-primary{{background:var(--accent);color:#fff;border:none;border-radius:9px;padding:11px 28px;font-size:14px;font-weight:700;cursor:pointer;transition:opacity .2s}}
  .kira-wiz-btn-primary:hover{{opacity:.88}}
  .kira-wiz-btn-sec{{background:transparent;color:var(--text-muted);border:1.5px solid var(--border);border-radius:9px;padding:10px 22px;font-size:14px;font-weight:600;cursor:pointer;transition:all .2s}}
  .kira-wiz-btn-sec:hover{{border-color:var(--accent);color:var(--text)}}
  .kira-wiz-import-card{{display:flex;align-items:center;gap:14px;background:var(--bg-raised);border:1.5px dashed var(--border);border-radius:12px;padding:16px 20px;margin-top:12px;cursor:pointer;transition:border-color .2s;text-align:left}}
  .kira-wiz-import-card:hover{{border-color:var(--accent)}}
  .kira-wiz-step-label{{font-size:11px;color:var(--text-muted);font-weight:600;letter-spacing:.08em;text-transform:uppercase;margin-bottom:32px}}
  /* ── Gesamt-Header ── */
  .es-mk-total{{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:var(--bg-card);border-radius:8px;margin-bottom:16px;flex-wrap:wrap;gap:8px}}
  .es-mk-total-info{{font-size:13px;color:var(--text-muted)}}
  .es-mk-total-info strong{{color:var(--text)}}
  /* ── Dialog ── */
  .es-mk-dialog-overlay{{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:center;justify-content:center}}
  .es-mk-dialog{{background:var(--bg-card);border-radius:12px;padding:24px;width:460px;max-width:95vw;max-height:80vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.4)}}
  .es-mk-dialog h3{{margin:0 0 16px;font-size:15px}}
  .es-mk-dialog-row{{margin-bottom:12px}}
  .es-mk-dialog-row label{{display:block;font-size:12px;color:var(--text-muted);margin-bottom:4px}}
  .es-mk-dialog-row input,.es-mk-dialog-row select{{width:100%;box-sizing:border-box;background:var(--bg-input,var(--bg-raised));border:1px solid var(--border);border-radius:6px;padding:7px 10px;font-size:13px;color:var(--text)}}
  .es-mk-dialog-btns{{display:flex;gap:8px;justify-content:flex-end;margin-top:16px}}
  /* ── KIRA-Ordner Akkordeon ── */
  .es-kira-ord-toggle{{cursor:pointer;font-size:12px;color:var(--accent);margin-top:6px;display:inline-block}}
  .es-kira-ord-list{{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px}}
  .es-kira-ord-chip{{display:flex;align-items:center;gap:4px;font-size:12px;padding:3px 8px;border-radius:6px;background:var(--bg-raised);border:1px solid var(--border);cursor:pointer}}
  .es-kira-ord-chip.active{{background:rgba(79,125,249,.15);border-color:var(--accent);color:var(--accent)}}
  /* ── Signaturen-Tab ── */
  .es-sig-list{{margin-top:4px}}
  .es-sig-item{{display:flex;align-items:center;gap:10px;padding:10px 14px;border:1px solid var(--border);border-radius:8px;margin-bottom:8px;background:var(--bg-raised);transition:border-color .14s}}
  .es-sig-item:hover{{border-color:var(--accent)}}
  .es-sig-name{{flex:1;font-size:13px;font-weight:600;color:var(--text)}}
  .es-sig-konto{{font-size:11px;color:var(--text-muted);margin-top:2px}}
  .es-sig-default-badge{{font-size:10px;padding:2px 7px;border-radius:10px;background:rgba(79,125,249,.15);color:var(--accent);font-weight:600;flex-shrink:0}}
  .es-sig-actions{{display:flex;gap:6px;flex-shrink:0}}
  .es-sig-empty{{padding:20px;text-align:center;color:var(--text-muted);font-size:13px;background:var(--bg-raised);border-radius:8px;border:1px dashed var(--border)}}
  /* Signatur-Editor-Modal */
  .es-sig-modal-overlay{{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9998;display:flex;align-items:center;justify-content:center;padding:16px}}
  .es-sig-modal{{background:var(--bg-card);border-radius:14px;width:760px;max-width:96vw;max-height:90vh;display:flex;flex-direction:column;box-shadow:0 20px 80px rgba(0,0,0,.45);border:1px solid var(--border)}}
  .es-sig-modal-head{{display:flex;align-items:center;justify-content:space-between;padding:18px 22px 14px;border-bottom:1px solid var(--border)}}
  .es-sig-modal-title{{font-size:15px;font-weight:700;color:var(--text)}}
  .es-sig-modal-body{{flex:1;overflow-y:auto;padding:16px 22px}}
  .es-sig-modal-foot{{display:flex;justify-content:flex-end;gap:8px;padding:14px 22px;border-top:1px solid var(--border)}}
  .es-sig-field{{margin-bottom:14px}}
  .es-sig-field label{{display:block;font-size:11px;font-weight:700;color:var(--text-muted);margin-bottom:5px;text-transform:uppercase;letter-spacing:.06em}}
  .es-sig-field input,.es-sig-field select{{width:100%;box-sizing:border-box;background:var(--bg-input,var(--bg-raised));border:1px solid var(--border);border-radius:7px;padding:8px 11px;font-size:13px;color:var(--text)}}
  .es-sig-field input:focus,.es-sig-field select:focus{{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(99,102,241,.12)}}
  #es-sig-quill-wrap .ql-toolbar{{background:var(--bg-raised);border-color:var(--border);border-radius:7px 7px 0 0}}
  #es-sig-quill-wrap .ql-container{{background:var(--bg);border-color:var(--border);border-radius:0 0 7px 7px;min-height:200px;font-size:13px;color:var(--text)}}
  </style>

  <!-- Tab-Leiste -->
  <div class="es-mail-tabs" id="es-mail-tabs">
    <button class="es-mail-tab act" data-tab="mailkonten" onclick="esMailTab('mailkonten',this)">Mailkonten</button>
    <button class="es-mail-tab" data-tab="monitor" onclick="esMailTab('monitor',this)">Mail-Monitor</button>
    <button class="es-mail-tab" data-tab="klassifizierung" onclick="esMailTab('klassifizierung',this)">Klassifizierung</button>
    <button class="es-mail-tab" data-tab="signaturen" onclick="esMailTab('signaturen',this)">Signaturen</button>
    <button class="es-mail-tab" data-tab="archiv" onclick="esMailTab('archiv',this)">Archiv</button>
    <button class="es-mail-tab" data-tab="sync" onclick="esMailTab('sync',this)">Sync &amp; Kira-Zugang</button>
  </div>

  <!-- ── TAB: MAILKONTEN ── -->
  <div class="es-mail-panel act" id="es-mtp-mailkonten">
    <!-- Gesamt-Stats + Alle-Aktionen -->
    <div class="es-mk-total" id="es-mk-total">
      <div class="es-mk-total-info"><strong id="es-mk-total-cnt">–</strong> Mails im Index</div>
      <div style="display:flex;gap:8px">
        <button class="es-mk-btn sec" onclick="esMkAlleAbrufen(this)">&#x25BA; Alle abrufen</button>
        <button class="es-mk-btn sec" onclick="esMkAlleTest()">&#x26A1; Alle testen</button>
      </div>
    </div>
    <!-- Konto-Liste -->
    <div id="es-mail-konten-list"><div style="padding:12px;color:var(--text-muted);font-size:13px">Lade Konten...</div></div>
    <button class="es-mk-btn" style="margin-top:8px" onclick="esMkWizardOpen()">+ Konto hinzuf&uuml;gen</button>
  </div>

  <!-- ── TAB: MAIL-MONITOR ── -->
  <div class="es-mail-panel" id="es-mtp-monitor">
  <!-- Mail-Monitor -->
  <div class="es-grp" style="margin-top:0">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
      <div class="es-grp-h" style="margin-bottom:0">Mail-Monitor</div>
      <div id="es-mail-monitor-badge"></div>
    </div>
    <div class="es-grp-sub">Automatisches IMAP-Polling l&auml;uft im Hintergrund und benachrichtigt KIRA bei neuen Mails.</div>
    <div class="es-row">
      <div class="es-row-label"><span>Mail-Monitor aktiv</span><span class="es-row-hint">Eingehende Mails werden automatisch gepr&uuml;ft und als Aufgaben eingetragen</span></div>
      <label class="es-toggle-wrap"><input class="es-toggle-inp" type="checkbox" id="cfg-mail-monitor-aktiv"><div class="es-toggle-vis"></div></label>
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>Abruf-Intervall</span><span class="es-row-hint">Wie h&auml;ufig neue Mails per IMAP abgerufen werden</span></div>
      <select id="cfg-mail-intervall" style="background:var(--bg-input,var(--bg-raised));border:1px solid var(--border);border-radius:6px;padding:5px 10px;font-size:13px;color:var(--text);cursor:pointer">
        <option value="2">2 Minuten</option>
        <option value="5" selected>5 Minuten</option>
        <option value="10">10 Minuten</option>
        <option value="15">15 Minuten</option>
        <option value="30">30 Minuten</option>
        <option value="60">60 Minuten</option>
      </select>
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>Postfach-Aktualisierung</span><span class="es-row-hint">Wann der Ungelesen-Z&auml;hler im Postfach aktualisiert wird</span></div>
      <select id="cfg-postfach-refresh" style="background:var(--bg-input,var(--bg-raised));border:1px solid var(--border);border-radius:6px;padding:5px 10px;font-size:13px;color:var(--text);cursor:pointer">
        <option value="0">Bei Abruf (Standard)</option>
        <option value="2">alle 2 Minuten</option>
        <option value="5">alle 5 Minuten</option>
        <option value="10">alle 10 Minuten</option>
        <option value="30">alle 30 Minuten</option>
      </select>
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>Als gelesen markieren</span><span class="es-row-hint">Wann eine ge&ouml;ffnete Mail automatisch als gelesen gilt</span></div>
      <select id="cfg-lese-markierung" style="background:var(--bg-input,var(--bg-raised));border:1px solid var(--border);border-radius:6px;padding:5px 10px;font-size:13px;color:var(--text);cursor:pointer">
        <option value="sofort">Sofort beim &Ouml;ffnen</option>
        <option value="1s">Nach 1 Sekunde</option>
        <option value="3s">Nach 3 Sekunden</option>
        <option value="5s">Nach 5 Sekunden</option>
        <option value="10s">Nach 10 Sekunden</option>
        <option value="30s">Nach 30 Sekunden</option>
        <option value="60s">Nach 1 Minute</option>
        <option value="2min">Nach 2 Minuten</option>
        <option value="5min">Nach 5 Minuten</option>
        <option value="manuell">Nur manuell (nur per Klick)</option>
      </select>
    </div>
    <div class="es-row" style="border-bottom:none">
      <div class="es-row-label">
        <span>Letzter Abruf</span>
        <span id="es-mail-monitor-status" class="es-row-hint">–</span>
      </div>
      <button class="es-mk-btn sec" style="font-size:11px;padding:4px 10px" onclick="esMailMonitorNow(this)">&#x25BA; Jetzt abrufen</button>
    </div>
  </div>
  </div><!-- /es-mtp-monitor -->

  <!-- ── TAB: MAIL-KLASSIFIZIERUNG ── -->
  <div class="es-mail-panel" id="es-mtp-klassifizierung">
  <!-- Mail-Klassifizierung -->
  <div class="es-grp" style="margin-top:0">
    <div class="es-grp-h">Mail-Klassifizierung</div>
    <div class="es-grp-sub">KI-basierte Kategorisierung eingehender Mails mit LLM.</div>
    <div class="es-row">
      <div class="es-row-label"><span>Klassifizierung (LLM)</span><span class="es-row-hint">Eingehende Mails automatisch kategorisieren (Anfrage / Newsletter / intern / etc.)</span></div>
      <label class="es-toggle-wrap"><input class="es-toggle-inp" type="checkbox" id="cfg-mail-classify"><div class="es-toggle-vis"></div></label>
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>Aufgaben automatisch erstellen</span><span class="es-row-hint">Aus Anfragen und wichtigen Mails direkt Aufgaben generieren</span></div>
      <label class="es-toggle-wrap"><input class="es-toggle-inp" type="checkbox" id="cfg-mail-tasks"><div class="es-toggle-vis"></div></label>
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>Newsletter ignorieren</span><span class="es-row-hint">Newsletter-Mails werden nicht als Aufgaben eingetragen</span></div>
      <label class="es-toggle-wrap"><input class="es-toggle-inp" type="checkbox" id="cfg-mail-ignore-newsletter"><div class="es-toggle-vis"></div></label>
    </div>
    <div class="es-row" style="border-bottom:none">
      <div class="es-row-label">
        <span>&#x21BA; Mails nachklassifizieren</span>
        <span class="es-row-hint">Nicht klassifizierte Mails aus dem Index r&uuml;ckwirkend verarbeiten und Tasks anlegen</span>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input type="date" id="es-recheck-seit"
               style="background:var(--bg-input,var(--bg-raised));border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:12px;color:var(--text)">
        <button class="es-mk-btn sec" id="btn-mail-recheck"
                onclick="esMailNachklassifizieren(this)">&#x21BA; Nachklassifizieren</button>
      </div>
    </div>
    <div id="es-recheck-progress" style="font-size:12px;color:var(--text-muted);padding:2px 0 6px 4px;min-height:16px"></div>
  </div>
  </div><!-- /es-mtp-klassifizierung -->

  <!-- ── TAB: SIGNATUREN ── -->
  <div class="es-mail-panel" id="es-mtp-signaturen">
    <div class="es-grp" style="margin-top:0">
      <div class="es-grp-h">E-Mail-Signaturen</div>
      <div class="es-grp-sub">Erstelle mehrere Signaturen pro Konto. Beim Verfassen wird die Standard-Signatur automatisch eingef&uuml;gt.</div>
      <div style="display:flex;justify-content:flex-end;margin-bottom:12px">
        <button class="es-mk-btn" onclick="esSigNeu()">+ Neue Signatur</button>
      </div>
      <div class="es-sig-list" id="es-sig-list">
        <div class="es-sig-empty">Signaturen werden geladen&hellip;</div>
      </div>
    </div>
  </div><!-- /es-mtp-signaturen -->

  <!-- ── TAB: ARCHIV ── -->
  <div class="es-mail-panel" id="es-mtp-archiv">
  <!-- Archiv-Ordner -->
  <div class="es-grp" style="margin-top:0">
    <div class="es-grp-h">&#x1F4C1; Mail-Archiv-Ordner <span style="color:#e06060;font-size:11px;font-weight:400">PFLICHT</span></div>
    <div class="es-grp-sub">KIRA ben&ouml;tigt ein lokales Archiv f&uuml;r vollst&auml;ndigen LLM-Kontext. Das Archiv ist deine exportierbare Datenbasis.</div>
    <div class="es-row">
      <div class="es-row-label"><span>Archiv-Ordner</span><span class="es-row-hint">Lokaler Pfad zum Mail-Archiv-Verzeichnis</span></div>
      <div style="display:flex;gap:6px;flex:1;max-width:460px">
        <input type="text" id="cfg-archiv-pfad" placeholder="C:/Pfad/zum/Mail Archiv/Archiv" style="flex:1;background:var(--bg-input,var(--bg-raised));border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:13px;color:var(--text)">
        <button class="es-mk-btn sec" onclick="esArchivOrdnerWaehlen(this)" style="white-space:nowrap" title="Ordner im Explorer ausw&auml;hlen">&#x1F4C2;</button>
        <button class="es-mk-btn sec" onclick="esMkArchivPruefen()" style="white-space:nowrap">&#x2713; Pr&uuml;fen</button>
      </div>
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>Neue Mails archivieren</span><span class="es-row-hint">Eingehende Mails automatisch als JSON+EML im Archiv speichern</span></div>
      <label class="es-toggle-wrap"><input class="es-toggle-inp" type="checkbox" id="cfg-archiv-aktiv"><div class="es-toggle-vis"></div></label>
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>Gel&ouml;schte Elemente bereinigen</span><span class="es-row-hint">EML + Anh&auml;nge nach Frist l&ouml;schen — Kurzprotokoll (Absender, Betreff, 300 Zeichen) bleibt dauerhaft</span></div>
      <label class="es-toggle-wrap"><input class="es-toggle-inp" type="checkbox" id="cfg-archiv-bereinigung-aktiv" {'checked' if bereinigung_aktiv else ''}><div class="es-toggle-vis"></div></label>
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>Bereinigungsfrist (Tage)</span><span class="es-row-hint">Gel&ouml;schte Mails im Archiv werden nach dieser Frist bereinigt (Standard: 90 Tage)</span></div>
      <input type="number" id="cfg-archiv-bereinigung-frist" value="{bereinigung_frist}" min="7" max="3650" style="width:80px;background:var(--bg-input,var(--bg-raised));border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:13px;color:var(--text);text-align:right">
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>Archiv-Status</span><span id="es-archiv-status-text" class="es-row-hint">–</span></div>
      <div style="display:flex;gap:8px;align-items:center">
        <div id="es-archiv-status-badge"></div>
        <button class="es-mk-btn sec" id="btn-archiv-reindex" onclick="esReindex(this)">Re-Index starten</button>
      </div>
    </div>
    <div id="es-reindex-progress" style="font-size:12px;color:var(--text-muted);margin-top:4px"></div>
  </div>
  </div><!-- /es-mtp-archiv -->

  <!-- ── TAB: SYNC & KIRA-ZUGANG ── -->
  <div class="es-mail-panel" id="es-mtp-sync">
  <!-- Sync-Ordner + KIRA-Zugang -->
  <div class="es-grp" style="margin-top:0">
    <div class="es-grp-h">Sync-Ordner &amp; KIRA-Zugang</div>
    <div class="es-grp-sub">Welche IMAP-Ordner &uuml;berwacht werden. KIRA LLM-Zugang: KIRA kann diese Ordner lesen und f&uuml;r Antworten nutzen.</div>
    <div id="es-sync-ordner-list"><div style="padding:8px;color:var(--text-muted);font-size:12px">Wird geladen...</div></div>
  </div>
  </div><!-- /es-mtp-sync -->

  <script>
  // ── Mail-Konten laden ──────────────────────────────────────────────────────
  function esRefreshAmpeln() {{
    fetch('/api/mail/konto/health').then(r=>r.json()).then(healthData=>{{
      const health=healthData.health||{{}};
      Object.entries(health).forEach(([email,h])=>{{
        const safe=email.replace(/[@.]/g,'_');
        const dot=document.getElementById('es-ampel-'+safe);
        if(dot) {{
          if(h.status==='ok') {{dot.className='es-mk-ampel es-mk-ampel-gruen';dot.title='Verbunden ('+new Date(h.last_check||0).toLocaleTimeString()+')';}}
          else if(h.status==='auth_fehler') {{dot.className='es-mk-ampel es-mk-ampel-rot';dot.title='Authentifizierung fehlgeschlagen';}}
          else {{dot.className='es-mk-ampel es-mk-ampel-gelb';dot.title='Verbindungsfehler';}}
        }}
        const liveEl=document.getElementById('es-mk-live-'+safe);
        const liveWrap=document.getElementById('es-mk-live-wrap-'+safe);
        if(liveEl&&liveWrap) {{
          if(h.status==='ok'&&h.inbox_count!=null) {{liveEl.textContent=h.inbox_count.toLocaleString();liveWrap.style.display='';}}
          else liveWrap.style.display='none';
        }}
        const reconWrap=document.getElementById('es-mk-recon-'+safe);
        if(reconWrap) reconWrap.style.display=h.status==='ok'?'none':'';
      }});
    }}).catch(()=>{{}});
  }}
  window.esMkVolltest = function(email, btn) {{
    if(btn){{btn.disabled=true;btn.textContent='Teste\u2026';}}
    fetch('/api/mail/konto/volltest',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email}})}})
    .then(r=>r.json()).then(d=>{{
      if(!d.ok){{showToast('Fehler: '+(d.error||'?'),'fehler');if(btn){{btn.disabled=false;btn.textContent='\u26A1 Verbindung testen';}}return;}}
      const jobId=d.job_id;
      showToast('Volltest gestartet (IMAP + SMTP + Roundtrip) \u2014 ca. 45s\u2026','info');
      let polls=0;
      const timer=setInterval(()=>{{
        polls++;
        fetch('/api/mail/konto/volltest-status?job_id='+jobId).then(r=>r.json()).then(s=>{{
          if(s.status==='done'){{
            clearInterval(timer);
            if(btn){{btn.disabled=false;btn.textContent='\u26A1 Verbindung testen';}}
            const r=s.result||{{}};
            const lines=[];
            if(r.imap_ok) lines.push('\u2713 IMAP: '+r.inbox_count+' Mails');
            else lines.push('\u2717 IMAP: '+(r.imap_error||'Fehler'));
            if(r.smtp_ok) lines.push('\u2713 SMTP: Testmail gesendet');
            else lines.push('\u2717 SMTP: '+(r.smtp_error||'nicht getestet'));
            if(r.roundtrip_ok) lines.push('\u2713 Roundtrip: Testmail empfangen');
            else if(r.smtp_ok) lines.push('\u26A0 Roundtrip: '+(r.roundtrip_error||'nicht verifiziert'));
            showToast(lines.join(' \u2022 '), r.imap_ok?'ok':'fehler');
            esRefreshAmpeln();
          }} else if(s.status==='error'){{
            clearInterval(timer);
            if(btn){{btn.disabled=false;btn.textContent='\u26A1 Verbindung testen';}}
            showToast('Volltest Fehler: '+(s.error||'?'),'fehler');
          }} else if(polls>40){{
            clearInterval(timer);
            if(btn){{btn.disabled=false;btn.textContent='\u26A1 Verbindung testen';}}
            showToast('Timeout beim Volltest','warnung');
          }}
        }}).catch(()=>{{}});
      }},3000);
    }}).catch(()=>{{if(btn){{btn.disabled=false;btn.textContent='\u26A1 Verbindung testen';}}showToast('Fehler','fehler');}});
  }};
  function esLoadMailKonten() {{
    fetch('/api/mail/konten').then(r=>r.json()).then(data=>{{
      const list = document.getElementById('es-mail-konten-list');
      if(!list) return;
      const mon = data.monitor || {{}};
      const mstat = document.getElementById('es-mail-monitor-status');
      const mbadge = document.getElementById('es-mail-monitor-badge');
      // Status: formatierte Zeitanzeige
      if(mstat) {{
        if(mon.last_sync) {{
          try {{
            const d=new Date(mon.last_sync);
            const now=new Date();
            const diffMin=Math.floor((now-d)/60000);
            let txt='';
            if(diffMin<1) txt='gerade eben';
            else if(diffMin<60) txt='vor '+diffMin+' Min.';
            else if(diffMin<1440) txt='heute '+d.toLocaleTimeString('de-DE',{{hour:'2-digit',minute:'2-digit'}})+' Uhr';
            else txt=d.toLocaleDateString('de-DE',{{day:'2-digit',month:'2-digit'}})+' '+d.toLocaleTimeString('de-DE',{{hour:'2-digit',minute:'2-digit'}})+' Uhr';
            mstat.textContent=txt;
          }} catch(e){{ mstat.textContent=mon.last_sync; }}
        }} else mstat.textContent='Noch kein Sync';
      }}
      if(mbadge) mbadge.innerHTML = mon.aktiv
        ? '<span class="es-badge on">&#x25CF; Aktiv</span>'
        : '<span class="es-badge off">&#x25CF; Inaktiv</span>';
      const mmAktiv = document.getElementById('cfg-mail-monitor-aktiv');
      const mmInt = document.getElementById('cfg-mail-intervall');
      if(mmAktiv) mmAktiv.checked = !!mon.aktiv;
      if(mmInt && mon.intervall) {{
        // intervall in Minuten (intern: Sekunden)
        const mins = Math.round(mon.intervall/60);
        const opt = mmInt.querySelector('option[value="'+mins+'"]');
        if(opt) opt.selected=true;
        else mmInt.value = '5';
      }}
      const std = data.standard_konto || '';
      const konten = data.konten || [];
      if(!konten.length) {{ list.innerHTML='<div style="padding:12px;color:var(--text-muted);font-size:13px">Keine Konten konfiguriert.</div>'; return; }}
      // Health-Status laden und Karten rendern
      fetch('/api/mail/konto/health').then(r=>r.json()).then(healthData=>{{
        const health = healthData.health || {{}};
        list.innerHTML = konten.map(k=>{{
          const safe = k.email.replace(/[@.]/g,'_');
          const h = health[k.email] || {{}};
          // Ampel-Badge: bevorzuge echten Health-Status, Fallback auf Token-Status
          let ampel='', ampelClass='', ampelTip='';
          if(h.status==='ok') {{
            ampel='&#x25CF;'; ampelClass='es-mk-ampel-gruen'; ampelTip='Verbindung aktiv ('+new Date(h.last_check||0).toLocaleTimeString()+')';
          }} else if(h.status==='auth_fehler') {{
            ampel='&#x25CF;'; ampelClass='es-mk-ampel-rot'; ampelTip='Authentifizierung fehlgeschlagen: '+(h.error||'');
          }} else if(h.status==='fehler') {{
            ampel='&#x25CF;'; ampelClass='es-mk-ampel-gelb'; ampelTip='Verbindungsfehler: '+(h.error||'');
          }} else if(k.token_status==='ok') {{
            ampel='&#x25CF;'; ampelClass='es-mk-ampel-gelb'; ampelTip='Token vorhanden — noch nicht geprüft';
          }} else {{
            ampel='&#x25CF;'; ampelClass='es-mk-ampel-rot'; ampelTip='Nicht verbunden';
          }}
          // Reconnect bei allem außer ok (auth_fehler, fehler, unbekannt, nie-geprüft)
          const needsReconnect = h.status!=='ok';
          const isDeaktiv = k.aktiv === false;
          return `<div class="es-mk-card${{isDeaktiv?' es-mk-card-deaktiv':''}}" id="es-mk-card-${{safe}}">
            ${{isDeaktiv?'<div class="es-mk-deaktiv-banner">&#x23F8; Deaktiviert &mdash; kein Abruf/Senden &bull; <span style="color:var(--success,#2e9e5b)">&#x2713; Archiv-Zugang aktiv</span></div>':''}}
            <div class="es-mk-card-head">
              ${{!isDeaktiv?`<input type="radio" name="mk-standard" class="es-mk-radio" value="${{k.email}}" ${{k.email===std?'checked':''}} onchange="esMkSetStandard('${{k.email}}')">`:''}}
              <div class="es-mk-ico" style="${{isDeaktiv?'opacity:.4':''}}">&#x2709;</div>
              <div class="es-mk-body">
                <div class="es-mk-email">${{k.email}} ${{k.email===std&&!isDeaktiv?'<span style="font-size:10px;color:#3b82f6;margin-left:6px;font-weight:600">&#x2605; Standard</span>':''}}</div>
                <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
                  <input type="text" id="es-mk-dname-${{safe}}" value="${{k.display_name||''}}" placeholder="Anzeigename (z.B. INFO rauMKult)" style="font-size:11px;padding:3px 7px;border:1px solid var(--border);border-radius:5px;background:var(--bg-input,var(--bg-raised));color:var(--text);width:180px" title="Anzeigename im Postfach">
                  <button style="font-size:10px;padding:2px 7px;border:1px solid var(--border);border-radius:5px;background:var(--bg-raised);color:var(--text);cursor:pointer" onclick="esMkSaveName('${{k.email}}','${{safe}}')">&#x2713;</button>
                </div>
              </div>
              ${{!isDeaktiv?`<span class="es-mk-ampel ${{ampelClass}}" id="es-ampel-${{safe}}" title="${{ampelTip}}">${{ampel}}</span>`:''}}
            </div>
            <div class="es-mk-stats" id="es-mk-stats-${{safe}}">
              <div class="es-mk-stat"><div class="es-mk-stat-val" id="es-mk-idx-${{safe}}">–</div><div class="es-mk-stat-lbl">Im Index</div></div>
              <div class="es-mk-stat"><div class="es-mk-stat-val" id="es-mk-arc-${{safe}}">–</div><div class="es-mk-stat-lbl">Archiviert</div></div>
              <div class="es-mk-stat" id="es-mk-live-wrap-${{safe}}" style="display:none"><div class="es-mk-stat-val" id="es-mk-live-${{safe}}">–</div><div class="es-mk-stat-lbl">Im Postfach</div></div>
            </div>
            <div class="es-mk-actions">
              ${{isDeaktiv
                ? `<button class="es-mk-btn sec" onclick="esMkToggleAktiv('${{k.email}}',true,this)">&#x25B6; Aktivieren</button>`
                : `<button class="es-mk-btn" onclick="esMkAbrufen('${{k.email}}',this)">&#x25BA; Abrufen</button>
                   <button class="es-mk-btn sec" onclick="esMkVolltest('${{k.email}}',this)">&#x26A1; Verbindung testen</button>
                   <span id="es-mk-recon-${{safe}}" style="${{needsReconnect?'':'display:none'}}"><button class="es-mk-btn warn" onclick="esMkReconnect('${{k.email}}',this)">&#x21BA; Verbindung wiederherstellen</button></span>
                   <button class="es-mk-btn warn" onclick="esMkToggleAktiv('${{k.email}}',false,this)" title="Konto deaktivieren — Archiv bleibt erhalten">&#x23F8; Deaktivieren</button>`
              }}
              <button class="es-mk-btn danger" onclick="esMkDeleteConfirm('${{k.email}}')">&#x1F5D1; L&ouml;schen</button>
            </div>
            ${{!isDeaktiv?`<div class="es-kira-ord-toggle" onclick="esMkToggleOrdner('${{safe}}','${{k.email}}')">&#x25B6; Zus&auml;tzliche Postfach-Ordner</div><div id="es-kira-ord-${{safe}}" style="display:none"></div>`:''}}
          </div>`;
        }}).join('');
        // Stats lazy laden + Health Check auto-starten
        konten.forEach(k=>esMkLoadStats(k.email));
        esLoadTotalCount();
        // Health-Check beim ersten Laden (nur einmalig, danach 30-Min-Intervall)
        konten.forEach(k=>{{
          fetch('/api/mail/konto/health-check',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:k.email}})}}).catch(()=>{{}});
        }});
        // Ampel nach 15s einmalig aktualisieren (nur ampel, kein komplettes reload)
        setTimeout(()=>esRefreshAmpeln(), 15000);
        // Danach alle 30 Minuten Health-Check + Ampel im Hintergrund
        if(!window._pfHealthTimer) {{
          window._pfHealthTimer = setInterval(()=>{{
            konten.forEach(k=>fetch('/api/mail/konto/health-check',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:k.email}})}}).catch(()=>{{}}));
            setTimeout(()=>esRefreshAmpeln(), 15000);
          }}, 1800000);
        }}
      }}).catch(()=>{{
        // Fallback ohne Health
        list.innerHTML = konten.map(k=>{{
          const safe=k.email.replace(/[@.]/g,'_');
          return `<div class="es-mk-card" id="es-mk-card-${{safe}}">
            <div class="es-mk-card-head"><div class="es-mk-ico">&#x2709;</div>
            <div class="es-mk-body"><div class="es-mk-email">${{k.email}}</div><div class="es-mk-desc">${{k.beschreibung||''}}</div></div></div>
            <div class="es-mk-actions">
              <button class="es-mk-btn" onclick="esMkAbrufen('${{k.email}}',this)">&#x25BA; Abrufen</button>
              <button class="es-mk-btn sec" onclick="esMkReconnect('${{k.email}}',this)">&#x21BA; Verbinden</button>
            </div></div>`;
        }}).join('');
        konten.forEach(k=>esMkLoadStats(k.email));
        esLoadTotalCount();
      }});
    }}).catch(()=>{{
      const list=document.getElementById('es-mail-konten-list');
      if(list) list.innerHTML='<div style="padding:12px;color:#c84444;font-size:13px">Fehler beim Laden.</div>';
    }});
  }}
  function esLoadTotalCount() {{
    fetch('/api/mail/konten/stats').then(r=>r.json()).then(d=>{{
      const el=document.getElementById('es-mk-total-cnt');
      if(el) el.textContent=(d.mails_index||0).toLocaleString();
    }}).catch(()=>{{}});
  }}
  function esMkLoadStats(email) {{
    const safe=email.replace(/[@.]/g,'_');
    fetch('/api/mail/konten/stats?email='+encodeURIComponent(email)).then(r=>r.json()).then(d=>{{
      const idx=document.getElementById('es-mk-idx-'+safe);
      const arc=document.getElementById('es-mk-arc-'+safe);
      if(idx) idx.textContent=(d.mails_index||0).toLocaleString();
      if(arc) arc.textContent=d.archiv?.archiviert!=null?d.archiv.archiviert.toLocaleString():'–';
    }}).catch(()=>{{}});
  }}
  window.esMkSaveName = function(email, safe) {{
    const inp = document.getElementById('es-mk-dname-'+safe);
    if(!inp) return;
    const name = inp.value.trim();
    fetch('/api/mail/konto/display-name',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email,name}})}})
    .then(r=>r.json()).then(d=>{{
      if(d.ok) showToast('Anzeigename gespeichert','ok');
      else showToast('Fehler: '+(d.error||'?'),'fehler');
    }}).catch(()=>{{}});
  }};
  window.esMkSetStandard = function(email) {{
    fetch('/api/mail/konto/standard',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:email}})}})
    .then(r=>r.json()).then(d=>{{ if(d.ok) {{ showToast(email+' als Standardkonto gesetzt','ok'); esLoadMailKonten(); }} }}).catch(()=>{{}});
  }};
  window.esMkAbrufen = function(email,btn) {{
    if(btn) {{btn.disabled=true;btn.textContent='...';}}
    fetch('/api/mail/konto/abrufen',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:email}})}})
    .then(r=>r.json()).then(d=>{{ showToast('Abruf gestartet','ok'); setTimeout(()=>{{if(btn){{btn.disabled=false;btn.textContent='&#x25BA; Abrufen';}} esMkLoadStats(email);}},3000); }}).catch(()=>{{if(btn){{btn.disabled=false;btn.textContent='&#x25BA; Abrufen';}}}});
  }};
  window.esMkAlleAbrufen = function(btn) {{
    if(btn) {{btn.disabled=true;btn.textContent='...';}}
    fetch('/api/mail/konto/alle-abrufen',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:'{{}}'}})
    .then(r=>r.json()).then(d=>{{ showToast('Abruf aller Konten gestartet','ok'); setTimeout(()=>{{if(btn){{btn.disabled=false;btn.textContent='&#x25BA; Alle abrufen';}} esLoadMailKonten();}},5000); }}).catch(()=>{{if(btn){{btn.disabled=false;btn.textContent='&#x25BA; Alle abrufen';}}}});
  }};
  window.esMkTest = function(email,btn) {{
    if(btn) {{btn.disabled=true;btn.textContent='Teste...';}}
    fetch('/api/mail/konto/imap-test',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:email}})}})
    .then(r=>r.json()).then(d=>{{
      if(d.ok) showToast(email+': OK — '+d.ordner_anzahl+' Ordner in '+d.dauer_ms+'ms','ok');
      else showToast(email+': FEHLER — '+(d.error||'?'),'fehler');
    }}).catch(()=>showToast('Verbindungsfehler','fehler'))
    .finally(()=>{{if(btn){{btn.disabled=false;btn.textContent='&#x26A1; Testen';}}}});
  }};
  window.esMkAlleTest = function() {{
    const cards=document.querySelectorAll('[id^="es-mk-card-"]');
    cards.forEach(card=>{{
      const btn=card.querySelector('.es-mk-btn.sec');
      const email=card.querySelector('.es-mk-email')?.textContent?.trim()?.split(' ')[0];
      if(email) esMkTest(email,null);
    }});
  }};
  window.esMkTokenDel = function(email) {{
    if(!confirm('Token für '+email+' löschen?')) return;
    fetch('/api/mail/konto/token-loeschen',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:email}})}})
    .then(r=>r.json()).then(d=>{{ showToast(d.ok?'Token gelöscht':'Fehler: '+(d.error||'?'),d.ok?'ok':'fehler'); esLoadMailKonten(); }}).catch(()=>{{}});
  }};
  window.esMkToggleAktiv = function(email, aktiv, btn) {{
    if(btn){{btn.disabled=true;btn.textContent=aktiv?'Aktivieren...':'Deaktivieren...';}}
    fetch('/api/mail/konto/toggle-aktiv',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email,aktiv}})}})
      .then(r=>r.json()).then(d=>{{
        if(d.ok){{showToast(aktiv?email+' aktiviert':email+' deaktiviert \u2014 Archiv-Zugang bleibt bestehen',aktiv?'ok':'warnung');esLoadMailKonten();}}
        else showToast('Fehler: '+(d.error||'?'),'fehler');
      }}).catch(()=>showToast('Fehler','fehler'));
  }};
  window.esMkDeleteConfirm = function(email) {{
    showKritischModal(
      'Konto l\u00f6schen \u2014 '+email,
      '<strong>Empfehlung: Konto deaktivieren statt l\u00f6schen.</strong><br><br>Deaktivierte Konten sind f\u00fcr KIRA und im Archiv weiterhin zug\u00e4nglich \u2014 nur Abruf und Senden ist gestoppt.<br><br>L\u00f6schen entfernt nur den Konfigurations-Eintrag. Archiv-Dateien auf der Festplatte bleiben erhalten.',
      'L\u00d6SCHEN',
      ()=>showToast('Konto-L\u00f6schen: Admin-Feature \u2014 bitte manuell in raumkult_config.json','warnung'),
      'Tipp: \u23f8 Deaktivieren \u2014 Archiv bleibt vollst\u00e4ndig zug\u00e4nglich'
    );
  }};
  window.esMkConnect = function(email) {{
    const safe=email.replace(/[@.]/g,'_');
    const btn=document.getElementById('esbtn-'+safe);
    if(btn) {{btn.textContent='Verbinden...';btn.classList.add('connecting');btn.disabled=true;}}
    fetch('/api/mail/oauth/connect',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:email}})}})
    .then(r=>r.json()).then(d=>{{
      if(d.ok) {{
        showToast('Browser öffnet sich zur Microsoft-Anmeldung für '+email,'ok');
        let polls=0;
        const poll=setInterval(()=>{{
          polls++;
          fetch('/api/mail/oauth/status?email='+encodeURIComponent(email)).then(r=>r.json()).then(s=>{{
            if(s.status==='ok') {{clearInterval(poll);showToast(email+' erfolgreich verbunden \u2014 Verbindung wird gepr\u00fcft\u2026','ok');fetch('/api/mail/konto/health-check',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:email}})}}).catch(()=>{{}});setTimeout(()=>esLoadMailKonten(),5000);}}
            else if(s.status==='error') {{clearInterval(poll);showToast('Fehler: '+(s.message||'?'),'fehler');esLoadMailKonten();}}
            else if(polls>60) {{clearInterval(poll);showToast('Timeout','warnung');esLoadMailKonten();}}
          }});
        }},3000);
      }} else showToast('Fehler: '+(d.error||'?'),'fehler');
    }}).catch(()=>showToast('Verbindungsfehler','fehler'));
  }};
  window.esMkToggleOrdner = function(safe,email) {{
    const el=document.getElementById('es-kira-ord-'+safe);
    if(!el) return;
    if(el.style.display==='none') {{
      el.style.display='block';
      // Immer neu laden (Ordner können sich ändern)
      el.innerHTML='<div style="color:var(--text-muted);font-size:12px">Lade IMAP-Ordner...</div>';
      // Holt alle IMAP-Ordner + aktuelle Kira- und Postfach-Ordner via /api/mail/folders
      fetch('/api/mail/folders').then(r=>r.json()).then(data=>{{
        const kdata = (data.konten||[]).find(k=>k.email===email);
        if(!kdata||!kdata.alle_imap_ordner||!kdata.alle_imap_ordner.length) {{
          el.innerHTML='<div style="color:var(--text-muted);font-size:12px">Keine IMAP-Ordner gefunden.</div>';
          return;
        }}
        const kiraOrdner = (kdata.kira_ordner||[]).map(o=>o.toLowerCase());
        const zusatzOrdner = (kdata.zusatz_ordner||[]).map(o=>o.toLowerCase());
        // Nur Ordner zeigen die NICHT in Kira-Kern-Ordnern (Screenshot 2) sind
        const freieOrdner = kdata.alle_imap_ordner.filter(o=>{{
          const ol=o.toLowerCase();
          return !kiraOrdner.some(k=>k===ol||k.includes(ol)||ol.includes(k));
        }});
        if(!freieOrdner.length) {{
          el.innerHTML='<div style="color:var(--text-muted);font-size:12px">Alle Ordner sind bereits als Kira-Kernordner konfiguriert.</div>';
          return;
        }}
        const chips = freieOrdner.map(o=>{{
          const isAktiv = zusatzOrdner.some(z=>z===o.toLowerCase()||z.includes(o.toLowerCase())||o.toLowerCase().includes(z));
          return `<div class="es-kira-ord-chip${{isAktiv?' active':''}}" onclick="esMkOrdnerToggle(this,'${{email}}','${{o}}')" title="${{isAktiv?'Im Postfach sichtbar — klicken zum Entfernen':'Klicken um im Postfach anzuzeigen'}}">${{o}}</div>`;
        }}).join('');
        el.innerHTML='<div class="es-kira-ord-list">'+chips+'</div>'
          +'<div style="font-size:11px;color:var(--text-muted);margin-top:6px">&#9432; Markierte Ordner erscheinen im Postfach (kein Kira-Archiv). Kira-Kernordner werden hier nicht angezeigt.</div>';
      }}).catch(()=>{{el.innerHTML='<div style="color:#c84444;font-size:12px">Fehler beim Laden der Ordner</div>';}});
    }} else el.style.display='none';
  }};
  window.esMkOrdnerToggle = function(el,email,ordner) {{
    const wirdAktiv = !el.classList.contains('active');
    el.classList.toggle('active');
    el.title = wirdAktiv ? 'Im Postfach sichtbar — klicken zum Entfernen' : 'Klicken um im Postfach anzuzeigen';
    fetch('/api/mail/konto/postfach-ordner',{{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{email,ordner,aktiv:wirdAktiv}})
    }}).then(r=>r.json()).then(d=>{{
      if(!d.ok) {{
        el.classList.toggle('active'); // Rückgängig
        showToast('Fehler: '+(d.error||'?'),'fehler');
      }} else {{
        showToast(wirdAktiv?'Ordner "'+ordner+'" im Postfach hinzugefügt':'Ordner "'+ordner+'" aus Postfach entfernt','ok');
        // Postfach-Sidebar neu laden
        if(typeof pfRenderFolders==='function') {{
          fetch('/api/mail/folders').then(r=>r.json()).then(data=>pfRenderFolders(data)).catch(()=>{{}});
        }}
      }}
    }}).catch(()=>{{el.classList.toggle('active');showToast('Verbindungsfehler','fehler');}});
  }};
  // ── Konto-Wizard ────────────────────────────────────────────────────────────
  let _wiz = {{step:0, email:'', name:'', provider:'', settings:{{}}, jobId:null, isReconnect:false}};

  window.esMkWizardOpen = function(reconnectEmail) {{
    _wiz = {{step:1, email:reconnectEmail||'', name:'', provider:'', settings:{{}}, jobId:null, isReconnect:!!reconnectEmail}};
    const overlay = document.createElement('div');
    overlay.id = 'kira-wiz-overlay';
    overlay.className = 'kira-wiz-overlay';
    overlay.innerHTML = `<div class="kira-wiz-box" id="kira-wiz-box"></div>`;
    document.body.appendChild(overlay);
    _wizRender();
  }};
  window.esMkReconnect = function(email, btn) {{
    esMkWizardOpen(email);
  }};

  function _wizClose() {{
    const o=document.getElementById('kira-wiz-overlay');
    if(o) o.remove();
    esLoadMailKonten();
  }}

  function _wizRender() {{
    const box=document.getElementById('kira-wiz-box');
    if(!box) return;
    if(_wiz.step===1) box.innerHTML=_wizStep1();
    else if(_wiz.step===2) {{ box.innerHTML=_wizStep2(); _wizDetectProvider(); }}
    else if(_wiz.step===3) box.innerHTML=_wizStep3();
    else if(_wiz.step===4) box.innerHTML=_wizStep4();
    else if(_wiz.step===5) {{ box.innerHTML=_wizStep5(); _wizStartOAuth(); }}
    else if(_wiz.step===6) box.innerHTML=_wizStep6();
  }}

  function _wizDots(active, total=4) {{
    return `<div class="kira-wiz-dots">${{Array.from({{length:total}},(_,i)=>`<span class="kira-wiz-dot${{i<active?' active':''}}"></span>`).join('')}}</div>`;
  }}
  function _wizBtns(leftHtml, rightHtml) {{
    return `<div class="kira-wiz-btns"><div>${{leftHtml||''}}</div><div class="kira-wiz-btns-right">${{rightHtml||''}}</div></div>`;
  }}

  function _wizStep1() {{
    const isRec=_wiz.isReconnect;
    return `<div class="kira-wiz-step">
      ${{_wizDots(1)}}
      <div class="kira-wiz-step-label">Schritt 1 von 4</div>
      <h2 class="kira-wiz-title">${{isRec?'Verbindung wiederherstellen':'Konto hinzuf\u00fcgen'}}</h2>
      <p class="kira-wiz-sub">${{isRec?`Neuen Login f\u00fcr <strong style="color:var(--text)">${{_wiz.email}}</strong> einrichten.`:'Geben Sie Name und E\u2011Mail\u2011Adresse ein.'}}</p>
      <div class="kira-wiz-fields">
        ${{!isRec?`<div class="kira-wiz-field"><label>Ihr Name</label><input id="wiz-name" type="text" placeholder="Max Mustermann" value="${{_wiz.name}}" autocomplete="name"></div>`:''}}
        <div class="kira-wiz-field"><label>E\u2011Mail\u2011Adresse</label><input id="wiz-email" type="email" placeholder="name@firma.de" value="${{_wiz.email}}" ${{isRec?'readonly':''}} autocomplete="email"></div>
      </div>
      ${{!isRec?`<div class="kira-wiz-import-card" onclick="showToast('Import-Assistent \u2014 kommt bald','info')">
        <span style="font-size:24px">&#x1F4E5;</span>
        <div><div style="font-size:14px;font-weight:600;color:var(--text)">Aus anderem E-Mail-Client importieren</div><div style="font-size:12px;color:var(--text-muted);margin-top:2px">Thunderbird, Outlook, Apple Mail \u2014 <span style="color:var(--accent)">In Vorbereitung</span></div></div>
      </div>`:''}}
      ${{_wizBtns(
        `<button class="kira-wiz-btn-sec" onclick="_wizClose()">Abbrechen</button>`,
        `<button class="kira-wiz-btn-primary" onclick="_wizStep1Next()">Weiter &rarr;</button>`
      )}}
    </div>`;
  }}
  window._wizStep1Next = function() {{
    const e=document.getElementById('wiz-email');
    const n=document.getElementById('wiz-name');
    if(!e||!e.value.trim()){{showToast('E-Mail-Adresse eingeben','warnung');return;}}
    _wiz.email=e.value.trim();
    _wiz.name=n?n.value.trim():'';
    _wiz.step=2; _wizRender();
  }};

  function _wizStep2() {{
    return `<div class="kira-wiz-step">
      ${{_wizDots(2)}}
      <div class="kira-wiz-step-label">Schritt 2 von 4</div>
      <h2 class="kira-wiz-title">Einstellungen werden ermittelt\u2026</h2>
      <p class="kira-wiz-sub">Bitte warten Sie, w\u00e4hrend KIRA den passenden Anbieter und die Servereinstellungen erkennt.</p>
      <div class="kira-wiz-loading-area"><div class="kira-wiz-spinner"></div></div>
      ${{_wizBtns(`<button class="kira-wiz-btn-sec" onclick="_wizClose()">Abbrechen</button>`, '')}}
    </div>`;
  }}
  function _wizDetectProvider() {{
    const box=document.getElementById('kira-wiz-box');
    // Status-Updates während Erkennung (Stufen-Anzeige)
    let stageText=['Stufe 1: Domain-Analyse\u2026','Stufe 2: DNS-Abfrage + Autodiscover\u2026','Stufe 3: Microsoft-Probe\u2026'];
    let si=0;
    const stageTimer=setInterval(()=>{{
      const sub=box?.querySelector('.kira-wiz-sub');
      if(sub && stageText[si]) sub.textContent=stageText[si++];
      if(si>=stageText.length) clearInterval(stageTimer);
    }},1200);
    fetch('/api/mail/provider-detect?email='+encodeURIComponent(_wiz.email))
    .then(r=>r.json()).then(d=>{{
      clearInterval(stageTimer);
      _wiz.provider=d.provider||'imap';
      _wiz.detectionStage=d.detection_stage||0;
      _wiz.settings={{
        imap_server:d.imap_server||'',
        imap_port:d.imap_port||993,
        imap_ssl:true,
        auth:d.auth||'imap_password',
        protocol:d.protocol||'imap',
        confidence:d.confidence||'low'
      }};
      _wiz.step=3; _wizRender();
    }}).catch(()=>{{clearInterval(stageTimer);_wiz.provider='imap';_wiz.step=3;_wizRender();}});
  }}

  function _wizStep3() {{
    const providerLabels={{'microsoft':'Microsoft 365 / Outlook','google':'Google Mail','yahoo':'Yahoo Mail','aol':'AOL Mail','gmx':'GMX','web_de':'Web.de','t_online':'T-Online','imap':'Standard IMAP / Passwort'}};
    const providerIcons={{'microsoft':'&#x1F4E7;','google':'&#x1F4E7;','yahoo':'&#x1F4EC;','aol':'&#x1F4EC;','imap':'&#x1F4E8;'}};
    const lbl=providerLabels[_wiz.provider]||_wiz.provider;
    const ic=providerIcons[_wiz.provider]||'&#x1F4E8;';
    const srv=_wiz.settings.imap_server||'Wird automatisch ermittelt';
    const isMicrosoft=_wiz.provider==='microsoft';
    return `<div class="kira-wiz-step">
      ${{_wizDots(3)}}
      <div class="kira-wiz-step-label">Schritt 3 von 4</div>
      <h2 class="kira-wiz-title">Einstellungen gefunden</h2>
      <p class="kira-wiz-sub">KIRA hat passende Servereinstellungen f\u00fcr <strong style="color:var(--text)">${{_wiz.email}}</strong> erkannt.</p>
      <div class="kira-wiz-found-box">
        <div class="kira-wiz-found-ico">${{ic}}</div>
        <div>
          <div class="kira-wiz-found-name">${{lbl}}</div>
          <div class="kira-wiz-found-detail">${{srv}}</div>
          ${{isMicrosoft?`<div style="font-size:12px;color:var(--accent);margin-top:4px">&#x2713; Browser-Anmeldung \u2014 kein Passwort n\u00f6tig</div>`:`<div style="font-size:12px;color:var(--text-muted);margin-top:4px">IMAP-Verbindung mit Passwort</div>`}}
        </div>
      </div>
      <div style="text-align:center;margin-top:16px">
        <a href="#" class="kira-wiz-link" onclick="_wiz.step=4;_wizRender();return false">&#x2699; Server-Einstellungen bearbeiten</a>
      </div>
      ${{_wizBtns(
        `<button class="kira-wiz-btn-sec" onclick="_wiz.step=1;_wizRender()">Zur\u00fcck</button>`,
        `<button class="kira-wiz-btn-primary" onclick="_wizStep3Next()">${{isMicrosoft?'Microsoft-Login starten &rarr;':'Verbinden &rarr;'}}</button>`
      )}}
    </div>`;
  }}
  window._wizStep3Next = function() {{
    if(_wiz.provider==='microsoft') {{ _wiz.step=5; _wizRender(); }}
    else if(_wiz.settings.auth==='imap_password') {{ _wiz.step=4; _wizRender(); }}
    else {{ _wiz.step=5; _wizRender(); }}
  }};

  function _wizStep4() {{
    const s=_wiz.settings;
    const proto=s.protocol||'imap';
    const isExchange=proto==='exchange';
    return `<div class="kira-wiz-step">
      ${{_wizDots(4)}}
      <div class="kira-wiz-step-label">Erweiterte Einstellungen</div>
      <h2 class="kira-wiz-title">Server-Einstellungen</h2>
      <p class="kira-wiz-sub">Nur bei Bedarf anpassen. F\u00fcr die meisten Konten sind die erkannten Werte korrekt.</p>
      <div class="kira-wiz-fields">
        <div class="kira-wiz-field"><label>Authentifizierung</label><select id="wiz-auth" onchange="_wizAuthChange()">
          <option value="oauth2_microsoft" ${{s.auth==='oauth2_microsoft'?'selected':''}}>Microsoft OAuth 2.0 (empfohlen)</option>
          <option value="oauth2_google" ${{s.auth==='oauth2_google'?'selected':''}}>Google OAuth 2.0</option>
          <option value="imap_password" ${{s.auth==='imap_password'?'selected':''}}>Benutzername und Passwort</option>
        </select></div>
        <div class="kira-wiz-field"><label>Posteingangserver &mdash; Protokoll</label><select id="wiz-proto" onchange="_wizProtoChange()">
          <option value="imap" ${{proto==='imap'?'selected':''}}>IMAP</option>
          <option value="exchange" ${{proto==='exchange'?'selected':''}}>Exchange / EWS (Microsoft)</option>
          <option value="pop3" ${{proto==='pop3'?'selected':''}}>POP3</option>
        </select></div>
        <div id="wiz-server-row" class="kira-wiz-field">
          <label>Server-Adresse
            ${{isExchange?'<span style="font-size:11px;color:var(--text-muted);margin-left:6px">(leer lassen f\u00fcr automatische Erkennung)</span>':''}}
          </label>
          <input id="wiz-server" type="text" value="${{isExchange?(s.ews_server||''):(s.imap_server||'')}}"
            placeholder="${{isExchange?'https://outlook.office365.com/EWS/Exchange.asmx (optional)':'imap.provider.de'}}">
        </div>
        <div id="wiz-port-row" class="kira-wiz-field" style="${{isExchange?'display:none':''}}">
          <label>Port</label>
          <input id="wiz-port" type="number" value="${{s.imap_port||993}}">
        </div>
        <div id="wiz-email-row" class="kira-wiz-field" style="${{isExchange?'':'display:none'}}">
          <label>E-Mail-Adresse</label>
          <input id="wiz-konto-email" type="email" value="${{_wiz.email}}" readonly>
        </div>
        <div id="wiz-pw-fields" style="${{s.auth==='imap_password'?'':'display:none'}}">
          <div class="kira-wiz-field"><label>Passwort / App-Passwort</label><input id="wiz-pw" type="password" placeholder="App-Passwort aus den Kontoeinstellungen"></div>
        </div>
      </div>
      ${{_wizBtns(
        `<button class="kira-wiz-btn-sec" onclick="_wiz.step=3;_wizRender()">Zur\u00fcck</button>`,
        `<button class="kira-wiz-btn-primary" onclick="_wizStep4Next()">Weiter &rarr;</button>`
      )}}
    </div>`;
  }}
  window._wizProtoChange = function() {{
    const p=document.getElementById('wiz-proto')?.value;
    const portRow=document.getElementById('wiz-port-row');
    const emailRow=document.getElementById('wiz-email-row');
    const serverInput=document.getElementById('wiz-server');
    if(p==='exchange') {{
      if(portRow) portRow.style.display='none';
      if(emailRow) emailRow.style.display='';
      if(serverInput) serverInput.placeholder='https://outlook.office365.com/EWS/Exchange.asmx (optional)';
    }} else {{
      if(portRow) portRow.style.display='';
      if(emailRow) emailRow.style.display='none';
      if(serverInput) serverInput.placeholder='imap.provider.de';
    }}
  }};
  window._wizAuthChange = function() {{
    const v=document.getElementById('wiz-auth')?.value;
    const pw=document.getElementById('wiz-pw-fields');
    if(pw) pw.style.display=v==='imap_password'?'':'none';
  }};
  window._wizStep4Next = function() {{
    const proto=document.getElementById('wiz-proto')?.value||'imap';
    _wiz.settings.protocol=proto;
    if(proto==='exchange') {{
      _wiz.settings.ews_server=document.getElementById('wiz-server').value;
      _wiz.settings.imap_server='outlook.office365.com';
    }} else {{
      _wiz.settings.imap_server=document.getElementById('wiz-server').value;
      _wiz.settings.imap_port=parseInt(document.getElementById('wiz-port')?.value)||993;
    }}
    _wiz.settings.auth=document.getElementById('wiz-auth').value;
    _wiz.settings.passwort=document.getElementById('wiz-pw')?.value||'';
    if(_wiz.settings.auth==='imap_password') _wizSaveImap();
    else {{ _wiz.step=5; _wizRender(); }}
  }};

  function _wizStep5() {{
    return `<div class="kira-wiz-step">
      ${{_wizDots(4)}}
      <div class="kira-wiz-step-label">Microsoft-Anmeldung</div>
      <h2 class="kira-wiz-title">Browser-Login wird ge\u00f6ffnet</h2>
      <p class="kira-wiz-sub">Ein Browserfenster \u00f6ffnet sich. Melden Sie sich dort mit <strong style="color:var(--text)">${{_wiz.email}}</strong> an und kehren Sie dann hierher zur\u00fcck.</p>
      <div class="kira-wiz-loading-area"><div class="kira-wiz-spinner"></div><p style="font-size:13px;color:var(--text-muted)">Warte auf Anmeldung\u2026</p></div>
      ${{_wizBtns(`<button class="kira-wiz-btn-sec" onclick="_wizClose()">Abbrechen</button>`, '')}}
    </div>`;
  }}
  function _wizStartOAuth() {{
    // Zuerst Konto anlegen falls neu
    const savePromise = _wiz.isReconnect
      ? Promise.resolve({{ok:true}})
      : fetch('/api/mail/konto/hinzufuegen',{{method:'POST',headers:{{'Content-Type':'application/json'}},
          body:JSON.stringify({{email:_wiz.email,beschreibung:_wiz.name||_wiz.email.split('@')[0],
            auth_methode:'oauth2',imap_server:_wiz.settings.imap_server||'outlook.office365.com',
            imap_port:_wiz.settings.imap_port||993,imap_ssl:true}})}}).then(r=>r.json());
    savePromise.then(saved=>{{
      if(!saved.ok && !_wiz.isReconnect){{showToast('Fehler: '+(saved.error||'?'),'fehler');return;}}
      const endpoint = _wiz.isReconnect ? '/api/mail/konto/reconnect' : '/api/mail/konto/oauth-start';
      return fetch(endpoint,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:_wiz.email}})}})
        .then(r=>r.json()).then(d=>{{
          if(!d.ok){{showToast('OAuth-Fehler: '+(d.error||'?'),'fehler');_wizClose();return;}}
          _wiz.jobId=d.job_id;
          _wizPollOAuth();
        }});
    }}).catch(e=>{{showToast('Fehler: '+e,'fehler');_wizClose();}});
  }}
  function _wizPollOAuth() {{
    let polls=0;
    const timer=setInterval(()=>{{
      polls++;
      fetch('/api/mail/konto/oauth-status?job_id='+_wiz.jobId).then(r=>r.json()).then(s=>{{
        if(s.status==='done'){{clearInterval(timer);fetch('/api/mail/konto/health-check',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:_wiz.email}})}}).catch(()=>{{}});_wiz.step=6;_wizRender();}}
        else if(s.status==='error'){{clearInterval(timer);_wiz.step=6;_wiz._error=s.error;_wizRender();}}
        else if(polls>120){{clearInterval(timer);_wiz._error='Timeout';_wiz.step=6;_wizRender();}}
      }}).catch(()=>{{}});
    }},2000);
  }}

  function _wizSaveImap() {{
    const s=_wiz.settings;
    fetch('/api/mail/konto/hinzufuegen',{{method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{email:_wiz.email,beschreibung:_wiz.name||_wiz.email.split('@')[0],
        auth_methode:'imap_password',imap_server:s.imap_server,imap_port:s.imap_port,
        imap_ssl:true,login:_wiz.email,passwort:s.passwort||''}})}}
    ).then(r=>r.json()).then(d=>{{
      if(d.ok){{_wiz.step=6;_wizRender();}}
      else showToast('Fehler: '+(d.error||'?'),'fehler');
    }}).catch(()=>showToast('Fehler','fehler'));
  }}

  function _wizStep6() {{
    const ok=!_wiz._error;
    return `<div class="kira-wiz-step">
      <div class="kira-wiz-success-icon">${{ok?'&#x2705;':'&#x26A0;&#xFE0F;'}}</div>
      <h2 class="kira-wiz-title">${{ok?'Erfolgreich verbunden':'Verbindung fehlgeschlagen'}}</h2>
      <p class="kira-wiz-sub">${{ok
        ?`<strong style="color:var(--text)">${{_wiz.email}}</strong> wurde erfolgreich eingerichtet und ist jetzt verbunden.`
        :`Beim Verbinden ist ein Fehler aufgetreten:<br><span style="color:#c83c3c;font-size:13px">${{_wiz._error||'Unbekannter Fehler'}}</span>`}}</p>
      ${{_wizBtns(
        ok?'':`<button class="kira-wiz-btn-sec" onclick="_wiz.step=1;_wiz._error=null;_wizRender()">&#x21BA; Erneut versuchen</button>`,
        `<button class="kira-wiz-btn-primary" onclick="_wizClose()">${{ok?'Fertig':'Schlie\u00dfen'}}</button>`
      )}}
    </div>`;
  }}
  window.esMkArchivPruefen = function() {{
    const pfad=document.getElementById('cfg-archiv-pfad').value;
    if(!pfad){{showToast('Bitte Pfad eingeben','warnung');return;}}
    fetch('/api/mail/archiv/pruefen?pfad='+encodeURIComponent(pfad)).then(r=>r.json()).then(d=>{{
      if(d.ok) showToast('Pfad vorhanden und erreichbar ✓','ok');
      else showToast('Pfad nicht gefunden oder nicht erreichbar','fehler');
    }}).catch(()=>{{}});
  }};
  window.esReindex = function(btn) {{
    if(btn){{btn.textContent='Läuft...';btn.disabled=true;}}
    fetch('/api/mail/archiv/reindex',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:'{{}}'}})
    .then(r=>r.json()).then(d=>{{
      showToast('Re-Index gestartet...','ok');
      const prog=document.getElementById('es-reindex-progress');
      const timer=setInterval(()=>{{
        fetch('/api/mail/archiv/reindex/progress').then(r=>r.json()).then(p=>{{
          if(prog) prog.textContent=p.done?'Fertig: '+p.processed+' Mails':p.processed+'/'+p.total+' verarbeitet';
          if(p.done){{clearInterval(timer);if(btn){{btn.disabled=false;btn.textContent='Re-Index starten';}} esLoadTotalCount();}}
        }}).catch(()=>clearInterval(timer));
      }},1500);
    }}).catch(()=>{{if(btn){{btn.disabled=false;btn.textContent='Re-Index starten';}}}});
  }};

  window.esMailNachklassifizieren = function(btn) {{
    const seitEl = document.getElementById('es-recheck-seit');
    const seit = seitEl ? seitEl.value : '';
    if(!seit) {{ showToast('Bitte Startdatum w\u00e4hlen','warnung'); return; }}
    if(btn) {{ btn.disabled=true; btn.textContent='L\u00e4uft\u2026'; }}
    const prog = document.getElementById('es-recheck-progress');
    if(prog) prog.textContent = 'Starte\u2026';
    fetch('/api/mail/nachklassifizieren', {{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{seit: seit, bis: null, trocken: false}})
    }}).then(r=>r.json()).then(d=>{{
      if(!d.ok) {{
        showToast('Fehler: '+(d.error||'?'),'fehler');
        if(btn){{ btn.disabled=false; btn.textContent='\u21BA Nachklassifizieren'; }}
        return;
      }}
      showToast('Nachklassifizierung gestartet ab '+seit+'\u2026','ok');
      let polls=0;
      const timer=setInterval(()=>{{
        polls++;
        fetch('/api/mail/nachklassifizieren/status').then(r=>r.json()).then(p=>{{
          const pct=p.gesamt>0?Math.round(100*p.geprueft/p.gesamt):0;
          if(prog){{
            if(p.finished){{
              prog.textContent='Fertig: '+p.gesamt+' gepr\u00fcft \u00b7 '+(p.tasks_erstellt||0)+' Tasks erstellt \u00b7 '+(p.ignoriert||0)+' ignoriert'+(p.fehler?' \u00b7 '+p.fehler+' Fehler':'');
            }} else {{
              prog.textContent=p.geprueft+'/'+p.gesamt+' ('+pct+'%) \u00b7 Tasks: '+(p.tasks_erstellt||0)+' \u00b7 '+((p.aktuell||'').slice(0,60));
            }}
          }}
          if(p.finished||polls>600){{
            clearInterval(timer);
            if(btn){{ btn.disabled=false; btn.textContent='\u21BA Nachklassifizieren'; }}
            if(p.tasks_erstellt>0) showToast(p.tasks_erstellt+' neue Tasks erstellt','ok');
          }}
        }}).catch(()=>clearInterval(timer));
      }},2000);
    }}).catch(()=>{{
      if(btn){{ btn.disabled=false; btn.textContent='\u21BA Nachklassifizieren'; }}
      if(prog) prog.textContent='Verbindungsfehler';
    }});
  }};

  // Sync-Ordner laden (bestehende Funktion)
  function esLoadMailArchiv() {{
    // Mail-Klassifizierung + Postfach-Refresh laden
    fetch('/api/einstellungen').then(r=>r.json()).then(d=>{{
      const mk=d.mail_klassifizierung||{{}};
      const c1=document.getElementById('cfg-mail-classify');
      const c2=document.getElementById('cfg-mail-tasks');
      const c3=document.getElementById('cfg-mail-ignore-newsletter');
      if(c1) c1.checked=!!mk.classify;
      if(c2) c2.checked=!!mk.auto_tasks;
      if(c3) c3.checked=!!mk.ignore_newsletter;
      // Standard-Datum für Nachklassifizierung (90 Tage zurück)
      const recheckSeit=document.getElementById('es-recheck-seit');
      if(recheckSeit&&!recheckSeit.value){{
        const d90=new Date(); d90.setDate(d90.getDate()-90);
        recheckSeit.value=d90.toISOString().slice(0,10);
      }}
      // Postfach-Refresh-Intervall
      const pr=d.mail_postfach?.refresh_intervall_min??0;
      const prSel=document.getElementById('cfg-postfach-refresh');
      if(prSel) {{
        const opt=prSel.querySelector('option[value="'+pr+'"]');
        if(opt) opt.selected=true; else prSel.value='0';
      }}
      // Lese-Markierung
      const lm=d.mail_postfach?.lese_markierung||'sofort';
      const lmSel=document.getElementById('cfg-lese-markierung');
      if(lmSel) lmSel.value=lm;
    }}).catch(()=>{{}});
    // Archiv laden
    fetch('/api/mail/archiv/status').then(r=>r.json()).then(d=>{{
      const pfad=document.getElementById('cfg-archiv-pfad');
      const aktiv=document.getElementById('cfg-archiv-aktiv');
      const badge=document.getElementById('es-archiv-status-badge');
      const txt=document.getElementById('es-archiv-status-text');
      if(pfad && d.pfad) pfad.value=d.pfad;
      if(aktiv) aktiv.checked=!!d.aktiv;
      if(txt) txt.textContent=(d.mails_index||0).toLocaleString()+' Mails im Index · '+(d.pfad||'kein Pfad');
      if(badge) badge.innerHTML=d.pfad_ok?'<span class="es-mk-status es-mk-ok">&#x2713; Archiv OK</span>':'<span class="es-mk-status es-mk-expired">&#x26A0; Pfad fehlt</span>';
    }}).catch(()=>{{}});
    // Sync-Ordner
    fetch('/api/mail/konten').then(r=>r.json()).then(data=>{{
      const konten=data.konten||[];
      const list=document.getElementById('es-sync-ordner-list');
      if(!list||!konten.length) return;
      fetch('/api/mail/archiv/status').then(r=>r.json()).then(arcData=>{{
        const syncOrdner=arcData.sync_ordner||{{}};
        list.innerHTML=konten.map(k=>{{
          const ordner=syncOrdner[k.email]||['INBOX','Gesendete Elemente'];
          const pflicht=['INBOX','Gesendete Elemente'];
          const alleOrdner=[...new Set([...pflicht,...ordner,'Entwürfe','Gelöschte Elemente','Spam'])];
          return `<div style="margin-bottom:12px"><div style="font-size:12px;font-weight:600;margin-bottom:6px">${{k.email}}</div>
            <div style="display:flex;flex-wrap:wrap;gap:6px">`+alleOrdner.map(o=>{{
              const checked=ordner.includes(o);
              const disabled_=pflicht.includes(o);
              return `<label style="display:flex;align-items:center;gap:4px;font-size:12px;cursor:${{disabled_?'default':'pointer'}}">
                <input type="checkbox" ${{checked?'checked':''}} ${{disabled_?'disabled':''}} onchange="esSyncOrdnerChange('${{k.email}}','${{o}}',this.checked)">${{o}}</label>`;
            }}).join('')+`</div></div>`;
        }}).join('');
      }}).catch(()=>{{}});
    }}).catch(()=>{{}});
  }}
  function _doSyncOrdnerChange(konto,ordner,aktiv) {{
    fetch('/api/mail/archiv/sync-ordner',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{konto,ordner,aktiv}})}})
    .then(r=>r.json()).then(d=>{{
      if(!d.ok) {{ showToast('Fehler beim Speichern: '+(d.error||'?'),'fehler'); return; }}
      showToast(aktiv?'Ordner "'+ordner+'" zu Kira hinzugefügt':'Ordner "'+ordner+'" aus Kira entfernt', aktiv?'ok':'warn');
      // Konto-Karten und Postfach-Sidebar neu laden
      esLoadMailKonten();
      if(typeof pfRenderFolders==='function') {{
        fetch('/api/mail/folders').then(r=>r.json()).then(data=>pfRenderFolders(data)).catch(()=>{{}});
      }}
    }}).catch(()=>{{}});
  }}
  window.esSyncOrdnerChange = function(konto,ordner,aktiv) {{
    if(!aktiv) {{
      // Deaktivieren nur mit Dreifach-Bestätigung
      showKritischModal(
        'Kira-Archiv-Ordner deaktivieren',
        'Ordner <strong>'+ordner+'</strong> f&uuml;r <em>'+konto+'</em> wird nicht mehr von Kira überwacht und archiviert.<br><br>'
        +'Bestehende Archiv-Daten bleiben erhalten — aber neue Mails in diesem Ordner werden nicht mehr von Kira verarbeitet und sind nicht mehr im LLM-Kontext.',
        ordner,
        function() {{ _doSyncOrdnerChange(konto,ordner,false); }},
        'Gib den Ordnernamen ein um zu bestätigen: '+ordner
      );
      // Checkbox zurücksetzen (wird durch showKritischModal erst nach Bestätigung deaktiviert)
      // Kein direktes Checkbox-Toggle hier — Reload nach Bestätigung
    }} else {{
      _doSyncOrdnerChange(konto,ordner,true);
    }}
  }};
  window.esArchivOrdnerWaehlen = function(btn) {{
    if(btn) {{ btn.disabled=true; btn.textContent='…'; }}
    fetch('/api/browse/folder').then(r=>r.json()).then(d=>{{
      if(!d.ok) {{ if(btn) {{btn.disabled=false;btn.textContent='&#x1F4C2;';}} return; }}
      const jobId=d.job_id;
      let polls=0;
      const t=setInterval(()=>{{
        polls++;
        fetch('/api/browse/result?job_id='+jobId).then(r=>r.json()).then(s=>{{
          if(s.done) {{
            clearInterval(t);
            if(btn) {{btn.disabled=false;btn.textContent='&#x1F4C2;';}}
            if(s.path) {{
              const inp=document.getElementById('cfg-archiv-pfad');
              if(inp) inp.value=s.path;
            }}
          }} else if(polls>60) {{
            clearInterval(t);
            if(btn) {{btn.disabled=false;btn.textContent='&#x1F4C2;';}}
          }}
        }}).catch(()=>{{}});
      }}, 500);
    }}).catch(()=>{{ if(btn) {{btn.disabled=false;btn.textContent='&#x1F4C2;';}} }});
  }};
  window.esMailMonitorNow = function(btn) {{
    if(btn) {{btn.disabled=true;btn.textContent='L\u00e4dt…';}}
    fetch('/api/mail/monitor/trigger',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:'{{}}'}})
    .then(r=>r.json()).then(d=>{{
      if(btn) {{btn.disabled=false;btn.textContent='\u25ba Jetzt abrufen';}}
      showToast(d.ok?'Abruf gestartet':'Fehler: '+(d.error||'?'),d.ok?'ok':'fehler');
    }}).catch(()=>{{ if(btn) {{btn.disabled=false;btn.textContent='\u25ba Jetzt abrufen';}} }});
  }};

  // ── Mail-Tab Switching ─────────────────────────────────────────────────────
  window.esMailTab = function(tabId, btn) {{
    document.querySelectorAll('.es-mail-tab').forEach(b=>b.classList.remove('act'));
    document.querySelectorAll('.es-mail-panel').forEach(p=>p.classList.remove('act'));
    if(btn) btn.classList.add('act');
    const panel = document.getElementById('es-mtp-'+tabId);
    if(panel) panel.classList.add('act');
    // Lazy-load pro Tab
    if(tabId==='signaturen') esLoadSignaturen();
    if(tabId==='sync') esLoadMailArchiv();
    if(tabId==='archiv') esLoadMailArchiv();
  }};

  // ── Signaturen ─────────────────────────────────────────────────────────────
  window.esLoadSignaturen = function() {{
    fetch('/api/mail/signaturen').then(r=>r.json()).then(d=>{{
      const list = document.getElementById('es-sig-list');
      if(!list) return;
      const sigs = d.signaturen || [];
      if(!sigs.length) {{
        list.innerHTML='<div class="es-sig-empty">Noch keine Signaturen angelegt.<br>Klicke \u201e+ Neue Signatur\u201c um zu beginnen.</div>';
        return;
      }}
      // Gruppierung nach Konto
      const byKonto = {{}};
      sigs.forEach(s=>{{
        if(!byKonto[s.konto]) byKonto[s.konto]=[];
        byKonto[s.konto].push(s);
      }});
      let html='';
      Object.entries(byKonto).forEach(([konto,ks])=>{{
        html+=`<div style="margin-bottom:20px">
          <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">${{konto}}</div>`;
        ks.forEach(s=>{{
          html+=`<div class="es-sig-item" id="es-sig-item-${{s.id}}">
            <div style="flex:1;min-width:0">
              <div class="es-sig-name">${{s.name||'Ohne Titel'}}</div>
              <div class="es-sig-konto">${{s.konto}}</div>
            </div>
            ${{s.ist_default?'<span class="es-sig-default-badge">&#x2605; Standard</span>':''}}
            <div class="es-sig-actions">
              ${{!s.ist_default?`<button class="es-mk-btn sec" style="font-size:11px;padding:3px 9px" title="Als Standard setzen" onclick="esSigSetDefault(${{s.id}},'${{s.konto.replace(/'/g,"\\'")}}')">&#x2605;</button>`:'<button class="es-mk-btn sec" style="font-size:11px;padding:3px 9px;opacity:.4" disabled title="Ist bereits Standard">&#x2605;</button>'}}
              <button class="es-mk-btn sec" style="font-size:11px;padding:3px 9px" onclick="esSigEdit(${{s.id}})">&#x270E; Bearbeiten</button>
              <button class="es-mk-btn danger" style="font-size:11px;padding:3px 9px" onclick="esSigDelete(${{s.id}},'${{(s.name||'').replace(/'/g,"\\'")}}')">&#x1F5D1;</button>
            </div>
          </div>`;
        }});
        html+='</div>';
      }});
      list.innerHTML=html;
    }}).catch(()=>{{
      const list=document.getElementById('es-sig-list');
      if(list) list.innerHTML='<div class="es-sig-empty" style="color:#c84444">Fehler beim Laden der Signaturen.</div>';
    }});
  }};

  // Signatur-Editor-State
  let _sigEdit = {{id:null,konto:'',name:'',html:'',quill:null}};

  window.esSigNeu = function() {{
    _sigEdit = {{id:null,konto:'',name:'',html:'',quill:null}};
    _esSigModalOpen('Neue Signatur');
  }};
  window.esSigEdit = function(id) {{
    fetch('/api/mail/signaturen').then(r=>r.json()).then(d=>{{
      const s=(d.signaturen||[]).find(x=>x.id===id);
      if(!s){{showToast('Signatur nicht gefunden','fehler');return;}}
      _sigEdit = {{id:s.id,konto:s.konto,name:s.name,html:s.html,quill:null}};
      _esSigModalOpen('Signatur bearbeiten');
    }}).catch(()=>showToast('Fehler','fehler'));
  }};
  window.esSigDelete = function(id,name) {{
    if(!confirm('Signatur \u201e'+name+'\u201c wirklich l\u00f6schen?')) return;
    fetch('/api/mail/signaturen/delete',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id:id}})}})
    .then(r=>r.json()).then(d=>{{
      showToast(d.ok?'Signatur gel\u00f6scht':'Fehler: '+(d.error||'?'),d.ok?'ok':'fehler');
      if(d.ok) esLoadSignaturen();
    }}).catch(()=>showToast('Fehler','fehler'));
  }};
  window.esSigSetDefault = function(id,konto) {{
    fetch('/api/mail/signaturen/default',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id:id,konto:konto}})}})
    .then(r=>r.json()).then(d=>{{
      showToast(d.ok?'Standard-Signatur gesetzt':'Fehler: '+(d.error||'?'),d.ok?'ok':'fehler');
      if(d.ok) esLoadSignaturen();
    }}).catch(()=>showToast('Fehler','fehler'));
  }};

  function _esSigModalOpen(title) {{
    // Konten für Dropdown
    fetch('/api/mail/konten').then(r=>r.json()).then(data=>{{
      const konten=(data.konten||[]).filter(k=>k.aktiv!==false).map(k=>k.email);
      const kontoOpts=konten.map(e=>`<option value="${{e}}" ${{e===_sigEdit.konto?'selected':''}}>${{e}}</option>`).join('');
      const modal=document.createElement('div');
      modal.className='es-sig-modal-overlay';
      modal.id='es-sig-modal';
      modal.innerHTML=`
        <div class="es-sig-modal">
          <div class="es-sig-modal-head">
            <span class="es-sig-modal-title">${{title}}</span>
            <button onclick="document.getElementById('es-sig-modal')?.remove()" style="background:none;border:none;cursor:pointer;font-size:20px;color:var(--text-muted);line-height:1">&times;</button>
          </div>
          <div class="es-sig-modal-body">
            <div class="es-sig-field">
              <label>Konto</label>
              <select id="es-sig-konto">${{kontoOpts||'<option value="">Kein aktives Konto</option>'}}</select>
            </div>
            <div class="es-sig-field">
              <label>Name der Signatur</label>
              <input type="text" id="es-sig-name" value="${{_sigEdit.name||''}}" placeholder="z.B. Standard, Formal, Kurz">
            </div>
            <div class="es-sig-field">
              <label>Signatur (HTML-Editor)</label>
              <div id="es-sig-quill-wrap">
                <div id="es-sig-quill-editor"></div>
              </div>
            </div>
          </div>
          <div class="es-sig-modal-foot">
            <button class="es-mk-btn sec" onclick="document.getElementById('es-sig-modal')?.remove()">Abbrechen</button>
            <button class="es-mk-btn" onclick="esSigSave()">Speichern</button>
          </div>
        </div>`;
      document.body.appendChild(modal);
      // Quill laden
      _esSigInitQuill();
    }}).catch(()=>showToast('Fehler beim Laden der Konten','fehler'));
  }}

  function _esSigInitQuill() {{
    if(window.Quill) {{
      _esSigSetupQuill();
      return;
    }}
    // Quill CDN laden
    const css=document.createElement('link');
    css.rel='stylesheet';
    css.href='https://cdn.quilljs.com/1.3.7/quill.snow.css';
    document.head.appendChild(css);
    const scr=document.createElement('script');
    scr.src='https://cdn.quilljs.com/1.3.7/quill.min.js';
    scr.onload=_esSigSetupQuill;
    document.head.appendChild(scr);
  }}

  function _esSigSetupQuill() {{
    const el=document.getElementById('es-sig-quill-editor');
    if(!el||!window.Quill) return;
    _sigEdit.quill=new Quill('#es-sig-quill-editor', {{
      theme:'snow',
      modules:{{
        toolbar:[
          ['bold','italic','underline','strike'],
          [{{color:[]}},{{'background':[]}}],
          [{{font:[]}},{{'size':['small',false,'large','huge']}}],
          [{{list:'ordered'}},{{'list':'bullet'}}],
          ['link','image'],
          ['clean']
        ]
      }}
    }});
    // Initial-HTML setzen
    if(_sigEdit.html) {{
      _sigEdit.quill.clipboard.dangerouslyPasteHTML(_sigEdit.html);
    }}
  }}

  window.esSigSave = function() {{
    const konto=(document.getElementById('es-sig-konto')?.value||'').trim();
    const name=(document.getElementById('es-sig-name')?.value||'').trim();
    const html=_sigEdit.quill?_sigEdit.quill.root.innerHTML:'';
    if(!konto){{showToast('Konto w\u00e4hlen','warnung');return;}}
    if(!name){{showToast('Name eingeben','warnung');return;}}
    fetch('/api/mail/signaturen/save',{{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{id:_sigEdit.id,konto,name,html}})
    }}).then(r=>r.json()).then(d=>{{
      if(d.ok){{
        showToast('Signatur gespeichert','ok');
        document.getElementById('es-sig-modal')?.remove();
        esLoadSignaturen();
      }} else showToast('Fehler: '+(d.error||'?'),'fehler');
    }}).catch(()=>showToast('Fehler','fehler'));
  }};
  </script>
</div>

<!-- ── SECTION: INTEGRATIONEN ─────────────────────────────────────────── -->
<div class="es-sec-panel" id="es-sec-integrationen">
  <div class="es-sec-h">Integrationen</div>
  <div class="es-sec-sub">Externe Dienste verbinden.</div>

  <!-- Microsoft Entra App -->
  <div class="es-grp">
    <div class="es-grp-h">&#x1F511; Microsoft KIRA Entra App</div>
    <div class="es-grp-sub">Zentrale Microsoft-App f&uuml;r den OAuth-Login aller Microsof-Konten. Kein per-Konto Setup n&ouml;tig.</div>
    <div class="es-row">
      <div class="es-row-label"><span>App-ID (Client)</span></div>
      <code style="font-size:12px;background:var(--bg-raised);padding:4px 8px;border-radius:5px;color:var(--text-muted)">a0591b2d-86c3-4bc1-adf0-a10e197da07f</code>
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>Mandant</span></div>
      <code style="font-size:12px;background:var(--bg-raised);padding:4px 8px;border-radius:5px;color:var(--text-muted)">common (Mehrere Organisationen)</code>
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>Status</span></div>
      <span id="ms-app-status" style="font-size:13px;color:var(--text-muted)">Noch nicht gepr&uuml;ft</span>
    </div>
    <div style="margin-top:8px">
      <button class="es-mk-btn sec" onclick="esMsAppTest(this)">&#x26A1; App-Verbindung testen</button>
    </div>
  </div>

  <!-- WhatsApp Business API -->
  <div class="es-grp">
    <div class="es-grp-h">&#x1F4F1; WhatsApp Business Cloud API</div>
    <div class="es-grp-sub">Eingehende WhatsApp-Nachrichten als KIRA-Tasks verarbeiten. Webhook-URL: <code style="font-size:11px;background:var(--bg-raised);padding:1px 5px;border-radius:4px">/api/webhook/whatsapp</code></div>
    <div class="es-row">
      <div class="es-row-label"><span>Verify Token</span><span class="es-row-hint">Frei wählbarer String — selber Wert in Meta Developer Console &gt; Webhook &gt; Verify Token</span></div>
      <input type="text" id="cfg-wa-verify" placeholder="z.B. kira-2026-xyz" style="width:220px;background:var(--bg-input,var(--bg-raised));border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:13px;color:var(--text)">
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>App Secret</span><span class="es-row-hint">Meta Developer Console &gt; App &gt; App-Einstellungen &gt; App Secret (für HMAC-Signatur-Prüfung)</span></div>
      <input type="password" id="cfg-wa-secret" placeholder="App Secret" style="width:220px;background:var(--bg-input,var(--bg-raised));border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:13px;color:var(--text)">
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>Phone Number ID</span><span class="es-row-hint">Aus Meta Developer Console (für späteres Senden von Antworten)</span></div>
      <input type="text" id="cfg-wa-phone-id" placeholder="Phone Number ID" style="width:220px;background:var(--bg-input,var(--bg-raised));border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:13px;color:var(--text)">
    </div>
    <div class="es-row">
      <div class="es-row-label"><span>Einrichtung</span></div>
      <div style="font-size:12px;color:var(--text-muted);line-height:1.6">
        1. Meta Business Manager → App → WhatsApp → Konfiguration<br>
        2. Callback URL: <code style="background:var(--bg-raised);padding:1px 4px;border-radius:3px">https://deine-domain/api/webhook/whatsapp</code><br>
        3. Verify Token: identisch mit dem Wert oben<br>
        4. Webhook-Felder abonnieren: <code style="background:var(--bg-raised);padding:1px 4px;border-radius:3px">messages</code>
      </div>
    </div>
    <div style="margin-top:8px">
      <button class="es-mk-btn" onclick="esWaSpeichern(this)">Speichern</button>
      <button class="es-mk-btn sec" style="margin-left:8px" onclick="esWaTest()">Webhook testen</button>
    </div>
  </div>

  <!-- Andere (In Planung) -->
  <div class="es-grp">
    <div class="es-grp-h">Weitere Integrationen</div>
    <div class="es-intg"><div class="es-intg-ico">&#x1F4C5;</div><div class="es-intg-body"><div class="es-intg-name">Google Calendar</div><div class="es-intg-sub">Termine synchronisieren</div></div><span class="es-badge plan">In Planung</span></div>
    <div class="es-intg"><div class="es-intg-ico">&#x1F4DD;</div><div class="es-intg-body"><div class="es-intg-name">CRM-Export</div><div class="es-intg-sub">Kundendaten exportieren</div></div><span class="es-badge plan">In Planung</span></div>
    <div class="es-intg"><div class="es-intg-ico">&#x1F517;</div><div class="es-intg-body"><div class="es-intg-name">Webhook</div><div class="es-intg-sub">Ereignisse an externe URLs senden</div></div><span class="es-badge plan">In Planung</span></div>
    <div class="es-intg"><div class="es-intg-ico">&#x1F4C8;</div><div class="es-intg-body"><div class="es-intg-name">Buchhaltungs-Export</div><div class="es-intg-sub">Rechnungsdaten exportieren</div></div><span class="es-badge plan">In Planung</span></div>
  </div>

  <script>
  function esIntegLoad() {{
    // WhatsApp-Einstellungen laden
    fetch('/api/einstellungen').then(r=>r.json()).then(d=>{{
      const wa=d.whatsapp||{{}};
      const el1=document.getElementById('cfg-wa-verify');
      const el3=document.getElementById('cfg-wa-phone-id');
      if(el1) el1.value=wa.verify_token||'';
      if(el3) el3.value=wa.phone_number_id||'';
    }}).catch(()=>{{}});
  }}
  window.esWaSpeichern = function(btn) {{
    const body={{
      whatsapp_verify_token:document.getElementById('cfg-wa-verify').value,
      whatsapp_app_secret:document.getElementById('cfg-wa-secret').value,
      whatsapp_phone_number_id:document.getElementById('cfg-wa-phone-id').value
    }};
    fetch('/api/whatsapp/secrets-speichern',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}})
    .then(r=>r.json()).then(d=>{{ showToast(d.ok?'WhatsApp-Einstellungen gespeichert':'Fehler: '+(d.error||'?'),d.ok?'ok':'fehler'); }}).catch(()=>showToast('Fehler','fehler'));
  }};
  window.esWaTest = function() {{
    const token=document.getElementById('cfg-wa-verify').value;
    if(!token){{showToast('Verify Token fehlt','warnung');return;}}
    const url='/api/webhook/whatsapp?hub.mode=subscribe&hub.verify_token='+encodeURIComponent(token)+'&hub.challenge=KIRATEST';
    fetch(url).then(r=>r.text()).then(t=>{{
      if(t==='KIRATEST') showToast('Webhook-Verifizierung erfolgreich ✓','ok');
      else showToast('Webhook antwortet falsch: '+t,'warnung');
    }}).catch(()=>showToast('Fehler beim Test','fehler'));
  }};
  window.esMsAppTest = function(btn) {{
    if(btn){{btn.disabled=true;btn.textContent='Teste\u2026';}}
    fetch('/api/mail/microsoft-app/test',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:'{{}}'}})
    .then(r=>r.json()).then(d=>{{
      const el=document.getElementById('ms-app-status');
      if(d.ok) {{
        if(el) el.innerHTML='<span style="color:#28c850;font-weight:600">&#x2713; Erreichbar</span> &middot; Issuer: '+d.issuer.replace('https://','').substring(0,40);
        showToast('Microsoft KIRA App erreichbar \u2713','ok');
      }} else {{
        if(el) el.innerHTML='<span style="color:#c83c3c;font-weight:600">&#x26A0; Fehler</span>: '+d.error;
        showToast('App-Test fehlgeschlagen: '+(d.error||'?'),'fehler');
      }}
      if(btn){{btn.disabled=false;btn.textContent='\u26A1 App-Verbindung testen';}}
    }}).catch(()=>{{
      if(btn){{btn.disabled=false;btn.textContent='\u26A1 App-Verbindung testen';}}
      showToast('Fehler beim Test','fehler');
    }});
  }};
  </script>
</div>

<!-- ── SECTION: AUTOMATIONEN ──────────────────────────────────────────── -->
<div class="es-sec-panel" id="es-sec-automationen">
  <div class="es-sec-h">Automationen</div>
  <div class="es-sec-sub">Automatische Workflows und regelbasierte Aktionen. Diese Funktion befindet sich in Planung.</div>

  <div class="es-grp">
    <div class="es-grp-h">Geplante Funktionen</div>
    <div class="es-row">
      <div class="es-rl">Automatische Nachfass-Mails<div class="es-rd">Erinnerungen automatisch per Mail versenden</div></div>
      <span class="es-badge plan">In Planung</span>
    </div>
    <div class="es-row">
      <div class="es-rl">Regelbasierte Aufgaben<div class="es-rd">Aufgaben automatisch nach Regeln erstellen</div></div>
      <span class="es-badge plan">In Planung</span>
    </div>
    <div class="es-row">
      <div class="es-rl">Zeitgesteuerte Berichte<div class="es-rd">W&ouml;chentliche/monatliche Zusammenfassungen</div></div>
      <span class="es-badge plan">In Planung</span>
    </div>
  </div>
</div>

<!-- ── SECTION: PROTOKOLL & LOGS ──────────────────────────────────────── -->
<div class="es-sec-panel" id="es-sec-protokoll">
  <div class="es-sec-h">Protokoll &amp; Logs</div>
  <div class="es-sec-sub">Runtime-Log, &Auml;nderungsverlauf und Konfigurationsbackup.</div>

  <div class="es-proto-tabs">
    <div class="es-proto-tab act" data-ptab="runtime" onclick="esShowProtoTab('runtime')">Runtime-Log</div>
    <div class="es-proto-tab" data-ptab="changelog" onclick="esShowProtoTab('changelog')">&Auml;nderungsverlauf</div>
    <div class="es-proto-tab" data-ptab="konfiguration" onclick="esShowProtoTab('konfiguration')">Konfiguration</div>
  </div>

  <!-- TAB: RUNTIME-LOG -->
  <div class="es-proto-tab-panel act" id="es-ptab-runtime">
    <div class="es-grp">
      <div class="es-grp-h">Runtime-Log Einstellungen</div>
      <div class="es-row">
        <div class="es-rl">Runtime-Log aktivieren<div class="es-rd">Systemereignisse in SQLite-Datenbank protokollieren</div></div>
        <label class="es-toggle-wrap">
          <input class="es-toggle-inp" type="checkbox" id="cfg-rl-aktiv" {'checked' if rtlog_cfg.get('aktiv', True) else ''}>
          <div class="es-toggle-vis"></div>
        </label>
        <span id="rtlog-live-dot" style="width:8px;height:8px;border-radius:50%;background:{'#5cb85c' if rtlog_cfg.get('aktiv',True) else '#888'};display:inline-block;margin-left:4px"></span>
      </div>
      <div class="es-row">
        <div class="es-rl">UI-Ereignisse loggen<div class="es-rd">Panel-Wechsel, Kira-Aktionen etc.</div></div>
        <label class="es-toggle-wrap">
          <input class="es-toggle-inp" type="checkbox" id="cfg-rl-ui" {'checked' if rtlog_cfg.get('log_ui', True) else ''}>
          <div class="es-toggle-vis"></div>
        </label>
      </div>
      <div class="es-row">
        <div class="es-rl">Kira-Interaktionen loggen<div class="es-rd">Kira-Chat-Anfragen und Antworten</div></div>
        <label class="es-toggle-wrap">
          <input class="es-toggle-inp" type="checkbox" id="cfg-rl-kira" {'checked' if rtlog_cfg.get('log_kira', True) else ''}>
          <div class="es-toggle-vis"></div>
        </label>
      </div>
      <div class="es-row">
        <div class="es-rl">LLM-Aufrufe loggen<div class="es-rd">API-Anfragen an Sprachmodelle</div></div>
        <label class="es-toggle-wrap">
          <input class="es-toggle-inp" type="checkbox" id="cfg-rl-llm" {'checked' if rtlog_cfg.get('log_llm', True) else ''}>
          <div class="es-toggle-vis"></div>
        </label>
      </div>
      <div class="es-row">
        <div class="es-rl">Hintergrund-Jobs loggen<div class="es-rd">Mail-Monitor, Daily-Check etc.</div></div>
        <label class="es-toggle-wrap">
          <input class="es-toggle-inp" type="checkbox" id="cfg-rl-bg" {'checked' if rtlog_cfg.get('log_bg', True) else ''}>
          <div class="es-toggle-vis"></div>
        </label>
      </div>
      <div class="es-row">
        <div class="es-rl">Einstellungs-&Auml;nderungen loggen<div class="es-rd">Speichern von Konfigurationsänderungen</div></div>
        <label class="es-toggle-wrap">
          <input class="es-toggle-inp" type="checkbox" id="cfg-rl-settings" {'checked' if rtlog_cfg.get('log_settings', True) else ''}>
          <div class="es-toggle-vis"></div>
        </label>
      </div>
      <div class="es-row">
        <div class="es-rl">Fehler immer loggen<div class="es-rd">Fehler unabh&auml;ngig von anderen Einstellungen</div></div>
        <label class="es-toggle-wrap">
          <input class="es-toggle-inp" type="checkbox" id="cfg-rl-fehler" {'checked' if rtlog_cfg.get('log_fehler', True) else ''}>
          <div class="es-toggle-vis"></div>
        </label>
      </div>
      <div class="es-row">
        <div class="es-rl">Vollkontext speichern<div class="es-rd">Vollst&auml;ndige Payloads in event_payloads-Tabelle</div></div>
        <label class="es-toggle-wrap">
          <input class="es-toggle-inp" type="checkbox" id="cfg-rl-vollkontext" {'checked' if rtlog_cfg.get('vollkontext_speichern', False) else ''}>
          <div class="es-toggle-vis"></div>
        </label>
      </div>
      <div class="es-row">
        <div class="es-rl">Kira liest Runtime-Log<div class="es-rd">Kira hat Zugriff auf aktuelle System-Ereignisse</div></div>
        <label class="es-toggle-wrap">
          <input class="es-toggle-inp" type="checkbox" id="cfg-rl-kira-lesen" {'checked' if rtlog_cfg.get('kira_lesen', True) else ''}>
          <div class="es-toggle-vis"></div>
        </label>
      </div>
    </div>

    <div class="es-grp">
      <div class="es-grp-h">Log-Typen Filter</div>
      <div style="margin-bottom:8px">
        {_rtlog_type_row("ui","UI-Ereignisse","cfg-rl-type-ui",rtlog_cfg.get("log_ui",True),rl_by_type.get("ui",0))}
        {_rtlog_type_row("kira","Kira-Chat","cfg-rl-type-kira",rtlog_cfg.get("log_kira",True),rl_by_type.get("kira",0))}
        {_rtlog_type_row("llm","LLM-Aufrufe","cfg-rl-type-llm",rtlog_cfg.get("log_llm",True),rl_by_type.get("llm",0))}
        {_rtlog_type_row("system","System/BG","cfg-rl-type-system",rtlog_cfg.get("log_bg",True),rl_by_type.get("system",0))}
        {_rtlog_type_row("settings","Einstellungen","cfg-rl-type-settings",rtlog_cfg.get("log_settings",True),rl_by_type.get("settings",0))}
      </div>
    </div>

    <div class="es-grp" id="rtlog-stats-box">
      <div class="es-grp-h">Statistiken &amp; Aktionen</div>
      <div id="rtlog-stats-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px">
        <div class="es-prev-card"><div class="pc-label">Gesamt</div><div class="pc-val">{rl_total}</div></div>
        <div class="es-prev-card"><div class="pc-label">Heute</div><div class="pc-val">{rl_today}</div></div>
        <div class="es-prev-card"><div class="pc-label">Fehler</div><div class="pc-val" style="color:{'#e84545' if rl_fehler else 'inherit'}">{rl_fehler}</div></div>
        <div class="es-prev-card"><div class="pc-label">DB-Gr&ouml;&szlig;e</div><div class="pc-val" style="font-size:12px">{rl_db_size}</div></div>
      </div>
      <div style="font-size:11px;color:var(--muted);margin-bottom:10px">
        Typen: <strong id="rtlog-typen-summary" style="color:var(--text)">{" · ".join(f'{k}:{v}' for k,v in rl_by_type.items()) or "–"}</strong>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="es-btn" onclick="refreshRtLogStats()">&#x21BB; Aktualisieren</button>
        <button class="es-btn" onclick="exportRtLog()">&#x2197; Export CSV</button>
        <button class="es-btn es-btn-red" onclick="clearRtLog()">DB leeren</button>
      </div>
    </div>

    <div class="es-grp">
      <div class="es-grp-h">Log-Viewer</div>
      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
        <select id="rl-filter-type" class="es-sel" style="min-width:110px">
          <option value="">Alle Typen</option>
          <option value="ui">ui</option>
          <option value="kira">kira</option>
          <option value="llm">llm</option>
          <option value="system">system</option>
          <option value="settings">settings</option>
        </select>
        <select id="rl-filter-status" class="es-sel" style="min-width:110px">
          <option value="">Alle Status</option>
          <option value="ok">ok</option>
          <option value="fehler">fehler</option>
        </select>
        <input id="rl-filter-search" type="text" class="es-inp" placeholder="Suche&hellip;" style="width:140px">
        <button class="es-btn" onclick="loadRuntimeLog(false)">Anzeigen</button>
        <button class="es-btn es-btn-red" style="margin-left:auto" onclick="loadRuntimeLog(false,true)">Nur Fehler</button>
      </div>
      <div id="runtimelog-entries" style="display:none;max-height:360px;overflow-y:auto;border:0.5px solid var(--border);border-radius:8px;background:var(--bg)"></div>
    </div>

    <div class="es-save-bar">
      <button class="es-btn es-btn-pri" onclick="saveSettings()">Speichern</button>
    </div>
  </div>

  <!-- TAB: ÄNDERUNGSVERLAUF -->
  <div class="es-proto-tab-panel" id="es-ptab-changelog">
    <div class="es-grp">
      <div class="es-grp-h">&Auml;nderungsverlauf</div>
      <div class="es-grp-sub">Protokoll aller gespeicherten Einstellungs- und Konfigurationsänderungen.</div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px">
        <div class="es-prev-card"><div class="pc-label">Eintr&auml;ge</div><div class="pc-val">{change_log_count}</div></div>
        <div class="es-prev-card"><div class="pc-label">Letzter Eintrag</div><div class="pc-val" style="font-size:11px">{change_log_last or "–"}</div></div>
        <div class="es-prev-card"><div class="pc-label">Module</div><div class="pc-val">{len(change_log_moduls)}</div></div>
      </div>
      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
        <select id="cl-filter-modul" class="es-sel" style="min-width:110px">
          <option value="">Alle Module</option>
          {"".join(f'<option value="{esc(m)}">{esc(m)}</option>' for m in change_log_moduls)}
        </select>
        <select id="cl-filter-result" class="es-sel" style="min-width:110px">
          <option value="">Alle Resultate</option>
          {"".join(f'<option value="{esc(r)}">{esc(r)}</option>' for r in change_log_results)}
        </select>
        <select id="cl-filter-feature" class="es-sel" style="min-width:130px">
          <option value="">Alle Features</option>
          {"".join(f'<option value="{esc(f)}">{esc(f)}</option>' for f in change_log_features)}
        </select>
        <select id="cl-filter-action" class="es-sel" style="min-width:110px">
          <option value="">Alle Aktionen</option>
          {"".join(f'<option value="{esc(a)}">{esc(a)}</option>' for a in change_log_actions)}
        </select>
        <input id="cl-filter-search" type="text" class="es-inp" placeholder="Suche&hellip;" style="width:130px">
        <button class="es-btn" onclick="loadChangeLog()">Anzeigen</button>
      </div>
      <div id="changelog-entries" style="display:none;max-height:400px;overflow-y:auto;border:0.5px solid var(--border);border-radius:8px;background:var(--bg)"></div>
    </div>
  </div>

  <!-- TAB: KONFIGURATION -->
  <div class="es-proto-tab-panel" id="es-ptab-konfiguration">
    <div class="es-grp">
      <div class="es-grp-h">Konfigurationsbackup</div>
      <div class="es-grp-sub">Exportiere oder importiere die gesamte Systemkonfiguration.</div>
      <div class="es-row">
        <div class="es-rl">Datenbank-Gr&ouml;&szlig;e<div class="es-rd">Aktuelle Gr&ouml;&szlig;e der Aufgaben-Datenbank</div></div>
        <span style="font-size:12px;color:var(--text);font-weight:600">{db_size_str}</span>
      </div>
      <div class="es-row">
        <div class="es-rl">Runtime-Log-DB<div class="es-rd">Gr&ouml;&szlig;e der Runtime-Events-Datenbank</div></div>
        <span style="font-size:12px;color:var(--text);font-weight:600">{rl_db_size}</span>
      </div>
      <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
        <button class="es-btn" onclick="showToast('Export: In Vorbereitung')">&#x2197; Config exportieren</button>
        <button class="es-btn" onclick="showToast('Import: In Vorbereitung')">&#x2199; Config importieren</button>
        <button class="es-btn es-btn-red" onclick="resetConfig()">Zur&uuml;cksetzen</button>
      </div>
    </div>
  </div>

</div><!-- /es-sec-protokoll -->

</div><!-- /es-main -->
</div><!-- /es-ct -->
</div><!-- /es-shell -->"""
    return html

# ── WISSEN Panel ──────────────────────────────────────────────────────────────
def build_wissen(db):
    try:
        rows = db.execute("SELECT * FROM wissen_regeln ORDER BY kategorie, id").fetchall()
    except:
        rows = []
    regeln = [dict(r) for r in rows]

    grouped = {}
    for r in regeln:
        kat = r.get("kategorie","sonstige")
        grouped.setdefault(kat, []).append(r)

    # Korrekturen
    try:
        korr = db.execute("SELECT * FROM corrections ORDER BY erstellt_am DESC LIMIT 20").fetchall()
        korr_list = [dict(r) for r in korr]
    except:
        korr_list = []

    # ── Ebene A: Bibliothek ──
    BIBLIO_CATS = [
        ("stil",     "Stil &amp; Ton"),
        ("preis",    "Preise &amp; Kalkulation"),
        ("technik",  "Technik"),
        ("prozess",  "Prozess"),
        ("fest",     "Gesch&auml;ftsregeln"),
    ]

    def _wissen_card(r, editable=True, with_id=True):
        rid = r['id']
        edit_btn = f"""<button class="btn btn-korr" style="margin-left:8px;font-size:11px;padding:2px 8px;" onclick="editRegel({rid},'{js_esc(r['titel'])}','{js_esc(r['inhalt'])}','{js_esc(r.get('kategorie',''))}')">Bearbeiten</button>""" if editable else ""
        del_btn = f"""<button class="btn btn-ignore" style="margin-left:4px;font-size:11px;padding:2px 8px;" onclick="wissenAction({rid},'loeschen')">Entfernen</button>""" if editable else ""
        id_attr = f' id="wr-{rid}"' if with_id else ""
        iid_attr = f' id="wi-{rid}"' if with_id else ""
        return f"""<div class="wissen-card"{id_attr}>
          <div class="wissen-titel">{esc(r['titel'])}</div>
          <div class="wissen-inhalt"{iid_attr}>{esc(r['inhalt'])}</div>
          <div class="wissen-meta"><span class="muted">{esc(r.get('kategorie',''))}</span>{edit_btn}{del_btn}</div>
        </div>"""

    def _wissen_card_review(r, kat_key):
        rid = r['id']
        label = 'Freigeben' if kat_key=='vorschlag' else 'Best&auml;tigen'
        return f"""<div class="wissen-card {'wissen-vorschlag' if kat_key=='vorschlag' else ''}" id="wr-{rid}">
          <div class="wissen-titel">{esc(r['titel'])}</div>
          <div class="wissen-inhalt" id="wi-{rid}">{esc(r['inhalt'])}</div>
          <div class="wissen-actions">
            <button class="btn btn-done" onclick="wissenAction({rid},'bestaetigen')">{label}</button>
            <button class="btn btn-korr" style="font-size:11px;padding:2px 8px;" onclick="editRegel({rid},'{js_esc(r['titel'])}','{js_esc(r['inhalt'])}','{js_esc(kat_key)}')">Bearbeiten</button>
            <button class="btn btn-ignore" onclick="wissenAction({rid},'ablehnen')">Ablehnen</button>
          </div>
        </div>"""

    # Zwei Haupt-Ebenen als Tabs
    n_biblio = sum(len(grouped.get(k, [])) for k, _ in BIBLIO_CATS)
    n_regeln = len(grouped.get("fest", [])) + len(grouped.get("gelernt", [])) + len(grouped.get("vorschlag", [])) + len(korr_list)

    top_tabs = f"""<div class="wissen-level-tabs">
      <div class="wissen-level-tab active" onclick="showWissenLevel(this,'bibliothek')">Bibliothek ({n_biblio})</div>
      <div class="wissen-level-tab" onclick="showWissenLevel(this,'regelsteuerung')">Regelsteuerung ({n_regeln})</div>
      <div class="wissen-level-tab" onclick="showWissenLevel(this,'neu')">+ Neue Regel</div>
    </div>"""


    # ── Bibliothek-Panel ──
    biblio_tabs = ""
    biblio_panels = ""
    first = True
    for kat_key, kat_label in BIBLIO_CATS:
        items = grouped.get(kat_key, [])
        if not items: continue
        active = " active" if first else ""
        biblio_tabs += f'<div class="wissen-tab{active}" onclick="showWissenTab(\'{kat_key}\',\'wbp\')">{kat_label} ({len(items)})</div>'
        cards = "".join(_wissen_card(r, with_id=False) for r in items)
        biblio_panels += f'<div id="wbp-{kat_key}" class="wissen-panel{active}">{cards}</div>'
        first = False
    # FAQ und Projektwissen als geplant
    biblio_tabs += '<div class="wissen-tab" onclick="showWissenTab(\'faq\',\'wbp\')" style="opacity:.55">FAQ <span class="si-badge planned" style="font-size:9px;padding:0 4px">Geplant</span></div>'
    biblio_tabs += '<div class="wissen-tab" onclick="showWissenTab(\'projektwissen\',\'wbp\')" style="opacity:.55">Projektwissen <span class="si-badge planned" style="font-size:9px;padding:0 4px">Geplant</span></div>'
    biblio_panels += '<div id="wbp-faq" class="wissen-panel"><p class="empty">FAQ-Eintr&auml;ge werden hier angezeigt, sobald sie erstellt werden.</p></div>'
    biblio_panels += '<div id="wbp-projektwissen" class="wissen-panel"><p class="empty">Projektwissen wird hier gesammelt &ndash; aus abgeschlossenen Auftr&auml;gen und Erkenntnissen.</p></div>'
    if not biblio_tabs:
        biblio_tabs = ""
        biblio_panels = "<p class='empty'>Noch keine Bibliotheks-Eintr&auml;ge.</p>"

    bibliothek_html = f'<div class="wissen-tabs">{biblio_tabs}</div>{biblio_panels}'

    # ── Regelsteuerung-Panel ──
    regel_tabs = ""
    regel_panels = ""
    regel_cats = [
        ("fest", "Feste Regeln"),
        ("gelernt", "Gelernt"),
        ("vorschlag", "Vorschl&auml;ge"),
        ("korrekturen", "Korrekturen"),
        ("freigaben", "Freigaben"),
    ]
    first = True
    for kat_key, kat_label in regel_cats:
        if kat_key == "korrekturen":
            items = korr_list
            cnt = len(items)
        elif kat_key == "freigaben":
            items = [r for r in regeln if r.get("status") == "aktiv" and r.get("bestaetigt_am")]
            cnt = len(items)
        else:
            items = grouped.get(kat_key, [])
            cnt = len(items)
        active = " active" if first else ""
        regel_tabs += f'<div class="wissen-tab{active}" onclick="showWissenTab(\'{kat_key}\')">{kat_label} ({cnt})</div>'

        if kat_key == "korrekturen":
            cards = ""
            for c in items:
                cards += f"""<div class="wissen-card wissen-korr">
                  <div class="wissen-titel">Korrektur: {esc(c.get('alter_typ',''))} &rarr; {esc(c.get('neuer_typ',''))}</div>
                  <div class="wissen-inhalt">{esc(c.get('notiz',''))}</div>
                  <div class="wissen-status muted">{esc((c.get('erstellt_am','') or '')[:10])}</div>
                </div>"""
            regel_panels += f'<div id="wissen-korrekturen" class="wissen-panel{active}">{cards or "<p class=\'empty\'>Noch keine Korrekturen.</p>"}</div>'
        elif kat_key == "freigaben":
            cards = "".join(_wissen_card(r, editable=False, with_id=False) for r in items) if items else "<p class='empty'>Noch keine freigegebenen Regeln.</p>"
            regel_panels += f'<div id="wissen-freigaben" class="wissen-panel{active}">{cards}</div>'
        elif kat_key in ("gelernt", "vorschlag"):
            cards = "".join(_wissen_card_review(r, kat_key) for r in items) if items else "<p class='empty'>Keine Eintr&auml;ge.</p>"
            regel_panels += f'<div id="wissen-{kat_key}" class="wissen-panel{active}">{cards}</div>'
        else:
            cards = "".join(_wissen_card(r) for r in items) if items else "<p class='empty'>Keine Eintr&auml;ge.</p>"
            regel_panels += f'<div id="wissen-{kat_key}" class="wissen-panel{active}">{cards}</div>'
        first = False

    regelsteuerung_html = f"""<div style="margin-bottom:8px;font-size:var(--fs-sm);color:var(--muted)">
      <strong>Verbindlich</strong> = Feste Regeln &amp; Freigaben &nbsp;&middot;&nbsp; <strong>Offen</strong> = Gelernt &amp; Vorschl&auml;ge (zur Pr&uuml;fung)
    </div>
    <div class="wissen-tabs">{regel_tabs}</div>{regel_panels}"""

    # ── Neue Regel ──
    neue_html = f"""<div class="wissen-card" style="max-width:560px">
        <div class="wissen-titel" style="margin-bottom:10px">Neue Regel hinzuf&uuml;gen</div>
        <label style="font-size:var(--fs-sm);color:var(--muted);display:block;margin-bottom:3px;">Kategorie:</label>
        <select id="nr-kat" style="width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:var(--radius);padding:8px;font-size:var(--fs-base);margin-bottom:9px;">
          <option value="fest">Feste Regel</option>
          <option value="stil">Stil &amp; Tonalit&auml;t</option>
          <option value="preis">Preise &amp; Kalkulation</option>
          <option value="technik">Technik &amp; Fachwissen</option>
          <option value="prozess">Prozess &amp; Abl&auml;ufe</option>
          <option value="gelernt">Gelernt</option>
          <option value="vorschlag">Vorschlag</option>
        </select>
        <label style="font-size:var(--fs-sm);color:var(--muted);display:block;margin-bottom:3px;">Titel:</label>
        <input type="text" id="nr-titel" placeholder="Kurzer Regeltitel" style="width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:var(--radius);padding:8px;font-size:var(--fs-base);margin-bottom:9px;">
        <label style="font-size:var(--fs-sm);color:var(--muted);display:block;margin-bottom:3px;">Inhalt / Beschreibung:</label>
        <textarea id="nr-inhalt" rows="4" placeholder="Die vollst&auml;ndige Regel oder Anweisung..." style="width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:var(--radius);padding:8px;font-size:var(--fs-base);font-family:inherit;resize:vertical;margin-bottom:9px;"></textarea>
        <button class="btn btn-done" onclick="neueRegel()">Regel speichern</button>
      </div>"""

    total = len(regeln)
    return f"""
    <div style="margin-bottom:12px;font-size:var(--fs-sm);color:var(--muted)">{total} Regeln gesamt</div>
    {top_tabs}
    <div id="wissen-level-bibliothek" class="wissen-level active">{bibliothek_html}</div>
    <div id="wissen-level-regelsteuerung" class="wissen-level">{regelsteuerung_html}</div>
    <div id="wissen-level-neu" class="wissen-level">{neue_html}</div>"""

# ── HAUPT-HTML ────────────────────────────────────────────────────────────────
def generate_html() -> str:
    db = get_db()
    tasks_rows = db.execute("SELECT * FROM tasks WHERE status='offen' ORDER BY prioritaet DESC, datum_mail DESC").fetchall()
    tasks = [dict(r) for r in tasks_rows]
    # Thread-Zählung: wie viele Tasks je thread_id?
    thread_counts = {}
    for t in tasks:
        tid = t.get("thread_id") or ""
        if tid:
            thread_counts[tid] = thread_counts.get(tid, 0) + 1
    for t in tasks:
        tid = t.get("thread_id") or ""
        t["_thread_count"] = thread_counts.get(tid, 1) if tid else 1
    heute = datetime.now().strftime("%d.%m.%Y %H:%M")
    n_ges = len(tasks)
    n_antwort = sum(1 for t in tasks if t.get("kategorie") == "Antwort erforderlich")
    try:
        _cfg_h = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
        _ntfy_h = _cfg_h.get("ntfy", {})
        ntfy_urlaub_modus = _ntfy_h.get("urlaub_modus", False)
    except Exception:
        ntfy_urlaub_modus = False

    alarm_dot = "<span class='alarm-dot'></span>" if n_antwort > 0 else ""

    # Kira context for JS
    kira_ctx = {}
    for t in tasks:
        kira_ctx[t["id"]] = {
            "titel":t.get("titel",""), "betreff":t.get("betreff",""),
            "email":t.get("kunden_email","") or "", "name":t.get("kunden_name","") or "",
            "kategorie":t.get("kategorie",""), "konto":t.get("konto","") or "",
            "datum":str(t.get("datum_mail","") or ""),
            "zusammenfassung":t.get("zusammenfassung","") or "",
            "absender_rolle":t.get("absender_rolle","") or "",
            "empfohlene_aktion":t.get("empfohlene_aktion","") or "",
            "kategorie_grund":t.get("kategorie_grund","") or "",
            "beschreibung":(t.get("beschreibung","") or "")[:500],
            "antwort_noetig": t.get("antwort_noetig",0),
            "message_id": t.get("message_id","") or "",
            "anhang_pfad": t.get("anhaenge_pfad","") or "",
            "prioritaet": t.get("prioritaet","") or "",
            "naechste_erinnerung": t.get("naechste_erinnerung","") or "",
            "notiz": t.get("notiz","") or "",
        }
    prompts_json = {t["id"]:t.get("claude_prompt","") for t in tasks if t.get("claude_prompt")}

    dashboard_html = build_dashboard(tasks, db)
    komm_html      = build_kommunikation(tasks)
    postfach_html  = build_postfach()
    org_html       = build_organisation(db)
    gesch_html     = build_geschaeft(db)
    wissen_html    = build_wissen(db)
    einstell_html  = build_einstellungen()
    db.close()

    # Kira Launcher — SVG-Varianten
    try:
        _kcfg = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
        _kira_cfg2   = _kcfg.get("kira", {})
        _kv          = _kira_cfg2.get("launcher_variant", "B")
        kira_size        = _kira_cfg2.get("size", 112)
        kira_prox_radius = _kira_cfg2.get("prox_radius", 0.5)
        kira_bounce_dist = _kira_cfg2.get("bounce_dist", 130)
        kira_idle        = _kira_cfg2.get("idle_mode", True)
        kira_idle_delay  = _kira_cfg2.get("idle_delay", 10)
    except Exception:
        _kv = "B"
        kira_size = 112
        kira_prox_radius = 0.5
        kira_bounce_dist = 130
        kira_idle = True
        kira_idle_delay = 10
    _kira_svg_a = '<svg class="kira-char-svg" id="kiraCharSVG" width="96" height="96" viewBox="0 0 100 100" style="overflow:visible"><defs><radialGradient id="kFGA" cx="35%" cy="28%" r="72%"><stop offset="0%" stop-color="#ffffff"/><stop offset="60%" stop-color="#EAE8FF"/><stop offset="100%" stop-color="#C8C2F8"/></radialGradient><radialGradient id="kPGA" cx="30%" cy="28%" r="72%"><stop offset="0%" stop-color="#7B6FE8"/><stop offset="100%" stop-color="#3A2F9E"/></radialGradient></defs><circle cx="50" cy="50" r="56" fill="none" stroke="#7B68EE" stroke-width="2.5" opacity="0" id="kiraGlowHalo"/><ellipse id="kiraShadow" cx="50" cy="97" rx="28" ry="4.5" fill="#3A2A9E" opacity="0.12"><animate attributeName="rx" values="28;22;28" dur="4s" repeatCount="indefinite"/></ellipse><g class="kira-float" id="kiraFloatGroup"><circle cx="50" cy="50" r="42" fill="url(#kFGA)" stroke="#D4D0FF" stroke-width="0.8"/><ellipse cx="34" cy="46" rx="9" ry="9.5" fill="#E8E5FF" id="kiraIrisL"/><ellipse cx="66" cy="46" rx="9" ry="9.5" fill="#E8E5FF" id="kiraIrisR"/><circle cx="34" cy="47" r="5" fill="url(#kPGA)" id="kiraPupilL"/><circle cx="66" cy="47" r="5" fill="url(#kPGA)" id="kiraPupilR"/><circle cx="31.5" cy="44.5" r="1.9" fill="#fff" opacity="0.85"/><circle cx="63.5" cy="44.5" r="1.9" fill="#fff" opacity="0.85"/><path d="M38 62 Q50 70 62 62" fill="none" stroke="#A8A0F0" stroke-width="2" stroke-linecap="round" id="kiraMouth"/></g></svg>'
    _kira_svg_b = '<svg class="kira-char-svg" id="kiraCharSVG" width="96" height="96" viewBox="0 0 100 100" style="overflow:visible"><defs><radialGradient id="kFG" cx="35%" cy="28%" r="75%"><stop offset="0%" stop-color="#ffffff"/><stop offset="40%" stop-color="#F0EEFF"/><stop offset="75%" stop-color="#C4BCFF"/><stop offset="100%" stop-color="#9B8FE8"/></radialGradient><radialGradient id="kHG" cx="30%" cy="22%" r="45%"><stop offset="0%" stop-color="#ffffff" stop-opacity="0.9"/><stop offset="100%" stop-color="#ffffff" stop-opacity="0"/></radialGradient><radialGradient id="kPG" cx="28%" cy="25%" r="75%"><stop offset="0%" stop-color="#8B7AEE"/><stop offset="45%" stop-color="#5340C8"/><stop offset="100%" stop-color="#2A1F7A"/></radialGradient><radialGradient id="kIG" cx="35%" cy="30%" r="70%"><stop offset="0%" stop-color="#E0DCFF"/><stop offset="100%" stop-color="#B8B0F5"/></radialGradient><radialGradient id="kSG" cx="50%" cy="15%" r="85%"><stop offset="0%" stop-color="#1a1040" stop-opacity="0"/><stop offset="70%" stop-color="#1a1040" stop-opacity="0"/><stop offset="100%" stop-color="#1a1040" stop-opacity="0.28"/></radialGradient></defs><circle cx="50" cy="50" r="56" fill="none" stroke="#7B68EE" stroke-width="3" opacity="0" id="kiraGlowHalo"/><ellipse id="kiraShadow" cx="50" cy="97" rx="30" ry="5" fill="#3A2A9E" opacity="0.15"><animate attributeName="rx" values="30;24;30" dur="4s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.15;0.07;0.15" dur="4s" repeatCount="indefinite"/></ellipse><g class="kira-float" id="kiraFloatGroup"><ellipse cx="50" cy="49" rx="43" ry="45" fill="url(#kFG)" stroke="#D0CAFF" stroke-width="0.8"/><ellipse cx="37" cy="32" rx="18" ry="12" fill="url(#kHG)"/><ellipse cx="22" cy="63" rx="10" ry="5.5" fill="#FF9EC8" opacity="0.22"/><ellipse cx="78" cy="63" rx="10" ry="5.5" fill="#FF9EC8" opacity="0.22"/><ellipse cx="33" cy="46" rx="13" ry="14" fill="url(#kIG)" id="kiraIrisL"/><ellipse cx="67" cy="46" rx="13" ry="14" fill="url(#kIG)" id="kiraIrisR"/><circle cx="33" cy="47" r="8.5" fill="url(#kPG)" id="kiraPupilL"/><circle cx="67" cy="47" r="8.5" fill="url(#kPG)" id="kiraPupilR"/><circle cx="29.5" cy="43" r="3.2" fill="#fff" opacity="0.85"/><circle cx="63.5" cy="43" r="3.2" fill="#fff" opacity="0.85"/><circle cx="34.5" cy="49.5" r="1.4" fill="#fff" opacity="0.45"/><circle cx="68.5" cy="49.5" r="1.4" fill="#fff" opacity="0.45"/><path d="M36 67 Q50 78 64 67" fill="none" stroke="#9B8FE8" stroke-width="2.5" stroke-linecap="round" id="kiraMouth"/><ellipse cx="50" cy="49" rx="43" ry="45" fill="url(#kSG)"/></g></svg>'
    _kira_svg_c = '<svg class="kira-char-svg" id="kiraCharSVG" width="96" height="96" viewBox="0 0 100 100" style="overflow:visible"><defs><radialGradient id="kFGC" cx="32%" cy="25%" r="75%"><stop offset="0%" stop-color="#4A45A8"/><stop offset="50%" stop-color="#1E1B5A"/><stop offset="100%" stop-color="#0A0820"/></radialGradient><radialGradient id="kEGC" cx="28%" cy="22%" r="75%"><stop offset="0%" stop-color="#A0EDFF"/><stop offset="55%" stop-color="#48C8F0"/><stop offset="100%" stop-color="#1A8EC4"/></radialGradient><radialGradient id="kHGC" cx="28%" cy="20%" r="50%"><stop offset="0%" stop-color="#ffffff" stop-opacity="0.15"/><stop offset="100%" stop-color="#ffffff" stop-opacity="0"/></radialGradient></defs><circle cx="50" cy="50" r="56" fill="none" stroke="#5588CC" stroke-width="3" opacity="0" id="kiraGlowHalo"/><circle cx="50" cy="50" r="46" fill="none" stroke="#4A90D9" stroke-width="0.8" opacity="0.35"><animate attributeName="r" values="46;51;46" dur="2.5s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.35;0.08;0.35" dur="2.5s" repeatCount="indefinite"/></circle><ellipse id="kiraShadow" cx="50" cy="97" rx="28" ry="5" fill="#0A0820" opacity="0.3"><animate attributeName="rx" values="28;22;28" dur="4s" repeatCount="indefinite"/></ellipse><g class="kira-float" id="kiraFloatGroup"><circle cx="50" cy="50" r="42" fill="url(#kFGC)"/><ellipse cx="34" cy="32" rx="18" ry="10" fill="url(#kHGC)"/><ellipse cx="35" cy="47" rx="8" ry="8.5" fill="#2A4080" opacity="0.4" id="kiraIrisL"/><ellipse cx="65" cy="47" rx="8" ry="8.5" fill="#2A4080" opacity="0.4" id="kiraIrisR"/><circle cx="35" cy="47.5" r="6" fill="url(#kEGC)" id="kiraPupilL"/><circle cx="65" cy="47.5" r="6" fill="url(#kEGC)" id="kiraPupilR"/><circle cx="32" cy="44.5" r="2.5" fill="#fff" opacity="0.75"/><circle cx="62" cy="44.5" r="2.5" fill="#fff" opacity="0.75"/><path d="M38 63 Q50 71 62 63" fill="none" stroke="#5B9BD4" stroke-width="2" stroke-linecap="round" id="kiraMouth"/></g></svg>'
    _kira_svg_init = _kira_svg_b if _kv == 'B' else (_kira_svg_a if _kv == 'A' else _kira_svg_c)

    return f"""<!DOCTYPE html>
<html lang="de" data-theme="light">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kira – Assistenz</title>
<style>
{CSS}
</style>
</head>
<body>
<div id="_diag" style="position:fixed;top:54px;left:50%;transform:translateX(-50%);z-index:99999;background:#dc4a4a;color:#fff;padding:10px 20px;border-radius:8px;font-size:13px;font-weight:600;pointer-events:none">&#x26A0; JavaScript l&#228;uft NICHT &#8212; Browser-Konsole (F12) pr&#252;fen</div>
<div class="sidebar-overlay" id="sidebarOverlay" onclick="closeMobileSidebar()"></div>
<div class="app-shell" id="appShell">

<!-- Sidebar -->
<aside class="sidebar" id="sidebar">
  <div class="sidebar-brand">
    <div class="sidebar-logo" id="sidebarLogo">K</div>
    <div class="sidebar-brand-text">
      <span class="sidebar-brand-name" id="brandName">Kira</span>
      <span class="sidebar-brand-sub" id="brandSub">Assistenz</span>
    </div>
    <button class="sb-toggle-btn" id="sbToggleBtn" onclick="toggleSidebar()" title="Sidebar ein-/ausklappen">
      <svg id="sidebarToggleIcon" width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="1.5" y="1.5" width="13" height="13" rx="2" stroke="currentColor" stroke-width="1.5"/><line x1="5.5" y1="1.5" x2="5.5" y2="14.5" stroke="currentColor" stroke-width="1.5"/></svg>
    </button>
  </div>
  <div class="sb-resize-handle" id="sidebarResizeHandle"></div>
  <nav class="sidebar-nav">
    <div class="sidebar-group">
      <div class="sidebar-item active" id="nav-dashboard" onclick="showPanel('dashboard')" data-label="Start">
        <span class="si-icon">&#x2302;</span><span class="si-label">Start</span>
        {"<span class='si-badge' style='background:rgba(220,74,74,.12);color:var(--danger);border-color:rgba(220,74,74,.25)'>" + str(n_antwort) + "</span>" if n_antwort > 0 else ""}
      </div>
      <div class="sidebar-item" id="nav-kommunikation" onclick="showPanel('kommunikation')" data-label="Kommunikation">
        <span class="si-icon">&#x2709;</span><span class="si-label">Kommunikation</span>
      </div>
      <div class="sidebar-item" id="nav-postfach" onclick="showPanel('postfach')" data-label="Postfach">
        <span class="si-icon">&#x1F4EC;</span><span class="si-label">Postfach</span><span id="nav-postfach-badge" class="si-badge" style="display:none;background:rgba(200,60,60,.12);color:#c83c3c;border-color:rgba(200,60,60,.25);font-size:11px"></span>
      </div>
      <div class="sidebar-item" id="nav-organisation" onclick="showPanel('organisation')" data-label="Organisation">
        <span class="si-icon">&#x1F4C5;</span><span class="si-label">Organisation</span>
      </div>
      <div class="sidebar-item" id="nav-geschaeft" onclick="showPanel('geschaeft')" data-label="Gesch&#228;ft">
        <span class="si-icon">&#x1F4B0;</span><span class="si-label">Gesch&auml;ft</span>
      </div>
    </div>
    <div class="sidebar-group">
      <div class="sidebar-group-label">Module</div>
      <div class="sidebar-item planned" id="nav-kunden" onclick="showPanel('kunden')" data-label="Kunden">
        <span class="si-icon">&#x1F465;</span><span class="si-label">Kunden</span>
        <span class="si-badge planned">Geplant</span>
      </div>
      <div class="sidebar-item planned" id="nav-marketing" onclick="showPanel('marketing')" data-label="Marketing">
        <span class="si-icon">&#x1F4E3;</span><span class="si-label">Marketing</span>
        <span class="si-badge planned">Geplant</span>
      </div>
      <div class="sidebar-item planned" id="nav-social" onclick="showPanel('social')" data-label="Social / DMs">
        <span class="si-icon">&#x1F4AC;</span><span class="si-label">Social / DMs</span>
        <span class="si-badge planned">Geplant</span>
      </div>
      <div class="sidebar-item" id="nav-wissen" onclick="showPanel('wissen')" data-label="Wissen">
        <span class="si-icon">&#x1F4DA;</span><span class="si-label">Wissen</span>
      </div>
      <div class="sidebar-item planned" id="nav-automationen" onclick="showPanel('automationen')" data-label="Automationen">
        <span class="si-icon">&#x26A1;</span><span class="si-label">Automationen</span>
        <span class="si-badge planned">Geplant</span>
      </div>
      <div class="sidebar-item planned" id="nav-analysen" onclick="showPanel('analysen')" data-label="Analysen">
        <span class="si-icon">&#x1F4CA;</span><span class="si-label">Analysen</span>
        <span class="si-badge planned">Geplant</span>
      </div>
    </div>
  </nav>
  <div class="sidebar-bottom">
    <div class="sidebar-item" id="nav-kira-aktivitaeten" onclick="showPanel('kira-aktivitaeten');loadKiraAktivitaeten()" data-label="Kira-Aktivitaeten">
      <span class="si-icon">&#x1F916;</span><span class="si-label">Kira-Log</span>
    </div>
    <div class="sidebar-item" id="nav-protokoll" onclick="showPanel('protokoll');loadProtokoll()" data-label="Protokoll">
      <span class="si-icon">&#x1F4CB;</span><span class="si-label">Protokoll</span>
      <span class="si-badge" id="proto-fehler-badge" style="display:none;background:rgba(220,74,74,.12);color:var(--danger);border-color:rgba(220,74,74,.25)"></span>
    </div>
    <div class="sidebar-item" id="nav-einstellungen" onclick="showPanel('einstellungen')" data-label="Einstellungen">
      <span class="si-icon">&#x2699;</span><span class="si-label">Einstellungen</span>
    </div>
  </div>
</aside>

<!-- Main -->
<div class="main-area">
  <div class="header">
    <div class="header-left">
      <button class="mobile-burger" onclick="openMobileSidebar()">&#x2630;</button>
      <input class="header-search" placeholder="&#x2315; Suche in allen Modulen&hellip;" onfocus="this.select()" id="globalSearch" autocomplete="off">
    </div>
    <div class="header-right">
      <div class="top-chip" onclick="toggleKiraQuick()" title="Kira Quick Actions">&#x26A1; Quick Actions</div>
      {'<div class="top-chip" style="background:#e84545;color:#fff;border-color:#c83030;font-weight:700" title="Urlaubsmodus aktiv — Push-Benachrichtigungen deaktiviert" onclick="esShowSec(\'benachrichtigungen\');showPanel(\'einstellungen\')">&#x1F3D6; Urlaub</div>' if ntfy_urlaub_modus else ''}
      <div class="top-chip ok" id="monitorStatusChip"><span class="chip-dot"></span><span id="monitorStatusText">Verbunden</span></div>
      <div class="top-chip" id="mailApproveChip" onclick="openMailApproveModal()" title="Mail wartet auf Freigabe" style="display:none;background:#f59e0b;color:#fff;border-color:#d97706;cursor:pointer;font-weight:700">&#x2709; <span id="mailApproveCount">0</span> Freigabe</div>
      <div class="top-chip" onclick="showPanel('kommunikation')" title="Offene Aufgaben">&#x1F514; <span id="headerBadgeCount">{n_ges}</span> offen</div>
      <div class="header-avatar" title="Einstellungen" onclick="showPanel('einstellungen')">K</div>
      <button class="btn btn-muted btn-xs" id="updateBtn" onclick="serverNeustart()" title="Server komplett neu starten (alle Instanzen beenden)" style="border-radius:6px">&#x21BB; Neustart</button>
    </div>
  </div>

  <div class="panel active" id="panel-dashboard">{dashboard_html}</div>
  <div class="panel" id="panel-kommunikation">{komm_html}</div>
  <div class="panel pf-panel" id="panel-postfach">{postfach_html}</div>
  <div class="panel" id="panel-organisation">{org_html}</div>
  <div class="panel" id="panel-geschaeft">{gesch_html}</div>
  <div class="panel" id="panel-wissen">{wissen_html}</div>
  <div class="panel" id="panel-einstellungen">{einstell_html}</div>
  <div class="panel" id="panel-kira-aktivitaeten">
    <div class="page-header">
      <h1 class="page-title">&#x1F916; Kira-Aktivit&auml;ten</h1>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <select id="kira-akt-seit" class="proto-filter" onchange="loadKiraAktivitaeten()">
          <option value="24h">Letzte 24 Stunden</option>
          <option value="7d">Letzte 7 Tage</option>
          <option value="30d">Letzte 30 Tage</option>
        </select>
        <select id="kira-akt-typ" class="proto-filter" onchange="loadKiraAktivitaeten()">
          <option value="">Alle Aktionen</option>
          <option value="kira_autonom">&#x1F916; Autonom</option>
          <option value="kira_vorschlag">&#x1F464; Best&auml;tigt</option>
        </select>
        <button class="btn btn-sec btn-xs" onclick="loadKiraAktivitaeten()">&#x21BB; Aktualisieren</button>
      </div>
    </div>
    <div id="kira-akt-list" style="margin-top:12px"></div>
  </div>
  <div class="panel" id="panel-protokoll">
    <div class="page-header">
      <h1 class="page-title">&#x1F4CB; Aktivit&auml;tsprotokoll</h1>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <select id="proto-filter-bereich" class="proto-filter" onchange="loadProtokoll()">
          <option value="">Alle Bereiche</option>
          <option value="Server">Server</option>
          <option value="Mail">Mail</option>
          <option value="Klassifizierung">Klassifizierung</option>
          <option value="Task">Task</option>
          <option value="Kira">Kira</option>
          <option value="LLM">LLM</option>
        </select>
        <select id="proto-filter-status" class="proto-filter" onchange="loadProtokoll()">
          <option value="">Alle Status</option>
          <option value="ok">OK</option>
          <option value="warnung">Warnung</option>
          <option value="fehler">Fehler</option>
        </select>
        <button class="btn btn-sec btn-xs" onclick="loadProtokoll()">&#x21BB; Aktualisieren</button>
        <button class="btn btn-sec btn-xs" onclick="copyProtoCSV()" title="Als CSV kopieren">&#x1F4CB; Kopieren</button>
      </div>
    </div>
    <div id="proto-stats" class="proto-stats-bar"></div>
    <div class="proto-table-wrap">
      <table class="proto-table" id="proto-table">
        <thead><tr>
          <th style="width:140px">Zeit</th>
          <th style="width:110px">Bereich</th>
          <th style="width:160px">Aktion</th>
          <th>Details</th>
          <th style="width:60px">Status</th>
          <th style="width:70px">Dauer</th>
        </tr></thead>
        <tbody id="proto-body"><tr><td colspan=6 style="text-align:center;padding:40px;color:var(--muted)">Wird geladen&hellip;</td></tr></tbody>
      </table>
    </div>
    <div id="proto-load-more" style="text-align:center;padding:16px;display:none">
      <button class="btn btn-sec btn-xs" onclick="loadProtokoll(true)">Weitere laden</button>
    </div>
  </div>

  <!-- Geplante Module gem&auml;&szlig; Prompt_04 -->
  <div class="panel" id="panel-kunden">
    <div class="planned-shell">
      <div class="planned-shell-icon">&#x1F465;</div>
      <div class="planned-shell-title">Kunden</div>
      <div class="planned-shell-desc">Zentrale Kundenverwaltung mit 360&deg;-Sicht auf jeden Kontakt.</div>
      <div class="planned-badge">&#x1F6A7; In Planung</div>
      <div class="planned-features">
        <div class="planned-feature-item">&#x2192; Timeline &ndash; Chronologischer Verlauf aller Interaktionen</div>
        <div class="planned-feature-item">&#x2192; Pipeline &ndash; Leads und Anfragen im Prozess verfolgen</div>
        <div class="planned-feature-item">&#x2192; Potenzial &ndash; Gesch&auml;ftspotenzial je Kunde bewerten</div>
        <div class="planned-feature-item">&#x2192; Zahlungsverhalten &ndash; Zahlungsmoral und -muster</div>
        <div class="planned-feature-item">&#x2192; Offene Themen &ndash; Unbeantwortete Fragen, laufende Vorg&auml;nge</div>
      </div>
    </div>
  </div>
  <div class="panel" id="panel-marketing">
    <div class="planned-shell">
      <div class="planned-shell-icon">&#x1F4E3;</div>
      <div class="planned-shell-title">Marketing</div>
      <div class="planned-shell-desc">Content-Planung, Kampagnen und Reichweite &ndash; mit KI-Unterst&uuml;tzung durch Kira.</div>
      <div class="planned-badge">&#x1F6A7; In Planung</div>
      <div class="planned-features">
        <div class="planned-feature-item">&#x2192; Content-Pipeline &ndash; Ideen, Entw&uuml;rfe, Ver&ouml;ffentlichungen</div>
        <div class="planned-feature-item">&#x2192; Themenideen aus Projekten &ndash; Automatisch aus laufenden Auftr&auml;gen</div>
        <div class="planned-feature-item">&#x2192; Kampagnen &ndash; Planung und Auswertung</div>
        <div class="planned-feature-item">&#x2192; Newsletter &ndash; Versand und Performance</div>
        <div class="planned-feature-item">&#x2192; Redaktionsplanung &ndash; Kalender f&uuml;r Social und Blog</div>
      </div>
    </div>
  </div>
  <div class="panel" id="panel-social">
    <div class="planned-shell">
      <div class="planned-shell-icon">&#x1F4AC;</div>
      <div class="planned-shell-title">Social / DMs</div>
      <div class="planned-shell-desc">Direktnachrichten aus sozialen Kan&auml;len zentral verwalten und mit Kira besprechen.</div>
      <div class="planned-badge">&#x1F6A7; In Planung</div>
      <div class="planned-features">
        <div class="planned-feature-item">&#x2192; DM-Eingang &ndash; WhatsApp, Instagram, Telegram an einem Ort</div>
        <div class="planned-feature-item">&#x2192; Schnellantworten &ndash; Vorlagen und KI-Vorschl&auml;ge</div>
        <div class="planned-feature-item">&#x2192; Lead-Zuordnung &ndash; DMs automatisch Kunden zuweisen</div>
        <div class="planned-feature-item">&#x2192; Terminbezug &ndash; Termine direkt aus Nachrichten erkennen</div>
        <div class="planned-feature-item">&#x2192; Plattformbezug &ndash; Quelle und Kanal sichtbar</div>
      </div>
    </div>
  </div>
  <div class="panel" id="panel-automationen">
    <div class="planned-shell">
      <div class="planned-shell-icon">&#x26A1;</div>
      <div class="planned-shell-title">Automationen</div>
      <div class="planned-shell-desc">Wiederkehrende Abl&auml;ufe automatisieren &ndash; von Follow-ups bis Eskalationen.</div>
      <div class="planned-badge">&#x1F6A7; In Planung</div>
      <div class="planned-features">
        <div class="planned-feature-item">&#x2192; Mail-Follow-up &ndash; Automatische Nachfass-Erinnerungen</div>
        <div class="planned-feature-item">&#x2192; Erinnerungsregeln &ndash; Zeitbasierte Wiedervorlagen</div>
        <div class="planned-feature-item">&#x2192; Eskalationen &ndash; Automatisch bei &Uuml;berf&auml;lligkeit</div>
        <div class="planned-feature-item">&#x2192; Workflow-Bausteine &ndash; Wiederverwendbare Abl&auml;ufe</div>
        <div class="planned-feature-item">&#x2192; Trigger / Bedingungen &ndash; Wenn-Dann-Regeln konfigurieren</div>
      </div>
    </div>
  </div>
  <div class="panel" id="panel-analysen">
    <div class="planned-shell">
      <div class="planned-shell-icon">&#x1F4CA;</div>
      <div class="planned-shell-title">Analysen</div>
      <div class="planned-shell-desc">Gesch&auml;ftsdaten auswerten, Muster erkennen und Entscheidungen datenbasiert treffen.</div>
      <div class="planned-badge">&#x1F6A7; In Planung</div>
      <div class="planned-features">
        <div class="planned-feature-item">&#x2192; Umsatzfragen &ndash; Volumen, Entwicklung, Vergleiche</div>
        <div class="planned-feature-item">&#x2192; Angebotsquote &ndash; Annahme-/Ablehnungsrate</div>
        <div class="planned-feature-item">&#x2192; Lead-Scoring &ndash; Qualit&auml;t und Konversion</div>
        <div class="planned-feature-item">&#x2192; Kanalwirkung &ndash; Welcher Kanal bringt Auftr&auml;ge</div>
        <div class="planned-feature-item">&#x2192; Preisentwicklung &ndash; Trends bei Leistungen</div>
        <div class="planned-feature-item">&#x2192; Performance-Reporting &ndash; Automatische KI-Reports</div>
      </div>
    </div>
  </div>

<!-- Bewertung Modal -->
<div class="modal-ov" id="geschBewertModal">
  <div class="modal">
    <h3>Klassifizierung bewerten</h3>
    <input type="hidden" id="gb-id">
    <div style="margin-bottom:8px;color:var(--muted);font-size:12px">Warum ist diese Klassifizierung falsch?</div>
    <textarea id="gb-grund" rows="3" placeholder="z.B. Das ist keine Routine-Zahlung, ich muss das aktiv bezahlen..."></textarea>
    <div class="modal-actions">
      <button class="btn btn-sm btn-warn" onclick="submitGeschBewertung()">Bewertung senden</button>
      <button class="btn btn-sm btn-muted" onclick="closeGeschBewertung()">Abbrechen</button>
    </div>
  </div>
</div>

<!-- Mail Lesen Modal -->
<div class="modal-ov" id="mailReadModal">
  <div class="modal" style="max-width:640px;max-height:80vh;overflow-y:auto">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
      <h3 id="mr-betreff" style="flex:1;margin:0"></h3>
      <button class="btn btn-tiny btn-muted" onclick="closeMailRead()" style="margin-left:10px">&times;</button>
    </div>
    <div id="mr-meta" style="font-size:12px;color:var(--muted);margin-bottom:10px"></div>
    <div id="mr-attachments" style="margin-bottom:10px"></div>
    <div id="mr-body" style="white-space:pre-wrap;font-size:13px;line-height:1.6;color:var(--text);max-height:55vh;overflow-y:auto;padding:10px;background:rgba(0,0,0,.3);border-radius:8px"></div>
  </div>
</div>

<!-- Kira Interaktions-Modal (Statusänderungen) -->
<div class="modal-ov" id="kiraInteraktModal">
  <div class="modal" style="max-width:480px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <h3 id="ki-title" style="margin:0;color:var(--kl)">Kira fragt nach</h3>
      <button class="btn btn-tiny btn-muted" onclick="closeKiraInterakt()">&times;</button>
    </div>
    <div id="ki-context" style="font-size:12px;color:var(--muted);margin-bottom:12px;padding:8px;background:var(--accent-bg);border-radius:8px"></div>
    <div id="ki-fields" style="display:flex;flex-direction:column;gap:10px"></div>
    <input type="hidden" id="ki-type">
    <input type="hidden" id="ki-id">
    <input type="hidden" id="ki-action">
    <div class="modal-actions" style="margin-top:14px">
      <button class="btn btn-done" onclick="submitKiraInterakt()">Speichern &amp; Erledigen</button>
      <button class="btn btn-sm btn-muted" onclick="skipKiraInterakt()">Ohne Angaben fortfahren</button>
    </div>
  </div>
</div>

<!-- Kira Launcher -->
<button class="kira-fab" id="kiraFab" onclick="toggleKiraQuick()" title="Kira Assistenz" data-variant="{_kv}" data-size="{kira_size}" data-prox-radius="{kira_prox_radius}" data-bounce-dist="{kira_bounce_dist}" data-idle-enabled="{'true' if kira_idle else 'false'}" data-idle-delay="{kira_idle_delay}">
  {_kira_svg_init}
  <span class="kira-fab-status" id="kiraFabStatus"></span>
</button>
<!-- Kira SVG-Vorlagen (alle 3 Varianten für JS-Wechsel) -->
<div id="kira-tmpl-A" style="display:none">{_kira_svg_a}</div>
<div id="kira-tmpl-B" style="display:none">{_kira_svg_b}</div>
<div id="kira-tmpl-C" style="display:none">{_kira_svg_c}</div>

<!-- Kira Quick Panel (Modus B) -->
<div class="kq-panel" id="kiraQuick">
  <div class="kq-header">
    <div class="kq-logo"><span class="kq-logo-k">K</span><span class="kq-logo-l">Kira</span></div>
    <div class="kq-htext">
      <div class="kq-htitle">Kira Assistenz</div>
      <div class="kq-hstatus"><span class="kq-hstatus-dot"></span>Bereit &middot; Anthropic Claude</div>
    </div>
    <div class="kq-close" onclick="closeKiraQuick()">&#x2715;</div>
  </div>
  <div class="kq-actions">
    <div class="kq-item" onclick="openKiraWorkspace('chat')">
      <div class="kq-icon purple">?</div>
      <div class="kq-body"><div class="kq-title">Frage stellen</div><div class="kq-sub">Freie Frage an Kira &mdash; zu allem im System</div></div>
      <span class="kq-arrow">&#x203A;</span>
    </div>
    <div class="kq-item" onclick="openKiraWorkspace('aufgabe')">
      <div class="kq-icon amber">&#x2610;</div>
      <div class="kq-body"><div class="kq-title">Aufgabe besprechen</div><div class="kq-sub">Aktuelle Aufgabe mit Kontext &ouml;ffnen</div></div>
      <span class="kq-arrow">&#x203A;</span>
    </div>
    <div class="kq-item" onclick="openKiraWorkspace('rechnung')">
      <div class="kq-icon green">&#x20AC;</div>
      <div class="kq-body"><div class="kq-title">Rechnung pr&uuml;fen</div><div class="kq-sub">Eingangs- oder Ausgangsrechnung analysieren</div></div>
      <span class="kq-arrow">&#x203A;</span>
    </div>
    <div class="kq-item" onclick="openKiraWorkspace('angebot')">
      <div class="kq-icon blue">&#x270E;</div>
      <div class="kq-body"><div class="kq-title">Angebot pr&uuml;fen</div><div class="kq-sub">Angebotsstatus, Nachfass oder Entwurf</div></div>
      <span class="kq-arrow">&#x203A;</span>
    </div>
    <div class="kq-item" onclick="openKiraWorkspace('kunde')">
      <div class="kq-icon coral">&#x265F;</div>
      <div class="kq-body"><div class="kq-title">Kunde &ouml;ffnen</div><div class="kq-sub">Kundendaten, Historie, offene Themen</div></div>
      <span class="kq-arrow">&#x203A;</span>
    </div>
    <div class="kq-item" onclick="openKiraWorkspace('suche')">
      <div class="kq-icon teal">&#x2315;</div>
      <div class="kq-body"><div class="kq-title">Suche</div><div class="kq-sub">In Mails, Aufgaben, Wissen, Gesch&auml;ft suchen</div></div>
      <span class="kq-arrow">&#x203A;</span>
    </div>
    <div class="kq-item" onclick="openKiraWorkspace('historie')">
      <div class="kq-icon gray">&#x21BB;</div>
      <div class="kq-body"><div class="kq-title">Letzte Verl&auml;ufe</div><div class="kq-sub">Gespeicherte Kira-Gespr&auml;che wieder &ouml;ffnen</div></div>
      <span class="kq-arrow">&#x203A;</span>
    </div>
  </div>
  <div class="kq-footer">
    <input class="kq-input" id="kqInput" type="text" placeholder="Direkt an Kira schreiben&hellip;"
      onkeydown="if(event.key==='Enter')kqDirectSend()">
    <button class="kq-send" onclick="kqDirectSend()">&#x2191;</button>
  </div>
</div>

<!-- Kira Workspace (Modus C) — voller Assistenz-Arbeitsbereich -->
<div class="kira-workspace-overlay" id="kiraWorkspace">
  <div class="kw-shell">
    <div class="kw-header">
      <div class="kw-header-left">
        <div class="kw-logo">K</div>
        <div>
          <div class="kw-title">Kira</div>
          <div class="kw-sub">KI-Assistenz &middot; Anthropic Claude</div>
        </div>
      </div>
      <div class="kw-header-right">
        <button class="btn btn-xs btn-muted" onclick="newKiraChat()">Neuer Chat</button>
        <button class="btn btn-xs btn-muted" onclick="toggleKiraTools()">Werkzeuge</button>
        <button class="kira-close" onclick="closeKiraWorkspace()">&times;</button>
      </div>
    </div>
    <div class="kw-body">
      <!-- Links: Kontexte / Verläufe -->
      <div class="kw-ctx-panel" id="kwCtxPanel">
        <div class="kw-ctx-hdr">
          <div class="kw-ctx-hdr-t">Kontexte &amp; Verl&auml;ufe</div>
          <input class="kw-ctx-search" type="text" placeholder="&#x2315; Kontext suchen&hellip;">
        </div>
        <div class="kw-ctx-section">
          <div class="kw-ctx-sec-h">Modus</div>
          <div class="kw-ctx-item active" onclick="showKTab('chat')" data-tab="chat">
            <span class="kw-ctx-chip offer">Chat</span>
            <div class="kw-ctx-body"><div class="kw-ctx-title">Freier Chat</div><div class="kw-ctx-sub">Direkt mit Kira sprechen</div></div>
          </div>
          <div class="kw-ctx-item" onclick="showKTab('aufgaben')" data-tab="aufgaben">
            <span class="kw-ctx-chip task">Aufgaben</span>
            <div class="kw-ctx-body"><div class="kw-ctx-title">Offene Aufgaben</div><div class="kw-ctx-sub">Priorisiert &amp; kommentiert</div></div>
          </div>
          <div class="kw-ctx-item" onclick="showKTab('muster')" data-tab="muster">
            <span class="kw-ctx-chip inv">Muster</span>
            <div class="kw-ctx-body"><div class="kw-ctx-title">Erkannte Muster</div><div class="kw-ctx-sub">Zahlungsverhalten, Quoten</div></div>
          </div>
          <div class="kw-ctx-item" onclick="showKTab('kwissen')" data-tab="kwissen">
            <span class="kw-ctx-chip know">Wissen</span>
            <div class="kw-ctx-body"><div class="kw-ctx-title">Gelerntes</div><div class="kw-ctx-sub">Kiras Erkenntnisse</div></div>
          </div>
        </div>
        <div class="kw-ctx-sep"></div>
        <div class="kw-ctx-section">
          <div class="kw-ctx-sec-h">Letzte Verl&auml;ufe</div>
          <div id="kw-hist-sidebar"><div style="color:var(--muted);font-size:11px;padding:4px 16px">Lade&hellip;</div></div>
        </div>
      </div>

      <!-- Mitte: Chat + Kontext-Bar + Quick-Actions + Input -->
      <div class="kw-center">
        <!-- Kontext-Bar -->
        <div class="kw-cbar" id="kwCbar" style="display:none">
          <span class="kw-cbar-mode" id="kwCbarMode"></span>
          <span class="kw-cbar-title" id="kwCbarTitle"></span>
          <span id="kwCbarTags"></span>
          <div class="kw-cbar-provider"><span class="kw-cbar-provider-dot"></span>Anthropic Claude</div>
          <div class="kw-cbar-acts">
            <span class="kw-cbar-btn" onclick="clearKiraContext()">Kontext l&ouml;sen</span>
          </div>
        </div>

        <!-- Tab-Inhalte -->
        <div id="kiraContent" style="flex:1;overflow:hidden;display:flex;flex-direction:column;">
          <div id="kc-chat" class="kira-chat-wrap" style="display:flex">
            <div class="kira-chat-area" id="kiraChatArea">
              <div class="kira-welcome">
                <div class="kira-welcome-icon">K</div>
                <div class="kira-welcome-text">Hallo! Ich bin Kira, deine KI-Assistentin.<br>
                Frag mich zu Rechnungen, Angeboten, Kunden &mdash; oder lass uns offene Aufgaben besprechen.</div>
              </div>
            </div>
          </div>
          <div id="kc-aufgaben" style="display:none"><div id="kira-aufgaben-list"><div style="color:var(--muted);font-size:var(--fs-base);">Lade&hellip;</div></div></div>
          <div id="kc-muster" style="display:none"><div id="kira-muster-content"><div style="color:var(--muted);font-size:var(--fs-base);">Lade&hellip;</div></div></div>
          <div id="kc-kwissen" style="display:none"><div id="kira-lernen-list"><div style="color:var(--muted);font-size:var(--fs-base);">Lade&hellip;</div></div></div>
          <div id="kc-historie" style="display:none"><div id="kira-historie-list"><div style="color:var(--muted);font-size:var(--fs-base);">Lade&hellip;</div></div></div>
        </div>

        <!-- Quick Actions Bar -->
        <div class="kw-quick-bar" id="kwQuickBar">
          <span class="kw-quick-lbl">Schnell:</span>
          <span class="kw-qb" onclick="kiraAddPrompt('Fasse zusammen')">Fasse zusammen</span>
          <span class="kw-qb" onclick="kiraAddPrompt('Was schlägst du vor?')">Vorschlag</span>
          <span class="kw-qb" onclick="kiraAddPrompt('Erstelle einen Entwurf')">Entwurf</span>
          <span class="kw-qb" onclick="kiraAddPrompt('Bewerte das Risiko')">Risiko</span>
        </div>

        <!-- Input-Bereich -->
        <div class="kw-input-area">
          <textarea class="kw-input-box" id="kiraInput" placeholder="Nachricht an Kira…" rows="1"
            onkeydown="if(event.key==='Enter'&&!event.shiftKey){{event.preventDefault();sendKiraMsg()}}"
            oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,120)+'px'"></textarea>
          <div class="kw-input-acts">
            <div class="kw-ia" title="Kontext anhängen" onclick="showToast('Kontext — In Planung')">+</div>
            <div class="kw-mode-sel" onclick="toggleKiraModeMenu()">Modus &#x25BE;</div>
            <button class="kw-ia send" onclick="sendKiraMsg()" id="kiraSendBtn">&#x2191;</button>
          </div>
        </div>
      </div>

      <!-- Rechts: Werkzeuge (collapsible) -->
      <div class="kw-tools collapsed" id="kwTools">
        <div class="kw-tools-hdr">
          <span class="kw-tools-t">Kontext &amp; Werkzeuge</span>
          <span class="kw-tools-close" onclick="toggleKiraTools()">&#x2715; Einklappen</span>
        </div>
        <div class="kw-tools-sec">
          <div class="kw-tools-sh">Anh&auml;nge</div>
          <div id="kw-tools-attachments"><div class="kw-t-item-sub" style="color:var(--muted)">Keine Anh&auml;nge</div></div>
        </div>
        <div class="kw-tools-sep"></div>
        <div class="kw-tools-sec">
          <div class="kw-tools-sh">Relevante Regeln</div>
          <div id="kw-tools-rules"><div class="kw-t-item-sub" style="color:var(--muted)">Keine aktiven Regeln</div></div>
        </div>
        <div class="kw-tools-sep"></div>
        <div class="kw-tools-sec">
          <div class="kw-tools-sh">N&auml;chste Aktionen</div>
          <div id="kw-tools-actions"><div class="kw-t-item-sub" style="color:var(--muted)">Keine Aktionen vorgeschlagen</div></div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Korrektur Modal -->
<div class="modal-ov" id="lh-modal" style="display:none" onclick="if(event.target===this)closeLhModal()">
  <div class="modal" style="max-width:680px;width:90vw">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <h3 style="margin:0">Filter-History &amp; L&ouml;schprotokoll</h3>
      <button onclick="closeLhModal()" style="background:none;border:none;font-size:20px;cursor:pointer;color:var(--text-muted)">&times;</button>
    </div>
    <div style="font-size:12px;color:var(--text-muted);margin-bottom:12px">
      Automatisch herausgefilterte DATEV-Duplikate und Mails mit abweichendem Anhang (behalten).
    </div>
    <div id="lh-modal-body"></div>
  </div>
</div>

<div class="multi-toolbar" id="multiToolbar">
  <span class="multi-tb-count" id="multiCount">0 ausgewählt</span>
  <span class="multi-tb-sep"></span>
  <button class="btn btn-done"     onclick="multiAction('erledigt')">Erledigt</button>
  <button class="btn btn-kenntnis" onclick="multiAction('zur_kenntnis')">Zur Kenntnis</button>
  <button class="btn btn-later"    onclick="multiAction('spaeter')">Später</button>
  <button class="btn btn-ignore"   onclick="multiAction('ignorieren')">Ignorieren</button>
  <button class="btn btn-loeschen" onclick="multiLoeschen()">Löschen</button>
  <span class="multi-tb-sep"></span>
  <button class="btn btn-korr" onclick="clearSelection()">✕ Abbrechen</button>
</div>

<div class="modal-ov" id="korrModal">
  <div class="modal">
    <h3>Korrektur / Feedback</h3>
    <input type="hidden" id="korr-tid">
    <input type="hidden" id="korr-alt">
    <label style="font-size:12px;color:var(--muted);display:block;margin-bottom:3px;">Kategorie ändern auf:</label>
    <select id="korr-neu">
      <option value="">– unverändert –</option>
      <option value="Antwort erforderlich">Antwort erforderlich</option>
      <option value="Neue Lead-Anfrage">Neue Lead-Anfrage</option>
      <option value="Angebotsrückmeldung">Angebotsrückmeldung</option>
      <option value="Rechnung / Beleg">Rechnung / Beleg</option>
      <option value="Shop / System">Shop / System</option>
      <option value="Zur Kenntnis">Zur Kenntnis</option>
      <option value="Ignorieren">Ignorieren</option>
    </select>
    <label style="font-size:12px;color:var(--muted);display:block;margin-bottom:3px;">Notiz (optional):</label>
    <textarea id="korr-notiz" placeholder="z.B. war kein Lead, war Lieferant..."></textarea>
    <div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border)">
      <label style="font-size:11px;color:var(--muted);display:block;margin-bottom:4px;">Als Alias merken (optional):</label>
      <div style="display:flex;gap:6px;align-items:center">
        <input type="email" id="korr-alias-email" placeholder="alias@email.de" style="flex:1;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 8px;font-size:12px">
        <input type="email" id="korr-haupt-email" placeholder="haupt@email.de" style="flex:1;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 8px;font-size:12px">
        <button class="btn btn-sec" onclick="saveAlias()" style="font-size:11px;padding:5px 10px">Alias merken</button>
      </div>
      <div style="font-size:10px;color:var(--muted);margin-top:3px">Alias-E-Mail wird bei allen Suchen auf Haupt-E-Mail gemappt</div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-done" onclick="saveKorrektur()">Speichern</button>
      <button class="btn btn-ignore" onclick="closeKorrModal()">Abbrechen</button>
    </div>
  </div>
</div>

<!-- Löschen + Kira lernt Modal -->
<div class="modal-ov" id="loeschModal">
  <div class="modal" style="max-width:460px">
    <h3 style="margin:0 0 4px;color:#d06060">&#x1F5D1; Löschen &amp; Kira lernt</h3>
    <input type="hidden" id="lm-tid">
    <div id="lm-titel" style="font-size:12px;color:var(--muted);margin-bottom:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"></div>
    <p style="font-size:12px;color:var(--text-secondary);margin:0 0 10px">Warum wird diese Aufgabe gel&ouml;scht? Kira liest die Mail, analysiert und legt eine Lernregel an.</p>
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px" id="lm-grund-btns">
      <button class="loeschen-grund-btn" onclick="setLoeschGrund(this,'DATEV-Duplikat')">DATEV-Duplikat</button>
      <button class="loeschen-grund-btn" onclick="setLoeschGrund(this,'Systemmail / automatisch')">Systemmail</button>
      <button class="loeschen-grund-btn" onclick="setLoeschGrund(this,'Irrelevant')">Irrelevant</button>
      <button class="loeschen-grund-btn" onclick="setLoeschGrund(this,'Spam / Werbung')">Spam / Werbung</button>
      <button class="loeschen-grund-btn" onclick="setLoeschGrund(this,'Falsches Konto')">Falsches Konto</button>
      <button class="loeschen-grund-btn" onclick="setLoeschGrund(this,'Bereits erledigt')">Bereits erledigt</button>
    </div>
    <input type="text" id="lm-grund" placeholder="Eigener Grund (oder oben klicken) …"
      style="width:100%;background:var(--bg-raised);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:9px 12px;font-size:13px;margin-bottom:10px;box-sizing:border-box"
      onkeydown="if(event.key==='Enter')saveLoeschen()">
    <div id="lm-kira-resp" style="display:none;background:var(--accent-bg);border:1px solid var(--accent-border);border-radius:8px;padding:10px 12px;font-size:12px;color:var(--text);margin-bottom:10px;line-height:1.5;max-height:160px;overflow-y:auto"></div>
    <div class="modal-actions">
      <button class="btn btn-loeschen" id="lm-save-btn" onclick="saveLoeschen()">Kira fragen &amp; l&ouml;schen</button>
      <button class="btn btn-ignore" onclick="closeLoeschModal()">Abbrechen</button>
    </div>
  </div>
</div>

<!-- Später Dialog Modal -->
<div class="modal-ov" id="spaeterModal">
  <div class="modal" style="max-width:420px">
    <h3 style="margin:0 0 6px">&#x23F0; Wann erinnern?</h3>
    <p style="font-size:12px;color:var(--muted);margin:0 0 14px">Kira fragt dich wann &mdash; schreib einfach nat&uuml;rlich, z.B. <em>morgen 10 Uhr</em>, <em>n&auml;chste Woche Montag</em>, <em>in 3 Stunden</em>.</p>
    <input type="hidden" id="sp-tid">
    <input type="text" id="sp-wann" placeholder="morgen 10 Uhr …"
      style="width:100%;background:var(--bg-raised);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:10px 12px;font-size:14px;margin-bottom:10px;box-sizing:border-box"
      onkeydown="if(event.key==='Enter')saveSpaeter()">
    <div id="sp-kira-resp" style="display:none;background:var(--accent-bg);border:1px solid var(--accent-border);border-radius:8px;padding:10px 12px;font-size:13px;color:var(--text);margin-bottom:10px;line-height:1.5"></div>
    <div class="modal-actions">
      <button class="btn btn-later" id="sp-save-btn" onclick="saveSpaeter()">Kira fragen</button>
      <button class="btn btn-ignore" onclick="closeSpaeterDialog()">Abbrechen</button>
    </div>
  </div>
</div>

<!-- Regel Bearbeiten Modal -->
<div class="modal-ov" id="editRegelModal">
  <div class="modal">
    <h3>Regel bearbeiten</h3>
    <input type="hidden" id="er-id">
    <label style="font-size:12px;color:var(--muted);display:block;margin-bottom:3px;">Kategorie:</label>
    <select id="er-kat" style="width:100%;background:var(--bg-raised);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px;margin-bottom:9px;">
      <option value="fest">Feste Regel</option>
      <option value="stil">Stil &amp; Tonalit&auml;t</option>
      <option value="preis">Preise &amp; Kalkulation</option>
      <option value="technik">Technik &amp; Fachwissen</option>
      <option value="prozess">Prozess &amp; Abl&auml;ufe</option>
      <option value="gelernt">Gelernt</option>
      <option value="vorschlag">Vorschlag</option>
    </select>
    <label style="font-size:12px;color:var(--muted);display:block;margin-bottom:3px;">Titel:</label>
    <input type="text" id="er-titel" style="width:100%;background:var(--bg-raised);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px;margin-bottom:9px;">
    <label style="font-size:12px;color:var(--muted);display:block;margin-bottom:3px;">Inhalt:</label>
    <textarea id="er-inhalt" rows="5" style="width:100%;background:var(--bg-raised);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px;font-family:inherit;resize:vertical;margin-bottom:9px;"></textarea>
    <div class="modal-actions">
      <button class="btn btn-done" onclick="saveRegelEdit()">Speichern</button>
      <button class="btn btn-ignore" onclick="closeEditRegel()">Abbrechen</button>
    </div>
  </div>
</div>

<!-- Kritisch-Bestätigung Modal (3-Schritt) -->
<div class="modal-ov" id="kritischModal">
  <div class="modal" style="max-width:440px">
    <h3 id="km-title" style="margin:0 0 6px;color:#d06060">Bestätigung erforderlich</h3>
    <p id="km-msg" style="font-size:12px;color:var(--text-secondary);margin:0 0 14px;line-height:1.55"></p>
    <div style="background:var(--bg-overlay);border:0.5px solid var(--border);border-radius:8px;padding:10px 14px;margin-bottom:12px;font-size:12px;color:var(--muted);line-height:1.5">
      Tippe <strong id="km-word" style="color:var(--text);font-family:monospace;font-size:13px;letter-spacing:.5px"></strong> zur Bestätigung:
    </div>
    <input type="text" id="km-inp" placeholder="" autocomplete="off"
      style="width:100%;background:var(--bg-raised);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:9px 12px;font-size:13px;margin-bottom:10px;box-sizing:border-box;font-family:monospace"
      oninput="km_check()" onkeydown="if(event.key==='Enter')km_confirm()">
    <p id="km-note" style="font-size:11px;color:var(--muted);margin:0 0 12px;display:none"></p>
    <div class="modal-actions">
      <button class="btn btn-loeschen" id="km-btn" onclick="km_confirm()" disabled style="opacity:.45;transition:opacity .15s">Bestätigen</button>
      <button class="btn btn-ignore" onclick="km_cancel()">Abbrechen</button>
    </div>
  </div>
</div>

<div class="status-toast" id="toast"><span id="toast-msg"></span><button id="toast-copy-btn" title="Inhalt kopieren" onclick="(function(b){{var txt=document.getElementById('toast-msg').textContent;if(navigator.clipboard){{navigator.clipboard.writeText(txt).then(function(){{b.textContent='✓';setTimeout(function(){{b.textContent='⧉';}},1200);}},function(){{var ta=document.createElement('textarea');ta.value=txt;document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);b.textContent='✓';setTimeout(function(){{b.textContent='⧉';}},1200);}});}}else{{var ta=document.createElement('textarea');ta.value=txt;document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);b.textContent='✓';setTimeout(function(){{b.textContent='⧉';}},1200);}}}})(this)">&#x29C9;</button></div>
<footer>Kira Assistenz &middot; <a href="javascript:location.reload()">Aktualisieren</a></footer>
</div><!-- /main-area -->
</div><!-- /app-shell -->

<script>
window.onerror = function(msg,src,line,col,err){{
  let b=document.getElementById('_jserr');
  if(!b){{b=document.createElement('div');b.id='_jserr';
    b.style='position:fixed;top:0;left:0;right:0;z-index:99999;background:#dc4a4a;color:#fff;font-size:12px;padding:6px 12px;font-family:monospace;white-space:pre-wrap';
    document.body&&document.body.appendChild(b);}}
  b.textContent='JS-FEHLER Zeile '+line+': '+msg;
}};
const KIRA_CTX = {json.dumps(kira_ctx, ensure_ascii=False).replace('<', '\\u003C').replace('>', '\\u003E')};
const PROMPTS  = {json.dumps(prompts_json, ensure_ascii=False).replace('<', '\\u003C').replace('>', '\\u003E')};
let kiraOpen = false;

// ═══ SIDEBAR & NAV ═══
const PANEL_TITLES = {{
  dashboard:'Start', kommunikation:'Kommunikation', organisation:'Organisation',
  geschaeft:'Gesch\u00e4ft', wissen:'Wissen', einstellungen:'Einstellungen',
  kunden:'Kunden', marketing:'Marketing',
  social:'Social / DMs', automationen:'Automationen', analysen:'Analysen'
}};

function showPanel(name) {{
  _rtlog('ui','panel_switched','Panel: '+name,{{submodul:'navigation',context_type:'panel',context_id:name}});
  document.querySelectorAll('.sidebar-item').forEach(n=>n.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  const nav = document.getElementById('nav-'+name);
  if(nav) nav.classList.add('active');
  const panel = document.getElementById('panel-'+name);
  if(panel) panel.classList.add('active');
  const ht = document.getElementById('headerTitle');
  if(ht) ht.textContent = PANEL_TITLES[name] || name;
  localStorage.setItem('kira_active_tab', name);
  closeMobileSidebar();
  if(name==='postfach' && typeof window.pfInit==='function') {{ window.pfInit(); }}
}}

// Prio-Karte Kebab-Menu
function togglePrioMenu(btn) {{
  const menu = btn.closest('.dash-prio-menu');
  const wasOpen = menu.classList.contains('open');
  document.querySelectorAll('.dash-prio-menu.open').forEach(m => m.classList.remove('open'));
  if (!wasOpen) menu.classList.add('open');
}}
document.addEventListener('click', function(e) {{
  if (!e.target.closest('.dash-prio-menu')) {{
    document.querySelectorAll('.dash-prio-menu.open').forEach(m => m.classList.remove('open'));
  }}
}});

function toggleSidebar() {{
  const sb = document.getElementById('sidebar');
  sb.classList.toggle('collapsed');
  const collapsed = sb.classList.contains('collapsed');
  localStorage.setItem('kira_sidebar_collapsed', collapsed ? '1' : '0');
  document.getElementById('appShell').classList.toggle('sb-collapsed', collapsed);
  const main = document.querySelector('.main-area');
  if (main) {{
    if (collapsed) {{
      main.style.marginLeft = '';  // CSS-Klasse übernimmt (56px)
    }} else {{
      const savedW = localStorage.getItem('kira_sidebar_w');
      main.style.marginLeft = savedW ? savedW + 'px' : '';
    }}
  }}
}}

// Sidebar drag-to-resize
(function() {{
  const handle = document.getElementById('sidebarResizeHandle');
  if(!handle) return;
  const sb = document.getElementById('sidebar');
  const main = document.querySelector('.main-area');
  let startX, startW;
  handle.addEventListener('mousedown', function(e) {{
    if(sb.classList.contains('collapsed')) return;
    startX = e.clientX;
    startW = sb.offsetWidth;
    handle.classList.add('dragging');
    sb.classList.add('resizing');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    function onMove(e) {{
      const w = Math.max(160, Math.min(380, startW + e.clientX - startX));
      document.documentElement.style.setProperty('--sidebar-w', w + 'px');
      if(main) main.style.marginLeft = w + 'px';
    }}
    function onUp() {{
      const w = sb.offsetWidth;
      localStorage.setItem('kira_sidebar_w', w);
      handle.classList.remove('dragging');
      sb.classList.remove('resizing');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    }}
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    e.preventDefault();
  }});
}})();

function openMobileSidebar() {{
  document.getElementById('sidebar').classList.add('mobile-open');
  document.getElementById('sidebarOverlay').classList.add('active');
}}
function closeMobileSidebar() {{
  document.getElementById('sidebar').classList.remove('mobile-open');
  document.getElementById('sidebarOverlay').classList.remove('active');
}}

// ═══ DESIGN / THEME ═══
function applyTheme(theme) {{
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('kira_theme', theme);
}}
function applyAccent(hex) {{
  document.documentElement.style.setProperty('--accent', hex);
  // Generate lighter variant
  const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
  const lr=Math.min(255,r+30),lg=Math.min(255,g+30),lb=Math.min(255,b+30);
  document.documentElement.style.setProperty('--accent-l','#'+[lr,lg,lb].map(x=>x.toString(16).padStart(2,'0')).join(''));
  document.documentElement.style.setProperty('--accent-bg',`rgba(${{r}},${{g}},${{b}},.08)`);
  document.documentElement.style.setProperty('--accent-border',`rgba(${{r}},${{g}},${{b}},.25)`);
  const hexEl = document.getElementById('cfg-accent-hex');
  if(hexEl) hexEl.textContent = hex;
  localStorage.setItem('kira_accent', hex);
}}
function resetAccent() {{
  const def = '#4f7df9';
  document.getElementById('cfg-accent').value = def;
  applyAccent(def);
}}
function applyFontSize(size) {{
  if(size) document.documentElement.dataset.fontsize = size;
  else delete document.documentElement.dataset.fontsize;
  localStorage.setItem('kira_fontsize', size);
}}
function applyDensity(density) {{
  if(density) document.documentElement.dataset.density = density;
  else delete document.documentElement.dataset.density;
  localStorage.setItem('kira_density', density);
}}
function applyCompanyName(name) {{
  const el = document.getElementById('brandName');
  if(el) el.textContent = name || 'Kira';
  localStorage.setItem('kira_company_name', name);
}}
function updateLogoPreview(val) {{
  const pv = document.getElementById('logo-upload-preview');
  if(!pv) return;
  if(val && (val.startsWith('http')||val.startsWith('data:'))) {{
    pv.innerHTML = '<img src="'+val+'" style="width:38px;height:38px;object-fit:contain">';
  }} else {{
    pv.textContent = val || '';
  }}
}}
function handleLogoUpload(input) {{
  const file = input.files[0];
  if(!file) return;
  if(file.size > 512000) {{ showToast('Datei zu gro\u00df (max. 500KB)'); return; }}
  const reader = new FileReader();
  reader.onload = function(e) {{
    const dataUrl = e.target.result;
    const inp = document.getElementById('cfg-logo');
    if(inp) inp.value = dataUrl;
    applyLogo(dataUrl);
    updateLogoPreview(dataUrl);
    localStorage.setItem('kira_logo', dataUrl);
  }};
  reader.readAsDataURL(file);
}}
function applyLogo(val) {{
  const el = document.getElementById('sidebarLogo');
  if(!el) return;
  if(val && (val.startsWith('http')||val.startsWith('data:'))) {{
    el.innerHTML = '<img src="'+val+'" alt="">';
  }} else {{
    el.textContent = val || 'K';
    const img = el.querySelector('img');
    if(img) img.remove();
  }}
  localStorage.setItem('kira_logo', val);
}}
function applyCardRadius(val) {{
  if(val) document.documentElement.style.setProperty('--card-radius', val);
  else document.documentElement.style.removeProperty('--card-radius');
  localStorage.setItem('kira_card_radius', val);
}}
function applyShadow(val) {{
  document.documentElement.dataset.shadow = val || '';
  localStorage.setItem('kira_shadow', val);
}}
function applyReduceMotion(checked) {{
  document.documentElement.dataset.reduceMotion = checked ? 'true' : '';
  localStorage.setItem('kira_reduce_motion', checked ? '1' : '0');
}}
function applyHighContrast(checked) {{
  document.documentElement.dataset.highContrast = checked ? 'true' : '';
  localStorage.setItem('kira_high_contrast', checked ? '1' : '0');
}}
function applyKiraSize(px) {{
  const fab=document.getElementById('kiraFab');
  if(fab){{fab.style.width=px+'px';fab.style.height=px+'px';}}
  // QP-Panel bottom anpassen: FAB-Größe + 36px Abstand
  const qp=document.querySelector('.kq-panel');
  if(qp){{qp.style.bottom=(parseInt(px)+36)+'px';}}
}}
function applyKiraProx(v) {{ window._kiraProxRadius=parseFloat(v); }}
function applyKiraBounce(v) {{ window._kiraBounce=parseInt(v); }}
function applyKiraIdle(v) {{ window._kiraIdleEnabled=!!v; }}
function applyKiraIdleDelay(v) {{ window._kiraIdleDelay=parseInt(v); }}
function applySidebarWidth(px) {{
  const v = Math.max(160, Math.min(400, parseInt(px)||220));
  document.documentElement.style.setProperty('--sidebar-w', v+'px');
  const ma = document.querySelector('.main-area');
  const sb = document.getElementById('sidebar');
  if(ma && sb && !sb.classList.contains('collapsed')) ma.style.marginLeft = v+'px';
  localStorage.setItem('kira_sidebar_width', v);
  const inp = document.getElementById('cfg-sidebar-width');
  if(inp && inp.value != v) inp.value = v;
}}
function applyFontFamily(val) {{
  const html = document.documentElement;
  if(val) html.dataset.fontFamily = val; else delete html.dataset.fontFamily;
  localStorage.setItem('kira_font_family', val||'');
}}
function applyRowHeight(val) {{
  const html = document.documentElement;
  if(val) html.dataset.rowHeight = val; else delete html.dataset.rowHeight;
  localStorage.setItem('kira_row_height', val||'');
}}
function applyToastPos(val) {{
  const html = document.documentElement;
  if(val) html.dataset.toastPos = val; else delete html.dataset.toastPos;
  localStorage.setItem('kira_toast_pos', val||'');
}}
function applyToastDauer(typ, val) {{
  const sek = Math.max(1, Math.min(60, parseInt(val)||4));
  localStorage.setItem('kira_toast_dauer_'+typ, sek);
}}
function applyTableZebra(checked) {{
  const html = document.documentElement;
  if(checked) html.dataset.tableZebra = 'true'; else delete html.dataset.tableZebra;
  localStorage.setItem('kira_table_zebra', checked ? '1' : '0');
}}
function applyTableLines(checked) {{
  const html = document.documentElement;
  if(checked) html.dataset.tableLines = 'true'; else delete html.dataset.tableLines;
  localStorage.setItem('kira_table_lines', checked ? '1' : '0');
}}
function saveDesignSettings() {{
  showToast('Design gespeichert');
  const st = document.getElementById('design-status');
  if(st) {{ st.textContent='Gespeichert'; setTimeout(()=>st.textContent='',2000); }}
}}

// Restore design settings on load
function restoreDesign() {{
  const theme = localStorage.getItem('kira_theme');
  if(theme) {{ applyTheme(theme); const sel=document.getElementById('cfg-theme'); if(sel) sel.value=theme; }}
  const accent = localStorage.getItem('kira_accent');
  if(accent) {{ applyAccent(accent); const inp=document.getElementById('cfg-accent'); if(inp) inp.value=accent; }}
  const fs = localStorage.getItem('kira_fontsize') || '';
  if(fs) {{ applyFontSize(fs); const sel=document.getElementById('cfg-fontsize'); if(sel) sel.value=fs; }}
  const dens = localStorage.getItem('kira_density') || '';
  if(dens) {{ applyDensity(dens); const sel=document.getElementById('cfg-density'); if(sel) sel.value=dens; }}
  const cn = localStorage.getItem('kira_company_name');
  if(cn) {{ applyCompanyName(cn); const inp=document.getElementById('cfg-company-name'); if(inp) inp.value=cn; }}
  const logo = localStorage.getItem('kira_logo');
  if(logo) {{ applyLogo(logo); updateLogoPreview(logo); const inp=document.getElementById('cfg-logo'); if(inp) inp.value=logo; }}
  // Card radius
  const cr = localStorage.getItem('kira_card_radius') || '';
  if(cr) {{ applyCardRadius(cr); const sel=document.getElementById('cfg-card-radius'); if(sel) sel.value=cr; }}
  // Shadow
  const sh = localStorage.getItem('kira_shadow') || '';
  if(sh) {{ applyShadow(sh); const sel=document.getElementById('cfg-shadow'); if(sel) sel.value=sh; }}
  // Reduce motion
  if(localStorage.getItem('kira_reduce_motion')==='1') {{
    applyReduceMotion(true); const cb=document.getElementById('cfg-reduce-motion'); if(cb) cb.checked=true;
  }}
  // High contrast
  if(localStorage.getItem('kira_high_contrast')==='1') {{
    applyHighContrast(true); const cb=document.getElementById('cfg-high-contrast'); if(cb) cb.checked=true;
  }}
  // Sidebar width (drag-resized)
  const sw = localStorage.getItem('kira_sidebar_w');
  if(sw) {{
    document.documentElement.style.setProperty('--sidebar-w', sw + 'px');
    const ma = document.querySelector('.main-area');
    if(ma && !localStorage.getItem('kira_sidebar_collapsed')) ma.style.marginLeft = sw + 'px';
  }}
  // Sidebar collapsed state
  if(localStorage.getItem('kira_sidebar_collapsed')==='1') {{
    const sb=document.getElementById('sidebar');
    sb.classList.add('collapsed');
    document.getElementById('appShell').classList.add('sb-collapsed');
  }}
  // Sidebar width (user setting)
  const sbwUser = localStorage.getItem('kira_sidebar_width');
  if(sbwUser) {{ applySidebarWidth(sbwUser); const inp=document.getElementById('cfg-sidebar-width'); if(inp) inp.value=sbwUser; }}
  // Font family
  const ff = localStorage.getItem('kira_font_family')||'';
  if(ff) {{ applyFontFamily(ff); const sel=document.getElementById('cfg-font-family'); if(sel) sel.value=ff; }}
  // Row height
  const rh = localStorage.getItem('kira_row_height')||'';
  if(rh) {{ applyRowHeight(rh); const sel=document.getElementById('cfg-row-height'); if(sel) sel.value=rh; }}
  // Toast position
  const tp = localStorage.getItem('kira_toast_pos')||'';
  if(tp) {{ applyToastPos(tp); const sel=document.getElementById('cfg-toast-pos'); if(sel) sel.value=tp; }}
  // Table zebra
  if(localStorage.getItem('kira_table_zebra')==='1') {{
    applyTableZebra(true); const cb=document.getElementById('cfg-table-zebra'); if(cb) cb.checked=true;
  }}
  const tl = localStorage.getItem('kira_table_lines');
  if(tl) {{ applyTableLines(tl==='1'); const cb2=document.getElementById('cfg-table-lines'); if(cb2) cb2.checked=(tl==='1'); }}
  // Toast-Dauern
  ['ok','fehler','warnung','info'].forEach(typ => {{
    const v = localStorage.getItem('kira_toast_dauer_'+typ);
    if(v) {{ const inp=document.getElementById('cfg-toast-dauer-'+typ); if(inp) inp.value=v; }}
  }});
}}

// KPI click -> jump to Kommunikation with filter
function filterKomm(kat) {{
  showPanel('kommunikation');
  // Highlight matching sections
  document.querySelectorAll('#panel-kommunikation .section').forEach(sec => {{
    const title = sec.querySelector('.section-title')?.textContent || '';
    if (kat === 'Antwort erforderlich' && title.includes('Antwort erforderlich')) sec.classList.remove('collapsed');
    else if (kat === 'Neue Lead-Anfrage' && title.includes('Neue Leads')) sec.classList.remove('collapsed');
    else if (kat === 'Angebotsrückmeldung' && title.includes('Angebotsrückmeldung')) sec.classList.remove('collapsed');
    else if (kat === 'Rechnung / Beleg' && title.includes('Rechnungen')) sec.classList.remove('collapsed');
    else sec.classList.add('collapsed');
  }});
}}

// Kommunikation v2 — Segment Tabs
let _kommActiveTab = 'alle';
function kommSegFilter(el, kat) {{
  document.querySelectorAll('.km-seg-t').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
  _kommActiveTab = kat;
  applyKommFilters2();
}}
// Keep old filterKommView alias for Organisation panel tabs (uses .komm-view-tab)
function filterKommView(el, kat) {{
  document.querySelectorAll('#panel-kommunikation .komm-view-tab').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
}}

// Toggle chip filter
function toggleKommFc(el) {{
  el.classList.toggle('active');
  applyKommFilters2();
}}

// Kommunikation combined filter
function applyKommFilters() {{ applyKommFilters2(); }}
function applyKommFilters2() {{
  const tab        = _kommActiveTab;
  const nurAntwort = document.querySelector('.km-fc[data-filter="antwort"]')?.classList.contains('active')||false;
  const nurFotos   = document.querySelector('.km-fc[data-filter="fotos"]')?.classList.contains('active')||false;
  const nurAnhang  = document.querySelector('.km-fc[data-filter="anhang"]')?.classList.contains('active')||false;
  const nurBeantw  = document.querySelector('.km-fc[data-filter="beantwortet"]')?.classList.contains('active')||false;
  const nurPruef   = document.querySelector('.km-fc[data-filter="pruefung"]')?.classList.contains('active')||false;
  const nurKira    = document.querySelector('.km-fc[data-filter="kira"]')?.classList.contains('active')||false;
  const quelle     = document.getElementById('km-filter-quelle')?.value||'';
  const prio       = document.getElementById('km-filter-prio')?.value||'';
  const search     = (document.getElementById('km-search-input')?.value||'').toLowerCase().trim();
  let count = 0;
  document.querySelectorAll('#km-items .wi').forEach(wi=>{{
    const wkat    = wi.dataset.kat||'';
    const wprio   = wi.dataset.prio||'';
    const wantwort= wi.dataset.antwort==='1';
    const wanhang = wi.dataset.anhang==='1';
    const wfotos  = wi.dataset.fotos==='1';
    const wemail  = wi.dataset.email||'';
    const wbeantw = wi.dataset.beantwortet==='1';
    const wpruef  = wi.dataset.pruefung==='1';
    const wkira   = wi.dataset.kira==='1';
    const wtitle  = wi.querySelector('.wi-title')?.textContent||'';
    const wsum    = wi.querySelector('.wi-sum')?.textContent||'';
    let show = true;
    if(tab && tab !== 'alle' && wkat !== tab) show = false;
    if(nurAntwort && !wantwort) show = false;
    if(nurFotos   && !wfotos)   show = false;
    if(nurAnhang  && !wanhang)  show = false;
    if(nurBeantw  && !wbeantw)  show = false;
    if(nurPruef   && !wpruef)   show = false;
    if(nurKira    && !wkira)    show = false;
    if(quelle && !wemail.toLowerCase().includes(quelle.toLowerCase())) show = false;
    if(prio   && wprio !== prio) show = false;
    if(search && !wtitle.toLowerCase().includes(search) && !wsum.toLowerCase().includes(search)) show = false;
    wi.style.display = show ? '' : 'none';
    if(show) count++;
  }});
  const ce = document.getElementById('km-filter-count');
  if(ce) ce.textContent = count + ' Vorg\u00e4nge';
}}

// Springe direkt zu einem Segment-Tab (für Stats-Links)
function jumpToSeg(kat) {{
  if(kat==='dringend') {{
    // Prio-Filter aktivieren statt Tab
    const sel = document.getElementById('km-filter-prio');
    if(sel) {{ sel.value='hoch'; applyKommFilters2(); }} return;
  }}
  document.querySelectorAll('#km-seg-nav .km-seg-t').forEach(t=>{{
    const m = t.getAttribute('onclick')?.match(/kommSegFilter\\(this,'([^']+)'\\)/);
    if(m && m[1]===kat) kommSegFilter(t,kat);
  }});
}}

// Select work item → fill context panel
function selectKommItem(tid, ev) {{
  if(ev && ev.target && (ev.target.tagName==='BUTTON'||ev.target.tagName==='INPUT'||ev.target.tagName==='LABEL')) return;
  document.querySelectorAll('#km-items .wi').forEach(w=>w.classList.remove('sel'));
  const wi = document.getElementById('task-'+tid);
  if(wi) wi.classList.add('sel');
  const ctx = KIRA_CTX[tid];
  const el  = document.getElementById('km-ctx-content');
  if(!el) return;
  if(!ctx) {{ el.innerHTML='<div class="km-ctx-empty"><span>Kein Kontext verfügbar</span></div>'; return; }}

  // Status badges
  let statusHtml = '';
  if(ctx.antwort_noetig) statusHtml += '<div class="km-ctx-s open"><span class="dot"></span>Antwort erforderlich</div>';
  if(ctx.naechste_erinnerung) {{
    try {{
      const erDate = new Date(ctx.naechste_erinnerung);
      statusHtml += '<div class="km-ctx-s wait"><span class="dot"></span>Erinnerung: '+erDate.toLocaleDateString('de',{{day:'2-digit',month:'2-digit'}}) + ' ' + erDate.toLocaleTimeString('de',{{hour:'2-digit',minute:'2-digit'}})+'</div>';
    }} catch(e) {{}}
  }}
  statusHtml += '<div class="km-ctx-s info"><span class="dot"></span>'+escH(ctx.kategorie||'')+'</div>';

  // Attachments
  let attHtml = '';
  if(ctx.anhang_pfad) {{
    const files = ctx.anhang_pfad.split(';').filter(Boolean);
    files.forEach(f=>{{
      const fname = f.split('\\\\').pop().split('/').pop();
      const ftype = fname.toLowerCase().match(/\\.pdf$/) ? '&#x1F4C4;' : fname.toLowerCase().match(/\\.(jpg|jpeg|png|gif)$/) ? '&#x1F5BC;' : '&#x1F4CE;';
      attHtml += '<div class="km-ctx-att" onclick="openAttachments(\\''+encodeURIComponent(f)+'\\')">'+ftype+' '+escH(fname)+'</div>';
    }});
  }}

  // Thread / last message
  let threadHtml = '';
  if(ctx.beschreibung) {{
    threadHtml = '<div class="km-ctx-msg in"><div class="km-ctx-msg-meta">'+escH(ctx.email||ctx.absender_rolle||'')+(ctx.datum?' &middot; '+escH(ctx.datum):'')+'</div>'+escH(ctx.beschreibung.slice(0,400))+'</div>';
  }}

  // Action buttons
  const encMid  = ctx.message_id ? encodeURIComponent(ctx.message_id) : '';
  const encAnh  = ctx.anhang_pfad ? encodeURIComponent(ctx.anhang_pfad) : '';
  const katEsc  = escH(ctx.kategorie||'');

  let html = '';
  html += '<div class="km-ctx-title">'+escH(ctx.titel||ctx.betreff||'')+'</div>';
  if(wi) html += '<div class="km-ctx-meta">'+( wi.querySelector('.wi-foot')?.innerHTML||'' )+'</div>';
  html += '<div class="km-ctx-status">'+statusHtml+'</div>';
  if(ctx.zusammenfassung) html += '<div class="km-ctx-block"><div class="km-ctx-h">Zusammenfassung</div><div class="km-ctx-text">'+escH(ctx.zusammenfassung)+'</div></div>';
  if(ctx.kategorie_grund) html += '<div class="km-ctx-block"><div class="km-ctx-h">Warum diese Einordnung</div><div class="km-ctx-text muted">'+escH(ctx.kategorie_grund)+'</div></div>';
  if(ctx.empfohlene_aktion) html += '<div class="km-ctx-recommend"><div class="km-ctx-recommend-h">Empfohlene n\u00e4chste Aktion</div><div class="km-ctx-recommend-t">'+escH(ctx.empfohlene_aktion)+'</div></div>';
  if(attHtml) html += '<div class="km-ctx-block"><div class="km-ctx-h">Anh\u00e4nge</div><div class="km-ctx-attachments">'+attHtml+'</div></div>';
  // Letzte Nachricht (schnell aus KIRA_CTX)
  if(threadHtml) html += '<div class="km-ctx-thread" id="km-thread-'+tid+'"><div class="km-ctx-h">Letzte Nachricht <button class="km-thread-load-btn" onclick="loadThread('+tid+')">&#x21BA; Verlauf laden</button></div>'+threadHtml+'</div>';
  else html += '<div class="km-ctx-thread" id="km-thread-'+tid+'"><div class="km-ctx-h">Nachrichten-Verlauf <button class="km-thread-load-btn" onclick="loadThread('+tid+')">laden</button></div></div>';
  html += '<div class="km-ctx-actions">';
  html += '<button class="btn btn-kira" onclick="openKira('+tid+')">Mit Kira besprechen</button>';
  if(ctx.email) html += '<a class="btn btn-primary" href="mailto:'+escH(ctx.email||'')+'">Outlook &#x2709;</a>';
  if(encMid) html += '<button class="btn btn-sec" onclick="readMail(\\''+encMid+'\\')">Mail lesen</button>';
  html += '<button class="btn btn-done" onclick="setStatusLernen('+tid+',\\'erledigt\\',\\''+katEsc+'\\')">Erledigt</button>';
  html += '<button class="btn btn-kenntnis" onclick="setStatusLernen('+tid+',\\'zur_kenntnis\\',\\''+katEsc+'\\')">Zur Kenntnis</button>';
  html += '<button class="btn btn-later" onclick="openSpaeterDialog('+tid+')">Sp\u00e4ter</button>';
  html += '<button class="btn btn-ignore" onclick="setStatusLernen('+tid+',\\'ignorieren\\',\\''+katEsc+'\\')">Ignorieren</button>';
  html += '<button class="btn btn-korr" onclick="openKorrektur('+tid+',\\''+katEsc+'\\')">Korrektur</button>';
  html += '<button class="btn btn-loeschen" onclick="confirmLoeschen('+tid+')">L\u00f6schen</button>';
  html += '</div>';
  el.innerHTML = html;
}}

// Thread-Verlauf laden
function loadThread(tid) {{
  _rtlog('ui','thread_loaded','Thread geladen',{{submodul:'kommunikation',context_type:'mail',context_id:String(tid)}});
  const wrap = document.getElementById('km-thread-'+tid);
  if(!wrap) return;
  wrap.innerHTML = '<div class="km-ctx-h">Nachrichten-Verlauf</div><div class="km-ctx-thread-loading">&#x23F3; wird geladen&hellip;</div>';
  fetch('/api/task/'+tid+'/thread')
    .then(r=>r.json())
    .then(d=>{{
      if(!d.thread||!d.thread.length){{
        wrap.innerHTML='<div class="km-ctx-h">Nachrichten-Verlauf</div><div style="font-size:11px;color:var(--muted);padding:8px 0">Keine weiteren Nachrichten gefunden.</div>';
        return;
      }}
      let th = '<div class="km-ctx-h">Verlauf &mdash; '+d.thread.length+' Nachricht'+(d.thread.length!==1?'en':'')+'</div>';
      d.thread.forEach(m=>{{
        const isCurrent = m.id==tid;
        th += '<div class="km-ctx-msg in'+(isCurrent?' km-thread-current':'')+'">';
        th += '<div class="km-ctx-msg-meta">'+escH(m.betreff||'(kein Betreff)')+(m.datum_mail?' &middot; '+escH(m.datum_mail.slice(0,10)):'')+(isCurrent?' <b>← diese</b>':'')+'</div>';
        if(m.beschreibung) th += '<div>'+escH(m.beschreibung.slice(0,300))+(m.beschreibung.length>300?'&hellip;':'')+'</div>';
        th += '</div>';
      }});
      wrap.innerHTML = th;
    }})
    .catch(()=>{{ wrap.innerHTML='<div class="km-ctx-h">Verlauf</div><div style="font-size:11px;color:var(--muted)">Fehler beim Laden.</div>'; }});
}}

// Fokusmodus Toggle
let _kommFokusModus = false;
function toggleKommFokusModus() {{
  _kommFokusModus = !_kommFokusModus;
  const wl  = document.getElementById('km-wl');
  const ctx = document.getElementById('km-ctx');
  const btn = document.getElementById('km-view-toggle');
  if(_kommFokusModus) {{
    if(wl)  wl.style.width  = '34%';
    if(ctx) ctx.style.width = '66%';
    if(btn) btn.textContent = '\u229F Listenmodus';
  }} else {{
    if(wl)  wl.style.width  = '58%';
    if(ctx) ctx.style.width = '42%';
    if(btn) btn.textContent = '\u229E Fokusmodus';
  }}
}}

// Organisation View-Switching
function showOrgView(el, view) {{
  document.querySelectorAll('.org-view-tabs .komm-view-tab').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
  document.querySelectorAll('.org-view').forEach(v=>v.classList.remove('active'));
  const target = document.getElementById('org-view-'+view);
  if(target) target.classList.add('active');
}}

// Task status
function setStatus(id, status) {{
  _rtlog('ui','task_status_set','Task '+id+' -> '+status,{{submodul:'kommunikation',context_type:'task',context_id:String(id)}});
  fetch('/api/task/'+id+'/status',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{status}})}}).then(r=>r.json()).then(d=>{{
    if(d.ok){{
      const el = document.getElementById('task-'+id);
      if(el){{el.style.opacity='0.2';setTimeout(()=>el.remove(),320);}}
      showToast('Aktualisiert');
    }}
  }}).catch(()=>showToast('Fehler'));
}}

// Status setzen + KI-Lern-Eintrag speichern (einzeln, nicht bulk)
function setStatusLernen(id, status, kat) {{
  fetch('/api/task/'+id+'/status',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{status, kat}})}}).then(r=>r.json()).then(d=>{{
    if(d.ok){{
      const el = document.getElementById('task-'+id);
      if(el){{el.style.opacity='0.2';setTimeout(()=>el.remove(),320);}}
      const label = {{erledigt:'Erledigt ✓',zur_kenntnis:'Zur Kenntnis ✓',ignorieren:'Ignoriert ✓'}}[status]||'Gespeichert';
      showToast(label+' — KI lernt');
    }}
  }}).catch(()=>showToast('Fehler'));
}}

// Multi-Select
let _selectedIds = new Set();
function toggleSelect(id, cb) {{
  const card = document.getElementById('task-'+id);
  if(cb.checked){{ _selectedIds.add(id); card.classList.add('selected'); }}
  else {{ _selectedIds.delete(id); card.classList.remove('selected'); }}
  _updateMultiBar();
}}
function _updateMultiBar() {{
  const tb = document.getElementById('multiToolbar');
  const n  = _selectedIds.size;
  document.getElementById('multiCount').textContent = n + (n===1?' ausgewählt':' ausgewählt');
  tb.classList.toggle('visible', n > 0);
}}
function clearSelection() {{
  _selectedIds.forEach(id=>{{
    const card = document.getElementById('task-'+id);
    if(card){{ card.classList.remove('selected'); card.querySelector('input[type=checkbox]').checked=false; }}
  }});
  _selectedIds.clear();
  _updateMultiBar();
}}
// Multi-Aktion: jede Entscheidung wird einzeln gespeichert (kein Bulk)
async function multiAction(status) {{
  const ids = [..._selectedIds];
  if(!ids.length) return;
  let done=0;
  for(const id of ids) {{
    const card = document.getElementById('task-'+id);
    const kat  = card ? card.dataset.kat : '';
    try {{
      const r = await fetch('/api/task/'+id+'/status',{{method:'POST',
        headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{status, kat}})}});
      const d = await r.json();
      if(d.ok) {{
        if(card){{card.style.opacity='0.2';setTimeout(()=>card.remove(),300);}}
        done++;
      }}
    }} catch(e){{}}
  }}
  clearSelection();
  showToast(done+' Mails aktualisiert — KI lernt aus jeder Entscheidung');
}}
// Löschen + Kira lernt
function confirmLoeschen(tid) {{
  const card = document.getElementById('task-'+tid);
  document.getElementById('lm-tid').value = tid;
  document.getElementById('lm-titel').textContent = card ? (card.querySelector('.task-title')||{{}}).textContent||'' : '';
  document.getElementById('lm-grund').value = '';
  document.getElementById('lm-kira-resp').style.display = 'none';
  document.getElementById('lm-kira-resp').innerHTML = '';
  document.getElementById('lm-save-btn').textContent = 'Kira fragen & löschen';
  document.getElementById('lm-save-btn').disabled = false;
  document.getElementById('lm-save-btn').onclick = saveLoeschen;
  document.querySelectorAll('.loeschen-grund-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('loeschModal').classList.add('open');
  setTimeout(()=>document.getElementById('lm-grund').focus(), 80);
}}
function setLoeschGrund(btn, text) {{
  document.querySelectorAll('.loeschen-grund-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('lm-grund').value = text;
}}
function closeLoeschModal() {{ document.getElementById('loeschModal').classList.remove('open'); }}
async function saveLoeschen() {{
  const tid   = document.getElementById('lm-tid').value;
  const grund = document.getElementById('lm-grund').value.trim() || 'Kein Grund angegeben';
  const btn   = document.getElementById('lm-save-btn');
  btn.textContent = 'Kira analysiert …'; btn.disabled = true;
  try {{
    const r = await fetch('/api/task/'+tid+'/loeschen', {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{grund, analysiere: true}})
    }});
    const d = await r.json();
    if(d.ok) {{
      const resp = document.getElementById('lm-kira-resp');
      let html = d.kira_antwort ? '<strong>Kira:</strong> '+escH(d.kira_antwort) : '';
      if(d.regel_gespeichert) html += '<br><span style="font-size:11px;color:var(--success)">&#x2713; Lernregel gespeichert</span>';
      if(d.archiv_geloescht)  html += '<br><span style="font-size:11px;color:var(--muted)">&#x2713; Archivdatei entfernt</span>';
      resp.innerHTML = html || 'Gelöscht.';
      resp.style.display = 'block';
      const card = document.getElementById('task-'+tid);
      if(card) {{ card.style.opacity='0.2'; setTimeout(()=>card.remove(),400); }}
      btn.textContent = 'OK';
      btn.onclick = ()=>{{ closeLoeschModal(); }};
      btn.disabled = false;
    }} else {{
      showToast('Fehler: '+(d.error||'Unbekannt'));
      btn.textContent='Kira fragen & löschen'; btn.disabled=false;
    }}
  }} catch(e) {{
    showToast('Netzwerkfehler');
    btn.textContent='Kira fragen & löschen'; btn.disabled=false;
  }}
}}
async function multiLoeschen() {{
  const ids = [..._selectedIds];
  if(!ids.length) return;
  const grund = prompt('Warum werden diese '+ids.length+' Aufgaben gelöscht?\\n(Kira lernt aus jeder Löschung)', 'DATEV-Duplikat');
  if(grund === null) return;
  let done = 0;
  for(const id of ids) {{
    try {{
      const r = await fetch('/api/task/'+id+'/loeschen', {{
        method:'POST', headers:{{'Content-Type':'application/json'}},
        body: JSON.stringify({{grund: grund||'Bulk-Löschung', analysiere: true}})
      }});
      const d = await r.json();
      if(d.ok) {{
        const card = document.getElementById('task-'+id);
        if(card) {{ card.style.opacity='0.2'; setTimeout(()=>card.remove(),300); }}
        done++;
      }}
    }} catch(e) {{}}
  }}
  clearSelection();
  showKiraToast(done+' Aufgaben gelöscht — Kira hat daraus gelernt');
}}

// Geschäft sub-tabs
function showGeschTab(name) {{
  document.querySelectorAll('.gesch-tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.gesch-panel').forEach(p=>p.classList.remove('active'));
  // Find matching tab by checking each tab's onclick text
  document.querySelectorAll('.gesch-tab').forEach(t=>{{
    if(t.getAttribute('onclick')?.includes("'"+name+"'")) t.classList.add('active');
  }});
  document.getElementById('gesch-'+name)?.classList.add('active');
  localStorage.setItem('kira_gesch_tab', name);
}}

// Geschäft: Kira mit Datensatz-Kontext öffnen
function geschKira(typ, nr, partner, betrag) {{
  _rtlog('ui','gesch_kira_opened',typ+' '+nr+' via Kira',{{submodul:'geschaeft',context_type:typ,context_id:String(nr)}});
  openKiraNaked();
  showKTab('chat');
  const labels = {{re:'Rechnung',ang:'Angebot',eingang:'Eingangsrechnung',mah:'Mahnung'}};
  const label = labels[typ]||typ;
  setKiraContextBar(label, nr, partner ? [partner] : []);
  kiraSetQuickActions(typ==='re'||typ==='eingang'?'rechnung':typ==='ang'?'angebot':'frage');
  const input = document.getElementById('kiraInput');
  if(input) {{
    const lines = [label + ': ' + nr];
    if(partner) lines.push('Kunde/Partner: ' + partner);
    if(betrag)  lines.push('Betrag: ' + betrag);
    lines.push('');
    lines.push('Was schlägst du vor?');
    input.value = lines.join('\\n');
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    input.focus();
  }}
}}

// Geschäft: Erledigt -> Kira-Interaktion öffnen
function geschErledigt(id) {{
  openKiraInterakt('geschaeft', id, 'erledigt', 'Eingangsrechnung erledigt', [
    {{type:'date', id:'ki-datum', label:'Wann bezahlt?', value:new Date().toISOString().slice(0,10)}},
    {{type:'select', id:'ki-betrag-voll', label:'Voller Betrag bezahlt?', options:[['ja','Ja'],['nein','Nein, reduzierter Betrag'],['unklar','Unklar']]}},
    {{type:'number', id:'ki-betrag', label:'Bezahlter Betrag (EUR)', placeholder:'0.00', condition:'ki-betrag-voll=nein'}},
    {{type:'text', id:'ki-grund', label:'Warum reduziert / warum so lange?', placeholder:'z.B. Skonto, Teilzahlung, Reklamation...', condition:'ki-betrag-voll=nein'}},
    {{type:'textarea', id:'ki-notiz', label:'Hinweise für Zukunft?', placeholder:'Was würdest du beim nächsten Mal anders machen?'}}
  ]);
}}

// Geschäft: Bewertung korrekt (bleibt sichtbar mit Badge)
function geschBewertung(id, bewertung) {{
  fetch('/api/geschaeft/'+id+'/bewertung',{{
    method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{bewertung:bewertung}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok){{
      if(bewertung==='korrekt'){{
        const el=document.getElementById('gesch-'+id);
        if(el){{
          el.style.borderColor='rgba(80,200,120,.3)';
          const hdr=el.querySelector('.gesch-aktiv-header');
          if(hdr && !hdr.querySelector('.badge-korrekt')){{
            const b=document.createElement('span');b.className='badge badge-korrekt';b.textContent='Korrekt';
            hdr.insertBefore(b,hdr.children[1]);
          }}
          el.querySelectorAll('.btn-muted:not([disabled])').forEach(btn=>{{
            if(btn.textContent.trim()==='Korrekt'){{btn.disabled=true;btn.style.opacity='.5';}}
          }});
        }}
        showToast('Korrekt bewertet');
      }} else {{
        const el=document.getElementById('gesch-'+id);
        if(el){{el.style.opacity='0.2';setTimeout(()=>el.remove(),300);}}
        showToast('Bewertung gespeichert');
      }}
    }}
  }}).catch(()=>showToast('Fehler'));
}}

// Anhänge über HTTP öffnen
function openAttachments(encodedPath) {{
  fetch('/api/attachments?path='+encodedPath).then(r=>r.json()).then(files=>{{
    if(!files.length){{ showToast('Keine Anhänge gefunden'); return; }}
    if(files.length===1){{ window.open('/api/file?path='+files[0].url,'_blank'); return; }}
    // Multiple files: show in mail-read modal as gallery
    let html='<div style="margin-bottom:12px"><strong style="color:var(--gold)">Anhänge ('+files.length+')</strong></div>';
    files.forEach(f=>{{
      const icon = f.type==='pdf'?'PDF':f.type.startsWith('image')?'Bild':'Datei';
      html+='<a href="/api/file?path='+f.url+'" target="_blank" class="att-link"><span class="att-icon">'+icon+'</span> '+f.name+'</a>';
    }});
    document.getElementById('mr-betreff').textContent='Anhänge';
    document.getElementById('mr-meta').innerHTML='';
    document.getElementById('mr-body').innerHTML=html;
    document.getElementById('mr-attachments').innerHTML='';
    document.getElementById('mailReadModal').classList.add('open');
  }}).catch(()=>showToast('Fehler beim Laden der Anhänge'));
}}

// Mail lesen
function readMail(encodedMsgId) {{
  _rtlog('ui','mail_read','Mail geöffnet',{{submodul:'kommunikation',context_type:'mail'}});
  document.getElementById('mr-betreff').textContent='Laden...';
  document.getElementById('mr-meta').innerHTML='';
  document.getElementById('mr-body').textContent='';
  document.getElementById('mr-attachments').innerHTML='';
  document.getElementById('mailReadModal').classList.add('open');
  fetch('/api/mail/read?message_id='+encodedMsgId).then(r=>r.json()).then(d=>{{
    document.getElementById('mr-betreff').textContent=d.betreff||'(Kein Betreff)';
    document.getElementById('mr-meta').innerHTML='<strong>Von:</strong> '+(d.absender||'')+'<br><strong>An:</strong> '+(d.an||'')+'<br><strong>Datum:</strong> '+(d.datum||'');
    document.getElementById('mr-body').textContent=d.text||'(Kein Inhalt)';
    if(d.anhaenge && d.anhaenge.length){{
      let ahtml='<div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--border)"><strong style="color:var(--gold);font-size:12px">Anhänge:</strong> ';
      d.anhaenge.forEach(a=>{{ ahtml+='<a href="/api/file?path='+encodeURIComponent(a.pfad)+'" target="_blank" class="att-link"><span class="att-icon">'+a.typ+'</span> '+a.name+'</a> '; }});
      ahtml+='</div>';
      document.getElementById('mr-attachments').innerHTML=ahtml;
    }}
  }}).catch(()=>{{
    document.getElementById('mr-body').textContent='Fehler beim Laden der Mail.';
  }});
}}
function closeMailRead() {{ document.getElementById('mailReadModal').classList.remove('open'); }}

// Geschäft: Bewertung falsch Dialog
function geschBewertungDialog(id) {{
  document.getElementById('gb-id').value=id;
  document.getElementById('gb-grund').value='';
  document.getElementById('geschBewertModal').classList.add('open');
}}
function closeGeschBewertung() {{ document.getElementById('geschBewertModal').classList.remove('open'); }}
function submitGeschBewertung() {{
  const id=document.getElementById('gb-id').value;
  const grund=document.getElementById('gb-grund').value.trim();
  if(!grund){{ showToast('Bitte Grund angeben'); return; }}
  fetch('/api/geschaeft/'+id+'/bewertung',{{
    method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{bewertung:'falsch',grund:grund}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok){{
      closeGeschBewertung();
      const el=document.getElementById('gesch-'+id);
      if(el){{el.style.opacity='0.2';setTimeout(()=>el.remove(),300);}}
      showToast('Bewertung gespeichert - Danke!');
    }}
  }}).catch(()=>showToast('Fehler'));
}}

// Ausgangsrechnungen filtern (scope: 'ar' für alle, 'az' für Zahlungen)
function filterAR(scope) {{
  const s = scope || 'ar';
  const year = document.getElementById(s+'-filter-year').value;
  const status = document.getElementById(s+'-filter-status').value;
  let count = 0;
  document.querySelectorAll('.'+s+'-row').forEach(row => {{
    const show = (!year || row.dataset.year === year) && (!status || row.dataset.status === status);
    row.style.display = show ? '' : 'none';
    if (show) count++;
  }});
  document.getElementById(s+'-count').textContent = count + ' Rechnungen';
}}

// Angebote filtern
function filterAng() {{
  const year = document.getElementById('ang-filter-year').value;
  const status = document.getElementById('ang-filter-status').value;
  let count = 0;
  document.querySelectorAll('.ang-row').forEach(row => {{
    const show = (!year || row.dataset.year === year) && (!status || row.dataset.status === status);
    row.style.display = show ? '' : 'none';
    if (show) count++;
  }});
  document.getElementById('ang-count').textContent = count + ' Angebote';
}}

// Ausgangsrechnung Status ändern -> Kira-Interaktion
function arSetStatus(id, status) {{
  _rtlog('ui','rechnung_status_set','RE '+id+' -> '+status,{{submodul:'geschaeft',context_type:'rechnung',context_id:String(id)}});
  if (status === 'bezahlt') {{
    openKiraInterakt('ausgangsrechnung', id, 'bezahlt', 'Rechnung als bezahlt markieren', [
      {{type:'date', id:'ki-datum', label:'Zahlungseingang am:', value:new Date().toISOString().slice(0,10)}},
      {{type:'select', id:'ki-betrag-voll', label:'Voller Betrag eingegangen?', options:[['ja','Ja, voller Betrag'],['nein','Nein, reduzierter Betrag'],['skonto','Skonto abgezogen']]}},
      {{type:'number', id:'ki-betrag', label:'Eingegangener Betrag (EUR)', placeholder:'0.00', condition:'ki-betrag-voll!=ja'}},
      {{type:'text', id:'ki-grund', label:'Grund für Abweichung:', placeholder:'z.B. Skonto, Teilzahlung, Reklamation...', condition:'ki-betrag-voll!=ja'}},
      {{type:'textarea', id:'ki-notiz', label:'Hinweise für zukünftige Rechnungen an diesen Kunden?', placeholder:'z.B. Zahlungsmoral, Skontonutzung...'}}
    ]);
  }} else if (status === 'streitfall') {{
    openKiraInterakt('ausgangsrechnung', id, 'streitfall', 'Streitfall markieren', [
      {{type:'text', id:'ki-grund', label:'Was ist das Problem?', placeholder:'z.B. Mängelrüge, Reklamation, Leistung bestritten...'}},
      {{type:'select', id:'ki-schritt', label:'Nächster Schritt?', options:[['abwarten','Abwarten'],['gespraech','Gespräch suchen'],['mahnung','Mahnung senden'],['anwalt','Rechtliche Schritte']]}},
      {{type:'textarea', id:'ki-notiz', label:'Details zum Vorgang:', placeholder:'Was ist passiert? Was wurde vereinbart?'}}
    ]);
  }}
}}

// Angebot Status ändern -> Kira-Interaktion
function angSetStatus(id, status) {{
  _rtlog('ui','angebot_status_set','Ang '+id+' -> '+status,{{submodul:'geschaeft',context_type:'angebot',context_id:String(id)}});
  if (status === 'angenommen') {{
    openKiraInterakt('angebot', id, 'angenommen', 'Angebot angenommen', [
      {{type:'date', id:'ki-datum', label:'Angenommen am:', value:new Date().toISOString().slice(0,10)}},
      {{type:'select', id:'ki-wie', label:'Wie kam es zum Abschluss?', options:[['direkt','Direkt angenommen'],['nachfass','Nach Nachfass'],['verhandlung','Nach Verhandlung'],['empfehlung','Über Empfehlung'],['sonstig','Sonstiges']]}},
      {{type:'text', id:'ki-dauer', label:'Wie lange hat die Entscheidung gedauert?', placeholder:'z.B. 3 Tage, 2 Wochen...'}},
      {{type:'textarea', id:'ki-notiz', label:'Was war ausschlaggebend? Was lief gut?', placeholder:'Erkenntnisse für zukünftige Angebote...'}}
    ]);
  }} else if (status === 'abgelehnt') {{
    openKiraInterakt('angebot', id, 'abgelehnt', 'Angebot abgelehnt', [
      {{type:'select', id:'ki-grund', label:'Hauptgrund der Ablehnung?', options:[['zu_teuer','Zu teuer'],['konkurrenz','Anderer Anbieter gewählt'],['abgesagt','Projekt abgesagt/verschoben'],['kein_bedarf','Kein Bedarf mehr'],['keine_antwort','Nie geantwortet'],['sonstig','Sonstiges']]}},
      {{type:'text', id:'ki-detail', label:'Details:', placeholder:'Was genau wurde als Grund genannt?'}},
      {{type:'number', id:'ki-preis-diff', label:'Preisdifferenz zum Wettbewerb (EUR, falls bekannt):', placeholder:'0'}},
      {{type:'textarea', id:'ki-notiz', label:'Was hättest du anders machen können?', placeholder:'Erkenntnisse für zukünftige Angebote...'}}
    ]);
  }} else if (status === 'keine_antwort') {{
    openKiraInterakt('angebot', id, 'keine_antwort', 'Keine Antwort erhalten', [
      {{type:'select', id:'ki-nachfass', label:'Wie oft wurde nachgefasst?', options:[['0','Nicht nachgefasst'],['1','1x nachgefasst'],['2','2x nachgefasst'],['3','3x oder öfter']]}},
      {{type:'textarea', id:'ki-notiz', label:'Vermutung warum keine Antwort?', placeholder:'z.B. Projekt verschoben, falscher Ansprechpartner...'}}
    ]);
  }}
}}

// Kira-Interaktions-Modal: öffnen
function openKiraInterakt(type, id, action, title, fields) {{
  document.getElementById('ki-type').value = type;
  document.getElementById('ki-id').value = id;
  document.getElementById('ki-action').value = action;
  document.getElementById('ki-title').textContent = 'Kira: ' + title;
  document.getElementById('ki-context').innerHTML = '<strong>' + type + ' #' + id + '</strong> &rarr; ' + action;
  const container = document.getElementById('ki-fields');
  container.innerHTML = '';
  fields.forEach(f => {{
    const wrap = document.createElement('div');
    wrap.className = 'ki-field';
    if (f.condition) wrap.dataset.condition = f.condition;
    let input = '';
    if (f.type === 'text') {{
      input = '<input type="text" id="'+f.id+'" placeholder="'+(f.placeholder||'')+'" style="width:100%;background:var(--bg-raised);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px">';
    }} else if (f.type === 'number') {{
      input = '<input type="number" id="'+f.id+'" placeholder="'+(f.placeholder||'')+'" step="0.01" style="width:100%;background:var(--bg-raised);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px">';
    }} else if (f.type === 'date') {{
      input = '<input type="date" id="'+f.id+'" value="'+(f.value||'')+'" style="width:100%;background:var(--bg-raised);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px">';
    }} else if (f.type === 'select') {{
      input = '<select id="'+f.id+'" onchange="updateKiraFields()" style="width:100%;background:var(--bg-raised);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px">';
      f.options.forEach(o => {{ input += '<option value="'+o[0]+'">'+o[1]+'</option>'; }});
      input += '</select>';
    }} else if (f.type === 'textarea') {{
      input = '<textarea id="'+f.id+'" rows="3" placeholder="'+(f.placeholder||'')+'" style="width:100%;background:var(--bg-raised);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px;font-family:inherit;resize:vertical"></textarea>';
    }}
    wrap.innerHTML = '<label style="font-size:12px;color:var(--muted);display:block;margin-bottom:3px">'+f.label+'</label>' + input;
    container.appendChild(wrap);
  }});
  updateKiraFields();
  document.getElementById('kiraInteraktModal').classList.add('open');
}}

// Bedingte Felder anzeigen/verstecken
function updateKiraFields() {{
  document.querySelectorAll('#ki-fields .ki-field[data-condition]').forEach(wrap => {{
    const cond = wrap.dataset.condition;
    const m = cond.match(/^([^!=]+)(!=|=)(.+)$/);
    if (!m) return;
    const el = document.getElementById(m[1]);
    if (!el) return;
    const match = m[2] === '=' ? el.value === m[3] : el.value !== m[3];
    wrap.style.display = match ? '' : 'none';
  }});
}}

// Modal schließen
function closeKiraInterakt() {{
  document.getElementById('kiraInteraktModal').classList.remove('open');
}}

// Ohne Angaben fortfahren
function skipKiraInterakt() {{
  const type = document.getElementById('ki-type').value;
  const id = document.getElementById('ki-id').value;
  const action = document.getElementById('ki-action').value;
  executeStatusChange(type, id, action, {{}});
}}

// Mit Angaben speichern
function submitKiraInterakt() {{
  const type = document.getElementById('ki-type').value;
  const id = document.getElementById('ki-id').value;
  const action = document.getElementById('ki-action').value;
  const data = {{}};
  document.querySelectorAll('#ki-fields input, #ki-fields select, #ki-fields textarea').forEach(el => {{
    if (el.id && el.style.display !== 'none' && el.closest('.ki-field')?.style.display !== 'none') {{
      data[el.id.replace('ki-','')] = el.value;
    }}
  }});
  data.zeitstempel = new Date().toISOString();
  executeStatusChange(type, id, action, data);
}}

// Status-Änderung ausführen
function executeStatusChange(type, id, action, data) {{
  const url = type === 'geschaeft' ? '/api/geschaeft/'+id+'/erledigt'
    : type === 'ausgangsrechnung' ? '/api/ausgangsrechnung/'+id+'/status'
    : '/api/angebot/'+id+'/status';
  const body = type === 'geschaeft' ? {{...data}} : {{status: action, ...data}};
  fetch(url, {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify(body)
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok) {{
      closeKiraInterakt();
      showToast('Gespeichert');
      setTimeout(()=>location.reload(), 600);
    }} else showToast(d.error||'Fehler');
  }}).catch(()=>showToast('Fehler'));
}}

// Einstellungen speichern
function saveSettings() {{
  // Provider-Modelle aus den aktuellen UI-Werten sammeln
  const providerUpdates = [];
  document.querySelectorAll('[id^="pmodel-"]').forEach(el=>{{
    const pid = el.id.replace('pmodel-','');
    const model = el.tagName==='SELECT' ? el.value : el.value.trim();
    const urlEl = document.getElementById('purl-'+pid);
    providerUpdates.push({{id:pid, model:model, base_url: urlEl ? urlEl.value.trim() : undefined}});
  }});

  const cfg = {{
    ntfy: {{
      aktiv:              document.getElementById('cfg-ntfy-aktiv')?.checked ?? false,
      topic_name:         document.getElementById('cfg-ntfy-topic')?.value.trim() || '',
      server:             document.getElementById('cfg-ntfy-server')?.value.trim() || 'https://ntfy.sh',
      arbeitszeit_aktiv:  document.getElementById('cfg-ntfy-arbeitszeit-aktiv')?.checked ?? false,
      arbeitszeit_von:    document.getElementById('cfg-ntfy-az-von')?.value || '08:00',
      arbeitszeit_bis:    document.getElementById('cfg-ntfy-az-bis')?.value || '18:00',
      urlaub_modus:       document.getElementById('cfg-ntfy-urlaub')?.checked ?? false,
      urlaub_von:         document.getElementById('cfg-urlaub-von')?.value || '',
      urlaub_bis:         document.getElementById('cfg-urlaub-bis')?.value || ''
    }},
    benachrichtigungen: {{
      inapp_mail:     document.getElementById('cfg-inapp-mail')?.checked ?? true,
      inapp_kira:     document.getElementById('cfg-inapp-kira')?.checked ?? true,
      inapp_aufgaben: document.getElementById('cfg-inapp-aufgaben')?.checked ?? true,
      inapp_bg:       document.getElementById('cfg-inapp-bg')?.checked ?? false,
      inapp_fehler:   document.getElementById('cfg-inapp-fehler')?.checked ?? true
    }},
    aufgaben: {{
      erinnerung_intervall_stunden: parseInt(document.getElementById('cfg-erinnerung-h')?.value)||24,
      unanswered_check_days:        parseInt(document.getElementById('cfg-unanswered-days')?.value)||3,
      deadline_warnung_tage:        parseInt(document.getElementById('cfg-deadline-warnung-tage')?.value)||1,
      erinnerung_typ:               document.getElementById('cfg-erinnerung-typ')?.value || 'push',
      default_prioritaet:           document.getElementById('cfg-default-prioritaet')?.value || 'normal',
      auto_archiv_tage:             parseInt(document.getElementById('cfg-auto-archiv-tage')?.value)||0
    }},
    nachfass: {{
      aktiv:              document.getElementById('cfg-nf-aktiv')?.checked ?? true,
      benachrichtigung:   document.getElementById('cfg-nf-typ')?.value || 'push',
      kira_nachfass_text: document.getElementById('cfg-nf-kira-text')?.checked ?? true,
      intervall_1_tage:   parseInt(document.getElementById('cfg-nf-1')?.value)||7,
      intervall_2_tage:   parseInt(document.getElementById('cfg-nf-2')?.value)||14,
      intervall_3_tage:   parseInt(document.getElementById('cfg-nf-3')?.value)||30,
      rechnung_tage:      parseInt(document.getElementById('cfg-nf-rechnung')?.value)||14
    }},
    server: {{
      port:             parseInt(document.getElementById('cfg-server-port')?.value)||8765,
      auto_open_browser: document.getElementById('cfg-auto-browser')?.checked ?? true
    }},
    llm: {{
      internet_recherche:      document.getElementById('cfg-llm-internet')?.checked ?? false,
      geschaeftsdaten_teilen:  document.getElementById('cfg-llm-geschaeft')?.checked ?? true,
      konversationen_speichern: document.getElementById('cfg-llm-konv')?.checked ?? true,
      _provider_updates: providerUpdates
    }},
    protokoll: {{
      max_eintraege: parseInt(document.getElementById('cfg-proto-max')?.value)||0,
      tage:          parseInt(document.getElementById('cfg-proto-tage')?.value)||90
    }},
    runtime_log: {{
      aktiv:                  document.getElementById('cfg-rl-aktiv')?.checked ?? true,
      ui_events:              document.getElementById('cfg-rl-ui')?.checked ?? true,
      kira_events:            document.getElementById('cfg-rl-kira')?.checked ?? true,
      llm_events:             document.getElementById('cfg-rl-llm')?.checked ?? true,
      hintergrund_events:     document.getElementById('cfg-rl-bg')?.checked ?? true,
      settings_events:        document.getElementById('cfg-rl-settings')?.checked ?? true,
      fehler_immer_loggen:    document.getElementById('cfg-rl-fehler')?.checked ?? true,
      vollkontext_speichern:  document.getElementById('cfg-rl-vollkontext')?.checked ?? true,
      kira_darf_lesen:        document.getElementById('cfg-rl-kira-lesen')?.checked ?? true
    }},
    kira: {{
      launcher_variant: document.getElementById('cfg-kira-variant')?.value || 'B',
      size:        parseInt(document.getElementById('cfg-kira-size')?.value       || '112'),
      prox_radius: parseFloat(document.getElementById('cfg-kira-prox')?.value    || '0.5'),
      bounce_dist: parseInt(document.getElementById('cfg-kira-bounce')?.value     || '130'),
      idle_mode:   document.getElementById('cfg-kira-idle')?.checked              ?? true,
      idle_delay:  parseInt(document.getElementById('cfg-kira-idle-delay')?.value || '10')
    }},
    mail_monitor: {{
      aktiv:              document.getElementById('cfg-mail-monitor-aktiv')?.checked ?? true,
      intervall_sekunden: (parseInt(document.getElementById('cfg-mail-intervall')?.value)||5)*60
    }},
    mail_postfach: {{
      refresh_intervall_min: parseInt(document.getElementById('cfg-postfach-refresh')?.value)||0,
      lese_markierung: document.getElementById('cfg-lese-markierung')?.value||'sofort'
    }},
    mail_klassifizierung: {{
      classify:           document.getElementById('cfg-mail-classify')?.checked ?? false,
      auto_tasks:         document.getElementById('cfg-mail-tasks')?.checked ?? false,
      ignore_newsletter:  document.getElementById('cfg-mail-ignore-newsletter')?.checked ?? false
    }},
    mail_archiv: {{
      pfad:                         document.getElementById('cfg-archiv-pfad')?.value.trim() || '',
      neue_mails_archivieren:       document.getElementById('cfg-archiv-aktiv')?.checked ?? true,
      geloeschte_bereinigung_aktiv: document.getElementById('cfg-archiv-bereinigung-aktiv')?.checked ?? true,
      bereinigung_frist_tage:       parseInt(document.getElementById('cfg-archiv-bereinigung-frist')?.value || '90', 10)
    }}
  }};
  fetch('/api/einstellungen',{{
    method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify(cfg)
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok) showToast('Einstellungen gespeichert');
    else showToast(d.error||'Fehler');
  }}).catch(()=>showToast('Fehler'));
}}

function testPush() {{
  const topic = document.getElementById('cfg-ntfy-topic')?.value.trim();
  const server = document.getElementById('cfg-ntfy-server')?.value.trim() || 'https://ntfy.sh';
  if(!topic) {{ showToast('Bitte zuerst einen Topic-Namen eingeben und speichern'); return; }}
  fetch('/api/ntfy/test', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{topic,server}})}})
    .then(r=>r.json()).then(d=>{{
      if(d.ok) showToast('\u2713 Test-Push gesendet! Check dein Ger\u00e4t.');
      else showToast('Fehler: '+(d.error||'Unbekannt'));
    }}).catch(()=>showToast('Fehler beim Senden'));
}}

// Runtime-Log: fire-and-forget helper (JS -> POST /api/runtime/event)
function _rtlog(event_type, action, summary, data) {{
  try {{
    fetch('/api/runtime/event', {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{event_type, action, summary, source:'browser', modul:'ui',
                             actor_type:'user', status:'ok', ...data}})
    }});
  }} catch(e) {{}}
}}

// Runtime-Log Viewer
let _rlOffset = 0;
function loadRuntimeLog(append, onlyFehler) {{
  const box = document.getElementById('runtimelog-entries');
  if(!box) return;
  if(!append) {{ _rlOffset=0; box.innerHTML=''; }}
  const typ    = document.getElementById('rl-filter-type')?.value  || '';
  const status = onlyFehler ? 'fehler' : (document.getElementById('rl-filter-status')?.value || '');
  const search = document.getElementById('rl-filter-search')?.value || '';
  const limit  = 50;
  let url = `/api/runtime/events?limit=${{limit}}&offset=${{_rlOffset}}`;
  if(typ)    url += `&event_type=${{encodeURIComponent(typ)}}`;
  if(status) url += `&status=${{encodeURIComponent(status)}}`;
  if(search) url += `&search=${{encodeURIComponent(search)}}`;
  fetch(url, {{cache:'no-store'}}).then(r=>r.json()).then(d=>{{
    box.style.display='block';
    const entries = d.entries || [];
    if(!entries.length && !append) {{
      box.innerHTML='<div style="padding:12px;color:var(--muted);font-size:12px">Keine Eintr&auml;ge gefunden.</div>';
      return;
    }}
    entries.forEach(e=>{{
      const row = document.createElement('div');
      row.style.cssText='padding:6px 10px;border-bottom:1px solid rgba(255,255,255,.05);font-size:11px;font-family:monospace';
      const col = e.status==='fehler' ? '#e84545' : 'var(--kl)';
      const ts = (e.ts||'').slice(0,19).replace('T',' ');
      row.innerHTML=`<span style="color:var(--muted)">${{ts}}</span> `+
        `<span style="color:${{col}};font-weight:700">${{e.event_type||''}}/${{e.action||''}}</span> `+
        `<span style="color:var(--text)">${{e.summary||''}}</span>`+
        (e.modul ? `<span style="color:var(--muted);margin-left:6px">[${{e.modul}}]</span>` : '');
      box.appendChild(row);
    }});
    _rlOffset += entries.length;
    if(entries.length === limit) {{
      const btn = document.createElement('div');
      btn.style.cssText='padding:8px;text-align:center;font-size:11px;cursor:pointer;color:var(--kl)';
      btn.textContent='Weitere laden';
      btn.onclick=()=>{{ btn.remove(); loadRuntimeLog(true, onlyFehler); }};
      box.appendChild(btn);
    }}
  }}).catch(()=>{{box.innerHTML='<div style="padding:10px;color:#e84545;font-size:11px">Fehler beim Laden.</div>';box.style.display='block';}});
}}

function refreshRtLogStats() {{
  fetch('/api/runtime/stats',{{cache:'no-store'}}).then(r=>r.json()).then(d=>{{
    const g = document.getElementById('rtlog-stats-grid');
    if(!g) return;
    const byType = d.by_type||{{}};
    g.innerHTML = `<div style="text-align:center;padding:6px;background:#111;border-radius:6px"><div style="font-size:18px;font-weight:700;color:var(--kl)">${{d.total||0}}</div><div style="font-size:10px;color:var(--muted)">Gesamt</div></div>
      <div style="text-align:center;padding:6px;background:#111;border-radius:6px"><div style="font-size:18px;font-weight:700;color:var(--kl)">${{d.today||0}}</div><div style="font-size:10px;color:var(--muted)">Heute</div></div>
      <div style="text-align:center;padding:6px;background:#111;border-radius:6px"><div style="font-size:18px;font-weight:700;color:${{d.fehler>0?'#e84545':'var(--kl)'}};">${{d.fehler||0}}</div><div style="font-size:10px;color:var(--muted)">Fehler</div></div>`;
    const dot = document.getElementById('rtlog-live-dot');
    if(dot) dot.style.background = '#5cb85c';
    // Update type count badges
    ['ui','kira','llm','system','settings'].forEach(t=>{{
      const el=document.getElementById('rl-type-cnt-'+t);
      if(el){{const c=byType[t]||0; el.textContent=c?c+' Eintr.':'';}};
    }});
    // Update typen summary line
    const ts=document.getElementById('rtlog-typen-summary');
    if(ts){{ts.textContent=Object.entries(byType).filter(([,v])=>v>0).map(([k,v])=>k+':'+v).join(' · ')||'–';}}
  }}).catch(()=>{{}});
}}

function exportRtLog() {{
  const typ = document.getElementById('rl-filter-type')?.value||'';
  const status = document.getElementById('rl-filter-status')?.value||'';
  const search = document.getElementById('rl-filter-search')?.value||'';
  let url = '/api/runtime/events?limit=5000&offset=0';
  if(typ) url+=`&event_type=${{encodeURIComponent(typ)}}`;
  if(status) url+=`&status=${{encodeURIComponent(status)}}`;
  if(search) url+=`&search=${{encodeURIComponent(search)}}`;
  fetch(url,{{cache:'no-store'}}).then(r=>r.json()).then(d=>{{
    const rows = d.entries||[];
    if(!rows.length){{showToast('Keine Einträge'); return;}}
    const cols = ['ts','event_type','action','summary','modul','status','provider','model','token_in','token_out','duration_ms'];
    let csv = cols.join(';')+'\\n';
    rows.forEach(r=>{{csv+=cols.map(c=>(String(r[c]||'')).replace(/;/g,',')).join(';')+'\\n';}});
    const a=document.createElement('a');
    a.href='data:text/csv;charset=utf-8,'+encodeURIComponent(csv);
    a.download='runtime_log_'+new Date().toISOString().slice(0,10)+'.csv';
    a.click();
    showToast(`${{rows.length}} Einträge exportiert`);
  }});
}}

// Kritisch-Bestätigung — 3-Schritt Modal
let _km_fn = null, _km_word = '';
function showKritischModal(title, msg, word, fn, note) {{
  document.getElementById('km-title').textContent = title;
  document.getElementById('km-msg').textContent = msg;
  document.getElementById('km-word').textContent = word;
  const inp = document.getElementById('km-inp');
  inp.value = ''; inp.placeholder = word;
  const noteEl = document.getElementById('km-note');
  if(note) {{ noteEl.textContent = note; noteEl.style.display = ''; }}
  else noteEl.style.display = 'none';
  const btn = document.getElementById('km-btn');
  btn.disabled = true; btn.style.opacity = '.45';
  _km_word = word; _km_fn = fn;
  document.getElementById('kritischModal').classList.add('open');
  setTimeout(()=>inp.focus(), 60);
}}
function km_check() {{
  const match = document.getElementById('km-inp').value === _km_word;
  const btn = document.getElementById('km-btn');
  btn.disabled = !match; btn.style.opacity = match ? '1' : '.45';
}}
function km_confirm() {{
  if(document.getElementById('km-inp').value !== _km_word) return;
  document.getElementById('kritischModal').classList.remove('open');
  const fn = _km_fn; _km_fn = null;
  if(fn) fn();
}}
function km_cancel() {{
  document.getElementById('kritischModal').classList.remove('open');
  _km_fn = null;
}}

function clearRtLog() {{
  showKritischModal(
    '\uD83D\uDDD1 Runtime-Log leeren',
    'Alle Eintr\u00e4ge der Runtime-Log-Datenbank werden unwiderruflich gel\u00f6scht. Diese Aktion kann nicht r\u00fcckg\u00e4ngig gemacht werden.',
    'LEEREN',
    function() {{
      fetch('/api/runtime/clear',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:'{{}}'}})
        .then(r=>r.json()).then(d=>{{
          if(d.ok){{showToast('Runtime-Log geleert'); refreshRtLogStats();
            const el=document.getElementById('runtimelog-entries');
            if(el){{el.innerHTML='';el.style.display='none';}}}}
          else showToast(d.error||'Fehler');
        }}).catch(()=>showToast('Fehler'));
    }}
  );
}}

function resetConfig() {{
  showKritischModal(
    'Konfiguration zur\u00fccksetzen',
    'Die gesamte config.json wird auf Werkseinstellungen zur\u00fcckgesetzt. API-Keys in secrets.json bleiben erhalten. Ein Backup wird als config.json.bak angelegt.',
    'ZUR\u00dcCKSETZEN',
    function() {{
      fetch('/api/config/reset',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:'{{}}'}})
        .then(r=>r.json()).then(d=>{{
          if(d.ok){{showToast('Konfiguration zur\u00fcckgesetzt \u2014 Seite wird neu geladen\u2026'); setTimeout(()=>location.reload(),1800);}}
          else showToast(d.error||'Fehler beim Zur\u00fccksetzen');
        }}).catch(()=>showToast('Fehler'));
    }},
    'Ein Backup der aktuellen Konfiguration wird als config.json.bak gespeichert.'
  );
}}

// Änderungsverlauf laden / toggle
function loadChangeLog(append) {{
  const box = document.getElementById('changelog-entries');
  if(!box) return;
  const modul   = (document.getElementById('cl-filter-modul')?.value    || '');
  const result  = (document.getElementById('cl-filter-result')?.value   || '');
  const search  = (document.getElementById('cl-filter-search')?.value   || '');
  const feature = (document.getElementById('cl-filter-feature')?.value  || '');
  const action  = (document.getElementById('cl-filter-action')?.value   || '');
  const query   = modul+'|'+result+'|'+search+'|'+feature+'|'+action;
  if(!append) {{
    if(box.style.display !== 'none' && _clLastQuery === query) {{
      box.style.display='none'; return;
    }}
    _clOffset = 0;
    _clLastQuery = query;
    box.style.display='block';
    box.innerHTML='<div style="padding:10px;color:var(--muted);font-size:12px">L\u00e4dt\u2026</div>';
  }}
  const qs = new URLSearchParams({{limit:'50',offset:String(_clOffset),modul,result,search,feature_id:feature,action}});
  fetch('/api/changelog?' + qs).then(r=>r.json()).then(d=>{{
    const entries = d.entries||[];
    const total   = d.total||0;
    const rCol = {{
      success:'#50c878', partial_success:'#a78bfa', partial_failure:'#f59e0b',
      failed:'#e84545', reverted:'#94a3b8', skipped:'#64748b'
    }};
    const rows = entries.map(e=>{{
      const res  = e.result||'';
      const rc   = rCol[res]||'#aaa';
      const det  = Array.isArray(e.details) ? e.details : (e.details?[e.details]:[]);
      const detHtml = det.length
        ? '<ul style="margin:3px 0 0 14px;padding:0;color:#aaa;font-size:10px">'
          + det.map(x=>'<li>'+escH(x)+'</li>').join('') + '</ul>'
        : '';
      const loc = e.location
        ? '<div style="color:#6b7280;font-size:10px;margin-top:2px">\uD83D\uDCCD '+escH(e.location)+'</div>'
        : '';
      const fu = (e.follow_up||[]).length
        ? '<div style="color:#a78bfa;font-size:10px;margin-top:2px">\u276F '+(e.follow_up||[]).map(f=>escH(f)).join(' \u00B7 ')+'</div>'
        : '';
      const rt = (e.related_todos||[]).length
        ? '<div style="color:#60a5fa;font-size:10px;margin-top:2px">\u21E8 '+(e.related_todos||[]).map(f=>escH(f)).join(' ')+'</div>'
        : '';
      const test = e.test_status && e.test_status!=='not_tested'
        ? ' <span style="font-size:9px;background:rgba(255,255,255,.06);padding:1px 5px;border-radius:3px;color:#94a3b8">\u2714 '+escH(e.test_status)+'</span>'
        : '';
      const sc = e.scope
        ? ' <span style="font-size:9px;background:rgba(255,255,255,.04);padding:1px 5px;border-radius:3px;color:#64748b">'+escH(e.scope)+'</span>'
        : '';
      const fid = e.feature_id
        ? ' <span style="font-size:9px;color:#4b5563">'+escH(e.feature_id)+'</span>'
        : '';
      const st = (e.status_before||e.status_after)
        ? '<div style="color:#4b5563;font-size:10px;margin-top:2px">'
          +(e.status_before?escH(e.status_before):'?')
          +' \u2192 '+(e.status_after?escH(e.status_after):'?')+'</div>'
        : '';
      return '<div style="padding:7px 10px;border-bottom:1px solid #1a1a1a">'
        + '<div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap">'
        + '<span style="color:#4b5563;font-size:10px;white-space:nowrap">'+(e.timestamp||'').slice(0,16).replace('T',' ')+'</span>'
        + '<span style="color:'+rc+';font-size:10px;font-weight:700">'+escH(res)+'</span>'
        + '<span style="color:#60a5fa;font-size:10px">'+escH(e.modul||'')+'</span>'
        + '<span style="color:#94a3b8;font-size:10px">'+escH(e.action||'')+'</span>'
        + sc + test + fid
        + '</div>'
        + '<div style="color:#e2e8f0;font-size:12px;margin-top:3px">'+escH(e.summary||'')+'</div>'
        + loc + st + detHtml + fu + rt
        + '</div>';
    }}).join('');
    if(!append) {{
      const hdrBtn = '<span style="cursor:pointer;color:#60a5fa;user-select:none" onclick="clCloseLog()">Schlie\u00DFen \u00D7</span>';
      const hdr = '<div style="padding:6px 10px;border-bottom:1px solid #1a1a1a;font-size:11px;color:#4b5563;display:flex;justify-content:space-between">'
        + '<span>'+total+' Eintr\u00E4ge (gesamt: '+(d.total_raw||0)+')</span>'
        + hdrBtn+'</div>';
      box.innerHTML = hdr + rows;
    }} else {{
      const mb = box.querySelector('#cl-more-btn');
      if(mb) mb.remove();
      box.insertAdjacentHTML('beforeend', rows);
    }}
    _clOffset += entries.length;
    if(_clOffset < total) {{
      box.insertAdjacentHTML('beforeend',
        '<div id="cl-more-btn" style="padding:8px 10px;text-align:center">'
        + '<button class="btn btn-xs btn-muted" onclick="loadChangeLog(true)">Weitere 50 laden ('+(total-_clOffset)+' verbleibend)</button>'
        + '</div>');
    }}
  }}).catch(()=>{{
    if(!append) box.innerHTML='<div style="padding:10px;color:#e84545;font-size:12px">Fehler beim Laden.</div>';
  }});
}}
var _clOffset = 0;
var _clLastQuery = '';
function clCloseLog() {{
  const b = document.getElementById('changelog-entries');
  if(b) b.style.display='none';
}}
// \u00C4nderungsverlauf als JSONL herunterladen
function exportChangeLog() {{
  fetch('/api/changelog?limit=9999').then(r=>r.json()).then(d=>{{
    const lines = (d.entries||[]).slice().reverse().map(e=>JSON.stringify(e)).join('\\n');
    const blob  = new Blob([lines], {{type:'application/x-ndjson'}});
    const url   = URL.createObjectURL(blob);
    const a     = document.createElement('a');
    a.href = url; a.download = 'change_log.jsonl'; a.click();
    URL.revokeObjectURL(url);
  }}).catch(()=>showToast('Export fehlgeschlagen'));
}}

// Provider Key speichern
function toggleKeyInput(pid, btn) {{
  const box = document.getElementById('keyinp-'+pid);
  if(!box) return;
  const open = box.style.display !== 'none';
  box.style.display = open ? 'none' : 'block';
  btn.textContent = open ? 'Schl\u00fcssel \u00e4ndern' : '\u00d7 Abbrechen';
  if(!open) document.getElementById('pkey-'+pid)?.focus();
}}
function saveProviderKey(providerId) {{
  const key = document.getElementById('pkey-'+providerId)?.value.trim();
  if(!key) {{ showToast('Bitte API Key eingeben'); return; }}
  fetch('/api/kira/provider/save-key',{{
    method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{provider_id:providerId, api_key:key}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok) {{
      showToast('API Key gespeichert');
      document.getElementById('pkey-'+providerId).value='';
      setTimeout(()=>location.reload(),800);
    }} else showToast(d.error||'Fehler');
  }}).catch(()=>showToast('Fehler'));
}}

// Provider hinzufügen
function addProvider() {{
  const typ = document.getElementById('add-provider-typ').value;
  const name = document.getElementById('add-provider-name').value.trim();
  if(!typ) {{ showToast('Bitte Provider-Typ wählen'); return; }}
  fetch('/api/kira/provider/add',{{
    method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{typ:typ, name:name}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok) {{ showToast('Provider hinzugefügt'); setTimeout(()=>location.reload(),600); }}
    else showToast(d.error||'Fehler');
  }}).catch(()=>showToast('Fehler'));
}}

// Provider aktivieren/deaktivieren
function toggleProvider(pid, aktiv) {{
  fetch('/api/kira/provider/toggle',{{
    method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{provider_id:pid, aktiv:aktiv}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok) {{
      const card = document.getElementById('pcard-'+pid);
      if(card) card.style.opacity = aktiv ? '1' : '.5';
      showToast(aktiv ? 'Provider aktiviert' : 'Provider deaktiviert');
    }}
  }}).catch(()=>showToast('Fehler'));
}}

// Provider Priorität ändern
function moveProvider(pid, direction) {{
  fetch('/api/kira/provider/move',{{
    method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{provider_id:pid, direction:direction}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok) setTimeout(()=>location.reload(),400);
    else showToast(d.error||'Fehler');
  }}).catch(()=>showToast('Fehler'));
}}

// Provider löschen
function deleteProvider(pid) {{
  showKritischModal(
    '\u26A0\uFE0F Provider entfernen',
    'Der LLM-Provider wird aus der Konfiguration gel\u00f6scht. Alle API-Key-Einstellungen gehen verloren.',
    'ENTFERNEN',
    function() {{
      fetch('/api/kira/provider/delete',{{
        method:'POST',headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{provider_id:pid}})
      }}).then(r=>r.json()).then(d=>{{
        if(d.ok) {{ showToast('Provider entfernt'); setTimeout(()=>location.reload(),400); }}
        else showToast(d.error||'Fehler');
      }}).catch(()=>showToast('Fehler'));
    }}
  );
}}

// Modell-Verfügbarkeit prüfen (sofort, nicht warten auf Hintergrund-Thread)
function checkProviderModel(pid) {{
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = '⏳';
  fetch('/api/kira/provider/check-models',{{
    method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{provider_id:pid}})
  }}).then(r=>r.json()).then(d=>{{
    btn.disabled = false;
    btn.textContent = '🔍 Modell';
    if(!d.ok) {{ showToast(d.error||'Fehler bei Modell-Prüfung'); return; }}
    const r = d.result||{{}};
    if(r.valid) {{
      showToast('✓ Modell verfügbar: ' + (r.model||''));
    }} else if(r.auto_update && r.auto_update.changed) {{
      showToast('⚠ Modell veraltet → automatisch auf ' + r.auto_update.new_model + ' umgestellt');
      setTimeout(()=>location.reload(),1200);
    }} else {{
      showToast('⚠ Modell veraltet: ' + (r.reason||'Nicht verfügbar'));
    }}
  }}).catch(()=>{{
    btn.disabled=false;
    btn.textContent='🔍 Modell';
    showToast('Verbindungsfehler');
  }});
}}

// Wissen level switching (Bibliothek / Regelsteuerung / Neu)
function showWissenLevel(el, level) {{
  document.querySelectorAll('.wissen-level-tab').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
  document.querySelectorAll('.wissen-level').forEach(l=>l.classList.remove('active'));
  document.getElementById('wissen-level-'+level)?.classList.add('active');
}}

// Wissen sub-tabs (ns: 'wbp' für Bibliothek-Panels, 'wissen' für Regelsteuerung)
function showWissenTab(name, ns) {{
  document.querySelectorAll('.wissen-tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.wissen-panel').forEach(p=>p.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById((ns||'wissen')+'-'+name)?.classList.add('active');
}}

// Wissen actions
function wissenAction(regelId, aktion) {{
  const doIt = function() {{
    _rtlog('ui','wissen_action',aktion+' Regel '+regelId,{{submodul:'wissen',context_type:'regel',context_id:String(regelId)}});
    fetch('/api/wissen/'+regelId+'/'+aktion,{{method:'POST'}}).then(r=>r.json()).then(d=>{{
      if(d.ok) {{
        const labels = {{bestaetigen:'Regel best\u00e4tigt',ablehnen:'Regel abgelehnt',loeschen:'Regel entfernt'}};
        showToast(labels[aktion]||'Aktualisiert');
        const el = document.getElementById('wr-'+regelId);
        if(el && aktion==='loeschen') {{ el.style.opacity='0.2'; setTimeout(()=>el.remove(),300); }}
        else setTimeout(()=>location.reload(),600);
      }}
    }}).catch(()=>showToast('Fehler'));
  }};
  if(aktion === 'loeschen') {{
    showKritischModal(
      '\uD83D\uDDD1 Wissensregel l\u00f6schen',
      'Diese Lernregel wird unwiderruflich gel\u00f6scht. Kira verliert das damit verbundene Wissen.',
      'L\u00d6SCHEN',
      doIt
    );
  }} else {{
    doIt();
  }}
}}

// Regel bearbeiten
function editRegel(id, titel, inhalt, kat) {{
  document.getElementById('er-id').value = id;
  document.getElementById('er-titel').value = titel;
  document.getElementById('er-inhalt').value = inhalt;
  document.getElementById('er-kat').value = kat;
  document.getElementById('editRegelModal').classList.add('open');
}}
function closeEditRegel() {{ document.getElementById('editRegelModal').classList.remove('open'); }}
function saveRegelEdit() {{
  const id     = document.getElementById('er-id').value;
  const kat    = document.getElementById('er-kat').value;
  const titel  = document.getElementById('er-titel').value.trim();
  const inhalt = document.getElementById('er-inhalt').value.trim();
  if(!titel||!inhalt) {{ showToast('Titel und Inhalt erforderlich'); return; }}
  fetch('/api/wissen/'+id+'/update',{{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{kategorie:kat, titel, inhalt}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok) {{ closeEditRegel(); showToast('Regel aktualisiert'); setTimeout(()=>location.reload(),500); }}
    else showToast(d.error||'Fehler');
  }}).catch(()=>showToast('Fehler'));
}}

// Neue Regel hinzufügen
function neueRegel() {{
  const kat    = document.getElementById('nr-kat').value;
  const titel  = document.getElementById('nr-titel').value.trim();
  const inhalt = document.getElementById('nr-inhalt').value.trim();
  if(!titel || !inhalt) {{ showToast('Titel und Inhalt erforderlich'); return; }}
  fetch('/api/wissen/neu',{{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{kategorie:kat, titel, inhalt}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok) {{
      showToast('Regel gespeichert');
      document.getElementById('nr-titel').value='';
      document.getElementById('nr-inhalt').value='';
      setTimeout(()=>location.reload(),600);
    }} else showToast(d.error||'Fehler');
  }}).catch(()=>showToast('Fehler'));
}}

// Kira 3-Modi
function toggleKiraQuick() {{
  const qp = document.getElementById('kiraQuick');
  const fab = document.getElementById('kiraFab');
  if(qp.classList.contains('open')) closeKiraQuick();
  else {{ qp.classList.add('open'); kiraOpen=true; if(fab) fab.classList.add('kira-fab-active'); }}
}}
function closeKiraQuick() {{
  const fab = document.getElementById('kiraFab');
  document.getElementById('kiraQuick').classList.remove('open');
  kiraOpen=false;
  if(fab) fab.classList.remove('kira-fab-active');
}}
function openKiraWorkspace(context) {{
  closeKiraQuick();
  document.getElementById('kiraWorkspace').classList.add('open');
  kiraOpen=true;
  _rtlog('ui','kira_workspace_open','Kira Workspace geoeffnet',{{submodul:'kira',context_type:context}});
  loadKiraHistSidebar();
  if(context==='chat') showKTab('chat');
  else if(context==='aufgabe') showKTab('aufgaben');
  else if(context==='historie') showKTab('historie');
  else if(context==='rechnung') {{ showKTab('chat'); kiraSetQuickActions('rechnung'); }}
  else if(context==='angebot') {{ showKTab('chat'); kiraSetQuickActions('angebot'); }}
  else if(context==='kunde') {{ showKTab('chat'); kiraSetQuickActions('kunde'); }}
  else if(context==='suche') {{ showKTab('chat'); kiraSetQuickActions('suche'); }}
  else showKTab('chat');
}}
function closeKiraWorkspace() {{
  _rtlog('ui','kira_workspace_closed','Kira Workspace geschlossen',{{submodul:'kira'}});
  document.getElementById('kiraWorkspace').classList.remove('open');
  kiraOpen=false;
  localStorage.setItem('kira_dismissed', Date.now());
}}
// Kira Launcher — globales Augen-Tracking + Proximity-Reaktion (3 Varianten)
(function kiraLauncher() {{
  // Konfiguration je Variante: LC/RC=Pupillen-Zentrum, ER=Augen-Radius, IRY=Iris-ry, PR=Pupillen-r
  const VCFG = {{
    'A': {{LC:[34,47],   RC:[66,47],   ER:4,   IRY:9.5, PR:5,   mn:'M38 62 Q50 70 62 62', ms:'M36 60 Q50 72 64 60'}},
    'B': {{LC:[33,47],   RC:[67,47],   ER:6.5, IRY:14,  PR:8.5, mn:'M36 67 Q50 78 64 67', ms:'M34 65 Q50 82 66 65'}},
    'C': {{LC:[35,47.5], RC:[65,47.5], ER:5,   IRY:8.5, PR:6,   mn:'M38 63 Q50 71 62 63', ms:'M36 61 Q50 74 64 61'}}
  }};
  let _mx=window.innerWidth/2, _my=window.innerHeight/2;
  let _bLastAct=Date.now();
  document.addEventListener('mousemove', e=>{{ _mx=e.clientX; _my=e.clientY; _bLastAct=Date.now(); }});

  // ── Gelangweilter Modus ─────────────────────────────────────────────────
  const _BSEQ=['blink','drowsy','blink','drowsy','yawn','drowsy','eye-roll','drowsy','blink','sleep'];
  const _BDUR={{blink:280,drowsy:4000,yawn:2600,'eye-roll':2400,sleep:999999}};
  const _BGAP={{blink:500,drowsy:0,yawn:300,'eye-roll':600,sleep:0}};
  let _bIdx=0, _bStart=0, _bActive=false;

  function _lerp(a,b,t){{return a+(b-a)*Math.min(1,Math.max(0,t));}}

  function _wakeUp(cfg){{
    _bActive=false; _bIdx=0; _bStart=0;
    const iL=document.getElementById('kiraIrisL'), iR=document.getElementById('kiraIrisR');
    const pL=document.getElementById('kiraPupilL'), pR=document.getElementById('kiraPupilR');
    const mth=document.getElementById('kiraMouth');
    if(iL)iL.setAttribute('ry',cfg.IRY);
    if(iR)iR.setAttribute('ry',cfg.IRY);
    if(pL){{pL.setAttribute('r',cfg.PR);pL.setAttribute('cx',cfg.LC[0]);pL.setAttribute('cy',cfg.LC[1]);}}
    if(pR){{pR.setAttribute('r',cfg.PR);pR.setAttribute('cx',cfg.RC[0]);pR.setAttribute('cy',cfg.RC[1]);}}
    if(mth)mth.setAttribute('d',cfg.mn);
  }}

  function _doBoredFrame(now,cfg){{
    const iL=document.getElementById('kiraIrisL'), iR=document.getElementById('kiraIrisR');
    const pL=document.getElementById('kiraPupilL'), pR=document.getElementById('kiraPupilR');
    const mth=document.getElementById('kiraMouth');
    // Gap: wenn _bStart in der Zukunft liegt, warten
    if(now<_bStart) return;
    const phase=_BSEQ[_bIdx%_BSEQ.length];
    const dur=_BDUR[phase];
    const t=(now-_bStart)/dur;

    if(phase==='blink'){{
      // Schnelles Blinzeln: auf→zu→auf
      const f=t<0.5?1-t*2:(t-0.5)*2;
      const ry=Math.max(0.3,cfg.IRY*f), pr=Math.max(0,cfg.PR*f);
      if(iL)iL.setAttribute('ry',ry.toFixed(2));
      if(iR)iR.setAttribute('ry',ry.toFixed(2));
      if(pL){{pL.setAttribute('r',pr.toFixed(2));pL.setAttribute('cx',cfg.LC[0]);pL.setAttribute('cy',cfg.LC[1]);}}
      if(pR){{pR.setAttribute('r',pr.toFixed(2));pR.setAttribute('cx',cfg.RC[0]);pR.setAttribute('cy',cfg.RC[1]);}}
      if(t>=1){{
        if(iL)iL.setAttribute('ry',cfg.IRY);if(iR)iR.setAttribute('ry',cfg.IRY);
        if(pL)pL.setAttribute('r',cfg.PR);if(pR)pR.setAttribute('r',cfg.PR);
        _bIdx++;_bStart=now+_BGAP.blink;
      }}
    }}else if(phase==='drowsy'){{
      // Schwere Lider: Augen gleiten auf 32% zu, Blick sinkt
      const ct=Math.min(1,t/0.7);
      const ry=_lerp(cfg.IRY,cfg.IRY*0.32,ct);
      const py=_lerp(cfg.LC[1],cfg.LC[1]+4,ct);
      if(iL)iL.setAttribute('ry',ry.toFixed(2));
      if(iR)iR.setAttribute('ry',ry.toFixed(2));
      if(pL){{pL.setAttribute('cx',cfg.LC[0]);pL.setAttribute('cy',py.toFixed(2));pL.setAttribute('r',cfg.PR);}}
      if(pR){{pR.setAttribute('cx',cfg.RC[0]);pR.setAttribute('cy',py.toFixed(2));pR.setAttribute('r',cfg.PR);}}
      if(t>=1){{_bIdx++;_bStart=now;}}
    }}else if(phase==='yawn'){{
      // Mund weit auf, Augen kneifen zusammen
      const op=Math.min(1,t<0.4?t/0.4:1);
      const cl=t>0.75?(t-0.75)/0.25:0;
      const ry=cfg.IRY*_lerp(0.32,0.12,op);
      if(iL)iL.setAttribute('ry',ry.toFixed(2));
      if(iR)iR.setAttribute('ry',ry.toFixed(2));
      if(pL){{pL.setAttribute('cx',cfg.LC[0]);pL.setAttribute('cy',cfg.LC[1]);pL.setAttribute('r',cfg.PR);}}
      if(pR){{pR.setAttribute('cx',cfg.RC[0]);pR.setAttribute('cy',cfg.RC[1]);pR.setAttribute('r',cfg.PR);}}
      if(mth){{const qy=_lerp(78,102,op);mth.setAttribute('d','M32 67 Q50 '+qy.toFixed(0)+' 68 67');}}
      if(t>=1){{if(mth)mth.setAttribute('d',cfg.mn);_bIdx++;_bStart=now+_BGAP.yawn;}}
    }}else if(phase==='eye-roll'){{
      // Augen öffnen sich leicht + Pupillen kreisen
      const openT=Math.min(1,t*4);
      const ry=_lerp(cfg.IRY*0.32,cfg.IRY*0.65,openT);
      if(iL)iL.setAttribute('ry',ry.toFixed(2));
      if(iR)iR.setAttribute('ry',ry.toFixed(2));
      const angle=(now%2400)/2400*Math.PI*2;
      const rr=cfg.ER*0.72;
      if(pL){{pL.setAttribute('cx',(cfg.LC[0]+Math.sin(angle)*rr*0.6).toFixed(2));pL.setAttribute('cy',(cfg.LC[1]-Math.cos(angle)*rr*0.4).toFixed(2));pL.setAttribute('r',cfg.PR);}}
      if(pR){{pR.setAttribute('cx',(cfg.RC[0]+Math.sin(angle)*rr*0.6).toFixed(2));pR.setAttribute('cy',(cfg.RC[1]-Math.cos(angle)*rr*0.4).toFixed(2));pR.setAttribute('r',cfg.PR);}}
      if(t>=1){{
        if(pL){{pL.setAttribute('cx',cfg.LC[0]);pL.setAttribute('cy',cfg.LC[1]);}}
        if(pR){{pR.setAttribute('cx',cfg.RC[0]);pR.setAttribute('cy',cfg.RC[1]);}}
        _bIdx++;_bStart=now+_BGAP['eye-roll'];
      }}
    }}else if(phase==='sleep'){{
      // Vollständig zu — schläft
      if(iL)iL.setAttribute('ry','0.4');if(iR)iR.setAttribute('ry','0.4');
      if(pL){{pL.setAttribute('r','0');pL.setAttribute('cx',cfg.LC[0]);pL.setAttribute('cy',cfg.LC[1]);}}
      if(pR){{pR.setAttribute('r','0');pR.setAttribute('cx',cfg.RC[0]);pR.setAttribute('cy',cfg.RC[1]);}}
      // Kurzes Schlaf-Zucken alle ~6s
      const zt=(now%6300)/6300;
      if(zt<0.04){{if(iL)iL.setAttribute('ry',(cfg.IRY*0.15).toFixed(2));if(iR)iR.setAttribute('ry',(cfg.IRY*0.15).toFixed(2));}}
    }}
  }}

  // ── rAF-Hauptschleife ───────────────────────────────────────────────────
  function _frame(){{
    const fab=document.getElementById('kiraFab');
    if(!fab){{requestAnimationFrame(_frame);return;}}
    const r=fab.getBoundingClientRect();
    const cx=r.left+r.width/2, cy=r.top+r.height/2;
    const dx=_mx-cx, dy=_my-cy;
    const dist=Math.sqrt(dx*dx+dy*dy);
    const v=fab.dataset.variant||'B', cfg=VCFG[v]||VCFG['B'];
    const pL=document.getElementById('kiraPupilL'), pR=document.getElementById('kiraPupilR');
    const halo=document.getElementById('kiraGlowHalo'), svg=document.getElementById('kiraCharSVG');
    const D_FAR=Math.min(window.innerWidth,window.innerHeight)*(window._kiraProxRadius||0.5);
    const D_NEAR=window._kiraBounce!==undefined?window._kiraBounce:130;
    const prox=Math.max(0,1-dist/D_FAR);
    const proxNear=D_NEAR>0?Math.max(0,1-dist/D_NEAR):0;
    const now=Date.now();
    const idleSec=(now-_bLastAct)/1000;
    const idleEnabled=window._kiraIdleEnabled!==false;
    const idleDelay=window._kiraIdleDelay||10;

    if(idleEnabled && idleSec>idleDelay){{
      // ── Gelangweilter Modus ──
      if(!_bActive){{_bActive=true;_bIdx=0;_bStart=now;fab.classList.add('kira-bored');}}
      _doBoredFrame(now,cfg);
      if(halo)halo.setAttribute('opacity','0');
      if(svg&&!fab.classList.contains('kira-fab-active'))svg.style.transform='scale(1)';
      fab.classList.remove('kira-excited');
    }}else{{
      // ── Aktiv-Modus ──
      if(_bActive){{_wakeUp(cfg);fab.classList.remove('kira-bored');}}
      if(pL&&pR&&dist>1){{
        const er=cfg.ER, nx=dx/dist, ny=dy/dist;
        pL.setAttribute('cx',String((cfg.LC[0]+nx*er).toFixed(2)));
        pL.setAttribute('cy',String((cfg.LC[1]+ny*er).toFixed(2)));
        pR.setAttribute('cx',String((cfg.RC[0]+nx*er).toFixed(2)));
        pR.setAttribute('cy',String((cfg.RC[1]+ny*er).toFixed(2)));
      }}
      if(halo)halo.setAttribute('opacity',String((prox*0.8).toFixed(3)));
      if(svg&&!fab.classList.contains('kira-fab-active'))svg.style.transform='scale('+(1+prox*0.2)+')';
      if(proxNear>0.35)fab.classList.add('kira-excited');
      else fab.classList.remove('kira-excited');
    }}
    requestAnimationFrame(_frame);
  }}

  function addFabListeners(fab){{
    fab.addEventListener('mousedown',()=>{{
      const v=fab.dataset.variant||'B', cfg=VCFG[v]||VCFG['B'];
      const svg=document.getElementById('kiraCharSVG'), mth=document.getElementById('kiraMouth');
      if(svg){{svg.style.transition='transform .09s';svg.style.transform='scale(0.82)';}}
      if(mth){{mth.setAttribute('d',cfg.ms);setTimeout(()=>mth.setAttribute('d',cfg.mn),750);}}
      setTimeout(()=>{{const s=document.getElementById('kiraCharSVG');if(s){{s.style.transition='transform .3s cubic-bezier(.18,.89,.32,1.28)';s.style.transform='scale(1.12)';}}}},110);
    }});
  }}

  window.switchKiraVariant=function(v){{
    const fab=document.getElementById('kiraFab'), tmpl=document.getElementById('kira-tmpl-'+v);
    if(!fab||!tmpl)return;
    const oldSvg=fab.querySelector('.kira-char-svg');
    if(oldSvg){{
      const div=document.createElement('div');
      div.innerHTML=tmpl.innerHTML;
      const newSvg=div.firstElementChild;
      if(newSvg)fab.replaceChild(newSvg,oldSvg);
    }}
    fab.dataset.variant=v;
    const cfg=VCFG[v]||VCFG['B'];
    const pL=document.getElementById('kiraPupilL'), pR=document.getElementById('kiraPupilR');
    if(pL){{pL.setAttribute('cx',cfg.LC[0]);pL.setAttribute('cy',cfg.LC[1]);}}
    if(pR){{pR.setAttribute('cx',cfg.RC[0]);pR.setAttribute('cy',cfg.RC[1]);}}
  }};

  const fab=document.getElementById('kiraFab');
  if(fab){{
    window._kiraProxRadius  = parseFloat(fab.dataset.proxRadius||'0.5');
    window._kiraBounce      = parseInt(fab.dataset.bounceDist||'130');
    window._kiraIdleEnabled = fab.dataset.idleEnabled!=='false';
    window._kiraIdleDelay   = parseInt(fab.dataset.idleDelay||'10');
    const _ksz=parseInt(fab.dataset.size||'112');
    fab.style.width=_ksz+'px'; fab.style.height=_ksz+'px';
    addFabListeners(fab);
    if(!window._kiraRafRunning){{window._kiraRafRunning=true;_frame();}}
  }}
}})();

// Legacy compat
function toggleKira(){{ toggleKiraQuick(); }}
function openKiraNaked(){{ openKiraWorkspace('chat'); }}
function closeKira(){{ closeKiraWorkspace(); closeKiraQuick(); }}

// Kira tabs / context switching
function showKTab(name){{
  // Update left context panel active state
  document.querySelectorAll('.kw-ctx-item[data-tab]').forEach(c=>c.classList.remove('active'));
  const activeNav = document.querySelector('.kw-ctx-item[data-tab="'+name+'"]');
  if(activeNav) activeNav.classList.add('active');
  document.querySelectorAll('[id^=kc-]').forEach(c=>c.style.display='none');
  const content = document.getElementById('kc-'+name);
  if(content) content.style.display = name==='chat' ? 'flex' : 'block';
  // Quick bar only in chat
  const qbar = document.getElementById('kwQuickBar');
  if(qbar) qbar.style.display = name==='chat' ? '' : 'none';
  if(name==='aufgaben') loadKiraInsights('aufgaben');
  if(name==='muster') loadKiraInsights('muster');
  if(name==='kwissen') loadKiraInsights('kwissen');
  if(name==='historie') loadKiraHistorie();
}}

// Kira Insights laden und rendern
let kiraInsightsCache = null;
function loadKiraInsights(tab) {{
  const render = (data) => {{
    if(tab==='aufgaben') renderKiraAufgaben(data);
    if(tab==='muster') renderKiraMuster(data);
    if(tab==='kwissen') renderKiraLernen(data);
  }};
  if(kiraInsightsCache) {{ render(kiraInsightsCache); return; }}
  fetch('/api/kira/insights').then(r=>r.json()).then(data=>{{
    kiraInsightsCache = data;
    render(data);
  }}).catch(()=>{{}});
}}

function renderKiraHome(data) {{
  // With LLM chat, proactive check pre-fills a message
  const aufgaben = data.aufgaben || [];
  if(aufgaben.length > 0 && !kiraSessionId) {{
    // Auto-suggest in chat
    const input = document.getElementById('kiraInput');
    if(input && !input.value) {{
      const top = aufgaben[0];
      input.placeholder = 'z.B. "' + (top.text||'').substring(0,40) + '..."';
    }}
  }}
}}

function renderKiraAufgaben(data) {{
  const el = document.getElementById('kira-aufgaben-list');
  if(!el) return;
  const aufgaben = data.aufgaben || [];
  if(aufgaben.length === 0) {{ el.innerHTML = '<div style="color:#50c878;padding:10px">Keine offenen Aufgaben.</div>'; return; }}
  let html = '';
  aufgaben.forEach(a => {{
    const pcls = a.prio >= 3 ? 'kira-prio-high' : a.prio >= 2 ? 'kira-prio-med' : 'kira-prio-low';
    html += '<div class="kira-card kira-task-card '+pcls+'" onclick="'+a.action+';showKTab(\\'chat\\');kiraSetQuickActions(\\'aufgabe\\')" style="cursor:pointer"><div class="kira-card-meta">'+a.text+'</div></div>';
  }});
  el.innerHTML = html;
}}

function renderKiraMuster(data) {{
  const el = document.getElementById('kira-muster-content');
  if(!el) return;
  const m = data.muster || {{}};
  let html = '<div class="kira-sec"><div class="kira-sec-title">Aus deinen Daten gelernt</div>';
  if(m.zahlungsdauer_avg) {{
    html += '<div class="kira-card"><div class="kira-card-meta"><strong>Zahlungsdauer</strong><br>\u00D8 '+m.zahlungsdauer_avg+' Tage &middot; Min: '+m.zahlungsdauer_min+' &middot; Max: '+m.zahlungsdauer_max+' &middot; Basis: '+m.zahlungsdauer_n+' Rechnungen</div></div>';
  }}
  if(m.angebotsquote !== undefined) {{
    html += '<div class="kira-card"><div class="kira-card-meta"><strong>Angebotsquote</strong><br>'+m.angebotsquote+'% angenommen ('+m.angebote_angenommen+' von '+m.angebote_total+')</div></div>';
  }}
  if(m.ablehngruende) {{
    html += '<div class="kira-card"><div class="kira-card-meta"><strong>Ablehnungsgründe</strong><br>';
    Object.entries(m.ablehngruende).forEach(([g,n]) => {{ html += n+'x '+escH(g)+'<br>'; }});
    html += '</div></div>';
  }}
  if(m.annahmegruende) {{
    html += '<div class="kira-card"><div class="kira-card-meta"><strong>Annahmegründe</strong><br>';
    Object.entries(m.annahmegruende).forEach(([g,n]) => {{ html += n+'x '+escH(g)+'<br>'; }});
    html += '</div></div>';
  }}
  if(!m.zahlungsdauer_avg && !m.angebotsquote) {{
    html += '<div class="kira-card"><div class="kira-card-meta" style="color:var(--muted)">Noch nicht genug Daten. Muster werden erkannt, sobald du mehr Rechnungen und Angebote bearbeitest.</div></div>';
  }}
  html += '</div>';
  el.innerHTML = html;
}}

function renderKiraLernen(data) {{
  const el = document.getElementById('kira-lernen-list');
  if(!el) return;
  const lernen = data.lernen || [];
  if(lernen.length === 0) {{ el.innerHTML = '<div style="color:var(--muted);padding:10px">Noch keine Erkenntnisse gespeichert. Bearbeite Rechnungen und Angebote mit dem Kira-Dialog, um Wissen aufzubauen.</div>'; return; }}
  let html = '<div class="kira-sec"><div class="kira-sec-title">Erkenntnisse aus deiner Arbeit</div>';
  lernen.forEach(l => {{
    html += '<div class="kira-card"><div class="kira-card-meta"><strong>'+escH(l.titel)+'</strong><br><span style="color:rgba(255,255,255,.7)">'+escH(l.inhalt)+'</span><br><span style="color:var(--muted);font-size:10px">'+escH(l.datum||'')+'</span></div></div>';
  }});
  html += '</div>';
  el.innerHTML = html;
}}

// ── Kira Chat ────────────────────────────────────────────────
let kiraSessionId = null;
let kiraSending = false;

function sendKiraMsg() {{
  const input = document.getElementById('kiraInput');
  const msg = input.value.trim();
  if(!msg || kiraSending) return;
  kiraSending = true;
  _rtlog('ui','kira_msg_sent','Nachricht an Kira gesendet',{{submodul:'kira',context_id:kiraSessionId}});
  input.value = '';
  input.style.height = 'auto';
  appendKiraMsg('user', msg);
  // Typing indicator
  const typing = document.createElement('div');
  typing.className = 'kira-typing';
  typing.id = 'kira-typing';
  typing.innerHTML = '<span></span><span></span><span></span>';
  document.getElementById('kiraChatArea').appendChild(typing);
  scrollKiraChat();
  const btn = document.getElementById('kiraSendBtn');
  btn.disabled = true;
  btn.style.opacity = '.4';
  fetch('/api/kira/chat', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{nachricht: msg, session_id: kiraSessionId}})
  }}).then(r=>r.json()).then(data=>{{
    document.getElementById('kira-typing')?.remove();
    if(data.error) {{
      appendKiraMsg('error', data.error);
      if(data.needs_api_key) appendKiraMsg('system', 'Bitte trage deinen API Key unter Einstellungen > KI-Assistent ein.');
    }} else {{
      kiraSessionId = data.session_id;
      const provInfo = data.provider ? (data.model ? data.provider+' ('+data.model+')' : data.provider) : '';
      const fallback = data.fallback_info && data.fallback_info.length ? data.fallback_info : null;
      appendKiraMsg('assistant', data.antwort, data.tools_verwendet, provInfo, fallback);
    }}
    kiraSending = false;
    btn.disabled = false;
    btn.style.opacity = '1';
    input.focus();
  }}).catch(()=>{{
    document.getElementById('kira-typing')?.remove();
    appendKiraMsg('error', 'Verbindungsfehler.');
    kiraSending = false;
    btn.disabled = false;
    btn.style.opacity = '1';
  }});
}}

var _kiraMsgIdx = 0;  // Zähler für Feedback-Buttons (Paket 6, session-oo)

function appendKiraMsg(rolle, text, tools, providerInfo, fallbackInfo) {{
  const area = document.getElementById('kiraChatArea');
  const welcome = area.querySelector('.kira-welcome');
  if(welcome) welcome.remove();
  const now = new Date().toLocaleTimeString('de-DE',{{hour:'2-digit',minute:'2-digit'}});
  const wrap = document.createElement('div');
  if(rolle==='user') {{
    wrap.className = 'msg user';
    wrap.innerHTML = '<div class="msg-head"><span class="msg-name u">Du</span><span class="msg-time">'+now+'</span></div>'
      +'<div class="msg-bubble">'+escH(text).replace(/\\n/g,'<br>')+'</div>';
  }} else if(rolle==='assistant') {{
    wrap.className = 'msg kira';
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = kiraFormatText(text);
    if(tools && tools.length) {{
      const ti = document.createElement('div');
      ti.className = 'kira-tools-used';
      ti.innerHTML = tools.map(t=>'<span class="kira-tool-badge">'+escH(t)+'</span>').join(' ');
      bubble.appendChild(ti);
    }}
    if(providerInfo || (fallbackInfo && fallbackInfo.length)) {{
      const meta = document.createElement('div');
      meta.style.cssText = 'font-size:10px;color:var(--muted);margin-top:8px;display:flex;align-items:center;gap:6px;flex-wrap:wrap';
      if(providerInfo) meta.innerHTML = '<span style="opacity:.65">via '+escH(providerInfo)+'</span>';
      if(fallbackInfo && fallbackInfo.length) {{
        meta.innerHTML += '<span style="color:#e8a545;opacity:.8" title="'+escH(fallbackInfo.join(', '))+'">⚡ Fallback</span>';
      }}
      bubble.appendChild(meta);
    }}
    const msgIdx = ++_kiraMsgIdx;
    wrap.innerHTML = '<div class="msg-head"><span class="msg-name">Kira</span><span class="msg-time">'+now+'</span></div>';
    wrap.appendChild(bubble);
    // Feedback-Buttons (Paket 6, session-oo) — DOM-Methoden statt innerHTML (Quote-Bug-Fix)
    const fbDiv = document.createElement('div');
    fbDiv.style.cssText = 'display:flex;gap:6px;margin-top:6px;padding-left:2px;';
    var _btnStyle = 'background:none;border:1px solid #333;border-radius:6px;color:#666;font-size:12px;padding:2px 8px;cursor:pointer';
    var _btn1 = document.createElement('button');
    _btn1.innerHTML = '&#x1F44D;'; _btn1.title = 'Hilfreich'; _btn1.style.cssText = _btnStyle;
    (function(_mi){{ _btn1.onclick = function(){{ kirafb('gut', _mi, this); }}; }})(msgIdx);
    var _btn2 = document.createElement('button');
    _btn2.innerHTML = '&#x1F44E;'; _btn2.title = 'Nicht hilfreich'; _btn2.style.cssText = _btnStyle;
    (function(_mi, _tx){{ _btn2.onclick = function(){{ kirafb('schlecht', _mi, this, _tx); }}; }})(msgIdx, text.substring(0,500));
    fbDiv.appendChild(_btn1); fbDiv.appendChild(_btn2);
    wrap.appendChild(fbDiv);
  }} else if(rolle==='error') {{
    wrap.className = 'msg error';
    wrap.innerHTML = '<div class="msg-bubble">'+escH(text)+'</div>';
  }} else {{
    wrap.className = 'msg system';
    wrap.innerHTML = '<div class="msg-bubble">'+escH(text)+'</div>';
  }}
  area.appendChild(wrap);
  scrollKiraChat();
}}

function kiraFormatText(text) {{
  return escH(text)
    .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\\n- /g, '<br>&bull; ')
    .replace(/\\n(\\d+)\\. /g, '<br>$1. ')
    .replace(/\\n/g, '<br>');
}}

function scrollKiraChat() {{
  const area = document.getElementById('kiraChatArea');
  setTimeout(()=>{{ area.scrollTop = area.scrollHeight; }}, 50);
}}

function newKiraChat() {{
  _rtlog('ui','new_kira_chat','Neuer Kira-Chat gestartet',{{submodul:'kira'}});
  kiraSessionId = null;
  const area = document.getElementById('kiraChatArea');
  area.innerHTML = '<div class="kira-welcome"><div class="kira-welcome-icon">K</div><div class="kira-welcome-text">Neuer Chat gestartet. Wie kann ich helfen?</div></div>';
  document.getElementById('kiraInput').value = '';
  showKTab('chat');
}}

// Hard Reset — Cache umgehen, alles neu laden
// Server komplett neu starten — killt alle Instanzen, startet neu, lädt Seite
async function serverNeustart() {{
  // Sofort Ladescreen zeigen — kein schwarzer Tab, kein 404
  document.open();
  document.write('<!doctype html><html><head><meta charset=utf-8><style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#0d0d0d;color:#ccc;font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:12px}}.spin{{font-size:36px;animation:rot 1s linear infinite}}@keyframes rot{{to{{transform:rotate(360deg)}}}}p{{font-size:15px;opacity:.8}}small{{font-size:12px;opacity:.45}}</style></head><body><div class=spin>↻</div><p>Server wird neu gestartet …</p><small id=s>0s</small><script>let t=0;setInterval(()=>{{t++;document.getElementById("s").textContent=t+"s";}},1000);<\\/script></body></html>');
  document.close();
  // Neustart anstoßen (Server antwortet kurz bevor er sich killt)
  try {{ await fetch('/api/server/neustart',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:'{{}}'}}); }} catch(e) {{}}
  // Warten bis neuer Server antwortet
  let attempts = 0;
  const poll = setInterval(async ()=>{{
    attempts++;
    try {{
      const r = await fetch('/api/server/version',{{cache:'no-store'}});
      if(r.ok) {{ clearInterval(poll); window.location.href = '/?nocache='+Date.now(); }}
    }} catch(e) {{
      if(attempts > 40) {{ clearInterval(poll); window.location.href = '/?nocache='+Date.now(); }}
    }}
  }}, 500);
}}

// Briefing aktualisieren
function refreshBriefing() {{
  const el = document.getElementById('kira-briefing');
  if(!el) return;
  el.style.opacity = '.5';
  fetch('/api/kira/briefing/regenerate').then(r=>r.json()).then(data=>{{
    if(data.zusammenfassung) {{
      location.reload();
    }} else {{
      el.style.opacity = '1';
      showToast(data.error || 'Briefing-Fehler');
    }}
  }}).catch(()=>{{ el.style.opacity='1'; showToast('Fehler'); }});
}}

// Monitor-Status prüfen (alle 30s) — aktualisiert Header-Chip
// ── Kira-Aktivitäten ─────────────────────────────────────────────────────────
function loadKiraAktivitaeten() {{
  const seit = document.getElementById('kira-akt-seit')?.value || '24h';
  const typ  = document.getElementById('kira-akt-typ')?.value  || '';
  const list = document.getElementById('kira-akt-list');
  if(!list) return;
  list.innerHTML = '<div style="color:#888;padding:20px 0">Lade…</div>';
  fetch(`/api/kira/aktivitaeten?seit=${{seit}}&typ=${{encodeURIComponent(typ)}}`)
    .then(r=>r.json()).then(data=>{{
      if(!data.eintraege || !data.eintraege.length) {{
        list.innerHTML = '<div style="color:#888;padding:20px 0">Keine Kira-Aktivitäten im gewählten Zeitraum.</div>';
        return;
      }}
      list.innerHTML = data.eintraege.map(e=>{{
        const icon = e.actor_type === 'kira_autonom' ? '🤖' : '👤';
        const badge = e.actor_type === 'kira_autonom'
          ? '<span style="background:#2563eb22;color:#2563eb;border-radius:4px;padding:1px 7px;font-size:11px;margin-left:6px">autonom</span>'
          : '<span style="background:#16a34a22;color:#16a34a;border-radius:4px;padding:1px 7px;font-size:11px;margin-left:6px">bestätigt</span>';
        return `<div style="display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border-soft)">
          <div style="font-size:20px;line-height:1.4">${{icon}}</div>
          <div style="flex:1;min-width:0">
            <div style="font-size:13px;font-weight:600;color:var(--text-main)">${{e.action || '—'}}${{badge}}</div>
            <div style="font-size:12px;color:var(--text-sub);margin-top:2px;white-space:pre-wrap;word-break:break-word">${{e.summary || ''}}</div>
          </div>
          <div style="font-size:11px;color:var(--text-faint);white-space:nowrap">${{e.ts ? e.ts.slice(0,16).replace('T',' ') : ''}}</div>
        </div>`;
      }}).join('');
    }}).catch(err=>{{
      list.innerHTML = `<div style="color:#e11d48;padding:16px 0">Fehler: ${{err.message}}</div>`;
    }});
}}

// ── Aktivitätsprotokoll ──────────────────────────────────────────────────────
let _protoOffset = 0;
function loadProtokoll(append) {{
  const bereich = document.getElementById('proto-filter-bereich')?.value || '';
  const status  = document.getElementById('proto-filter-status')?.value  || '';
  if(!append) _protoOffset = 0;
  const url = `/api/aktivitaeten?limit=100&offset=${{_protoOffset}}&bereich=${{encodeURIComponent(bereich)}}&status=${{encodeURIComponent(status)}}`;
  fetch(url,{{cache:'no-store'}}).then(r=>r.json()).then(data=>{{
    const entries = data.entries || [];
    const stats   = data.stats   || {{}};
    // Stats-Bar
    const sb = document.getElementById('proto-stats');
    if(sb) {{
      const fStr = stats.fehler > 0 ? `<span class="ps-fehler"><b>${{stats.fehler}}</b> Fehler</span>` : '<span>Keine Fehler</span>';
      sb.innerHTML = `<span><b>${{stats.total}}</b> Einträge gesamt</span><span>&bull;</span>${{fStr}}<span>&bull;</span><span>Letzte Aktivität: ${{_fmtProtoTime(stats.letzte)}}</span>`;
    }}
    // Fehler-Badge in Sidebar
    const badge = document.getElementById('proto-fehler-badge');
    if(badge) {{
      if(stats.fehler > 0) {{ badge.textContent = stats.fehler; badge.style.display = ''; }}
      else badge.style.display = 'none';
    }}
    // Tabelle
    const tbody = document.getElementById('proto-body');
    if(!tbody) return;
    if(!append) tbody.innerHTML = '';
    if(!entries.length && !append) {{
      tbody.innerHTML = '<tr><td colspan=6 style="text-align:center;padding:40px;color:var(--muted)">Keine Einträge</td></tr>';
      return;
    }}
    entries.forEach(e=>{{
      const tr = document.createElement('tr');
      const stCls = (e.status==='fehler'?'fehler':e.status==='warnung'?'warnung':'ok');
      const fehlerTip = e.fehler_text ? ` title="${{e.fehler_text.replace(/"/g,"'").substring(0,200)}}"` : '';
      tr.innerHTML = `
        <td style="white-space:nowrap;color:var(--text-secondary)">${{_fmtProtoTime(e.zeitstempel)}}</td>
        <td><span class="proto-bereich">${{e.bereich||''}}</span></td>
        <td>${{e.aktion||''}}</td>
        <td style="color:var(--text-secondary);max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${{(e.details||'').replace(/"/g,"'")}}">${{e.details||''}}</td>
        <td${{fehlerTip}}><span class="proto-st ${{stCls}}">${{e.status||'ok'}}</span></td>
        <td style="color:var(--text-secondary)">${{e.dauer_ms!=null?e.dauer_ms+'ms':''}}</td>`;
      tbody.appendChild(tr);
    }});
    _protoOffset += entries.length;
    const more = document.getElementById('proto-load-more');
    if(more) more.style.display = entries.length >= 100 ? '' : 'none';
  }}).catch(()=>{{}});
}}
function _fmtProtoTime(ts) {{
  if(!ts) return '—';
  try {{
    const d = new Date(ts); const now = new Date();
    const diff = (now - d) / 1000;
    if(diff < 60) return 'gerade eben';
    if(diff < 3600) return Math.floor(diff/60) + ' Min.';
    if(diff < 86400) return 'Heute ' + d.toTimeString().slice(0,5);
    if(diff < 172800) return 'Gestern ' + d.toTimeString().slice(0,5);
    return d.toLocaleDateString('de-DE',{{day:'2-digit',month:'2-digit'}}) + ' ' + d.toTimeString().slice(0,5);
  }} catch(e) {{ return ts; }}
}}
function copyProtoCSV() {{
  const rows = [];
  document.querySelectorAll('#proto-body tr').forEach(tr=>{{
    const cells = Array.from(tr.querySelectorAll('td')).map(td=>'"'+td.textContent.trim().replace(/"/g,'""')+'"');
    rows.push(cells.join(';'));
  }});
  navigator.clipboard.writeText('Zeit;Bereich;Aktion;Details;Status;Dauer\\n'+rows.join('\\n'))
    .then(()=>showToast('In Zwischenablage kopiert'))
    .catch(()=>showToast('Kopieren fehlgeschlagen'));
}}
// Fehler-Badge beim Laden aktualisieren
(function() {{
  function checkProtoBadge() {{
    fetch('/api/aktivitaeten?limit=1',{{cache:'no-store'}}).then(r=>r.json()).then(d=>{{
      const badge = document.getElementById('proto-fehler-badge');
      if(!badge) return;
      const f = (d.stats||{{}}).fehler||0;
      if(f>0) {{ badge.textContent=f; badge.style.display=''; }} else badge.style.display='none';
    }}).catch(()=>{{}});
  }}
  setTimeout(checkProtoBadge, 3000);
  setInterval(checkProtoBadge, 60000);
}})();

function checkMonitorStatus() {{
  fetch('/api/monitor/status').then(r=>r.json()).then(data=>{{
    const chip = document.getElementById('monitorStatusChip');
    const txt = document.getElementById('monitorStatusText');
    const dot = document.querySelector('#monitorStatusChip .chip-dot');
    if(!chip) return;
    if(data.running) {{
      chip.className = 'top-chip ok';
      if(txt) txt.textContent = 'Verbunden';
      if(dot) {{ dot.style.background='#639922'; }}
      chip.title = 'Mail-Monitor aktiv' + (data.last_poll ? ' — '+new Date(data.last_poll).toLocaleTimeString('de-DE') : '');
    }} else {{
      chip.className = 'top-chip';
      chip.style.background='#FCEBEB';chip.style.borderColor='#F7C1C1';chip.style.color='#A32D2D';
      if(txt) txt.textContent = 'Offline';
      chip.title = 'Mail-Monitor inaktiv';
    }}
  }}).catch(()=>{{}});
}}
setInterval(checkMonitorStatus, 30000);
setTimeout(checkMonitorStatus, 2000);

// Server-Shutdown Bestätigung beim Tab-Schließen
// Kein beforeunload-Dialog mehr — Server läuft im Hintergrund weiter

// Server stoppen wenn Fenster geschlossen wird (optional über Button)
function shutdownServer() {{
  if(confirm('Server komplett herunterfahren?')) {{
    fetch('/api/shutdown', {{method:'POST'}}).then(()=>{{
      document.title = 'Kira - Gestoppt';
      document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;color:#bda27c;font-size:20px">Server gestoppt. Fenster kann geschlossen werden.</div>';
    }}).catch(()=>{{}});
  }}
}}

function loadKiraHistorie() {{
  fetch('/api/kira/conversations').then(r=>r.json()).then(data=>{{
    const el = document.getElementById('kira-historie-list');
    if(!data || !data.length) {{
      el.innerHTML = '<div style="color:var(--muted);padding:10px">Noch keine Konversationen gespeichert.</div>';
      return;
    }}
    let html = '<div class="kira-sec"><div class="kira-sec-title">Bisherige Konversationen</div>';
    data.forEach(c=>{{
      const datum = c.gestartet ? new Date(c.gestartet).toLocaleString('de-DE',{{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}}) : '';
      html += '<div class="kira-card clickable" onclick="loadKiraConv(\\\''+c.session_id+'\\\')">'+
        '<div class="kira-card-title">'+escH(c.vorschau||'(Leer)')+'</div>'+
        '<div class="kira-card-meta">'+datum+' &middot; '+c.nachrichten+' Nachr. &middot; '+
        ((c.tokens?.input||0)+(c.tokens?.output||0))+' Tokens</div></div>';
    }});
    html += '</div>';
    el.innerHTML = html;
  }}).catch(()=>{{}});
}}

function loadKiraConv(sessionId) {{
  _rtlog('ui','kira_conv_loaded','Konversation geladen',{{submodul:'kira',context_type:'konversation',context_id:String(sessionId)}});
  kiraSessionId = sessionId;
  showKTab('chat');
  const area = document.getElementById('kiraChatArea');
  area.innerHTML = '<div style="color:var(--muted);font-size:12px;padding:8px">Lade Konversation&hellip;</div>';
  fetch('/api/kira/conversation?session_id='+sessionId).then(r=>r.json()).then(messages=>{{
    area.innerHTML = '';
    messages.forEach(m=>{{
      if(m.rolle==='user' || m.rolle==='assistant') appendKiraMsg(m.rolle, m.nachricht||'');
    }});
  }}).catch(()=>{{
    area.innerHTML = '<div style="color:#e84545;padding:8px">Fehler beim Laden.</div>';
  }});
}}
// ── Kira Workspace: neue Hilfsfunktionen ────────────────────────────────────

// Kontext-Bar setzen
function setKiraContextBar(mode, title, tags) {{
  const bar = document.getElementById('kwCbar');
  if(!bar) return;
  const mEl = document.getElementById('kwCbarMode');
  const tEl = document.getElementById('kwCbarTitle');
  const gEl = document.getElementById('kwCbarTags');
  if(mEl) mEl.textContent = mode;
  if(tEl) tEl.textContent = title || '';
  if(gEl) {{
    gEl.innerHTML = (tags||[]).map(t=>`<span class="kw-cbar-tag">${{escH(t)}}</span>`).join(' ');
  }}
  bar.style.display = '';
}}

// Kontext-Bar löschen
function clearKiraContext() {{
  const bar = document.getElementById('kwCbar');
  if(bar) bar.style.display = 'none';
  kiraSetQuickActions('frage');
}}

// Quick-Actions je Kontext-Typ setzen
function kiraSetQuickActions(typ) {{
  const bar = document.getElementById('kwQuickBar');
  if(!bar) return;
  const sets = {{
    frage:    ['Fasse zusammen','Was schlägst du vor?','Erklär mir das','Erstelle einen Entwurf'],
    aufgabe:  ['Analysiere die Aufgabe','Erstelle einen Aktionsplan','Risiko bewerten','Nachfass-Vorlage'],
    rechnung: ['Rechnung prüfen','Skonto berechnen','Zahlungserinnerung','Buchungshinweis'],
    angebot:  ['Angebot analysieren','Nachfass-Text erstellen','Chancen bewerten','Ablehnungsgrund'],
    kunde:    ['Kundenhistorie zusammenfassen','Offene Posten','Kommunikationsnotiz','Nächster Schritt'],
    suche:    ['Suche in Mails','Suche in Aufgaben','Suche in Wissen','Volltext-Suche'],
    dokument: ['Zusammenfassen','Kernaussagen','Aktionspunkte','Fragen generieren'],
    mail:     ['Was ist zu tun?','Antwort vorschlagen','Aufgabe daraus erstellen','Risiko einschätzen','Weiterleiten an?'],
  }};
  const items = sets[typ] || sets.frage;
  bar.innerHTML = '<span class="kw-quick-lbl">Schnell:</span>' +
    items.map(t=>`<span class="kw-qb" onclick="kiraAddPrompt('${{t.replace(/'/g,"\\'")}}')">${{escH(t)}}</span>`).join('');
}}

// Text in Input-Box einfügen
function kiraAddPrompt(text) {{
  const inp = document.getElementById('kiraInput');
  if(!inp) return;
  inp.value = inp.value ? inp.value + '\\n' + text : text;
  inp.style.height = 'auto';
  inp.style.height = Math.min(inp.scrollHeight, 120) + 'px';
  inp.focus();
}}

// Werkzeuge-Panel ein-/ausklappen
function toggleKiraTools() {{
  const t = document.getElementById('kwTools');
  if(t) t.classList.toggle('collapsed');
}}

// Tools-Panel befüllen
function setKiraTools(attachments, rules, actions) {{
  const a = document.getElementById('kw-tools-attachments');
  const r = document.getElementById('kw-tools-rules');
  const n = document.getElementById('kw-tools-actions');
  if(a) a.innerHTML = (attachments||[]).length ? attachments.map(f=>`<div class="kw-t-att">&#x1F4CE; ${{escH(f)}}</div>`).join('') : '<div class="kw-t-item-sub" style="color:var(--muted)">Keine Anhänge</div>';
  if(r) r.innerHTML = (rules||[]).length ? rules.map(x=>`<div class="kw-t-rule"><div class="kw-t-rule-h">${{escH(x.titel||x)}}</div>${{x.inhalt?escH(x.inhalt):''}}</div>`).join('') : '<div class="kw-t-item-sub" style="color:var(--muted)">Keine aktiven Regeln</div>';
  if(n) n.innerHTML = (actions||[]).length ? actions.map(x=>`<div class="kw-t-next">→ ${{escH(x)}}</div>`).join('') : '<div class="kw-t-item-sub" style="color:var(--muted)">Keine Aktionen vorgeschlagen</div>';
}}

// Quick Panel: Direkt senden
function kqDirectSend() {{
  _rtlog('ui','kq_direct_send','Quick Panel Direkt-Senden',{{submodul:'kira'}});
  const inp = document.getElementById('kqInput');
  if(!inp || !inp.value.trim()) return;
  const msg = inp.value.trim();
  inp.value = '';
  openKiraWorkspace('chat');
  setTimeout(()=>{{
    const ki = document.getElementById('kiraInput');
    if(ki) {{ ki.value = msg; sendKiraMsg(); }}
  }}, 80);
}}

// Modus-Menü (In Planung)
function toggleKiraModeMenu() {{
  showToast('Modus-Auswahl — In Planung');
}}

// Verlaufs-Sidebar laden und rendern
function loadKiraHistSidebar() {{
  fetch('/api/kira/conversations').then(r=>r.json()).then(data=>{{
    renderKiraHistSidebar(data);
  }}).catch(()=>{{}});
}}

function renderKiraHistSidebar(data) {{
  const el = document.getElementById('kw-hist-sidebar');
  if(!el) return;
  if(!data || !data.length) {{
    el.innerHTML = '<div style="color:var(--muted);font-size:11px;padding:4px 16px">Noch keine Konversationen.</div>';
    return;
  }}
  const chipMap = {{}};
  el.innerHTML = data.slice(0,12).map(c=>{{
    const d = c.gestartet ? new Date(c.gestartet).toLocaleDateString('de-DE',{{day:'2-digit',month:'2-digit'}}) : '';
    const preview = (c.vorschau||'(Leer)').substring(0,36);
    return `<div class="kw-ctx-item" onclick="loadKiraConv('${{c.session_id}}')" style="cursor:pointer">
      <span class="kw-ctx-chip mail">↻</span>
      <div class="kw-ctx-body"><div class="kw-ctx-title" title="${{escH(c.vorschau||'')}}">${{escH(preview)}}${{(c.vorschau||{{}}).length>36?'&hellip;':''}} </div>
      <div class="kw-ctx-sub">${{d}} &middot; ${{c.nachrichten||0}} Nachr.</div></div>
    </div>`;
  }}).join('');
}}


// Kira proaktiv öffnen wenn wichtige Aufgaben da sind
function kiraProaktivCheck() {{
  const dismissed = parseInt(localStorage.getItem('kira_dismissed')||'0');
  const cooldown = 30 * 60 * 1000;
  if(Date.now() - dismissed < cooldown) return;
  fetch('/api/kira/insights').then(r=>r.json()).then(data=>{{
    kiraInsightsCache = data;
    const hochprio = (data.aufgaben||[]).filter(a => a.prio >= 2);
    if(hochprio.length > 0) {{
      // Only pulse the FAB, never auto-open the panel
      const fab = document.querySelector('.kira-fab');
      if(fab) fab.classList.add('kira-fab-pulse');
      renderKiraHome(data);
    }}
  }}).catch(()=>{{}});
}}

// Mit Kira besprechen – Chat öffnen mit Kontext
function openKira(taskId){{
  const ctx = KIRA_CTX[taskId];
  if(!ctx){{ showToast('Kein Kontext'); return; }}
  openKiraNaked();
  showKTab('chat');
  kiraSetQuickActions('frage');
  // Pre-fill chat with task context
  const input = document.getElementById('kiraInput');
  if(input) {{
    const msg = 'Aufgabe: ' + (ctx.titel||'') + '\\nVon: ' + (ctx.name||ctx.email||'') +
      '\\nKategorie: ' + (ctx.kategorie||'') +
      '\\nZusammenfassung: ' + (ctx.zusammenfassung||'') +
      '\\n\\nWas schlägst du vor?';
    input.value = msg;
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    input.focus();
  }}
}}

function generateDraft(taskId){{
  const kaiInput = document.getElementById('kai-in-'+taskId)?.value||'';
  const resEl = document.getElementById('draft-'+taskId);
  if(resEl) resEl.innerHTML='<div style="color:var(--muted);font-size:12px;padding:6px 0;">Entwurf wird erstellt&hellip;</div>';
  fetch('/api/task/'+taskId+'/generate-draft',{{
    method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{kai_input:kaiInput}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.entwurf&&resEl){{
      resEl.innerHTML=`
        <div class="komm-block" style="margin-top:8px">
          <div class="komm-lbl">Entwurf${{d.hinweis?' &middot; '+escH(d.hinweis):''}}</div>
          <div class="komm-result" id="et-${{taskId}}">${{escH(d.entwurf)}}</div>
          <div class="komm-actions">
            <button class="btn-kp" onclick="copyEntwurf(${{taskId}})">Kopieren</button>
            <a href="https://claude.ai/new" target="_blank" class="btn-ks"
               onclick="copyClaudePrompt(${{taskId}})">In Claude öffnen</a>
          </div>
        </div>`;
    }} else if(resEl) {{
      resEl.innerHTML='<div style="color:#e84545;font-size:12px;padding:5px 0;">'+escH((d&&d.error)||'Fehler')+'</div>';
    }}
  }}).catch(()=>{{ if(resEl) resEl.innerHTML='<div style="color:#e84545;font-size:12px;">Serverfehler</div>'; }});
}}

function copyEntwurf(taskId){{
  const el=document.getElementById('et-'+taskId);
  if(el) navigator.clipboard.writeText(el.textContent)
    .then(()=>showToast('Kopiert!'),()=>showToast('Kopieren fehlgeschlagen'));
}}
function copyClaudePrompt(taskId){{
  const text = PROMPTS[taskId]||document.getElementById('et-'+taskId)?.textContent||'';
  navigator.clipboard.writeText(text).catch(()=>{{}});
}}

// Korrektur
function openKorrektur(taskId, alterKat){{
  document.getElementById('korr-tid').value=taskId;
  document.getElementById('korr-alt').value=alterKat;
  document.getElementById('korr-neu').value='';
  document.getElementById('korr-notiz').value='';
  document.getElementById('korrModal').classList.add('open');
}}
function closeKorrModal(){{ document.getElementById('korrModal').classList.remove('open'); }}
function saveAlias(){{
  const alias = document.getElementById('korr-alias-email').value.trim();
  const haupt = document.getElementById('korr-haupt-email').value.trim();
  if(!alias || !haupt) {{ showToast('Alias- und Haupt-E-Mail erforderlich'); return; }}
  fetch('/api/kunden/alias',{{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{alias_email: alias, haupt_email: haupt}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok) {{ showToast('Alias gespeichert: ' + alias + ' → ' + haupt); }}
    else {{ showToast('Fehler: ' + (d.error || 'Unbekannt')); }}
  }}).catch(()=>showToast('Netzwerkfehler'));
}}
function showLöschHistorie(){{
  fetch('/api/loeschhistorie').then(r=>r.json()).then(rows=>{{
    let html='<div style="max-height:70vh;overflow-y:auto">';
    if(!rows.length){{html+='<p style="color:var(--text-muted);padding:16px">Keine Einträge.</p>';}}
    rows.forEach(r=>{{
      const behalten = (r.grund||'').startsWith('BEHALTEN');
      const col = behalten ? '#6CB4F0' : '#EF9F27';
      const icon = behalten ? '🔵' : '🗑️';
      html+=`<div style="padding:10px 0;border-bottom:1px solid var(--border)">
        <div style="display:flex;gap:8px;align-items:flex-start">
          <span style="font-size:16px">${{icon}}</span>
          <div style="flex:1;min-width:0">
            <div style="font-weight:600;font-size:13px;color:var(--text)">${{r.betreff||'(kein Betreff)'}}</div>
            <div style="font-size:11px;color:var(--text-muted);margin:2px 0">
              Konto: ${{r.konto||'–'}} &middot; Absender: ${{r.absender||'–'}} &middot; ${{(r.datum_mail||'').slice(0,16)}}
            </div>
            <div style="font-size:11px;color:var(--text-muted)">Anhänge: ${{r.anhaenge_info||'–'}}</div>
            <div style="font-size:12px;color:${{col}};margin-top:4px">${{r.grund||'–'}}</div>
            ${{r.referenz_task_id ? `<div style="font-size:11px;color:var(--text-muted)">Referenz-Task: #${{r.referenz_task_id}} (${{r.referenz_konto}})</div>` : ''}}
          </div>
          <div style="font-size:11px;color:var(--text-muted);white-space:nowrap">${{(r.geloescht_am||'').slice(0,10)}}</div>
        </div>
      </div>`;
    }});
    html+='</div>';
    document.getElementById('lh-modal-body').innerHTML=html;
    document.getElementById('lh-modal').style.display='flex';
  }}).catch(()=>showToast('Fehler beim Laden der Lösch-History'));
}}
function closeLhModal(){{
  document.getElementById('lh-modal').style.display='none';
}}
function saveKorrektur(){{
  const tid  = document.getElementById('korr-tid').value;
  const alt  = document.getElementById('korr-alt').value;
  const neu  = document.getElementById('korr-neu').value;
  const notiz= document.getElementById('korr-notiz').value;
  if(!neu&&!notiz){{ showToast('Bitte Kategorie oder Notiz angeben'); return; }}
  fetch('/api/task/'+tid+'/korrektur',{{
    method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{alter_typ:alt,neuer_typ:neu,notiz}})
  }}).then(r=>r.json()).then(d=>{{
    closeKorrModal();
    showKiraToast(d.kira_antwort || 'Korrektur gespeichert.');
    setTimeout(()=>location.reload(),1800);
  }}).catch(()=>showToast('Fehler'));
}}

// Kira Aufgabenliste
function loadKiraTasks(){{
  fetch('/api/tasks/open').then(r=>r.json()).then(data=>{{
    const el=document.getElementById('kira-tasks-list');
    if(!data.length){{el.innerHTML="<p class='empty'>Keine offenen Aufgaben.</p>";return;}}
    el.innerHTML=data.map(t=>`
      <div class="kira-card clickable" onclick="openKira(${{t.id}})">
        <div class="kira-card-title">${{escH(t.titel)}}</div>
        <div class="kira-card-meta">${{escH(t.kategorie)}} &middot; ${{escH(t.kunden_email||'')}}</div>
      </div>`).join('');
  }}).catch(()=>{{}});
}}

function escH(s){{return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}}
function showToast(msg, typ){{
  const t=document.getElementById('toast');
  const msgEl=document.getElementById('toast-msg');
  if(t._toastTimer)clearTimeout(t._toastTimer);
  if(msgEl)msgEl.textContent=msg; else t.firstChild&&(t.firstChild.textContent=msg);
  t.className='status-toast';
  if(typ)t.classList.add(typ);
  t.classList.add('show');
  const defaults={{ok:4,fehler:10,warnung:7,info:5}};
  const sek=parseInt(localStorage.getItem('kira_toast_dauer_'+(typ||'ok'))||defaults[typ||'ok']||4);
  t._toastTimer=setTimeout(()=>{{t.classList.remove('show');t.className='status-toast';}},sek*1000);
}}
function showKiraToast(msg){{showToast('Kira: '+msg,'info');}}
// Später-Dialog
function openSpaeterDialog(tid){{
  document.getElementById('sp-tid').value=tid;
  document.getElementById('sp-wann').value='';
  document.getElementById('sp-kira-resp').style.display='none';
  document.getElementById('sp-kira-resp').textContent='';
  document.getElementById('sp-save-btn').textContent='Kira fragen';
  document.getElementById('sp-save-btn').disabled=false;
  document.getElementById('spaeterModal').classList.add('open');
  setTimeout(()=>document.getElementById('sp-wann').focus(),80);
}}
function closeSpaeterDialog(){{ document.getElementById('spaeterModal').classList.remove('open'); }}
async function saveSpaeter(){{
  const tid  = document.getElementById('sp-tid').value;
  const wann = document.getElementById('sp-wann').value.trim();
  if(!wann){{ document.getElementById('sp-wann').focus(); return; }}
  const btn = document.getElementById('sp-save-btn');
  btn.textContent='Kira denkt …';
  btn.disabled=true;
  try{{
    const r = await fetch('/api/task/'+tid+'/spaeter',{{
      method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{wann}})
    }});
    const d = await r.json();
    if(d.ok){{
      const respEl = document.getElementById('sp-kira-resp');
      respEl.textContent = d.kira_antwort || 'Termin gespeichert.';
      respEl.style.display='block';
      btn.textContent='OK';
      btn.onclick=()=>{{closeSpaeterDialog();location.reload();}};
      btn.disabled=false;
    }} else {{
      showToast('Fehler: '+(d.error||'Unbekannt'));
      btn.textContent='Kira fragen';btn.disabled=false;
    }}
  }}catch(e){{
    showToast('Netzwerkfehler');
    btn.textContent='Kira fragen';btn.disabled=false;
  }}
}}
document.addEventListener('keydown',e=>{{
  if(e.key==='Escape'){{
    if(document.getElementById('kiraInteraktModal').classList.contains('open')) closeKiraInterakt();
    else if(document.getElementById('mailReadModal').classList.contains('open')) closeMailRead();
    else if(document.getElementById('geschBewertModal').classList.contains('open')) closeGeschBewertung();
    else if(document.getElementById('editRegelModal').classList.contains('open')) closeEditRegel();
    else if(document.getElementById('korrModal').classList.contains('open')) closeKorrModal();
    else if(document.getElementById('loeschModal').classList.contains('open')) closeLoeschModal();
    else if(document.getElementById('spaeterModal').classList.contains('open')) closeSpaeterDialog();
    else if(document.getElementById('kiraWorkspace').classList.contains('open')) closeKiraWorkspace();
    else if(document.getElementById('kiraQuick').classList.contains('open')) closeKiraQuick();
  }}
}});
// Restore active tab + design on load
(function(){{
  restoreDesign();
  const tab = localStorage.getItem('kira_active_tab');
  if(tab && tab !== 'dashboard') showPanel(tab);
  const gt = localStorage.getItem('kira_gesch_tab');
  if(gt && gt !== 'uebersicht') showGeschTab(gt);
}})();
// Kira proaktiv: Insights laden + ggf. Panel öffnen
setTimeout(()=>kiraProaktivCheck(), 1500);
// Silent auto-refresh alle 5 Minuten: nur Dashboard-Daten nachladen, kein location.reload()
function silentRefreshDashboard() {{
  if(kiraSending) return; // nie unterbrechen wenn Chat aktiv
  const active = document.querySelector('.panel.active');
  if(!active || active.id !== 'panel-dashboard') return; // nur wenn Dashboard sichtbar
  fetch('/api/tasks/open').then(r=>r.json()).then(data=>{{
    const badge = document.getElementById('headerBadgeCount');
    if(badge && data.tasks) badge.textContent = data.tasks.length;
  }}).catch(()=>{{}});
}}
setInterval(silentRefreshDashboard, 300000);

// ── JS-Diagnose ──────────────────────────────────────────────────────────
window.onerror = function(msg, src, line, col, err) {{
  let bar = document.getElementById('js-error-bar');
  if(!bar) {{
    bar = document.createElement('div');
    bar.id = 'js-error-bar';
    bar.style = 'position:fixed;top:0;left:0;right:0;z-index:99999;background:#dc4a4a;color:#fff;font-size:13px;padding:8px 16px;font-family:monospace';
    document.body.appendChild(bar);
  }}
  bar.textContent = 'JS-FEHLER: ' + msg + ' (Zeile ' + line + ')';
}};
// JS-Diagnose: Balken ausblenden wenn JS läuft
(function() {{
  const d = document.getElementById('_diag');
  if(d) d.remove();
  const btn = document.getElementById('updateBtn');
  if(btn) btn.title = 'JS OK \u2013 Server neu starten';
  document.title = document.title.replace(' \u2013 ', ' \u2713 \u2013 ');
}})();

/* ── Vorgang-Signal-Polling (Paket 8, session-nn) ── */
(function() {{
  'use strict';

  // Inject CSS für Toast + Modal
  const _css = document.createElement('style');
  _css.textContent = [
    '#_vg-toast-container{{position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none}}',
    '.vg-toast{{background:var(--card-bg,#1e1e1e);color:var(--text,#e0e0e0);border:1px solid var(--border,#333);border-left:4px solid #f59e0b;border-radius:8px;padding:14px 16px;min-width:280px;max-width:380px;box-shadow:0 4px 20px rgba(0,0,0,.5);pointer-events:all;cursor:pointer}}',
    '.vg-toast.stufe-c{{border-left-color:#ef4444}}',
    '.vg-toast-title{{font-size:12px;font-weight:600;opacity:.65;margin-bottom:4px;text-transform:uppercase;letter-spacing:.04em}}',
    '.vg-toast-body{{font-size:13px;line-height:1.4}}',
    '.vg-toast-close{{float:right;opacity:.4;cursor:pointer;font-size:16px;line-height:1;margin:-2px -4px 0 8px}}',
    '.vg-toast-close:hover{{opacity:.9}}',
    '#_vg-modal-overlay{{position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:10000;display:flex;align-items:center;justify-content:center}}',
    '#_vg-modal{{background:var(--card-bg,#1e1e1e);color:var(--text,#e0e0e0);border:1px solid var(--border,#444);border-top:4px solid #ef4444;border-radius:12px;padding:28px 32px;max-width:480px;width:90%;box-shadow:0 8px 40px rgba(0,0,0,.7)}}',
    '#_vg-modal h3{{margin:0 0 8px;font-size:17px}}',
    '#_vg-modal p{{margin:0 0 20px;font-size:14px;opacity:.8;line-height:1.5;white-space:pre-wrap}}',
    '#_vg-modal .modal-btns{{display:flex;gap:10px;justify-content:flex-end}}',
    '#_vg-modal button{{padding:8px 20px;border-radius:6px;border:none;cursor:pointer;font-size:13px;font-weight:600}}',
    '#_vg-modal .btn-ok{{background:#ef4444;color:#fff}}',
    '#_vg-modal .btn-snooze{{background:var(--btn-bg,#2a2a2a);color:var(--text,#e0e0e0);border:1px solid var(--border,#444)}}'
  ].join('\\n');
  document.head.appendChild(_css);

  const _tc = document.createElement('div');
  _tc.id = '_vg-toast-container';
  document.body.appendChild(_tc);

  var _shownSignals = {{}};
  var _modalOpen = false;

  function _markGelesen(sid, aktion) {{
    fetch('/api/vorgang/signal/gelesen', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{signal_id:sid,aktion:aktion}})}}).catch(function(){{}});
  }}

  function _showToast(sig) {{
    var t = document.createElement('div');
    t.className = 'vg-toast' + (sig.stufe === 'C' ? ' stufe-c' : '');
    t.innerHTML = '<span class="vg-toast-close">&#10005;</span><div class="vg-toast-title">Vorgang ' +
      (sig.stufe === 'C' ? '&#9888; Aktion' : '&#9432; Hinweis') + '</div><div class="vg-toast-body">' +
      sig.titel + '</div>';
    _tc.appendChild(t);
    t.querySelector('.vg-toast-close').onclick = function(e) {{ e.stopPropagation(); _markGelesen(sig.id,'geschlossen'); t.remove(); }};
    t.onclick = function() {{ _markGelesen(sig.id,'geklickt'); t.remove(); }};
    setTimeout(function() {{ if(t.parentNode) {{ _markGelesen(sig.id,'auto_timeout'); t.remove(); }} }}, 12000);
  }}

  function _showModal(sig) {{
    if(_modalOpen) return;
    _modalOpen = true;
    var ov = document.createElement('div');
    ov.id = '_vg-modal-overlay';
    ov.innerHTML = '<div id="_vg-modal"><h3>&#9888; ' + sig.titel + '</h3><p>' +
      (sig.nachricht||'') + '</p><div class="modal-btns">' +
      '<button class="btn-snooze" id="_vgSnooze">Sp\u00e4ter</button>' +
      '<button class="btn-ok" id="_vgOk">Verstanden</button></div></div>';
    document.body.appendChild(ov);
    ov.querySelector('#_vgOk').onclick = function() {{ _markGelesen(sig.id,'bestaetigt'); ov.remove(); _modalOpen=false; }};
    ov.querySelector('#_vgSnooze').onclick = function() {{ _markGelesen(sig.id,'snoozed'); ov.remove(); _modalOpen=false; }};
  }}

  function _pollSignals() {{
    fetch('/api/vorgang/signals?limit=5').then(function(r) {{
      return r.ok ? r.json() : null;
    }}).then(function(d) {{
      if(!d) return;
      (d.signals||[]).forEach(function(sig) {{
        if(_shownSignals[sig.id]) return;
        _shownSignals[sig.id] = true;
        if(sig.stufe === 'C') _showModal(sig); else _showToast(sig);
      }});
    }}).catch(function(){{}});
  }}

  setTimeout(function() {{ _pollSignals(); setInterval(_pollSignals, 10000); }}, 5000);
}})();

// ── Kira-Feedback (Paket 6, session-oo) ──────────────────────────────────────
function kirafb(rating, msgIdx, btn, kiraText) {{
  var payload = {{
    session_id: kiraSessionId || '',
    message_idx: msgIdx,
    rating: rating,
    kira_antwort: kiraText || ''
  }};
  fetch('/api/kira/feedback', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(payload)
  }}).then(function(r){{return r.json();}}).then(function(d){{
    if(d.ok) {{
      if(btn && btn.parentNode) {{
        btn.parentNode.querySelectorAll('button').forEach(function(b){{ b.style.opacity='0.4'; b.disabled=true; }});
        btn.style.opacity='1';
        btn.style.borderColor = rating==='gut' ? '#059669' : '#dc2626';
      }}
      if(d.auto_regel_id) {{
        showToast('Kira lernt: Wissens-Regel #' + d.auto_regel_id + ' erstellt', 'ok');
      }}
    }}
  }}).catch(function(){{}});
}}

// ── Mail-Freigabe (Paket 2, session-oo) ──────────────────────────────────────
var _mailApproveItems = [];

function _pollMailApprove() {{
  fetch('/api/mail/approve/pending').then(function(r){{return r.json();}}).then(function(d){{
    _mailApproveItems = d.pending || [];
    var n = d.count || 0;
    var chip = document.getElementById('mailApproveChip');
    var cnt  = document.getElementById('mailApproveCount');
    if(chip) chip.style.display = n > 0 ? '' : 'none';
    if(cnt)  cnt.textContent = n;
  }}).catch(function(){{}});
}}

setTimeout(function(){{ _pollMailApprove(); setInterval(_pollMailApprove, 15000); }}, 3000);

function openMailApproveModal() {{
  if(!_mailApproveItems.length) return;
  var item = _mailApproveItems[0];
  var overlay = document.getElementById('mailApproveOverlay');
  if(!overlay) {{
    overlay = document.createElement('div');
    overlay.id = 'mailApproveOverlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:9999;display:flex;align-items:center;justify-content:center;';
    document.body.appendChild(overlay);
  }}
  overlay.innerHTML = '<div style="background:#1a1a1a;border:1px solid #333;border-radius:14px;padding:28px;max-width:560px;width:100%;color:#e0e0e0;font-family:Segoe UI,sans-serif;">' +
    '<div style="font-size:13px;color:#f59e0b;font-weight:700;margin-bottom:8px">&#x2709; Mail wartet auf Freigabe</div>' +
    '<div style="font-size:16px;font-weight:700;margin-bottom:4px">An: <span style="color:#93c5fd">' + _esc(item.an) + '</span></div>' +
    '<div style="font-size:14px;color:#aaa;margin-bottom:12px">Betreff: ' + _esc(item.betreff) + '</div>' +
    '<textarea id="mailApproveBody" style="width:100%;min-height:120px;background:#111;color:#e0e0e0;border:1px solid #333;border-radius:8px;padding:10px;font-family:inherit;font-size:13px;box-sizing:border-box;resize:vertical">' + _esc(item.body_plain || '') + '</textarea>' +
    '<div style="margin-top:8px;font-size:11px;color:#666">Queue-ID #' + item.id + ' — erstellt ' + (item.erstellt_am||'').slice(0,16) + '</div>' +
    '<div style="display:flex;gap:10px;margin-top:18px;justify-content:flex-end">' +
    '<button onclick="closeMailApproveOverlay()" style="background:#2a2a2a;color:#ccc;border:1px solid #444;border-radius:8px;padding:8px 18px;cursor:pointer;font-size:13px">Abbrechen</button>' +
    '<button onclick="mailApproveAction(' + item.id + ',\'reject\')" style="background:#7f1d1d;color:#fca5a5;border:1px solid #b91c1c;border-radius:8px;padding:8px 18px;cursor:pointer;font-size:13px">Ablehnen</button>' +
    '<button onclick="mailApproveAction(' + item.id + ',\'edit\')" style="background:#1e3a5f;color:#93c5fd;border:1px solid #2563eb;border-radius:8px;padding:8px 18px;cursor:pointer;font-size:13px">Senden (bearbeitet)</button>' +
    '<button onclick="mailApproveAction(' + item.id + ',\'approve\')" style="background:#065f46;color:#6ee7b7;border:1px solid #059669;border-radius:8px;padding:8px 18px;cursor:pointer;font-size:13px;font-weight:700">Senden</button>' +
    '</div>' +
    '</div>';
  overlay.style.display = 'flex';
}}

function closeMailApproveOverlay() {{
  var o = document.getElementById('mailApproveOverlay');
  if(o) o.style.display = 'none';
}}

function mailApproveAction(id, action) {{
  var body = document.getElementById('mailApproveBody');
  var payload = {{action: action}};
  if(action === 'edit' && body) payload.body = body.value;
  fetch('/api/mail/approve/' + id, {{
    method: 'POST',
    headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify(payload)
  }}).then(function(r){{return r.json();}}).then(function(d){{
    closeMailApproveOverlay();
    if(d.ok) {{
      showToast(d.message || 'Mail gesendet', 'ok');
      _pollMailApprove();
    }} else {{
      showToast('Fehler: ' + (d.error||'?'), 'fehler');
    }}
  }}).catch(function(e){{ showToast('Netzwerkfehler', 'fehler'); }});
}}

function _esc(s) {{
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}
</script>
</body>
</html>"""


# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
/* ═══ DESIGN SYSTEM ═══ Neutral, CSS-Variable-driven, Light/Dark ready ═══ */
:root{
  /* Accent — overridden by user settings */
  --accent:#4f7df9;--accent-l:#6b94ff;--accent-bg:rgba(79,125,249,.08);--accent-border:rgba(79,125,249,.25);
  /* Kira accent */
  --kl:var(--accent-l);--kp:var(--accent);
  /* Semantic */
  --danger:#dc4a4a;--success:#3dae6a;--warn:#d4933e;--info:#4f7df9;
  /* Surfaces — Dark mode default */
  --bg:#0e0e10;--bg-raised:#161618;--bg-overlay:#1c1c1f;--card:#161618;
  --border:rgba(255,255,255,.08);--border-strong:rgba(255,255,255,.14);
  /* Text */
  --text:#e4e4e7;--text-secondary:rgba(255,255,255,.58);--muted:rgba(255,255,255,.42);
  /* Sizing */
  --fs-xs:12px;--fs-sm:13px;--fs-base:15px;--fs-md:16px;--fs-lg:18px;--fs-xl:24px;--fs-xxl:30px;
  --radius:8px;--radius-lg:12px;
  /* Configurable design tokens */
  --card-radius:var(--radius-lg);--shadow-strength:0.12;--transition-speed:0.2s;
  /* Sidebar */
  --sidebar-w:220px;--sidebar-collapsed-w:56px;
  /* Compat aliases */
  --gold:var(--accent);--gl:var(--accent-l);
}
/* Light mode */
[data-theme="light"]{
  --bg:#f5f5f7;--bg-raised:#fff;--bg-overlay:#f0f0f3;--card:#fff;
  --border:rgba(0,0,0,.08);--border-strong:rgba(0,0,0,.14);
  --text:#1a1a1e;--text-secondary:rgba(0,0,0,.58);--muted:rgba(0,0,0,.42);
  --accent-bg:rgba(79,125,249,.06);--accent-border:rgba(79,125,249,.2);
}
/* Density */
[data-density="compact"]{--fs-base:12px;--fs-md:13px;}
[data-density="comfortable"]{--fs-base:14px;--fs-md:15px;}
/* Reduced motion */
[data-reduce-motion="true"] *{animation:none!important;transition-duration:0s!important;}
/* High contrast */
[data-high-contrast="true"]{--text:#fff;--text-secondary:rgba(255,255,255,.75);--muted:rgba(255,255,255,.6);
  --border:rgba(255,255,255,.18);--border-strong:rgba(255,255,255,.28);}
[data-theme="light"][data-high-contrast="true"]{--text:#000;--text-secondary:rgba(0,0,0,.75);--muted:rgba(0,0,0,.6);
  --border:rgba(0,0,0,.18);--border-strong:rgba(0,0,0,.28);}
/* Shadow modes */
[data-shadow="none"] .task-card,[data-shadow="none"] .kpi-card,[data-shadow="none"] .dash-kpi,
[data-shadow="none"] .modal,[data-shadow="none"] .kira-workspace,[data-shadow="none"] .kira-quick{box-shadow:none!important;}
[data-shadow="strong"] .task-card,[data-shadow="strong"] .kpi-card,[data-shadow="strong"] .dash-kpi{box-shadow:0 2px 12px rgba(0,0,0,.15);}
/* Font size override — overrides CSS variables so all var(--fs-*) respond */
[data-fontsize="small"]{--fs-xs:10px;--fs-sm:11px;--fs-base:12px;--fs-md:13px;--fs-lg:15px;--fs-xl:20px;--fs-xxl:26px;}
[data-fontsize="large"]{--fs-xs:13px;--fs-sm:14px;--fs-base:16px;--fs-md:17px;--fs-lg:20px;--fs-xl:28px;--fs-xxl:34px;}
/* Font family */
[data-font-family="mono"] body{font-family:'Fira Mono','Cascadia Code','Courier New',monospace!important;}
[data-font-family="system"] body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif!important;}
/* Row height */
[data-row-height="compact"] .proto-table td,[data-row-height="compact"] .proto-table th{padding:4px 10px!important;}
[data-row-height="comfortable"] .proto-table td,[data-row-height="comfortable"] .proto-table th{padding:14px 10px!important;}
/* Toast position */
[data-toast-pos="top-right"] .status-toast{bottom:auto!important;top:24px;}
[data-toast-pos="bottom-left"] .status-toast{right:auto!important;left:24px;bottom:82px;}
[data-toast-pos="bottom-center"] .status-toast{right:50%!important;transform:translateX(50%) translateY(8px);bottom:82px;}
[data-toast-pos="bottom-center"] .status-toast.show{transform:translateX(50%) translateY(0);}
[data-toast-pos="top-center"] .status-toast{right:50%!important;bottom:auto!important;top:24px;transform:translateX(50%) translateY(-8px);}
[data-toast-pos="top-center"] .status-toast.show{transform:translateX(50%) translateY(0);}
[data-toast-pos="top-left"] .status-toast{right:auto!important;left:24px!important;bottom:auto!important;top:24px;}
/* Table zebra */
[data-table-zebra="true"] .proto-table tbody tr:nth-child(even) td{background:var(--bg-overlay);}
[data-table-lines="true"] .proto-table tbody tr td{border-bottom:0.5px solid var(--border);}
/* Global form element theming — prevents hardcoded black backgrounds in light mode */
input:not([type="color"]):not([type="checkbox"]):not([type="radio"]),select,textarea{
  background:var(--bg-raised);color:var(--text);}

*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'Inter',-apple-system,'Segoe UI',Roboto,sans-serif;
  font-size:var(--fs-md);line-height:1.55;overflow-x:hidden;display:flex;min-height:100vh;}
a{color:var(--accent);text-decoration:none;}
a:hover{text-decoration:underline;}

/* ═══ APP SHELL — Sidebar + Main ═══ */
.app-shell{display:flex;flex:1;min-height:100vh;}

/* Sidebar — warm light grey, matches light UI theme */
.sidebar{width:var(--sidebar-w);background:#EDECE8;border-right:0.5px solid rgba(0,0,0,.1);
  display:flex;flex-direction:column;position:fixed;top:0;left:0;height:100vh;z-index:90;
  transition:width .22s cubic-bezier(.4,0,.2,1);overflow:hidden;flex-shrink:0;position:fixed;}
.sidebar.collapsed{width:var(--sidebar-collapsed-w);overflow:visible;}
.sidebar.resizing{transition:none!important;}

/* Brand / Header area */
.sidebar-brand{padding:14px 14px 12px;display:flex;align-items:center;gap:10px;border-bottom:0.5px solid rgba(0,0,0,.08);min-height:56px;}
.sidebar-logo{width:30px;height:30px;border-radius:7px;background:var(--accent);color:#fff;display:flex;
  align-items:center;justify-content:center;font-weight:900;font-size:15px;flex-shrink:0;}
.sidebar-logo img{width:30px;height:30px;border-radius:7px;object-fit:cover;}
.sidebar-brand-text{display:flex;flex-direction:column;overflow:hidden;white-space:nowrap;flex:1;}
.sidebar-brand-name{font-size:var(--fs-md);font-weight:700;color:#1C1C1A;line-height:1.2;}
.sidebar-brand-sub{font-size:11px;color:#888780;line-height:1.3;}
.sidebar.collapsed .sidebar-brand-text{display:none;}

/* Toggle button — top right of brand area */
.sb-toggle-btn{width:26px;height:26px;border-radius:6px;background:transparent;border:none;
  cursor:pointer;color:#888780;font-size:13px;font-weight:600;display:flex;align-items:center;
  justify-content:center;flex-shrink:0;transition:background .12s,color .12s;margin-left:auto;}
.sb-toggle-btn:hover{background:rgba(0,0,0,.07);color:#1C1C1A;}
.sidebar.collapsed .sidebar-brand{padding:0;border-bottom:0.5px solid rgba(0,0,0,.08);}
.sidebar.collapsed .sidebar-logo{display:none;}
.sidebar.collapsed .sb-toggle-btn{margin:0;width:56px;height:56px;border-radius:0;}
.sidebar.collapsed .sb-toggle-btn svg{transform:scaleX(-1);}
/* Collapsed: größere Icons, zentriert, Hover-Tooltips */
.sidebar.collapsed .sidebar-nav,.sidebar.collapsed .sidebar-bottom{overflow:visible;}
.sidebar.collapsed .sidebar-item{justify-content:center;padding:11px 0;}
.sidebar.collapsed .si-icon{font-size:22px;width:auto;}
.sidebar.collapsed .sidebar-item::after{content:attr(data-label);position:absolute;left:calc(100% + 8px);top:50%;transform:translateY(-50%);background:#1C1C1A;color:#fff;font-size:12px;font-weight:600;padding:5px 11px;border-radius:7px;white-space:nowrap;opacity:0;pointer-events:none;transition:opacity .12s;z-index:200;box-shadow:0 2px 8px rgba(0,0,0,.18);}
.sidebar.collapsed .sidebar-item:hover::after{opacity:1;}

/* Drag-resize handle — right edge of sidebar */
.sb-resize-handle{position:absolute;top:0;right:0;width:5px;height:100%;cursor:col-resize;z-index:10;
  transition:background .15s;}
.sb-resize-handle:hover,.sb-resize-handle.dragging{background:rgba(79,125,249,.35);}

/* Nav items */
.sidebar-nav{flex:1;overflow-y:auto;padding:10px 8px;}
.sidebar-group{margin-bottom:4px;}
.sidebar-group-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:#AAA9A5;
  padding:10px 10px 5px;user-select:none;}
.sidebar.collapsed .sidebar-group-label{display:none;}
.sidebar-item{display:flex;align-items:center;gap:11px;padding:9px 10px;border-radius:var(--radius);
  cursor:pointer;color:#3C3C3A;font-size:13px;font-weight:600;
  transition:all .12s;user-select:none;position:relative;white-space:nowrap;margin-bottom:2px;}
.sidebar-item:hover{background:rgba(0,0,0,.06);color:#1C1C1A;}
.sidebar-item.active{background:#fff;color:var(--accent);box-shadow:0 1px 5px rgba(0,0,0,.1);border:none;}
.sidebar-item .si-icon{width:22px;text-align:center;font-size:18px;flex-shrink:0;line-height:1;}
.sidebar-item.active .si-icon{opacity:1;}
.sidebar-item .si-label{overflow:hidden;text-overflow:ellipsis;}
.sidebar.collapsed .si-label{display:none;}
.sidebar-item .si-badge{font-size:9px;font-weight:700;padding:2px 7px;border-radius:10px;margin-left:auto;
  background:rgba(220,74,74,.12);color:#C0392B;border:none;}
.sidebar-item .si-badge.planned{background:rgba(0,0,0,.07);color:#888780;border:none;font-weight:500;}
.sidebar.collapsed .si-badge{display:none;}
.sidebar-item.planned{opacity:.5;}
.sidebar-item.planned:hover{opacity:.8;}

.sidebar-bottom{border-top:0.5px solid rgba(0,0,0,.08);padding:8px;}
.sidebar-toggle{display:none!important;} /* legacy, jetzt sb-toggle-btn */
/* Sidebar dark mode overrides */
[data-theme="dark"] .sidebar{background:#101012;border-right-color:rgba(255,255,255,.06);}
[data-theme="dark"] .sidebar-brand{border-bottom-color:rgba(255,255,255,.06);}
[data-theme="dark"] .sidebar-brand-name{color:var(--text);}
[data-theme="dark"] .sidebar-brand-sub{color:var(--text-secondary);}
[data-theme="dark"] .sidebar-group-label{color:var(--muted);}
[data-theme="dark"] .sidebar-item{color:var(--text-secondary);}
[data-theme="dark"] .sidebar-item:hover{background:rgba(255,255,255,.06);color:var(--text);}
[data-theme="dark"] .sidebar-item.active{background:var(--bg-overlay);color:var(--accent);box-shadow:none;}
[data-theme="dark"] .sb-toggle-btn{color:var(--muted);}
[data-theme="dark"] .sb-toggle-btn:hover{background:rgba(255,255,255,.06);color:var(--text);}
[data-theme="dark"] .sidebar-bottom{border-top-color:rgba(255,255,255,.06);}
[data-theme="dark"] .sidebar.collapsed .sidebar-item::after{background:var(--bg-overlay);color:var(--text);}

/* Main content */
.main-area{flex:1;margin-left:var(--sidebar-w);transition:margin-left .22s cubic-bezier(.4,0,.2,1);
  display:flex;flex-direction:column;min-height:100vh;}
.sidebar.collapsed ~ .main-area,.app-shell.sb-collapsed .main-area{margin-left:var(--sidebar-collapsed-w);}

/* Header / Topbar */
.header{background:var(--bg-raised);border-bottom:0.5px solid var(--border);
  padding:0 24px;display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:80;min-height:52px;gap:16px;}
.header-left{display:flex;align-items:center;gap:12px;flex:1;}
.header-search{background:var(--bg);border:0.5px solid var(--border-strong);border-radius:8px;
  padding:7px 14px;font-size:13px;color:var(--text-secondary);width:280px;max-width:100%;
  font-family:inherit;outline:none;transition:border-color .15s;}
.header-search:focus{border-color:var(--accent);color:var(--text);}
.header-search::placeholder{color:var(--muted);}
.header-right{display:flex;align-items:center;gap:8px;flex-shrink:0;}
.top-chip{background:var(--bg);border:0.5px solid var(--border-strong);border-radius:6px;
  padding:5px 12px;font-size:12px;color:var(--text-secondary);display:flex;align-items:center;gap:5px;
  cursor:pointer;user-select:none;white-space:nowrap;transition:background .12s;}
.top-chip:hover{background:var(--accent-bg);border-color:var(--accent-border);}
.top-chip.ok{background:#EAF3DE;border-color:#C0DD97;color:#3B6D11;}
.top-chip.ok:hover{background:#ddeec8;}
.chip-dot{width:7px;height:7px;background:#639922;border-radius:50%;flex-shrink:0;}
.header-avatar{width:32px;height:32px;border-radius:50%;background:var(--accent-bg);
  display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;
  color:var(--accent);cursor:pointer;flex-shrink:0;border:0.5px solid var(--accent-border);}
/* legacy compat */
.header-title{font-size:var(--fs-lg);font-weight:800;color:var(--text);}
.header-meta{color:var(--muted);font-size:var(--fs-sm);display:flex;align-items:center;gap:12px;}
.header-meta strong{color:var(--text);font-size:var(--fs-base);}

/* Panels */
.panel{display:none;padding:20px 24px 80px;max-width:1200px;margin:0 auto;width:100%;}
.panel.active{display:block;}
.panel.pf-panel{padding:0;max-width:none;overflow:hidden}
/* Dashboard: full-width, no max-width constraint */
#panel-dashboard{max-width:none;padding:20px 24px 80px;}

/* Planned module shell */
.planned-shell{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:340px;text-align:center;padding:60px 30px;}
.planned-shell-icon{font-size:48px;margin-bottom:16px;opacity:.3;}
.planned-shell-title{font-size:var(--fs-xl);font-weight:800;color:var(--text);margin-bottom:8px;}
.planned-shell-desc{font-size:var(--fs-base);color:var(--muted);max-width:420px;line-height:1.7;margin-bottom:16px;}
.planned-badge{display:inline-flex;align-items:center;gap:5px;font-size:var(--fs-sm);font-weight:700;
  padding:5px 14px;border-radius:20px;background:var(--accent-bg);color:var(--accent);border:1px solid var(--accent-border);}
.planned-features{margin-top:24px;text-align:left;max-width:420px;display:flex;flex-direction:column;gap:6px;}
.planned-feature-item{font-size:var(--fs-base);color:var(--text-secondary);padding:8px 14px;
  background:var(--bg-raised);border:1px solid var(--border);border-radius:var(--radius);line-height:1.5;}

/* ═══ DASHBOARD — 4 Zones (reference redesign) ═══ */

/* Zone A: Tagesbriefing */
.dash-briefing{background:var(--bg-raised);border:0.5px solid var(--border);border-radius:12px;
  padding:14px 20px;margin-bottom:18px;display:flex;flex-direction:column;gap:10px;
  box-shadow:0 1px 4px rgba(0,0,0,.04);}
.dash-briefing-head{display:flex;align-items:center;justify-content:space-between;gap:12px;}
.dash-briefing-title{font-size:14px;font-weight:600;color:var(--text);}
.dash-briefing-items{display:flex;align-items:center;gap:16px;flex-wrap:wrap;}
.dash-b-item{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-secondary);}
.dash-b-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;}
.dash-briefing-refresh{background:var(--bg);border:0.5px solid var(--border-strong);
  border-radius:6px;padding:4px 10px;font-size:11px;color:var(--text-secondary);cursor:pointer;
  flex-shrink:0;transition:background .12s;white-space:nowrap;}
.dash-briefing-refresh:hover{background:var(--accent-bg);color:var(--accent);}
/* LLM-Zusammenfassung Block */
.dash-briefing-summary{border-top:0.5px solid var(--border);padding-top:10px;display:flex;flex-direction:column;gap:8px;}
.dash-bs-text{font-size:13px;color:var(--text);line-height:1.55;}
.dash-bs-prios{display:flex;flex-direction:column;gap:4px;}
.dash-bs-prio{display:flex;align-items:flex-start;gap:7px;font-size:12px;color:var(--text-secondary);}
.dash-bs-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0;margin-top:4px;}
/* Protokoll Panel */
.proto-stats-bar{display:flex;gap:16px;padding:8px 0 14px;font-size:12px;color:var(--text-secondary);}
.proto-stats-bar b{color:var(--text);}
.proto-stats-bar .ps-fehler{color:var(--danger);}
.proto-filter{background:var(--bg);border:0.5px solid var(--border-strong);border-radius:6px;
  padding:4px 8px;font-size:12px;color:var(--text);cursor:pointer;}
.proto-table-wrap{overflow-x:auto;border:0.5px solid var(--border);border-radius:10px;}
.proto-table{width:100%;border-collapse:collapse;font-size:12px;}
.proto-table th{background:var(--bg-raised);padding:8px 12px;text-align:left;font-weight:600;
  color:var(--text-secondary);border-bottom:0.5px solid var(--border);white-space:nowrap;}
.proto-table td{padding:7px 12px;border-bottom:0.5px solid var(--border);vertical-align:top;color:var(--text);}
.proto-table tr:last-child td{border-bottom:none;}
.proto-table tr:hover td{background:var(--bg-raised);}
.proto-st{display:inline-flex;align-items:center;justify-content:center;border-radius:4px;
  padding:2px 7px;font-size:10px;font-weight:600;white-space:nowrap;}
.proto-st.ok{background:rgba(29,158,117,.1);color:#1d9e75;}
.proto-st.fehler{background:rgba(220,74,74,.1);color:#d04444;}
.proto-st.warnung{background:rgba(239,159,39,.1);color:#b87c10;}
.proto-bereich{display:inline-block;background:var(--accent-bg);color:var(--accent);
  border-radius:4px;padding:1px 6px;font-size:10px;font-weight:600;}

/* Zone B: KPI Grid */
.dash-kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:22px;}
@media(max-width:1100px){.dash-kpi-grid{grid-template-columns:repeat(4,minmax(0,1fr));}}
@media(max-width:860px){.dash-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}
@media(max-width:480px){.dash-kpi-grid{grid-template-columns:1fr 1fr;}}
.dash-kpi{background:var(--bg-raised);border:0.5px solid var(--border);border-radius:12px;
  padding:18px 20px;cursor:pointer;
  transition:border-color .18s,box-shadow .18s,transform .15s;position:relative;
  box-shadow:0 1px 4px rgba(0,0,0,.05);}
.dash-kpi:hover{border-color:var(--accent);
  box-shadow:0 6px 22px rgba(0,0,0,.1),0 1px 4px rgba(0,0,0,.05);transform:translateY(-2px);}
.dash-kpi:active{transform:translateY(0);}
.dash-kpi-label{font-size:10px;font-weight:700;color:var(--text-secondary);margin-bottom:10px;
  letter-spacing:.6px;text-transform:uppercase;}
.dash-kpi-row{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;}
.dash-kpi-val{font-size:30px;font-weight:700;color:var(--text);line-height:1;letter-spacing:-.5px;}
.dash-kpi-change{font-size:11px;font-weight:600;padding:2px 8px;border-radius:5px;white-space:nowrap;}
.dash-kpi-change.up{background:#EAF3DE;color:#3B6D11;}
.dash-kpi-change.warn{background:#FAEEDA;color:#854F0B;}
.dash-kpi-change.danger{background:#FCEBEB;color:#A32D2D;}
.dash-kpi-change.info{background:#E8F0FE;color:#1a5ca8;}
.dash-kpi-spark{margin-top:14px;height:34px;overflow:hidden;}
.dash-kpi-spark svg{width:100%;height:34px;}
/* KPI state variants */
.dash-kpi.kpi-danger{border-color:rgba(226,75,74,.35);background:rgba(226,75,74,.02);}
.dash-kpi.kpi-danger .dash-kpi-val{color:#D63B3A;}
.dash-kpi.kpi-warn{border-color:rgba(239,159,39,.35);}
.dash-kpi.kpi-warn .dash-kpi-val{color:#C17C13;}
.dash-kpi.kpi-accent{border-color:var(--accent-border);background:var(--accent-bg);}
.dash-kpi.kpi-accent .dash-kpi-val{color:var(--accent);}

/* Zone C: Work Blocks */
.dash-work-grid{display:grid;grid-template-columns:63fr 37fr;gap:18px;margin-bottom:22px;}
@media(max-width:900px){.dash-work-grid{grid-template-columns:1fr;}}
.dash-panel{background:var(--bg-raised);border:0.5px solid var(--border);border-radius:12px;
  padding:20px 22px;box-shadow:0 1px 5px rgba(0,0,0,.05);}
.dash-panel-title{font-size:14px;font-weight:700;color:var(--text);margin-bottom:3px;letter-spacing:-.1px;}
.dash-panel-sub{font-size:11px;color:var(--text-secondary);margin-bottom:16px;font-weight:500;}
.dash-right-col{display:flex;flex-direction:column;gap:16px;}

/* Heute priorisiert cards */
.dash-prio-item{display:flex;align-items:flex-start;gap:12px;padding:12px 14px;
  background:var(--bg);border:0.5px solid var(--border);border-radius:9px;
  border-left:3px solid #ccc;margin-bottom:8px;
  transition:box-shadow .15s,transform .15s;box-shadow:0 1px 3px rgba(0,0,0,.04);}
.dash-prio-item:last-child{margin-bottom:0;}
.dash-prio-item:hover{box-shadow:0 4px 16px rgba(0,0,0,.09);transform:translateY(-1px);}
.dash-prio-item.prio-red{border-left-color:#D63B3A;}
.dash-prio-item.prio-amber{border-left-color:#C17C13;}
.dash-prio-item.prio-blue{border-left-color:#2E72C2;}
.dash-prio-item.prio-green{border-left-color:#1D9E75;}
.dash-prio-item.prio-gray{border-left-color:#B4B2A9;}
.dash-prio-body{flex:1;min-width:0;}
.dash-prio-title{font-size:13px;font-weight:600;color:var(--text);margin-bottom:3px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.dash-prio-meta{font-size:11px;color:var(--text-secondary);margin-bottom:5px;font-weight:500;}
.dash-prio-tags{display:flex;gap:4px;flex-wrap:wrap;align-items:center;}
.dash-tag{font-size:10px;padding:2px 7px;border-radius:5px;white-space:nowrap;font-weight:600;}
.dash-tag-red{background:#FCEBEB;color:#8B2020;}
.dash-tag-amber{background:#FEF3E2;color:#7A4A08;}
.dash-tag-blue{background:#E8F0FE;color:#1a5ca8;}
.dash-tag-gray{background:#F1EFE8;color:#5F5E5A;}
.dash-tag-green{background:#EAF3DE;color:#2E6010;}
.dash-prio-next{font-size:10px;color:var(--text-secondary);margin-left:2px;font-style:italic;}
/* Kebab/dots context menu */
.dash-prio-menu{position:relative;flex-shrink:0;margin-left:auto;}
.dash-prio-dots{background:none;border:1px solid transparent;border-radius:6px;width:30px;height:30px;
  cursor:pointer;color:var(--muted);display:flex;align-items:center;justify-content:center;
  font-size:18px;line-height:1;letter-spacing:1px;
  transition:background .12s,color .12s,border-color .12s,transform .22s cubic-bezier(.4,0,.2,1);
  padding:0;font-family:inherit;}
.dash-prio-dots:hover,.dash-prio-menu.open .dash-prio-dots{
  background:var(--bg-raised);color:var(--text);border-color:var(--border);}
.dash-prio-menu.open .dash-prio-dots{transform:rotate(90deg);}
.dash-prio-dropdown{position:absolute;right:0;top:calc(100% + 5px);background:var(--bg-raised);
  border:1px solid var(--border);border-radius:10px;padding:4px;min-width:155px;
  box-shadow:0 8px 32px rgba(0,0,0,.14),0 2px 6px rgba(0,0,0,.06);z-index:200;
  opacity:0;transform:translateY(-8px) scale(.96);pointer-events:none;
  transition:opacity .16s,transform .16s cubic-bezier(.4,0,.2,1);}
.dash-prio-menu.open .dash-prio-dropdown{opacity:1;transform:translateY(0) scale(1);pointer-events:auto;}
.dash-prio-dd-btn{display:flex;align-items:center;gap:9px;width:100%;text-align:left;padding:8px 12px;
  background:none;border:none;border-radius:7px;font-size:12px;font-weight:500;color:var(--text);
  cursor:pointer;font-family:inherit;transition:background .1s,color .1s;white-space:nowrap;}
.dash-prio-dd-btn:hover{background:var(--accent-bg);color:var(--accent);}
.dash-prio-dd-btn.dd-kira{color:#534AB7;}
.dash-prio-dd-btn.dd-kira:hover{background:#EEEDFE;color:#534AB7;}
.dash-prio-dd-sep{height:1px;background:var(--border);margin:3px 4px;}
/* Standalone buttons (used elsewhere on dashboard) */
.dash-btn{font-size:11px;padding:5px 12px;border-radius:6px;border:1px solid var(--border);
  background:var(--bg-raised);color:var(--text-secondary);cursor:pointer;white-space:nowrap;
  transition:background .12s,color .12s,box-shadow .12s,transform .12s;
  font-family:inherit;font-weight:500;box-shadow:0 1px 3px rgba(0,0,0,.06);}
.dash-btn:hover{background:var(--accent-bg);border-color:var(--accent-border);color:var(--accent);
  box-shadow:0 3px 10px rgba(79,125,249,.18);transform:translateY(-1px);}
.dash-btn:active{transform:translateY(0);box-shadow:none;}
.dash-btn-kira{background:#EEEDFE;border-color:#CECBF6;color:#534AB7;box-shadow:0 1px 3px rgba(83,74,183,.1);}
.dash-btn-kira:hover{background:#DDD9FA;box-shadow:0 3px 10px rgba(83,74,183,.25);transform:translateY(-1px);}

/* Termine & Fristen list */
.dash-term-item{display:flex;align-items:center;gap:10px;padding:8px 10px;
  border-radius:6px;font-size:12px;color:var(--text);}
.dash-term-item:nth-child(odd){background:var(--bg);}
.dash-term-date{font-size:11px;font-weight:600;min-width:48px;flex-shrink:0;}
.dash-term-date.urgent{color:#E24B4A;}
.dash-term-date.soon{color:#EF9F27;}
.dash-term-date.normal{color:var(--muted);}
.dash-term-text{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.dash-term-badge{font-size:9px;padding:2px 6px;border-radius:4px;margin-left:auto;white-space:nowrap;font-weight:500;}

/* Geschäft aktuell list */
.dash-biz-item{display:flex;align-items:center;gap:8px;padding:8px 10px;
  border-radius:6px;font-size:12px;color:var(--text);}
.dash-biz-item:nth-child(odd){background:var(--bg);}
.dash-biz-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;}
.dash-biz-text{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;}
.dash-biz-val{margin-left:auto;font-weight:600;font-size:12px;white-space:nowrap;flex-shrink:0;}

/* Zone D: Signals */
.dash-signals{background:var(--bg-raised);border:0.5px solid var(--border);border-radius:12px;
  padding:20px 22px;margin-bottom:22px;box-shadow:0 1px 5px rgba(0,0,0,.05);}
.dash-sig-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:14px;}
@media(max-width:860px){.dash-sig-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}
@media(max-width:480px){.dash-sig-grid{grid-template-columns:1fr;}}
.dash-sig{padding:11px 14px;border-radius:9px;border:1px solid;display:flex;align-items:flex-start;
  gap:8px;font-size:11px;font-weight:500;cursor:pointer;
  transition:box-shadow .15s,transform .15s;line-height:1.5;}
.dash-sig:hover{transform:translateY(-1px);box-shadow:0 4px 14px rgba(0,0,0,.1);}
.dash-sig .sig-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-top:3px;}
.dash-sig .sig-text{flex:1;}
.dash-sig .sig-arr{margin-left:auto;font-size:13px;opacity:.6;flex-shrink:0;font-weight:600;}
.dash-sig.s-red{background:#FEF2F2;border-color:#FCA5A5;color:#7C1E1E;}
.dash-sig.s-amber{background:#FFFBEB;border-color:#FCD34D;color:#7A4A08;}
.dash-sig.s-blue{background:#EFF6FF;border-color:#93C5FD;color:#1a4a8a;}
.dash-sig.s-coral{background:#FFF5F2;border-color:#FCA497;color:#712B13;}
.dash-sig.s-teal{background:#F0FDF9;border-color:#6EE7C0;color:#0D5B46;}
.dash-sig.s-gray{background:var(--bg);border-color:var(--border);color:var(--text-secondary);}

/* Legacy compat for old cockpit classes (used in Kira briefing inside panel-dashboard) */
.briefing-icon{width:26px;height:26px;background:var(--accent);color:#fff;border-radius:6px;display:flex;
  align-items:center;justify-content:center;font-weight:900;font-size:13px;flex-shrink:0;}
.monitor-dot{width:8px;height:8px;border-radius:50%;background:var(--success);display:inline-block;}

/* Legacy compat */
.summary{display:flex;gap:8px;margin-bottom:18px;flex-wrap:wrap;}
.sum-item{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:11px 15px;flex:1;min-width:90px;}
.sum-num{font-size:var(--fs-xl);font-weight:900;color:var(--accent);}
.sum-label{font-size:var(--fs-xs);color:var(--muted);margin-top:1px;}
.sum-alarm{border-color:rgba(220,74,74,.35);background:rgba(220,74,74,.04);}
.sum-alarm .sum-num{color:var(--danger);}
.clickable-kpi{cursor:pointer;transition:border-color .2s,transform .1s;}
.clickable-kpi:hover{border-color:var(--accent-border);transform:translateY(-1px);}
.dash-mini-block{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:13px;}
.dash-row{display:flex;gap:8px;padding:5px 0;border-bottom:1px solid var(--border);align-items:center;flex-wrap:wrap;font-size:var(--fs-sm);}
.dash-typ{color:var(--accent);font-weight:700;min-width:80px;}
.dash-datum{color:var(--muted);min-width:70px;}
.dash-betrag{color:var(--text);font-weight:600;min-width:80px;text-align:right;}
.dash-name{color:var(--text-secondary);flex:1;}
.dash-summary-num{font-size:var(--fs-xxl);font-weight:900;color:var(--accent);margin:8px 0 2px;}

/* ═══ Kommunikation Filters ═══ */
.komm-view-tabs{display:flex;gap:2px;margin-bottom:12px;flex-wrap:wrap;}
.komm-view-tab{padding:6px 14px;border-radius:var(--radius);cursor:pointer;font-size:var(--fs-sm);font-weight:700;
  color:var(--muted);border:1px solid transparent;transition:all .15s;user-select:none;}
.komm-view-tab:hover{color:var(--text);background:rgba(128,128,128,.08);}
.komm-view-tab.active{color:var(--accent);background:var(--accent-bg);border-color:var(--accent-border);}
.komm-filter-bar{display:flex;gap:10px;margin-bottom:16px;align-items:center;flex-wrap:wrap;
  padding:10px 14px;background:var(--bg-raised);border:1px solid var(--border);border-radius:var(--radius);}
.komm-filter-bar select{background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;
  padding:5px 10px;font-size:var(--fs-sm);font-family:inherit;cursor:pointer;}
.komm-filter-bar select:focus{outline:none;border-color:var(--accent-border);}
.komm-filter-check{font-size:var(--fs-sm);color:var(--text-secondary);display:flex;align-items:center;gap:4px;cursor:pointer;}
.komm-filter-check input{accent-color:var(--accent);}
.komm-filter-count{font-size:var(--fs-sm);color:var(--muted);margin-left:auto;}

/* ═══ Kommunikation Modul v2 ═══ */
#panel-kommunikation{max-width:none;padding:0;}
#panel-kommunikation.active{display:flex;flex-direction:column;}
.km-hdr{background:var(--header-bg);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;}
.km-hdr-left{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.km-title{font-size:18px;font-weight:500;color:var(--text);}
.km-stats{display:flex;gap:14px;flex-wrap:wrap;}
.km-stat{font-size:12px;color:var(--muted);}
.km-stat b{font-weight:500;color:var(--text);}
.km-stat-link{cursor:pointer;border-radius:4px;padding:1px 4px;transition:background .15s;}
.km-stat-link:hover{background:var(--accent-bg);color:var(--accent);}
.km-stat-link:hover b{color:var(--accent);}
.km-ctx-thread-loading{font-size:11px;color:var(--muted);padding:8px 0;}
.km-thread-current{border-left:2px solid var(--accent);padding-left:8px;}
.km-thread-load-btn{font-size:10px;padding:1px 7px;border-radius:4px;border:1px solid var(--border);background:var(--bg-raised);color:var(--muted);cursor:pointer;margin-left:8px;transition:all .15s;}
.km-thread-load-btn:hover{border-color:var(--accent-border);color:var(--accent);}
.km-hdr-acts{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap;}
.km-act-btn{font-size:11px;padding:5px 12px;border-radius:6px;border:1px solid var(--border);background:var(--bg-raised);color:var(--text-secondary);cursor:pointer;white-space:nowrap;transition:all .15s;}
.km-act-btn:hover{border-color:var(--accent-border);color:var(--accent);}
.km-seg{background:var(--header-bg);border-bottom:1px solid var(--border);padding:0 24px;display:flex;gap:0;overflow-x:auto;scrollbar-width:none;}
.km-seg::-webkit-scrollbar{display:none;}
.km-seg-t{padding:11px 16px;font-size:13px;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap;transition:color .15s;user-select:none;}
.km-seg-t:hover{color:var(--text-secondary);}
.km-seg-t.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:500;}
.km-seg-cnt{font-size:10px;background:var(--bg-raised);color:var(--muted);padding:1px 6px;border-radius:10px;margin-left:4px;}
.km-seg-t.active .km-seg-cnt{background:var(--accent-bg);color:var(--accent);}
.km-flt{background:var(--header-bg);border-bottom:1px solid var(--border);padding:10px 24px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;}
.km-flt-label{font-size:11px;color:var(--muted);margin-right:2px;}
.km-fc{font-size:11px;padding:4px 10px;border-radius:14px;border:1px solid var(--border);background:var(--bg-raised);color:var(--text-secondary);cursor:pointer;white-space:nowrap;transition:all .15s;user-select:none;}
.km-fc:hover{border-color:var(--accent-border);color:var(--accent);}
.km-fc.active{background:var(--accent-bg);border-color:var(--accent-border);color:var(--accent);}
.km-fc-sel{font-size:11px;padding:4px 8px;border-radius:14px;border:1px solid var(--border);background:var(--bg-raised);color:var(--text-secondary);cursor:pointer;outline:none;font-family:inherit;}
.km-fc-sel:focus{border-color:var(--accent-border);}
.km-fc-count{font-size:11px;color:var(--muted);padding-left:4px;}
.km-search-inp{font-size:11px;padding:4px 10px;border-radius:14px;border:1px solid var(--border);background:var(--bg-raised);color:var(--text);outline:none;width:160px;margin-left:auto;font-family:inherit;}
.km-search-inp:focus{border-color:var(--accent-border);}
.km-workspace{display:flex;overflow:hidden;min-height:calc(100vh - 240px);}
.km-wl{width:58%;border-right:1px solid var(--border);overflow-y:auto;background:var(--bg);transition:width .2s;}
.km-wl-inner{padding:12px 16px;}
.km-ctx{width:42%;overflow-y:auto;background:var(--card);transition:width .2s;}
.km-ctx-inner{padding:20px 24px;}
.km-ctx-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:300px;color:var(--muted);font-size:13px;gap:10px;text-align:center;padding:40px 20px;}
.km-empty{text-align:center;padding:60px 20px;color:var(--muted);font-size:14px;line-height:2.2;}
/* Work Items */
.wi{display:flex;gap:12px;padding:14px 16px 14px 40px;background:var(--card);border:1px solid var(--border);border-radius:10px;margin-bottom:8px;cursor:pointer;transition:border-color .18s,background .18s,box-shadow .18s;position:relative;box-shadow:0 1px 6px rgba(0,0,0,.14);}
.wi:hover{border-color:var(--accent-border);box-shadow:0 3px 16px rgba(79,125,249,.18);}
.wi.sel{border-color:var(--accent);background:var(--accent-bg);box-shadow:0 0 0 2px rgba(79,125,249,.18);}
.wi.selected{border-color:var(--accent);box-shadow:0 0 0 2px rgba(55,138,221,.15);}
.wi-check{position:absolute;left:10px;top:50%;transform:translateY(-50%);z-index:2;opacity:0;transition:opacity .15s;}
.wi-check input[type=checkbox]{width:20px;height:20px;cursor:pointer;accent-color:var(--accent);}
.wi:hover .wi-check,.wi.selected .wi-check{opacity:1;}
.wi-accent{width:3px;border-radius:2px;flex-shrink:0;align-self:stretch;}
.wi-body{flex:1;min-width:0;}
.wi-top{display:flex;align-items:center;gap:6px;margin-bottom:5px;}
.wi-tags-row{display:flex;gap:4px;flex-wrap:wrap;align-items:center;flex:1;}
.wi-time{font-size:11px;color:var(--muted);flex-shrink:0;font-weight:500;}
.wi-title{font-size:15px;font-weight:700;color:var(--text);margin-bottom:4px;line-height:1.3;letter-spacing:-.01em;}
.wi-meta{font-size:var(--fs-sm);color:var(--muted);margin-bottom:4px;}
.wi-sum{font-size:13px;color:var(--text-secondary);margin-bottom:4px;line-height:1.5;}
.wi-empfehlung{font-size:var(--fs-sm);color:var(--accent);font-weight:600;margin-bottom:3px;}
.wi-grund{font-size:var(--fs-xs);color:var(--muted);font-style:italic;margin-bottom:5px;line-height:1.4;}
.wi-acts{display:flex;gap:4px;flex-wrap:wrap;margin-top:6px;}
.wi-quick-btn{font-size:var(--fs-xs);padding:3px 10px;border-radius:5px;cursor:pointer;white-space:nowrap;transition:all .15s;font-weight:600;}
.wi-btn-k{background:var(--accent-bg);border:1px solid var(--accent-border);color:var(--accent);}
.wi-btn-k:hover{background:var(--accent);color:#fff;border-color:var(--accent);}
/* Tags (km-) */
.km-tg{font-size:9px;padding:2px 7px;border-radius:4px;white-space:nowrap;}
.km-tg-red{background:rgba(220,74,74,.12);color:#d06060;}
.km-tg-amber{background:rgba(239,159,39,.12);color:#a07020;}
.km-tg-blue{background:var(--accent-bg);color:var(--accent);}
.km-tg-gray{background:var(--bg-raised);color:var(--muted);}
.km-tg-green{background:rgba(80,180,80,.1);color:#3a8a3a;}
.km-tg-purple{background:var(--accent-bg);color:var(--accent);border:1px solid var(--accent-border);}
.km-tg-warn{background:rgba(212,147,62,.12);color:var(--warn);border:1px solid rgba(212,147,62,.2);}
/* Context panel */
.km-ctx-title{font-size:18px;font-weight:700;color:var(--text);margin-bottom:8px;line-height:1.3;letter-spacing:-.01em;}
.km-ctx-meta{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;}
.km-ctx-block{margin-bottom:16px;}
.km-ctx-h{font-size:10px;font-weight:600;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.6px;}
.km-ctx-text{font-size:13px;color:var(--text);line-height:1.6;}
.km-ctx-text.muted{color:var(--text-secondary);}
.km-ctx-status{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;}
.km-ctx-s{font-size:11px;padding:5px 12px;border-radius:6px;display:flex;align-items:center;gap:5px;}
.km-ctx-s .dot{width:6px;height:6px;border-radius:50%;}
.km-ctx-s.open{background:rgba(220,74,74,.12);color:#d06060;}
.km-ctx-s.open .dot{background:#E24B4A;}
.km-ctx-s.wait{background:rgba(239,159,39,.12);color:#a07020;}
.km-ctx-s.wait .dot{background:#EF9F27;}
.km-ctx-s.info{background:var(--accent-bg);color:var(--accent);}
.km-ctx-s.info .dot{background:var(--accent);}
.km-ctx-recommend{background:var(--bg-raised);border:1px solid var(--accent-border);border-radius:8px;padding:12px 16px;margin-bottom:16px;}
.km-ctx-recommend-h{font-size:11px;font-weight:500;color:var(--accent);margin-bottom:4px;}
.km-ctx-recommend-t{font-size:13px;color:var(--text);line-height:1.5;}
.km-ctx-attachments{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:4px;}
.km-ctx-att{background:var(--bg-raised);border:1px solid var(--border);border-radius:6px;padding:8px 12px;font-size:11px;color:var(--text-secondary);display:flex;align-items:center;gap:6px;cursor:pointer;transition:border-color .15s;}
.km-ctx-att:hover{border-color:var(--accent-border);color:var(--accent);}
.km-ctx-thread{border-top:1px solid var(--border);padding-top:14px;margin-bottom:16px;}
.km-ctx-msg{padding:10px 12px;border-radius:8px;margin-bottom:6px;font-size:12px;line-height:1.55;}
.km-ctx-msg.in{background:var(--bg-raised);color:var(--text);}
.km-ctx-msg.out{background:var(--accent-bg);color:var(--text);}
.km-ctx-msg-meta{font-size:10px;color:var(--muted);margin-bottom:3px;}
.km-ctx-actions{border-top:1px solid var(--border);padding-top:16px;margin-top:4px;display:flex;flex-wrap:wrap;gap:6px;}

/* ═══ Sections ═══ */
.section{margin-bottom:18px;}
.section-title{font-size:var(--fs-xs);font-weight:800;color:var(--accent);letter-spacing:.8px;
  text-transform:uppercase;padding-bottom:7px;border-bottom:1px solid var(--border);margin-bottom:10px;cursor:pointer;user-select:none;}
.section-title:after{content:' \\25BE';font-size:10px;}
.section.collapsed .section-body{display:none;}
.section.collapsed .section-title:after{content:' \\25B8';}
.count-badge{background:var(--accent-bg);color:var(--accent);font-size:var(--fs-xs);padding:1px 7px;
  border-radius:10px;font-weight:700;letter-spacing:0;text-transform:none;}

/* ═══ Task Card ═══ */
.task-card{background:var(--card);border:1px solid var(--border);border-radius:var(--card-radius);
  padding:12px 14px 12px 50px;margin-bottom:8px;transition:border-color .2s;position:relative;}
.task-card:hover{border-color:var(--accent-border);}
.prio-hoch  {border-left:3px solid var(--danger);}
.prio-mittel{border-left:3px solid var(--accent);}
.prio-niedrig{border-left:3px solid rgba(128,128,128,.4);}
.task-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;flex-wrap:wrap;gap:4px;}
.task-tags{display:flex;gap:5px;flex-wrap:wrap;align-items:center;}
.task-datum{color:var(--muted);font-size:var(--fs-sm);}
.task-title{font-size:var(--fs-md);font-weight:700;color:var(--text);margin-bottom:5px;}
.task-summary{font-size:var(--fs-sm);color:var(--text-secondary);margin-bottom:5px;}
.task-meta-row{font-size:var(--fs-sm);color:var(--muted);margin-bottom:4px;display:flex;flex-wrap:wrap;gap:5px;align-items:center;}
.meta-label{color:var(--muted);}
.meta-val{color:var(--text-secondary);}
.meta-sep{color:var(--border-strong);}
.muted-email{color:var(--muted);font-size:var(--fs-xs);}
.task-naechste{font-size:var(--fs-sm);color:var(--accent);margin-bottom:4px;font-weight:600;}
.task-grund{font-size:var(--fs-xs);color:var(--muted);margin-bottom:5px;font-style:italic;}
.task-notiz{font-size:var(--fs-sm);color:var(--muted);margin-bottom:7px;font-style:italic;}
.task-actions{display:flex;gap:5px;flex-wrap:wrap;}

/* ═══ Tags ═══ */
.tag{font-size:var(--fs-xs);font-weight:800;padding:2px 8px;border-radius:20px;}
.tag-alarm  {background:rgba(220,74,74,.12);color:var(--danger);border:1px solid rgba(220,74,74,.3);}
.tag-anfrage{background:var(--accent-bg);color:var(--accent);border:1px solid var(--accent-border);}
.tag-antwort{background:rgba(79,125,249,.1);color:#6b94ff;border:1px solid rgba(79,125,249,.25);}
.tag-zahlung{background:rgba(61,174,106,.1);color:var(--success);border:1px solid rgba(61,174,106,.25);}
.tag-rechnung{background:rgba(212,147,62,.1);color:var(--warn);border:1px solid rgba(212,147,62,.25);}
.tag-shop   {background:rgba(200,130,80,.1);color:#d08050;border:1px solid rgba(200,130,80,.2);}
.tag-muted  {background:rgba(128,128,128,.08);color:var(--muted);border:1px solid var(--border);}
.konto-badge{font-size:var(--fs-xs);color:var(--muted);background:rgba(128,128,128,.06);border:1px solid var(--border);border-radius:5px;padding:2px 6px;}
.badge{font-size:var(--fs-xs);padding:2px 7px;border-radius:10px;font-weight:700;}
.badge-warn {background:rgba(212,147,62,.15);color:var(--warn);border:1px solid rgba(212,147,62,.25);}
.badge-warn2{background:rgba(220,100,50,.15);color:#d06040;border:1px solid rgba(220,100,50,.25);}
.badge-alarm{background:rgba(220,74,74,.12);color:var(--danger);border:1px solid rgba(220,74,74,.25);}
.muted{color:var(--muted);}

/* ═══ Buttons ═══ */
.btn{padding:6px 12px;border-radius:var(--radius);font-size:var(--fs-sm);font-weight:700;cursor:pointer;
  border:none;display:inline-block;transition:all .15s;text-decoration:none;line-height:1.4;font-family:inherit;}
.btn-primary{background:var(--accent);color:#fff;}
.btn-primary:hover{opacity:.88;}
.btn-kira{background:var(--accent-bg);color:var(--accent);border:1px solid var(--accent-border);}
.btn-kira:hover{background:rgba(79,125,249,.18);}
.btn-sec{background:rgba(128,128,128,.08);color:var(--text);border:1px solid var(--border);}
.btn-sec:hover{background:rgba(128,128,128,.14);}
.btn-done{background:rgba(61,174,106,.1);color:var(--success);border:1px solid rgba(61,174,106,.22);}
.btn-done:hover{background:rgba(61,174,106,.2);}
.btn-kenntnis{background:rgba(55,138,221,.08);color:#378ADD;border:1px solid rgba(55,138,221,.2);}
.btn-kenntnis:hover{background:rgba(55,138,221,.16);}
.btn-later{background:rgba(212,147,62,.1);color:var(--warn);border:1px solid rgba(212,147,62,.2);}
.btn-later:hover{background:rgba(212,147,62,.2);}
.btn-ignore{background:rgba(128,128,128,.08);color:rgba(128,128,128,.7);border:1px solid rgba(128,128,128,.18);}
.btn-ignore:hover{background:rgba(128,128,128,.16);}
.btn-korr{background:rgba(128,128,128,.05);color:var(--muted);border:1px solid var(--border);}
.btn-korr:hover{background:rgba(128,128,128,.12);color:var(--text);}
.badge-erinnerung{background:rgba(212,147,62,.12);color:var(--warn);border:1px solid rgba(212,147,62,.25);}
.btn-loeschen{background:rgba(220,74,74,.08);color:#d06060;border:1px solid rgba(220,74,74,.2);}
.btn-loeschen:hover{background:rgba(220,74,74,.18);}
.loeschen-grund-btn{padding:4px 10px;font-size:11px;border-radius:5px;border:1px solid var(--border);background:var(--bg-raised);color:var(--text-secondary);cursor:pointer;transition:all .15s;}
.loeschen-grund-btn:hover,.loeschen-grund-btn.active{background:rgba(220,74,74,.12);border-color:rgba(220,74,74,.35);color:#d06060;}
/* Multi-select */
.tc-check{position:absolute;left:12px;top:50%;transform:translateY(-50%);z-index:2;opacity:0;transition:opacity .15s;cursor:pointer;display:flex;align-items:center;}
.tc-check input[type=checkbox]{width:24px;height:24px;cursor:pointer;accent-color:var(--accent);border-radius:5px;}
.task-card:hover .tc-check,.task-card.selected .tc-check{opacity:1;}
.task-card.selected{border-color:var(--accent);box-shadow:0 0 0 2px rgba(55,138,221,.18);}
.task-card.selected::before{content:'';position:absolute;inset:0;border-radius:var(--card-radius);background:rgba(55,138,221,.04);pointer-events:none;}
/* Multi-Toolbar */
.multi-toolbar{position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(80px);
  background:var(--bg-raised);border:1px solid var(--border);border-radius:12px;
  box-shadow:0 8px 32px rgba(0,0,0,.18);padding:10px 16px;display:flex;align-items:center;
  gap:10px;z-index:9000;transition:transform .25s cubic-bezier(.34,1.56,.64,1),opacity .2s;opacity:0;}
.multi-toolbar.visible{transform:translateX(-50%) translateY(0);opacity:1;}
.multi-tb-count{font-size:13px;font-weight:600;color:var(--text);min-width:72px;}
.multi-tb-sep{width:1px;height:24px;background:var(--border);}
.multi-toolbar .btn{font-size:12px;padding:5px 12px;}
.btn-sm{padding:5px 12px;font-size:var(--fs-sm);}
.btn-tiny{padding:3px 8px;font-size:var(--fs-xs);}
.btn-xs{padding:2px 6px;font-size:10px;}
.btn-green{background:rgba(61,174,106,.1);color:var(--success);border:1px solid rgba(61,174,106,.22);}
.btn-green:hover{background:rgba(61,174,106,.2);}
.btn-gold{background:var(--accent-bg);color:var(--accent);border:1px solid var(--accent-border);}
.btn-gold:hover{opacity:.85;}
.btn-muted{background:rgba(128,128,128,.06);color:var(--muted);border:1px solid var(--border);}
.btn-muted:hover{background:rgba(128,128,128,.12);color:var(--text);}
.btn-warn{background:rgba(220,74,74,.06);color:#d06060;border:1px solid rgba(220,74,74,.18);}
.btn-warn:hover{background:rgba(220,74,74,.14);}
.badge-korrekt{font-size:10px;font-weight:700;color:var(--success);background:rgba(61,174,106,.1);padding:1px 6px;border-radius:3px;}
.att-link{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;margin:2px 3px;border-radius:5px;font-size:var(--fs-sm);
  background:var(--accent-bg);border:1px solid var(--accent-border);color:var(--accent);text-decoration:none;transition:all .15s;}
.att-link:hover{opacity:.85;}
.att-icon{font-size:10px;font-weight:800;color:var(--muted);}

/* ═══ Organisation ═══ */
.org-view-tabs{display:flex;gap:2px;margin-bottom:14px;flex-wrap:wrap;}
.org-view{display:none;}.org-view.active{display:block;}
.org-row{display:flex;gap:10px;padding:7px 8px;border-radius:var(--radius);margin-bottom:3px;align-items:center;flex-wrap:wrap;background:var(--accent-bg);}
.org-typ-badge{font-size:var(--fs-xs);font-weight:700;color:var(--accent);background:rgba(128,128,128,.08);padding:2px 8px;border-radius:4px;min-width:60px;text-align:center;}
.org-datum{color:var(--muted);font-size:var(--fs-sm);min-width:90px;}
.org-betreff{flex:1;font-size:var(--fs-base);}
.org-email{font-size:var(--fs-sm);min-width:130px;text-align:right;}
.org-konto{font-size:var(--fs-xs);}

/* ═══ Geschaeft ═══ */
/* Module Header */
.gh-mod-header{display:flex;align-items:center;gap:12px;padding:12px 16px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);margin-bottom:14px;flex-wrap:wrap;}
.gh-mod-title{font-size:var(--fs-lg);font-weight:800;color:var(--text);white-space:nowrap;}
.gh-mod-stats{display:flex;gap:16px;flex-wrap:wrap;flex:1;}
.gh-stat{display:flex;flex-direction:column;align-items:center;min-width:52px;}
.gh-stat-num{font-size:var(--fs-base);font-weight:700;color:var(--accent);line-height:1.2;}
.gh-stat-lbl{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.3px;white-space:nowrap;}
.gh-stat.alarm .gh-stat-num{color:var(--danger);}
.gh-mod-acts{display:flex;gap:6px;margin-left:auto;}
/* Tabs */
.gesch-tabs,.wissen-tabs{display:flex;gap:2px;margin-bottom:14px;flex-wrap:wrap;}
.gesch-tab,.wissen-tab{padding:6px 14px;border-radius:var(--radius);cursor:pointer;font-size:var(--fs-sm);font-weight:700;color:var(--muted);border:1px solid transparent;transition:all .15s;user-select:none;}
.gesch-tab:hover,.wissen-tab:hover{color:var(--text);background:rgba(128,128,128,.08);}
.gesch-tab.active,.wissen-tab.active{color:var(--accent);background:var(--accent-bg);border-color:var(--accent-border);}
.gesch-panel,.wissen-panel{display:none;}
.gesch-panel.active,.wissen-panel.active{display:block;}
/* KPI Grid */
.gh-kpi-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px;}
@media(max-width:680px){.gh-kpi-grid{grid-template-columns:repeat(2,1fr);}}
.gh-kpi-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:13px 15px;cursor:pointer;transition:border-color .2s,transform .1s;}
.gh-kpi-card:hover{border-color:var(--accent-border);transform:translateY(-1px);}
.gh-kpi-card.alarm{border-color:rgba(220,74,74,.3);background:rgba(220,74,74,.03);}
.gh-kpi-num{font-size:22px;font-weight:800;color:var(--accent);letter-spacing:-.5px;line-height:1.1;}
.gh-kpi-card.alarm .gh-kpi-num{color:var(--danger);}
.gh-kpi-lbl{font-size:var(--fs-xs);color:var(--muted);margin-top:3px;text-transform:uppercase;letter-spacing:.3px;}
.gh-kpi-sub{font-size:var(--fs-xs);color:var(--text-secondary);margin-top:2px;}
/* 60/40 Zones */
.gh-zones{display:grid;grid-template-columns:3fr 2fr;gap:12px;}
@media(max-width:860px){.gh-zones{grid-template-columns:1fr;}}
.gh-zone{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden;}
.gh-zone-hdr{display:flex;align-items:center;justify-content:space-between;padding:9px 13px;border-bottom:1px solid var(--border);font-size:var(--fs-sm);font-weight:700;color:var(--text);}
.gh-zone-body{padding:8px 10px;max-height:340px;overflow-y:auto;}
/* Business item rows */
.gh-bi-row{display:flex;align-items:flex-start;gap:8px;padding:7px 6px;border-radius:6px;margin-bottom:2px;transition:background .12s;}
.gh-bi-row:hover{background:rgba(128,128,128,.06);}
.gh-bi-typ{font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;white-space:nowrap;flex-shrink:0;margin-top:2px;}
.gh-bi-typ.re{color:var(--accent);background:var(--accent-bg);}
.gh-bi-typ.nf{color:#a78bfa;background:rgba(167,139,250,.1);}
.gh-bi-typ.mah{color:var(--danger);background:rgba(220,74,74,.1);}
.gh-bi-info{flex:1;min-width:0;}
.gh-bi-name{font-size:var(--fs-sm);color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.gh-bi-meta{font-size:10px;color:var(--muted);margin-top:1px;}
.gh-bi-right{display:flex;flex-direction:column;align-items:flex-end;gap:2px;flex-shrink:0;}
.gh-bi-betrag{font-size:var(--fs-sm);font-weight:700;color:var(--text);white-space:nowrap;}
/* Warning items */
.gh-warn-item{display:flex;align-items:flex-start;gap:8px;padding:8px 10px;border-radius:6px;margin-bottom:4px;border-left:2px solid rgba(220,74,74,.4);background:rgba(220,74,74,.04);}
.gh-warn-item.info{border-left-color:var(--accent-border);background:rgba(128,128,128,.04);}
.gh-warn-item.ok{border-left-color:rgba(80,200,120,.4);background:rgba(80,200,120,.03);}
.gh-warn-dot{width:6px;height:6px;border-radius:50%;background:var(--danger);margin-top:5px;flex-shrink:0;}
.gh-warn-item.info .gh-warn-dot{background:var(--accent);}
.gh-warn-item.ok .gh-warn-dot{background:#50c878;}
.gh-warn-body{flex:1;}
.gh-warn-text{font-size:var(--fs-sm);color:var(--text);}
.gh-warn-sub{font-size:10px;color:var(--muted);margin-top:2px;}
.gh-warn-act{font-size:var(--fs-xs);color:var(--accent);cursor:pointer;margin-top:3px;display:inline-block;}
.gh-warn-act:hover{text-decoration:underline;}
/* Table classes (used by AR/ANG/Zahlungen/Mahnungen tabs) */
.gesch-summary-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;}
.gesch-sum-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:12px;text-align:center;cursor:pointer;transition:border-color .2s,transform .1s;}
.gesch-sum-card:hover{border-color:var(--accent-border);transform:translateY(-1px);}
.gesch-sum-num{font-size:var(--fs-xl);font-weight:900;color:var(--accent);}
.gesch-sum-label{font-size:var(--fs-xs);color:var(--muted);margin-top:2px;}
.gesch-sum-alarm{border-color:rgba(220,74,74,.3);background:rgba(220,74,74,.04);}
.gesch-sum-alarm .gesch-sum-num{color:var(--danger);}
.gesch-table{font-size:var(--fs-sm);}
.gesch-row{display:flex;gap:6px;padding:6px 4px;border-bottom:1px solid var(--border);align-items:center;}
.gesch-header{font-weight:700;color:var(--accent);border-bottom:1px solid var(--border-strong);}
.gc-datum{min-width:80px;color:var(--muted);}
.gc-betrag{min-width:80px;text-align:right;font-weight:600;}
.gc-nr{min-width:90px;color:var(--muted);}.gc-partner{min-width:120px;flex:1;}
.gesch-typ-badge{font-size:10px;font-weight:700;color:var(--accent);background:var(--accent-bg);padding:1px 6px;border-radius:3px;}
.gesch-aktiv-card{background:var(--card);border:1px solid rgba(220,74,74,.16);border-radius:var(--radius-lg);padding:13px;margin-bottom:10px;}
.gesch-aktiv-header{display:flex;gap:10px;align-items:center;margin-bottom:6px;flex-wrap:wrap;}
.gesch-aktiv-betrag{font-size:var(--fs-lg);font-weight:900;color:var(--text);}
.gesch-aktiv-datum{font-size:var(--fs-sm);color:var(--muted);margin-left:auto;}
.gesch-aktiv-body{margin-bottom:8px;}
.gesch-aktiv-betreff{font-size:var(--fs-base);font-weight:600;color:var(--text);}
.gesch-aktiv-partner{font-size:var(--fs-sm);color:var(--muted);}
.gesch-aktiv-actions{display:flex;gap:6px;flex-wrap:wrap;}
.gesch-typ-eingang{color:var(--accent);background:var(--accent-bg);}
.gesch-typ-mahnung{color:var(--danger);background:rgba(220,74,74,.08);}
.gesch-row-aktiv{border-left:2px solid var(--danger);}
.gc-detail{min-width:100px;flex:1;color:var(--muted);}.gc-actions{display:flex;gap:4px;min-width:120px;justify-content:flex-end;}
.gesch-ar-summary{display:flex;gap:20px;padding:10px 14px;margin-bottom:10px;background:var(--accent-bg);border:1px solid var(--border);border-radius:var(--radius);font-size:var(--fs-base);flex-wrap:wrap;}
.gesch-ar-summary span{white-space:nowrap;}
.gesch-filter-bar{display:flex;gap:10px;margin-bottom:14px;align-items:center;flex-wrap:wrap;}
.gesch-filter-bar select{background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:var(--fs-sm);font-family:inherit;cursor:pointer;}
.gesch-filter-bar select:focus{outline:none;border-color:var(--accent-border);}
.gesch-filter-count{font-size:var(--fs-sm);color:var(--muted);margin-left:auto;}
.gc-status{min-width:80px;}.gc-nf{min-width:110px;}
.gesch-urgent-item{display:flex;gap:8px;align-items:center;padding:7px 8px;border-radius:var(--radius);margin-bottom:3px;background:rgba(220,74,74,.04);font-size:var(--fs-base);flex-wrap:wrap;}
.gesch-nf-indicator{font-size:var(--fs-xs);font-weight:700;padding:2px 6px;border-radius:4px;background:rgba(128,128,128,.08);}
.nf-overdue{color:var(--danger);background:rgba(220,74,74,.1);animation:pulse 2s infinite;}
.nf-planned{color:var(--accent);}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}

/* ═══ Einstellungen ═══ */
.settings-row{display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);}
.settings-row label{font-size:var(--fs-base);color:var(--text);min-width:200px;}
.settings-row input[type=text],.settings-row input[type=number]{background:var(--bg);color:var(--text);border:1px solid var(--border);
  border-radius:6px;padding:6px 10px;font-size:var(--fs-base);width:220px;font-family:inherit;}
.settings-row input[type=checkbox]{width:18px;height:18px;accent-color:var(--accent);}
.settings-row input[type=color]{width:40px;height:28px;border:1px solid var(--border);border-radius:4px;cursor:pointer;background:transparent;}
.settings-row select{background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:var(--fs-base);font-family:inherit;}

/* ═══ Wissen ═══ */
.wissen-level-tabs{display:flex;gap:4px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--border);}
.wissen-level-tab{padding:8px 18px;border-radius:var(--radius);cursor:pointer;font-size:var(--fs-base);font-weight:800;
  color:var(--muted);border:1px solid transparent;transition:all .15s;user-select:none;}
.wissen-level-tab:hover{color:var(--text);background:rgba(128,128,128,.08);}
.wissen-level-tab.active{color:var(--accent);background:var(--accent-bg);border-color:var(--accent-border);}
.wissen-level{display:none;}.wissen-level.active{display:block;}
.wissen-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:12px;margin-bottom:8px;}
.wissen-vorschlag{border-color:var(--accent-border);}
.wissen-korr{border-color:rgba(212,147,62,.2);}
.wissen-titel{font-size:var(--fs-base);font-weight:700;color:var(--accent);margin-bottom:4px;}
.wissen-inhalt{font-size:var(--fs-sm);color:var(--text-secondary);margin-bottom:6px;line-height:1.6;}
.wissen-status{font-size:var(--fs-xs);color:var(--muted);}
.wissen-actions{display:flex;gap:6px;}
.wissen-meta{font-size:var(--fs-xs);color:var(--muted);display:flex;align-items:center;}

/* ═══ Toast ═══ */
.status-toast{position:fixed;bottom:82px;right:24px;background:var(--bg-raised);border:1px solid var(--accent-border);
  border-radius:var(--radius-lg);padding:10px 18px;color:var(--accent);font-weight:700;font-size:var(--fs-base);
  transform:translateY(50px);opacity:0;transition:all .28s;z-index:500;pointer-events:none;
  box-shadow:0 4px 20px rgba(0,0,0,.25);}
.status-toast.show{transform:translateY(0);opacity:1;pointer-events:auto;}
.status-toast.ok{background:#1a6e3c;color:#fff;border-color:#1a6e3c;}
.status-toast.fehler{background:#c0392b;color:#fff;border-color:#c0392b;}
.status-toast.warnung{background:#c87417;color:#fff;border-color:#c87417;}
.status-toast.info{background:var(--accent);color:#fff;border-color:var(--accent);}
#toast-copy-btn{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);border-radius:5px;cursor:pointer;font-size:16px;padding:3px 8px;margin-left:10px;opacity:.85;vertical-align:middle;color:inherit;line-height:1;flex-shrink:0;}
#toast-copy-btn:hover{opacity:1;background:rgba(255,255,255,.25);}
.status-toast{display:flex;align-items:center;gap:0;}

/* ═══ Kira FAB — Animierter Launcher ═══ */
.kira-fab{position:fixed;bottom:20px;right:20px;z-index:200;
  width:112px;height:112px;border-radius:50%;
  background:transparent;border:none;box-shadow:none;
  cursor:pointer;display:flex;align-items:center;justify-content:center;
  padding:0;outline:none;}
.kira-fab.kira-fab-active .kira-char-svg{filter:drop-shadow(0 0 12px rgba(123,104,238,.6));}
.kira-fab.kira-bored .kira-float{animation-duration:6s;animation-timing-function:ease-in-out;}
.kira-char-svg{display:block;transition:transform .25s ease-out;overflow:visible;}
.kira-float{animation:kiraFloat 4s ease-in-out infinite;transform-origin:50% 50%;}
@keyframes kiraFloat{0%,100%{transform:translateY(0) rotate(0deg);}25%{transform:translateY(-9px) rotate(1.2deg);}50%{transform:translateY(-13px) rotate(0deg);}75%{transform:translateY(-7px) rotate(-0.9deg);}}
.kira-excited .kira-float{animation:kiraFloatExcited 1s ease-in-out infinite;}
@keyframes kiraFloatExcited{0%,100%{transform:translateY(0) scaleY(1);}35%{transform:translateY(-17px) scaleY(1.06);}65%{transform:translateY(-4px) scaleY(0.96);}}
.kira-fab-status{position:absolute;top:10px;right:10px;width:14px;height:14px;
  background:#1D9E75;border-radius:50%;border:2.5px solid #fff;box-shadow:0 0 6px rgba(29,158,117,.5);}
.kira-fab-pulse{animation:kiraPulse 2s ease-in-out infinite;}
@keyframes kiraPulse{0%,100%{opacity:1;}50%{opacity:.6;}}

/* ═══ Kira Quick Panel (kq-*) ═══ */
.kq-panel{position:fixed;bottom:148px;right:20px;z-index:250;width:340px;
  background:var(--bg-raised);border:0.5px solid var(--border);border-radius:14px;
  box-shadow:0 8px 40px rgba(0,0,0,.15);display:none;flex-direction:column;overflow:hidden;}
.kq-panel.open{display:flex;}
.kq-header{display:flex;align-items:center;gap:10px;padding:18px 20px 14px;border-bottom:0.5px solid var(--border);}
.kq-logo{width:36px;height:36px;background:#534AB7;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-direction:column;flex-shrink:0;}
.kq-logo-k{color:#fff;font-size:15px;font-weight:500;line-height:1;}
.kq-logo-l{color:#CECBF6;font-size:7px;margin-top:1px;}
.kq-htext{flex:1;}
.kq-htitle{font-size:16px;font-weight:500;color:var(--text);}
.kq-hstatus{font-size:11px;color:var(--text-secondary);display:flex;align-items:center;gap:5px;margin-top:2px;}
.kq-hstatus-dot{width:6px;height:6px;border-radius:50%;background:#1D9E75;flex-shrink:0;}
.kq-close{width:28px;height:28px;border-radius:6px;border:0.5px solid var(--border);background:var(--bg);
  display:flex;align-items:center;justify-content:center;font-size:14px;color:var(--muted);cursor:pointer;}
.kq-close:hover{color:var(--text);border-color:var(--border-strong);}
.kq-actions{padding:10px 12px;}
.kq-item{display:flex;align-items:center;gap:12px;padding:11px 14px;border-radius:10px;cursor:pointer;
  transition:background .12s,border-color .12s;border:0.5px solid transparent;margin-bottom:2px;}
.kq-item:hover{background:var(--accent-bg);border-color:var(--border);}
.kq-icon{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:15px;flex-shrink:0;}
.kq-icon.purple{background:rgba(83,74,183,.12);color:#534AB7;}
.kq-icon.amber{background:rgba(186,117,23,.12);color:#BA7517;}
.kq-icon.green{background:rgba(59,109,17,.12);color:#3B6D11;}
.kq-icon.blue{background:rgba(24,95,165,.12);color:#185FA5;}
.kq-icon.coral{background:rgba(153,60,29,.12);color:#993C1D;}
.kq-icon.teal{background:rgba(15,110,86,.12);color:#0F6E56;}
.kq-icon.gray{background:rgba(128,128,128,.1);color:var(--text-secondary);}
.kq-body{flex:1;min-width:0;}
.kq-title{font-size:13px;font-weight:500;color:var(--text);margin-bottom:1px;}
.kq-sub{font-size:11px;color:var(--text-secondary);}
.kq-arrow{font-size:13px;color:var(--border-strong);flex-shrink:0;transition:color .12s;}
.kq-item:hover .kq-arrow{color:#534AB7;}
.kq-footer{padding:10px 16px 14px;border-top:0.5px solid var(--border);display:flex;align-items:center;gap:8px;}
.kq-input{flex:1;background:var(--bg);border:0.5px solid var(--border);border-radius:8px;padding:8px 12px;
  font-size:12px;color:var(--text);font-family:inherit;}
.kq-input:focus{outline:none;border-color:#534AB7;}
.kq-send{width:32px;height:32px;border-radius:8px;background:#534AB7;border:none;
  display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;cursor:pointer;flex-shrink:0;}
.kq-send:hover{background:#6358cc;}

/* ═══ Kira Workspace (kw-*) ═══ */
.kira-workspace-overlay{display:none;position:fixed;inset:0;z-index:350;background:rgba(28,28,26,.45);align-items:center;justify-content:center;padding:16px;}
.kira-workspace-overlay.open{display:flex;}
.kw-shell{background:var(--bg-raised);border:0.5px solid var(--border);border-radius:14px;
  width:96vw;max-width:1280px;height:88vh;display:flex;flex-direction:column;box-shadow:0 16px 60px rgba(0,0,0,.2);overflow:hidden;}
.kw-header{display:flex;justify-content:space-between;align-items:center;padding:14px 20px;border-bottom:0.5px solid var(--border);flex-shrink:0;}
.kw-header-left{display:flex;align-items:center;gap:10px;}
.kw-logo{width:32px;height:32px;background:#534AB7;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;font-weight:500;flex-shrink:0;}
.kw-title{font-size:15px;font-weight:500;color:var(--text);}
.kw-sub{font-size:11px;color:var(--muted);margin-top:1px;}
.kw-header-right{display:flex;gap:6px;align-items:center;}
.kw-body{display:flex;flex:1;overflow:hidden;}
.kw-ctx-panel{width:260px;min-width:260px;border-right:0.5px solid var(--border);display:flex;flex-direction:column;overflow-y:auto;background:var(--bg-raised);}
.kw-ctx-hdr{padding:16px 18px 12px;border-bottom:0.5px solid var(--border);}
.kw-ctx-hdr-t{font-size:14px;font-weight:500;color:var(--text);margin-bottom:8px;}
.kw-ctx-search{width:100%;background:var(--bg);border:0.5px solid var(--border);border-radius:6px;padding:6px 10px;font-size:11px;color:var(--muted);font-family:inherit;}
.kw-ctx-search:focus{outline:none;border-color:#534AB7;}
.kw-ctx-section{padding:12px 0;}
.kw-ctx-sec-h{font-size:10px;font-weight:500;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;padding:0 18px 6px;}
.kw-ctx-item{display:flex;align-items:flex-start;gap:8px;padding:8px 18px;cursor:pointer;transition:background .12s;border-left:2px solid transparent;}
.kw-ctx-item:hover{background:var(--accent-bg);}
.kw-ctx-item.active{background:var(--accent-bg);border-left-color:#534AB7;}
.kw-ctx-chip{font-size:8px;padding:2px 6px;border-radius:3px;white-space:nowrap;flex-shrink:0;margin-top:2px;}
.kw-ctx-chip.mail{background:rgba(24,95,165,.1);color:#185FA5;}
.kw-ctx-chip.task{background:rgba(186,117,23,.1);color:#854F0B;}
.kw-ctx-chip.inv{background:rgba(59,109,17,.1);color:#3B6D11;}
.kw-ctx-chip.offer{background:rgba(83,74,183,.1);color:#3C3489;}
.kw-ctx-chip.know{background:rgba(15,110,86,.1);color:#085041;}
.kw-ctx-chip.cust{background:rgba(153,60,29,.1);color:#712B13;}
.kw-ctx-body{flex:1;min-width:0;}
.kw-ctx-title{font-size:12px;font-weight:500;color:var(--text);margin-bottom:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.kw-ctx-sub{font-size:10px;color:var(--muted);}
.kw-ctx-sep{height:0.5px;background:var(--border);margin:0 18px;}
.kw-center{flex:1;display:flex;flex-direction:column;background:var(--bg);overflow:hidden;}
.kw-cbar{background:var(--bg-raised);border-bottom:0.5px solid var(--border);padding:10px 20px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;flex-shrink:0;}
.kw-cbar-mode{font-size:11px;padding:4px 10px;border-radius:5px;background:rgba(83,74,183,.1);color:#534AB7;font-weight:500;}
.kw-cbar-title{font-size:13px;font-weight:500;color:var(--text);}
.kw-cbar-tag{font-size:9px;padding:2px 7px;border-radius:4px;background:var(--bg);color:var(--text-secondary);}
.kw-cbar-provider{font-size:10px;color:var(--muted);margin-left:auto;display:flex;align-items:center;gap:4px;}
.kw-cbar-provider-dot{width:6px;height:6px;border-radius:50%;background:#1D9E75;}
.kw-cbar-acts{display:flex;gap:4px;}
.kw-cbar-btn{font-size:10px;padding:3px 9px;border-radius:4px;border:0.5px solid var(--border);background:var(--bg-raised);color:var(--text-secondary);cursor:pointer;white-space:nowrap;}
.kw-cbar-btn:hover{border-color:#534AB7;color:var(--text);}
.kira-chat-wrap{display:flex;flex-direction:column;flex:1;overflow:hidden;}
.kira-chat-area{flex:1;overflow-y:auto;padding:20px 24px;}
.kw-quick-bar{padding:8px 20px;display:flex;gap:6px;flex-wrap:wrap;border-bottom:0.5px solid var(--border);background:var(--bg-raised);flex-shrink:0;}
.kw-quick-lbl{font-size:10px;color:var(--muted);margin-right:4px;align-self:center;}
.kw-qb{font-size:10px;padding:5px 12px;border-radius:14px;border:0.5px solid var(--border);background:var(--bg-raised);color:var(--text-secondary);cursor:pointer;white-space:nowrap;transition:border-color .12s,color .12s;}
.kw-qb:hover{border-color:#534AB7;color:#534AB7;}
.kw-tools{width:260px;min-width:260px;border-left:0.5px solid var(--border);display:flex;flex-direction:column;overflow-y:auto;background:var(--bg-raised);}
.kw-tools.collapsed{display:none;}
.kw-tools-hdr{padding:14px 16px 10px;border-bottom:0.5px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.kw-tools-t{font-size:13px;font-weight:500;color:var(--text);}
.kw-tools-close{font-size:11px;color:var(--muted);cursor:pointer;}
.kw-tools-close:hover{color:var(--text);}
.kw-tools-sec{padding:14px 16px;}
.kw-tools-sh{font-size:10px;font-weight:500;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:8px;}
.kw-tools-sep{height:0.5px;background:var(--border);margin:0 16px;}
.kw-t-item{background:var(--bg);border:0.5px solid var(--border);border-radius:6px;padding:10px 12px;margin-bottom:6px;font-size:11px;color:var(--text);cursor:pointer;transition:border-color .12s;}
.kw-t-item:hover{border-color:#534AB7;}
.kw-t-item-h{font-weight:500;margin-bottom:2px;}
.kw-t-item-sub{font-size:10px;color:var(--text-secondary);}
.kw-t-rule{background:rgba(15,110,86,.07);border:0.5px solid rgba(15,110,86,.2);border-radius:6px;padding:8px 12px;margin-bottom:4px;font-size:11px;color:#085041;line-height:1.4;}
.kw-t-rule-h{font-weight:500;margin-bottom:2px;}
.kw-t-next{background:var(--bg);border:0.5px solid var(--border);border-radius:6px;padding:8px 12px;margin-bottom:4px;font-size:11px;cursor:pointer;color:var(--text-secondary);transition:border-color .12s,color .12s;}
.kw-t-next:hover{border-color:#534AB7;color:#534AB7;}
.kw-t-att{display:flex;align-items:center;gap:6px;padding:8px 12px;background:var(--bg);border:0.5px solid var(--border);border-radius:6px;margin-bottom:4px;font-size:11px;color:var(--text-secondary);cursor:pointer;}
.kw-input-area{background:var(--bg-raised);border-top:0.5px solid var(--border);padding:14px 20px;display:flex;align-items:flex-end;gap:10px;flex-shrink:0;}
.kw-input-box{flex:1;background:var(--bg);color:var(--text);border:0.5px solid var(--border);border-radius:10px;padding:12px 16px;font-size:13px;line-height:1.5;resize:none;font-family:inherit;min-height:48px;max-height:120px;overflow-y:auto;}
.kw-input-box:focus{outline:none;border-color:#534AB7;}
.kw-input-acts{display:flex;gap:6px;flex-shrink:0;align-items:center;}
.kw-ia{width:34px;height:34px;border-radius:8px;border:0.5px solid var(--border);background:var(--bg);display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:13px;color:var(--muted);}
.kw-ia:hover{border-color:#534AB7;color:#534AB7;}
.kw-ia.send{background:#534AB7;border-color:#534AB7;color:#fff;}
.kw-ia.send:hover{background:#6358cc;border-color:#6358cc;}
.kw-mode-sel{font-size:10px;padding:5px 10px;border-radius:6px;border:0.5px solid rgba(83,74,183,.3);background:rgba(83,74,183,.07);color:#534AB7;cursor:pointer;}
/* ═══ Kira Nachrichten ═══ */
.msg{margin-bottom:16px;max-width:90%;}
.msg.kira{margin-right:auto;}
.msg.user{margin-left:auto;}
.msg-head{display:flex;align-items:center;gap:6px;margin-bottom:4px;}
.msg-name{font-size:11px;font-weight:500;color:#534AB7;}
.msg-name.u{color:var(--text);}
.msg-time{font-size:10px;color:var(--muted);}
.msg-bubble{font-size:13px;line-height:1.6;color:var(--text);padding:14px 18px;border-radius:10px;}
.msg.kira .msg-bubble{background:var(--bg-raised);border:0.5px solid var(--border);border-bottom-left-radius:4px;}
.msg.user .msg-bubble{background:rgba(83,74,183,.1);border:0.5px solid rgba(83,74,183,.25);border-bottom-right-radius:4px;}
.msg.error .msg-bubble{background:rgba(220,74,74,.07);color:#c05050;border:0.5px solid rgba(220,74,74,.18);}
.msg.system .msg-bubble{background:rgba(83,74,183,.07);color:#534AB7;text-align:center;font-size:12px;}
.msg-bubble strong{color:#534AB7;}
.msg-bubble code{background:rgba(128,128,128,.1);padding:1px 4px;border-radius:3px;font-size:12px;}
.kira-tools-used{margin-top:8px;display:flex;gap:4px;flex-wrap:wrap;}
.kira-tool-badge{font-size:10px;padding:1px 6px;border-radius:4px;background:rgba(83,74,183,.1);color:#534AB7;border:0.5px solid rgba(83,74,183,.2);}
/* Legacy kira-msg compat */
.kira-card{background:var(--bg);border:0.5px solid var(--border);border-radius:8px;padding:10px 12px;margin-bottom:6px;cursor:default;}
.kira-card.clickable{cursor:pointer;}
.kira-card.clickable:hover{border-color:#534AB7;}
.kira-task-card{cursor:pointer;transition:all .2s;}
.kira-task-card:hover{border-color:#534AB7;transform:translateX(-2px);}
.kira-prio-high{border-left:3px solid var(--danger);}
.kira-prio-med{border-left:3px solid var(--warn);}
.kira-prio-low{border-left:3px solid rgba(128,128,128,.3);}
.kira-card-title{font-size:var(--fs-base);font-weight:500;margin-bottom:3px;}
.kira-card-meta{font-size:var(--fs-sm);color:var(--muted);}
.kira-close{background:none;border:none;color:var(--muted);font-size:20px;cursor:pointer;padding:2px 6px;border-radius:4px;}
.kira-close:hover{color:var(--text);background:rgba(128,128,128,.1);}
.kira-typing{display:flex;gap:4px;padding:14px 24px;align-items:center;}
.kira-typing span{width:7px;height:7px;border-radius:50%;background:#534AB7;opacity:.35;animation:kiraTypingDot 1.4s infinite ease-in-out;}
.kira-typing span:nth-child(2){animation-delay:.2s;}
.kira-typing span:nth-child(3){animation-delay:.4s;}
@keyframes kiraTypingDot{0%,80%,100%{opacity:.3;transform:scale(.8)}40%{opacity:1;transform:scale(1.1)}}
@keyframes kiraFadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.kira-welcome{text-align:center;padding:48px 24px;}
.kira-welcome-icon{width:52px;height:52px;background:#534AB7;border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 16px;font-size:20px;font-weight:500;color:#fff;box-shadow:0 4px 20px rgba(83,74,183,.25);}
.kira-welcome-text{color:var(--muted);font-size:13px;line-height:1.7;}
#kc-aufgaben,#kc-muster,#kc-kwissen,#kc-historie{overflow-y:auto;padding:13px 16px;flex:1;}

/* Kommunikationsfenster */
.komm-block{background:rgba(128,128,128,.04);border:1px solid var(--border);border-radius:var(--radius);padding:11px;margin-bottom:9px;}
.komm-lbl{font-size:10px;font-weight:800;color:var(--accent);letter-spacing:.6px;text-transform:uppercase;margin-bottom:5px;opacity:.8;}
.komm-txt{font-size:var(--fs-sm);color:var(--text-secondary);line-height:1.6;}
.komm-txt ul{padding-left:16px;}
.komm-input{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);
  border-radius:var(--radius);padding:9px;font-size:var(--fs-base);line-height:1.6;min-height:72px;
  resize:vertical;font-family:inherit;}
.komm-input:focus{outline:none;border-color:var(--accent-border);}
.komm-result{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);
  padding:10px;font-size:var(--fs-sm);white-space:pre-wrap;line-height:1.7;
  max-height:240px;overflow-y:auto;color:var(--text-secondary);}
.komm-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;}
.btn-kp{background:var(--accent-bg);color:var(--accent);border:1px solid var(--accent-border);
  padding:7px 13px;border-radius:var(--radius);font-size:var(--fs-sm);font-weight:700;cursor:pointer;transition:all .15s;border-style:solid;}
.btn-kp:hover{opacity:.85;}
.btn-ks{background:rgba(128,128,128,.06);color:var(--muted);border:1px solid var(--border);
  padding:6px 11px;border-radius:var(--radius);font-size:var(--fs-sm);font-weight:600;cursor:pointer;text-decoration:none;display:inline-block;}
.btn-ks:hover{color:var(--text);background:rgba(128,128,128,.12);}

/* ═══ Modals ═══ */
.modal-ov{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:400;align-items:center;justify-content:center;padding:20px;}
[data-theme="light"] .modal-ov{background:rgba(0,0,0,.4);}
.modal-ov.open{display:flex;}
.modal{background:var(--bg-raised);border:1px solid var(--border-strong);border-radius:var(--radius-lg);padding:20px;width:100%;max-width:460px;
  box-shadow:0 8px 40px rgba(0,0,0,.3);}
.modal h3{color:var(--accent);font-size:var(--fs-md);margin-bottom:12px;}
.modal select,.modal textarea,.modal input[type=text]{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);
  border-radius:var(--radius);padding:8px;font-size:var(--fs-base);font-family:inherit;margin-bottom:9px;}
.modal textarea{min-height:70px;resize:vertical;}
.modal-actions{display:flex;gap:7px;margin-top:4px;}

.empty{color:var(--muted);font-size:var(--fs-base);padding:7px 0;}
footer{color:var(--muted);font-size:var(--fs-sm);text-align:center;padding:13px;border-top:1px solid var(--border);}

/* ═══ Responsive ═══ */
@media(max-width:768px){
  .sidebar{transform:translateX(-100%);position:fixed;z-index:150;}
  .sidebar.mobile-open{transform:translateX(0);}
  .main-area{margin-left:0!important;}
  .header{padding:12px 16px;}
  .panel{padding:16px 14px 80px;}
  .mobile-burger{display:flex!important;}
}
.mobile-burger{display:none;align-items:center;justify-content:center;width:36px;height:36px;
  border:1px solid var(--border);border-radius:var(--radius);cursor:pointer;background:transparent;color:var(--text);font-size:18px;}
.mobile-burger:hover{background:rgba(128,128,128,.08);}
.sidebar-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:140;}
.sidebar-overlay.active{display:block;}
"""


# ── HTTP Handler ──────────────────────────────────────────────────────────────
class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def do_GET(self):
        if self.path == '/favicon.ico':
            # Minimal valid 1x1 32bpp transparent ICO (70 bytes)
            ico = bytes.fromhex(
                '000001000100'          # ICONDIR: reserved=0, type=1, count=1
                '01010000010020003000000016000000'  # ICONDIRENTRY: 1x1, 0c, 1p, 32bpp, size=48, off=22
                # BITMAPINFOHEADER (40 bytes):
                '28000000'              # biSize=40
                '01000000'              # biWidth=1
                '02000000'              # biHeight=2 (ICO doubles height)
                '0100'                  # biPlanes=1
                '2000'                  # biBitCount=32
                '00000000'              # biCompression=BI_RGB
                '00000000'              # biSizeImage=0
                '00000000'              # biXPelsPerMeter=0
                '00000000'              # biYPelsPerMeter=0
                '00000000'              # biClrUsed=0
                '00000000'              # biClrImportant=0
                '00000000'              # XOR pixel: BGRA fully transparent
                '00000000'              # AND mask: DWORD-padded
            )
            self._respond(200, 'image/x-icon', ico)

        elif self.path in ('/', '/dashboard', '/index.html'):
            html = generate_html()
            self._html(html)

        elif self.path == '/partner':
            pv_path = SCRIPTS_DIR.parent / 'partner_view.html'
            try:
                html = pv_path.read_text('utf-8')
                self._html(html)
            except FileNotFoundError:
                self.send_error(404, 'partner_view.html nicht gefunden')

        elif self.path == '/api/tasks/open':
            db = get_db()
            rows = db.execute("SELECT * FROM tasks WHERE status='offen' ORDER BY prioritaet DESC, datum_mail DESC").fetchall()
            db.close()
            self._json([{k:v for k,v in dict(r).items() if k in
                ('id','typ','kategorie','titel','kunden_email','prioritaet','datum_mail','zusammenfassung','absender_rolle')}
                for r in rows])

        elif self.path == '/api/tasks/closed':
            db = get_db()
            rows = db.execute("""SELECT * FROM tasks WHERE status IN ('erledigt','ignorieren')
                ORDER BY aktualisiert_am DESC LIMIT 50""").fetchall()
            db.close()
            self._json([dict(r) for r in rows])

        elif self.path == '/api/corrections':
            db = get_db()
            try:
                rows = db.execute("SELECT * FROM corrections ORDER BY erstellt_am DESC LIMIT 50").fetchall()
                self._json([dict(r) for r in rows])
            except:
                self._json([])
            finally:
                db.close()

        elif self.path.startswith('/api/loeschhistorie'):
            db = get_db()
            try:
                rows = db.execute("""
                    SELECT id, geloescht_am, task_id, konto, absender, betreff,
                           datum_mail, anhaenge_info, grund, referenz_task_id, referenz_konto
                    FROM loeschhistorie
                    ORDER BY geloescht_am DESC LIMIT 100
                """).fetchall()
                self._json([dict(r) for r in rows])
            except:
                self._json([])
            finally:
                db.close()

        elif self.path == '/api/geschaeft':
            db = get_db()
            try:
                rows = db.execute("SELECT * FROM geschaeft ORDER BY datum DESC LIMIT 100").fetchall()
                self._json([dict(r) for r in rows])
            except:
                self._json([])
            finally:
                db.close()

        elif self.path == '/api/organisation':
            db = get_db()
            try:
                rows = db.execute("SELECT * FROM organisation ORDER BY datum_erkannt DESC").fetchall()
                self._json([dict(r) for r in rows])
            except:
                self._json([])
            finally:
                db.close()

        elif self.path == '/api/wissen':
            db = get_db()
            try:
                rows = db.execute("SELECT * FROM wissen_regeln ORDER BY kategorie, id").fetchall()
                self._json([dict(r) for r in rows])
            except:
                self._json([])
            finally:
                db.close()

        elif self.path.startswith('/api/file?'):
            self._serve_file()

        elif self.path.startswith('/api/attachments?'):
            self._list_attachments()

        elif self.path.startswith('/api/mail/read?'):
            self._read_mail()

        elif self.path.startswith('/api/mail/kira-kontext?'):
            self._api_mail_kira_kontext()

        elif self.path == '/api/mail/folders':
            self._api_mail_folders()

        elif self.path == '/api/mail/konten':
            self._api_mail_konten()

        elif self.path.startswith('/api/mail/oauth/status'):
            self._api_mail_oauth_status()

        elif self.path.startswith('/api/mail/favorites'):
            self._api_mail_favorites_get()

        elif self.path == '/api/mail/snooze/count':
            self._api_mail_snooze_count()

        elif self.path.startswith('/api/mail/combined/konten'):
            self._api_mail_combined_konten_get()

        elif self.path.startswith('/api/mail/combined'):
            self._api_mail_combined()

        elif self.path.startswith('/api/mail/list'):
            self._api_mail_list()

        elif self.path.startswith('/api/mail/thread'):
            self._api_mail_thread()

        elif self.path.startswith('/api/mail/mark-read'):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            msg_id = qs.get('message_id', [''])[0]
            if msg_id:
                try:
                    conn = sqlite3.connect(str(MAIL_INDEX_DB))
                    conn.execute("UPDATE mails SET gelesen=1 WHERE message_id=?", (msg_id,))
                    conn.commit()
                    conn.close()
                    self._json({'ok': True})
                except Exception as e:
                    self._json({'ok': False, 'error': str(e)})
            else:
                self._json({'ok': False, 'error': 'missing message_id'})

        elif self.path == '/api/mail/archiv/status':
            self._api_mail_archiv_status()

        elif self.path == '/api/mail/archiv/reindex/progress':
            self._api_mail_archiv_reindex_progress()

        elif self.path.startswith('/api/ausgangsrechnungen'):
            self._api_ausgangsrechnungen()

        elif self.path.startswith('/api/angebote'):
            self._api_angebote()

        elif self.path == '/api/kira/insights':
            self._api_kira_insights()

        elif self.path.startswith('/api/kira/aktivitaeten'):
            self._api_kira_aktivitaeten()

        elif self.path == '/api/kira/proaktiv/status':
            self._api_kira_proaktiv_status()

        elif self.path == '/api/monitor/status':
            self._json(get_monitor_status())

        elif self.path.startswith('/api/aktivitaeten'):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            limit   = int(qs.get('limit',  ['200'])[0])
            offset  = int(qs.get('offset', ['0'])[0])
            bereich = qs.get('bereich', [''])[0]
            status  = qs.get('status',  [''])[0]
            entries = alog_entries(min(limit,500), offset, bereich or None, status or None)
            stats   = alog_stats()
            self._json({'entries': entries, 'stats': stats})

        elif self.path.startswith('/api/runtime/events'):
            qs          = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            limit       = min(int(qs.get('limit',  ['50'])[0]),  500)
            offset      = int(qs.get('offset', ['0'])[0])
            event_type  = qs.get('event_type', [''])[0]
            modul       = qs.get('modul',      [''])[0]
            status      = qs.get('status',     [''])[0]
            action      = qs.get('action',     [''])[0]
            search      = qs.get('search',     [''])[0]
            session_id  = qs.get('session_id', [''])[0]
            try:
                data = rlog_get(limit=limit, offset=offset,
                                event_type=event_type or None, modul=modul or None,
                                status=status or None, action=action or None,
                                search=search or None, session_id=session_id or None)
            except Exception as ex:
                data = {'entries': [], 'total': 0, '_err': str(ex)}
            self._json(data)

        elif self.path == '/api/runtime/stats':
            try:
                self._json(rlog_stats())
            except Exception as ex:
                self._json({'error': str(ex)})

        elif self.path.startswith('/api/runtime/event/') and self.path.endswith('/payload'):
            eid = self.path[len('/api/runtime/event/'):-len('/payload')]
            try:
                self._json(rlog_payload(eid))
            except Exception as ex:
                self._json({'error': str(ex)})

        elif self.path.startswith('/api/changelog'):
            qs       = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            limit    = min(int(qs.get('limit',  ['50'])[0]), 1000)
            offset   = int(qs.get('offset', ['0'])[0])
            modul    = qs.get('modul',      [''])[0]
            feature  = qs.get('feature_id', [''])[0]
            result_f = qs.get('result',     [''])[0]
            action_f = qs.get('action',     [''])[0]
            search   = qs.get('search',     [''])[0]
            try:
                from change_log import get_entries as _cl_get, get_stats as _cl_stats
                data  = _cl_get(limit=limit, offset=offset, modul=modul,
                                feature_id=feature, result=result_f,
                                action=action_f, search=search)
                stats = _cl_stats()
                data['stats'] = stats
            except Exception as ex:
                data = {'entries': [], 'total': 0, 'total_raw': 0, 'stats': {}, '_err': str(ex)}
            self._json(data)

        elif self.path == '/api/server/version':
            import hashlib
            try:
                h = hashlib.md5(Path(__file__).read_bytes()).hexdigest()[:8]
            except Exception:
                h = 'unknown'
            self._json({'version': h, 'ts': datetime.now().isoformat()})

        elif self.path == '/api/kira/briefing':
            try:
                briefing = generate_daily_briefing()
                self._json(briefing)
            except Exception as e:
                self._json({"error": str(e)})

        elif self.path == '/api/kira/briefing/regenerate':
            try:
                import sqlite3 as _sq
                _db = _sq.connect(str(TASKS_DB))
                from datetime import date as _d
                _db.execute("DELETE FROM kira_briefings WHERE datum=?", (_d.today().isoformat(),))
                _db.commit()
                _db.close()
                briefing = generate_daily_briefing()
                self._json(briefing)
            except Exception as e:
                self._json({"error": str(e)})

        elif self.path == '/api/mail/approve/pending':
            self._api_mail_approve_pending()

        elif self.path.startswith('/api/kira/task/') and self.path.endswith('/status'):
            # GET /api/kira/task/{id}/status (Paket 5, session-oo)
            parts = self.path.split('/')
            task_id = parts[4] if len(parts) >= 5 else ''
            self._json(get_react_task_status(task_id) if task_id else {'error': 'Keine Task-ID'})

        elif self.path == '/api/kira/conversations':
            self._json(kira_get_conversations())

        elif self.path.startswith('/api/kira/conversation?'):
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            sid = params.get('session_id', [''])[0]
            self._json(kira_get_messages(sid) if sid else [])

        elif self.path.startswith('/api/webhook/whatsapp'):
            self._handle_whatsapp_verify()

        elif self.path == '/api/einstellungen':
            self._api_einstellungen_get()

        elif self.path.startswith('/api/mail/konten/stats'):
            self._api_mail_konto_stats()

        elif self.path.startswith('/api/mail/konten/ordner'):
            self._api_mail_konto_ordner()

        elif self.path.startswith('/api/mail/archiv/pruefen'):
            self._api_mail_archiv_pruefen()

        elif self.path.startswith('/api/mail/provider-detect'):
            self._api_mail_provider_detect()

        elif self.path.startswith('/api/mail/konto/oauth-status'):
            self._api_mail_konto_oauth_status()

        elif self.path.startswith('/api/mail/konto/volltest-status'):
            self._api_mail_konto_volltest_status()

        elif self.path.startswith('/api/mail/nachklassifizieren/status'):
            self._api_mail_nachklassifizieren_status()

        elif self.path.startswith('/api/mail/konto/health'):
            self._api_mail_konto_health()

        elif self.path.startswith('/api/mail/protokoll'):
            self._api_mail_protokoll()

        elif self.path == '/api/mail/signaturen':
            self._api_mail_signaturen_get()

        elif self.path.startswith('/api/browse/result'):
            self._api_browse_result()

        elif self.path == '/api/browse/folder':
            self._api_browse_folder()

        # ── Presence-API (Paket 9, session-nn) ───────────────────────────────
        elif self.path == '/api/presence':
            try:
                from presence_detector import get_idle_seconds, is_user_present
                idle = get_idle_seconds()
                self._json({"ok": True, "idle_seconds": idle, "present": is_user_present()})
            except Exception as e:
                self._json({"ok": False, "error": str(e)})

        # ── Vorgang-API (Paket 6, session-nn) ────────────────────────────────
        elif self.path == '/api/vorgaenge' or self.path.startswith('/api/vorgaenge?'):
            self._api_vorgaenge_list()

        elif self.path == '/api/vorgang/signals' or self.path.startswith('/api/vorgang/signals?'):
            self._api_vorgang_signals()

        elif self.path.startswith('/api/vorgang/kunde/'):
            self._api_vorgang_kunde()

        elif re.match(r'^/api/vorgang/\d+$', self.path):
            self._api_vorgang_detail()

        else:
            self._respond(404, 'text/plain', b'Not found')

    def _handle_whatsapp_verify(self):
        """GET /api/webhook/whatsapp — Meta Hub-Verifizierung für WhatsApp Business Cloud API."""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        mode      = qs.get('hub.mode', [''])[0]
        token     = qs.get('hub.verify_token', [''])[0]
        challenge = qs.get('hub.challenge', [''])[0]
        try:
            secrets = json.loads((SCRIPTS_DIR / "secrets.json").read_text('utf-8'))
            verify_token = secrets.get("whatsapp_verify_token", "")
        except Exception:
            verify_token = ""
        if mode == 'subscribe' and verify_token and token == verify_token:
            self._respond(200, 'text/plain', challenge.encode())
        else:
            self._respond(403, 'text/plain', b'Forbidden')

    def _api_kira_insights(self):
        """GET /api/kira/insights — Muster-Analyse aus allen gesammelten Daten."""
        db = get_db()
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            today_dt = datetime.now()
            insights = {"aufgaben": [], "muster": {}, "lernen": []}

            # 1. DRINGENDE AUFGABEN sammeln
            # Offene Ausgangsrechnungen > 30 Tage
            try:
                for r in db.execute("SELECT id, re_nummer, kunde_name, datum, betrag_brutto FROM ausgangsrechnungen WHERE status='offen'"):
                    try:
                        d = datetime.strptime(str(r['datum'])[:10], "%Y-%m-%d")
                        tage = (today_dt - d).days
                        if tage > 14:
                            insights["aufgaben"].append({
                                "typ": "rechnung_offen", "prio": 2 if tage > 30 else 1,
                                "text": f"Rechnung {r['re_nummer']} ({r['kunde_name'] or 'Unbekannt'}) seit {tage} Tagen offen — {r['betrag_brutto'] or 0:,.2f} EUR",
                                "action": f"showGeschTab('ausgangsre')"
                            })
                    except: pass
            except: pass

            # Nachfass fällig
            try:
                for r in db.execute("SELECT id, a_nummer, kunde_name, naechster_nachfass FROM angebote WHERE status='offen' AND naechster_nachfass IS NOT NULL AND naechster_nachfass <= ?", (today,)):
                    insights["aufgaben"].append({
                        "typ": "nachfass_faellig", "prio": 2,
                        "text": f"Nachfass fällig: {r['a_nummer']} ({r['kunde_name'] or 'Unbekannt'})",
                        "action": f"showGeschTab('angebote')"
                    })
            except: pass

            # Offene Eingangsrechnungen
            try:
                n_eingang = db.execute("SELECT COUNT(*) FROM geschaeft WHERE wichtigkeit='aktiv' AND (bewertung IS NULL OR bewertung!='erledigt')").fetchone()[0]
                if n_eingang > 0:
                    insights["aufgaben"].append({
                        "typ": "eingang_offen", "prio": 1,
                        "text": f"{n_eingang} offene Eingangsrechnungen zu bearbeiten",
                        "action": "showGeschTab('eingangsre')"
                    })
            except: pass

            # Skonto-Fristen
            try:
                ddb = sqlite3.connect(str(DETAIL_DB))
                ddb.row_factory = sqlite3.Row
                for r in ddb.execute("SELECT re_nummer, skonto_datum, skonto_prozent, skonto_betrag FROM rechnungen_detail WHERE skonto_datum >= ? AND skonto_datum IS NOT NULL", (today,)):
                    try:
                        tage_rest = (datetime.strptime(r['skonto_datum'], "%Y-%m-%d").date() - today_dt.date()).days
                        if tage_rest >= 0 and tage_rest <= 3:
                            insights["aufgaben"].append({
                                "typ": "skonto_dringend", "prio": 3,
                                "text": f"Skonto {r['skonto_prozent']}% für {r['re_nummer']} läuft in {tage_rest} Tagen ab! Ersparnis: {r['skonto_betrag'] or 0:,.2f} EUR",
                                "action": "showGeschTab('ausgangsre')"
                            })
                    except: pass
                ddb.close()
            except: pass

            # Antworten nötig
            try:
                n_antwort = db.execute("SELECT COUNT(*) FROM tasks WHERE kategorie='Antwort erforderlich'").fetchone()[0]
                if n_antwort > 0:
                    insights["aufgaben"].append({
                        "typ": "antwort_noetig", "prio": 2,
                        "text": f"{n_antwort} Anfragen warten auf deine Antwort",
                        "action": "filterKomm('Antwort erforderlich')"
                    })
            except: pass

            # 2. MUSTER aus geschaeft_statistik
            try:
                stats = db.execute("SELECT * FROM geschaeft_statistik ORDER BY erstellt_am DESC").fetchall()
                zahlungsdauern = []
                ablehngruende = {}
                annahmegruende = {}
                for s in stats:
                    try:
                        daten = json.loads(s['daten_json']) if s['daten_json'] else {}
                    except: daten = {}
                    if s['ereignis'] == 'status_bezahlt' and daten.get('zahlungsdauer_tage'):
                        zahlungsdauern.append(daten['zahlungsdauer_tage'])
                    if s['ereignis'] == 'status_abgelehnt':
                        g = daten.get('grund', 'Unbekannt') or 'Unbekannt'
                        ablehngruende[g] = ablehngruende.get(g, 0) + 1
                    if s['ereignis'] == 'status_angenommen':
                        g = daten.get('wie', 'Unbekannt') or 'Unbekannt'
                        annahmegruende[g] = annahmegruende.get(g, 0) + 1

                if zahlungsdauern:
                    avg = sum(zahlungsdauern) / len(zahlungsdauern)
                    insights["muster"]["zahlungsdauer_avg"] = round(avg, 1)
                    insights["muster"]["zahlungsdauer_min"] = min(zahlungsdauern)
                    insights["muster"]["zahlungsdauer_max"] = max(zahlungsdauern)
                    insights["muster"]["zahlungsdauer_n"] = len(zahlungsdauern)
                if ablehngruende:
                    insights["muster"]["ablehngruende"] = dict(sorted(ablehngruende.items(), key=lambda x: -x[1]))
                if annahmegruende:
                    insights["muster"]["annahmegruende"] = dict(sorted(annahmegruende.items(), key=lambda x: -x[1]))

                # Angebotsquote
                try:
                    ang_total = db.execute("SELECT COUNT(*) FROM angebote").fetchone()[0]
                    ang_angen = db.execute("SELECT COUNT(*) FROM angebote WHERE status='angenommen'").fetchone()[0]
                    ang_abgel = db.execute("SELECT COUNT(*) FROM angebote WHERE status='abgelehnt'").fetchone()[0]
                    if ang_total >= 3:
                        insights["muster"]["angebotsquote"] = round(ang_angen / ang_total * 100, 1)
                    insights["muster"]["angebote_total"] = ang_total
                    insights["muster"]["angebote_angenommen"] = ang_angen
                    insights["muster"]["angebote_abgelehnt"] = ang_abgel
                except: pass

            except: pass

            # 3. LETZTE ERKENNTNISSE aus wissen_regeln
            try:
                for r in db.execute("SELECT id, titel, inhalt, erstellt_am FROM wissen_regeln WHERE kategorie='gelernt' ORDER BY id DESC LIMIT 10"):
                    insights["lernen"].append({"titel": r['titel'], "inhalt": r['inhalt'], "datum": r['erstellt_am']})
            except: pass

            # Aufgaben nach Priorität sortieren
            insights["aufgaben"].sort(key=lambda x: -x.get("prio", 0))

            self._json(insights)
        except Exception as e:
            self._json({"error": str(e)})
        finally:
            db.close()

    def _is_safe_path(self, path_str):
        """Sicherheitscheck: Pfad muss in erlaubtem Root liegen."""
        try:
            resolved = Path(path_str).resolve()
            return any(str(resolved).startswith(r) for r in ALLOWED_ROOTS) or str(resolved).startswith(str(ARCHIV_ROOT))
        except:
            return False

    def _serve_file(self):
        """GET /api/file?path=... — Serviert Dateien über HTTP."""
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        file_path = params.get('path',[''])[0]
        if not file_path:
            self._respond(400, 'text/plain', b'Missing path')
            return
        fp = Path(file_path)
        if not fp.exists() or not fp.is_file():
            self._respond(404, 'text/plain', b'File not found')
            return
        if not self._is_safe_path(file_path):
            self._respond(403, 'text/plain', b'Access denied')
            return
        mime = mimetypes.guess_type(str(fp))[0] or 'application/octet-stream'
        try:
            data = fp.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            disp = 'inline' if mime.startswith(('image/','application/pdf','text/')) else 'attachment'
            self.send_header('Content-Disposition', f'{disp}; filename="{fp.name}"')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self._respond(500, 'text/plain', str(e).encode())

    def _list_attachments(self):
        """GET /api/attachments?path=... — Listet Dateien in einem Ordner."""
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        dir_path = params.get('path',[''])[0]
        if not dir_path:
            self._json([])
            return
        dp = Path(dir_path)
        if not dp.exists() or not dp.is_dir():
            # Vielleicht ist es ein File-Pfad, versuche parent/attachments
            parent_att = dp.parent / "attachments" if dp.is_file() else dp
            if not parent_att.exists():
                # Versuche den mail_folder_pfad + attachments
                att_dir = dp / "attachments"
                if att_dir.exists():
                    dp = att_dir
                else:
                    self._json([])
                    return
            else:
                dp = parent_att
        files = []
        for f in sorted(dp.iterdir()):
            if f.is_file():
                mime = mimetypes.guess_type(str(f))[0] or 'application/octet-stream'
                ftype = 'pdf' if mime == 'application/pdf' else mime.split('/')[0] if '/' in mime else 'file'
                files.append({
                    "name": f.name,
                    "url": urllib.parse.quote(str(f), safe=''),
                    "type": ftype,
                    "size": f.stat().st_size
                })
        self._json(files)

    @staticmethod
    def _parse_eml_content(eml_path):
        """Parst EML-Datei, liefert (text_plain, html_sanitized).
        html_sanitized ist HTML mit entfernten Scripts/Formularen für sichere Browser-Anzeige.
        KIRA soll weiterhin text_plain aus mail_index.db nutzen."""
        import email as _email
        from email import policy as _ep
        import re as _re
        text, html = '', ''
        try:
            with open(str(eml_path), 'rb') as f:
                raw = f.read()
            msg = _email.message_from_bytes(raw, policy=_ep.compat32)
            if msg.is_multipart():
                for part in msg.walk():
                    ct  = part.get_content_type()
                    cd  = str(part.get('Content-Disposition', ''))
                    if 'attachment' in cd.lower():
                        continue
                    if ct == 'text/plain' and not text:
                        try:
                            charset = part.get_content_charset('utf-8') or 'utf-8'
                            payload = part.get_payload(decode=True)
                            if payload:
                                text = payload.decode(charset, errors='replace')
                        except: pass
                    elif ct == 'text/html' and not html:
                        try:
                            charset = part.get_content_charset('utf-8') or 'utf-8'
                            payload = part.get_payload(decode=True)
                            if payload:
                                html = payload.decode(charset, errors='replace')
                        except: pass
            else:
                ct = msg.get_content_type()
                charset = msg.get_content_charset('utf-8') or 'utf-8'
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        content = payload.decode(charset, errors='replace')
                        if ct == 'text/html':
                            html = content
                        else:
                            text = content
                except: pass
        except Exception:
            pass
        # HTML sanitieren — Scripts, Forms, iframes entfernen
        if html:
            for tag in ['script','style','form','iframe','object','embed','meta','base','link']:
                html = _re.sub(rf'<{tag}[^>]*>.*?</{tag}>', '', html, flags=_re.DOTALL|_re.IGNORECASE)
                html = _re.sub(rf'<{tag}[^>]*/>', '', html, flags=_re.IGNORECASE)
            html = _re.sub(r'\son\w+\s*=\s*["\'][^"\']*["\']', '', html, flags=_re.IGNORECASE)
            html = _re.sub(r'\son\w+\s*=\s*[^\s>]+', '', html, flags=_re.IGNORECASE)
            html = _re.sub(r'(href|src)\s*=\s*["\']javascript:[^"\']*["\']', 'href="#"', html, flags=_re.IGNORECASE)
        return text, html

    def _read_mail(self):
        """GET /api/mail/read — EML ist primäre Quelle (beste Formatierung für Anzeige).
        KIRA nutzt weiterhin text_plain aus mail_index.db."""
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        msg_id = params.get('message_id',[''])[0]
        if not msg_id:
            self._json({"error": "Missing message_id"})
            return
        result = {"betreff":"","absender":"","an":"","datum":"","text":"","html":"","anhaenge":[]}

        # ── 1. Primär: mail_index.db → EML → beste Qualität ──────────────────
        mail_folder = ''
        eml_path_str = ''
        try:
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT betreff,absender,an,datum,text_plain,mail_folder_pfad,eml_path,anhaenge,anhaenge_pfad "
                "FROM mails WHERE message_id=?", (msg_id,)
            ).fetchone()
            if row:
                result["betreff"]  = row["betreff"]  or ""
                result["absender"] = row["absender"] or ""
                result["an"]       = row["an"]       or ""
                result["datum"]    = (row["datum"]   or "")[:16]
                mail_folder     = row["mail_folder_pfad"] or ""
                eml_path_str    = row["eml_path"]    or ""
                # Fallback-Text aus DB (für schnelle Anzeige und KIRA-Kontext)
                result["text"]  = row["text_plain"]  or ""

                # EML lesen — beste Qualität, Original-Formatierung
                eml_to_try = []
                if eml_path_str and Path(eml_path_str).exists():
                    eml_to_try.append(Path(eml_path_str))
                if mail_folder:
                    candidate = Path(mail_folder) / "mail.eml"
                    if candidate.exists():
                        eml_to_try.append(candidate)

                for ep in eml_to_try:
                    t, h = self._parse_eml_content(ep)
                    if h:
                        result["html"] = h
                        if not result["text"] and t:
                            result["text"] = t
                        break
                    elif t:
                        result["text"] = t
                        break

                # Anhänge aus DB-JSON-Liste oder Dateisystem
                att_dir = None
                anh_pfad = row["anhaenge_pfad"] or ""
                if anh_pfad and Path(anh_pfad).is_dir():
                    att_dir = Path(anh_pfad)
                elif mail_folder:
                    att_check = Path(mail_folder) / "attachments"
                    if att_check.exists():
                        att_dir = att_check
                if att_dir:
                    for f in sorted(att_dir.iterdir()):
                        if f.is_file() and not f.name.startswith('.'):
                            mime = mimetypes.guess_type(str(f))[0] or ''
                            ftype = 'PDF' if 'pdf' in mime else 'Bild' if mime.startswith('image') else 'Datei'
                            result["anhaenge"].append({"name": f.name, "pfad": str(f), "typ": ftype})
            conn.close()
        except Exception:
            pass

        # ── 2. Fallback: kunden.db interaktionen ──────────────────────────────
        if not result["text"] and not result["html"]:
            try:
                kdb = sqlite3.connect(str(KUNDEN_DB))
                kdb.row_factory = sqlite3.Row
                krow = kdb.execute("SELECT * FROM interaktionen WHERE message_id=?", (msg_id,)).fetchone()
                if krow:
                    if not result["betreff"]:
                        result["betreff"] = krow["betreff"] or ""
                        result["absender"] = krow["absender"] or ""
                        result["datum"]    = krow["datum"] or ""
                    kfolder = krow["mail_folder_pfad"] or ""
                    result["text"] = krow["text_plain"] or ""
                    if kfolder and not result["html"]:
                        for ep in [Path(kfolder)/"mail.eml"]:
                            if ep.exists():
                                t, h = self._parse_eml_content(ep)
                                if h: result["html"] = h
                                elif t and len(t) > len(result["text"]): result["text"] = t
                                break
                        if not result["text"]:
                            mj = Path(kfolder) / "mail.json"
                            if mj.exists():
                                try:
                                    import re as _re2
                                    md = json.loads(mj.read_text('utf-8'))
                                    plain = md.get("text","")
                                    if plain:
                                        clean = _re2.sub(r'<[^>]+>',' ',plain)
                                        clean = _re2.sub(r'\s+',' ',clean).strip()
                                        result["text"] = clean
                                except: pass
                kdb.close()
            except: pass

        self._json(result)

    def _api_mail_kira_kontext(self):
        """GET /api/mail/kira-kontext?message_id=X
        Liefert vollständigen Mail-Text + Sender-Verlauf (letzte 5) + offene Tasks des Absenders.
        Kira bekommt damit sofort vollständigen Kundenverlauf ohne manuelles Nachsuchen."""
        _ensure_mail_columns()
        qs     = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        msg_id = params.get('message_id', [''])[0]
        if not msg_id:
            self._json({"error": "Missing message_id"})
            return

        result = {
            "betreff": "", "absender": "", "datum": "", "an": "",
            "text": "", "anhaenge": [],
            "sender_verlauf": [],   # letzte 5 Mails desselben Absenders
            "offene_tasks": [],     # passende offene Tasks
        }

        # ── 1. Primär-Mail aus mail_index.db + EML ─────────────────────────
        absender_email = ""
        try:
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT betreff,absender,an,datum,text_plain,mail_folder_pfad,eml_path "
                "FROM mails WHERE message_id=?", (msg_id,)
            ).fetchone()
            if row:
                result["betreff"]  = row["betreff"]  or ""
                result["absender"] = row["absender"] or ""
                result["an"]       = row["an"]       or ""
                result["datum"]    = row["datum"]    or ""
                result["text"]     = row["text_plain"] or ""
                # EML als bessere Textquelle
                for eml_candidate in [row["eml_path"] or "", row["mail_folder_pfad"] or ""]:
                    if not eml_candidate: continue
                    ep = Path(eml_candidate) if eml_candidate.endswith('.eml') else Path(eml_candidate) / "mail.eml"
                    if ep.exists():
                        t, _ = self._parse_eml_content(ep)
                        if t and len(t) > len(result["text"]):
                            result["text"] = t
                        break
                # Absender-E-Mail extrahieren für Verlauf-Suche
                import re as _re3
                m_addr = _re3.search(r'[\w.+-]+@[\w.-]+', result["absender"])
                if m_addr:
                    absender_email = m_addr.group(0).lower()
            conn.close()
        except Exception:
            pass

        # ── 2. Sender-Verlauf: letzte 5 Mails desselben Absenders ──────────
        if absender_email:
            try:
                conn2 = sqlite3.connect(str(MAIL_INDEX_DB))
                conn2.row_factory = sqlite3.Row
                verlauf_rows = conn2.execute(
                    "SELECT betreff, datum, text_plain FROM mails "
                    "WHERE LOWER(absender) LIKE ? AND message_id != ? "
                    "ORDER BY datum DESC LIMIT 5",
                    (f"%{absender_email}%", msg_id)
                ).fetchall()
                for r in verlauf_rows:
                    snippet = (r["text_plain"] or "")[:120].replace('\n', ' ').strip()
                    result["sender_verlauf"].append({
                        "betreff": r["betreff"] or "",
                        "datum":   (r["datum"] or "")[:10],
                        "snippet": snippet,
                    })
                conn2.close()
            except Exception:
                pass

        # ── 3. Offene Tasks des Absenders (tasks.db) ────────────────────────
        if absender_email:
            try:
                domain = absender_email.split('@')[-1] if '@' in absender_email else ''
                db3 = get_db()
                task_rows = db3.execute(
                    "SELECT titel, kategorie, kunden_email, datum_mail FROM aufgaben "
                    "WHERE status='offen' AND ("
                    "  LOWER(kunden_email) LIKE ? OR LOWER(kunden_email) LIKE ? "
                    ") ORDER BY datum_mail DESC LIMIT 8",
                    (f"%{absender_email}%", f"%{domain}%")
                ).fetchall()
                for r in task_rows:
                    result["offene_tasks"].append({
                        "titel":    (r["titel"] or "")[:80],
                        "kategorie": r["kategorie"] or "",
                        "datum":    (r["datum_mail"] or "")[:10],
                    })
                db3.close()
            except Exception:
                pass

        self._json(result)

    # ── MAIL KONTEN / OAuth ────────────────────────────────────────────────

    def _api_mail_konten(self):
        """GET /api/mail/konten — Kontoliste aus raumkult_config.json + Token-Status."""
        import time as _time
        try:
            archiver_cfg = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\raumkult_config.json")
            token_dir    = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\tokens")
            konten_raw = []
            if archiver_cfg.exists():
                cfg = json.loads(archiver_cfg.read_text('utf-8'))
                konten_raw = cfg.get('konten', [])

            # Custom-Labels aus config.json laden
            konto_display_names = {}
            try:
                _lcfg = json.loads((SCRIPTS_DIR / 'config.json').read_text('utf-8'))
                konto_display_names = _lcfg.get('mail_konto_labels', {})
            except Exception:
                pass

            konten = []
            for k in konten_raw:
                email = k.get('email', '')
                safe  = email.replace('@', '_').replace('.', '_')
                token_file = token_dir / f"{safe}_token.json"
                status = 'missing'
                if token_file.exists():
                    try:
                        td = json.loads(token_file.read_text('utf-8'))
                        at = td.get('AccessToken', {})
                        if at:
                            exp = max(int(v.get('expires_on', 0)) for v in at.values())
                            status = 'ok' if exp > _time.time() else 'expired'
                        else:
                            status = 'expired'
                    except Exception:
                        status = 'expired'
                konten.append({
                    'email':       email,
                    'beschreibung': k.get('beschreibung', ''),
                    'aktiv':       k.get('aktiv', True),
                    'auth_methode': k.get('auth_methode', ''),
                    'token_status': status,
                    'display_name': konto_display_names.get(email, ''),
                })

            # Mail-Monitor-Status
            mon_aktiv   = False
            mon_last    = ''
            mon_intv    = 300
            try:
                cfg_data = json.loads((SCRIPTS_DIR / 'config.json').read_text('utf-8'))
                mm = cfg_data.get('mail_monitor', {})
                mon_aktiv = bool(mm.get('aktiv', False))
                mon_intv  = int(mm.get('intervall_sekunden', 300))
            except Exception:
                pass
            try:
                conn2 = sqlite3.connect(str(KNOWLEDGE_DIR / 'runtime_events.db'))
                row2  = conn2.execute(
                    "SELECT ts FROM events WHERE modul='mail_monitor' ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if row2:
                    mon_last = row2[0][:16]
                conn2.close()
            except Exception:
                pass

            std_konto = ''
            try:
                _cfg2 = json.loads((SCRIPTS_DIR / 'config.json').read_text('utf-8'))
                std_konto = _cfg2.get('mail_konten', {}).get('standard_konto', '')
            except Exception:
                pass
            self._json({'konten': konten, 'standard_konto': std_konto, 'monitor': {'aktiv': mon_aktiv, 'last_sync': mon_last, 'intervall': mon_intv}})
        except Exception as e:
            self._json({'konten': [], 'standard_konto': '', 'monitor': {}, 'error': str(e)})

    def _api_mail_oauth_connect(self, body):
        """POST /api/mail/oauth/connect — Startet interaktive OAuth2-Anmeldung im Browser."""
        import threading as _threading
        email = (body.get('email') or '').strip()
        if not email:
            self._json({'ok': False, 'error': 'email fehlt'})
            return

        archiver_cfg = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\raumkult_config.json")
        token_dir    = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\tokens")

        konto = None
        if archiver_cfg.exists():
            cfg = json.loads(archiver_cfg.read_text('utf-8'))
            for k in cfg.get('konten', []):
                if k.get('email', '').lower() == email.lower():
                    konto = k
                    break

        if not konto:
            self._json({'ok': False, 'error': f'Konto {email} nicht in Konfiguration gefunden'})
            return

        _MAIL_OAUTH_STATE[email] = {'status': 'connecting', 'message': 'Browser wird geöffnet...'}

        def _do_auth():
            try:
                import msal
                client_id  = konto.get('oauth2_client_id', '0c6f47fc-2daa-475f-a7b0-f1c03743dbae')
                tenant_id  = konto.get('oauth2_tenant_id', 'common') or 'common'
                scopes     = ['https://outlook.office.com/IMAP.AccessAsUser.All']
                safe       = email.replace('@', '_').replace('.', '_')
                cache_path = token_dir / f"{safe}_token.json"

                cache = msal.SerializableTokenCache()
                if cache_path.exists():
                    cache.deserialize(cache_path.read_text('utf-8'))

                app = msal.PublicClientApplication(
                    client_id=client_id,
                    authority=f"https://login.microsoftonline.com/{tenant_id}",
                    token_cache=cache,
                )

                # 1. Silent aus Cache
                accounts = app.get_accounts(username=email)
                result = None
                if accounts:
                    result = app.acquire_token_silent(scopes, account=accounts[0])

                # 2. Interaktiv (öffnet Browser-Fenster)
                if not result or 'access_token' not in result:
                    result = app.acquire_token_interactive(scopes, login_hint=email)

                if result and 'access_token' in result:
                    if cache.has_state_changed:
                        cache_path.write_text(cache.serialize(), encoding='utf-8')
                    _MAIL_OAUTH_STATE[email] = {'status': 'ok', 'message': 'Verbunden'}
                else:
                    err = result.get('error_description', result.get('error', 'Unbekannter Fehler')) if result else 'Keine Antwort'
                    _MAIL_OAUTH_STATE[email] = {'status': 'error', 'message': err}
            except Exception as exc:
                _MAIL_OAUTH_STATE[email] = {'status': 'error', 'message': str(exc)}

        t = _threading.Thread(target=_do_auth, daemon=True)
        t.start()
        self._json({'ok': True, 'status': 'connecting'})

    def _api_mail_oauth_status(self):
        """GET /api/mail/oauth/status?email=... — Prüft Fortschritt der OAuth2-Verbindung."""
        qs    = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        email = qs.get('email', [''])[0]
        state = _MAIL_OAUTH_STATE.get(email, {'status': 'unknown'})
        self._json(state)

    # ── Postfach API ──────────────────────────────────────────────────────────
    def _api_mail_folders(self):
        """GET /api/mail/folders — Liefert Konten + Ordner (Live-IMAP + Cache + DB-Fallback)."""
        import time as _time
        import imaplib as _imaplib
        _ensure_mail_columns()

        _FOLDER_ICONS = {
            'inbox': '&#x1F4EC;', 'posteingang': '&#x1F4EC;', 'eingang': '&#x1F4EC;',
            'gesendete': '&#x1F4E4;', 'gesendet': '&#x1F4E4;', 'sent': '&#x1F4E4;',
            'entwurf': '&#x1F4DD;', 'draft': '&#x1F4DD;',
            'gel': '&#x1F5D1;', 'deleted': '&#x1F5D1;', 'trash': '&#x1F5D1;', 'papierkorb': '&#x1F5D1;',
            'spam': '&#x26D4;', 'junk': '&#x26D4;',
            'archiv': '&#x1F4C1;', 'archive': '&#x1F4C1;',
        }
        _FOLDER_LABELS = {
            'gesendete elemente': 'Gesendet', 'gesendete objekte': 'Gesendet',
            'gesendete': 'Gesendet', 'sent items': 'Gesendet', 'sent': 'Gesendet',
            'inbox': 'Posteingang', 'posteingang': 'Posteingang',
            'entwürfe': 'Entwürfe', 'drafts': 'Entwürfe',
            'gelöschte elemente': 'Gelöscht', 'deleted messages': 'Gelöscht',
            'deleted items': 'Gelöscht', 'trash': 'Papierkorb', 'papierkorb': 'Papierkorb',
            'junk-e-mail': 'Spam', 'junk': 'Spam', 'spam': 'Spam',
            'archiv': 'Archiv', 'archive': 'Archiv',
        }

        def _fn_icon(fn):
            fl = fn.lower()
            return next((v for k, v in _FOLDER_ICONS.items() if k in fl), '&#x1F4C2;')

        def _fn_label(fn):
            fl = fn.lower()
            return next((v for k, v in _FOLDER_LABELS.items() if k == fl or k in fl), fn)

        def _decode_imap_utf7(name):
            """Dekodiert IMAP Modified UTF-7 (RFC 3501) → Unicode-String."""
            import base64 as _b64
            res = []
            i = 0
            while i < len(name):
                if name[i] == '&':
                    end = name.find('-', i + 1)
                    if end == -1:
                        res.append(name[i:]); break
                    b64 = name[i + 1:end]
                    if b64:
                        pad = (4 - len(b64) % 4) % 4
                        try:
                            chars = _b64.b64decode(b64 + '=' * pad).decode('utf-16-be')
                            res.append(chars)
                        except Exception:
                            res.append(name[i:end + 1])
                    else:
                        res.append('&')
                    i = end + 1
                else:
                    res.append(name[i]); i += 1
            return ''.join(res)

        def _imap_list_ordner(konto_dict):
            """Holt IMAP-Ordnerliste via Live-Verbindung. Gibt [] bei Fehler."""
            try:
                from mail_monitor import imap_connect as _imap_connect
                imap = _imap_connect(konto_dict)
                try:
                    imap.sock.settimeout(12)
                except Exception: pass
                status, folder_list = imap.list()
                ordner = []
                if status == 'OK':
                    for entry in (folder_list or []):
                        if isinstance(entry, bytes):
                            raw = entry.decode(errors='replace')
                            # Format: (\HasNoChildren) "/" "INBOX"
                            parts = raw.split('"/"')
                            if len(parts) >= 2:
                                name = parts[-1].strip().strip('"')
                            else:
                                parts2 = raw.rsplit(' ', 1)
                                name = parts2[-1].strip().strip('"') if parts2 else ''
                            if name:
                                ordner.append(_decode_imap_utf7(name))
                try: imap.logout()
                except: pass
                return ordner
            except Exception:
                return []

        try:
            # Alle aktiven Konten laden
            archiver_cfg = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\raumkult_config.json")
            konten_raw = []
            if archiver_cfg.exists():
                cfg_arc = json.loads(archiver_cfg.read_text('utf-8'))
                konten_raw = [k for k in cfg_arc.get('konten', []) if k.get('aktiv', True)]

            kira_cfg = {}
            try:
                kira_cfg = json.loads((SCRIPTS_DIR / 'config.json').read_text('utf-8'))
            except Exception:
                pass

            konto_labels_map = kira_cfg.get('mail_konto_labels', {})
            std_konto = kira_cfg.get('mail_konten', {}).get('standard_konto', '')
            sync_ordner_cfg  = kira_cfg.get('mail_archiv', {}).get('sync_ordner', {})
            zusatz_cfg       = kira_cfg.get('mail_konten', {}).get('postfach_zusatz_ordner', {})

            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            conn.row_factory = sqlite3.Row

            result = {"konten": [], "standard_konto": std_konto}

            for konto_dict in konten_raw:
                email = konto_dict.get('email', '')
                if not email:
                    continue

                # ── IMAP-Ordner via Cache oder Live ──
                now_ts = _time.time()
                with _folder_cache_lock:
                    cached = _folder_cache.get(email)
                    cache_valid = cached and (now_ts - cached['ts']) < _FOLDER_CACHE_TTL

                if cache_valid:
                    alle_imap_ordner = cached['ordner']
                else:
                    alle_imap_ordner = _imap_list_ordner(konto_dict)
                    if alle_imap_ordner:
                        with _folder_cache_lock:
                            _folder_cache[email] = {'ts': now_ts, 'ordner': alle_imap_ordner}

                # Kira-Kern-Ordner (Screenshot 2) + Postfach-Zusatz-Ordner (Screenshot 1)
                kira_ordner_namen = [o.lower() for o in sync_ordner_cfg.get(email, [])]
                zusatz_ordner_namen = [o.lower() for o in zusatz_cfg.get(email, [])]

                # Sichtbare Ordner = Kira-Kern + Postfach-Zusatz
                # Alle IMAP-Ordner filtern: zeige nur die in einer der beiden Listen
                def _soll_zeigen(fn):
                    fl = fn.lower()
                    for k in kira_ordner_namen:
                        if k in fl or fl in k:
                            return True
                    for z in zusatz_ordner_namen:
                        if z in fl or fl in z:
                            return True
                    return False

                # Wenn noch keine Konfiguration → Fallback: alle zeigen die im DB sind
                if not kira_ordner_namen and not zusatz_ordner_namen:
                    sichtbare_ordner = alle_imap_ordner or []
                else:
                    sichtbare_ordner = [fn for fn in alle_imap_ordner if _soll_zeigen(fn)] if alle_imap_ordner else []

                # Unread-Counts + Mailanzahlen aus mail_index.db
                db_rows = conn.execute(
                    "SELECT folder, COUNT(*) as cnt FROM mails WHERE konto=? GROUP BY folder",
                    (email,)
                ).fetchall()
                db_cnt  = {r['folder']: r['cnt'] for r in db_rows}
                db_unread_rows = conn.execute(
                    "SELECT folder, COUNT(*) as cnt FROM mails WHERE konto=? AND gelesen=0 GROUP BY folder",
                    (email,)
                ).fetchall()
                db_unread = {r['folder']: r['cnt'] for r in db_unread_rows}

                # Fallback: wenn keine IMAP-Ordner → aus DB-Ordner nehmen
                if not sichtbare_ordner:
                    sichtbare_ordner = list(db_cnt.keys())

                ordner_list = []
                for fn in sichtbare_ordner:
                    fl = fn.lower()
                    is_kira = any(k in fl or fl in k for k in kira_ordner_namen)
                    ordner_list.append({
                        'name':   fn,
                        'label':  _fn_label(fn),
                        'icon':   _fn_icon(fn),
                        'count':  db_cnt.get(fn, 0),
                        'unread': db_unread.get(fn, 0),
                        'typ':    'kira' if is_kira else 'postfach',
                    })

                # Sortierung: Kira-Ordner zuerst (INBOX top), dann Postfach-Zusatz
                _SORT_ORDER = ['inbox','posteingang','gesendete','sent','entwurf','draft',
                               'gel','deleted','trash','papierkorb','spam','junk']
                def _sort_key(o):
                    fl = o['name'].lower()
                    prio = next((i for i, k in enumerate(_SORT_ORDER) if k in fl), 99)
                    return (0 if o['typ']=='kira' else 1, prio, o['name'].lower())

                ordner_list.sort(key=_sort_key)

                display_name = konto_labels_map.get(email, '')
                result['konten'].append({
                    'email': email,
                    'label': email.split('@')[0],
                    'display_name': display_name,
                    'ordner': ordner_list,
                    'alle_imap_ordner': alle_imap_ordner,  # für Screenshot 1 Chip-Auswahl
                    'kira_ordner': sync_ordner_cfg.get(email, []),
                    'zusatz_ordner': zusatz_cfg.get(email, []),
                })

            conn.close()
            self._json(result)
        except Exception as e:
            self._json({"konten": [], "error": str(e)})

    def _api_mail_favorites_get(self):
        """GET /api/mail/favorites — Gespeicherte Favoriten."""
        try:
            cfg = json.loads((SCRIPTS_DIR / 'config.json').read_text('utf-8')) if (SCRIPTS_DIR / 'config.json').exists() else {}
            self._json({'favorites': cfg.get('mail_favorites', [])})
        except Exception as e:
            self._json({'favorites': [], 'error': str(e)})

    def _api_mail_favorites_set(self, body):
        """POST /api/mail/favorites — Favorit hinzufügen oder entfernen."""
        konto  = body.get('konto', '')
        folder = body.get('folder', '')
        label  = body.get('label', folder)
        action = body.get('action', 'add')  # 'add' oder 'remove'
        if not konto or not folder:
            self._json({'ok': False, 'error': 'konto/folder fehlt'})
            return
        try:
            cfg_path = SCRIPTS_DIR / 'config.json'
            cfg = json.loads(cfg_path.read_text('utf-8')) if cfg_path.exists() else {}
            favs = cfg.get('mail_favorites', [])
            if action == 'remove':
                favs = [f for f in favs if not (f['konto'] == konto and f['folder'] == folder)]
            else:
                if not any(f['konto'] == konto and f['folder'] == folder for f in favs):
                    favs.append({'konto': konto, 'folder': folder, 'label': label})
            cfg['mail_favorites'] = favs
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
            self._json({'ok': True, 'favorites': favs})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_combined_konten_get(self):
        """GET /api/mail/combined/konten — Liefert konfigurierte Konten für Gemeinsames Postfach."""
        try:
            cfg = json.loads((SCRIPTS_DIR / 'config.json').read_text('utf-8')) if (SCRIPTS_DIR / 'config.json').exists() else {}
            konten = cfg.get('combined_postfach', {}).get('konten', [])
            self._json({'konten': konten})
        except Exception as e:
            self._json({'konten': [], 'error': str(e)})

    def _api_mail_combined_konten_set(self, body):
        """POST /api/mail/combined/konten — Setzt Konten für Gemeinsames Postfach."""
        konten = body.get('konten', [])
        try:
            cfg_path = SCRIPTS_DIR / 'config.json'
            cfg = json.loads(cfg_path.read_text('utf-8')) if cfg_path.exists() else {}
            cfg.setdefault('combined_postfach', {})['konten'] = konten
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
            self._json({'ok': True, 'konten': konten})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_gelesen(self, body):
        """POST /api/mail/gelesen — Lese-Status mehrerer Mails setzen. {ids:[...], gelesen:bool}"""
        _ensure_mail_columns()
        ids     = body.get('ids', [])
        gelesen = 1 if body.get('gelesen', True) else 0
        if not ids:
            self._json({'ok': False, 'error': 'ids fehlt'})
            return
        try:
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            placeholders = ','.join('?' * len(ids))
            conn.execute(f"UPDATE mails SET gelesen={gelesen} WHERE message_id IN ({placeholders})", ids)
            conn.commit()
            conn.close()
            self._json({'ok': True})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_flag(self, body):
        """POST /api/mail/flag — Kennzeichnen-Status setzen. {message_id, flagged:bool}"""
        _ensure_mail_columns()
        msg_id  = body.get('message_id', '')
        flagged = 1 if body.get('flagged', False) else 0
        if not msg_id:
            self._json({'ok': False, 'error': 'message_id fehlt'})
            return
        try:
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            conn.execute("UPDATE mails SET flagged=? WHERE message_id=?", (flagged, msg_id))
            conn.commit()
            conn.close()
            self._json({'ok': True})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_pin(self, body):
        """POST /api/mail/pin — Angeheftet-Status setzen. {message_id, pinned:bool}"""
        _ensure_mail_columns()
        msg_id = body.get('message_id', '')
        pinned = 1 if body.get('pinned', False) else 0
        if not msg_id:
            self._json({'ok': False, 'error': 'message_id fehlt'})
            return
        try:
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            conn.execute("UPDATE mails SET pinned=? WHERE message_id=?", (pinned, msg_id))
            conn.commit()
            conn.close()
            self._json({'ok': True})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_loeschen(self, body):
        """POST /api/mail/loeschen — Mails aus DB löschen. {ids:[...]}"""
        ids = body.get('ids', [])
        if not ids:
            self._json({'ok': False, 'error': 'ids fehlt'})
            return
        try:
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            placeholders = ','.join('?' * len(ids))
            conn.execute(f"DELETE FROM mails WHERE message_id IN ({placeholders})", ids)
            conn.commit()
            conn.close()
            self._json({'ok': True, 'deleted': len(ids)})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_snooze(self, body):
        """POST /api/mail/snooze — Snooze setzen oder aufheben.
        {message_id, snooze_until: 'YYYY-MM-DD HH:MM:SS' | null, konto: email}
        Legt bei erstem Snooze den IMAP-Ordner "Erneut erinnern" automatisch an.
        """
        from datetime import datetime as _dt
        _ensure_mail_columns()
        message_id   = body.get('message_id', '')
        snooze_until = body.get('snooze_until')  # None = aufheben
        konto        = body.get('konto', '')
        if not message_id:
            self._json({'ok': False, 'error': 'message_id fehlt'})
            return
        try:
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            conn.execute("UPDATE mails SET snooze_until=? WHERE message_id=?", (snooze_until, message_id))
            conn.commit()
            conn.close()
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})
            return

        # IMAP-Ordner "Erneut erinnern" auto-anlegen + in sync_ordner eintragen
        imap_ordner_erstellt = False
        SNOOZE_FOLDER = 'Erneut erinnern'
        if snooze_until and konto:
            try:
                cfg_path = SCRIPTS_DIR / 'config.json'
                cfg = json.loads(cfg_path.read_text('utf-8')) if cfg_path.exists() else {}
                sync_ordner = cfg.get('mail_archiv', {}).get('sync_ordner', {})
                if SNOOZE_FOLDER not in sync_ordner.get(konto, []):
                    # IMAP-Ordner erstellen
                    try:
                        archiver_cfg = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\raumkult_config.json")
                        if archiver_cfg.exists():
                            cfg_arc = json.loads(archiver_cfg.read_text('utf-8'))
                            konto_dict = next((k for k in cfg_arc.get('konten', []) if k.get('email') == konto), None)
                            if konto_dict:
                                from mail_monitor import imap_connect as _imap_connect
                                imap = _imap_connect(konto_dict)
                                # Ordner erstellen (ignoriere Fehler falls er schon existiert)
                                imap.create(SNOOZE_FOLDER)
                                try: imap.logout()
                                except: pass
                                imap_ordner_erstellt = True
                    except Exception:
                        pass
                    # In sync_ordner eintragen (auch wenn IMAP-Erstellung fehlschlug)
                    if konto not in sync_ordner:
                        sync_ordner[konto] = []
                    if SNOOZE_FOLDER not in sync_ordner[konto]:
                        sync_ordner[konto].append(SNOOZE_FOLDER)
                        if 'mail_archiv' not in cfg:
                            cfg['mail_archiv'] = {}
                        cfg['mail_archiv']['sync_ordner'] = sync_ordner
                        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception:
                pass

        # Anzeigetext für snooze_until
        snooze_label = ''
        if snooze_until:
            try:
                sd = _dt.fromisoformat(snooze_until.replace(' ', 'T'))
                snooze_label = sd.strftime('%d.%m.%Y %H:%M')
            except Exception:
                snooze_label = snooze_until
        self._json({'ok': True, 'snooze_label': snooze_label, 'imap_ordner_erstellt': imap_ordner_erstellt})

    def _api_mail_snooze_count(self):
        """GET /api/mail/snooze/count — Anzahl aktuell schlafender Mails."""
        _ensure_mail_columns()
        try:
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            count = conn.execute(
                "SELECT COUNT(*) FROM mails WHERE snooze_until IS NOT NULL AND datetime(snooze_until) > datetime('now')"
            ).fetchone()[0]
            conn.close()
            self._json({'count': count})
        except Exception as e:
            self._json({'count': 0, 'error': str(e)})

    def _api_mail_kira_markieren(self, body):
        """POST /api/mail/kira-markieren — Mail als von Kira verwendet markieren."""
        _ensure_mail_columns()
        msg_id = body.get('message_id', '')
        wert   = 1 if body.get('verwendet', True) else 0
        if not msg_id:
            self._json({'ok': False, 'error': 'message_id fehlt'})
            return
        try:
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            conn.execute("UPDATE mails SET kira_verwendet=? WHERE message_id=?", (wert, msg_id))
            conn.commit()
            conn.close()
            self._json({'ok': True})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_combined(self):
        """GET /api/mail/combined?q=&offset=&limit=&folder_type= — Gemeinsames Postfach aus mehreren Konten."""
        import re as _re
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        q           = qs.get('q', [''])[0].strip()
        offset      = int(qs.get('offset', ['0'])[0])
        limit       = min(int(qs.get('limit', ['50'])[0]), 200)
        folder_type = qs.get('folder_type', ['all'])[0].lower()  # inbox|sent|drafts|all|unread|snoozed
        try:
            cfg = json.loads((SCRIPTS_DIR / 'config.json').read_text('utf-8')) if (SCRIPTS_DIR / 'config.json').exists() else {}
            konten = cfg.get('combined_postfach', {}).get('konten', [])
        except Exception:
            konten = []
        if not konten:
            self._json({'total': 0, 'mails': [], 'hint': 'Keine Konten konfiguriert'})
            return
        # Build folder filter based on folder_type
        _FOLDER_PATTERNS = {
            'inbox':  ["LOWER(folder) LIKE '%inbox%'", "LOWER(folder) LIKE '%posteingang%'"],
            'sent':   ["LOWER(folder) LIKE '%sent%'", "LOWER(folder) LIKE '%gesendet%'"],
            'drafts': ["LOWER(folder) LIKE '%draft%'", "LOWER(folder) LIKE '%entwurf%'"],
        }
        extra_where = ''
        if folder_type == 'snoozed':
            folder_clause = "1=1"  # alle Ordner — snooze_until filtert
            extra_where = " AND snooze_until IS NOT NULL AND datetime(snooze_until) > datetime('now')"
        elif folder_type == 'unread':
            inbox_parts = ' OR '.join(_FOLDER_PATTERNS['inbox'])
            folder_clause = f"({inbox_parts})"
            extra_where = " AND gelesen=0 AND (snooze_until IS NULL OR datetime(snooze_until) <= datetime('now'))"
        elif folder_type in _FOLDER_PATTERNS:
            folder_clause = '(' + ' OR '.join(_FOLDER_PATTERNS[folder_type]) + ')'
        else:  # 'all' — inbox + sent (skip internal/spam/trash)
            inbox_parts  = ' OR '.join(_FOLDER_PATTERNS['inbox'])
            sent_parts   = ' OR '.join(_FOLDER_PATTERNS['sent'])
            folder_clause = f"({inbox_parts} OR {sent_parts})"
            extra_where = " AND (snooze_until IS NULL OR datetime(snooze_until) <= datetime('now'))"
        try:
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            conn.row_factory = sqlite3.Row
            placeholders = ','.join(['?' for _ in konten])
            where  = f"konto IN ({placeholders}) AND {folder_clause}{extra_where}"
            params = list(konten)
            if q:
                where += " AND (betreff LIKE ? OR absender LIKE ? OR text_plain LIKE ?)"
                like = f"%{q}%"
                params += [like, like, like]
            _ensure_mail_columns()
            total = conn.execute(f"SELECT COUNT(*) FROM mails WHERE {where}", params).fetchone()[0]
            rows  = conn.execute(
                f"SELECT id,konto,betreff,absender,datum,message_id,hat_anhaenge,anhaenge,thread_id,text_plain,gelesen,"
                f"COALESCE(flagged,0) as flagged,COALESCE(pinned,0) as pinned,"
                f"COALESCE(kira_verwendet,0) as kira_verwendet,snooze_until "
                f"FROM mails WHERE {where} ORDER BY datum DESC LIMIT ? OFFSET ?",
                params + [limit, offset]
            ).fetchall()
            mails = []
            for r in rows:
                af = r['absender'] or ''
                m  = _re.search(r'^([^<]+)<', af)
                short = m.group(1).strip() if m else af.split('@')[0]
                mails.append({
                    'message_id':     r['message_id'],
                    'betreff':        r['betreff'] or '(kein Betreff)',
                    'absender':       af,
                    'absender_short': short[:40],
                    'datum':          (r['datum'] or '')[:16],
                    'hat_anhaenge':   bool(r['hat_anhaenge']) and len(json.loads(r['anhaenge'] or '[]')) > 0,
                    'thread_id':      r['thread_id'] or '',
                    'hat_thread':     False,
                    'thread_count':   1,
                    'text_plain':     (r['text_plain'] or '')[:120],
                    'unread':         (r['gelesen'] == 0) if r['gelesen'] is not None else False,
                    'konto':          r['konto'] or '',
                    'flagged':        bool(r['flagged']),
                    'pinned':         bool(r['pinned']),
                    'kira_verwendet': bool(r['kira_verwendet']),
                    'snooze_until':   r['snooze_until'] or '',
                })
            conn.close()
            self._json({'total': total, 'mails': mails})
        except Exception as e:
            self._json({'total': 0, 'mails': [], 'error': str(e)})

    def _api_mail_list(self):
        """GET /api/mail/list?konto=&folder=&offset=&limit=&q= — Mailsliste aus mail_index.db."""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        konto  = qs.get('konto',  [''])[0]
        folder = qs.get('folder', [''])[0]
        offset = int(qs.get('offset', ['0'])[0])
        limit  = min(int(qs.get('limit', ['50'])[0]), 200)
        q      = qs.get('q', [''])[0].strip()

        try:
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            conn.row_factory = sqlite3.Row

            params = [konto, folder]
            where  = "konto=? AND folder=?"
            # Snoozed Mails in Inbox-Ansicht ausblenden (aber nicht im Snooze-Ordner)
            _folder_low = folder.lower()
            if 'inbox' in _folder_low or 'posteingang' in _folder_low:
                where += " AND (snooze_until IS NULL OR datetime(snooze_until) <= datetime('now'))"
            if q:
                where += " AND (betreff LIKE ? OR absender LIKE ? OR text_plain LIKE ?)"
                like = f"%{q}%"
                params += [like, like, like]

            _ensure_mail_columns()
            total = conn.execute(f"SELECT COUNT(*) FROM mails WHERE {where}", params).fetchone()[0]
            rows  = conn.execute(
                f"SELECT id,konto,konto_label,betreff,absender,an,datum,message_id,"
                f"hat_anhaenge,anhaenge,thread_id,text_plain,gelesen,"
                f"COALESCE(flagged,0) as flagged,COALESCE(pinned,0) as pinned,"
                f"COALESCE(kira_verwendet,0) as kira_verwendet,snooze_until FROM mails WHERE {where} "
                f"ORDER BY datum DESC LIMIT ? OFFSET ?",
                params + [limit, offset]
            ).fetchall()

            # Thread-Counts berechnen
            thread_counts = {}
            for r in rows:
                tid = r['thread_id']
                if tid and tid not in thread_counts:
                    cnt = conn.execute("SELECT COUNT(*) FROM mails WHERE thread_id=?", (tid,)).fetchone()[0]
                    thread_counts[tid] = cnt

            mails = []
            for r in rows:
                import re as _re
                absender_full = r['absender'] or ''
                m = _re.search(r'^([^<]+)<', absender_full)
                absender_short = m.group(1).strip() if m else absender_full.split('@')[0]
                tid = r['thread_id'] or ''
                tc  = thread_counts.get(tid, 1)
                mails.append({
                    'message_id':    r['message_id'],
                    'betreff':       r['betreff'] or '(kein Betreff)',
                    'absender':      absender_full,
                    'absender_short': absender_short[:40],
                    'datum':         (r['datum'] or '')[:16],
                    'hat_anhaenge':  bool(r['hat_anhaenge']) and len(json.loads(r['anhaenge'] or '[]')) > 0,
                    'thread_id':     tid,
                    'hat_thread':    tc > 1,
                    'thread_count':  tc,
                    'text_plain':    (r['text_plain'] or '')[:120],
                    'unread':        (r['gelesen'] == 0) if r['gelesen'] is not None else False,
                    'flagged':       bool(r['flagged']),
                    'pinned':        bool(r['pinned']),
                    'kira_verwendet': bool(r['kira_verwendet']),
                    'snooze_until':  r['snooze_until'] or '',
                })

            conn.close()
            self._json({'total': total, 'mails': mails})
        except Exception as e:
            self._json({'total': 0, 'mails': [], 'error': str(e)})

    def _api_mail_thread(self):
        """GET /api/mail/thread?thread_id=... — Alle Mails in einem Thread."""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        thread_id = qs.get('thread_id', [''])[0]
        if not thread_id:
            self._json({'mails': []})
            return
        try:
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT message_id,betreff,absender,datum,text_plain,hat_anhaenge "
                "FROM mails WHERE thread_id=? ORDER BY datum ASC",
                (thread_id,)
            ).fetchall()
            import re as _re
            mails = []
            for r in rows:
                absender_full = r['absender'] or ''
                m2 = _re.search(r'^([^<]+)<', absender_full)
                absender_short = m2.group(1).strip() if m2 else absender_full.split('@')[0]
                mails.append({
                    'message_id':    r['message_id'],
                    'betreff':       r['betreff'] or '',
                    'absender':      absender_full,
                    'absender_short': absender_short[:40],
                    'datum':         (r['datum'] or '')[:16],
                    'text_plain':    (r['text_plain'] or '')[:300],
                    'hat_anhaenge':  bool(r['hat_anhaenge']),
                })
            conn.close()
            self._json({'mails': mails, 'thread_id': thread_id})
        except Exception as e:
            self._json({'mails': [], 'error': str(e)})

    def _api_mail_send(self, body):
        """POST /api/mail/send — Sendet eine Mail via mail_sender.py."""
        from_email  = body.get('from_email', 'info@raumkult.eu')
        to          = body.get('to', '')
        cc          = body.get('cc', '')
        bcc         = body.get('bcc', '')
        subject     = body.get('subject', '')
        body_plain  = body.get('body_plain', '')
        body_html   = body.get('body_html', '')
        in_reply_to = body.get('in_reply_to', '')
        refs        = body.get('references', '')

        if not to or not subject:
            self._json({'ok': False, 'error': 'to und subject erforderlich'})
            return
        try:
            from mail_sender import send_mail
            result = send_mail(
                from_email=from_email, to=to, cc=cc, bcc=bcc,
                subject=subject, body_plain=body_plain, body_html=body_html,
                in_reply_to=in_reply_to, references=refs,
            )
            self._json(result)
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    # ── Kira-Feedback (Paket 6, session-oo) ──────────────────────────────────

    def _api_kira_feedback(self, body: dict):
        """POST /api/kira/feedback — Thumbs up/down Bewertung einer Kira-Antwort."""
        session_id   = body.get("session_id", "")
        msg_idx      = int(body.get("message_idx", 0))
        rating       = body.get("rating", "")
        kommentar    = body.get("kommentar", "") or ""
        kira_antwort = body.get("kira_antwort", "") or ""
        if rating not in ("gut", "schlecht"):
            self._json({"ok": False, "error": "rating muss 'gut' oder 'schlecht' sein"})
            return
        try:
            db = sqlite3.connect(str(TASKS_DB))
            cur = db.execute("""
                INSERT INTO kira_feedback (session_id, message_idx, rating, kommentar, kira_antwort)
                VALUES (?,?,?,?,?)
            """, (session_id, msg_idx, rating, kommentar[:500], kira_antwort[:1000]))
            db.commit()
            feedback_id = cur.lastrowid
            auto_regel_id = None
            if rating == "schlecht" and kira_antwort:
                try:
                    from kira_llm import chat as _kc
                    lern_prompt = (
                        f"Kira hat folgende Antwort gegeben, die als schlecht bewertet wurde: "
                        f"'{kira_antwort[:400]}'\n\n"
                        f"Formuliere eine kurze Lernregel die Kira zukuenftig besser macht. "
                        f"JSON: {{\"titel\": \"max 100 Zeichen\", \"inhalt\": \"max 200 Zeichen\"}}"
                    )
                    lern_result = _kc(lern_prompt)
                    lern_text = (lern_result.get("text") or "").strip()
                    import re as _re, json as _j
                    m = _re.search(r'\{[^}]*"titel"[^}]*\}', lern_text, _re.DOTALL)
                    if m:
                        parsed = _j.loads(m.group(0))
                        titel  = parsed.get("titel", "Auto-Lernregel")[:100]
                        inhalt = parsed.get("inhalt", lern_text[:200])[:500]
                        rc = db.execute("""
                            INSERT INTO wissen_regeln (titel, inhalt, kategorie, quelle, erstellt_am)
                            VALUES (?,?,'auto_gelernt','feedback_schlecht',CURRENT_TIMESTAMP)
                        """, (titel, inhalt))
                        db.commit()
                        auto_regel_id = rc.lastrowid
                        db.execute("UPDATE kira_feedback SET auto_regel_id=? WHERE id=?",
                                   (auto_regel_id, feedback_id))
                        db.commit()
                except Exception:
                    pass
            db.close()
            self._json({"ok": True, "feedback_id": feedback_id, "auto_regel_id": auto_regel_id})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    # ── Mail-Approve-Queue (Paket 2, session-oo) ─────────────────────────────

    def _api_mail_approve_pending(self):
        """GET /api/mail/approve/pending — offene Mail-Freigaben zurückgeben."""
        try:
            db = sqlite3.connect(str(TASKS_DB))
            db.row_factory = sqlite3.Row
            rows = db.execute("""
                SELECT id, an, betreff, body_plain, konto, in_reply_to,
                       task_id, vorgang_id, erstellt_von, erstellt_am, ablauf_am
                FROM mail_approve_queue
                WHERE status = 'pending'
                ORDER BY erstellt_am DESC
                LIMIT 20
            """).fetchall()
            db.close()
            items = [dict(r) for r in rows]
            self._json({"ok": True, "pending": items, "count": len(items)})
        except Exception as e:
            self._json({"ok": False, "error": str(e), "pending": [], "count": 0})

    def _api_mail_approve_action(self, queue_id: int, body: dict):
        """POST /api/mail/approve/{id} — approve/reject/edit."""
        action    = body.get("action", "").strip()   # approve | reject | edit
        new_body  = body.get("body", "").strip()      # wenn edit: neuer Text
        now       = datetime.now().isoformat()

        if action not in ("approve", "reject", "edit"):
            self._json({"ok": False, "error": "action muss approve | reject | edit sein"})
            return
        try:
            db = sqlite3.connect(str(TASKS_DB))
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT * FROM mail_approve_queue WHERE id=? AND status='pending'", (queue_id,)
            ).fetchone()
            if not row:
                db.close()
                self._json({"ok": False, "error": f"Queue-Eintrag {queue_id} nicht gefunden oder nicht pending"})
                return

            if action == "reject":
                db.execute("UPDATE mail_approve_queue SET status='rejected', entschieden_am=? WHERE id=?",
                           (now, queue_id))
                db.commit()
                db.close()
                self._json({"ok": True, "message": f"Mail #{queue_id} abgelehnt."})
                return

            # approve oder edit (edit → body übernehmen, dann senden)
            body_plain = new_body if (action == "edit" and new_body) else (row["body_plain"] or "")
            from_email = row["konto"] or "info@raumkult.eu"
            try:
                from mail_sender import send_mail
                result = send_mail(
                    from_email=from_email,
                    to=row["an"],
                    subject=row["betreff"],
                    body_plain=body_plain,
                    in_reply_to=row["in_reply_to"] or "",
                )
                if result.get("ok"):
                    db.execute(
                        "UPDATE mail_approve_queue SET status='sent', entschieden_am=?, gesendet_am=? WHERE id=?",
                        (now, now, queue_id)
                    )
                    db.commit()
                    # kira_vorschlag wenn Mail von Kira-Entwurf stammte, sonst user
                    _at = "kira_vorschlag" if row.get("erstellt_von") == "kira" else "user"
                    rlog("server", "mail_gesendet",
                         f"Mail #{queue_id} an {row['an']} gesendet ({action})",
                         modul="server", source="server", actor_type=_at,
                         status="ok", entity_snapshot={"queue_id": queue_id, "an": row["an"]})

                    # Stil-Lernen: wenn User stark editiert hat (Paket 6-C)
                    if action == "edit" and new_body:
                        orig = row["body_plain"] or ""
                        if orig and len(orig) > 10:
                            diff_pct = abs(len(new_body) - len(orig)) / max(len(orig), 1)
                            if diff_pct > 0.40:
                                try:
                                    from kira_llm import chat as _kc
                                    stil_prompt = (
                                        f"Original-Entwurf von Kira:\n'{orig[:300]}'\n\n"
                                        f"Nutzer-Version:\n'{new_body[:300]}'\n\n"
                                        f"Erkenne den Stil-Unterschied und formuliere eine kurze Lernregel. "
                                        f"JSON: {{\"titel\": \"Stil-Regel: ...\", \"inhalt\": \"...\"}}"
                                    )
                                    lern_result = _kc(stil_prompt)
                                    lern_text = (lern_result.get("text") or "").strip()
                                    import re as _re, json as _j
                                    m = _re.search(r'\{[^}]*"titel"[^}]*\}', lern_text, _re.DOTALL)
                                    if m:
                                        parsed = _j.loads(m.group(0))
                                        db.execute("""
                                            INSERT INTO wissen_regeln (titel, inhalt, kategorie, quelle, erstellt_am)
                                            VALUES (?,?,'auto_gelernt','mail_stil_diff',CURRENT_TIMESTAMP)
                                        """, (parsed.get("titel","Stil-Regel")[:100],
                                              parsed.get("inhalt", lern_text[:200])[:500]))
                                        db.commit()
                                except Exception:
                                    pass

                    db.close()
                    self._json({"ok": True, "message": f"Mail an {row['an']} gesendet."})
                else:
                    db.close()
                    self._json({"ok": False, "error": result.get("error", "Sendefehler")})
            except Exception as e:
                db.close()
                self._json({"ok": False, "error": str(e)})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _api_kira_aktivitaeten(self):
        """GET /api/kira/aktivitaeten?seit=24h&typ= — Kira autonome Aktionen."""
        try:
            qs   = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            seit = qs.get("seit", ["24h"])[0]
            typ  = qs.get("typ",  [""])[0]
            interval_map = {"24h": "-24 hours", "7d": "-7 days", "30d": "-30 days"}
            interval = interval_map.get(seit, "-24 hours")
            db_path = SCRIPTS_DIR.parent / "knowledge" / "runtime_events.db"
            if not db_path.exists():
                self._json({"ok": True, "eintraege": []})
                return
            import sqlite3 as _sq
            with _sq.connect(str(db_path)) as con:
                con.row_factory = _sq.Row
                if typ:
                    rows = con.execute(
                        "SELECT ts, action, summary, actor_type FROM events "
                        "WHERE actor_type=? AND ts > datetime('now', ?) "
                        "ORDER BY ts DESC LIMIT 50",
                        (typ, interval)
                    ).fetchall()
                else:
                    rows = con.execute(
                        "SELECT ts, action, summary, actor_type FROM events "
                        "WHERE actor_type IN ('kira_autonom','kira_vorschlag') "
                        "AND ts > datetime('now', ?) "
                        "ORDER BY ts DESC LIMIT 50",
                        (interval,)
                    ).fetchall()
            self._json({"ok": True, "eintraege": [dict(r) for r in rows]})
        except Exception as e:
            self._json({"ok": False, "error": str(e), "eintraege": []})

    def _api_kira_proaktiv_status(self):
        """GET /api/kira/proaktiv/status — Status des letzten proaktiven Scans."""
        try:
            import kira_proaktiv as _p
            state = _p._load_state()
            letzter_scan = state.get("letzter_scan", "noch kein Scan")
            aktionen_heute = {k: v for k, v in state.items()
                              if k.startswith("proaktiv_") and str(datetime.now().date()) in str(v)}
            self._json({
                "ok": True,
                "letzter_scan": letzter_scan,
                "aktionen_heute": len(aktionen_heute),
                "proaktiv_aktiv": True
            })
        except ImportError:
            self._json({"ok": False, "error": "kira_proaktiv nicht verfügbar", "proaktiv_aktiv": False})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _api_kira_proaktiv_scan(self):
        """POST /api/kira/proaktiv/scan — Startet proaktiven Scan manuell."""
        try:
            import kira_proaktiv as _p
            import threading as _t
            def _run():
                _p.run_proaktiver_scan()
            _t.Thread(target=_run, daemon=True, name="ProaktivScanManual").start()
            self._json({"ok": True, "msg": "Proaktiver Scan gestartet"})
        except ImportError:
            self._json({"ok": False, "error": "kira_proaktiv nicht verfügbar"})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _api_mail_archiv_status(self):
        """GET /api/mail/archiv/status — Archiv-Pfad + Mailanzahl."""
        try:
            cfg = json.loads((SCRIPTS_DIR / 'config.json').read_text('utf-8'))
            ma = cfg.get('mail_archiv', {})
            pfad = ma.get('pfad', '')
            pfad_ok = bool(pfad and Path(pfad).exists())
            mails_total = 0
            if pfad_ok:
                try:
                    conn2 = sqlite3.connect(str(MAIL_INDEX_DB))
                    mails_total = conn2.execute("SELECT COUNT(*) FROM mails").fetchone()[0]
                    conn2.close()
                except Exception:
                    pass
            sync_ordner = ma.get('sync_ordner', cfg.get('mail_archiv', {}).get('sync_ordner', {}))
            self._json({
                'pfad': pfad,
                'pfad_ok': pfad_ok,
                'pfad_vorhanden': pfad_ok,
                'mails_index': mails_total,
                'mails_total': mails_total,
                'aktiv': ma.get('neue_mails_archivieren', True),
                'neue_mails_archivieren': ma.get('neue_mails_archivieren', True),
                'sync_ordner': sync_ordner,
            })
        except Exception as e:
            self._json({'pfad': '', 'pfad_vorhanden': False, 'mails_total': 0, 'error': str(e)})

    def _api_mail_archiv_reindex_progress(self):
        """GET /api/mail/archiv/reindex/progress — Fortschritt des laufenden Re-Index."""
        try:
            from mail_archiv_reindex import get_progress
            self._json(get_progress())
        except Exception as e:
            self._json({'running': False, 'finished': True, 'error': str(e)})

    def _api_mail_archiv_reindex(self, body):
        """POST /api/mail/archiv/reindex — Startet Re-Index als Hintergrund-Thread."""
        import threading as _threading
        pfad = (body.get('pfad') or '').strip()
        if not pfad:
            try:
                cfg = json.loads((SCRIPTS_DIR / 'config.json').read_text('utf-8'))
                pfad = cfg.get('mail_archiv', {}).get('pfad', '')
            except Exception:
                pass
        if not pfad:
            self._json({'ok': False, 'error': 'Kein Archiv-Pfad angegeben'})
            return
        if not Path(pfad).exists():
            self._json({'ok': False, 'error': f'Pfad nicht gefunden: {pfad}'})
            return
        def _run():
            try:
                from mail_archiv_reindex import reindex
                reindex(archiv_pfad=pfad)
            except Exception as ex:
                import logging
                logging.getLogger('server').error(f'Reindex-Fehler: {ex}')
        _threading.Thread(target=_run, daemon=True).start()
        self._json({'ok': True, 'pfad': pfad})

    def _api_mail_archiv_sync_ordner(self, body):
        """POST /api/mail/archiv/sync-ordner — Aktiviert/deaktiviert Sync-Ordner für ein Konto."""
        try:
            konto  = (body.get('konto') or '').strip()
            ordner = (body.get('ordner') or '').strip()
            aktiv  = bool(body.get('aktiv', True))
            if not konto or not ordner:
                self._json({'ok': False, 'error': 'konto und ordner erforderlich'})
                return
            cfg_path = SCRIPTS_DIR / 'config.json'
            cfg = json.loads(cfg_path.read_text('utf-8'))
            ma = cfg.setdefault('mail_archiv', {})
            so = ma.setdefault('sync_ordner', {})
            ordner_list = so.setdefault(konto, [])
            pflicht = {'INBOX', 'Gesendete Elemente'}
            if ordner in pflicht:
                if ordner not in ordner_list:
                    ordner_list.append(ordner)
            elif aktiv and ordner not in ordner_list:
                ordner_list.append(ordner)
            elif not aktiv and ordner in ordner_list:
                ordner_list.remove(ordner)
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
            self._json({'ok': True})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_konto_postfach_ordner(self, body):
        """POST /api/mail/konto/postfach-ordner — Speichert Postfach-Zusatz-Ordner (Screenshot 1 Chips)."""
        try:
            email  = (body.get('email') or '').strip()
            ordner = body.get('ordner', '')   # einzelner Ordnername (oder Liste)
            if isinstance(ordner, list):
                ordner = ordner[0] if ordner else ''
            aktiv  = bool(body.get('aktiv', True))
            if not email or not ordner:
                self._json({'ok': False, 'error': 'email und ordner erforderlich'})
                return
            cfg_path = SCRIPTS_DIR / 'config.json'
            cfg = json.loads(cfg_path.read_text('utf-8'))
            mk = cfg.setdefault('mail_konten', {})
            pz = mk.setdefault('postfach_zusatz_ordner', {})
            lst = pz.setdefault(email, [])
            if aktiv and ordner not in lst:
                lst.append(ordner)
            elif not aktiv and ordner in lst:
                lst.remove(ordner)
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
            # Folder-Cache invalidieren
            with _folder_cache_lock:
                _folder_cache.pop(email, None)
            self._json({'ok': True})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_verschieben(self, body):
        """POST /api/mail/verschieben — Verschiebt Mail zwischen IMAP-Ordnern + DB-Update."""
        try:
            konto      = (body.get('konto') or '').strip()
            message_id = (body.get('message_id') or '').strip()
            ziel       = (body.get('ziel_ordner') or '').strip()
            if not konto or not message_id or not ziel:
                self._json({'ok': False, 'error': 'konto, message_id und ziel_ordner erforderlich'})
                return

            # Quellordner aus mail_index.db ermitteln
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT folder, uid FROM mails WHERE konto=? AND message_id=? LIMIT 1",
                (konto, message_id)
            ).fetchone()
            conn.close()
            if not row:
                self._json({'ok': False, 'error': 'Mail nicht im Index gefunden'})
                return
            quell_ordner = row['folder']

            # IMAP-Zugangsdaten laden
            from mail_monitor import _imap_connect_konto
            imap = _imap_connect_konto(konto)
            if not imap:
                self._json({'ok': False, 'error': 'IMAP-Verbindung fehlgeschlagen'})
                return

            try:
                # Quellordner öffnen
                s, _ = imap.select(f'"{quell_ordner}"')
                if s != 'OK':
                    self._json({'ok': False, 'error': f'Ordner {quell_ordner} nicht zugänglich'})
                    return

                # UID anhand Message-ID suchen
                clean_mid = message_id.strip('<>').strip()
                sr, ud = imap.uid('SEARCH', 'HEADER', 'Message-ID', clean_mid)
                if sr != 'OK' or not ud or not ud[0]:
                    # Fallback: Message-ID mit spitzen Klammern
                    mid_fb = f'<{clean_mid}>'
                    sr, ud = imap.uid('SEARCH', 'HEADER', 'Message-ID', mid_fb)
                if sr != 'OK' or not ud or not ud[0]:
                    self._json({'ok': False, 'error': 'UID nicht gefunden'})
                    return
                uid = ud[0].split()[0]

                # COPY in Zielordner
                cr, _ = imap.uid('COPY', uid, f'"{ziel}"')
                if cr != 'OK':
                    self._json({'ok': False, 'error': f'COPY nach {ziel} fehlgeschlagen'})
                    return

                # Original als gelöscht markieren + expunge
                imap.uid('STORE', uid, '+FLAGS', '(\\Deleted)')
                imap.expunge()
            finally:
                try: imap.logout()
                except: pass

            # DB aktualisieren
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            conn.execute(
                "UPDATE mails SET folder=? WHERE konto=? AND message_id=?",
                (ziel, konto, message_id)
            )
            conn.commit()
            conn.close()

            # Folder-Cache invalidieren
            with _folder_cache_lock:
                _folder_cache.pop(konto, None)

            self._json({'ok': True, 'quell_ordner': quell_ordner, 'neuer_ordner': ziel})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_protokoll(self):
        """GET /api/mail/protokoll?konto=&limit=50&offset=0 — Gelöschte-Protokoll abrufen."""
        _ensure_geloeschte_protokoll_table()
        try:
            qs     = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            konto  = qs.get('konto', [''])[0]
            limit  = int(qs.get('limit', ['50'])[0])
            offset = int(qs.get('offset', ['0'])[0])
            db = get_db()
            if konto:
                rows = db.execute(
                    "SELECT * FROM geloeschte_protokoll WHERE konto=? ORDER BY datum_geloescht DESC LIMIT ? OFFSET ?",
                    (konto, limit, offset)
                ).fetchall()
                total = db.execute("SELECT COUNT(*) FROM geloeschte_protokoll WHERE konto=?", (konto,)).fetchone()[0]
            else:
                rows = db.execute(
                    "SELECT * FROM geloeschte_protokoll ORDER BY datum_geloescht DESC LIMIT ? OFFSET ?",
                    (limit, offset)
                ).fetchall()
                total = db.execute("SELECT COUNT(*) FROM geloeschte_protokoll").fetchone()[0]
            db.close()
            self._json({
                'ok': True,
                'total': total,
                'eintraege': [dict(r) for r in rows]
            })
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    # ── Signaturen ─────────────────────────────────────────────────────────────

    def _api_mail_signaturen_get(self):
        """GET /api/mail/signaturen — Alle Signaturen."""
        _ensure_mail_signaturen_table()
        try:
            db = get_db()
            rows = db.execute(
                "SELECT id, konto, name, html, ist_default, erstellt, geaendert FROM mail_signaturen ORDER BY konto, ist_default DESC, name"
            ).fetchall()
            db.close()
            self._json({'ok': True, 'signaturen': [dict(r) for r in rows]})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_signaturen_save(self, body):
        """POST /api/mail/signaturen/save — Signatur anlegen oder aktualisieren."""
        _ensure_mail_signaturen_table()
        try:
            sig_id  = body.get('id')          # None = neu
            konto   = body.get('konto', '').strip()
            name    = body.get('name', '').strip()
            html    = body.get('html', '')
            if not konto or not name:
                self._json({'ok': False, 'error': 'konto und name erforderlich'}); return
            db = get_db()
            now = datetime.now().isoformat(timespec='seconds')
            if sig_id:
                db.execute(
                    "UPDATE mail_signaturen SET konto=?, name=?, html=?, geaendert=? WHERE id=?",
                    (konto, name, html, now, int(sig_id))
                )
            else:
                db.execute(
                    "INSERT INTO mail_signaturen (konto, name, html, ist_default, erstellt, geaendert) VALUES (?,?,?,0,?,?)",
                    (konto, name, html, now, now)
                )
            db.commit()
            db.close()
            self._json({'ok': True})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_signaturen_delete(self, body):
        """POST /api/mail/signaturen/delete — Signatur löschen."""
        _ensure_mail_signaturen_table()
        try:
            sig_id = int(body.get('id', 0))
            if not sig_id:
                self._json({'ok': False, 'error': 'id fehlt'}); return
            db = get_db()
            db.execute("DELETE FROM mail_signaturen WHERE id=?", (sig_id,))
            db.commit()
            db.close()
            self._json({'ok': True})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_signaturen_default(self, body):
        """POST /api/mail/signaturen/default — Standard-Signatur für ein Konto setzen (id=0 = keine)."""
        _ensure_mail_signaturen_table()
        try:
            konto  = body.get('konto', '').strip()
            sig_id = int(body.get('id', 0))
            if not konto:
                self._json({'ok': False, 'error': 'konto fehlt'}); return
            db = get_db()
            db.execute("UPDATE mail_signaturen SET ist_default=0 WHERE konto=?", (konto,))
            if sig_id:
                db.execute("UPDATE mail_signaturen SET ist_default=1 WHERE id=? AND konto=?", (sig_id, konto))
            db.commit()
            db.close()
            self._json({'ok': True})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    # ── Ende Signaturen ────────────────────────────────────────────────────────

    def _api_mail_konto_stats(self):
        """GET /api/mail/konten/stats?email= — Archiv+Index-Stats für ein Konto."""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        email = qs.get('email', [''])[0]
        try:
            conn = sqlite3.connect(str(MAIL_INDEX_DB))
            if email:
                cnt = conn.execute("SELECT COUNT(*) FROM mails WHERE konto=?", (email,)).fetchone()[0]
            else:
                cnt = conn.execute("SELECT COUNT(*) FROM mails").fetchone()[0]
            conn.close()
            # Archivgröße (schnell: nur Ordner-Check, kein rekursiver Walk)
            archiv_info = {}
            try:
                cfg = json.loads((SCRIPTS_DIR / 'config.json').read_text('utf-8'))
                archiv_pfad = cfg.get('mail_archiv', {}).get('pfad', '')
                if archiv_pfad and email:
                    safe = email.replace('@','_').replace('.','_')
                    konto_pfad = Path(archiv_pfad) / safe
                    if konto_pfad.exists():
                        # Anzahl Unterordner = ca. Mails
                        subdirs = sum(1 for _ in konto_pfad.rglob('mail.json') if True)
                        archiv_info = {'archiviert': subdirs, 'pfad': str(konto_pfad)}
            except Exception:
                pass
            self._json({'ok': True, 'mails_index': cnt, 'archiv': archiv_info})
        except Exception as e:
            self._json({'ok': False, 'error': str(e), 'mails_index': 0})

    def _api_mail_konto_ordner(self):
        """GET /api/mail/konten/ordner?email= — IMAP-Ordner eines Kontos."""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        email = qs.get('email', [''])[0]
        try:
            import sys as _sys
            if str(SCRIPTS_DIR) not in _sys.path:
                _sys.path.insert(0, str(SCRIPTS_DIR))
            import mail_monitor as _mm
            konten = _mm._load_accounts()
            konto = next((k for k in konten if k['email'] == email), None)
            if not konto:
                self._json({'ok': False, 'error': 'Konto nicht gefunden', 'ordner': []})
                return
            imap = _mm.imap_connect(konto)
            _, fl = imap.list()
            imap.logout()
            ordner = []
            for entry in (fl or []):
                if isinstance(entry, bytes):
                    parts = entry.decode(errors='replace').split('"/"')
                    if parts:
                        name = parts[-1].strip().strip('"')
                        ordner.append(name)
            self._json({'ok': True, 'ordner': ordner})
        except Exception as e:
            self._json({'ok': False, 'error': str(e), 'ordner': []})

    def _api_mail_archiv_pruefen(self):
        """GET /api/mail/archiv/pruefen?pfad= — Prüft ob Archivpfad existiert."""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        pfad = qs.get('pfad', [''])[0]
        if not pfad:
            self._json({'ok': False, 'status': 'kein_pfad'})
            return
        p = Path(pfad)
        exists = p.exists() and p.is_dir()
        writeable = False
        if exists:
            try:
                import os
                writeable = os.access(str(p), os.W_OK)
            except Exception:
                pass
        self._json({'ok': exists, 'writeable': writeable, 'status': 'ok' if exists else 'nicht_gefunden'})

    def _api_mail_konto_imap_test(self, body):
        """POST /api/mail/konto/imap-test — Testet IMAP-Verbindung und gibt Ordner zurück."""
        email = body.get('email', '')
        try:
            import sys as _sys
            if str(SCRIPTS_DIR) not in _sys.path:
                _sys.path.insert(0, str(SCRIPTS_DIR))
            import mail_monitor as _mm, time as _time
            konten = _mm._load_accounts()
            konto = next((k for k in konten if k['email'] == email), None)
            if not konto:
                self._json({'ok': False, 'error': 'Konto nicht gefunden'})
                return
            t0 = _time.monotonic()
            imap = _mm.imap_connect(konto)
            _, fl = imap.list()
            imap.logout()
            ms = int((_time.monotonic() - t0) * 1000)
            ordner = []
            for entry in (fl or []):
                if isinstance(entry, bytes):
                    parts = entry.decode(errors='replace').split('"/"')
                    if parts:
                        ordner.append(parts[-1].strip().strip('"'))
            self._json({'ok': True, 'ordner_anzahl': len(ordner), 'dauer_ms': ms, 'ordner': ordner[:20]})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_konto_abrufen(self, body):
        """POST /api/mail/konto/abrufen — Manuellen Poll für ein/alle Konten starten."""
        import threading as _t, sys as _sys
        if str(SCRIPTS_DIR) not in _sys.path:
            _sys.path.insert(0, str(SCRIPTS_DIR))
        import mail_monitor as _mm
        def _do():
            try:
                _mm.poll_all_accounts()
            except Exception:
                pass
        _t.Thread(target=_do, daemon=True).start()
        self._json({'ok': True, 'status': 'gestartet'})

    def _api_mail_konto_alle_abrufen(self, body):
        """POST /api/mail/konto/alle-abrufen — Alle Konten pollen."""
        self._api_mail_konto_abrufen(body)

    def _api_mail_konto_toggle_aktiv(self, body):
        """POST /api/mail/konto/toggle-aktiv — Konto aktivieren/deaktivieren (Archiv bleibt erhalten)."""
        email  = body.get('email', '')
        aktiv  = bool(body.get('aktiv', True))
        archiver_cfg_path = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\raumkult_config.json")
        try:
            cfg = json.loads(archiver_cfg_path.read_text('utf-8'))
            found = False
            for k in cfg.get('konten', []):
                if k.get('email') == email:
                    k['aktiv'] = aktiv
                    found = True
                    break
            if not found:
                self._json({'ok': False, 'error': 'Konto nicht gefunden'})
                return
            archiver_cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
            self._elog(f"Konto {'aktiviert' if aktiv else 'deaktiviert'}: {email}")
            self._json({'ok': True, 'email': email, 'aktiv': aktiv})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_konto_token_loeschen(self, body):
        """POST /api/mail/konto/token-loeschen — OAuth2-Token löschen."""
        email = body.get('email', '')
        try:
            token_dir = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\tokens")
            safe = email.replace('@', '_').replace('.', '_')
            token_file = token_dir / f"{safe}_token.json"
            if token_file.exists():
                token_file.unlink()
                self._json({'ok': True})
            else:
                self._json({'ok': False, 'error': 'Token-Datei nicht gefunden'})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_konto_standard(self, body):
        """POST /api/mail/konto/standard — Standardkonto setzen."""
        email = body.get('email', '')
        try:
            cfg_path = SCRIPTS_DIR / 'config.json'
            cfg = json.loads(cfg_path.read_text('utf-8'))
            cfg.setdefault('mail_konten', {})['standard_konto'] = email
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
            self._json({'ok': True})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_konto_hinzufuegen(self, body):
        """POST /api/mail/konto/hinzufuegen — Neues Konto in raumkult_config.json anlegen."""
        email = body.get('email', '').strip()
        if not email:
            self._json({'ok': False, 'error': 'E-Mail fehlt'})
            return
        try:
            archiver_cfg = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\raumkult_config.json")
            cfg = json.loads(archiver_cfg.read_text('utf-8')) if archiver_cfg.exists() else {'konten': []}
            konten = cfg.setdefault('konten', [])
            # Duplikat-Check
            if any(k.get('email') == email for k in konten):
                self._json({'ok': False, 'error': 'Konto bereits vorhanden'})
                return
            # Passwort obfuskieren (Base64, wie bestehende Konten)
            passwort = body.get('passwort', '')
            if passwort:
                import base64
                passwort = 'enc:' + base64.b64encode(passwort.encode()).decode()
            neues_konto = {
                'email': email,
                'login': body.get('login', email),
                'passwort': passwort,
                'beschreibung': body.get('beschreibung', email.split('@')[0]),
                'aktiv': True,
                'auth_methode': body.get('auth_methode', 'oauth2'),
                'imap_server': body.get('imap_server', 'outlook.office365.com'),
                'imap_port': int(body.get('imap_port', 993)),
                'imap_ssl': bool(body.get('imap_ssl', True)),
            }
            konten.append(neues_konto)
            archiver_cfg.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
            # Sync-Ordner in config.json anlegen
            cfg_kira = json.loads((SCRIPTS_DIR / 'config.json').read_text('utf-8'))
            cfg_kira.setdefault('mail_archiv', {}).setdefault('sync_ordner', {})[email] = ['INBOX', 'Gesendete Elemente']
            (SCRIPTS_DIR / 'config.json').write_text(json.dumps(cfg_kira, ensure_ascii=False, indent=2), 'utf-8')
            self._json({'ok': True})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_einstellungen_get(self):
        """GET /api/einstellungen — Lädt aktuelle Einstellungen inkl. mail_klassifizierung."""
        try:
            secrets_path = SCRIPTS_DIR / 'secrets.json'
            secrets = json.loads(secrets_path.read_text('utf-8')) if secrets_path.exists() else {}
            config_path = SCRIPTS_DIR / 'config.json'
            cfg = json.loads(config_path.read_text('utf-8')) if config_path.exists() else {}
            self._json({
                'ok': True,
                'whatsapp': {
                    'verify_token': secrets.get('whatsapp_verify_token', ''),
                    'phone_number_id': secrets.get('whatsapp_phone_number_id', ''),
                },
                'mail_klassifizierung': cfg.get('mail_klassifizierung', {}),
                'mail_postfach': {**{'refresh_intervall_min': 0, 'lese_markierung': 'sofort'}, **cfg.get('mail_postfach', {})},
            })
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_provider_detect(self):
        """GET /api/mail/provider-detect?email= — 3-stufige Anbieter-Erkennung."""
        try:
            import sys as _sys
            if str(SCRIPTS_DIR) not in _sys.path:
                _sys.path.insert(0, str(SCRIPTS_DIR))
            import mail_monitor as _mm
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            email = qs.get('email', [''])[0]
            # Erweiterte 3-stufige Erkennung
            result = _mm.detect_provider_advanced(email)
            self._json({'ok': True, **result})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_konto_oauth_start(self, body):
        """POST /api/mail/konto/oauth-start — Browser-OAuth starten, gibt job_id zurück."""
        import uuid, sys as _sys
        if str(SCRIPTS_DIR) not in _sys.path:
            _sys.path.insert(0, str(SCRIPTS_DIR))
        import mail_monitor as _mm
        email = body.get('email', '').strip()
        if not email:
            self._json({'ok': False, 'error': 'E-Mail fehlt'})
            return
        job_id = str(uuid.uuid4())[:8]
        _mm.start_oauth_browser_flow(email, job_id)
        self._json({'ok': True, 'job_id': job_id, 'email': email})

    def _api_mail_konto_oauth_status(self):
        """GET /api/mail/konto/oauth-status?job_id= — OAuth-Job-Status abfragen."""
        try:
            import sys as _sys
            if str(SCRIPTS_DIR) not in _sys.path:
                _sys.path.insert(0, str(SCRIPTS_DIR))
            import mail_monitor as _mm
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            job_id = qs.get('job_id', [''])[0]
            status = _mm.get_oauth_job_status(job_id)
            self._json({'ok': True, **status})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_konto_reconnect(self, body):
        """POST /api/mail/konto/reconnect — Bestehendes Konto mit Browser-OAuth neu verbinden."""
        import uuid, sys as _sys
        if str(SCRIPTS_DIR) not in _sys.path:
            _sys.path.insert(0, str(SCRIPTS_DIR))
        import mail_monitor as _mm
        email = body.get('email', '').strip()
        if not email:
            self._json({'ok': False, 'error': 'E-Mail fehlt'})
            return
        # Token-Cache löschen damit frischer Login erzwungen wird
        try:
            cache_p = _mm._token_cache_path(email)
            if cache_p.exists():
                cache_p.unlink()
        except Exception:
            pass
        # Neuen OAuth-Job starten
        job_id = str(uuid.uuid4())[:8]
        _mm.start_oauth_browser_flow(email, job_id)
        self._json({'ok': True, 'job_id': job_id, 'email': email, 'aktion': 'reconnect'})

    def _api_mail_konto_health(self):
        """GET /api/mail/konto/health — Health-Status aller Konten (gecacht)."""
        try:
            import sys as _sys
            if str(SCRIPTS_DIR) not in _sys.path:
                _sys.path.insert(0, str(SCRIPTS_DIR))
            import mail_monitor as _mm
            health = _mm.get_all_health_status()
            self._json({'ok': True, 'health': health})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_konto_health_check(self, body):
        """POST /api/mail/konto/health-check — Sofortige echte Verbindungsprüfung."""
        import threading as _t, sys as _sys
        if str(SCRIPTS_DIR) not in _sys.path:
            _sys.path.insert(0, str(SCRIPTS_DIR))
        import mail_monitor as _mm
        email = body.get('email', '').strip()
        if not email:
            self._json({'ok': False, 'error': 'E-Mail fehlt'})
            return
        # In Thread starten (kann 5-10s dauern)
        def _do():
            _mm.check_account_health(email)
        _t.Thread(target=_do, daemon=True).start()
        self._json({'ok': True, 'status': 'gestartet', 'email': email})

    def _api_browse_folder(self):
        """GET /api/browse/folder — Öffnet nativen OS-Ordner-Auswahldialog (tkinter)."""
        import threading, uuid
        job_id = str(uuid.uuid4())[:8]
        _BROWSE_RESULTS[job_id] = None
        def _pick():
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.wm_attributes('-topmost', 1)
                path = filedialog.askdirectory(title='Ordner wählen')
                root.destroy()
                _BROWSE_RESULTS[job_id] = path or ''
            except Exception as e:
                _BROWSE_RESULTS[job_id] = ''
        threading.Thread(target=_pick, daemon=True).start()
        self._json({'ok': True, 'job_id': job_id})

    def _api_browse_result(self):
        """GET /api/browse/result?job_id= — Ergebnis des Ordner-Dialogs."""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        job_id = qs.get('job_id', [''])[0]
        result = _BROWSE_RESULTS.get(job_id)
        if result is None:
            self._json({'done': False})
        else:
            del _BROWSE_RESULTS[job_id]
            self._json({'done': True, 'path': result})

    def _api_mail_konto_display_name(self, body):
        """POST /api/mail/konto/display-name — Setzt benutzerdefinierten Anzeigenamen für ein Konto."""
        email = body.get('email', '').strip()
        name  = body.get('name', '').strip()
        if not email:
            self._json({'ok': False, 'error': 'E-Mail fehlt'})
            return
        try:
            cfg_path = SCRIPTS_DIR / 'config.json'
            cfg = json.loads(cfg_path.read_text('utf-8')) if cfg_path.exists() else {}
            if 'mail_konto_labels' not in cfg:
                cfg['mail_konto_labels'] = {}
            if name:
                cfg['mail_konto_labels'][email] = name
            else:
                cfg['mail_konto_labels'].pop(email, None)
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
            self._json({'ok': True, 'email': email, 'name': name})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_konto_volltest_start(self, body):
        """POST /api/mail/konto/volltest — Volltest starten (IMAP + SMTP + Roundtrip)."""
        import uuid, sys as _sys
        if str(SCRIPTS_DIR) not in _sys.path:
            _sys.path.insert(0, str(SCRIPTS_DIR))
        import mail_monitor as _mm
        email = body.get('email', '').strip()
        if not email:
            self._json({'ok': False, 'error': 'E-Mail fehlt'})
            return
        job_id = str(uuid.uuid4())[:8]
        _mm.start_volltest(email, job_id)
        self._json({'ok': True, 'job_id': job_id, 'email': email, 'hinweis': 'Volltest läuft (IMAP + SMTP + 30s Roundtrip). ca. 45s.'})

    def _api_mail_konto_volltest_status(self):
        """GET /api/mail/konto/volltest-status?job_id= — Volltest-Status abfragen."""
        try:
            import sys as _sys
            if str(SCRIPTS_DIR) not in _sys.path:
                _sys.path.insert(0, str(SCRIPTS_DIR))
            import mail_monitor as _mm
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            job_id = qs.get('job_id', [''])[0]
            status = _mm.get_volltest_status(job_id)
            self._json({'ok': True, **status})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_mail_nachklassifizieren(self, body):
        """POST /api/mail/nachklassifizieren — Mail-Nachklassifizierung starten."""
        import threading as _threading, sys as _sys
        if str(SCRIPTS_DIR) not in _sys.path:
            _sys.path.insert(0, str(SCRIPTS_DIR))
        seit  = (body.get('seit') or '').strip()
        bis   = body.get('bis') or None
        trocken = bool(body.get('trocken', False))
        if not seit:
            self._json({'ok': False, 'error': 'seit-Datum fehlt (Format: YYYY-MM-DD)'})
            return
        try:
            datetime.strptime(seit, '%Y-%m-%d')
        except ValueError:
            self._json({'ok': False, 'error': f'Ungültiges Datum: {seit}'})
            return
        # Laufenden Job abweisen
        try:
            from daily_check import get_recheck_progress as _grp
            if _grp().get('running', False):
                self._json({'ok': False, 'error': 'Nachklassifizierung läuft bereits'})
                return
        except Exception:
            pass
        def _run():
            try:
                from daily_check import recheck_mails
                recheck_mails(seit, bis, trocken)
            except Exception as ex:
                import logging
                logging.getLogger('server').error(f'Nachklassifizierung-Fehler: {ex}')
        _threading.Thread(target=_run, daemon=True).start()
        self._json({'ok': True, 'status': 'gestartet', 'seit': seit, 'bis': bis, 'trocken': trocken})

    def _api_mail_nachklassifizieren_status(self):
        """GET /api/mail/nachklassifizieren/status — Fortschritt abfragen."""
        try:
            import sys as _sys
            if str(SCRIPTS_DIR) not in _sys.path:
                _sys.path.insert(0, str(SCRIPTS_DIR))
            from daily_check import get_recheck_progress
            self._json(get_recheck_progress())
        except Exception as e:
            self._json({'running': False, 'finished': True, 'error': str(e)})

    def _api_mail_microsoft_app_test(self):
        """POST /api/mail/microsoft-app/test — Zentrale KIRA Entra App auf Erreichbarkeit testen."""
        try:
            import sys as _sys
            if str(SCRIPTS_DIR) not in _sys.path:
                _sys.path.insert(0, str(SCRIPTS_DIR))
            import mail_monitor as _mm
            result = _mm.test_microsoft_app()
            self._json({'ok': result['ok'], **result})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_whatsapp_secrets_speichern(self, body):
        """POST /api/whatsapp/secrets-speichern — WhatsApp-Credentials in secrets.json speichern."""
        try:
            secrets_path = SCRIPTS_DIR / 'secrets.json'
            secrets = json.loads(secrets_path.read_text('utf-8')) if secrets_path.exists() else {}
            if 'whatsapp_verify_token' in body:
                secrets['whatsapp_verify_token'] = body['whatsapp_verify_token']
            if 'whatsapp_app_secret' in body:
                secrets['whatsapp_app_secret'] = body['whatsapp_app_secret']
            if 'whatsapp_phone_number_id' in body:
                secrets['whatsapp_phone_number_id'] = body['whatsapp_phone_number_id']
            secrets_path.write_text(json.dumps(secrets, ensure_ascii=False, indent=2), 'utf-8')
            # Auch phone_number_id in config.json
            cfg_path = SCRIPTS_DIR / 'config.json'
            cfg = json.loads(cfg_path.read_text('utf-8'))
            if 'whatsapp_phone_number_id' in body:
                cfg.setdefault('whatsapp', {})['phone_number_id'] = body['whatsapp_phone_number_id']
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), 'utf-8')
            self._json({'ok': True})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})

    def _api_ausgangsrechnungen(self):
        """GET /api/ausgangsrechnungen — Listet Ausgangsrechnungen."""
        db = get_db()
        try:
            rows = db.execute("SELECT * FROM ausgangsrechnungen ORDER BY datum DESC").fetchall()
            self._json([dict(r) for r in rows])
        except:
            self._json([])
        finally:
            db.close()

    def _api_angebote(self):
        """GET /api/angebote — Listet Angebote."""
        db = get_db()
        try:
            rows = db.execute("SELECT * FROM angebote ORDER BY datum DESC").fetchall()
            self._json([dict(r) for r in rows])
        except:
            self._json([])
        finally:
            db.close()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        raw_body = self.rfile.read(length) or b'{}'
        self._raw_post_body = raw_body  # für HMAC-Prüfung (WhatsApp)
        body   = json.loads(raw_body)

        if self.path == '/api/mail/oauth/connect':
            self._api_mail_oauth_connect(body)
            return

        if self.path == '/api/mail/archiv/reindex':
            self._api_mail_archiv_reindex(body)
            return

        if self.path == '/api/mail/archiv/sync-ordner':
            self._api_mail_archiv_sync_ordner(body)
            return

        if self.path == '/api/mail/konto/postfach-ordner':
            self._api_mail_konto_postfach_ordner(body)
            return

        if self.path == '/api/mail/verschieben':
            self._api_mail_verschieben(body)
            return

        if self.path == '/api/mail/send':
            self._api_mail_send(body)
            return

        # Mail-HITL-Approve-Queue (Paket 2, session-oo)
        if self.path.startswith('/api/mail/approve/') and self.path != '/api/mail/approve/pending':
            parts = self.path.split('/')
            try:
                queue_id = int(parts[-1])
            except (ValueError, IndexError):
                self._json({'ok': False, 'error': 'Ungültige Queue-ID'})
                return
            self._api_mail_approve_action(queue_id, body)
            return

        if self.path == '/api/mail/konto/imap-test':
            self._api_mail_konto_imap_test(body)
            return

        if self.path in ('/api/mail/konto/abrufen', '/api/mail/monitor/trigger'):
            self._api_mail_konto_abrufen(body)
            return

        if self.path == '/api/mail/konto/alle-abrufen':
            self._api_mail_konto_alle_abrufen(body)
            return

        if self.path == '/api/mail/konto/token-loeschen':
            self._api_mail_konto_token_loeschen(body)
            return

        if self.path == '/api/mail/konto/toggle-aktiv':
            self._api_mail_konto_toggle_aktiv(body)
            return

        if self.path == '/api/mail/favorites':
            self._api_mail_favorites_set(body)
            return

        if self.path == '/api/mail/gelesen':
            self._api_mail_gelesen(body)
            return

        if self.path == '/api/mail/flag':
            self._api_mail_flag(body)
            return

        if self.path == '/api/mail/pin':
            self._api_mail_pin(body)
            return

        if self.path == '/api/mail/loeschen':
            self._api_mail_loeschen(body)
            return

        if self.path == '/api/mail/snooze':
            self._api_mail_snooze(body)
            return

        if self.path == '/api/mail/kira-markieren':
            self._api_mail_kira_markieren(body)
            return

        if self.path == '/api/mail/combined/konten':
            self._api_mail_combined_konten_set(body)
            return

        if self.path == '/api/mail/konto/standard':
            self._api_mail_konto_standard(body)
            return

        if self.path == '/api/mail/konto/hinzufuegen':
            self._api_mail_konto_hinzufuegen(body)
            return

        if self.path == '/api/mail/konto/oauth-start':
            self._api_mail_konto_oauth_start(body)
            return

        if self.path == '/api/mail/konto/reconnect':
            self._api_mail_konto_reconnect(body)
            return

        if self.path == '/api/mail/konto/health-check':
            self._api_mail_konto_health_check(body)
            return

        if self.path == '/api/mail/konto/display-name':
            self._api_mail_konto_display_name(body)
            return

        if self.path == '/api/mail/konto/volltest':
            self._api_mail_konto_volltest_start(body)
            return

        if self.path == '/api/mail/nachklassifizieren':
            self._api_mail_nachklassifizieren(body)
            return

        if self.path == '/api/mail/microsoft-app/test':
            self._api_mail_microsoft_app_test()
            return

        if self.path == '/api/mail/signaturen/save':
            self._api_mail_signaturen_save(body)
            return

        if self.path == '/api/mail/signaturen/delete':
            self._api_mail_signaturen_delete(body)
            return

        if self.path == '/api/mail/signaturen/default':
            self._api_mail_signaturen_default(body)
            return

        if self.path == '/api/whatsapp/secrets-speichern':
            self._api_whatsapp_secrets_speichern(body)
            return

        # Server-Neustart: alle Port-8765-Instanzen beenden, dann neu starten
        if self.path == '/api/server/neustart':
            alog("Server", "Neustart", "Nutzer-initiiert via UI", "ok")
            self._json({'ok': True, 'message': 'Server wird neu gestartet …'})
            import subprocess, threading, sys, os
            exe = sys.executable
            script = os.path.abspath(__file__)
            _NO_WIN = 0x08000000  # CREATE_NO_WINDOW — kein Terminalfenster
            def _restart():
                import time; time.sleep(0.5)
                # Kill ALLE Prozesse auf Port 8765 (inkl. eigene)
                r = subprocess.run(['netstat','-ano'], capture_output=True,
                                   text=True, encoding='utf-8', errors='replace',
                                   creationflags=_NO_WIN)
                my_pid = os.getpid()
                for line in r.stdout.splitlines():
                    if f':{PORT}' in line:
                        parts = line.split()
                        if parts and parts[-1].isdigit():
                            pid = int(parts[-1])
                            if pid != my_pid:
                                subprocess.run(['taskkill','/F','/PID',str(pid)],
                                               capture_output=True, creationflags=_NO_WIN)
                time.sleep(0.8)
                subprocess.Popen([exe, script],
                                 creationflags=0x00000008 | _NO_WIN,  # DETACHED + NO_WIN
                                 close_fds=True)
                time.sleep(0.2)
                os.kill(my_pid, 9)
            threading.Thread(target=_restart, daemon=True).start()
            return

        # Runtime-Log: UI-Ereignisse vom Browser empfangen
        if self.path == '/api/runtime/event':
            try:
                rlog(
                    body.get('event_type', 'ui'),
                    body.get('action', 'ui_event'),
                    body.get('summary', ''),
                    session_id=body.get('session_id'),
                    source=body.get('source', 'browser'),
                    modul=body.get('modul', 'ui'),
                    submodul=body.get('submodul'),
                    actor_type=body.get('actor_type', 'user'),
                    context_type=body.get('context_type'),
                    context_id=body.get('context_id'),
                    status=body.get('status', 'ok'),
                    result=body.get('result'),
                )
                self._json({'ok': True})
            except Exception as ex:
                self._json({'ok': False, 'error': str(ex)})
            return

        # Runtime-Log leeren
        if self.path == '/api/runtime/clear':
            try:
                from runtime_log import _clear_all
                _clear_all()
                self._json({'ok': True})
            except Exception as ex:
                self._json({'ok': False, 'error': str(ex)})
            return

        # Kira-Feedback (Paket 6, session-oo)
        if self.path == '/api/kira/feedback':
            self._api_kira_feedback(body)
            return

        # ReAct-Task starten (Paket 5, session-oo)
        if self.path == '/api/kira/task':
            aufgabe = body.get('aufgabe', '').strip()
            max_rounds = int(body.get('max_rounds', 5))
            if not aufgabe:
                self._json({'error': 'aufgabe erforderlich'})
                return
            try:
                task_id = start_react_task(aufgabe, max_rounds=max_rounds)
                self._json({'ok': True, 'task_id': task_id, 'status': 'running'})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # ReAct-Task abbrechen
        if self.path.startswith('/api/kira/task/') and self.path.endswith('/cancel'):
            parts = self.path.split('/')
            task_id = parts[4] if len(parts) >= 5 else ''
            try:
                ok = cancel_react_task(task_id) if task_id else False
                self._json({'ok': ok})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # Kira Chat (LLM)
        if self.path == '/api/kira/chat':
            nachricht = body.get('nachricht', '').strip()
            if not nachricht:
                self._json({'error': 'Keine Nachricht'})
                return
            session_id = body.get('session_id')
            try:
                result = kira_chat(nachricht, session_id)
                self._json(result)
            except Exception as e:
                self._json({'error': f'Chat-Fehler: {str(e)}'})
            return

        # Kira Proaktiver Scan (manuell auslösen)
        if self.path == '/api/kira/proaktiv/scan':
            self._api_kira_proaktiv_scan()
            return

        # Kira API Key speichern (Legacy-Compat + neuer Weg)
        if self.path == '/api/kira/api-key':
            key = body.get('api_key', '').strip()
            pid = body.get('provider_id', '')
            if not key:
                self._json({'ok': False, 'error': 'Kein Key angegeben'})
                return
            if pid:
                save_provider_key(pid, key)
            else:
                secrets_path = SCRIPTS_DIR / "secrets.json"
                secrets = {}
                try: secrets = json.loads(secrets_path.read_text('utf-8'))
                except: pass
                secrets['anthropic_api_key'] = key
                secrets_path.write_text(json.dumps(secrets, ensure_ascii=False, indent=2), 'utf-8')
            self._json({'ok': True})
            return

        # Provider Key speichern
        if self.path == '/api/kira/provider/save-key':
            pid = body.get('provider_id', '').strip()
            key = body.get('api_key', '').strip()
            if not pid or not key:
                self._json({'ok': False, 'error': 'Provider-ID und Key erforderlich'})
                return
            save_provider_key(pid, key)
            self._json({'ok': True})
            return

        # Provider hinzufügen
        if self.path == '/api/kira/provider/add':
            typ = body.get('typ', '').strip()
            name = body.get('name', '').strip()
            if typ not in PROVIDER_TYPES:
                self._json({'ok': False, 'error': 'Unbekannter Provider-Typ'})
                return
            ptype = PROVIDER_TYPES[typ]
            if not name:
                name = ptype["name"]
            try:
                c = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
            except: c = {}
            llm = c.setdefault("llm", {})
            providers = llm.setdefault("providers", [])
            max_prio = max((p.get("prioritaet", 0) for p in providers), default=0)
            pid = f"{typ}-{len(providers)+1}-{int(datetime.now().timestamp())}"
            new_p = {
                "id": pid,
                "typ": typ,
                "name": name,
                "model": ptype.get("default_model", ""),
                "aktiv": True,
                "prioritaet": max_prio + 1,
            }
            if typ == "custom":
                new_p["base_url"] = ""
            providers.append(new_p)
            (SCRIPTS_DIR / "config.json").write_text(json.dumps(c, ensure_ascii=False, indent=2), 'utf-8')
            self._json({'ok': True, 'provider_id': pid})
            return

        # Provider aktivieren/deaktivieren
        if self.path == '/api/kira/provider/toggle':
            pid = body.get('provider_id', '')
            aktiv = body.get('aktiv', True)
            try:
                c = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
                for p in c.get("llm", {}).get("providers", []):
                    if p.get("id") == pid:
                        p["aktiv"] = bool(aktiv)
                        break
                (SCRIPTS_DIR / "config.json").write_text(json.dumps(c, ensure_ascii=False, indent=2), 'utf-8')
                self._json({'ok': True})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # Provider Priorität verschieben
        if self.path == '/api/kira/provider/move':
            pid = body.get('provider_id', '')
            direction = body.get('direction', 0)  # -1 = höher, +1 = niedriger
            try:
                c = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
                providers = c.get("llm", {}).get("providers", [])
                providers.sort(key=lambda p: p.get("prioritaet", 99))
                idx = next((i for i, p in enumerate(providers) if p.get("id") == pid), None)
                if idx is not None:
                    new_idx = max(0, min(len(providers)-1, idx + direction))
                    if new_idx != idx:
                        providers.insert(new_idx, providers.pop(idx))
                        for i, p in enumerate(providers):
                            p["prioritaet"] = i + 1
                        c["llm"]["providers"] = providers
                        (SCRIPTS_DIR / "config.json").write_text(json.dumps(c, ensure_ascii=False, indent=2), 'utf-8')
                self._json({'ok': True})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # Provider löschen
        if self.path == '/api/kira/provider/delete':
            pid = body.get('provider_id', '')
            try:
                c = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
                providers = c.get("llm", {}).get("providers", [])
                c["llm"]["providers"] = [p for p in providers if p.get("id") != pid]
                # Re-number priorities
                for i, p in enumerate(c["llm"]["providers"]):
                    p["prioritaet"] = i + 1
                (SCRIPTS_DIR / "config.json").write_text(json.dumps(c, ensure_ascii=False, indent=2), 'utf-8')
                self._json({'ok': True})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # Modell-Verfügbarkeit prüfen (sofort + Auto-Update)
        if self.path == '/api/kira/provider/check-models':
            pid = body.get('provider_id', '').strip()
            try:
                all_provs = get_all_providers()
                if pid:
                    provs = [p for p in all_provs if p.get("id") == pid]
                else:
                    provs = [p for p in all_provs if p.get("aktiv", True)]
                if not provs:
                    self._json({'ok': False, 'error': 'Provider nicht gefunden'})
                    return
                results = {}
                for p in provs:
                    vr = _validate_model(p)
                    if not vr.get('valid') and not vr.get('skipped'):
                        vr['auto_update'] = _auto_update_model(p)
                    results[p.get('id', p.get('typ'))] = vr
                # Direkt zurückgeben (state-file wird in validate_all_providers geschrieben,
                # hier nur Einzel-Ergebnis)
                single = results.get(pid, next(iter(results.values()), {})) if pid else results
                self._json({'ok': True, 'result': single, 'all': results})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # Task actions
        m = re.match(r'/api/task/(\d+)/(\w[\w-]*)', self.path)
        if m:
            task_id = int(m.group(1))
            action  = m.group(2)
            self._handle_task_action(task_id, action, body)
            return

        # Neue Regel anlegen
        if self.path == '/api/wissen/neu':
            db = get_db()
            try:
                kat    = body.get('kategorie','vorschlag')
                titel  = body.get('titel','').strip()
                inhalt = body.get('inhalt','').strip()
                if not titel or not inhalt:
                    self._json({'ok': False, 'error': 'Titel und Inhalt erforderlich'})
                    return
                db.execute("INSERT INTO wissen_regeln (kategorie,titel,inhalt,status) VALUES (?,?,?,'aktiv')",
                           (kat, titel, inhalt))
                db.commit()
                self._json({'ok': True})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            finally:
                db.close()
            return

        # Wissen actions
        m2 = re.match(r'/api/wissen/(\d+)/(\w+)', self.path)
        if m2:
            regel_id = int(m2.group(1))
            aktion   = m2.group(2)
            self._handle_wissen_action(regel_id, aktion, body)
            return

        # Server Shutdown
        if self.path == '/api/shutdown':
            self._json({'ok': True})
            stop_monitor()
            threading.Timer(0.5, lambda: os._exit(0)).start()
            return

        # Geschäft actions
        m3 = re.match(r'/api/geschaeft/(\d+)/(\w+)', self.path)
        if m3:
            gid    = int(m3.group(1))
            aktion = m3.group(2)
            self._handle_geschaeft_action(gid, aktion, body)
            return

        # Ausgangsrechnung actions
        m4 = re.match(r'/api/ausgangsrechnung/(\d+)/(\w+)', self.path)
        if m4:
            ar_id = int(m4.group(1))
            aktion = m4.group(2)
            db = get_db()
            try:
                if aktion == 'status':
                    new_status = body.get('status', '')
                    now = body.get('zeitstempel') or datetime.now().isoformat()
                    bezahlt_am = body.get('datum', now[:10])
                    betrag_bezahlt = body.get('betrag', '')
                    betrag_voll = body.get('betrag-voll', 'ja')
                    grund = body.get('grund', '')
                    notiz = body.get('notiz', '')
                    # Hole RE-Nummer für Wissenseintrag
                    ar_row = db.execute("SELECT re_nummer, kunde_name, kunde_email, betrag_brutto FROM ausgangsrechnungen WHERE id=?", (ar_id,)).fetchone()
                    re_nr = ar_row['re_nummer'] if ar_row else f'#{ar_id}'
                    kunde = (ar_row['kunde_name'] or ar_row['kunde_email'] or 'Unbekannt') if ar_row else 'Unbekannt'
                    betrag_orig = ar_row['betrag_brutto'] if ar_row else 0
                    if new_status == 'bezahlt':
                        db.execute("UPDATE ausgangsrechnungen SET status='bezahlt', bezahlt_am=?, notiz=? WHERE id=?",
                                   (bezahlt_am, notiz, ar_id))
                    elif new_status in ('streitfall', 'offen'):
                        db.execute("UPDATE ausgangsrechnungen SET status=?, notiz=? WHERE id=?",
                                   (new_status, notiz, ar_id))
                    # ALLE Interaktionsdaten strukturiert speichern
                    daten = {k: v for k, v in body.items() if k not in ('status',)}
                    daten['zeitstempel'] = now
                    daten['re_nummer'] = re_nr
                    daten['kunde'] = kunde
                    db.execute("INSERT INTO geschaeft_statistik (typ,referenz_id,ereignis,daten_json,erstellt_am) VALUES (?,?,?,?,?)",
                               ('ausgangsrechnung', ar_id, f'status_{new_status}', json.dumps(daten, ensure_ascii=False), now))
                    # Strukturierte Erkenntnisse in Wissenspeicher
                    wissen_parts = []
                    if new_status == 'bezahlt':
                        wissen_parts.append(f'Rechnung {re_nr} ({kunde}) am {bezahlt_am} bezahlt.')
                        if betrag_voll == 'nein' and betrag_bezahlt:
                            wissen_parts.append(f'Nur {betrag_bezahlt} EUR statt {betrag_orig} EUR.')
                        if grund:
                            wissen_parts.append(f'Grund: {grund}')
                        # Zahlungsdauer berechnen
                        try:
                            r_datum = ar_row['datum'] if ar_row else None
                            if r_datum:
                                from datetime import timedelta
                                d1 = datetime.strptime(str(r_datum)[:10], "%Y-%m-%d")
                                d2 = datetime.strptime(bezahlt_am[:10], "%Y-%m-%d")
                                tage = (d2 - d1).days
                                wissen_parts.append(f'Zahlungsdauer: {tage} Tage.')
                                daten['zahlungsdauer_tage'] = tage
                        except: pass
                    elif new_status == 'streitfall':
                        wissen_parts.append(f'Rechnung {re_nr} ({kunde}) als Streitfall markiert.')
                        if grund:
                            wissen_parts.append(f'Grund: {grund}')
                    if notiz:
                        wissen_parts.append(f'Notiz: {notiz}')
                    if wissen_parts:
                        titel = f'{re_nr} ({kunde}): {new_status}'
                        inhalt = ' '.join(wissen_parts)
                        db.execute("INSERT INTO wissen_regeln (kategorie,titel,inhalt,quelle,erstellt_am) VALUES (?,?,?,?,?)",
                                   ('gelernt', titel, inhalt, f'Kira-Interaktion: {re_nr}', now))
                    db.commit()
                    self._json({'ok': True})
                else:
                    self._respond(404, 'text/plain', b'Not found')
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            finally:
                db.close()
            return

        # Angebot actions
        m5 = re.match(r'/api/angebot/(\d+)/(\w+)', self.path)
        if m5:
            ang_id = int(m5.group(1))
            aktion = m5.group(2)
            db = get_db()
            try:
                if aktion == 'status':
                    new_status = body.get('status', '')
                    now = body.get('zeitstempel') or datetime.now().isoformat()
                    grund = body.get('grund', '') or body.get('detail', '')
                    wie = body.get('wie', '')
                    notiz = body.get('notiz', '')
                    nachfass_count = body.get('nachfass', '')
                    # Hole Angebot-Daten für Wissenseintrag
                    ang_row = db.execute("SELECT a_nummer, kunde_name, kunde_email, betrag_geschaetzt FROM angebote WHERE id=?", (ang_id,)).fetchone()
                    a_nr = ang_row['a_nummer'] if ang_row else f'#{ang_id}'
                    kunde = (ang_row['kunde_name'] or ang_row['kunde_email'] or 'Unbekannt') if ang_row else 'Unbekannt'
                    if new_status in ('angenommen', 'abgelehnt', 'keine_antwort', 'offen', 'bearbeitet'):
                        db.execute("UPDATE angebote SET status=? WHERE id=?", (new_status, ang_id))
                        if new_status == 'abgelehnt':
                            db.execute("UPDATE angebote SET grund_abgelehnt=? WHERE id=?", (grund, ang_id))
                        elif new_status == 'angenommen':
                            full_grund = (wie + ' ' + notiz).strip()
                            db.execute("UPDATE angebote SET grund_angenommen=? WHERE id=?", (full_grund, ang_id))
                    # ALLE Interaktionsdaten strukturiert speichern
                    daten = {k: v for k, v in body.items() if k not in ('status',)}
                    daten['zeitstempel'] = now
                    daten['a_nummer'] = a_nr
                    daten['kunde'] = kunde
                    db.execute("INSERT INTO geschaeft_statistik (typ,referenz_id,ereignis,daten_json,erstellt_am) VALUES (?,?,?,?,?)",
                               ('angebot', ang_id, f'status_{new_status}', json.dumps(daten, ensure_ascii=False), now))
                    # Strukturierte Erkenntnisse in Wissenspeicher
                    wissen_parts = []
                    if new_status == 'angenommen':
                        wissen_parts.append(f'Angebot {a_nr} ({kunde}) angenommen.')
                        if wie:
                            wissen_parts.append(f'Wie kam es dazu: {wie}')
                    elif new_status == 'abgelehnt':
                        wissen_parts.append(f'Angebot {a_nr} ({kunde}) abgelehnt.')
                        if grund:
                            wissen_parts.append(f'Hauptgrund: {grund}')
                    elif new_status == 'keine_antwort':
                        wissen_parts.append(f'Angebot {a_nr} ({kunde}): Keine Antwort erhalten.')
                        if nachfass_count:
                            wissen_parts.append(f'Nachgefasst: {nachfass_count}x')
                    if notiz:
                        wissen_parts.append(f'Notiz: {notiz}')
                    if wissen_parts:
                        titel = f'{a_nr} ({kunde}): {new_status}'
                        inhalt = ' '.join(wissen_parts)
                        db.execute("INSERT INTO wissen_regeln (kategorie,titel,inhalt,quelle,erstellt_am) VALUES (?,?,?,?,?)",
                                   ('gelernt', titel, inhalt, f'Kira-Interaktion: {a_nr}', now))
                    db.commit()
                    self._json({'ok': True})
                else:
                    self._respond(404, 'text/plain', b'Not found')
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            finally:
                db.close()
            return

        # Einstellungen speichern
        if self.path == '/api/einstellungen':
            try:
                config_path = SCRIPTS_DIR / "config.json"
                old = {}
                try: old = json.loads(config_path.read_text('utf-8'))
                except: pass
                # Merge: keep _kommentar and _anleitung fields
                merged = {**old, **body}
                for key in body:
                    if isinstance(body[key], dict) and isinstance(old.get(key), dict):
                        merged[key] = {**old[key], **body[key]}
                # Provider-Updates aus llm._provider_updates anwenden
                llm_section = merged.get("llm", {})
                provider_updates = llm_section.pop("_provider_updates", None)
                if provider_updates and "providers" in llm_section:
                    prov_map = {p["id"]: p for p in llm_section["providers"]}
                    for upd in provider_updates:
                        pid = upd.get("id", "")
                        if pid in prov_map:
                            if upd.get("model"):
                                prov_map[pid]["model"] = upd["model"]
                            if upd.get("base_url") is not None:
                                prov_map[pid]["base_url"] = upd["base_url"]
                config_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), 'utf-8')
                rlog('settings', 'einstellungen_gespeichert', 'Einstellungen via UI gespeichert',
                     source='server', modul='einstellungen', actor_type='user', status='ok',
                     settings_after=json.dumps({k: v for k, v in merged.items()
                                                if k not in ('llm',)}, ensure_ascii=False)[:2000])
                self._json({'ok': True})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # ntfy Test-Push
        if self.path == '/api/ntfy/test':
            try:
                import urllib.request as _urlreq
                topic  = (body.get('topic') or '').strip()
                server = (body.get('server') or 'https://ntfy.sh').rstrip('/')
                if not topic:
                    self._json({'ok': False, 'error': 'Kein Topic angegeben'})
                    return
                url = f"{server}/{topic}"
                req = _urlreq.Request(
                    url,
                    data='Kira Test-Push: Verbindung erfolgreich! \u2728'.encode('utf-8'),
                    headers={'Content-Type': 'text/plain; charset=utf-8',
                             'Title': 'Kira Assistenz', 'Priority': 'default'},
                    method='POST')
                with _urlreq.urlopen(req, timeout=8) as resp:
                    st = resp.status
                self._json({'ok': st < 300})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # Partner-View: Leni-Feedback als GitHub-Issue anlegen
        if self.path == '/api/partner/feedback-issue':
            try:
                import urllib.request as _urllib
                secrets_path = SCRIPTS_DIR / 'secrets.json'
                try:
                    secrets = json.loads(secrets_path.read_text('utf-8'))
                except Exception:
                    secrets = {}
                token = secrets.get('partner_feedback_token', '')
                if not token:
                    self._json({'ok': False, 'error': 'partner_feedback_token fehlt in secrets.json'})
                    return
                gh_owner = body.get('gh_owner', 'kaimarienfeld')
                gh_repo  = body.get('gh_repo', 'kira-partner')
                feature  = body.get('featureName') or body.get('featureId', '?')
                react    = body.get('react', '')
                text     = body.get('text', '')
                date     = body.get('date', '')
                title    = f"[Feedback] {feature}" + (f" — {react}" if react else "")
                issue_body = "\n\n".join([
                    f"**Funktion:** {feature}",
                    f"**Reaktion:** {react or '(keine)'}",
                    f"**Feedback:**\n{text or '(kein Text)'}",
                    f"**Datum:** {date}",
                    f"**Feature-ID:** `{body.get('featureId','?')}`",
                ])
                payload = json.dumps({'title': title, 'body': issue_body, 'labels': ['leni-feedback']}).encode('utf-8')
                req = _urllib.Request(
                    f'https://api.github.com/repos/{gh_owner}/{gh_repo}/issues',
                    data=payload,
                    headers={
                        'Authorization': f'Bearer {token}',
                        'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2022-11-28',
                        'Content-Type': 'application/json',
                    },
                    method='POST'
                )
                with _urllib.urlopen(req, timeout=10) as resp:
                    result = json.loads(resp.read())
                issue_url = result.get('html_url', '')
                issue_nr  = result.get('number', '')
                # E-Mail an Kai senden
                try:
                    import smtplib, ssl as _ssl2
                    from email.mime.text import MIMEText as _MIMEText
                    mail_cfg2  = CFG.get('email_notification', {})
                    smtp_srv   = mail_cfg2.get('smtp_server', '')
                    smtp_prt   = int(mail_cfg2.get('smtp_port', 587))
                    kai_addr   = mail_cfg2.get('absender_email', '')
                    kai_pw     = mail_cfg2.get('absender_passwort', '')
                    if smtp_srv and kai_addr:
                        issues_url = f'https://github.com/{gh_owner}/{gh_repo}/issues'
                        mail_text = (
                            f"Leni hat Feedback gegeben!\n\n"
                            f"Funktion:  {feature}\n"
                            f"Reaktion:  {react or '(keine)'}\n"
                            f"Feedback:  {text or '(kein Text)'}\n"
                            f"Datum:     {date}\n\n"
                            f"Direkt zum Issue #{issue_nr}:\n{issue_url}\n\n"
                            f"Alle Feedbacks:\n{issues_url}?q=label%3Aleni-feedback\n"
                        )
                        m2 = _MIMEText(mail_text, 'plain', 'utf-8')
                        m2['From']    = kai_addr
                        m2['To']      = kai_addr
                        m2['Subject'] = f'📬 Leni: {feature}' + (f' — {react}' if react else '')
                        ctx2 = _ssl2.create_default_context()
                        with smtplib.SMTP(smtp_srv, smtp_prt, timeout=15) as sv:
                            sv.ehlo(); sv.starttls(context=ctx2); sv.login(kai_addr, kai_pw)
                            sv.sendmail(kai_addr, kai_addr, m2.as_string())
                except Exception:
                    pass  # Mail-Fehler darf Issue-Erfolg nicht blockieren
                self._json({'ok': True, 'issue_url': issue_url})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # Partner-View: GitHub Issues abrufen (Proxy, kein Token im Browser nötig)
        if self.path == '/api/partner/feedback-issues':
            try:
                import urllib.request as _urllib2
                secrets_path2 = SCRIPTS_DIR / 'secrets.json'
                try:
                    sec2 = json.loads(secrets_path2.read_text('utf-8'))
                except Exception:
                    sec2 = {}
                tok2 = sec2.get('partner_feedback_token', '')
                gh_o = 'kaimarienfeld'; gh_r = 'kira-partner'
                url2 = f'https://api.github.com/repos/{gh_o}/{gh_r}/issues?labels=leni-feedback&state=open&per_page=50'
                req2 = _urllib2.Request(url2, headers={
                    'Authorization': f'Bearer {tok2}',
                    'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28',
                })
                with _urllib2.urlopen(req2, timeout=10) as r2:
                    issues = json.loads(r2.read())
                self._json([{
                    'number': i['number'], 'title': i['title'],
                    'url': i['html_url'], 'created': i['created_at'][:10],
                    'body': (i.get('body') or '')[:400]
                } for i in issues])
            except Exception as e:
                self._json({'error': str(e)})
            return

        # Partner-View: Mail an Leni senden (Willkommen oder Passwort)
        if self.path == '/api/partner/send-leni-mail':
            try:
                import smtplib, ssl as _ssl
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                mail_cfg = CFG.get('email_notification', {})
                smtp_server  = mail_cfg.get('smtp_server', '')
                smtp_port    = int(mail_cfg.get('smtp_port', 587))
                absender     = mail_cfg.get('absender_email', '')
                pw_smtp      = mail_cfg.get('absender_passwort', '')
                if not smtp_server or not absender:
                    self._json({'ok': False, 'error': 'SMTP nicht konfiguriert (Einstellungen > Mail)'})
                    return
                mail_type = body.get('type', 'welcome')
                to_addr   = body.get('to', '').strip()
                link      = body.get('link', '')
                if not to_addr:
                    self._json({'ok': False, 'error': 'Keine Empfaenger-E-Mail angegeben'})
                    return
                msg = MIMEMultipart('alternative')
                bcc_addr = (
                    body.get('bcc')
                    or CFG.get('partner_view', {}).get('leni_mail_bcc')
                    or absender
                )
                msg['From'] = absender
                msg['To']   = to_addr
                if bcc_addr and bcc_addr != to_addr:
                    msg['Bcc'] = bcc_addr
                if mail_type == 'welcome':
                    msg['Subject'] = 'Du bist dabei! Kira wartet auf dich'
                    text = (
                        f"Hallo Leni,\n\n"
                        f"Kai und Kira sind bereit! Dein persoenlicher Blick auf die neue rauMKult-App wartet auf dich.\n\n"
                        f"Hier ist dein Link:\n{link}\n\n"
                        f"Dein Passwort kommt in einer separaten Mail.\n\n"
                        f"Auf der Seite kannst du direkt einstellen, wie und wie oft du ueber Neuigkeiten informiert werden moechtest.\n"
                        f"Einfach nach dem Einloggen oben auf Einstellungen klicken.\n\n"
                        f"Freue mich auf dein Feedback!\n"
                        f"Kai"
                    )
                elif mail_type == 'update':
                    msg['Subject'] = '✨ Neuigkeiten bei KIRA Partner!'
                    text = (
                        f"Hallo Leni,\n\n"
                        f"Kai hat die KIRA Partner-Seite aktualisiert — "
                        f"es gibt neue Funktionen oder Neuigkeiten zu entdecken!\n\n"
                        f"Schau einfach kurz rein:\n{link}\n\n"
                        f"Freue mich auf dein Feedback!\n"
                        f"Kai"
                    )
                else:  # password
                    pw = body.get('password', '')
                    msg['Subject'] = 'Dein Zugang zu KIRA Partner'
                    text = (
                        f"Hallo Leni,\n\n"
                        f"hier ist dein persoenliches Passwort fuer die KIRA Partner-Seite:\n\n"
                        f"    {pw}\n\n"
                        f"Link zur Seite: {link}\n\n"
                        f"Bitte nicht weiterleiten!\n"
                        f"Kai"
                    )
                msg.attach(MIMEText(text, 'plain', 'utf-8'))
                ctx = _ssl.create_default_context()
                with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as s:
                    s.ehlo()
                    s.starttls(context=ctx)
                    s.login(absender, pw_smtp)
                    s.sendmail(absender, to_addr, msg.as_string())
                self._json({'ok': True, 'type': mail_type, 'to': to_addr})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # Config zurücksetzen auf Werkseinstellungen
        if self.path == '/api/config/reset':
            try:
                config_path = SCRIPTS_DIR / "config.json"
                backup_path = SCRIPTS_DIR / "config.json.bak"
                try:
                    backup_path.write_text(config_path.read_text('utf-8'), 'utf-8')
                except Exception:
                    pass
                defaults = {
                    "_kommentar": "Deine persönliche Konfiguration für den rauMKult Assistenten",
                    "ntfy": {"aktiv": False, "topic_name": "", "server": "https://ntfy.sh"},
                    "aufgaben": {"unanswered_check_days": 3, "erinnerung_intervall_stunden": 24},
                    "nachfass": {"intervall_1_tage": 7, "intervall_2_tage": 14, "intervall_3_tage": 30},
                    "server": {"port": 8765, "auto_open_browser": True},
                    "protokoll": {"max_eintraege": 0, "tage": 90},
                    "runtime_log": {"aktiv": True, "ui_events": True, "kira_events": True,
                                   "llm_events": True, "hintergrund_events": True,
                                   "settings_events": True, "fehler_immer_loggen": True,
                                   "vollkontext_speichern": True, "kira_darf_lesen": True},
                    "kira": {"launcher_variant": "B", "size": 112, "prox_radius": 0.5,
                             "bounce_dist": 130, "idle_mode": True, "idle_delay": 10},
                    "llm": {"internet_recherche": False, "geschaeftsdaten_teilen": True,
                            "konversationen_speichern": True, "max_kontext_items": 50,
                            "auto_wissen_extrahieren": True, "providers": []}
                }
                config_path.write_text(json.dumps(defaults, ensure_ascii=False, indent=2), 'utf-8')
                rlog('settings', 'config_reset', 'Konfiguration auf Werkseinstellungen zurückgesetzt',
                     source='server', modul='einstellungen', actor_type='user', status='ok')
                self._json({'ok': True})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # Kunden-Alias speichern
        if self.path == '/api/kunden/alias':
            alias_email = (body.get('alias_email','') or '').strip().lower()
            haupt_email = (body.get('haupt_email','') or '').strip().lower()
            if not alias_email or not haupt_email:
                self._json({'ok': False, 'error': 'alias_email und haupt_email erforderlich'})
                return
            try:
                db = get_db()
                db.execute("DELETE FROM kunden_aliases WHERE alias_email=?", (alias_email,))
                db.execute("INSERT INTO kunden_aliases (alias_email, haupt_email) VALUES (?,?)",
                           (alias_email, haupt_email))
                db.commit()
                db.close()
                self._json({'ok': True})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        # WhatsApp Webhook (Meta Business Cloud API)
        if self.path == '/api/webhook/whatsapp':
            self._handle_whatsapp_webhook(self._raw_post_body, body)
            return

        # Instagram DM Webhook
        if self.path == '/api/webhook/instagram':
            self._handle_channel_webhook(body, kanal='instagram')
            return

        # ── Vorgang-API POST (Paket 6, session-nn) ───────────────────────────
        if self.path == '/api/vorgang/neu':
            self._api_vorgang_neu(body)
            return

        if re.match(r'^/api/vorgang/\d+/status$', self.path):
            self._api_vorgang_status(body)
            return

        if re.match(r'^/api/vorgang/\d+/link$', self.path):
            self._api_vorgang_link(body)
            return

        if self.path == '/api/vorgang/signal/gelesen':
            self._api_vorgang_signal_gelesen(body)
            return

        self._respond(404, 'text/plain', b'Not found')

    def _handle_whatsapp_webhook(self, raw_body: bytes, body: dict):
        """
        POST /api/webhook/whatsapp — Meta WhatsApp Business Cloud API.
        Validiert X-Hub-Signature-256 (HMAC-SHA256) mit whatsapp_app_secret aus secrets.json.
        Parst Meta-Format: entry[0].changes[0].value.messages[...].
        Ruft verarbeite_kanal_eingang() für jede eingehende Text-Nachricht auf.
        """
        import hmac, hashlib

        # HMAC-Signatur prüfen (wenn app_secret konfiguriert)
        try:
            secrets = json.loads((SCRIPTS_DIR / "secrets.json").read_text('utf-8'))
            app_secret = secrets.get("whatsapp_app_secret", "")
        except Exception:
            app_secret = ""

        if app_secret:
            sig_header = self.headers.get('X-Hub-Signature-256', '')
            mac = hmac.new(app_secret.encode(), raw_body, hashlib.sha256)
            expected = 'sha256=' + mac.hexdigest()
            if not hmac.compare_digest(sig_header, expected):
                self._respond(401, 'application/json',
                              json.dumps({'error': 'Invalid signature'}).encode())
                return

        # Meta erwartet immer 200 OK — bei Fehler trotzdem 200 senden
        if body.get('object') != 'whatsapp_business_account':
            self._json({'status': 'ok', 'note': 'ignored'})
            return

        processed = 0
        errors = []
        for entry in body.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value', {})
                for msg in value.get('messages', []):
                    msg_type = msg.get('type', '')
                    sender   = msg.get('from', '')
                    msg_id   = msg.get('id', '')
                    ts       = msg.get('timestamp', '')

                    # Text extrahieren (text- oder interactive-Nachrichten)
                    if msg_type == 'text':
                        text = msg.get('text', {}).get('body', '')
                    elif msg_type == 'interactive':
                        # Button-Antworten etc.
                        interactive = msg.get('interactive', {})
                        text = (interactive.get('button_reply', {}).get('title', '')
                                or interactive.get('list_reply', {}).get('title', ''))
                    else:
                        # Audio, Bild etc. → Typ als Platzhalter
                        text = f"[{msg_type.upper()}-Nachricht]"

                    if not sender or not text:
                        continue

                    try:
                        import kira_proaktiv
                        kira_proaktiv.verarbeite_kanal_eingang(
                            kanal='whatsapp',
                            absender=sender,
                            text=text,
                            meta={'id': msg_id, 'datum': ts, 'konto': 'whatsapp'},
                        )
                        processed += 1
                    except Exception as e:
                        errors.append(str(e))

        self._json({'status': 'ok', 'processed': processed,
                    'errors': errors if errors else None})

    def _handle_channel_webhook(self, body: dict, kanal: str):
        """
        Empfängt WhatsApp/Instagram Nachrichten und legt Tasks an.
        Erwartet X-Webhook-Secret Header.
        Body: {from, text, timestamp, media_url (optional)}
        HINWEIS: Die eigentliche WhatsApp/Instagram API-Registrierung
        (Meta App Setup, Phone Number Registration) muss separat eingerichtet werden.
        Dieser Endpoint ist der Empfangs-Hook nach erfolgreicher API-Integration.
        """
        # Auth-Check
        try:
            secrets = json.loads((SCRIPTS_DIR / "secrets.json").read_text('utf-8'))
            webhook_secret = secrets.get("webhook_secret", "")
        except:
            webhook_secret = ""
        provided_secret = self.headers.get('X-Webhook-Secret', '')
        if webhook_secret and provided_secret != webhook_secret:
            self._respond(401, 'application/json', json.dumps({'error': 'Unauthorized'}).encode())
            return

        sender = str(body.get('from', '') or '')
        text   = str(body.get('text', '') or '')
        ts     = str(body.get('timestamp', '') or datetime.now().isoformat())
        konto  = kanal  # "whatsapp" oder "instagram"

        if not sender or not text:
            self._json({'error': 'from und text erforderlich'})
            return

        try:
            from llm_classifier import classify_mail, kategorie_to_task_typ
            cl = classify_mail(konto, sender, f"[{kanal.upper()}] {text[:80]}", text,
                               folder='', is_sent=False, kanal=kanal)
            kat      = cl["kategorie"]
            task_typ = kategorie_to_task_typ(kat)

            db = get_db()
            db.execute("""INSERT INTO tasks
                (typ, kategorie, titel, zusammenfassung, beschreibung,
                 kunden_email, kunden_name, absender_rolle, empfohlene_aktion,
                 kategorie_grund, betreff, konto, datum_mail,
                 prioritaet, antwort_noetig, konfidenz)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task_typ, kat, text[:120],
                 cl.get("zusammenfassung", text[:100]),
                 text[:1000],
                 sender, "", cl.get("absender_rolle", ""),
                 cl.get("empfohlene_aktion", ""),
                 cl.get("kategorie_grund", f"{kanal}-Eingang"),
                 f"[{kanal.upper()}] {text[:80]}", konto, ts,
                 cl.get("prioritaet", "mittel"),
                 1 if cl.get("antwort_noetig") else 0,
                 cl.get("konfidenz", "mittel")))
            db.commit()
            task_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.close()
            self._json({'status': 'ok', 'task_id': task_id, 'kategorie': kat})
        except Exception as e:
            self._json({'error': str(e)})

    def _handle_task_action(self, task_id, action, body):
        if action == 'status':
            from task_manager import update_task_status
            status = body.get('status', '')
            kat    = body.get('kat', '')   # optional: ursprüngliche Kategorie für KI-Lernen
            ok = update_task_status(task_id, status, body.get('notiz', ''))
            alog("Task", f"Status → {status}", f"ID {task_id} | Kat: {kat}", "ok" if ok else "fehler", task_id=task_id)
            rlog('system', 'task_status_changed', f"Task {task_id}: {kat} -> {status}",
                 source='server', modul='aufgaben', actor_type='user',
                 context_type='task', context_id=str(task_id),
                 status='ok' if ok else 'fehler')
            # KI-Lern-Eintrag: jede bewusste Entscheidung einzeln speichern
            if ok and kat and status in ('erledigt', 'zur_kenntnis', 'ignorieren'):
                try:
                    db = get_db()
                    # Lern-Mapping: status → neuer_typ für corrections-Tabelle
                    lern_map = {
                        'erledigt':      'Abgeschlossen',
                        'zur_kenntnis':  'Zur Kenntnis',
                        'ignorieren':    'Ignorieren',
                    }
                    db.execute(
                        "INSERT INTO corrections (task_id, alter_typ, neuer_typ, notiz) VALUES (?,?,?,?)",
                        (task_id, kat, lern_map[status],
                         f'Nutzer-Aktion: {status}')
                    )
                    db.commit()
                    db.close()
                except Exception:
                    pass
            self._json({'ok': ok})

        elif action == 'korrektur':
            db = get_db()
            try:
                alter = body.get('alter_typ','')
                neu   = body.get('neuer_typ','')
                notiz = body.get('notiz','')
                alog("Task", "Korrektur", f"ID {task_id}: {alter} → {neu}", "ok", task_id=task_id)
                db.execute("INSERT INTO corrections (task_id,alter_typ,neuer_typ,notiz) VALUES (?,?,?,?)",
                           (task_id, alter, neu, notiz))
                if neu and neu != alter:
                    db.execute("UPDATE tasks SET kategorie=? WHERE id=?", (neu, task_id))
                db.commit()
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
                db.close()
                return
            finally:
                db.close()
            # Kira gibt aktives Feedback zur Korrektur
            kira_antwort = 'Korrektur gespeichert und wird beim nächsten Klassifizierungs-Scan berücksichtigt.'
            try:
                kat_info  = f' von „{alter}" nach „{neu}"' if neu and neu != alter else ''
                notiz_info = f' Deine Notiz: „{notiz}"' if notiz else ''
                kira_prompt = (
                    f'Ich habe soeben eine Korrektur für Aufgabe #{task_id} gespeichert{kat_info}.{notiz_info} '
                    f'Bestätige kurz in 1–2 Sätzen (auf Deutsch), dass du das aufgenommen hast, '
                    f'wo du es abgelegt hast (wissen_regeln / Lernhistorie) und wie du es beim nächsten Scan anwendest.')
                kira_result = kira_chat(kira_prompt)
                kira_antwort = kira_result.get('antwort', kira_antwort)
            except Exception:
                pass
            self._json({'ok': True, 'kira_antwort': kira_antwort})

        elif action == 'spaeter':
            wann_text = body.get('wann', '').strip()
            if not wann_text:
                self._json({'ok': False, 'error': 'Kein Zeitpunkt angegeben'})
                return
            now      = datetime.now()
            now_str  = now.strftime('%A, %d. %B %Y, %H:%M Uhr')
            fallback = (now + timedelta(hours=24)).isoformat()
            naechste = fallback
            kira_antwort = f'Ich erinnere dich am {(now + timedelta(hours=24)).strftime("%d.%m.%Y um %H:%M Uhr")}.'
            try:
                kira_prompt = (
                    f'Heute ist {now_str}. '
                    f'Der Nutzer möchte diese Aufgabe verschieben und hat eingegeben: "{wann_text}". '
                    f'Antworte NUR mit diesem JSON-Objekt (kein anderer Text, kein Markdown): '
                    f'{{"datetime": "YYYY-MM-DDTHH:MM:00", "bestaetigung": "OK, ich erinnere dich am [ausgeschriebener Termin auf Deutsch]."}}')
                kira_result = kira_chat(kira_prompt)
                raw = kira_result.get('antwort', '')
                m = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
                if m:
                    import json as _j
                    data = _j.loads(m.group(0))
                    naechste     = data.get('datetime', fallback)
                    kira_antwort = data.get('bestaetigung', kira_antwort)
                elif raw:
                    kira_antwort = raw
            except Exception:
                pass
            if not naechste:
                naechste = fallback
            db = get_db()
            try:
                db.execute(
                    "UPDATE tasks SET status='offen', naechste_erinnerung=? WHERE id=?",
                    (naechste, task_id))
                db.commit()
                self._json({'ok': True, 'kira_antwort': kira_antwort, 'naechste_erinnerung': naechste})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            finally:
                db.close()

        elif action == 'thread':
            db = get_db()
            try:
                row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
                if not row:
                    self._json({'thread': [], 'error': 'nicht gefunden'}); return
                t = dict(row)
                thread_id    = t.get('thread_id','') or ''
                kunden_email = t.get('kunden_email','') or ''
                konto        = t.get('konto','') or ''
                messages = []
                if thread_id:
                    rows = db.execute(
                        "SELECT id,betreff,kunden_email,konto,datum_mail,beschreibung,absender_rolle,status "
                        "FROM tasks WHERE thread_id=? ORDER BY datum_mail ASC LIMIT 30",
                        (thread_id,)).fetchall()
                    messages = [dict(r) for r in rows]
                if not messages and kunden_email:
                    rows = db.execute(
                        "SELECT id,betreff,kunden_email,konto,datum_mail,beschreibung,absender_rolle,status "
                        "FROM tasks WHERE kunden_email=? AND konto=? ORDER BY datum_mail DESC LIMIT 15",
                        (kunden_email, konto)).fetchall()
                    messages = [dict(r) for r in rows]
                for m in messages:
                    if m.get('beschreibung'):
                        m['beschreibung'] = m['beschreibung'][:500]
                self._json({'thread': messages, 'current_id': task_id})
            except Exception as e:
                self._json({'thread': [], 'error': str(e)})
            finally:
                db.close()

        elif action == 'loeschen':
            db = get_db()
            try:
                row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
                if not row:
                    self._json({'ok': False, 'error': 'Task nicht gefunden'})
                    return
                t = dict(row)
                alog("Task", "Löschen", f"ID {task_id}: {(t.get('betreff','') or '')[:80]}", "ok", task_id=task_id)
                msgid  = t.get('message_id', '') or ''
                pfad   = t.get('mail_folder_pfad', '') or ''
                betr   = t.get('betreff', '') or ''
                konto  = t.get('konto', '') or ''
                absnd  = t.get('kunden_email', '') or ''
                datum  = t.get('datum_mail', '') or ''
                grund      = body.get('grund', 'Nutzer gelöscht') or 'Nutzer gelöscht'
                analysiere = body.get('analysiere', False)
                kat        = t.get('kategorie', '') or ''
                text_raw   = t.get('beschreibung', '') or ''
                absender_r = t.get('absender_rolle', '') or ''

                # Permanent block in loeschhistorie (message_id als Sperre)
                db.execute(
                    "INSERT INTO loeschhistorie (konto, absender, betreff, datum_mail, grund, message_id) "
                    "VALUES (?,?,?,?,?,?)",
                    (konto, absnd, betr, datum,
                     f'Nutzer gelöscht – {grund}', msgid))

                # Archive-Datei löschen
                archiv_geloescht = False
                if pfad:
                    mail_json = Path(pfad) / 'mail.json'
                    for allowed_root in ALLOWED_ROOTS:
                        if str(mail_json).startswith(allowed_root):
                            try:
                                if mail_json.exists():
                                    mail_json.unlink()
                                    archiv_geloescht = True
                            except Exception:
                                pass
                            break

                # Task aus DB entfernen
                db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
                db.commit()

                # Kira analysiert und lernt
                kira_antwort = ''
                regel_gespeichert = False
                if analysiere:
                    try:
                        preview = text_raw[:600].replace('\n',' ')
                        kira_prompt = (
                            f'Aufgabe #{task_id} wurde vom Nutzer gelöscht.\n'
                            f'Grund: "{grund}"\n'
                            f'Betreff: "{betr}"\n'
                            f'Konto: {konto} | Absender: {absnd} | Kategorie: {kat}\n'
                            f'Mailinhalt (Ausschnitt): {preview}\n\n'
                            f'Analysiere kurz (2-3 Sätze): Was ist das für ein Mailtyp, warum wurde er gelöscht, '
                            f'und welche EINE konkrete Erkennungsregel solltest du daraus ableiten? '
                            f'Antworte auf Deutsch. Formuliere die Regel als klaren Satz für dein Regelwerk.')
                        kira_result = kira_chat(kira_prompt)
                        kira_antwort = kira_result.get('antwort', '')
                        if kira_antwort:
                            # Als Lernregel in wissen_regeln speichern
                            regel_titel  = f'Lernregel: {grund[:60]}'
                            regel_inhalt = f'Kontext: Betreff "{betr[:80]}", Konto {konto}. {kira_antwort}'
                            db2 = get_db()
                            db2.execute(
                                "INSERT INTO wissen_regeln (kategorie, titel, inhalt, status) VALUES (?,?,?,?)",
                                ('gelernt', regel_titel, regel_inhalt, 'aktiv'))
                            db2.commit()
                            db2.close()
                            regel_gespeichert = True
                    except Exception:
                        pass

                self._json({'ok': True, 'archiv_geloescht': archiv_geloescht,
                            'kira_antwort': kira_antwort,
                            'regel_gespeichert': regel_gespeichert})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            finally:
                db.close()

        elif action == 'generate-draft':
            db = get_db()
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            db.close()
            if not row:
                self._json({'error': 'Aufgabe nicht gefunden'})
                return
            t = dict(row)
            kai_input = body.get('kai_input','').strip()
            absender  = f"{t.get('kunden_name','')} <{t.get('kunden_email','')}>"
            result    = generate_draft(
                betreff     = t.get('betreff','') or '',
                absender    = absender,
                text        = t.get('beschreibung','') or '',
                kunden_email= t.get('kunden_email','') or '',
            )
            entwurf = result.get('entwurf','')
            hinweis = result.get('hinweis','')
            if kai_input:
                hinweis = f"Kai-Anmerkung: {kai_input[:80]}" + (" ..." if len(kai_input)>80 else "")
                entwurf = f"[Kai: {kai_input}]\n\n{entwurf}"
            try:
                db2 = get_db()
                db2.execute("INSERT INTO task_kira_context (task_id,kai_input,kira_antwort) VALUES (?,?,?)",
                            (task_id, kai_input, entwurf))
                db2.commit()
                db2.close()
            except: pass
            self._json({'entwurf': entwurf, 'hinweis': hinweis,
                        'claude_prompt': result.get('claude_prompt','')})

        else:
            self._respond(404, 'text/plain', b'Not found')

    def _handle_wissen_action(self, regel_id, aktion, body=None):
        db = get_db()
        try:
            if aktion == 'bestaetigen':
                db.execute("UPDATE wissen_regeln SET status='aktiv', bestaetigt_am=? WHERE id=?",
                           (datetime.now().isoformat(), regel_id))
            elif aktion == 'ablehnen':
                db.execute("UPDATE wissen_regeln SET status='abgelehnt' WHERE id=?", (regel_id,))
            elif aktion == 'loeschen':
                db.execute("DELETE FROM wissen_regeln WHERE id=?", (regel_id,))
            elif aktion == 'update' and body:
                kat    = body.get('kategorie','')
                titel  = body.get('titel','').strip()
                inhalt = body.get('inhalt','').strip()
                if not titel or not inhalt:
                    self._json({'ok': False, 'error': 'Titel und Inhalt erforderlich'})
                    return
                db.execute("UPDATE wissen_regeln SET kategorie=?, titel=?, inhalt=? WHERE id=?",
                           (kat, titel, inhalt, regel_id))
            db.commit()
            self._json({'ok': True})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})
        finally:
            db.close()

    def _handle_geschaeft_action(self, gid, aktion, body):
        db = get_db()
        try:
            now = body.get('zeitstempel') or datetime.now().isoformat()
            if aktion == 'erledigt':
                bezahlt_am = body.get('datum', now[:10])
                notiz = body.get('notiz', '')
                betrag_voll = body.get('betrag-voll', 'ja')
                betrag_bezahlt = body.get('betrag', '')
                grund = body.get('grund', '')
                # Hole Eingangsrechnung-Daten
                g_row = db.execute("SELECT betreff, gegenpartei, gegenpartei_email, rechnungsnummer, betrag FROM geschaeft WHERE id=?", (gid,)).fetchone()
                partner = (g_row['gegenpartei'] or g_row['gegenpartei_email'] or 'Unbekannt') if g_row else 'Unbekannt'
                re_nr = (g_row['rechnungsnummer'] or '') if g_row else ''
                betreff = (g_row['betreff'] or '') if g_row else ''
                db.execute("UPDATE geschaeft SET bewertung='erledigt', bewertung_grund=? WHERE id=?",
                           (f'bezahlt am {bezahlt_am}. {notiz}'.strip(), gid))
                # Strukturierte Interaktionsdaten
                daten = {k: v for k, v in body.items()}
                daten['zeitstempel'] = now
                daten['partner'] = partner
                daten['re_nummer'] = re_nr
                db.execute("INSERT INTO geschaeft_statistik (typ,referenz_id,ereignis,daten_json,erstellt_am) VALUES (?,?,?,?,?)",
                           ('geschaeft', gid, 'erledigt', json.dumps(daten, ensure_ascii=False), now))
                # Strukturierte Erkenntnisse
                wissen_parts = [f'Eingangsrechnung von {partner} erledigt.']
                if re_nr:
                    wissen_parts.append(f'Re-Nr: {re_nr}.')
                wissen_parts.append(f'Bezahlt am: {bezahlt_am}.')
                if betrag_voll == 'nein' and betrag_bezahlt:
                    wissen_parts.append(f'Reduzierter Betrag: {betrag_bezahlt} EUR.')
                if grund:
                    wissen_parts.append(f'Grund: {grund}')
                if notiz:
                    wissen_parts.append(f'Notiz: {notiz}')
                titel = f'Eingangsrechnung {partner}: erledigt'
                if re_nr:
                    titel = f'{re_nr} ({partner}): erledigt'
                db.execute("INSERT INTO wissen_regeln (kategorie,titel,inhalt,quelle,erstellt_am) VALUES (?,?,?,?,?)",
                           ('gelernt', titel, ' '.join(wissen_parts), f'Kira-Interaktion: Geschaeft #{gid}', now))
                db.commit()
                self._json({'ok': True})
            elif aktion == 'bewertung':
                bew = body.get('bewertung','')
                grund = body.get('grund','')
                db.execute("UPDATE geschaeft SET bewertung=?, bewertung_grund=? WHERE id=?",
                           (bew, grund, gid))
                db.execute("INSERT INTO geschaeft_statistik (typ,referenz_id,ereignis,daten_json,erstellt_am) VALUES (?,?,?,?,?)",
                           ('geschaeft', gid, f'bewertung_{bew}', json.dumps({"grund": grund, "zeitstempel": now}, ensure_ascii=False), now))
                db.commit()
                self._json({'ok': True})
            else:
                self._respond(404, 'text/plain', b'Not found')
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})
        finally:
            db.close()

    # ── Vorgang-API Implementierung (Paket 6, session-nn) ─────────────────────

    def _api_vorgaenge_list(self):
        """GET /api/vorgaenge[?typ=...&email=...&limit=50] — Offene Vorgänge."""
        try:
            from case_engine import get_open_vorgaenge
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            typ        = qs.get('typ',   [None])[0]
            email      = qs.get('email', [None])[0]
            limit      = int(qs.get('limit', ['50'])[0])
            vorgaenge  = get_open_vorgaenge(typ=typ, kunden_email=email, limit=limit)
            self._json({"ok": True, "vorgaenge": vorgaenge})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _api_vorgang_detail(self):
        """GET /api/vorgang/{id} — Vollständiger Kontext eines Vorgangs."""
        try:
            from case_engine import get_vorgang_context
            vid = int(self.path.split('/')[-1])
            ctx = get_vorgang_context(vid)
            if ctx.get("vorgang") is None:
                self._respond(404, 'application/json',
                              json.dumps({"ok": False, "error": "Vorgang nicht gefunden"}).encode())
                return
            self._json({"ok": True, **ctx})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _api_vorgang_kunde(self):
        """GET /api/vorgang/kunde/{email} — Alle Vorgänge eines Kunden."""
        try:
            from case_engine import get_open_vorgaenge
            email = urllib.parse.unquote(self.path.split('/api/vorgang/kunde/')[-1])
            vorgaenge = get_open_vorgaenge(kunden_email=email, limit=100)
            self._json({"ok": True, "email": email, "vorgaenge": vorgaenge})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _api_vorgang_signals(self):
        """GET /api/vorgang/signals — Ausstehende B/C-Signale (für Toast/Modal)."""
        try:
            from case_engine import get_pending_signals
            qs     = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            limit  = int(qs.get('limit', ['5'])[0])
            signals = get_pending_signals(max_count=limit)
            self._json({"ok": True, "signals": signals})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _api_vorgang_neu(self, body: dict):
        """POST /api/vorgang/neu — Neuen Vorgang manuell anlegen."""
        try:
            from case_engine import create_vorgang
            typ           = body.get("typ", "sonstiger_vorgang")
            kunden_email  = body.get("kunden_email", "")
            kunden_name   = body.get("kunden_name", "")
            titel         = body.get("titel", "")
            konfidenz     = float(body.get("konfidenz", 0.9))
            konto         = body.get("konto")
            quelle        = body.get("quelle", "manuell")
            vid = create_vorgang(
                typ=typ, kunden_email=kunden_email, kunden_name=kunden_name,
                titel=titel, quelle=quelle, konfidenz=konfidenz,
                konto=konto, entscheidungsstufe="A",
            )
            self._json({"ok": True, "vorgang_id": vid})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _api_vorgang_status(self, body: dict):
        """POST /api/vorgang/{id}/status — Statusübergang."""
        try:
            from case_engine import update_status, get_valid_transitions, get_vorgang
            vid = int(re.search(r'/api/vorgang/(\d+)/status', self.path).group(1))
            neuer_status = body.get("status", "")
            grund        = body.get("grund", "")
            actor        = body.get("actor", "kai")
            if not neuer_status:
                self._json({"ok": False, "error": "status fehlt"})
                return
            v = get_vorgang(vid)
            if v is None:
                self._json({"ok": False, "error": "Vorgang nicht gefunden"})
                return
            ok = update_status(vid, neuer_status, grund=grund, actor=actor)
            if ok:
                self._json({"ok": True, "vorgang_id": vid, "neuer_status": neuer_status})
            else:
                erlaubt = get_valid_transitions(v["typ"], v["status"])
                self._json({"ok": False, "error": f"Übergang nicht erlaubt",
                            "erlaubte_uebergaenge": erlaubt,
                            "aktueller_status": v["status"]})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _api_vorgang_link(self, body: dict):
        """POST /api/vorgang/{id}/link — Entität mit Vorgang verknüpfen."""
        try:
            from case_engine import link_entity
            vid          = int(re.search(r'/api/vorgang/(\d+)/link', self.path).group(1))
            entitaet_typ = body.get("entitaet_typ", "")
            entitaet_id  = str(body.get("entitaet_id", ""))
            rolle        = body.get("rolle", "zugehoerig")
            if not entitaet_typ or not entitaet_id:
                self._json({"ok": False, "error": "entitaet_typ und entitaet_id erforderlich"})
                return
            link_id = link_entity(vid, entitaet_typ, entitaet_id, rolle=rolle)
            self._json({"ok": True, "link_id": link_id})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _api_vorgang_signal_gelesen(self, body: dict):
        """POST /api/vorgang/signal/gelesen — Signal als angezeigt markieren."""
        try:
            from case_engine import mark_signal_shown
            signal_id = int(body.get("signal_id", 0))
            aktion    = body.get("aktion", "gesehen")
            if not signal_id:
                self._json({"ok": False, "error": "signal_id fehlt"})
                return
            mark_signal_shown(signal_id, aktion)
            self._json({"ok": True})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _html(self, html: str):
        b = html.encode('utf-8', errors='replace')
        self._respond(200, 'text/html; charset=utf-8', b)

    def _json(self, data):
        b = json.dumps(data, default=str, ensure_ascii=False).encode('utf-8')
        self._respond(200, 'application/json', b)

    def _respond(self, code, ctype, body):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.end_headers()
        self.wfile.write(body)


# ── Start ─────────────────────────────────────────────────────────────────────
def _kill_old_instances(port):
    """Beendet alle anderen Prozesse auf diesem Port und wartet, bis der Port frei ist."""
    import subprocess, os, socket, time
    _NO_WIN = 0x08000000  # CREATE_NO_WINDOW
    my_pid = os.getpid()
    killed = []
    try:
        r = subprocess.run(['netstat', '-ano'], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', creationflags=_NO_WIN)
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and f':{port}' in parts[1]:
                try:
                    pid = int(parts[-1])
                    if pid and pid != my_pid:
                        subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                                       capture_output=True, creationflags=_NO_WIN)
                        killed.append(pid)
                except (ValueError, IndexError):
                    pass
        if killed:
            print(f"[Kira] {len(killed)} alte Instanz(en) beendet: {killed}")
    except Exception as e:
        print(f"[Kira] Cleanup-Fehler: {e}")
    # Warten bis Port wirklich frei ist (max 3 Sekunden)
    for _ in range(6):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('127.0.0.1', port))
            s.close()
            break  # Port frei!
        except OSError:
            time.sleep(0.5)
    else:
        time.sleep(1.0)  # letzter Versuch


def run_server(open_browser=True):
    config = {}
    try:
        config = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
    except: pass

    port      = config.get("server", {}).get("port", PORT)
    auto_open = config.get("server", {}).get("auto_open_browser", True)

    _kill_old_instances(port)
    _ensure_case_engine_tables()
    rlog_ensure_cfg()
    alog("Server", "Start", f"Port {port} | Python {__import__('sys').version.split()[0]}", "ok")
    rlog('system', 'server_started', f"Kira Dashboard gestartet auf Port {port}",
         source='server', modul='server', actor_type='system', status='ok')

    httpd = ThreadedHTTPServer(('127.0.0.1', port), DashboardHandler)
    url   = f"http://localhost:{port}"
    print(f"[Kira Dashboard v4] {url}")

    if open_browser and auto_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    # Signal-Watcher für Desktop-Overlays starten (Paket 9, session-nn)
    try:
        from activity_window import start_signal_watcher
        start_signal_watcher()
        print("[Signal-Watcher] Desktop-Overlay aktiv (15s Intervall)")
    except Exception as _sw_err:
        print(f"[Signal-Watcher] Nicht verfügbar: {_sw_err}")

    # Mail-Monitor starten (Echtzeit-IMAP-Polling)
    monitor_cfg = config.get("mail_monitor", {})
    if monitor_cfg.get("aktiv", True):
        monitor_thread = start_monitor_thread()
        if monitor_thread:
            print("[Mail-Monitor] Gestartet (IMAP-Polling)")
        else:
            print("[Mail-Monitor] Nicht verfügbar (msal fehlt oder keine Config)")

    # Archiv-Bereinigung: täglich einmal im Hintergrund (03:00 Uhr oder 24h nach Start)
    def _archiv_cleanup_loop():
        import time as _time
        import importlib
        _time.sleep(10)  # kurze Verzögerung nach Server-Start
        while True:
            try:
                ac = importlib.import_module("archiv_cleanup")
                cs = ac.run_cleanup()
                if cs.get("bereinigt", 0) > 0:
                    rlog('system', 'archiv_cleanup',
                         f"Archiv-Bereinigung: {cs['bereinigt']} Mails bereinigt, "
                         f"{cs['protokoll']} protokolliert",
                         source='server', modul='archiv_cleanup',
                         actor_type='system', status='ok')
            except Exception as _e:
                pass
            _time.sleep(86400)  # 24h bis zur nächsten Bereinigung

    _cleanup_t = threading.Thread(target=_archiv_cleanup_loop, daemon=True, name="ArchivCleanup")
    _cleanup_t.start()

    # Snooze-Wecker: jede Minute abgelaufene Snoozed-Mails aufwecken
    def _snooze_waker_loop():
        import time as _time
        _time.sleep(30)  # kurze Verzögerung
        while True:
            try:
                _ensure_mail_columns()
                conn = sqlite3.connect(str(MAIL_INDEX_DB))
                rows = conn.execute(
                    "SELECT message_id FROM mails WHERE snooze_until IS NOT NULL "
                    "AND datetime(snooze_until) <= datetime('now')"
                ).fetchall()
                if rows:
                    ids = [r[0] for r in rows]
                    conn.executemany(
                        "UPDATE mails SET snooze_until=NULL, gelesen=0 WHERE message_id=?",
                        [(mid,) for mid in ids]
                    )
                    conn.commit()
                    rlog('system', 'snooze_wakeup',
                         f"{len(ids)} Snooze-Mail(s) aufgeweckt",
                         source='server', modul='snooze', actor_type='system', status='ok')
                conn.close()
            except Exception:
                pass
            _time.sleep(60)

    _snooze_t = threading.Thread(target=_snooze_waker_loop, daemon=True, name="SnoozeWaker")
    _snooze_t.start()

    # Modell-Validierung: einmal 20s nach Start, dann alle 24h
    def _model_validation_loop():
        import time as _time
        _time.sleep(20)
        while True:
            try:
                validate_all_providers()
            except Exception as _e:
                pass
            _time.sleep(86400)

    _model_val_t = threading.Thread(target=_model_validation_loop, daemon=True, name="ModelValidation")
    _model_val_t.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        stop_monitor()
        print("\nServer gestoppt.")


if __name__ == '__main__':
    run_server()
