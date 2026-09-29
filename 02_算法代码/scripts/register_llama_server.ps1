# Register Windows Task Scheduler entry to auto-start llama-server on user logon
# Run as Administrator:
#   powershell -ExecutionPolicy Bypass -File scripts\register_llama_server.ps1

$ErrorActionPreference = 'Stop'
$TaskName = 'PowerTopology_LlamaServer'
$ScriptPath = Join-Path $PSScriptRoot 'start_llama_server.ps1'

# Trigger: at user logon
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Run as current user (no elevation needed for non-system processes)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited

$Action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

# Allow restart on failure
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1)

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    Register-ScheduledTask -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Settings $Settings `
        -Description 'Start llama-server (b9000) hidden on logon. Powers the local 配电网 LLM assistant.' `
        | Out-Null

    Write-Host "[OK] Task '$TaskName' registered (trigger: AtLogOn)" -ForegroundColor Green
    Write-Host "      Restart behavior: 5 attempts, 1 min apart"
    Write-Host "      Limit: 5 min per run"
}
catch {
    Write-Host "[ERR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
