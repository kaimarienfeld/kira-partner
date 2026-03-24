#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kira – rauMKult® Dashboard (v3)
http://localhost:8765
Komplett neu aufgebaut: neues DB-Schema, echtes Dashboard, funktionale Kira,
strukturiertes Geschäft, interaktives Wissen.
"""
import json, sys, webbrowser, threading, urllib.parse, sqlite3, re, mimetypes
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"
KUNDEN_DB     = KNOWLEDGE_DIR / "kunden.db"
ARCHIV_ROOT   = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\Archiv")
ALLOWED_ROOTS = [str(ARCHIV_ROOT), str(KNOWLEDGE_DIR)]
sys.path.insert(0, str(SCRIPTS_DIR))

from response_gen import generate_draft

PORT = 8765

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
    n_rechn   = sum(1 for t in tasks if t.get("kategorie") == "Rechnung / Beleg")
    n_ges     = len(tasks)

    # Organisation-Daten
    try:
        n_org = db.execute("SELECT COUNT(*) FROM organisation").fetchone()[0]
    except: n_org = 0

    # Geschäft-Zusammenfassung
    try:
        row = db.execute("SELECT COUNT(*) c, COALESCE(SUM(betrag),0) s FROM geschaeft WHERE datum >= date('now','-30 days')").fetchone()
        n_gesch_30 = row[0]
        s_gesch_30 = row[1]
    except:
        n_gesch_30 = 0; s_gesch_30 = 0

    # Dringende Tasks (max 5)
    urgent = [t for t in tasks if t.get("kategorie") in ("Antwort erforderlich","Neue Lead-Anfrage","Angebotsrückmeldung")][:5]
    urgent_html = "\n".join(task_card(t) for t in urgent) if urgent else "<p class='empty'>Keine dringenden Aufgaben.</p>"

    # Letzte Geschäftsvorgänge (max 5)
    try:
        gesch_rows = db.execute("SELECT typ,datum,betrag,gegenpartei,gegenpartei_email,betreff FROM geschaeft ORDER BY datum DESC LIMIT 5").fetchall()
        gesch_html = ""
        for r in gesch_rows:
            betrag = f"{r['betrag']:.2f} EUR" if r['betrag'] else ""
            gesch_html += f"""<div class="dash-row">
              <span class="dash-typ">{esc(r['typ'] or '')}</span>
              <span class="dash-datum">{format_datum(r['datum'])}</span>
              <span class="dash-betrag">{betrag}</span>
              <span class="dash-name">{esc((r['gegenpartei'] or r['gegenpartei_email'] or '')[:30])}</span>
            </div>"""
    except:
        gesch_html = ""

    # Organisation (nächste Termine/Fristen)
    try:
        org_rows = db.execute("SELECT typ,datum_erkannt,beschreibung,kunden_email FROM organisation ORDER BY datum_erkannt DESC LIMIT 5").fetchall()
        org_html = ""
        for r in org_rows:
            org_html += f"""<div class="dash-row">
              <span class="dash-typ">{esc(r['typ'] or '')}</span>
              <span class="dash-datum">{esc(r['datum_erkannt'] or '')}</span>
              <span class="dash-name">{esc((r['beschreibung'] or '')[:50])}</span>
            </div>"""
    except:
        org_html = ""

    return f"""
<div class="summary" id="kpi-bar">
  <div class="sum-item {'sum-alarm' if n_antwort>0 else ''} clickable-kpi" onclick="filterKomm('Antwort erforderlich')">
    <div class="sum-num">{n_antwort}</div><div class="sum-label">Antworten nötig</div>
  </div>
  <div class="sum-item clickable-kpi" onclick="filterKomm('Neue Lead-Anfrage')">
    <div class="sum-num">{n_leads}</div><div class="sum-label">Neue Leads</div>
  </div>
  <div class="sum-item clickable-kpi" onclick="filterKomm('Angebotsrückmeldung')">
    <div class="sum-num">{n_angebot}</div><div class="sum-label">Angebotsrückmeldungen</div>
  </div>
  <div class="sum-item clickable-kpi" onclick="showPanel('organisation')">
    <div class="sum-num">{n_org}</div><div class="sum-label">Termine / Fristen</div>
  </div>
  <div class="sum-item clickable-kpi" onclick="showPanel('geschaeft')">
    <div class="sum-num">{n_gesch_30}</div><div class="sum-label">Geschäft (30 Tage)</div>
  </div>
  <div class="sum-item clickable-kpi" onclick="filterKomm('Rechnung / Beleg')">
    <div class="sum-num">{n_rechn}</div><div class="sum-label">Rechnungen</div>
  </div>
  <div class="sum-item"><div class="sum-num">{n_ges}</div><div class="sum-label">Gesamt offen</div></div>
</div>

<div class="dash-grid">
  <div class="dash-block">
    <div class="section-title">Heute wichtig</div>
    {urgent_html}
  </div>
  <div class="dash-side">
    {"<div class='dash-mini-block'><div class='section-title'>Termine / Fristen</div>" + org_html + "</div>" if org_html else ""}
    {"<div class='dash-mini-block'><div class='section-title'>Letzte Geschäftsvorgänge</div>" + gesch_html + "</div>" if gesch_html else ""}
    {f"<div class='dash-mini-block'><div class='section-title'>Geschäft (30 Tage)</div><div class='dash-summary-num'>{s_gesch_30:,.2f} EUR</div><div class='muted' style='font-size:12px'>{n_gesch_30} Vorgänge</div></div>" if n_gesch_30 > 0 else ""}
  </div>
</div>"""

# ── KOMMUNIKATION Panel ──────────────────────────────────────────────────────
def build_kommunikation(tasks):
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

    html = ""
    for key, label, lst in groups:
        html += build_section(label, lst)
    if rest:
        html += build_section("Sonstige", rest, collapsed=True)
    return html or "<p class='empty'>Keine offenen Kommunikationsaufgaben.</p>"

# ── ORGANISATION Panel ────────────────────────────────────────────────────────
def build_organisation(db):
    try:
        rows = db.execute("SELECT * FROM organisation ORDER BY datum_erkannt DESC").fetchall()
    except:
        rows = []

    if not rows:
        return "<p class='empty'>Keine Organisations-Einträge. Termine, Fristen und Rückrufbitten werden hier angezeigt, sobald sie aus Mails erkannt werden.</p>"

    groups = {"termin": [], "frist": [], "rueckruf": [], "sonstige": []}
    for r in rows:
        typ = r["typ"] or "sonstige"
        if typ in groups:
            groups[typ].append(dict(r))
        else:
            groups["sonstige"].append(dict(r))

    labels = {"termin": "Termine", "frist": "Fristen", "rueckruf": "Rückrufbitten", "sonstige": "Sonstiges"}
    html = ""
    for key, label in labels.items():
        items = groups.get(key, [])
        if not items: continue
        rows_html = ""
        for o in items:
            rows_html += f"""<div class="org-row">
              <span class="org-typ-badge">{esc(key)}</span>
              <span class="org-datum">{esc(o.get('datum_erkannt','') or '')}</span>
              <span class="org-betreff">{esc((o.get('beschreibung','') or o.get('betreff','') or '')[:70])}</span>
              <span class="org-email muted">{esc(o.get('kunden_email','') or '')}</span>
              <span class="org-konto muted">{esc(o.get('konto','') or '')}</span>
            </div>"""
        html += f'<div class="section"><div class="section-title">{label} <span class="count-badge">{len(items)}</span></div><div class="section-body">{rows_html}</div></div>'
    return html

# ── GESCHÄFT Panel ────────────────────────────────────────────────────────────
def build_geschaeft(db):
    """Geschäft Dashboard mit 5 Sub-Tabs: Übersicht, Ausgangsrechnungen, Angebote, Eingangsrechnungen, Mahnungen."""
    try: ar = [dict(r) for r in db.execute("SELECT * FROM ausgangsrechnungen ORDER BY datum DESC").fetchall()]
    except: ar = []
    try: ang = [dict(r) for r in db.execute("SELECT * FROM angebote ORDER BY datum DESC").fetchall()]
    except: ang = []
    try: eingang = [dict(r) for r in db.execute("SELECT * FROM geschaeft WHERE wichtigkeit='aktiv' AND (bewertung IS NULL OR bewertung!='erledigt') ORDER BY datum DESC").fetchall()]
    except: eingang = []

    ar_offen = [r for r in ar if r.get("status") == "offen"]
    ar_gemahnt = [r for r in ar if (r.get("mahnung_count") or 0) > 0]
    ang_offen = [r for r in ang if r.get("status") == "offen"]
    s_ar_offen = sum(r.get("betrag_brutto") or 0 for r in ar_offen)
    today = datetime.now().strftime("%Y-%m-%d")
    n_nf = sum(1 for r in ang if r.get("status") == "offen" and (r.get("naechster_nachfass") or "") <= today)

    # Statistik-Daten
    ang_angenommen = [r for r in ang if r.get("status") == "angenommen"]
    ang_abgelehnt = [r for r in ang if r.get("status") == "abgelehnt"]
    ang_bearbeitet = [r for r in ang if r.get("status") == "bearbeitet"]
    ar_bezahlt = [r for r in ar if r.get("status") == "bezahlt"]
    stats = {"ang_total": len(ang), "ang_angenommen": len(ang_angenommen),
             "ang_abgelehnt": len(ang_abgelehnt), "ar_bezahlt": len(ar_bezahlt), "ar_total": len(ar)}

    html = f"""
    <div class="gesch-tabs">
      <div class="gesch-tab active" onclick="showGeschTab('uebersicht')">Übersicht</div>
      <div class="gesch-tab" onclick="showGeschTab('ausgangsre')">Ausgangsrechnungen ({len(ar)})</div>
      <div class="gesch-tab" onclick="showGeschTab('angebote')">Angebote ({len(ang)})</div>
      <div class="gesch-tab" onclick="showGeschTab('eingangsre')">Eingangsrechnungen ({len(eingang)})</div>
      <div class="gesch-tab" onclick="showGeschTab('mahnungen')">Mahnungen ({len(ar_gemahnt)})</div>
    </div>
    <div id="gesch-uebersicht" class="gesch-panel active">{_build_gesch_uebersicht(ar_offen, ar_gemahnt, ang_offen, s_ar_offen, n_nf, eingang, today, stats)}</div>
    <div id="gesch-ausgangsre" class="gesch-panel">{_build_ar_table(ar)}</div>
    <div id="gesch-angebote" class="gesch-panel">{_build_ang_table(ang, today)}</div>
    <div id="gesch-eingangsre" class="gesch-panel">{_gesch_aktiv_cards(eingang)}</div>
    <div id="gesch-mahnungen" class="gesch-panel">{_build_mahnung_section(ar_gemahnt, ar_offen)}</div>"""
    return html


def _build_gesch_uebersicht(ar_offen, ar_gemahnt, ang_offen, s_ar_offen, n_nf, eingang, today, stats=None):
    """Übersicht-Tab mit KPI-Cards, dringenden Punkten und Statistik."""
    html = f"""<div class="gesch-summary-grid">
      <div class="gesch-sum-card{' gesch-sum-alarm' if ar_offen else ''}">
        <div class="gesch-sum-num">{len(ar_offen)}</div>
        <div class="gesch-sum-label">Offene Ausgangsrechnungen</div>
      </div>
      <div class="gesch-sum-card{' gesch-sum-alarm' if s_ar_offen else ''}">
        <div class="gesch-sum-num">{s_ar_offen:,.2f} EUR</div>
        <div class="gesch-sum-label">Offenes Volumen (Ausgang)</div>
      </div>
      <div class="gesch-sum-card">
        <div class="gesch-sum-num">{len(ang_offen)}</div>
        <div class="gesch-sum-label">Offene Angebote</div>
      </div>
      <div class="gesch-sum-card{' gesch-sum-alarm' if n_nf else ''}">
        <div class="gesch-sum-num">{n_nf}</div>
        <div class="gesch-sum-label">Nachfass fällig</div>
      </div>
      <div class="gesch-sum-card{' gesch-sum-alarm' if eingang else ''}">
        <div class="gesch-sum-num">{len(eingang)}</div>
        <div class="gesch-sum-label">Offene Eingangsrechnungen</div>
      </div>
      <div class="gesch-sum-card{' gesch-sum-alarm' if ar_gemahnt else ''}">
        <div class="gesch-sum-num">{len(ar_gemahnt)}</div>
        <div class="gesch-sum-label">Gemahnte Rechnungen</div>
      </div>
    </div>"""
    # Dringende Punkte
    urgent = []
    for r in ar_offen[:3]:
        re_nr = esc(r.get("re_nummer", ""))
        kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:30])
        urgent.append(f'<div class="gesch-urgent-item"><span class="gesch-typ-badge gesch-typ-eingang">Rechnung</span> {re_nr} &middot; {kunde} &middot; {format_datum(r.get("datum"))}</div>')
    for r in ang_offen:
        if (r.get("naechster_nachfass") or "") <= today:
            a_nr = esc(r.get("a_nummer", ""))
            kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:30])
            urgent.append(f'<div class="gesch-urgent-item"><span class="gesch-typ-badge" style="color:var(--kl);background:rgba(139,107,170,.12)">Nachfass</span> {a_nr} &middot; {kunde} &middot; Fällig: {r.get("naechster_nachfass","")}</div>')
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
        hinweis = "" if ang_total >= 10 else f'<span class="muted" style="font-size:11px;margin-left:8px">(Datenbasis: {ang_total} Angebote – ab 10 aussagekräftig)</span>'
        html += f"""<div class="section" style="margin-top:16px">
      <div class="section-title">Statistik</div>
      <div class="section-body">
        <div class="gesch-summary-grid" style="grid-template-columns:repeat(auto-fill,minmax(130px,1fr))">
          <div class="gesch-sum-card"><div class="gesch-sum-num">{quote}</div><div class="gesch-sum-label">Angebotsquote{hinweis}</div></div>
          <div class="gesch-sum-card"><div class="gesch-sum-num">{ang_angen}</div><div class="gesch-sum-label">Angenommen</div></div>
          <div class="gesch-sum-card"><div class="gesch-sum-num">{ang_abgel}</div><div class="gesch-sum-label">Abgelehnt</div></div>
          <div class="gesch-sum-card"><div class="gesch-sum-num">{s.get('ar_bezahlt',0)}/{s.get('ar_total',0)}</div><div class="gesch-sum-label">Rechnungen bezahlt</div></div>
        </div>
      </div>
    </div>"""
    return html


def _build_ar_table(rows):
    """Ausgangsrechnungen-Tab mit Filter und Tabelle."""
    if not rows:
        return "<p class='empty'>Keine Ausgangsrechnungen vorhanden.</p>"
    years = sorted(set(r.get("datum", "")[:4] for r in rows if r.get("datum")), reverse=True)
    y_opts = "".join(f'<option value="{y}">{y}</option>' for y in years)
    html = f"""<div class="gesch-filter-bar">
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
        <span class="gc-status">Status</span><span class="gc-actions">Aktionen</span>
      </div>"""
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


def _build_mahnung_section(gemahnt, ar_offen):
    """Mahnungen-Tab: Gemahnte Rechnungen + überfällige offene."""
    html = ""
    # Überfällige offene ohne Mahnung
    today_dt = datetime.now()
    overdue = []
    for r in ar_offen:
        if (r.get("mahnung_count") or 0) > 0:
            continue
        try:
            d = datetime.strptime((r.get("datum", "") or "")[:10], "%Y-%m-%d")
            days = (today_dt - d).days
            if days > 30:
                overdue.append((r, days))
        except:
            continue
    if overdue:
        html += '<div class="section"><div class="section-title">Überfällige Rechnungen (ohne Mahnung)</div><div class="section-body">'
        for r, days in sorted(overdue, key=lambda x: -x[1]):
            rid = r.get("id", "")
            re_nr = esc(r.get("re_nummer", ""))
            kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:30])
            html += f'<div class="gesch-urgent-item"><span class="badge badge-warn">{days} Tage</span> {re_nr} &middot; {kunde} &middot; {format_datum(r.get("datum"))} <button class="btn btn-xs btn-green" onclick="arSetStatus({rid},\'bezahlt\')" style="margin-left:auto">Bezahlt</button></div>'
        html += '</div></div>'

    if gemahnt:
        html += '<div class="section"><div class="section-title">Mahnungen &amp; Zahlungserinnerungen</div><div class="section-body">'
        for r in gemahnt:
            rid = r.get("id", "")
            re_nr = esc(r.get("re_nummer", ""))
            datum = format_datum(r.get("datum"))
            kunde = esc((r.get("kunde_name") or r.get("kunde_email") or "")[:30])
            mc = r.get("mahnung_count") or 0
            lm = r.get("letzte_mahnung", "") or ""
            status = r.get("status", "offen")
            betrag = f'{r.get("betrag_brutto") or 0:,.2f} EUR' if r.get("betrag_brutto") else ""
            timeline = f'<span class="muted" style="font-size:11px">Rechnung: {datum}'
            if mc >= 1:
                timeline += ' &#8594; 1. Erinnerung'
            if mc >= 2:
                timeline += ' &#8594; 2. Mahnung'
            if mc >= 3:
                timeline += ' &#8594; Letzte Mahnung'
            timeline += f' &middot; Letzte: {format_datum(lm)}</span>'
            s_cls = "tag-zahlung" if status == "bezahlt" else "tag-alarm"
            acts = ""
            if status == "offen":
                acts = f'<button class="btn btn-xs btn-green" onclick="arSetStatus({rid},\'bezahlt\')">Bezahlt</button> <button class="btn btn-xs btn-warn" onclick="arSetStatus({rid},\'streitfall\')">Streitfall</button>'
            html += f"""<div class="gesch-aktiv-card" style="border-color:rgba(232,69,69,.3)">
              <div class="gesch-aktiv-header">
                <span class="gesch-typ-badge gesch-typ-mahnung">Mahnung x{mc}</span>
                <span class="tag {s_cls}">{status}</span>
                <span class="gesch-aktiv-betrag">{betrag}</span>
                <span class="gesch-aktiv-datum">{datum}</span>
              </div>
              <div class="gesch-aktiv-body">
                <div class="gesch-aktiv-betreff">{re_nr} &middot; {kunde}</div>
                <div>{timeline}</div>
              </div>
              <div class="gesch-aktiv-actions">{acts}</div>
            </div>"""
        html += '</div></div>'

    if not gemahnt and not overdue:
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


    html = f"""
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

    # Kategorien mit Labels
    KAT_LABELS = [
        ("fest",      "Feste Regeln"),
        ("stil",      "Stil & Tonalität"),
        ("preis",     "Preise & Kalkulation"),
        ("technik",   "Technik & Fachwissen"),
        ("prozess",   "Prozess & Abläufe"),
        ("gelernt",   "Gelernt"),
        ("vorschlag", "Vorschläge"),
    ]

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

    # Tabs bauen
    tabs_html = ""
    panels_html = ""
    first = True
    for kat_key, kat_label in KAT_LABELS:
        items = grouped.get(kat_key, [])
        if not items and kat_key not in ("gelernt", "vorschlag"): continue
        active = " active" if first else ""
        tabs_html += f'<div class="wissen-tab{active}" onclick="showWissenTab(\'{kat_key}\')">{kat_label} ({len(items)})</div>'

        cards = ""
        for r in items:
            rid = r['id']
            status = r.get('status','aktiv')
            # Feste/Stil/Preis/Technik/Prozess: anzeigen + bearbeiten + löschen
            if kat_key in ("fest","stil","preis","technik","prozess"):
                cards += f"""<div class="wissen-card" id="wr-{rid}">
                  <div class="wissen-titel">{esc(r['titel'])}</div>
                  <div class="wissen-inhalt" id="wi-{rid}">{esc(r['inhalt'])}</div>
                  <div class="wissen-meta"><span class="muted">{esc(kat_key)}</span>
                    <button class="btn btn-korr" style="margin-left:8px;font-size:11px;padding:2px 8px;" onclick="editRegel({rid},'{js_esc(r['titel'])}','{js_esc(r['inhalt'])}','{js_esc(kat_key)}')">Bearbeiten</button>
                    <button class="btn btn-ignore" style="margin-left:4px;font-size:11px;padding:2px 8px;" onclick="wissenAction({rid},'loeschen')">Entfernen</button>
                  </div>
                </div>"""
            else:
                # Gelernt / Vorschlag: mit Bestätigen/Ablehnen + Bearbeiten
                cards += f"""<div class="wissen-card {'wissen-vorschlag' if kat_key=='vorschlag' else ''}" id="wr-{rid}">
                  <div class="wissen-titel">{esc(r['titel'])}</div>
                  <div class="wissen-inhalt" id="wi-{rid}">{esc(r['inhalt'])}</div>
                  <div class="wissen-actions">
                    <button class="btn btn-done" onclick="wissenAction({rid},'bestaetigen')">{'Freigeben' if kat_key=='vorschlag' else 'Bestätigen'}</button>
                    <button class="btn btn-korr" style="font-size:11px;padding:2px 8px;" onclick="editRegel({rid},'{js_esc(r['titel'])}','{js_esc(r['inhalt'])}','{js_esc(kat_key)}')">Bearbeiten</button>
                    <button class="btn btn-ignore" onclick="wissenAction({rid},'ablehnen')">Ablehnen</button>
                  </div>
                </div>"""

        panels_html += f'<div id="wissen-{kat_key}" class="wissen-panel{active}">{cards or "<p class=\\'empty\\'>Keine Einträge.</p>"}</div>'
        first = False

    # Korrekturen-Tab
    tabs_html += f'<div class="wissen-tab" onclick="showWissenTab(\'korrekturen\')">Korrekturen ({len(korr_list)})</div>'
    korr_html = ""
    for c in korr_list:
        korr_html += f"""<div class="wissen-card wissen-korr">
          <div class="wissen-titel">Korrektur: {esc(c.get('alter_typ',''))} &rarr; {esc(c.get('neuer_typ',''))}</div>
          <div class="wissen-inhalt">{esc(c.get('notiz',''))}</div>
          <div class="wissen-status muted">{esc((c.get('erstellt_am','') or '')[:10])}</div>
        </div>"""
    panels_html += f'<div id="wissen-korrekturen" class="wissen-panel">{korr_html or "<p class=\\'empty\\'>Noch keine Korrekturen.</p>"}</div>'

    # Neue-Regel-Tab
    tabs_html += '<div class="wissen-tab" onclick="showWissenTab(\'neu\')">+ Neue Regel</div>'
    panels_html += """<div id="wissen-neu" class="wissen-panel">
      <div class="wissen-card" style="max-width:560px">
        <div class="wissen-titel" style="margin-bottom:10px">Neue Regel hinzufügen</div>
        <label style="font-size:12px;color:var(--muted);display:block;margin-bottom:3px;">Kategorie:</label>
        <select id="nr-kat" style="width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px;margin-bottom:9px;">
          <option value="fest">Feste Regel</option>
          <option value="stil">Stil &amp; Tonalität</option>
          <option value="preis">Preise &amp; Kalkulation</option>
          <option value="technik">Technik &amp; Fachwissen</option>
          <option value="prozess">Prozess &amp; Abläufe</option>
          <option value="gelernt">Gelernt</option>
          <option value="vorschlag">Vorschlag</option>
        </select>
        <label style="font-size:12px;color:var(--muted);display:block;margin-bottom:3px;">Titel:</label>
        <input type="text" id="nr-titel" placeholder="Kurzer Regeltitel" style="width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px;margin-bottom:9px;">
        <label style="font-size:12px;color:var(--muted);display:block;margin-bottom:3px;">Inhalt / Beschreibung:</label>
        <textarea id="nr-inhalt" rows="4" placeholder="Die vollständige Regel oder Anweisung..." style="width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:7px;padding:8px;font-size:13px;font-family:inherit;resize:vertical;margin-bottom:9px;"></textarea>
        <button class="btn btn-done" onclick="neueRegel()">Regel speichern</button>
      </div>
    </div>"""

    total = len(regeln)
    return f"""
    <div style="margin-bottom:10px;font-size:12px;color:var(--muted)">{total} Regeln gesamt</div>
    <div class="wissen-tabs">{tabs_html}</div>
    {panels_html}"""

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
<html lang="de">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kira – rauMKult® Assistenz</title>
<style>
{CSS}
</style>
</head>
<body>

<div class="header">
  <div class="header-logo">rauMKult<span>&reg;</span><span style="font-size:11px;font-weight:400;color:var(--muted);margin-left:8px">Kira Assistenz</span></div>
  <div class="header-meta"><strong>{n_ges} offene Aufgaben</strong>{heute}</div>
</div>

<nav class="nav">
  <div class="nav-item active" id="nav-dashboard"     onclick="showPanel('dashboard')">Dashboard {alarm_dot}</div>
  <div class="nav-item"        id="nav-kommunikation" onclick="showPanel('kommunikation')">Kommunikation</div>
  <div class="nav-item"        id="nav-organisation"  onclick="showPanel('organisation')">Organisation</div>
  <div class="nav-item"        id="nav-geschaeft"     onclick="showPanel('geschaeft')">Geschäft</div>
  <div class="nav-item"        id="nav-wissen"        onclick="showPanel('wissen')">Wissen</div>
  <div class="nav-item"        id="nav-einstellungen" onclick="showPanel('einstellungen')">Einstellungen</div>
</nav>

<div class="panel active" id="panel-dashboard">{dashboard_html}</div>
<div class="panel" id="panel-kommunikation">{komm_html}</div>
<div class="panel" id="panel-organisation">{org_html}</div>
<div class="panel" id="panel-geschaeft">{gesch_html}</div>
<div class="panel" id="panel-wissen">{wissen_html}</div>
<div class="panel" id="panel-einstellungen">{einstell_html}</div>

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

<!-- Kira FAB -->
<button class="kira-fab" onclick="toggleKira()" title="Kira öffnen">K</button>

<!-- Kira Panel -->
<div class="kira-panel" id="kiraPanel">
  <div class="kira-ph">
    <div><div class="kira-ph-title">Kira</div><div class="kira-ph-sub">rauMKult® Assistenz</div></div>
    <button class="kira-close" onclick="closeKira()">&#x2715;</button>
  </div>
  <div class="kira-tabs">
    <div class="kira-tab active" id="ktab-home"    onclick="showKTab('home')">Home</div>
    <div class="kira-tab" id="ktab-chat"           onclick="showKTab('chat')">Chat</div>
    <div class="kira-tab" id="ktab-aufgaben"       onclick="showKTab('aufgaben')">Aufgaben</div>
    <div class="kira-tab" id="ktab-kwissen"        onclick="showKTab('kwissen')">Wissen</div>
  </div>
  <div class="kira-content">
    <div id="kc-home">
      <div class="kira-sec"><div class="kira-sec-title">Status</div>
        <div class="kira-card"><div class="kira-card-meta" style="color:{'#e84545' if n_antwort>0 else 'var(--muted)'}">
          {'Achtung: ' + str(n_antwort) + ' Antworten ausstehend' if n_antwort>0 else 'Keine dringenden Antworten'}
        </div></div>
      </div>
      <div class="kira-sec"><div class="kira-sec-title">Hinweis</div>
        <div class="kira-card"><div class="kira-card-meta">Klicke auf einer Aufgabenkarte auf <strong style="color:var(--kl)">Mit Kira besprechen</strong>, um das Kommunikationsfenster zu öffnen.</div></div>
      </div>
    </div>
    <div id="kc-chat" style="display:none">
      <div id="komm-container"><div style="color:var(--muted);font-size:13px;padding:6px 0;">Wähle eine Aufgabe und klicke &bdquo;Mit Kira besprechen&ldquo;.</div></div>
    </div>
    <div id="kc-aufgaben" style="display:none">
      <div id="kira-tasks-list"><div style="color:var(--muted);font-size:13px;">Lade&hellip;</div></div>
    </div>
    <div id="kc-kwissen" style="display:none">
      <div class="kira-sec"><div class="kira-sec-title">Feste Regeln</div>
        <div class="kira-card"><div class="kira-card-meta">Keine Preise in der Erstantwort. Anrede nach Kundensprache (Du/Sie). Kein KI-Sound.</div></div>
        <div class="kira-card"><div class="kira-card-meta">Erst Einordnung + Infos einsammeln. Entwurf erst nach Kai-Input.</div></div>
        <div class="kira-card"><div class="kira-card-meta">Fotos immer anfordern. Max 3-7 Rückfragen.</div></div>
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
<footer>Kira – rauMKult® Assistenz &middot; <a href="javascript:location.reload()">Aktualisieren</a></footer>

<script>
const KIRA_CTX = {json.dumps(kira_ctx, ensure_ascii=False)};
const PROMPTS  = {json.dumps(prompts_json, ensure_ascii=False)};
let kiraOpen = false;

// Nav panels
function showPanel(name) {{
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.getElementById('nav-'+name).classList.add('active');
  document.getElementById('panel-'+name).classList.add('active');
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
  event.target.classList.add('active');
  document.getElementById('gesch-'+name)?.classList.add('active');
}}

// Geschäft: Erledigt
function geschErledigt(id) {{
  fetch('/api/geschaeft/'+id+'/erledigt',{{method:'POST'}}).then(r=>r.json()).then(d=>{{
    if(d.ok){{
      const el=document.getElementById('gesch-'+id);
      if(el){{el.style.opacity='0.2';setTimeout(()=>el.remove(),300);}}
      showToast('Als erledigt markiert');
    }}
  }}).catch(()=>showToast('Fehler'));
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

// Ausgangsrechnung Status ändern
function arSetStatus(id, status) {{
  const labels = {{bezahlt:'Als bezahlt markieren?',streitfall:'Als Streitfall markieren?'}};
  if (!confirm(labels[status] || 'Status ändern?')) return;
  fetch('/api/ausgangsrechnung/'+id+'/status', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{status}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok) {{ showToast('Status aktualisiert'); setTimeout(()=>location.reload(), 600); }}
    else showToast(d.error||'Fehler');
  }}).catch(()=>showToast('Fehler'));
}}

// Angebot Status ändern
function angSetStatus(id, status) {{
  const labels = {{angenommen:'Als angenommen markieren?',abgelehnt:'Als abgelehnt markieren?',keine_antwort:'Als keine Antwort markieren?'}};
  if (!confirm(labels[status] || 'Status ändern?')) return;
  let grund = '';
  if (status === 'abgelehnt') {{
    grund = prompt('Warum wurde das Angebot abgelehnt?\\n(zu teuer / anderer Anbieter / Projekt abgesagt / Sonstiges)', '') || '';
  }} else if (status === 'angenommen') {{
    grund = prompt('Hinweise zum Zustandekommen?\\n(z.B. nach Nachfass, sofort, Verhandlung)', '') || '';
  }}
  fetch('/api/angebot/'+id+'/status', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{status, grund}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.ok) {{ showToast('Status aktualisiert'); setTimeout(()=>location.reload(), 600); }}
    else showToast(d.error||'Fehler');
  }}).catch(()=>showToast('Fehler'));
}}

// Einstellungen speichern
function saveSettings() {{
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

// Kira panel
function toggleKira(){{ kiraOpen ? closeKira() : openKiraNaked(); }}
function openKiraNaked(){{ kiraOpen=true; document.getElementById('kiraPanel').classList.add('open'); }}
function closeKira(){{ kiraOpen=false; document.getElementById('kiraPanel').classList.remove('open'); }}

// Kira tabs
function showKTab(name){{
  document.querySelectorAll('.kira-tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('[id^=kc-]').forEach(c=>c.style.display='none');
  document.getElementById('ktab-'+name)?.classList.add('active');
  document.getElementById('kc-'+name).style.display='block';
  if(name==='aufgaben') loadKiraTasks();
}}

// Mit Kira besprechen – Kommunikationsfenster
function openKira(taskId){{
  const ctx = KIRA_CTX[taskId];
  if(!ctx){{ showToast('Kein Kontext'); return; }}
  openKiraNaked();
  showKTab('chat');

  const fehlend = ctx.kategorie==='Neue Lead-Anfrage'
    ? '<li>Ort / PLZ des Projekts</li><li>Maße der Fläche</li><li>Fotos der Fläche</li><li>Gewünschte Zieloptik</li>'
    : '<li>Details aus dem Mailinhalt prüfen</li>';

  const risiko = ctx.kategorie==='Antwort erforderlich'
    ? 'Antwort ist überfällig – Reaktionszeit beachten.'
    : ctx.kategorie==='Neue Lead-Anfrage'
    ? 'Keine Preise in der Erstantwort. Erst Infos sammeln, dann qualifizieren.'
    : '';

  document.getElementById('komm-container').innerHTML = `
    <div style="padding-top:4px">
      <div class="komm-block">
        <div class="komm-lbl">Zusammenfassung</div>
        <div class="komm-txt">
          <strong>${{escH(ctx.titel)}}</strong><br>
          <span style="color:var(--muted);font-size:11px">Von: ${{escH(ctx.name||ctx.email)}} &middot; ${{escH(ctx.konto)}} &middot; ${{escH(ctx.datum)}}</span><br>
          <span style="color:rgba(255,255,255,.75)">${{escH(ctx.zusammenfassung)}}</span>
        </div>
      </div>
      <div class="komm-block">
        <div class="komm-lbl">Einordnung</div>
        <div class="komm-txt">
          <strong>Kategorie:</strong> ${{escH(ctx.kategorie)}}<br>
          <strong>Absenderrolle:</strong> ${{escH(ctx.absender_rolle)}}<br>
          <strong>Empfehlung:</strong> ${{escH(ctx.empfohlene_aktion)}}<br>
          <strong>Grund:</strong> ${{escH(ctx.kategorie_grund)}}
        </div>
      </div>
      ${{risiko?'<div class="komm-block"><div class="komm-lbl">Hinweis</div><div class="komm-txt">'+escH(risiko)+'</div></div>':''}}
      <div class="komm-block">
        <div class="komm-lbl">Fehlende Infos</div>
        <div class="komm-txt"><ul>${{fehlend}}</ul></div>
      </div>
      <div class="komm-block">
        <div class="komm-lbl">Deine Gedanken / Richtung</div>
        <textarea class="komm-input" id="kai-in-${{taskId}}"
          placeholder="z.B. kurze Rückfrage stellen, Termin vorschlagen, Absage..."></textarea>
        <div class="komm-actions">
          <button class="btn-kp" onclick="generateDraft(${{taskId}})">Entwurf erstellen</button>
          <a href="mailto:${{escH(ctx.email)}}?subject=${{encodeURIComponent('Re: '+(ctx.betreff||''))}}"
             class="btn-ks" target="_blank">Outlook</a>
        </div>
      </div>
      <div id="draft-${{taskId}}"></div>
    </div>`;
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
    if(document.getElementById('mailReadModal').classList.contains('open')) closeMailRead();
    else if(document.getElementById('geschBewertModal').classList.contains('open')) closeGeschBewertung();
    else if(document.getElementById('editRegelModal').classList.contains('open')) closeEditRegel();
    else if(document.getElementById('korrModal').classList.contains('open')) closeKorrModal();
    else if(kiraOpen) closeKira();
  }}
}});
setTimeout(()=>location.reload(),300000);
</script>
</body>
</html>"""


# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
:root{--gold:#bda27c;--gl:#d4b896;--bg:#0b0b0b;--card:#111;--border:rgba(255,255,255,.09);
      --text:#e8e8e8;--muted:rgba(255,255,255,.48);--kp:#8b6baa;--kl:#b08fd0;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:-apple-system,Arial,sans-serif;font-size:14px;line-height:1.5;overflow-x:hidden;}
a{color:var(--gold);text-decoration:none;}

/* Header & Nav */
.header{background:linear-gradient(180deg,rgba(189,162,124,.13),transparent);border-bottom:1px solid var(--border);
         padding:13px 22px;display:flex;align-items:center;justify-content:space-between;
         position:sticky;top:0;z-index:100;backdrop-filter:blur(8px);}
.header-logo{font-size:17px;font-weight:900;color:var(--gold);}
.header-logo span{color:var(--text);font-weight:300;}
.header-meta{color:var(--muted);font-size:12px;text-align:right;}
.header-meta strong{color:var(--text);display:block;font-size:14px;}
.nav{display:flex;gap:2px;padding:9px 22px;border-bottom:1px solid var(--border);background:#0d0d0d;}
.nav-item{padding:6px 14px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600;
           color:var(--muted);border:1px solid transparent;transition:all .15s;user-select:none;}
.nav-item:hover{color:var(--text);background:rgba(255,255,255,.05);}
.nav-item.active{color:var(--gold);background:rgba(189,162,124,.11);border-color:rgba(189,162,124,.28);}
.alarm-dot{display:inline-block;background:#e84545;border-radius:50%;width:7px;height:7px;margin-left:5px;vertical-align:middle;}

/* Panels */
.panel{display:none;padding:18px 22px 80px;max-width:1100px;margin:0 auto;}
.panel.active{display:block;}

/* Summary / KPI Bar */
.summary{display:flex;gap:8px;margin-bottom:18px;flex-wrap:wrap;}
.sum-item{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:11px 15px;flex:1;min-width:90px;}
.sum-num{font-size:22px;font-weight:900;color:var(--gold);}
.sum-label{font-size:11px;color:var(--muted);margin-top:1px;}
.sum-alarm{border-color:rgba(232,69,69,.35);background:rgba(232,69,69,.05);}
.sum-alarm .sum-num{color:#e84545;}
.clickable-kpi{cursor:pointer;transition:border-color .2s,transform .1s;}
.clickable-kpi:hover{border-color:rgba(189,162,124,.4);transform:translateY(-1px);}

/* Dashboard Grid */
.dash-grid{display:grid;grid-template-columns:1fr 340px;gap:18px;}
@media(max-width:860px){.dash-grid{grid-template-columns:1fr;}}
.dash-side{display:flex;flex-direction:column;gap:14px;}
.dash-mini-block{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:13px;}
.dash-row{display:flex;gap:8px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,.04);align-items:center;flex-wrap:wrap;font-size:12px;}
.dash-typ{color:var(--gold);font-weight:700;min-width:80px;}
.dash-datum{color:var(--muted);min-width:70px;}
.dash-betrag{color:var(--text);font-weight:600;min-width:80px;text-align:right;}
.dash-name{color:rgba(255,255,255,.6);flex:1;}
.dash-summary-num{font-size:26px;font-weight:900;color:var(--gold);margin:8px 0 2px;}

/* Sections */
.section{margin-bottom:18px;}
.section-title{font-size:11px;font-weight:800;color:var(--gold);letter-spacing:.8px;
                text-transform:uppercase;padding-bottom:7px;border-bottom:1px solid var(--border);margin-bottom:10px;cursor:pointer;user-select:none;}
.section-title:after{content:' ▾';font-size:10px;}
.section.collapsed .section-body{display:none;}
.section.collapsed .section-title:after{content:' ▸';}
.count-badge{background:rgba(189,162,124,.18);color:var(--gold);font-size:11px;padding:1px 7px;border-radius:10px;font-weight:700;letter-spacing:0;text-transform:none;}

/* Task Card */
.task-card{background:var(--card);border:1px solid var(--border);border-radius:11px;padding:12px 14px;margin-bottom:8px;transition:border-color .2s;}
.task-card:hover{border-color:rgba(189,162,124,.22);}
.prio-hoch  {border-left:3px solid #e84545;}
.prio-mittel{border-left:3px solid var(--gold);}
.prio-niedrig{border-left:3px solid #555;}
.task-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;flex-wrap:wrap;gap:4px;}
.task-tags{display:flex;gap:5px;flex-wrap:wrap;align-items:center;}
.task-datum{color:var(--muted);font-size:12px;}
.task-title{font-size:14px;font-weight:700;color:#fff;margin-bottom:5px;}
.task-summary{font-size:12px;color:rgba(255,255,255,.72);margin-bottom:5px;}
.task-meta-row{font-size:12px;color:var(--muted);margin-bottom:4px;display:flex;flex-wrap:wrap;gap:5px;align-items:center;}
.meta-label{color:rgba(255,255,255,.38);}
.meta-val{color:rgba(255,255,255,.68);}
.meta-sep{color:rgba(255,255,255,.2);}
.muted-email{color:rgba(255,255,255,.4);font-size:11px;}
.task-naechste{font-size:12px;color:var(--gold);margin-bottom:4px;font-weight:600;}
.task-grund{font-size:11px;color:var(--muted);margin-bottom:5px;font-style:italic;}
.task-notiz{font-size:12px;color:var(--muted);margin-bottom:7px;font-style:italic;}
.task-actions{display:flex;gap:5px;flex-wrap:wrap;}

/* Tags */
.tag{font-size:11px;font-weight:800;padding:2px 8px;border-radius:20px;}
.tag-alarm  {background:rgba(232,69,69,.2);color:#e84545;border:1px solid rgba(232,69,69,.38);}
.tag-anfrage{background:rgba(189,162,124,.2);color:var(--gold);border:1px solid rgba(189,162,124,.35);}
.tag-antwort{background:rgba(100,160,255,.14);color:#7baff5;border:1px solid rgba(100,160,255,.28);}
.tag-zahlung{background:rgba(80,200,120,.14);color:#6dc98a;border:1px solid rgba(80,200,120,.28);}
.tag-rechnung{background:rgba(200,180,80,.14);color:#c8b450;border:1px solid rgba(200,180,80,.28);}
.tag-shop   {background:rgba(200,130,80,.14);color:#e09060;border:1px solid rgba(200,130,80,.28);}
.tag-muted  {background:rgba(255,255,255,.06);color:var(--muted);border:1px solid var(--border);}
.konto-badge{font-size:11px;color:var(--muted);background:rgba(255,255,255,.05);border:1px solid var(--border);border-radius:5px;padding:2px 6px;}
.badge{font-size:11px;padding:2px 7px;border-radius:10px;font-weight:700;}
.badge-warn {background:rgba(200,150,50,.2);color:#c89650;border:1px solid rgba(200,150,50,.3);}
.badge-warn2{background:rgba(230,100,50,.2);color:#e06040;border:1px solid rgba(230,100,50,.3);}
.badge-alarm{background:rgba(232,69,69,.2);color:#e84545;border:1px solid rgba(232,69,69,.3);}
.muted{color:var(--muted);}

/* Buttons */
.btn{padding:6px 12px;border-radius:7px;font-size:12px;font-weight:700;cursor:pointer;border:none;
      display:inline-block;transition:all .15s;text-decoration:none;line-height:1.4;}
.btn-primary{background:var(--gold);color:#000;}
.btn-primary:hover{background:var(--gl);}
.btn-kira{background:rgba(139,107,170,.22);color:var(--kl);border:1px solid rgba(139,107,170,.42);}
.btn-kira:hover{background:rgba(139,107,170,.36);}
.btn-sec{background:rgba(255,255,255,.07);color:var(--text);border:1px solid var(--border);}
.btn-sec:hover{background:rgba(255,255,255,.12);}
.btn-done{background:rgba(80,200,120,.13);color:#6dc98a;border:1px solid rgba(80,200,120,.27);}
.btn-done:hover{background:rgba(80,200,120,.25);}
.btn-later{background:rgba(200,150,50,.11);color:#c89650;border:1px solid rgba(200,150,50,.22);}
.btn-later:hover{background:rgba(200,150,50,.22);}
.btn-ignore{background:rgba(120,120,120,.11);color:#888;border:1px solid rgba(120,120,120,.22);}
.btn-ignore:hover{background:rgba(120,120,120,.22);}
.btn-korr{background:rgba(255,255,255,.04);color:rgba(255,255,255,.4);border:1px solid rgba(255,255,255,.09);}
.btn-korr:hover{background:rgba(255,255,255,.09);color:var(--text);}

/* Organisation */
.org-row{display:flex;gap:10px;padding:7px 8px;border-radius:7px;margin-bottom:3px;align-items:center;flex-wrap:wrap;background:rgba(189,162,124,.04);}
.org-typ-badge{font-size:11px;font-weight:700;color:var(--gold);background:rgba(189,162,124,.12);padding:2px 8px;border-radius:4px;min-width:60px;text-align:center;}
.org-datum{color:var(--muted);font-size:12px;min-width:90px;}
.org-betreff{flex:1;font-size:13px;}
.org-email{font-size:12px;min-width:130px;text-align:right;}
.org-konto{font-size:11px;}

/* Geschäft */
.gesch-tabs,.wissen-tabs{display:flex;gap:2px;margin-bottom:14px;flex-wrap:wrap;}
.gesch-tab,.wissen-tab{padding:6px 14px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:700;
  color:var(--muted);border:1px solid transparent;transition:all .15s;user-select:none;}
.gesch-tab:hover,.wissen-tab:hover{color:var(--text);background:rgba(255,255,255,.05);}
.gesch-tab.active,.wissen-tab.active{color:var(--gold);background:rgba(189,162,124,.11);border-color:rgba(189,162,124,.28);}
.gesch-panel,.wissen-panel{display:none;}
.gesch-panel.active,.wissen-panel.active{display:block;}
.gesch-summary-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;}
.gesch-sum-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px;text-align:center;}
.gesch-sum-num{font-size:20px;font-weight:900;color:var(--gold);}
.gesch-sum-label{font-size:11px;color:var(--muted);margin-top:2px;}
.gesch-table{font-size:12px;}
.gesch-row{display:flex;gap:6px;padding:6px 4px;border-bottom:1px solid rgba(255,255,255,.04);align-items:center;}
.gesch-header{font-weight:700;color:var(--gold);border-bottom:1px solid var(--border);}
.gc-typ{min-width:100px;}
.gc-datum{min-width:80px;color:var(--muted);}
.gc-betrag{min-width:80px;text-align:right;font-weight:600;}
.gc-nr{min-width:90px;color:var(--muted);}
.gc-partner{min-width:120px;flex:1;}
.gc-betreff{flex:2;color:rgba(255,255,255,.6);}
.gesch-typ-badge{font-size:10px;font-weight:700;color:var(--gold);background:rgba(189,162,124,.1);padding:1px 6px;border-radius:3px;}
.gesch-sum-alarm{border-color:rgba(232,69,69,.35);background:rgba(232,69,69,.05);}
.gesch-sum-alarm .gesch-sum-num{color:#e84545;}
.gesch-aktiv-card{background:var(--card);border:1px solid rgba(232,69,69,.2);border-radius:10px;padding:13px;margin-bottom:10px;}
.gesch-aktiv-header{display:flex;gap:10px;align-items:center;margin-bottom:6px;flex-wrap:wrap;}
.gesch-aktiv-betrag{font-size:16px;font-weight:900;color:var(--text);}
.gesch-aktiv-datum{font-size:12px;color:var(--muted);margin-left:auto;}
.gesch-aktiv-body{margin-bottom:8px;}
.gesch-aktiv-betreff{font-size:13px;font-weight:600;color:var(--text);}
.gesch-aktiv-partner{font-size:12px;color:var(--muted);}
.gesch-aktiv-actions{display:flex;gap:6px;flex-wrap:wrap;}
.gesch-typ-eingang{color:var(--gold);background:rgba(189,162,124,.15);}
.gesch-typ-mahnung{color:#e84545;background:rgba(232,69,69,.12);}
.gesch-routine-row{opacity:.7;}
.gesch-routine-row:hover{opacity:1;}
.gesch-row-aktiv{border-left:2px solid #e84545;}
.gesch-row-routine{opacity:.55;}
.gc-actions{display:flex;gap:4px;min-width:100px;justify-content:flex-end;}
.btn{border:none;cursor:pointer;border-radius:6px;font-weight:700;font-family:inherit;transition:all .15s;}
.btn-sm{padding:5px 12px;font-size:12px;}
.btn-tiny{padding:3px 8px;font-size:11px;}
.btn-xs{padding:2px 6px;font-size:10px;}
.btn-green{background:rgba(80,180,80,.15);color:#5cb85c;border:1px solid rgba(80,180,80,.3);}
.btn-green:hover{background:rgba(80,180,80,.25);}
.btn-gold{background:rgba(189,162,124,.15);color:var(--gold);border:1px solid rgba(189,162,124,.3);}
.btn-gold:hover{background:rgba(189,162,124,.25);}
.btn-muted{background:rgba(255,255,255,.05);color:var(--muted);border:1px solid var(--border);}
.btn-muted:hover{background:rgba(255,255,255,.1);color:var(--text);}
.btn-warn{background:rgba(232,69,69,.08);color:#e88;border:1px solid rgba(232,69,69,.2);}
.btn-warn:hover{background:rgba(232,69,69,.18);}
.badge-korrekt{font-size:10px;font-weight:700;color:#5cb85c;background:rgba(80,180,80,.12);padding:1px 6px;border-radius:3px;}
.att-link{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;margin:2px 3px;border-radius:5px;font-size:12px;
  background:rgba(189,162,124,.08);border:1px solid rgba(189,162,124,.2);color:var(--gold);text-decoration:none;transition:all .15s;}
.att-link:hover{background:rgba(189,162,124,.18);border-color:rgba(189,162,124,.4);}
.att-icon{font-size:10px;font-weight:800;color:var(--muted);}

/* Geschäft Filter & Tabellen */
.gesch-filter-bar{display:flex;gap:10px;margin-bottom:14px;align-items:center;flex-wrap:wrap;}
.gesch-filter-bar select{background:#0b0b0b;color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:12px;font-family:inherit;cursor:pointer;}
.gesch-filter-bar select:focus{outline:none;border-color:rgba(189,162,124,.4);}
.gesch-filter-count{font-size:12px;color:var(--muted);margin-left:auto;}
.gc-status{min-width:80px;}
.gc-nf{min-width:110px;}
.gesch-urgent-item{display:flex;gap:8px;align-items:center;padding:7px 8px;border-radius:7px;margin-bottom:3px;background:rgba(232,69,69,.04);font-size:13px;flex-wrap:wrap;}
.gesch-nf-indicator{font-size:11px;font-weight:700;padding:2px 6px;border-radius:4px;background:rgba(255,255,255,.05);}
.nf-overdue{color:#e84545;background:rgba(232,69,69,.12);animation:pulse 2s infinite;}
.nf-planned{color:var(--gold);}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}

/* Einstellungen */
.settings-row{display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.04);}
.settings-row label{font-size:13px;color:var(--text);min-width:200px;}
.settings-row input[type=text],.settings-row input[type=number]{background:#0b0b0b;color:var(--text);border:1px solid var(--border);
  border-radius:6px;padding:6px 10px;font-size:13px;width:220px;font-family:inherit;}
.settings-row input[type=checkbox]{width:18px;height:18px;accent-color:var(--gold);}

/* Wissen */
.wissen-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:8px;}
.wissen-vorschlag{border-color:rgba(139,107,170,.25);}
.wissen-korr{border-color:rgba(200,150,50,.2);}
.wissen-titel{font-size:13px;font-weight:700;color:var(--gold);margin-bottom:4px;}
.wissen-inhalt{font-size:12px;color:rgba(255,255,255,.72);margin-bottom:6px;line-height:1.6;}
.wissen-status{font-size:11px;color:var(--muted);}
.wissen-actions{display:flex;gap:6px;}

/* Toast */
.status-toast{position:fixed;bottom:82px;right:24px;background:#1a1a1a;border:1px solid rgba(189,162,124,.4);
               border-radius:10px;padding:10px 18px;color:var(--gold);font-weight:700;font-size:13px;
               transform:translateY(50px);opacity:0;transition:all .28s;z-index:500;pointer-events:none;}
.status-toast.show{transform:translateY(0);opacity:1;}

/* Kira FAB */
.kira-fab{position:fixed;bottom:22px;right:22px;z-index:200;
           background:linear-gradient(135deg,#5d3f7a,#8b6baa);border-radius:50%;
           width:52px;height:52px;display:flex;align-items:center;justify-content:center;
           cursor:pointer;box-shadow:0 4px 18px rgba(139,107,170,.5);font-size:18px;
           transition:transform .2s,box-shadow .2s;border:none;color:#fff;font-weight:900;}
.kira-fab:hover{transform:scale(1.09);box-shadow:0 6px 26px rgba(139,107,170,.68);}

/* Kira Panel */
.kira-panel{position:fixed;top:0;right:0;height:100vh;width:390px;max-width:96vw;
             background:#0d0b12;border-left:1px solid rgba(139,107,170,.28);z-index:300;
             transform:translateX(106%);transition:transform .28s cubic-bezier(.4,0,.2,1);
             display:flex;flex-direction:column;box-shadow:-6px 0 36px rgba(0,0,0,.6);}
.kira-panel.open{transform:translateX(0);}
.kira-ph{padding:14px 16px 11px;border-bottom:1px solid rgba(139,107,170,.18);
          display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.kira-ph-title{font-size:15px;font-weight:900;color:var(--kl);}
.kira-ph-sub{font-size:11px;color:var(--muted);margin-top:1px;}
.kira-close{background:none;border:none;color:var(--muted);font-size:20px;cursor:pointer;padding:2px 6px;border-radius:4px;}
.kira-close:hover{color:var(--text);background:rgba(255,255,255,.08);}
.kira-tabs{display:flex;gap:1px;padding:7px 10px;border-bottom:1px solid rgba(139,107,170,.13);flex-shrink:0;}
.kira-tab{flex:1;text-align:center;padding:5px 3px;font-size:11px;font-weight:700;
           color:var(--muted);cursor:pointer;border-radius:6px;transition:all .15s;}
.kira-tab:hover{color:var(--text);background:rgba(255,255,255,.05);}
.kira-tab.active{color:var(--kl);background:rgba(139,107,170,.15);}
.kira-content{flex:1;overflow-y:auto;padding:13px 14px;}
.kira-sec{margin-bottom:14px;}
.kira-sec-title{font-size:10px;font-weight:800;color:rgba(176,143,208,.85);letter-spacing:.7px;text-transform:uppercase;margin-bottom:7px;}
.kira-card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);border-radius:8px;padding:9px 11px;margin-bottom:7px;cursor:default;}
.kira-card.clickable{cursor:pointer;}
.kira-card.clickable:hover{border-color:rgba(139,107,170,.35);background:rgba(139,107,170,.08);}
.kira-card-title{font-size:13px;font-weight:700;margin-bottom:3px;}
.kira-card-meta{font-size:12px;color:var(--muted);}

/* Kommunikationsfenster */
.komm-block{background:rgba(0,0,0,.22);border:1px solid rgba(139,107,170,.18);border-radius:8px;padding:11px;margin-bottom:9px;}
.komm-lbl{font-size:10px;font-weight:800;color:rgba(176,143,208,.8);letter-spacing:.6px;text-transform:uppercase;margin-bottom:5px;}
.komm-txt{font-size:12px;color:rgba(255,255,255,.78);line-height:1.6;}
.komm-txt ul{padding-left:16px;}
.komm-input{width:100%;background:#0b0a10;color:var(--text);border:1px solid rgba(139,107,170,.28);
             border-radius:8px;padding:9px;font-size:13px;line-height:1.6;min-height:72px;
             resize:vertical;font-family:inherit;}
.komm-input:focus{outline:none;border-color:rgba(139,107,170,.55);}
.komm-result{background:#0b0a10;border:1px solid rgba(189,162,124,.22);border-radius:8px;
              padding:10px;font-size:12px;white-space:pre-wrap;line-height:1.7;
              max-height:240px;overflow-y:auto;color:rgba(255,255,255,.82);}
.komm-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;}
.btn-kp{background:rgba(139,107,170,.28);color:var(--kl);border:1px solid rgba(139,107,170,.48);
         padding:7px 13px;border-radius:7px;font-size:12px;font-weight:700;cursor:pointer;transition:all .15s;border-style:solid;}
.btn-kp:hover{background:rgba(139,107,170,.42);}
.btn-ks{background:rgba(255,255,255,.05);color:var(--muted);border:1px solid rgba(255,255,255,.1);
         padding:6px 11px;border-radius:7px;font-size:12px;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block;}
.btn-ks:hover{color:var(--text);background:rgba(255,255,255,.1);}

/* Korrektur Modal */
.modal-ov{display:none;position:fixed;inset:0;background:rgba(0,0,0,.84);z-index:400;align-items:center;justify-content:center;padding:20px;}
.modal-ov.open{display:flex;}
.modal{background:#161616;border:1px solid rgba(189,162,124,.28);border-radius:13px;padding:20px;width:100%;max-width:460px;}
.modal h3{color:var(--gold);font-size:14px;margin-bottom:12px;}
.modal select,.modal textarea,.modal input[type=text]{width:100%;background:#0b0b0b;color:var(--text);border:1px solid var(--border);
  border-radius:7px;padding:8px;font-size:13px;font-family:inherit;margin-bottom:9px;}
.modal textarea{min-height:70px;resize:vertical;}
.modal-actions{display:flex;gap:7px;margin-top:4px;}

.empty{color:var(--muted);font-size:13px;padding:7px 0;}
footer{color:var(--muted);font-size:12px;text-align:center;padding:13px;border-top:1px solid var(--border);}
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

        else:
            self._respond(404, 'text/plain', b'Not found')

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
                    grund = body.get('grund', '')
                    now = datetime.now().isoformat()
                    if new_status == 'bezahlt':
                        db.execute("UPDATE ausgangsrechnungen SET status='bezahlt', bezahlt_am=? WHERE id=?", (now, ar_id))
                    elif new_status in ('streitfall', 'offen'):
                        db.execute("UPDATE ausgangsrechnungen SET status=? WHERE id=?", (new_status, ar_id))
                    db.execute("INSERT INTO geschaeft_statistik (typ,referenz_id,ereignis,daten_json,erstellt_am) VALUES (?,?,?,?,?)",
                               ('ausgangsrechnung', ar_id, f'status_{new_status}', json.dumps({"grund": grund}), now))
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
                    grund = body.get('grund', '')
                    now = datetime.now().isoformat()
                    if new_status in ('angenommen', 'abgelehnt', 'keine_antwort', 'offen', 'bearbeitet'):
                        db.execute("UPDATE angebote SET status=? WHERE id=?", (new_status, ang_id))
                        if new_status == 'abgelehnt' and grund:
                            db.execute("UPDATE angebote SET grund_abgelehnt=? WHERE id=?", (grund, ang_id))
                        elif new_status == 'angenommen' and grund:
                            db.execute("UPDATE angebote SET grund_angenommen=? WHERE id=?", (grund, ang_id))
                    db.execute("INSERT INTO geschaeft_statistik (typ,referenz_id,ereignis,daten_json,erstellt_am) VALUES (?,?,?,?,?)",
                               ('angebot', ang_id, f'status_{new_status}', json.dumps({"grund": grund}), now))
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
            now = datetime.now().isoformat()
            if aktion == 'erledigt':
                db.execute("UPDATE geschaeft SET bewertung='erledigt', bewertung_grund='manuell erledigt' WHERE id=?", (gid,))
                db.commit()
                self._json({'ok': True})
            elif aktion == 'bewertung':
                bew = body.get('bewertung','')
                grund = body.get('grund','')
                db.execute("UPDATE geschaeft SET bewertung=?, bewertung_grund=? WHERE id=?",
                           (bew, grund, gid))
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

    httpd = HTTPServer(('127.0.0.1', port), DashboardHandler)
    url   = f"http://localhost:{port}"
    print(f"[Kira Dashboard v3] {url}")

    if open_browser and auto_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer gestoppt.")


if __name__ == '__main__':
    run_server()
