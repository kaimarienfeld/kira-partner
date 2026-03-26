@echo off
:: rauMKult® Dashboard starten — startet ohne sichtbares Terminalfenster
set DIR=%~dp0
start "" /B wscript.exe "%DIR%start_kira_silent.vbs"
