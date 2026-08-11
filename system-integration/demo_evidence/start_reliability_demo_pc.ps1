param(
    [int]$DashboardPort = 8085,
    [int]$DashboardUdpPort = 5011,
    [int]$ProxyUdpPort = 5012,
    [int]$BridgeUdpPort = 5013
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Python = (Get-Command python -ErrorAction Stop).Source
$RunDir = Join-Path $Root "data\demo_runtime"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

$PidFile = Join-Path $RunDir "reliability_demo_pids.csv"
if (Test-Path $PidFile) {
    throw "PID file already exists: $PidFile. Run system-integration/demo_evidence/stop_reliability_demo_pc.ps1 first."
}

function Assert-PortFree {
    param([int]$Port, [string]$Kind)
    if ($Kind -eq "tcp") {
        $busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    } else {
        $busy = Get-NetUDPEndpoint -LocalPort $Port -ErrorAction SilentlyContinue
    }
    if ($busy) {
        throw "$Kind port $Port is already in use. Close the old demo terminal/process or choose another port."
    }
}

function Start-DemoProcess {
    param(
        [string]$Name,
        [string[]]$Arguments
    )
    $Stdout = Join-Path $RunDir "$Name.out.log"
    $Stderr = Join-Path $RunDir "$Name.err.log"
    $Process = Start-Process -FilePath $Python `
        -ArgumentList $Arguments `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $Stdout `
        -RedirectStandardError $Stderr `
        -WindowStyle Hidden `
        -PassThru
    [pscustomobject]@{
        name = $Name
        pid = $Process.Id
        stdout = $Stdout
        stderr = $Stderr
    }
}

Assert-PortFree -Port $DashboardPort -Kind "tcp"
Assert-PortFree -Port $DashboardUdpPort -Kind "udp"
Assert-PortFree -Port $ProxyUdpPort -Kind "udp"
Assert-PortFree -Port $BridgeUdpPort -Kind "udp"

$Started = @()
$Started += Start-DemoProcess "dashboard" @(
    "network-telemetry-dashboard/code/pc_app/solar_live_dashboard.py",
    "--udp-host", "0.0.0.0",
    "--udp-port", "$DashboardUdpPort",
    "--http-host", "127.0.0.1",
    "--http-port", "$DashboardPort",
    "--bess-load-w", "0.1",
    "--recovery-window", "10",
    "--log", "network-telemetry-dashboard/data/solar_live_dashboard_reliability_bridge_log.csv"
)
Start-Sleep -Milliseconds 600

$Started += Start-DemoProcess "reliability_proxy" @(
    "network-telemetry-dashboard/code/pc_app/solar_reliability_proxy.py",
    "--bind-host", "0.0.0.0",
    "--bind-port", "$ProxyUdpPort",
    "--forward-host", "127.0.0.1",
    "--forward-port", "$DashboardUdpPort",
    "--drop-every", "7",
    "--corrupt-every", "9",
    "--inject-first", "30",
    "--log", "network-telemetry-dashboard/data/solar_reliability_proxy_bridge_log.csv"
)
Start-Sleep -Milliseconds 600

$Started += Start-DemoProcess "tracker_bridge" @(
    "fpga-digital-communications/code/pc_app/tracker_udp_comm_bridge.py",
    "--bind-host", "0.0.0.0",
    "--bind-port", "$BridgeUdpPort",
    "--forward-host", "127.0.0.1",
    "--forward-port", "$ProxyUdpPort",
    "--log", "fpga-digital-communications/data/tracker_udp_comm_bridge_reliability_log.csv"
)

$Started | Export-Csv -NoTypeInformation -Path $PidFile

Write-Host "Started reliability demo PC side."
Write-Host "Dashboard URL: http://127.0.0.1:$DashboardPort"
Write-Host "Orin must send UDP to this PC on port $BridgeUdpPort."
Write-Host "PID file: $PidFile"
$Started | Format-Table -AutoSize
