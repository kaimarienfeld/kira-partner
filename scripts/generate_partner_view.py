#!/usr/bin/env python3
"""
generate_partner_view.py
════════════════════════
Liest feature_registry.json und aktualisiert partner_view.html.

Wird automatisch nach jedem git commit im KIRA-Projekt aufgerufen.
Push zu GitHub erst nach expliziter Freigabe durch Kai.

Usage:
  python generate_partner_view.py          # lokal generieren (kein Push)
  python generate_partner_view.py --push   # generieren + nach GitHub pushen
  python generate_partner_view.py --check  # nur prüfen ob HTML aktuell ist

Konfiguration (scripts/config.json):
  partner_github_repo_dir  : lokaler Pfad zum geclonten GitHub-Pages-Repo
  partner_github_branch    : Branch (default: main)
  partner_github_repo_url  : z.B. https://github.com/USERNAME/kira-partner
"""

import json
import os
import re
import sys
import subprocess
import shutil
from datetime import date, datetime

# ─────────────────────────────────────────────────────────────
# PFADE
# ─────────────────────────────────────────────────────────────
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
BASE_DIR      = os.path.dirname(SCRIPT_DIR)
REGISTRY_PATH = os.path.join(BASE_DIR, 'feature_registry.json')
HTML_PATH     = os.path.join(BASE_DIR, 'partner_view.html')
CONFIG_PATH   = os.path.join(SCRIPT_DIR, 'config.json')

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
    """
    Gibt Features zurück die den Status leni_idea haben
    (= Lenis Idee wurde eingetragen, aber noch nicht umgesetzt).
    """
    return [f for f in features if f.get('status') == 'leni_idea']


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    mode_push  = '--push'  in sys.argv
    mode_check = '--check' in sys.argv

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
    print(f'  -> Für Leni sichtbar: {len(visible_items)} Features')
    print(f'  -> Ausgeblendet (technisch): {len(skipped)} Features')

    # CFG Info
    partner_cfg = cfg.get('partner_view', {})
    pw_kai  = partner_cfg.get('partner_pw_kai',  'KaiAdmin2026 (Standard!)')
    pw_leni = partner_cfg.get('partner_pw_leni', 'HalloLeni2026 (Standard!)')
    ntfy_kai = cfg.get('ntfy', {}).get('topic_name', '(nicht konfiguriert)')
    print(f'  -> Passwort Kai:  {pw_kai}')
    print(f'  -> Passwort Leni: {pw_leni}')
    print(f'  -> ntfy Kai:      {ntfy_kai}')

    # Status-Zusammenfassung
    status_counts = {}
    for item in visible_items:
        s = item['status']
        status_counts[s] = status_counts.get(s, 0) + 1
    for s, cnt in sorted(status_counts.items()):
        label = {'done':'Eingebaut','partial':'Teilweise','planned':'Geplant',
                 'leni_idea':'Lenis Ideen','leni_done':'Lenis Ideen umgesetzt'}.get(s, s)
        print(f'     {label}: {cnt}')

    # Leni-Ideen Check
    pending_leni = check_leni_feedback_pending(features)
    if pending_leni:
        print(f'\n  >> {len(pending_leni)} offene Leni-Idee(n) in der Registry:')
        for f in pending_leni:
            print(f'     [{f["id"]}] {f.get("leni_name", f.get("name", "?"))}')

    if mode_check:
        print('\n  OK Check abgeschlossen (kein Schreiben).')
        return

    # HTML aktualisieren
    try:
        new_html, changed = update_html(features_js, cfg_js, today_str)
    except (FileNotFoundError, ValueError) as e:
        print(f'  FEHLER beim HTML-Update: {e}')
        sys.exit(1)

    if changed:
        write_html(new_html)
        print(f'\n  OK partner_view.html aktualisiert -> {HTML_PATH}')
    else:
        print(f'\n  OK partner_view.html ist bereits aktuell (kein Schreiben nötig)')

    # GitHub Push
    if mode_push:
        print('\n  Pushe zu GitHub Pages...')
        if push_to_github(cfg):
            print('  OK Fertig!')
        else:
            print('  FEHLER Push fehlgeschlagen -- bitte Konfiguration pruefen.')
            sys.exit(1)
    else:
        print()
        repo_dir = cfg.get('partner_github_repo_dir', '')
        if repo_dir:
            print('  -> Zum Deployen: python generate_partner_view.py --push')
        else:
            print('  -> GitHub-Konfiguration fehlt noch (partner_github_repo_dir in config.json)')
        print()


if __name__ == '__main__':
    main()
