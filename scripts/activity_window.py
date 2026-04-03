#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KIRA Activity Window (session-nn, erweitert session-cccc)
Desktop-Overlay für Stufe-B/C-Signale — läuft als Hintergrund-Thread.
Nutzt nur stdlib tkinter, keine externen Abhängigkeiten.

Öffentliche API:
  show_signal_overlay(signal: dict, on_confirm=None, on_snooze=None) -> None
    signal = {"id": int, "titel": str, "nachricht": str, "stufe": "B"|"C"}

  start_signal_watcher() -> None
    Startet den Hintergrund-Thread der alle 15s Stufe-C-Signale prüft
    und ggf. ein Overlay zeigt. Einmal aufrufen beim Server-Start.
"""
import threading
import time
import logging
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

log = logging.getLogger("activity_window")

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
TASKS_DB      = KNOWLEDGE_DIR / "tasks.db"

# Cooldown-Tracking: Verhindert Spam für gleiche Trigger
_trigger_cooldowns: dict[str, float] = {}
_COOLDOWN_SECS = 3600  # 1 Stunde zwischen gleichen Triggern

_overlay_lock = threading.Lock()
_watcher_started = False


def show_signal_overlay(signal: dict, on_confirm=None, on_snooze=None) -> None:
    """Zeigt ein topmost tkinter-Fenster für ein Signal. Thread-safe."""
    if not _overlay_lock.acquire(blocking=False):
        return  # Bereits ein Overlay offen

    def _run():
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()

            win = tk.Toplevel(root)
            win.title("KIRA — Aktion erforderlich")
            win.attributes("-topmost", True)
            win.configure(bg="#1a1a1a", padx=24, pady=20)
            win.resizable(False, False)

            # Zentrieren
            w, h = 420, 220
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2 - 60}")

            # Header
            tk.Label(win, text="⚠  Vorgang — Aktion erforderlich",
                     bg="#1a1a1a", fg="#ef4444",
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 6))

            # Titel
            tk.Label(win, text=signal.get("titel", ""),
                     bg="#1a1a1a", fg="#e0e0e0",
                     font=("Segoe UI", 13, "bold"),
                     wraplength=370, justify="left").pack(anchor="w")

            # Nachricht
            msg = (signal.get("nachricht") or "").split("\n")[0][:200]
            if msg:
                tk.Label(win, text=msg,
                         bg="#1a1a1a", fg="#aaaaaa",
                         font=("Segoe UI", 10),
                         wraplength=370, justify="left").pack(anchor="w", pady=(4, 0))

            # Buttons
            btn_frame = tk.Frame(win, bg="#1a1a1a")
            btn_frame.pack(side="bottom", fill="x", pady=(16, 0))

            def _confirm():
                win.destroy()
                root.destroy()
                if on_confirm:
                    on_confirm(signal)

            def _snooze():
                win.destroy()
                root.destroy()
                if on_snooze:
                    on_snooze(signal)

            tk.Button(btn_frame, text="Verstanden", command=_confirm,
                      bg="#ef4444", fg="white", relief="flat",
                      font=("Segoe UI", 10, "bold"),
                      padx=14, pady=6, cursor="hand2").pack(side="right", padx=(6, 0))

            tk.Button(btn_frame, text="Später", command=_snooze,
                      bg="#2a2a2a", fg="#cccccc", relief="flat",
                      font=("Segoe UI", 10),
                      padx=14, pady=6, cursor="hand2").pack(side="right")

            win.protocol("WM_DELETE_WINDOW", _snooze)
            win.lift()
            win.focus_force()
            root.mainloop()
        except Exception as e:
            log.error(f"activity_window Fehler: {e}")
        finally:
            _overlay_lock.release()

    t = threading.Thread(target=_run, name="kira-overlay", daemon=True)
    t.start()


def start_signal_watcher() -> None:
    """
    Startet den Hintergrund-Watcher (einmalig). Prüft alle 15s auf
    Stufe-C-Signale und zeigt ein Desktop-Overlay wenn der Nutzer anwesend ist.
    """
    global _watcher_started
    if _watcher_started:
        return
    _watcher_started = True

    def _watch():
        while True:
            try:
                time.sleep(15)
                _check_and_show()
            except Exception as e:
                log.error(f"signal_watcher Fehler: {e}")

    t = threading.Thread(target=_watch, name="kira-signal-watcher", daemon=True)
    t.start()
    log.info("Signal-Watcher gestartet (15s Intervall)")


def _emit_signal(sig: dict) -> None:
    """Schreibt ein Signal in die Case-Engine-DB für Browser-Polling (Toast/Modal)."""
    try:
        from case_engine import create_signal
        create_signal(
            stufe=sig.get("stufe", "B"),
            titel=sig.get("titel", ""),
            nachricht=sig.get("nachricht", ""),
            typ=sig.get("typ", "activity_trigger"),
        )
    except Exception:
        pass  # Case-Engine nicht verfügbar — nur Desktop-Overlay


def _cooldown_ok(key: str) -> bool:
    """Prüft ob Trigger angezeigt werden darf (Cooldown abgelaufen)."""
    now = time.time()
    last = _trigger_cooldowns.get(key, 0)
    if now - last < _COOLDOWN_SECS:
        return False
    _trigger_cooldowns[key] = now
    return True


def _scan_ueberfaellige_rechnungen() -> dict | None:
    """Prüft ausgangsrechnungen auf >14 Tage überfällige Einträge."""
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        today = datetime.now().date()
        rows = db.execute("""
            SELECT re_nummer, datum, kunde_name, betrag_brutto
            FROM ausgangsrechnungen
            WHERE status='offen' AND datum IS NOT NULL
            ORDER BY datum ASC
        """).fetchall()
        db.close()

        ueberfaellige = []
        for r in rows:
            try:
                re_datum = datetime.strptime(str(r["datum"])[:10], "%Y-%m-%d").date()
                tage = (today - re_datum).days
            except Exception:
                continue
            if tage >= 14:
                ueberfaellige.append({
                    "re_nummer": r["re_nummer"],
                    "kunde": r["kunde_name"] or "Unbekannt",
                    "betrag": r["betrag_brutto"] or 0,
                    "tage": tage,
                })

        if not ueberfaellige:
            return None

        key = f"re-ueberf-{len(ueberfaellige)}"
        if not _cooldown_ok(key):
            return None

        # Höchste zuerst
        ueberfaellige.sort(key=lambda x: x["tage"], reverse=True)
        top = ueberfaellige[0]
        n = len(ueberfaellige)
        titel = f"{n} Rechnung{'en' if n > 1 else ''} überfällig"
        lines = []
        for u in ueberfaellige[:3]:
            lines.append(f"{u['re_nummer']} — {u['kunde']} ({u['tage']}d, {u['betrag']:,.0f} €)")
        nachricht = "\n".join(lines)
        if n > 3:
            nachricht += f"\n… und {n - 3} weitere"

        stufe = "C" if top["tage"] >= 30 else "B"
        return {
            "id": f"re-ueberf-{top['re_nummer']}",
            "stufe": stufe,
            "titel": titel,
            "nachricht": nachricht,
        }
    except Exception as e:
        log.debug(f"scan_ueberfaellige: {e}")
        return None


def _scan_neue_leads() -> dict | None:
    """Prüft auf neue Leads (Tasks vom Typ 'anfrage' der letzten 2h)."""
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        seit = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
        rows = db.execute("""
            SELECT id, titel, kunde_name, erstellt_am
            FROM tasks
            WHERE typ IN ('anfrage', 'lead', 'anfrage_lead')
              AND erstellt_am >= ?
              AND status NOT IN ('erledigt', 'archiviert', 'ignoriert')
            ORDER BY erstellt_am DESC
        """, (seit,)).fetchall()
        db.close()

        if not rows:
            return None

        # Nur anzeigen wenn mindestens 1 neuer Lead im Cooldown-Fenster
        key = f"neue-leads-{rows[0]['id']}"
        if not _cooldown_ok(key):
            return None

        n = len(rows)
        top = rows[0]
        titel = f"{n} neue{'r' if n == 1 else ''} Lead{'s' if n > 1 else ''}"
        lines = []
        for r in rows[:3]:
            name = r["kunde_name"] or r["titel"] or f"Task #{r['id']}"
            lines.append(name)
        nachricht = ", ".join(lines)
        if n > 3:
            nachricht += f" + {n - 3} weitere"

        return {
            "id": f"lead-{top['id']}",
            "stufe": "B",
            "titel": titel,
            "nachricht": nachricht,
        }
    except Exception as e:
        log.debug(f"scan_neue_leads: {e}")
        return None


def _scan_kira_freigaben() -> dict | None:
    """Prüft auf Kira-Entwürfe die >2h auf Freigabe warten."""
    try:
        db = sqlite3.connect(str(TASKS_DB))
        db.row_factory = sqlite3.Row
        grenze = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
        rows = db.execute("""
            SELECT id, an, betreff, erstellt_am
            FROM mail_approve_queue
            WHERE status='pending' AND erstellt_am <= ?
            ORDER BY erstellt_am ASC
        """, (grenze,)).fetchall()
        db.close()

        if not rows:
            return None

        key = f"freigaben-{len(rows)}"
        if not _cooldown_ok(key):
            return None

        n = len(rows)
        titel = f"{n} Kira-Entwurf{'e' if n > 1 else ''} warten auf Freigabe"
        lines = []
        for r in rows[:3]:
            lines.append(f"An {r['an']}: {r['betreff']}")
        nachricht = "\n".join(lines)
        if n > 3:
            nachricht += f"\n… und {n - 3} weitere"

        return {
            "id": f"freigabe-{rows[0]['id']}",
            "stufe": "B",
            "titel": titel,
            "nachricht": nachricht,
        }
    except Exception as e:
        log.debug(f"scan_kira_freigaben: {e}")
        return None


def _check_and_show() -> None:
    """Holt Signale aus mehreren Quellen und zeigt ggf. ein Overlay."""
    try:
        from presence_detector import is_user_present
        if not is_user_present(idle_threshold_s=300):
            return  # Nutzer länger als 5 Min inaktiv — kein Popup

        # 1. Case-Engine Stufe-C-Signale (höchste Priorität)
        try:
            from case_engine import get_pending_signals, mark_signal_shown
            signals = get_pending_signals(max_count=3)
            c_signals = [s for s in signals if s.get("stufe") == "C"]
            if c_signals:
                sig = c_signals[0]
                def _confirm(s):
                    try: mark_signal_shown(s["id"], "bestaetigt_desktop")
                    except: pass
                def _snooze(s):
                    try: mark_signal_shown(s["id"], "snoozed_desktop")
                    except: pass
                show_signal_overlay(sig, on_confirm=_confirm, on_snooze=_snooze)
                return
        except Exception:
            pass

        # 2. Qualifizierungs-Status (pausiert = Guthaben leer)
        try:
            import json
            state_file = KNOWLEDGE_DIR / "qualify_state.json"
            if state_file.exists():
                state = json.loads(state_file.read_text("utf-8"))
                if state.get("paused") and not state.get("_desktop_shown"):
                    sig = {
                        "id": "qual_pause",
                        "stufe": "C",
                        "titel": "Qualifizierung pausiert",
                        "nachricht": state.get("pause_grund", "LLM-Provider nicht erreichbar"),
                        "aktion": "Guthaben aufladen und in KIRA fortsetzen",
                    }
                    def _confirm_q(s):
                        try:
                            state["_desktop_shown"] = True
                            state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
                        except: pass
                    show_signal_overlay(sig, on_confirm=_confirm_q, on_snooze=_confirm_q)
                    return
        except Exception:
            pass

        # 3. Überfällige Rechnungen (>14 Tage → Stufe B, >30 Tage → Stufe C)
        re_sig = _scan_ueberfaellige_rechnungen()
        if re_sig:
            _emit_signal(re_sig)
            show_signal_overlay(re_sig)
            return

        # 4. Kira-Freigaben wartend >2h
        fg_sig = _scan_kira_freigaben()
        if fg_sig:
            _emit_signal(fg_sig)
            show_signal_overlay(fg_sig)
            return

        # 5. Case-Engine Stufe-B-Signale
        try:
            from case_engine import get_pending_signals, mark_signal_shown
            signals = get_pending_signals(max_count=5)
            b_signals = [s for s in signals if s.get("stufe") == "B"]
            if b_signals:
                sig = b_signals[0]
                def _confirm_b(s):
                    try: mark_signal_shown(s["id"], "bestaetigt_desktop")
                    except: pass
                show_signal_overlay(sig, on_confirm=_confirm_b, on_snooze=_confirm_b)
                return
        except Exception:
            pass

        # 6. Neue Leads (letzte 2h)
        lead_sig = _scan_neue_leads()
        if lead_sig:
            _emit_signal(lead_sig)
            show_signal_overlay(lead_sig)
            return

    except Exception as e:
        log.error(f"_check_and_show Fehler: {e}")
