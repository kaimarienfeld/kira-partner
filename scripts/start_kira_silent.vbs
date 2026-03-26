' rauMKult® Kira Dashboard – startet Python ohne sichtbares Terminalfenster
' Doppelklick auf start_dashboard.bat oder direkt auf diese Datei

Dim pythonw, script, dir
dir     = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
pythonw = "C:\Users\kaimr\AppData\Local\Programs\Python\Python313\pythonw.exe"
script  = dir & "\server.py"

' Fenster-Modus 0 = versteckt, False = nicht auf Abschluss warten
CreateObject("WScript.Shell").Run """" & pythonw & """ """ & script & """", 0, False
