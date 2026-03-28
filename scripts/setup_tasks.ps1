# rauMKult Task Scheduler Setup
# Ausfuehren mit: powershell -ExecutionPolicy Bypass -File setup_tasks.ps1

$bat = 'C:\Users\kaimr\.claude\projects\C--Users-kaimr-OneDrive---rauMKult-Sichtbeton-00-rauMKult-Auftr-ge-Anfragen\memory\scripts\daily_check.bat'

# Alte Tasks loeschen
foreach ($name in @("rauMKult_DailyCheck_Morgens","rauMKult_DailyCheck_Abends",
                     "rauMKult_DailyCheck_0500","rauMKult_DailyCheck_1200","rauMKult_DailyCheck_1600")) {
    schtasks /Delete /TN $name /F 2>$null | Out-Null
}
Write-Host "Alte Tasks geloescht."

# Neue Tasks anlegen
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`""
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -StartWhenAvailable

foreach ($time in @("05:00","12:00","16:00")) {
    $trigger = New-ScheduledTaskTrigger -Daily -At $time
    $taskName = "rauMKult_DailyCheck_$($time -replace ':','')"
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Settings $settings -RunLevel Highest -Force | Out-Null
    Write-Host "Task erstellt: $taskName ($time)"
}

Write-Host ""
Write-Host "Fertig! Laeuft taeglich um 05:00, 12:00 und 16:00."
Write-Host "Bericht: $env:USERPROFILE\Desktop\rauMKult Tagesbericht.lnk"
