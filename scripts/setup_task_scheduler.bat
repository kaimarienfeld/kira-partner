@echo off
:: rauMKult(r) - Task Scheduler Einrichtung
:: Rechtsklick -> "Als Administrator ausfuehren"

set PS1=C:\Users\kaimr\.claude\projects\C--Users-kaimr-OneDrive---rauMKult-Sichtbeton-00-rauMKult-Auftr-ge-Anfragen\memory\scripts\setup_tasks.ps1

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
pause
