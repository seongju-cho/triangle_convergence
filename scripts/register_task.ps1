<#
.SYNOPSIS
    Registers the daily channel-breakout scan in Windows Task Scheduler.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Time 07:30 -SmtpPassword "abcd efgh ijkl mnop"

.EXAMPLE
    # also catch the KOSPI close on the same day (lower cache_ttl to 6 in the config)
    powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Time 07:30,17:30
#>
param(
    [string[]]$Time = @("07:30"),
    [string]$TaskName = "ChannelMonitorDaily",
    [string]$Config = "monitor.config.json",
    [string]$SmtpPassword,
    [switch]$RunWhetherLoggedOn
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$bat = Join-Path $PSScriptRoot "run_daily.bat"

if (-not (Test-Path $bat)) { throw "run_daily.bat not found next to this script" }
if (-not (Test-Path (Join-Path $root ".venv\Scripts\python.exe"))) {
    Write-Warning "no .venv in $root - create it before the first run"
}

if ($SmtpPassword) {
    [Environment]::SetEnvironmentVariable("CHANNEL_MONITOR_SMTP_PASSWORD", $SmtpPassword, "User")
    Write-Host "stored CHANNEL_MONITOR_SMTP_PASSWORD as a user environment variable"
}

$action = New-ScheduledTaskAction -Execute $bat -Argument "`"$Config`"" -WorkingDirectory $root
$triggers = $Time | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 15)

$register = @{
    TaskName    = $TaskName
    Action      = $action
    Trigger     = $triggers
    Settings    = $settings
    Description = "Daily NASDAQ/KOSPI ascending-channel breakout scan with email alerts"
    Force       = $true
}

if ($RunWhetherLoggedOn) {
    # runs while logged off, but Windows must store the account password
    $cred = Get-Credential -Message "Account to run the task as (DOMAIN\user or .\user)"
    $register["User"] = $cred.UserName
    $register["Password"] = $cred.GetNetworkCredential().Password
    $register["RunLevel"] = "Limited"
}

Register-ScheduledTask @register | Out-Null

Write-Host "registered '$TaskName' at $($Time -join ', ')"
Write-Host "run it now:   Start-ScheduledTask -TaskName $TaskName"
Write-Host "check state:  Get-ScheduledTaskInfo -TaskName $TaskName"
Write-Host "remove it:    Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
