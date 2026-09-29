# Start llama-server (b9000) as a hidden background daemon
# Pre-reqs:
#   1. Download llama-b9000-bin-win-cpu-x64.zip to C:\Users\lenovo\AppData\Local\Temp\llama-b9000
#      (see docs/AVX-512-WORKAROUNDS.md for mirror options)
#   2. GGUF model at E:\llm_models\Qwen3.5-4B-Claude-Opus\Qwen3.5-4B.Q4_K_M.gguf
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start_llama_server.ps1
#
# Auto-install (Task Scheduler, on logon):
#   powershell -ExecutionPolicy Bypass -File scripts\register_llama_server.ps1

$ErrorActionPreference = 'Stop'

$BinDir      = 'C:\Users\lenovo\AppData\Local\Temp\llama-b9000'
$ModelPath   = 'E:\llm_models\Qwen3.5-4B-Claude-Opus\Qwen3.5-4B.Q4_K_M.gguf'
$Host        = '127.0.0.1'
$Port        = 8081
$LogFile     = 'C:\Users\lenovo\AppData\Local\Temp\llama-server.log'
$ErrorLog    = 'C:\Users\lenovo\AppData\Local\Temp\llama-server.err'
$TaskName    = 'PowerTopology_LlamaServer'

# Sanity check
if (-not (Test-Path $BinDir)) {
    Write-Host "[ERR] llama-server binary not found at $BinDir" -ForegroundColor Red
    Write-Host "      Download with: curl.exe -L -o ...llama-b9000-bin-win-cpu-x64.zip ...gh-proxy.com..."
    exit 1
}
if (-not (Test-Path $ModelPath)) {
    Write-Host "[ERR] GGUF model not found at $ModelPath" -ForegroundColor Red
    exit 1
}

# Already running?
$running = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "[OK] llama-server already listening on port $Port" -ForegroundColor Green
    exit 0
}

# Launch
$exe = Join-Path $BinDir 'llama-server.exe'
Write-Host "[..] Starting llama-server..."
Write-Host "      exe:    $exe"
Write-Host "      model:  $ModelPath"
Write-Host "      url:    http://${Host}:${Port}/v1"

$proc = Start-Process -FilePath $exe `
    -ArgumentList '-m', $ModelPath, '--host', $Host, '--port', $Port, `
                  '-c', '4096', '-ngl', '0', '-t', '8', '--log-disable' `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError $ErrorLog `
    -WindowStyle Hidden -PassThru

Write-Host "      PID:    $($proc.Id)"

# Wait for server to be ready (up to 120s, model + ctx=4096 takes ~30-60s to load)
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest -Uri "http://${Host}:${Port}/v1/models" `
                -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            $ready = $true
            Write-Host "[OK] llama-server READY after $($i*2)s" -ForegroundColor Green
            break
        }
    } catch { }
}

if (-not $ready) {
    Write-Host "[WARN] Server did not respond within 120s. Check $ErrorLog." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "  - Test: curl http://${Host}:${Port}/v1/models"
Write-Host "  - Use from Python: LLMClient(backend='llama-server', server_url='http://${Host}:${Port}/v1')"
Write-Host "  - Run 51-net benchmark: py -3.11 02_算法代码/tests/bench_gate_triggers_51.py --networks 51"
Write-Host "  - Stop: Get-Process -Name llama-server | Stop-Process"
