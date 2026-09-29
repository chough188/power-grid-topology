# Daily Audit Summary cron wrapper for Windows Task Scheduler
# Run at 06:00 every day. Logs to scripts/cron_audit_summary.log
$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$LogFile = Join-Path $PSScriptRoot "cron_audit_summary.log"
$Stamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
"[$Stamp] cron_audit_summary started" | Out-File -Append -FilePath $LogFile -Encoding UTF8

try {
    Set-Location $ProjectDir
    $env:PYTHONIOENCODING = "utf-8"
    & py -3 scripts/daily_audit_run.py 1 2>&1 | Out-File -Append -FilePath $LogFile -Encoding UTF8
    $rc = $LASTEXITCODE
    $Stamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
    "[$Stamp] cron_audit_summary exit=$rc" | Out-File -Append -FilePath $LogFile -Encoding UTF8
    exit $rc
}
catch {
    $Stamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
    "[$Stamp] ERROR: $_" | Out-File -Append -FilePath $LogFile -Encoding UTF8
    exit 1
}
