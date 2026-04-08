' rauMKult® Kira – Harter Neustart (kein Fenster sichtbar)
' Doppelklick: beendet alle Python-Prozesse auf Port 8765, startet Server neu, oeffnet Browser

Dim sh, dir, pythonw, script
Set sh  = CreateObject("WScript.Shell")
dir     = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
pythonw = "C:\Users\kaimr\AppData\Local\Programs\Python\Python313\pythonw.exe"
script  = dir & "\server.py"

' 1. Alle Python-Prozesse killen (pythonw + python)
sh.Run "taskkill /F /IM pythonw.exe", 0, True
sh.Run "taskkill /F /IM python.exe",  0, True

' 2. Prozess auf Port 8765 direkt killen (falls noch einer laeuft)
sh.Run "cmd /c for /f ""tokens=5"" %a in ('netstat -ano ^| findstr "":8765 ""') do taskkill /F /PID %a", 0, True

' 3. Kurz warten bis Port frei ist
WScript.Sleep 3000

' 4. Server neu starten
sh.Run """" & pythonw & """ """ & script & """", 0, False

' 5. Warten bis Server hochgefahren, dann Browser oeffnen (ohne --no-sandbox)
WScript.Sleep 4000
Dim fso, chromePath, edgePath, url
Set fso = CreateObject("Scripting.FileSystemObject")
url = "http://localhost:8765"
chromePath = sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\Google\Chrome\Application\chrome.exe"
edgePath = sh.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Microsoft\Edge\Application\msedge.exe"
If fso.FileExists(chromePath) Then
    sh.Run """" & chromePath & """ " & url, 1, False
ElseIf fso.FileExists(edgePath) Then
    sh.Run """" & edgePath & """ " & url, 1, False
Else
    sh.Run url, 1, False
End If
