param([Parameter(Mandatory=$true)][ValidateSet('startup','backup')][string]$Mode)
$ErrorActionPreference = 'Stop'
$config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'settings.local.json') -Raw | ConvertFrom-Json
foreach ($key in @('distro','linuxUser','linuxPackagePath','repo','backups','project')) {
    if ([string]$config.$key -notmatch '^[A-Za-z0-9_./-]+$') { throw "Invalid or missing $key (spaces are not supported)." }
}
foreach ($key in @('linuxPackagePath','repo','backups')) {
    if (-not ([string]$config.$key).StartsWith('/')) { throw "$key must be an absolute Linux path." }
}
$script = if ($Mode -eq 'backup') { 'backup/scheduled.py' } else { 'portal-start/start_portal.py' }
$wsl = Join-Path $env:WINDIR 'System32\wsl.exe'
$logDir = Join-Path $env:LOCALAPPDATA 'OnyxMeetings\launcher-logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $Mode + '-' + [guid]::NewGuid().ToString('N')
$stdin = Join-Path $logDir "$stamp.stdin.txt"
[System.IO.File]::WriteAllText($stdin, '')
try {
    # Values above exclude whitespace/quotes; Start-Process joins arguments into a command line.
    $arguments = @('-d', $config.distro, '-u', $config.linuxUser, '--exec', 'env',
        "MEETINGS_PROJECT=$($config.project)", "MEETINGS_REPO=$($config.repo)",
        "MEETINGS_BACKUPS=$($config.backups)", 'python3', '-u', "$($config.linuxPackagePath)/$script")
    $process = Start-Process -FilePath $wsl -ArgumentList $arguments -WindowStyle Hidden `
        -RedirectStandardInput $stdin -RedirectStandardOutput (Join-Path $logDir "$stamp.stdout.log") `
        -RedirectStandardError (Join-Path $logDir "$stamp.stderr.log") -Wait -PassThru
    $code = $process.ExitCode
    if ($null -eq $code) { throw 'WSL did not return an exit code.' }
    "Exit code: $code" | Set-Content (Join-Path $logDir "$stamp.result.txt")
    exit $code
}
catch {
    $_ | Out-String | Set-Content (Join-Path $logDir "$stamp.error.txt")
    exit 1
}
finally {
    Remove-Item -LiteralPath $stdin -ErrorAction SilentlyContinue
}
