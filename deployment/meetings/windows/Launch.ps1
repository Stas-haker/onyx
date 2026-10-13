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
& $wsl -d $config.distro -u $config.linuxUser --exec env "MEETINGS_PROJECT=$($config.project)" "MEETINGS_REPO=$($config.repo)" "MEETINGS_BACKUPS=$($config.backups)" python3 -u "$($config.linuxPackagePath)/$script"
exit $LASTEXITCODE
