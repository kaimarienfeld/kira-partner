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
from datetime import datetime
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

from llm_response_gen import generate_draft
from kira_llm import (chat as kira_chat, get_conversations as kira_get_conversations,
                       get_conversation_messages as kira_get_messages,
                       get_api_key as kira_get_api_key, get_config as get_llm_config,
                       get_all_providers, save_provider_key, check_provider_status,
                       PROVIDER_TYPES, generate_daily_briefing)
from mail_monitor import start_monitor_thread, get_monitor_status, stop_monitor

PORT = 8765

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
<div class="task-card {prio_class(prio)}" id="task-{tid}">
  <div class="task-header">
    <div class="task-tags">
      <span class="tag {tag_class}">{tag_text}</span>
      {"<span class='konto-badge'>" + konto + "</span>" if konto else ""}
      {badge}
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
    <button class="btn btn-done"   onclick="setStatus({tid},'erledigt')">Erledigt</button>
    <button class="btn btn-later"  onclick="setStatus({tid},'spaeter')">Später</button>
    <button class="btn btn-ignore" onclick="setStatus({tid},'ignorieren')">Ignorieren</button>
    <button class="btn btn-korr"   onclick="openKorrektur({tid},'{js_esc(kat)}')">Korrektur</button>
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

    # LLM-Briefing (falls verfügbar)
    llm_summary = ""
    try:
        briefing = generate_daily_briefing()
        bz = (briefing.get("zusammenfassung","") or "").strip()
        if bz:
            llm_summary = f'<div class="dash-b-item" style="color:var(--text);font-style:italic;font-size:11px">{esc(bz[:120])}{"&hellip;" if len(bz)>120 else ""}</div>'
    except: pass

    if not briefing_items and not llm_summary:
        briefing_items = ['<div class="dash-b-item" style="color:var(--success)"><span class="dash-b-dot" style="background:var(--success)"></span>Alles im gr&uuml;nen Bereich</div>']

    briefing_html = f'''<div id="kira-briefing" class="dash-briefing">
  <div class="dash-briefing-title">Tagesbriefing</div>
  <div class="dash-briefing-items">
    {"".join(briefing_items)}
    {llm_summary}
  </div>
  <button class="dash-briefing-refresh" onclick="refreshBriefing()">&#x21BB; Aktualisieren</button>
</div>'''

    # ── Zone B: KPI-Karten mit Sparklines ──
    def spark_line(color, pts):
        return f'<div class="dash-kpi-spark"><svg viewBox="0 0 200 34"><polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5" opacity="0.5"/></svg></div>'
    def spark_bars(color, rects):
        return f'<div class="dash-kpi-spark"><svg viewBox="0 0 200 34">{rects}</svg></div>'

    kpi_html = f"""<div class="dash-kpi-grid" id="kpi-bar">
  <div class="dash-kpi {'kpi-danger' if n_antwort>0 else ''}" onclick="filterKomm('Antwort erforderlich')">
    <div class="dash-kpi-label">Antworten n&ouml;tig</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_antwort}</span>{'<span class="dash-kpi-change danger">dringend</span>' if n_antwort>0 else '<span class="dash-kpi-change info">aktuell</span>'}</div>
    {spark_line('#E24B4A','0,30 30,26 60,22 90,28 120,18 150,12 170,8 200,14')}
  </div>
  <div class="dash-kpi {'kpi-accent' if n_leads>0 else ''}" onclick="filterKomm('Neue Lead-Anfrage')">
    <div class="dash-kpi-label">Neue Leads</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_leads}</span><span class="dash-kpi-change info">diese Woche</span></div>
    {spark_line('#378ADD','0,32 30,28 60,30 90,24 120,20 150,16 170,18 200,10')}
  </div>
  <div class="dash-kpi {'kpi-warn' if s_ar_offen>0 else ''}" onclick="showPanel('geschaeft')">
    <div class="dash-kpi-label">Offenes Rechnungsvolumen</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">&euro;&nbsp;{s_ar_offen:,.0f}</span>{'<span class="dash-kpi-change warn">' + str(n_ar_offen) + ' offen</span>' if n_ar_offen>0 else ''}</div>
    {spark_bars('#EF9F27','<rect x="10" y="20" width="22" height="14" rx="2" fill="#EF9F27" opacity="0.3"/><rect x="42" y="14" width="22" height="20" rx="2" fill="#EF9F27" opacity="0.4"/><rect x="74" y="8" width="22" height="26" rx="2" fill="#EF9F27" opacity="0.5"/><rect x="106" y="12" width="22" height="22" rx="2" fill="#EF9F27" opacity="0.4"/><rect x="138" y="6" width="22" height="28" rx="2" fill="#EF9F27" opacity="0.6"/><rect x="170" y="10" width="22" height="24" rx="2" fill="#EF9F27" opacity="0.5"/>')}
  </div>
  <div class="dash-kpi {'kpi-warn' if n_nachfass>0 else ''}" onclick="showPanel('geschaeft');setTimeout(()=>showGeschTab('angebote'),100)">
    <div class="dash-kpi-label">Nachfass f&auml;llig</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_nachfass}</span>{'<span class="dash-kpi-change warn">!! Angebote</span>' if n_nachfass>0 else ''}</div>
    {spark_line('#BA7517','0,20 40,24 80,18 120,26 160,14 200,22')}
  </div>
  <div class="dash-kpi" onclick="filterKomm('Angebotsrückmeldung')">
    <div class="dash-kpi-label">Angebotsrückmeldungen</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_angebot}</span>{'<span class="dash-kpi-change up">offen</span>' if n_angebot>0 else ''}</div>
    {spark_line('#639922','0,28 40,24 80,20 120,16 160,18 200,12')}
  </div>
  <div class="dash-kpi {'kpi-danger' if n_org>0 else ''}" onclick="showPanel('organisation')">
    <div class="dash-kpi-label">Termine / Fristen</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_org}</span>{'<span class="dash-kpi-change danger">heute</span>' if n_org>0 else ''}</div>
  </div>
  <div class="dash-kpi" onclick="showPanel('geschaeft');setTimeout(()=>showGeschTab('eingangsre'),100)">
    <div class="dash-kpi-label">Eingangsrechnungen offen</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_eingang}</span>{'<span class="dash-kpi-change warn">prüfen</span>' if n_eingang>0 else ''}</div>
  </div>
  <div class="dash-kpi" onclick="showPanel('kommunikation')">
    <div class="dash-kpi-label">Gesamt offen</div>
    <div class="dash-kpi-row"><span class="dash-kpi-val">{n_ges}</span></div>
    {spark_line('#888780','0,10 40,14 80,18 120,16 160,20 200,22')}
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
  <div class="dash-prio-actions">
    <button class="dash-btn" onclick="filterKomm('{esc(kat)}')">&#x2192; &Ouml;ffnen</button>
    <button class="dash-btn dash-btn-kira" onclick="openKiraWorkspace('aufgabe')">Mit Kira</button>
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

    signals_html = ""
    if signals:
        sig_items = ""
        for cls, dot_color, text, action in signals[:6]:
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
    # Ansichten / Sub-Tabs
    view_tabs = [
        ("alle", "Alle"),
        ("Antwort erforderlich", "Antwort erforderlich"),
        ("Neue Lead-Anfrage", "Neue Leads"),
        ("Angebotsrückmeldung", "Angebotsrückmeldungen"),
        ("Zur Kenntnis", "Zur Kenntnis"),
        ("Shop / System", "Newsletter / System"),
        ("erledigt", "Abgeschlossen"),
    ]
    tabs_html = '<div class="komm-view-tabs">'
    for key, label in view_tabs:
        active = " active" if key == "alle" else ""
        tabs_html += f'<div class="komm-view-tab{active}" onclick="filterKommView(this,\'{key}\')">{label}</div>'
    tabs_html += '</div>'

    # Filter-Bar
    konten = sorted(set(t.get("konto","") or "" for t in tasks if t.get("konto")))
    konto_opts = "".join(f'<option value="{esc(k)}">{esc(k)}</option>' for k in konten)
    filter_html = f"""<div class="komm-filter-bar">
      <select id="komm-filter-quelle" onchange="applyKommFilters()">
        <option value="">Alle Quellen</option>{konto_opts}
      </select>
      <select id="komm-filter-dringlichkeit" onchange="applyKommFilters()">
        <option value="">Alle Priorit&auml;ten</option>
        <option value="hoch">Hoch</option>
        <option value="mittel">Mittel</option>
        <option value="niedrig">Niedrig</option>
      </select>
      <label class="komm-filter-check"><input type="checkbox" id="komm-filter-antwort" onchange="applyKommFilters()"> Offene Frage</label>
      <label class="komm-filter-check"><input type="checkbox" id="komm-filter-anhang" onchange="applyKommFilters()"> Mit Anh&auml;ngen</label>
      <span id="komm-filter-count" class="komm-filter-count">{len(tasks)} Vorg&auml;nge</span>
    </div>"""

    # Task cards with data attributes for filtering
    groups = [
        ("Antwort erforderlich",  "Antwort erforderlich", []),
        ("Neue Lead-Anfrage",     "Neue Leads",           []),
        ("Angebotsrückmeldung",   "Angebotsrückmeldungen",[]),
        ("Rechnung / Beleg",      "Rechnungen / Belege",  []),
        ("Shop / System",         "Shop / System",        []),
    ]
    rest = []
    for t in tasks:
        kat = t.get("kategorie","")
        placed = False
        for key, label, lst in groups:
            if kat == key:
                lst.append(t)
                placed = True
                break
        if not placed:
            rest.append(t)

    cards_html = ""
    for key, label, lst in groups:
        cards_html += build_section(label, lst)
    if rest:
        cards_html += build_section("Sonstige", rest, collapsed=True)
    if not cards_html:
        cards_html = "<p class='empty'>Keine offenen Kommunikationsaufgaben.</p>"

    return f"""{tabs_html}
{filter_html}
<div id="komm-cards-container">{cards_html}</div>"""

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

    html = f"""
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
    <div id="gesch-zahlungen" class="gesch-panel">{_build_ar_table(ar_bezahlt) if ar_bezahlt else "<p class='empty'>Keine bezahlten Rechnungen.</p>"}</div>
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
    """Übersicht-Tab mit KPI-Cards, dringenden Punkten und Statistik."""
    vol_cls = ' gesch-sum-alarm' if s_ar_offen else ''
    html = f"""<div class="gesch-volumen-hero{vol_cls}" onclick="showGeschTab('ausgangsre')" style="cursor:pointer">
      <div class="gesch-volumen-label">Offenes Volumen (Ausgangsrechnungen)</div>
      <div class="gesch-volumen-num">{s_ar_offen:,.2f} EUR</div>
      <div class="gesch-volumen-sub">{len(ar_offen)} offene Rechnungen</div>
    </div>
    <div class="gesch-summary-grid">
      <div class="gesch-sum-card{' gesch-sum-alarm' if ar_offen else ''}" onclick="showGeschTab('ausgangsre')" style="cursor:pointer">
        <div class="gesch-sum-num">{len(ar_offen)}</div>
        <div class="gesch-sum-label">Offene Ausgangsrechnungen</div>
      </div>
      <div class="gesch-sum-card" onclick="showGeschTab('angebote')" style="cursor:pointer">
        <div class="gesch-sum-num">{len(ang_offen)}</div>
        <div class="gesch-sum-label">Offene Angebote</div>
      </div>
      <div class="gesch-sum-card{' gesch-sum-alarm' if n_nf else ''}" onclick="showGeschTab('angebote')" style="cursor:pointer">
        <div class="gesch-sum-num">{n_nf}</div>
        <div class="gesch-sum-label">Nachfass fällig</div>
      </div>
      <div class="gesch-sum-card{' gesch-sum-alarm' if eingang else ''}" onclick="showGeschTab('eingangsre')" style="cursor:pointer">
        <div class="gesch-sum-num">{len(eingang)}</div>
        <div class="gesch-sum-label">Offene Eingangsrechnungen</div>
      </div>
      <div class="gesch-sum-card{' gesch-sum-alarm' if ar_gemahnt else ''}" onclick="showGeschTab('mahnungen')" style="cursor:pointer">
        <div class="gesch-sum-num">{len(ar_gemahnt)}</div>
        <div class="gesch-sum-label">Gemahnte Rechnungen</div>
      </div>
    </div>"""
    # Skonto-Hinweise (zeitkritisch!)
    skonto_dringend = stats.get("skonto_dringend", []) if stats else []
    if skonto_dringend:
        html += '<div class="section" style="margin-top:16px"><div class="section-title" style="color:#50c878">Skonto-Fristen</div><div class="section-body">'
        for sk in sorted(skonto_dringend, key=lambda x: x["skonto_datum"]):
            tage_rest = (datetime.strptime(sk["skonto_datum"], "%Y-%m-%d").date() - datetime.now().date()).days
            dringend_cls = ' style="color:#e84545"' if tage_rest <= 2 else ""
            html += f'<div class="gesch-urgent-item"><span class="badge badge-korrekt">{sk["skonto_prozent"]}%</span> {sk["re_nr"]} &middot; <span{dringend_cls}>noch {tage_rest} Tage</span> (bis {format_datum(sk["skonto_datum"])}) &middot; Ersparnis: {sk["skonto_betrag"]:,.2f} EUR</div>'
        html += '</div></div>'

    # Dringende Punkte
    urgent = []
    for r in ar_offen[:3]:
        re_nr = esc(r.get("re_nummer", ""))
        kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:30])
        d = r.get("_detail", {})
        ziel = d.get("zahlungsziel_datum", "")
        extra = f' &middot; Fällig: {format_datum(ziel)}' if ziel else ""
        urgent.append(f'<div class="gesch-urgent-item"><span class="gesch-typ-badge gesch-typ-eingang">Rechnung</span> {re_nr} &middot; {kunde} &middot; {format_datum(r.get("datum"))}{extra}</div>')
    for r in ang_offen:
        if (r.get("naechster_nachfass") or "") <= today:
            a_nr = esc(r.get("a_nummer", ""))
            kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:30])
            urgent.append(f'<div class="gesch-urgent-item"><span class="gesch-typ-badge" style="color:var(--kl);background:var(--accent-bg)">Nachfass</span> {a_nr} &middot; {kunde} &middot; Fällig: {r.get("naechster_nachfass","")}</div>')
    for r in ar_gemahnt[:2]:
        re_nr = esc(r.get("re_nummer", ""))
        kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:30])
        mc = r.get("mahnung_count", 0)
        urgent.append(f'<div class="gesch-urgent-item"><span class="gesch-typ-badge gesch-typ-mahnung">Mahnung x{mc}</span> {re_nr} &middot; {kunde}</div>')
    if not urgent:
        urgent.append('<p class="empty">Keine dringenden Punkte.</p>')
    n_urg = len(ar_offen) + n_nf + len(ar_gemahnt)
    html += f"""<div class="section" style="margin-top:16px">
      <div class="section-title">Dringend <span class="count-badge">{n_urg}</span></div>
      <div class="section-body">{"".join(urgent[:7])}</div>
    </div>"""
    # Statistik-Sektion
    if stats:
        s = stats
        ang_total = s.get("ang_total", 0)
        ang_angen = s.get("ang_angenommen", 0)
        ang_abgel = s.get("ang_abgelehnt", 0)
        quote = f"{ang_angen / ang_total * 100:.0f}%" if ang_total >= 3 else "–"
        hinweis = "" if ang_total >= 10 else f'<span class="muted" style="font-size:11px;margin-left:8px">(Datenbasis: {ang_total} Angebote)</span>'
        ar_ges = s.get("ar_gesamt_eur", 0)
        ar_bez = s.get("ar_bezahlt_eur", 0)
        zdauern = s.get("zahlungsdauern", [])
        zd_avg = f'{sum(zdauern)/len(zdauern):.0f}d' if zdauern else "–"
        zd_hinweis = "" if len(zdauern) >= 5 else f' <span class="muted" style="font-size:10px">({len(zdauern)} Werte)</span>'
        html += f"""<div class="section" style="margin-top:16px">
      <div class="section-title">Statistik &amp; Finanzen</div>
      <div class="section-body">
        <div class="gesch-summary-grid" style="grid-template-columns:repeat(auto-fill,minmax(140px,1fr))">
          <div class="gesch-sum-card"><div class="gesch-sum-num">{ar_ges:,.0f} &euro;</div><div class="gesch-sum-label">Fakturiert gesamt</div></div>
          <div class="gesch-sum-card"><div class="gesch-sum-num" style="color:#50c878">{ar_bez:,.0f} &euro;</div><div class="gesch-sum-label">Bezahlt</div></div>
          <div class="gesch-sum-card"><div class="gesch-sum-num">{s.get('ar_bezahlt',0)}/{s.get('ar_total',0)}</div><div class="gesch-sum-label">Rechnungen bezahlt</div></div>
          <div class="gesch-sum-card"><div class="gesch-sum-num">{zd_avg}</div><div class="gesch-sum-label">&Oslash; Zahlungsdauer{zd_hinweis}</div></div>
          <div class="gesch-sum-card"><div class="gesch-sum-num">{quote}</div><div class="gesch-sum-label">Angebotsquote{hinweis}</div></div>
          <div class="gesch-sum-card"><div class="gesch-sum-num">{ang_angen}</div><div class="gesch-sum-label">Angenommen</div></div>
          <div class="gesch-sum-card"><div class="gesch-sum-num">{ang_abgel}</div><div class="gesch-sum-label">Abgelehnt</div></div>
        </div>
      </div>
    </div>"""
    return html


def _build_ar_table(rows):
    """Ausgangsrechnungen-Tab mit Filter, Detail-Infos und Tabelle."""
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
      <select id="ar-filter-year" onchange="filterAR()"><option value="">Alle Jahre</option>{y_opts}</select>
      <select id="ar-filter-status" onchange="filterAR()">
        <option value="">Alle Status</option><option value="offen">Offen</option>
        <option value="bezahlt">Bezahlt</option><option value="streitfall">Streitfall</option>
      </select>
      <span id="ar-count" class="gesch-filter-count">{len(rows)} Rechnungen</span>
    </div>
    <div class="gesch-table" id="ar-table">
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
        if status == "offen":
            acts = f'<button class="btn btn-xs btn-green" onclick="arSetStatus({rid},\'bezahlt\')">Bezahlt</button> <button class="btn btn-xs btn-warn" onclick="arSetStatus({rid},\'streitfall\')">Streitfall</button>'
        elif status == "streitfall":
            acts = f'<button class="btn btn-xs btn-green" onclick="arSetStatus({rid},\'bezahlt\')">Doch bezahlt</button>'
        else:
            acts = '<span style="color:rgba(80,200,120,.6);font-size:11px">&#10003; bezahlt</span>'
        html += f"""<div class="gesch-row ar-row" id="ar-{rid}" data-year="{yr}" data-status="{status}">
          <span class="gc-nr">{re_nr}{m_badge}</span><span class="gc-datum">{format_datum(datum)}</span>
          <span class="gc-partner">{kunde}</span><span class="gc-betrag">{betrag}</span>
          <span class="gc-detail" style="font-size:11px">{detail_html}</span>
          <span class="gc-status"><span class="tag {s_cls}">{status}</span></span>
          <span class="gc-actions">{anh_btn} {mail_btn} {acts}</span>
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
          <span class="gc-actions">{anh_btn} {mail_btn} {acts}</span>
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
def build_einstellungen():
    config = {}
    try:
        config = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
    except: pass

    ntfy = config.get("ntfy", {})
    aufg = config.get("aufgaben", {})
    srv  = config.get("server", {})
    nf   = config.get("nachfass", {})
    llm  = get_llm_config()

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

    def _wissen_card(r, editable=True):
        rid = r['id']
        edit_btn = f"""<button class="btn btn-korr" style="margin-left:8px;font-size:11px;padding:2px 8px;" onclick="editRegel({rid},'{js_esc(r['titel'])}','{js_esc(r['inhalt'])}','{js_esc(r.get('kategorie',''))}')">Bearbeiten</button>""" if editable else ""
        del_btn = f"""<button class="btn btn-ignore" style="margin-left:4px;font-size:11px;padding:2px 8px;" onclick="wissenAction({rid},'loeschen')">Entfernen</button>""" if editable else ""
        return f"""<div class="wissen-card" id="wr-{rid}">
          <div class="wissen-titel">{esc(r['titel'])}</div>
          <div class="wissen-inhalt" id="wi-{rid}">{esc(r['inhalt'])}</div>
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
        biblio_tabs += f'<div class="wissen-tab{active}" onclick="showWissenTab(\'{kat_key}\')">{kat_label} ({len(items)})</div>'
        cards = "".join(_wissen_card(r) for r in items)
        biblio_panels += f'<div id="wissen-{kat_key}" class="wissen-panel{active}">{cards}</div>'
        first = False
    # FAQ und Projektwissen als geplant
    biblio_tabs += '<div class="wissen-tab" onclick="showWissenTab(\'faq\')" style="opacity:.55">FAQ <span class="si-badge planned" style="font-size:9px;padding:0 4px">Geplant</span></div>'
    biblio_tabs += '<div class="wissen-tab" onclick="showWissenTab(\'projektwissen\')" style="opacity:.55">Projektwissen <span class="si-badge planned" style="font-size:9px;padding:0 4px">Geplant</span></div>'
    biblio_panels += '<div id="wissen-faq" class="wissen-panel"><p class="empty">FAQ-Eintr&auml;ge werden hier angezeigt, sobald sie erstellt werden.</p></div>'
    biblio_panels += '<div id="wissen-projektwissen" class="wissen-panel"><p class="empty">Projektwissen wird hier gesammelt &ndash; aus abgeschlossenen Auftr&auml;gen und Erkenntnissen.</p></div>'
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
            cards = "".join(_wissen_card(r, editable=False) for r in items) if items else "<p class='empty'>Noch keine freigegebenen Regeln.</p>"
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
      <button class="btn btn-muted btn-xs" onclick="hardReload()" title="Neu laden" style="border-radius:6px">&#x21BB;</button>
    </div>
  </div>

  <div class="panel active" id="panel-dashboard">{dashboard_html}</div>
  <div class="panel" id="panel-kommunikation">{komm_html}</div>
  <div class="panel" id="panel-organisation">{org_html}</div>
  <div class="panel" id="panel-geschaeft">{gesch_html}</div>
  <div class="panel" id="panel-wissen">{wissen_html}</div>
  <div class="panel" id="panel-einstellungen">{einstell_html}</div>

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
<div class="kira-quick" id="kiraQuick">
  <div class="kira-quick-header">
    <span style="font-weight:800;color:var(--accent)">Kira</span>
    <button class="kira-close" onclick="closeKiraQuick()">&times;</button>
  </div>
  <div class="kira-quick-actions">
    <div class="kira-quick-item" onclick="openKiraWorkspace('chat')">
      <span class="kira-quick-icon">&#x1F4AC;</span>
      <div><strong>Frage stellen</strong><br><span class="muted">Kira direkt etwas fragen</span></div>
    </div>
    <div class="kira-quick-item" onclick="openKiraWorkspace('aufgabe')">
      <span class="kira-quick-icon">&#x2709;</span>
      <div><strong>Aufgabe besprechen</strong><br><span class="muted">Offene Vorg&auml;nge mit Kira kl&auml;ren</span></div>
    </div>
    <div class="kira-quick-item" onclick="showPanel('geschaeft');closeKiraQuick()">
      <span class="kira-quick-icon">&#x1F4B0;</span>
      <div><strong>Rechnung pr&uuml;fen</strong><br><span class="muted">Rechnungen und Zahlungen</span></div>
    </div>
    <div class="kira-quick-item" onclick="showPanel('geschaeft');setTimeout(()=>showGeschTab('angebote'),100);closeKiraQuick()">
      <span class="kira-quick-icon">&#x1F4C4;</span>
      <div><strong>Angebot pr&uuml;fen</strong><br><span class="muted">Offene Angebote und Nachfass</span></div>
    </div>
    <div class="kira-quick-item" onclick="showPanel('kunden');closeKiraQuick()">
      <span class="kira-quick-icon">&#x1F465;</span>
      <div><strong>Kunde &ouml;ffnen</strong><br><span class="muted">Kunden-Informationen</span></div>
    </div>
    <div class="kira-quick-item" onclick="openKiraWorkspace('chat');closeKiraQuick()">
      <span class="kira-quick-icon">&#x1F50D;</span>
      <div><strong>Suche</strong><br><span class="muted">Kira nach Informationen fragen</span></div>
    </div>
  </div>
</div>

<!-- Kira Workspace (Modus C) — voller Assistenz-Arbeitsbereich -->
<div class="kira-workspace-overlay" id="kiraWorkspace">
  <div class="kira-workspace">
    <div class="kira-ws-header">
      <div style="display:flex;align-items:center;gap:10px">
        <span class="briefing-icon">K</span>
        <div>
          <div class="kira-ph-title">Kira Workspace</div>
          <div class="kira-ph-sub">KI-Assistenz</div>
        </div>
      </div>
      <div style="display:flex;gap:6px;align-items:center">
        <button class="btn btn-xs btn-muted" onclick="newKiraChat()">Neuer Chat</button>
        <button class="kira-close" onclick="closeKiraWorkspace()">&times;</button>
      </div>
    </div>
    <div class="kira-ws-body">
      <!-- Links: Kontexte / Threads -->
      <div class="kira-ws-sidebar">
        <div class="kira-ws-sidebar-title">Kontexte</div>
        <div class="kira-ws-ctx-list">
          <div class="kira-ws-ctx active" onclick="showKTab('chat')">&#x1F4AC; Chat</div>
          <div class="kira-ws-ctx" onclick="showKTab('aufgaben')">&#x2709; Aufgaben</div>
          <div class="kira-ws-ctx" onclick="showKTab('muster')">&#x1F4CA; Muster</div>
          <div class="kira-ws-ctx" onclick="showKTab('kwissen')">&#x1F4DA; Gelernt</div>
          <div class="kira-ws-ctx" onclick="showKTab('historie')">&#x1F4C2; Historie</div>
        </div>
        <div class="kira-ws-sidebar-title" style="margin-top:14px">Vorbereitet</div>
        <div class="kira-ws-ctx-list">
          <div class="kira-ws-ctx planned-ctx">&#x1F465; Kunde</div>
          <div class="kira-ws-ctx planned-ctx">&#x1F4C4; Angebot</div>
          <div class="kira-ws-ctx planned-ctx">&#x1F4B0; Rechnung</div>
          <div class="kira-ws-ctx planned-ctx">&#x1F4C1; Dokument</div>
          <div class="kira-ws-ctx planned-ctx">&#x1F50D; Recherche</div>
          <div class="kira-ws-ctx planned-ctx">&#x1F4E3; Marketing</div>
          <div class="kira-ws-ctx planned-ctx">&#x1F4AC; Social</div>
        </div>
      </div>
      <!-- Mitte: Chat / Hauptinhalt -->
      <div class="kira-ws-main" id="kiraContent">
        <div id="kc-chat" class="kira-chat-wrap" style="display:flex">
          <div class="kira-chat-area" id="kiraChatArea">
            <div class="kira-welcome">
              <div class="kira-welcome-icon">K</div>
              <div class="kira-welcome-text">Hallo! Ich bin Kira, deine KI-Assistentin.<br>
              Frag mich zu Rechnungen, Angeboten, Kunden &mdash; oder lass uns offene Aufgaben besprechen.</div>
            </div>
          </div>
          <div class="kira-input-bar">
            <textarea id="kiraInput" class="kira-input" placeholder="Nachricht an Kira..." rows="1"
              onkeydown="if(event.key==='Enter'&&!event.shiftKey){{event.preventDefault();sendKiraMsg()}}"
              oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,120)+'px'"></textarea>
            <button class="kira-send-btn" onclick="sendKiraMsg()" id="kiraSendBtn">&#x27A4;</button>
          </div>
        </div>
        <div id="kc-aufgaben" style="display:none">
          <div id="kira-aufgaben-list"><div style="color:var(--muted);font-size:var(--fs-base);">Lade&hellip;</div></div>
        </div>
        <div id="kc-muster" style="display:none">
          <div id="kira-muster-content"><div style="color:var(--muted);font-size:var(--fs-base);">Lade&hellip;</div></div>
        </div>
        <div id="kc-kwissen" style="display:none">
          <div id="kira-lernen-list"><div style="color:var(--muted);font-size:var(--fs-base);">Lade&hellip;</div></div>
        </div>
        <div id="kc-historie" style="display:none">
          <div id="kira-historie-list"><div style="color:var(--muted);font-size:var(--fs-base);">Lade&hellip;</div></div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Korrektur Modal -->
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
    <div class="modal-actions">
      <button class="btn btn-done" onclick="saveKorrektur()">Speichern</button>
      <button class="btn btn-ignore" onclick="closeKorrModal()">Abbrechen</button>
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
const KIRA_CTX = {json.dumps(kira_ctx, ensure_ascii=False)};
const PROMPTS  = {json.dumps(prompts_json, ensure_ascii=False)};
let kiraOpen = false;

// ═══ SIDEBAR & NAV ═══
const PANEL_TITLES = {{
  dashboard:'Start', kommunikation:'Kommunikation', organisation:'Organisation',
  geschaeft:'Gesch\u00e4ft', wissen:'Wissen', einstellungen:'Einstellungen',
  kunden:'Kunden', marketing:'Marketing',
  social:'Social / DMs', automationen:'Automationen', analysen:'Analysen'
}};

function showPanel(name) {{
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

// Kommunikation View-Tabs
function filterKommView(el, kat) {{
  document.querySelectorAll('.komm-view-tab').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
  const container = document.getElementById('komm-cards-container');
  if(!container) return;
  if(kat === 'alle') {{
    container.querySelectorAll('.section').forEach(s=>s.style.display='');
    container.querySelectorAll('.task-card').forEach(c=>c.style.display='');
  }} else if(kat === 'erledigt') {{
    container.querySelectorAll('.section').forEach(s=>s.style.display='none');
  }} else {{
    container.querySelectorAll('.section').forEach(s=>{{
      const title = s.querySelector('.section-title')?.textContent||'';
      const match = kat==='Antwort erforderlich' && title.includes('Antwort') ||
        kat==='Neue Lead-Anfrage' && title.includes('Leads') ||
        kat==='Angebotsrückmeldung' && title.includes('Angebots') ||
        kat==='Zur Kenntnis' && title.includes('Kenntnis') ||
        kat==='Shop / System' && (title.includes('Shop')||title.includes('Newsletter'));
      s.style.display = match ? '' : 'none';
      if(match) s.classList.remove('collapsed');
    }});
  }}
  applyKommFilters();
}}

// Kommunikation Filter
function applyKommFilters() {{
  const quelle = document.getElementById('komm-filter-quelle')?.value||'';
  const prio = document.getElementById('komm-filter-dringlichkeit')?.value||'';
  const nurAntwort = document.getElementById('komm-filter-antwort')?.checked||false;
  const nurAnhang = document.getElementById('komm-filter-anhang')?.checked||false;
  let count = 0;
  document.querySelectorAll('#komm-cards-container .task-card').forEach(card=>{{
    let show = true;
    if(quelle) {{
      const kb = card.querySelector('.konto-badge');
      if(!kb || !kb.textContent.includes(quelle)) show = false;
    }}
    if(prio) {{
      if(!card.classList.contains('prio-'+prio)) show = false;
    }}
    if(nurAntwort) {{
      if(!card.querySelector('.btn-kira')) show = false;
    }}
    if(nurAnhang) {{
      const btns = card.querySelectorAll('.btn');
      const hasAnh = Array.from(btns).some(b=>b.textContent.includes('Anh'));
      if(!hasAnh) show = false;
    }}
    card.style.display = show ? '' : 'none';
    if(show) count++;
  }});
  const ce = document.getElementById('komm-filter-count');
  if(ce) ce.textContent = count + ' Vorg\u00e4nge';
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
  fetch('/api/task/'+id+'/status',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{status}})}}).then(r=>r.json()).then(d=>{{
    if(d.ok){{
      const el = document.getElementById('task-'+id);
      if(el){{el.style.opacity='0.2';setTimeout(()=>el.remove(),320);}}
      showToast('Aktualisiert');
    }}
  }}).catch(()=>showToast('Fehler'));
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

// Ausgangsrechnungen filtern
function filterAR() {{
  const year = document.getElementById('ar-filter-year').value;
  const status = document.getElementById('ar-filter-status').value;
  let count = 0;
  document.querySelectorAll('.ar-row').forEach(row => {{
    const show = (!year || row.dataset.year === year) && (!status || row.dataset.status === status);
    row.style.display = show ? '' : 'none';
    if (show) count++;
  }});
  document.getElementById('ar-count').textContent = count + ' Rechnungen';
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

// Wissen sub-tabs
function showWissenTab(name) {{
  document.querySelectorAll('.wissen-tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.wissen-panel').forEach(p=>p.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('wissen-'+name)?.classList.add('active');
}}

// Wissen actions
function wissenAction(regelId, aktion) {{
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
  if(context==='chat') showKTab('chat');
  else if(context==='aufgabe') showKTab('aufgaben');
}}
function closeKiraWorkspace() {{
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
  // Update workspace sidebar active state
  document.querySelectorAll('.kira-ws-ctx').forEach(c=>c.classList.remove('active'));
  document.querySelectorAll('.kira-ws-ctx').forEach(c=>{{
    if(c.textContent.toLowerCase().includes(name==='kwissen'?'gelernt':name==='muster'?'muster':name)) c.classList.add('active');
  }});
  document.querySelectorAll('[id^=kc-]').forEach(c=>c.style.display='none');
  const content = document.getElementById('kc-'+name);
  if(content) content.style.display = name==='chat' ? 'flex' : 'block';
  document.getElementById('kiraContent')?.classList.toggle('kira-chat-mode', name==='chat');
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
  kiraSessionId = null;
  const area = document.getElementById('kiraChatArea');
  area.innerHTML = '<div class="kira-welcome"><div class="kira-welcome-icon">K</div><div class="kira-welcome-text">Neuer Chat gestartet. Wie kann ich helfen?</div></div>';
  document.getElementById('kiraInput').value = '';
  showKTab('chat');
}}

// Hard Reset — Cache umgehen, alles neu laden
function hardReload() {{
  // Cache-Busting: URL mit Timestamp
  window.location.href = '/?nocache=' + Date.now();
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
function saveKorrektur(){{
  const tid  = document.getElementById('korr-tid').value;
  const alt  = document.getElementById('korr-alt').value;
  const neu  = document.getElementById('korr-neu').value;
  const notiz= document.getElementById('korr-notiz').value;
  if(!neu&&!notiz){{ showToast('Bitte Kategorie oder Notiz angeben'); return; }}
  fetch('/api/task/'+tid+'/korrektur',{{
    method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{alter_typ:alt,neuer_typ:neu,notiz}})
  }}).then(r=>r.json()).then(()=>{{
    closeKorrModal();
    showToast('Korrektur gespeichert');
    setTimeout(()=>location.reload(),600);
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
document.addEventListener('keydown',e=>{{
  if(e.key==='Escape'){{
    if(document.getElementById('kiraInteraktModal').classList.contains('open')) closeKiraInterakt();
    else if(document.getElementById('mailReadModal').classList.contains('open')) closeMailRead();
    else if(document.getElementById('geschBewertModal').classList.contains('open')) closeGeschBewertung();
    else if(document.getElementById('editRegelModal').classList.contains('open')) closeEditRegel();
    else if(document.getElementById('korrModal').classList.contains('open')) closeKorrModal();
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

/* Zone A: Tagesbriefing — horizontal bar */
.dash-briefing{background:var(--bg-raised);border:0.5px solid var(--border);border-radius:10px;
  padding:12px 20px;margin-bottom:16px;display:flex;align-items:center;gap:20px;flex-wrap:wrap;}
.dash-briefing-title{font-size:14px;font-weight:600;color:var(--text);white-space:nowrap;flex-shrink:0;}
.dash-briefing-items{display:flex;align-items:center;gap:18px;flex-wrap:wrap;flex:1;}
.dash-b-item{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-secondary);white-space:nowrap;}
.dash-b-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;}
.dash-briefing-refresh{margin-left:auto;background:var(--bg);border:0.5px solid var(--border-strong);
  border-radius:6px;padding:4px 10px;font-size:11px;color:var(--text-secondary);cursor:pointer;
  flex-shrink:0;transition:background .12s;}
.dash-briefing-refresh:hover{background:var(--accent-bg);color:var(--accent);}

/* Zone B: KPI Grid */
.dash-kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:20px;}
@media(max-width:1100px){.dash-kpi-grid{grid-template-columns:repeat(4,minmax(0,1fr));}}
@media(max-width:860px){.dash-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}
@media(max-width:480px){.dash-kpi-grid{grid-template-columns:1fr 1fr;}}
.dash-kpi{background:var(--bg-raised);border:0.5px solid var(--border);border-radius:10px;
  padding:16px 18px;cursor:pointer;transition:border-color .2s,box-shadow .2s,transform .12s;position:relative;}
.dash-kpi:hover{border-color:var(--accent);box-shadow:0 2px 12px rgba(0,0,0,.06);transform:translateY(-1px);}
.dash-kpi-label{font-size:12px;color:var(--muted);margin-bottom:6px;line-height:1.3;}
.dash-kpi-row{display:flex;align-items:baseline;gap:8px;}
.dash-kpi-val{font-size:26px;font-weight:500;color:var(--text);line-height:1.1;}
.dash-kpi-change{font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px;white-space:nowrap;}
.dash-kpi-change.up{background:#EAF3DE;color:#3B6D11;}
.dash-kpi-change.warn{background:#FAEEDA;color:#854F0B;}
.dash-kpi-change.danger{background:#FCEBEB;color:#A32D2D;}
.dash-kpi-change.info{background:#E6F1FB;color:#185FA5;}
.dash-kpi-spark{margin-top:10px;height:34px;overflow:hidden;}
.dash-kpi-spark svg{width:100%;height:34px;}
/* KPI state variants */
.dash-kpi.kpi-danger{border-color:rgba(226,75,74,.3);}
.dash-kpi.kpi-danger .dash-kpi-val{color:#E24B4A;}
.dash-kpi.kpi-warn{border-color:rgba(239,159,39,.3);}
.dash-kpi.kpi-warn .dash-kpi-val{color:#EF9F27;}
.dash-kpi.kpi-accent{border-color:var(--accent-border);background:var(--accent-bg);}
.dash-kpi.kpi-accent .dash-kpi-val{color:var(--accent);}

/* Zone C: Work Blocks */
.dash-work-grid{display:grid;grid-template-columns:63fr 37fr;gap:16px;margin-bottom:20px;}
@media(max-width:900px){.dash-work-grid{grid-template-columns:1fr;}}
.dash-panel{background:var(--bg-raised);border:0.5px solid var(--border);border-radius:10px;padding:18px 20px;}
.dash-panel-title{font-size:15px;font-weight:600;color:var(--text);margin-bottom:3px;}
.dash-panel-sub{font-size:11px;color:var(--muted);margin-bottom:14px;}
.dash-right-col{display:flex;flex-direction:column;gap:14px;}

/* Heute priorisiert cards */
.dash-prio-item{display:flex;align-items:flex-start;gap:12px;padding:11px 14px;
  background:var(--bg);border:0.5px solid var(--border);border-radius:8px;
  border-left:3px solid #ccc;margin-bottom:8px;transition:box-shadow .15s;}
.dash-prio-item:last-child{margin-bottom:0;}
.dash-prio-item:hover{box-shadow:0 2px 8px rgba(0,0,0,.06);}
.dash-prio-item.prio-red{border-left-color:#E24B4A;}
.dash-prio-item.prio-amber{border-left-color:#EF9F27;}
.dash-prio-item.prio-blue{border-left-color:#378ADD;}
.dash-prio-item.prio-green{border-left-color:#1D9E75;}
.dash-prio-item.prio-gray{border-left-color:#B4B2A9;}
.dash-prio-body{flex:1;min-width:0;}
.dash-prio-title{font-size:13px;font-weight:500;color:var(--text);margin-bottom:2px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.dash-prio-meta{font-size:11px;color:var(--muted);margin-bottom:5px;}
.dash-prio-tags{display:flex;gap:4px;flex-wrap:wrap;align-items:center;}
.dash-tag{font-size:10px;padding:2px 7px;border-radius:4px;white-space:nowrap;font-weight:500;}
.dash-tag-red{background:#FCEBEB;color:#A32D2D;}
.dash-tag-amber{background:#FAEEDA;color:#854F0B;}
.dash-tag-blue{background:#E6F1FB;color:#185FA5;}
.dash-tag-gray{background:#F1EFE8;color:#5F5E5A;}
.dash-tag-green{background:#EAF3DE;color:#3B6D11;}
.dash-prio-next{font-size:10px;color:var(--muted);margin-left:2px;}
.dash-prio-actions{display:flex;gap:4px;margin-left:auto;flex-shrink:0;align-items:flex-start;padding-top:2px;}
.dash-btn{font-size:10px;padding:4px 10px;border-radius:5px;border:0.5px solid var(--border-strong);
  background:var(--bg);color:var(--text-secondary);cursor:pointer;white-space:nowrap;
  transition:background .12s;font-family:inherit;}
.dash-btn:hover{background:var(--accent-bg);border-color:var(--accent-border);color:var(--accent);}
.dash-btn-kira{background:#EEEDFE;border-color:#CECBF6;color:#534AB7;}
.dash-btn-kira:hover{background:#DDD9FA;}

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
.dash-signals{background:var(--bg-raised);border:0.5px solid var(--border);border-radius:10px;
  padding:18px 20px;margin-bottom:20px;}
.dash-sig-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:12px;}
@media(max-width:860px){.dash-sig-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}
@media(max-width:480px){.dash-sig-grid{grid-template-columns:1fr;}}
.dash-sig{padding:10px 14px;border-radius:8px;border:0.5px solid;display:flex;align-items:flex-start;
  gap:8px;font-size:11px;cursor:pointer;transition:opacity .15s;line-height:1.45;}
.dash-sig:hover{opacity:.8;}
.dash-sig .sig-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-top:3px;}
.dash-sig .sig-text{flex:1;}
.dash-sig .sig-arr{margin-left:auto;font-size:12px;opacity:.5;flex-shrink:0;}
.dash-sig.s-red{background:#FCEBEB;border-color:#F7C1C1;color:#791F1F;}
.dash-sig.s-amber{background:#FAEEDA;border-color:#FAC775;color:#633806;}
.dash-sig.s-blue{background:#E6F1FB;border-color:#B5D4F4;color:#0C447C;}
.dash-sig.s-coral{background:#FAECE7;border-color:#F5C4B3;color:#712B13;}
.dash-sig.s-teal{background:#E1F5EE;border-color:#9FE1CB;color:#085041;}
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
  padding:12px 14px;margin-bottom:8px;transition:border-color .2s;}
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
.btn-later{background:rgba(212,147,62,.1);color:var(--warn);border:1px solid rgba(212,147,62,.2);}
.btn-later:hover{background:rgba(212,147,62,.2);}
.btn-ignore{background:rgba(128,128,128,.08);color:rgba(128,128,128,.7);border:1px solid rgba(128,128,128,.18);}
.btn-ignore:hover{background:rgba(128,128,128,.16);}
.btn-korr{background:rgba(128,128,128,.05);color:var(--muted);border:1px solid var(--border);}
.btn-korr:hover{background:rgba(128,128,128,.12);color:var(--text);}
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
.gesch-tabs,.wissen-tabs{display:flex;gap:2px;margin-bottom:14px;flex-wrap:wrap;}
.gesch-tab,.wissen-tab{padding:6px 14px;border-radius:var(--radius);cursor:pointer;font-size:var(--fs-sm);font-weight:700;
  color:var(--muted);border:1px solid transparent;transition:all .15s;user-select:none;}
.gesch-tab:hover,.wissen-tab:hover{color:var(--text);background:rgba(128,128,128,.08);}
.gesch-tab.active,.wissen-tab.active{color:var(--accent);background:var(--accent-bg);border-color:var(--accent-border);}
.gesch-panel,.wissen-panel{display:none;}
.gesch-panel.active,.wissen-panel.active{display:block;}
.gesch-summary-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;}
.gesch-sum-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:12px;text-align:center;}
.gesch-sum-num{font-size:var(--fs-xl);font-weight:900;color:var(--accent);}
.gesch-sum-label{font-size:var(--fs-xs);color:var(--muted);margin-top:2px;}
.gesch-table{font-size:var(--fs-sm);}
.gesch-row{display:flex;gap:6px;padding:6px 4px;border-bottom:1px solid var(--border);align-items:center;}
.gesch-header{font-weight:700;color:var(--accent);border-bottom:1px solid var(--border-strong);}
.gc-typ{min-width:100px;}
.gc-datum{min-width:80px;color:var(--muted);}
.gc-betrag{min-width:80px;text-align:right;font-weight:600;}
.gc-nr{min-width:90px;color:var(--muted);}
.gc-partner{min-width:120px;flex:1;}
.gc-betreff{flex:2;color:var(--text-secondary);}
.gesch-typ-badge{font-size:10px;font-weight:700;color:var(--accent);background:var(--accent-bg);padding:1px 6px;border-radius:3px;}
.gesch-sum-alarm{border-color:rgba(220,74,74,.3);background:rgba(220,74,74,.04);}
.gesch-sum-alarm .gesch-sum-num{color:var(--danger);}
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
.gesch-routine-row{opacity:.7;}.gesch-routine-row:hover{opacity:1;}
.gesch-row-aktiv{border-left:2px solid var(--danger);}
.gesch-row-routine{opacity:.55;}
.gc-detail{min-width:100px;flex:1;color:var(--muted);}
.gc-actions{display:flex;gap:4px;min-width:100px;justify-content:flex-end;}
.gesch-ar-summary{display:flex;gap:20px;padding:10px 14px;margin-bottom:10px;background:var(--accent-bg);
  border:1px solid var(--border);border-radius:var(--radius);font-size:var(--fs-base);flex-wrap:wrap;}
.gesch-ar-summary span{white-space:nowrap;}
.gesch-volumen-hero{background:linear-gradient(135deg,var(--accent-bg),transparent);border:1px solid var(--accent-border);
  border-radius:var(--radius-lg);padding:18px 24px;margin-bottom:16px;text-align:center;transition:border-color .2s;}
.gesch-volumen-hero:hover{border-color:var(--accent);}
.gesch-volumen-hero.gesch-sum-alarm{border-color:rgba(220,74,74,.3);background:linear-gradient(135deg,rgba(220,74,74,.05),transparent);}
.gesch-volumen-label{font-size:var(--fs-sm);color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;}
.gesch-volumen-num{font-size:28px;font-weight:800;color:var(--accent);letter-spacing:-.5px;}
.gesch-volumen-hero.gesch-sum-alarm .gesch-volumen-num{color:var(--danger);}
.gesch-volumen-sub{font-size:var(--fs-sm);color:var(--muted);margin-top:2px;}
.gesch-sum-card{cursor:pointer;transition:border-color .2s,transform .1s;}
.gesch-sum-card:hover{border-color:var(--accent-border);transform:translateY(-1px);}
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
  flex-direction:column;cursor:pointer;box-shadow:0 4px 18px rgba(0,0,0,.25);
  transition:transform .2s,box-shadow .2s;border:none;color:#fff;position:fixed;}
.kira-fab:hover{transform:scale(1.07);box-shadow:0 6px 26px rgba(83,74,183,.45);}
.kira-fab-k{color:#fff;font-size:16px;font-weight:600;line-height:1;}
.kira-fab-label{color:#CECBF6;font-size:8px;margin-top:1px;line-height:1;}
.kira-fab-status{position:absolute;top:1px;right:1px;width:12px;height:12px;
  background:#1D9E75;border-radius:50%;border:2px solid var(--bg);}

/* ═══ Kira Quick Panel (Modus B) ═══ */
.kira-quick{position:fixed;bottom:82px;right:22px;z-index:250;width:320px;
  background:var(--bg-raised);border:1px solid var(--border-strong);border-radius:var(--radius-lg);
  box-shadow:0 8px 40px rgba(0,0,0,.35);display:none;flex-direction:column;overflow:hidden;}
.kira-quick.open{display:flex;}
.kira-quick-header{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border);}
.kira-quick-actions{padding:6px 0;}
.kira-quick-item{display:flex;align-items:center;gap:12px;padding:10px 16px;cursor:pointer;transition:background .12s;font-size:var(--fs-sm);}
.kira-quick-item:hover{background:var(--accent-bg);}
.kira-quick-icon{font-size:18px;width:24px;text-align:center;flex-shrink:0;}
.kira-quick-item strong{font-size:var(--fs-base);color:var(--text);}

/* ═══ Kira Workspace (Modus C) ═══ */
.kira-workspace-overlay{display:none;position:fixed;inset:0;z-index:350;background:rgba(0,0,0,.6);align-items:center;justify-content:center;padding:20px;}
.kira-workspace-overlay.open{display:flex;}
.kira-workspace{background:var(--bg-raised);border:1px solid var(--border-strong);border-radius:var(--radius-lg);
  width:95vw;max-width:1200px;height:85vh;display:flex;flex-direction:column;box-shadow:0 12px 60px rgba(0,0,0,.5);overflow:hidden;}
.kira-ws-header{display:flex;justify-content:space-between;align-items:center;padding:14px 20px;
  border-bottom:1px solid var(--border);flex-shrink:0;}
.kira-ws-body{display:flex;flex:1;overflow:hidden;}
.kira-ws-sidebar{width:200px;border-right:1px solid var(--border);padding:12px;overflow-y:auto;flex-shrink:0;background:var(--bg);}
.kira-ws-sidebar-title{font-size:10px;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;padding:4px 8px;margin-bottom:4px;}
.kira-ws-ctx-list{display:flex;flex-direction:column;gap:2px;margin-bottom:8px;}
.kira-ws-ctx{padding:7px 10px;border-radius:var(--radius);cursor:pointer;font-size:var(--fs-sm);color:var(--text-secondary);transition:all .12s;}
.kira-ws-ctx:hover{background:var(--accent-bg);color:var(--text);}
.kira-ws-ctx.active{background:var(--accent-bg);color:var(--accent);font-weight:700;}
.kira-ws-ctx.planned-ctx{opacity:.4;cursor:default;font-style:italic;}
.kira-ws-main{flex:1;display:flex;flex-direction:column;overflow:hidden;}

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

/* Kira Chat */
.kira-content.kira-chat-mode{overflow:hidden;padding:0;}
.kira-chat-wrap{display:flex;flex-direction:column;flex:1;overflow:hidden;}
.kira-chat-area{flex:1;overflow-y:auto;padding:13px 14px;}
.kira-input-bar{display:flex;gap:8px;padding:10px 14px;border-top:1px solid var(--border);
  background:var(--bg-raised);flex-shrink:0;align-items:flex-end;}
.kira-input{flex:1;background:var(--bg);color:var(--text);border:1px solid var(--border);
  border-radius:var(--radius-lg);padding:9px 12px;font-size:var(--fs-base);line-height:1.5;resize:none;
  font-family:inherit;min-height:38px;max-height:120px;overflow-y:auto;}
.kira-input:focus{outline:none;border-color:var(--accent-border);}
.kira-send-btn{background:var(--accent);border:none;border-radius:50%;
  width:38px;height:38px;color:#fff;font-size:16px;cursor:pointer;flex-shrink:0;
  display:flex;align-items:center;justify-content:center;transition:all .15s;}
.kira-send-btn:hover{transform:scale(1.06);box-shadow:0 2px 12px rgba(0,0,0,.25);}
.kira-send-btn:disabled{opacity:.4;cursor:default;transform:none;}
.kira-msg{padding:9px 12px;border-radius:12px;margin-bottom:8px;font-size:var(--fs-base);line-height:1.6;
  max-width:88%;word-wrap:break-word;animation:kiraFadeIn .25s ease;}
@keyframes kiraFadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.kira-msg-user{background:var(--accent-bg);color:var(--text);margin-left:auto;border-bottom-right-radius:4px;border:1px solid var(--accent-border);}
.kira-msg-kira{background:rgba(128,128,128,.08);color:var(--text);border-bottom-left-radius:4px;}
.kira-msg-kira strong{color:var(--accent);}
.kira-msg-kira code{background:rgba(128,128,128,.12);padding:1px 4px;border-radius:3px;font-size:var(--fs-sm);}
.kira-msg-error{background:rgba(220,74,74,.08);color:#d06060;border:1px solid rgba(220,74,74,.18);}
.kira-msg-system{background:var(--accent-bg);color:var(--accent);font-size:var(--fs-sm);text-align:center;max-width:100%;}
.kira-tools-used{margin-top:6px;display:flex;gap:4px;flex-wrap:wrap;}
.kira-tool-badge{font-size:10px;padding:1px 6px;border-radius:4px;background:var(--accent-bg);
  color:var(--accent);border:1px solid var(--accent-border);}
.kira-typing{display:flex;gap:4px;padding:10px 14px;align-items:center;}
.kira-typing span{width:7px;height:7px;border-radius:50%;background:var(--accent);opacity:.4;
  animation:kiraTypingDot 1.4s infinite ease-in-out;}
.kira-typing span:nth-child(2){animation-delay:.2s;}
.kira-typing span:nth-child(3){animation-delay:.4s;}
@keyframes kiraTypingDot{0%,80%,100%{opacity:.3;transform:scale(.8)}40%{opacity:1;transform:scale(1.1)}}
.kira-welcome{text-align:center;padding:40px 20px;}
.kira-welcome-icon{width:56px;height:56px;background:var(--accent);
  border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 14px;
  font-size:22px;font-weight:900;color:#fff;box-shadow:0 4px 20px rgba(0,0,0,.2);}
.kira-welcome-text{color:var(--muted);font-size:var(--fs-base);line-height:1.7;}
#kc-aufgaben,#kc-muster,#kc-kwissen,#kc-historie{overflow-y:auto;padding:13px 14px;flex:1;}

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
        if self.path in ('/', '/dashboard', '/index.html'):
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
                self._json({'ok': True})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return

        self._respond(404, 'text/plain', b'Not found')

    def _handle_task_action(self, task_id, action, body):
        if action == 'status':
            from task_manager import update_task_status
            ok = update_task_status(task_id, body.get('status',''), body.get('notiz',''))
            self._json({'ok': ok})

        elif action == 'korrektur':
            db = get_db()
            try:
                alter = body.get('alter_typ','')
                neu   = body.get('neuer_typ','')
                notiz = body.get('notiz','')
                db.execute("INSERT INTO corrections (task_id,alter_typ,neuer_typ,notiz) VALUES (?,?,?,?)",
                           (task_id, alter, neu, notiz))
                if neu and neu != alter:
                    db.execute("UPDATE tasks SET kategorie=? WHERE id=?", (neu, task_id))
                db.commit()
                self._json({'ok': True})
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
        b = html.encode('utf-8')
        self._respond(200, 'text/html; charset=utf-8', b)

    def _json(self, data):
        b = json.dumps(data, default=str, ensure_ascii=False).encode('utf-8')
        self._respond(200, 'application/json', b)

    def _respond(self, code, ctype, body):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)


# ── Start ─────────────────────────────────────────────────────────────────────
def run_server(open_browser=True):
    config = {}
    try:
        config = json.loads((SCRIPTS_DIR / "config.json").read_text('utf-8'))
    except: pass

    port      = config.get("server", {}).get("port", PORT)
    auto_open = config.get("server", {}).get("auto_open_browser", True)

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
