#!/usr/bin/env python3
"""
generate_partner_view.py
════════════════════════
Liest feature_registry.json und aktualisiert partner_view.html.

Usage:
  python generate_partner_view.py          # lokal generieren (kein Push)
  python generate_partner_view.py --push   # generieren + lokaler Git-Push
  python generate_partner_view.py --check  # nur prüfen ob HTML aktuell ist
  python generate_partner_view.py --auto   # VOLLAUTOMATISCH: generieren + GitHub API Push
                                           #   + Mail/ntfy an Leni wenn neue Features
                                           #   (max 1x/Tag, technische Pushes ohne Mail)

Konfiguration:
  scripts/config.json   : partner_view.*, ntfy.*
  scripts/secrets.json  : github_pat (Fine-grained PAT für kira-partner)
"""

import json
import os
import re
import sys
import subprocess
import shutil
import base64
import hashlib
import urllib.request
import urllib.error
from datetime import date, datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# PFADE
# ─────────────────────────────────────────────────────────────
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
BASE_DIR      = os.path.dirname(SCRIPT_DIR)
REGISTRY_PATH = os.path.join(BASE_DIR, 'feature_registry.json')
HTML_PATH     = os.path.join(BASE_DIR, 'partner_view.html')
CONFIG_PATH   = os.path.join(SCRIPT_DIR, 'config.json')
SECRETS_PATH  = os.path.join(SCRIPT_DIR, 'secrets.json')
AUTO_STATE_PATH = os.path.join(BASE_DIR, 'knowledge', 'partner_auto_state.json')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'knowledge', 'mail_templates')

# ─────────────────────────────────────────────────────────────
# STATUS-MAPPING: intern -> partner-view
# ─────────────────────────────────────────────────────────────
STATUS_MAP = {
    'done':      'done',
    'partial':   'partial',
    'planned':   'planned',
    'leni_idea': 'leni_idea',
    'leni_done': 'leni_done',
}

DEFAULT_ICON = '⚙️'


# ─────────────────────────────────────────────────────────────
# KONFIGURATION laden
# ─────────────────────────────────────────────────────────────
def load_config():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────
# REGISTRY laden
# ─────────────────────────────────────────────────────────────
def load_registry():
    with open(REGISTRY_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────
# FEATURES -> JS-Array
# ─────────────────────────────────────────────────────────────
def build_features_js(features: list) -> str:
    """
    Wandelt die Registry-Features in das JS-Format für partner_view.html um.
    Features mit leni_visible=false werden übersprungen.
    """
    items = []
    skipped = []

    for f in features:
        if f.get('leni_visible') is False:
            skipped.append(f.get('id', '?'))
            continue

        status   = STATUS_MAP.get(
            f.get('leni_status') or f.get('status', 'planned'),
            'planned'
        )
        leni_name = f.get('leni_name') or f.get('name', '(kein Name)')
        leni_desc = f.get('leni_desc') or f.get('description', '')
        icon      = f.get('icon', DEFAULT_ICON)
        added     = f.get('last_updated', date.today().isoformat())
        leni_note = f.get('leni_note')

        items.append({
            'id':        f['id'],
            'icon':      icon,
            'name':      leni_name,
            'status':    status,
            'added':     added,
            'desc':      leni_desc,
            'leni_note': leni_note
        })

    js = json.dumps(items, ensure_ascii=False, indent=2)
    return js, items, skipped


# ─────────────────────────────────────────────────────────────
# HTML AKTUALISIEREN
# ─────────────────────────────────────────────────────────────
def build_cfg_js(config: dict, today: str) -> str:
    """
    Baut den CFG-Block aus config.json für die partner_view.html.
    Liest Passwörter und ntfy-Einstellungen aus der lokalen Konfiguration.
    """
    partner = config.get('partner_view', {})
    ntfy    = config.get('ntfy', {})

    cfg = {
        'pw_kai':      partner.get('partner_pw_kai',   'Kai2026'),
        'pw_leni':     partner.get('partner_pw_leni',  'Leni2026'),
        'app_start':   today,
        'ntfy_kai':    ntfy.get('topic_name',          ''),
        'ntfy_leni':   partner.get('ntfy_leni',        ''),
        'ntfy_server': ntfy.get('server',              'https://ntfy.sh'),
        'gh_owner':    partner.get('gh_owner',         'kaimarienfeld'),
        'gh_repo':     partner.get('gh_repo',          'kira-partner'),
    }
    return json.dumps(cfg, ensure_ascii=False, indent=2)


def update_html(features_js: str, cfg_js: str, updated_date: str) -> tuple[str, bool]:
    """
    Liest partner_view.html, ersetzt FEATURES- und CFG-Konstante per Regex.
    Gibt (neues_html, wurde_geändert) zurück.
    """
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        original = f.read()

    updated = original

    # Ersetze const FEATURES = [...];
    new_features = f'const FEATURES = {features_js};'
    pat_features = re.compile(r'const\s+FEATURES\s*=\s*\[.*?\];', re.DOTALL)
    updated, cnt_f = re.subn(pat_features, new_features, updated)
    if cnt_f == 0:
        raise ValueError(
            'FEATURES-Array nicht in partner_view.html gefunden. '
            'Bitte prüfen ob "const FEATURES = [...];" vorhanden ist.'
        )

    # Ersetze const CFG = {...};
    new_cfg  = f'const CFG = {cfg_js};'
    pat_cfg  = re.compile(r'const\s+CFG\s*=\s*\{.*?\};', re.DOTALL)
    updated, cnt_c = re.subn(pat_cfg, new_cfg, updated)
    if cnt_c == 0:
        print('  WARN CFG-Block nicht gefunden -- FEATURES wurden trotzdem aktualisiert.')

    # Pflege-Kommentar: Zeitstempel der letzten Generator-Ausführung
    ts_pattern = re.compile(r'<!-- generated: .*? -->')
    ts_comment = f'<!-- generated: {updated_date} -->'
    if ts_pattern.search(updated):
        updated = ts_pattern.sub(ts_comment, updated)
    else:
        updated = updated.replace('</title>', f'</title>\n{ts_comment}')

    changed = (updated != original)
    return updated, changed


def write_html(content: str):
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(content)


# ─────────────────────────────────────────────────────────────
# GITHUB PUSH
# ─────────────────────────────────────────────────────────────
def push_to_github(cfg: dict) -> bool:
    """
    Kopiert partner_view.html -> index.html im GitHub-Pages-Repo und pusht.
    Voraussetzung: Git ist konfiguriert und SSH/HTTPS-Auth funktioniert.
    """
    repo_dir = cfg.get('partner_github_repo_dir', '')
    branch   = cfg.get('partner_github_branch', 'main')
    repo_url = cfg.get('partner_github_repo_url', '')

    if not repo_dir:
        print('  FEHLER partner_github_repo_dir nicht in config.json konfiguriert.')
        print('    Bitte eintragen und nochmal pushen.')
        return False

    if not os.path.isdir(repo_dir):
        print(f'  FEHLER Repo-Verzeichnis nicht gefunden: {repo_dir}')
        print(f'    Bitte Repository klonen: git clone {repo_url} {repo_dir}')
        return False

    target_html = os.path.join(repo_dir, 'index.html')
    shutil.copy2(HTML_PATH, target_html)
    print(f'  -> Kopiert nach {target_html}')

    today_str = date.today().isoformat()
    cmds = [
        (['git', 'add', 'index.html'],                                    'Staging'),
        (['git', 'commit', '-m', f'auto: partner view update {today_str}'], 'Commit'),
        (['git', 'push', 'origin', branch],                               'Push'),
    ]

    for cmd, label in cmds:
        result = subprocess.run(
            cmd, cwd=repo_dir,
            capture_output=True, text=True, encoding='utf-8'
        )
        if result.returncode != 0:
            # "nothing to commit" ist kein echter Fehler
            if 'nothing to commit' in result.stdout + result.stderr:
                print(f'  -> {label}: Keine Änderungen (bereits aktuell)')
                return True
            print(f'  FEHLER {label} fehlgeschlagen:')
            print(f'    {result.stderr.strip()}')
            return False
        print(f'  OK {label}')

    if repo_url:
        # GitHub Pages braucht ~1 Min zum Rebuild
        pages_url = repo_url.replace('github.com', 'USERNAME.github.io').replace('https://github.com/', '')
        print(f'\n  GitHub Pages aktualisiert! URL: https://{pages_url}/')
        print('     (Seite braucht ~1 Minute zum Erscheinen)')

    return True


# ─────────────────────────────────────────────────────────────
# LENIS FEEDBACK AUSWERTEN (für open_tasks)
# ─────────────────────────────────────────────────────────────
def check_leni_feedback_pending(features: list) -> list:
    return [f for f in features if f.get('status') == 'leni_idea']


# ─────────────────────────────────────────────────────────────
# SECRETS laden
# ─────────────────────────────────────────────────────────────
def load_secrets() -> dict:
    try:
        with open(SECRETS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────
# AUTO-STATE: persistenter Zustand für --auto Modus
# ─────────────────────────────────────────────────────────────
def load_auto_state() -> dict:
    try:
        with open(AUTO_STATE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_auto_state(state: dict):
    os.makedirs(os.path.dirname(AUTO_STATE_PATH), exist_ok=True)
    with open(AUTO_STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────
# GITHUB API PUSH (kein lokaler Clone nötig)
# ─────────────────────────────────────────────────────────────
def push_to_github_api(html_content: str, cfg: dict) -> bool:
    """
    Pusht partner_view.html als index.html zum GitHub-Repo via REST API.
    Liest den aktuellen SHA, vergleicht Content, PUT bei Änderungen.
    """
    secrets = load_secrets()
    token = secrets.get('github_pat') or secrets.get('partner_feedback_token', '')
    if not token:
        print('  FEHLER: Kein GitHub-Token in secrets.json (github_pat)')
        return False

    partner = cfg.get('partner_view', {})
    owner = partner.get('gh_owner', 'kaimarienfeld')
    repo = partner.get('gh_repo', 'kira-partner')
    branch = cfg.get('partner_github_branch') or partner.get('partner_github_branch', 'main')
    api_url = f'https://api.github.com/repos/{owner}/{repo}/contents/index.html'

    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'KIRA-Partner-Generator/1.0',
    }

    # GET: aktuellen SHA + Content holen
    req = urllib.request.Request(api_url + f'?ref={branch}', headers=headers)
    current_sha = None
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            current_sha = data.get('sha', '')
            # Content vergleichen (base64-decoded)
            remote_content = base64.b64decode(data.get('content', '')).decode('utf-8')
            if remote_content.strip() == html_content.strip():
                print('  -> GitHub: index.html ist bereits identisch (kein Push nötig)')
                return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print('  -> GitHub: index.html existiert noch nicht, wird neu erstellt')
        else:
            print(f'  FEHLER GitHub GET: {e.code} {e.reason}')
            return False
    except Exception as e:
        print(f'  FEHLER GitHub GET: {e}')
        return False

    # PUT: neuen Content hochladen
    content_b64 = base64.b64encode(html_content.encode('utf-8')).decode('ascii')
    today_str = date.today().isoformat()
    put_body = {
        'message': f'auto: Partner-View Update {today_str}',
        'content': content_b64,
        'branch': branch,
    }
    if current_sha:
        put_body['sha'] = current_sha

    put_data = json.dumps(put_body).encode('utf-8')
    req = urllib.request.Request(api_url, data=put_data, headers={
        **headers, 'Content-Type': 'application/json'
    }, method='PUT')

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            commit_sha = result.get('commit', {}).get('sha', '?')[:7]
            print(f'  OK GitHub Push erfolgreich (Commit: {commit_sha})')
            pages_url = f'https://{owner}.github.io/{repo}'
            print(f'  -> Live: {pages_url}/ (1-2 Min. bis GitHub Pages aktualisiert)')
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f'  FEHLER GitHub PUT: {e.code} {e.reason}')
        print(f'    {body[:200]}')
        return False
    except Exception as e:
        print(f'  FEHLER GitHub PUT: {e}')
        return False


# ─────────────────────────────────────────────────────────────
# FEATURE-CHANGE-ERKENNUNG
# ─────────────────────────────────────────────────────────────
def detect_feature_changes(visible_items: list, auto_state: dict) -> list:
    """
    Vergleicht aktuelle sichtbare Features mit dem letzten Snapshot.
    Gibt Liste von Änderungs-Strings zurück (z.B. "Dashboard-Redesign (neu)").
    """
    prev_features = auto_state.get('last_features', {})
    changes = []

    for item in visible_items:
        fid = item['id']
        name = item['name']
        status = item['status']

        if fid not in prev_features:
            changes.append(f'{name} (neu)')
        elif prev_features[fid].get('status') != status:
            old_label = _status_label(prev_features[fid].get('status', ''))
            new_label = _status_label(status)
            changes.append(f'{name} ({old_label} \u2192 {new_label})')

    return changes


def _status_label(s: str) -> str:
    return {'done': 'Eingebaut', 'partial': 'Teilweise', 'planned': 'Geplant',
            'leni_idea': 'Leni-Idee', 'leni_done': 'Umgesetzt'}.get(s, s)


def save_feature_snapshot(visible_items: list, auto_state: dict) -> dict:
    """Speichert den aktuellen Feature-Stand als Snapshot."""
    auto_state['last_features'] = {
        item['id']: {'name': item['name'], 'status': item['status']}
        for item in visible_items
    }
    auto_state['last_push_date'] = datetime.now().isoformat()
    return auto_state


# ─────────────────────────────────────────────────────────────
# MAIL-VERSAND (direkt über mail_monitor.send_system_mail)
# ─────────────────────────────────────────────────────────────
def send_update_mail(cfg: dict, feature_changes: list) -> bool:
    """Sendet HTML-Update-Mail an Leni + BCC mit den neuen Features."""
    partner = cfg.get('partner_view', {})
    to_addr = partner.get('leni_email', '')
    bcc_addr = partner.get('leni_mail_bcc', '')

    if not to_addr and not bcc_addr:
        print('  -> Mail: Kein Empfänger konfiguriert (leni_email / leni_mail_bcc)')
        return False

    # HTML-Template laden
    tpl_path = os.path.join(TEMPLATES_DIR, 'benachrichtigung.html')
    if not os.path.exists(tpl_path):
        print(f'  -> Mail: Template nicht gefunden: {tpl_path}')
        return False

    with open(tpl_path, 'r', encoding='utf-8') as f:
        html_tpl = f.read()

    # Feature-Blöcke bauen
    feat_html = ''
    feat_text_lines = []
    for feat in feature_changes:
        feat_html += (
            '<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:6px">'
            '<tr><td style="padding:8px 12px;background:#f8f7ff;border-radius:6px">'
            '<span style="color:#7c4dff;font-weight:600;margin-right:6px">&#10024;</span>'
            f'<span style="color:#1e1e2e;font-size:14px">{feat}</span>'
            '</td></tr></table>'
        )
        feat_text_lines.append(f'  * {feat}')

    today_str = date.today().strftime('%d.%m.%Y')
    owner = partner.get('gh_owner', 'kaimarienfeld')
    repo = partner.get('gh_repo', 'kira-partner')
    link = f'https://{owner}.github.io/{repo}'

    html = (html_tpl
        .replace('{{TITEL}}', f'{len(feature_changes)} neue Updates für dich')
        .replace('{{DATUM}}', today_str)
        .replace('{{INTRO_TEXT}}', 'Es gibt neue Funktionen und Verbesserungen in KIRA!')
        .replace('{{FEATURES_BLOCK}}', feat_html)
        .replace('{{LINK}}', link))

    text = (f'KIRA Update - {today_str}\n\n'
            f'{len(feature_changes)} neue Features/Änderungen:\n'
            + '\n'.join(feat_text_lines) +
            f'\n\nSchau dir alles an: {link}')

    subject = f'KIRA Update: {len(feature_changes)} neue Features'

    # mail_monitor importieren und senden
    try:
        sys.path.insert(0, SCRIPT_DIR)
        from mail_monitor import send_system_mail
        result = send_system_mail(
            to=to_addr,
            subject=subject,
            body_text=text,
            body_html=html,
            bcc=bcc_addr if bcc_addr and bcc_addr != to_addr else ''
        )
        if result.get('ok'):
            print(f'  OK Mail gesendet an {to_addr} (BCC: {bcc_addr or "-"}) via {result.get("from", "?")}')
            return True
        else:
            print(f'  FEHLER Mail: {result.get("error", "unbekannt")}')
            return False
    except Exception as e:
        print(f'  FEHLER Mail-Import/Versand: {e}')
        return False


# ─────────────────────────────────────────────────────────────
# NTFY PUSH
# ─────────────────────────────────────────────────────────────
def send_ntfy_push(cfg: dict, feature_changes: list):
    """Sendet ntfy-Push an Kais Topic (und Lenis, falls konfiguriert)."""
    ntfy_cfg = cfg.get('ntfy', {})
    server = ntfy_cfg.get('server', 'https://ntfy.sh')
    topics = []

    kai_topic = ntfy_cfg.get('topic_name', '')
    if kai_topic:
        topics.append(('Kai', kai_topic))

    leni_topic = cfg.get('partner_view', {}).get('ntfy_leni', '')
    if leni_topic:
        topics.append(('Leni', leni_topic))

    if not topics:
        return

    title = f'KIRA: {len(feature_changes)} neue Features'
    body = '\n'.join(f'* {f}' for f in feature_changes[:5])
    if len(feature_changes) > 5:
        body += f'\n... und {len(feature_changes) - 5} weitere'

    for name, topic in topics:
        try:
            url = f'{server}/{topic}'
            data = body.encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={
                'Title': title,
                'Tags': 'sparkles,kira',
                'Priority': '3',
            })
            with urllib.request.urlopen(req, timeout=8):
                print(f'  OK ntfy Push an {name} ({topic})')
        except Exception as e:
            print(f'  WARN ntfy Push an {name} fehlgeschlagen: {e}')


# ─────────────────────────────────────────────────────────────
# --auto MODUS: Alles automatisch
# ─────────────────────────────────────────────────────────────
def run_auto(features: list, cfg: dict, visible_items: list,
             features_js: str, cfg_js: str, today_str: str):
    """
    Vollautomatischer Ablauf:
    1. HTML regenerieren
    2. Zu GitHub pushen (API)
    3. Feature-Änderungen erkennen
    4. Mail + ntfy senden (max 1x/Tag, nur bei echten Feature-Änderungen)
    """
    print('\n  === AUTO-MODUS ===')

    # 1. HTML aktualisieren
    try:
        new_html, html_changed = update_html(features_js, cfg_js, today_str)
    except (FileNotFoundError, ValueError) as e:
        print(f'  FEHLER HTML-Update: {e}')
        return False

    if html_changed:
        write_html(new_html)
        print(f'  OK HTML aktualisiert')
    else:
        print(f'  -> HTML bereits aktuell')

    # HTML-Content für GitHub (frisch lesen, egal ob gerade geändert oder nicht)
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html_for_push = f.read()

    # 2. GitHub API Push
    print('\n  [Schritt 2] GitHub Push...')
    push_ok = push_to_github_api(html_for_push, cfg)
    if not push_ok:
        print('  FEHLER GitHub Push gescheitert -- Abbruch')
        return False

    # 3. Feature-Änderungen erkennen
    auto_state = load_auto_state()
    changes = detect_feature_changes(visible_items, auto_state)

    # Snapshot IMMER speichern (auch ohne Mail)
    auto_state = save_feature_snapshot(visible_items, auto_state)

    if not changes:
        print('\n  [Schritt 3] Keine neuen Feature-Änderungen erkannt')
        print('  -> Technischer Push (keine Mail/ntfy)')
        save_auto_state(auto_state)
        return True

    print(f'\n  [Schritt 3] {len(changes)} Feature-Änderung(en) erkannt:')
    for c in changes:
        print(f'     * {c}')

    # 4. 1x/Tag-Limit prüfen
    last_mail_date = auto_state.get('last_mail_date', '')
    today_iso = date.today().isoformat()

    if last_mail_date == today_iso:
        print(f'\n  [Schritt 4] Mail bereits heute gesendet ({last_mail_date}) -- übersprungen')
        save_auto_state(auto_state)
        return True

    # 5. Mail senden
    print(f'\n  [Schritt 4] Sende Benachrichtigungen...')
    mail_ok = send_update_mail(cfg, changes)

    # 6. ntfy Push
    send_ntfy_push(cfg, changes)

    # State aktualisieren
    if mail_ok:
        auto_state['last_mail_date'] = today_iso
        auto_state['last_mail_features'] = changes
    save_auto_state(auto_state)

    print('\n  === AUTO-MODUS ABGESCHLOSSEN ===')
    return True


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    mode_push  = '--push'  in sys.argv
    mode_check = '--check' in sys.argv
    mode_auto  = '--auto'  in sys.argv

    print(f'\n  KIRA Partner-View Generator -- {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('  ' + '-' * 54)

    # Registry laden
    try:
        registry = load_registry()
    except FileNotFoundError:
        print(f'  FEHLER feature_registry.json nicht gefunden: {REGISTRY_PATH}')
        sys.exit(1)

    features   = registry.get('features', [])
    cfg        = load_config()
    today_str  = date.today().isoformat()

    # Features -> JS
    features_js, visible_items, skipped = build_features_js(features)
    cfg_js = build_cfg_js(cfg, today_str)

    print(f'  -> Registry: {len(features)} Features total')
    print(f'  -> Sichtbar: {len(visible_items)} | Versteckt: {len(skipped)}')

    # Status-Zusammenfassung
    status_counts = {}
    for item in visible_items:
        s = item['status']
        status_counts[s] = status_counts.get(s, 0) + 1
    for s, cnt in sorted(status_counts.items()):
        label = {'done':'Eingebaut','partial':'Teilweise','planned':'Geplant',
                 'leni_idea':'Lenis Ideen','leni_done':'Umgesetzt'}.get(s, s)
        print(f'     {label}: {cnt}')

    # Leni-Ideen Check
    pending_leni = check_leni_feedback_pending(features)
    if pending_leni:
        print(f'\n  >> {len(pending_leni)} offene Leni-Idee(n):')
        for f in pending_leni:
            print(f'     [{f["id"]}] {f.get("leni_name", f.get("name", "?"))}')

    if mode_check:
        print('\n  OK Check abgeschlossen.')
        return

    # --auto Modus: Alles automatisch
    if mode_auto:
        success = run_auto(features, cfg, visible_items, features_js, cfg_js, today_str)
        sys.exit(0 if success else 1)

    # Standard-Modus: nur lokal generieren
    try:
        new_html, changed = update_html(features_js, cfg_js, today_str)
    except (FileNotFoundError, ValueError) as e:
        print(f'  FEHLER beim HTML-Update: {e}')
        sys.exit(1)

    if changed:
        write_html(new_html)
        print(f'\n  OK partner_view.html aktualisiert -> {HTML_PATH}')
    else:
        print(f'\n  OK partner_view.html ist bereits aktuell')

    # --push: lokaler Git-Push (Legacy)
    if mode_push:
        print('\n  Pushe zu GitHub Pages (lokal)...')
        if push_to_github(cfg):
            print('  OK Fertig!')
        else:
            print('  FEHLER Push fehlgeschlagen.')
            sys.exit(1)
    elif not mode_auto:
        print('\n  -> Automatisch: python generate_partner_view.py --auto')
        print('  -> Lokaler Push: python generate_partner_view.py --push')
        print()


if __name__ == '__main__':
    main()
