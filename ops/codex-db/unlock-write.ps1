[CmdletBinding()]
param(
    [int]$Minutes = 5
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot "lib.ps1")

if ($Minutes -lt 1 -or $Minutes -gt 120) {
    throw "Minutes must be between 1 and 120."
}

$stateDir = Get-CodexDbStateDir
$unlockPath = Get-CodexDbUnlockPath
$nowUtc = (Get-Date).ToUniversalTime()
$expiresUtc = $nowUtc.AddMinutes($Minutes)

$payload = [pscustomobject]@{
    approvedBy    = [Environment]::UserName
    createdAtUtc  = $nowUtc.ToString("o")
    expiresAtUtc  = $expiresUtc.ToString("o")
    minutes       = $Minutes
    machine       = $env:COMPUTERNAME
}

$payload | ConvertTo-Json | Set-Content -Path $unlockPath -Encoding UTF8

Write-Output ("Write access unlocked until " + $expiresUtc.ToString("u"))
