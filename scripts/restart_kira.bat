@echo off
:: rauMKult® Kira – Harter Neustart
:: Beendet ALLE Python-Prozesse auf Port 8765 und startet den Server neu

:: 1. Alle python / pythonw Prozesse beenden
taskkill /F /IM pythonw.exe 2>nul
taskkill /F /IM python.exe 2>nul

:: 2. Sicherheitshalber: Prozess der auf Port 8765 hoert direkt killen
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765 "') do (
    taskkill /F /PID %%a 2>nul
)

:: 3. Kurz warten bis Port frei ist
timeout /t 3 /nobreak >nul

:: 4. Server neu starten (kein Fenster sichtbar)
set DIR=%~dp0
start "" /B wscript.exe "%DIR%start_kira_silent.vbs"

:: 5. Browser oeffnen (mit Verzoegerung damit Server starten kann)
timeout /t 4 /nobreak >nul
start http://localhost:8765
