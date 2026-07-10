Set-Location -Path $PSScriptRoot
$ErrorActionPreference = "Continue"
if (-not (Test-Path "logs")) { New-Item -ItemType Directory -Path "logs" | Out-Null }

$log = Join-Path $PSScriptRoot ("logs\run_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

# Pre-check: internet & Pexels API
"==== pre-checks at $(Get-Date -Format HH:mm:ss) ====" | Out-File -FilePath $log -Append -Encoding utf8
& "$PSScriptRoot\.venv\Scripts\python.exe" -u -m src.healthcheck >> $log 2>&1
$healthy = $LASTEXITCODE
if ($healthy -ne 0) {
    "==== skipped: prerequisites not met ====" | Out-File -FilePath $log -Append -Encoding utf8
    exit 1
}

# Retry up to 3x (handles network / antivirus TLS not being ready right after login).
$code = 1
for ($i = 1; $i -le 3 -and $code -ne 0; $i++) {
    "==== pipeline attempt $i at $(Get-Date -Format HH:mm:ss) ====" | Out-File -FilePath $log -Append -Encoding utf8
    & "$PSScriptRoot\.venv\Scripts\python.exe" -u -m src.pipeline >> $log 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0 -and $i -lt 3) { Start-Sleep -Seconds 60 }
}

exit $code
