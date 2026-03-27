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
                       PROVIDER_TYPES, generate_daily_briefing)
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

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

# ── DB Helpers ────────────────────────────────────────────────────────────────
def get_db():
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    return db

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
        for r in org_rows:
            dat = esc(r['datum_erkannt'] or '')
            desc = esc((r['beschreibung'] or '')[:45])
            typ = esc(r['typ'] or '')
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
            if urgency == "urgent": badge = f'<span class="dash-term-badge dash-tag-red">heute</span>'
            elif urgency == "soon": badge = f'<span class="dash-term-badge dash-tag-amber">bald</span>'
            term_html += f'''<div class="dash-term-item">
  <span class="dash-term-date {urgency}">{dat_display}</span>
  <span class="dash-term-text">{desc or typ}</span>
  {badge}
</div>'''
    except: term_html = '<div style="padding:12px;color:var(--muted);font-size:12px">Keine Termine erfasst</div>'

    # ── Zone C3: Geschäft aktuell ──
    try:
        gesch_rows = db.execute("SELECT typ,datum,betrag,gegenpartei,gegenpartei_email FROM geschaeft ORDER BY datum DESC LIMIT 5").fetchall()
        biz_html = ""
        for r in gesch_rows:
            typ = esc(r['typ'] or '')
            betrag = r['betrag'] or 0
            name = esc((r['gegenpartei'] or r['gegenpartei_email'] or '')[:30])
            # Color by type
            if "Zahlung" in typ or "Eingang" in typ:
                dot_color = "#1D9E75"; val_color = "#1D9E75"; prefix = "+"
            elif "überfällig" in typ.lower() or "Mahnung" in typ:
                dot_color = "#E24B4A"; val_color = "#E24B4A"; prefix = ""
            elif "Nachfass" in typ:
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
    cnt = f'<span style="font-size:10px;color:var(--muted);margin-left:auto;margin-right:8px">{count} Eintr.</span>' if count else ''
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
    llm   = get_llm_config()
    proto = config.get("protokoll", {})
    rtlog_cfg = config.get("runtime_log", {})
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

    # Multi-Provider Karten generieren
    providers = get_all_providers()
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
        status_icon = "🟢" if pstatus["status"] == "ok" else ("🔑" if pstatus["status"] == "no_key" else "📦")
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
            key_row = f'''<div class="settings-row" style="margin-top:4px">
              <label style="font-size:11px">API Key</label>
              <div style="display:flex;gap:4px;align-items:center">
                <input type="password" id="pkey-{esc(pid)}" value="" placeholder="Key eingeben..." style="width:180px;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;font-size:11px;">
                <button class="btn btn-sm" style="font-size:10px;padding:2px 8px;background:var(--kl);color:#000;border:none;border-radius:4px;cursor:pointer" onclick="saveProviderKey('{js_esc(pid)}')">Speichern</button>
              </div>
            </div>'''

        base_url_row = ""
        if ptyp == "custom":
            base_url_val = esc(prov.get("base_url", ""))
            base_url_row = f'''<div class="settings-row" style="margin-top:4px">
              <label style="font-size:11px">Base URL</label>
              <input type="text" id="purl-{esc(pid)}" value="{base_url_val}" placeholder="https://api.example.com/v1" style="width:220px;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;font-size:11px;">
            </div>'''
        if ptyp == "custom":
            model_row = f'''<div class="settings-row" style="margin-top:4px">
              <label style="font-size:11px">Modell-ID</label>
              <input type="text" id="pmodel-{esc(pid)}" value="{esc(pmodel)}" placeholder="model-name" style="width:180px;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;font-size:11px;">
            </div>'''
        else:
            model_row = f'''<div class="settings-row" style="margin-top:4px">
              <label style="font-size:11px">Modell</label>
              <select id="pmodel-{esc(pid)}" style="width:180px;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;font-size:11px;">
                {model_options}
              </select>
            </div>'''

        provider_cards += f'''<div class="provider-card" id="pcard-{esc(pid)}" style="{opacity}border:1px solid var(--border);border-radius:8px;padding:10px 14px;margin-bottom:8px;background:#111;">
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
              <label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="paktiv-{esc(pid)}" {aktiv_checked} onchange="toggleProvider('{js_esc(pid)}',this.checked)"> Aktiv</label>
              <button class="btn btn-sm" style="font-size:10px;padding:1px 6px;background:transparent;color:#e84545;border:1px solid #e84545;border-radius:4px;cursor:pointer" onclick="deleteProvider('{js_esc(pid)}')" title="Entfernen">✕</button>
            </div>
          </div>
          <div style="font-size:11px;margin-bottom:4px;{'color:#5cb85c;font-weight:700' if pstatus['status']=='ok' else 'color:var(--muted)'}">{'API Key aktiv — Chat bereit' if pstatus['status']=='ok' else status_text}</div>
          {model_row}
          {key_row}
          {base_url_row}
        </div>'''

    # Provider-Typ-Optionen für "Hinzufügen"
    add_type_options = ""
    for tkey, tval in PROVIDER_TYPES.items():
        add_type_options += f'<option value="{esc(tkey)}">{esc(tval["name"])}</option>'

    html = f"""
    <div class="section">
      <div class="section-title">Erscheinungsbild</div>
      <div class="section-body">
        <div class="settings-row">
          <label>Farbschema</label>
          <select id="cfg-theme" onchange="applyTheme(this.value)">
            <option value="dark">Dunkel</option>
            <option value="light">Hell</option>
          </select>
        </div>
        <div class="settings-row">
          <label>Akzentfarbe</label>
          <div style="display:flex;align-items:center;gap:8px">
            <input type="color" id="cfg-accent" value="#4f7df9" onchange="applyAccent(this.value)">
            <span id="cfg-accent-hex" style="font-size:var(--fs-sm);color:var(--muted)">#4f7df9</span>
            <button class="btn btn-xs btn-muted" onclick="resetAccent()">Zur&uuml;cksetzen</button>
          </div>
        </div>
        <div class="settings-row">
          <label>Schriftgr&ouml;&szlig;e</label>
          <select id="cfg-fontsize" onchange="applyFontSize(this.value)">
            <option value="">Normal</option>
            <option value="small">Klein</option>
            <option value="large">Gro&szlig;</option>
          </select>
        </div>
        <div class="settings-row">
          <label>Dichte</label>
          <select id="cfg-density" onchange="applyDensity(this.value)">
            <option value="">Normal</option>
            <option value="compact">Kompakt</option>
            <option value="comfortable">Komfortabel</option>
          </select>
        </div>
        <div class="settings-row">
          <label>Firmenname</label>
          <input type="text" id="cfg-company-name" placeholder="z.B. Meine Firma" oninput="applyCompanyName(this.value)">
        </div>
        <div class="settings-row">
          <label>Logo (URL oder Emoji)</label>
          <input type="text" id="cfg-logo" placeholder="z.B. https://... oder K" oninput="applyLogo(this.value)">
        </div>
        <div class="settings-row">
          <label>Kartenradius</label>
          <select id="cfg-card-radius" onchange="applyCardRadius(this.value)">
            <option value="">Normal (12px)</option>
            <option value="4px">Eckig (4px)</option>
            <option value="8px">Leicht (8px)</option>
            <option value="16px">Rund (16px)</option>
          </select>
        </div>
        <div class="settings-row">
          <label>Schatten</label>
          <select id="cfg-shadow" onchange="applyShadow(this.value)">
            <option value="">Normal</option>
            <option value="none">Keine Schatten</option>
            <option value="strong">Stark</option>
          </select>
        </div>
        <div class="settings-row">
          <label>Animationen reduzieren</label>
          <input type="checkbox" id="cfg-reduce-motion" onchange="applyReduceMotion(this.checked)">
        </div>
        <div class="settings-row">
          <label>Hoher Kontrast</label>
          <input type="checkbox" id="cfg-high-contrast" onchange="applyHighContrast(this.checked)">
        </div>
        <div style="margin-top:8px">
          <button class="btn btn-sm btn-gold" onclick="saveDesignSettings()">Design speichern</button>
          <span id="design-status" style="margin-left:10px;color:var(--muted);font-size:var(--fs-sm)"></span>
        </div>
      </div>
    </div>
    <div class="section">
      <div class="section-title">Push-Benachrichtigungen (ntfy.sh)</div>
      <div class="section-body">
        <div class="settings-row">
          <label>Aktiv</label>
          <input type="checkbox" id="cfg-ntfy-aktiv" {'checked' if ntfy.get("aktiv") else ''}>
        </div>
        <div class="settings-row">
          <label>Topic-Name</label>
          <input type="text" id="cfg-ntfy-topic" value="{esc(ntfy.get('topic_name',''))}" placeholder="raumkult-...">
        </div>
        <div class="settings-row">
          <label>Server</label>
          <input type="text" id="cfg-ntfy-server" value="{esc(ntfy.get('server','https://ntfy.sh'))}" placeholder="https://ntfy.sh">
        </div>
      </div>
    </div>
    <div class="section">
      <div class="section-title">Aufgaben & Erinnerungen</div>
      <div class="section-body">
        <div class="settings-row">
          <label>Erinnerungsintervall (Stunden)</label>
          <input type="number" id="cfg-erinnerung-h" value="{aufg.get('erinnerung_intervall_stunden', 24)}" min="1" max="168">
        </div>
        <div class="settings-row">
          <label>Unbeantwortete Mails prüfen (Tage zurück)</label>
          <input type="number" id="cfg-unanswered-days" value="{aufg.get('unanswered_check_days', 14)}" min="1" max="90">
        </div>
      </div>
    </div>
    <div class="section">
      <div class="section-title">Nachfass-Intervalle (Angebote)</div>
      <div class="section-body">
        <div class="settings-row">
          <label>1. Nachfass (Tage nach Angebot)</label>
          <input type="number" id="cfg-nf-1" value="{nf.get('intervall_1_tage', 10)}" min="1" max="60">
        </div>
        <div class="settings-row">
          <label>2. Nachfass (Tage nach 1. Nachfass)</label>
          <input type="number" id="cfg-nf-2" value="{nf.get('intervall_2_tage', 21)}" min="1" max="90">
        </div>
        <div class="settings-row">
          <label>3. Nachfass (Tage nach 2. Nachfass)</label>
          <input type="number" id="cfg-nf-3" value="{nf.get('intervall_3_tage', 45)}" min="1" max="120">
        </div>
      </div>
    </div>
    <div class="section">
      <div class="section-title">Dashboard</div>
      <div class="section-body">
        <div class="settings-row">
          <label>Server-Port</label>
          <input type="number" id="cfg-server-port" value="{srv.get('port', 8765)}" min="1024" max="65535">
        </div>
        <div class="settings-row">
          <label>Browser automatisch öffnen</label>
          <input type="checkbox" id="cfg-auto-browser" {'checked' if srv.get("auto_open_browser", True) else ''}>
        </div>
      </div>
    </div>
    <div class="section">
      <div class="section-title">KI-Assistent (Kira Multi-LLM)</div>
      <div class="section-body">
        <div style="font-size:12px;color:var(--muted);margin-bottom:10px">
          Provider werden in Priorit&auml;tsreihenfolge durchlaufen. F&auml;llt einer aus, springt Kira automatisch auf den n&auml;chsten.
        </div>
        <div id="provider-list">
          {provider_cards}
        </div>
        <div style="margin-top:8px;padding:10px 14px;border:1px dashed var(--border);border-radius:8px;background:#0a0a0a">
          <div style="font-size:12px;font-weight:700;color:var(--kl);margin-bottom:6px">+ Provider hinzuf&uuml;gen</div>
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
            <select id="add-provider-typ" style="width:200px;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;font-size:12px;">
              {add_type_options}
            </select>
            <input type="text" id="add-provider-name" placeholder="Name (z.B. &quot;OpenAI Backup&quot;)" style="width:180px;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;font-size:12px;">
            <button class="btn btn-sm btn-gold" onclick="addProvider()">Hinzuf&uuml;gen</button>
          </div>
        </div>
        <div style="margin-top:12px;border-top:1px solid var(--border);padding-top:10px">
          <div style="font-size:12px;font-weight:700;margin-bottom:6px">Allgemeine KI-Einstellungen</div>
          <div class="settings-row">
            <label>Internet-Recherche erlauben</label>
            <input type="checkbox" id="cfg-llm-internet" {'checked' if llm.get('internet_recherche') else ''}>
          </div>
          <div class="settings-row">
            <label>Gesch&auml;ftsdaten im Kontext teilen</label>
            <input type="checkbox" id="cfg-llm-geschaeft" {'checked' if llm.get('geschaeftsdaten_teilen', True) else ''}>
          </div>
          <div class="settings-row">
            <label>Konversationen speichern</label>
            <input type="checkbox" id="cfg-llm-konv" {'checked' if llm.get('konversationen_speichern', True) else ''}>
          </div>
        </div>
        <div style="font-size:10px;color:var(--muted);margin-top:8px">
          API Keys: <a href="https://console.anthropic.com/settings/keys" target="_blank" style="color:var(--kl)">Anthropic</a>
          &middot; <a href="https://platform.openai.com/api-keys" target="_blank" style="color:var(--kl)">OpenAI</a>
          &middot; <a href="https://openrouter.ai/keys" target="_blank" style="color:var(--kl)">OpenRouter</a>
          &middot; <a href="https://ollama.com" target="_blank" style="color:var(--kl)">Ollama</a>
        </div>
      </div>
    </div>
    <div class="section">
      <div class="section-title">Aktivit&auml;tsprotokoll</div>
      <div class="section-body">
        <div class="settings-row">
          <label>Max. Eintr&auml;ge <span style="color:var(--muted);font-weight:400">(0 = unbegrenzt)</span></label>
          <input type="number" id="cfg-proto-max" value="{proto.get('max_eintraege', 0)}" min="0" max="100000" style="width:100px">
        </div>
        <div class="settings-row">
          <label>Eintr&auml;ge behalten (Tage) <span style="color:var(--muted);font-weight:400">(0 = nie l&ouml;schen)</span></label>
          <input type="number" id="cfg-proto-tage" value="{proto.get('tage', 0)}" min="0" max="3650" style="width:100px">
        </div>
        <div class="settings-row">
          <label>Datenbankgr&ouml;&szlig;e (tasks.db)</label>
          <span style="font-size:13px;color:var(--text-secondary)">{db_size_str}</span>
        </div>
      </div>
    </div>
    <div class="section">
      <div class="section-title">&Auml;nderungsverlauf (Mikro-Log)</div>
      <div class="section-body">
        <div style="font-size:12px;color:var(--muted);margin-bottom:10px">
          Mikrogranulares append-only Log aller Code-, CSS-, JS- und Konfigurations&auml;nderungen
          (<code style="font-size:10px;background:rgba(255,255,255,.06);padding:1px 4px;border-radius:3px">change_log.jsonl</code>).
          Jeder Micro-Schritt = eigene Zeile. Nie &uuml;berschreiben, nie umsortieren.
        </div>
        <div class="settings-row">
          <label>Eintr&auml;ge gesamt</label>
          <span style="font-size:13px;color:var(--text-secondary)">{change_log_count}</span>
        </div>
        <div class="settings-row">
          <label>Letzter Eintrag</label>
          <span style="font-size:13px;color:var(--text-secondary)">{change_log_last or "&ndash;"}</span>
        </div>
        <div class="settings-row">
          <label>Ergebnis-Verteilung</label>
          <span style="font-size:12px;color:var(--text-secondary)">{" &middot; ".join(f'{k}: {v}' for k,v in change_log_by_res.items()) or "&ndash;"}</span>
        </div>
        <div class="settings-row">
          <label>Speicherort</label>
          <span style="font-size:11px;color:var(--muted);font-family:monospace">memory/change_log.jsonl</span>
        </div>
        <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <select id="cl-filter-modul" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:12px;font-family:inherit">
            <option value="">Alle Module</option>
            {"".join(f'<option value="{m}">{m}</option>' for m in change_log_moduls)}
          </select>
          <select id="cl-filter-result" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:12px;font-family:inherit">
            <option value="">Alle Ergebnisse</option>
            {"".join(f'<option value="{r}">{r}</option>' for r in change_log_results)}
          </select>
          <select id="cl-filter-feature" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:12px;font-family:inherit">
            <option value="">Alle Features</option>
            {"".join(f'<option value="{f}">{f}</option>' for f in change_log_features)}
          </select>
          <select id="cl-filter-action" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:12px;font-family:inherit">
            <option value="">Alle Actions</option>
            {"".join(f'<option value="{a}">{a}</option>' for a in change_log_actions)}
          </select>
          <input id="cl-filter-search" type="text" placeholder="Suche in summary / details / location&hellip;"
            style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:12px;font-family:inherit;width:200px">
          <button class="btn btn-xs btn-sec" onclick="loadChangeLog(false)">Anzeigen</button>
          <button class="btn btn-xs btn-sec" onclick="exportChangeLog()">Export JSONL</button>
        </div>
        <div id="changelog-entries" style="margin-top:10px;display:none;max-height:500px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;background:#080808"></div>
      </div>
    </div>
    <div class="section" id="sec-rtlog">
      <div class="section-title" style="display:flex;justify-content:space-between;align-items:center">
        <span>Runtime-Log &amp; Telemetrie</span>
        <span id="rtlog-live-dot" style="width:8px;height:8px;border-radius:50%;background:{'#5cb85c' if rtlog_cfg.get('aktiv',True) else '#888'};display:inline-block" title="{'Aktiv' if rtlog_cfg.get('aktiv',True) else 'Inaktiv'}"></span>
      </div>
      <div class="section-body">
        <div style="font-size:12px;color:var(--muted);margin-bottom:12px">
          L&uuml;ckenloses Protokoll aller UI-, Kira- und System-Ereignisse.
          Kira kann damit auf Verlauf und Fehler zugreifen.
          DB: <code style="font-size:10px;background:rgba(255,255,255,.06);padding:1px 4px;border-radius:3px">knowledge/runtime_events.db</code>
        </div>

        <!-- Master-Toggle -->
        <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:#111;border-radius:8px;margin-bottom:10px;border:1px solid var(--border)">
          <div>
            <span style="font-weight:700;font-size:13px">Logging aktiv</span>
            <span style="font-size:11px;color:var(--muted);margin-left:8px">Haupt-Schalter</span>
          </div>
          <input type="checkbox" id="cfg-rl-aktiv" {'checked' if rtlog_cfg.get('aktiv', True) else ''} style="width:16px;height:16px;cursor:pointer">
        </div>

        <!-- Typ-Toggles mit Live-Stats -->
        <div style="border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:10px">
          <div style="padding:6px 10px;background:#0d0d0d;font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px">Ereignis-Typen</div>
          {_rtlog_type_row('ui',       'UI-Klicks &amp; Navigation',      'cfg-rl-ui',       rtlog_cfg.get('ui_events',True),       rl_by_type.get('ui',0))}
          {_rtlog_type_row('kira',     'Kira Tools &amp; Kontext',        'cfg-rl-kira',     rtlog_cfg.get('kira_events',True),     rl_by_type.get('kira',0))}
          {_rtlog_type_row('llm',      'LLM Provider / Token / Dauer',   'cfg-rl-llm',      rtlog_cfg.get('llm_events',True),      rl_by_type.get('llm',0))}
          {_rtlog_type_row('system',   'System &amp; Hintergrund-Jobs',  'cfg-rl-bg',       rtlog_cfg.get('hintergrund_events',True),rl_by_type.get('system',0))}
          {_rtlog_type_row('settings', 'Einstellungs&auml;nderungen',    'cfg-rl-settings', rtlog_cfg.get('settings_events',True), rl_by_type.get('settings',0))}
        </div>

        <!-- Spezial-Optionen -->
        <div style="border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:10px">
          <div style="padding:6px 10px;background:#0d0d0d;font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px">Optionen</div>
          <div class="settings-row" style="padding:6px 10px;border-bottom:1px solid rgba(255,255,255,.04)">
            <label style="font-size:12px">Fehler immer loggen <span style="color:var(--muted);font-size:10px">(auch wenn Typ deaktiviert)</span></label>
            <input type="checkbox" id="cfg-rl-fehler" {'checked' if rtlog_cfg.get('fehler_immer_loggen', True) else ''}>
          </div>
          <div class="settings-row" style="padding:6px 10px;border-bottom:1px solid rgba(255,255,255,.04)">
            <label style="font-size:12px">Vollkontext speichern <span style="color:var(--muted);font-size:10px">(User-Fragen + Kira-Antworten vollst&auml;ndig)</span></label>
            <input type="checkbox" id="cfg-rl-vollkontext" {'checked' if rtlog_cfg.get('vollkontext_speichern', True) else ''}>
          </div>
          <div class="settings-row" style="padding:6px 10px">
            <label style="font-size:12px">Kira darf Logs lesen <span style="color:var(--muted);font-size:10px">(Tool: runtime_log_suchen aktiv)</span></label>
            <input type="checkbox" id="cfg-rl-kira-lesen" {'checked' if rtlog_cfg.get('kira_darf_lesen', True) else ''}>
          </div>
        </div>

        <!-- Live-Stats -->
        <div id="rtlog-stats-box" style="border:1px solid var(--border);border-radius:8px;padding:10px 12px;background:#0a0a0a;margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <span style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px">Live-Statistiken</span>
            <button class="btn btn-xs btn-sec" onclick="refreshRtLogStats()" style="font-size:10px;padding:2px 8px">&#x21BB; Aktualisieren</button>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px" id="rtlog-stats-grid">
            <div style="text-align:center;padding:6px;background:#111;border-radius:6px"><div style="font-size:18px;font-weight:700;color:var(--kl)">{rl_total}</div><div style="font-size:10px;color:var(--muted)">Gesamt</div></div>
            <div style="text-align:center;padding:6px;background:#111;border-radius:6px"><div style="font-size:18px;font-weight:700;color:var(--kl)">{rl_today}</div><div style="font-size:10px;color:var(--muted)">Heute</div></div>
            <div style="text-align:center;padding:6px;background:#111;border-radius:6px"><div style="font-size:18px;font-weight:700;color:{'#e84545' if rl_fehler else 'var(--kl)'}">{rl_fehler}</div><div style="font-size:10px;color:var(--muted)">Fehler</div></div>
          </div>
          <div style="margin-top:8px;font-size:11px;color:var(--muted);display:flex;gap:16px;flex-wrap:wrap">
            <span>Sitzungen: <strong style="color:var(--text)">{rl_sessions}</strong></span>
            <span>DB-Gr&ouml;&szlig;e: <strong style="color:var(--text)">{rl_db_size}</strong></span>
            <span>Typen: <strong style="color:var(--text)">{" · ".join(f'{k}:{v}' for k,v in rl_by_type.items()) or "–"}</strong></span>
          </div>
        </div>

        <!-- Viewer -->
        <div style="margin-bottom:8px;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
          <select id="rl-filter-type" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:12px;font-family:inherit">
            <option value="">Alle Typen</option>
            <option value="ui">ui</option><option value="kira">kira</option>
            <option value="llm">llm</option><option value="system">system</option>
            <option value="settings">settings</option>
          </select>
          <select id="rl-filter-status" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:12px;font-family:inherit">
            <option value="">Alle Status</option><option value="ok">ok</option><option value="fehler">fehler</option>
          </select>
          <input id="rl-filter-search" type="text" placeholder="Suche&hellip;" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:12px;font-family:inherit;width:140px">
          <button class="btn btn-xs btn-sec" onclick="loadRuntimeLog(false)">Anzeigen</button>
          <button class="btn btn-xs" style="background:#e84545;color:#fff;border:none;border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer" onclick="loadRuntimeLog(false,true)">Nur Fehler</button>
          <button class="btn btn-xs btn-sec" onclick="exportRtLog()" style="margin-left:auto">Export CSV</button>
          <button class="btn btn-xs" style="background:transparent;color:#e84545;border:1px solid #e84545;border-radius:6px;padding:4px 8px;font-size:11px;cursor:pointer" onclick="clearRtLog()">DB leeren</button>
        </div>
        <div id="runtimelog-entries" style="display:none;max-height:360px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;background:#080808"></div>
      </div>
    </div>
    <div style="margin-top:14px">
      <button class="btn btn-sm btn-gold" onclick="saveSettings()">Einstellungen speichern</button>
      <span id="settings-status" style="margin-left:10px;color:var(--muted);font-size:12px"></span>
    </div>"""
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
        id_attr = f' id="wr-{rid}"' if with_id else ""
        wi_id_attr = f' id="wi-{rid}"' if with_id else ""
        edit_btn = f"""<button class="btn btn-korr" style="margin-left:8px;font-size:11px;padding:2px 8px;" onclick="editRegel({rid},'{js_esc(r['titel'])}','{js_esc(r['inhalt'])}','{js_esc(r.get('kategorie',''))}')">Bearbeiten</button>""" if editable else ""
        del_btn = f"""<button class="btn btn-ignore" style="margin-left:4px;font-size:11px;padding:2px 8px;" onclick="wissenAction({rid},'loeschen')">Entfernen</button>""" if editable else ""
        return f"""<div class="wissen-card"{id_attr}>
          <div class="wissen-titel">{esc(r['titel'])}</div>
          <div class="wissen-inhalt"{wi_id_attr}>{esc(r['inhalt'])}</div>
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
    org_html       = build_organisation(db)
    gesch_html     = build_geschaeft(db)
    wissen_html    = build_wissen(db)
    einstell_html  = build_einstellungen()
    db.close()

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
      <div class="top-chip ok" id="monitorStatusChip"><span class="chip-dot"></span><span id="monitorStatusText">Verbunden</span></div>
      <div class="top-chip" onclick="showPanel('kommunikation')" title="Offene Aufgaben">&#x1F514; <span id="headerBadgeCount">{n_ges}</span> offen</div>
      <div class="header-avatar" title="Einstellungen" onclick="showPanel('einstellungen')">K</div>
      <button class="btn btn-muted btn-xs" id="updateBtn" onclick="serverNeustart()" title="Server komplett neu starten (alle Instanzen beenden)" style="border-radius:6px">&#x21BB; Neustart</button>
    </div>
  </div>

  <div class="panel active" id="panel-dashboard">{dashboard_html}</div>
  <div class="panel" id="panel-kommunikation">{komm_html}</div>
  <div class="panel" id="panel-organisation">{org_html}</div>
  <div class="panel" id="panel-geschaeft">{gesch_html}</div>
  <div class="panel" id="panel-wissen">{wissen_html}</div>
  <div class="panel" id="panel-einstellungen">{einstell_html}</div>
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

<!-- Kira Launcher (Modus A) -->
<button class="kira-fab" onclick="toggleKiraQuick()" title="Kira Assistenz">
  <span class="kira-fab-k">K</span>
  <span class="kira-fab-label">Kira</span>
  <span class="kira-fab-status" id="kiraFabStatus"></span>
</button>

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
          <div class="kw-title">Kira Workspace</div>
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
          <div class="kw-ctx-sec-h">Navigation</div>
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
        <input type="email" id="korr-alias-email" placeholder="alias@email.de" style="flex:1;background:#111;color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 8px;font-size:12px">
        <input type="email" id="korr-haupt-email" placeholder="haupt@email.de" style="flex:1;background:#111;color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 8px;font-size:12px">
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
      style="width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:7px;padding:9px 12px;font-size:13px;margin-bottom:10px;box-sizing:border-box"
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
      style="width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:7px;padding:10px 12px;font-size:14px;margin-bottom:10px;box-sizing:border-box"
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
    <select id="er-kat" style="width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px;margin-bottom:9px;">
      <option value="fest">Feste Regel</option>
      <option value="stil">Stil &amp; Tonalit&auml;t</option>
      <option value="preis">Preise &amp; Kalkulation</option>
      <option value="technik">Technik &amp; Fachwissen</option>
      <option value="prozess">Prozess &amp; Abl&auml;ufe</option>
      <option value="gelernt">Gelernt</option>
      <option value="vorschlag">Vorschlag</option>
    </select>
    <label style="font-size:12px;color:var(--muted);display:block;margin-bottom:3px;">Titel:</label>
    <input type="text" id="er-titel" style="width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px;margin-bottom:9px;">
    <label style="font-size:12px;color:var(--muted);display:block;margin-bottom:3px;">Inhalt:</label>
    <textarea id="er-inhalt" rows="5" style="width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px;font-family:inherit;resize:vertical;margin-bottom:9px;"></textarea>
    <div class="modal-actions">
      <button class="btn btn-done" onclick="saveRegelEdit()">Speichern</button>
      <button class="btn btn-ignore" onclick="closeEditRegel()">Abbrechen</button>
    </div>
  </div>
</div>

<div class="status-toast" id="toast"></div>
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
  if(logo) {{ applyLogo(logo); const inp=document.getElementById('cfg-logo'); if(inp) inp.value=logo; }}
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
    const m = t.getAttribute('onclick')?.match(/kommSegFilter\(this,'([^']+)'\)/);
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
      const ftype = fname.toLowerCase().match(/\.pdf$/) ? '&#x1F4C4;' : fname.toLowerCase().match(/\.(jpg|jpeg|png|gif)$/) ? '&#x1F5BC;' : '&#x1F4CE;';
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
      input = '<input type="text" id="'+f.id+'" placeholder="'+(f.placeholder||'')+'" style="width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px">';
    }} else if (f.type === 'number') {{
      input = '<input type="number" id="'+f.id+'" placeholder="'+(f.placeholder||'')+'" step="0.01" style="width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px">';
    }} else if (f.type === 'date') {{
      input = '<input type="date" id="'+f.id+'" value="'+(f.value||'')+'" style="width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px">';
    }} else if (f.type === 'select') {{
      input = '<select id="'+f.id+'" onchange="updateKiraFields()" style="width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px">';
      f.options.forEach(o => {{ input += '<option value="'+o[0]+'">'+o[1]+'</option>'; }});
      input += '</select>';
    }} else if (f.type === 'textarea') {{
      input = '<textarea id="'+f.id+'" rows="3" placeholder="'+(f.placeholder||'')+'" style="width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px;font-family:inherit;resize:vertical"></textarea>';
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
      aktiv: document.getElementById('cfg-ntfy-aktiv').checked,
      topic_name: document.getElementById('cfg-ntfy-topic').value.trim(),
      server: document.getElementById('cfg-ntfy-server').value.trim() || 'https://ntfy.sh'
    }},
    aufgaben: {{
      erinnerung_intervall_stunden: parseInt(document.getElementById('cfg-erinnerung-h').value)||24,
      unanswered_check_days: parseInt(document.getElementById('cfg-unanswered-days').value)||14
    }},
    nachfass: {{
      intervall_1_tage: parseInt(document.getElementById('cfg-nf-1').value)||10,
      intervall_2_tage: parseInt(document.getElementById('cfg-nf-2').value)||21,
      intervall_3_tage: parseInt(document.getElementById('cfg-nf-3').value)||45
    }},
    server: {{
      port: parseInt(document.getElementById('cfg-server-port').value)||8765,
      auto_open_browser: document.getElementById('cfg-auto-browser').checked
    }},
    llm: {{
      internet_recherche: document.getElementById('cfg-llm-internet')?.checked || false,
      geschaeftsdaten_teilen: document.getElementById('cfg-llm-geschaeft')?.checked ?? true,
      konversationen_speichern: document.getElementById('cfg-llm-konv')?.checked ?? true,
      _provider_updates: providerUpdates
    }},
    protokoll: {{
      max_eintraege: parseInt(document.getElementById('cfg-proto-max')?.value)||0,
      tage: parseInt(document.getElementById('cfg-proto-tage')?.value)||0
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
    // Update type dot colors
    const types = {{'ui':'cfg-rl-ui','kira':'cfg-rl-kira','llm':'cfg-rl-llm','system':'cfg-rl-bg','settings':'cfg-rl-settings'}};
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

function clearRtLog() {{
  if(!confirm('Runtime-Log-Datenbank wirklich leeren? Alle Einträge werden gelöscht.')) return;
  fetch('/api/runtime/clear',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:'{{}}'}})
    .then(r=>r.json()).then(d=>{{
      if(d.ok){{showToast('Runtime-Log geleert'); refreshRtLogStats(); document.getElementById('runtimelog-entries').innerHTML=''; document.getElementById('runtimelog-entries').style.display='none';}}
      else showToast(d.error||'Fehler');
    }}).catch(()=>showToast('Fehler'));
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
    const lines = (d.entries||[]).slice().reverse().map(e=>JSON.stringify(e)).join('\n');
    const blob  = new Blob([lines], {{type:'application/x-ndjson'}});
    const url   = URL.createObjectURL(blob);
    const a     = document.createElement('a');
    a.href = url; a.download = 'change_log.jsonl'; a.click();
    URL.revokeObjectURL(url);
  }}).catch(()=>showToast('Export fehlgeschlagen'));
}}

// Provider Key speichern
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
  if(!confirm('Provider wirklich entfernen?')) return;
  fetch('/api/kira/provider/delete',{{
    method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{provider_id:pid}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok) {{ showToast('Provider entfernt'); setTimeout(()=>location.reload(),400); }}
    else showToast(d.error||'Fehler');
  }}).catch(()=>showToast('Fehler'));
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
  _rtlog('ui','wissen_action',aktion+' Regel '+regelId,{{submodul:'wissen',context_type:'regel',context_id:String(regelId)}});
  fetch('/api/wissen/'+regelId+'/'+aktion,{{method:'POST'}}).then(r=>r.json()).then(d=>{{
    if(d.ok) {{
      const labels = {{bestaetigen:'Regel bestätigt',ablehnen:'Regel abgelehnt',loeschen:'Regel entfernt'}};
      showToast(labels[aktion]||'Aktualisiert');
      const el = document.getElementById('wr-'+regelId);
      if(el && aktion==='loeschen') {{ el.style.opacity='0.2'; setTimeout(()=>el.remove(),300); }}
      else setTimeout(()=>location.reload(),600);
    }}
  }}).catch(()=>showToast('Fehler'));
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
  if(qp.classList.contains('open')) closeKiraQuick();
  else {{ qp.classList.add('open'); kiraOpen=true; }}
}}
function closeKiraQuick() {{
  document.getElementById('kiraQuick').classList.remove('open');
  kiraOpen=false;
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
    html += '<div class="kira-card kira-task-card '+pcls+'" onclick="'+a.action+';closeKira()" style="cursor:pointer"><div class="kira-card-meta">'+a.text+'</div></div>';
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

function appendKiraMsg(rolle, text, tools, providerInfo, fallbackInfo) {{
  const area = document.getElementById('kiraChatArea');
  const welcome = area.querySelector('.kira-welcome');
  if(welcome) welcome.remove();
  const div = document.createElement('div');
  if(rolle==='user') {{
    div.className = 'kira-msg kira-msg-user';
    div.textContent = text;
  }} else if(rolle==='assistant') {{
    div.className = 'kira-msg kira-msg-kira';
    div.innerHTML = kiraFormatText(text);
    if(tools && tools.length) {{
      const ti = document.createElement('div');
      ti.className = 'kira-tools-used';
      ti.innerHTML = tools.map(t=>'<span class="kira-tool-badge">'+escH(t)+'</span>').join(' ');
      div.appendChild(ti);
    }}
    // Provider-Info anzeigen
    const meta = document.createElement('div');
    meta.style.cssText = 'font-size:10px;color:var(--muted);margin-top:6px;display:flex;align-items:center;gap:6px;flex-wrap:wrap';
    if(providerInfo) meta.innerHTML = '<span style="opacity:.7">via '+escH(providerInfo)+'</span>';
    if(fallbackInfo && fallbackInfo.length) {{
      meta.innerHTML += '<span style="color:#e8a545;opacity:.8" title="'+escH(fallbackInfo.join(', '))+'">⚡ Fallback</span>';
    }}
    if(meta.innerHTML) div.appendChild(meta);
  }} else if(rolle==='error') {{
    div.className = 'kira-msg kira-msg-error';
    div.textContent = text;
  }} else {{
    div.className = 'kira-msg kira-msg-system';
    div.textContent = text;
  }}
  area.appendChild(div);
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
  document.write('<!doctype html><html><head><meta charset=utf-8><style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#0d0d0d;color:#ccc;font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:12px}}.spin{{font-size:36px;animation:rot 1s linear infinite}}@keyframes rot{{to{{transform:rotate(360deg)}}}}p{{font-size:15px;opacity:.8}}small{{font-size:12px;opacity:.45}}</style></head><body><div class=spin>↻</div><p>Server wird neu gestartet …</p><small id=s>0s</small><script>let t=0;setInterval(()=>{{t++;document.getElementById("s").textContent=t+"s";}},1000);<\/script></body></html>');
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
  }};
  const items = sets[typ] || sets.frage;
  bar.innerHTML = '<span class="kw-quick-lbl">Schnell:</span>' +
    items.map(t=>`<span class="kw-qb" onclick="kiraAddPrompt('${{t.replace(/'/g,"\\'")}}')">${{escH(t)}}</span>`).join('');
}}

// Text in Input-Box einfügen
function kiraAddPrompt(text) {{
  const inp = document.getElementById('kiraInput');
  if(!inp) return;
  inp.value = inp.value ? inp.value + '\n' + text : text;
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
function showToast(msg){{
  const t=document.getElementById('toast');
  t.textContent=msg;t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),2400);
}}
function showKiraToast(msg){{
  const t=document.getElementById('toast');
  t.textContent='Kira: '+msg;t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),5000);
}}
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
  fetch('/api/tasks').then(r=>r.json()).then(data=>{{
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
/* Font size override */
[data-fontsize="small"]{font-size:12px;}
[data-fontsize="large"]{font-size:15px;}

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
.status-toast.show{transform:translateY(0);opacity:1;}

/* ═══ Kira FAB ═══ */
.kira-fab{position:fixed;bottom:22px;right:22px;z-index:200;
  background:#534AB7;border-radius:50%;width:52px;height:52px;display:flex;align-items:center;justify-content:center;
  flex-direction:column;cursor:pointer;box-shadow:0 4px 18px rgba(0,0,0,.35);
  transition:transform .2s,box-shadow .2s;border:none;color:#fff;}
.kira-fab:hover{transform:scale(1.07);box-shadow:0 6px 26px rgba(83,74,183,.5);}
.kira-fab-k{color:#fff;font-size:16px;font-weight:600;line-height:1;}
.kira-fab-label{color:#CECBF6;font-size:8px;margin-top:1px;line-height:1;}
.kira-fab-status{position:absolute;top:1px;right:1px;width:12px;height:12px;
  background:#1D9E75;border-radius:50%;border:2px solid var(--bg);}

/* ═══ Kira Quick Panel (kq-*) ═══ */
.kq-panel{position:fixed;bottom:82px;right:22px;z-index:250;width:340px;
  background:var(--bg-raised);border:1px solid var(--border-strong);border-radius:var(--radius-lg);
  box-shadow:0 8px 40px rgba(0,0,0,.5);display:none;flex-direction:column;overflow:hidden;}
.kq-panel.open{display:flex;}
.kq-header{display:flex;align-items:center;gap:10px;padding:14px 16px 12px;border-bottom:1px solid var(--border);}
.kq-logo{width:34px;height:34px;background:#534AB7;border-radius:9px;display:flex;align-items:center;justify-content:center;flex-direction:column;flex-shrink:0;}
.kq-logo-k{color:#fff;font-size:14px;font-weight:600;line-height:1;}
.kq-logo-l{color:#CECBF6;font-size:7px;margin-top:1px;}
.kq-htext{flex:1;}
.kq-htitle{font-size:14px;font-weight:600;color:var(--text);}
.kq-hstatus{font-size:10px;color:var(--text-secondary);display:flex;align-items:center;gap:4px;margin-top:2px;}
.kq-hstatus-dot{width:6px;height:6px;border-radius:50%;background:#1D9E75;flex-shrink:0;}
.kq-close{width:26px;height:26px;border-radius:6px;border:1px solid var(--border);background:var(--bg);
  display:flex;align-items:center;justify-content:center;font-size:13px;color:var(--text-secondary);cursor:pointer;}
.kq-close:hover{color:var(--text);border-color:var(--border-strong);}
.kq-actions{padding:8px 10px;}
.kq-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:9px;cursor:pointer;
  transition:background .12s,border-color .12s;border:1px solid transparent;margin-bottom:2px;}
.kq-item:hover{background:var(--accent-bg);border-color:var(--accent-border);}
.kq-icon{width:34px;height:34px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0;}
.kq-icon.purple{background:rgba(83,74,183,.18);color:#CECBF6;}
.kq-icon.amber{background:rgba(186,117,23,.18);color:#f0b855;}
.kq-icon.green{background:rgba(59,109,17,.2);color:#7ecf3f;}
.kq-icon.blue{background:rgba(24,95,165,.2);color:#6db3f2;}
.kq-icon.coral{background:rgba(153,60,29,.2);color:#f08060;}
.kq-icon.teal{background:rgba(15,110,86,.2);color:#3fcfa0;}
.kq-icon.gray{background:rgba(128,128,128,.12);color:var(--text-secondary);}
.kq-body{flex:1;min-width:0;}
.kq-title{font-size:13px;font-weight:500;color:var(--text);margin-bottom:1px;}
.kq-sub{font-size:11px;color:var(--text-secondary);}
.kq-arrow{font-size:14px;color:var(--border-strong);flex-shrink:0;transition:color .12s;}
.kq-item:hover .kq-arrow{color:#CECBF6;}
.kq-footer{padding:9px 14px 12px;border-top:1px solid var(--border);display:flex;align-items:center;gap:8px;}
.kq-input{flex:1;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:7px 11px;
  font-size:12px;color:var(--text);font-family:inherit;}
.kq-input:focus{outline:none;border-color:var(--accent-border);}
.kq-send{width:30px;height:30px;border-radius:8px;background:#534AB7;border:none;
  display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;cursor:pointer;flex-shrink:0;}
.kq-send:hover{background:#6358cc;}

/* ═══ Kira Workspace (kw-*) ═══ */
.kira-workspace-overlay{display:none;position:fixed;inset:0;z-index:350;background:rgba(0,0,0,.65);align-items:center;justify-content:center;padding:16px;}
.kira-workspace-overlay.open{display:flex;}
.kw-shell{background:var(--bg-raised);border:1px solid var(--border-strong);border-radius:var(--radius-lg);
  width:96vw;max-width:1260px;height:87vh;display:flex;flex-direction:column;box-shadow:0 16px 60px rgba(0,0,0,.6);overflow:hidden;}
.kw-header{display:flex;justify-content:space-between;align-items:center;padding:12px 18px;border-bottom:1px solid var(--border);flex-shrink:0;}
.kw-header-left{display:flex;align-items:center;gap:10px;}
.kw-logo{width:30px;height:30px;background:#534AB7;border-radius:7px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;font-weight:700;flex-shrink:0;}
.kw-title{font-size:14px;font-weight:700;color:#CECBF6;}
.kw-sub{font-size:11px;color:var(--muted);margin-top:1px;}
.kw-header-right{display:flex;gap:6px;align-items:center;}
.kw-body{display:flex;flex:1;overflow:hidden;}
.kw-ctx-panel{width:240px;min-width:240px;border-right:1px solid var(--border);display:flex;flex-direction:column;overflow-y:auto;background:var(--bg);}
.kw-ctx-hdr{padding:12px 15px 9px;border-bottom:1px solid var(--border);}
.kw-ctx-hdr-t{font-size:12px;font-weight:700;color:var(--text);margin-bottom:7px;}
.kw-ctx-search{width:100%;background:var(--bg-raised);border:1px solid var(--border);border-radius:6px;padding:5px 9px;font-size:11px;color:var(--text);font-family:inherit;}
.kw-ctx-search:focus{outline:none;border-color:var(--accent-border);}
.kw-ctx-section{padding:9px 0;}
.kw-ctx-sec-h{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;padding:0 15px 5px;}
.kw-ctx-item{display:flex;align-items:flex-start;gap:7px;padding:7px 15px;cursor:pointer;transition:background .12s;border-left:2px solid transparent;}
.kw-ctx-item:hover{background:var(--accent-bg);}
.kw-ctx-item.active{background:rgba(83,74,183,.1);border-left-color:#534AB7;}
.kw-ctx-chip{font-size:8px;padding:2px 5px;border-radius:3px;white-space:nowrap;flex-shrink:0;margin-top:2px;}
.kw-ctx-chip.mail{background:rgba(24,95,165,.2);color:#6db3f2;}
.kw-ctx-chip.task{background:rgba(186,117,23,.2);color:#f0b855;}
.kw-ctx-chip.inv{background:rgba(59,109,17,.2);color:#7ecf3f;}
.kw-ctx-chip.offer{background:rgba(83,74,183,.2);color:#CECBF6;}
.kw-ctx-chip.know{background:rgba(15,110,86,.2);color:#3fcfa0;}
.kw-ctx-chip.cust{background:rgba(153,60,29,.2);color:#f08060;}
.kw-ctx-body{flex:1;min-width:0;}
.kw-ctx-title{font-size:12px;font-weight:500;color:var(--text);margin-bottom:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.kw-ctx-sub{font-size:10px;color:var(--text-secondary);}
.kw-ctx-sep{height:1px;background:var(--border);margin:2px 15px;}
.kw-center{flex:1;display:flex;flex-direction:column;background:var(--bg-raised);overflow:hidden;}
.kw-cbar{background:var(--bg);border-bottom:1px solid var(--border);padding:9px 16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;flex-shrink:0;}
.kw-cbar-mode{font-size:11px;padding:3px 9px;border-radius:5px;background:rgba(83,74,183,.2);color:#CECBF6;font-weight:600;}
.kw-cbar-title{font-size:13px;font-weight:500;color:var(--text);}
.kw-cbar-tag{font-size:9px;padding:2px 6px;border-radius:4px;background:rgba(128,128,128,.12);color:var(--text-secondary);}
.kw-cbar-provider{font-size:10px;color:var(--muted);margin-left:auto;display:flex;align-items:center;gap:4px;}
.kw-cbar-provider-dot{width:6px;height:6px;border-radius:50%;background:#1D9E75;}
.kw-cbar-acts{display:flex;gap:4px;}
.kw-cbar-btn{font-size:10px;padding:3px 8px;border-radius:4px;border:1px solid var(--border);background:var(--bg-raised);color:var(--text-secondary);cursor:pointer;white-space:nowrap;}
.kw-cbar-btn:hover{border-color:var(--accent-border);color:var(--text);}
.kw-quick-bar{padding:7px 16px;display:flex;gap:5px;flex-wrap:wrap;border-bottom:1px solid var(--border);background:var(--bg);flex-shrink:0;}
.kw-quick-lbl{font-size:10px;color:var(--muted);align-self:center;margin-right:3px;}
.kw-qb{font-size:10px;padding:4px 10px;border-radius:12px;border:1px solid var(--border);background:var(--bg-raised);color:var(--text-secondary);cursor:pointer;white-space:nowrap;transition:border-color .12s,color .12s;}
.kw-qb:hover{border-color:rgba(83,74,183,.45);color:#CECBF6;}
.kw-tools{width:240px;min-width:240px;border-left:1px solid var(--border);display:flex;flex-direction:column;overflow-y:auto;background:var(--bg);}
.kw-tools.collapsed{display:none;}
.kw-tools-hdr{padding:12px 14px 9px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.kw-tools-t{font-size:12px;font-weight:700;color:var(--text);}
.kw-tools-close{font-size:11px;color:var(--muted);cursor:pointer;padding:2px 5px;border-radius:4px;}
.kw-tools-close:hover{color:var(--text);background:rgba(128,128,128,.1);}
.kw-tools-sec{padding:11px 14px;}
.kw-tools-sh{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:7px;}
.kw-tools-sep{height:1px;background:var(--border);margin:0 14px;}
.kw-t-item{background:var(--bg-raised);border:1px solid var(--border);border-radius:6px;padding:8px 11px;margin-bottom:5px;font-size:11px;color:var(--text);cursor:pointer;transition:border-color .12s;}
.kw-t-item:hover{border-color:var(--accent-border);}
.kw-t-item-h{font-weight:600;margin-bottom:2px;}
.kw-t-item-sub{font-size:10px;color:var(--text-secondary);}
.kw-t-rule{background:rgba(15,110,86,.1);border:1px solid rgba(15,110,86,.25);border-radius:6px;padding:8px 11px;margin-bottom:4px;font-size:11px;color:#3fcfa0;line-height:1.4;}
.kw-t-rule-h{font-weight:600;margin-bottom:2px;color:#5fe8b8;}
.kw-t-next{background:var(--bg-raised);border:1px solid var(--border);border-radius:6px;padding:7px 11px;margin-bottom:4px;font-size:11px;cursor:pointer;color:var(--text-secondary);transition:border-color .12s,color .12s;}
.kw-t-next:hover{border-color:rgba(83,74,183,.4);color:#CECBF6;}
.kw-t-att{display:flex;align-items:center;gap:6px;padding:7px 11px;background:var(--bg-raised);border:1px solid var(--border);border-radius:6px;margin-bottom:4px;font-size:11px;color:var(--text-secondary);cursor:pointer;}
.kira-chat-wrap{display:flex;flex-direction:column;flex:1;overflow:hidden;}
.kira-chat-area{flex:1;overflow-y:auto;padding:16px 20px;}
.kw-input-area{background:var(--bg);border-top:1px solid var(--border);padding:12px 16px;display:flex;align-items:flex-end;gap:8px;flex-shrink:0;}
.kw-input-box{flex:1;background:var(--bg-raised);color:var(--text);border:1px solid var(--border);border-radius:10px;padding:10px 14px;font-size:var(--fs-base);line-height:1.5;resize:none;font-family:inherit;min-height:42px;max-height:120px;overflow-y:auto;}
.kw-input-box:focus{outline:none;border-color:var(--accent-border);}
.kw-input-acts{display:flex;gap:5px;flex-shrink:0;align-items:center;}
.kw-ia{width:32px;height:32px;border-radius:7px;border:1px solid var(--border);background:var(--bg-raised);display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:13px;color:var(--text-secondary);}
.kw-ia:hover{border-color:var(--accent-border);color:var(--text);}
.kw-ia.send{background:#534AB7;border-color:#534AB7;color:#fff;}
.kw-ia.send:hover{background:#6358cc;}
.kw-mode-sel{font-size:10px;padding:4px 9px;border-radius:6px;border:1px solid rgba(83,74,183,.4);background:rgba(83,74,183,.12);color:#CECBF6;cursor:pointer;}
/* Legacy compat */
.kira-ph-title{font-size:15px;font-weight:900;color:var(--accent);}
.kira-ph-sub{font-size:var(--fs-xs);color:var(--muted);margin-top:1px;}
.kira-close{background:none;border:none;color:var(--muted);font-size:20px;cursor:pointer;padding:2px 6px;border-radius:4px;}
.kira-close:hover{color:var(--text);background:rgba(128,128,128,.12);}
.kira-content{flex:1;overflow-y:auto;padding:13px 14px;}
.kira-sec{margin-bottom:14px;}
.kira-sec-title{font-size:10px;font-weight:800;color:var(--accent);letter-spacing:.7px;text-transform:uppercase;margin-bottom:7px;opacity:.8;}
.kira-card{background:rgba(128,128,128,.06);border:1px solid var(--border);border-radius:var(--radius);padding:9px 11px;margin-bottom:7px;cursor:default;}
.kira-card.clickable{cursor:pointer;}
.kira-card.clickable:hover{border-color:var(--accent-border);background:var(--accent-bg);}
.kira-task-card{cursor:pointer;transition:all .2s;}
.kira-task-card:hover{border-color:var(--accent-border);background:var(--accent-bg);transform:translateX(-2px);}
.kira-prio-high{border-left:3px solid var(--danger);}
.kira-prio-med{border-left:3px solid var(--warn);}
.kira-prio-low{border-left:3px solid rgba(128,128,128,.3);}
.kira-fab-pulse{animation:kiraPulse 2s ease-in-out infinite;}
@keyframes kiraPulse{0%,100%{box-shadow:0 3px 15px rgba(0,0,0,.3);}50%{box-shadow:0 3px 25px rgba(220,74,74,.5);}}
.kira-card-title{font-size:var(--fs-base);font-weight:700;margin-bottom:3px;}
.kira-card-meta{font-size:var(--fs-sm);color:var(--muted);}
.kira-input-bar{display:flex;gap:8px;padding:10px 14px;border-top:1px solid var(--border);background:var(--bg-raised);flex-shrink:0;align-items:flex-end;}
.kira-input{flex:1;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:var(--radius-lg);padding:9px 12px;font-size:var(--fs-base);line-height:1.5;resize:none;font-family:inherit;min-height:38px;max-height:120px;overflow-y:auto;}
.kira-input:focus{outline:none;border-color:var(--accent-border);}
.kira-send-btn{background:var(--accent);border:none;border-radius:50%;width:38px;height:38px;color:#fff;font-size:16px;cursor:pointer;flex-shrink:0;display:flex;align-items:center;justify-content:center;transition:all .15s;}
.kira-send-btn:hover{transform:scale(1.06);box-shadow:0 2px 12px rgba(0,0,0,.25);}
.kira-send-btn:disabled{opacity:.4;cursor:default;transform:none;}
.kira-msg{padding:9px 12px;border-radius:12px;margin-bottom:8px;font-size:var(--fs-base);line-height:1.6;max-width:88%;word-wrap:break-word;animation:kiraFadeIn .25s ease;}
@keyframes kiraFadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.kira-msg-user{background:var(--accent-bg);color:var(--text);margin-left:auto;border-bottom-right-radius:4px;border:1px solid var(--accent-border);}
.kira-msg-kira{background:rgba(128,128,128,.08);color:var(--text);border-bottom-left-radius:4px;}
.kira-msg-kira strong{color:var(--accent);}
.kira-msg-kira code{background:rgba(128,128,128,.12);padding:1px 4px;border-radius:3px;font-size:var(--fs-sm);}
.kira-msg-error{background:rgba(220,74,74,.08);color:#d06060;border:1px solid rgba(220,74,74,.18);}
.kira-msg-system{background:var(--accent-bg);color:var(--accent);font-size:var(--fs-sm);text-align:center;max-width:100%;}
.kira-tools-used{margin-top:6px;display:flex;gap:4px;flex-wrap:wrap;}
.kira-tool-badge{font-size:10px;padding:1px 6px;border-radius:4px;background:var(--accent-bg);color:var(--accent);border:1px solid var(--accent-border);}
.kira-typing{display:flex;gap:4px;padding:10px 14px;align-items:center;}
.kira-typing span{width:7px;height:7px;border-radius:50%;background:var(--accent);opacity:.4;animation:kiraTypingDot 1.4s infinite ease-in-out;}
.kira-typing span:nth-child(2){animation-delay:.2s;}
.kira-typing span:nth-child(3){animation-delay:.4s;}
@keyframes kiraTypingDot{0%,80%,100%{opacity:.3;transform:scale(.8)}40%{opacity:1;transform:scale(1.1)}}
.kira-welcome{text-align:center;padding:40px 20px;}
.kira-welcome-icon{width:52px;height:52px;background:#534AB7;border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 14px;font-size:20px;font-weight:900;color:#fff;box-shadow:0 4px 20px rgba(83,74,183,.3);}
.kira-welcome-text{color:var(--muted);font-size:var(--fs-base);line-height:1.7;}
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

        elif self.path.startswith('/api/ausgangsrechnungen'):
            self._api_ausgangsrechnungen()

        elif self.path.startswith('/api/angebote'):
            self._api_angebote()

        elif self.path == '/api/kira/insights':
            self._api_kira_insights()

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

        elif self.path == '/api/kira/conversations':
            self._json(kira_get_conversations())

        elif self.path.startswith('/api/kira/conversation?'):
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            sid = params.get('session_id', [''])[0]
            self._json(kira_get_messages(sid) if sid else [])

        else:
            self._respond(404, 'text/plain', b'Not found')

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

    def _read_mail(self):
        """GET /api/mail/read?message_id=... — Liest Mail-Inhalt."""
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        msg_id = params.get('message_id',[''])[0]
        if not msg_id:
            self._json({"error": "Missing message_id"})
            return
        result = {"betreff":"","absender":"","an":"","datum":"","text":"","anhaenge":[]}
        # 1. Versuche aus kunden.db
        try:
            kdb = sqlite3.connect(str(KUNDEN_DB))
            kdb.row_factory = sqlite3.Row
            row = kdb.execute("SELECT * FROM interaktionen WHERE message_id=?", (msg_id,)).fetchone()
            if row:
                result["betreff"] = row["betreff"] or ""
                result["absender"] = row["absender"] or ""
                result["datum"] = row["datum"] or ""
                result["text"] = row["text_plain"] or ""
                mail_folder = row["mail_folder_pfad"] or ""
                anh_pfad = row["anhaenge_pfad"] or ""
                # Volltext aus mail.json lesen falls text_plain abgeschnitten
                if mail_folder:
                    mj = Path(mail_folder) / "mail.json"
                    if mj.exists():
                        try:
                            md = json.loads(mj.read_text('utf-8'))
                            result["an"] = md.get("an","")
                            # Volltext wenn vorhanden
                            plain = md.get("text","")
                            if plain and len(plain) > len(result["text"]):
                                # Strip HTML
                                import re as re2
                                clean = re2.sub(r'<[^>]+>',' ',plain)
                                clean = re2.sub(r'\s+',' ',clean).strip()
                                if len(clean) > len(result["text"]):
                                    result["text"] = clean
                        except: pass
                # Anhänge auflisten
                att_dir = None
                if anh_pfad and Path(anh_pfad).is_dir():
                    att_dir = Path(anh_pfad)
                elif mail_folder:
                    att_check = Path(mail_folder) / "attachments"
                    if att_check.exists():
                        att_dir = att_check
                if att_dir:
                    for f in sorted(att_dir.iterdir()):
                        if f.is_file():
                            mime = mimetypes.guess_type(str(f))[0] or ''
                            ftype = 'PDF' if 'pdf' in mime else 'Bild' if mime.startswith('image') else 'Datei'
                            result["anhaenge"].append({"name":f.name,"pfad":str(f),"typ":ftype})
            kdb.close()
        except: pass
        # 2. Fallback: Suche in geschaeft.mail_ref
        if not result["text"]:
            try:
                db = get_db()
                grow = db.execute("SELECT * FROM geschaeft WHERE mail_ref=?", (msg_id,)).fetchone()
                if grow:
                    result["betreff"] = grow["betreff"] or ""
                    result["datum"] = grow["datum"] or ""
                    # Versuche mail_folder aus kunden.db
                    if not result["text"]:
                        result["text"] = f"Typ: {grow['typ']}\nBetrag: {grow['betrag'] or ''}\nGegenpartei: {grow['gegenpartei_email'] or ''}"
                db.close()
            except: pass
        self._json(result)

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
        body   = json.loads(self.rfile.read(length) or b'{}')

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

        # WhatsApp Webhook
        if self.path == '/api/webhook/whatsapp':
            self._handle_channel_webhook(body, kanal='whatsapp')
            return

        # Instagram DM Webhook
        if self.path == '/api/webhook/instagram':
            self._handle_channel_webhook(body, kanal='instagram')
            return

        self._respond(404, 'text/plain', b'Not found')

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
    rlog_ensure_cfg()
    alog("Server", "Start", f"Port {port} | Python {__import__('sys').version.split()[0]}", "ok")
    rlog('system', 'server_started', f"Kira Dashboard gestartet auf Port {port}",
         source='server', modul='server', actor_type='system', status='ok')

    httpd = ThreadedHTTPServer(('127.0.0.1', port), DashboardHandler)
    url   = f"http://localhost:{port}"
    print(f"[Kira Dashboard v4] {url}")

    if open_browser and auto_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    # Mail-Monitor starten (Echtzeit-IMAP-Polling)
    monitor_cfg = config.get("mail_monitor", {})
    if monitor_cfg.get("aktiv", True):
        monitor_thread = start_monitor_thread()
        if monitor_thread:
            print("[Mail-Monitor] Gestartet (IMAP-Polling)")
        else:
            print("[Mail-Monitor] Nicht verfügbar (msal fehlt oder keine Config)")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        stop_monitor()
        print("\nServer gestoppt.")


if __name__ == '__main__':
    run_server()
