[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AdminUser,
    [string]$HostName = "192.168.8.131",
    [string]$RepoRoot = "/opt/stacks/polyedge-v2",
    [string]$DeployUser = "codexdeploy",
    [string]$PublicKeyPath = "$HOME\.ssh\codex_polyedge_lxc_ed25519.pub",
    [switch]$UseSudo
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $PSCommandPath
$stageDir = "/tmp/polyedge-codex-bootstrap"
$remoteTarget = "$AdminUser@$HostName"
$publicKeyName = Split-Path -Leaf $PublicKeyPath

if (-not (Test-Path $PublicKeyPath)) {
    throw "Public key not found at $PublicKeyPath. Run install-local-codex-ssh.ps1 first."
}

$filesToCopy = @(
    (Join-Path $scriptDir "polyedge-codex-gate.sh"),
    (Join-Path $scriptDir "polyedge-codex-compose.sh"),
    (Join-Path $scriptDir "install-lxc-codex-access.sh"),
    $PublicKeyPath
)

& ssh $remoteTarget "mkdir -p $stageDir"
foreach ($file in $filesToCopy) {
    & scp $file "${remoteTarget}:$stageDir/"
}

$installCommand = "bash $stageDir/install-lxc-codex-access.sh --repo-root '$RepoRoot' --deploy-user '$DeployUser' --public-key-file '$stageDir/$publicKeyName'"
if ($UseSudo) {
    $installCommand = "sudo $installCommand"
}

& ssh $remoteTarget $installCommand
