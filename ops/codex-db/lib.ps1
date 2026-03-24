Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-CodexDbStateDir {
    $baseDir = Join-Path $env:LOCALAPPDATA "PolyEdge\codex-db"
    if (-not (Test-Path $baseDir)) {
        New-Item -ItemType Directory -Force -Path $baseDir | Out-Null
    }
    return $baseDir
}

function Get-CodexDbUtf8NoBomEncoding {
    return [System.Text.UTF8Encoding]::new($false)
}

function Get-CodexDbUnlockPath {
    return (Join-Path (Get-CodexDbStateDir) "write-unlock.json")
}

function Get-CodexDbAuditPath {
    return (Join-Path (Get-CodexDbStateDir) "query-audit.jsonl")
}

function Get-CodexDbDefaultEnvPath {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("read", "write")]
        [string]$Mode
    )

    $repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    if ($Mode -eq "read") {
        return (Join-Path $repoRoot ".env.codex-db")
    }

    return (Join-Path $repoRoot ".env")
}

function Read-CodexEnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        throw "Environment file not found: $Path"
    }

    $values = @{}
    foreach ($line in Get-Content $Path) {
        if ($line -match '^\s*$') {
            continue
        }
        if ($line -match '^\s*#') {
            continue
        }
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            continue
        }

        $name = $matches[1]
        $rawValue = $matches[2].Trim()
        if (
            ($rawValue.StartsWith('"') -and $rawValue.EndsWith('"')) -or
            ($rawValue.StartsWith("'") -and $rawValue.EndsWith("'"))
        ) {
            $rawValue = $rawValue.Substring(1, $rawValue.Length - 2)
        }
        $values[$name] = $rawValue
    }

    return $values
}

function Get-CodexDbConfig {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("read", "write")]
        [string]$Mode,
        [string]$EnvPath
    )

    if (-not $EnvPath) {
        $EnvPath = Get-CodexDbDefaultEnvPath -Mode $Mode
    }

    $config = Read-CodexEnvFile -Path $EnvPath
    foreach ($key in @("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")) {
        if (-not $config.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($config[$key])) {
            throw "Missing required key '$key' in $EnvPath"
        }
    }

    if ($Mode -eq "read" -and $config["POSTGRES_PASSWORD"] -match '^(CHANGEME|BOOTSTRAP_REQUIRED|REPLACE_)') {
        throw "Read-only credentials in $EnvPath are placeholders. Run bootstrap-readonly-role.ps1 first."
    }

    return [pscustomobject]@{
        Host     = $config["POSTGRES_HOST"]
        Port     = $config["POSTGRES_PORT"]
        User     = $config["POSTGRES_USER"]
        Password = $config["POSTGRES_PASSWORD"]
        Database = $config["POSTGRES_DB"]
        EnvPath  = $EnvPath
    }
}

function Get-PsqlPath {
    $command = Get-Command psql -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "psql was not found on PATH."
    }
    return $command.Source
}

function Get-CodexDbQueryText {
    param(
        [string]$Sql,
        [string]$File
    )

    if ([string]::IsNullOrWhiteSpace($Sql) -and [string]::IsNullOrWhiteSpace($File)) {
        throw "Specify either -Sql or -File."
    }
    if (-not [string]::IsNullOrWhiteSpace($Sql) -and -not [string]::IsNullOrWhiteSpace($File)) {
        throw "Use only one of -Sql or -File."
    }

    if (-not [string]::IsNullOrWhiteSpace($File)) {
        if (-not (Test-Path $File)) {
            throw "SQL file not found: $File"
        }
        return [System.IO.File]::ReadAllText((Resolve-Path $File))
    }

    return $Sql
}

function Assert-NoPsqlMetaCommands {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SqlText
    )

    $lineNumber = 0
    foreach ($line in ($SqlText -split "`r?`n")) {
        $lineNumber += 1
        if ($line -match '^\s*\\') {
            throw "psql meta-command rejected on line $lineNumber."
        }
    }
}

function Get-CodexDbQueryPreview {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SqlText
    )

    foreach ($line in ($SqlText -split "`r?`n")) {
        $trimmed = $line.Trim()
        if ($trimmed) {
            if ($trimmed.Length -gt 200) {
                return $trimmed.Substring(0, 200)
            }
            return $trimmed
        }
    }

    return ""
}

function Get-CodexDbQueryHash {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SqlText
    )

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($SqlText)
    $hash = [System.Security.Cryptography.SHA256]::Create()
    try {
        $result = $hash.ComputeHash($bytes)
    } finally {
        $hash.Dispose()
    }
    return ([System.BitConverter]::ToString($result)).Replace("-", "").ToLowerInvariant()
}

function Get-CodexDbUnlockState {
    $unlockPath = Get-CodexDbUnlockPath
    if (-not (Test-Path $unlockPath)) {
        return $null
    }

    try {
        $state = Get-Content $unlockPath -Raw | ConvertFrom-Json
    } catch {
        return $null
    }

    if (-not $state.expiresAtUtc) {
        return $null
    }

    try {
        $expiresAt = [datetime]::Parse(
            $state.expiresAtUtc,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [System.Globalization.DateTimeStyles]::AdjustToUniversal
        )
    } catch {
        return $null
    }

    if ($expiresAt -le (Get-Date).ToUniversalTime()) {
        Remove-Item $unlockPath -Force -ErrorAction SilentlyContinue
        return $null
    }

    return [pscustomobject]@{
        ExpiresAtUtc = $expiresAt
        Minutes      = $state.minutes
        ApprovedBy   = $state.approvedBy
    }
}

function Assert-CodexDbWriteUnlocked {
    $state = Get-CodexDbUnlockState
    if (-not $state) {
        throw "Write mode is locked. Run .\ops\codex-db\unlock-write.ps1 -Minutes 5 first."
    }
    return $state
}

function Write-CodexDbAuditEntry {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Entry
    )

    $auditPath = Get-CodexDbAuditPath
    $payload = [pscustomobject]$Entry | ConvertTo-Json -Compress
    Add-Content -Path $auditPath -Value $payload -Encoding UTF8
}

function Get-CodexDbResultSummary {
    param(
        [string[]]$StdOutLines,
        [string[]]$StdErrLines,
        [int]$ExitCode
    )

    $combined = @()
    if ($StdOutLines) {
        $combined += $StdOutLines
    }
    if ($StdErrLines) {
        $combined += $StdErrLines
    }

    $meaningful = @($combined | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($meaningful.Count -eq 0) {
        return "exit=$ExitCode"
    }

    for ($i = $meaningful.Count - 1; $i -ge 0; $i--) {
        $line = $meaningful[$i].Trim()
        if ($line -match '^\(\d+\s+rows?\)$') {
            return $line
        }
        if ($line -match '^(SELECT|UPDATE|DELETE|INSERT|ALTER|CREATE|DROP|GRANT|REVOKE|TRUNCATE)\b') {
            return $line
        }
    }

    return $meaningful[$meaningful.Count - 1].Trim()
}

function New-CodexDbSessionSql {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("read", "write")]
        [string]$Mode,
        [Parameter(Mandatory = $true)]
        [string]$SqlText
    )

    $sessionSetup = @(
        "SET client_min_messages = warning;"
        "SET statement_timeout = '15s';"
        "SET lock_timeout = '5s';"
    )

    if ($Mode -eq "read") {
        $sessionSetup += @(
            "SET application_name = 'codex_db_ro';"
            "SET default_transaction_read_only = on;"
        )
    } else {
        $sessionSetup += "SET application_name = 'codex_db_rw';"
    }

    return (($sessionSetup + $SqlText.Trim()) -join [Environment]::NewLine) + [Environment]::NewLine
}
