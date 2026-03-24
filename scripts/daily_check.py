#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rauMKult® Daily Check v4
- Neue Mails scannen und mit mail_classifier klassifizieren
- Unbeantwortete Mails -> Tasks anlegen (via rebuild_all Logik)
- Erinnerungen für offene Tasks
- ntfy.sh + Toast Notifications
- Inkrementelles Update (kein vollständiger Rebuild)
"""
import json, sqlite3, re, subprocess, sys
from pathlib import Path
from datetime import datetime, timedelta
from html.parser import HTMLParser

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
COWORK_DIR    = SCRIPTS_DIR.parent / "cowork"
STATUS_FILE   = KNOWLEDGE_DIR / "daily_check_status.json"
COWORK_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(SCRIPTS_DIR))
from task_manager import get_due_reminders, increment_reminder, load_config
from mail_classifier import classify_mail, extract_email, is_system_sender, kategorie_to_task_typ
from response_gen import generate_draft

ARCHIV_ROOT = Path(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\Archiv")
MAILBOXEN = ["anfrage_raumkult_eu","info_raumkult_eu","invoice_sichtbeton-cire_de",
             "kaimrf_rauMKultSichtbeton_onmicrosoft_com","shop_sichtbeton-cire_de"]
KONTO_LABEL = {
    "anfrage@raumkult.eu":"anfrage","info@raumkult.eu":"info",
    "invoice@sichtbeton-cire.de":"invoice","shop@sichtbeton-cire.de":"shop",
    "kaimrf@rauMKultSichtbeton.onmicrosoft.com":"intern",
}
EIGENE_DOMAINS = {"raumkult.eu","sichtbeton-cire.de","raumkultsichtbeton.onmicrosoft.com"}

TASKS_DB  = KNOWLEDGE_DIR / "tasks.db"
KUNDEN_DB = KNOWLEDGE_DIR / "kunden.db"
SENT_DB   = KNOWLEDGE_DIR / "sent_mails.db"


# ── HTML Helper ───────────────────────────────────────────────────────────────
class _P(HTMLParser):
    def __init__(self): super().__init__(); self.r=[]; self.s=False
    def handle_starttag(self,t,a):
        if t in('style','script','head'): self.s=True
        if t in('br','p','div','li','tr'): self.r.append('\n')
    def handle_endtag(self,t):
        if t in('style','script','head'): self.s=False
    def handle_data(self,d):
        if not self.s and d.strip(): self.r.append(d.strip())
    def text(self): return re.sub(r'\s+',' ',' '.join(self.r)).strip()

def h2t(html):
    if not html: return ""
    try: p=_P(); p.feed(html); return p.text()
    except: return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',html)).strip()


# ── Status ────────────────────────────────────────────────────────────────────
def load_status():
    if STATUS_FILE.exists():
        return json.loads(STATUS_FILE.read_text('utf-8'))
    return {"letzter_lauf":(datetime.now()-timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")}

def save_status(data):
    STATUS_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8')


def get_kunden_email(absender, an, folder):
    q = an if ("Gesendete" in folder or "Sent" in folder) else absender
    m = re.search(r'<([^>]+@[^>]+)>',q)
    email = m.group(1).lower() if m else q.lower()
    domain = email.split('@')[-1] if '@' in email else ''
    return None if domain in EIGENE_DOMAINS else email.strip()


# ── Neue Mails scannen ───────────────────────────────────────────────────────
def scan_new_mails(since_dt):
    new_mails = []
    for mbx in MAILBOXEN:
        mbx_path = ARCHIV_ROOT / mbx
        if not mbx_path.exists(): continue
        kl = next((v for k,v in KONTO_LABEL.items() if k.lower() in mbx.replace("_","@",1).lower()), mbx[:8])
        for folder_dir in mbx_path.iterdir():
            if not folder_dir.is_dir(): continue
            fn = folder_dir.name
            for mail_dir in folder_dir.iterdir():
                if not mail_dir.is_dir(): continue
                mj = mail_dir/"mail.json"
                if not mj.exists(): continue
                dn = mail_dir.name
                if len(dn)>=10:
                    try:
                        if datetime.strptime(dn[:10],"%Y-%m-%d") < since_dt - timedelta(days=1): continue
                    except: pass
                try: mail=json.loads(mj.read_text('utf-8'))
                except: continue
                ds = mail.get('datum','') or ''
                try: mdt=datetime.strptime(ds[:19],"%Y-%m-%d %H:%M:%S")
                except: continue
                if mdt <= since_dt: continue
                tp = h2t(mail.get('text','') or '')
                new_mails.append({
                    "konto": next((v for k,v in KONTO_LABEL.items() if k.lower() in (mail.get('konto','') or '').lower()), kl),
                    "betreff":mail.get('betreff','') or '','absender':mail.get('absender','') or '',
                    "an":mail.get('an','') or '','datum':ds,'message_id':mail.get('message_id',''),
                    "hat_anhaenge":bool(mail.get('hat_anhaenge')),'anhaenge':mail.get('anhaenge',[]),
                    "anhaenge_pfad":mail.get('anhaenge_pfad','') or '','text_plain':tp,
                    "folder":fn,'mail_folder_pfad':str(mail_dir),'mailbox':mbx,
                })
    return sorted(new_mails, key=lambda x: x['datum'])


# ── Mails klassifizieren und in DBs eintragen ────────────────────────────────
def process_new_mails(new_mails, stats):
    """Klassifiziert neue Mails mit mail_classifier und trägt sie ein."""
    kunden_db = sqlite3.connect(str(KUNDEN_DB))
    sent_db   = sqlite3.connect(str(SENT_DB))
    tasks_db  = sqlite3.connect(str(TASKS_DB))
    tasks_db.row_factory = sqlite3.Row

    # Gesendete Index laden
    sent_index = {}
    try:
        sent_db.row_factory = sqlite3.Row
        for r in sent_db.execute("SELECT kunden_email, datum FROM gesendete_mails ORDER BY datum").fetchall():
            em = (r["kunden_email"] or "").lower()
            if em: sent_index.setdefault(em, []).append(r["datum"])
    except: pass

    for m in new_mails:
        folder  = m['folder']
        is_sent = "Gesendete" in folder or "Sent" in folder
        k_email = get_kunden_email(m['absender'], m['an'], folder)
        konto   = m['konto']
        absnd   = m['absender']
        betr    = m['betreff']
        text    = m['text_plain']
        datum   = m['datum']
        msgid   = m['message_id']

        # In kunden.db eintragen
        if k_email:
            try:
                kunden_db.execute("""INSERT OR IGNORE INTO interaktionen
                    (konto_label,betreff,absender,kunden_email,datum,datum_iso,message_id,folder,
                     mail_typ,text_plain,hat_anhaenge,anhaenge_pfad,mail_folder_pfad)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (konto, betr, absnd, k_email, datum, '', msgid, folder,
                     'eingehend' if not is_sent else 'gesendet',
                     text[:4000], 1 if m['hat_anhaenge'] else 0,
                     m['anhaenge_pfad'], m['mail_folder_pfad']))
                stats['kunden'] = stats.get('kunden',0)+1
            except: pass

        # Gesendete in sent_mails.db
        if is_sent and k_email:
            try:
                sent_db.execute("""INSERT OR IGNORE INTO gesendete_mails
                    (konto_label,betreff,an,kunden_email,datum,message_id,text_plain,hat_anhaenge,mail_typ,mail_folder_pfad)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (konto, betr, m['an'], k_email, datum, msgid,
                     text[:6000], 1 if m['hat_anhaenge'] else 0, 'gesendet', m['mail_folder_pfad']))
            except: pass
            continue  # Gesendete -> kein Task

        if not k_email: continue

        # Eigene Domain überspringen
        dom = k_email.split('@')[-1] if '@' in k_email else ''
        if dom in EIGENE_DOMAINS: continue

        # Klassifizieren mit mail_classifier
        cl = classify_mail(konto, absnd, betr, text, folder=folder, is_sent=is_sent)
        kat = cl["kategorie"]

        # Ignorieren / Newsletter / Zur Kenntnis -> kein Task
        if kat in ("Ignorieren", "Newsletter / Werbung", "Abgeschlossen", "Zur Kenntnis"):
            stats['ignoriert'] = stats.get('ignoriert',0)+1
            continue

        if kat in ("Shop / System", "Rechnung / Beleg") and not cl["antwort_noetig"]:
            stats['zur_kenntnis'] = stats.get('zur_kenntnis',0)+1
            continue

        # Schon beantwortet?
        dates = sent_index.get(k_email.lower(), [])
        if any(d > datum for d in dates):
            continue

        # Duplikat-Check
        if msgid:
            existing = tasks_db.execute("SELECT id FROM tasks WHERE message_id=?", (msgid,)).fetchone()
            if existing: continue

        task_typ = kategorie_to_task_typ(kat)

        # Entwurf
        entwurf = ""
        claude_prompt = ""
        if cl["antwort_noetig"] and k_email:
            try:
                draft = generate_draft(betr, absnd, text, k_email)
                entwurf = draft.get("entwurf","")
                claude_prompt = draft.get("claude_prompt","")
            except: pass

        # Task anlegen
        try:
            tasks_db.execute("""INSERT INTO tasks
                (typ, kategorie, titel, zusammenfassung, beschreibung,
                 kunden_email, kunden_name, absender_rolle, empfohlene_aktion,
                 kategorie_grund, message_id, mail_folder_pfad, anhaenge_pfad,
                 antwort_entwurf, claude_prompt, betreff, konto, datum_mail,
                 prioritaet, antwort_noetig)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task_typ, kat, betr[:120] or f"Mail von {k_email}",
                 cl["zusammenfassung"], text[:1000],
                 k_email, "", cl["absender_rolle"],
                 cl["empfohlene_aktion"], cl["kategorie_grund"],
                 msgid, m['mail_folder_pfad'], m['anhaenge_pfad'] or "",
                 entwurf[:4000], claude_prompt[:2000],
                 betr[:120], konto, datum,
                 cl["prioritaet"], 1 if cl["antwort_noetig"] else 0))
            stats['tasks_erstellt'] = stats.get('tasks_erstellt',0)+1
        except Exception as e:
            print(f"  Task-Fehler: {e}")

    kunden_db.commit(); kunden_db.close()
    sent_db.commit(); sent_db.close()
    tasks_db.commit(); tasks_db.close()


# ── Notifications ─────────────────────────────────────────────────────────────
def send_ntfy(title: str, message: str, priority: str = "default"):
    config = load_config()
    ntfy_cfg = config.get("ntfy", {})
    if not ntfy_cfg.get("aktiv"): return
    topic  = ntfy_cfg.get("topic_name","")
    server = ntfy_cfg.get("server","https://ntfy.sh")
    if not topic or topic.startswith("raumkult-dein"): return
    try:
        import urllib.request
        url  = f"{server}/{topic}"
        data = message.encode('utf-8')
        req  = urllib.request.Request(url, data=data, method='POST')
        req.add_header("Title", title)
        req.add_header("Priority", priority)
        req.add_header("Tags", "bell")
        urllib.request.urlopen(req, timeout=8)
        print("  ntfy: gesendet")
    except Exception as e:
        print(f"  ntfy: Fehler - {e}")


def send_toast(title: str, message: str):
    url = "http://localhost:8765"
    ps = f"""
try {{
  [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
  [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime] | Out-Null
  $xml = [Windows.Data.Xml.Dom.XmlDocument]::new()
  $xml.LoadXml('<toast launch="{url}"><visual><binding template="ToastGenericImageAndText02"><text id="1">{title}</text><text id="2">{message}</text></binding></visual><actions><action content="Dashboard" arguments="{url}" activationType="protocol"/></actions></toast>')
  $n = [Windows.UI.Notifications.ToastNotification]::new($xml)
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("rauMKult").Show($n)
}} catch {{}}
"""
    try:
        subprocess.run(["powershell.exe","-NoProfile","-NonInteractive",
                        "-ExecutionPolicy","Bypass","-Command",ps],
                       timeout=8, capture_output=True)
    except: pass


# ── Hauptprogramm ─────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().strftime('%H:%M')}] rauMKult Daily Check v4...")
    config = load_config()

    status = load_status()
    try: last_run = datetime.strptime(status["letzter_lauf"][:19],"%Y-%m-%d %H:%M:%S")
    except: last_run = datetime.now() - timedelta(days=1)

    # 1. Neue Mails scannen
    new_mails = scan_new_mails(last_run)
    stats = {"gesamt": len(new_mails), "kunden": 0, "tasks_erstellt": 0, "ignoriert": 0, "zur_kenntnis": 0}
    print(f"  Neue Mails: {len(new_mails)}")

    # 2. Klassifizieren und eintragen
    if new_mails:
        process_new_mails(new_mails, stats)
        print(f"  Tasks erstellt: {stats.get('tasks_erstellt',0)}")
        print(f"  Ignoriert: {stats.get('ignoriert',0)}")

    # 3. Fällige Erinnerungen
    due = get_due_reminders()
    for t in due:
        increment_reminder(t["id"])

    # 4. Offene Tasks + Nachfass-Fälligkeiten prüfen
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    open_tasks = db.execute("SELECT kategorie, COUNT(*) c FROM tasks WHERE status='offen' GROUP BY kategorie").fetchall()
    total_open = sum(r['c'] for r in open_tasks)
    n_antwort  = sum(r['c'] for r in open_tasks if r['kategorie'] == 'Antwort erforderlich')
    n_leads    = sum(r['c'] for r in open_tasks if r['kategorie'] == 'Neue Lead-Anfrage')

    # Nachfass-Fälligkeiten für Angebote
    today = datetime.now().strftime("%Y-%m-%d")
    n_nachfass = 0
    try:
        nf_rows = db.execute("SELECT a_nummer, kunde_email FROM angebote WHERE status='offen' AND naechster_nachfass IS NOT NULL AND naechster_nachfass <= ?", (today,)).fetchall()
        n_nachfass = len(nf_rows)
        if n_nachfass > 0:
            print(f"  Nachfass fällig: {n_nachfass} Angebote")
    except: pass

    # Offene Ausgangsrechnungen > 30 Tage
    n_overdue = 0
    try:
        cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        n_overdue = db.execute("SELECT COUNT(*) FROM ausgangsrechnungen WHERE status='offen' AND datum < ?", (cutoff,)).fetchone()[0]
        if n_overdue > 0:
            print(f"  Überfällige Rechnungen (>30 Tage): {n_overdue}")
    except: pass
    db.close()

    # 5. Notifications
    teile = []
    if n_antwort:  teile.append(f"{n_antwort} Antworten nötig")
    if n_leads:    teile.append(f"{n_leads} neue Leads")
    if due:        teile.append(f"{len(due)} Erinnerungen fällig")
    if n_nachfass: teile.append(f"{n_nachfass} Nachfass fällig")
    if n_overdue:  teile.append(f"{n_overdue} Rechnungen überfällig")

    if teile or total_open > 0:
        msg   = " · ".join(teile) if teile else f"{total_open} offene Aufgaben"
        title = f"rauMKult - {total_open} Aufgaben offen"
        send_toast(title, msg)
        send_ntfy(title, msg, priority="high" if n_antwort > 0 else "default")

    save_status({
        "letzter_lauf": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stats": stats,
        "offene_tasks": total_open,
    })

    print(f"  Tasks offen: {total_open} (davon {n_antwort} Antwort nötig)")
    print(f"  Erinnerungen fällig: {len(due)}")
    print(f"[{datetime.now().strftime('%H:%M')}] Fertig.")


if __name__ == "__main__":
    main()
