@echo off
set PYTHON=C:\Users\kaimr\AppData\Local\Programs\Python\Python313\python.exe
set DIR=C:\Users\kaimr\.claude\projects\C--Users-kaimr-OneDrive---rauMKult-Sichtbeton-00-rauMKult-Auftr-ge-Anfragen\memory\scripts
set LOG=%DIR%\..\cowork\daily_check.log
set PYTHONIOENCODING=utf-8

echo [%DATE% %TIME%] Daily Check >> "%LOG%" 2>&1
"%PYTHON%" "%DIR%\daily_check.py" >> "%LOG%" 2>&1
