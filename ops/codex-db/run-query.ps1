[CmdletBinding()]
param(
    [string]$Sql,
    [string]$File,
    [switch]$Write,
    [string]$ReadEnvPath,
    [string]$WriteEnvPath
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot "lib.ps1")

$mode = if ($Write) { "write" } else { "read" }
$startedAt = Get-Date
$sqlText = ""
$sqlHash = ""
$preview = ""
$envPath = if ($mode -eq "write") { $WriteEnvPath } else { $ReadEnvPath }
$resolvedEnvPath = $envPath
$config = $null
$psqlPath = $null
$sessionSql = ""
$resultSummary = ""
$succeeded = $false

$tempDir = Get-CodexDbStateDir
$sqlPath = Join-Path $tempDir ("query-" + [guid]::NewGuid().ToString("N") + ".sql")
$stdoutPath = Join-Path $tempDir ("query-" + [guid]::NewGuid().ToString("N") + ".stdout.log")
$stderrPath = Join-Path $tempDir ("query-" + [guid]::NewGuid().ToString("N") + ".stderr.log")

$previousPassword = $env:PGPASSWORD
$process = $null
$stdoutLines = @()
$stderrLines = @()
$exitCode = 1

try {
    $sqlText = Get-CodexDbQueryText -Sql $Sql -File $File
    Assert-NoPsqlMetaCommands -SqlText $sqlText
    $sqlHash = Get-CodexDbQueryHash -SqlText $sqlText
    $preview = Get-CodexDbQueryPreview -SqlText $sqlText

    if ($mode -eq "write") {
        $null = Assert-CodexDbWriteUnlocked
    }

    $config = Get-CodexDbConfig -Mode $mode -EnvPath $envPath
    $resolvedEnvPath = $config.EnvPath
    $sessionSql = New-CodexDbSessionSql -Mode $mode -SqlText $sqlText
    [System.IO.File]::WriteAllText($sqlPath, $sessionSql, (Get-CodexDbUtf8NoBomEncoding))

    $psqlPath = Get-PsqlPath
    $env:PGPASSWORD = $config.Password
    $args = @(
        "-X"
        "-v", "ON_ERROR_STOP=1"
        "-h", $config.Host
        "-p", $config.Port
        "-U", $config.User
        "-d", $config.Database
        "-f", $sqlPath
    )

    $process = Start-Process `
        -FilePath $psqlPath `
        -ArgumentList $args `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -NoNewWindow `
        -PassThru `
        -Wait

    $exitCode = $process.ExitCode
    if (Test-Path $stdoutPath) {
        $stdoutLines = @(Get-Content $stdoutPath)
    }
    if (Test-Path $stderrPath) {
        $stderrLines = @(Get-Content $stderrPath)
    }

    foreach ($line in $stdoutLines) {
        Write-Output $line
    }
    foreach ($line in $stderrLines) {
        [Console]::Error.WriteLine($line)
    }

    if ($exitCode -ne 0) {
        throw "psql exited with code $exitCode."
    }
    $succeeded = $true
} catch {
    $resultSummary = $_.Exception.Message
    throw
} finally {
    if ($null -eq $previousPassword) {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    } else {
        $env:PGPASSWORD = $previousPassword
    }

    $durationMs = [math]::Round(((Get-Date) - $startedAt).TotalMilliseconds)
    if (-not $resultSummary) {
        $resultSummary = Get-CodexDbResultSummary -StdOutLines $stdoutLines -StdErrLines $stderrLines -ExitCode $exitCode
    }
    Write-CodexDbAuditEntry @{
        timestampUtc = (Get-Date).ToUniversalTime().ToString("o")
        mode         = $mode
        sqlHash      = $sqlHash
        preview      = $preview
        succeeded    = $succeeded
        result       = $resultSummary
        durationMs   = $durationMs
        envPath      = $resolvedEnvPath
    }

    foreach ($path in @($sqlPath, $stdoutPath, $stderrPath)) {
        if (Test-Path $path) {
            Remove-Item $path -Force -ErrorAction SilentlyContinue
        }
    }
}
