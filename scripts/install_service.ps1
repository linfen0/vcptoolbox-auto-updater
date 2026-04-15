#Requires -RunAsAdministrator

<#
.SYNOPSIS
    Install VCPToolBoxAutoUpdater as a Windows service.
#>

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$ConfigPath = Join-Path $ProjectDir "config.yaml"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Virtual environment not found. Syncing dependencies with uv..." -ForegroundColor Yellow
    Set-Location $ProjectDir
    & uv sync
}

if (-not (Test-Path $ConfigPath)) {
    Write-Error "Config file not found at $ConfigPath"
    exit 1
}

& $VenvPython -m vcptoolbox_updater install

[Environment]::SetEnvironmentVariable(
    "VCPTOOLBOX_UPDATER_CONFIG",
    $ConfigPath,
    "Machine"
)

& sc config VCPToolBoxAutoUpdater start= auto
& sc failure VCPToolBoxAutoUpdater reset= 86400 actions= restart/5000/restart/5000/restart/5000

& $VenvPython -m vcptoolbox_updater start

Write-Host "Service installed and started successfully." -ForegroundColor Green