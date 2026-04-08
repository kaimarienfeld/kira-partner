#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kira_llm.py — Kira's Multi-LLM-Gehirn
Unterstützt: Anthropic, OpenAI, OpenRouter, Ollama, Custom (OpenAI-kompatibel).
Automatischer Fallback bei Ausfall oder leerem Guthaben.
Einheitlicher System-Prompt mit allen rauMKult-Geschäftsdaten für JEDES Modell.
"""
import json, sqlite3, os, uuid, time, threading, random
from pathlib import Path
from datetime import datetime, date
try:
    from activity_log import log as _alog
except Exception:
    def _alog(*a, **k): pass

try:
    from runtime_log import elog as _elog
except Exception:
    def _elog(*a, **k): return ""

SCRIPTS_DIR   = Path(__file__).parent
KNOWLEDGE_DIR = SCRIPTS_DIR.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"
KUNDEN_DB     = KNOWLEDGE_DIR / "kunden.db"
DETAIL_DB     = KNOWLEDGE_DIR / "rechnungen_detail.db"
MAIL_INDEX_DB = KNOWLEDGE_DIR / "mail_index.db"
SECRETS_FILE  = SCRIPTS_DIR / "secrets.json"
CONFIG_FILE   = SCRIPTS_DIR / "config.json"

# ── Provider-Registry ─────────────────────────────────────────────────────────
PROVIDER_TYPES = {
    "anthropic": {
        "name": "Anthropic (Claude)",
        "models": [
            ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
            ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
            ("claude-opus-4-6", "Claude Opus 4.6"),
        ],
        "default_model": "claude-sonnet-4-6",
        "pip_package": "anthropic",
        "supports_tools": True,
        "needs_key": True,
    },
    "openai": {
        "name": "OpenAI",
        "models": [
            ("gpt-4o", "GPT-4o"),
            ("gpt-4o-mini", "GPT-4o Mini"),
            ("gpt-4.1", "GPT-4.1"),
            ("o3-mini", "o3-mini"),
        ],
        "default_model": "gpt-4o",
        "pip_package": "openai",
        "supports_tools": True,
        "needs_key": True,
    },
    "openrouter": {
        "name": "OpenRouter",
        "models": [
            ("anthropic/claude-sonnet-4", "Claude Sonnet 4"),
            ("openai/gpt-4o", "GPT-4o"),
            ("google/gemini-2.5-pro-preview", "Gemini 2.5 Pro"),
            ("deepseek/deepseek-r1", "DeepSeek R1"),
            ("meta-llama/llama-4-maverick", "Llama 4 Maverick"),
        ],
        "default_model": "anthropic/claude-sonnet-4",
        "pip_package": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "supports_tools": True,
        "needs_key": True,
    },
    "ollama": {
        "name": "Ollama (Lokal)",
        "models": [
            ("llama3.1", "Llama 3.1"),
            ("mistral", "Mistral"),
            ("qwen2.5", "Qwen 2.5"),
            ("deepseek-r1", "DeepSeek R1"),
        ],
        "default_model": "llama3.1",
        "pip_package": "openai",
        "base_url": "http://localhost:11434/v1",
        "supports_tools": False,
        "needs_key": False,
    },
    "custom": {
        "name": "Benutzerdefiniert (OpenAI-kompatibel)",
        "models": [],
        "default_model": "",
        "pip_package": "openai",
        "supports_tools": True,
        "needs_key": True,
    },
}


class ProviderUnavailableError(Exception):
    """Provider nicht erreichbar — Fallback auf nächsten."""
    pass


class ModelNotFoundError(ProviderUnavailableError):
    """Modell nicht gefunden — Auto-Update wird versucht, Fallback auf nächsten Provider."""
    pass


_MODEL_CACHE: dict = {}      # {provider_id: (timestamp_float, [model_id_strings])}
_MODEL_CACHE_TTL = 86400     # 24 Stunden

# ── Circuit Breaker (Paket 1, session-oo) ─────────────────────────────────────
_CIRCUIT_BREAKER: dict = {}  # {provider_id: {"failures": int, "open_until": float|None, "last_failure": float|None}}
_CB_FAILURE_THRESHOLD = 3    # nach N Fehlern in _CB_FAILURE_WINDOW → Circuit öffnet
_CB_FAILURE_WINDOW    = 60   # Sekunden — ältere Fehler zählen nicht
_CB_OPEN_DURATION     = 300  # Sekunden — Circuit bleibt offen (5 Min)
_CB_LOCK              = threading.Lock()

# ── Rate Limiter (Paket 1, session-oo) ────────────────────────────────────────
_RATE_TIMESTAMPS: list = []  # Rolling-Window der letzten API-Calls (Timestamps)
_RATE_LOCK        = threading.Lock()
_RATE_MAX_DEFAULT = 20       # Max Calls pro 60s (überschreibbar via config.json llm_rate_limit_per_minute)


def _cb_is_open(provider_id: str) -> bool:
    """True wenn Circuit Breaker für diesen Provider gesperrt ist."""
    with _CB_LOCK:
        cb = _CIRCUIT_BREAKER.get(provider_id)
        if not cb:
            return False
        if cb.get("open_until") and time.time() < cb["open_until"]:
            return True
        if cb.get("open_until"):
            _CIRCUIT_BREAKER[provider_id] = {"failures": 0, "open_until": None, "last_failure": None}
        return False


def _cb_record_failure(provider_id: str) -> None:
    """Registriert einen Fehler — öffnet Circuit nach Schwellwert."""
    now = time.time()
    with _CB_LOCK:
        if provider_id not in _CIRCUIT_BREAKER:
            _CIRCUIT_BREAKER[provider_id] = {"failures": 0, "open_until": None, "last_failure": None}
        cb = _CIRCUIT_BREAKER[provider_id]
        if cb.get("last_failure") and now - cb["last_failure"] > _CB_FAILURE_WINDOW:
            cb["failures"] = 0
        cb["failures"] += 1
        cb["last_failure"] = now
        if cb["failures"] >= _CB_FAILURE_THRESHOLD:
            cb["open_until"] = now + _CB_OPEN_DURATION
            try:
                _elog("llm", "circuit_breaker_open",
                      f"Circuit Breaker {provider_id}: {cb['failures']} Fehler → gesperrt für {_CB_OPEN_DURATION}s",
                      modul="kira_llm", source="circuit_breaker", status="warnung")
            except Exception:
                pass


def _rate_check_and_record() -> bool:
    """Prüft Rate Limit. Gibt False zurück wenn über Limit — True wenn OK und Call registriert."""
    now = time.time()
    with _RATE_LOCK:
        global _RATE_TIMESTAMPS
        _RATE_TIMESTAMPS = [t for t in _RATE_TIMESTAMPS if now - t < 60]
        max_calls = _RATE_MAX_DEFAULT
        try:
            cfg = get_config()
            max_calls = cfg.get("llm_rate_limit_per_minute", _RATE_MAX_DEFAULT)
        except Exception:
            pass
        if len(_RATE_TIMESTAMPS) >= max_calls:
            return False
        _RATE_TIMESTAMPS.append(now)
        return True


# ── Config & Secrets ──────────────────────────────────────────────────────────
def _load_secrets():
    try:
        return json.loads(SECRETS_FILE.read_text('utf-8'))
    except:
        return {}


def _save_secrets(data):
    SECRETS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')


def get_config():
    """Lädt LLM-Konfiguration. Migriert altes Format automatisch."""
    defaults = {
        "internet_recherche": False,
        "geschaeftsdaten_teilen": True,
        "konversationen_speichern": True,
        "max_kontext_items": 50,
        "auto_wissen_extrahieren": True,
    }
    try:
        c = json.loads(CONFIG_FILE.read_text('utf-8'))
        llm = c.get("llm", {})
    except:
        llm = {}

    for k, v in defaults.items():
        if k not in llm:
            llm[k] = v

    # Migration: altes Format (single model) → providers list
    if "providers" not in llm:
        old_model = llm.pop("model", "claude-sonnet-4-20250514")
        llm["providers"] = [{
            "id": "default-anthropic",
            "typ": "anthropic",
            "name": "Claude (Anthropic)",
            "model": old_model,
            "aktiv": True,
            "prioritaet": 1,
        }]

    return llm


def get_providers():
    """Gibt aktive Provider sortiert nach Kosten zurück (günstigste zuerst)."""
    config = get_config()
    providers = config.get("providers", [])
    active = [p for p in providers if p.get("aktiv", True)]
    active.sort(key=lambda p: _provider_cost_rank(p))
    return active


def get_all_providers():
    """Gibt ALLE Provider zurück (auch inaktive), sortiert nach Kosten."""
    config = get_config()
    providers = config.get("providers", [])
    providers.sort(key=lambda p: _provider_cost_rank(p))
    return providers


# Kosten-Ranking: niedrigere Zahl = günstiger = wird bevorzugt
_COST_RANK = {
    "ollama": 0,      # Lokal = kostenlos
    "custom": 1,      # Eigener Server = sehr günstig
    "openai": 10,     # GPT-4o-mini = günstig
    "openrouter": 11, # OpenRouter = günstig
    "anthropic": 20,  # Claude = teurer
}

def _provider_cost_rank(provider: dict) -> int:
    """Sortier-Schlüssel: günstigster Provider zuerst."""
    typ = provider.get("typ", "")
    return _COST_RANK.get(typ, 50)


# Günstigstes Modell je Provider-Typ für einfache Aufgaben
_BUDGET_MODELS = {
    "anthropic":  "claude-haiku-4-5-20251001",
    "openai":     "gpt-4o-mini",
    "openrouter": "openai/gpt-4o-mini",
}

# Leistungsfähiges Modell je Provider-Typ für komplexe Aufgaben
_CAPABLE_MODELS = {
    "anthropic":  "claude-sonnet-4-6",
    "openai":     "gpt-4o",
    "openrouter": "anthropic/claude-sonnet-4-6",
}


def get_provider_for_task(task_type: str = "classify") -> tuple:
    """Wählt den besten Provider + Modell für eine Aufgabe.

    task_type:
      - "classify"  → günstigstes Modell (GPT-4o-mini, Haiku)
      - "extract"   → günstigstes Modell (Wissen-Extraktion, Zusammenfassungen)
      - "chat"      → leistungsfähiges Modell (Kira-Chat, komplexe Analyse)
      - "generate"  → leistungsfähiges Modell (Antwort-Generierung)

    Returns: (provider_dict_with_model, model_name) oder (None, None)
    """
    providers = get_providers()
    if not providers:
        return None, None

    is_simple = task_type in ("classify", "extract")
    model_map = _BUDGET_MODELS if is_simple else _CAPABLE_MODELS

    for p in providers:
        typ = p.get("typ", "")
        # Für einfache Aufgaben: günstiges Modell erzwingen
        if is_simple and typ in model_map:
            provider = dict(p)
            provider["model"] = model_map[typ]
            return provider, provider["model"]
        elif is_simple and typ in ("ollama", "custom"):
            return p, p.get("model", "?")
        # Für komplexe Aufgaben: leistungsfähiges Modell bevorzugen
        elif not is_simple and typ in model_map:
            provider = dict(p)
            provider["model"] = model_map[typ]
            return provider, provider["model"]
        else:
            return p, p.get("model", "?")

    return providers[0], providers[0].get("model", "?")


def _get_provider_key(provider):
    """Holt den API Key für einen Provider."""
    secrets = _load_secrets()
    pid = provider.get("id", "")
    typ = provider.get("typ", "")

    # 1. Provider-spezifischer Key
    per_provider = secrets.get("provider_keys", {})
    if per_provider.get(pid):
        return per_provider[pid]

    # 2. Typ-basierter Key (Abwärtskompatibilität)
    type_keys = {
        "anthropic": "anthropic_api_key",
        "openai": "openai_api_key",
        "google": "google_api_key",
    }
    if typ in type_keys and secrets.get(type_keys[typ]):
        return secrets[type_keys[typ]]

    # 3. ENV-Variablen
    env_keys = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    if typ in env_keys:
        return os.environ.get(env_keys[typ], "")

    # Ollama braucht keinen Key
    ptype = PROVIDER_TYPES.get(typ, {})
    if not ptype.get("needs_key", True):
        return "not-needed"

    return ""


def save_provider_key(provider_id, api_key):
    """Speichert einen API Key für einen Provider."""
    secrets = _load_secrets()
    if "provider_keys" not in secrets:
        secrets["provider_keys"] = {}
    secrets["provider_keys"][provider_id] = api_key
    _save_secrets(secrets)


def get_api_key():
    """Legacy: Gibt den Key des ersten aktiven Providers zurück."""
    providers = get_providers()
    if providers:
        return _get_provider_key(providers[0])
    return ""


def check_provider_status(provider):
    """Prüft ob ein Provider nutzbar ist (Key vorhanden, Paket installiert)."""
    typ = provider.get("typ", "")
    ptype = PROVIDER_TYPES.get(typ, {})

    # Key prüfen
    if ptype.get("needs_key", True):
        key = _get_provider_key(provider)
        if not key:
            return {"status": "no_key", "message": "Kein API Key"}

    # Paket prüfen
    pkg = ptype.get("pip_package", "")
    if pkg:
        try:
            __import__(pkg)
        except ImportError:
            return {"status": "no_package", "message": f"pip install {pkg}"}

    return {"status": "ok", "message": "Bereit"}


# ── Model-Validierung & Auto-Update ──────────────────────────────────────────
_MODEL_FALLBACK_RANKING = {
    "anthropic":  [
        "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
    ],
    "openai":     [
        "gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3-mini",
    ],
    "openrouter": [
        "anthropic/claude-sonnet-4", "openai/gpt-4o",
        "google/gemini-2.5-pro-preview", "deepseek/deepseek-r1",
        "meta-llama/llama-4-maverick",
    ],
    "ollama":     [],   # dynamisch — alles was lokal läuft
}

_MODEL_VALIDATION_STATE_FILE = KNOWLEDGE_DIR / "model_validation_state.json"


def _send_ntfy_push(title: str, message: str, priority: str = "default"):
    """Sendet eine ntfy Push-Notification basierend auf config.json ntfy-Einstellungen."""
    try:
        cfg = json.loads(CONFIG_FILE.read_text('utf-8'))
        ntfy_cfg = cfg.get("ntfy", {})
        if not ntfy_cfg.get("aktiv"):
            return
        topic = ntfy_cfg.get("topic_name", "")
        server = ntfy_cfg.get("server", "https://ntfy.sh")
        if not topic or topic.startswith("raumkult-dein"):
            return
        import urllib.request
        data = message.encode('utf-8')
        req = urllib.request.Request(f"{server}/{topic}", data=data)
        req.add_header("Title", title)
        req.add_header("Priority", priority)
        req.add_header("Tags", "robot,warning")
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass


def _model_in_list(model_id: str, available: list) -> bool:
    """Prüft ob ein Modell verfügbar ist. Unterstützt Prefix-Match für dated snapshots.

    Beispiel: 'claude-sonnet-4-6' matched 'claude-sonnet-4-6-20250514' (und umgekehrt).
    """
    for m in available:
        if m == model_id:
            return True
        if m.startswith(model_id + "-202"):   # dated snapshot
            return True
        if model_id.startswith(m + "-202"):   # config hat dated, API hat base
            return True
    return False


def _fetch_provider_models(provider) -> list:
    """Holt verfügbare Modelle vom Provider. Ergebnis wird 24h gecacht."""
    typ = provider.get("typ", "")
    pid = provider.get("id", typ)

    # Cache-Prüfung
    cache_entry = _MODEL_CACHE.get(pid)
    if cache_entry:
        ts, models = cache_entry
        if time.time() - ts < _MODEL_CACHE_TTL:
            return models

    models = []
    try:
        key = _get_provider_key(provider)
        ptype = PROVIDER_TYPES.get(typ, {})
        base_url = provider.get("base_url") or ptype.get("base_url", "")
        import urllib.request

        if typ == "anthropic":
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            models = [m["id"] for m in data.get("data", [])]

        elif typ in ("openai", "openrouter", "custom"):
            api_base = (base_url or "https://api.openai.com/v1").rstrip("/")
            req = urllib.request.Request(
                f"{api_base}/models",
                headers={"Authorization": f"Bearer {key}"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            models = [m["id"] for m in data.get("data", [])]

        elif typ == "ollama":
            ol_base = (base_url or "http://localhost:11434").replace("/v1", "").rstrip("/")
            req = urllib.request.Request(f"{ol_base}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]

    except Exception:
        pass

    if models:
        _MODEL_CACHE[pid] = (time.time(), models)

    return models


def _validate_model(provider) -> dict:
    """Prüft ob das konfigurierte Modell des Providers noch verfügbar ist.

    Returns:
        {"valid": bool, "model": str, "available_models": list, "reason": str}
    """
    model = provider.get("model", "")
    typ = provider.get("typ", "")

    if not model:
        return {"valid": False, "model": model, "reason": "Kein Modell konfiguriert"}

    available = _fetch_provider_models(provider)

    if not available:
        # API nicht erreichbar — kein false-positive auslösen
        return {
            "valid": True,
            "model": model,
            "reason": "Provider-API nicht erreichbar — Validierung übersprungen",
            "skipped": True,
        }

    if _model_in_list(model, available):
        return {"valid": True, "model": model, "available_count": len(available)}

    return {
        "valid": False,
        "model": model,
        "available_models": available[:20],   # erste 20 für Übersicht
        "reason": f"'{model}' nicht in Provider-Modellliste ({len(available)} verfügbar)",
    }


def _auto_update_model(provider) -> dict:
    """Wechselt automatisch zum besten verfügbaren Modell und speichert in config.json.

    Returns:
        {"changed": bool, "old_model": str, "new_model": str}
    """
    typ = provider.get("typ", "")
    old_model = provider.get("model", "")
    pid = provider.get("id", "")
    pname = provider.get("name", typ)

    available = _fetch_provider_models(provider)
    if not available:
        return {"changed": False, "old_model": old_model, "new_model": old_model,
                "reason": "Modellliste nicht abrufbar"}

    # Fallback-Ranking durchsuchen
    new_model = None
    for candidate in _MODEL_FALLBACK_RANKING.get(typ, []):
        if _model_in_list(candidate, available):
            new_model = candidate
            break

    # Kein Treffer im Ranking → erstes verfügbares nehmen
    if not new_model and available:
        new_model = available[0]

    if not new_model or new_model == old_model:
        return {"changed": False, "old_model": old_model, "new_model": old_model}

    # config.json aktualisieren
    try:
        c = json.loads(CONFIG_FILE.read_text('utf-8'))
        for p in c.get("llm", {}).get("providers", []):
            if p.get("id") == pid:
                p["model"] = new_model
                break
        CONFIG_FILE.write_text(json.dumps(c, ensure_ascii=False, indent=2), 'utf-8')
    except Exception as e:
        return {"changed": False, "old_model": old_model, "new_model": new_model,
                "error": str(e)}

    # Push + Event-Log
    _send_ntfy_push(
        "⚠ Kira: Modell-Wechsel",
        f"{pname}: {old_model} → {new_model}",
        priority="high",
    )
    _elog("llm", "model_auto_update",
          f"Provider {pid}: {old_model} → {new_model}",
          source="kira_llm", modul="kira", submodul="model_validation",
          status="ok", provider=pid,
          entity_snapshot={"old_model": old_model, "new_model": new_model,
                           "available_count": len(available)})

    return {"changed": True, "old_model": old_model, "new_model": new_model}


def _normalize_model(provider) -> dict:
    """Ersetzt dated Snapshots durch saubere Basis-IDs aus dem Fallback-Ranking.

    Beispiel: 'claude-sonnet-4-6-20250514' → 'claude-sonnet-4-6'
    Wird aufgerufen wenn Modell noch gültig ist, aber eine datierte Version nutzt.
    Returns: {"changed": bool, "old_model": str, "new_model": str}
    """
    model = provider.get("model", "")
    typ = provider.get("typ", "")
    pid = provider.get("id", "")

    # Nur wenn Modell ein dated Snapshot ist (enthält -YYYYMMDD oder -YYYY-MM-DD)
    import re
    if not re.search(r'-20\d{6}(-|$)|-20\d\d-\d\d-\d\d', model):
        return {"changed": False, "old_model": model, "new_model": model}

    for candidate in _MODEL_FALLBACK_RANKING.get(typ, []):
        # candidate ist Basis-ID von model wenn model mit candidate+"-20" beginnt
        if model.startswith(candidate + "-20"):
            try:
                c = json.loads(CONFIG_FILE.read_text('utf-8'))
                for p in c.get("llm", {}).get("providers", []):
                    if p.get("id") == pid:
                        p["model"] = candidate
                        break
                CONFIG_FILE.write_text(json.dumps(c, ensure_ascii=False, indent=2), 'utf-8')
                _elog("llm", "model_normalize",
                      f"Provider {pid}: {model} → {candidate} (Snapshot → Basis-ID)",
                      source="kira_llm", modul="kira", submodul="model_validation",
                      status="ok", provider=pid,
                      entity_snapshot={"old_model": model, "new_model": candidate})
            except Exception:
                return {"changed": False, "old_model": model, "new_model": model}
            return {"changed": True, "old_model": model, "new_model": candidate}

    return {"changed": False, "old_model": model, "new_model": model}


def validate_all_providers() -> dict:
    """Validiert alle aktiven Provider, korrigiert veraltete Modelle automatisch.

    Schreibt Ergebnis nach knowledge/model_validation_state.json (für Dashboard/UI).
    Returns: {provider_id: validation_result_dict}
    """
    results = {}
    for provider in get_providers():
        typ = provider.get("typ", "")
        pid = provider.get("id", typ)

        # Nur Provider mit Key (und erreichbarer API) prüfen
        if PROVIDER_TYPES.get(typ, {}).get("needs_key", True):
            if not _get_provider_key(provider):
                results[pid] = {"status": "no_key", "skipped": True}
                continue

        vr = _validate_model(provider)
        if not vr.get("valid") and not vr.get("skipped"):
            # Modell nicht mehr verfügbar → bestes verfügbares wählen
            update = _auto_update_model(provider)
            vr["auto_update"] = update
        elif vr.get("valid") and not vr.get("skipped"):
            # Modell noch gültig aber evtl. dated Snapshot → auf Basis-ID normalisieren
            norm = _normalize_model(provider)
            if norm.get("changed"):
                vr["normalized"] = norm

        results[pid] = vr

    # Ergebnis persistieren damit server.py es lesen kann
    try:
        state = {
            "timestamp": datetime.now().isoformat(),
            "results": results,
        }
        _MODEL_VALIDATION_STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), 'utf-8'
        )
    except Exception:
        pass

    return results


# ── DB Initialisierung ───────────────────────────────────────────────────────
def init_conversations_db():
    db = sqlite3.connect(str(TASKS_DB))
    db.execute("""CREATE TABLE IF NOT EXISTS kira_konversationen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        rolle TEXT NOT NULL,
        nachricht TEXT,
        tool_calls_json TEXT,
        tool_results_json TEXT,
        provider_used TEXT,
        token_input INTEGER DEFAULT 0,
        token_output INTEGER DEFAULT 0,
        erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE INDEX IF NOT EXISTS idx_kira_konv_session
        ON kira_konversationen(session_id)""")
    # provider_used Spalte nachrüsten falls alt
    try:
        db.execute("SELECT provider_used FROM kira_konversationen LIMIT 1")
    except:
        try:
            db.execute("ALTER TABLE kira_konversationen ADD COLUMN provider_used TEXT")
        except:
            pass
    db.commit()
    db.close()


# ── System-Prompt Builder ────────────────────────────────────────────────────
def build_system_prompt(config=None):
    config = config or get_config()
    today = date.today().isoformat()
    # kira_cfg kommt aus config.json["kira"] (Top-Level), NICHT aus dem llm-Sub-Dict
    try:
        _full_cfg = json.loads(CONFIG_FILE.read_text('utf-8'))
        kira_cfg = _full_cfg.get("kira", {})
    except Exception:
        kira_cfg = {}
    kira_name = (kira_cfg.get("name") or "Kira").strip() or "Kira"

    # Persönlichkeit-Stil
    _stil_map = {
        "professionell": "Professionell und sachlich — pr\u00e4zise Informationen, knappe Empfehlungen, kein Smalltalk.",
        "freundlich":    "Freundlich und unterst\u00fctzend — zug\u00e4nglich, positiver Ton, gelegentliche pers\u00f6nliche Anmerkungen erlaubt.",
        "direkt":        "Direkt und klar — kurze S\u00e4tze, keine F\u00fcllw\u00f6rter, Fakten zuerst, kein Ausrufezeichen-Spam.",
    }
    stil = _stil_map.get(kira_cfg.get("persoenlichkeit", "direkt"), _stil_map["direkt"])

    # ── Profil-basierte Identität laden ──
    try:
        from task_manager import get_active_profile
        _profil = get_active_profile()
        _team = _profil.get("team", [])
        _hauptbenutzer = _team[0] if _team else {}
        _firma = _profil.get("firma_name", "") or "Unternehmen"
        _inhaber_name = _hauptbenutzer.get("name", "")
        _inhaber_rolle = _hauptbenutzer.get("rolle", "Inhaber")
        _firma_beschr = _profil.get("firma_beschreibung", "")
    except Exception:
        _firma = _cfg.get("firma_name", "") or "Unternehmen"
        _inhaber_name = ""
        _inhaber_rolle = "Inhaber"
        _firma_beschr = ""

    prompt = f"""Du bist {kira_name} \u2014 die autonome KI-Gesch\u00e4ftsassistentin von {_firma}.
{_inhaber_rolle}: {_inhaber_name}. Heute: {today}.{f' {_firma_beschr}' if _firma_beschr else ''}

━━━ DEINE KERNIDENTITÄT ━━━
Du bist KEINE Chat-KI die nur antwortet wenn gefragt. Du bist eine eigenständige Geschäftsassistentin die:
- das Unternehmen aktiv überwacht und vorantreibt
- selbstständig Zusammenhänge erkennt und darauf reagiert
- den {_inhaber_rolle} entlastet indem du so viel wie möglich selbst erledigst
- niemals wartest bis etwas eskaliert — du handelst proaktiv

━━━ DEINE VOLLMACHTEN (AUTOMATISCH AUSFÜHRBAR) ━━━
Diese Aktionen führst du nach eigenem Ermessen aus und informierst den {_inhaber_rolle} danach:
✓ Angebotsstatus aktualisieren (angenommen / abgelehnt / nachfassen)
✓ Rechnungsstatus setzen (bezahlt / offen / überfällig)
✓ Tasks erstellen, priorisieren, erledigen
✓ Wissen speichern und Muster erkennen
✓ Entwürfe für Mails, Angebote, Rechnungen erstellen
✓ Kunden- und Kontaktdaten pflegen

Diese Aktionen führst du NUR nach Bestätigung des {_inhaber_rolle}s aus:
⚡ Mails tatsächlich versenden
⚡ Zahlungen oder Beträge buchen
⚡ Kundendaten löschen
⚡ Externe Dienste (ntfy, GitHub, APIs) nutzen

━━━ STRUKTURELLE FÄHIGKEITEN ━━━
Du kannst die Datenstruktur aktiv verändern:
✓ Aufgaben erstellen, bearbeiten, erledigen, löschen (task_erstellen, task_bearbeiten, task_erledigen, tasks_loeschen)
✓ Kategorien korrigieren — für Tasks, Captures, Vorgänge, Belege (korrektur)
✓ Wissensregeln erstellen, bearbeiten, deaktivieren (wissen_verwalten)
✓ Korrekturen werden automatisch als Lernbeispiele für den Classifier gespeichert

Wenn der Benutzer sagt "das ist falsch eingeordnet" → korrektur-Tool nutzen
Wenn der Benutzer sagt "merk dir das" / "das ist wichtig" → wissen_verwalten
Wenn aus dem Gespräch eine Aufgabe entsteht → task_erstellen anbieten

━━━ SO ARBEITEST DU ━━━
1. KONTEXT ZUERST: Bevor du antwortest oder handelst, nutze IMMER die Tools um den vollständigen Kontext zu holen.
   - Bei Kundenanfragen: mail_suchen + kunde_nachschlagen
   - Bei Angeboten: rechnungsdetails_abrufen + mail_suchen für Historie
   - Bei neuen Mails: Prüfe ob es Verbindungen zu offenen Vorgängen gibt
2. VOLLSTÄNDIGE ANALYSE: Schaue immer in ALLE relevanten Datenquellen:
   - Mails (12.000+ Archiv), Tasks, Angebote, Rechnungen, Kunden, Wissen
3. PROAKTIVE EMPFEHLUNGEN: Gib immer konkrete nächste Schritte an, nicht nur Beobachtungen
4. LERNE: Wenn etwas gut oder schlecht läuft → wissen_verwalten
5. KANÄLE: Du verarbeitest Eingaben aus allen Quellen:
   - E-Mail (5 Postfächer) | WhatsApp | Instagram | Manuell | Shop-Bestellungen | Dokumente

━━━ WAS DU IMMER WEISST ━━━
Du kennst jederzeit:
- Alle offenen/bezahlten Rechnungen mit Fälligkeiten
- Alle Angebote (offen/angenommen/abgelehnt) mit Nachfass-Terminen
- Alle Kundeninteraktionen und deren komplette Geschichte
- Alle 12.000+ archivierten Mails (suchbar via mail_suchen)
- Offene Tasks, Erinnerungen, Deadlines
- Eingangsmails der letzten Tage
- Deine eigenen Aktivitäten (runtime_log_suchen)

━━━ GESCHÄFT {_firma} ━━━
{_firma_beschr or f'{_firma} — Details aus den Benutzerprofile-Einstellungen.'}
{_inhaber_rolle}: {_inhaber_name}.

━━━ KOMMUNIKATION ━━━
- Direkt, klar, professionell — kein Marketing-Sprech
- Kurze Sätze, keine Füllwörter
- Zahlen immer mit EUR und 2 Dezimalstellen
- Datum: TT.MM.JJJJ
- Wenn du etwas automatisch ausgeführt hast: "Habe X erledigt." — kein Ausrufezeichen-Spam
- Wenn der {_inhaber_rolle} fragt "was liegt an": Priorisierte Liste mit konkreten Handlungsoptionen

━━━ VERTRAULICHKEIT ━━━
Alle Geschäftsdaten sind streng vertraulich. Nie erfinden — immer aus Daten.
"""
    # Persönlichkeit-Stil-Override (aus Einstellungen)
    if kira_cfg.get("persoenlichkeit", "direkt") != "direkt":
        prompt += f"\n\n\u2501\u2501\u2501 KOMMUNIKATIONSSTIL (angepasst) \u2501\u2501\u2501\n{stil}\n"
    # Sprache (aus kira-Einstellungen)
    _sprache = kira_cfg.get("sprache", "deutsch")
    if _sprache == "englisch":
        prompt += "\n\n\u2501\u2501\u2501 SPRACHE \u2501\u2501\u2501\nAntworte immer auf Englisch, unabh\u00e4ngig von der Sprache der Anfrage.\n"
    elif _sprache == "gemischt":
        prompt += "\n\n\u2501\u2501\u2501 SPRACHE \u2501\u2501\u2501\nAntworte in derselben Sprache wie die Anfrage (Deutsch wenn auf Deutsch gefragt, Englisch wenn auf Englisch).\n"
    # "deutsch" = Standard, kein Override
    # Chitchat / Smalltalk (aus kira-Einstellungen)
    if not kira_cfg.get("chitchat_erlaubt", True):
        prompt += "\n\n\u2501\u2501\u2501 FOKUS \u2501\u2501\u2501\nDu bist ausschlie\u00dflich auf Gesch\u00e4ftsthemen fokussiert. Beantworte keine allgemeinen Wissensfragen, Smalltalk oder Themen ohne direkten Bezug zu den Gesch\u00e4ftsdaten. Weise freundlich darauf hin, dass du f\u00fcr gesch\u00e4ftliche Aufgaben zust\u00e4ndig bist.\n"
    # Benutzerdefinierte System-Prompt-Ergänzung
    custom_prompt = (kira_cfg.get("system_prompt_custom") or "").strip()
    if custom_prompt:
        prompt += f"\n\n\u2501\u2501\u2501 ZUS\u00c4TZLICHE ANWEISUNGEN \u2501\u2501\u2501\n{custom_prompt}\n"

    # Antwort-Länge (aus llm-Einstellungen)
    try:
        _llm_cfg = _full_cfg.get("llm", {})
    except Exception:
        _llm_cfg = {}
    _antwort_laenge = _llm_cfg.get("antwort_laenge", "normal")
    if _antwort_laenge == "kurz":
        prompt += "\n\n\u2501\u2501\u2501 ANTWORT-STIL \u2501\u2501\u2501\nAntworte immer sehr kurz und knapp \u2014 maximal 3 S\u00e4tze pro Punkt, keine ausschweifenden Erkl\u00e4rungen.\n"
    elif _antwort_laenge == "ausfuehrlich":
        prompt += "\n\n\u2501\u2501\u2501 ANTWORT-STIL \u2501\u2501\u2501\nAntworte ausf\u00fchrlich und detailliert \u2014 erkl\u00e4re Zusammenh\u00e4nge, liefere Hintergr\u00fcnde und konkrete Handlungsoptionen.\n"
    # "normal" = kein Override n\u00f6tig

    if config.get("geschaeftsdaten_teilen", True):
        prompt += "\n" + _build_data_context(config, kira_cfg)

    # Runtime-Log Kontext: Kira sieht ihre letzten Aktivitäten
    try:
        cfg = get_config()
        if cfg.get("runtime_log", {}).get("kira_darf_lesen", True):
            from runtime_log import get_recent_for_kira
            recent = get_recent_for_kira(limit=20)
            if recent:
                prompt += f"\n\nDEINE LETZTEN AKTIVITÄTEN (Runtime-Log):\n{recent}\n"
                prompt += "\nNutze diese Informationen proaktiv — z.B. wenn der Benutzer fragt was du getan hast, welche Fehler auftraten, oder wenn du selbst Kontext zu früheren Aktionen brauchst."
    except Exception:
        pass

    # Offene Vorgänge (Case Engine) — Paket 7, session-nn
    try:
        from case_engine import get_vorgang_summary_for_kira
        vs = get_vorgang_summary_for_kira(limit=8)
        if vs and vs.strip():
            prompt += f"\n\nOFFENE VORGAENGE (Case Engine):\n{vs}\n"
            prompt += "\nNutze vorgang_kontext_laden fuer den vollstaendigen Kontext eines Vorgangs.\n"
    except Exception:
        pass

    # Episodisches Gedaechtnis (Paket 3, session-oo)
    # Letzte 3 abgeschlossene Konversationen als Gespraechsfaden-Kontext
    try:
        mem_db = sqlite3.connect(str(TASKS_DB))
        mem_db.row_factory = sqlite3.Row
        recent_sessions = mem_db.execute("""
            SELECT session_id, MIN(erstellt_am) as ts_start, COUNT(*) as n_msgs
            FROM kira_konversationen
            GROUP BY session_id
            HAVING n_msgs >= 2
            ORDER BY ts_start DESC
            LIMIT 3
        """).fetchall()
        if recent_sessions:
            mem_lines = []
            for sess in recent_sessions:
                sid = sess["session_id"]
                ts  = (sess["ts_start"] or "")[:16]
                u_row = mem_db.execute(
                    "SELECT nachricht FROM kira_konversationen WHERE session_id=? AND rolle='user' ORDER BY id LIMIT 1",
                    (sid,)
                ).fetchone()
                k_row = mem_db.execute(
                    "SELECT nachricht FROM kira_konversationen WHERE session_id=? AND rolle='assistant' ORDER BY id LIMIT 1",
                    (sid,)
                ).fetchone()
                u_text = ((u_row["nachricht"] if u_row else "") or "")[:120].replace('\n', ' ')
                k_text = ((k_row["nachricht"] if k_row else "") or "")[:150].replace('\n', ' ')
                mem_lines.append(f"  [{ts}] Benutzer: {u_text}")
                if k_text:
                    mem_lines.append(f"         Kira: {k_text}...")
            if mem_lines:
                # Token-Budget: max ~800 Token = ~3200 Zeichen
                mem_block = "\n".join(mem_lines)
                if len(mem_block) > 3200:
                    mem_block = mem_block[:3200] + "..."
                prompt += f"\n\nLETZTE GESPRAECHE (Gedaechtnis):\n{mem_block}\n"
                prompt += "(Fuer tiefere Suche: konversation_suchen nutzen)\n"
        mem_db.close()
    except Exception:
        pass

    return prompt


def _build_data_context(config, kira_cfg=None):
    max_items = config.get("max_kontext_items", 50)
    today = date.today().isoformat()
    ctx = "AKTUELLE GESCHÄFTSDATEN:\n"

    # Kontext-Steuerung: "immer" | "relevant" (nur wenn Daten vorhanden) | "nie"
    kira_cfg = kira_cfg or {}
    _k_aufgaben    = kira_cfg.get("kontext_aufgaben",   "immer")
    _k_mails       = kira_cfg.get("kontext_mails",      "immer")
    _k_rechnungen  = kira_cfg.get("kontext_rechnungen", "immer")

    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row

    if _k_rechnungen != "nie":
        try:
            rows = db.execute("SELECT * FROM ausgangsrechnungen ORDER BY datum DESC LIMIT ?", (max_items,)).fetchall()
            offen = [r for r in rows if r['status'] == 'offen']
            bezahlt = [r for r in rows if r['status'] == 'bezahlt']
            if _k_rechnungen == "immer" or rows:
                ctx += f"\n=== AUSGANGSRECHNUNGEN ({len(rows)} gesamt, {len(offen)} offen) ===\n"
                for r in offen:
                    _bb = f"{r['betrag_brutto'] or 0:.2f}".replace('.', ',')
                    ctx += f"  [{r['id']}] {r['re_nummer']} | {r['datum']} | {r['kunde_name'] or r['kunde_email'] or '?'} | {_bb} EUR | OFFEN"
                    if r['mahnung_count'] and r['mahnung_count'] > 0:
                        ctx += f" | {r['mahnung_count']}x gemahnt"
                    ctx += "\n"
                if bezahlt:
                    ctx += f"  ({len(bezahlt)} bezahlt, älteste: {bezahlt[-1]['datum'] if bezahlt else '-'})\n"
        except: pass

        try:
            rows = db.execute("SELECT * FROM angebote ORDER BY datum DESC LIMIT ?", (max_items,)).fetchall()
            ang_offen = [r for r in rows if r['status'] == 'offen']
            if _k_rechnungen == "immer" or rows:
                ctx += f"\n=== ANGEBOTE ({len(rows)} gesamt, {len(ang_offen)} offen) ===\n"
                for r in ang_offen:
                    nf = r['nachfass_count'] or 0
                    nn = r['naechster_nachfass'] or ''
                    ctx += f"  [{r['id']}] {r['a_nummer']} | {r['datum']} | {r['kunde_name'] or r['kunde_email'] or '?'} | Nachfass: {nf}/3"
                    if nn and nn <= today:
                        ctx += f" | NACHFASS FÄLLIG ({nn})"
                    ctx += "\n"
        except: pass

        try:
            rows = db.execute("SELECT * FROM geschaeft WHERE wichtigkeit='aktiv' AND (bewertung IS NULL OR bewertung!='erledigt') ORDER BY datum DESC LIMIT ?", (max_items,)).fetchall()
            if rows:
                ctx += f"\n=== OFFENE EINGANGSRECHNUNGEN ({len(rows)}) ===\n"
                for r in rows:
                    _eb = f"{r['betrag'] or 0:.2f}".replace('.', ',')
                    ctx += f"  [{r['id']}] {r['gegenpartei'] or r['gegenpartei_email'] or '?'} | {r['betreff'][:50]} | {_eb} EUR | {r['datum']}\n"
        except: pass

    if _k_aufgaben != "nie":
        try:
            rows = db.execute("SELECT kategorie, COUNT(*) as n FROM tasks GROUP BY kategorie ORDER BY n DESC").fetchall()
            if _k_aufgaben == "immer" or rows:
                ctx += "\n=== KOMMUNIKATION (Posteingang) ===\n"
                for r in rows:
                    ctx += f"  {r['kategorie']}: {r['n']} Einträge\n"
        except: pass

    # Mail-Kontext aus Archiv: letzte 15 wichtige Mails (INBOX, nicht Newsletter)
    if _k_mails != "nie":
        try:
            if MAIL_INDEX_DB.exists():
                mdb = sqlite3.connect(str(MAIL_INDEX_DB))
                mdb.row_factory = sqlite3.Row
                mail_rows = mdb.execute("""
                    SELECT absender_short, absender, betreff, datum_iso, datum,
                           hat_anhaenge, anhaenge, message_id, folder, text_plain
                    FROM mails
                    WHERE (folder LIKE '%INBOX%' OR folder LIKE '%Eingang%' OR folder LIKE 'INBOX')
                    ORDER BY datum_iso DESC LIMIT 15
                """).fetchall()
                mdb.close()
                if mail_rows:
                    # kira_verwendet setzen für alle in den Kontext aufgenommenen Mails
                    used_ids = [m['message_id'] for m in mail_rows if m['message_id']]
                    if used_ids:
                        try:
                            mdb2 = sqlite3.connect(str(MAIL_INDEX_DB))
                            mdb2.executemany(
                                "UPDATE mails SET kira_verwendet=1 WHERE message_id=?",
                                [(mid,) for mid in used_ids]
                            )
                            mdb2.commit()
                            mdb2.close()
                        except Exception:
                            pass
                    ctx += f"\n=== LETZTE EINGANGSMAILS ({len(mail_rows)}) ===\n"
                    ctx += "(Für vollständigen Mailinhalt: mail_lesen(message_id) aufrufen)\n"
                    for m in mail_rows:
                        absender_disp = m['absender_short'] or m['absender'] or '?'
                        datum_disp = (m['datum_iso'] or m['datum'] or '')[:16]
                        anhang_flag = " [Anhang]" if m['hat_anhaenge'] else ""
                        text_preview = (m['text_plain'] or '')[:150].replace('\n', ' ')
                        ctx += f"  [{m['message_id'][:30] if m['message_id'] else '?'}] {datum_disp} | {absender_disp[:40]} | {(m['betreff'] or '')[:60]}{anhang_flag}\n"
                        if text_preview:
                            ctx += f"    → {text_preview}...\n"
        except Exception:
            pass

    if _k_rechnungen != "nie":
        try:
            ddb = sqlite3.connect(str(DETAIL_DB))
            ddb.row_factory = sqlite3.Row
            for r in ddb.execute("SELECT re_nummer, skonto_datum, skonto_prozent, skonto_betrag, zahlungsziel_datum FROM rechnungen_detail WHERE skonto_datum >= ? OR zahlungsziel_datum >= ?", (today, today)):
                ctx += f"  Frist: {r['re_nummer']} — Skonto {r['skonto_prozent']}% bis {r['skonto_datum']}, Ziel bis {r['zahlungsziel_datum']}\n"
            ddb.close()
        except: pass

    try:
        rows = db.execute("SELECT titel, inhalt FROM wissen_regeln WHERE kategorie='gelernt' ORDER BY id DESC LIMIT 20").fetchall()
        if rows:
            ctx += f"\n=== GELERNTE ERKENNTNISSE ({len(rows)}) ===\n"
            for r in rows:
                ctx += f"  • {r['titel']}: {r['inhalt'][:100]}\n"
    except: pass

    # Auto-gelernte Regeln (aus Mail-Ablehnungen, Stil-Korrekturen, Feedback)
    try:
        auto_rows = db.execute(
            "SELECT titel, inhalt, quelle FROM wissen_regeln "
            "WHERE kategorie='auto_gelernt' AND status='aktiv' "
            "ORDER BY id DESC LIMIT 15"
        ).fetchall()
        if auto_rows:
            ctx += f"\n=== AUTO-GELERNTE REGELN ({len(auto_rows)}) ===\n"
            ctx += "(Diese Regeln wurden aus Nutzer-Feedback automatisch erstellt. BEACHTE sie bei Mail-Entwuerfen und Antworten!)\n"
            for r in auto_rows:
                _src = ""
                if r['quelle'] == 'mail_rejection':
                    _src = " [Mail-Ablehnung]"
                elif r['quelle'] == 'mail_stil_diff':
                    _src = " [Stil-Korrektur]"
                elif r['quelle'] and 'feedback' in r['quelle']:
                    _src = " [Chat-Feedback]"
                ctx += f"  • {r['titel']}: {r['inhalt'][:150]}{_src}\n"
    except: pass

    # Klassifizierungs-Korrekturen (aus Kira-Chat gelernt)
    try:
        klass_rows = db.execute(
            "SELECT titel, inhalt FROM wissen_regeln "
            "WHERE kategorie='klassifizierung' AND status='aktiv' "
            "ORDER BY id DESC LIMIT 10"
        ).fetchall()
        if klass_rows:
            ctx += f"\n=== KLASSIFIZIERUNGS-KORREKTUREN ({len(klass_rows)}) ===\n"
            ctx += "(Aus Kira-Chat-Korrekturen gelernt — beachte bei Kategorisierungen!)\n"
            for r in klass_rows:
                ctx += f"  • {r['titel']}: {r['inhalt'][:120]}\n"
    except: pass

    try:
        zahlungsdauern = []
        for s in db.execute("SELECT daten_json FROM geschaeft_statistik WHERE ereignis='status_bezahlt' AND daten_json IS NOT NULL"):
            d = json.loads(s[0]) if s[0] else {}
            if d.get('zahlungsdauer_tage'):
                zahlungsdauern.append(d['zahlungsdauer_tage'])
        if zahlungsdauern:
            avg = sum(zahlungsdauern) / len(zahlungsdauern)
            ctx += f"\n=== MUSTER ===\n  Ø Zahlungsdauer: {avg:.0f} Tage (Basis: {len(zahlungsdauern)} Rechnungen)\n"
    except: pass

    # Proaktiver Scan: letzte Findings einbeziehen
    try:
        import kira_proaktiv as _p
        state = _p._load_state()
        today_str = date.today().isoformat()
        findings = []
        for key, val in state.items():
            if not key.startswith("proaktiv_"):
                continue
            # Format: proaktiv_<typ>_<id> = {datum, text, aktion, ...}
            if isinstance(val, dict) and val.get("datum", "")[:10] == today_str:
                txt = val.get("text", "")
                if txt:
                    findings.append(f"  ⚡ {txt}")
        if findings:
            ctx += f"\n=== PROAKTIVE KIRA-FINDINGS HEUTE ({len(findings)}) ===\n"
            ctx += "\n".join(findings[:20]) + "\n"
            ctx += "(Weitere Findings in knowledge/proaktiv_state.json)\n"
    except Exception:
        pass

    # Schlafende Mails (Snooze) — Kira kennt alle Mails die auf Erinnerung warten
    if _k_mails != "nie":
        try:
            if MAIL_INDEX_DB.exists():
                snooze_conn = sqlite3.connect(str(MAIL_INDEX_DB))
                snooze_conn.row_factory = sqlite3.Row
                snooze_rows = snooze_conn.execute(
                    "SELECT konto, betreff, absender, datum, snooze_until "
                    "FROM mails WHERE snooze_until IS NOT NULL AND datetime(snooze_until) > datetime('now') "
                    "ORDER BY snooze_until ASC"
                ).fetchall()
                snooze_conn.close()
                if snooze_rows:
                    ctx += f"\n=== SCHLAFENDE MAILS — ERNEUT ERINNERN ({len(snooze_rows)}) ===\n"
                    ctx += "(Diese Mails wurden vom Nutzer zurückgestellt und wecken sich automatisch)\n"
                    for r in snooze_rows:
                        ctx += (f"  Erinnert {r['snooze_until'][:16]} | {r['absender'] or '?'} | "
                                f"{(r['betreff'] or '')[:60]} | Konto: {r['konto']}\n")
        except Exception:
            pass

    # Gelöschte-Protokoll: Kira kann auf bereinigten Mail-Kontext zugreifen
    try:
        gp_rows = db.execute("""
            SELECT konto, datum_mail, absender, betreff, kurzinhalt, datum_geloescht
            FROM geloeschte_protokoll
            ORDER BY datum_geloescht DESC LIMIT 20
        """).fetchall()
        if gp_rows:
            ctx += f"\n=== GELÖSCHTE MAILS PROTOKOLL (letzte {len(gp_rows)}) ===\n"
            ctx += "(Aus Archiv bereinigt — Anhänge entfernt, Kurzinhalt bleibt erhalten)\n"
            for r in gp_rows:
                dm = (r['datum_mail'] or '')[:10]
                dg = (r['datum_geloescht'] or '')[:10]
                ctx += (f"  {dm} | {r['absender'] or '?'} | "
                        f"{(r['betreff'] or '')[:60]} | bereinigt: {dg}\n")
                if r['kurzinhalt']:
                    ctx += f"    → {r['kurzinhalt'][:150]}\n"
    except Exception:
        pass

    # Lexware Office — offene Posten Kurzuebersicht (session-eee, nur wenn Modul aktiv)
    try:
        _lex_cfg = config.get("lexware", {})
        if _lex_cfg.get("status") == "freigeschaltet":
            _lrows = db.execute(
                "SELECT typ, kontakt_name, brutto, datum, faellig FROM lexware_belege "
                "WHERE status='open' ORDER BY faellig LIMIT 10"
            ).fetchall()
            if _lrows:
                ctx += f"\n=== LEXWARE OFFICE — OFFENE POSTEN ({len(_lrows)}) ===\n"
                for lr in _lrows:
                    faellig = lr[4] or lr[3] or ""
                    ctx += f"  {lr[0].upper()} | {lr[1] or '?'} | {lr[2]:.2f} EUR | faellig: {faellig[:10]}\n"
            _pq = db.execute(
                "SELECT COUNT(*) FROM eingangsbelege_pruefqueue WHERE status='zu_pruefen'"
            ).fetchone()
            if _pq and _pq[0]:
                ctx += f"  {_pq[0]} Eingangsbeleg(e) warten auf Prüfung in Buchhaltungs-Queue.\n"
    except Exception:
        pass

    # Dokumente — letzte Eingänge und offene Dokumente (session-eeee)
    _k_dokumente = kira_cfg.get("kontext_dokumente", "immer")
    if _k_dokumente != "nie":
        try:
            dok_rows = db.execute(
                "SELECT id, titel, dateiname, kategorie, dokumentrolle, quelle, status, "
                "routing_ziel, zielmodul, erstellt_am, konfidenz "
                "FROM dokumente WHERE geloescht_am IS NULL "
                "ORDER BY erstellt_am DESC LIMIT 15"
            ).fetchall()
            if (_k_dokumente == "immer" or dok_rows) and dok_rows:
                neue = [r for r in dok_rows if r['status'] == 'neu']
                ctx += f"\n=== DOKUMENTE ({len(dok_rows)} letzte, {len(neue)} neu) ===\n"
                for r in dok_rows:
                    datum = (r['erstellt_am'] or '')[:16]
                    konfidenz = f" ({r['konfidenz']*100:.0f}%)" if r['konfidenz'] else ""
                    ctx += (f"  [{r['id']}] {datum} | {r['titel'] or r['dateiname']} | "
                            f"{r['kategorie'] or '?'} | {r['status']} | "
                            f"Routing: {r['routing_ziel'] or '?'} → {r['zielmodul'] or '?'}{konfidenz}\n")
        except Exception:
            pass

    # Offene Zusagen / Commitments — Kira weiß was zugesagt wurde
    try:
        _tbl = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mail_commitments'").fetchone()
        if _tbl:
            _zrows = db.execute("""
                SELECT id, typ, text, datum_faellig, absender, betreff, erstellt_am
                FROM mail_commitments WHERE status='offen'
                ORDER BY CASE WHEN datum_faellig IS NULL THEN '9999' ELSE datum_faellig END ASC
                LIMIT 15
            """).fetchall()
            if _zrows:
                ctx += f"\n=== OFFENE ZUSAGEN ({len(_zrows)}) ===\n"
                ctx += "(Vom Benutzer zugesagte oder erkannte Termine/Fristen aus E-Mails)\n"
                for zr in _zrows:
                    df = (zr['datum_faellig'] or 'kein Datum')[:10]
                    abs_k = (zr['absender'] or '').split('<')[0].strip()[:30]
                    ctx += f"  [{zr['id']}] {zr['typ']} | {df} | {abs_k} | {(zr['text'] or '')[:80]}\n"
                ctx += "→ Wenn der Benutzer fragt 'was habe ich offen?' oder 'offene Zusagen': diese Liste verwenden.\n"
    except Exception:
        pass

    db.close()
    return ctx


def mail_vollinhalt_lesen(message_id: str) -> dict:
    """
    Liest den vollständigen Inhalt einer Mail aus dem lokalen Archiv.
    Gibt dict zurück: {ok, betreff, absender, datum, text, anhaenge, eml_path, error}
    Sucht zuerst in mail_index.db → dann liest mail.json aus mail_folder_pfad.
    """
    if not MAIL_INDEX_DB.exists():
        return {"ok": False, "error": "mail_index.db nicht vorhanden"}
    try:
        mdb = sqlite3.connect(str(MAIL_INDEX_DB))
        mdb.row_factory = sqlite3.Row
        row = mdb.execute(
            "SELECT * FROM mails WHERE message_id=?", (message_id,)
        ).fetchone()
        mdb.close()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    if not row:
        return {"ok": False, "error": f"Mail nicht gefunden: {message_id}"}

    result = {
        "ok": True,
        "message_id": message_id,
        "betreff": row["betreff"] or "",
        "absender": row["absender"] or "",
        "datum": row["datum_iso"] or row["datum"] or "",
        "text": row["text_plain"] or "",
        "anhaenge": [],
        "eml_path": row["eml_path"] or "",
        "mail_folder_pfad": row["mail_folder_pfad"] or "",
        "hat_anhaenge": bool(row["hat_anhaenge"]),
    }

    # Anhänge aus JSON
    try:
        if row["anhaenge"]:
            result["anhaenge"] = json.loads(row["anhaenge"])
    except Exception:
        pass

    # Vollständigen Text aus mail.json nachladen (falls text_plain kurz/leer)
    mail_folder = row["mail_folder_pfad"] or ""
    if mail_folder:
        json_path = Path(mail_folder) / "mail.json"
        try:
            if json_path.exists():
                mj = json.loads(json_path.read_text('utf-8'))
                full_text = mj.get("text", "")
                if full_text and len(full_text) > len(result["text"]):
                    result["text"] = full_text[:20000]
                if mj.get("anhaenge"):
                    result["anhaenge"] = mj["anhaenge"]
                anhaenge_pfad = mj.get("anhaenge_pfad", "")
                if anhaenge_pfad and Path(anhaenge_pfad).exists():
                    result["anhaenge_pfad"] = anhaenge_pfad
                    result["anhaenge_dateien"] = [f.name for f in Path(anhaenge_pfad).iterdir() if f.is_file()]
        except Exception:
            pass

    # kira_verwendet setzen — Kira hat diese Mail explizit gelesen
    try:
        mdb3 = sqlite3.connect(str(MAIL_INDEX_DB))
        mdb3.execute("UPDATE mails SET kira_verwendet=1 WHERE message_id=?", (message_id,))
        mdb3.commit()
        mdb3.close()
    except Exception:
        pass

    return result


# ── Tool-Definitionen (Anthropic-Format = Canonical) ─────────────────────────
def get_tools(config=None):
    config = config or get_config()
    tools = [
        {
            "name": "rechnung_bezahlt",
            "description": "Markiert eine Ausgangsrechnung als bezahlt. Fragt automatisch nach Details.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "rechnung_id": {"type": "integer", "description": "ID der Rechnung in der Datenbank"},
                    "bezahlt_am": {"type": "string", "description": "Datum der Zahlung (YYYY-MM-DD)"},
                    "voller_betrag": {"type": "boolean", "description": "Wurde der volle Betrag bezahlt?"},
                    "betrag": {"type": "number", "description": "Bezahlter Betrag (nur wenn nicht voller Betrag)"},
                    "notiz": {"type": "string", "description": "Zusätzliche Notizen"}
                },
                "required": ["rechnung_id", "bezahlt_am", "voller_betrag"]
            }
        },
        {
            "name": "angebot_status",
            "description": "Ändert den Status eines Angebots (angenommen/abgelehnt/keine_antwort).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "angebot_id": {"type": "integer", "description": "ID des Angebots"},
                    "status": {"type": "string", "enum": ["angenommen", "abgelehnt", "keine_antwort"]},
                    "grund": {"type": "string", "description": "Grund für den Status"}
                },
                "required": ["angebot_id", "status"]
            }
        },
        {
            "name": "eingangsrechnung_erledigt",
            "description": "Markiert eine Eingangsrechnung als erledigt/bezahlt.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "geschaeft_id": {"type": "integer", "description": "ID des Geschäftsvorgangs"},
                    "bezahlt_am": {"type": "string", "description": "Datum der Zahlung (YYYY-MM-DD)"},
                    "notiz": {"type": "string", "description": "Notizen"}
                },
                "required": ["geschaeft_id", "bezahlt_am"]
            }
        },
        {
            "name": "kunde_nachschlagen",
            "description": "Sucht Kundendaten in der Datenbank. Gibt alle bekannten Interaktionen zurück.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "suchbegriff": {"type": "string", "description": "Name, E-Mail oder Firma des Kunden"}
                },
                "required": ["suchbegriff"]
            }
        },
        {
            "name": "nachfass_email_entwerfen",
            "description": "Entwirft eine Nachfass-E-Mail für ein offenes Angebot.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "angebot_id": {"type": "integer", "description": "ID des Angebots"},
                    "ton": {"type": "string", "enum": ["freundlich", "bestimmt", "letzte_chance"], "description": "Tonfall"}
                },
                "required": ["angebot_id"]
            }
        },
        {
            "name": "wissen_verwalten",
            "description": (
                "Erstellt, bearbeitet oder deaktiviert Wissensregeln. "
                "Nutze 'erstellen' für neue Erkenntnisse. "
                "'bearbeiten' um bestehende Regeln zu aktualisieren. "
                "'deaktivieren' um veraltete Regeln zu entfernen."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "aktion": {"type": "string", "enum": ["erstellen", "bearbeiten", "deaktivieren"], "description": "Was soll getan werden?"},
                    "regel_id": {"type": "integer", "description": "ID der Regel (nur bei bearbeiten/deaktivieren)"},
                    "titel": {"type": "string", "description": "Kurzer Titel der Erkenntnis"},
                    "inhalt": {"type": "string", "description": "Ausführlicher Inhalt"},
                    "kategorie": {"type": "string", "enum": ["gelernt", "kunde", "prozess", "markt", "klassifizierung", "stil", "kira", "fest", "preis", "technik"]},
                    "status": {"type": "string", "enum": ["aktiv", "inaktiv", "entwurf"]}
                },
                "required": ["aktion"]
            }
        },
        {
            "name": "rechnungsdetails_abrufen",
            "description": "Gibt vollständige Details einer Rechnung zurück (Positionen, Beträge, Zahlungsziel, Skonto).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "re_nummer": {"type": "string", "description": "Rechnungsnummer (z.B. RE-SB260104)"}
                },
                "required": ["re_nummer"]
            }
        },
    ]

    tools.append({
        "name": "angebot_pruefen",
        "description": "Prüft den Status eines Angebots: sucht nach Kundenantworten und gibt Handlungsempfehlung.",
        "input_schema": {
            "type": "object",
            "properties": {
                "a_nummer": {"type": "string", "description": "Angebotsnummer (z.B. A-SB260094)"}
            },
            "required": ["a_nummer"]
        }
    })

    tools.append({
        "name": "duplikate_suchen",
        "description": (
            "Scannt alle offenen Aufgaben nach Duplikaten und ähnlichen Mails. "
            "Erkennt z.B. 1 Mail mit vielen Anhängen + X Mails mit je 1 Anhang aber gleichem Betreff/Body. "
            "Gibt Cluster mit Task-IDs, Betreffs und Anhang-Infos zurück. "
            "Nutze dies um dem Nutzer proaktiv Bereinigungsvorschläge zu machen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "min_aehnlichkeit": {
                    "type": "number",
                    "description": "Minimale Ähnlichkeit 0.0–1.0 (Standard: 0.75)",
                    "default": 0.75
                }
            },
            "required": []
        }
    })
    tools.append({
        "name": "korrektur",
        "description": (
            "Korrigiert die Kategorie oder Zuordnung eines beliebigen Eintrags — Mail, Task, Capture, Vorgang oder Beleg. "
            "Speichert die Korrektur als Lernbeispiel für den Classifier. "
            "Nutze dieses Tool wenn der Benutzer sagt, dass etwas falsch eingeordnet ist — egal welcher Kanal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entitaet_typ": {
                    "type": "string",
                    "enum": ["task", "capture", "vorgang", "beleg"],
                    "description": "Was wird korrigiert? task = Mail-/Aufgabenklassifizierung, capture = Capture-Eintrag, vorgang = Geschäftsvorgang, beleg = Lexware-Beleg"
                },
                "entitaet_id": {"type": "integer", "description": "ID des Eintrags"},
                "neue_kategorie": {
                    "type": "string",
                    "description": "Die korrekte Kategorie (abhängig vom Entitätstyp)"
                },
                "grund": {"type": "string", "description": "Warum die alte Kategorie falsch war — wird als Lernregel gespeichert"},
                "auch_status": {
                    "type": "string",
                    "description": "Optional: Status gleich mitändern (z.B. 'offen', 'erledigt', 'ignorieren')"
                },
                "kanal": {
                    "type": "string",
                    "description": "Ursprungskanal der Korrektur (email, whatsapp, instagram, capture, lexware, manuell, chat)"
                }
            },
            "required": ["entitaet_typ", "entitaet_id", "neue_kategorie", "grund"]
        }
    })
    tools.append({
        "name": "task_erstellen",
        "description": (
            "Erstellt eine neue Aufgabe. Nutze dies wenn aus einer Konversation heraus eine Aufgabe entsteht — "
            "z.B. 'Kunde anrufen', 'Angebot nachfassen', 'Dokument prüfen'. "
            "Die Aufgabe erscheint sofort im Dashboard."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "betreff": {"type": "string", "description": "Kurzer Titel der Aufgabe"},
                "zusammenfassung": {"type": "string", "description": "Ausführlichere Beschreibung"},
                "kategorie": {
                    "type": "string",
                    "enum": [
                        "Antwort erforderlich", "Neue Lead-Anfrage", "Angebotsrückmeldung",
                        "Rechnung / Beleg", "Zur Kenntnis", "Shop / System", "Sonstiger Vorgang"
                    ],
                    "description": "Aufgabenkategorie"
                },
                "prioritaet": {"type": "string", "enum": ["hoch", "mittel", "niedrig"]},
                "deadline": {"type": "string", "description": "Fälligkeitsdatum YYYY-MM-DD (optional)"},
                "kanal": {"type": "string", "description": "Ursprungskanal (email, whatsapp, instagram, capture, manuell, chat)"}
            },
            "required": ["betreff", "kategorie"]
        }
    })
    tools.append({
        "name": "task_bearbeiten",
        "description": (
            "Ändert Felder einer bestehenden Aufgabe — Betreff, Kategorie, Priorität, Deadline, Zusammenfassung. "
            "Nutze dies statt korrektur wenn es keine Fehlklassifizierung ist sondern eine inhaltliche Änderung."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "ID der Aufgabe"},
                "betreff": {"type": "string", "description": "Neuer Titel"},
                "zusammenfassung": {"type": "string", "description": "Neue Beschreibung"},
                "kategorie": {"type": "string", "description": "Neue Kategorie"},
                "prioritaet": {"type": "string", "enum": ["hoch", "mittel", "niedrig"]},
                "deadline": {"type": "string", "description": "Neues Fälligkeitsdatum YYYY-MM-DD"},
                "notiz": {"type": "string", "description": "Warum die Änderung"}
            },
            "required": ["task_id"]
        }
    })
    tools.append({
        "name": "task_erledigen",
        "description": (
            "Markiert eine oder mehrere Aufgaben als erledigt/abgelegt OHNE sie zu löschen. "
            "Benutze dies für: erledigte Rechnungen, abgelegte Belege, bestätigte Informationen, "
            "bearbeitete Anfragen. BEVORZUGE dieses Tool gegenüber tasks_loeschen! "
            "Die Aufgaben bleiben im Archiv auffindbar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Liste der zu erledigenden Task-IDs"
                },
                "status": {
                    "type": "string",
                    "enum": ["erledigt", "zur_kenntnis", "ignorieren"],
                    "description": "erledigt = bearbeitet/abgelegt; zur_kenntnis = gelesen/abgehakt; ignorieren = nicht relevant"
                },
                "notiz": {
                    "type": "string",
                    "description": "Optionale Notiz / Erkenntniss (wird als Lernregel gespeichert)"
                }
            },
            "required": ["task_ids", "status"]
        }
    })

    tools.append({
        "name": "tasks_loeschen",
        "description": (
            "DAUERHAFTES Löschen — Aufgaben werden unwiderruflich aus DB UND Mail-Archiv entfernt. "
            "NUR verwenden wenn der Benutzer EXPLIZIT 'löschen' sagt! "
            "Für erledigte Rechnungen, Belege oder abgeschlossene Vorgänge stattdessen task_erledigen nutzen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Liste der zu löschenden Task-IDs"
                },
                "grund": {
                    "type": "string",
                    "description": "Grund für die Löschung (wird als Lernregel gespeichert)"
                }
            },
            "required": ["task_ids", "grund"]
        }
    })

    # Kira darf Runtime-Log lesen wenn konfiguriert
    try:
        from runtime_log import _get_cfg as _rlcfg
        if _rlcfg().get("kira_darf_lesen", True):
            tools.append({
                "name": "runtime_log_suchen",
                "description": (
                    "Durchsucht das Runtime-Ereignisprotokoll von Kira. "
                    "Zeigt was der Nutzer zuletzt getan hat, welche Tools aufgerufen wurden, "
                    "LLM-Kosten, Hintergrundjobs, Fehler und Einstellungsaenderungen. "
                    "Nützlich um: 'Was habe ich heute alles erledigt?', 'Welche Fehler gab es?', "
                    "'Wie viele Tokens habe ich heute verbraucht?' zu beantworten."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "event_type":   {"type": "string", "enum": ["ui","kira","llm","system","settings"], "description": "Nur bestimmten Event-Typ zeigen"},
                        "action":       {"type": "string", "description": "Aktion filtern (z.B. 'chat_completed', 'tool_called')"},
                        "modul":        {"type": "string", "description": "Modul filtern (z.B. 'kira', 'geschaeft')"},
                        "context_type": {"type": "string", "description": "Kontext-Typ filtern (z.B. 'rechnung', 'angebot')"},
                        "status":       {"type": "string", "enum": ["ok","fehler","partial_failure"], "description": "Status filtern"},
                        "search":       {"type": "string", "description": "Freitextsuche in summary/result"},
                        "limit":        {"type": "integer", "description": "Maximale Anzahl Eintraege (Standard: 20)", "default": 20}
                    }
                }
            })
    except Exception:
        pass

    # Mail-Tools (immer aktiv wenn mail_index.db vorhanden)
    if MAIL_INDEX_DB.exists():
        tools.append({
            "name": "mail_suchen",
            "description": "Sucht in allen archivierten Mails (12.000+). Nutze dieses Tool wenn du nach Mails eines Kunden, zu einem Projekt oder mit bestimmtem Inhalt suchst. Gibt Absender, Betreff, Datum und Textvorschau zurück.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query":   {"type": "string", "description": "Suchbegriff — in Betreff, Absender und Mailtext"},
                    "konto":   {"type": "string", "description": "Optional: nur dieses Konto durchsuchen (z.B. 'anfrage@raumkult.eu')"},
                    "folder":  {"type": "string", "description": "Optional: nur diesen Ordner (INBOX, Gesendete Elemente)"},
                    "limit":   {"type": "integer", "description": "Max. Ergebnisse (Standard: 20)", "default": 20}
                },
                "required": ["query"]
            }
        })
        tools.append({
            "name": "mail_lesen",
            "description": "Liest den vollständigen Inhalt einer Mail aus dem Archiv inklusive komplettem Text und Anhang-Liste. Verwende die message_id aus den Suchergebnissen oder der Mailliste.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "Message-ID der Mail (aus mail_suchen oder der Mailliste)"}
                },
                "required": ["message_id"]
            }
        })

    if config.get("internet_recherche", False):
        tools.append({
            "name": "web_recherche",
            "description": "Sucht im Internet nach Informationen. Nützlich für Firmeninfos, Bauvorschriften, Marktpreise etc.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Suchbegriff"},
                    "max_results": {"type": "integer", "description": "Max. Ergebnisse (1-5)", "default": 3}
                },
                "required": ["query"]
            }
        })

    # ── Vorgang-Tool (Paket 7, session-nn) ───────────────────────────────────
    tools.append({
        "name": "vorgang_kontext_laden",
        "description": (
            "Lädt den vollständigen Vorgang-Kontext: verknüpfte Mails, Tasks, Angebote, Rechnungen + "
            "Statushistorie. Nutze dies IMMER wenn der Benutzer über einen Kunden oder laufenden Vorgang spricht, "
            "um den kompletten Sachstand zu kennen. Kann auch alle offenen Vorgänge eines Kunden "
            "oder eine Gesamt-Übersicht liefern."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vorgang_id": {
                    "type": "integer",
                    "description": "Vorgang-ID für Detailansicht (V-2026-0001 → ID aus der DB)"
                },
                "kunden_email": {
                    "type": "string",
                    "description": "Kunden-E-Mail — gibt alle offenen Vorgänge dieses Kunden zurück"
                },
            }
        }
    })

    tools.append({
        "name": "vorgang_status_setzen",
        "description": (
            "Setzt den Status eines Vorgangs (z.B. 'angebot_versendet', 'angenommen', 'abgeschlossen'). "
            "Nur erlaubte Statusübergänge sind möglich — das Tool gibt erlaubte Optionen zurück wenn "
            "ein Übergang nicht möglich ist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vorgang_id": {"type": "integer", "description": "Vorgang-ID"},
                "neuer_status": {"type": "string", "description": "Neuer Status (z.B. 'angenommen', 'abgeschlossen')"},
                "grund": {"type": "string", "description": "Grund oder Notiz zum Statuswechsel"}
            },
            "required": ["vorgang_id", "neuer_status"]
        }
    })

    # ── Microsoft Graph Kalender (Paket 8, session-oo) ───────────────────────
    tools.append({
        "name": "termin_erstellen",
        "description": (
            "Erstellt einen Termin im Microsoft Outlook-Kalender via Graph API. "
            "Nutze dieses Tool wenn der Benutzer einen Kundentermin, Baustellentermin oder Meeting eintragen moechte. "
            "Stufe B: Der Benutzer bestaetigt den Termin-Eintrag vorher. "
            "Falls die Graph-Berechtigung fehlt, gibt das Tool eine Anleitung zur Einrichtung zurueck."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "betreff":  {"type": "string", "description": "Termin-Titel"},
                "start":    {"type": "string", "description": "Start ISO-8601 'YYYY-MM-DDTHH:MM:00'"},
                "end":      {"type": "string", "description": "Ende ISO-8601 (optional, default: +1h)"},
                "ort":      {"type": "string", "description": "Ort / Adresse (optional)"},
                "notiz":    {"type": "string", "description": "Beschreibung oder Notiz (optional)"},
                "konto":    {"type": "string", "description": "E-Mail-Konto fuer den Kalender (optional)"}
            },
            "required": ["betreff", "start"]
        }
    })
    tools.append({
        "name": "termine_anzeigen",
        "description": "Zeigt Kalender-Termine der naechsten N Tage aus Outlook via Graph API.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tage":  {"type": "integer", "description": "Anzahl Tage voraus (Standard: 7)"},
                "konto": {"type": "string",  "description": "E-Mail-Konto (optional)"}
            }
        }
    })

    # ── Semantische Mail-Suche via FTS5 (Paket 7, session-oo) ────────────────
    if MAIL_INDEX_DB.exists():
        tools.append({
            "name": "semantisch_suchen",
            "description": (
                "Durchsucht alle 12.000+ Mails mit SQLite FTS5 — schneller und praeziser als mail_suchen. "
                "Findet relevante Mails nach Inhalt, Betreff und Absender mit BM25-Ranking. "
                "Bevorzuge dieses Tool gegenueber mail_suchen fuer alle inhaltlichen Mail-Suchen."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string",
                              "description": "Suchbegriff (FTS5: 'Sichtbeton Kosten' oder 'Angebot*' oder '\"genaue Phrase\"')"},
                    "limit": {"type": "integer", "description": "Max. Ergebnisse (Standard: 10)", "default": 10},
                    "konto": {"type": "string", "description": "Nur dieses Konto durchsuchen (optional)"}
                },
                "required": ["query"]
            }
        })

    # ── Vorgang-Naechste-Aktion Tool (Paket 4, session-oo) ───────────────────
    tools.append({
        "name": "vorgang_naechste_aktion_vorschlagen",
        "description": (
            "Analysiert einen offenen Vorgang und schlaegt die optimale naechste Aktion vor. "
            "Gibt erlaubte Status-Uebergaenge, Kundenhistorie und konkreten Handlungsvorschlag zurueck. "
            "Nutze dieses Tool wenn du fuer einen Vorgang nicht weisst was als naechstes zu tun ist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vorgang_id": {"type": "integer", "description": "Vorgang-ID"}
            },
            "required": ["vorgang_id"]
        }
    })

    # ── Konversations-Gedaechtnis Tool (Paket 3, session-oo) ─────────────────
    tools.append({
        "name": "konversation_suchen",
        "description": (
            "Sucht in frueheren Kira-Gespraechen nach einem Begriff, Kunden oder Thema. "
            "Nutze dieses Tool wenn der Benutzer fragt 'haben wir damals ueber X gesprochen?' oder "
            "wenn du Kontext aus frueheren Gespraechen brauchst. "
            "Gibt die relevantesten Gespraechs-Ausschnitte zurueck (max 5 Sessions)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Suchbegriff — in Gespraechen suchen (Name, Thema, Stichwort)"},
                "seit_tagen": {"type": "integer", "description": "Nur Gespraeche der letzten N Tage (optional, Standard: alle)", "default": 0}
            },
            "required": ["query"]
        }
    })

    # ── Mail-Senden Tool (Paket 2, session-oo) ────────────────────────────────
    tools.append({
        "name": "mail_senden",
        "description": (
            "Erstellt einen Mail-Entwurf und legt ihn zur Freigabe vor (HITL-Gate). "
            "Die Mail wird NICHT sofort gesendet — Der Benutzer muss sie im Dashboard bestätigen. "
            "Nutze dieses Tool wenn du eine Antwort, Nachfass-Mail oder Mahnung verfassen sollst. "
            "Gibt eine Vorschau des Entwurfs zurück."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "an": {"type": "string", "description": "Empfänger E-Mail-Adresse"},
                "betreff": {"type": "string", "description": "E-Mail Betreff"},
                "text": {"type": "string", "description": "Mail-Text (Plain-Text)"},
                "konto": {"type": "string", "description": "Absender-Konto (z.B. 'info@raumkult.eu') — optional, Standard-Konto wird verwendet"},
                "in_antwort_auf_message_id": {"type": "string", "description": "Message-ID der Mail auf die geantwortet wird (optional)"},
                "task_id": {"type": "integer", "description": "Verknüpfter Task (optional)"},
                "vorgang_id": {"type": "integer", "description": "Verknüpfter Vorgang (optional)"}
            },
            "required": ["an", "betreff", "text"]
        }
    })

    # ── Lexware Office Tools (session-eee) ───────────────────────────────────
    try:
        from lexware_client import is_lexware_configured
        _lex_ok = is_lexware_configured(config)
    except Exception:
        _lex_ok = False
    if _lex_ok:
        tools.append({
            "name": "lexware_belege_laden",
            "description": (
                "Laedt aktuelle Belege (Rechnungen, Angebote, Eingangsrechnungen) aus Lexware Office. "
                "Nutze dieses Tool wenn der Benutzer nach Rechnungen, Debitoren oder Zahlungsstaenden fragt. "
                "Gibt offene Posten, faellige Betraege und letzte Sync-Zeit zurueck."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "typ": {
                        "type": "string",
                        "enum": ["invoice", "quotation", "purchase_invoice", "alle"],
                        "description": "Belegtyp (Standard: alle)"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["open", "paidoff", "voided", "overdue", "alle"],
                        "description": "Belegstatus (Standard: open)"
                    },
                    "limit": {"type": "integer", "description": "Max. Anzahl Belege (Standard: 20)"}
                }
            }
        })
        tools.append({
            "name": "lexware_eingangsbeleg_klassifizieren",
            "description": (
                "Klassifiziert einen Eingangsbeleg in der Buchhaltungs-Pruefqueue: "
                "setzt Konto-Vorschlag, Steuer-Typ und Status. "
                "Nutze dieses Tool wenn der Benutzer einen Eingangsbeleg manuell oder automatisch einordnen moechte."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "beleg_id": {"type": "integer", "description": "ID des Eingangsbellegs in der Pruefqueue"},
                    "konto_vorschlag": {"type": "string", "description": "Buchungskonto-Bezeichnung (z.B. 'Buerokosten')"},
                    "konto_nummer": {"type": "string", "description": "SKR04-Kontonummer (z.B. '4930')"},
                    "steuer_typ": {"type": "string", "description": "z.B. '19%', '7%', 'steuerfrei'"},
                    "beleg_text": {"type": "string", "description": "Buchungstext fuer Lexware"},
                    "status": {
                        "type": "string",
                        "enum": ["klassifiziert", "abgelegt", "unklar"],
                        "description": "Neuer Status nach Klassifizierung"
                    }
                },
                "required": ["beleg_id", "status"]
            }
        })

    # Capture / Mobile Memo Tools (session-hhh)
    tools.append({
        "name": "capture_suchen",
        "description": (
            "Sucht in Capture-Eintraegen (Schnellerfassungen, Memos, Fotos, Baustellennotizen). "
            "Nutze dieses Tool wenn der Benutzer nach einem frueheren Memo sucht oder fragt ob etwas erfasst wurde."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "suchbegriff": {"type": "string", "description": "Freitext-Suchbegriff"},
                "status": {
                    "type": "string",
                    "enum": ["eingegangen", "pruefung", "zugeordnet", "erledigt", "alle"],
                    "description": "Status-Filter (Standard: alle offenen)"
                },
                "limit": {"type": "integer", "description": "Max. Anzahl Ergebnisse (Standard: 10)"}
            },
            "required": []
        }
    })
    tools.append({
        "name": "capture_zuordnen",
        "description": (
            "Ordnet einen Capture-Eintrag einem Objekt im System zu: Vorgang, Kunde, Rechnung, Angebot, Aufgabe, Wissen. "
            "Nutze dieses Tool wenn Kira einen Capture-Eintrag einem bekannten Kontext zuordnen soll."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "capture_id": {"type": "integer", "description": "ID des Capture-Eintrags"},
                "entity_type": {
                    "type": "string",
                    "description": "Typ: vorgang, kunde, rechnung, angebot, aufgabe, wissen, lexware_kontakt"
                },
                "entity_id": {"type": "string", "description": "ID oder Nummer des Zielobjekts"},
                "begruendung": {"type": "string", "description": "Kurze Begruendung fuer die Zuordnung"}
            },
            "required": ["capture_id", "entity_type", "entity_id"]
        }
    })

    # ── Dokument-Tools (session-eeee) ──
    tools.append({
        "name": "dokument_suchen",
        "description": (
            "Sucht in Dokumenten (PDFs, Rechnungen, Angebote, Verträge, Briefe, Scans). "
            "Nutze dieses Tool wenn der Benutzer nach einem Dokument sucht oder wissen will welche Dokumente vorliegen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "suchbegriff": {"type": "string", "description": "Freitext-Suchbegriff"},
                "status": {
                    "type": "string",
                    "enum": ["neu", "zugeordnet", "in_bearbeitung", "archiviert", "entwurf", "alle"],
                    "description": "Status-Filter"
                },
                "kategorie": {"type": "string", "description": "Kategorie: rechnung, angebot, mahnung, vertrag, brief, sonstiges"},
                "limit": {"type": "integer", "description": "Max. Anzahl Ergebnisse (Standard: 10)"}
            },
            "required": []
        }
    })
    tools.append({
        "name": "dokument_erstellen",
        "description": (
            "Erstellt ein neues Dokument im Dokument-Studio. "
            "Nutze dieses Tool wenn der Benutzer ein Schreiben, eine Mahnung, ein Angebot oder ein anderes Dokument erstellen möchte."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "titel": {"type": "string", "description": "Titel des Dokuments"},
                "kategorie": {
                    "type": "string",
                    "enum": ["brief", "rechnung", "angebot", "mahnung", "anschreiben", "memo", "protokoll", "auswertung", "frei"],
                    "description": "Dokumentkategorie"
                },
                "inhalt": {"type": "string", "description": "HTML-Inhalt des Dokuments"},
                "vorgang_id": {"type": "integer", "description": "Vorgang-ID für die Zuordnung"}
            },
            "required": ["titel"]
        }
    })
    tools.append({
        "name": "dokument_zuordnen",
        "description": (
            "Ordnet ein Dokument einem Vorgang zu. "
            "Nutze dieses Tool wenn ein Dokument einem bestimmten Geschäftsvorgang zugewiesen werden soll."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dokument_id": {"type": "integer", "description": "ID des Dokuments"},
                "vorgang_id": {"type": "integer", "description": "ID des Vorgangs"}
            },
            "required": ["dokument_id", "vorgang_id"]
        }
    })

    return tools


def _tools_to_openai(tools):
    """Konvertiert Anthropic-Format Tools nach OpenAI Function-Calling Format."""
    return [{
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"]
        }
    } for t in tools]


def _tools_to_prompt(tools):
    """Baut Tool-Beschreibungen als Text für Provider ohne Tool-Support."""
    lines = ["Du hast folgende Werkzeuge. Wenn du eines nutzen willst, antworte EXAKT im Format:",
             '{"tool": "TOOL_NAME", "params": {PARAMETER}}',
             "Werkzeuge:"]
    for t in tools:
        params = ", ".join(f'{k} ({v.get("type","")})' for k, v in t["input_schema"].get("properties", {}).items())
        lines.append(f'- {t["name"]}: {t["description"]} — Parameter: {params}')
    return "\n".join(lines)


# ── Tool-Ausführung ──────────────────────────────────────────────────────────
def execute_tool(name, params):
    t0 = time.monotonic()
    try:
        handlers = {
            "rechnung_bezahlt": _tool_rechnung_bezahlt,
            "angebot_status": _tool_angebot_status,
            "eingangsrechnung_erledigt": _tool_eingangsrechnung_erledigt,
            "kunde_nachschlagen": _tool_kunde_nachschlagen,
            "nachfass_email_entwerfen": _tool_nachfass_email,
            "wissen_verwalten": _tool_wissen_verwalten,
            "wissen_speichern": _tool_wissen_verwalten,  # Legacy-Alias
            "korrektur": _tool_korrektur,
            "mail_korrektur": _tool_korrektur,  # Legacy-Alias
            "task_erstellen": _tool_task_erstellen,
            "task_bearbeiten": _tool_task_bearbeiten,
            "rechnungsdetails_abrufen": _tool_rechnungsdetails,
            "angebot_pruefen": _tool_angebot_pruefen,
            "web_recherche": _tool_web_recherche,
            "duplikate_suchen": _tool_duplikate_suchen,
            "tasks_loeschen": _tool_tasks_loeschen,
            "task_erledigen": _tool_task_erledigen,
            "runtime_log_suchen": _tool_runtime_log_suchen,
            "mail_suchen": _tool_mail_suchen,
            "mail_lesen": _tool_mail_lesen,
            "vorgang_kontext_laden": _tool_vorgang_kontext_laden,
            "vorgang_status_setzen": _tool_vorgang_status_setzen,
            "termin_erstellen": _tool_termin_erstellen,
            "termine_anzeigen": _tool_termine_anzeigen,
            "semantisch_suchen": _tool_semantisch_suchen,
            "vorgang_naechste_aktion_vorschlagen": _tool_vorgang_naechste_aktion_vorschlagen,
            "konversation_suchen": _tool_konversation_suchen,
            "mail_senden": _tool_mail_senden,
            "lexware_belege_laden": _tool_lexware_belege_laden,
            "lexware_eingangsbeleg_klassifizieren": _tool_lexware_eingangsbeleg_klassifizieren,
            "capture_suchen": _tool_capture_suchen,
            "capture_zuordnen": _tool_capture_zuordnen,
            "dokument_suchen": _tool_dokument_suchen,
            "dokument_erstellen": _tool_dokument_erstellen,
            "dokument_zuordnen": _tool_dokument_zuordnen,
        }
        handler = handlers.get(name)
        if not handler:
            _alog("Kira", f"Tool: {name}", "Unbekanntes Tool", "fehler", fehler=f"Unbekanntes Tool: {name}")
            _elog("kira", f"tool_unknown", f"Unbekanntes Tool: {name}",
                  source="kira_llm", modul="kira", submodul="tools",
                  actor_type="kira", status="fehler",
                  error_message=f"Unbekanntes Tool: {name}")
            return {"error": f"Unbekanntes Tool: {name}"}
        result = handler(params)
        ms = int((time.monotonic() - t0) * 1000)
        details = str(params)[:120] if params else ""
        if result.get("error"):
            _alog("Kira", f"Tool: {name}", details, "fehler", fehler=str(result.get("error",""))[:300], dauer_ms=ms)
            _elog("kira", f"tool_called", f"Tool {name} fehlgeschlagen",
                  source="kira_llm", modul="kira", submodul="tools",
                  actor_type="kira", status="fehler", duration_ms=ms,
                  error_message=str(result.get("error",""))[:500],
                  context_snapshot=params,
                  entity_snapshot=result)
        else:
            _alog("Kira", f"Tool: {name}", details, "ok", dauer_ms=ms)
            _elog("kira", "tool_called", f"Tool {name}: {str(result.get('message','ok'))[:120]}",
                  source="kira_llm", modul="kira", submodul="tools",
                  actor_type="kira", status="ok", duration_ms=ms,
                  result=str(result.get("message",""))[:200],
                  context_snapshot=params,
                  entity_snapshot=result)
        return result
    except Exception as e:
        ms = int((time.monotonic() - t0) * 1000)
        _alog("Kira", f"Tool: {name}", "", "fehler", fehler=str(e)[:300], dauer_ms=ms)
        _elog("kira", "tool_exception", f"Tool {name} Exception: {str(e)[:200]}",
              source="kira_llm", modul="kira", submodul="tools",
              actor_type="kira", status="fehler", duration_ms=ms,
              error_message=str(e)[:500],
              context_snapshot=params)
        return {"error": str(e)}


def _tool_rechnung_bezahlt(p):
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    rid = p["rechnung_id"]
    now = datetime.now().isoformat()
    row = db.execute("SELECT * FROM ausgangsrechnungen WHERE id=?", (rid,)).fetchone()
    if not row:
        db.close()
        return {"error": f"Rechnung #{rid} nicht gefunden"}
    re_nr = row['re_nummer']
    kunde = row['kunde_name'] or row['kunde_email'] or 'Unbekannt'
    betrag_orig = row['betrag_brutto'] or 0
    # Idempotenz-Check (Paket 1, session-oo)
    if row['status'] == 'bezahlt':
        db.close()
        _elog("kira", "tool_idempotent_skip", f"rechnung_bezahlt: RE {re_nr} war bereits bezahlt",
              modul="kira_llm", source="kira_llm", actor_type="kira", status="ok")
        return {"ok": True, "message": f"Rechnung {re_nr} war bereits als bezahlt markiert.", "idempotent": True}
    db.execute("UPDATE ausgangsrechnungen SET status='bezahlt', bezahlt_am=?, notiz=? WHERE id=?",
               (p["bezahlt_am"], p.get("notiz", ""), rid))
    tage = None
    try:
        d1 = datetime.strptime(str(row['datum'])[:10], "%Y-%m-%d")
        d2 = datetime.strptime(p["bezahlt_am"][:10], "%Y-%m-%d")
        tage = (d2 - d1).days
    except: pass
    daten = {**p, "zeitstempel": now, "re_nummer": re_nr, "kunde": kunde, "zahlungsdauer_tage": tage}
    db.execute("INSERT INTO geschaeft_statistik (typ,referenz_id,ereignis,daten_json,erstellt_am) VALUES (?,?,?,?,?)",
               ('ausgangsrechnung', rid, 'status_bezahlt', json.dumps(daten, ensure_ascii=False), now))
    wissen = f"Rechnung {re_nr} ({kunde}) am {p['bezahlt_am']} bezahlt."
    if tage is not None:
        wissen += f" Zahlungsdauer: {tage} Tage."
    if not p.get("voller_betrag") and p.get("betrag"):
        _bo = f"{betrag_orig:.2f}".replace('.', ',')
        wissen += f" Reduzierter Betrag: {p['betrag']} EUR (statt {_bo} EUR)."
    if p.get("notiz"):
        wissen += f" {p['notiz']}"
    db.execute("INSERT INTO wissen_regeln (kategorie,titel,inhalt,quelle,erstellt_am) VALUES (?,?,?,?,?)",
               ('gelernt', f'{re_nr} ({kunde}): bezahlt', wissen, 'Kira-Chat', now))
    db.commit()
    db.close()
    result = f"Rechnung {re_nr} als bezahlt markiert (am {p['bezahlt_am']})."
    if tage is not None:
        result += f" Zahlungsdauer: {tage} Tage."
    return {"ok": True, "message": result}


def _tool_angebot_status(p):
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    aid = p["angebot_id"]
    now = datetime.now().isoformat()
    row = db.execute("SELECT * FROM angebote WHERE id=?", (aid,)).fetchone()
    if not row:
        db.close()
        return {"error": f"Angebot #{aid} nicht gefunden"}
    a_nr = row['a_nummer']
    kunde = row['kunde_name'] or row['kunde_email'] or 'Unbekannt'
    new_status = p["status"]
    # Idempotenz-Check (Paket 1, session-oo)
    if row['status'] == new_status:
        db.close()
        _elog("kira", "tool_idempotent_skip", f"angebot_status: Angebot {a_nr} war bereits '{new_status}'",
              modul="kira_llm", source="kira_llm", actor_type="kira", status="ok")
        return {"ok": True, "message": f"Angebot {a_nr} war bereits als '{new_status}' markiert.", "idempotent": True}
    db.execute("UPDATE angebote SET status=? WHERE id=?", (new_status, aid))
    if new_status == 'abgelehnt' and p.get("grund"):
        db.execute("UPDATE angebote SET grund_abgelehnt=? WHERE id=?", (p["grund"], aid))
    elif new_status == 'angenommen' and p.get("grund"):
        db.execute("UPDATE angebote SET grund_angenommen=? WHERE id=?", (p["grund"], aid))
    daten = {**p, "zeitstempel": now, "a_nummer": a_nr, "kunde": kunde}
    db.execute("INSERT INTO geschaeft_statistik (typ,referenz_id,ereignis,daten_json,erstellt_am) VALUES (?,?,?,?,?)",
               ('angebot', aid, f'status_{new_status}', json.dumps(daten, ensure_ascii=False), now))
    wissen = f"Angebot {a_nr} ({kunde}): {new_status}."
    if p.get("grund"):
        wissen += f" Grund: {p['grund']}"
    db.execute("INSERT INTO wissen_regeln (kategorie,titel,inhalt,quelle,erstellt_am) VALUES (?,?,?,?,?)",
               ('gelernt', f'{a_nr} ({kunde}): {new_status}', wissen, 'Kira-Chat', now))
    db.commit()
    db.close()
    return {"ok": True, "message": f"Angebot {a_nr} als '{new_status}' markiert."}


def _tool_eingangsrechnung_erledigt(p):
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    gid = p["geschaeft_id"]
    now = datetime.now().isoformat()
    row = db.execute("SELECT * FROM geschaeft WHERE id=?", (gid,)).fetchone()
    if not row:
        db.close()
        return {"error": f"Geschäftsvorgang #{gid} nicht gefunden"}
    partner = row['gegenpartei'] or row['gegenpartei_email'] or 'Unbekannt'
    # Idempotenz-Check (Paket 1, session-oo)
    if row['bewertung'] == 'erledigt':
        db.close()
        _elog("kira", "tool_idempotent_skip", f"eingangsrechnung_erledigt: Vorgang #{gid} war bereits erledigt",
              modul="kira_llm", source="kira_llm", actor_type="kira", status="ok")
        return {"ok": True, "message": f"Eingangsrechnung von {partner} war bereits als erledigt markiert.", "idempotent": True}
    db.execute("UPDATE geschaeft SET bewertung='erledigt', bewertung_grund=? WHERE id=?",
               (f"bezahlt am {p['bezahlt_am']}. {p.get('notiz','')}".strip(), gid))
    daten = {**p, "zeitstempel": now, "partner": partner}
    db.execute("INSERT INTO geschaeft_statistik (typ,referenz_id,ereignis,daten_json,erstellt_am) VALUES (?,?,?,?,?)",
               ('geschaeft', gid, 'erledigt', json.dumps(daten, ensure_ascii=False), now))
    db.execute("INSERT INTO wissen_regeln (kategorie,titel,inhalt,quelle,erstellt_am) VALUES (?,?,?,?,?)",
               ('gelernt', f'Eingangsrechnung {partner}: erledigt',
                f"Bezahlt am {p['bezahlt_am']}. {p.get('notiz','')}", 'Kira-Chat', now))
    db.commit()
    db.close()
    return {"ok": True, "message": f"Eingangsrechnung von {partner} als erledigt markiert."}


def _tool_kunde_nachschlagen(p):
    suchbegriff = p["suchbegriff"].lower()
    results = []
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    for table, fields in [
        ("ausgangsrechnungen", "re_nummer, kunde_name, kunde_email, betrag_brutto, status, datum"),
        ("angebote", "a_nummer, kunde_name, kunde_email, status, datum"),
    ]:
        try:
            for r in db.execute(f"SELECT {fields} FROM {table} WHERE LOWER(kunde_name) LIKE ? OR LOWER(kunde_email) LIKE ?",
                                (f'%{suchbegriff}%', f'%{suchbegriff}%')):
                results.append(dict(r))
        except: pass
    db.close()
    try:
        kdb = sqlite3.connect(str(KUNDEN_DB))
        kdb.row_factory = sqlite3.Row
        for r in kdb.execute("SELECT DISTINCT absender_name, absender_email, COUNT(*) as interaktionen FROM interaktionen WHERE LOWER(absender_name) LIKE ? OR LOWER(absender_email) LIKE ? GROUP BY absender_email",
                             (f'%{suchbegriff}%', f'%{suchbegriff}%')):
            results.append({"name": r['absender_name'], "email": r['absender_email'], "interaktionen": r['interaktionen']})
        kdb.close()
    except: pass
    if not results:
        return {"message": f"Kein Kunde gefunden für '{p['suchbegriff']}'"}
    return {"kunden": results, "anzahl": len(results)}


def _tool_nachfass_email(p):
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT * FROM angebote WHERE id=?", (p["angebot_id"],)).fetchone()
    db.close()
    if not row:
        return {"error": f"Angebot #{p['angebot_id']} nicht gefunden"}
    try:
        from response_gen import generate_nachfass
        stufe = {"freundlich": 1, "bestimmt": 2, "letzte_chance": 3}.get(p.get("ton", "freundlich"), 1)
        entwurf = generate_nachfass(stufe, row['a_nummer'], row['kunde_name'] or 'Kunde',
                                     row['kunde_email'] or '', row['betreff'] or '')
        return {"entwurf": entwurf, "an": row['kunde_email'], "angebot": row['a_nummer']}
    except Exception as e:
        return {"error": f"Nachfass-Generierung fehlgeschlagen: {e}"}


def _tool_wissen_verwalten(p):
    """Erstellt, bearbeitet oder deaktiviert Wissensregeln."""
    aktion = p.get("aktion", "erstellen")  # Legacy-Kompatibilität: ohne aktion = erstellen
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    now = datetime.now().isoformat()
    try:
        if aktion == "erstellen":
            titel = p.get("titel", "")
            inhalt = p.get("inhalt", "")
            kategorie = p.get("kategorie", "gelernt")
            if not titel or not inhalt:
                return {"ok": False, "error": "titel und inhalt sind Pflicht bei erstellen"}
            status = p.get("status", "aktiv")
            db.execute(
                "INSERT INTO wissen_regeln (kategorie,titel,inhalt,quelle,erstellt_am,status) VALUES (?,?,?,?,?,?)",
                (kategorie, titel, inhalt, 'Kira-Chat', now, status))
            db.commit()
            return {"ok": True, "message": f"Erkenntnis gespeichert: {titel}"}

        elif aktion == "bearbeiten":
            regel_id = p.get("regel_id")
            if not regel_id:
                return {"ok": False, "error": "regel_id ist Pflicht bei bearbeiten"}
            row = db.execute("SELECT * FROM wissen_regeln WHERE id=?", (regel_id,)).fetchone()
            if not row:
                return {"ok": False, "error": f"Regel {regel_id} nicht gefunden"}
            updates = []
            vals = []
            for feld in ("titel", "inhalt", "kategorie", "status"):
                if p.get(feld):
                    updates.append(f"{feld}=?")
                    vals.append(p[feld])
            if not updates:
                return {"ok": False, "error": "Keine Felder zum Aktualisieren angegeben"}
            vals.append(regel_id)
            db.execute(f"UPDATE wissen_regeln SET {','.join(updates)} WHERE id=?", vals)
            db.commit()
            return {"ok": True, "message": f"Regel #{regel_id} aktualisiert: {', '.join(updates)}"}

        elif aktion == "deaktivieren":
            regel_id = p.get("regel_id")
            if not regel_id:
                return {"ok": False, "error": "regel_id ist Pflicht bei deaktivieren"}
            row = db.execute("SELECT id, titel FROM wissen_regeln WHERE id=?", (regel_id,)).fetchone()
            if not row:
                return {"ok": False, "error": f"Regel {regel_id} nicht gefunden"}
            db.execute("UPDATE wissen_regeln SET status='inaktiv' WHERE id=?", (regel_id,))
            db.commit()
            return {"ok": True, "message": f"Regel #{regel_id} deaktiviert: {row['titel']}"}

        else:
            return {"ok": False, "error": f"Unbekannte Aktion: {aktion}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        db.close()


def _tool_rechnungsdetails(p):
    try:
        ddb = sqlite3.connect(str(DETAIL_DB))
        ddb.row_factory = sqlite3.Row
        row = ddb.execute("SELECT * FROM rechnungen_detail WHERE re_nummer=?", (p["re_nummer"],)).fetchone()
        if not row:
            ddb.close()
            return {"error": f"Rechnung {p['re_nummer']} nicht in Detail-DB"}
        result = dict(row)
        if result.get("positionen_json"):
            result["positionen"] = json.loads(result["positionen_json"])
            del result["positionen_json"]
        result.pop("roh_text", None)
        mahnungen = [dict(r) for r in ddb.execute("SELECT typ, stufe, datum, betrag FROM mahnungen_detail WHERE re_nummer=?", (p["re_nummer"],))]
        if mahnungen:
            result["mahnungen"] = mahnungen
        ddb.close()
        return result
    except Exception as e:
        return {"error": str(e)}


def _tool_angebot_pruefen(p):
    """Prüft Status eines Angebots via angebote_tracker."""
    a_nr = p.get("a_nummer", "")
    if not a_nr:
        return {"error": "Keine Angebotsnummer angegeben"}
    try:
        from angebote_tracker import find_angebot_responses, classify_response_llm, suggest_next_action
        import sqlite3
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        ang = db.execute("SELECT * FROM angebote WHERE a_nummer=?", (a_nr,)).fetchone()
        db.close()
        if not ang:
            return {"error": f"Angebot {a_nr} nicht gefunden"}

        responses = find_angebot_responses(a_nr, ang['kunde_email'] or "", ang['datum'] or "")
        result = {"a_nummer": a_nr, "kunde": ang['kunde_name'], "betrag": ang['betrag_geschaetzt'],
                  "status": ang['status'], "datum": ang['datum'], "nachfass_count": ang['nachfass_count'] or 0,
                  "antworten_gefunden": len(responses)}
        if responses:
            best = responses[0]
            cl = classify_response_llm(a_nr, best.get('text_plain', ''), best.get('betreff', ''))
            result["letzte_antwort"] = {"betreff": best.get('betreff', ''), "datum": best.get('datum', ''),
                                         "klassifizierung": cl}
        if ang['status'] == 'offen' and ang['datum']:
            from datetime import datetime
            try:
                tage = (datetime.now().date() - datetime.strptime(ang['datum'][:10], "%Y-%m-%d").date()).days
                action = suggest_next_action(dict(ang), tage, ang['nachfass_count'] or 0)
                if action:
                    result["vorschlag"] = action
                result["tage_offen"] = tage
            except: pass
        return result
    except Exception as e:
        return {"error": str(e)}


def _tool_web_recherche(p):
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(p["query"], max_results=p.get("max_results", 3)))
        return {"ergebnisse": [{"titel": r["title"], "url": r["href"], "text": r["body"][:200]} for r in results]}
    except ImportError:
        return {"error": "duckduckgo-search nicht installiert (pip install duckduckgo-search)"}
    except Exception as e:
        return {"error": f"Suche fehlgeschlagen: {e}"}


def _tool_duplikate_suchen(p):
    """Findet Cluster ähnlicher Mails in tasks.db (gleicher Betreff + Body, unterschiedliche Anhangzahl)."""
    import difflib, json as _json
    min_sim = float(p.get("min_aehnlichkeit", 0.75))
    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute("""SELECT id, betreff, beschreibung, kunden_email, konto,
                                    anhaenge_pfad, datum_mail, kategorie
                             FROM tasks WHERE status='offen'
                             ORDER BY datum_mail DESC LIMIT 200""").fetchall()
    finally:
        db.close()

    if not rows:
        return {"cluster": [], "hinweis": "Keine offenen Tasks gefunden."}

    def _norm(s):
        import re as _re
        return _re.sub(r'\s+', ' ', (s or '').strip().lower())

    def _anhang_count(pfad):
        if not pfad: return 0
        try:
            from pathlib import Path as _P
            d = _P(pfad)
            if d.is_dir():
                return len([f for f in d.iterdir() if f.suffix.lower() in
                             ('.pdf','.png','.jpg','.jpeg','.xlsx','.docx','.zip')])
        except Exception:
            pass
        return 1 if pfad else 0

    tasks = [dict(r) for r in rows]
    used = set()
    clusters = []

    for i, t1 in enumerate(tasks):
        if t1['id'] in used:
            continue
        b1 = _norm(t1.get('betreff', ''))
        cluster = [t1]
        for j, t2 in enumerate(tasks):
            if i == j or t2['id'] in used:
                continue
            b2 = _norm(t2.get('betreff', ''))
            sim = difflib.SequenceMatcher(None, b1, b2).ratio()
            if sim >= min_sim:
                cluster.append(t2)

        if len(cluster) < 2:
            continue

        for t in cluster:
            used.add(t['id'])

        # Analyse: Anhangzahlen pro Task
        cluster_info = []
        for t in cluster:
            ac = _anhang_count(t.get('anhaenge_pfad', ''))
            cluster_info.append({
                "id": t['id'],
                "betreff": (t.get('betreff') or '')[:80],
                "konto": t.get('konto', ''),
                "datum": (t.get('datum_mail') or '')[:10],
                "anhaenge": ac,
                "kategorie": t.get('kategorie', ''),
            })

        cluster_info.sort(key=lambda x: x['anhaenge'], reverse=True)
        max_anh = cluster_info[0]['anhaenge']
        rest_ids = [c['id'] for c in cluster_info[1:]]

        clusters.append({
            "cluster_groesse": len(cluster_info),
            "betreff": cluster_info[0]['betreff'],
            "original_verdacht": cluster_info[0],
            "duplikate_verdacht": cluster_info[1:],
            "empfehlung": (
                f"1 Mail mit {max_anh} Anhängen ist vermutlich das Original. "
                f"{len(rest_ids)} Mails mit je weniger Anhängen sind mögliche Duplikate. "
                f"Duplikat-IDs: {rest_ids}"
            ) if max_anh > 1 else (
                f"{len(cluster_info)} Mails mit sehr ähnlichem Betreff. IDs: {[c['id'] for c in cluster_info]}"
            )
        })

    if not clusters:
        return {"cluster": [], "hinweis": f"Keine Duplikat-Cluster gefunden (Schwellwert: {min_sim:.0%})."}
    return {"cluster": clusters, "gesamt_cluster": len(clusters)}


def _tool_task_erstellen(p):
    """Erstellt eine neue Aufgabe in der tasks-Tabelle."""
    betreff = p.get("betreff", "")
    if not betreff:
        return {"ok": False, "error": "betreff ist Pflicht"}
    kategorie = p.get("kategorie", "Sonstiger Vorgang")
    zusammenfassung = p.get("zusammenfassung", "")
    prioritaet = p.get("prioritaet", "mittel")
    deadline = p.get("deadline", "")
    kanal = p.get("kanal", "chat")
    now = datetime.now().isoformat()
    try:
        db = sqlite3.connect(str(TASKS_DB))
        cur = db.execute(
            "INSERT INTO tasks (betreff, zusammenfassung, kategorie, prioritaet, deadline, kanal, erstellt_am, status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (betreff, zusammenfassung, kategorie, prioritaet, deadline or None, kanal, now, "offen"))
        task_id = cur.lastrowid
        db.commit()
        db.close()
        return {
            "ok": True,
            "task_id": task_id,
            "message": f"Aufgabe #{task_id} erstellt: {betreff}"
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _tool_task_bearbeiten(p):
    """Ändert Felder einer bestehenden Aufgabe."""
    task_id = p.get("task_id")
    if not task_id:
        return {"ok": False, "error": "task_id ist Pflicht"}
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT id, betreff FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            db.close()
            return {"ok": False, "error": f"Task {task_id} nicht gefunden"}
        updates = []
        vals = []
        for feld in ("betreff", "zusammenfassung", "kategorie", "prioritaet", "deadline"):
            if p.get(feld):
                updates.append(f"{feld}=?")
                vals.append(p[feld])
        if not updates:
            db.close()
            return {"ok": False, "error": "Keine Felder zum Aktualisieren angegeben"}
        vals.append(task_id)
        db.execute(f"UPDATE tasks SET {','.join(updates)} WHERE id=?", vals)
        db.commit()
        db.close()
        return {"ok": True, "message": f"Task #{task_id} aktualisiert: {', '.join(f.split('=')[0] for f in updates)}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _ensure_corrections_columns():
    """Stellt sicher, dass corrections-Tabelle die neuen Spalten hat."""
    try:
        db = sqlite3.connect(str(TASKS_DB))
        cols = [r[1] for r in db.execute("PRAGMA table_info(corrections)").fetchall()]
        if "entitaet_typ" not in cols:
            db.execute("ALTER TABLE corrections ADD COLUMN entitaet_typ TEXT DEFAULT 'task'")
        if "kanal" not in cols:
            db.execute("ALTER TABLE corrections ADD COLUMN kanal TEXT DEFAULT 'email'")
        db.commit()
        db.close()
    except Exception:
        pass

_corrections_cols_ensured = False

def _tool_korrektur(p):
    """Universelle Korrektur — Task, Capture, Vorgang oder Beleg."""
    global _corrections_cols_ensured
    if not _corrections_cols_ensured:
        _ensure_corrections_columns()
        _corrections_cols_ensured = True

    ent_typ = p.get("entitaet_typ", "task")
    ent_id = p.get("entitaet_id") or p.get("task_id")  # Legacy-Kompatibilität
    neue_kat = p.get("neue_kategorie", "")
    grund = p.get("grund", "")
    auch_status = p.get("auch_status", "") or p.get("auch_task_status", "")  # Legacy
    kanal = p.get("kanal", "chat")

    if not ent_id or not neue_kat:
        return {"ok": False, "error": "entitaet_id und neue_kategorie sind Pflicht"}

    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        now = datetime.now().isoformat()
        alter_typ = "unbekannt"
        label = ""

        if ent_typ == "task":
            row = db.execute("SELECT id, kategorie, betreff, message_id, zusammenfassung, absender_rolle FROM tasks WHERE id=?", (ent_id,)).fetchone()
            if not row:
                db.close()
                return {"ok": False, "error": f"Task {ent_id} nicht gefunden"}
            alter_typ = row["kategorie"] or "unbekannt"
            label = (row["betreff"] or "")[:80]
            db.execute("UPDATE tasks SET kategorie=? WHERE id=?", (neue_kat, ent_id))
            if auch_status and auch_status in ("offen", "erledigt", "ignorieren"):
                db.execute("UPDATE tasks SET status=? WHERE id=?", (auch_status, ent_id))
            # mail_index.db synchronisieren
            msgid = row["message_id"] or ""
            if msgid:
                try:
                    mi_db = sqlite3.connect(str(KNOWLEDGE_DIR / "mail_index.db"))
                    mi_db.execute("UPDATE mails SET kategorie=?, klassifiziert_am=? WHERE message_id=?",
                                  (neue_kat, now, msgid))
                    mi_db.commit()
                    mi_db.close()
                except Exception:
                    pass

        elif ent_typ == "capture":
            row = db.execute("SELECT id, kategorie, raw_text FROM captures WHERE id=?", (ent_id,)).fetchone()
            if not row:
                db.close()
                return {"ok": False, "error": f"Capture {ent_id} nicht gefunden"}
            alter_typ = row["kategorie"] or "unbekannt"
            label = (row["raw_text"] or "")[:80]
            db.execute("UPDATE captures SET kategorie=? WHERE id=?", (neue_kat, ent_id))
            if auch_status:
                db.execute("UPDATE captures SET status=? WHERE id=?", (auch_status, ent_id))

        elif ent_typ == "vorgang":
            row = db.execute("SELECT id, typ, vorgang_nr FROM vorgaenge WHERE id=?", (ent_id,)).fetchone()
            if not row:
                db.close()
                return {"ok": False, "error": f"Vorgang {ent_id} nicht gefunden"}
            alter_typ = row["typ"] or "unbekannt"
            label = row["vorgang_nr"] or f"Vorgang #{ent_id}"
            db.execute("UPDATE vorgaenge SET typ=? WHERE id=?", (neue_kat, ent_id))

        elif ent_typ == "beleg":
            row = db.execute("SELECT id, kategorie, dateiname FROM lexware_eingangsbelege WHERE id=?", (ent_id,)).fetchone()
            if not row:
                db.close()
                return {"ok": False, "error": f"Beleg {ent_id} nicht gefunden"}
            alter_typ = row["kategorie"] or "unbekannt"
            label = (row["dateiname"] or "")[:80]
            db.execute("UPDATE lexware_eingangsbelege SET kategorie=? WHERE id=?", (neue_kat, ent_id))

        else:
            db.close()
            return {"ok": False, "error": f"Unbekannter Entitätstyp: {ent_typ}"}

        # Korrektur in corrections-Tabelle (Lernbeispiel für Classifier)
        try:
            db.execute(
                "INSERT INTO corrections (task_id, alter_typ, neuer_typ, notiz, erstellt_am, entitaet_typ, kanal) "
                "VALUES (?,?,?,?,?,?,?)",
                (ent_id, alter_typ, neue_kat, grund, now, ent_typ, kanal))
        except Exception:
            pass

        # Wissensregel speichern
        if grund:
            titel = f"Korrektur: {alter_typ} → {neue_kat}"
            inhalt = f"{ent_typ.capitalize()} \"{label}\" war als '{alter_typ}' klassifiziert, korrekt ist '{neue_kat}'. Grund: {grund}"
            db.execute(
                "INSERT INTO wissen_regeln (kategorie, titel, inhalt, quelle, status, erstellt_am) VALUES (?,?,?,?,?,?)",
                ("klassifizierung", titel, inhalt, f"Kira-Chat Korrektur ({kanal})", "aktiv", now))

        db.commit()
        db.close()
        return {
            "ok": True,
            "message": f"Korrektur gespeichert: '{alter_typ}' → '{neue_kat}' ({ent_typ}). "
                       f"Wird als Lernbeispiel für zukünftige Klassifizierungen verwendet.",
            "alter_typ": alter_typ,
            "neuer_typ": neue_kat,
            "entitaet_typ": ent_typ
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _tool_task_erledigen(p):
    """Setzt Tasks auf erledigt/zur_kenntnis/ignorieren. Keine Datei-Löschung."""
    task_ids = p.get("task_ids", [])
    status   = p.get("status", "erledigt")
    notiz    = p.get("notiz", "")
    if not task_ids:
        return {"error": "Keine Task-IDs angegeben"}
    valid = {"erledigt", "zur_kenntnis", "ignorieren"}
    if status not in valid:
        return {"error": f"Ungültiger Status '{status}'. Erlaubt: {', '.join(valid)}"}

    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    now = datetime.now().isoformat()
    erledigt = []
    fehler = []
    try:
        for tid in task_ids:
            row = db.execute("SELECT id, betreff, kategorie, status FROM tasks WHERE id=?", (tid,)).fetchone()
            if not row:
                fehler.append(f"#{tid}: nicht gefunden")
                continue
            # Idempotenz-Check (Paket 1, session-oo)
            if row["status"] == status:
                erledigt.append({"id": tid, "betreff": (row["betreff"] or "")[:60], "idempotent": True})
                continue
            db.execute("UPDATE tasks SET status=? WHERE id=?", (status, tid))
            erledigt.append({"id": tid, "betreff": (row["betreff"] or "")[:60]})

        if erledigt and notiz:
            betreffs = ", ".join(f'"{e["betreff"]}"' for e in erledigt[:3])
            db.execute(
                "INSERT INTO wissen_regeln (kategorie,titel,inhalt,status,quelle,erstellt_am) VALUES (?,?,?,?,?,?)",
                ('gelernt',
                 f'Kira erledigt: {notiz[:60]}',
                 f'Kira hat {len(erledigt)} Task(s) als {status} markiert. {notiz} Beispiele: {betreffs}.',
                 'aktiv', 'Kira-Chat', now))

        db.commit()
    finally:
        db.close()

    label_map = {"erledigt": "erledigt", "zur_kenntnis": "zur Kenntnis genommen", "ignorieren": "ignoriert"}
    return {
        "ok": True,
        "erledigt": len(erledigt),
        "details": erledigt,
        "fehler": fehler,
        "message": f"{len(erledigt)} Task(s) als '{label_map.get(status, status)}' markiert."
    }


def _tool_tasks_loeschen(p):
    """Löscht Tasks inkl. Archivdatei und speichert Lernregel. Nur nach Nutzer-OK aufrufen!"""
    from pathlib import Path as _P
    ARCHIV_ROOT = _P(r"C:\Users\kaimr\OneDrive - rauMKult Sichtbeton\0001_APPS_rauMKult\Mail Archiv\Archiv")
    ALLOWED = [str(ARCHIV_ROOT), str(KNOWLEDGE_DIR)]

    task_ids = p.get("task_ids", [])
    grund    = p.get("grund", "Kira gelöscht")
    if not task_ids:
        return {"error": "Keine Task-IDs angegeben"}

    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    geloescht = []
    fehler = []
    now = datetime.now().isoformat()

    try:
        for tid in task_ids:
            try:
                row = db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
                if not row:
                    fehler.append(f"#{tid}: nicht gefunden")
                    continue
                t = dict(row)
                msgid = t.get('message_id', '') or ''
                pfad  = t.get('mail_folder_pfad', '') or ''
                betr  = t.get('betreff', '') or ''
                konto = t.get('konto', '') or ''
                absnd = t.get('kunden_email', '') or ''
                datum = t.get('datum_mail', '') or ''

                # Permanent block
                db.execute(
                    "INSERT INTO loeschhistorie (konto, absender, betreff, datum_mail, grund, message_id) "
                    "VALUES (?,?,?,?,?,?)",
                    (konto, absnd, betr, datum, f'Kira gelöscht – {grund}', msgid))

                # Archiv löschen
                archiv_ok = False
                if pfad:
                    mail_json = _P(pfad) / 'mail.json'
                    for allowed in ALLOWED:
                        if str(mail_json).startswith(allowed):
                            try:
                                if mail_json.exists():
                                    mail_json.unlink()
                                    archiv_ok = True
                            except Exception:
                                pass
                            break

                db.execute("DELETE FROM tasks WHERE id=?", (tid,))
                geloescht.append({"id": tid, "betreff": betr[:60], "archiv": archiv_ok})
            except Exception as e:
                fehler.append(f"#{tid}: {e}")

        # Lernregel
        if geloescht:
            betreffs = ", ".join(f'"{g["betreff"]}"' for g in geloescht[:3])
            db.execute(
                "INSERT INTO wissen_regeln (kategorie, titel, inhalt, status, erstellt_am) VALUES (?,?,?,?,?)",
                ('gelernt',
                 f'Kira-Löschung: {grund[:60]}',
                 f'Kira hat {len(geloescht)} Tasks gelöscht. Grund: {grund}. Beispiele: {betreffs}.',
                 'aktiv', now))

        db.commit()
    finally:
        db.close()

    return {
        "geloescht": len(geloescht),
        "details": geloescht,
        "fehler": fehler,
        "message": f"{len(geloescht)} Task(s) gelöscht, Lernregel gespeichert."
    }


def _tool_runtime_log_suchen(p):
    """Kira liest das Runtime-Ereignisprotokoll."""
    try:
        from runtime_log import eget, estats
        limit = min(int(p.get("limit", 20)), 100)
        data = eget(
            limit=limit,
            event_type=p.get("event_type") or None,
            modul=p.get("modul") or None,
            action=p.get("action") or None,
            context_type=p.get("context_type") or None,
            status=p.get("status") or None,
            search=p.get("search") or None,
        )
        entries = data.get("entries", [])
        total = data.get("total", 0)
        stats = estats()
        # Kompakte Textdarstellung für Kira
        lines = [f"Runtime-Log: {total} Eintraege gefunden (gesamt: {stats.get('total',0)}), "
                 f"davon {stats.get('heute',0)} heute, {stats.get('fehler',0)} Fehler",
                 f"Tokens gesamt heute: LLM-Events mit token_in/out in Eintraegen"]
        for e in entries:
            ts = (e.get("ts") or "")[:16]
            et = e.get("event_type","?")
            act = e.get("action","?")
            summ = e.get("summary","")
            st = e.get("status","ok")
            ctx = f" [{e['context_type']}:{e['context_id']}]" if e.get("context_type") and e.get("context_id") else ""
            tok = f" | {e['token_in']}->{e['token_out']} Tok" if e.get("token_in") else ""
            prov = f" [{e.get('provider','')}]" if e.get("provider") else ""
            line = f"{ts} [{et}] {act}{ctx}{prov}: {summ}{tok}"
            if st not in ("ok","success"): line += f" !{st}"
            lines.append(line)
        return {"ok": True, "message": "\n".join(lines), "total": total}
    except Exception as e:
        return {"error": str(e)}


def _tool_mail_suchen(p):
    """Sucht in mail_index.db nach Mails."""
    if not MAIL_INDEX_DB.exists():
        return {"error": "Mail-Archiv nicht verfügbar"}
    query  = (p.get("query") or "").strip()
    konto  = (p.get("konto") or "").strip()
    folder = (p.get("folder") or "").strip()
    limit  = min(int(p.get("limit", 20)), 100)
    if not query:
        return {"error": "Suchbegriff (query) erforderlich"}
    try:
        conn = sqlite3.connect(str(MAIL_INDEX_DB))
        conn.row_factory = sqlite3.Row
        like = f"%{query}%"
        where_parts = ["(betreff LIKE ? OR absender LIKE ? OR text_plain LIKE ?)"]
        params = [like, like, like]
        if konto:
            where_parts.append("konto LIKE ?")
            params.append(f"%{konto}%")
        if folder:
            where_parts.append("folder LIKE ?")
            params.append(f"%{folder}%")
        where = " AND ".join(where_parts)
        total = conn.execute(f"SELECT COUNT(*) FROM mails WHERE {where}", params).fetchone()[0]
        rows  = conn.execute(
            f"SELECT message_id, absender_short, absender, betreff, datum_iso, datum, "
            f"folder, hat_anhaenge, text_plain FROM mails WHERE {where} "
            f"ORDER BY datum_iso DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        conn.close()
        lines = [f"Mail-Suche '{query}': {total} Treffer (zeige {len(rows)})"]
        for r in rows:
            ab = r['absender_short'] or r['absender'] or '?'
            dt = (r['datum_iso'] or r['datum'] or '')[:16]
            anh = " [Anh]" if r['hat_anhaenge'] else ""
            prev = (r['text_plain'] or '')[:100].replace('\n', ' ')
            lines.append(f"[{r['message_id']}] {dt} | {ab[:35]} | {(r['betreff'] or '')[:60]}{anh}")
            if prev:
                lines.append(f"  → {prev}")
        return {"ok": True, "message": "\n".join(lines), "total": total}
    except Exception as e:
        return {"error": str(e)}


def _tool_mail_lesen(p):
    """Liest vollständigen Mailinhalt aus dem Archiv."""
    message_id = (p.get("message_id") or "").strip()
    if not message_id:
        return {"error": "message_id erforderlich"}
    result = mail_vollinhalt_lesen(message_id)
    if not result.get("ok"):
        return {"error": result.get("error", "Mail nicht gefunden")}
    text = result.get("text", "")
    anhaenge = result.get("anhaenge", [])
    anh_text = f"\nAnhänge: {', '.join(anhaenge)}" if anhaenge else ""
    msg = (
        f"Von: {result['absender']}\n"
        f"An: {result.get('an','')}\n"
        f"Datum: {result['datum']}\n"
        f"Betreff: {result['betreff']}{anh_text}\n\n"
        f"--- Mailinhalt ---\n{text[:15000]}"
    )
    return {"ok": True, "message": msg}


# ── Vorgang-Tools (Paket 7, session-nn) ──────────────────────────────────────

def _tool_vorgang_kontext_laden(p):
    """Lädt Vorgang-Kontext — nach ID, Kunden-E-Mail oder Gesamt-Übersicht."""
    try:
        from case_engine import get_vorgang_context, get_open_vorgaenge, get_vorgang_summary_for_kira
        vid   = p.get("vorgang_id")
        email = (p.get("kunden_email") or "").strip()

        if vid:
            ctx = get_vorgang_context(int(vid))
            v = ctx.get("vorgang")
            if not v:
                return {"error": f"Vorgang {vid} nicht gefunden"}
            lines = [
                f"Vorgang {v['vorgang_nr']} — {v['typ'].upper()} | Status: {v['status']}",
                f"Titel: {v['titel']}",
                f"Kunde: {v.get('kunden_name') or ''} <{v.get('kunden_email') or ''}>",
                f"Erstellt: {v['erstellt_am'][:10]}  Konto: {v.get('konto') or '—'}",
            ]
            history = ctx.get("status_history", [])
            if history:
                lines.append(f"\nStatusverlauf ({len(history)} Einträge):")
                for h in history[-5:]:
                    lines.append(f"  {h['geaendert_am'][:16]}: {h['von_status']} → {h['zu_status']} ({h.get('actor','?')})")
            tasks = ctx.get("tasks", [])
            if tasks:
                lines.append(f"\nVerknüpfte Tasks ({len(tasks)}):")
                for t in tasks[:5]:
                    lines.append(f"  [T{t['id']}] {t['status']} — {t['titel'][:60]}")
            links = ctx.get("links", [])
            mails = [l for l in links if l['entitaet_typ'] == 'mail']
            if mails:
                lines.append(f"\nVerknüpfte Mails: {len(mails)}")
            return {"ok": True, "message": "\n".join(lines), "kontext": ctx}

        elif email:
            vorgaenge = get_open_vorgaenge(kunden_email=email, limit=20)
            if not vorgaenge:
                return {"ok": True, "message": f"Keine offenen Vorgänge für {email}"}
            lines = [f"Offene Vorgänge für {email} ({len(vorgaenge)}):"]
            for v in vorgaenge:
                lines.append(f"  [{v['id']}] {v['vorgang_nr']} {v['typ'].upper()} | {v['status']} | {v['titel'][:50]}")
            return {"ok": True, "message": "\n".join(lines), "vorgaenge": vorgaenge}

        else:
            summary = get_vorgang_summary_for_kira(limit=10)
            return {"ok": True, "message": summary or "Keine offenen Vorgänge"}

    except Exception as e:
        return {"error": str(e)}


def _tool_vorgang_status_setzen(p):
    """Setzt den Status eines Vorgangs über die Case Engine."""
    try:
        from case_engine import update_status, get_valid_transitions, get_vorgang
        vid          = p.get("vorgang_id")
        neuer_status = (p.get("neuer_status") or "").strip()
        grund        = (p.get("grund") or "").strip()
        if not vid or not neuer_status:
            return {"error": "vorgang_id und neuer_status erforderlich"}
        v = get_vorgang(int(vid))
        if not v:
            return {"error": f"Vorgang {vid} nicht gefunden"}
        ok = update_status(int(vid), neuer_status, grund=grund, actor="kira")
        if ok:
            return {"ok": True, "message": f"Vorgang {v['vorgang_nr']}: Status → {neuer_status}"}
        erlaubt = get_valid_transitions(v["typ"], v["status"])
        return {
            "error": f"Übergang '{v['status']}' → '{neuer_status}' nicht erlaubt",
            "erlaubte_uebergaenge": erlaubt,
        }
    except Exception as e:
        return {"error": str(e)}


def _tool_termin_erstellen(p):
    """Erstellt Kalender-Termin via Microsoft Graph (Paket 8, session-oo)."""
    betreff = (p.get("betreff") or "").strip()
    start   = (p.get("start") or "").strip()
    end     = (p.get("end") or "").strip() or None
    ort     = (p.get("ort") or "").strip()
    notiz   = (p.get("notiz") or "").strip()
    konto   = (p.get("konto") or "").strip()

    if not betreff or not start:
        return {"error": "betreff und start sind erforderlich"}

    # Standard-Konto aus Config wenn nicht angegeben
    if not konto:
        try:
            cfg = get_config()
            konten = cfg.get("mail_konten", [])
            konto = konten[0]["email"] if konten else ""
        except Exception:
            pass

    if not konto:
        return {"error": "Kein E-Mail-Konto konfiguriert fuer Kalender-Zugriff"}

    try:
        from graph_calendar import erstelle_termin
        result = erstelle_termin(konto, betreff, start, end=end, ort=ort, notiz=notiz)
        if result.get("ok"):
            _elog("kira", "termin_erstellt",
                  f"Termin '{betreff}' am {start[:10]} via Graph",
                  source="kira_llm", modul="kira", submodul="tools",
                  actor_type="kira_vorschlag", status="ok")
        return result
    except Exception as e:
        return {"error": str(e)}


def _tool_termine_anzeigen(p):
    """Listet Outlook-Termine via Microsoft Graph (Paket 8, session-oo)."""
    tage  = max(1, min(int(p.get("tage") or 7), 30))
    konto = (p.get("konto") or "").strip()
    if not konto:
        try:
            cfg = get_config()
            konten = cfg.get("mail_konten", [])
            konto = konten[0]["email"] if konten else ""
        except Exception:
            pass
    if not konto:
        return {"error": "Kein E-Mail-Konto konfiguriert"}
    try:
        from graph_calendar import liste_termine
        return liste_termine(konto, tage=tage)
    except Exception as e:
        return {"error": str(e)}


def _tool_semantisch_suchen(p):
    """FTS5-Volltextsuche in Mail-Archiv mit BM25-Ranking (Paket 7, session-oo)."""
    query = (p.get("query") or "").strip()
    limit = max(1, min(int(p.get("limit") or 10), 30))
    konto = (p.get("konto") or "").strip()
    if not query:
        return {"error": "query erforderlich"}
    if not MAIL_INDEX_DB.exists():
        return {"error": "mail_index.db nicht vorhanden"}
    try:
        mdb = sqlite3.connect(str(MAIL_INDEX_DB))
        mdb.row_factory = sqlite3.Row
        # Pruefen ob FTS-Tabelle vorhanden
        has_fts = mdb.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mail_fts'"
        ).fetchone()
        if not has_fts:
            mdb.close()
            # Fallback auf LIKE-Suche
            return _tool_mail_suchen(p)

        sql_args = [query, limit]
        konto_filter = ""
        if konto:
            konto_filter = " AND m.konto=?"
            sql_args = [query] + [konto, limit]

        rows = mdb.execute(f"""
            SELECT m.message_id, m.betreff, m.absender, m.datum_iso, m.konto,
                   m.folder, m.hat_anhaenge, m.text_plain,
                   rank
            FROM mail_fts
            JOIN mails m ON mail_fts.rowid = m.id
            WHERE mail_fts MATCH ? {konto_filter}
            ORDER BY rank
            LIMIT ?
        """, sql_args).fetchall()
        mdb.close()

        results = []
        for r in rows:
            results.append({
                "message_id": r["message_id"],
                "betreff": r["betreff"],
                "absender": r["absender"],
                "datum": (r["datum_iso"] or "")[:16],
                "konto": r["konto"],
                "folder": r["folder"],
                "hat_anhaenge": bool(r["hat_anhaenge"]),
                "vorschau": (r["text_plain"] or "")[:200].replace('\n', ' '),
            })
        return {"ok": True, "query": query, "treffer": len(results), "ergebnisse": results}
    except Exception as e:
        # FTS5-Syntaxfehler -> Fallback
        try:
            return _tool_mail_suchen(p)
        except Exception:
            return {"error": str(e)}


def _tool_vorgang_naechste_aktion_vorschlagen(p):
    """Analysiert einen Vorgang und schlaegt naechste Aktion vor (Paket 4, session-oo)."""
    vid = p.get("vorgang_id")
    if not vid:
        return {"error": "vorgang_id erforderlich"}
    try:
        from case_engine import get_vorgang_context, get_valid_transitions
        ctx = get_vorgang_context(int(vid))
        if not ctx:
            return {"error": f"Vorgang {vid} nicht gefunden"}
        v         = ctx.get("vorgang", {})
        typ       = v.get("typ", "")
        status    = v.get("status", "")
        erlaubte  = get_valid_transitions(typ, status)
        # Kompakter Kontext fuer internes LLM-Reasoning
        eintraege = ctx.get("eintraege", [])
        context_summary = (
            f"Vorgang {v.get('vorgang_nr')}: {v.get('titel','')}\n"
            f"Typ: {typ} | Status: {status}\n"
            f"Kunde: {v.get('kunden_name') or v.get('kunden_email','?')}\n"
            f"Erstellt: {(v.get('erstellt_am') or '')[:10]} | "
            f"Letzte Aenderung: {(v.get('aktualisiert_am') or '')[:10]}\n"
            f"Verknuepfte Eintraege: {len(eintraege)}\n"
            f"Erlaubte Uebergaenge: {', '.join(erlaubte) if erlaubte else 'keine (abgeschlossen?)'}"
        )
        return {
            "ok": True,
            "vorgang_nr": v.get("vorgang_nr"),
            "status": status,
            "typ": typ,
            "erlaubte_uebergaenge": erlaubte,
            "kontext": context_summary,
            "empfehlung": (
                f"Naechster Schritt fuer {typ} im Status '{status}': "
                + (erlaubte[0] if erlaubte else "kein weiterer Uebergang moeglich")
            ),
        }
    except Exception as e:
        return {"error": str(e)}


def _tool_konversation_suchen(p):
    """Durchsucht kira_konversationen nach einem Suchbegriff (Paket 3, session-oo)."""
    query     = (p.get("query") or "").strip()
    seit_tage = int(p.get("seit_tagen") or 0)
    if not query:
        return {"error": "query erforderlich"}

    db = sqlite3.connect(str(TASKS_DB))
    db.row_factory = sqlite3.Row
    try:
        sql_args = [f"%{query}%"]
        date_filter = ""
        if seit_tage > 0:
            from datetime import datetime, timedelta
            cutoff = (datetime.now() - timedelta(days=seit_tage)).isoformat()
            date_filter = "AND erstellt_am >= ?"
            sql_args.append(cutoff)

        # Sessions mit Match finden
        sessions = db.execute(f"""
            SELECT DISTINCT session_id, MIN(erstellt_am) as ts
            FROM kira_konversationen
            WHERE nachricht LIKE ? {date_filter}
            ORDER BY ts DESC
            LIMIT 5
        """, sql_args).fetchall()

        if not sessions:
            db.close()
            return {"ok": True, "treffer": 0, "ergebnisse": [],
                    "message": f"Keine Gespraeche zu '{query}' gefunden."}

        results = []
        for sess in sessions:
            sid = sess["session_id"]
            ts  = (sess["ts"] or "")[:16]
            # Alle Nachrichten dieser Session die den Suchbegriff enthalten
            msgs = db.execute("""
                SELECT rolle, nachricht, erstellt_am FROM kira_konversationen
                WHERE session_id=? AND nachricht LIKE ?
                ORDER BY id
                LIMIT 3
            """, (sid, f"%{query}%")).fetchall()
            snippets = []
            for m in msgs:
                text = (m["nachricht"] or "")[:200].replace('\n', ' ')
                snippets.append(f"[{m['rolle']}] {text}")
            results.append({
                "session_id": sid[:8] + "...",
                "datum": ts,
                "treffer": len(msgs),
                "ausschnitte": snippets,
            })
        db.close()
        return {
            "ok": True,
            "query": query,
            "treffer": len(results),
            "ergebnisse": results,
        }
    except Exception as e:
        db.close()
        return {"error": str(e)}


def _tool_mail_senden(p):
    """
    Erstellt einen Mail-Entwurf in mail_approve_queue (HITL-Gate, Paket 2 session-oo).
    Die Mail wird NICHT sofort gesendet — der Benutzer muss im Dashboard bestätigen.
    """
    an      = (p.get("an") or "").strip()
    betreff = (p.get("betreff") or "").strip()
    text    = (p.get("text") or "").strip()
    konto   = (p.get("konto") or "").strip() or None
    reply_id = (p.get("in_antwort_auf_message_id") or "").strip() or None
    task_id  = p.get("task_id")
    vorgang_id = p.get("vorgang_id")

    if not an or not betreff or not text:
        return {"error": "an, betreff und text sind erforderlich"}

    # Re:-Betreff sicherstellen wenn Antwort auf bestehende Mail
    if reply_id and not betreff.lower().startswith("re:"):
        betreff = "Re: " + betreff

    from datetime import datetime, timedelta
    ablauf = (datetime.now() + timedelta(days=3)).isoformat()

    db = sqlite3.connect(str(TASKS_DB))
    try:
        cur = db.execute("""
            INSERT INTO mail_approve_queue
                (an, betreff, body_plain, konto, in_reply_to, task_id, vorgang_id,
                 erstellt_von, status, ablauf_am)
            VALUES (?,?,?,?,?,?,?,'kira','pending',?)
        """, (an, betreff, text, konto, reply_id, task_id, vorgang_id, ablauf))
        db.commit()
        queue_id = cur.lastrowid
    except Exception as e:
        db.close()
        return {"error": f"DB-Fehler: {e}"}
    db.close()

    _elog("kira", "mail_entwurf_erstellt",
          f"Mail-Entwurf #{queue_id} für {an}: {betreff[:60]}",
          modul="kira_llm", source="kira_llm", actor_type="kira_autonom", status="ok",
          entity_snapshot={"queue_id": queue_id, "an": an, "betreff": betreff})

    # Signal (Stufe B) — Toast im Dashboard
    try:
        from case_engine import create_signal
        create_signal(
            titel=f"Mail wartet auf Freigabe",
            nachricht=f"An: {an}\nBetreff: {betreff}",
            stufe="B",
            quelle="kira_tool",
            meta={"queue_id": queue_id},
        )
    except Exception:
        pass  # Signal optional — HITL-Queue ist die Hauptsache

    return {
        "ok": True,
        "queue_id": queue_id,
        "message": f"Mail-Entwurf #{queue_id} erstellt und wartet auf Freigabe im Dashboard.",
        "vorschau": {"an": an, "betreff": betreff, "text_preview": text[:200]},
    }


# ── Lexware Office Tools (session-eee) ───────────────────────────────────────

def _tool_lexware_belege_laden(p):
    """Laedt Belege aus lexware_belege (tasks.db) fuer Kira-Kontext."""
    typ    = p.get("typ", "alle")
    status = p.get("status", "open")
    limit  = int(p.get("limit", 20))
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        try:
            where_parts = []
            bind = []
            if typ and typ != "alle":
                where_parts.append("typ=?")
                bind.append(typ)
            if status and status != "alle":
                where_parts.append("status=?")
                bind.append(status)
            where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
            rows = db.execute(
                f"SELECT * FROM lexware_belege {where_sql} ORDER BY datum DESC LIMIT ?",
                bind + [limit]
            ).fetchall()
        except Exception:
            rows = []
        finally:
            db.close()

        if not rows:
            return {"ok": True, "message": "Keine Belege gefunden (oder noch kein Sync durchgefuehrt)."}

        total_offen = sum(r["brutto"] for r in rows if r["status"] == "open" and r["brutto"])
        lines = [f"Lexware Belege ({len(rows)} Eintraege, offen: {total_offen:.2f} EUR):"]
        for r in rows:
            faellig = f" | Faellig: {r['faellig']}" if r["faellig"] else ""
            lines.append(
                f"  [{r['typ'].upper()}] {r['nummer'] or r['lexware_id'][:8]} "
                f"| {r['kontakt_name'] or '?'} | {r['brutto']:.2f} EUR "
                f"| Status: {r['status']}{faellig}"
            )
        return {"ok": True, "message": "\n".join(lines), "anzahl": len(rows), "offen_eur": total_offen}
    except Exception as e:
        return {"error": str(e)}


def _tool_lexware_eingangsbeleg_klassifizieren(p):
    """Klassifiziert einen Eingangsbeleg in der Pruefqueue (tasks.db)."""
    beleg_id        = p.get("beleg_id")
    status          = p.get("status", "klassifiziert")
    konto_vorschlag = (p.get("konto_vorschlag") or "").strip()
    konto_nummer    = (p.get("konto_nummer") or "").strip()
    steuer_typ      = (p.get("steuer_typ") or "").strip()
    beleg_text      = (p.get("beleg_text") or "").strip()

    if not beleg_id:
        return {"error": "beleg_id erforderlich"}

    try:
        db = sqlite3.connect(str(TASKS_DB))
        try:
            db.execute("""
                UPDATE eingangsbelege_pruefqueue
                SET status=?, konto_vorschlag=?, konto_nummer=?,
                    steuer_typ=?, beleg_text=?, pruef_ts=datetime('now'),
                    kira_frage='Automatisch klassifiziert von Kira'
                WHERE id=?
            """, (status, konto_vorschlag, konto_nummer, steuer_typ, beleg_text, beleg_id))
            db.commit()
            updated = db.execute(
                "SELECT id, absender, betrag, betreff FROM eingangsbelege_pruefqueue WHERE id=?",
                (beleg_id,)
            ).fetchone()
        finally:
            db.close()

        if updated:
            return {
                "ok": True,
                "message": (
                    f"Eingangsbeleg #{beleg_id} klassifiziert: Status={status}, "
                    f"Konto: {konto_vorschlag} ({konto_nummer}), Steuer: {steuer_typ}"
                )
            }
        return {"error": f"Beleg #{beleg_id} nicht gefunden"}
    except Exception as e:
        return {"error": str(e)}


# ── Provider-Adapter ─────────────────────────────────────────────────────────
def _call_anthropic(provider, user_message, system_prompt, tools, max_tokens=2048, temperature=0.7):
    """Anthropic Claude API Aufruf mit Tool-Loop, Circuit Breaker und Exponential Backoff (Paket 1, session-oo)."""
    import anthropic

    provider_id = provider.get("id", "anthropic")

    # Circuit Breaker prüfen
    if _cb_is_open(provider_id):
        raise ProviderUnavailableError(f"Circuit Breaker offen für {provider_id} — warte auf Reset")

    # Rate Limit prüfen
    if not _rate_check_and_record():
        raise ProviderUnavailableError("Rate Limit erreicht (intern) — zu viele LLM-Calls pro Minute")

    key = _get_provider_key(provider)
    client = anthropic.Anthropic(api_key=key)
    model = provider.get("model", "claude-sonnet-4-20250514")

    messages = [{"role": "user", "content": user_message}]
    final_text = ""
    all_tool_results = []
    response = None

    for _ in range(5):
        # Exponential Backoff bei transienten Fehlern (max 3 Versuche: 0s, ~1s, ~3s)
        last_err = None
        for attempt in range(3):
            try:
                create_kwargs = dict(
                    model=model, max_tokens=max_tokens,
                    system=system_prompt, tools=tools, messages=messages
                )
                if temperature is not None:
                    create_kwargs["temperature"] = max(0.0, min(1.0, float(temperature)))
                response = client.messages.create(**create_kwargs)
                last_err = None
                break
            except anthropic.AuthenticationError:
                _cb_record_failure(provider_id)
                raise ProviderUnavailableError("API Key ungültig")
            except anthropic.RateLimitError:
                _cb_record_failure(provider_id)
                raise ProviderUnavailableError("Rate Limit / Guthaben leer")
            except anthropic.APIStatusError as e:
                if e.status_code in (502, 503, 529):
                    last_err = ProviderUnavailableError(f"Server überlastet ({e.status_code})")
                    if attempt < 2:
                        time.sleep((2 ** attempt) + random.random())
                        continue
                    break
                if e.status_code == 404 and "not_found_error" in str(e).lower():
                    _MODEL_CACHE.pop(provider.get("id", ""), None)
                    _auto_update_model(provider)
                    raise ModelNotFoundError(f"Modell '{model}' nicht gefunden — Auto-Update versucht")
                raise
            except Exception as e:
                if any(x in str(e).lower() for x in ("overloaded", "timeout", "connection")):
                    last_err = ProviderUnavailableError(str(e))
                    if attempt < 2:
                        time.sleep((2 ** attempt) + random.random())
                        continue
                    break
                raise
        if last_err:
            _cb_record_failure(provider_id)
            raise last_err

        has_tool_use = any(b.type == "tool_use" for b in response.content)
        for b in response.content:
            if b.type == "text":
                final_text += b.text

        if not has_tool_use:
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results_msg = []
        for b in response.content:
            if b.type == "tool_use":
                result = execute_tool(b.name, b.input)
                all_tool_results.append({"tool": b.name, "input": b.input, "result": result})
                tool_results_msg.append({
                    "type": "tool_result",
                    "tool_use_id": b.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str)
                })
        messages.append({"role": "user", "content": tool_results_msg})

    return {
        "text": final_text,
        "tools": all_tool_results,
        "tokens_in": response.usage.input_tokens if response else 0,
        "tokens_out": response.usage.output_tokens if response else 0,
    }


def _call_openai_compat(provider, user_message, system_prompt, tools, max_tokens=2048, temperature=0.7):
    """OpenAI-kompatible API (OpenAI, OpenRouter, Ollama, Custom) mit Tool-Loop."""
    import openai

    provider_id = provider.get("id", provider.get("typ", "openai"))
    if _cb_is_open(provider_id):
        raise ProviderUnavailableError(f"Circuit Breaker offen fuer {provider_id} — warte kurz")
    if not _rate_check_and_record():
        raise ProviderUnavailableError("Rate Limit erreicht (max LLM-Calls/Min) — bitte warten")

    key = _get_provider_key(provider)
    typ = provider.get("typ", "openai")
    ptype = PROVIDER_TYPES.get(typ, {})
    base_url = provider.get("base_url") or ptype.get("base_url")

    kwargs = {"api_key": key or "not-needed"}
    if base_url:
        kwargs["base_url"] = base_url
    client = openai.OpenAI(**kwargs)
    model = provider.get("model", ptype.get("default_model", "gpt-4o"))

    supports_tools = ptype.get("supports_tools", True) and provider.get("supports_tools", True)
    oai_tools = _tools_to_openai(tools) if (tools and supports_tools) else None

    sys_content = system_prompt
    if tools and not supports_tools:
        sys_content += "\n\n" + _tools_to_prompt(tools)

    # Vision-Content: Anthropic-Format → OpenAI-Format konvertieren
    oai_user_content = user_message
    if isinstance(user_message, list):
        oai_content = []
        for block in user_message:
            if isinstance(block, dict) and block.get("type") == "image":
                src = block.get("source", {})
                oai_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{src.get('media_type', 'image/jpeg')};base64,{src.get('data', '')}"}
                })
            elif isinstance(block, dict) and block.get("type") == "text":
                oai_content.append({"type": "text", "text": block["text"]})
            else:
                oai_content.append({"type": "text", "text": str(block)})
        oai_user_content = oai_content

    messages = [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": oai_user_content}
    ]

    final_text = ""
    all_tool_results = []
    response = None

    for _ in range(5):
        last_err = None
        for attempt in range(3):
            try:
                call_kwargs = {"model": model, "messages": messages, "max_tokens": max_tokens}
                if oai_tools:
                    call_kwargs["tools"] = oai_tools
                if temperature is not None:
                    call_kwargs["temperature"] = max(0.0, min(2.0, float(temperature)))
                response = client.chat.completions.create(**call_kwargs)
                last_err = None
                break
            except openai.AuthenticationError:
                raise ProviderUnavailableError("API Key ungültig")
            except openai.RateLimitError:
                raise ProviderUnavailableError("Rate Limit / Guthaben leer")
            except openai.NotFoundError:
                _MODEL_CACHE.pop(provider.get("id", ""), None)
                _auto_update_model(provider)
                raise ModelNotFoundError(f"Modell '{model}' nicht gefunden — Auto-Update versucht")
            except openai.BadRequestError as e:
                err = str(e).lower()
                if any(x in err for x in ("model_not_found", "does not exist", "unknown model", "invalid model")):
                    _MODEL_CACHE.pop(provider.get("id", ""), None)
                    _auto_update_model(provider)
                    raise ModelNotFoundError(f"Modell '{model}' ungültig — Auto-Update versucht")
                raise
            except Exception as e:
                err = str(e).lower()
                if any(x in err for x in ("overloaded", "503", "502", "timeout", "connection", "refused")):
                    last_err = ProviderUnavailableError(str(e))
                    if attempt < 2:
                        time.sleep((2 ** attempt) + random.random())
                        continue
                    break
                raise
        if last_err:
            _cb_record_failure(provider_id)
            raise last_err

        choice = response.choices[0]
        msg = choice.message

        if msg.content:
            final_text += msg.content

        if not msg.tool_calls:
            # Check for text-based tool calls (for providers without tool support)
            if not supports_tools and msg.content:
                tool_call = _parse_text_tool_call(msg.content)
                if tool_call:
                    result = execute_tool(tool_call["tool"], tool_call["params"])
                    all_tool_results.append({"tool": tool_call["tool"], "input": tool_call["params"], "result": result})
                    messages.append({"role": "assistant", "content": msg.content})
                    messages.append({"role": "user", "content": f"Tool-Ergebnis: {json.dumps(result, ensure_ascii=False, default=str)}"})
                    continue
            break

        # Process tool calls
        messages.append(msg.model_dump())
        for tc in msg.tool_calls:
            fn = tc.function
            try:
                params = json.loads(fn.arguments)
            except:
                params = {}
            result = execute_tool(fn.name, params)
            all_tool_results.append({"tool": fn.name, "input": params, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False, default=str)
            })

    usage = response.usage if response else None
    return {
        "text": final_text,
        "tools": all_tool_results,
        "tokens_in": usage.prompt_tokens if usage else 0,
        "tokens_out": usage.completion_tokens if usage else 0,
    }


def _parse_text_tool_call(text):
    """Versucht einen Tool-Call aus Freitext zu extrahieren (für Provider ohne Tool-Support)."""
    import re
    match = re.search(r'\{[^{}]*"tool"\s*:\s*"([^"]+)"[^{}]*"params"\s*:\s*(\{[^}]+\})', text)
    if match:
        try:
            return {"tool": match.group(1), "params": json.loads(match.group(2))}
        except:
            pass
    return None


# ── Klassifizierungs-Aufruf (leichter System-Prompt, Haiku) ─────────────────
def classify_direct(prompt: str, max_tokens: int = 768,
                    vision_images: list = None) -> dict:
    """
    Direkter, günstiger LLM-Aufruf für Mail-Klassifizierung + Wissen-Extraktion.
    Wählt automatisch das günstigste Modell und probiert ALLE Provider durch.
    Bei Guthaben-Leer/Fehler → nächster Provider → erst wenn ALLE scheitern: Error.
    """
    providers = get_providers()
    if not providers:
        return {"error": "Kein Provider konfiguriert", "antwort": ""}

    # Budget-Provider-Liste: günstigstes Modell pro Provider
    budget_providers = []
    for p in providers:
        typ = p.get("typ", "")
        if typ in _BUDGET_MODELS:
            bp = dict(p)
            bp["model"] = _BUDGET_MODELS[typ]
            budget_providers.append(bp)
        elif typ in ("ollama", "custom"):
            budget_providers.append(p)
        else:
            budget_providers.append(p)

    if not budget_providers:
        budget_providers = providers

    # ── Universeller System-Prompt aus config.json ──
    _classify_sys = (
        "Du bist ein E-Mail-Klassifizierer für ein geschäftliches Unternehmen. "
        "Deine Aufgabe: E-Mails in Kategorien einteilen und entscheiden ob Handlungsbedarf besteht. "
        "Du erkennst: Kundenanfragen, Leads, Angebots-Antworten, Rechnungen, Termine, Support-Anfragen, Newsletter. "
        "Bei Unsicherheit: lieber 'Antwort erforderlich' als 'Ignorieren' oder 'Zur Kenntnis'."
    )
    try:
        _cfg = json.loads(CONFIG_FILE.read_text('utf-8'))
        _firma = _cfg.get("firma_name", "")
        _branche = _cfg.get("firma_branche", "")
        _beschr = _cfg.get("firma_beschreibung", "")
        if _firma:
            _classify_sys += f" Firma: {_firma}."
        if _branche:
            _classify_sys += f" Branche: {_branche}."
        if _beschr:
            _classify_sys += f" {_beschr[:200]}"
    except Exception:
        pass

    # Vision-Content aufbereiten (Bilder + Text als Content-Block-Liste)
    user_msg = prompt
    if vision_images:
        content_blocks = []
        for img in vision_images:
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.get("media_type", "image/jpeg"),
                    "data": img["data"],
                }
            })
        content_blocks.append({"type": "text", "text": prompt})
        user_msg = content_blocks

    # Alle Provider durchprobieren (günstigste zuerst)
    errors = []
    for provider in budget_providers:
        try:
            if provider.get("typ") == "anthropic":
                result = _call_anthropic(provider, user_msg, _classify_sys, [], max_tokens=max_tokens)
            else:
                result = _call_openai_compat(provider, user_msg, _classify_sys, [], max_tokens=max_tokens)
            return {"antwort": result.get("text", ""),
                    "tokens_in":  result.get("tokens_in", 0),
                    "tokens_out": result.get("tokens_out", 0),
                    "model": provider.get("model", "?")}
        except Exception as e:
            err_msg = str(e)
            errors.append(f"{provider.get('name', provider.get('id', '?'))}: {err_msg}")
            log.warning(f"classify_direct Provider-Fehler ({provider.get('name', '?')}): {err_msg}")
            continue

    # Alle Provider gescheitert
    return {"error": "Alle Provider gescheitert: " + " | ".join(errors),
            "antwort": "", "all_providers_failed": True}


# ── Auto-Wissen Extraktion ───────────────────────────────────────────────────
_WISSEN_KEYWORDS = ("zahlung", "bezahlt", "bevorzugt", "immer", "nie", "wichtig",
                    "deadline", "frist", "mahnung", "angebot", "reklamation",
                    "lieferant", "partner", "kunde", "muster", "regel")

def _auto_extract_wissen_async(user_msg: str, kira_antwort: str, session_id: str):
    """Startet Hintergrund-Thread: extrahiert Geschäftsregeln aus Konversation."""
    # Nur wenn Antwort business-relevante Schlüsselwörter enthält
    combined = (user_msg + " " + kira_antwort).lower()
    if not any(kw in combined for kw in _WISSEN_KEYWORDS):
        return

    def _extract():
        try:
            import threading
            provider, model_name = get_provider_for_task("extract")
            if not provider:
                return
            prompt_extract = (
                "Analysiere das folgende Gespräch und extrahiere bis zu 2 wichtige Geschäftsregeln "
                "oder Erkenntnisse die für zukünftige Gespräche nützlich sind. "
                "Nur wirklich neue, nicht-triviale Erkenntnisse. Wenn keine → gib [] zurück.\n"
                "Format: JSON-Array [{\"titel\": \"...\", \"inhalt\": \"...\"}]\n\n"
                f"Nutzer: {user_msg[:500]}\n\nKira: {kira_antwort[:500]}"
            )
            sys_extract = "Du extrahierst Geschäftsregeln als kompaktes JSON."
            if provider.get("typ") == "anthropic":
                result = _call_anthropic(provider, prompt_extract, sys_extract, [])
            else:
                result = _call_openai_compat(provider, prompt_extract, sys_extract, [])
            raw = result.get("text", "").strip()
            # JSON aus Antwort extrahieren
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start < 0 or end <= start:
                return
            entries = json.loads(raw[start:end])
            if not isinstance(entries, list):
                return
            now = datetime.now().isoformat()
            db = sqlite3.connect(str(TASKS_DB))
            for e in entries[:2]:
                titel = (e.get("titel") or "").strip()
                inhalt = (e.get("inhalt") or "").strip()
                if not titel or not inhalt or len(inhalt) < 10:
                    continue
                existing = db.execute("SELECT id FROM wissen_regeln WHERE titel=?", (titel,)).fetchone()
                if existing:
                    continue
                db.execute("INSERT INTO wissen_regeln (kategorie,titel,inhalt,quelle,erstellt_am) VALUES (?,?,?,?,?)",
                           ('auto_gelernt', titel, inhalt, f'auto_extract:{session_id[:8]}', now))
            db.commit()
            db.close()
        except Exception:
            pass

    import threading
    t = threading.Thread(target=_extract, daemon=True)
    t.start()


# ── Wissen-Extraktion: Schreibstil aus gesendeten Mails ─────────────────────
def extract_schreibstil(max_mails: int = 50) -> dict:
    """Analysiert gesendete Mails und extrahiert Schreibstil-Regeln per LLM (GPT-4o-mini).

    Returns: {"regeln": [...], "model": "...", "error": None}
    """
    try:
        sent_db = sqlite3.connect(str(KNOWLEDGE_DIR / "sent_mails.db"))
        sent_db.row_factory = sqlite3.Row
        # Zufällige Auswahl für Stil-Diversität
        mails = sent_db.execute(
            "SELECT betreff, text_plain, kunden_email FROM gesendete_mails "
            "WHERE text_plain IS NOT NULL AND LENGTH(text_plain) > 50 "
            "ORDER BY RANDOM() LIMIT ?", (max_mails,)
        ).fetchall()
        sent_db.close()

        if not mails:
            return {"regeln": [], "error": "Keine gesendeten Mails gefunden"}

        # Texte zusammenfassen (max 200 Zeichen pro Mail)
        samples = "\n---\n".join(
            f"An: {m['kunden_email'] or '?'}\nBetreff: {m['betreff'] or ''}\n{(m['text_plain'] or '')[:200]}"
            for m in mails[:max_mails]
        )

        prompt = (
            f"Analysiere diese {len(mails)} gesendeten E-Mails und extrahiere den Schreibstil des Absenders.\n\n"
            "Gib ein JSON-Array zurück mit bis zu 8 Stil-Regeln:\n"
            '[{"titel": "...", "inhalt": "...", "konfidenz": 0.0-1.0, "kategorie": "stil"}]\n\n'
            "Achte auf:\n"
            "- Anrede-Stil (Du/Sie, formell/informell)\n"
            "- Grußformeln am Ende\n"
            "- Satzlänge und Ton (kurz/knapp oder ausführlich)\n"
            "- Typische Wendungen und Floskeln\n"
            "- Sprache (Deutsch/Englisch/gemischt)\n\n"
            f"E-Mail-Beispiele:\n{samples[:6000]}"
        )

        provider, model_name = get_provider_for_task("extract")
        if not provider:
            return {"regeln": [], "error": "Kein Provider verfügbar"}

        sys_prompt = "Du bist ein Schreibstil-Analyst. Extrahiere Stil-Muster als kompaktes JSON."
        if provider.get("typ") == "anthropic":
            result = _call_anthropic(provider, prompt, sys_prompt, [], max_tokens=1024)
        else:
            result = _call_openai_compat(provider, prompt, sys_prompt, [], max_tokens=1024)

        raw = result.get("text", "").strip()
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start < 0 or end <= start:
            return {"regeln": [], "error": "Kein JSON in Antwort", "model": model_name}

        regeln = json.loads(raw[start:end])
        if not isinstance(regeln, list):
            return {"regeln": [], "error": "Ungültiges Format", "model": model_name}

        # In wissen_regeln speichern
        now = datetime.now().isoformat()
        db = sqlite3.connect(str(TASKS_DB))
        gespeichert = 0
        for r in regeln[:8]:
            titel = (r.get("titel") or "").strip()
            inhalt = (r.get("inhalt") or "").strip()
            konfidenz = float(r.get("konfidenz", 0.7))
            if not titel or not inhalt or len(inhalt) < 10:
                continue
            # Duplikat-Check
            existing = db.execute("SELECT id FROM wissen_regeln WHERE titel=?", (titel,)).fetchone()
            if existing:
                continue
            # Auto-Approve bei hoher Konfidenz (>= 0.9)
            status = "aktiv" if konfidenz >= 0.9 else "vorschlag"
            db.execute(
                "INSERT INTO wissen_regeln (kategorie,titel,inhalt,quelle,erstellt_am,status) VALUES (?,?,?,?,?,?)",
                ("stil", titel, inhalt, f"auto_schreibstil:{model_name}", now, status)
            )
            gespeichert += 1
        db.commit()
        db.close()

        return {
            "regeln": regeln[:8], "model": model_name,
            "gespeichert": gespeichert, "mails_analysiert": len(mails),
            "error": None,
        }
    except Exception as e:
        return {"regeln": [], "error": str(e)}


# ── Wissen-Extraktion: Geschäftsmuster aus Klassifizierungen ────────────────
def extract_geschaeftsmuster() -> dict:
    """Extrahiert Geschäftsmuster aus mail_index.db Klassifizierungen per LLM.

    Phase 1: Statistische Analyse (kostenlos)
    Phase 2: LLM-Zusammenfassung (GPT-4o-mini, ~$0.01)

    Returns: {"regeln": [...], "model": "...", "error": None}
    """
    try:
        mi_db = sqlite3.connect(str(MAIL_INDEX_DB))
        mi_db.row_factory = sqlite3.Row

        # Phase 1: Statistische Analyse
        stats = {}

        # Kategorie-Verteilung pro Absender-Domain
        domain_kats = mi_db.execute("""
            SELECT SUBSTR(absender, INSTR(absender, '@')+1) as domain, kategorie, COUNT(*) c
            FROM mails
            WHERE kategorie IS NOT NULL AND kategorie != '' AND folder='INBOX'
              AND absender LIKE '%@%'
            GROUP BY domain, kategorie
            HAVING c >= 3
            ORDER BY c DESC LIMIT 50
        """).fetchall()
        stats["domain_kategorien"] = [
            {"domain": r["domain"], "kategorie": r["kategorie"], "anzahl": r["c"]}
            for r in domain_kats
        ]

        # Top-Absender nach Geschäftsrelevanz
        top_absender = mi_db.execute("""
            SELECT absender, COUNT(*) c, kategorie
            FROM mails
            WHERE kategorie IN ('Neue Lead-Anfrage', 'Angebotsrückmeldung', 'Antwort erforderlich')
              AND folder='INBOX'
            GROUP BY absender
            ORDER BY c DESC LIMIT 20
        """).fetchall()
        stats["top_geschaeft"] = [
            {"absender": r["absender"], "anzahl": r["c"], "kategorie": r["kategorie"]}
            for r in top_absender
        ]

        # Betreff-Muster
        betreff_muster = mi_db.execute("""
            SELECT LOWER(SUBSTR(betreff, 1, 30)) as muster, COUNT(*) c, kategorie
            FROM mails
            WHERE kategorie IS NOT NULL AND folder='INBOX' AND betreff IS NOT NULL
            GROUP BY muster
            HAVING c >= 5
            ORDER BY c DESC LIMIT 20
        """).fetchall()
        stats["betreff_muster"] = [
            {"muster": r["muster"], "anzahl": r["c"], "kategorie": r["kategorie"]}
            for r in betreff_muster
        ]

        mi_db.close()

        # Phase 2: LLM-Zusammenfassung
        provider, model_name = get_provider_for_task("extract")
        if not provider:
            return {"regeln": [], "stats": stats, "error": "Kein Provider"}

        prompt = (
            "Analysiere diese E-Mail-Statistiken und extrahiere 5-8 Geschäftsregeln/-muster:\n\n"
            f"Absender-Kategorien:\n{json.dumps(stats['domain_kategorien'][:20], ensure_ascii=False)}\n\n"
            f"Top-Geschäftskontakte:\n{json.dumps(stats['top_geschaeft'][:10], ensure_ascii=False)}\n\n"
            f"Betreff-Muster:\n{json.dumps(stats['betreff_muster'][:10], ensure_ascii=False)}\n\n"
            "Gib ein JSON-Array zurück:\n"
            '[{"titel": "...", "inhalt": "...", "konfidenz": 0.0-1.0, "kategorie": "prozess|preis|technik"}]'
        )

        sys_prompt = "Du analysierst Geschäftsmuster aus E-Mail-Statistiken. Kompaktes JSON."
        if provider.get("typ") == "anthropic":
            result = _call_anthropic(provider, prompt, sys_prompt, [], max_tokens=1024)
        else:
            result = _call_openai_compat(provider, prompt, sys_prompt, [], max_tokens=1024)

        raw = result.get("text", "").strip()
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start < 0 or end <= start:
            return {"regeln": [], "stats": stats, "error": "Kein JSON", "model": model_name}

        regeln = json.loads(raw[start:end])

        # Speichern
        now = datetime.now().isoformat()
        db = sqlite3.connect(str(TASKS_DB))
        gespeichert = 0
        for r in regeln[:8]:
            titel = (r.get("titel") or "").strip()
            inhalt = (r.get("inhalt") or "").strip()
            konfidenz = float(r.get("konfidenz", 0.7))
            kat = r.get("kategorie", "gelernt")
            if kat not in ("prozess", "preis", "technik", "gelernt"):
                kat = "gelernt"
            if not titel or not inhalt or len(inhalt) < 10:
                continue
            existing = db.execute("SELECT id FROM wissen_regeln WHERE titel=?", (titel,)).fetchone()
            if existing:
                continue
            status = "aktiv" if konfidenz >= 0.9 else "vorschlag"
            db.execute(
                "INSERT INTO wissen_regeln (kategorie,titel,inhalt,quelle,erstellt_am,status) VALUES (?,?,?,?,?,?)",
                (kat, titel, inhalt, f"auto_geschaeftsmuster:{model_name}", now, status)
            )
            gespeichert += 1
        db.commit()
        db.close()

        return {
            "regeln": regeln[:8], "model": model_name,
            "gespeichert": gespeichert, "stats": stats, "error": None,
        }
    except Exception as e:
        return {"regeln": [], "error": str(e)}


# ── Haupt-Chat-Funktion ─────────────────────────────────────────────────────
def chat(user_message, session_id=None, history=None, bild=None):
    """Chat mit automatischem Provider-Fallback. bild={type,media_type,data} fuer Foto-Analyse."""
    config = get_config()

    # Chat-Provider: leistungsfähiges Modell erzwingen (Claude Sonnet / GPT-4o)
    raw_providers = get_providers()
    providers = []
    for p in raw_providers:
        typ = p.get("typ", "")
        if typ in _CAPABLE_MODELS:
            cp = dict(p)
            cp["model"] = _CAPABLE_MODELS[typ]
            providers.append(cp)
        else:
            providers.append(p)

    if not providers:
        return {
            "error": "Kein LLM-Provider konfiguriert. Bitte in Einstellungen mindestens einen Provider einrichten.",
            "needs_setup": True
        }

    # Temperatur aus LLM-Einstellungen (llm.temperatur, Default 0.7)
    try:
        _chat_full_cfg = json.loads(CONFIG_FILE.read_text('utf-8'))
        _chat_temperature = float(_chat_full_cfg.get("llm", {}).get("temperatur", 0.7))
    except Exception:
        _chat_temperature = 0.7

    system_prompt = build_system_prompt(config)
    tools = get_tools(config)
    session_id = session_id or str(uuid.uuid4())

    # Bild zu Content-List kombinieren (Anthropic vision format)
    if bild and isinstance(bild, dict) and bild.get("data"):
        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": bild.get("media_type", "image/jpeg"),
                    "data": bild["data"],
                }
            },
            {"type": "text", "text": user_message}
        ]
    else:
        user_content = user_message

    if config.get("konversationen_speichern", True):
        _save_message(session_id, "user", user_message)

    last_error = None
    result = None
    used_provider = None
    tried = []

    for provider in providers:
        pid = provider.get("id", "?")
        pname = provider.get("name", provider.get("typ", "?"))
        typ = provider.get("typ", "")

        # Vorab-Check: Key vorhanden?
        status = check_provider_status(provider)
        if status["status"] != "ok":
            tried.append(f"{pname}: {status['message']}")
            continue

        try:
            if typ == "anthropic":
                result = _call_anthropic(provider, user_content, system_prompt, tools, temperature=_chat_temperature)
            else:
                # OpenAI-kompatible Provider: Vision nur wenn Bild-URL-Format
                result = _call_openai_compat(provider, user_message, system_prompt, tools, temperature=_chat_temperature)
            used_provider = provider
            break
        except ProviderUnavailableError as e:
            last_error = str(e)
            tried.append(f"{pname}: {last_error}")
            continue
        except Exception as e:
            last_error = str(e)
            tried.append(f"{pname}: {last_error}")
            continue
    else:
        # Alle Provider fehlgeschlagen
        error_detail = "\n".join(f"  • {t}" for t in tried) if tried else "Keine Provider konfiguriert"
        _alog("LLM", "Chat fehlgeschlagen", error_detail[:300], "fehler", fehler=error_detail[:300])
        _elog("llm", "chat_failed", "Alle LLM-Provider nicht erreichbar",
              source="kira_llm", modul="kira", submodul="chat",
              session_id=session_id, actor_type="kira",
              status="fehler", error_message=error_detail[:500],
              user_input=user_message)
        return {
            "error": f"Alle Provider nicht erreichbar:\n{error_detail}",
            "needs_api_key": any("Key" in t for t in tried),
        }

    # Antwort speichern
    final_text = result["text"]
    all_tool_results = result["tools"]
    provider_name = used_provider.get("name", used_provider.get("typ", "?"))
    model_name    = used_provider.get("model", "")
    tin, tout = result.get("tokens_in", 0), result.get("tokens_out", 0)
    _alog("LLM", "Chat", f"{provider_name} | {tin}→{tout} Tokens | {len(all_tool_results)} Tools", "ok")
    _elog("llm", "chat_completed",
          f"{provider_name} | {tin}\u2192{tout} Tokens | {len(all_tool_results)} Tools",
          source="kira_llm", modul="kira", submodul="chat",
          session_id=session_id, actor_type="kira",
          status="ok",
          provider=provider_name, model=model_name,
          token_in=tin, token_out=tout,
          user_input=user_message,
          assistant_output=final_text,
          entity_snapshot={"tools": [t.get("tool") for t in all_tool_results],
                           "fallback": tried if tried else None})

    if config.get("konversationen_speichern", True):
        _save_message(session_id, "assistant", final_text,
                      tool_calls=all_tool_results if all_tool_results else None,
                      tokens_in=result.get("tokens_in", 0),
                      tokens_out=result.get("tokens_out", 0),
                      provider=provider_name)

    response = {
        "antwort": final_text,
        "session_id": session_id,
        "provider": provider_name,
        "model": used_provider.get("model", ""),
        "tools_verwendet": [t["tool"] for t in all_tool_results],
        "tool_ergebnisse": all_tool_results,
        "tokens": {
            "input": result.get("tokens_in", 0),
            "output": result.get("tokens_out", 0)
        }
    }

    # Fallback-Info wenn nicht der erste Provider genutzt wurde
    if tried:
        response["fallback_info"] = tried

    # Auto-Wissen extrahieren (Hintergrund-Thread, wenn aktiviert)
    if config.get("auto_wissen_extrahieren", True) and final_text:
        _auto_extract_wissen_async(user_message, final_text, session_id)

    return response


# ── Konversations-Verwaltung ─────────────────────────────────────────────────
def _save_message(session_id, rolle, nachricht, tool_calls=None, tokens_in=0, tokens_out=0, provider=None):
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.execute("""INSERT INTO kira_konversationen
            (session_id, rolle, nachricht, tool_calls_json, token_input, token_output, provider_used)
            VALUES (?,?,?,?,?,?,?)""",
            (session_id, rolle, nachricht,
             json.dumps(tool_calls, ensure_ascii=False, default=str) if tool_calls else None,
             tokens_in, tokens_out, provider))
        db.commit()
        db.close()
    except: pass


def get_conversations(limit=20):
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        rows = db.execute("""
            SELECT session_id,
                   MIN(erstellt_am) as gestartet,
                   MAX(erstellt_am) as letzte_nachricht,
                   COUNT(*) as nachrichten,
                   SUM(token_input) as total_input,
                   SUM(token_output) as total_output
            FROM kira_konversationen
            GROUP BY session_id
            ORDER BY MAX(erstellt_am) DESC
            LIMIT ?
        """, (limit,)).fetchall()
        result = []
        for r in rows:
            first = db.execute("SELECT nachricht FROM kira_konversationen WHERE session_id=? AND rolle='user' ORDER BY id LIMIT 1",
                               (r['session_id'],)).fetchone()
            vorschau = (first['nachricht'][:80] + '...') if first and first['nachricht'] and len(first['nachricht']) > 80 else (first['nachricht'] if first and first['nachricht'] else '')
            result.append({
                "session_id": r['session_id'],
                "gestartet": r['gestartet'],
                "letzte_nachricht": r['letzte_nachricht'],
                "nachrichten": r['nachrichten'],
                "vorschau": vorschau,
                "tokens": {"input": r['total_input'] or 0, "output": r['total_output'] or 0}
            })
        db.close()
        return result
    except:
        return []


def get_conversation_messages(session_id):
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT * FROM kira_konversationen WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        db.close()
        return [dict(r) for r in rows]
    except:
        return []


# ── Tagesbriefing ────────────────────────────────────────────────────────────
def generate_daily_briefing():
    """Generiert ein Tagesbriefing via LLM. Fallback auf Statistik-basiert."""
    config = get_config()
    today = date.today().isoformat()

    # Cache prüfen (nur 1x pro Tag)
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        cached = db.execute(
            "SELECT inhalt_json, erstellt_am FROM kira_briefings WHERE datum=?", (today,)
        ).fetchone()
        if cached:
            db.close()
            result_data = json.loads(cached['inhalt_json'])
            if 'erstellt_am' not in result_data and cached['erstellt_am']:
                result_data['erstellt_am'] = cached['erstellt_am']
            return result_data
    except:
        pass

    # Briefing-Tabelle erstellen falls nötig
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS kira_briefings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datum TEXT UNIQUE,
            inhalt_json TEXT,
            provider_used TEXT,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.commit()
    except:
        pass

    # Daten sammeln für Kontext
    stats = _build_briefing_stats(db)

    # LLM-Briefing versuchen
    briefing = None
    provider_used = "statistik"
    try:
        providers = get_providers()
        if providers:
            try:
                from task_manager import get_active_profile as _gap_b
                _bp = _gap_b()
                _bn = _bp.get("firma_name", "") or "Unternehmen"
            except Exception:
                _bn = "Unternehmen"
            prompt = f"""Erstelle ein kurzes Tagesbriefing für den Benutzer ({_bn}).
Heute: {today}

AKTUELLE GESCHÄFTSDATEN:
{json.dumps(stats, ensure_ascii=False, indent=2)}

FORMAT (als JSON):
{{
  "zusammenfassung": "2-3 Sätze: Was ist heute wichtig?",
  "prioritaeten": [
    {{"typ": "rechnung|angebot|aufgabe", "text": "Konkrete Handlungsaufforderung", "prio": 1}},
    ...max 5
  ],
  "vorschlaege": ["Konkrete Vorschläge was der Benutzer heute tun sollte"],
  "kennzahlen": {{
    "offenes_volumen": 12345.67,
    "angebote_offen": 5,
    "nachfass_faellig": 2,
    "avg_zahlungsdauer": 34
  }}
}}

Sei direkt, keine Floskeln. Fokus auf Handlung."""

            result = chat(f"[SYSTEM: Tagesbriefing generieren]\n\n{prompt}", session_id=None)
            if not result.get("error"):
                m = __import__('re').search(r'\{[\s\S]*\}', result.get("antwort", ""))
                if m:
                    briefing = json.loads(m.group(0))
                    provider_used = result.get("provider", "llm")
    except:
        pass

    # Fallback: Statistik-basiert
    if not briefing:
        briefing = _build_stats_briefing(stats)

    # Cache speichern
    try:
        now_ts = datetime.now().isoformat(timespec='seconds')
        briefing['erstellt_am'] = now_ts
        db.execute("INSERT OR REPLACE INTO kira_briefings (datum, inhalt_json, provider_used, erstellt_am) VALUES (?,?,?,?)",
                   (today, json.dumps(briefing, ensure_ascii=False), provider_used, now_ts))
        db.commit()
    except:
        pass

    try:
        db.close()
    except:
        pass
    return briefing


def _build_briefing_stats(db):
    """Sammelt aktuelle Geschäftsdaten für das Briefing."""
    stats = {}
    try:
        # Offene Rechnungen
        r = db.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(betrag_brutto),0) as vol FROM ausgangsrechnungen WHERE status='offen'").fetchone()
        stats["rechnungen_offen"] = {"anzahl": r['cnt'], "volumen": r['vol']}

        # Offene Angebote
        a = db.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(betrag_geschaetzt),0) as vol FROM angebote WHERE status='offen'").fetchone()
        stats["angebote_offen"] = {"anzahl": a['cnt'], "volumen": a['vol']}

        # Offene Aufgaben
        t = db.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status='offen'").fetchone()
        stats["aufgaben_offen"] = t['cnt']

        # Antwort nötig
        an = db.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status='offen' AND antwort_noetig=1").fetchone()
        stats["antwort_noetig"] = an['cnt']

        # Überfällige Mahnungen
        m = db.execute("SELECT COUNT(*) as cnt FROM ausgangsrechnungen WHERE status='offen' AND mahnung_count > 0").fetchone()
        stats["gemahnt"] = m['cnt']

        # Nachfass fällig (vereinfacht)
        from angebote_tracker import check_all_open_angebote
        tracker = check_all_open_angebote()
        stats["nachfass_faellig"] = len(tracker.get("nachfass_faellig", []))
        stats["nachfass_details"] = [
            {"a_nummer": n["a_nummer"], "kunde": n["kunde"], "tage": n["tage_offen"]}
            for n in tracker.get("nachfass_faellig", [])[:5]
        ]
    except:
        pass
    return stats


def _build_stats_briefing(stats):
    """Fallback-Briefing aus reinen Statistiken."""
    parts = []
    ro = stats.get("rechnungen_offen", {})
    ao = stats.get("angebote_offen", {})
    an = stats.get("antwort_noetig", 0)

    if an:
        parts.append(f"{an} Mail(s) warten auf Antwort")
    if ro.get("anzahl"):
        parts.append(f"{ro['anzahl']} offene Rechnungen ({ro['volumen']:.0f} EUR)")
    if ao.get("anzahl"):
        parts.append(f"{ao['anzahl']} offene Angebote ({ao['volumen']:.0f} EUR)")

    nf = stats.get("nachfass_faellig", 0)
    if nf:
        parts.append(f"{nf} Nachfass-Aktionen fällig")

    return {
        "zusammenfassung": ". ".join(parts) + "." if parts else "Keine dringenden Punkte heute.",
        "prioritaeten": [],
        "vorschlaege": [],
        "kennzahlen": {
            "offenes_volumen": ro.get("volumen", 0),
            "angebote_offen": ao.get("anzahl", 0),
            "nachfass_faellig": nf,
            "avg_zahlungsdauer": 0,
        }
    }


# ── ReAct-Schleife + Hintergrund-Tasks (Paket 5, session-oo) ─────────────────
# Background-Task Registry: {task_id: {status, steps, result, error, abgebrochen}}
_REACT_TASKS: dict = {}
_REACT_TASKS_LOCK = threading.Lock()

_REACT_CONTINUE_SIGNALS = ("[WEITER]", "[CONTINUE]", "[MEHR]", "[NOCH_NICHT_FERTIG]")


def _react_should_continue(text: str) -> bool:
    """Prueft ob Kiras Antwort ein Fortsetzungs-Signal enthaelt."""
    upper = text.upper()
    return any(sig.upper() in upper for sig in _REACT_CONTINUE_SIGNALS)


def _react_strip_signal(text: str) -> str:
    """Entfernt Fortsetzungs-Signale aus dem Antwort-Text."""
    for sig in _REACT_CONTINUE_SIGNALS:
        text = text.replace(sig, "").replace(sig.lower(), "")
    return text.strip()


def chat_react(task_id: str, user_input: str, max_rounds: int = 5) -> None:
    """
    ReAct-Loop: Fuehrt komplexe Aufgaben in mehreren Runden aus (Paket 5, session-oo).
    Laeuft in Hintergrund-Thread. Fortschritt via get_react_task_status().

    Kira signalisiert Fortsetzung mit [WEITER] am Ende der Antwort.
    Nach max_rounds oder wenn kein Signal mehr: automatisch stopp.
    """
    with _REACT_TASKS_LOCK:
        _REACT_TASKS[task_id] = {
            "status": "running",
            "steps": [],
            "result": None,
            "error": None,
            "abgebrochen": False,
            "gestartet_am": datetime.now().isoformat(),
        }

    def _run():
        session_id = str(uuid.uuid4())
        current_input = user_input
        accumulated_results = []

        for runde in range(1, max_rounds + 1):
            # Abbruch-Check
            with _REACT_TASKS_LOCK:
                if _REACT_TASKS.get(task_id, {}).get("abgebrochen"):
                    _REACT_TASKS[task_id]["status"] = "abgebrochen"
                    return

            # Chat-Call mit Session-Kontext
            try:
                result = chat(current_input, session_id=session_id)
            except Exception as e:
                with _REACT_TASKS_LOCK:
                    _REACT_TASKS[task_id]["status"] = "fehler"
                    _REACT_TASKS[task_id]["error"] = str(e)
                return

            if result.get("error"):
                with _REACT_TASKS_LOCK:
                    _REACT_TASKS[task_id]["status"] = "fehler"
                    _REACT_TASKS[task_id]["error"] = result["error"]
                return

            text = result.get("text", "")
            tools_used = result.get("tools", [])
            continue_flag = _react_should_continue(text)
            clean_text = _react_strip_signal(text)

            step = {
                "runde": runde,
                "input": current_input[:200],
                "output": clean_text[:500],
                "tools": [t.get("tool") for t in tools_used],
                "fortsetzung": continue_flag,
            }
            accumulated_results.append(clean_text)

            with _REACT_TASKS_LOCK:
                _REACT_TASKS[task_id]["steps"].append(step)

            _elog("kira", "react_round",
                  f"ReAct Runde {runde}/{max_rounds} | Task {task_id[:8]} | Fortsetzung={continue_flag}",
                  source="kira_llm", modul="kira", submodul="react",
                  session_id=session_id, actor_type="kira", status="ok",
                  context_snapshot={"runde": runde, "tools": step["tools"]})

            if not continue_flag:
                break

            # Naechste Runde: Ergebnis als Kontext mitnehmen
            current_input = (
                f"Vorheriges Ergebnis (Runde {runde}):\n{clean_text[:800]}\n\n"
                f"Mach weiter mit der urspruenglichen Aufgabe: {user_input[:200]}"
            )

        # Fertig
        with _REACT_TASKS_LOCK:
            _REACT_TASKS[task_id]["status"] = "fertig"
            _REACT_TASKS[task_id]["result"] = "\n\n".join(accumulated_results)

    t = threading.Thread(target=_run, name=f"kira-react-{task_id[:8]}", daemon=True)
    t.start()


def start_react_task(user_input: str, max_rounds: int = 5) -> str:
    """Startet einen ReAct-Hintergrund-Task. Gibt task_id zurueck."""
    task_id = str(uuid.uuid4())
    chat_react(task_id, user_input, max_rounds)
    return task_id


def get_react_task_status(task_id: str) -> dict:
    """Status eines laufenden oder abgeschlossenen ReAct-Tasks."""
    with _REACT_TASKS_LOCK:
        task = _REACT_TASKS.get(task_id)
    if not task:
        return {"error": f"Task {task_id} nicht gefunden"}
    return {
        "task_id": task_id,
        "status": task["status"],           # running | fertig | fehler | abgebrochen
        "runden": len(task.get("steps", [])),
        "letzter_step": task["steps"][-1] if task.get("steps") else None,
        "result": task.get("result"),
        "error": task.get("error"),
        "gestartet_am": task.get("gestartet_am"),
    }


def cancel_react_task(task_id: str) -> bool:
    """Bricht einen laufenden ReAct-Task ab."""
    with _REACT_TASKS_LOCK:
        if task_id in _REACT_TASKS:
            _REACT_TASKS[task_id]["abgebrochen"] = True
            return True
    return False


# ── Capture Tools (session-hhh) ───────────────────────────────────────────────

def _tool_capture_suchen(p):
    """Sucht in capture_items nach Suchbegriff und/oder Status."""
    suchbegriff = (p.get("suchbegriff") or "").strip()
    status = p.get("status", "")
    limit = min(int(p.get("limit", 10)), 30)
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        where_parts = ["archived=0"]
        params = []
        if suchbegriff:
            where_parts.append("(LOWER(raw_text) LIKE ? OR LOWER(normalized_text) LIKE ?)")
            params += [f'%{suchbegriff.lower()}%', f'%{suchbegriff.lower()}%']
        if status and status != "alle":
            where_parts.append("status=?")
            params.append(status)
        where = " AND ".join(where_parts)
        rows = db.execute(
            f"SELECT id, created_at, source_channel, raw_text, status, confidence, matched_entity_type, matched_entity_id FROM capture_items WHERE {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        db.close()
        if not rows:
            return {"ok": True, "message": "Keine Capture-Eintraege gefunden.", "anzahl": 0}
        lines = [f"Capture-Eintraege ({len(rows)} Ergebnisse):"]
        for r in rows:
            ts = r["created_at"][:16] if r["created_at"] else ""
            txt = (r["raw_text"] or "")[:100]
            match = f"→ {r['matched_entity_type']}#{r['matched_entity_id']}" if r["matched_entity_type"] else ""
            lines.append(f"  #{r['id']} [{r['status']}] {ts} ({r['source_channel']}) | {txt} {match}")
        return {"ok": True, "message": "\n".join(lines), "anzahl": len(rows)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _tool_capture_zuordnen(p):
    """Ordnet einen Capture-Eintrag einem Systemobjekt zu."""
    cap_id = int(p.get("capture_id", 0))
    entity_type = p.get("entity_type", "")
    entity_id = str(p.get("entity_id", ""))
    begruendung = p.get("begruendung", "")
    if not cap_id or not entity_type or not entity_id:
        return {"ok": False, "error": "capture_id, entity_type und entity_id erforderlich"}
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        item = db.execute("SELECT id FROM capture_items WHERE id=?", (cap_id,)).fetchone()
        if not item:
            db.close()
            return {"ok": False, "error": f"Capture #{cap_id} nicht gefunden"}
        db.execute("""UPDATE capture_items SET status='zugeordnet', final_entity_type=?,
                      final_entity_id=?, review_required=0, updated_at=datetime('now') WHERE id=?""",
                   (entity_type, entity_id, cap_id))
        db.execute("""INSERT INTO capture_matches (capture_id, candidate_type, candidate_id, score, reason, accepted)
                      VALUES (?,?,?,1.0,?,1)""",
                   (cap_id, entity_type, entity_id, f"Kira-Zuordnung: {begruendung}" if begruendung else "Kira-Zuordnung"))
        db.execute("INSERT INTO capture_actions (capture_id, actor_type, action, result) VALUES (?,?,?,?)",
                   (cap_id, 'kira', 'zugeordnet', f"{entity_type}#{entity_id}"))
        db.commit()
        db.close()
        try:
            _elog("capture", "tool_capture_zugeordnet", f"Capture #{cap_id} → {entity_type}#{entity_id} via Kira",
                  source="kira_llm", modul="capture", status="ok")
        except Exception:
            pass
        return {"ok": True, "message": f"Capture #{cap_id} erfolgreich {entity_type}#{entity_id} zugeordnet."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Dokument-Tools (session-eeee) ────────────────────────────────────────────

def _tool_dokument_suchen(p):
    """Sucht Dokumente nach Kriterien."""
    suchbegriff = (p.get("suchbegriff") or "").strip()
    status = p.get("status", "")
    kategorie = p.get("kategorie", "")
    limit = min(int(p.get("limit", 10)), 30)
    try:
        from dokument_storage import list_dokumente, _ensure_tables
        _ensure_tables()
        docs = list_dokumente(
            status=status if status else None,
            limit=limit,
        )
        if suchbegriff:
            q = suchbegriff.lower()
            docs = [d for d in docs if q in (d.get("titel","") + d.get("dateiname","") + d.get("kategorie","") + d.get("ocr_text","")[:500]).lower()]
        if kategorie:
            docs = [d for d in docs if d.get("kategorie") == kategorie]
        if not docs:
            return {"ok": True, "message": "Keine Dokumente gefunden.", "anzahl": 0}
        lines = [f"Dokumente ({len(docs)} Ergebnisse):"]
        for d in docs:
            ts = (d.get("erstellt_am") or "")[:16]
            lines.append(f"  #{d['id']} [{d['status']}] {ts} | {d.get('titel') or d.get('dateiname','?')} | {d.get('kategorie','?')} | Routing: {d.get('routing_ziel','?')}")
        return {"ok": True, "message": "\n".join(lines), "anzahl": len(docs)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _tool_dokument_erstellen(p):
    """Erstellt ein neues Dokument im Studio."""
    titel = p.get("titel", "Kira-Dokument")
    kategorie = p.get("kategorie", "frei")
    inhalt = p.get("inhalt", "")
    vorgang_id = p.get("vorgang_id")
    try:
        from dokument_storage import create_dokument, _ensure_tables
        _ensure_tables()
        dok_id = create_dokument(
            titel=titel,
            dateityp="html",
            quelle="kira",
            kategorie=kategorie,
            status="entwurf",
            erstellt_von="kira",
            vorgang_id=int(vorgang_id) if vorgang_id else None,
        )
        try:
            _elog("dokument", "doc_create", f"Kira hat Dokument erstellt: {titel}",
                  source="kira_llm", modul="dokumente", status="ok")
        except Exception:
            pass
        return {"ok": True, "message": f"Dokument #{dok_id} '{titel}' erstellt (Kategorie: {kategorie}). Kann im Dokument-Studio bearbeitet werden.", "id": dok_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _tool_dokument_zuordnen(p):
    """Ordnet ein Dokument einem Vorgang zu."""
    dok_id = int(p.get("dokument_id", 0))
    vorgang_id = int(p.get("vorgang_id", 0))
    if not dok_id or not vorgang_id:
        return {"ok": False, "error": "dokument_id und vorgang_id erforderlich"}
    try:
        from dokument_storage import update_dokument, _ensure_tables
        _ensure_tables()
        update_dokument(dok_id, vorgang_id=vorgang_id, status="zugeordnet")
        try:
            _elog("dokument", "doc_assign", f"Kira: Dokument #{dok_id} → Vorgang #{vorgang_id}",
                  source="kira_llm", modul="dokumente", status="ok")
        except Exception:
            pass
        return {"ok": True, "message": f"Dokument #{dok_id} wurde Vorgang #{vorgang_id} zugeordnet."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# Init DB bei Import
init_conversations_db()
