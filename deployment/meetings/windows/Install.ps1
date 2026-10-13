$ErrorActionPreference = 'Stop'
$settingsPath = Join-Path $PSScriptRoot 'settings.local.json'
if (-not (Test-Path -LiteralPath $settingsPath -PathType Leaf)) { throw 'Copy settings.example.json to settings.local.json and supply your own paths first.' }
$config = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
foreach ($key in @('distro','linuxUser','linuxPackagePath','repo','backups','project')) {
    if ([string]$config.$key -notmatch '^[A-Za-z0-9_./-]+$') { throw "Invalid $key" }
}
if ((Get-TimeZone).Id -ne $config.windowsTimeZone) { throw 'Windows timezone differs from configured schedule timezone.' }
$wsl = Join-Path $env:WINDIR 'System32\wsl.exe'
& $wsl -d $config.distro -u $config.linuxUser --exec python3 -m py_compile "$($config.linuxPackagePath)/backup/backup.py" "$($config.linuxPackagePath)/backup/scheduled.py" "$($config.linuxPackagePath)/backup/check_workers.py" "$($config.linuxPackagePath)/portal-start/start_portal.py"
if ($LASTEXITCODE -ne 0) { throw 'WSL package check failed. No tasks installed.' }
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$launcher = Join-Path $PSScriptRoot 'Launch.ps1'
foreach ($mode in @('startup','backup')) {
    $trigger = if ($mode -eq 'startup') { New-ScheduledTaskTrigger -AtLogOn -User $user } else { New-ScheduledTaskTrigger -Daily -At '03:00' }
    $action = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`" -Mode $mode"
    Register-ScheduledTask -TaskName "Onyx Meetings $mode" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
}
Write-Host 'Tasks installed. No services started now. Existing tasks under other names are not disabled.'
