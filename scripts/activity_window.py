#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KIRA Activity Window (session-nn)
Desktop-Overlay für Stufe-C-Signale — läuft als Hintergrund-Thread.
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

log = logging.getLogger("activity_window")

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
            from pathlib import Path
            state_file = Path(__file__).parent.parent / "knowledge" / "qualify_state.json"
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

        # 3. Case-Engine Stufe-B-Signale (niedrigere Prio, aber anzeigen wenn nichts anderes)
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

    except Exception as e:
        log.error(f"_check_and_show Fehler: {e}")
