$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$RunDir = Join-Path $Root "data\demo_runtime"
$PidFile = Join-Path $RunDir "reliability_demo_pids.csv"

if (!(Test-Path $PidFile)) {
    Write-Host "No reliability demo PID file found."
    return
}

$Rows = Import-Csv $PidFile
foreach ($Row in $Rows) {
    $PidNumber = [int]$Row.pid
    $Process = Get-Process -Id $PidNumber -ErrorAction SilentlyContinue
    if ($Process) {
        Stop-Process -Id $PidNumber
        Write-Host "Stopped $($Row.name) pid=$PidNumber"
    } else {
        Write-Host "Already stopped $($Row.name) pid=$PidNumber"
    }
}

Remove-Item -LiteralPath $PidFile
Write-Host "Reliability demo PC side stopped."
