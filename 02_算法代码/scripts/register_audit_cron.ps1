# Register Windows Task Scheduler entry for daily audit summary

# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File scripts\register_audit_cron.ps1

$TaskName = "PowerTopology_DailyAuditSummary"
$ScriptPath = Join-Path $PSScriptRoot "cron_audit_summary.ps1"

# 06:00 daily
$Trigger = New-ScheduledTaskTrigger -Daily -At "06:00"

# Run as current user (no elevation)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited

$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5)

try {
    # Remove existing task if present
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    Register-ScheduledTask -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Settings $Settings `
        -Description "Daily LLM audit summary: index audit logs to ELK and write Markdown report to output/audit_daily/"

    Write-Host "[ok] registered task: $TaskName"
    Write-Host "  Trigger: Daily at 06:00"
    Write-Host "  Script: $ScriptPath"
    Write-Host "  Log: scripts/cron_audit_summary.log"
    Write-Host ""
    Write-Host "Test now: schtasks /Run /TN `"$TaskName`""
}
catch {
    Write-Host "[fail] could not register task: $_"
    exit 1
}
