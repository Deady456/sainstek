# Setup Windows Task Scheduler untuk generate & upload video harian otomatis
# Jalankan sebagai Administrator: right-click -> Run with PowerShell

$TaskName = "FreeFaceless Daily Video"
$ScriptPath = Join-Path $PSScriptRoot "run_daily.ps1"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

# Peak hours untuk YouTube Shorts Indonesia (bisa disesuaikan)
$Triggers = @(
    New-ScheduledTaskTrigger -Daily -At 08:00  # pagi
    New-ScheduledTaskTrigger -Daily -At 12:00  # jam makan siang
    New-ScheduledTaskTrigger -Daily -At 16:00  # sore
    New-ScheduledTaskTrigger -Daily -At 20:00  # prime time malam
)

$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Keempat trigger akan jalan: 1 video per jadwal -> 4 video/hari
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Triggers -Settings $Settings -RunLevel Highest -Force

Write-Host "`nTask '$TaskName' berhasil dibuat!" -ForegroundColor Green
Write-Host "Jadwal: 08:00, 12:00, 16:00, 20:00 setiap hari -> 4 video/hari" -ForegroundColor Cyan
Write-Host "`nCek di Task Scheduler: taskschd.msc" -ForegroundColor Yellow
