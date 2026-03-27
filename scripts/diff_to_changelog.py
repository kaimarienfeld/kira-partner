#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diff_to_changelog.py — Automatisches Atomares Mikro-Logging aus git diff
=========================================================================
Erzeugt EINEN change_log.jsonl-Eintrag pro atomarer Änderung:
  - Jede CSS-Property (color, font-size, border-radius ...) = eigener Eintrag
  - Jede Python-Funktion = eigener Eintrag
  - Jede JS-Funktion = eigener Eintrag
  - Jedes HTML-Element / Attribut = eigener Eintrag
  - Jede Farbe, Schriftart, Abstandsänderung = eigener Eintrag
  - Kein Zusammenfassen, kein Gruppieren

Usage:
    python diff_to_changelog.py              # analysiert git diff HEAD
    python diff_to_changelog.py --staged     # git diff --cached (vor Commit)
    python diff_to_changelog.py --dry-run    # nur anzeigen, nicht schreiben
    python diff_to_changelog.py --session X  # Session-ID überschreiben
    python diff_to_changelog.py --since HASH # diff gegen bestimmten Commit

Als git pre-commit hook eingebunden in .git/hooks/pre-commit.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR   = Path(__file__).parent
MEMORY_DIR    = SCRIPTS_DIR.parent
CHANGE_LOG    = MEMORY_DIR / "change_log.jsonl"
HANDOFF_FILE  = MEMORY_DIR / "session_handoff.json"
MAX_ENTRIES   = 1000  # Sicherheitslimit pro Lauf

# ── Session-ID ermitteln ──────────────────────────────────────────────────────

def get_session_id(override: str = "") -> str:
    if override:
        return override
    try:
        data = json.loads(HANDOFF_FILE.read_text(encoding="utf-8"))
        sid = data.get("last_session", "")
        if sid:
            return sid
    except Exception:
        pass
    return "session-" + datetime.now().strftime("%Y-%m-%d") + "-auto"


# ── git diff ausführen ────────────────────────────────────────────────────────

def get_diff(staged: bool = False, since: str = "") -> str:
    try:
        if staged:
            cmd = ["git", "diff", "--cached", "-U5"]
        elif since:
            cmd = ["git", "diff", since, "HEAD", "-U5"]
        else:
            cmd = ["git", "diff", "HEAD", "-U5"]
        result = subprocess.run(cmd, capture_output=True,
                                cwd=str(MEMORY_DIR))
        return result.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[diff_to_changelog] git diff Fehler: {e}", file=sys.stderr)
        return ""


# ── Dateiname → modul ────────────────────────────────────────────────────────

def file_to_modul(filepath: str) -> str:
    name = Path(filepath).stem
    modul_map = {
        "server":        "server",
        "kira_llm":      "kira_llm",
        "runtime_log":   "runtime_log",
        "activity_log":  "activity_log",
        "change_log":    "change_log",
        "mail_monitor":  "mail_monitor",
        "daily_check":   "daily_check",
        "task_manager":  "task_manager",
        "angebote_tracker": "angebote",
        "llm_classifier": "llm_classifier",
    }
    return modul_map.get(name, name)


def file_to_scope(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    scope_map = {".py": "python", ".js": "javascript", ".ts": "typescript",
                 ".html": "html", ".css": "css", ".json": "config",
                 ".md": "docs", ".jsonl": "log"}
    return scope_map.get(ext, "code")


# ── CSS-Erkennung ─────────────────────────────────────────────────────────────

CSS_SELECTOR_RE   = re.compile(r'^[\s]*([.#\[\w][^{]*)\{')
CSS_PROPERTY_RE   = re.compile(r'^[\s]*([\w-]+)\s*:\s*(.+?)\s*;?\s*$')
CSS_COLOR_RE      = re.compile(r'#([0-9a-fA-F]{3,8})\b|rgba?\([^)]+\)|hsla?\([^)]+\)')
CSS_FONT_PROPS    = {"font-family", "font-size", "font-weight", "font-style",
                     "font-variant", "letter-spacing", "line-height", "text-transform",
                     "text-decoration", "text-align"}
CSS_LAYOUT_PROPS  = {"display", "flex", "flex-direction", "align-items",
                     "justify-content", "grid", "grid-template", "position",
                     "top", "left", "right", "bottom", "float", "z-index",
                     "width", "height", "min-width", "max-width", "min-height",
                     "max-height", "overflow", "white-space"}
CSS_SPACING_PROPS = {"margin", "margin-top", "margin-bottom", "margin-left",
                     "margin-right", "padding", "padding-top", "padding-bottom",
                     "padding-left", "padding-right", "gap", "row-gap",
                     "column-gap", "border-spacing"}
CSS_VISUAL_PROPS  = {"background", "background-color", "background-image",
                     "border", "border-radius", "border-top", "border-bottom",
                     "border-left", "border-right", "box-shadow", "opacity",
                     "color", "cursor", "transition", "animation",
                     "outline", "transform"}


def classify_css_property(prop: str) -> str:
    p = prop.lower().strip()
    if p in CSS_FONT_PROPS:        return "css_typography_changed"
    if p in CSS_SPACING_PROPS:     return "css_spacing_changed"
    if p in CSS_LAYOUT_PROPS:      return "css_layout_changed"
    if p in CSS_VISUAL_PROPS:      return "css_visual_changed"
    if "color" in p:               return "css_color_changed"
    return "css_property_changed"


def extract_css_color_hint(value: str) -> str:
    m = CSS_COLOR_RE.search(value)
    return f" [{m.group(0)}]" if m else ""


# ── HTML-Erkennung ────────────────────────────────────────────────────────────

HTML_TAG_OPEN_RE  = re.compile(r'<(\w[\w-]*)((?:\s+[\w:-]+(?:\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]*))?)*)\s*/?>', re.DOTALL)
HTML_ATTR_RE      = re.compile(r'([\w:-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+))')
HTML_ATTR_BOOL_RE = re.compile(r'\b(disabled|checked|readonly|required|hidden|selected|multiple|autofocus)\b')


def parse_html_element(tag: str, attrs_str: str) -> dict:
    attrs = {}
    for m in HTML_ATTR_RE.finditer(attrs_str):
        key = m.group(1)
        val = m.group(2) or m.group(3) or m.group(4) or ""
        attrs[key] = val
    for m in HTML_ATTR_BOOL_RE.finditer(attrs_str):
        attrs[m.group(1)] = True
    return {"tag": tag, "attrs": attrs}


def html_element_summary(tag: str, attrs: dict) -> str:
    parts = [f"<{tag}"]
    if "id" in attrs:
        parts.append(f"id={attrs['id']}")
    if "class" in attrs:
        parts.append(f"class={attrs['class']}")
    if "style" in attrs:
        style_short = attrs["style"][:60] + ("…" if len(attrs["style"]) > 60 else "")
        parts.append(f"style={style_short}")
    for k in ("type", "name", "value", "href", "src", "onclick", "data-tab"):
        if k in attrs:
            v = str(attrs[k])
            parts.append(f"{k}={v[:40]}")
    for k in ("disabled", "checked", "readonly", "required", "hidden"):
        if attrs.get(k) is True:
            parts.append(k)
    return " ".join(parts) + ">"


# ── Python-Erkennung ──────────────────────────────────────────────────────────

PY_FUNC_RE    = re.compile(r'^([ \t]*)def\s+(\w+)\s*\(([^)]*)\)')
PY_CLASS_RE   = re.compile(r'^([ \t]*)class\s+(\w+)\s*(?:\(([^)]*)\))?')
PY_IMPORT_RE  = re.compile(r'^(?:from\s+([\w.]+)\s+import\s+(.+)|import\s+(.+))')
PY_DECORATOR_RE = re.compile(r'^([ \t]*)@(\w[\w.]*)')
PY_ASSIGN_RE  = re.compile(r'^([ \t]*)(\w+)\s*=\s*(.{0,80})')
PY_RETURN_RE  = re.compile(r'^([ \t]*)return\s+(.{0,80})')
PY_RAISE_RE   = re.compile(r'^([ \t]*)raise\s+(\w+)')


# ── JS-Erkennung ─────────────────────────────────────────────────────────────

JS_FUNC_RE    = re.compile(r'^([ \t]*)(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)')
JS_ARROW_RE   = re.compile(r'^([ \t]*)(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>')
JS_METHOD_RE  = re.compile(r'^([ \t]*)(\w+)\s*:\s*(?:async\s+)?function\s*\(([^)]*)\)')
JS_CONST_RE   = re.compile(r'^([ \t]*)(?:const|let|var)\s+(\w+)\s*=\s*(.{0,80})')
JS_FETCH_RE   = re.compile(r"fetch\(['\"]([^'\"]+)['\"]")
JS_EVENT_RE   = re.compile(r"addEventListener\(['\"](\w+)['\"]")
JS_RTLOG_RE   = re.compile(r"_rtlog\(['\"](\w+)['\"],\s*['\"](\w+)['\"],\s*['\"]([^'\"]*)['\"]")


# ── Inline-Style-Erkennung ────────────────────────────────────────────────────

INLINE_STYLE_RE = re.compile(r'style\s*=\s*["\']([^"\']+)["\']')
INLINE_PROP_RE  = re.compile(r'([\w-]+)\s*:\s*([^;]+)')


# ── Kontext-Tracking ──────────────────────────────────────────────────────────

class LineContext:
    """Verfolgt den aktuellen Kontext beim Parsen (CSS-Selektor, Funktion etc.)"""
    def __init__(self):
        self.reset()

    def reset(self):
        self.css_selector  = None   # aktueller CSS-Selektor
        self.py_func       = None   # aktuelle Python-Funktion
        self.py_class      = None   # aktuelle Python-Klasse
        self.js_func       = None   # aktuelle JS-Funktion
        self.brace_depth   = 0      # CSS-Klammer-Tiefe
        self.indent_level  = 0      # Python-Einrückungstiefe

    def update_with_context_line(self, line: str):
        """Context-Zeile (nicht verändert, nur zur Kontext-Erkennung)"""
        stripped = line.strip()

        # CSS-Selektor
        m = CSS_SELECTOR_RE.match(stripped)
        if m and not stripped.startswith("//") and not stripped.startswith("#"):
            self.css_selector = m.group(1).strip()
            self.brace_depth += 1
            return
        if "{" in stripped:
            self.brace_depth += stripped.count("{")
        if "}" in stripped:
            self.brace_depth -= stripped.count("}")
            if self.brace_depth <= 0:
                self.brace_depth = 0
                self.css_selector = None

        # Python-Funktion
        m = PY_FUNC_RE.match(line)
        if m:
            self.py_func = m.group(2)
            return
        m = PY_CLASS_RE.match(line)
        if m:
            self.py_class = m.group(2)
            return

        # JS-Funktion
        m = JS_FUNC_RE.match(line)
        if m:
            self.js_func = m.group(2)
            return
        m = JS_ARROW_RE.match(line)
        if m:
            self.js_func = m.group(2)
            return


# ── Haupt-Parser ──────────────────────────────────────────────────────────────

def parse_diff(diff_text: str, session_id: str, dry_run: bool = False) -> list:
    """Parst git diff-Text und gibt Liste atomarer Einträge zurück."""
    entries = []
    current_file     = ""
    current_file_b   = ""
    in_hunk          = False
    context          = LineContext()
    added_line_num   = 0
    hunk_line_num    = 0

    lines = diff_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # ── Datei-Header ──────────────────────────────────────────────────────
        if line.startswith("--- "):
            context.reset()
            i += 1
            continue
        if line.startswith("+++ "):
            current_file_b = line[4:].strip()
            if current_file_b.startswith("b/"):
                current_file_b = current_file_b[2:]
            current_file = current_file_b
            in_hunk = False
            context.reset()
            i += 1
            continue

        # ── Hunk-Header ───────────────────────────────────────────────────────
        if line.startswith("@@"):
            in_hunk = True
            m = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)', line)
            if m:
                hunk_line_num = int(m.group(1))
                added_line_num = hunk_line_num
            i += 1
            continue

        if not in_hunk:
            i += 1
            continue

        # ── Context-Zeile (nicht verändert) ──────────────────────────────────
        if line.startswith(" "):
            context.update_with_context_line(line[1:])
            added_line_num += 1
            i += 1
            continue

        # ── Entfernte Zeile ───────────────────────────────────────────────────
        if line.startswith("-"):
            # nur für Status-Before merken, kein Eintrag
            i += 1
            continue

        # ── Hinzugefügte Zeile ────────────────────────────────────────────────
        if line.startswith("+"):
            content = line[1:]
            stripped = content.strip()

            # Skip leere Zeilen und reine Kommentare
            if not stripped:
                added_line_num += 1
                i += 1
                continue

            modul   = file_to_modul(current_file)
            scope   = file_to_scope(current_file)
            loc     = f"{current_file}:{added_line_num}"
            new_entries = analyze_added_line(
                content, stripped, current_file, modul, scope, loc,
                context, session_id, added_line_num
            )
            entries.extend(new_entries)

            # Kontext auch für spätere Zeilen aktualisieren
            context.update_with_context_line(content)
            added_line_num += 1

            if len(entries) >= MAX_ENTRIES:
                entries.append(_make_entry(
                    session_id, "auto-limit", modul, "limit_reached",
                    f"Limit von {MAX_ENTRIES} Einträgen erreicht — Rest nicht geloggt",
                    [current_file], loc, scope, [], "", "partial"
                ))
                return entries
            i += 1
            continue

        added_line_num += 1
        i += 1

    return entries


# ── Atomare Analyse einer hinzugefügten Zeile ─────────────────────────────────

def analyze_added_line(
    content: str, stripped: str,
    filepath: str, modul: str, scope: str, loc: str,
    ctx: LineContext, session_id: str, line_num: int
) -> list:
    """Analysiert eine hinzugefügte Zeile und gibt 0..N atomare Einträge zurück."""
    results = []
    ext = Path(filepath).suffix.lower()

    # ══════════════════════════════════════════════════════════════════════════
    # 1. CSS-Properties (auch inline in Python-Strings / HTML)
    # ══════════════════════════════════════════════════════════════════════════

    # Inline style="..." — jede Property einzeln
    for m_style in INLINE_STYLE_RE.finditer(stripped):
        style_val = m_style.group(1)
        for m_prop in INLINE_PROP_RE.finditer(style_val):
            prop  = m_prop.group(1).strip()
            value = m_prop.group(2).strip()
            if not prop or not value:
                continue
            action  = classify_css_property(prop)
            color_h = extract_css_color_hint(value)
            tag_hint = ""
            # Versuche umgebenden Tag zu finden
            m_tag = re.search(r'<(\w[\w-]*)', stripped)
            if m_tag:
                tag_hint = f" | Tag: <{m_tag.group(1)}>"
            results.append(_make_entry(
                session_id, "auto-diff", modul, action,
                f"inline style {prop}: {value[:60]}{color_h}",
                [filepath], loc, "css",
                [f"Inline-Style in {filepath}{tag_hint}",
                 f"Eigenschaft: {prop}",
                 f"Wert: {value}",
                 f"Kontext: {ctx.css_selector or ctx.py_func or ctx.js_func or 'global'}"],
            ))

    # Reine CSS-Property-Zeile (auch innerhalb Python-Strings, NICHT in .md)
    m_prop = CSS_PROPERTY_RE.match(stripped)
    if m_prop and ext not in (".md", ".txt", ".rst") \
            and not stripped.startswith("#") and not stripped.startswith("//"):
        prop  = m_prop.group(1).strip()
        value = m_prop.group(2).strip().rstrip(";,\"'\\").strip()
        if prop and value and len(prop) < 50:
            action  = classify_css_property(prop)
            color_h = extract_css_color_hint(value)
            sel_hint = f" | Selektor: {ctx.css_selector}" if ctx.css_selector else ""
            results.append(_make_entry(
                session_id, "auto-diff", modul, action,
                f"{prop}: {value[:60]}{color_h}{sel_hint}",
                [filepath], loc, "css",
                [f"Datei: {filepath}",
                 f"CSS-Eigenschaft: {prop}",
                 f"Wert: {value}",
                 f"Selektor: {ctx.css_selector or '(unbekannt)'}",
                 f"Kontext-Funktion: {ctx.py_func or ctx.js_func or 'global'}"],
            ))
            return results  # CSS-Property ist atomar, kein weiterer Check nötig

    # CSS-Selektor-Definition (nicht JS-Funktion, nicht Kontrollfluss, nicht fetch/if/for)
    m_sel = CSS_SELECTOR_RE.match(stripped)
    if m_sel and not stripped.startswith("//") and ext not in (".md", ".txt"):
        sel = m_sel.group(1).strip()
        _js_keywords = ("if", "for", "while", "switch", "try", "else", "function",
                        "fetch(", "return", "const ", "let ", "var ", "class ",
                        "async ", "export ", "import ", ".then(", ".catch(")
        _is_js = any(sel.startswith(kw) or sel.startswith("." + kw) for kw in _js_keywords)
        _is_js = _is_js or bool(re.match(r'^[\w$]+\s*\(', sel))  # funcName(
        if sel and not _is_js:
            results.append(_make_entry(
                session_id, "auto-diff", modul, "css_selector_added",
                f"CSS-Selektor: {sel[:80]}",
                [filepath], loc, "css",
                [f"Neuer/geänderter CSS-Block",
                 f"Selektor: {sel}",
                 f"Datei: {filepath}"],
            ))
            return results

    # ══════════════════════════════════════════════════════════════════════════
    # 2. Python-Strukturen
    # ══════════════════════════════════════════════════════════════════════════

    if ext == ".py" or (ext not in (".css", ".html")):

        # Python-Funktion
        m_func = PY_FUNC_RE.match(content)
        if m_func:
            name   = m_func.group(2)
            params = m_func.group(3).strip()
            is_new = True  # vereinfacht — git diff kann das nicht sicher sagen
            in_cls = f" (Klasse: {ctx.py_class})" if ctx.py_class else ""
            results.append(_make_entry(
                session_id, "auto-diff", modul, "python_function_added",
                f"def {name}({params[:60]}){in_cls}",
                [filepath], loc, "python",
                [f"Python-Funktion: {name}",
                 f"Parameter: ({params})",
                 f"Datei: {filepath}",
                 f"Klasse: {ctx.py_class or 'Modul-Level'}",
                 f"Einrückung: {len(m_func.group(1))} Leerzeichen"],
            ))
            return results

        # Python-Klasse
        m_cls = PY_CLASS_RE.match(content)
        if m_cls:
            name    = m_cls.group(2)
            parents = m_cls.group(3) or ""
            results.append(_make_entry(
                session_id, "auto-diff", modul, "python_class_added",
                f"class {name}({parents})" if parents else f"class {name}",
                [filepath], loc, "python",
                [f"Python-Klasse: {name}",
                 f"Elternklassen: {parents or 'keine'}",
                 f"Datei: {filepath}"],
            ))
            return results

        # Python-Import
        m_imp = PY_IMPORT_RE.match(stripped)
        if m_imp:
            if m_imp.group(1):
                summary = f"from {m_imp.group(1)} import {m_imp.group(2).strip()}"
            else:
                summary = f"import {m_imp.group(3).strip()}"
            results.append(_make_entry(
                session_id, "auto-diff", modul, "import_added",
                summary[:100], [filepath], loc, "python",
                [f"Import: {summary}", f"Datei: {filepath}"],
            ))
            return results

        # Python-Decorator
        m_dec = PY_DECORATOR_RE.match(content)
        if m_dec:
            results.append(_make_entry(
                session_id, "auto-diff", modul, "python_decorator_added",
                f"@{m_dec.group(2)} (in {ctx.py_func or 'Modul-Level'})",
                [filepath], loc, "python",
                [f"Decorator: @{m_dec.group(2)}", f"Datei: {filepath}"],
            ))
            return results

    # ══════════════════════════════════════════════════════════════════════════
    # 3. JavaScript-Strukturen
    # ══════════════════════════════════════════════════════════════════════════

    # JS-Funktion (klassisch)
    m_jsfunc = JS_FUNC_RE.match(content)
    if m_jsfunc:
        name   = m_jsfunc.group(2)
        params = m_jsfunc.group(3).strip()
        results.append(_make_entry(
            session_id, "auto-diff", modul, "js_function_added",
            f"function {name}({params[:60]})",
            [filepath], loc, "javascript",
            [f"JS-Funktion: {name}",
             f"Parameter: ({params})",
             f"Datei: {filepath}",
             f"Kontext: {ctx.js_func or 'global'}"],
        ))
        return results

    # Arrow-Function / Const-Funktion
    m_arrow = JS_ARROW_RE.match(content)
    if m_arrow:
        name   = m_arrow.group(2)
        params = m_arrow.group(3).strip()
        results.append(_make_entry(
            session_id, "auto-diff", modul, "js_function_added",
            f"const {name} = ({params[:60]}) => ...",
            [filepath], loc, "javascript",
            [f"JS Arrow-Funktion: {name}",
             f"Parameter: ({params})",
             f"Datei: {filepath}"],
        ))
        return results

    # _rtlog()-Aufruf
    m_rtlog = JS_RTLOG_RE.search(stripped)
    if m_rtlog:
        results.append(_make_entry(
            session_id, "auto-diff", modul, "logging_call_added",
            f"_rtlog('{m_rtlog.group(1)}', '{m_rtlog.group(2)}', '{m_rtlog.group(3)}')",
            [filepath], loc, "javascript",
            [f"Runtime-Log-Aufruf im Browser",
             f"Typ: {m_rtlog.group(1)} | Action: {m_rtlog.group(2)} | Label: {m_rtlog.group(3)}",
             f"Datei: {filepath}",
             f"JS-Funktion: {ctx.js_func or 'global'}"],
        ))
        return results

    # fetch()-Aufruf → API-Endpunkt-Nutzung
    m_fetch = JS_FETCH_RE.search(stripped)
    if m_fetch:
        endpoint = m_fetch.group(1)
        method_m = re.search(r"method\s*:\s*['\"](\w+)['\"]", stripped)
        method   = method_m.group(1) if method_m else "GET"
        results.append(_make_entry(
            session_id, "auto-diff", modul, "api_call_added",
            f"fetch {method} {endpoint}",
            [filepath], loc, "javascript",
            [f"API-Aufruf: {method} {endpoint}",
             f"JS-Funktion: {ctx.js_func or 'global'}",
             f"Datei: {filepath}"],
        ))
        return results

    # JS const/let/var
    m_const = JS_CONST_RE.match(content)
    if m_const and "{" not in m_const.group(3) and "=>" not in m_const.group(3):
        name  = m_const.group(2)
        value = m_const.group(3).strip().rstrip(",;").strip()
        results.append(_make_entry(
            session_id, "auto-diff", modul, "js_variable_added",
            f"const/let {name} = {value[:60]}",
            [filepath], loc, "javascript",
            [f"JS-Variable: {name}",
             f"Wert: {value}",
             f"Datei: {filepath}",
             f"Funktion: {ctx.js_func or 'global'}"],
        ))
        return results

    # ══════════════════════════════════════════════════════════════════════════
    # 4. HTML-Elemente
    # ══════════════════════════════════════════════════════════════════════════

    # HTML-Tags mit Attributen
    for m_tag in HTML_TAG_OPEN_RE.finditer(stripped):
        tag      = m_tag.group(1).lower()
        attrs_s  = m_tag.group(2)
        elem     = parse_html_element(tag, attrs_s)
        attrs    = elem["attrs"]

        # Jedes wichtige Attribut einzeln loggen
        for attr_name in ("id", "class", "style", "type", "name", "value",
                          "href", "src", "onclick", "data-tab", "data-type",
                          "placeholder", "title", "aria-label"):
            if attr_name in attrs:
                val = str(attrs[attr_name])
                results.append(_make_entry(
                    session_id, "auto-diff", modul,
                    "html_attribute_added" if attr_name not in ("class", "style")
                    else "html_class_added" if attr_name == "class"
                    else "html_inline_style_added",
                    f"<{tag}> {attr_name}=\"{val[:70]}\"",
                    [filepath], loc, "html",
                    [f"HTML-Element: <{tag}>",
                     f"Attribut: {attr_name}",
                     f"Wert: {val}",
                     f"Kontext: {ctx.py_func or ctx.js_func or 'template'}"],
                ))

        # Boolesche Attribute
        for ba in ("disabled", "checked", "readonly", "required", "hidden"):
            if attrs.get(ba) is True:
                results.append(_make_entry(
                    session_id, "auto-diff", modul, "html_attribute_added",
                    f"<{tag}> {ba} (bool)",
                    [filepath], loc, "html",
                    [f"HTML-Element: <{tag}>",
                     f"Bool-Attribut: {ba} gesetzt",
                     f"Kontext: {ctx.py_func or ctx.js_func or 'template'}"],
                ))

        if results:
            return results

        # Tag ohne relevante Attribute — einfachen Eintrag
        results.append(_make_entry(
            session_id, "auto-diff", modul, "html_element_added",
            html_element_summary(tag, attrs)[:100],
            [filepath], loc, "html",
            [f"HTML-Tag: <{tag}>",
             f"Datei: {filepath}",
             f"Kontext: {ctx.py_func or ctx.js_func or 'template'}"],
        ))
        return results

    # ══════════════════════════════════════════════════════════════════════════
    # 5. API-Endpunkte (Python-Route-Pattern)
    # ══════════════════════════════════════════════════════════════════════════

    m_route = re.search(r"['\"]/(api/[^'\"]+)['\"]", stripped)
    if m_route:
        endpoint = m_route.group(1)
        if "path ==" in stripped or "self.path ==" in stripped:
            method_m = re.search(r"(GET|POST|PUT|DELETE|PATCH)", stripped)
            method   = method_m.group(1) if method_m else "?"
            results.append(_make_entry(
                session_id, "auto-diff", modul, "api_endpoint_added",
                f"{method} /{endpoint}",
                [filepath], loc, "python",
                [f"API-Endpunkt: {method} /{endpoint}",
                 f"Datei: {filepath}",
                 f"Funktion: {ctx.py_func or 'DashboardHandler'}"],
            ))
            return results

    # ══════════════════════════════════════════════════════════════════════════
    # 6. Config/JSON-Werte
    # ══════════════════════════════════════════════════════════════════════════

    if ext == ".json":
        m_kv = re.match(r'^\s*"([\w_-]+)"\s*:\s*(.{1,100})', stripped)
        if m_kv:
            key = m_kv.group(1)
            val = m_kv.group(2).rstrip(",").strip()
            results.append(_make_entry(
                session_id, "auto-diff", modul, "config_value_changed",
                f'"{key}": {val[:60]}',
                [filepath], loc, "config",
                [f"Config-Key: {key}",
                 f"Neuer Wert: {val}",
                 f"Datei: {filepath}"],
            ))
            return results

    # ══════════════════════════════════════════════════════════════════════════
    # 7. Farb-/Größen-Werte in beliebigen Zeilen
    # ══════════════════════════════════════════════════════════════════════════

    color_m = CSS_COLOR_RE.search(stripped)
    if color_m and any(kw in stripped.lower() for kw in
                       ["color", "background", "border", "shadow", "fill", "stroke"]):
        color = color_m.group(0)
        results.append(_make_entry(
            session_id, "auto-diff", modul, "css_color_changed",
            f"Farbwert {color} in: {stripped[:80]}",
            [filepath], loc, scope,
            [f"Farbwert: {color}",
             f"Kontext: {stripped[:120]}",
             f"Selektor/Funktion: {ctx.css_selector or ctx.py_func or ctx.js_func or 'unbekannt'}"],
        ))
        return results

    # ══════════════════════════════════════════════════════════════════════════
    # 8. Fallback — generischer Eintrag für unerkannte Zeilen
    #    (nur wenn Zeile inhaltlich relevant und nicht rein strukturell)
    # ══════════════════════════════════════════════════════════════════════════

    skip_patterns = [
        r"^\s*[{}\[\]()]\s*$",           # nur Klammern
        r"^\s*#\s*$",                     # leerer Kommentar
        r"^\s*//\s*$",                    # leerer JS-Kommentar
        r"^\s*pass\s*$",                  # Python pass
        r"^\s*\.\.\.\s*$",               # Ellipsis
    ]
    for pat in skip_patterns:
        if re.match(pat, stripped):
            return results

    if len(stripped) > 5:
        ctx_hint = (ctx.css_selector or ctx.py_func or ctx.js_func or "global")
        results.append(_make_entry(
            session_id, "auto-diff", modul, "code_line_added",
            f"{stripped[:90]}",
            [filepath], loc, scope,
            [f"Datei: {filepath}:{line_num}",
             f"Inhalt: {stripped[:200]}",
             f"Kontext: {ctx_hint}"],
        ))

    return results


# ── Entry-Builder ─────────────────────────────────────────────────────────────

def _make_entry(session_id, feature_id, modul, action, summary,
                files, location, scope, details, status_before="",
                result="success"):
    return {
        "timestamp":     datetime.now().isoformat(timespec="seconds"),
        "session_id":    session_id,
        "feature_id":    feature_id,
        "modul":         modul,
        "action":        action,
        "scope":         scope,
        "files":         files,
        "location":      location,
        "summary":       summary,
        "details":       details if isinstance(details, list) else [details],
        "result":        result,
        "status_before": status_before,
        "status_after":  "done",
        "test_status":   "not_tested",
        "follow_up":     [],
        "related_todos": [],
    }


# ── Schreiben ─────────────────────────────────────────────────────────────────

def write_entries(entries: list, dry_run: bool = False) -> int:
    if dry_run:
        for e in entries:
            print(f"[DRY] [{e['action']:30s}] {e['summary'][:80]}")
            if e.get("details"):
                for d in e["details"][:2]:
                    print(f"        {d}")
        return len(entries)

    try:
        with open(CHANGE_LOG, "a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n")
        return len(entries)
    except Exception as ex:
        print(f"[diff_to_changelog] Schreiben fehlgeschlagen: {ex}", file=sys.stderr)
        return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Atomares Mikro-Logging aus git diff → change_log.jsonl"
    )
    parser.add_argument("--staged",   action="store_true",
                        help="git diff --cached (für pre-commit Hook)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Nur anzeigen, nicht schreiben")
    parser.add_argument("--session",  default="",
                        help="Session-ID überschreiben")
    parser.add_argument("--since",    default="",
                        help="diff gegen diesen Commit-Hash")
    parser.add_argument("--quiet",    action="store_true",
                        help="Keine Ausgabe außer bei Fehlern")
    args = parser.parse_args()

    session_id = get_session_id(args.session)
    diff_text  = get_diff(staged=args.staged, since=args.since)

    if not diff_text or not diff_text.strip():
        if not args.quiet:
            print("[diff_to_changelog] Keine Änderungen gefunden.")
        return 0

    entries = parse_diff(diff_text, session_id, dry_run=args.dry_run)

    if not entries:
        if not args.quiet:
            print("[diff_to_changelog] Keine loggbaren Änderungen erkannt.")
        return 0

    written = write_entries(entries, dry_run=args.dry_run)

    if not args.quiet:
        label = "[DRY-RUN]" if args.dry_run else "[GESCHRIEBEN]"
        print(f"[diff_to_changelog] {label} {written} atomare Einträge → change_log.jsonl")

    return 0


if __name__ == "__main__":
    sys.exit(main())
