[CmdletBinding()]
param(
    [string]$HostAlias = "polyedge-lxc-codex",
    [string]$HostName = "192.168.8.131",
    [string]$RemoteUser = "codexdeploy",
    [string]$KeyPath = "$HOME\.ssh\codex_polyedge_lxc_ed25519"
)

$ErrorActionPreference = "Stop"

$sshDir = Join-Path $HOME ".ssh"
$configPath = Join-Path $sshDir "config"
$knownHostsPath = Join-Path $sshDir "known_hosts"
$identityFile = $KeyPath -replace "\\", "/"

New-Item -ItemType Directory -Force -Path $sshDir | Out-Null

if (-not (Test-Path $KeyPath)) {
    $keygenCommand = 'ssh-keygen -t ed25519 -f "' + $KeyPath + '" -N "" -C "codex-to-polyedge-lxc"'
    & cmd.exe /d /c $keygenCommand | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "ssh-keygen failed while creating $KeyPath"
    }
}

$configBlock = @"
Host $HostAlias
    HostName $HostName
    User $RemoteUser
    IdentityFile $identityFile
    IdentitiesOnly yes
    PreferredAuthentications publickey
    BatchMode yes
    StrictHostKeyChecking yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
"@

if (Test-Path $configPath) {
    $configText = Get-Content $configPath -Raw
} else {
    $configText = ""
}

$aliasRegex = "(?m)^Host\s+$([regex]::Escape($HostAlias))\s*$"
if ($configText -notmatch $aliasRegex) {
    $prefix = ""
    if ($configText.Length -gt 0) {
        if ($configText.EndsWith("`r`n") -or $configText.EndsWith("`n")) {
            $prefix = "`r`n"
        } else {
            $prefix = "`r`n`r`n"
        }
    }
    Add-Content -Path $configPath -Value ($prefix + $configBlock.TrimEnd() + "`r`n")
}

$sshKeyscan = Get-Command ssh-keyscan -ErrorAction SilentlyContinue
if ($sshKeyscan) {
    $scanOutput = & cmd.exe /d /c ("ssh-keyscan -H " + $HostName + " 2>NUL")
    if ($LASTEXITCODE -eq 0 -and $scanOutput) {
        if (-not (Test-Path $knownHostsPath)) {
            New-Item -ItemType File -Force -Path $knownHostsPath | Out-Null
        }
        $knownHostsText = Get-Content $knownHostsPath -Raw -ErrorAction SilentlyContinue
        foreach ($line in $scanOutput) {
            if ($knownHostsText -notlike "*$line*") {
                Add-Content -Path $knownHostsPath -Value $line
            }
        }
    }
}

Write-Host "Local SSH alias installed: $HostAlias"
Write-Host "Private key: $KeyPath"
Write-Host "Public key:  $KeyPath.pub"
Write-Host ""
Get-Content "$KeyPath.pub"
