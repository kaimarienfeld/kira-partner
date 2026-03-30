#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KIRA Presence Detector (session-nn)
Windows-native Idle-Time-Erkennung via ctypes (keine externen Abhängigkeiten).

Öffentliche API:
  get_idle_seconds() -> int     — Sekunden seit letzter Benutzereingabe
  is_user_present(threshold=120) -> bool — True wenn Nutzer aktiv
"""
import ctypes
import ctypes.wintypes


def get_idle_seconds() -> int:
    """Gibt zurück wie viele Sekunden seit der letzten Benutzereingabe vergangen sind."""
    try:
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        millis_idle = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return max(0, millis_idle // 1000)
    except Exception:
        return 0  # Fehler → Nutzer als anwesend annehmen


def is_user_present(idle_threshold_s: int = 120) -> bool:
    """
    True wenn der Nutzer in den letzten `idle_threshold_s` Sekunden aktiv war.
    Standard: 2 Minuten (120s).
    """
    return get_idle_seconds() < idle_threshold_s
