[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot "lib.ps1")

$unlockPath = Get-CodexDbUnlockPath
if (Test-Path $unlockPath) {
    Remove-Item $unlockPath -Force
    Write-Output "Write access locked."
} else {
    Write-Output "Write access was already locked."
}
