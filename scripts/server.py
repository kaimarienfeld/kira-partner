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
DETAIL_DB     = KNOWLEDGE_DIR / "rechnungen_detail.db"
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

    html = f"""
    <div class="gesch-tabs">
      <div class="gesch-tab active" onclick="showGeschTab('uebersicht')">Übersicht</div>
      <div class="gesch-tab" onclick="showGeschTab('ausgangsre')">Ausgangsrechnungen ({len(ar)})</div>
      <div class="gesch-tab" onclick="showGeschTab('angebote')">Angebote ({len(ang)})</div>
      <div class="gesch-tab" onclick="showGeschTab('eingangsre')">Eingangsrechnungen ({len(eingang)})</div>
      <div class="gesch-tab" onclick="showGeschTab('mahnungen')">Mahnungen ({n_mahnungen})</div>
    </div>
    <div id="gesch-uebersicht" class="gesch-panel active">{_build_gesch_uebersicht(ar_offen, ar_gemahnt, ang_offen, s_ar_offen, n_nf, eingang, today, stats)}</div>
    <div id="gesch-ausgangsre" class="gesch-panel">{_build_ar_table(ar)}</div>
    <div id="gesch-angebote" class="gesch-panel">{_build_ang_table(ang, today)}</div>
    <div id="gesch-eingangsre" class="gesch-panel">{_gesch_aktiv_cards(eingang)}</div>
    <div id="gesch-mahnungen" class="gesch-panel">{_build_mahnung_section(ar_gemahnt, ar_offen, mahnung_details)}</div>"""
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

<!-- Kira Interaktions-Modal (Statusänderungen) -->
<div class="modal-ov" id="kiraInteraktModal">
  <div class="modal" style="max-width:480px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <h3 id="ki-title" style="margin:0;color:var(--kl)">Kira fragt nach</h3>
      <button class="btn btn-tiny btn-muted" onclick="closeKiraInterakt()">&times;</button>
    </div>
    <div id="ki-context" style="font-size:12px;color:var(--muted);margin-bottom:12px;padding:8px;background:rgba(139,107,170,.06);border-radius:8px"></div>
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
    <div class="kira-tab" id="ktab-aufgaben"       onclick="showKTab('aufgaben')">Aufgaben</div>
    <div class="kira-tab" id="ktab-muster"         onclick="showKTab('muster')">Muster</div>
    <div class="kira-tab" id="ktab-kwissen"        onclick="showKTab('kwissen')">Gelernt</div>
  </div>
  <div class="kira-content">
    <div id="kc-home">
      <div id="kira-home-loading" style="color:var(--muted);font-size:13px;padding:10px">Lade Insights&hellip;</div>
      <div id="kira-home-content" style="display:none"></div>
    </div>
    <div id="kc-aufgaben" style="display:none">
      <div id="kira-aufgaben-list"><div style="color:var(--muted);font-size:13px;">Lade&hellip;</div></div>
    </div>
    <div id="kc-muster" style="display:none">
      <div id="kira-muster-content"><div style="color:var(--muted);font-size:13px;">Lade&hellip;</div></div>
    </div>
    <div id="kc-kwissen" style="display:none">
      <div id="kira-lernen-list"><div style="color:var(--muted);font-size:13px;">Lade&hellip;</div></div>
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
  localStorage.setItem('kira_active_tab', name);
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
  const tabs = document.querySelectorAll('.gesch-tab');
  const names = ['uebersicht','ausgangsre','angebote','eingangsre','mahnungen'];
  const idx = names.indexOf(name);
  if (idx >= 0 && tabs[idx]) tabs[idx].classList.add('active');
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
function closeKira(){{ kiraOpen=false; document.getElementById('kiraPanel').classList.remove('open'); localStorage.setItem('kira_dismissed', Date.now()); }}

// Kira tabs
function showKTab(name){{
  document.querySelectorAll('.kira-tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('[id^=kc-]').forEach(c=>c.style.display='none');
  document.getElementById('ktab-'+name)?.classList.add('active');
  document.getElementById('kc-'+name).style.display='block';
  if(name==='aufgaben') loadKiraInsights('aufgaben');
  if(name==='muster') loadKiraInsights('muster');
  if(name==='kwissen') loadKiraInsights('kwissen');
}}

// Kira Insights laden und rendern
let kiraInsightsCache = null;
function loadKiraInsights(tab) {{
  const render = (data) => {{
    if(tab==='aufgaben' || !tab) renderKiraAufgaben(data);
    if(tab==='muster' || !tab) renderKiraMuster(data);
    if(tab==='kwissen' || !tab) renderKiraLernen(data);
    if(!tab) renderKiraHome(data);
  }};
  if(kiraInsightsCache) {{ render(kiraInsightsCache); return; }}
  fetch('/api/kira/insights').then(r=>r.json()).then(data=>{{
    kiraInsightsCache = data;
    render(data);
  }}).catch(()=>{{}});
}}

function renderKiraHome(data) {{
  const el = document.getElementById('kira-home-content');
  const loading = document.getElementById('kira-home-loading');
  if(!el) return;
  const aufgaben = data.aufgaben || [];
  let html = '';
  if(aufgaben.length > 0) {{
    html += '<div class="kira-sec"><div class="kira-sec-title" style="color:#e84545">Hallo Kai, ich habe '+aufgaben.length+' wichtige Punkte</div>';
    aufgaben.slice(0,5).forEach(a => {{
      const pcls = a.prio >= 3 ? 'kira-prio-high' : a.prio >= 2 ? 'kira-prio-med' : 'kira-prio-low';
      html += '<div class="kira-card kira-task-card '+pcls+'" onclick="'+a.action+';closeKira()" style="cursor:pointer"><div class="kira-card-meta">'+a.text+'</div></div>';
    }});
    html += '</div>';
  }} else {{
    html += '<div class="kira-sec"><div class="kira-sec-title" style="color:#50c878">Alles im Griff</div><div class="kira-card"><div class="kira-card-meta">Keine dringenden Aufgaben. Gut gemacht!</div></div></div>';
  }}
  // Muster-Teaser
  const m = data.muster || {{}};
  if(m.zahlungsdauer_avg || m.angebotsquote) {{
    html += '<div class="kira-sec"><div class="kira-sec-title">Erkenntnisse</div>';
    if(m.zahlungsdauer_avg) html += '<div class="kira-card"><div class="kira-card-meta">Zahlungsdauer: \u00D8 '+m.zahlungsdauer_avg+' Tage ('+m.zahlungsdauer_n+' Rechnungen)</div></div>';
    if(m.angebotsquote) html += '<div class="kira-card"><div class="kira-card-meta">Angebotsquote: '+m.angebotsquote+'% ('+m.angebote_angenommen+'/'+m.angebote_total+')</div></div>';
    html += '</div>';
  }}
  // Letzte Erkenntnisse
  const lernen = data.lernen || [];
  if(lernen.length > 0) {{
    html += '<div class="kira-sec"><div class="kira-sec-title">Zuletzt gelernt</div>';
    lernen.slice(0,3).forEach(l => {{
      html += '<div class="kira-card"><div class="kira-card-meta" style="font-size:11px"><strong>'+escH(l.titel)+'</strong><br>'+escH(l.inhalt).substring(0,100)+'</div></div>';
    }});
    html += '</div>';
  }}
  el.innerHTML = html;
  if(loading) loading.style.display = 'none';
  el.style.display = 'block';
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

// Kira proaktiv öffnen wenn wichtige Aufgaben da sind
function kiraProaktivCheck() {{
  const dismissed = parseInt(localStorage.getItem('kira_dismissed')||'0');
  const cooldown = 30 * 60 * 1000; // 30 Minuten Cooldown nach Dismiss
  if(Date.now() - dismissed < cooldown) return;
  fetch('/api/kira/insights').then(r=>r.json()).then(data=>{{
    kiraInsightsCache = data;
    const hochprio = (data.aufgaben||[]).filter(a => a.prio >= 2);
    if(hochprio.length > 0 && !kiraOpen) {{
      renderKiraHome(data);
      // Sanftes Aufpoppen nach 2 Sekunden
      setTimeout(()=>{{
        if(!kiraOpen) {{
          openKiraNaked();
          const fab = document.querySelector('.kira-fab');
          if(fab) fab.classList.add('kira-fab-pulse');
        }}
      }}, 2000);
    }} else {{
      renderKiraHome(data);
    }}
  }}).catch(()=>{{}});
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
    if(document.getElementById('kiraInteraktModal').classList.contains('open')) closeKiraInterakt();
    else if(document.getElementById('mailReadModal').classList.contains('open')) closeMailRead();
    else if(document.getElementById('geschBewertModal').classList.contains('open')) closeGeschBewertung();
    else if(document.getElementById('editRegelModal').classList.contains('open')) closeEditRegel();
    else if(document.getElementById('korrModal').classList.contains('open')) closeKorrModal();
    else if(kiraOpen) closeKira();
  }}
}});
// Restore active tab on load
(function(){{
  const tab = localStorage.getItem('kira_active_tab');
  if(tab && tab !== 'dashboard') showPanel(tab);
  const gt = localStorage.getItem('kira_gesch_tab');
  if(gt && gt !== 'uebersicht') showGeschTab(gt);
}})();
// Kira proaktiv: Insights laden + ggf. Panel öffnen
setTimeout(()=>kiraProaktivCheck(), 1500);
// Auto-refresh every 5 min, preserves tab state via localStorage
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
.gc-detail{min-width:100px;flex:1;color:var(--muted);}
.gc-actions{display:flex;gap:4px;min-width:100px;justify-content:flex-end;}
.gesch-ar-summary{display:flex;gap:20px;padding:10px 14px;margin-bottom:10px;background:rgba(189,162,124,.06);
  border:1px solid var(--border);border-radius:8px;font-size:13px;flex-wrap:wrap;}
.gesch-ar-summary span{white-space:nowrap;}
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

/* Geschäft Hero-Volumen */
.gesch-volumen-hero{background:linear-gradient(135deg,rgba(189,162,124,.08),rgba(189,162,124,.02));border:1px solid rgba(189,162,124,.2);border-radius:12px;padding:18px 24px;margin-bottom:16px;text-align:center;transition:border-color .2s;}
.gesch-volumen-hero:hover{border-color:rgba(189,162,124,.5);}
.gesch-volumen-hero.gesch-sum-alarm{border-color:rgba(232,69,69,.3);background:linear-gradient(135deg,rgba(232,69,69,.06),rgba(232,69,69,.02));}
.gesch-volumen-label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;}
.gesch-volumen-num{font-size:28px;font-weight:800;color:var(--gold);letter-spacing:-.5px;}
.gesch-volumen-hero.gesch-sum-alarm .gesch-volumen-num{color:#e84545;}
.gesch-volumen-sub{font-size:12px;color:var(--muted);margin-top:2px;}
.gesch-sum-card{cursor:pointer;transition:border-color .2s,transform .1s;}
.gesch-sum-card:hover{border-color:rgba(189,162,124,.4);transform:translateY(-1px);}
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
.kira-task-card{cursor:pointer;transition:all .2s;}
.kira-task-card:hover{border-color:rgba(139,107,170,.4);background:rgba(139,107,170,.1);transform:translateX(-2px);}
.kira-prio-high{border-left:3px solid #e84545;}
.kira-prio-med{border-left:3px solid #f0ad4e;}
.kira-prio-low{border-left:3px solid rgba(189,162,124,.4);}
.kira-fab-pulse{animation:kiraPulse 2s ease-in-out infinite;}
@keyframes kiraPulse{0%,100%{box-shadow:0 3px 15px rgba(93,63,122,.4);}50%{box-shadow:0 3px 25px rgba(232,69,69,.6);}}
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

        elif self.path == '/api/kira/insights':
            self._api_kira_insights()

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
